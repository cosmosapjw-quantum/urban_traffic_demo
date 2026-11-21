"""Current-native original MetroFlow 100k 3-city input preparation and V03 honesty gate."""
import hashlib
import json
from pathlib import Path

from metroflow.v1.v03_readiness import assess_v03_readiness

ROOT=Path(__file__).resolve().parents[2]
A=ROOT/"artifacts/v03_weighted_fifo_20261121"
OLD=ROOT/"artifacts/v03_quantile_capture_20261121/C9_preparation"


def read(p):
    return json.loads(p.read_bytes())


def authority():
    plan=read(ROOT/"docs/v1/PLAN.json")
    path=ROOT/"scenarios/v1/release_matrix.json"
    return plan,read(path),hashlib.sha256(path.read_bytes()).hexdigest()


def test_three_current_native_original_city_input_calendars_not_physical_days():
    plan,matrix,sha=authority()
    expected={"river_weekday_s17":5093765,
              "coastal_weekend_s41":2449750,
              "valley_weekday_s7":918450}
    receipts=[read(A/"C9_preparation"/(c["id"]+".prepare.json")) for c in matrix["cases"]]
    assert len(receipts)==3
    source=receipts[0]["candidate_source_sha256"]
    native=receipts[0]["native_binary_sha256"]
    for row in receipts:
        assert row["status"]=="WHOLE_CALENDAR_PREPARED"
        assert row["candidate"]["source_dirty"] is False
        assert row["calendar"]["resident_stock"]==matrix["population"]==100000
        assert row["calendar"]["legs"]==expected[row["case"]]
        assert row["candidate_source_sha256"]==source
        assert row["native_binary_sha256"]==native
        assert row["matrix_sha256"]==sha
        assert row["horizon_s"]==row["simulated_s"]==0
    score=assess_v03_readiness(plan,matrix,matrix_sha256=sha,
        preparation_receipts=receipts,
        live_candidate_source_sha256=source,
        live_native_binary_sha256=native)
    assert (score["dag"]["completed"],score["dag"]["total"])==(19,21)
    assert (score["v03"]["dependency_nodes_completed"],
            score["v03"]["dependency_nodes_total"])==(3,3)
    assert (score["v03"]["calendar_preparation_verified"],
            score["v03"]["calendar_preparation_total"])==(3,3)
    assert (score["v03"]["completed_full_day_runs"],
            score["v03"]["required_full_day_runs"])==(0,9)
    assert score["v03"]["status"]=="BLOCKED"
    assert not score["v03"]["ready_for_release"]


def test_previous_source_city_preparation_receipts_are_stale():
    plan,matrix,sha=authority()
    measurement=read(A/"C9_CURRENT_NATIVE_READINESS.json")["measurement_context"]
    previous=[read(OLD/(c["id"]+".prepare.json")) for c in matrix["cases"]]
    score=assess_v03_readiness(plan,matrix,matrix_sha256=sha,
        preparation_receipts=previous,
        live_candidate_source_sha256=measurement["live_candidate_source_sha256"],
        live_native_binary_sha256=measurement["live_native_binary_sha256"])
    assert score["v03"]["calendar_preparation_verified"]==0
    assert {r["reason"] for r in score["case_preparation"].values()}=={
        "CURRENT_SOURCE_CONTENT_HASH_DIFFERS"}
