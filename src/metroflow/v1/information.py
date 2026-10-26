"""R01 immutable causal channels. No present-truth input to the decision surface.

Reports are completed measurements or explicitly labelled predictions. Scheduling
is an external fixed clock, never triggered by an unseen incident. Communication
coordinates are a declared metric, unrelated to vehicle interaction distance.
"""

from dataclasses import dataclass, asdict
import hashlib
import json
import math
from ..active_suffix.common import BudgetExceeded
from .city import reject
from .observations import CostKey, CostObservation


@dataclass(frozen=True, slots=True)
class PriorCost:
    key: CostKey
    seconds: float
    version: str
    measure: str

    def __post_init__(self):
        if math.isnan(self.seconds) or self.seconds < 0 or not self.version or not self.measure:
            reject('explicit nonnegative static prior, version and measure required')


@dataclass(frozen=True, slots=True)
class Channel:
    id: str
    kind: str
    coverage: tuple[CostKey, ...]
    radius_m: float
    latency_s: float
    propagation_mps: float
    max_age_s: float

    def __post_init__(self):
        if (not self.id or self.kind not in ('direct', 'v2v', 'server', 'history')
                or not isinstance(self.coverage, tuple) or len(set(self.coverage)) != len(self.coverage)
                or math.isnan(self.radius_m) or self.radius_m < 0
                or not math.isfinite(self.latency_s) or self.latency_s < 0
                or not math.isfinite(self.propagation_mps) or self.propagation_mps <= 0
                or not math.isfinite(self.max_age_s) or self.max_age_s < 0
                or (self.kind in ('direct', 'v2v') and not math.isfinite(self.radius_m))):
            reject('invalid channel coverage/radius/latency/propagation/age')


@dataclass(frozen=True, slots=True)
class Report:
    channel_id: str
    observation: CostObservation


@dataclass(frozen=True, slots=True)
class InformationState:
    model_id: str
    time_s: float
    reports: tuple[Report, ...] = ()


@dataclass(frozen=True, slots=True)
class DeliveredCost:
    key: CostKey
    seconds: float
    source: str
    version: str
    stamp_s: float | None
    age_s: float | None
    delivered_s: float | None
    measure: str
    status: str
    population: str | None


@dataclass(frozen=True, slots=True)
class DecisionObservation:
    decision: str
    time_s: float
    costs: tuple[DeliveredCost, ...]
    coverage_fraction: float


class InformationModel:
    """Finite age horizon, explicit prior fallback, atomic budget failure.

    Server radius may be infinite. Its finite max_age bounds useful history even
    then: a report too far away to arrive within this age can never be used.
    Newest eligible stamp wins; equal stamps use declared channel precedence.
    Observer location can change at en-route boundaries without truth access.
    """

    def __init__(self, priors, channels, *, record_budget=10000):
        self.priors, self.channels = tuple(priors), tuple(channels)
        if (not self.priors or len({p.key for p in self.priors}) != len(self.priors)
                or len({c.id for c in self.channels}) != len(self.channels)
                or isinstance(record_budget, bool) or not isinstance(record_budget, int)
                or record_budget < 1):
            reject('unique cost keys/channels and positive integer budget required')
        keys = {p.key for p in self.priors}
        if any(not set(c.coverage) <= keys for c in self.channels):
            reject('channel coverage requires declared prior for every key')
        self.record_budget = record_budget
        payload = dict(contract='R01_completed_causal_cost_v1', priors=[asdict(p) for p in self.priors],
                       channels=[asdict(c) for c in self.channels], budget=record_budget)
        # Infinity means explicitly unavailable prior or unlimited server radius.
        self.identity = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def initial(self):
        return InformationState(self.identity, 0.0)

    def check(self, state):
        if state.model_id != self.identity or not math.isfinite(state.time_s) or state.time_s < 0:
            reject('information state belongs to another contract')
        if len(state.reports) > self.record_budget:
            reject('invalid information checkpoint record count')
        for r in state.reports:
            self._validate_report(r, state.time_s)

    def _validate_report(self, report, now):
        channel = next((c for c in self.channels if c.id == report.channel_id), None)
        if channel is None or report.observation.key not in channel.coverage:
            reject('report outside declared channel coverage')
        if report.observation.stamp_s > now:
            reject('future or unfinished report cannot be published')
        prior = next(p for p in self.priors if p.key == report.observation.key)
        if report.observation.measure != prior.measure:
            reject('report/prior estimands differ; cannot add or substitute unlike time costs')
        return channel

    def advance(self, state, now, reports=()):
        self.check(state)
        if not math.isfinite(now) or now < state.time_s:
            reject('information clock must be monotone')
        incoming = tuple(reports)
        for r in incoming:
            self._validate_report(r, now)
        kept = []
        for r in state.reports + incoming:
            c = self._validate_report(r, now)
            if now - r.observation.stamp_s <= c.max_age_s and r not in kept:
                if any(old.channel_id == r.channel_id
                       and old.observation.key == r.observation.key
                       and old.observation.stamp_s == r.observation.stamp_s
                       for old in kept):
                    reject('conflicting reports at same channel/key/stamp')
                kept.append(r)
        # No averaging away time/correlation marks to fit a record budget.
        if len(kept) > self.record_budget:
            exc = BudgetExceeded('R01 information history record budget')
            exc.checkpoint = state
            raise exc
        kept.sort(key=lambda r: (r.observation.stamp_s, r.channel_id,
                                 r.observation.key, repr(r.observation)))
        return InformationState(self.identity, float(now), tuple(kept))

    def observe(self, state, observer_xy, *, decision='origin'):
        self.check(state)
        if (decision not in ('origin', 'en_route') or len(observer_xy) != 2
                or not all(map(math.isfinite, observer_xy))):
            reject('explicit origin/en_route decision and finite observer coordinates required')
        now = state.time_s
        costs = []
        for prior in self.priors:
            eligible = []
            for rank, channel in enumerate(self.channels):
                for report in state.reports:
                    o = report.observation
                    if report.channel_id != channel.id or o.key != prior.key:
                        continue
                    distance = math.dist(observer_xy, o.sensor_xy)
                    delivered = o.stamp_s + channel.latency_s + distance / channel.propagation_mps
                    if (distance <= channel.radius_m and delivered <= now
                            and now - o.stamp_s <= channel.max_age_s):
                        eligible.append((o.stamp_s, -rank, repr(o), delivered, o, channel))
            if eligible:
                _, _, _, delivered, o, c = max(eligible, key=lambda x: x[:3])
                costs.append(DeliveredCost(prior.key, o.seconds, c.id + ':' + o.source,
                                           o.version, o.stamp_s, now - o.stamp_s, delivered,
                                           o.measure, 'DELIVERED', o.population))
            else:
                costs.append(DeliveredCost(prior.key, prior.seconds, 'DECLARED_PRIOR',
                                           prior.version, None, None, None, prior.measure,
                                           'DECLARED_PRIOR', None))
        coverage = sum(c.status == 'DELIVERED' for c in costs) / len(costs)
        return DecisionObservation(decision, now, tuple(costs), coverage)
