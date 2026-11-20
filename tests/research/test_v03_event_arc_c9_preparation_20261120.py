"""Original-source 100k full-city calendars, current-native identity, no false day."""
import hashlib
import json
from pathlib import Path

from metroflow.v1.v03_readiness import assess_v03_readiness

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts/v03_event_arc_20261120"
OLD = ROOT / "artifacts/v03_exact_interval_view_20261120/preparation"


def read(p):
    return json.loads(p.read_bytes())


def reference():
    plan = read(ROOT / "docs/v1/PLAN.json")
    path = ROOT / "scenarios/v1/release_matrix.json"
    return plan, read(path), hashlib.sha256(path.read_bytes()).hexdigest()


def test_all_three_current_original_calendars_are_100k_and_preparation_only():
    plan, matrix, matrix_sha = reference()
    expected = {"river_weekday_s17": 5093765,
                "coastal_weekend_s41": 2449750,
                "valley_weekday_s7": 918450}
    rows = [read(ART / "C9_preparation" / (case["id"] + ".prepare.json"))
            for case in matrix["cases"]]
    assert len(rows) == len(expected) == 3
    source_sha = rows[0]["candidate_source_sha256"]
    native_sha = rows[0]["native_binary_sha256"]
    for row in rows:
        assert row["status"] == "WHOLE_CALENDAR_PREPARED"
        assert row["calendar"]["resident_stock"] == matrix["population"] == 100000
        assert row["calendar"]["legs"] == expected[row["case"]]
        assert row["simulated_s"] == row["horizon_s"] == 0
        assert row["engine_backend"] == "rust_whole"
        assert row["candidate"]["source_dirty"] is False
        assert row["candidate_source_sha256"] == source_sha
        assert row["native_binary_sha256"] == native_sha
        assert row["matrix_sha256"] == matrix_sha
    result = assess_v03_readiness(
        plan, matrix, matrix_sha256=matrix_sha,
        preparation_receipts=rows, live_candidate_source_sha256=source_sha,
        live_native_binary_sha256=native_sha)
    assert result["v03"]["calendar_preparation_verified"] == 3
    assert result["v03"]["dependency_nodes_completed"] == 3
    assert (result["dag"]["completed"], result["dag"]["total"]) == (19, 21)
    assert (result["v03"]["completed_full_day_runs"],
            result["v03"]["required_full_day_runs"]) == (0, 9)
    assert result["v03"]["status"] == "BLOCKED"
    assert result["v03"]["ready_for_release"] is False


def test_previous_native_original_calendar_receipts_are_stale_for_current_code():
    plan, matrix, matrix_sha = reference()
    rows = [read(OLD / (case["id"] + ".prepare.json")) for case in matrix["cases"]]
    now = read(ART / "C9_CURRENT_NATIVE_READINESS.json")
    r = assess_v03_readiness(
        plan, matrix, matrix_sha256=matrix_sha, preparation_receipts=rows,
        live_candidate_source_sha256=now["measurement_context"]["live_candidate_source_sha256"],
        live_native_binary_sha256=now["measurement_context"]["live_native_binary_sha256"])
    assert r["v03"]["calendar_preparation_verified"] == 0
    assert {x["reason"] for x in r["case_preparation"].values()} == {
        "CURRENT_SOURCE_CONTENT_HASH_DIFFERS"}
