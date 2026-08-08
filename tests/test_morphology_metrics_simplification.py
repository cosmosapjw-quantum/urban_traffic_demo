"""Degree-2 interstitial contraction for Boeing-comparable morphometrics.

The pinned empirical corpus in `morphology_reference.py` reports OSMnx values
measured after `simplify_graph` removes degree-2 interstitial nodes. Measuring
every compiled node instead makes node spacing, rather than morphology, control
`mean_node_degree` and `dead_end_share`.
"""

from __future__ import annotations

import math

import pytest


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

    from metroflow.city.morphology_metrics import (
        MeasurementSpec,
        compute_street_network_morphometrics,
    )

    topology = _topology(((0.0, 0.0), (100.0, 0.0), (200.0, 0.0)), ((0, 1), (1, 2)))

    metrics = compute_street_network_morphometrics(
        topology, spec=MeasurementSpec.BOEING_2019_HO
    )

    assert metrics.physical_segment_count == 1
    assert math.isclose(metrics.median_segment_length_m, 200.0)
    assert math.isclose(metrics.mean_node_degree, 1.0)
    assert math.isclose(metrics.dead_end_share, 1.0)


def test_the_runtime_diagnostic_spec_measures_every_compiled_node() -> None:
    """The unsimplified numbers must stay byte-compatible: replay depends on them.

    Previously this asserted that the unsimplified path was *the default*. It is
    no longer a default -- a boolean could not say which of Boeing's two
    statistics it meant, and the two live callers picked differently -- but the
    values it produces must not move.
    """

    from metroflow.city.morphology_metrics import (
        MeasurementSpec,
        compute_street_network_morphometrics,
    )

    topology = _topology(((0.0, 0.0), (100.0, 0.0), (200.0, 0.0)), ((0, 1), (1, 2)))

    metrics = compute_street_network_morphometrics(
        topology, spec=MeasurementSpec.RUNTIME_COMPILED_DIAGNOSTIC
    )

    assert metrics.physical_segment_count == 2
    assert math.isclose(metrics.median_segment_length_m, 100.0)
    assert math.isclose(metrics.mean_node_degree, 4.0 / 3.0)
    assert math.isclose(metrics.dead_end_share, 2.0 / 3.0)


def test_contraction_preserves_junctions_and_deflated_dead_end_share() -> None:
    """Interstitial nodes deflate dead-end share; contraction restores it.

    A three-armed star whose arms are each subdivided once: 7 compiled nodes,
    of which 3 are real cul-de-sacs, 3 are interstitial, and 1 is the junction.
    """

    from metroflow.city.morphology_metrics import (
        MeasurementSpec,
        compute_street_network_morphometrics,
    )

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

    unsimplified = compute_street_network_morphometrics(
        topology, spec=MeasurementSpec.RUNTIME_COMPILED_DIAGNOSTIC
    )
    simplified = compute_street_network_morphometrics(
        topology, spec=MeasurementSpec.BOEING_2019_HO
    )

    assert unsimplified.dead_end_share == 3.0 / 7.0
    assert simplified.dead_end_share == 3.0 / 4.0
    assert simplified.physical_segment_count == 3
    assert math.isclose(simplified.mean_node_degree, 1.5)
    assert math.isclose(simplified.median_segment_length_m, 200.0)


def test_a_junction_free_ring_is_dropped_exactly_as_osmnx_drops_it() -> None:
    """This test previously asserted the opposite, on my assumption, not evidence.

    It said a junction-free ring "must not vanish", and the code satisfied that
    by contracting the ring into a zero-chord self-loop. Nothing asserted the
    resulting circuity, which was 4e14 -- a number that satisfies the envelope's
    `<= 1.3644` upper bound by being enormous rather than by being right.

    Measured against `osmnx==2.1.1`: `simplify_graph` on a 4-node ring returns a
    graph with 0 nodes and 0 edges. The ring has no endpoint to anchor a chain,
    so the reference implementation removes it. Matching that is the point of
    claiming parity, so the ring is dropped -- and counted, because losing street
    length silently is the failure this instrument exists to detect.
    """

    from metroflow.city.morphology_metrics import (
        MeasurementSpec,
        UnmeasurableNetworkError,
        compute_street_network_morphometrics,
    )

    ring = _topology(
        ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)),
        ((0, 1), (1, 2), (2, 3), (3, 0)),
    )

    with pytest.raises(UnmeasurableNetworkError, match="junction-free ring"):
        compute_street_network_morphometrics(ring, spec=MeasurementSpec.BOEING_2019_HO)

    # The unsimplified diagnostic still sees it, because it contracts nothing.
    diagnostic = compute_street_network_morphometrics(
        ring, spec=MeasurementSpec.RUNTIME_COMPILED_DIAGNOSTIC
    )
    assert diagnostic.physical_segment_count == 4
    assert math.isclose(diagnostic.circuity, 1.0)
