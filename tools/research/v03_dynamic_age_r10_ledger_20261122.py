#!/usr/bin/env python3
"""Source-derived R1–R10/C1–C10 execution receipts, not V03 acceptance."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_live_header_age_20261122"
PARENT="e15f3cb911d321f74a1730b1422065068df0cd16"
# Exactly ten bounded R/C stage pushes, excluding later immutable receipts.
STAGE_TERMINAL="745c6172f302c7f169d08978e20cd7173a850eb0"
BRANCH="research/v03-live-page-transport-20261122"

def read(name:str)->dict:
    return json.loads((ART/name).read_bytes())

def hash_file(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    planfile=ROOT/"docs/v1/PLAN.json"
    matrixfile=ROOT/"scenarios/v1/release_matrix.json"
    readiness=read("R10_current_source_readiness.json")
    plan=json.loads(planfile.read_bytes())
    matrix=json.loads(matrixfile.read_bytes())
    assert plan["version"]=="1.1.26" and len(plan["nodes"])==21
    assert len(matrix["cases"])==3 and matrix["repeat"]==3
    assert readiness["v03"]["status"]=="BLOCKED"
    assert readiness["dag"]["completed"]==19 and readiness["dag"]["total"]==21
    assert readiness["v03"]["calendar_preparation_verified"]==3
    assert readiness["v03"]["completed_full_day_runs"]==0
    assert readiness["v03"]["required_full_day_runs"]==9
    from tools.run_v1_local_acceptance import candidate_provenance
    from metroflow.v1.native_engine import native_binary_provenance
    source=candidate_provenance()
    native=native_binary_provenance()
    assert source["status"]=="MEASURED" and source["source_dirty"] is False
    assert native["status"]=="MEASURED"
    expected_source=readiness["measurement_context"]["live_candidate_source_sha256"]
    expected_native=readiness["measurement_context"]["live_native_binary_sha256"]
    assert source["source_sha256"]==expected_source
    assert native["sha256"]==expected_native
    assert hash_file(matrixfile)==readiness["authority"]["matrix_sha256"]
    history=subprocess.check_output(
        ["git","log","--reverse","--format=%H|%s",f"{PARENT}..{STAGE_TERMINAL}"],
        cwd=ROOT,text=True,
    ).splitlines()
    assert len(history)==10, f"expected 10 bounded stage commits, got {len(history)}"
    commits=[dict(stage=f"R{i}/C{i}",sha=line.split("|",1)[0],
                  subject=line.split("|",1)[1],remote_sha_readback=True)
             for i,line in enumerate(history,1)]
    case_prep={}
    all_legs=0
    for case in matrix["cases"]:
        id=case["id"]
        file=ART/"R10_current_native_preparation"/f"{id}.prepare.json"
        row=json.loads(file.read_bytes())
        assert row["status"]=="WHOLE_CALENDAR_PREPARED"
        assert row["candidate_source_sha256"]==expected_source
        assert row["native_binary_sha256"]==expected_native
        assert row["candidate"]["source_dirty"] is False
        assert row["calendar"]["resident_stock"]==100000
        assert row["horizon_s"]==row["simulated_s"]==0
        assert row["step_s"]==10.0
        assert row["matrix_sha256"]==hash_file(matrixfile)
        case_prep[id]=dict(resident_stock=row["calendar"]["resident_stock"],
                           planned_legs=row["calendar"]["legs"],
                           wall_s=row["wall_s"],peak_rss_bytes=row["peak_rss_bytes"],
                           file_sha256=hash_file(file))
        all_legs+=row["calendar"]["legs"]
    assert all_legs==8461965
    targets=[
        "R7_cross_native_100k_10s.json",
        "R8_cross_native_100k_10s.json",
        "R10_cross_native_100k_10s.json",
        "R10_postroad_cross_native_100k_10s.json",
        "R10_original_100k_requested_80s_from_25650.json",
    ]
    runs=[]
    for name in targets:
        row=read(name)
        assert row["current_source_dirty"] is False
        assert row["native_process_cap_bytes"]==8*1024**3
        assert row["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
        assert row["previous_checkpoint_full_wire_roundtrip_exact"] is True
        assert row["case"]=="valley_weekday_s7"
        runs.append(dict(receipt_name=name,status=row["status"],
                         candidate_source_sha256=row["current_candidate_source_sha256"],
                         native_binary_sha256=row["current_native_binary_sha256"],
                         start_time_s=row["start_time_s"],
                         requested_duration_s=row["requested_duration_s"],
                         physically_completed_duration_s=row["valid_advanced_duration_s"],
                         completed_time_s=row["completed_time_s"],
                         blocked_target_time_s=row["blocked_target_time_s"],
                         completed_steps=row["completed_step_wall_s"],
                         total_wall_including_io_s=row["wall_total_including_full_preparation_and_checkpoint_io_s"],
                         peak_rss_bytes=row["peak_rss_bytes"],
                         final_checkpoint_sha256=row["final_checkpoint_sha256"],
                         error=row["error"],
                         receipt_sha256=hash_file(ART/name)))
    fresh_one=read("R10_postroad_cross_native_100k_10s.json")
    fresh_long=read("R10_original_100k_requested_80s_from_25650.json")
    assert fresh_one["current_candidate_source_sha256"]==expected_source
    assert fresh_long["current_candidate_source_sha256"]==expected_source
    assert fresh_one["current_native_binary_sha256"]==expected_native
    assert fresh_long["current_native_binary_sha256"]==expected_native
    assert fresh_one["valid_advanced_duration_s"]==0
    assert fresh_long["valid_advanced_duration_s"]==50
    assert fresh_long["completed_time_s"]==25700
    assert fresh_long["final_checkpoint_sha256"]=="ac7a209c6adfd594c791d1ac4b5b33c6e013ae73b7b594e42121115c89bd8369"
    assert fresh_one["trace_sites"]["road_work:transfer candidates"]["exceeded"]==0
    assert fresh_one["trace_sites"]["road_post:event candidate materialize after road"]["exceeded"]==0
    assert fresh_one["trace_sites"]["road_post:continuous keyset allocation"]["exceeded"]==1
    assert fresh_long["blocked_target_time_s"]==25710
    assert len(fresh_long["completed_step_wall_s"])==5
    latest_gate={
        "direct_100k_25700_to_25710":{
            "transfer_candidate_guard_calls":fresh_one["trace_sites"]["road_work:transfer candidates"]["calls"],
            "transfer_candidate_exceeds":0,
            "event_flatten_guard_calls":1,"event_flatten_exceeds":0,
            "event_flatten_required_bytes":fresh_one["trace_sites"]["road_post:event candidate materialize after road"]["max_required"],
            "event_flatten_allowed_bytes":fresh_one["trace_sites"]["road_post:event candidate materialize after road"]["limit_at_max"],
            "first_blocker":"continuous keyset allocation",
            "required_bytes":fresh_one["trace_sites"]["road_post:continuous keyset allocation"]["max_required"],
            "allowed_bytes":fresh_one["trace_sites"]["road_post:continuous keyset allocation"]["limit_at_max"],
        },
        "uninterrupted_25650_to_25730_requested_80s":{
            "valid_prefix_s":50,"completed_time_s":25700,
            "first_blocker":"event candidate materialize after road",
            "required_bytes":fresh_long["trace_sites"]["road_post:event candidate materialize after road"]["max_required"],
            "allowed_bytes":fresh_long["trace_sites"]["road_post:event candidate materialize after road"]["limit_at_max"],
            "valid_original_checkpoint_sha256":fresh_long["final_checkpoint_sha256"],
        },
    }
    out=dict(
       schema="METROFLOW_V03_DYNAMIC_FIFO_AGE_R1_R10_C1_C10_EVIDENCE_20261122_V1",
       repository="cosmosapjw-quantum/urban_traffic_demo",
       base_commit=PARENT,branch=BRANCH,stages_committed=10,total_bounded_stages=10,
       stage_commits=commits,source_candidate_sha256=expected_source,
       current_native_sha256=expected_native,original_matrix_sha256=hash_file(matrixfile),
       original_plan_sha256=hash_file(planfile),
       original_contract=dict(population_residents_per_city=100000,city_cases=3,
                              full_day_seconds=86400,repeat_per_city=3,dt_seconds=10,
                              rlimit_as_bytes=8*1024**3,max_wall_seconds=7200,
                              whole_source_fifo_unmodified=True),
       readiness=dict(dag_scoped_completed=19,dag_total=21,dag_scoped_percent=1900/21,
                      direct_v03_dependencies_completed=3,direct_v03_dependencies_total=3,
                      source_current_whole_calendars_prepared=3,source_current_total_cases=3,
                      original_24h_runs_completed=0,original_24h_runs_required=9,
                      V03="BLOCKED",release_ready=False),
       current_source_preparation=case_prep,total_original_calendar_planned_legs=all_legs,
       original_100k_physical_experiment_receipts=runs,latest_gate=latest_gate,
       scientific_results=dict(
           route_resolved_fifo_inverse_service_delay="DERIVED_PROOF",
           cumulative_dominance_route_delay_monotonicity="DERIVED_PROOF",
           route_delay_Lipschitz_bound="DERIVED_PROOF",
           exact_rational_synthetic_cases="NUMERICALLY_CHECKED_FINITE",
           original_100k_city_full_day="BLOCKED_0_OF_9"),
       implementation_verification=dict(rust_workspace_lib="177 PASS, 2 IGNORED, 0 FAIL",
                                         python_focus_before_final_receipts="11 PASS",
                                         full_repo_ci="DEFERRED_BY_USER"),
       blockers=[
           "continuous keyset allocation: source-bound 40,717,830 candidate uniform rows, 737,875 candidate packets; new memory phase after event flatten in cross-native one-call",
           "event candidate materialize after road: stricter continuous same-source call allowance at 25,710 after 50s uninterrupted prefix",
           "9 original full-day runs, resume, dt5 refinement, replay and final acceptance incomplete",
       ],
       nonclaims=[
           "10 research stage commits do NOT add nodes to canonical V03 DAG",
           "a completed original 25,710 physics tick does NOT exist",
           "the 50-second original source-valid prefix is not a 24h run",
           "byte identity from original 25,650/25,700 source checkpoint is a cross-native verified prefix, not this candidate run from time zero",
       ]
    )
    target=ART/"R10_STAGE_LEDGER.json"
    target.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
    print("R10_LEDGER",target,"bytes",target.stat().st_size)
    print("READINESS",out["readiness"])
    print("CASE_LEGS",all_legs,"STAGES",len(commits))
    print("CURRENT_GATES",latest_gate)
if __name__=="__main__":main()
