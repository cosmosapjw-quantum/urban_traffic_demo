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

from .growth_topology import WELD_TOLERANCE_M, StreetTopologyBuilder, iter_chains
from .district_profiles import assign_district_archetypes, profile_for
from .generated_map import PreviewCityTopology
from .graph import Node, RoadClass, RoadLink
from metroflow.map.road_geometry import (
    CenterlineSource,
    LinkGeometryAssignment,
    RoadCenterline,
    RoadGeometryCatalog,
    _point_to_segment_distance,
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
    # The recorded topology. `compile_grown_network` consumes this instead of
    # re-deriving junctions from rounded coordinates; `None` only for networks
    # built by older callers that pass a bare street tuple.
    topology: object | None = None


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
    """Accumulates grown streets, with topology recorded as it is created.

    Backed by `StreetTopologyBuilder`: a junction is a node id minted where the
    junction happens and shared by everything incident to it. The previous
    version kept plain point lists and left a later pass to infer junctions from
    coordinates, which is how 97.6% of streets came to begin on another street's
    interior with no node there.

    The spatial grids index BUILDER ids, so they are a search accelerator and
    never an authority: what is connected to what is answered by the builder.
    """

    def __init__(self, cell_m: float) -> None:
        self._cell = float(cell_m)
        self.builder = StreetTopologyBuilder()
        self.node_grid = _Grid(cell_m)
        self.street_class: list[RoadClass] = []
        # street id -> True once it owns at least one segment, so contact search
        # can skip seeds that have not grown.
        self.segment_grid = _Grid(cell_m)
        self._indexed_segments: set[tuple[int, int]] = set()
        self._segment_refs: list[tuple[int, int]] = []
        self.class_grid: dict[RoadClass, _Grid] = {}
        self.class_points: dict[RoadClass, list[tuple[tuple[float, float], int, float]]] = {}

    # --- geometry, delegated to the builder --------------------------------

    @property
    def streets(self) -> list[list[tuple[float, float]]]:
        """Point view, for callers that only read geometry."""

        return [list(self.builder.points_of(sid)) for sid in self.builder.street_ids]

    def points_of(self, street_id: int) -> tuple[tuple[float, float], ...]:
        return self.builder.points_of(street_id)

    def open_street(
        self,
        road_class: RoadClass,
        start: tuple[float, float],
        *,
        start_node_id: int | None = None,
        layer: int = 0,
    ) -> int:
        street_id = self.builder.open_street(
            points=(start,), start_node_id=start_node_id, layer=layer
        )
        self.street_class.append(road_class)
        node_id = self.builder.node_ids_of(street_id)[0]
        self.node_grid.add(start[0], start[1], node_id)
        return street_id

    def extend(self, street_id: int, point: tuple[float, float]) -> None:
        node_id = self.builder.extend_street(street_id, point)
        self.node_grid.add(point[0], point[1], node_id)
        self._index_last_segment(street_id)

    def extend_to_node(self, street_id: int, node_id: int, *, max_gap_m: float) -> bool:
        """Finish a street ON an existing junction. False if it cannot legally."""

        try:
            self.builder.extend_street_to_node(street_id, node_id, max_gap_m=max_gap_m)
        except ValueError:
            # Already on this street, or too far to weld without inventing
            # length. Either way the tip simply stops here.
            return False
        self._index_last_segment(street_id)
        return True

    def prepend_to_node(self, street_id: int, node_id: int, *, max_gap_m: float) -> bool:
        """Finish the start of a street ON an existing junction. False if it cannot legally."""

        try:
            self.builder.prepend_street_to_node(street_id, node_id, max_gap_m=max_gap_m)
        except ValueError:
            return False
        self._reindex_street(street_id)
        return True

    def split_at_arc_length(self, street_id: int, arc_length_m: float) -> int:
        return self.builder.split_at_arc_length(street_id, arc_length_m)

    def arc_length_of(self, street_id: int) -> float:
        return self.builder.arc_length_of(street_id)

    # --- snap queries -------------------------------------------------------

    def nearest_node(self, point: tuple[float, float], radius: float) -> int | None:
        best_id, best_distance = None, radius
        for node_id in self.node_grid.near(point[0], point[1], radius):
            distance = math.dist(point, self.builder.point_of(node_id))
            if distance <= best_distance:
                best_id, best_distance = node_id, distance
        return best_id

    def point_of(self, node_id: int) -> tuple[float, float]:
        return self.builder.point_of(node_id)

    def nearest_contact_street(
        self, point: tuple[float, float], radius: float, *, exclude_street: int
    ) -> int | None:
        """Which street runs closest to `point`, measured to its SEGMENTS.

        Returns the street, not a coordinate. The caller then asks the builder
        to split it, which inserts the projection into that street's own
        polyline -- so a contact that is not a shared node is unrepresentable
        rather than merely discouraged.
        """

        best_street, best_distance = None, radius
        for key in self.segment_grid.near(point[0], point[1], radius):
            street_id, vertex_index = self._segment_refs[key]
            if street_id == exclude_street:
                continue
            points = self.builder.points_of(street_id)
            if vertex_index + 1 >= len(points):
                continue
            left, right = points[vertex_index], points[vertex_index + 1]
            distance = _point_to_segment_distance(point, left, right)
            if distance <= best_distance:
                best_street, best_distance = street_id, distance
        return best_street

    def nearest_crossing(
        self,
        tip: tuple[float, float],
        nxt: tuple[float, float],
        *,
        exclude_street: int,
    ) -> tuple[int, tuple[float, float]] | None:
        """First street the STEP crosses, and where.

        Testing only the arriving point misses every street the step clears in
        one stride, which is why 1942 crossings on grid_core/17 stayed
        unregistered after contacts were fixed: a step is tens of metres and the
        contact radius is a fraction of that.
        """

        best: tuple[int, tuple[float, float]] | None = None
        best_distance = float("inf")
        radius = math.dist(tip, nxt)
        midpoint = ((tip[0] + nxt[0]) / 2.0, (tip[1] + nxt[1]) / 2.0)
        for key in self.segment_grid.near(midpoint[0], midpoint[1], radius):
            street_id, vertex_index = self._segment_refs[key]
            if street_id == exclude_street:
                continue
            points = self.builder.points_of(street_id)
            if vertex_index + 1 >= len(points):
                continue
            hit = _segment_intersection(tip, nxt, points[vertex_index], points[vertex_index + 1])
            if hit is None:
                continue
            distance = math.dist(tip, hit)
            if distance < best_distance:
                best, best_distance = (street_id, hit), distance
        return best

    def nearest_crossing_target(self, point: tuple[float, float]) -> int | None:
        """Street whose geometry passes closest to `point`."""

        best, best_distance = None, float("inf")
        for key in self.segment_grid.near(point[0], point[1], self._cell):
            street_id, vertex_index = self._segment_refs[key]
            points = self.builder.points_of(street_id)
            if vertex_index + 1 >= len(points):
                continue
            distance = _point_to_segment_distance(
                point, points[vertex_index], points[vertex_index + 1]
            )
            if distance < best_distance:
                best, best_distance = street_id, distance
        return best

    def bind_node_into_street(
        self, street_id: int, node_id: int, *, tolerance_m: float
    ) -> bool:
        bound = self.builder.bind_node_into_street(
            street_id, node_id, tolerance_m=tolerance_m
        )
        if bound:
            self._reindex_street(street_id)
        return bound

    def contact(
        self, street_id: int, point: tuple[float, float], radius: float
    ) -> int | None:
        node_id = self.builder.contact(street_id, point=point, tolerance_m=radius)
        if node_id is not None:
            self._reindex_street(street_id)
            self.node_grid.add(*self.builder.point_of(node_id), node_id)
        return node_id

    # --- indexing -----------------------------------------------------------

    _segment_refs: list[tuple[int, int]]

    def _index_last_segment(self, street_id: int) -> None:
        points = self.builder.points_of(street_id)
        if len(points) < 2:
            return
        self._index_segment(street_id, len(points) - 2)
        self._index_class_segment(street_id, len(points) - 2)

    def _reindex_street(self, street_id: int) -> None:
        """A split renumbers this street's segments, so index them all again.

        The dedupe guard is keyed on (street, vertex index), and a split SHIFTS
        every index after it -- so without clearing the guard first, the
        renumbered segments are silently skipped and the crossing search stops
        seeing parts of a street it has already split. Over-covering is safe:
        the grid is a candidate filter and every hit is re-measured against live
        geometry.
        """

        self._indexed_segments = {
            key for key in self._indexed_segments if key[0] != street_id
        }
        points = self.builder.points_of(street_id)
        for index in range(len(points) - 1):
            self._index_segment(street_id, index)

    def _index_segment(self, street_id: int, vertex_index: int) -> None:
        if (street_id, vertex_index) in self._indexed_segments:
            return
        self._indexed_segments.add((street_id, vertex_index))
        points = self.builder.points_of(street_id)
        left, right = points[vertex_index], points[vertex_index + 1]
        key = len(self._segment_refs)
        self._segment_refs.append((street_id, vertex_index))
        # Sample along the segment, not just its ends and middle. An arterial
        # step is 110 m against a 44 m grid cell, so three samples leave cells
        # the segment passes through with no entry, and a crossing search
        # centred in one of them finds nothing.
        span = math.dist(left, right)
        samples = max(int(span / (self._cell * 0.5)) + 1, 2)
        for index in range(samples + 1):
            t = index / samples
            self.segment_grid.add(
                left[0] + t * (right[0] - left[0]),
                left[1] + t * (right[1] - left[1]),
                key,
            )

    def _index_class_segment(self, street_id: int, vertex_index: int) -> None:
        road_class = self.street_class[street_id]
        grid = self.class_grid.get(road_class)
        if grid is None:
            grid = _Grid(self._cell)
            self.class_grid[road_class] = grid
            self.class_points[road_class] = []
        points = self.builder.points_of(street_id)
        left, right = points[vertex_index], points[vertex_index + 1]
        heading = math.atan2(right[1] - left[1], right[0] - left[0])
        entries = self.class_points[road_class]
        grid.add(right[0], right[1], len(entries))
        entries.append((right, street_id, heading))

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
        start_node_id: int | None = None,
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
        street_index = fabric.open_street(
            road_class, start, start_node_id=start_node_id
        )
        # A branch is seeded ON its parent, so contact detection must stay off
        # until the tip has cleared it - otherwise every street terminates on
        # step one and the whole fabric collapses into stubs.
        clearance_steps = 1
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
                # Bind to the junction itself. Appending a copy of its
                # coordinates is what used to leave two nodes at one point with
                # nothing joining them.
                fabric.extend_to_node(street_index, node_hit, max_gap_m=step_m)
                ended_free = False
                break  # snapped onto an existing junction: raises its degree
            # A step that crosses a street must register that crossing, even
            # when neither endpoint lands near it, and even when this street is
            # not the kind that stops on contact. Two roads meeting at grade is
            # a junction regardless of whether either of them ends there --
            # gating registration on `terminate_on_contact` left every
            # expressway and bypass arc crossing the city unrecorded.
            #
            # Not gated on `may_contact` either: `_segment_intersection` is
            # strictly interior, so a child leaving its parent's node shares an
            # endpoint rather than crossing, and needs no clearance window.
            crossing = fabric.nearest_crossing(tip, nxt, exclude_street=street_index)
            if crossing is not None:
                crossed_street, hit = crossing
                junction = fabric.contact(crossed_street, hit, step_m)
                bound = fabric.extend_to_node(
                    street_index, junction, max_gap_m=step_m * 1.5
                ) if junction is not None else False
                if bound and not terminate_on_contact:
                    # Carry on THROUGH the junction, so a limited-access road
                    # still records where it meets the surface streets.
                    tip = fabric.point_of(junction)
                    continue
                # Whether or not the tip could be bound to the junction, this
                # step has reached a street it crosses and must not continue
                # past it. Falling through to `extend(nxt)` would step straight
                # over the crossing and leave it unregistered -- which is what
                # kept 123 arterial-by-local crossings alive after the swept
                # test landed, since `extend_to_node` legitimately refuses when
                # the junction is already on this street or lies beyond the gap.
                ended_free = False
                break

            contact_radius = step_m * cfg.snap_edge_fraction
            target = (
                fabric.nearest_contact_street(
                    nxt, contact_radius, exclude_street=street_index
                )
                if may_contact
                else None
            )
            if target is not None:
                # Split the TARGET at the true projection, which inserts that
                # vertex into the target's own polyline, then finish this street
                # on the node that split produced. Both streets now carry the
                # same node id, so the junction exists in the graph and not only
                # on the page. The old path appended a copy of a nearby vertex
                # and left them unconnected.
                junction = fabric.contact(target, nxt, contact_radius)
                if junction is not None and fabric.extend_to_node(
                    street_index, junction, max_gap_m=step_m
                ):
                    ended_free = False
                    break

            fabric.extend(street_index, nxt)
            tip = nxt

        if len(fabric.points_of(street_index)) < 2:
            # A seed that never grew. It owns one node and no segment, so
            # `iter_chains` skips it; nothing needs truncating because the
            # builder never materialised a segment to begin with.
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

    _register_remaining_crossings(fabric)
    _extend_dangling_tips(fabric, max_reach_m=cfg.local_step_m * 1.5)
    _finalize_geometry_repairs(fabric)

    # The builder is the authority now, so the network carries it: junction and
    # dead-end counts are read off recorded incidence rather than guessed from
    # coordinates. `dead_end_count` used to be hardcoded to 0.
    builder = fabric.builder
    streets = tuple(
        GrownStreet(
            street_id=street_id,
            road_class=fabric.street_class[street_id],
            points_m=builder.points_of(street_id),
        )
        for street_id in builder.street_ids
        if len(builder.node_ids_of(street_id)) >= 2
    )
    junctions = builder.junction_node_ids()
    dead_ends = sum(
        1
        for node_id in junctions
        if len(builder.incident_street_ids(node_id)) == 1
        and sum(
            1
            for street_id in builder.incident_street_ids(node_id)
            for position in (0, -1)
            if builder.node_ids_of(street_id)[position] == node_id
        )
        == 1
    )
    return GrownNetwork(
        streets=streets,
        dead_end_count=dead_ends,
        junction_count=len(junctions),
        topology=builder,
    )


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
        street_id
        for street_id in fabric.builder.street_ids
        if len(fabric.builder.node_ids_of(street_id)) >= 2
        and fabric.street_class[street_id] in source_classes
    ]
    for street_index in sources:
        # Anchors are chosen as ARC LENGTHS first, then resolved. Splitting the
        # parent inserts vertices into it, which would invalidate any positional
        # walk mid-iteration -- arc length is invariant under exactly that
        # mutation, which is why the topology model addresses positions this way.
        points = list(fabric.points_of(street_index))
        anchor_arcs: list[float] = []
        travelled = 0.0
        # The phase must be drawn from the SAME spacing the increment uses.
        # Drawing it from raw class spacing while incrementing by the scaled,
        # district-resolved value put the two a factor of `spacing_scale` apart:
        # local raw is 82 m against 246-990 m scaled, so every source shorter
        # than one scaled interval was seeded every time and the increment never
        # fired again. That also made `spacing_scale` -- documented as the OSM
        # calibration knob -- inert for the first anchor on every street.
        next_seed = _local_spacing_at(
            points[0], cfg, spacing_m, profile_at=profile_at, tier=tier
        ) * float(rng.uniform(0.3, 1.0))
        for left, right in zip(points, points[1:]):
            segment = math.dist(left, right)
            if segment <= 1e-9:
                continue
            while travelled + segment >= next_seed:
                anchor_arcs.append(next_seed)
                probe = (
                    left[0] + ((next_seed - travelled) / segment) * (right[0] - left[0]),
                    left[1] + ((next_seed - travelled) / segment) * (right[1] - left[1]),
                )
                next_seed += _local_spacing_at(
                    probe, cfg, spacing_m, profile_at=profile_at, tier=tier
                )
            travelled += segment

        for anchor_arc in anchor_arcs:
            # Split the parent HERE. The node this returns belongs to the parent
            # and to both children, so the branch origin is a junction in the
            # graph and not merely a point where three polylines happen to
            # coincide. Previously the anchor was interpolated and discarded,
            # leaving 97.6% of streets beginning on another street's interior
            # with no node there.
            anchor_node = fabric.split_at_arc_length(street_index, anchor_arc)
            anchor = fabric.point_of(anchor_node)
            profile = profile_at(anchor) if profile_at is not None else None
            if profile is None:
                local_step, local_turn = step_m, turn_deg
                local_steps, local_dead_end = max_steps, cul_de_sac_share
            elif tier == "collector":
                local_step, local_turn = step_m, turn_deg
                local_steps, local_dead_end = max_steps, cul_de_sac_share
            else:
                local_step = profile.local_step_m
                local_turn = profile.local_turn_deg
                local_steps = profile.local_max_steps
                local_dead_end = profile.cul_de_sac_share
            local_spacing = _local_spacing_at(
                anchor, cfg, spacing_m, profile_at=profile_at, tier=tier
            )

            tangent = _tangent_at(fabric, street_index, anchor_node)
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
                    # Bind the child to the junction the split produced, rather
                    # than starting a fresh node at the same coordinates.
                    start_node_id=anchor_node,
                )


def _local_spacing_at(point, cfg, spacing_m, *, profile_at, tier):
    """Spacing the district at `point` asks for, scaled."""

    profile = profile_at(point) if profile_at is not None else None
    if profile is None:
        return spacing_m * cfg.spacing_scale
    if tier == "collector":
        return profile.collector_spacing_m * cfg.spacing_scale
    return profile.local_spacing_m * cfg.spacing_scale


def _tangent_at(fabric: "_Fabric", street_id: int, node_id: int) -> float:
    """Direction of the parent street where the branch leaves it."""

    node_ids = fabric.builder.node_ids_of(street_id)
    index = node_ids.index(node_id)
    left_index = max(index - 1, 0)
    right_index = min(index + 1, len(node_ids) - 1)
    left = fabric.point_of(node_ids[left_index])
    right = fabric.point_of(node_ids[right_index])
    return math.atan2(right[1] - left[1], right[0] - left[0])


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


def compile_grown_network(network, *, quantum_m: float = 1.0) -> PreviewCityTopology:
    """Compile a grown network into a topology, from recorded incidence.

    Accepts a `GrownNetwork` (preferred) or a bare tuple of `GrownStreet`.

    With a `GrownNetwork` the junctions come from `StreetTopologyBuilder`: a node
    is where growth said a junction is. Nothing here compares coordinates, so
    translating the city cannot change its graph, two streets between one pair of
    junctions both survive, and a branch origin is connected to its parent.

    The bare-tuple path is the previous behaviour -- junctions inferred from
    coordinates rounded to `quantum_m` -- kept for callers that hold streets
    without their topology. It carries every defect the builder exists to
    remove, and says so.
    """

    builder = getattr(network, "topology", None)
    streets = getattr(network, "streets", network)
    if builder is None:
        return _compile_from_coordinates(streets, quantum_m=quantum_m)
    return _compile_from_incidence(builder, streets)


def _compile_from_incidence(builder, streets) -> PreviewCityTopology:
    class_by_street = {street.street_id: street.road_class for street in streets}

    chains = iter_chains(builder)
    used_nodes: list[int] = []
    index_by_node: dict[int, int] = {}

    def node_index(node_id: int) -> int:
        existing = index_by_node.get(node_id)
        if existing is not None:
            return existing
        compact = len(used_nodes)
        index_by_node[node_id] = compact
        used_nodes.append(node_id)
        return compact

    links: list[RoadLink] = []
    centerlines: list[RoadCenterline] = []
    assignments: list[LinkGeometryAssignment] = []
    dropped: list[str] = []

    for street_id, chain_nodes in chains:
        road_class = class_by_street.get(street_id)
        if road_class is None:
            dropped.append(f"street {street_id}: no road class")
            continue
        points = [builder.point_of(node_id) for node_id in chain_nodes]
        arc = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
        if arc <= 0.0:
            dropped.append(f"street {street_id}: zero-length chain")
            continue
        if chain_nodes[0] == chain_nodes[-1]:
            # A closed chain cannot be one link: `RoadLink` requires src != dst.
            # Split it at its midpoint node so the loop survives as two links
            # rather than being dropped, which is what the old compiler did.
            middle = len(chain_nodes) // 2
            if middle == 0:
                dropped.append(f"street {street_id}: unsplittable closed chain")
                continue
            halves = [chain_nodes[: middle + 1], chain_nodes[middle:]]
        else:
            halves = [list(chain_nodes)]

        for part in halves:
            if len(part) < 2 or part[0] == part[-1]:
                dropped.append(f"street {street_id}: degenerate chain half")
                continue
            part_points = [builder.point_of(node_id) for node_id in part]
            part_arc = sum(math.dist(a, b) for a, b in zip(part_points, part_points[1:]))
            if part_arc <= 0.0:
                dropped.append(f"street {street_id}: zero-length chain half")
                continue
            src, dst = node_index(part[0]), node_index(part[-1])
            lanes, speed, capacity = DESIGN[road_class]
            geometry_id = len(centerlines)
            centerlines.append(
                RoadCenterline(
                    geometry_id=geometry_id,
                    points_m=tuple(part_points),
                    source=CenterlineSource.SYNTHETIC,
                    layer=builder.street_layer(street_id),
                )
            )
            forward_id = len(links)
            for source, destination in ((src, dst), (dst, src)):
                links.append(
                    RoadLink(
                        link_id=len(links),
                        src_node_id=source,
                        dst_node_id=destination,
                        road_class=road_class,
                        length_m=part_arc,
                        free_flow_speed_mps=speed,
                        capacity_veh_per_tick=capacity,
                        lanes=lanes,
                        physical_road_id=geometry_id,
                    )
                )
            assignments.append(
                LinkGeometryAssignment(link_id=forward_id, geometry_id=geometry_id)
            )
            assignments.append(
                LinkGeometryAssignment(
                    link_id=forward_id + 1, geometry_id=geometry_id, reversed=True
                )
            )

    nodes = tuple(
        Node(compact, x=float(builder.point_of(node_id)[0]), y=float(builder.point_of(node_id)[1]))
        for compact, node_id in enumerate(used_nodes)
    )
    return PreviewCityTopology(
        nodes=nodes,
        links=tuple(links),
        road_geometry=RoadGeometryCatalog(
            centerlines=tuple(centerlines), assignments=tuple(assignments)
        ),
        metadata={
            "engine": "growth_fabric_v1",
            "topology_source": "recorded_incidence",
            # Every chain the compiler declined to emit, with its reason. The
            # previous compiler dropped a second street between one node pair
            # silently; nothing may leave this function unrecorded.
            "dropped_chain_count": len(dropped),
            "dropped_chain_reasons": tuple(dropped[:32]),
            # Fragments that reach nothing. A road nobody can drive to is a
            # generator defect, so it is counted rather than quietly tolerated
            # or silently deleted.
            **_connectivity_metadata(links, len(used_nodes)),
        },
    )


def _compile_from_coordinates(streets, *, quantum_m: float = 1.0) -> PreviewCityTopology:
    """Legacy path: infer junctions by rounding coordinates.

    Retained only for callers holding streets without their builder. Every
    defect measured against this path is still present here -- a branch origin
    is not a junction, a translation changes the graph, and a second street
    between one node pair is dropped.
    """

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




def _segment_intersection(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> tuple[float, float] | None:
    """Proper crossing point of two segments, or None.

    Proper means strictly interior to both: segments that merely share an
    endpoint already meet at a node, and treating that as a crossing would split
    a street at a junction it already has.
    """

    d1x, d1y = a2[0] - a1[0], a2[1] - a1[1]
    d2x, d2y = b2[0] - b1[0], b2[1] - b1[1]
    denominator = d1x * d2y - d1y * d2x
    if abs(denominator) < 1e-12:
        return None  # parallel or degenerate
    ox, oy = b1[0] - a1[0], b1[1] - a1[1]
    t = (ox * d2y - oy * d2x) / denominator
    u = (ox * d1y - oy * d1x) / denominator
    if not (1e-9 < t < 1.0 - 1e-9) or not (1e-9 < u < 1.0 - 1e-9):
        return None
    return (a1[0] + t * d1x, a1[1] + t * d1y)


def _register_remaining_crossings(fabric: _Fabric) -> int:
    """Split every same-grade crossing the growth loop did not catch.

    The loop tests each step before taking it, which cannot cover geometry
    created after the test: `extend_to_node` appends a segment from the tip to
    the junction, and that segment can cross a third street nobody re-examined.
    Measured on grid_core/17, the loop catches 893 crossings and leaves 223.

    Patching each growth path to re-test its own output would make the invariant
    depend on every future path remembering to do so. A sweep afterwards makes it
    structural: whatever the loop produced, a same-grade crossing ends up as a
    junction. Splitting introduces new segments, so it iterates until a round
    finds none -- bounded, because each split strictly shortens the segments that
    remain crossable.
    """

    registered = 0
    state = _crossing_state_signature(fabric)
    while True:
        crossings = state[1]
        if not crossings:
            return registered
        progressed = False
        for left_street, right_street, point in crossings:
            # Split ONE street, then make the other adopt that same node.
            # Splitting both independently mints two nodes at one point, which
            # is the very coincidence this module exists to prevent.
            junction = fabric.contact(left_street, point, 1.0)
            if junction is None:
                continue
            fabric.bind_node_into_street(right_street, junction, tolerance_m=1.0)
            next_state = _crossing_state_signature(fabric)
            if next_state != state:
                registered += 1
                progressed = True
                state = next_state
                # Both streets have changed their segment indices. Re-measure
                # live geometry before selecting the next crossing.
                break
        if not progressed:
            raise RuntimeError(
                "crossing repair made no progress with "
                f"{len(_find_crossings(fabric))} crossings remaining"
            )


def _crossing_state_signature(
    fabric: _Fabric,
) -> tuple[
    tuple[tuple[int, tuple[tuple[float, float], ...]], ...],
    tuple[tuple[int, int, tuple[float, float]], ...],
]:
    """Canonical live geometry plus unresolved crossings for repair progress."""

    return (
        tuple(
            (street_id, fabric.builder.points_of(street_id))
            for street_id in fabric.builder.street_ids
        ),
        tuple(_find_crossings(fabric)),
    )


def _find_crossings(fabric: _Fabric) -> list[tuple[int, int, tuple[float, float]]]:
    """Same-grade proper crossings between distinct streets, deterministic order."""

    cell = max(fabric.segment_grid.cell_m, 1.0)
    buckets: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for street_id in fabric.builder.street_ids:
        points = fabric.builder.points_of(street_id)
        for index in range(len(points) - 1):
            left, right = points[index], points[index + 1]
            for key in _segment_supercover_cells(left, right, cell):
                buckets.setdefault(key, []).append((street_id, index))

    candidates: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    for entries in buckets.values():
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                left_ref, right_ref = sorted((entries[i], entries[j]))
                left_street, left_index = left_ref
                right_street, right_index = right_ref
                if left_street == right_street:
                    continue
                if (
                    fabric.builder.street_layer(left_street)
                    != fabric.builder.street_layer(right_street)
                ):
                    continue
                candidates.add((left_ref, right_ref))

    found: list[tuple[int, int, tuple[float, float]]] = []
    for (left_street, left_index), (right_street, right_index) in sorted(candidates):
        left_node_ids = fabric.builder.node_ids_of(left_street)
        right_node_ids = fabric.builder.node_ids_of(right_street)
        if left_index + 1 >= len(left_node_ids) or right_index + 1 >= len(right_node_ids):
            continue
        left_pair = {left_node_ids[left_index], left_node_ids[left_index + 1]}
        right_pair = {right_node_ids[right_index], right_node_ids[right_index + 1]}
        if left_pair & right_pair:
            continue
        left_points = fabric.builder.points_of(left_street)
        right_points = fabric.builder.points_of(right_street)
        hit = _segment_intersection(
            left_points[left_index], left_points[left_index + 1],
            right_points[right_index], right_points[right_index + 1],
        )
        if hit is not None:
            found.append((left_street, right_street, hit))
    return found


def _segment_supercover_cells(
    left: tuple[float, float],
    right: tuple[float, float],
    cell_m: float,
) -> tuple[tuple[int, int], ...]:
    """Cells a segment touches, in traversal order, without filling its bbox.

    This is a deterministic 2-D grid traversal. At a corner tie it emits both
    orthogonal neighbours before the diagonal cell, so a segment touching a
    cell only at a corner cannot lose a crossing candidate. A segment lying on
    a grid boundary carries cells on both sides of that boundary.
    """

    cell = float(cell_m)
    if not math.isfinite(cell) or cell <= 0.0:
        raise ValueError("cell_m must be finite and > 0")
    x0, y0 = left
    x1, y1 = right
    dx, dy = x1 - x0, y1 - y0
    x_cell = math.floor(x0 / cell)
    y_cell = math.floor(y0 / cell)
    x_step = 1 if dx > 0.0 else -1 if dx < 0.0 else 0
    y_step = 1 if dy > 0.0 else -1 if dy < 0.0 else 0
    if x_step < 0 and _is_grid_boundary(x0, cell):
        x_cell -= 1
    if y_step < 0 and _is_grid_boundary(y0, cell):
        y_cell -= 1

    x_on_boundary = x_step == 0 and _is_grid_boundary(x0, cell)
    y_on_boundary = y_step == 0 and _is_grid_boundary(y0, cell)
    cells: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    def add(cell_x: int, cell_y: int) -> None:
        candidates = [(cell_x, cell_y)]
        if x_on_boundary:
            candidates.append((cell_x - 1, cell_y))
        if y_on_boundary:
            candidates.append((cell_x, cell_y - 1))
        if x_on_boundary and y_on_boundary:
            candidates.append((cell_x - 1, cell_y - 1))
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                cells.append(candidate)

    add(x_cell, y_cell)
    x_delta = cell / abs(dx) if x_step else float("inf")
    y_delta = cell / abs(dy) if y_step else float("inf")
    next_x = (x_cell + (1 if x_step > 0 else 0)) * cell
    next_y = (y_cell + (1 if y_step > 0 else 0)) * cell
    x_max = (next_x - x0) / dx if x_step else float("inf")
    y_max = (next_y - y0) / dy if y_step else float("inf")

    while min(x_max, y_max) <= 1.0 + 1e-12:
        if x_max < y_max - 1e-12:
            x_cell += x_step
            add(x_cell, y_cell)
            x_max += x_delta
        elif y_max < x_max - 1e-12:
            y_cell += y_step
            add(x_cell, y_cell)
            y_max += y_delta
        else:
            previous_x, previous_y = x_cell, y_cell
            x_cell += x_step
            y_cell += y_step
            add(x_cell, previous_y)
            add(previous_x, y_cell)
            add(x_cell, y_cell)
            x_max += x_delta
            y_max += y_delta
    return tuple(cells)


def _is_grid_boundary(value: float, cell_m: float) -> bool:
    scaled = value / cell_m
    return math.isclose(scaled, round(scaled), abs_tol=1e-12)


def _finalize_geometry_repairs(fabric: _Fabric) -> int:
    """Repair endpoint contacts created by tip extension, then re-sweep crossings."""

    repaired = _register_endpoint_touches(fabric)
    _register_remaining_crossings(fabric)
    return repaired


def _register_endpoint_touches(fabric: _Fabric) -> int:
    """Bind each same-layer endpoint that lies on a foreign segment interior.

    The source node, rather than a fresh projection node, is inserted into the
    target. That keeps the contact a single builder identity and confines any
    sub-tolerance geometry movement to the topology module's declared weld
    policy.
    """

    repaired = 0
    while True:
        candidates = _find_endpoint_touches(fabric)
        if not candidates:
            return repaired
        for _distance, source, node_id, target in candidates:
            if node_id in fabric.builder.node_ids_of(target):
                continue
            if fabric.bind_node_into_street(target, node_id, tolerance_m=WELD_TOLERANCE_M):
                repaired += 1
                break
        else:
            raise RuntimeError(
                "endpoint-touch repair made no progress with "
                f"{len(_find_endpoint_touches(fabric))} touches remaining"
            )


def _find_endpoint_touches(
    fabric: _Fabric,
) -> list[tuple[float, int, int, int]]:
    """Return deterministic same-layer, non-parallel endpoint touch candidates."""

    candidates: list[tuple[float, int, int, int]] = []
    for source in fabric.builder.street_ids:
        source_nodes = fabric.builder.node_ids_of(source)
        if len(source_nodes) < 2:
            continue
        for position, node_id in ((0, source_nodes[0]), (-1, source_nodes[-1])):
            if len(fabric.builder.incident_street_ids(node_id)) != 1:
                continue
            tip = fabric.builder.point_of(node_id)
            inner = fabric.builder.point_of(source_nodes[1 if position == 0 else -2])
            heading = math.atan2(tip[1] - inner[1], tip[0] - inner[0])
            for target in fabric.builder.street_ids:
                if (
                    target == source
                    or fabric.builder.street_layer(target)
                    != fabric.builder.street_layer(source)
                ):
                    continue
                target_points = fabric.builder.points_of(target)
                for left, right in zip(target_points, target_points[1:]):
                    dx, dy = right[0] - left[0], right[1] - left[1]
                    span_sq = dx * dx + dy * dy
                    if span_sq <= 0.0:
                        continue
                    ratio = ((tip[0] - left[0]) * dx + (tip[1] - left[1]) * dy) / span_sq
                    if not 1e-9 < ratio < 1.0 - 1e-9:
                        continue
                    distance = _point_to_segment_distance(tip, left, right)
                    if distance > WELD_TOLERANCE_M:
                        continue
                    target_heading = math.atan2(dy, dx)
                    delta = abs(math.atan2(
                        math.sin(heading - target_heading), math.cos(heading - target_heading)
                    ))
                    if min(delta, math.pi - delta) < math.radians(EXTEND_TO_CROSS_MIN_ANGLE_DEG):
                        continue
                    candidates.append((distance, source, node_id, target))
                    break
    return sorted(candidates)


# A tip may only be extended by this much before the extension stops being a
# repair and starts being a road nobody was building. Expressed as a multiple of
# the local step so it scales with the fabric rather than being an absolute.
EXTEND_TO_CROSS_MIN_ANGLE_DEG = 25.0


def _extend_dangling_tips(fabric: _Fabric, *, max_reach_m: float) -> int:
    """Extend free-ending tips to the street they nearly reached.

    Connectivity repair, not density control. Fixing the branch-spacing units
    took density into the real band and pushed dead-end share to 0.284-0.434
    against a real-city maximum of 0.288: seeding fewer streets leaves the ones
    that did grow dangling. This converts those cul-de-sacs into junctions
    without seeding more street.

    It adds length, so it can only push density up -- which is why it runs after
    the spacing is right rather than instead of fixing it.

    Deterministic: every candidate is collected first and applied shortest-first,
    ties broken by street id, so the outcome cannot depend on discovery order.
    """

    builder = fabric.builder
    candidates: list[tuple[float, int, int, int, tuple[float, float]]] = []

    for street_id in builder.street_ids:
        node_ids = builder.node_ids_of(street_id)
        if len(node_ids) < 2:
            continue
        for position in (0, -1):
            tip_node = node_ids[position]
            if len(builder.incident_street_ids(tip_node)) != 1:
                continue  # already a junction
            inner = node_ids[1] if position == 0 else node_ids[-2]
            tip = builder.point_of(tip_node)
            heading = math.atan2(
                tip[1] - builder.point_of(inner)[1],
                tip[0] - builder.point_of(inner)[0],
            )
            reach = (
                tip[0] + max_reach_m * math.cos(heading),
                tip[1] + max_reach_m * math.sin(heading),
            )
            hit = fabric.nearest_crossing(tip, reach, exclude_street=street_id)
            if hit is None:
                continue
            target_street, point = hit
            if not _meets_at_a_useful_angle(fabric, target_street, point, heading):
                continue
            candidates.append((math.dist(tip, point), street_id, tip_node, position, point))

    extended = 0
    for _distance, street_id, tip_node, position, point in sorted(
        candidates, key=lambda item: (item[0], item[1], item[2], item[3])
    ):
        if len(builder.incident_street_ids(tip_node)) != 1:
            continue  # an earlier extension already joined this tip
        target = fabric.nearest_crossing_target(point)
        if target is None or target == street_id:
            continue
        junction = fabric.contact(target, point, 1.0)
        if junction is None:
            continue
        if position == 0:
            if fabric.prepend_to_node(street_id, junction, max_gap_m=max_reach_m * 1.2):
                extended += 1
        else:
            if fabric.extend_to_node(street_id, junction, max_gap_m=max_reach_m * 1.2):
                extended += 1
    return extended


def _meets_at_a_useful_angle(
    fabric: _Fabric,
    street_id: int,
    point: tuple[float, float],
    heading: float,
) -> bool:
    """Reject a near-parallel meeting: that is a duplicate, not a junction."""

    points = fabric.builder.points_of(street_id)
    best, best_distance = None, float("inf")
    for left, right in zip(points, points[1:]):
        distance = _point_to_segment_distance(point, left, right)
        if distance < best_distance:
            best, best_distance = (left, right), distance
    if best is None:
        return False
    left, right = best
    target_heading = math.atan2(right[1] - left[1], right[0] - left[0])
    delta = abs(math.atan2(math.sin(heading - target_heading), math.cos(heading - target_heading)))
    delta = min(delta, math.pi - delta)
    return delta >= math.radians(EXTEND_TO_CROSS_MIN_ANGLE_DEG)


def _connectivity_metadata(links, node_count: int) -> dict:
    """Largest-component share and the size of every fragment outside it."""

    if node_count == 0:
        return {"largest_component_share": 0.0, "isolated_fragment_sizes": ()}
    adjacency: dict[int, set[int]] = {index: set() for index in range(node_count)}
    for link in links:
        adjacency[int(link.src_node_id)].add(int(link.dst_node_id))
        adjacency[int(link.dst_node_id)].add(int(link.src_node_id))

    seen: set[int] = set()
    sizes: list[int] = []
    for start in range(node_count):
        if start in seen:
            continue
        stack, size = [start], 0
        seen.add(start)
        while stack:
            node = stack.pop()
            size += 1
            for other in adjacency[node]:
                if other not in seen:
                    seen.add(other)
                    stack.append(other)
        sizes.append(size)
    sizes.sort(reverse=True)
    return {
        "largest_component_share": sizes[0] / node_count,
        "isolated_fragment_sizes": tuple(sizes[1:]),
    }
