"""Geometry must stop being the source of truth for topology.

Measured on the current tree: `_branch_pass` interpolates a branch anchor inside
a parent segment and never inserts it into the parent's point list, while
`compile_grown_network` derives junctions only from vertices whose coordinates
round to the same 1 m cell. So both children register the anchor and the parent
does not. 97.98% of 3117 anchors on `polycentric_tod`/17 lie more than 0.5 m
from any vertex of their own parent; re-inserting them takes weak components
from 40 to 1 and mean degree from 2.665 to 3.525, adding 3058 undirected edges --
24.4% of the correct edge set. The morphology envelope accepts the network in
both states.

An earlier attempt to fix this by snapping contacts to the true segment
projection made things worse, because the compiler matched shared coordinates and
a mid-segment contact left the other street with no matching point. That failure
mode has to be impossible by construction, not avoided by care: a junction is
recorded when it is created, and the compiler consumes that record.
"""

from __future__ import annotations

import math

import pytest


def _grown(style_id: str = "polycentric_tod", seed: int = 17):
    from metroflow.city.growth_fabric import grow_street_network
    from metroflow.city.terrain_field import build_terrain_field
    from metroflow.city.urban_form import build_urban_form_field

    terrain = build_terrain_field(width=6000, height=6000, seed=seed, style_id=style_id)
    urban_form = build_urban_form_field(terrain=terrain, style_id=style_id, seed=seed)
    return grow_street_network(terrain=terrain, urban_form=urban_form, seed=seed)


def _undirected(topology) -> set[tuple[int, int]]:
    return {
        (min(int(link.src_node_id), int(link.dst_node_id)),
         max(int(link.src_node_id), int(link.dst_node_id)))
        for link in topology.links
    }


def _weak_components(topology) -> int:
    adjacency: dict[int, set[int]] = {int(node.node_id): set() for node in topology.nodes}
    for link in topology.links:
        adjacency[int(link.src_node_id)].add(int(link.dst_node_id))
        adjacency[int(link.dst_node_id)].add(int(link.src_node_id))
    seen: set[int] = set()
    components = 0
    for start in adjacency:
        if start in seen:
            continue
        components += 1
        stack = [start]
        seen.add(start)
        while stack:
            node = stack.pop()
            for other in adjacency[node]:
                if other not in seen:
                    seen.add(other)
                    stack.append(other)
    return components


# --- the defect itself -----------------------------------------------------


def _starts_on_another_streets_interior(streets, tolerance_m: float = 0.5) -> int:
    """Street start points that lie on another street but are not a vertex of it.

    This is the branch-anchor defect stated as something measurable. A child is
    seeded at a point interpolated inside its parent's segment; the parent never
    gains a vertex there, so the two are drawn touching and are not connected.
    """

    from metroflow.map.road_geometry import _point_to_segment_distance

    polylines = [street.points_m for street in streets]
    orphaned = 0
    for index, street in enumerate(streets):
        start = street.points_m[0]
        for other_index, other in enumerate(polylines):
            if other_index == index:
                continue
            if any(math.dist(start, vertex) <= tolerance_m for vertex in other):
                continue  # a shared vertex is a properly recorded junction
            if any(
                _point_to_segment_distance(start, left, right) <= tolerance_m
                for left, right in zip(other, other[1:])
            ):
                orphaned += 1
                break
    return orphaned


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PR-B integration pending. _branch_pass interpolates the anchor and never "
        "inserts it into the parent, so 6107 of 6257 streets (97.6%) on "
        "polycentric_tod/17 begin on another street's interior with no node there."
    ),
)
def test_every_branch_anchor_joins_its_parent_to_both_children() -> None:
    """A branch origin drawn on its parent must be a junction in the graph."""

    network = _grown()

    orphaned = _starts_on_another_streets_interior(network.streets)

    assert orphaned == 0, (
        f"{orphaned} of {len(network.streets)} streets begin on another street's "
        "interior without a node there"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PR-B integration pending. 40 weak components on polycentric_tod/17, 27 on grid_core/17; 22 of those 27 are exactly an orphaned anchor plus its two children, degrees (2,1,1)."
    ),
)
def test_the_grown_network_is_one_connected_component() -> None:
    """40 components on polycentric_tod/17 today, 27 on grid_core/17.

    22 of those 27 are exactly three nodes with degrees (2,1,1) -- an orphaned
    anchor and its two children, which is the defect's signature.
    """

    from metroflow.city.growth_fabric import compile_grown_network

    for style_id in ("polycentric_tod", "grid_core", "ring_radial"):
        topology = compile_grown_network(_grown(style_id=style_id).streets)
        assert _weak_components(topology) == 1, f"{style_id} is not connected"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PR-B integration pending. mean degree is 2.665 because 3058 undirected edges (24.4% of the correct set) are missing; re-inserting the anchors gives 3.525."
    ),
)
def test_mean_node_degree_reflects_the_edges_that_actually_exist() -> None:
    """2.665 today because a quarter of the edge set is missing."""

    from metroflow.city.growth_fabric import compile_grown_network

    topology = compile_grown_network(_grown().streets)
    degree = 2.0 * len(_undirected(topology)) / len(topology.nodes)

    assert degree > 3.3, f"mean node degree {degree:.3f} is too low for a connected fabric"


# --- geometry may not define topology --------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PR-B integration pending. node identity is round(coord / 1.0), so translating grid_core/17 by (0.37, 0.37) moves the compiled graph from 6278/16690 to 6282/16702."
    ),
)
def test_translating_the_whole_city_does_not_change_its_graph() -> None:
    """Today (0.37, 0.37) moves grid_core/17 from 6278/16690 to 6282/16702.

    Node identity is `round(coord / 1.0)`, so which junctions exist depends on
    where the city happens to sit relative to a 1 m lattice.
    """

    from metroflow.city.growth_fabric import compile_grown_network

    network = _grown(style_id="grid_core")
    reference = compile_grown_network(network.streets)
    shifted = compile_grown_network(_translated(network, 0.37, 0.37).streets)

    assert len(shifted.nodes) == len(reference.nodes)
    assert len(shifted.links) == len(reference.links)


def _translated(network, dx: float, dy: float):
    from dataclasses import replace

    streets = tuple(
        replace(street, points_m=tuple((x + dx, y + dy) for x, y in street.points_m))
        for street in network.streets
    )
    return replace(network, streets=streets)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PR-B integration pending. compile_grown_network's seen_pairs silently drops the second street between one node pair: grid_core/17 builds 8355 chains and emits 8345 centerlines, losing 10."
    ),
)
def test_two_streets_between_the_same_pair_of_junctions_both_survive() -> None:
    """`seen_pairs` drops the second one: 10 chains / 0.65 km on grid_core/17.

    Two roads between one pair of junctions is ordinary -- a dual carriageway is
    exactly that -- and OSMnx keeps both.
    """

    from metroflow.city.growth_fabric import compile_grown_network

    streets = _grown(style_id="grid_core").streets
    topology = compile_grown_network(streets)

    # Assert the loss itself, not the presence of a diagnostic key: a key that is
    # never emitted makes `.get(key, 0) == 0` pass with the defect intact.
    assert _chain_count(streets) == len(topology.road_geometry.centerlines), (
        f"{_chain_count(streets) - len(topology.road_geometry.centerlines)} chains "
        "were built and silently dropped before becoming centerlines"
    )


def _chain_count(streets, quantum_m: float = 1.0) -> int:
    """Count the junction-to-junction chains `compile_grown_network` builds.

    Mirrors the compiler's own splitting rule so the comparison is against what
    it decided to keep, not against an independent idea of what it should have.
    """

    def key(point):
        return (round(point[0] / quantum_m), round(point[1] / quantum_m))

    use_count: dict[tuple[int, int], int] = {}
    for street in streets:
        for index, point in enumerate(street.points_m):
            k = key(point)
            use_count[k] = use_count.get(k, 0) + (
                2 if index in (0, len(street.points_m) - 1) else 1
            )

    chains = 0
    for street in streets:
        points = street.points_m
        current = [points[0]]
        for index in range(1, len(points)):
            current.append(points[index])
            if index == len(points) - 1 or use_count.get(key(points[index]), 0) >= 2:
                if len(current) >= 2:
                    chains += 1
                current = [points[index]]
    return chains


# --- geometry and topology must agree --------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PR-B integration pending. 6909 unregistered same-grade crossings on grid_core/17, against 0 on all five real OSM extracts. grow() has no swept-segment crossing test."
    ),
)
def test_streets_that_cross_at_the_same_grade_meet_at_a_node() -> None:
    """6909 unregistered crossings on grid_core/17, against 0 on every real extract."""

    from metroflow.city.growth_fabric import compile_grown_network
    from metroflow.map.road_geometry import count_interior_centerline_intersections

    topology = compile_grown_network(_grown(style_id="grid_core").streets)

    assert count_interior_centerline_intersections(topology.road_geometry) == 0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PR-B integration pending. 6261 unregistered touches on grid_core/17, against 0 on all five real extracts."
    ),
)
def test_streets_that_touch_without_crossing_also_meet_at_a_node() -> None:
    """6261 unregistered touches on grid_core/17, against 0 on every real extract."""

    from metroflow.city.growth_fabric import compile_grown_network
    from metroflow.map.road_geometry import count_unregistered_centerline_touches

    topology = compile_grown_network(_grown(style_id="grid_core").streets)

    assert count_unregistered_centerline_touches(topology.road_geometry) == 0


# --- the mechanism, in isolation -------------------------------------------


def test_splitting_a_street_mints_one_node_shared_by_both_sides() -> None:
    """`split_at_arc_length` is the only way to create a mid-street junction.

    Arc length, not a (segment, position) pair: a positional parameterisation
    stops meaning the same place the moment anything splits the street, which is
    the instability the id model exists to remove.
    """

    from metroflow.city.growth_topology import StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    parent = builder.open_street(points=((0.0, 0.0), (100.0, 0.0)))

    node_id = builder.split_at_arc_length(parent, 50.0)

    assert builder.point_of(node_id) == (50.0, 0.0)
    assert node_id in builder.node_ids_of(parent), "the parent must carry the split vertex"
    assert builder.incident_street_ids(node_id) == (parent,)

    child = builder.open_street(points=((50.0, 0.0), (50.0, 50.0)), start_node_id=node_id)
    assert set(builder.incident_street_ids(node_id)) == {parent, child}


def test_splitting_twice_at_the_same_arc_length_reuses_the_node() -> None:
    """Both siblings of one branch anchor must bind to a single junction.

    Idempotent because arc length is split-invariant: the second call resolves to
    the same point, finds the vertex already there, and returns it.
    """

    from metroflow.city.growth_topology import StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    parent = builder.open_street(points=((0.0, 0.0), (100.0, 0.0)))

    first = builder.split_at_arc_length(parent, 50.0)
    second = builder.split_at_arc_length(parent, 50.0)

    assert first == second
    assert len(builder.node_ids_of(parent)) == 3


def test_arc_length_still_addresses_the_same_place_after_a_split() -> None:
    """The property that makes anchors survivable across mutation."""

    from metroflow.city.growth_topology import StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    street = builder.open_street(points=((0.0, 0.0), (100.0, 0.0), (200.0, 0.0)))
    far_end = builder.node_ids_of(street)[-1]

    builder.split_at_arc_length(street, 50.0)
    later = builder.split_at_arc_length(street, 150.0)

    assert builder.point_of(later) == (150.0, 0.0)
    assert builder.node_ids_of(street)[-1] == far_end
    assert builder.point_of(far_end) == (200.0, 0.0)
    assert math.isclose(builder.arc_length_of(street), 200.0, abs_tol=1e-9)


def test_a_street_cannot_be_split_outside_its_own_geometry() -> None:
    from metroflow.city.growth_topology import StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    street = builder.open_street(points=((0.0, 0.0), (100.0, 0.0)))

    with pytest.raises(ValueError):
        builder.split_at_arc_length(street, 250.0)
    with pytest.raises(ValueError):
        builder.split_at_arc_length(street, -1.0)


def test_splitting_at_an_endpoint_returns_that_endpoint() -> None:
    """No zero-length stub, and no duplicate node on top of an existing one."""

    from metroflow.city.growth_topology import StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    street = builder.open_street(points=((0.0, 0.0), (100.0, 0.0)))
    start, end = builder.node_ids_of(street)

    assert builder.split_at_arc_length(street, 0.0) == start
    assert builder.split_at_arc_length(street, 100.0) == end
    assert len(builder.node_ids_of(street)) == 2


def test_two_distinct_nodes_may_not_sit_at_the_same_point() -> None:
    """The compiler no longer compares coordinates, so this must be caught here.

    Without it, a growth bug that mints two nodes at one location produces two
    unlinked coincident junctions -- structurally the same defect as today's
    orphaned anchors, just arrived at from the other direction.
    """

    from metroflow.city.growth_topology import CoincidentNodeError, StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    builder.open_street(points=((0.0, 0.0), (100.0, 0.0)))
    builder.open_street(points=((0.0, 0.0), (0.0, 100.0)))

    with pytest.raises(CoincidentNodeError):
        builder.assert_no_coincident_nodes()


def test_contacting_a_street_splits_it_at_the_true_projection() -> None:
    """Not at the nearest existing vertex, which is what happens today.

    98.6% of contacts currently land up to 64.8 m from the true projection,
    and that error is baked into the compiled link's length.
    """

    from metroflow.city.growth_topology import StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    target = builder.open_street(points=((0.0, 0.0), (100.0, 0.0)))

    node_id = builder.contact(target, point=(37.0, 4.0), tolerance_m=10.0)

    assert node_id is not None
    x, y = builder.point_of(node_id)
    assert (x, y) == pytest.approx((37.0, 0.0), abs=1e-9)
    assert math.isclose(builder.arc_length_of(target), 100.0, abs_tol=1e-9)


# --- defects found by adversarial review of this module --------------------


def test_a_sub_tolerance_segment_returns_the_nearer_vertex_not_the_left_one() -> None:
    """Both weld checks can be true at once, and the left one won a tie it lost.

    On a segment shorter than 2 * WELD_TOLERANCE_M, `remainder <= tol` and
    `span - remainder <= tol` are both satisfiable. Returning the first match
    hands back the left vertex even when the request is nearer the right one.
    """

    from metroflow.city.growth_topology import StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    street = builder.open_street(points=((0.0, 0.0), (0.4, 0.0), (100.0, 0.0)))
    left, middle, _right = builder.node_ids_of(street)

    # 0.24 along a 0.4 m segment satisfies BOTH weld checks (0.24 <= 0.25 and
    # 0.4 - 0.24 = 0.16 <= 0.25), and the right vertex is the nearer one.
    assert builder.split_at_arc_length(street, 0.10) == left
    assert builder.split_at_arc_length(street, 0.24) == middle


def test_a_request_past_a_run_of_tiny_segments_does_not_snap_to_the_far_end() -> None:
    """The loop could fall through to `return node_ids[-1]`, the wrong end.

    A street whose segments are all under the weld tolerance never satisfies the
    advance condition, so every request fell out of the loop and returned the
    last node regardless of what was asked for.
    """

    from metroflow.city.growth_topology import StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    points = tuple((0.1 * index, 0.0) for index in range(10))
    street = builder.open_street(points=points)
    node_ids = builder.node_ids_of(street)

    assert builder.split_at_arc_length(street, 0.0) == node_ids[0]
    assert builder.split_at_arc_length(street, 0.2) == node_ids[2]
    assert builder.split_at_arc_length(street, 0.5) == node_ids[5]


def test_a_street_can_terminate_on_an_existing_node() -> None:
    """Without this, `contact()` splits the target and connects nothing.

    The arriving tip needs to BECOME the node the split created; otherwise it
    stays a separate vertex beside it and the two streets remain unconnected --
    the same defect the module exists to remove.
    """

    from metroflow.city.growth_topology import StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    target = builder.open_street(points=((0.0, 0.0), (100.0, 0.0)))
    arriving = builder.open_street(points=((37.0, 60.0), (37.0, 10.0)))

    node_id = builder.contact(target, point=(37.0, 4.0), tolerance_m=10.0)
    builder.extend_street_to_node(arriving, node_id)

    assert builder.node_ids_of(arriving)[-1] == node_id
    assert set(builder.incident_street_ids(node_id)) == {target, arriving}
    assert builder.points_of(arriving)[-1] == pytest.approx((37.0, 0.0), abs=1e-9)


def test_coincident_node_detection_ignores_a_grade_separated_crossing() -> None:
    """A bridge over a road shares a coordinate and is not a junction.

    A coordinate-only invariant would make grade separation unrepresentable,
    which matters because RAMP and BRIDGE are exactly what the generator still
    has to grow.
    """

    from metroflow.city.growth_topology import StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    builder.open_street(points=((0.0, 0.0), (100.0, 0.0)), layer=0)
    builder.open_street(points=((50.0, -50.0), (50.0, 50.0)), layer=1)
    builder.split_at_arc_length(0, 50.0)
    builder.split_at_arc_length(1, 50.0)

    builder.assert_no_coincident_nodes()  # different layers: not a junction
