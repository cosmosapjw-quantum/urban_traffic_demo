"""The measurement must state which definition it implements, and match it.

`compute_street_network_morphometrics` currently takes a boolean
`simplify_interstitial_nodes` whose True branch is described as
"OSMnx-equivalent". It is not equivalent, and the boolean cannot say which of
Boeing's two published statistics it means.

Every expected value below was measured from `osmnx==2.1.1` on the same shape,
not chosen. Where OSMnx and this code already agree, that is recorded too --
the draft design called the lollipop's circuity of 5.0 a defect, and the oracle
shows OSMnx computes 4.99 for the same graph, so it is the correct answer and
the "fix" would have introduced a divergence while claiming to remove one.
"""

from __future__ import annotations

import math

import pytest


def _topology(nodes, edges):
    """Build a PreviewCityTopology from node coordinates and undirected edges."""

    from metroflow.city.generated_map import PreviewCityTopology
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.map.road_geometry import (
        CenterlineSource,
        LinkGeometryAssignment,
        RoadCenterline,
        RoadGeometryCatalog,
    )

    node_objects = tuple(Node(i, x=float(p[0]), y=float(p[1])) for i, p in enumerate(nodes))
    links: list[RoadLink] = []
    centerlines: list[RoadCenterline] = []
    assignments: list[LinkGeometryAssignment] = []
    for geometry_id, edge in enumerate(edges):
        if len(edge) == 2:
            left, right = edge
            points = (tuple(map(float, nodes[left])), tuple(map(float, nodes[right])))
        else:
            left, right, points = edge
            points = tuple(tuple(map(float, p)) for p in points)
        length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
        forward = len(links)
        for source, destination in ((left, right), (right, left)):
            links.append(
                RoadLink(
                    link_id=len(links),
                    src_node_id=source,
                    dst_node_id=destination,
                    road_class=RoadClass.LOCAL,
                    length_m=length,
                    free_flow_speed_mps=10.0,
                    capacity_veh_per_tick=1.0,
                    lanes=1,
                    physical_road_id=geometry_id,
                )
            )
        centerlines.append(
            RoadCenterline(
                geometry_id=geometry_id,
                points_m=points,
                source=CenterlineSource.SYNTHETIC,
            )
        )
        assignments.append(LinkGeometryAssignment(link_id=forward, geometry_id=geometry_id))
        assignments.append(
            LinkGeometryAssignment(link_id=forward + 1, geometry_id=geometry_id, reversed=True)
        )
    return PreviewCityTopology(
        nodes=node_objects,
        links=tuple(links),
        road_geometry=RoadGeometryCatalog(
            centerlines=tuple(centerlines), assignments=tuple(assignments)
        ),
        metadata={},
    )


_SQUARE = [(0.0, 0.0), (0.0, 100.0), (100.0, 100.0), (100.0, 0.0)]
_RING_EDGES = [(0, 1), (1, 2), (2, 3), (3, 0)]


def _boeing(topology):
    from metroflow.city.morphology_metrics import (
        MeasurementSpec,
        compute_street_network_morphometrics,
    )

    return compute_street_network_morphometrics(topology, spec=MeasurementSpec.BOEING_2019_HO)


# --- the specification must be stated, not defaulted -----------------------


def test_a_measurement_specification_is_required() -> None:
    """A bare call cannot silently pick a definition."""

    from metroflow.city.morphology_metrics import compute_street_network_morphometrics

    topology = _topology(_SQUARE + [(0.0, -100.0)], _RING_EDGES + [(0, 4)])

    with pytest.raises(TypeError):
        compute_street_network_morphometrics(topology)


def test_the_runtime_diagnostic_spec_is_a_distinct_named_thing() -> None:
    """Two definitions must not share one name; that is the current defect."""

    from metroflow.city.morphology_metrics import (
        MeasurementSpec,
        compute_street_network_morphometrics,
    )

    topology = _topology(_SQUARE + [(0.0, -100.0)], _RING_EDGES + [(0, 4)])

    boeing = compute_street_network_morphometrics(
        topology, spec=MeasurementSpec.BOEING_2019_HO
    )
    runtime = compute_street_network_morphometrics(
        topology, spec=MeasurementSpec.RUNTIME_COMPILED_DIAGNOSTIC
    )

    assert boeing.measurement_spec == "BOEING_2019_HO"
    assert runtime.measurement_spec == "RUNTIME_COMPILED_DIAGNOSTIC"
    assert boeing.as_dict()["measurement_spec"] == "BOEING_2019_HO"


# --- shapes, with OSMnx's own answers --------------------------------------


def test_self_loop_bearings_are_excluded_from_the_orientation_histogram() -> None:
    """OSMnx measures ln2 here; we measure 1.366159 by counting the loop.

    A lollipop is a 4-node ring plus one stub. After contraction it is a
    self-loop plus one edge. OSMnx skips self-loop bearings outright, so only the
    stub's bearing and its reciprocal remain -- exactly two occupied bins, ln 2.
    """

    metrics = _boeing(_topology(_SQUARE + [(0.0, -100.0)], _RING_EDGES + [(0, 4)]))

    assert metrics.orientation_entropy == pytest.approx(math.log(2.0), abs=1e-12)


def test_self_loop_length_still_counts_toward_circuity() -> None:
    """Measured from OSMnx: 4.9912 for this shape. Our 5.0 is already right.

    Boeing's circuity is total length over total endpoint chord, and a self-loop
    contributes length with a zero chord. `circuity_avg` in OSMnx does the same.
    Excluding zero-chord segments from the numerator -- the change the draft
    design proposed -- would move us away from the reference, not toward it.
    """

    metrics = _boeing(_topology(_SQUARE + [(0.0, -100.0)], _RING_EDGES + [(0, 4)]))

    assert metrics.circuity == pytest.approx(5.0, rel=1e-9)


def test_parallel_edges_stay_two_streets_between_two_nodes() -> None:
    """OSMnx keeps both edges, both nodes at degree 2, circuity finite.

    We contract them into a closed loop: one segment, one node, circuity 4.66e14.
    Two roads between the same pair of junctions are ordinary -- a dual
    carriageway is exactly this -- so silently merging them is a loss.
    """

    straight = ((0.0, 0.0), (200.0, 0.0))
    bowed = ((0.0, 0.0), (100.0, 40.0), (200.0, 0.0))
    metrics = _boeing(
        _topology([(0.0, 0.0), (200.0, 0.0)], [(0, 1, straight), (0, 1, bowed)])
    )

    assert metrics.physical_segment_count == 2
    assert metrics.mean_node_degree == pytest.approx(2.0)
    assert math.isfinite(metrics.circuity)
    assert metrics.circuity < 1.5


def test_a_junction_free_ring_has_no_measurable_streets() -> None:
    """OSMnx's simplify_graph deletes it: 4 nodes and 4 edges become 0 and 0.

    It has no endpoint to anchor a chain, so nothing survives contraction. We
    currently emit one zero-chord segment and report circuity 4e14 -- a number
    that silently passes a `<= 1.3644` gate check by being enormous rather than
    by being right.
    """

    from metroflow.city.morphology_metrics import UnmeasurableNetworkError

    with pytest.raises(UnmeasurableNetworkError):
        _boeing(_topology(_SQUARE, _RING_EDGES))


def test_dropped_rings_are_reported_rather_than_silently_discarded() -> None:
    """Matching OSMnx costs real street length; that has to be visible."""

    metrics = _boeing(
        _topology(
            _SQUARE + [(300.0, 0.0), (300.0, 100.0)],
            _RING_EDGES + [(4, 5)],
        )
    )

    assert metrics.dropped_ring_count == 1
    assert metrics.dropped_ring_length_m == pytest.approx(400.0)


# --- invariances -----------------------------------------------------------


def test_degree_two_subdivision_changes_nothing() -> None:
    """The defining property of a simplified measurement.

    Today: splitting one arm of a plus into 1/2/4 collinear pieces moves entropy
    1.386294 -> 1.366159 -> 1.291417, because each member edge contributes its
    own bearing instead of the contracted chain contributing one.
    """

    plus_nodes = [(0.0, 0.0), (100.0, 0.0), (0.0, 100.0), (-100.0, 0.0), (0.0, -100.0)]
    plus = _topology(plus_nodes, [(0, 1), (0, 2), (0, 3), (0, 4)])

    split_nodes = plus_nodes + [(50.0, 0.0)]
    split = _topology(split_nodes, [(0, 5), (5, 1), (0, 2), (0, 3), (0, 4)])

    twice_nodes = split_nodes + [(25.0, 0.0), (75.0, 0.0)]
    twice = _topology(twice_nodes, [(0, 6), (6, 5), (5, 7), (7, 1), (0, 2), (0, 3), (0, 4)])

    reference = _boeing(plus).as_dict()
    for variant in (split, twice):
        measured = _boeing(variant).as_dict()
        for metric in (
            "orientation_entropy",
            "orientation_order",
            "median_segment_length_m",
            "circuity",
            "mean_node_degree",
            "dead_end_share",
            "four_way_share",
            "physical_segment_count",
        ):
            assert measured[metric] == pytest.approx(reference[metric], abs=1e-9), metric


def test_translating_the_whole_network_changes_nothing() -> None:
    """Absolute position is not morphology."""

    nodes = [(0.0, 0.0), (100.0, 0.0), (0.0, 100.0), (-100.0, 0.0), (0.0, -100.0)]
    edges = [(0, 1), (0, 2), (0, 3), (0, 4)]
    shifted = [(x + 4321.5, y - 8765.25) for x, y in nodes]

    assert _boeing(_topology(nodes, edges)).as_dict() == pytest.approx(
        _boeing(_topology(shifted, edges)).as_dict(), abs=1e-6
    )


def test_densifying_a_straight_edge_with_collinear_vertices_changes_nothing() -> None:
    """Polyline resolution is a storage choice, not a property of the city."""

    nodes = [(0.0, 0.0), (100.0, 0.0), (0.0, 100.0), (-100.0, 0.0), (0.0, -100.0)]
    sparse = [(0, 1), (0, 2), (0, 3), (0, 4)]
    dense = [
        (0, 1, ((0.0, 0.0), (25.0, 0.0), (50.0, 0.0), (75.0, 0.0), (100.0, 0.0))),
        (0, 2),
        (0, 3),
        (0, 4),
    ]

    assert _boeing(_topology(nodes, dense)).as_dict() == pytest.approx(
        _boeing(_topology(nodes, sparse)).as_dict(), abs=1e-9
    )
