"""R01 costs in seconds: completed conditional means, never additive queue proxies."""

from dataclasses import dataclass
import math
import hashlib
from .city import reject


@dataclass(frozen=True, slots=True, order=True)
class CostKey:
    kind: str
    id: str
    vehicle_class: str

    def __post_init__(self):
        if self.kind not in ('link', 'route') or not self.id or not self.vehicle_class:
            reject('cost needs link/route identity and explicit vehicle class')


@dataclass(frozen=True, slots=True)
class CostObservation:
    key: CostKey
    seconds: float
    stamp_s: float
    start_s: float
    end_s: float
    mass_veh: float
    sensor_xy: tuple[float, float]
    source: str
    version: str
    population: str
    measure: str = 'completed conditional birth-to-exit mean; includes all recorded holds'

    def __post_init__(self):
        if (
            math.isnan(self.seconds) or self.seconds < 0
            or any(not math.isfinite(x) or x < 0 for x in (
                self.stamp_s, self.start_s, self.end_s, self.mass_veh))
            or self.mass_veh <= 0 or not self.start_s <= self.end_s <= self.stamp_s
            or not isinstance(self.sensor_xy, tuple) or len(self.sensor_xy) != 2
            or not all(map(math.isfinite, self.sensor_xy))
            or not self.source or not self.version or not self.measure or not self.population
        ):
            reject('invalid completed cost observation')


def completed_route_observations(model, state, *, since_s, sensor_xy, version):
    """Read only fully completed outlet records from the *same* T04 physics.

    since_s selects records by their completion endpoint (exclusive). Repeated
    polling must advance this cursor. This is a conditional sample, not a whole
    population ETA. Birth moments cannot identify link entry moments: link costs
    must come from separately instrumented completed link measurements.
    """
    model.check(state)
    now = state.road.time_s
    if not math.isfinite(since_s) or not 0 <= since_s <= now:
        reject('observation cursor must precede current physical time')
    rows = []
    for tag in sorted({e.tag for e in state.events if e.destination is None}):
        events = tuple(e for e in state.events if e.tag == tag and e.destination is None
                       and since_s < e.end_s <= now)
        if not events:
            continue
        mass = math.fsum(e.mass for e in events)
        elapsed = math.fsum(e.mass * (e.start_s + e.end_s) / 2 - e.birth_moment
                            for e in events)
        rows.append(CostObservation(
            CostKey('route', tag, model.network.vehicle_classes[tag].name),
            elapsed / mass, now, min(e.start_s for e in events),
            max(e.end_s for e in events), mass, sensor_xy[tag], 'T04_completed_outlet', version,
            hashlib.sha256(repr((model.identity, tag, events)).encode()).hexdigest()))
    return tuple(rows)


def conditional_eta_error(prediction, realized):
    """Compare matching estimand/population only; no joint correlation inference."""
    if (prediction.key != realized.key or prediction.measure != realized.measure
            or prediction.population != realized.population):
        reject('ETA comparison requires matching key and declared population/measure')
    if not math.isfinite(prediction.seconds) or not math.isfinite(realized.seconds):
        return None
    return prediction.seconds - realized.seconds
