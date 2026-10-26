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
