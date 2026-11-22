"""Source-backed MetroFlow V03 R10 second age-moment/restart surgical evidence."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
A=ROOT/"artifacts/v03_variance_restart_20261122"

def get(name):
    return json.loads((A/name).read_bytes())

def test_ten_stage_commits_are_separate_from_canonical_21_node_roadmap():
    d=get("R10_STAGE_LEDGER.json")
    stages=d["ten_separately_pushed_stages"]
    assert len(stages)==d["stage_completed"]==10
    assert len({r["commit_SHA"] for r in stages})==10
    assert [r["stage"] for r in stages]==[f"R{i}/C{i}" for i in range(1,11)]
    assert stages[0]["commit_SHA"]=="7030522c2743b99967b963c71aa9d5933c1b7b11"
    assert stages[-1]["commit_SHA"]=="ecd5f28de1fdfb6b59c1e9958797c824d1f32acd"
    assert all(r["remote_SHA_readback_verified"] for r in stages)
    assert d["V03"]["DAG_scoped_completed"]==19
    assert d["V03"]["DAG_total"]==21
    assert d["V03"]["original_calendars_prepared_current_source"]==3
    assert d["V03"]["full_day_runs_completed"]==0
    assert d["V03"]["full_day_runs_required"]==9
    assert d["V03"]["status"]=="BLOCKED"
    assert d["authority"]["original_process_RLIMIT_AS_bytes"]==8*1024**3


def test_original_100k_cross_native_25710_full_wire_passed_but_25720_blocked():
    x=get("R10_paged_original_100k_25710_requested_20s.json")
    assert x["status"]=="BLOCKED_RESOURCE"
    assert x["case"]=="valley_weekday_s7"
    assert x["cross_native_original_25710_source"] is True
    assert x["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert x["previous_mass_ledger"] is not None
    assert x["requested_duration_s"]==20
    assert x["valid_advanced_duration_s"]==0
    assert x["completed_time_s"]==25710
    assert x["blocked_target_time_s"]==25720
    assert x["final_checkpoint_sha256"] is None
    assert x["error"]["class"]=="BudgetExceeded"
    assert "phase=transfer header reservation" in x["error"]["message"]
    assert x["current_source_dirty"] is False
    assert x["native_process_cap_bytes"]==8*1024**3
    assert x["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    t=x["trace_sites"]["road_work:transfer candidates"]
    h=x["trace_sites"]["road_work:transfer header reservation"]
    assert t["calls"]==271693 and t["exceeded"]==0
    assert h["calls"]==271694 and h["exceeded"]==1
    assert h["max_required"]==4952601544
    assert h["limit_at_max"]==4952574903
    assert h["max_required"]-h["limit_at_max"]==26641


def test_paged_trace_has_bounded_actual_source_owners_and_improved_capacity():
    old=get("R10_original_100k_25710_requested_20s.json")
    new=get("R10_paged_original_100k_25710_requested_20s.json")
    assert old["trace_sites"]["road_work:transfer candidates"]["exceeded"]==1
    assert new["trace_sites"]["road_work:transfer candidates"]["exceeded"]==0
    assert old["status"]==new["status"]=="BLOCKED_RESOURCE"
    assert old["current_candidate_source_sha256"]!=new["current_candidate_source_sha256"]
    assert old["current_native_binary_sha256"]!=new["current_native_binary_sha256"]
    assert new["peak_rss_bytes"]<old["peak_rss_bytes"]
    assert new["trace_sites"]["road_work:transfer header reservation"]["terms_at_max"][
        "diagnostic_source_actual_capacity_bytes"]==300001680


def test_fresh_source_all_city_preparation_does_not_mean_original_full_day():
    d=get("R10_STAGE_LEDGER.json")
    assert d["total_city_planned_legs"]==8461965
    assert (d["V03"]["full_day_runs_completed"],d["V03"]["full_day_runs_required"])==(0,9)
    e=get("R10_current_source_readiness.json")
    assert e["v03"]["status"]=="BLOCKED"
    assert e["v03"]["calendar_preparation_verified"]==3
    assert (e["dag"]["completed"],e["dag"]["total"])==(19,21)
    assert e["measurement_context"]["live_candidate_source_sha256"]==d["source_SHA256"]
    assert e["measurement_context"]["live_native_binary_sha256"]==d["native_binary_SHA256"]
    total=0
    for key in ("river_weekday_s17","coastal_weekend_s41","valley_weekday_s7"):
        p=A/"R10_current_native_preparation"/f"{key}.prepare.json"
        c=json.loads(p.read_bytes())
        assert c["status"]=="WHOLE_CALENDAR_PREPARED"
        assert c["calendar"]["resident_stock"]==100000
        assert c["simulated_s"]==c["horizon_s"]==0
        assert c["candidate_source_sha256"]==d["source_SHA256"]
        assert c["native_binary_sha256"]==d["native_binary_SHA256"]
        assert c["candidate"]["source_dirty"] is False
        assert c["matrix_sha256"]==hashlib.sha256(
            (ROOT/"scenarios/v1/release_matrix.json").read_bytes()).hexdigest()
        total+=c["calendar"]["legs"]
    assert total==8461965


def test_uninstrumented_original_physics_has_different_real_source_gate():
    x=get("R10_offtrace_original_100k_25710_requested_20s.json")
    assert x["case"]=="valley_weekday_s7"
    assert x["trace_mode"]=="off"
    assert x["cross_native_original_25710_source"] is True
    assert x["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert x["previous_mass_ledger"] is not None
    assert x["status"]=="BLOCKED_RESOURCE"
    assert x["valid_advanced_duration_s"]==0
    assert x["start_time_s"]==x["completed_time_s"]==25710
    assert x["blocked_target_time_s"]==25720
    assert x["requested_duration_s"]==20
    assert x["final_checkpoint_sha256"] is None
    assert x["native_process_cap_bytes"]==8*1024**3
    assert x["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    assert "phase=indexed sweep preflight" in x["error"]["message"]
    assert "required_bytes=4999929400" in x["error"]["message"]
    assert "budget_bytes=4952574903" in x["error"]["message"]
    assert x["current_source_dirty"] is False


def test_source_physics_theorem_and_replay_do_not_inflate_acceptance():
    d=get("R10_STAGE_LEDGER.json")
    assert d["science"]["finite_horizon_route_second_age_transport"]=="DERIVED_THIS_LOOP"
    assert d["science"]["independent_fraction_two_route_cohort_cases"]==384
    assert d["science"]["historical_100k_second_birth_moment_available"] is False
    assert d["implementation"]["true_one_decoder_replay"]=="VERIFIED_ORIGINAL_100K"
    assert d["implementation"]["exact_two_bundle_native_load_validation"]=="VERIFIED_ORIGINAL_100K"
    assert d["uninstrumented_physical_first_blocker"]["excess_bytes"]==47354497
    assert d["last_first_blocker"]["excess_bytes"]==26641
    assert d["V03"]["status"]=="BLOCKED"
