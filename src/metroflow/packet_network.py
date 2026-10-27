"""Label-independent fluid packets on declared homogeneous shared lane groups.

Exactly simultaneous boundary entries are exchangeably mixed. This is an explicit
closure for unresolved within-step order, not a gauge transformation of a known
serial queue. Older packets remain ahead of newer packets. Equal fragments of
one packet are representation redundancy; different targets or future physical
laws are not. Retained route and birth moments support mass and mean-duration
observables, NOT individual identities or arbitrary age quantiles.
"""

from dataclasses import dataclass, replace, asdict
from collections import defaultdict
from types import MappingProxyType
from .foundation_kinetics import VehicleClass
import hashlib
import json as json
import math
from .ordered_network import Network as ParentNetwork
from .ordered_lane import distance_clock, clock_time
from .active_suffix.common import BudgetExceeded, _factor, _signal_green


@dataclass(frozen=True, slots=True)
class Part:
    tag: str
    remaining: tuple[str, ...]
    mass: float
    birth_moment: float
    entry_start_s: float | None = None
    entry_end_s: float | None = None


@dataclass(frozen=True, slots=True)
class Packet:
    target_m: float
    parts: tuple[Part, ...]

    @property
    def mass(self):
        return math.fsum(p.mass for p in self.parts)


@dataclass(frozen=True, slots=True)
class Pending:
    born_s: float
    parts: tuple[Part, ...]

    @property
    def mass(self):
        return math.fsum(p.mass for p in self.parts)


@dataclass(frozen=True, slots=True)
class Cell:
    progress_m: float = 0.0
    activity: float = 1.0
    packets: tuple[Packet, ...] = ()
    admitted: float = 0.0
    completed: float = 0.0
    entry_moment: float = 0.0
    exit_moment: float = 0.0
    vehicle_metres: float = 0.0
    speed_mps: float = 0.0
    latent: tuple[tuple[str, float], ...] = ()

    @property
    def occupancy(self):
        return math.fsum(p.mass for p in self.packets)

    def residence(self, t):
        return (self.admitted - self.completed) * t - self.entry_moment + self.exit_moment


@dataclass(frozen=True, slots=True)
class Event:
    tag: str
    source: str
    destination: str | None
    mass: float
    start_s: float
    end_s: float
    birth_moment: float


@dataclass(frozen=True, slots=True)
class ClassLedger:
    name: str
    released: float = 0.0
    completed: float = 0.0
    source_wait_seconds: float = 0.0
    exit_queue_seconds: float = 0.0
    transfer_hold_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class State:
    model_id: str
    time_s: float
    cells: tuple[Cell, ...]
    pending: tuple[tuple[Pending, ...], ...]
    released: float = 0.0
    completed: float = 0.0
    birth_moment: float = 0.0
    exit_moment: float = 0.0
    source_wait_seconds: float = 0.0
    transfer_hold_seconds: float = 0.0
    pre_entry_seconds: float = 0.0
    class_ledger: tuple[ClassLedger, ...] = ()

    @property
    def system_vehicle_seconds(self):
        return (self.released - self.completed) * self.time_s - self.birth_moment + self.exit_moment


def combine(parts):
    """Exact additive sufficient statistics at identical current clock target.

    Report tags remain separate observables but never determine physical order.
    This preserves the first birth moment; an age-dependent law needs more state.
    """
    groups = defaultdict(list)
    for p in parts:
        if p.mass > 0:
            groups[p.tag, p.remaining, p.entry_start_s, p.entry_end_s].append(p)
    return tuple(
        Part(
            tag,
            path,
            math.fsum(p.mass for p in values),
            math.fsum(p.birth_moment for p in values),
            entry_start,
            entry_end,
        )
        for (tag, path, entry_start, entry_end), values in sorted(
            groups.items(),
            key=lambda x: (
                x[0][0],
                x[0][1],
                -1.0 if x[0][2] is None else x[0][2],
                -1.0 if x[0][3] is None else x[0][3],
            ),
        )
    )


def _portion(parts, fraction):
    return tuple(
        replace(p, mass=p.mass * fraction, birth_moment=p.birth_moment * fraction)
        for p in parts
        if p.mass * fraction > 0
    )


def interval_packets(parts, target_m, record_budget):
    """Keep nonoverlapping entry intervals in FIFO order; mix only common slices.

    Incoming piecewise-constant fluxes are split at all their endpoints. Point
    admissions remain atoms. Birth first moments split proportionally within an
    input flux mark, as in the exchangeable parent observation contract.
    """
    parts = tuple(parts)
    edges = sorted({x for p in parts for x in (p.entry_start_s, p.entry_end_s)})
    packets = []
    records = 0
    for k, a in enumerate(edges):
        point = combine(p for p in parts if p.entry_start_s == p.entry_end_s == a)
        if point:
            records += len(point)
            if records > record_budget:
                raise BudgetExceeded("entry interval record budget")
            packets.append(Packet(target_m, point))
        if k + 1 == len(edges):
            break
        b = edges[k + 1]
        segment = combine(
            replace(
                p,
                mass=p.mass * (b - a) / (p.entry_end_s - p.entry_start_s),
                birth_moment=p.birth_moment * (b - a) / (p.entry_end_s - p.entry_start_s),
                entry_start_s=a,
                entry_end_s=b,
            )
            for p in parts
            if p.entry_start_s <= a and p.entry_end_s >= b and p.entry_end_s > p.entry_start_s
        )
        if segment:
            records += len(segment)
            if records > record_budget:
                raise BudgetExceeded("entry interval record budget")
            packets.append(Packet(target_m, segment))
    return tuple(packets)


def _rates(heads, sending, receiving, priorities):
    """Weighted progressive filling of packet rates, with fixed turn fractions.

    q_i<=S_i and sum_i beta_ij q_i<=R_j. A blocked positive fraction blocks its
    entire shared packet. This is max-min fairness, not a claim of globally
    maximal throughput or of all traffic-engineering node invariance axioms.
    """
    q = {i: 0.0 for i in heads}
    active = {i for i in heads if sending[i] > 0}
    while active:
        bounds = [(sending[i] - q[i]) / priorities[i] for i in active]
        for j, supply in receiving.items():
            slope = math.fsum(heads[i].get(j, 0.0) * priorities[i] for i in active)
            if slope > 0:
                used = math.fsum(heads[i].get(j, 0.0) * q[i] for i in heads)
                bounds.append(max(0.0, supply - used) / slope)
        step = max(0.0, min(bounds))
        for i in active:
            q[i] += step * priorities[i]
        saturated = {
            j
            for j, supply in receiving.items()
            if supply - math.fsum(heads[i].get(j, 0.0) * q[i] for i in heads)
            <= 1e-12 * max(1.0, supply)
        }
        remove = {
            i
            for i in active
            if sending[i] - q[i] <= 1e-12 * max(1.0, sending[i])
            or any(heads[i].get(j, 0.0) > 0 for j in saturated)
        }
        if not remove:
            raise ArithmeticError("progressive supply allocation stalled")
        active -= remove
    return q


class PacketNetwork:
    def __init__(
        self,
        groups,
        routes,
        dt_s=1.0,
        windows=(),
        record_budget=10000,
        allowed_turns=None,
        *,
        vehicle_classes=None,
        space_capacities_m=None,
        standing_gap_m=0.0,
        event_budget=None,
        motion=None,
        preserve_entry_intervals=False,
    ):
        parent = ParentNetwork(groups, routes, dt_s, windows, record_budget, allowed_turns)
        self.groups = parent.groups
        self.routes = parent.route
        self.index = parent.index
        self.dt = parent.dt
        self.windows = parent.windows
        self.record_budget = record_budget
        self.incoming = parent.incoming
        self.identity = hashlib.sha256(
            ("exchangeable_boundary_packet_v2_birth:" + parent.identity).encode()
        ).hexdigest()
        if (vehicle_classes is None) != (space_capacities_m is None):
            raise ValueError("class-aware storage requires both tag classes and lane space")
        if not math.isfinite(standing_gap_m) or standing_gap_m < 0:
            raise ValueError("finite nonnegative standing gap required")
        if event_budget is not None and (
            isinstance(event_budget, bool) or not isinstance(event_budget, int) or event_budget < 1
        ):
            raise ValueError("positive integer junction event budget required")
        self.event_budget = event_budget
        if motion is not None and not isinstance(getattr(motion, "identity", None), str):
            raise ValueError("motion policy requires a frozen identity")
        self.motion = motion
        self.preserve_entry_intervals = bool(preserve_entry_intervals)
        self.vehicle_classes = MappingProxyType(dict(vehicle_classes or {}))
        self.space_capacities_m = MappingProxyType(dict(space_capacities_m or {}))
        self.standing_gap_m = standing_gap_m
        self.physical_storage = vehicle_classes is not None
        if self.physical_storage:
            if set(self.vehicle_classes) != set(self.routes) or set(self.space_capacities_m) != set(
                self.index
            ):
                raise ValueError("every route class and group space must be declared")
            if any(not isinstance(c, VehicleClass) for c in self.vehicle_classes.values()) or any(
                not math.isfinite(x) or x <= 0 for x in self.space_capacities_m.values()
            ):
                raise ValueError("valid physical classes and positive lane space required")
            by_name = {}
            for c in self.vehicle_classes.values():
                if c.name in by_name and by_name[c.name] != c:
                    raise ValueError("class name has incompatible physical parameters")
                by_name[c.name] = c
            self.class_names = tuple(sorted(by_name))
        else:
            self.class_names = ()
        if motion is not None and not self.physical_storage:
            raise ValueError("finite-response motion requires physical class storage")
        if (
            self.physical_storage
            or event_budget is not None
            or preserve_entry_intervals
            or motion is not None
        ):
            payload = dict(
                parent=self.identity,
                classes={k: asdict(v) for k, v in self.vehicle_classes.items()},
                space=dict(self.space_capacities_m),
                gap=standing_gap_m,
                event_budget=event_budget,
                motion=motion.identity if motion else None,
                entry_intervals=self.preserve_entry_intervals,
            )
            if motion is None and not preserve_entry_intervals:
                payload.pop("motion")
                payload.pop("entry_intervals")
            self.identity = hashlib.sha256(
                json.dumps(payload, sort_keys=True, allow_nan=False).encode()
            ).hexdigest()

    def footprint(self, tag):
        return (
            self.vehicle_classes[tag].length_m + self.standing_gap_m
            if self.physical_storage
            else 1.0
        )

    def occupied_space(self, cell):
        return math.fsum(
            p.mass * self.footprint(p.tag) for packet in cell.packets for p in packet.parts
        )

    def space_capacity(self, group):
        return self.space_capacities_m[group.id] if self.physical_storage else group.physics.storage

    def initial(self, start_s=0.0):
        if (
            not math.isfinite(start_s)
            or start_s < 0
            or abs(start_s / self.dt - round(start_s / self.dt)) > 1e-9
        ):
            raise ValueError("nonnegative grid-aligned time origin")
        return State(
            self.identity,
            start_s,
            tuple(Cell() for _ in self.groups),
            tuple(() for _ in self.groups),
            class_ledger=tuple(ClassLedger(name) for name in self.class_names),
        )

    def counts(self, state):
        return dict(
            packets=sum(len(c.packets) for c in state.cells) + sum(len(p) for p in state.pending),
            parts=sum(len(p.parts) for c in state.cells for p in c.packets)
            + sum(len(p.parts) for q in state.pending for p in q),
        )

    def rebase_clock(self, state, offsets):
        """Pure coordinate origin change Z_i -> Z_i+k_i, target_i -> target_i+k_i."""
        if len(offsets) != len(self.groups) or not all(map(math.isfinite, offsets)):
            raise ValueError("invalid clock offsets")
        self.check(state)
        return replace(
            state,
            cells=tuple(
                replace(
                    c,
                    progress_m=c.progress_m + k,
                    packets=tuple(replace(p, target_m=p.target_m + k) for p in c.packets),
                )
                for c, k in zip(state.cells, offsets)
            ),
        )

    def check(self, s):
        if (
            s.model_id != self.identity
            or len(s.cells) != len(self.groups)
            or len(s.pending) != len(self.groups)
        ):
            raise ValueError("network/state identity mismatch")
        values = (
            s.time_s,
            s.released,
            s.completed,
            s.birth_moment,
            s.exit_moment,
            s.source_wait_seconds,
            s.transfer_hold_seconds,
            s.pre_entry_seconds,
        )
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("invalid cumulative ledger")
        for i, (g, c, waiting) in enumerate(zip(self.groups, s.cells, s.pending)):
            if (
                not math.isfinite(c.progress_m)
                or not 0 <= c.activity <= 1
                or not math.isfinite(c.speed_mps)
                or c.speed_mps < 0
                or any(not math.isfinite(v) or not 0 <= v <= 1 for _, v in c.latent)
            ):
                raise ValueError("invalid distance clock")
            if any(
                not math.isfinite(v) or v < 0
                for v in (c.admitted, c.completed, c.entry_moment, c.exit_moment, c.vehicle_metres)
            ):
                raise ValueError("invalid cell ledger")
            if any(a.target_m > b.target_m + 1e-10 for a, b in zip(c.packets, c.packets[1:])):
                raise ArithmeticError("packet order")
            if any(a.born_s > b.born_s for a, b in zip(waiting, waiting[1:])):
                raise ArithmeticError("source order")
            for packet in c.packets + waiting:
                if not packet.parts:
                    raise ValueError("empty packet is not a state")
                if isinstance(packet, Packet) and not math.isfinite(packet.target_m):
                    raise ValueError("nonfinite target")
                if isinstance(packet, Pending) and not 0 <= packet.born_s <= s.time_s:
                    raise ValueError("invalid source time")
                for p in packet.parts:
                    if (
                        p.tag not in self.routes
                        or not p.remaining
                        or p.remaining[0] != g.id
                        or not math.isfinite(p.mass)
                        or p.mass <= 0
                        or not math.isfinite(p.birth_moment)
                        or not 0 <= p.birth_moment <= p.mass * s.time_s + 1e-8
                    ):
                        raise ValueError("invalid homogeneous part")
                    if (p.entry_start_s is None) != (p.entry_end_s is None) or (
                        p.entry_start_s is not None
                        and (
                            not all(map(math.isfinite, (p.entry_start_s, p.entry_end_s)))
                            or not 0 <= p.entry_start_s <= p.entry_end_s <= s.time_s + 1e-9
                        )
                    ):
                        raise ValueError("invalid retained boundary interval")
                    full = self.routes[p.tag]
                    if not any(full[k:] == p.remaining for k in range(len(full))):
                        raise ValueError("non-route suffix")
            if abs(c.admitted - c.completed - c.occupancy) > 1e-9 * max(1.0, c.admitted):
                raise ArithmeticError("cell mass ledger")
            capacity = self.space_capacity(g)
            if self.occupied_space(c) > capacity + 1e-9 * max(1.0, capacity):
                raise ArithmeticError("IMPLEMENTATION_ERROR: cell storage")
        if tuple(x.name for x in s.class_ledger) != self.class_names:
            raise ValueError("class ledger registry mismatch")
        if self.physical_storage and (
            abs(math.fsum(x.released for x in s.class_ledger) - s.released)
            > 1e-9 * max(1.0, s.released)
            or abs(math.fsum(x.completed for x in s.class_ledger) - s.completed)
            > 1e-9 * max(1.0, s.completed)
        ):
            raise ArithmeticError("IMPLEMENTATION_ERROR: class/global ledger mismatch")
        if self.physical_storage:
            for field in ("source_wait_seconds", "transfer_hold_seconds"):
                observed = math.fsum(getattr(x, field) for x in s.class_ledger)
                if abs(observed - getattr(s, field)) > 1e-8 * max(1.0, observed, getattr(s, field)):
                    raise ArithmeticError("IMPLEMENTATION_ERROR: class/global residence mismatch")
        for ledger in s.class_ledger:
            if any(
                not math.isfinite(x) or x < 0
                for x in (
                    ledger.released,
                    ledger.completed,
                    ledger.source_wait_seconds,
                    ledger.exit_queue_seconds,
                    ledger.transfer_hold_seconds,
                )
            ):
                raise ValueError("invalid class cumulative ledger")
            stored = math.fsum(
                p.mass
                for c in s.cells
                for packet in c.packets
                for p in packet.parts
                if self.vehicle_classes[p.tag].name == ledger.name
            )
            stored += math.fsum(
                p.mass
                for q in s.pending
                for packet in q
                for p in packet.parts
                if self.vehicle_classes[p.tag].name == ledger.name
            )
            if abs(ledger.released - ledger.completed - stored) > 1e-9 * max(1.0, ledger.released):
                raise ArithmeticError("IMPLEMENTATION_ERROR: class mass ledger")
        mass = math.fsum(c.occupancy for c in s.cells) + math.fsum(
            p.mass for q in s.pending for p in q
        )
        if abs(s.released - s.completed - mass) > 1e-9 * max(1.0, s.released):
            raise ArithmeticError("network mass ledger")
        residence = (
            math.fsum(c.residence(s.time_s) for c in s.cells)
            + s.source_wait_seconds
            + s.transfer_hold_seconds
            + s.pre_entry_seconds
        )
        if abs(residence - s.system_vehicle_seconds) > 1e-8 * max(1.0, residence):
            raise ArithmeticError("residence ledger")

    def step(self, state, offers=()):
        """Road-source batches born now: backward-compatible physical behavior."""
        return self.step_measures(
            state, tuple((tag, mass, mass * state.time_s) for tag, mass in offers)
        )

    def step_measures(self, state, offers=()):
        """Accept (tag, mass [veh], original birth first moment [veh*s]).

        Earlier journey age changes observations only, not road admission order.
        pre_entry_seconds records already-accrued residence before this network
        boundary. Road/source/transfer residence remains separately measurable.
        Current homogeneity makes a first moment sufficient for mean duration,
        not for age-dependent dynamics or travel-time quantiles.
        """
        if self.motion is not None:
            return self.advance_interval(state, self.dt, offers)
        try:
            return self._step(state, tuple(offers))
        except (BudgetExceeded, ArithmeticError) as e:
            e.checkpoint = state
            raise

    def advance_interval(self, state, dt_s, offers=()):
        """Explicit variable interval; control boundaries may not be crossed.

        Source offers may additionally retain (entry_start,entry_end), both
        no later than the current clock. No global model dt is mutated.
        """
        if not math.isfinite(dt_s) or dt_s <= 0:
            raise ValueError("positive finite interval required")
        t, end = state.time_s, state.time_s + dt_s
        for _, a, b, _ in self.windows:
            if t + 1e-10 < a < end - 1e-10 or t + 1e-10 < b < end - 1e-10:
                raise ValueError("interval crosses a closure boundary")
        for g in self.groups:
            sig = g.signal
            if sig:
                for phase in (0.0, sig.green_s):
                    edge = (
                        sig.offset_s
                        + phase
                        + (math.floor((t - sig.offset_s - phase) / sig.cycle_s) + 1) * sig.cycle_s
                    )
                    if t + 1e-10 < edge < end - 1e-10:
                        raise ValueError("interval crosses a signal boundary")
        try:
            return self._step(state, tuple(offers), dt_s)
        except (BudgetExceeded, ArithmeticError) as exc:
            exc.checkpoint = state
            raise

    def _step(self, s, offers, interval_s=None):
        self.check(s)
        t = s.time_s
        dt = self.dt if interval_s is None else interval_s
        end = t + dt
        ledger = {x.name: x for x in s.class_ledger}

        def class_add(tag, field, value):
            if self.physical_storage:
                key = self.vehicle_classes[tag].name
                ledger[key] = replace(ledger[key], **{field: getattr(ledger[key], field) + value})

        pending = [list(q) for q in s.pending]
        new = defaultdict(list)
        born = 0.0
        birth1 = 0.0
        inherited = 0.0
        for offer in offers:
            if len(offer) not in (3, 5):
                raise ValueError("source offer needs mass/birth and optional interval")
            tag, mass, birth = offer[:3]
            a, b = offer[3:] if len(offer) == 5 else (None, None)
            if a is not None and (
                not all(map(math.isfinite, (a, b))) or not 0 <= a <= b <= t + 1e-9
            ):
                raise ValueError("source interval must precede current clock")
            if (
                tag not in self.routes
                or not all(map(math.isfinite, (mass, birth)))
                or mass < 0
                or birth < 0
                or birth > mass * t
                or (mass == 0 and birth != 0)
            ):
                raise ValueError("invalid source mass or original birth moment")
            if mass:
                route = self.routes[tag]
                new[self.index[route[0]]].append(Part(tag, route, mass, birth, a, b))
                born += mass
                birth1 += birth
                inherited += mass * t - birth
                class_add(tag, "released", mass)
        for i, parts in new.items():
            pending[i].append(Pending(t, combine(parts)))
        source_wait = dt * math.fsum(p.mass for q in pending for p in q)
        for q in pending:
            for packet in q:
                for part in packet.parts:
                    class_add(part.tag, "source_wait_seconds", dt * part.mass)
        factor = [_factor(g.id, t + dt / 2, self.windows) for g in self.groups]
        receive = [g.physics.entry_rate * f for g, f in zip(self.groups, factor)]
        free = [rate * dt for rate in receive]  # remaining vehicle admission increments
        free_space = [
            max(0.0, self.space_capacity(g) - self.occupied_space(c))
            for g, c in zip(self.groups, s.cells)
        ]
        cells = []
        queues = {}
        motions = {}
        for i, (g, c) in enumerate(zip(self.groups, s.cells)):
            p = g.physics
            if self.motion is not None:
                if not c.packets and getattr(self.motion, "empty_stationary", False):
                    # No packet can invoke passage here; the declared empty T02
                    # law returns exactly these values, including latent reset.
                    dx, speed, latent = 0.0, 0.0, ()
                else:
                    motions[i] = self.motion.advance(self, g, c, t, dt, factor[i])
                    dx, speed, latent = motions[i].distance_m, motions[i].speed_mps, motions[i].latent
                activity = c.activity
            else:
                nu = p.base_stop_rate + p.interaction_rate * (c.occupancy / p.storage) ** 2
                dx, activity = distance_clock(dt, c.activity, p.speed_mps, p.restart_rate, nu)
                speed, latent = c.speed_mps, c.latent
            moved = math.fsum(
                x.mass * min(dx, max(0.0, x.target_m - c.progress_m)) for x in c.packets
            )
            cells.append(
                replace(
                    c,
                    progress_m=c.progress_m + dx,
                    activity=activity,
                    speed_mps=speed,
                    latent=latent,
                    vehicle_metres=c.vehicle_metres + moved,
                )
            )
            queues[i] = [
                [
                    packet,
                    (
                        motions[i].passage(max(0.0, packet.target_m - c.progress_m))
                        if self.motion is not None
                        else clock_time(
                            max(0.0, packet.target_m - c.progress_m),
                            c.activity,
                            p.speed_mps,
                            p.restart_rate,
                            nu,
                        )
                    )
                    if packet.target_m - c.progress_m <= dx + 1e-10
                    else math.inf,
                ]
                for packet in c.packets
            ]
        position = [0] * len(cells)
        events = []
        incoming = defaultdict(list)
        incoming_marks = defaultdict(list)
        sink = 0.0
        exit1 = 0.0
        hold = 0.0
        for _, inc in sorted(self.incoming.items()):
            cursor = 0.0
            iterations = 0
            while cursor < dt:
                iterations += 1
                if iterations > (
                    self.record_budget + 2 * len(inc)
                    if self.event_budget is None
                    else self.event_budget
                ):
                    raise BudgetExceeded("packet junction budget")
                heads = {}
                future = []
                beta = {}
                beta_space = {}
                for i in inc:
                    k = position[i]
                    if k >= len(queues[i]):
                        continue
                    packet, ready = queues[i][k]
                    if ready > cursor + 1e-10:
                        if ready < dt:
                            future.append(ready)
                        continue
                    heads[i] = packet
                    dest = defaultdict(list)
                    for p in packet.parts:
                        j = self.index[p.remaining[1]] if len(p.remaining) > 1 else -1
                        dest[j].append(p.mass)
                    beta[i] = {j: math.fsum(v) / packet.mass for j, v in dest.items()}
                    beta_space[i] = {
                        j: math.fsum(
                            p.mass * self.footprint(p.tag)
                            for p in packet.parts
                            if (self.index[p.remaining[1]] if len(p.remaining) > 1 else -1) == j
                        )
                        / packet.mass
                        for j in dest
                    }
                sending = {
                    i: self.groups[i].physics.exit_rate
                    * factor[i]
                    * float(_signal_green(self.groups[i].signal, t + dt / 2))
                    for i in heads
                }
                receiving = {
                    j: receive[j] if free[j] > 1e-13 and free_space[j] > 1e-13 else 0.0
                    for i in heads
                    for j in beta[i]
                    if j >= 0
                }
                rates = (
                    _rates(beta, sending, receiving, {i: self.groups[i].priority for i in heads})
                    if heads
                    else {}
                )
                rates = {i: r for i, r in rates.items() if r > 0}
                if not rates:
                    if future:
                        cursor = min(future)
                        continue
                    break
                dest_rates = {
                    j: math.fsum(beta[i].get(j, 0.0) * r for i, r in rates.items())
                    for j in receiving
                }
                space_rates = {
                    j: math.fsum(beta_space[i].get(j, 0.0) * r for i, r in rates.items())
                    for j in receiving
                }
                limits = [dt - cursor] + [x - cursor for x in future if x > cursor]
                limits.extend(heads[i].mass / r for i, r in rates.items())
                limits.extend(free[j] / r for j, r in dest_rates.items() if r > 0)
                limits.extend(free_space[j] / r for j, r in space_rates.items() if r > 0)
                h = min(limits)
                if h <= 0 or cursor + h == cursor:
                    raise ArithmeticError("packet event resolution exhausted")
                mid = t + cursor + h / 2
                for i, rate in sorted(rates.items()):
                    packet = heads[i]
                    ready = queues[i][position[i]][1]
                    fraction = min(1.0, rate * h / packet.mass)
                    if 1 - fraction < 1e-14:
                        fraction = 1.0
                    served = _portion(packet.parts, fraction)
                    mass = math.fsum(p.mass for p in served)
                    if fraction == 1:
                        position[i] += 1
                    else:
                        queues[i][position[i]][0] = replace(
                            packet, parts=_portion(packet.parts, 1 - fraction)
                        )
                    cells[i] = replace(
                        cells[i],
                        completed=cells[i].completed + mass,
                        exit_moment=cells[i].exit_moment + mass * mid,
                    )
                    for p in served:
                        class_add(
                            p.tag,
                            "exit_queue_seconds",
                            p.mass
                            * max(
                                0.0,
                                cursor + h / 2 - ready,
                            ),
                        )
                        j = self.index[p.remaining[1]] if len(p.remaining) > 1 else -1
                        events.append(
                            Event(
                                p.tag,
                                self.groups[i].id,
                                self.groups[j].id if j >= 0 else None,
                                p.mass,
                                t + cursor,
                                t + cursor + h,
                                p.birth_moment,
                            )
                        )
                        if j >= 0:
                            free[j] = max(0.0, free[j] - p.mass)
                            free_space[j] = max(0.0, free_space[j] - p.mass * self.footprint(p.tag))
                            class_add(p.tag, "transfer_hold_seconds", p.mass * (end - mid))
                            incoming[j].append(
                                replace(
                                    p,
                                    remaining=p.remaining[1:],
                                    **(
                                        dict(entry_start_s=t + cursor, entry_end_s=t + cursor + h)
                                        if self.preserve_entry_intervals
                                        else {}
                                    ),
                                )
                            )
                            if self.motion is not None:
                                incoming_marks[j].append(
                                    self.motion.transfer_mark(
                                        self, p.tag, p.mass, motions[i], cursor + h / 2
                                    )
                                )
                            hold += p.mass * (end - mid)
                        else:
                            sink += p.mass
                            class_add(p.tag, "completed", p.mass)
                            exit1 += p.mass * mid
                cursor += h
                if len(events) > self.record_budget:
                    raise BudgetExceeded("packet transfer budget")
        for i, c in enumerate(cells):
            for packet, ready in queues[i][position[i] :]:
                for part in packet.parts:
                    class_add(part.tag, "exit_queue_seconds", part.mass * max(0.0, dt - ready))
            cells[i] = replace(c, packets=tuple(p for p, _ in queues[i][position[i] :]))
            if self.motion is not None:
                active_classes = {
                    self.vehicle_classes[p.tag].name
                    for packet in cells[i].packets
                    for p in packet.parts
                }
                cells[i] = replace(
                    cells[i],
                    speed_mps=cells[i].speed_mps if active_classes else 0.0,
                    latent=tuple((k, v) for k, v in cells[i].latent if k in active_classes),
                )
        # Independent source queues; within each exactly simultaneous source
        # packet use proportional admission, never the input list order.
        for i, queue in enumerate(pending):
            remain = []
            for packet in queue:
                space = math.fsum(p.mass * self.footprint(p.tag) for p in packet.parts)
                fraction = (
                    min(1.0, free[i] / packet.mass, free_space[i] / space)
                    if free[i] > 0 and free_space[i] > 0
                    else 0.0
                )
                if 1 - fraction < 1e-14:
                    fraction = 1.0
                parts = _portion(packet.parts, fraction)
                mass = math.fsum(p.mass for p in parts)
                free[i] = max(0.0, free[i] - mass)
                free_space[i] = max(
                    0.0, free_space[i] - math.fsum(p.mass * self.footprint(p.tag) for p in parts)
                )
                if self.preserve_entry_intervals:
                    parts = tuple(replace(p, entry_start_s=end, entry_end_s=end) for p in parts)
                incoming[i].extend(parts)
                if self.motion is not None:
                    incoming_marks[i].extend(
                        self.motion.source_mark(self, p.tag, p.mass) for p in parts
                    )
                if fraction < 1:
                    remain.append(replace(packet, parts=_portion(packet.parts, 1 - fraction)))
            pending[i] = remain
        for i, parts in incoming.items():
            parts = combine(parts)
            mass = math.fsum(p.mass for p in parts)
            if not mass:
                continue
            c = cells[i]
            if self.motion is not None:
                c = self.motion.admit(self, c, parts, incoming_marks[i])
            target = c.progress_m + self.groups[i].physics.length_m
            packets = (
                interval_packets(parts, target, self.record_budget)
                if self.preserve_entry_intervals
                else (Packet(target, parts),)
            )
            cells[i] = replace(
                c,
                packets=c.packets + packets,
                admitted=c.admitted + mass,
                entry_moment=c.entry_moment + mass * end,
            )
        out = State(
            self.identity,
            end,
            tuple(cells),
            tuple(tuple(q) for q in pending),
            s.released + born,
            s.completed + sink,
            s.birth_moment + birth1,
            s.exit_moment + exit1,
            s.source_wait_seconds + source_wait,
            s.transfer_hold_seconds + hold,
            s.pre_entry_seconds + inherited,
            tuple(ledger[k] for k in self.class_names),
        )
        if self.counts(out)["parts"] > self.record_budget:
            raise BudgetExceeded("packet state budget")
        self.check(out)
        for i, (g, a, b) in enumerate(zip(self.groups, s.cells, out.cells)):
            tol = 1e-9 * max(1.0, out.released)
            if (
                b.admitted - a.admitted > receive[i] * dt + tol
                or b.completed - a.completed > g.physics.exit_rate * factor[i] * dt + tol
            ):
                raise ArithmeticError("link rate budget")
        return out, tuple(events)
