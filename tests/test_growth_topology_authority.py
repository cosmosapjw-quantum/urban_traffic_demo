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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PR-B integration pending. growth_fabric does not yet use StreetTopologyBuilder: _branch_pass interpolates the anchor and never inserts it into the parent, so 97.98% of 3117 anchors on polycentric_tod/17 are >0.5 m from any parent vertex."
    ),
)
def test_every_branch_anchor_joins_its_parent_to_both_children() -> None:
    """A branch origin drawn on its parent must be a junction in the graph."""

    from metroflow.city.growth_fabric import compile_grown_network

    network = _grown()
    topology = compile_grown_network(network)

    orphaned = [
        junction
        for junction in network.junctions
        if len(junction.incident_street_ids) < 2
    ]

    assert not orphaned, f"{len(orphaned)} recorded junctions are not shared"
    assert all(
        junction.node_id is not None for junction in network.junctions
    ), "every junction must carry the stable node id it was created with"
    assert len(topology.nodes) >= len(network.junctions)


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
        topology = compile_grown_network(_grown(style_id=style_id))
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

    topology = compile_grown_network(_grown())
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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PR-B integration pending. compile_grown_network's seen_pairs silently drops the second street between one node pair: 10 chains / 0.65 km on grid_core/17, and no drop ledger exists."
    ),
)
def test_two_streets_between_the_same_pair_of_junctions_both_survive() -> None:
    """`seen_pairs` drops the second one: 10 chains / 0.65 km on grid_core/17.

    Two roads between one pair of junctions is ordinary -- a dual carriageway is
    exactly that -- and OSMnx keeps both.
    """

    from metroflow.city.growth_fabric import compile_grown_network

    topology = compile_grown_network(_grown())

    assert topology.metadata.get("dropped_chain_count", 0) == 0


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

    topology = compile_grown_network(_grown(style_id="grid_core"))

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
