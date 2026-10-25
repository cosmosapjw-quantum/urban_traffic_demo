"""Source-conditioned finite information on the unchanged packed physical model.

Observation histories, not present remote truth, determine route choice. The
network still uses the legacy activity closure; the separate continuous-speed
reference is not silently substituted only into perceived routing costs.
"""

from bisect import bisect_right
from copy import copy
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from .common import BudgetExceeded
from .packed import PackedModel


@dataclass(frozen=True, slots=True)
class Information:
    radius_m: float = 1000.0
    propagation_mps: float = 50.0
    latency_s: float = 2.0

    def __post_init__(self):
        if not all(map(math.isfinite, (self.radius_m, self.propagation_mps, self.latency_s))):
            raise ValueError("nonfinite information parameters")
        if self.radius_m < 0 or self.propagation_mps <= 0 or self.latency_s < 0:
            raise ValueError("invalid information support")


@dataclass(frozen=True, slots=True)
class CostFrame:
    stamp_s: float
    values: tuple[float, ...]

    def __post_init__(self):
        if not math.isfinite(self.stamp_s) or self.stamp_s < 0:
            raise ValueError("invalid observation timestamp")
        if any(math.isnan(x) or x < 0 for x in self.values):
            raise ValueError("negative or NaN time cost")


@dataclass(frozen=True, slots=True)
class CausalState:
    physical: object
    history: tuple[CostFrame, ...] = ()


def perceived(prior, distances, info, history, now):
    """Latest delivered report per sensor. Remote absence leaves static prior.

    Distance is the declared Euclidean communication metric, not a physical
    leader distance. No interpolation of future reports, no omniscient fallback.
    """
    if len(prior) != len(distances) or any(math.isnan(x) or x < 0 for x in prior):
        raise ValueError("prior and sensor shape/cost mismatch")
    if not math.isfinite(now) or now < 0 or any(not math.isfinite(d) or d < 0 for d in distances):
        raise ValueError("invalid query time or distance")
    stamps = tuple(f.stamp_s for f in history)
    if any(a >= b for a, b in zip(stamps, stamps[1:])) or any(
        len(f.values) != len(prior) for f in history
    ):
        raise ValueError("observation history must be strictly ordered and dimensioned")
    result = list(prior)
    for i, d in enumerate(distances):
        if d > info.radius_m:
            continue
        eligible = now - info.latency_s - d / info.propagation_mps
        j = bisect_right(stamps, eligible) - 1
        if j >= 0:
            result[i] = history[j].values[i]
    return tuple(result)


class _ObservedKernel(PackedModel):
    def _information_costs(self, state, costs, t):
        # The physical prediction uses the current interval; publish only when
        # that interval is complete. Current choices cannot see this new frame.
        self.emitted = CostFrame(t + self.cfg.dt_s, tuple(costs[r.id] for r in self.roads))
        if not self._refresh_needed(state, t, None):
            return None
        return tuple(
            dict(
                zip(
                    (r.id for r in self.roads),
                    perceived(self.static_prior, ds, info, self.observation_history, t),
                )
            )
            for ds, info in zip(self.distances, self.information)
        )

    def _refresh_needed(self, state, t, factors):
        # Unobserved true incidents must not leak through the refresh clock.
        return (
            state.last_choice_s < 0 or t - state.last_choice_s >= self.cfg.route_refresh_s - 1e-10
        )


class CausalPackedModel:
    """Decision support at fixed source sites, not per-vehicle/en-route belief.

    Each cost-frame contains one scalar per directed road. Storage depends on
    road count and delay horizon, not vehicle amount. Budget overflow preserves
    the input immutable state. Reusing old information is not a safety override.
    """

    def __init__(
        self,
        roads,
        demands,
        observer_xy,
        sensor_xy,
        information=None,
        config=None,
        allowed_turns=None,
        capacity_windows=(),
        conflicts=(),
        frame_budget=256,
    ):
        self.kernel = _ObservedKernel(
            roads, demands, config, allowed_turns, capacity_windows, conflicts
        )
        self.observers = tuple(tuple(p) for p in observer_xy)
        if len(self.observers) != len(self.kernel.demands):
            raise ValueError("one observer per demand schedule")
        keys = tuple(r.id for r in self.kernel.roads)
        if set(sensor_xy) != set(keys):
            raise ValueError("every directed road needs a declared sensor")
        self.sensors = tuple(tuple(sensor_xy[k]) for k in keys)
        if any(
            len(p) != 2 or not all(map(math.isfinite, p)) for p in self.observers + self.sensors
        ):
            raise ValueError("invalid communication coordinates")
        if isinstance(frame_budget, bool) or not isinstance(frame_budget, int) or frame_budget < 1:
            raise ValueError("invalid observation budget")
        self.frame_budget = frame_budget
        if information is None:
            information = Information()
        self.information = (
            (information,) * len(self.observers)
            if isinstance(information, Information)
            else tuple(information)
        )
        if len(self.information) != len(self.observers) or not all(
            isinstance(x, Information) for x in self.information
        ):
            raise ValueError("one information profile per observer")
        self.distances = tuple(tuple(math.dist(o, s) for s in self.sensors) for o in self.observers)
        self.prior = tuple(
            (
                r.length_m / r.free_speed_mps
                + (
                    (r.signal.cycle_s - r.signal.green_s) ** 2 / (2 * r.signal.cycle_s)
                    if r.signal
                    else 0.0
                )
            )
            if not r.signal or r.signal.green_s > 0
            else math.inf
            for r in self.kernel.roads
        )
        self.max_delay = max(
            (
                info.latency_s + d / info.propagation_mps
                for ds, info in zip(self.distances, self.information)
                for d in ds
                if d <= info.radius_m
            ),
            default=0.0,
        )

    def initial(self):
        return CausalState(self.kernel.initial())

    def step(self, state):
        # Per-call scratch object: neither the model's kernel nor input state is
        # mutated. Histories/fingerprints are replayable and branchable.
        local = copy(self.kernel)
        local.observation_history = state.history
        local.static_prior = self.prior
        local.distances = self.distances
        local.information = self.information
        try:
            physical = local.step(state.physical)
            history = state.history + (local.emitted,)
            cutoff = physical.tick * local.cfg.dt_s - self.max_delay
            # Retain a predecessor to the oldest still-needed query timestamp.
            index = max(0, bisect_right(tuple(f.stamp_s for f in history), cutoff) - 1)
            history = history[index:]
            if len(history) > self.frame_budget:
                raise BudgetExceeded("observation-history bound")
            return CausalState(physical, history)
        except BudgetExceeded as exc:
            exc.checkpoint = state
            raise

    def occupancy(self, state):
        return self.kernel.occupancy(state.physical)

    def fingerprint(self, state):
        # +inf is a valid unavailable cost; encode it explicitly for strict JSON.
        def finite(x):
            return x if math.isfinite(x) else "unavailable"

        payload = dict(
            contract="causal_source_cost_v1",
            physical=self.kernel.fingerprint(state.physical),
            observers=self.observers,
            sensors=self.sensors,
            information=[asdict(x) for x in self.information],
            frame_budget=self.frame_budget,
            history=[(f.stamp_s, [finite(x) for x in f.values]) for f in state.history],
        )
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
