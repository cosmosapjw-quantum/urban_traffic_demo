from __future__ import annotations

import json
import subprocess
import sys

import pytest


@pytest.fixture(scope="module")
def one_map_report():
    from metroflow.city.plausibility_audit import (
        run_realistic_city_plausibility_audit,
    )

    return run_realistic_city_plausibility_audit(
        style_ids=("organic",),
        seeds=(17,),
        include_previews=True,
    )


def test_empirical_envelopes_are_mechanical_twenty_percent_expansions() -> None:
    from metroflow.city.plausibility_audit import build_empirical_metric_envelopes

    envelopes = build_empirical_metric_envelopes()

    assert envelopes["orientation_order"].reference_min == 0.002
    assert envelopes["orientation_order"].lower == pytest.approx(0.0016)
    assert envelopes["orientation_order"].upper == 1.0
    assert envelopes["median_segment_length_m"].lower == pytest.approx(42.8)
    assert envelopes["median_segment_length_m"].upper == pytest.approx(140.64)
    assert envelopes["circuity"].lower == 1.0
    assert envelopes["circuity"].upper == pytest.approx(1.3644)
    assert all(item.expansion_fraction == 0.2 for item in envelopes.values())
    assert len({item.source_url for item in envelopes.values()}) == 1


def test_canonical_matrix_is_six_styles_by_five_unique_seeds() -> None:
    from metroflow.city.morphology_reference import MORPHOLOGY_ARCHETYPES
    from metroflow.city.plausibility_audit import (
        REALISTIC_CITY_AUDIT_SEEDS,
        REALISTIC_CITY_AUDIT_STYLES,
    )

    assert REALISTIC_CITY_AUDIT_STYLES == MORPHOLOGY_ARCHETYPES
    assert REALISTIC_CITY_AUDIT_SEEDS == (17, 29, 41, 44, 53)
    assert len(REALISTIC_CITY_AUDIT_STYLES) * len(REALISTIC_CITY_AUDIT_SEEDS) == 30


def test_branch_free_corridor_gold_cases_distinguish_chain_junction_and_cycle() -> None:
    from metroflow.city.plausibility_audit import (
        _maximum_branch_free_corridor_from_edges,
    )

    chain = {
        0: (0, 1, 100.0),
        1: (1, 2, 100.0),
        2: (2, 3, 100.0),
    }
    junction = {
        0: (0, 1, 100.0),
        1: (1, 2, 100.0),
        2: (1, 3, 100.0),
    }
    cycle = {
        0: (0, 1, 100.0),
        1: (1, 2, 100.0),
        2: (2, 3, 100.0),
        3: (3, 0, 100.0),
    }

    assert _maximum_branch_free_corridor_from_edges(chain) == 300.0
    assert _maximum_branch_free_corridor_from_edges(junction) == 100.0
    assert _maximum_branch_free_corridor_from_edges(cycle) == 400.0


def test_map_audit_records_structural_empirical_and_counterevidence_metrics(
    one_map_report,
) -> None:
    report = one_map_report
    record = report.records[0]

    assert report.schema_version == "realistic_city_plausibility_audit_v1"
    assert report.map_count == 1
    assert record.style_id == "organic"
    assert record.seed == 17
    assert len(record.map_fingerprint) == 64
    assert record.metrics["weak_component_count"] == 1
    assert record.metrics["connectivity_repair_link_count"] == 0
    assert record.metrics["proper_intersection_count"] == 0
    assert record.metrics["sampled_od_reachability_share"] == 1.0
    assert record.metrics["developed_block_frontage_coverage"] == 1.0
    assert record.metrics["maximum_branch_free_corridor_m"] > 0.0
    assert 0.0 <= record.metrics["dominant_orientation_bin_share"] <= 1.0
    assert 0.0 <= record.metrics["dominant_length_bin_share"] <= 1.0
    assert 0.0 <= record.metrics["dominant_block_area_bin_share"] <= 1.0
    assert 0.0 <= record.metrics["water_cell_share"] <= 1.0
    assert 0.0 <= record.metrics["buildable_cell_share"] <= 1.0
    assert record.preview is not None
    assert set(record.preview["layers"]) == {
        "terrain",
        "roads",
        "blocks",
        "land_use",
        "runtime",
    }


def test_plausibility_audit_is_deterministic_for_same_map() -> None:
    from metroflow.city.plausibility_audit import run_realistic_city_plausibility_audit

    first = run_realistic_city_plausibility_audit(
        style_ids=("grid_core",),
        seeds=(29,),
        include_previews=False,
    )
    second = run_realistic_city_plausibility_audit(
        style_ids=("grid_core",),
        seeds=(29,),
        include_previews=False,
    )

    assert first.fingerprint == second.fingerprint
    assert first.records == second.records
    assert first.reference_corpus_fingerprint == second.reference_corpus_fingerprint


def test_plausibility_artifacts_preserve_claim_boundary(tmp_path, one_map_report) -> None:
    from metroflow.city.plausibility_audit import (
        load_realistic_city_plausibility_audit,
        write_realistic_city_plausibility_artifacts,
    )

    paths = write_realistic_city_plausibility_artifacts(
        tmp_path / "audit",
        report=one_map_report,
    )
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    markdown = paths["markdown"].read_text(encoding="utf-8")
    html = paths["html"].read_text(encoding="utf-8")

    assert payload["evidence_status"] == "diagnostic_plausibility_audit"
    assert payload["raw_osm_data_included"] is False
    assert payload["external_data_learning_used"] is False
    assert manifest["report_fingerprint"] == one_map_report.fingerprint
    assert manifest["map_count"] == 1
    assert "DIAGNOSTIC ONLY" in markdown
    assert "not named-city validation" in markdown
    assert "data-layer=\"terrain\"" in html
    assert "data-layer=\"roads\"" in html
    assert "data-layer=\"blocks\"" in html
    assert "data-layer=\"land_use\"" in html
    assert "data-layer=\"runtime\"" in html
    loaded = load_realistic_city_plausibility_audit(paths["json"])
    assert loaded.fingerprint == one_map_report.fingerprint
    assert loaded.records[0].preview is None


def test_audit_rejects_duplicate_or_unknown_matrix_axes() -> None:
    from metroflow.city.plausibility_audit import run_realistic_city_plausibility_audit

    with pytest.raises(ValueError, match="style_ids must be unique"):
        run_realistic_city_plausibility_audit(
            style_ids=("organic", "organic"),
            seeds=(17,),
        )
    with pytest.raises(ValueError, match="seeds must be unique"):
        run_realistic_city_plausibility_audit(
            style_ids=("organic",),
            seeds=(17, 17),
        )
    with pytest.raises(ValueError, match="morphology style_id"):
        run_realistic_city_plausibility_audit(
            style_ids=("named_city_clone",),
            seeds=(17,),
        )


def test_plausibility_audit_import_does_not_load_accelerators() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import metroflow.city.plausibility_audit; "
                "assert 'jax' not in sys.modules; "
                "assert 'torch' not in sys.modules; "
                "assert '_metroflow_rust' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
