"""Interval-flux policy on PacketNetwork; finite-response motion from T02.

Boundary holds remain numerical approximations, separately measured and refined.
Different entry windows retain distinct marks. No per-person/vehicle objects,
new road solver, truth-driven routing or unqualified travel-time p95 is added.
"""

from dataclasses import dataclass, replace, asdict
import hashlib
import json
import math

from ..foundation_kinetics import characteristic, passage
from ..packet_network import State, Event
from ..active_suffix.common import BudgetExceeded, _factor
from .kinetics import (
    ClassMass,
    compile_bulk,
    advance_bulk,
    KineticEnvironment,
    predict_passage,
)
from .lanegroups import packet_model
from .city import reject


@dataclass(frozen=True, slots=True)
class BoundaryFlux:
    tag: str
    start_s: float
    end_s: float
    mass_veh: float
    birth_moment: float | None = None

    def __post_init__(self):
        if (
            not self.tag
            or any(not math.isfinite(x) or x < 0 for x in (self.start_s, self.end_s, self.mass_veh))
            or self.end_s < self.start_s
        ):
            reject("finite nonnegative boundary flux and ordered endpoints required")
        if self.birth_moment is not None and (
            not math.isfinite(self.birth_moment)
            or not 0 <= self.birth_moment <= self.mass_veh * self.start_s
        ):
            reject("external birth mark must precede the entry window")
        for field in ("start_s", "end_s", "mass_veh"):
            object.__setattr__(self, field, float(getattr(self, field)))
        if self.birth_moment is not None:
            object.__setattr__(self, "birth_moment", float(self.birth_moment))

    def slice(self, a, b):
        if self.start_s == self.end_s:
            fraction = 1.0
            lo = hi = self.start_s
        else:
            lo, hi = max(a, self.start_s), min(b, self.end_s)
            fraction = max(0.0, hi - lo) / (self.end_s - self.start_s)
        mass = self.mass_veh * fraction
        birth = mass * (lo + hi) / 2 if self.birth_moment is None else self.birth_moment * fraction
        return (self.tag, mass, birth, lo, hi)


@dataclass(frozen=True, slots=True)
class HeldMotion:
    distance_m: float
    speed_mps: float
    latent: tuple[tuple[str, float], ...]
    v0: float
    target: float
    physical: object
    classes: tuple[ClassMass, ...]
    hazards: tuple[float, ...]

    def passage(self, distance):
        return passage(self.physical, self.v0, self.target, distance)[0]

    def speed_at(self, t):
        return characteristic(self.physical, self.v0, self.target, t)[1]

    def latent_at(self, name, t):
        c = next(c for c in self.classes if c.vehicle.name == name)
        nu = self.hazards[next(i for i, c in enumerate(self.classes) if c.vehicle.name == name)]
        rate = c.restart_s_inv + nu
        return (
            c.latent
            if rate == 0
            else c.latent + (c.restart_s_inv / rate - c.latent) * (-math.expm1(-rate * t))
        )


@dataclass(frozen=True, slots=True)
class FiniteResponseMotion:
    # Exact empty-link law: distance/speed/latent are identically zero.
    empty_stationary = True

    templates: tuple[ClassMass, ...]
    entry_speeds: tuple[tuple[str, float], ...]

    @property
    def identity(self):
        return hashlib.sha256(
            json.dumps(
                dict(law="T02_symmetric_finite_response_v1", config=asdict(self)),
                sort_keys=True,
                allow_nan=False,
            ).encode()
        ).hexdigest()

    def bulk(self, model, group, cell, t):
        counts = {}
        registry = {c.vehicle.name: c for c in self.templates}
        latent = dict(cell.latent)
        for packet in cell.packets:
            for p in packet.parts:
                name = model.vehicle_classes[p.tag].name
                counts.setdefault(name, []).append(p.mass)
        classes = tuple(
            replace(
                registry[k], mass_veh=math.fsum(values), latent=latent.get(k, registry[k].latent)
            )
            for k, values in sorted(counts.items())
        )
        return compile_bulk(classes, speed_mps=cell.speed_mps if classes else 0.0, time_s=t)

    def advance(self, model, group, cell, t, dt, factor):
        bulk = self.bulk(model, group, cell, t)
        cap = 0.0 if factor == 0 else group.physics.speed_mps
        env = KineticEnvironment(model.space_capacities_m[group.id], cap, t)
        if not bulk.classes:
            # No traffic: no drift, with a harmless conditional zero-target law.
            c = self.templates[0].vehicle
            return HeldMotion(0.0, 0.0, (), 0.0, 0.0, c, (), ())
        step = advance_bulk(bulk, env, dt)
        coeff = step.coefficients
        return HeldMotion(
            step.distance_m,
            step.state.speed_mps,
            tuple((c.vehicle.name, c.latent) for c in step.state.classes),
            bulk.speed_mps,
            coeff.target_mps,
            coeff.characteristic_class,
            bulk.classes,
            coeff.hazards_s_inv,
        )

    def source_mark(self, model, tag, mass):
        name = model.vehicle_classes[tag].name
        c = next(c for c in self.templates if c.vehicle.name == name)
        return name, mass, dict(self.entry_speeds)[name], c.latent

    def transfer_mark(self, model, tag, mass, motion, t):
        name = model.vehicle_classes[tag].name
        return name, mass, motion.speed_at(t), motion.latent_at(name, t)

    def admit(self, model, cell, parts, marks):
        # Exchangeable moment projection at an admission boundary is a closure;
        # finite acceleration applies between these composition-changing events.
        old_mass = cell.occupancy
        added = math.fsum(p.mass for p in parts)
        speed = (old_mass * cell.speed_mps + math.fsum(m * v for _, m, v, _ in marks)) / (
            old_mass + added
        )
        by_class = {}
        for packet in cell.packets:
            for p in packet.parts:
                k = model.vehicle_classes[p.tag].name
                by_class.setdefault(k, []).append((p.mass, dict(cell.latent)[k]))
        for k, m, _, p in marks:
            by_class.setdefault(k, []).append((m, p))
        latent = tuple(
            (k, math.fsum(m * p for m, p in values) / math.fsum(m for m, _ in values))
            for k, values in sorted(by_class.items())
        )
        return replace(cell, speed_mps=speed, latent=latent)


@dataclass(frozen=True, slots=True)
class TransportState:
    model_id: str
    road: State
    deferred: tuple[tuple, ...] = ()
    events: tuple[Event, ...] = ()
    source_quantization_seconds: float = 0.0
    source_admission_hold_seconds: float = 0.0
    peak_parts: int = 0
    peak_records: int = 0
    peak_packets: int = 0
    consumed_points: tuple[int, ...] = ()


def _normalize_fluxes(fluxes):
    # Exact mass fragmentation quotient at the same physical interval/mark law.
    groups = {}
    for f in fluxes:
        if not isinstance(f, BoundaryFlux):
            reject("typed BoundaryFlux required")
        if f.mass_veh:
            key = (
                f.tag,
                f.start_s,
                f.end_s,
                None if f.birth_moment is None else f.birth_moment / f.mass_veh,
            )
            groups.setdefault(key, []).append(f)
    result = []
    for (tag, a, b, mark), values in sorted(
        groups.items(),
        key=lambda x: (x[0][1], x[0][2], x[0][0], -1.0 if x[0][3] is None else x[0][3]),
    ):
        mass = math.fsum(f.mass_veh for f in values)
        result.append(
            BoundaryFlux(
                tag, a, b, mass, None if mark is None else math.fsum(f.birth_moment for f in values)
            )
        )
    joined = []
    for f in sorted(result, key=lambda f: (f.tag, f.start_s, f.end_s)):
        prev = joined[-1] if joined else None
        same_mark = prev is not None and (
            (prev.birth_moment is None and f.birth_moment is None)
            or (
                prev.birth_moment is not None
                and f.birth_moment is not None
                and prev.birth_moment / prev.mass_veh == f.birth_moment / f.mass_veh
            )
        )
        if (
            prev is not None
            and prev.tag == f.tag
            and prev.end_s == f.start_s
            and prev.end_s > prev.start_s
            and f.end_s > f.start_s
            and same_mark
            and prev.mass_veh / (prev.end_s - prev.start_s) == f.mass_veh / (f.end_s - f.start_s)
        ):
            joined[-1] = BoundaryFlux(
                f.tag,
                prev.start_s,
                f.end_s,
                prev.mass_veh + f.mass_veh,
                None if f.birth_moment is None else prev.birth_moment + f.birth_moment,
            )
        else:
            joined.append(f)
    return tuple(sorted(joined, key=lambda f: (f.start_s, f.end_s, f.tag)))


class TransportModel:
    """One interval driver for the selected PacketNetwork, not another engine.

    max_step_s controls declared boundary quantization. Source windows are
    integrated exactly, held at their next boundary and then admitted by the
    existing node policy. All emitted transfer intervals remain observable.
    """

    def __init__(
        self,
        contract,
        routes,
        vehicle_classes,
        fluxes=(),
        *,
        max_step_s=0.1,
        templates=(),
        entry_speeds=None,
        record_budget=2000000,
        event_budget=10000,
        substep_budget=100000,
    ):
        if (
            not math.isfinite(max_step_s)
            or max_step_s <= 0
            or isinstance(record_budget, bool)
            or not isinstance(record_budget, int)
            or not 1 <= record_budget <= 2000000
        ):
            reject("positive max step and live/history record budget <=2M required")
        if (
            isinstance(substep_budget, bool)
            or not isinstance(substep_budget, int)
            or substep_budget < 1
        ):
            reject("positive integer substep budget required")
        self.substep_budget = substep_budget
        registry = {c.name: c for c in vehicle_classes.values()}
        templates = tuple(templates)
        supplied = {c.vehicle.name: c for c in templates}
        if len(supplied) != len(templates):
            reject("duplicate kinetic class template")
        if len(registry) > 3 or any(
            k not in registry or c.vehicle != registry[k] for k, c in supplied.items()
        ):
            reject("at most three matching kinetic templates required")
        templates = tuple(supplied.get(k, ClassMass(c, 1.0)) for k, c in sorted(registry.items()))
        speeds = {k: 0.0 for k in registry} if entry_speeds is None else dict(entry_speeds)
        if set(speeds) != set(registry) or any(
            not math.isfinite(v) or v < 0 for v in speeds.values()
        ):
            reject("one finite nonnegative entry speed per physical class required")
        self.motion = FiniteResponseMotion(templates, tuple(sorted(speeds.items())))
        self.network = packet_model(
            contract,
            routes,
            vehicle_classes,
            dt_s=max_step_s,
            record_budget=record_budget,
            event_budget=event_budget,
            motion=self.motion,
            preserve_entry_intervals=True,
        )
        self.fluxes = _normalize_fluxes(fluxes)
        if any(f.tag not in self.network.routes for f in self.fluxes):
            reject("source flux uses an unknown committed route")
        self.max_step_s = max_step_s
        self.record_budget = record_budget
        self.identity = hashlib.sha256(
            json.dumps(
                dict(
                    policy="T04_interval_boundary_quantization_v1",
                    network=self.network.identity,
                    fluxes=[asdict(f) for f in self.fluxes],
                    step=max_step_s,
                    budget=record_budget,
                    substep_budget=substep_budget,
                ),
                sort_keys=True,
            ).encode()
        ).hexdigest()

    def check(self, state):
        if state.model_id != self.identity:
            reject("transport identity mismatch")
        self.network.check(state.road)
        t = state.road.time_s
        if len(set(state.consumed_points)) != len(state.consumed_points) or any(
            k < 0
            or k >= len(self.fluxes)
            or self.fluxes[k].start_s != self.fluxes[k].end_s
            or self.fluxes[k].start_s > t
            for k in state.consumed_points
        ):
            reject("invalid point-source cursor")
        available = [
            f.slice(0.0, t)
            for k, f in enumerate(self.fluxes)
            if (k in state.consumed_points if f.start_s == f.end_s else t > f.start_s)
        ]
        expected = math.fsum(x[1] for x in available)
        birth = math.fsum(x[2] for x in available)
        released = state.road.released + math.fsum(x[1] for x in state.deferred)
        recorded_birth = state.road.birth_moment + math.fsum(x[2] for x in state.deferred)
        if abs(released - expected) > 1e-9 * max(1.0, expected) or abs(
            recorded_birth - birth
        ) > 1e-8 * max(1.0, birth):
            reject("source flux mass/birth ledger mismatch", "NUMERICAL_ERROR")

    def initial(self):
        return TransportState(self.identity, self.network.initial())

    def _boundary(self, t, end):
        grid = (math.floor(t / self.max_step_s + 1e-10) + 1) * self.max_step_s
        target = min(end, grid)
        candidates = [x for f in self.fluxes for x in (f.start_s, f.end_s)]
        candidates.extend(x for _, a, b, _ in self.network.windows for x in (a, b))
        for g in self.network.groups:
            s = g.signal
            if s:
                for phase in (0.0, s.green_s):
                    edge = (
                        s.offset_s
                        + phase
                        + (math.floor((t - s.offset_s - phase) / s.cycle_s) + 1) * s.cycle_s
                    )
                    candidates.append(edge)
        return min([target] + [x for x in candidates if t + 1e-10 < x < target])

    def advance(self, state, end_s):
        if state.model_id != self.identity or not math.isfinite(end_s) or end_s < state.road.time_s:
            reject("transport identity or clock mismatch")
        self.check(state)
        original = state
        iterations = 0
        try:
            while state.road.time_s < end_s:
                if iterations >= self.substep_budget:
                    raise BudgetExceeded("transport substep budget")
                iterations += 1
                t = state.road.time_s
                target = self._boundary(t, end_s)
                offers = list(state.deferred)
                # Point source measures are available at their actual boundary.
                consumed = list(state.consumed_points)
                point_quant = 0.0
                for k, f in enumerate(self.fluxes):
                    if f.start_s == f.end_s and f.start_s <= t and k not in consumed:
                        offers.append(f.slice(t, t))
                        point_quant += f.mass_veh * (t - f.start_s)
                        consumed.append(k)
                road, events = self.network.advance_interval(state.road, target - t, offers)
                deferred = tuple(
                    f.slice(t, target)
                    for f in self.fluxes
                    if f.end_s > f.start_s and min(target, f.end_s) > max(t, f.start_s)
                )
                quant = math.fsum(m * (target - (a + b) / 2) for _, m, _, a, b in deferred)
                history = state.events + events
                parts = self.network.counts(road)["parts"] + len(deferred)
                records = parts + len(history)
                if records > self.record_budget:
                    raise BudgetExceeded("transport live/history record budget")
                source_admitted = max(
                    0.0,
                    math.fsum(b.admitted - a.admitted for a, b in zip(state.road.cells, road.cells))
                    - math.fsum(e.mass for e in events if e.destination is not None),
                )
                state = TransportState(
                    self.identity,
                    road,
                    deferred,
                    history,
                    state.source_quantization_seconds + quant + point_quant,
                    state.source_admission_hold_seconds + source_admitted * (target - t),
                    max(state.peak_parts, parts),
                    max(state.peak_records, records),
                    max(state.peak_packets, self.network.counts(road)["packets"] + len(deferred)),
                    tuple(consumed),
                )
        except (BudgetExceeded, ArithmeticError) as exc:
            exc.checkpoint = state
            exc.request_checkpoint = original
            raise
        return state

    def report(self, state):
        if state.model_id != self.identity:
            reject("transport identity mismatch")
        self.check(state)
        road = state.road
        deferred = math.fsum(x[1] for x in state.deferred)
        birth = road.birth_moment + math.fsum(x[2] for x in state.deferred)
        released = road.released + deferred
        planned = math.fsum(f.mass_veh for f in self.fluxes)
        unfinished = planned - road.completed
        source = deferred + math.fsum(p.mass for q in road.pending for p in q)
        active = math.fsum(c.occupancy for c in road.cells)
        deferred_age = math.fsum(x[1] * road.time_s - x[2] for x in state.deferred)
        system = road.system_vehicle_seconds + deferred_age
        observed = (
            math.fsum(c.residence(road.time_s) for c in road.cells)
            + road.source_wait_seconds
            + road.transfer_hold_seconds
            + road.pre_entry_seconds
            + deferred_age
        )
        completed_birth = math.fsum(e.birth_moment for e in state.events if e.destination is None)
        conditional_mean = (
            (road.exit_moment - completed_birth) / road.completed if road.completed else None
        )
        mass_residual = released - road.completed - source - active
        residence_residual = system - observed
        passed = abs(mass_residual) <= 1e-9 * max(1.0, released) and abs(
            residence_residual
        ) <= 1e-8 * max(1.0, system)
        return dict(
            status="PASS" if passed else "NUMERICAL_ERROR",
            time_s=road.time_s,
            released_veh=released,
            scheduled_veh=planned,
            not_yet_released_veh=planned - released,
            birth_moment_veh_s=birth,
            completed_veh=road.completed,
            source_pending_veh=source,
            active_veh=active,
            unfinished_fraction=unfinished / planned if planned else 0.0,
            mass_residual_veh=mass_residual,
            residence_residual_veh_s=residence_residual,
            road_residence_veh_s=math.fsum(c.residence(road.time_s) for c in road.cells),
            node_exit_queue_veh_s=math.fsum(c.exit_queue_seconds for c in road.class_ledger),
            road_class_ledger=[asdict(c) for c in road.class_ledger],
            deferred_source_class_veh={
                name: math.fsum(
                    x[1] for x in state.deferred if self.network.vehicle_classes[x[0]].name == name
                )
                for name in self.network.class_names
            },
            mean_completed_s=conditional_mean,
            whole_population_mean_s=conditional_mean
            if unfinished <= 1e-9 * max(1.0, planned)
            else None,
            source_quantization_veh_s=state.source_quantization_seconds
            + state.source_admission_hold_seconds,
            source_arrival_quantization_veh_s=state.source_quantization_seconds,
            source_admission_quantization_veh_s=state.source_admission_hold_seconds,
            source_queue_veh_s=road.source_wait_seconds - state.source_admission_hold_seconds,
            transfer_quantization_veh_s=road.transfer_hold_seconds,
            physical_pre_entry_veh_s=road.pre_entry_seconds
            + deferred_age
            - state.source_quantization_seconds,
            p95_s=None,
            p95_status="UNSUPPORTED_JOINT_BIRTH_EXIT_DISTRIBUTION",
            peak_parts=state.peak_parts,
            peak_packets=state.peak_packets,
            peak_records=state.peak_records,
            max_step_s=self.max_step_s,
        )

    def completed_at(self, state, time_s):
        if not math.isfinite(time_s) or not 0 <= time_s <= state.road.time_s:
            reject("completion query must be within recorded history")
        return math.fsum(
            e.mass
            * (
                float(time_s >= e.end_s)
                if e.end_s == e.start_s
                else max(0.0, min(1.0, (time_s - e.start_s) / (e.end_s - e.start_s)))
            )
            for e in state.events
            if e.destination is None
        )

    def link_eta(self, state, group_id, length_m=None, horizon_s=3600.0):
        """Frozen-current-environment motion passage, excluding node service wait."""
        self.check(state)
        i = self.network.index[group_id]
        group = self.network.groups[i]
        bulk = self.motion.bulk(self.network, group, state.road.cells[i], state.road.time_s)
        cap = (
            0.0
            if _factor(group.id, state.road.time_s, self.network.windows) == 0
            else group.physics.speed_mps
        )
        env = KineticEnvironment(self.network.space_capacities_m[group_id], cap, state.road.time_s)
        return predict_passage(
            bulk,
            env,
            group.physics.length_m if length_m is None else length_m,
            step_s=self.max_step_s,
            horizon_s=horizon_s,
        )
