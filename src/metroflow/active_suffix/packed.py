"""Causal aligned-grid clock with exact equal-mass arrival run compression.

This opt-in policy reuses the legacy physical, kinetic, routing and node update.
It removes two administrative ticks and uses trapezoidal system residence, but
retains time quantization and the legacy backlog/node splitting approximation.
No claim of exact within-tick congested flow, full FIFO or constant memory.
"""

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import math
from .engine import Model


@dataclass(frozen=True, slots=True)
class TransitRun:
    first_tick: int
    last_tick: int
    suffix: int
    mass_per_tick: float

    @property
    def mass(self):
        return (self.last_tick - self.first_tick + 1) * self.mass_per_tick


def pack_runs(events):
    """Canonical integer interval sweep; merge only EXACT equal positive rates.

    Each run describes many homogeneous flow bins, never individual cars. There
    is no positive-mass pruning or tolerance-based alteration of rates. fsum
    limits rounding in overlap sums; the mass ledger remains floating point.
    """
    groups = defaultdict(list)
    for e in events:
        if e.first_tick > e.last_tick or not math.isfinite(e.mass_per_tick) or e.mass_per_tick <= 0:
            raise ValueError("invalid transit run")
        groups[e.suffix].append(e)
    packed = []
    for sid, runs in sorted(groups.items()):
        changes = defaultdict(list)
        for k, e in enumerate(runs):
            changes[e.first_tick].append((k, e.mass_per_tick))
            changes[e.last_tick + 1].append((k, None))
        active = {}
        last = None
        rate = 0.0
        for at, updates in sorted(changes.items()):
            if last is not None and last < at and rate > 0:
                if (
                    packed
                    and packed[-1].suffix == sid
                    and packed[-1].last_tick + 1 == last
                    and packed[-1].mass_per_tick == rate
                ):
                    prev = packed.pop()
                    packed.append(TransitRun(prev.first_tick, at - 1, sid, rate))
                else:
                    packed.append(TransitRun(last, at - 1, sid, rate))
            for k, value in updates:
                if value is None:
                    active.pop(k)
                else:
                    active[k] = value
            rate = math.fsum(active.values())
            last = at
    return tuple(sorted(packed, key=lambda e: (e.first_tick, e.suffix, e.last_tick)))


class PackedModel(Model):
    """Fixed-step transport requires source/control boundaries aligned with dt.

    Flow admitted during [t,t+dt) is an aggregate bin, maturing during
    [t+ceil(tau/dt)*dt, t+(ceil(tau/dt)+1)*dt). Residence integrates the declared
    bin release/completion rates. Delays never round down. Exact free-flow holds
    when all link delays are integral multiples of dt and no constraints bind.
    """

    def __init__(
        self, roads, demands, config=None, allowed_turns=None, capacity_windows=(), conflicts=()
    ):
        from .common import Config

        roads = tuple(roads)
        demands = tuple(demands)
        capacity_windows = tuple(capacity_windows)
        cfg = config or Config()
        if not math.isfinite(cfg.dt_s) or cfg.dt_s <= 0:
            raise ValueError("invalid dt")
        times = [x for d in demands for x in (d.start_s, d.end_s)]
        times.extend(x for _, a, b, _ in capacity_windows for x in (a, b))
        times.extend(
            x
            for r in roads
            if r.signal
            for x in (r.signal.cycle_s, r.signal.green_s, r.signal.offset_s)
        )
        for t in times:
            z = t / cfg.dt_s
            if not math.isfinite(z) or abs(z - round(z)) > 1e-10:
                raise ValueError(
                    "source/signal/closure boundaries must be aligned to dt; use interval reference otherwise"
                )
        super().__init__(roads, demands, cfg, allowed_turns, capacity_windows, conflicts)

    def _mature(self, state):
        queues = dict(state.queues)
        future = []
        for e in state.transit:
            if not isinstance(e, TransitRun):
                raise ValueError("packed state contract required")
            count = max(0, min(state.tick, e.last_tick) - e.first_tick + 1)
            if count:
                queues[e.suffix] = queues.get(e.suffix, 0.0) + count * e.mass_per_tick
            first = e.first_tick + count
            if first <= e.last_tick:
                future.append(TransitRun(first, e.last_tick, e.suffix, e.mass_per_tick))
        return queues, future

    def _arrival(self, tick, delay, suffix, mass):
        due = tick - 1 + delay
        return TransitRun(due, due, suffix, mass)

    def _pack(self, future):
        return pack_runs(future)

    def _residence(self, state, occupied, released, completed, dt):
        old_stock = math.fsum(occupied) + math.fsum(state.pending)
        return state.vehicle_seconds + dt * (
            old_stock + 0.5 * (released - (completed - state.completed))
        )

    def fingerprint(self, state):
        return hashlib.sha256(
            ("packed_causal_grid_v1:" + super().fingerprint(state)).encode()
        ).hexdigest()
