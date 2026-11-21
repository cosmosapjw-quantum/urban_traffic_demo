"""Latest source-bound MetroFlow V03 R10 evidence assertions, not 24h PASS."""
from pathlib import Path
import json
import hashlib

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_live_header_age_20261122"


def read(name:str):
    return json.loads((ART/name).read_bytes())


def test_research_stage_ten_sha_count_and_v03_readiness_are_separate():
    x=read("R10_STAGE_LEDGER.json")
    assert x["total_bounded_stages"]==x["stages_committed"]==10
    stages=x["stage_commits"]
    assert len(stages)==len({r["sha"] for r in stages})==10
    assert [r["stage"] for r in stages]==[f"R{i}/C{i}" for i in range(1,11)]
    assert stages[-1]["sha"]=="745c6172f302c7f169d08978e20cd7173a850eb0"
    assert all(r["remote_sha_readback"] for r in stages)
    r=x["readiness"]
    assert (r["dag_scoped_completed"],r["dag_total"])==(19,21)
    assert (r["direct_v03_dependencies_completed"],r["direct_v03_dependencies_total"])==(3,3)
    assert (r["source_current_whole_calendars_prepared"],r["source_current_total_cases"])==(3,3)
    assert (r["original_24h_runs_completed"],r["original_24h_runs_required"])==(0,9)
    assert r["V03"]=="BLOCKED" and r["release_ready"] is False
    assert x["original_matrix_sha256"]==hashlib.sha256(
        (ROOT/"scenarios/v1/release_matrix.json").read_bytes()
    ).hexdigest()
    assert x["original_contract"]["rlimit_as_bytes"]==8*1024**3
    assert x["total_original_calendar_planned_legs"]==8461965


def test_original_100k_cross_native_25_710_is_not_falsely_accepted():
    x=read("R10_postroad_cross_native_100k_10s.json")
    assert x["status"]=="BLOCKED_RESOURCE"
    assert x["start_time_s"]==x["completed_time_s"]==25700
    assert x["requested_duration_s"]==10 and x["valid_advanced_duration_s"]==0
    assert x["blocked_target_time_s"]==25710
    assert x["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert x["error"]["class"]=="BudgetExceeded"
    assert "phase=continuous keyset allocation" in x["error"]["message"]
    assert x["final_checkpoint_sha256"] is None
    assert x["trace_sites"]["road_work:transfer candidates"]["calls"]==258538
    assert x["trace_sites"]["road_work:transfer candidates"]["exceeded"]==0
    assert x["trace_sites"]["road_post:event candidate materialize after road"]["exceeded"]==0
    q=x["trace_sites"]["road_post:continuous keyset allocation"]
    assert q["exceeded"]==1
    assert q["max_required"]==5533362416
    assert q["limit_at_max"]==5025214575


def test_same_current_source_80s_request_has_only_50s_valid_prefix():
    x=read("R10_original_100k_requested_80s_from_25650.json")
    assert x["status"]=="BLOCKED_RESOURCE_WITH_VALID_PREFIX"
    assert x["start_time_s"]==25650
    assert x["requested_duration_s"]==80
    assert x["valid_advanced_duration_s"]==50
    assert x["completed_time_s"]==25700
    assert x["blocked_target_time_s"]==25710
    assert x["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert x["final_checkpoint_sha256"]=="ac7a209c6adfd594c791d1ac4b5b33c6e013ae73b7b594e42121115c89bd8369"
    assert x["final_checkpoint_bytes"]==3405043386
    assert x["native_process_cap_bytes"]==8*1024**3
    assert x["current_source_dirty"] is False
    assert x["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    assert len(x["completed_step_wall_s"])==5
    assert [p["completed_time_s"] for p in x["completed_step_wall_s"]]==[
        25660,25670,25680,25690,25700
    ]
    q=x["trace_sites"]["road_post:event candidate materialize after road"]
    assert q["exceeded"]==1
    assert q["max_required"]==5015432736
    assert q["limit_at_max"]==4939690935
    assert x["current_candidate_source_sha256"]==read(
        "R10_postroad_cross_native_100k_10s.json"
    )["current_candidate_source_sha256"]


def test_three_fresh_source_city_preparation_cases_are_not_full_simulations():
    z=read("R10_current_source_readiness.json")
    assert z["v03"]["calendar_preparation_verified"]==3
    assert z["v03"]["completed_full_day_runs"]==0
    assert z["v03"]["status"]=="BLOCKED"
    assert all(c["status"]=="PREPARED_SCOPED" for c in z["case_preparation"].values())
    total=0
    for case in ("river_weekday_s17","coastal_weekend_s41","valley_weekday_s7"):
        p=ART/"R10_current_native_preparation"/(case+".prepare.json")
        c=json.loads(p.read_bytes())
        assert c["status"]=="WHOLE_CALENDAR_PREPARED"
        assert c["simulated_s"]==c["horizon_s"]==0
        assert c["calendar"]["resident_stock"]==100000
        assert c["candidate_source_sha256"]==z["measurement_context"]["live_candidate_source_sha256"]
        assert c["native_binary_sha256"]==z["measurement_context"]["live_native_binary_sha256"]
        assert c["candidate"]["source_dirty"] is False
        total+=c["calendar"]["legs"]
    assert total==8461965
