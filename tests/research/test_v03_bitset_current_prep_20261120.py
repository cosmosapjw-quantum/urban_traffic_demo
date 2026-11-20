"""Current source-native bitset 100k three-city preparation and stale receipt gate.

These prepare-only receipts contain no completed urban physics days (simulated_s=0).
"""
import hashlib
import json
from pathlib import Path

from metroflow.v1.v03_readiness import assess_v03_readiness
from metroflow.v1.native_engine import native_binary_provenance
from tools.run_v1_local_acceptance import candidate_provenance

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_composed_events_20261120"


def test_original_three_100k_city_calendar_preparations_current_native_source():
    r=json.loads((ART/"C9_CURRENT_V03_READINESS.json").read_bytes())
    source=candidate_provenance()
    binary=native_binary_provenance()
    assert source["status"]==binary["status"]=="MEASURED"
    assert source["source_dirty"] is False
    assert r["measurement_context"]["live_candidate_source_sha256"]==source["source_sha256"]
    assert r["measurement_context"]["live_native_binary_sha256"]==binary["sha256"]
    assert r["dag"]["completed"]==19 and r["dag"]["total"]==21
    assert r["v03"]["dependency_nodes_completed"]==3
    assert r["v03"]["calendar_preparation_verified"]==3
    assert r["v03"]["completed_full_day_runs"]==0
    assert r["v03"]["required_full_day_runs"]==9
    assert r["v03"]["status"]=="BLOCKED"
    cases={
        "river_weekday_s17":5093765,
        "coastal_weekend_s41":2449750,
        "valley_weekday_s7":918450,
    }
    total=0
    sha=hashlib.sha256((ROOT/"scenarios/v1/release_matrix.json").read_bytes()).hexdigest()
    for case,legs in cases.items():
        f=ART/"C9_preparation"/(case+".prepare.json")
        obj=json.loads(f.read_bytes())
        assert obj["case"]==case
        assert obj["status"]=="WHOLE_CALENDAR_PREPARED"
        assert obj["calendar"]["resident_stock"]==100000
        assert obj["calendar"]["legs"]==legs
        assert obj["horizon_s"]==obj["simulated_s"]==0
        assert obj["candidate_source_sha256"]==source["source_sha256"]
        assert obj["native_binary_sha256"]==binary["sha256"]
        assert obj["matrix_sha256"]==sha
        assert obj["peak_rss_bytes"]<8*1024**3
        assert obj["wall_s"]<7200
        total+=legs
    assert total==8461965


def test_previous_mark_compressed_native_preparation_receipts_are_now_stale():
    matrix_path=ROOT/"scenarios/v1/release_matrix.json"
    matrix_raw=matrix_path.read_bytes()
    matrix=json.loads(matrix_raw)
    plan=json.loads((ROOT/"docs/v1/PLAN.json").read_bytes())
    receipts=[
        json.loads((ART/"C5_preparation"/(c["id"]+".prepare.json")).read_bytes())
        for c in matrix["cases"]
    ]
    x=assess_v03_readiness(
        plan,matrix,matrix_sha256=hashlib.sha256(matrix_raw).hexdigest(),
        preparation_receipts=receipts,
        live_candidate_source_sha256=candidate_provenance()["source_sha256"],
        live_native_binary_sha256=native_binary_provenance()["sha256"],
    )
    assert x["v03"]["calendar_preparation_verified"]==0
    assert x["v03"]["completed_full_day_runs"]==0
    assert all(item["status"]=="REJECTED_EVIDENCE"
               for item in x["case_preparation"].values())
