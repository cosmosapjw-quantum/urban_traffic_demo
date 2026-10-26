"""Budgeted physical local access roads, not zero-cost zone teleports.

Sites are authored activity locations. The existing RoadMap is immutable. Only
layer-zero surface streets receive frontage; mainlines/ramps/bridges are never
silently split into driveways. Units: m, dimensionless grade, relative weight.
"""

from dataclasses import dataclass, replace
import math
from .restored_city import RoadMap, Junction, Section
from .restored_geometry import ground_profile, elevation, terrain_gate, crossing


@dataclass(frozen=True, slots=True)
class Site:
    id: str
    xy: tuple[float, float]
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class AccessResult:
    city: RoadMap
    admitted: tuple[tuple[str, str, str, float], ...]
    rejected: tuple[tuple[str, str], ...]
    used_length_m: float


def _projection(xy, points):
    candidates = []
    for k, (a, b) in enumerate(zip(points, points[1:])):
        dx, dy = b[0] - a[0], b[1] - a[1]
        den = dx * dx + dy * dy
        if den <= 1e-16:
            continue
        u = max(0.0, min(1.0, ((xy[0] - a[0]) * dx + (xy[1] - a[1]) * dy) / den))
        q = (a[0] + u * dx, a[1] + u * dy)
        candidates.append((math.dist(xy, q), k, u, q))
    return min(candidates) if candidates else None


def _clean(points):
    result = []
    for p in points:
        if not result or math.dist(p, result[-1]) > 1e-8:
            result.append(p)
    return tuple(result)


def _proposal(city, site, road, projection, serial):
    _, k, _, xy = projection
    t = city.terrain
    join = (*xy, elevation(t, *xy))
    end = (*site.xy, elevation(t, *site.xy))
    points, length, grade = ground_profile(t, (xy, site.xy))
    if grade > 0.12:
        return None, "grade"
    if terrain_gate(t, (xy, site.xy), 9.0, "surface"):
        return None, "exclusion"
    # Check every other physical road, not just endpoint proximity. Crossing an
    # elevated road needs 5m clearance. Shared attachment is explicitly legal.
    for other in city.sections:
        for a, b in zip(points, points[1:]):
            for c, d in zip(other.points, other.points[1:]):
                hit = crossing(a, b, c, d)
                if hit is None:
                    continue
                u, v, p = hit
                at_join = math.dist(p, xy) < 1e-6
                if at_join and (
                    other.id == road.id
                    or any(math.dist(xy, q[:2]) < 1e-6 for q in (other.points[0], other.points[-1]))
                ):
                    continue
                gap = abs(a[2] + u * (b[2] - a[2]) - c[2] - v * (d[2] - c[2]))
                if gap < 5.0 - 1e-8:
                    return None, "road_contact"
    new_nodes = list(city.nodes)
    sections = list(city.sections)
    if math.dist(join, road.points[0]) < 1e-7:
        join_id = road.start
        join = road.points[0]
    elif math.dist(join, road.points[-1]) < 1e-7:
        join_id = road.end
        join = road.points[-1]
    else:
        join_id = f"access-j:{serial}:{site.id}"
        if join_id in {n.id for n in city.nodes}:
            raise ValueError("access ID collision")
        new_nodes.append(Junction(join_id, join))
        left = _clean((*road.points[: k + 1], join))
        right = _clean((join, *road.points[k + 1 :]))
        # Reintegrate the same terrain-restricted centreline to get the split
        # ratio. Renormalization closes the parent's authoritative length ledger.
        la = ground_profile(t, tuple(p[:2] for p in left))[1]
        lb = ground_profile(t, tuple(p[:2] for p in right))[1]
        lchild = road.length_m * la / (la + lb)
        sections.remove(road)
        sections.extend(
            (
                replace(
                    road, id=road.id + f":cut{serial}a", end=join_id, points=left, length_m=lchild
                ),
                replace(
                    road,
                    id=road.id + f":cut{serial}b",
                    start=join_id,
                    points=right,
                    length_m=road.length_m - lchild,
                ),
            )
        )
    site_id = f"access-site:{site.id}"
    if site_id in {n.id for n in city.nodes}:
        raise ValueError("site already materialized")
    new_nodes.append(Junction(site_id, end))
    points = (join, *points[1:-1], end)
    sections.append(
        Section(
            f"access:{site.id}", join_id, site_id, points, "local", "surface", 1, 1, length, grade
        )
    )
    new = replace(
        city,
        nodes=tuple(sorted(new_nodes, key=lambda n: n.id)),
        sections=tuple(sorted(sections, key=lambda s: s.id)),
    )
    return (new, (site.id, site_id, join_id, length)), None


def grow_access(
    city,
    sites,
    budget_m=800.0,
    max_roads=4,
    max_length_m=400.0,
    min_length_m=15.0,
    admission_rule=None,
):
    """Greedy service-weight/length construction with exact budget accounting.

    Candidate set: nearest point on each eligible local/collector surface road.
    The search is not a global network/economic optimum. Accepted spurs create
    access, not a guaranteed decrease in traffic delay. Geometry never changes
    to evade a gate. Previous maps remain valid immutable snapshots.
    admission_rule(city,site,road,projection) may return a rejection reason;
    None preserves the previous generator. The rule must be deterministic.
    """
    sites = tuple(sites)
    if (
        not math.isfinite(budget_m)
        or budget_m < 0
        or not math.isfinite(max_length_m)
        or max_length_m <= 0
        or not math.isfinite(min_length_m)
        or not 0 < min_length_m < max_length_m
        or isinstance(max_roads, bool)
        or not isinstance(max_roads, int)
        or max_roads < 0
    ):
        raise ValueError("invalid construction budget")
    L = city.terrain.n * city.terrain.spacing_m
    if len({s.id for s in sites}) != len(sites):
        raise ValueError("duplicate site IDs")
    for s in sites:
        if (
            not s.id
            or len(s.xy) != 2
            or not all(math.isfinite(v) and 0 <= v <= L for v in s.xy)
            or not math.isfinite(s.weight)
            or s.weight <= 0
        ):
            raise ValueError("invalid site")
    current = city
    remaining = {s.id: s for s in sites}
    admitted = []
    reasons = {}
    used = 0.0
    while remaining and len(admitted) < max_roads:
        best = None
        for site in sorted(remaining.values(), key=lambda s: s.id):
            candidates = []
            already = False
            for road in current.sections:
                if road.facility != "surface" or road.hierarchy not in ("local", "collector"):
                    continue
                projection = _projection(site.xy, road.points)
                if projection and projection[0] < min_length_m:
                    # A site within the declared access envelope is already fronting.
                    # It is not counted as a new road or a completed transport trip.
                    if not terrain_gate(current.terrain, (site.xy, projection[3]), 2.0, "surface"):
                        # Proximity does not certify a traversable connector.
                        # Coincident xy needs no grade calculation; every other
                        # short access obeys the same 0.12 grade limit as roads.
                        if (
                            projection[0] <= 1e-8
                            or ground_profile(current.terrain, (site.xy, projection[3]))[2] <= 0.12
                        ):
                            already = True
                if projection and min_length_m <= projection[0] <= max_length_m:
                    # Do not leave tiny parent fragments around a pre-existing junction.
                    for endpoint, index, u in (
                        (road.points[0], 0, 0.0),
                        (road.points[-1], len(road.points) - 2, 1.0),
                    ):
                        if math.dist(projection[3], endpoint[:2]) < 20.0:
                            projection = (math.dist(site.xy, endpoint[:2]), index, u, endpoint[:2])
                            break
                    candidates.append((projection[0], road.id, road, projection))
            if already:
                reasons[site.id] = "already_fronting"
                continue
            if not candidates:
                reasons[site.id] = "no_eligible_frontage"
                continue
            for _, _, road, proj in sorted(candidates, key=lambda x: (x[0], x[1])):
                if proj[0] > budget_m - used + 1e-9:
                    reasons[site.id] = "budget"
                    break
                if admission_rule is not None:
                    reason = admission_rule(current, site, road, proj)
                    if reason:
                        reasons[site.id] = reason
                        continue
                proposal, reason = _proposal(current, site, road, proj, len(admitted))
                if proposal is None:
                    reasons[site.id] = reason
                    continue
                length = proposal[1][3]
                if length > max_length_m or used + length > budget_m + 1e-9:
                    reasons[site.id] = "budget_or_length"
                    continue
                rank = (-site.weight / length, site.id, road.id)
                if best is None or rank < best[0]:
                    best = (rank, proposal)
                # shortest viable frontage for this site, then compare sites.
                break
        if best is None:
            break
        current, row = best[1]
        admitted.append(row)
        used += row[3]
        remaining.pop(row[0])
    rejected = tuple((sid, reasons.get(sid, "road_count_budget")) for sid in sorted(remaining))
    return AccessResult(current, tuple(admitted), rejected, used)
