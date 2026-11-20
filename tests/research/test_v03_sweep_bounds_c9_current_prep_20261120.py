"""Current-native original whole-calendar readiness, prior receipts stale."""
import hashlib
import json
from pathlib import Path
from metroflow.v1.v03_readiness import assess_v03_readiness

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_sweep_live_bounds_20261120"
HISTORY=ROOT/"artifacts/v03_event_arc_20261120/C9_preparation"

def read(p):
    return json.loads(p.read_bytes())

def test_prepared_original_city_matrix_and_declared_zero_physics_time():
    plan=read(ROOT/"docs/v1/PLAN.json")
    matrix_path=ROOT/"scenarios/v1/release_matrix.json"
    matrix=read(matrix_path)
    sha=hashlib.sha256(matrix_path.read_bytes()).hexdigest()
    expected={"river_weekday_s17":5093765,"coastal_weekend_s41":2449750,"valley_weekday_s7":918450}
    rows=[read(ART/"C9_preparation"/(c["id"]+".prepare.json")) for c in matrix["cases"]]
    assert len(rows)==3
    src=rows[0]["candidate_source_sha256"]
    native=rows[0]["native_binary_sha256"]
    for row in rows:
        assert row["status"]=="WHOLE_CALENDAR_PREPARED"
        assert row["candidate"]["source_dirty"] is False
        assert row["calendar"]["resident_stock"]==100000
        assert row["calendar"]["legs"]==expected[row["case"]]
        assert row["matrix_sha256"]==sha
        assert row["candidate_source_sha256"]==src
        assert row["native_binary_sha256"]==native
        assert row["horizon_s"]==row["simulated_s"]==0
    r=assess_v03_readiness(plan,matrix,matrix_sha256=sha,
        preparation_receipts=rows,live_candidate_source_sha256=src,
        live_native_binary_sha256=native)
    assert r["v03"]["calendar_preparation_verified"]==3
    assert (r["v03"]["dependency_nodes_completed"],r["v03"]["dependency_nodes_total"])==(3,3)
    assert (r["dag"]["completed"],r["dag"]["total"])==(19,21)
    assert (r["v03"]["completed_full_day_runs"],r["v03"]["required_full_day_runs"])==(0,9)
    assert r["v03"]["status"]=="BLOCKED"
    assert not r["v03"]["ready_for_release"]

def test_three_historical_native_preparations_not_reused_after_code_change():
    plan=read(ROOT/"docs/v1/PLAN.json")
    mp=ROOT/"scenarios/v1/release_matrix.json";matrix=read(mp)
    meta=read(ART/"C9_CURRENT_NATIVE_READINESS.json")["measurement_context"]
    rows=[read(HISTORY/(c["id"]+".prepare.json")) for c in matrix["cases"]]
    res=assess_v03_readiness(plan,matrix,matrix_sha256=hashlib.sha256(mp.read_bytes()).hexdigest(),
        preparation_receipts=rows,
        live_candidate_source_sha256=meta["live_candidate_source_sha256"],
        live_native_binary_sha256=meta["live_native_binary_sha256"])
    assert res["v03"]["calendar_preparation_verified"]==0
    assert {x["reason"] for x in res["case_preparation"].values()} == {"CURRENT_SOURCE_CONTENT_HASH_DIFFERS"}
