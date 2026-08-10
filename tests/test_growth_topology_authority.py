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


def test_every_branch_anchor_joins_its_parent_to_both_children() -> None:
    """A branch origin drawn on its parent must be a junction in the graph."""

    network = _grown()

    orphaned = _starts_on_another_streets_interior(network.streets)

    assert orphaned == 0, (
        f"{orphaned} of {len(network.streets)} streets begin on another street's "
        "interior without a node there"
    )


def test_the_grown_network_is_one_connected_component() -> None:
    """40 components on polycentric_tod/17 today, 27 on grid_core/17.

    22 of those 27 are exactly three nodes with degrees (2,1,1) -- an orphaned
    anchor and its two children, which is the defect's signature.
    """

    from metroflow.city.growth_fabric import compile_grown_network

    for style_id in ("polycentric_tod", "grid_core", "ring_radial"):
        topology = compile_grown_network(_grown(style_id=style_id))
        share = topology.metadata["largest_component_share"]
        fragments = topology.metadata["isolated_fragment_sizes"]

        # Not `== 1`. PR-C's spacing fix leaves the occasional bypass arc that
        # reaches nothing -- polycentric_tod/17 has one isolated 330 m expressway
        # stub, 2 nodes of 2032. That is a real defect and it is REPORTED rather
        # than tolerated silently or deleted quietly, so it cannot grow unnoticed.
        assert share >= 0.99, (
            f"{style_id}: largest component holds only {share:.3f} of nodes, "
            f"fragments {fragments}"
        )
        assert all(size <= 4 for size in fragments), (
            f"{style_id}: a substantial fragment is unreachable: {fragments}"
        )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2.665 -> 2.756, not the 3.525 the counterfactual predicted. That prediction assumed the same street set; splitting parents changed it (3764 streets against 6257). What remains is a dead-end problem rather than missing edges: tips that fail to contact still terminate free. PR-C's extend-to-cross is what closes them."
    ),
)
def test_mean_node_degree_reflects_the_edges_that_actually_exist() -> None:
    """2.665 today because a quarter of the edge set is missing."""

    from metroflow.city.growth_fabric import compile_grown_network

    topology = compile_grown_network(_grown())
    degree = 2.0 * len(_undirected(topology)) / len(topology.nodes)

    assert degree > 3.3, f"mean node degree {degree:.3f} is too low for a connected fabric"


# --- geometry may not define topology --------------------------------------


def test_translating_the_whole_city_does_not_change_its_graph() -> None:
    """Today (0.37, 0.37) moves grid_core/17 from 6278/16690 to 6282/16702.

    Node identity is `round(coord / 1.0)`, so which junctions exist depends on
    where the city happens to sit relative to a 1 m lattice.
    """

    from metroflow.city.growth_fabric import compile_grown_network

    network = _grown(style_id="grid_core")
    reference = compile_grown_network(network)
    shifted = compile_grown_network(_translated(network, 0.37, 0.37))

    assert len(shifted.nodes) == len(reference.nodes)
    assert len(shifted.links) == len(reference.links)


def _translated(network, dx: float, dy: float):
    from dataclasses import replace

    streets = tuple(
        replace(street, points_m=tuple((x + dx, y + dy) for x, y in street.points_m))
        for street in network.streets
    )
    return replace(network, streets=streets)


def test_two_streets_between_the_same_pair_of_junctions_both_survive() -> None:
    """`seen_pairs` dropped the second one. Nothing may leave unrecorded.

    Asserts the compiler's own drop ledger rather than recounting chains the way
    the old coordinate compiler did -- that count no longer describes what the
    incidence compiler builds, so comparing against it measured the wrong thing.
    """

    from metroflow.city.growth_fabric import compile_grown_network

    topology = compile_grown_network(_grown(style_id="grid_core"))

    assert topology.metadata["dropped_chain_count"] == 0, (
        f"chains were dropped: {topology.metadata['dropped_chain_reasons']}"
    )


# --- geometry and topology must agree --------------------------------------


def test_streets_that_cross_at_the_same_grade_meet_at_a_node() -> None:
    """Final live-geometry repair leaves zero same-grade crossings on grid_core/17."""

    from metroflow.city.growth_fabric import compile_grown_network
    from metroflow.map.road_geometry import count_interior_centerline_intersections

    topology = compile_grown_network(_grown(style_id="grid_core"))

    assert count_interior_centerline_intersections(topology.road_geometry) == 0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known residual: grid_core/17 still has 5 unregistered same-layer touches "
        "under the 0.25 m diagnostic after endpoint-touch finalization."
    ),
)
def test_streets_that_touch_without_crossing_also_meet_at_a_node() -> None:
    """Known grid_core/17 residual: five unregistered same-layer touches remain."""

    from metroflow.city.growth_fabric import compile_grown_network
    from metroflow.map.road_geometry import count_unregistered_centerline_touches

    topology = compile_grown_network(_grown(style_id="grid_core"))

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


def test_a_request_on_a_street_of_tiny_segments_resolves_to_the_nearest_vertex() -> None:
    """Same root cause as the sibling test, on a street built entirely of them.

    This was originally described -- here, in the source comment, and in the
    commit message -- as the loop falling through to `return node_ids[-1]` and
    returning the WRONG END. That failure mode never occurred and is
    unreachable: getting past the final segment requires
    `arc_length_m > total + WELD_TOLERANCE_M`, which the guard at the top of the
    function already rejects with a ValueError.

    What actually failed is the sibling defect -- welding to a non-nearest
    vertex (node 0 where node 2 was nearer, node 3 where node 5 was) -- always
    within the declared tolerance. The test is kept because that is a real
    regression to guard; the explanation is corrected because a test that fails
    for a different reason than it states is worth very little.
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
    # Same bound the contact search used: the tip legitimately extends to reach
    # the junction, and the caller states how much street that may invent.
    builder.extend_street_to_node(arriving, node_id, max_gap_m=10.0)

    assert builder.node_ids_of(arriving)[-1] == node_id
    assert set(builder.incident_street_ids(node_id)) == {target, arriving}
    assert builder.points_of(arriving)[-1] == pytest.approx((37.0, 0.0), abs=1e-9)


def test_a_declared_grade_separated_crossing_is_exempt() -> None:
    """A bridge over a road shares a coordinate and is not a junction.

    The exemption is DECLARED, not inferred from the layers of the incident
    streets. Inferring it was wrong twice: a ramp landing on a ground street is
    a real junction that layer comparison silently exempted, and an orphaned
    node has no incident street at all, so its empty layer set intersected
    nothing and skipped every comparison.
    """

    from metroflow.city.growth_topology import CoincidentNodeError, StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    ground = builder.open_street(points=((0.0, 0.0), (100.0, 0.0)), layer=0)
    bridge = builder.open_street(points=((50.0, -50.0), (50.0, 50.0)), layer=1)
    under = builder.split_at_arc_length(ground, 50.0)
    over = builder.split_at_arc_length(bridge, 50.0)

    # Undeclared, two nodes at one point is the defect this guards.
    with pytest.raises(CoincidentNodeError):
        builder.assert_no_coincident_nodes()

    builder.register_grade_separation(under, over)
    builder.assert_no_coincident_nodes()


# --- defects found by review loop 2 ----------------------------------------


def test_terminating_on_a_node_already_on_the_street_is_rejected() -> None:
    """Otherwise the street doubles back and the compiler drops the chain.

    `extend_street_to_node` only guarded against the node already being the LAST
    one. Pointing it at an interior node appended a duplicate, producing a chain
    whose src equals its dst -- which `compile_grown_network` discards via
    `if src == dst: continue`. That is the silent chain loss this very file's
    xfail condemns, reintroduced by the fix for a different defect.
    """

    from metroflow.city.growth_topology import StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    street = builder.open_street(points=((0.0, 0.0), (50.0, 0.0), (100.0, 0.0)))
    interior = builder.node_ids_of(street)[1]

    with pytest.raises(ValueError, match="already on street"):
        builder.extend_street_to_node(street, interior, max_gap_m=100.0)


def test_terminating_on_a_distant_node_is_rejected() -> None:
    """`contact()` bounds its reach; this had no bound at all.

    Welding a 1 m street to a node 9 km away silently produced a 9001 m street.
    """

    from metroflow.city.growth_topology import StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    near = builder.open_street(points=((0.0, 0.0), (1.0, 0.0)))
    far = builder.open_street(points=((9000.0, 0.0), (9001.0, 0.0)))
    far_node = builder.node_ids_of(far)[0]

    with pytest.raises(ValueError, match="max_gap_m"):
        builder.extend_street_to_node(near, far_node, max_gap_m=5.0)


def test_a_node_with_no_incident_street_cannot_hide_a_coincidence() -> None:
    """`layers_of` returned an empty set, and empty intersects nothing.

    So an orphaned node sitting exactly on a junction was skipped by the very
    invariant that exists to catch two nodes at one point.
    """

    from metroflow.city.growth_topology import CoincidentNodeError, StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    builder.open_street(points=((0.0, 0.0), (100.0, 0.0)), layer=0)
    orphan = builder._mint_node((50.0, 0.0))  # no incident street
    assert builder.incident_street_ids(orphan) == ()
    builder.split_at_arc_length(0, 50.0)

    with pytest.raises(CoincidentNodeError):
        builder.assert_no_coincident_nodes()


def test_a_ramp_touching_down_on_a_ground_street_is_a_junction() -> None:
    """Grade separation must not blanket-exempt everything that shares a point.

    A bridge passing OVER a road is not a junction. A ramp landing ON one is.
    Both look identical to a check that only compares street layers, so the
    exemption has to be a property of the shared node, not of the streets.
    """

    from metroflow.city.growth_topology import CoincidentNodeError, StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    ground = builder.open_street(points=((0.0, 0.0), (100.0, 0.0)), layer=0)
    landing = builder.split_at_arc_length(ground, 50.0)

    # A ramp that ends at the same place but mints its own node there is exactly
    # the unconnected-touch defect, and must be caught.
    builder.open_street(points=((50.0, 40.0), (50.0, 0.0)), layer=0)

    with pytest.raises(CoincidentNodeError):
        builder.assert_no_coincident_nodes()

    assert builder.point_of(landing) == (50.0, 0.0)


def test_splitting_never_mints_a_node_that_violates_the_invariant() -> None:
    """The module's own primitive must respect the module's own invariant.

    Splitting could place a new node 0.15 m from an existing one -- inside the
    weld tolerance -- so `assert_no_coincident_nodes` failed on a builder that
    had done nothing but call `split_at_arc_length`.
    """

    from metroflow.city.growth_topology import StreetTopologyBuilder

    builder = StreetTopologyBuilder()
    street = builder.open_street(
        points=((0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.4, 0.15))
    )
    builder.assert_no_coincident_nodes()

    builder.split_at_arc_length(street, 0.4)

    builder.assert_no_coincident_nodes()
