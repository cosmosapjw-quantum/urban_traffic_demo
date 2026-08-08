"""The orientation distribution is bidirectional, so entropy cannot reach 0.

Every bearing is recorded together with its reciprocal, so bins `i` and `i+18`
always carry equal counts. The minimum is one street direction occupying two
bins -- `ln 2`, not `0`. Declaring a floor of `0` overstates the attainable
range, which makes the vacuity diagnostic understate how permissive the envelope
is: it reports 53.5% coverage where the true figure against `[ln 2, ln 36]` is
66.3%.

This is a diagnostic correction, not a gate change. The raw lower bound is
1.6664, far above `ln 2`, so the clamp does not bind and no envelope bound moves.
"""

from __future__ import annotations

import math

import pytest


def test_a_single_straight_street_hits_the_theoretical_floor_exactly() -> None:
    """Nothing can go below this, so it is the floor by construction."""

    from metroflow.city.generated_map import PreviewCityTopology
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.city.morphology_metrics import (
        MeasurementSpec,
        compute_street_network_morphometrics,
    )
    from metroflow.map.road_geometry import build_endpoint_geometry_catalog

    nodes = (Node(0, x=0.0, y=0.0), Node(1, x=100.0, y=0.0))
    links = tuple(
        RoadLink(
            link_id=direction,
            src_node_id=direction,
            dst_node_id=1 - direction,
            road_class=RoadClass.LOCAL,
            length_m=100.0,
            free_flow_speed_mps=10.0,
            capacity_veh_per_tick=4.0,
            physical_road_id=0,
        )
        for direction in (0, 1)
    )
    topology = PreviewCityTopology(
        nodes=nodes,
        links=links,
        road_geometry=build_endpoint_geometry_catalog(nodes=nodes, links=links),
    )

    metrics = compute_street_network_morphometrics(
        topology, spec=MeasurementSpec.BOEING_2019_HO
    )

    assert metrics.orientation_entropy == pytest.approx(math.log(2.0), abs=1e-12)


def test_the_declared_theoretical_floor_matches_what_is_attainable() -> None:
    from metroflow.city.plausibility_audit import _THEORETICAL_RANGES

    lower, upper = _THEORETICAL_RANGES["orientation_entropy"]

    assert lower == pytest.approx(math.log(2.0))
    assert upper == pytest.approx(math.log(36.0))


def test_correcting_the_floor_does_not_move_any_envelope_bound() -> None:
    """A diagnostic fix must not quietly change what the gate accepts."""

    from metroflow.city.plausibility_audit import build_empirical_metric_envelopes

    envelope = build_empirical_metric_envelopes()["orientation_entropy"]

    # The raw 0.8*min lower bound is 1.6664, well above ln 2, so the clamp is
    # non-binding and the admitted interval is untouched.
    assert envelope.lower == pytest.approx(1.6664)
    assert envelope.upper == pytest.approx(math.log(36.0))


def test_the_vacuity_diagnostic_stops_understating_its_own_permissiveness() -> None:
    """0.5350 was measured against an unattainable floor; 0.6633 is the truth."""

    from metroflow.city.plausibility_audit import build_empirical_metric_envelopes

    diagnostics = build_empirical_metric_envelopes()["orientation_entropy"].diagnostics()

    assert diagnostics["theoretical_coverage"] == pytest.approx(0.6633, abs=5e-4)
    assert diagnostics["lower_bound_is_inert"] is False
