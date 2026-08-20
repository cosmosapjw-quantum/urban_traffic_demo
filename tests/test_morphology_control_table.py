"""One instrument, many arms.

`run_realistic_city_plausibility_audit` calls `generate_city_map` with
`topology_mode="realistic_synthetic_v1"` internally, so it can only ever score
the generator under test. No control arm - not the legacy default, not the
sidecar paths, and not the OSM importer built for exactly this purpose - can be
measured on it. The street-morphology half of the gate needs only nodes, links
and road_geometry, all of which every `PreviewCityTopology` carries.
"""

from __future__ import annotations

from dataclasses import replace

import pytest


def _square_topology():
    """A closed square with one stub, so it survives contraction.

    A bare 4-node ring is junction-free: it has no endpoint to anchor a chain,
    and `BOEING_2019_HO` drops it exactly as OSMnx `simplify_graph` does (that
    reference behaviour is measured in
    tests/test_morphology_metrics_simplification.py). The single stub gives the
    ring an endpoint, so the shape stays measurable while remaining a square.
    """

    from metroflow.city.generated_map import PreviewCityTopology
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.map.road_geometry import build_endpoint_geometry_catalog

    nodes = tuple(
        Node(index, x=x, y=y)
        for index, (x, y) in enumerate(
            ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0), (0.0, -100.0))
        )
    )
    pairs = ((0, 1), (1, 2), (2, 3), (3, 0), (0, 4))
    links = tuple(
        RoadLink(
            link_id=index * 2 + direction,
            src_node_id=pair[direction],
            dst_node_id=pair[1 - direction],
            road_class=RoadClass.LOCAL,
            length_m=100.0,
            free_flow_speed_mps=10.0,
            capacity_veh_per_tick=4.0,
            physical_road_id=index,
        )
        for index, pair in enumerate(pairs)
        for direction in (0, 1)
    )
    geometry = build_endpoint_geometry_catalog(nodes=nodes, links=links)
    return PreviewCityTopology(nodes=nodes, links=links, road_geometry=geometry)


def test_scores_a_bare_topology_without_a_generated_city_map() -> None:
    from metroflow.city.morphology_control_table import score_street_morphology

    score = score_street_morphology(_square_topology(), arm="unit-square")

    assert score.arm == "unit-square"
    assert set(score.metrics) == {
        "orientation_order",
        "orientation_entropy",
        "median_segment_length_m",
        "circuity",
        "mean_node_degree",
        "dead_end_share",
        "four_way_share",
    }
    # A closed square has no cul-de-sacs, so it must fail the dead-end floor.
    assert "dead_end_share" in score.failed_metrics
    assert score.passed is False


def test_score_uses_the_simplified_graph_by_default() -> None:
    """Boeing values are OSMnx-simplified; the instrument must match."""

    from metroflow.city.morphology_control_table import score_street_morphology

    from metroflow.city.morphology_metrics import MeasurementSpec

    simplified = score_street_morphology(_square_topology(), arm="a")
    compiled = score_street_morphology(
        _square_topology(), arm="a", spec=MeasurementSpec.RUNTIME_COMPILED_DIAGNOSTIC
    )

    assert simplified.simplified is True
    assert simplified.measurement_spec == "BOEING_2019_HO"
    # The ring contracts to one 400 m self-loop; the stub stays 100 m.
    assert simplified.metrics["median_segment_length_m"] == 250.0
    assert compiled.metrics["median_segment_length_m"] == 100.0


def test_control_table_ranks_arms_by_measured_pass_count() -> None:
    from metroflow.city.morphology_control_table import (
        build_morphology_control_table,
        score_street_morphology,
    )

    table = build_morphology_control_table(
        (
            score_street_morphology(_square_topology(), arm="alpha", case="s17"),
            score_street_morphology(_square_topology(), arm="beta", case="s17"),
            score_street_morphology(_square_topology(), arm="beta", case="s29"),
        )
    )

    assert tuple(item.arm for item in table.summaries) == ("alpha", "beta")
    assert table.summary_for("beta").case_count == 2
    assert table.summary_for("beta").passed_case_count == 0
    assert table.fingerprint == build_morphology_control_table(table.scores).fingerprint


def test_control_table_records_which_metrics_cannot_discriminate() -> None:
    """A vacuous bound must be visible in the artifact, not silently passing."""

    from metroflow.city.morphology_control_table import (
        build_morphology_control_table,
        score_street_morphology,
    )

    table = build_morphology_control_table(
        (score_street_morphology(_square_topology(), arm="alpha"),)
    )

    assert table.vacuous_metrics == ("orientation_order",)
    assert table.as_dict()["envelope_diagnostics"]["circuity"]["lower_bound_is_inert"] is True


def test_control_table_declares_that_it_does_not_score_the_scalable_v2_arm() -> None:
    """A valid legacy/control table cannot be read as scalable-v2 validation."""
    from metroflow.city.morphology_control_table import (
        build_morphology_control_table,
        score_street_morphology,
    )

    table = build_morphology_control_table(
        (score_street_morphology(_square_topology(), arm="alpha"),)
    )

    assert "does not score scalable_synthetic_v2" in table.as_dict()["claim_boundary"]


@pytest.mark.parametrize(
    ("field_name", "message"),
    (
        ("measurement_spec", "measurement_spec"),
        ("source_topology_fingerprint", "source_topology_fingerprint"),
    ),
)
def test_current_control_table_requires_score_measurement_identity(
    field_name: str,
    message: str,
) -> None:
    """A newly written table cannot contain an unbound measurement record."""
    from metroflow.city.morphology_control_table import (
        build_morphology_control_table,
        score_street_morphology,
    )

    score = score_street_morphology(_square_topology(), arm="alpha")

    with pytest.raises(ValueError, match=message):
        build_morphology_control_table((replace(score, **{field_name: None}),))


def test_measurement_spec_is_part_of_the_current_score_fingerprint_payload() -> None:
    """Relabelling one metric definition must change the scientific identity."""
    from metroflow.city.morphology_control_table import (
        build_morphology_control_table,
        score_street_morphology,
    )
    from metroflow.city.morphology_metrics import MeasurementSpec

    score = score_street_morphology(_square_topology(), arm="alpha")
    relabelled = replace(
        score,
        measurement_spec=MeasurementSpec.RUNTIME_COMPILED_DIAGNOSTIC.value,
    )

    payload = score.as_dict()
    assert payload["measurement_spec"] == MeasurementSpec.BOEING_2019_HO.value
    assert build_morphology_control_table((score,)).schema_version == (
        "morphology_control_table_v4"
    )
    assert build_morphology_control_table((score,)).fingerprint != (
        build_morphology_control_table((relabelled,)).fingerprint
    )
