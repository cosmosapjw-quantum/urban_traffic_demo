"""Homogeneous one-lane drift plus FIFO fluid server, metres/seconds/vehicles.

All moving mass shares one continuous distance clock. Exit waiting is a point
queue with a global storage bound, not a spatial kinematic-wave solution. Source
amounts are boundary batches at step starts, in declared tie order. Different
physical vehicle laws must not be mixed into this homogeneous lane closure.
"""

from dataclasses import dataclass, replace
import math
from .active_suffix.common import BudgetExceeded


@dataclass(frozen=True, slots=True)
class Lane:
    length_m: float = 100.0
    speed_mps: float = 10.0
    entry_rate: float = 1.0
    exit_rate: float = 1.0
    storage: float = 30.0
    restart_rate: float = 0.2
    base_stop_rate: float = 0.0
    interaction_rate: float = 0.2

    def __post_init__(self):
        positive = (
            self.length_m,
            self.speed_mps,
            self.entry_rate,
            self.exit_rate,
            self.storage,
            self.restart_rate,
        )
        if any(not math.isfinite(x) or x <= 0 for x in positive):
            raise ValueError("positive finite lane scales required")
        if any(not math.isfinite(x) or x < 0 for x in (self.base_stop_rate, self.interaction_rate)):
            raise ValueError("invalid stopping rates")


@dataclass(frozen=True, slots=True)
class Waiting:
    tag: str
    mass: float
    born_s: float


@dataclass(frozen=True, slots=True)
class Cohort:
    tag: str
    mass: float
    born_s: float
    entry_s: float
    target_m: float


@dataclass(frozen=True, slots=True)
class Departure:
    tag: str
    mass: float
    start_s: float
    end_s: float
    born_s: float
    entry_s: float


@dataclass(frozen=True, slots=True)
class ClockState:
    time_s: float = 0.0
    progress_m: float = 0.0
    activity: float = 1.0
    waiting: tuple[Waiting, ...] = ()
    inside: tuple[Cohort, ...] = ()
    released: float = 0.0
    admitted: float = 0.0
    completed: float = 0.0
    birth_moment: float = 0.0
    entry_moment: float = 0.0
    exit_moment: float = 0.0
    vehicle_metres: float = 0.0

    @property
    def occupancy(self):
        return math.fsum(c.mass for c in self.inside)

    @property
    def pending_mass(self):
        return math.fsum(c.mass for c in self.waiting)

    @property
    def network_vehicle_seconds(self):
        return (self.admitted - self.completed) * self.time_s - self.entry_moment + self.exit_moment

    @property
    def system_vehicle_seconds(self):
        return (self.released - self.completed) * self.time_s - self.birth_moment + self.exit_moment


def distance_clock(dt, p, speed, alpha, nu):
    if (
        not all(map(math.isfinite, (dt, p, speed, alpha, nu)))
        or dt < 0
        or not 0 <= p <= 1
        or speed <= 0
        or alpha <= 0
        or nu < 0
    ):
        raise ValueError("invalid clock parameters")
    rate = alpha + nu
    if not math.isfinite(rate):
        raise ValueError("combined rate overflow")
    if dt == 0:
        return 0.0, p
    eq = alpha / rate
    z = rate * dt
    change = -math.expm1(-z)
    # Positive weighted mean; series resolves rest-start O(dt^2) displacement.
    f = change / z if math.isfinite(z) else 0.0
    g = z * (0.5 + z * (-1 / 6 + z * (1 / 24 + z * (-1 / 120 + z / 720)))) if z < 1e-3 else 1 - f
    distance = speed * dt * (p * f + eq * g)
    if not math.isfinite(distance):
        raise ArithmeticError("distance clock overflow")
    return distance, p * (1 - change) + eq * change


def clock_time(distance, p, speed, alpha, nu):
    """Same characteristic's first hit under frozen rates; no frozen entry speed."""
    distance_clock(0.0, p, speed, alpha, nu)
    if not math.isfinite(distance) or distance < 0:
        raise ValueError("invalid distance")
    if distance == 0:
        return 0.0
    high = max(1.0, distance / (speed * alpha / (alpha + nu)))
    while distance_clock(high, p, speed, alpha, nu)[0] < distance:
        high *= 2
        if not math.isfinite(high):
            raise ArithmeticError("clock bracket overflow")
    low = 0.0
    for _ in range(70):
        mid = (low + high) / 2
        if distance_clock(mid, p, speed, alpha, nu)[0] >= distance:
            high = mid
        else:
            low = mid
    return high


def _rate(lane, tag, receiving):
    if receiving is None:
        return lane.exit_rate
    if tag not in receiving:
        raise ValueError("missing downstream commodity supply")
    value = receiving[tag]
    if not math.isfinite(value) or value < 0:
        raise ValueError("invalid downstream supply rate")
    return min(lane.exit_rate, value)


def _check(lane, state):
    totals = (
        state.released,
        state.admitted,
        state.completed,
        state.birth_moment,
        state.entry_moment,
        state.exit_moment,
        state.vehicle_metres,
    )
    if any(not math.isfinite(x) or x < 0 for x in totals):
        raise ValueError("invalid cumulative state ledger")
    if (
        not math.isfinite(state.time_s)
        or state.time_s < 0
        or not math.isfinite(state.progress_m)
        or state.progress_m < 0
    ):
        raise ValueError("invalid state clock")
    if not math.isfinite(state.activity) or not 0 <= state.activity <= 1:
        raise ValueError("invalid state activity")
    if any(
        not math.isfinite(c.mass) or c.mass <= 0 or not c.tag for c in state.waiting + state.inside
    ):
        raise ValueError("invalid state cohort")
    if any(a.target_m > b.target_m for a, b in zip(state.inside, state.inside[1:])):
        raise ValueError("entry order was not preserved")
    tol = 1e-9 * max(1.0, state.released)
    if (
        abs(state.released - state.admitted - state.pending_mass) > tol
        or abs(state.admitted - state.completed - state.occupancy) > tol
        or state.occupancy > lane.storage + 1e-9 * max(1.0, lane.storage)
    ):
        raise ArithmeticError("lane mass or finite-storage ledger")


def advance(lane, state, dt, offers=(), receiving=None, record_budget=10000):
    """Atomic boundary admission, frozen-density drift, ordered exact-time service.

    Storage freed during this step is available next step: conservative boundary
    splitting. Service may start at a characteristic's within-step arrival time.
    Strict FIFO is only for this declared shared lane, not all city directions.
    """
    _check(lane, state)
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError("positive finite step required")
    if isinstance(record_budget, bool) or not isinstance(record_budget, int) or record_budget < 1:
        raise ValueError("positive integer record budget required")
    pending = list(state.waiting)
    inside = list(state.inside)
    t = state.time_s
    born = 0.0
    for tag, mass in tuple(offers):
        if not isinstance(tag, str) or not tag or not math.isfinite(mass) or mass < 0:
            raise ValueError("invalid batch tag or nonnegative mass")
        if mass > 0:
            pending.append(Waiting(tag, mass, t))
            born += mass
    for c in pending + inside:
        _rate(lane, c.tag, receiving)
    available = min(lane.entry_rate * dt, max(0.0, lane.storage - state.occupancy))
    admitted = 0.0
    remaining = []
    for c in pending:
        m = min(c.mass, available)
        available -= m
        admitted += m
        if m > 0:
            inside.append(Cohort(c.tag, m, c.born_s, t, state.progress_m + lane.length_m))
        if m < c.mass:
            remaining.append(replace(c, mass=c.mass - m))
    occupied = math.fsum(c.mass for c in inside)
    nu = lane.base_stop_rate + lane.interaction_rate * (occupied / lane.storage) ** 2
    dx, activity = distance_clock(dt, state.activity, lane.speed_mps, lane.restart_rate, nu)
    moved = math.fsum(c.mass * min(dx, max(0.0, c.target_m - state.progress_m)) for c in inside)
    cursor = 0.0
    departures = []
    left = []
    exit_moment = state.exit_moment
    completed = state.completed
    for i, c in enumerate(inside):
        distance = max(0.0, c.target_m - state.progress_m)
        if distance > dx:
            left.extend(inside[i:])
            break
        ready = clock_time(distance, state.activity, lane.speed_mps, lane.restart_rate, nu)
        start = max(cursor, ready)
        rate = _rate(lane, c.tag, receiving)
        if start >= dt or rate == 0:
            left.extend(inside[i:])
            break
        amount = min(c.mass, rate * (dt - start))
        end = start + amount / rate
        departures.append(Departure(c.tag, amount, t + start, t + end, c.born_s, c.entry_s))
        completed += amount
        exit_moment += amount * (2 * t + start + end) / 2
        cursor = end
        if amount < c.mass:
            left.append(replace(c, mass=c.mass - amount))
            left.extend(inside[i + 1 :])
            break
    if len(left) + len(remaining) > record_budget:
        exc = BudgetExceeded("ordered lane cohort budget")
        exc.checkpoint = state
        raise exc
    out = ClockState(
        t + dt,
        state.progress_m + dx,
        activity,
        tuple(remaining),
        tuple(left),
        state.released + born,
        state.admitted + admitted,
        completed,
        state.birth_moment + born * t,
        state.entry_moment + admitted * t,
        exit_moment,
        state.vehicle_metres + moved,
    )
    _check(lane, out)
    return out, tuple(departures)


def quote_admission(lane, state, tag, mass, receiving=None):
    """Frozen-rate cost of a hypothetical newly admitted batch: first,last,mean.

    Includes every earlier cohort's readiness and FIFO service. Assumes fixed
    supply and rates, no future competing arrivals, and immediate admission.
    This is a conditional prediction, not a claim to know future congestion.
    External waiting is excluded. For interaction_rate=0 and constant supply it
    matches the same drift/server run; a blocked predecessor gives infinity.
    """
    _check(lane, state)
    if not math.isfinite(mass) or mass <= 0 or not isinstance(tag, str) or not tag:
        raise ValueError("positive probe mass and tag required")
    if state.waiting or state.occupancy + mass > lane.storage:
        raise ValueError("quote requires available immediate admission")
    nu = (
        lane.base_stop_rate + lane.interaction_rate * ((state.occupancy + mass) / lane.storage) ** 2
    )
    probe = Cohort(tag, mass, state.time_s, state.time_s, state.progress_m + lane.length_m)
    cursor = 0.0
    for c in state.inside + (probe,):
        ready = clock_time(
            max(0.0, c.target_m - state.progress_m),
            state.activity,
            lane.speed_mps,
            lane.restart_rate,
            nu,
        )
        rate = _rate(lane, c.tag, receiving)
        if rate == 0:
            return (math.inf,) * 3
        first = max(cursor, ready)
        cursor = first + c.mass / rate
    return first, cursor, (first + cursor) / 2
