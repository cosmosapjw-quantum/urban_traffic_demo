"""Declared synthetic activity priors on the immutable M02 block geometry.

Persons and job/service opportunities remain separate measures. Polygon patches
are additive uniform densities, not inferred buildings or observed microdata.
"""

from dataclasses import dataclass
import math

from ..terrain_city.area_access import AreaAccess
from ..terrain_city.block_access import segment_inside
from ..terrain_city.landscape import inside
from .city import reject


@dataclass(frozen=True, slots=True)
class ActivityPatch:
    mass: float
    points: tuple[tuple[float, float], ...]
    prior: str = "declared synthetic area density"
    holes: tuple = ()
    building_geometry: object = None

    def __post_init__(self):
        if self.holes or self.building_geometry is not None:
            reject("holes/building solids are unsupported", "UNSUPPORTED_GEOMETRY")
        object.__setattr__(self, "holes", ())
        object.__setattr__(self, "points", tuple(tuple(p) for p in self.points))
        if not math.isfinite(self.mass) or self.mass <= 0 or not self.prior:
            reject("positive finite patch mass and explicit prior required")
        if not self.points or any(
            len(p) != 2 or not all(map(math.isfinite, p)) for p in self.points
        ):
            reject("finite planar activity geometry required")
        if len(self.points) != 1:
            try:
                AreaAccess(self.points)
            except ValueError as exc:
                reject(str(exc), "UNSUPPORTED_GEOMETRY")


@dataclass(frozen=True, slots=True)
class ActivityMeasure:
    city_identity: str
    block_id: str
    kind: str
    patches: tuple[ActivityPatch, ...]
    block_points: tuple[tuple[float, float], ...]
    warnings: tuple[str, ...]

    @property
    def mass(self):
        return math.fsum(p.mass for p in self.patches)

    @property
    def units(self):
        return "persons" if self.kind == "residential" else "opportunities"

    def quadrature(self, depth=2, max_samples=20000):
        rows = []
        for patch in self.patches:
            rule = (
                ((patch.points[0], 1.0, 0.0),)
                if len(patch.points) == 1
                else AreaAccess(patch.points).quadrature(depth, max_samples)
            )
            rows.extend((xy, w * patch.mass / self.mass, radius) for xy, w, radius in rule)
            if len(rows) > max_samples:
                reject("activity quadrature budget exceeded; no mass omitted", "BLOCKED_RESOURCE")
        return tuple(rows)


def compile_activity(city, block_id, kind="residential", patches=None, *, service_stock=None):
    blocks = {b.id: b for b in city.face_graph.blocks}
    if block_id not in blocks or kind not in ("residential", "job", "service"):
        reject("registered block and residential/job/service kind required")
    block = blocks[block_id]
    nodes = {n.id: n for n in city.roadmap.nodes}
    points = tuple(nodes[k].xyz[:2] for k in block.boundary)
    area = AreaAccess(points)
    stock = (
        block.residents if kind == "residential" else block.jobs if kind == "job" else service_stock
    )
    if stock is None or not math.isfinite(stock) or stock <= 0:
        reject("positive declared activity stock required; empty blocks have no probability law")
    patches = (
        tuple(patches)
        if patches is not None
        else (ActivityPatch(stock, points, "uniform area fallback; synthetic"),)
    )
    if not patches or abs(math.fsum(p.mass for p in patches) - stock) > 1e-9 * max(1.0, stock):
        reject("activity patch mass differs from block stock")
    for p in patches:
        if not all(inside(x, area.polygon) for x in p.points) or (
            len(p.points) > 1
            and not all(
                segment_inside(a, b, area.polygon)
                for a, b in zip(p.points, p.points[1:] + p.points[:1])
            )
        ):
            reject("activity patch outside block")
    concentrations = {}
    for p in patches:
        if len(p.points) == 1:
            concentrations[p.points[0]] = concentrations.get(p.points[0], 0.0) + p.mass
    warnings = (
        ("REPRESENTATIVENESS: hundreds of activity units concentrated at one point",)
        if any(m >= 100 for m in concentrations.values())
        else ()
    )
    return ActivityMeasure(city.identity, block_id, kind, patches, points, warnings)


def intrazonal_law(origin, destination, *, speed_mps=1.4, depth=2, max_pairs=20000):
    """Independent declared endpoint measures, internal geodesic; no road access added.

    Coincident points legitimately have zero distance; sharing a block ID does
    not imply zero completion time. This is a demand endpoint law, not a solver.
    """
    from .journey import DelayLaw

    if (origin.city_identity, origin.block_id) != (destination.city_identity, destination.block_id):
        reject("intrazonal endpoints require the same city and block")
    if not math.isfinite(speed_mps) or speed_mps <= 0:
        reject("positive finite intrazonal speed required")
    a, b = origin.quadrature(depth), destination.quadrature(depth)
    if len(a) * len(b) > max_pairs:
        reject("intrazonal endpoint pair budget exceeded", "BLOCKED_RESOURCE")
    area = AreaAccess(origin.block_points)
    return DelayLaw(
        tuple((area.route_distance(x, y) / speed_mps, wx * wy) for x, wx, _ in a for y, wy, _ in b)
    )
