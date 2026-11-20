"""Current-native full original demand calendar readiness, never physics-day acceptance."""
import hashlib
import json
from pathlib import Path

from metroflow.v1.v03_readiness import assess_v03_readiness

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts/v03_compact_lineage_20261120"
OLD = ROOT / "artifacts/v03_sweep_live_bounds_20261120/C9_preparation"


def read(path):
    return json.loads(path.read_bytes())


def authority():
    path = ROOT / "scenarios/v1/release_matrix.json"
    matrix = read(path)
    plan = read(ROOT / "docs/v1/PLAN.json")
    return plan, matrix, hashlib.sha256(path.read_bytes()).hexdigest()


def test_current_native_original_100k_city_calendars_without_physical_day():
    plan, matrix, matrix_sha = authority()
    expected = {"river_weekday_s17":5093765,
                "coastal_weekend_s41":2449750,
                "valley_weekday_s7":918450}
    receipts = [read(ART / "C9_preparation" / (case["id"] + ".prepare.json"))
                for case in matrix["cases"]]
    assert len(receipts) == 3
    source = receipts[0]["candidate_source_sha256"]
    native = receipts[0]["native_binary_sha256"]
    for row in receipts:
        assert row["status"] == "WHOLE_CALENDAR_PREPARED"
        assert row["simulated_s"] == row["horizon_s"] == 0
        assert row["candidate"]["source_dirty"] is False
        assert row["calendar"]["resident_stock"] == matrix["population"] == 100000
        assert row["calendar"]["legs"] == expected[row["case"]]
        assert row["candidate_source_sha256"] == source
        assert row["native_binary_sha256"] == native
        assert row["matrix_sha256"] == matrix_sha
    score = assess_v03_readiness(
        plan, matrix, matrix_sha256=matrix_sha,
        preparation_receipts=receipts,
        live_candidate_source_sha256=source,
        live_native_binary_sha256=native,
    )
    assert (score["dag"]["completed"],score["dag"]["total"]) == (19,21)
    assert (score["v03"]["dependency_nodes_completed"],
            score["v03"]["dependency_nodes_total"]) == (3,3)
    assert score["v03"]["calendar_preparation_verified"] == 3
    assert (score["v03"]["completed_full_day_runs"],
            score["v03"]["required_full_day_runs"]) == (0,9)
    assert score["v03"]["status"] == "BLOCKED"
    assert not score["v03"]["ready_for_release"]


def test_old_native_preparations_are_not_reused_after_source_change():
    plan, matrix, matrix_sha = authority()
    now = read(ART / "C9_CURRENT_NATIVE_READINESS.json")
    m = now["measurement_context"]
    receipts = [read(OLD / (case["id"] + ".prepare.json"))
                for case in matrix["cases"]]
    score = assess_v03_readiness(
        plan, matrix, matrix_sha256=matrix_sha,
        preparation_receipts=receipts,
        live_candidate_source_sha256=m["live_candidate_source_sha256"],
        live_native_binary_sha256=m["live_native_binary_sha256"],
    )
    assert score["v03"]["calendar_preparation_verified"] == 0
    assert {s["reason"] for s in score["case_preparation"].values()} == {
        "CURRENT_SOURCE_CONTENT_HASH_DIFFERS"}
