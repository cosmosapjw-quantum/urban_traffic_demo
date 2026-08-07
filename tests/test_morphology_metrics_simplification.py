"""Degree-2 interstitial contraction for Boeing-comparable morphometrics.

The pinned empirical corpus in `morphology_reference.py` reports OSMnx values
measured after `simplify_graph` removes degree-2 interstitial nodes. Measuring
every compiled node instead makes node spacing, rather than morphology, control
`mean_node_degree` and `dead_end_share`.
"""

from __future__ import annotations

import math


def _topology(nodes, endpoint_pairs, *, length_m=100.0):
    from metroflow.city.generated_map import PreviewCityTopology
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.map.road_geometry import build_endpoint_geometry_catalog

    node_tuple = tuple(Node(index, x=x, y=y) for index, (x, y) in enumerate(nodes))
    links = tuple(
        RoadLink(
            link_id=index * 2 + direction,
            src_node_id=pair[direction],
            dst_node_id=pair[1 - direction],
            road_class=RoadClass.LOCAL,
            length_m=length_m,
            free_flow_speed_mps=10.0,
            capacity_veh_per_tick=4.0,
            physical_road_id=index,
        )
        for index, pair in enumerate(endpoint_pairs)
        for direction in (0, 1)
    )
    geometry = build_endpoint_geometry_catalog(nodes=node_tuple, links=links)
    return PreviewCityTopology(nodes=node_tuple, links=links, road_geometry=geometry)


def test_contraction_merges_a_collinear_chain_into_one_segment() -> None:
    """0--1--2 is one street with two ends, not two streets with three nodes."""

    from metroflow.city.morphology_metrics import compute_street_network_morphometrics

    topology = _topology(((0.0, 0.0), (100.0, 0.0), (200.0, 0.0)), ((0, 1), (1, 2)))

    metrics = compute_street_network_morphometrics(
        topology,
        simplify_interstitial_nodes=True,
    )

    assert metrics.physical_segment_count == 1
    assert math.isclose(metrics.median_segment_length_m, 200.0)
    assert math.isclose(metrics.mean_node_degree, 1.0)
    assert math.isclose(metrics.dead_end_share, 1.0)


def test_contraction_is_opt_in_and_defaults_to_the_unsimplified_graph() -> None:
    """The default must stay byte-compatible: it feeds replay fingerprints."""

    from metroflow.city.morphology_metrics import compute_street_network_morphometrics

    topology = _topology(((0.0, 0.0), (100.0, 0.0), (200.0, 0.0)), ((0, 1), (1, 2)))

    metrics = compute_street_network_morphometrics(topology)

    assert metrics.physical_segment_count == 2
    assert math.isclose(metrics.median_segment_length_m, 100.0)
    assert math.isclose(metrics.mean_node_degree, 4.0 / 3.0)
    assert math.isclose(metrics.dead_end_share, 2.0 / 3.0)


def test_contraction_preserves_junctions_and_deflated_dead_end_share() -> None:
    """Interstitial nodes deflate dead-end share; contraction restores it.

    A three-armed star whose arms are each subdivided once: 7 compiled nodes,
    of which 3 are real cul-de-sacs, 3 are interstitial, and 1 is the junction.
    """

    from metroflow.city.morphology_metrics import compute_street_network_morphometrics

    topology = _topology(
        (
            (0.0, 0.0),  # 0 junction
            (100.0, 0.0),  # 1 interstitial
            (200.0, 0.0),  # 2 cul-de-sac
            (0.0, 100.0),  # 3 interstitial
            (0.0, 200.0),  # 4 cul-de-sac
            (-100.0, 0.0),  # 5 interstitial
            (-200.0, 0.0),  # 6 cul-de-sac
        ),
        ((0, 1), (1, 2), (0, 3), (3, 4), (0, 5), (5, 6)),
    )

    unsimplified = compute_street_network_morphometrics(topology)
    simplified = compute_street_network_morphometrics(
        topology,
        simplify_interstitial_nodes=True,
    )

    assert unsimplified.dead_end_share == 3.0 / 7.0
    assert simplified.dead_end_share == 3.0 / 4.0
    assert simplified.physical_segment_count == 3
    assert math.isclose(simplified.mean_node_degree, 1.5)
    assert math.isclose(simplified.median_segment_length_m, 200.0)


def test_contraction_keeps_a_junction_free_ring_measurable() -> None:
    """A closed ring has no degree!=2 anchor; it must not vanish."""

    from metroflow.city.morphology_metrics import compute_street_network_morphometrics

    topology = _topology(
        ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)),
        ((0, 1), (1, 2), (2, 3), (3, 0)),
    )

    metrics = compute_street_network_morphometrics(
        topology,
        simplify_interstitial_nodes=True,
    )

    assert metrics.physical_segment_count == 1
    assert math.isclose(metrics.median_segment_length_m, 400.0)
    assert metrics.dead_end_share == 0.0
