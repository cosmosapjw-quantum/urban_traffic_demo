"""One instrument, many arms.

`run_realistic_city_plausibility_audit` calls `generate_city_map` with
`topology_mode="realistic_synthetic_v1"` internally, so it can only ever score
the generator under test. No control arm - not the legacy default, not the
sidecar paths, and not the OSM importer built for exactly this purpose - can be
measured on it. The street-morphology half of the gate needs only nodes, links
and road_geometry, all of which every `PreviewCityTopology` carries.
"""

from __future__ import annotations


def _square_topology():
    from metroflow.city.generated_map import PreviewCityTopology
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.map.road_geometry import build_endpoint_geometry_catalog

    nodes = tuple(
        Node(index, x=x, y=y)
        for index, (x, y) in enumerate(
            ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0))
        )
    )
    pairs = ((0, 1), (1, 2), (2, 3), (3, 0))
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

    simplified = score_street_morphology(_square_topology(), arm="a")
    compiled = score_street_morphology(
        _square_topology(), arm="a", simplify_interstitial_nodes=False
    )

    assert simplified.simplified is True
    assert simplified.metrics["median_segment_length_m"] == 400.0
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
