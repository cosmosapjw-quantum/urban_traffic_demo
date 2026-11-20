"""Current opt-in-native source preflight: genuine 100000-resident calendars.

Preparation verifies inputs/source, not whole-day physical run nor the
conditional safety proof of experimental Arc-pair resource accounting.
"""
import hashlib
import json
from pathlib import Path

from tools.run_v1_local_acceptance import candidate_provenance
from metroflow.v1.native_engine import native_binary_provenance
from metroflow.v1.v03_readiness import assess_v03_readiness

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_fifo_unique_accounting_20261120"


def test_actual_three_city_original_100k_calendars_source_and_binary_current():
    r=json.loads((ART/"C9_CURRENT_NATIVE_V03_READINESS.json").read_bytes())
    src=candidate_provenance()
    native=native_binary_provenance()
    assert src["status"]==native["status"]=="MEASURED"
    assert src["source_dirty"] is False
    assert r["measurement_context"]["live_candidate_source_sha256"]==src["source_sha256"]
    assert r["measurement_context"]["live_native_binary_sha256"]==native["sha256"]
    assert r["dag"]["completed"]==19 and r["dag"]["total"]==21
    assert r["v03"]["dependency_nodes_completed"]==3
    assert r["v03"]["dependency_nodes_total"]==3
    assert r["v03"]["calendar_preparation_verified"]==3
    assert r["v03"]["calendar_preparation_total"]==3
    assert r["v03"]["completed_full_day_runs"]==0
    assert r["v03"]["required_full_day_runs"]==9
    assert r["v03"]["status"]=="BLOCKED"
    assert r["v03"]["ready_for_release"] is False
    full=0
    for case,legs in [
        ("river_weekday_s17",5093765),
        ("coastal_weekend_s41",2449750),
        ("valley_weekday_s7",918450)
    ]:
        obj=json.loads((ART/"C9_preparation"/(case+".prepare.json")).read_bytes())
        assert obj["status"]=="WHOLE_CALENDAR_PREPARED"
        assert obj["case"]==case
        assert obj["calendar"]["resident_stock"]==100000
        assert obj["calendar"]["legs"]==legs
        assert obj["simulated_s"]==obj["horizon_s"]==0
        assert obj["native_binary_sha256"]==native["sha256"]
        assert obj["candidate_source_sha256"]==src["source_sha256"]
        assert obj["peak_rss_bytes"]<8*1024**3 and obj["wall_s"]<7200
        full+=legs
    assert full==8461965


def test_previous_c6_binary_is_rejected_from_new_native_eligibility():
    matrix_file=ROOT/"scenarios/v1/release_matrix.json"
    matrix_bytes=matrix_file.read_bytes()
    matrix=json.loads(matrix_bytes)
    plan=json.loads((ROOT/"docs/v1/PLAN.json").read_bytes())
    receipts=[json.loads((ART/"C6_preparation"/(c["id"]+".prepare.json")).read_bytes())
              for c in matrix["cases"]]
    result=assess_v03_readiness(
        plan,matrix,matrix_sha256=hashlib.sha256(matrix_bytes).hexdigest(),
        preparation_receipts=receipts,
        live_candidate_source_sha256=candidate_provenance()["source_sha256"],
        live_native_binary_sha256=native_binary_provenance()["sha256"],
    )
    assert result["v03"]["calendar_preparation_verified"]==0
    assert result["v03"]["completed_full_day_runs"]==0
    assert all(q["status"]=="REJECTED_EVIDENCE" for q in result["case_preparation"].values())


def test_same_source_default_failure_and_two_optin_25650_success_receipts():
    current=json.loads((ART/"C9_CURRENT_NATIVE_V03_READINESS.json").read_bytes())
    old=json.loads((ART/"C8_ORIGINAL_DEFAULT_25650.json").read_bytes())
    a=json.loads((ART/"C8_PAIR_RUN1_25650.json").read_bytes())
    b=json.loads((ART/"C8_PAIR_EXPERIMENT_25650.json").read_bytes())
    assert old["status"]=="BLOCKED_BudgetExceeded"
    assert a["status"]==b["status"]=="EXECUTED_SOURCE_BOUND_25650_SCOPED"
    assert a["final_checkpoint_sha256"]==b["final_checkpoint_sha256"]
    assert a["mass_ledger"]==b["mass_ledger"]
    assert a["loaded_native_sha256"]==b["loaded_native_sha256"]==old["loaded_native_sha256"]==current["measurement_context"]["live_native_binary_sha256"]
    assert a["source_sha256"]==b["source_sha256"]==old["source_sha256"]==current["measurement_context"]["live_candidate_source_sha256"]
    assert old["original_native_cap_bytes"]==a["original_native_cap_bytes"]==5242806391
    assert old["original_8GiB_process_cap_bytes"]==a["original_8GiB_process_cap_bytes"]==8*1024**3
    assert old["original_24h_runs_accepted"]==a["original_24h_runs_accepted"]==0
