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
import json
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]


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


@pytest.mark.parametrize(
    ("fixture_name", "reason_code"),
    (
        ("paris.osm", "UNSUPPORTED_DIRECTIONAL_LANE_ALLOCATION"),
        ("prague.osm", "UNSUPPORTED_ONEWAY_VALUE"),
    ),
)
def test_known_osm_control_tag_gaps_use_typed_exceptions(
    fixture_name: str,
    reason_code: str,
) -> None:
    """Known unsupported tags must be distinguishable from programming errors."""
    from metroflow.benchmarks.morphology_control_table import build_osm_topology
    from metroflow.map import osm_import

    error_type = getattr(osm_import, "UnsupportedOSMTagError", None)
    assert error_type is not None, "OSM unsupported-tag failures need a public type"

    with pytest.raises(error_type) as caught:
        build_osm_topology(_REPO_ROOT / "artifacts" / "osm_control" / fixture_name)

    assert caught.value.reason_code == reason_code


def test_collect_scores_preclassifies_unsupported_standard_styles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Known standard/style gaps must not be inferred from caught exceptions."""
    from metroflow.benchmarks import morphology_control_table as control_table

    topology = _square_topology()
    build_calls: list[tuple[str, str, int]] = []

    def build(*, arm: str, style_id: str, seed: int):
        build_calls.append((arm, style_id, seed))
        if arm == "standard":
            raise AssertionError("unsupported standard style reached the generator")
        return topology

    monkeypatch.setattr(control_table, "build_arm_topology", build)

    scores, skipped = control_table.collect_scores(
        styles=("grid_core",),
        seeds=(17,),
    )

    assert {(score.arm, score.case) for score in scores} == {
        ("sidecar_local_fabric", "grid_core/17"),
        ("sidecar_local_fabric_planar", "grid_core/17"),
        ("realistic_synthetic_v1", "grid_core/17"),
        ("growth_fabric_v1", "grid_core/17"),
    }
    assert tuple(type(item).__name__ for item in skipped) == ("SkippedCase",)
    assert tuple(item.as_dict() for item in skipped) == (
        {
            "arm": "standard",
            "case": "grid_core/17",
            "reason_code": "UNSUPPORTED_ARM_STYLE",
        },
    )
    assert ("standard", "grid_core", 17) not in build_calls


def test_collect_scores_does_not_normalize_unexpected_generation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A programming failure must abort collection instead of becoming evidence."""
    from metroflow.benchmarks import morphology_control_table as control_table

    def explode(*, arm: str, style_id: str, seed: int):
        del arm, style_id, seed
        raise RuntimeError("unexpected generator failure")

    monkeypatch.setattr(control_table, "build_arm_topology", explode)

    with pytest.raises(RuntimeError, match="unexpected generator failure"):
        control_table.collect_scores(styles=("ring_radial",), seeds=(17,))


def test_collect_scores_records_only_typed_osm_tag_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the importer-owned unsupported-tag type may become an OSM skip."""
    from metroflow.benchmarks import morphology_control_table as control_table
    from metroflow.map.osm_import import UnsupportedOSMTagError

    def unsupported(path: Path):
        del path
        raise UnsupportedOSMTagError(
            "UNSUPPORTED_ONEWAY_VALUE",
            "unsupported fixture tag",
        )

    monkeypatch.setattr(control_table, "build_osm_topology", unsupported)

    scores, skipped = control_table.collect_scores(
        styles=(),
        seeds=(),
        osm_paths=(Path("known.osm"),),
    )

    assert scores == ()
    assert tuple(type(item).__name__ for item in skipped) == ("SkippedCase",)
    assert tuple(item.as_dict() for item in skipped) == (
        {
            "arm": "osm",
            "case": "known.osm",
            "reason_code": "UNSUPPORTED_ONEWAY_VALUE",
        },
    )


def test_collect_scores_propagates_unexpected_osm_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An arbitrary OSM failure must not be normalized as an expected skip."""
    from metroflow.benchmarks import morphology_control_table as control_table

    def explode(path: Path):
        del path
        raise TypeError("unexpected OSM failure")

    monkeypatch.setattr(control_table, "build_osm_topology", explode)

    with pytest.raises(TypeError, match="unexpected OSM failure"):
        control_table.collect_scores(
            styles=(),
            seeds=(),
            osm_paths=(Path("broken.osm"),),
        )


def test_collect_scores_rejects_a_result_outside_the_attempt_partition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mislabeled score must fail the exact attempt-partition invariant."""
    from metroflow.benchmarks import morphology_control_table as control_table

    topology = _square_topology()
    real_score = control_table.score_street_morphology

    monkeypatch.setattr(
        control_table,
        "build_arm_topology",
        lambda *, arm, style_id, seed: topology,
    )

    def mislabeled_score(topology, *, arm: str, case: str):
        return replace(real_score(topology, arm=arm, case=case), case="wrong-case")

    monkeypatch.setattr(control_table, "score_street_morphology", mislabeled_score)

    with pytest.raises(RuntimeError, match="score/skip inventory"):
        control_table.collect_scores(styles=("ring_radial",), seeds=(17,))


def test_committed_v4_artifact_has_an_exact_structured_attempt_inventory() -> None:
    """The evidence bundle must account for every score or typed skip exactly once."""
    artifact = (
        _REPO_ROOT
        / "artifacts"
        / "runtime_spine_review"
        / "morphology-control-table-v4-20260820.json"
    )
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    scores = payload["scores"]
    skipped = payload["skipped_cases"]

    assert len(scores) == 135
    assert len(skipped) == 22
    assert all(isinstance(item, dict) for item in skipped)
    assert all(set(item) == {"arm", "case", "reason_code"} for item in skipped)

    score_keys = {(item["arm"], item["case"]) for item in scores}
    skip_keys = {(item["arm"], item["case"]) for item in skipped}
    assert len(score_keys) == len(scores)
    assert len(skip_keys) == len(skipped)
    assert score_keys.isdisjoint(skip_keys)
    assert len(score_keys | skip_keys) == 157
    assert [item["reason_code"] for item in skipped].count("UNSUPPORTED_ARM_STYLE") == 20
    assert [item["reason_code"] for item in skipped].count(
        "UNSUPPORTED_DIRECTIONAL_LANE_ALLOCATION"
    ) == 1
    assert [item["reason_code"] for item in skipped].count(
        "UNSUPPORTED_ONEWAY_VALUE"
    ) == 1


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


def test_control_table_rejects_duplicate_score_keys() -> None:
    """Duplicate identities must not inflate summaries or overwrite diagnostics."""
    from metroflow.city.morphology_control_table import (
        build_morphology_control_table,
        score_street_morphology,
    )

    score = score_street_morphology(_square_topology(), arm="alpha", case="s17")

    with pytest.raises(ValueError, match=r"unique by \(arm, case\)"):
        build_morphology_control_table((score, score))


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
