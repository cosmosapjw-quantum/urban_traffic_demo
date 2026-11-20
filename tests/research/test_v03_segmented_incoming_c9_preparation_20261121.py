"""Current source-native V03 original 100k calendars, zero completed days."""
import hashlib
import json
from pathlib import Path

from metroflow.v1.v03_readiness import assess_v03_readiness

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_segmented_incoming_20261121"
OLD=ROOT/"artifacts/v03_compact_lineage_20261120/C9_preparation"


def read(path):
    return json.loads(path.read_bytes())


def authoritative():
    plan=read(ROOT/"docs/v1/PLAN.json")
    path=ROOT/"scenarios/v1/release_matrix.json"
    matrix=read(path)
    return plan,matrix,hashlib.sha256(path.read_bytes()).hexdigest()


def test_three_original_full_100k_input_calendars_reprepared_for_new_native():
    plan,matrix,matrix_sha=authoritative()
    expected={"river_weekday_s17":5_093_765,
              "coastal_weekend_s41":2_449_750,
              "valley_weekday_s7":918_450}
    receipts=[read(ART/"C9_preparation"/(c["id"]+".prepare.json"))
              for c in matrix["cases"]]
    assert len(receipts)==3
    source=receipts[0]["candidate_source_sha256"]
    native=receipts[0]["native_binary_sha256"]
    for row in receipts:
        assert row["status"]=="WHOLE_CALENDAR_PREPARED"
        assert row["calendar"]["resident_stock"]==matrix["population"]==100000
        assert row["calendar"]["legs"]==expected[row["case"]]
        assert row["candidate"]["source_dirty"] is False
        assert row["candidate_source_sha256"]==source
        assert row["native_binary_sha256"]==native
        assert row["matrix_sha256"]==matrix_sha
        assert row["horizon_s"]==row["simulated_s"]==0
    result=assess_v03_readiness(
        plan,matrix,matrix_sha256=matrix_sha,
        preparation_receipts=receipts,
        live_candidate_source_sha256=source,
        live_native_binary_sha256=native)
    assert (result["dag"]["completed"],result["dag"]["total"])==(19,21)
    assert (result["v03"]["dependency_nodes_completed"],
            result["v03"]["dependency_nodes_total"])==(3,3)
    assert (result["v03"]["calendar_preparation_verified"],
            result["v03"]["calendar_preparation_total"])==(3,3)
    assert (result["v03"]["completed_full_day_runs"],
            result["v03"]["required_full_day_runs"])==(0,9)
    assert result["v03"]["status"]=="BLOCKED"
    assert result["v03"]["ready_for_release"] is False


def test_prior_source_and_binary_calendar_receipts_are_stale_for_new_native():
    plan,matrix,matrix_sha=authoritative()
    ready=read(ART/"C9_CURRENT_NATIVE_READINESS.json")
    rows=[read(OLD/(c["id"]+".prepare.json")) for c in matrix["cases"]]
    result=assess_v03_readiness(
        plan,matrix,matrix_sha256=matrix_sha,
        preparation_receipts=rows,
        live_candidate_source_sha256=ready["measurement_context"]["live_candidate_source_sha256"],
        live_native_binary_sha256=ready["measurement_context"]["live_native_binary_sha256"])
    assert result["v03"]["calendar_preparation_verified"]==0
    assert {v["reason"] for v in result["case_preparation"].values()}=={
        "CURRENT_SOURCE_CONTENT_HASH_DIFFERS"}
