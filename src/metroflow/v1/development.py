"""Finite candidate driveway selection and separate physical capacity ledger.

Construction and capacity are declared engineering priors, not calibrated
headways. Gate capacity below is a horizon admission bound, not a dynamic flow
solver; T03 will own joint road receiving constraints and interface queues.
"""

from dataclasses import dataclass
from itertools import combinations
import math

from ..terrain_city.area_access import Portal
from ..terrain_city.block_access import segment_inside
from ..terrain_city.landscape import segment_clear
from ..restored_geometry import ground_profile
from .access import activity_access
from .city import reject


@dataclass(frozen=True, slots=True)
class EntryPortal:
    id: str
    city_identity: str
    block_id: str
    node_id: str
    xy: tuple[float, float]
    capacity_veh_s: float
    construction_length_m: float
    maximum_grade: float
    existing: bool

    @property
    def door(self):
        return Portal(self.id, self.xy)


def compile_entry(
    city,
    measure,
    portal_id,
    *,
    capacity_veh_s,
    corridor,
    existing=False,
    width_m=2.0,
    max_grade=0.12,
):
    """Validate a declared internal corridor to a registered physical ground door.

    Travel over the block is represented by the activity law alone. Corridor
    length here is construction cost, never another delay term.
    """
    if measure.city_identity != city.identity:
        reject("activity belongs to a different city snapshot")
    refs = [p for p in city.portals if p.id == portal_id and p.block_id == measure.block_id]
    if len(refs) != 1:
        reject("entry requires registered block portal")
    if not all(math.isfinite(v) and v > 0 for v in (capacity_veh_s, width_m, max_grade)):
        reject("positive finite entry capacity, width and grade limit required")
    nodes = {n.id: n for n in city.roadmap.nodes}
    node = nodes[refs[0].node_id]
    block = next(b for b in city.face_graph.blocks if b.id == measure.block_id)
    if node.id not in block.boundary:
        reject("entry needs topological contact with a registered face boundary node")
    path = tuple(tuple(p) for p in corridor)
    from ..terrain_city.area_access import AreaAccess

    area = AreaAccess(measure.block_points)
    # Boundary validation is shared with the physical access compiler.
    area.portal_costs(area.points[0], (Portal(portal_id, node.xyz[:2]),))
    if (
        len(path) < 2
        or path[-1] != node.xyz[:2]
        or any(len(p) != 2 or not all(map(math.isfinite, p)) for p in path)
    ):
        reject("corridor must end at registered ground door")
    regions = city.landscape.water + city.landscape.protected
    for a, b in zip(path, path[1:]):
        if not segment_inside(a, b, area.polygon) or not segment_clear(a, b, regions, width_m):
            reject("corridor violates block or mask", "PHYSICAL_INFEASIBLE")
    _, length, grade = ground_profile(city.landscape.terrain, path)
    if length <= 0 or grade > max_grade:
        reject("corridor length/grade infeasible", "PHYSICAL_INFEASIBLE")
    return EntryPortal(
        portal_id,
        city.identity,
        measure.block_id,
        node.id,
        node.xyz[:2],
        capacity_veh_s,
        0.0 if existing else length,
        grade,
        existing,
    )


def select_entries(
    measure,
    entries,
    *,
    construction_budget_m,
    max_distance_m,
    forecast_vehicles,
    horizon_s,
    speed_mps=1.4,
    length_weight_s_m=1.0,
    load_weight_s=60.0,
    depth=2,
):
    """Enumerate <=12 candidate doors; return all tied feasible minimizers.

    Objective: weighted mean access seconds + length_weight*new length +
    load_weight*sum(gate_probability*utilization²). Hard distance coverage is
    checked on every quadrature cell using its maximum-radius upper bound.
    Unserved activity and horizon excess vehicles are reported separately.
    No renormalization, population deletion, or ID priority is permitted.
    """
    entries = tuple(entries)
    values = (construction_budget_m, forecast_vehicles, length_weight_s_m, load_weight_s)
    if any(not math.isfinite(v) or v < 0 for v in values) or any(
        not math.isfinite(v) or v <= 0 for v in (max_distance_m, horizon_s, speed_mps)
    ):
        reject("finite nonnegative budgets/weights and positive distance/horizon/speed required")
    if not entries or len(entries) > 12:
        reject("entry subset search requires 1..12 candidates", "BLOCKED_RESOURCE")
    if any(
        (e.city_identity, e.block_id) != (measure.city_identity, measure.block_id) for e in entries
    ):
        reject("entry belongs to a different city or block")
    if len({e.id for e in entries}) != len(entries) or len({e.xy for e in entries}) != len(entries):
        reject("duplicate physical entry")
    if any(
        not math.isfinite(e.capacity_veh_s)
        or e.capacity_veh_s <= 0
        or not math.isfinite(e.construction_length_m)
        or e.construction_length_m < 0
        for e in entries
    ):
        reject("invalid physical entry prior")
    rows = []
    mandatory = {e.id for e in entries if e.existing}
    for count in range(1, len(entries) + 1):
        for subset in combinations(entries, count):
            if not mandatory <= {e.id for e in subset}:
                continue
            length = math.fsum(e.construction_length_m for e in subset)
            if length > construction_budget_m:
                continue
            law, report = activity_access(
                measure, (e.door for e in subset), speed_mps=speed_mps, depth=depth
            )
            # RMS triangle radius * sqrt(12) bounds every vertex displacement,
            # hence the full convex cell. This is conservative, not sampled-only.
            rule = measure.quadrature(depth)
            uncovered = math.fsum(
                w
                for (_, w, r), s in zip(rule, report["samples"])
                if s["cost_s"] * speed_mps + math.sqrt(12.0) * r > max_distance_m
            )
            shares = dict(law.portal_weights())
            loads = tuple(
                dict(
                    portal=e.id,
                    probability=shares.get(e.id, 0.0),
                    vehicles=forecast_vehicles * shares.get(e.id, 0.0),
                    capacity_veh_s=e.capacity_veh_s,
                    excess_vehicles=max(
                        0.0,
                        forecast_vehicles * shares.get(e.id, 0.0) - horizon_s * e.capacity_veh_s,
                    ),
                )
                for e in subset
            )
            excess = math.fsum(r["excess_vehicles"] for r in loads)
            load_score = math.fsum(
                r["probability"] * (r["vehicles"] / (horizon_s * r["capacity_veh_s"])) ** 2
                for r in loads
            )
            score = law.mean_s + length_weight_s_m * length + load_weight_s * load_score
            rows.append(
                dict(
                    portals=tuple(e.id for e in subset),
                    objective_s=score,
                    construction_length_m=length,
                    mean_s=law.mean_s,
                    p95_quadrature_s=report["p95_quadrature_s"],
                    loads=loads,
                    unserved_activity_upper=measure.mass * uncovered,
                    activity_units=measure.units,
                    excess_vehicles=excess,
                    feasible=uncovered <= 1e-12 and excess <= 1e-9,
                )
            )
    feasible = [r for r in rows if r["feasible"]]
    best = min((r["objective_s"] for r in feasible), default=math.inf)
    return dict(
        status="PASS" if feasible else "PHYSICAL_INFEASIBLE",
        alternatives=[
            r for r in feasible if math.isclose(r["objective_s"], best, abs_tol=1e-9, rel_tol=1e-10)
        ],
        candidates=rows,
        total_activity=measure.mass,
        units=measure.units,
        capacity_semantics="horizon admission bound; joint road receiving NOT_IMPLEMENTED",
    )


@dataclass(frozen=True, slots=True)
class DevelopmentSite:
    block_id: str
    entry: EntryPortal
    added_capacity: int
    priority: int = 0  # declared policy ordering, never inferred from block ID


@dataclass(frozen=True, slots=True)
class CohortMove:
    origin: str
    destination: str
    persons: int


@dataclass(frozen=True, slots=True)
class GrowthState:
    model_id: str
    epoch_s: float
    allocations: tuple[tuple[str, int], ...]
    added_capacities: tuple[tuple[str, int], ...]
    built_blocks: tuple[str, ...]
    original_residents: int
    requested_increment: int = 0
    pending_increment: int = 0
    construction_m: float = 0.0
    moves: tuple[CohortMove, ...] = ()
    consumed_access_stamp_s: float = -1.0
    status: str = "INITIAL"


class GrowthModel:
    """Finite slow-epoch synthetic policy; existing residents never auto-relocate."""

    def __init__(self, city, sites, *, budget_m, slow_epoch_s=3600.0, max_access_s=1800.0):
        import hashlib

        self.city, self.sites = city, tuple(sites)
        self.budget_m, self.slow_epoch_s, self.max_access_s = budget_m, slow_epoch_s, max_access_s
        blocks = {b.id: b for b in city.face_graph.blocks}
        if (
            any(not math.isfinite(x) or x < 0 for x in (budget_m, max_access_s))
            or not math.isfinite(slow_epoch_s)
            or slow_epoch_s <= 0
            or len({s.block_id for s in self.sites}) != len(self.sites)
            or len({s.priority for s in self.sites}) != len(self.sites)
        ):
            reject("finite budgets/clocks and unique explicit site priorities required")
        if len(self.sites) > 1000:
            reject("development site budget exceeded", "BLOCKED_RESOURCE")
        for site in self.sites:
            if (
                site.block_id not in blocks
                or site.entry.block_id != site.block_id
                or site.entry.city_identity != city.identity
                or not math.isfinite(site.entry.construction_length_m)
                or site.entry.construction_length_m < 0
                or not math.isfinite(site.entry.capacity_veh_s)
                or site.entry.capacity_veh_s <= 0
                or not any(
                    n.id == site.entry.node_id and n.xyz[:2] == site.entry.xy
                    for n in city.roadmap.nodes
                )
                or isinstance(site.added_capacity, bool)
                or not isinstance(site.added_capacity, int)
                or site.added_capacity <= 0
                or not any(
                    p.id == site.entry.id and p.block_id == site.block_id for p in city.portals
                )
            ):
                reject("development requires registered physically compiled entry/capacity")
            # Recheck authoritative masks/contact; no new land footprint is invented.
            from ..terrain_city.landscape import inside

            if any(
                inside(site.entry.xy, p.points)
                for p in city.landscape.water + city.landscape.protected
            ):
                reject("development entry on water/protected mask", "PHYSICAL_INFEASIBLE")
        self.identity = hashlib.sha256(
            repr((city.identity, self.sites, budget_m, slow_epoch_s, max_access_s)).encode()
        ).hexdigest()

    def initial(self):
        return GrowthState(
            self.identity,
            0.0,
            tuple((b.id, b.residents) for b in self.city.face_graph.blocks),
            tuple((b.id, 0) for b in self.city.face_graph.blocks),
            (),
            sum(b.residents for b in self.city.face_graph.blocks),
        )

    def check(self, state):
        blocks = {b.id: b for b in self.city.face_graph.blocks}
        a, c = dict(state.allocations), dict(state.added_capacities)
        if (
            state.model_id != self.identity
            or set(a) != set(blocks)
            or set(c) != set(blocks)
            or any(
                not isinstance(x, int) or isinstance(x, bool) or x < 0
                for x in list(a.values())
                + list(c.values())
                + [state.pending_increment, state.requested_increment]
            )
            or any(a[k] > blocks[k].housing_capacity + c[k] for k in blocks)
            or sum(a.values()) + state.pending_increment
            != state.original_residents + state.requested_increment
            or state.original_residents != sum(b.residents for b in blocks.values())
            or not math.isfinite(state.construction_m)
            or state.construction_m < 0
            or state.construction_m > self.budget_m + 1e-9
        ):
            reject("growth identity, capacity or resident ledger failure", "CONTRACT_ERROR")

    def advance(self, state, snapshot, now_s, requested_increment=0, moves=()):
        from dataclasses import replace

        self.check(state)
        if (
            not math.isfinite(now_s)
            or now_s != state.epoch_s + self.slow_epoch_s
            or snapshot.city_identity != self.materialize_city(state).identity
            or snapshot.stamp_s >= now_s
            or snapshot.stamp_s <= state.consumed_access_stamp_s
            or isinstance(requested_increment, bool)
            or not isinstance(requested_increment, int)
            or requested_increment < 0
        ):
            reject(
                "growth requires previous completed epoch and next slow boundary", "CONTRACT_ERROR"
            )
        a, capacity = dict(state.allocations), dict(state.added_capacities)
        blocks = {b.id: b for b in self.city.face_graph.blocks}
        costs = dict(snapshot.costs)
        built = set(state.built_blocks)
        construction = state.construction_m
        pending = state.pending_increment + requested_increment
        for site in sorted(self.sites, key=lambda s: -s.priority):
            if (
                not math.isfinite(costs.get(site.block_id, math.inf))
                or costs[site.block_id] > self.max_access_s
            ):
                continue
            if site.block_id not in built and pending > 0:
                cost = site.entry.construction_length_m
                if construction + cost > self.budget_m:
                    continue
                built.add(site.block_id)
                construction += cost
                capacity[site.block_id] += site.added_capacity
            free = (
                blocks[site.block_id].housing_capacity + capacity[site.block_id] - a[site.block_id]
            )
            amount = min(pending, free)
            a[site.block_id] += amount
            pending -= amount
        moves = tuple(moves)
        for move in moves:
            if (
                move.origin == move.destination
                or move.origin not in a
                or move.destination not in a
                or isinstance(move.persons, bool)
                or not isinstance(move.persons, int)
                or move.persons <= 0
                or a[move.origin] < move.persons
                or not math.isfinite(costs.get(move.destination, math.inf))
                or costs[move.destination] > self.max_access_s
                or a[move.destination] + move.persons
                > blocks[move.destination].housing_capacity + capacity[move.destination]
            ):
                reject("explicit cohort movement infeasible", "PENDING_DEVELOPMENT")
            a[move.origin] -= move.persons
            a[move.destination] += move.persons
        result = replace(
            state,
            epoch_s=now_s,
            allocations=tuple(sorted(a.items())),
            added_capacities=tuple(sorted(capacity.items())),
            built_blocks=tuple(sorted(built)),
            requested_increment=state.requested_increment + requested_increment,
            pending_increment=pending,
            construction_m=construction,
            moves=state.moves + moves,
            consumed_access_stamp_s=snapshot.stamp_s,
            status="PENDING_DEVELOPMENT" if pending else "APPLIED",
        )
        self.check(result)
        return result

    def materialize_city(self, state):
        """Canonical next-epoch city; this is not a hot-swap of occupied traffic."""
        from dataclasses import replace
        from .city import compile_city

        self.check(state)
        a, c = dict(state.allocations), dict(state.added_capacities)
        blocks = tuple(
            replace(b, residents=a[b.id], housing_capacity=b.housing_capacity + c[b.id])
            for b in self.city.face_graph.blocks
        )
        return compile_city(
            self.city.roadmap,
            self.city.landscape,
            blocks,
            self.city.portals,
            requested_population=self.city.requested_population + state.requested_increment,
            unplaced_residents=self.city.unplaced_residents + state.pending_increment,
        )

    def compile_next_demand(self, state, **kwargs):
        from .activity import compile_activity
        from .demand import compile_daily_demand

        city = self.materialize_city(state)
        homes = tuple(compile_activity(city, b.id) for b in city.face_graph.blocks if b.residents)
        jobs = tuple(compile_activity(city, b.id, "job") for b in city.face_graph.blocks if b.jobs)
        return compile_daily_demand(homes, jobs, **kwargs)


def lagged_growth_control():
    """Bridge/bypass access improvement is consumed only after a completed epoch."""
    from .access_audit import fixture_city
    from .activity import compile_activity
    from .accessibility import compile_accessibility
    from .timing_oracles import timing_fixture
    from .transport import BoundaryFlux
    from .observations import completed_route_observations

    city = fixture_city()
    measure = compile_activity(city, "block")
    entry = compile_entry(
        city, measure, "east", capacity_veh_s=1.0, corridor=((300.0, 20.0), (310.0, 10.0))
    )
    model = GrowthModel(city, (DevelopmentSite("block", entry, 20),), budget_m=100, max_access_s=50)
    baseline = timing_fixture(0.1, window=0, lengths=(1000.0,))
    base_state = baseline.advance(baseline.initial(), 180.0)
    base_obs = completed_route_observations(
        baseline, base_state, since_s=0, sensor_xy={"trip": (0.0, 0.0)}, version=baseline.identity
    )
    old = compile_accessibility(city.identity, tuple(("block", o) for o in base_obs), 180.0)
    first = model.advance(model.initial(), old, 3600, 10)
    bypass = timing_fixture(
        0.1, lengths=(100.0,), fluxes=(BoundaryFlux("trip", 3600.0, 3600.0, 1.0),)
    )
    bypass_state = bypass.advance(bypass.initial(), 3780.0)
    bypass_obs = completed_route_observations(
        bypass,
        bypass_state,
        since_s=3600.0,
        sensor_xy={"trip": (0.0, 0.0)},
        version=bypass.identity,
    )
    improved = compile_accessibility(
        model.materialize_city(first).identity, tuple(("block", o) for o in bypass_obs), 3780.0
    )
    second = model.advance(first, improved, 7200)
    demand = model.compile_next_demand(second, worker_fraction=0.1, service_fraction=0)
    return [
        dict(
            case="bridge_bypass_lag",
            status="PASS"
            if first.pending_increment == 10 and second.pending_increment == 0
            else "NOT_ACCEPTED",
            first_pending=first.pending_increment,
            second_pending=second.pending_increment,
            realized_baseline_s=dict(old.costs)["block"],
            realized_bypass_s=dict(improved.costs)["block"],
            original_residents=second.original_residents,
            new_residents=sum(dict(second.allocations).values()),
            construction_m=second.construction_m,
            next_demand_identity=demand.identity,
            next_demand_city_identity=demand.city_identity,
        )
    ]
