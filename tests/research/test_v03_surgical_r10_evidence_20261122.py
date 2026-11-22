"""Source-backed R10 surgical evidence, original population and negative scopes."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_surgical_residence_20261122"

def read(name):
    return json.loads((ART/name).read_bytes())

def test_first_original_100k_25710_full_wire_is_real_but_not_a_24h_day():
    x=read("R10_postrestore_original_100k_10s.json")
    assert x["case"]=="valley_weekday_s7"
    assert x["status"]=="EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON"
    assert x["error"] is None
    assert x["requested_duration_s"]==x["valid_advanced_duration_s"]==10
    assert x["completed_time_s"]==25710
    assert x["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert x["final_checkpoint_sha256"]=="64b77baece5ba45fa0928d59b58d9f8f9fc2178bcd93542b05264736978733fe"
    assert x["final_checkpoint_bytes"]==4011233450
    assert x["current_source_dirty"] is False
    assert x["native_process_cap_bytes"]==8*1024**3
    assert x["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    assert x["completed_mass_ledger"] is not None
    for name in ("road_work:transfer candidates",
                 "service_sinks:service finish",
                 "journey_commit:checkpointability",
                 "engine_admission:capture/validation"):
        assert x["trace_sites"][name]["exceeded"]==0
    assert x["trace_sites"]["road_post:optional keyset interning estimate"]["exceeded"]==1
    assert x["trace_counters"]["keyset.surgical_deferred_due_to_budget"][1]==1

def test_restoring_25710_20s_proposal_is_blocked_before_any_physics():
    x=read("R10_same_native_25710_requested_20s.json")
    assert x["case"]=="valley_weekday_s7"
    assert x["requested_duration_s"]==20
    assert x["status"]=="ERROR"
    assert x["valid_advanced_duration_s"] is None
    assert x["final_checkpoint_sha256"] is None
    assert x["error"]["phase"]=="RESTORE_PREVIOUS_COMPLETE_STATE"
    assert "native journey stored/working byte budget" in x["error"]["message"]
    q=x["trace_sites"]["journey_store:stored/working"]
    assert q["exceeded"]==1
    assert q["max_required"]==226237504
    assert q["limit_at_max"]==226233207

def test_final_current_native_three_city_preps_are_new_source_and_not_full_day():
    s=read("R10_current_source_readiness.json")
    assert s["v03"]["status"]=="BLOCKED"
    assert s["dag"]["completed"]==19 and s["dag"]["total"]==21
    assert s["v03"]["calendar_preparation_verified"]==3
    assert s["v03"]["completed_full_day_runs"]==0
    assert s["v03"]["required_full_day_runs"]==9
    total=0
    for key in ("river_weekday_s17","coastal_weekend_s41","valley_weekday_s7"):
        d=json.loads((ART/"R10_current_native_preparation"/(key+".prepare.json")).read_bytes())
        assert d["status"]=="WHOLE_CALENDAR_PREPARED"
        assert d["simulated_s"]==d["horizon_s"]==0
        assert d["calendar"]["resident_stock"]==100000
        assert d["candidate_source_sha256"]==s["measurement_context"]["live_candidate_source_sha256"]
        assert d["native_binary_sha256"]==s["measurement_context"]["live_native_binary_sha256"]
        assert d["candidate"]["source_dirty"] is False
        total+=d["calendar"]["legs"]
    assert total==8461965

def test_stage_ledger_has_exactly_ten_unique_pushes_and_current_source():
    d=read("R10_STAGE_LEDGER.json")
    x=d["ten_separate_stage_commits_remote_verified"]
    assert len(x)==d["number_of_stages"]==len({s["sha"] for s in x})==10
    assert [v["stage"] for v in x]==[f"R{i}/C{i}" for i in range(1,11)]
    assert x[-1]["sha"]=="5348d81650961dc602b257624e373c4a17f863aa"
    assert all(v["published_remote_SHA_readback"] for v in x)
    assert d["valid_source_original_25710"]["physically_completed_seconds"]==10
    assert d["canonical_readiness"]["full_24h_100k_runs_completed"]==0
    assert d["canonical_readiness"]["DAG_total"]==21
    assert d["canonical_readiness"]["scoped_DAG_completed"]==19
    assert d["total_original_planned_legs"]==8461965
    assert d["matrix_sha256"]==hashlib.sha256(
        (ROOT/"scenarios/v1/release_matrix.json").read_bytes()).hexdigest()
