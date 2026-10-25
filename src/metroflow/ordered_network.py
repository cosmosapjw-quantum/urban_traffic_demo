"""Conservative split network of explicitly declared homogeneous FIFO groups."""

from dataclasses import dataclass
from .ordered_lane import Lane, ClockState, Waiting
from .active_suffix.common import Signal, BudgetExceeded
from dataclasses import asdict, replace
from collections import defaultdict
import hashlib
import json
import math
from .ordered_lane import Cohort, distance_clock, clock_time
from .active_suffix.common import _factor, _signal_green
from .active_suffix.node import allocate


@dataclass(frozen=True, slots=True)
class Group:
    id: str
    tail: str
    head: str
    physics: Lane
    priority: float = 1.0
    signal: Signal | None = None


@dataclass(frozen=True, slots=True)
class Route:
    tag: str
    groups: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Transfer:
    tag: str
    source: str
    destination: str | None
    mass: float
    start_s: float
    end_s: float
    born_s: float


@dataclass(frozen=True, slots=True)
class NetworkState:
    model_id: str
    time_s: float
    lanes: tuple[ClockState, ...]
    pending: tuple[Waiting, ...] = ()
    released: float = 0.0
    completed: float = 0.0
    birth_moment: float = 0.0
    exit_moment: float = 0.0
    source_wait_seconds: float = 0.0
    transfer_hold_seconds: float = 0.0

    @property
    def system_vehicle_seconds(self):
        return (self.released - self.completed) * self.time_s - self.birth_moment + self.exit_moment


class Network:
    """Common drift, per-group FIFO, simultaneous priority merge, finite receiving.

    Downstream space is reserved from OLD occupancy. Internal departures arrive
    at the next boundary; this numerical holding time is explicit. Source batches
    are also admitted at the end boundary, after reserved internal traffic. The
    model is not an LWR wave solver or a full lane-changing model. Different
    physical classes require separate groups, not silent mixing of their laws.
    """

    def __init__(
        self, groups, routes, dt_s=1.0, windows=(), record_budget=10000, allowed_turns=None
    ):
        self.groups = tuple(sorted(groups, key=lambda g: g.id))
        self.routes = tuple(routes)
        self.dt = dt_s
        self.windows = tuple(windows)
        self.record_budget = record_budget
        if not math.isfinite(dt_s) or dt_s <= 0:
            raise ValueError("positive finite step")
        if (
            isinstance(record_budget, bool)
            or not isinstance(record_budget, int)
            or record_budget < 1
        ):
            raise ValueError("positive record budget")
        self.index = {g.id: i for i, g in enumerate(self.groups)}
        if not self.groups or len(self.index) != len(self.groups):
            raise ValueError("nonempty unique groups")
        self.route = {r.tag: r.groups for r in self.routes}
        if not self.routes or len(self.route) != len(self.routes):
            raise ValueError("nonempty unique route tags")
        self.next = {}
        self.first = {}
        self.incoming = defaultdict(list)

        def aligned(x):
            return abs(x / dt_s - round(x / dt_s)) < 1e-9

        for i, g in enumerate(self.groups):
            if not g.id or g.tail == g.head or not math.isfinite(g.priority) or g.priority <= 0:
                raise ValueError("invalid directed group")
            self.incoming[g.head].append(i)
            s = g.signal
            if s and (
                not all(map(math.isfinite, (s.cycle_s, s.green_s, s.offset_s)))
                or s.cycle_s <= 0
                or not 0 <= s.green_s <= s.cycle_s
                or not all(aligned(x) for x in (s.cycle_s, s.green_s, s.offset_s))
            ):
                raise ValueError("signal boundaries must align with step")
        for r in self.routes:
            if (
                not r.tag
                or not r.groups
                or len(set(r.groups)) != len(r.groups)
                or any(k not in self.index for k in r.groups)
            ):
                raise ValueError("nonempty loopless declared route")
            self.first[r.tag] = self.index[r.groups[0]]
            for k, edge in enumerate(r.groups):
                i = self.index[edge]
                j = self.index[r.groups[k + 1]] if k + 1 < len(r.groups) else -1
                if j >= 0:
                    if self.groups[i].head != self.groups[j].tail or (
                        allowed_turns is not None and (edge, self.groups[j].id) not in allowed_turns
                    ):
                        raise ValueError("illegal route transition")
                self.next[r.tag, i] = j
        for key, a, b, f in self.windows:
            if (
                key not in self.index
                or not all(map(math.isfinite, (a, b, f)))
                or not 0 <= a < b
                or not 0 <= f <= 1
            ):
                raise ValueError("invalid closure")
            if not aligned(a) or not aligned(b):
                raise ValueError("closure boundary must align")
        payload = (
            tuple(asdict(g) for g in self.groups),
            tuple(asdict(r) for r in self.routes),
            dt_s,
            self.windows,
            record_budget,
        )
        self.identity = hashlib.sha256(
            json.dumps(payload, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()

    def initial(self):
        return NetworkState(self.identity, 0.0, tuple(ClockState() for _ in self.groups))

    def check(self, state):
        if state.model_id != self.identity or len(state.lanes) != len(self.groups):
            raise ValueError("network identity mismatch")
        values = (
            state.time_s,
            state.released,
            state.completed,
            state.birth_moment,
            state.exit_moment,
            state.source_wait_seconds,
            state.transfer_hold_seconds,
        )
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("nonfinite or negative network ledger")
        for g, s in zip(self.groups, state.lanes):
            totals = (
                s.time_s,
                s.progress_m,
                s.released,
                s.admitted,
                s.completed,
                s.birth_moment,
                s.entry_moment,
                s.exit_moment,
                s.vehicle_metres,
            )
            if any(not math.isfinite(v) or v < 0 for v in totals):
                raise ValueError("invalid local cumulative ledger")
            if (
                abs(s.admitted - s.completed - s.occupancy) > 1e-9 * max(1.0, s.admitted)
                or s.released != s.admitted
            ):
                raise ArithmeticError("local vehicle ledger")
            if abs(s.time_s - state.time_s) > 1e-9 or not 0 <= s.activity <= 1 or s.waiting:
                raise ValueError("inconsistent lane clock")
            if any(
                not math.isfinite(c.mass)
                or c.mass <= 0
                or (c.tag, self.index[g.id]) not in self.next
                for c in s.inside
            ):
                raise ValueError("invalid lane commodity")
            if any(a.target_m > b.target_m for a, b in zip(s.inside, s.inside[1:])):
                raise ArithmeticError("lane order violated")
            if s.occupancy > g.physics.storage + 1e-9 * max(1.0, g.physics.storage):
                raise ArithmeticError("finite storage exceeded")
        if any(
            p.tag not in self.route or not math.isfinite(p.mass) or p.mass <= 0
            for p in state.pending
        ):
            raise ValueError("invalid external commodity")
        occupancy = math.fsum(x.occupancy for x in state.lanes)
        pending = math.fsum(x.mass for x in state.pending)
        if abs(state.released - state.completed - occupancy - pending) > 1e-9 * max(
            1.0, state.released
        ):
            raise ArithmeticError("network mass ledger")
        residence = (
            math.fsum(x.network_vehicle_seconds for x in state.lanes)
            + state.source_wait_seconds
            + state.transfer_hold_seconds
        )
        if abs(residence - state.system_vehicle_seconds) > 1e-8 * max(1.0, residence):
            raise ArithmeticError("road/source/transfer residence ledger")

    def step(self, state, offers=()):
        try:
            return self._step(state, tuple(offers))
        except BudgetExceeded as e:
            e.checkpoint = state
            raise

    def _step(self, state, offers):
        self.check(state)
        dt = self.dt
        t = state.time_s
        end = t + dt
        external = list(state.pending)
        born = 0.0
        for tag, mass in offers:
            if tag not in self.route or not math.isfinite(mass) or mass < 0:
                raise ValueError("invalid source batch")
            if mass > 0:
                external.append(Waiting(tag, mass, t))
                born += mass
        factors = [_factor(g.id, t + dt / 2, self.windows) for g in self.groups]
        receiving_rate = [g.physics.entry_rate * f for g, f in zip(self.groups, factors)]
        capacity = [
            min(rate * dt, max(0.0, g.physics.storage - s.occupancy))
            for rate, g, s in zip(receiving_rate, self.groups, state.lanes)
        ]
        free = list(capacity)
        reserved = [0.0] * len(self.groups)
        adv = []
        queues = {}
        events = []
        for i, (g, s) in enumerate(zip(self.groups, state.lanes)):
            lane = g.physics
            nu = lane.base_stop_rate + lane.interaction_rate * (s.occupancy / lane.storage) ** 2
            dx, p = distance_clock(dt, s.activity, lane.speed_mps, lane.restart_rate, nu)
            advance_m = math.fsum(
                c.mass * min(dx, max(0.0, c.target_m - s.progress_m)) for c in s.inside
            )
            adv.append(
                replace(
                    s,
                    time_s=end,
                    progress_m=s.progress_m + dx,
                    activity=p,
                    vehicle_metres=s.vehicle_metres + advance_m,
                )
            )
            queues[i] = [
                [
                    c,
                    c.mass,
                    clock_time(
                        max(0.0, c.target_m - s.progress_m),
                        s.activity,
                        lane.speed_mps,
                        lane.restart_rate,
                        nu,
                    )
                    if c.target_m - s.progress_m <= dx + 1e-10
                    else math.inf,
                ]
                for c in s.inside
            ]
        position = [0] * len(self.groups)
        # Each receiving group belongs to one tail node, so independent junctions
        # cannot duplicate its budget. Within a junction the heads compete jointly.
        for node, inc in sorted(self.incoming.items()):
            cursor = 0.0
            iterations = 0
            while cursor < dt:
                iterations += 1
                if iterations > self.record_budget + 2 * len(inc):
                    raise BudgetExceeded("junction event budget")
                heads = {}
                future = []
                for i in inc:
                    k = position[i]
                    if k >= len(queues[i]):
                        continue
                    c, mass, ready = queues[i][k]
                    if ready > cursor + 1e-10:
                        if ready < dt:
                            future.append(ready)
                        continue
                    heads[i] = (c, mass, self.next[c.tag, i])
                sending = {
                    i: self.groups[i].physics.exit_rate
                    * factors[i]
                    * float(_signal_green(self.groups[i].signal, t + dt / 2))
                    for i in heads
                }
                receiving = {
                    j: (receiving_rate[j] if free[j] > 0 else 0.0)
                    if j >= 0
                    else math.fsum(sending.values())
                    for _, _, j in heads.values()
                }
                demand = {(i, j): sending[i] for i, (_, _, j) in heads.items()}
                flow = (
                    allocate(
                        demand, sending, receiving, {i: self.groups[i].priority for i in heads}
                    )
                    if demand
                    else {}
                )
                flow = {key: value for key, value in flow.items() if value > 0}
                if not flow:
                    if future:
                        cursor = min(future)
                        continue
                    break
                dest_rate = defaultdict(float)
                limits = [dt - cursor] + [r - cursor for r in future if r > cursor]
                for (i, j), rate in flow.items():
                    limits.append(heads[i][1] / rate)
                    if j >= 0:
                        dest_rate[j] += rate
                limits.extend(free[j] / rate for j, rate in dest_rate.items())
                h = min(limits)
                if h <= 0:
                    raise ArithmeticError("nonpositive junction progress")
                for (i, j), rate in sorted(flow.items()):
                    c, mass, _ = heads[i]
                    amount = min(mass, rate * h)
                    if abs(amount - mass) <= 1e-13 * max(1.0, mass):
                        amount = mass
                    queues[i][position[i]][1] -= amount
                    if queues[i][position[i]][1] <= 0:
                        position[i] += 1
                    events.append(
                        Transfer(
                            c.tag,
                            self.groups[i].id,
                            self.groups[j].id if j >= 0 else None,
                            amount,
                            t + cursor,
                            t + cursor + h,
                            c.born_s,
                        )
                    )
                    if j >= 0:
                        free[j] = max(0.0, free[j] - amount)
                        reserved[j] += amount
                    s = adv[i]
                    adv[i] = replace(
                        s,
                        completed=s.completed + amount,
                        exit_moment=s.exit_moment + amount * (t + cursor + h / 2),
                    )
                cursor += h
                if len(events) > self.record_budget:
                    raise BudgetExceeded("transfer record budget")
        for i, s in enumerate(adv):
            left = tuple(replace(c, mass=m) for c, m, _ in queues[i] if m > 0)
            adv[i] = replace(s, inside=left)
        sink = 0.0
        sink_moment = 0.0
        hold = 0.0

        def inject(i, tag, mass, born_s):
            s = adv[i]
            c = Cohort(tag, mass, born_s, end, s.progress_m + self.groups[i].physics.length_m)
            adv[i] = replace(
                s,
                inside=s.inside + (c,),
                released=s.released + mass,
                admitted=s.admitted + mass,
                birth_moment=s.birth_moment + mass * born_s,
                entry_moment=s.entry_moment + mass * end,
            )

        for e in sorted(events, key=lambda e: (e.start_s, e.end_s, e.source, e.tag)):
            if e.destination is None:
                sink += e.mass
                sink_moment += e.mass * (e.start_s + e.end_s) / 2
            else:
                inject(self.index[e.destination], e.tag, e.mass, e.born_s)
                hold += e.mass * (end - (e.start_s + e.end_s) / 2)
        remain = []
        source_wait = dt * math.fsum(p.mass for p in external)
        for p in external:
            i = self.first[p.tag]
            mass = min(p.mass, free[i])
            free[i] -= mass
            if mass > 0:
                inject(i, p.tag, mass, p.born_s)
            if mass < p.mass:
                remain.append(replace(p, mass=p.mass - mass))
        if sum(len(s.inside) for s in adv) + len(remain) > self.record_budget:
            raise BudgetExceeded("network cohort budget")
        out = NetworkState(
            self.identity,
            end,
            tuple(adv),
            tuple(remain),
            state.released + born,
            state.completed + sink,
            state.birth_moment + born * t,
            state.exit_moment + sink_moment,
            state.source_wait_seconds + source_wait,
            state.transfer_hold_seconds + hold,
        )
        self.check(out)
        for g, old, new in zip(self.groups, state.lanes, out.lanes):
            tol = 1e-9 * max(1.0, state.released + born)
            if (
                new.admitted - old.admitted
                > g.physics.entry_rate * dt * factors[self.index[g.id]] + tol
            ):
                raise ArithmeticError("entry capacity exceeded")
            if (
                new.completed - old.completed
                > g.physics.exit_rate * dt * factors[self.index[g.id]] + tol
            ):
                raise ArithmeticError("exit capacity exceeded")
        return out, tuple(events)
