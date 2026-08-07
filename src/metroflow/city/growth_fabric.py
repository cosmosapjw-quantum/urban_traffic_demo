"""Accretive street growth: streets are grown, not sampled and connected.

Every existing generation stage connects a FIXED point set with a local stencil,
and that choice mechanically fixes the morphology. Measured on the current
`realistic_synthetic_v1` fabric: mean node degree 4.98-5.72 against a reference
band of 2.55-3.55, dead-end share 0.0000-0.0025 against 0.027-0.288, and
circuity exactly 1.0 because straight segments are the only thing a stencil can
emit. No parameter choice inside that family reaches the targets: dropping the
diagonal offsets fixes degree (14/14 in envelope) but drives four-way share to
0.61-0.85 against a 0.69 ceiling.

This module grows streets one step at a time under local constraints, which is
what produces the three missing properties by construction rather than by
tuning:

* **T-junctions.** Snapping a growing tip onto the interior of an existing
  street splits it and yields a degree-3 node. A stencil can only ever produce
  degree-4 crossings, which is why four-way share explodes when diagonals go.
* **Dead ends.** A tip that cannot legally extend terminates as a cul-de-sac.
  Nothing in the stencil family can create a leaf, which is why dead-end share
  sits at zero regardless of thresholds.
* **Curvature.** A tip turns a little at each step, so a street between two
  junctions is a polyline with arc length greater than its chord.

Hierarchy is assigned at seeding time, not relabelled afterwards: arterials are
seeded first at wide spacing, collectors branch off arterials, locals branch off
collectors. Growth is fully deterministic given a seed.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .district_profiles import assign_district_archetypes, profile_for
from .generated_map import PreviewCityTopology
from .graph import Node, RoadClass, RoadLink
from metroflow.map.road_geometry import (
    CenterlineSource,
    LinkGeometryAssignment,
    RoadCenterline,
    RoadGeometryCatalog,
)

__all__ = [
    "GrowthConfig",
    "GrownStreet",
    "GrownNetwork",
    "grow_street_network",
    "compile_grown_network",
]


@dataclass(frozen=True, slots=True)
class GrowthConfig:
    """Per-class growth controls. Distances are meters unless noted."""

    arterial_spacing_m: float = 620.0
    collector_spacing_m: float = 270.0
    local_spacing_m: float = 82.0

    arterial_step_m: float = 110.0
    collector_step_m: float = 62.0
    local_step_m: float = 44.0

    # Maximum turn per growth step, in degrees. This is what creates circuity:
    # zero would reproduce the straight-segment failure exactly.
    arterial_turn_deg: float = 10.0
    collector_turn_deg: float = 15.0
    local_turn_deg: float = 19.0

    arterial_max_steps: int = 90
    collector_max_steps: int = 30
    local_max_steps: int = 14

    # A tip within this fraction of a step of an existing node snaps onto it
    # (degree 4); within this fraction of a street interior it splits it
    # (degree 3). Snap-to-node must be the tighter of the two or every
    # T-junction degenerates into a crossing.
    snap_node_fraction: float = 0.58
    snap_edge_fraction: float = 0.30

    # Intended share of local tips released as deliberate cul-de-sacs.
    #
    # It does not currently do that. `may_dead_end` is passed into `grow()` and
    # never read in its body; its only effect is at the call site, where a tip
    # flagged True gets FEWER growth steps than one flagged False -- the
    # polarity is inverted relative to the name. Dead ends in the compiled graph
    # come from tips that failed to contact, not from this share, and
    # `GrownNetwork.dead_end_count` is always 0.
    local_cul_de_sac_share: float = 0.34
    min_intensity: float = 0.055
    seed_jitter_m: float = 30.0
    redundancy_constraint_enabled: bool = False
    """Reject a seed whose ground a PARALLEL road of its class already covers.

    Off by default, and therefore dead: nothing in `src/` or `tests/` sets it
    True, so the shipped generator performs no occupancy rejection at all.

    It is also broken where it would run. `class_occupied` measures
    point-to-point distance to indexed VERTICES, not distance to segments, and
    `_index_vertex` skips vertex 0 entirely; at the tuned radius that misses
    11.2% of the seeds a segment-distance test rejects. At the default radius
    (135.3 m) it fires on 5707 of 5708 local seeds, which is unusable.

    The `0.59` duplication figure this docstring previously quoted does not
    reproduce at head -- it is off by 2.6x and its units were wrong (the metric
    returns redundant cells over occupied cells, not streets). Direction-aware
    duplication is 0.2270 as the test measures it, 0.2570 under a
    segmentation-invariant raster. See tests/test_growth_redundancy_and_bypass.py.
    """
    redundancy_radius_fraction: float = 0.55
    """Rejection radius as a fraction of that tier's spacing."""
    parallel_tolerance_deg: float = 32.0
    """How far off-parallel a nearby same-class road must be to count as new."""
    bypass_radius_m: float = 2100.0
    """Distance from the primary centre at which the bypass ring runs."""
    bypass_segment_count: int = 8
    spacing_scale: float = 3.0
    """Uniform multiplier on every street spacing.

    Calibrated against the offline OSM control extracts, which makes those
    extracts a development set rather than an independent control.

    The quoted band needs its convention named. `5.3-13.9 km/km2` is measured
    over a node BOUNDING BOX; the instrument this generator is actually scored
    with (`morphology_quality.py`, node convex hull) gives `7.4-17.8 km/km2` on
    the same five extracts. Generated fabric sits at 24.1-40.2 km/km2 over the
    30-case grid, i.e. outside the band under either convention.

    Intersection density is a different story and earlier text here got it
    wrong in both directions. Measured under ONE convention -- hull area, nodes
    of unique-neighbour degree >= 3 -- the extracts give 25.1-132.9 /km2 and
    generated fabric 102.2-138.6 /km2. So it overlaps the real range and sits
    near its top, rather than being comfortably inside it (the original claim)
    or clearly outside it (the first correction). Both earlier figures mixed a
    bounding-box denominator with a raw incident-edge degree, which double
    counts wherever parallel edges exist -- live on 4 of the 5 extracts.
    """
    district_profiles_enabled: bool = True
    """Vary local spacing, block size and cul-de-sac share by district.

    Off, the whole city grows with one spacing and one cul-de-sac share, so
    a downtown core and a suburb come out with identical fabric. On, each
    growth step reads the profile of the nearest urban centre.
    """


@dataclass(frozen=True, slots=True)
class GrownStreet:
    street_id: int
    road_class: RoadClass
    points_m: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class GrownNetwork:
    streets: tuple[GrownStreet, ...]
    dead_end_count: int
    junction_count: int


class _Grid:
    """Uniform-bucket index over growing geometry, for local snap queries."""

    def __init__(self, cell_m: float) -> None:
        self._cell = float(cell_m)
        self._cells: dict[tuple[int, int], list[int]] = {}

    @property
    def cell_m(self) -> float:
        return self._cell

    def _key(self, x: float, y: float) -> tuple[int, int]:
        return (int(math.floor(x / self._cell)), int(math.floor(y / self._cell)))

    def add(self, x: float, y: float, item: int) -> None:
        self._cells.setdefault(self._key(x, y), []).append(item)

    def near(self, x: float, y: float, radius: float) -> set[int]:
        span = int(math.ceil(radius / self._cell))
        cx, cy = self._key(x, y)
        out: set[int] = set()
        for dx in range(-span, span + 1):
            for dy in range(-span, span + 1):
                out.update(self._cells.get((cx + dx, cy + dy), ()))
        return out


class _Fabric:
    """Accumulates grown streets and answers snap queries against them."""

    def __init__(self, cell_m: float) -> None:
        self._cell = float(cell_m)
        self.nodes: list[tuple[float, float]] = []
        self.node_grid = _Grid(cell_m)
        # Each street is a growing polyline plus the node ids at its two ends.
        self.streets: list[list[tuple[float, float]]] = []
        self.street_class: list[RoadClass] = []
        self.vertex_grid = _Grid(cell_m)
        self.vertex_owner: list[tuple[int, int]] = []
        # Where each class already has pavement, so growth does not lay a second
        # road of the same class on ground the first one already covers.
        self.class_grid: dict[RoadClass, _Grid] = {}
        self.class_points: dict[RoadClass, list[tuple[tuple[float, float], int, float]]] = {}

    def add_node(self, point: tuple[float, float]) -> int:
        node_id = len(self.nodes)
        self.nodes.append(point)
        self.node_grid.add(point[0], point[1], node_id)
        return node_id

    def nearest_node(self, point: tuple[float, float], radius: float) -> int | None:
        best_id, best_distance = None, radius
        for node_id in self.node_grid.near(point[0], point[1], radius):
            other = self.nodes[node_id]
            distance = math.dist(point, other)
            if distance <= best_distance:
                best_id, best_distance = node_id, distance
        return best_id

    def nearest_contact(
        self, point: tuple[float, float], radius: float, *, exclude_street: int
    ) -> tuple[int, tuple[float, float]] | None:
        """Closest point on any nearby street SEGMENT, not just its vertices.

        Vertices sit one growth step apart (tens of metres) while the snap
        radius is a fraction of a step, so a vertex-only test lets a street
        cross another and carry on without connecting. Measuring to the segment
        is what makes a crossing become a junction.
        """

        best: tuple[int, tuple[float, float]] | None = None
        best_distance = radius
        for index in self.vertex_grid.near(point[0], point[1], radius):
            street_index, vertex_index = self.vertex_owner[index]
            if street_index == exclude_street:
                continue
            street = self.streets[street_index]
            for offset in (-1, 0):
                left_index = vertex_index + offset
                if left_index < 0 or left_index + 1 >= len(street):
                    continue
                left, right = street[left_index], street[left_index + 1]
                dx, dy = right[0] - left[0], right[1] - left[1]
                length_sq = dx * dx + dy * dy
                if length_sq <= 1e-12:
                    continue
                t = ((point[0] - left[0]) * dx + (point[1] - left[1]) * dy) / length_sq
                t = max(0.0, min(1.0, t))
                closest = (left[0] + t * dx, left[1] + t * dy)
                distance = math.dist(point, closest)
                if distance > best_distance:
                    continue
                # Snap to a real VERTEX of the other street, not to an arbitrary
                # point along it. `compile_grown_network` detects junctions by
                # shared coordinates, so a mid-segment contact leaves the other
                # street with no matching point and no junction is ever formed.
                vertex = left if math.dist(closest, left) <= math.dist(closest, right) else right
                best, best_distance = (street_index, vertex), distance
        return best

    def open_street(self, road_class: RoadClass, start: tuple[float, float]) -> int:
        street_index = len(self.streets)
        self.streets.append([start])
        self.street_class.append(road_class)
        self._index_vertex(street_index, 0)
        return street_index

    def extend(self, street_index: int, point: tuple[float, float]) -> None:
        self.streets[street_index].append(point)
        self._index_vertex(street_index, len(self.streets[street_index]) - 1)

    def _index_vertex(self, street_index: int, vertex_index: int) -> None:
        point = self.streets[street_index][vertex_index]
        self.vertex_owner.append((street_index, vertex_index))
        self.vertex_grid.add(point[0], point[1], len(self.vertex_owner) - 1)
        road_class = self.street_class[street_index]
        grid = self.class_grid.get(road_class)
        if grid is None:
            grid = _Grid(self._cell)
            self.class_grid[road_class] = grid
            self.class_points[road_class] = []
        points = self.class_points[road_class]
        street = self.streets[street_index]
        if vertex_index == 0:
            # A lone start point has no direction yet. Storing it as heading 0
            # makes every street look parallel to the x-axis and the occupancy
            # test then rejects nearly every seed. The segment leaving this
            # point is indexed when the next vertex arrives.
            return
        previous = street[vertex_index - 1]
        heading = math.atan2(point[1] - previous[1], point[0] - previous[0])
        grid.add(point[0], point[1], len(points))
        points.append((point, street_index, heading))

    def class_occupied(
        self,
        point: tuple[float, float],
        radius: float,
        road_class: RoadClass,
        *,
        heading: float,
        parallel_tolerance_rad: float,
        exclude_street: int | None = None,
    ) -> bool:
        """True when a PARALLEL street of this class already covers the ground.

        Direction matters. Rejecting every nearby same-class street also blocks
        perpendicular cross-streets, and those are exactly what forms junctions -
        without them every street ends as a stub. Only a road running roughly
        alongside an existing one is a duplicate.
        """

        grid = self.class_grid.get(road_class)
        if grid is None:
            return False
        points = self.class_points[road_class]
        for index in grid.near(point[0], point[1], radius):
            other, owner, other_heading = points[index]
            if exclude_street is not None and owner == exclude_street:
                continue
            if math.dist(point, other) > radius:
                continue
            # Compare undirected orientations: opposite headings are parallel.
            delta = abs(math.atan2(
                math.sin(heading - other_heading), math.cos(heading - other_heading)
            ))
            if min(delta, math.pi - delta) <= parallel_tolerance_rad:
                return True
        return False


def grow_street_network(
    *,
    terrain,
    urban_form,
    seed: int,
    config: GrowthConfig | None = None,
) -> GrownNetwork:
    """Grow a hierarchical street network over the accepted terrain fields."""

    cfg = config or GrowthConfig()
    rng = np.random.default_rng(int(seed) & 0xFFFF_FFFF)
    fabric = _Fabric(cell_m=max(cfg.local_step_m, 40.0))

    buildable = terrain.buildable_mask
    intensity = urban_form.development_intensity
    height, width = buildable.shape
    x_min = float(terrain.x_coordinates_m[0])
    y_min = float(terrain.y_coordinates_m[0])

    def cell_of(point: tuple[float, float]) -> tuple[int, int] | None:
        column = int((point[0] - x_min) / terrain.cell_size_x_m)
        row = int((point[1] - y_min) / terrain.cell_size_y_m)
        if 0 <= row < height and 0 <= column < width:
            return row, column
        return None

    def developable(point: tuple[float, float], floor: float) -> bool:
        cell = cell_of(point)
        if cell is None:
            return False
        return bool(buildable[cell]) and float(intensity[cell]) >= floor

    def field_angle(point: tuple[float, float]) -> float:
        cell = cell_of(point)
        if cell is None:
            return 0.0
        return math.atan2(
            float(urban_form.orientation_y[cell]), float(urban_form.orientation_x[cell])
        )

    def grow(
        start: tuple[float, float],
        heading: float,
        road_class: RoadClass,
        step_m: float,
        turn_deg: float,
        max_steps: int,
        floor: float,
        *,
        may_dead_end: bool,
        terminate_on_contact: bool = True,
        occupancy_radius_m: float = 0.0,
    ) -> tuple[int, bool] | None:
        """Grow one street from `start`. Returns (street_index, ended_free)."""

        if not developable(start, floor):
            return None
        # Parish-Muller local constraint, applied at SEEDING only: do not start
        # a road where this class already runs. Without it near-parallel streets
        # accumulate instead of merging, which inflates length without adding
        # intersections. It must not gate growth itself - a tip has to be free
        # to approach an existing street and snap onto it, or no junction ever
        # forms and every street ends as a stub.
        if occupancy_radius_m > 0.0 and cfg.redundancy_constraint_enabled:
            # Probe the ground the street will actually cover, one step out.
            # Testing `start` itself always rejects, because a branch is seeded
            # ON its parent - which for same-class passes (the arterial grid and
            # the cross-street pass) is a street of the very class being tested.
            probe = (
                start[0] + step_m * math.cos(heading),
                start[1] + step_m * math.sin(heading),
            )
            if fabric.class_occupied(
                probe,
                occupancy_radius_m,
                road_class,
                heading=heading,
                parallel_tolerance_rad=math.radians(cfg.parallel_tolerance_deg),
            ):
                return None
        street_index = fabric.open_street(road_class, start)
        # A branch is seeded ON its parent, so contact detection must stay off
        # until the tip has cleared it - otherwise every street terminates on
        # step one and the whole fabric collapses into stubs.
        clearance_steps = 1
        # A street's origin is a junction: later tips may snap onto it, which
        # is what turns a pair of T-junctions into a four-way crossing.
        fabric.add_node(start)
        tip = start
        ended_free = True
        for step_index in range(max_steps):
            # Follow the local grain: snap toward whichever of the orientation
            # field's four axes is closest to the current heading, then jitter
            # about THAT axis rather than about the previous heading. Letting
            # the heading random-walk instead makes every street a smooth arc
            # and drives orientation entropy to its maximum, which reads as a
            # contour plot rather than a city.
            axis = field_angle(tip)
            best = min(
                (axis + quarter * math.pi / 2.0 for quarter in range(4)),
                key=lambda candidate: abs(
                    math.atan2(math.sin(candidate - heading), math.cos(candidate - heading))
                ),
            )
            delta = math.atan2(math.sin(best - heading), math.cos(best - heading))
            limit = math.radians(turn_deg)
            heading += max(-limit, min(limit, delta))
            stepped = heading + math.radians(float(rng.normal(0.0, turn_deg * 0.30)))
            nxt = (tip[0] + step_m * math.cos(stepped), tip[1] + step_m * math.sin(stepped))

            if not developable(nxt, floor):
                ended_free = False
                break

            may_contact = terminate_on_contact and step_index >= clearance_steps
            node_hit = (
                fabric.nearest_node(nxt, step_m * cfg.snap_node_fraction)
                if may_contact
                else None
            )
            if node_hit is not None:
                fabric.extend(street_index, fabric.nodes[node_hit])
                ended_free = False
                break  # snapped onto an existing junction: raises its degree
            vertex_hit = (
                fabric.nearest_contact(
                    nxt, step_m * cfg.snap_edge_fraction, exclude_street=street_index
                )
                if may_contact
                else None
            )
            if vertex_hit is not None:
                _other_index, contact = vertex_hit
                fabric.extend(street_index, contact)
                # Splitting a street interior creates a new degree-3 junction.
                # Register it so later growth can snap onto it and lift it to a
                # four-way, instead of only ever producing T-junctions.
                fabric.add_node(contact)
                ended_free = False
                break

            fabric.extend(street_index, nxt)
            tip = nxt

        if len(fabric.streets[street_index]) < 2:
            # Too short to be a street. Truncate to a single point so it is
            # filtered out later; stale vertex references are guarded above.
            del fabric.streets[street_index][1:]
            return None
        return street_index, ended_free

    centers = tuple((float(c.x_m), float(c.y_m)) for c in urban_form.centers)
    gateways = tuple((float(x), float(y)) for x, y in urban_form.gateways_m)

    if cfg.district_profiles_enabled and centers:
        archetypes = assign_district_archetypes(center_count=len(centers), seed=seed)
        district_profiles = tuple(profile_for(name) for name in archetypes)
    else:
        district_profiles = ()

    def profile_at(point: tuple[float, float]):
        """Road character of the district containing `point` (nearest centre)."""

        if not district_profiles:
            return None
        index = min(
            range(len(centers)), key=lambda i: math.dist(point, centers[i])
        )
        return district_profiles[index]

    # --- arterials: long, low-curvature spokes and rings between anchors ------
    for center in centers:
        for index in range(6):
            angle = index * math.pi / 3.0 + float(rng.uniform(0.0, math.pi / 3.0))
            grow(
                (
                    center[0] + float(rng.normal(0.0, cfg.seed_jitter_m)),
                    center[1] + float(rng.normal(0.0, cfg.seed_jitter_m)),
                ),
                angle,
                RoadClass.ARTERIAL,
                cfg.arterial_step_m,
                cfg.arterial_turn_deg,
                cfg.arterial_max_steps,
                cfg.min_intensity * 0.4,
                may_dead_end=False,
                occupancy_radius_m=cfg.arterial_spacing_m * cfg.spacing_scale * 0.45,
            )
    for gateway in gateways:
        nearest = min(centers, key=lambda c: math.dist(c, gateway)) if centers else (0.0, 0.0)
        grow(
            gateway,
            math.atan2(nearest[1] - gateway[1], nearest[0] - gateway[0]),
            RoadClass.EXPRESSWAY,
            cfg.arterial_step_m,
            cfg.arterial_turn_deg * 0.5,
            cfg.arterial_max_steps,
            0.0,
            may_dead_end=False,
            terminate_on_contact=False,
            occupancy_radius_m=cfg.bypass_radius_m * 0.5,
        )

    # --- bypass ring: through traffic must be able to avoid the core ---------
    # Radial expressways all converge on the centre, so without this every
    # cross-city trip is forced through downtown.
    if centers:
        core = centers[0]
        radius = cfg.bypass_radius_m
        segments = max(6, int(cfg.bypass_segment_count))
        for index in range(segments):
            angle = 2.0 * math.pi * index / segments
            start = (core[0] + radius * math.cos(angle), core[1] + radius * math.sin(angle))
            grow(
                start,
                angle + math.pi / 2.0,  # tangential: run around the core
                RoadClass.EXPRESSWAY,
                cfg.arterial_step_m,
                cfg.arterial_turn_deg,
                cfg.arterial_max_steps,
                0.0,
                may_dead_end=False,
                terminate_on_contact=False,
                occupancy_radius_m=radius * 0.35,
            )

    # --- arterial grid: branch off the spokes at ~1 km, so major roads form a
    # --- network instead of a star. Without this the class mix collapses to
    # --- expressway -> collector with almost no arterial tier.
    _branch_pass(
        fabric,
        rng,
        cfg,
        grow,
        source_classes=(RoadClass.EXPRESSWAY, RoadClass.ARTERIAL),
        road_class=RoadClass.ARTERIAL,
        spacing_m=cfg.arterial_spacing_m,
        step_m=cfg.arterial_step_m,
        turn_deg=cfg.arterial_turn_deg,
        max_steps=cfg.arterial_max_steps,
        floor=cfg.min_intensity * 0.4,
        cul_de_sac_share=0.0,
        occupancy_fraction=cfg.redundancy_radius_fraction,
    )

    # --- collectors: branch perpendicular off whatever exists so far ---------
    _branch_pass(
        fabric,
        rng,
        cfg,
        grow,
        source_classes=(RoadClass.ARTERIAL, RoadClass.EXPRESSWAY),
        road_class=RoadClass.COLLECTOR,
        spacing_m=cfg.collector_spacing_m,
        step_m=cfg.collector_step_m,
        turn_deg=cfg.collector_turn_deg,
        max_steps=cfg.collector_max_steps,
        floor=cfg.min_intensity * 0.7,
        cul_de_sac_share=0.0,
        profile_at=profile_at,
        tier="collector",
        occupancy_fraction=cfg.redundancy_radius_fraction,
    )

    # --- locals: the only stage permitted to leave cul-de-sacs ---------------
    _branch_pass(
        fabric,
        rng,
        cfg,
        grow,
        source_classes=(RoadClass.COLLECTOR, RoadClass.ARTERIAL),
        road_class=RoadClass.LOCAL,
        spacing_m=cfg.local_spacing_m,
        step_m=cfg.local_step_m,
        turn_deg=cfg.local_turn_deg,
        max_steps=cfg.local_max_steps,
        floor=cfg.min_intensity,
        cul_de_sac_share=cfg.local_cul_de_sac_share,
        profile_at=profile_at,
        tier="local",
        occupancy_fraction=cfg.redundancy_radius_fraction,
    )

    # --- cross streets: close the blocks -------------------------------------
    # Locals all branch perpendicular off collectors, so without this pass they
    # are parallel to one another and the fabric is a comb, not a grid. Blocks
    # only exist once streets run both ways.
    _branch_pass(
        fabric,
        rng,
        cfg,
        grow,
        source_classes=(RoadClass.LOCAL,),
        road_class=RoadClass.LOCAL,
        spacing_m=cfg.local_spacing_m,
        step_m=cfg.local_step_m,
        turn_deg=cfg.local_turn_deg,
        max_steps=cfg.local_max_steps,
        floor=cfg.min_intensity,
        cul_de_sac_share=cfg.local_cul_de_sac_share,
        profile_at=profile_at,
        tier="local",
        occupancy_fraction=cfg.redundancy_radius_fraction,
    )

    streets = tuple(
        GrownStreet(street_id=index, road_class=fabric.street_class[index], points_m=tuple(points))
        for index, points in enumerate(fabric.streets)
        if len(points) >= 2
    )
    return GrownNetwork(streets=streets, dead_end_count=0, junction_count=len(fabric.nodes))


def _branch_pass(
    fabric: _Fabric,
    rng,
    cfg: GrowthConfig,
    grow,
    *,
    source_classes: tuple[RoadClass, ...],
    road_class: RoadClass,
    spacing_m: float,
    step_m: float,
    turn_deg: float,
    max_steps: int,
    floor: float,
    cul_de_sac_share: float,
    profile_at=None,
    tier: str = "local",
    occupancy_fraction: float = 0.0,
) -> None:
    """Seed new streets at fixed arc spacing along already-grown streets."""

    sources = [
        index
        for index, points in enumerate(fabric.streets)
        if len(points) >= 2 and fabric.street_class[index] in source_classes
    ]
    for street_index in sources:
        points = list(fabric.streets[street_index])
        travelled = 0.0
        next_seed = spacing_m * float(rng.uniform(0.3, 1.0))
        for left, right in zip(points, points[1:]):
            segment = math.dist(left, right)
            if segment <= 1e-9:
                continue
            while travelled + segment >= next_seed:
                t = (next_seed - travelled) / segment
                anchor = (
                    left[0] + t * (right[0] - left[0]),
                    left[1] + t * (right[1] - left[1]),
                )
                # Read the district at the anchor, so spacing, block size and
                # cul-de-sac share follow the district rather than the city.
                profile = profile_at(anchor) if profile_at is not None else None
                if profile is None:
                    local_spacing, local_step = spacing_m * cfg.spacing_scale, step_m
                    local_turn, local_steps = turn_deg, max_steps
                    local_dead_end = cul_de_sac_share
                elif tier == "collector":
                    local_spacing = profile.collector_spacing_m * cfg.spacing_scale
                    local_step, local_turn = step_m, turn_deg
                    local_steps, local_dead_end = max_steps, cul_de_sac_share
                else:
                    local_spacing = profile.local_spacing_m * cfg.spacing_scale
                    local_step = profile.local_step_m
                    local_turn = profile.local_turn_deg
                    local_steps = profile.local_max_steps
                    local_dead_end = profile.cul_de_sac_share

                tangent = math.atan2(right[1] - left[1], right[0] - left[0])
                for side in (tangent + math.pi / 2.0, tangent - math.pi / 2.0):
                    may_dead_end = float(rng.random()) < local_dead_end
                    grow(
                        anchor,
                        side,
                        road_class,
                        local_step,
                        local_turn,
                        local_steps if may_dead_end else local_steps + 2,
                        floor,
                        may_dead_end=may_dead_end,
                        occupancy_radius_m=local_spacing * occupancy_fraction,
                    )
                next_seed += local_spacing
            travelled += segment


# --- compilation -----------------------------------------------------------
#
# Chains between junctions become ONE curved centerline with arc-length links,
# rather than one link per polyline vertex. That is what lets circuity exceed
# 1.0: `planar_blocks._endpoint_topology` explodes polylines into per-vertex
# straight pairs, which pins circuity at exactly 1.0 no matter what the
# generator produces.

DESIGN = {
    RoadClass.EXPRESSWAY: (3, 27.8, 1.8),
    RoadClass.ARTERIAL: (2, 16.7, 1.1),
    RoadClass.COLLECTOR: (1, 11.1, 0.70),
    RoadClass.LOCAL: (1, 8.3, 0.45),
}


def compile_grown_network(streets, *, quantum_m: float = 1.0) -> PreviewCityTopology:
    """Split streets at shared vertices; keep each chain as ONE curved centerline."""

    def key(point):
        return (round(point[0] / quantum_m), round(point[1] / quantum_m))

    use_count: dict[tuple[int, int], int] = {}
    for street in streets:
        for index, point in enumerate(street.points_m):
            k = key(point)
            # Interior vertices count once; endpoints always anchor a node.
            use_count[k] = use_count.get(k, 0) + (
                2 if index in (0, len(street.points_m) - 1) else 1
            )

    node_id_by_key: dict[tuple[int, int], int] = {}
    nodes: list[Node] = []

    def node_for(point):
        k = key(point)
        existing = node_id_by_key.get(k)
        if existing is not None:
            return existing
        node_id = len(nodes)
        node_id_by_key[k] = node_id
        nodes.append(Node(node_id, x=float(point[0]), y=float(point[1])))
        return node_id

    chains: list[tuple[RoadClass, list]] = []
    for street in streets:
        points = list(street.points_m)
        current = [points[0]]
        for index in range(1, len(points)):
            current.append(points[index])
            is_end = index == len(points) - 1
            if is_end or use_count.get(key(points[index]), 0) >= 2:
                if len(current) >= 2:
                    chains.append((street.road_class, list(current)))
                current = [points[index]]

    links: list[RoadLink] = []
    centerlines = []
    assignments = []
    seen_pairs: set[tuple[int, int]] = set()
    for road_class, points in chains:
        deduped = [points[0]]
        for p in points[1:]:
            if math.dist(p, deduped[-1]) > 1e-6:
                deduped.append(p)
        if len(deduped) < 2:
            continue
        src, dst = node_for(deduped[0]), node_for(deduped[-1])
        if src == dst:
            continue
        pair = (min(src, dst), max(src, dst))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        arc = sum(math.dist(a, b) for a, b in zip(deduped, deduped[1:]))
        if arc <= 0.0:
            continue
        lanes, speed, capacity = DESIGN[road_class]
        geometry_id = len(centerlines)
        # Anchor endpoints exactly on the node coordinates.
        snapped = [(nodes[src].x, nodes[src].y)] + [
            (float(p[0]), float(p[1])) for p in deduped[1:-1]
        ] + [(nodes[dst].x, nodes[dst].y)]
        cleaned = [snapped[0]]
        for p in snapped[1:]:
            if math.dist(p, cleaned[-1]) > 1e-9:
                cleaned.append(p)
        if len(cleaned) < 2:
            continue
        centerlines.append(
            RoadCenterline(
                geometry_id=geometry_id,
                points_m=tuple(cleaned),
                source=CenterlineSource.SYNTHETIC,
            )
        )
        arc = sum(math.dist(a, b) for a, b in zip(cleaned, cleaned[1:]))
        forward_id = len(links)
        links.append(
            RoadLink(
                link_id=forward_id, src_node_id=src, dst_node_id=dst,
                road_class=road_class, length_m=arc, free_flow_speed_mps=speed,
                capacity_veh_per_tick=capacity, lanes=lanes, physical_road_id=geometry_id,
            )
        )
        links.append(
            RoadLink(
                link_id=forward_id + 1, src_node_id=dst, dst_node_id=src,
                road_class=road_class, length_m=arc, free_flow_speed_mps=speed,
                capacity_veh_per_tick=capacity, lanes=lanes, physical_road_id=geometry_id,
            )
        )
        assignments.append(LinkGeometryAssignment(link_id=forward_id, geometry_id=geometry_id))
        assignments.append(
            LinkGeometryAssignment(link_id=forward_id + 1, geometry_id=geometry_id, reversed=True)
        )

    geometry = RoadGeometryCatalog(
        centerlines=tuple(centerlines), assignments=tuple(assignments)
    )
    return PreviewCityTopology(
        nodes=tuple(nodes), links=tuple(links), road_geometry=geometry,
        metadata={"engine": "growth_fabric_v1"},
    )


