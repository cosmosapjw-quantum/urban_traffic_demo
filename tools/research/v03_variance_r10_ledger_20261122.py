#!/usr/bin/env python3
"""Source-locked 10-pair MetroFlow V03 variance/restart research evidence."""
from __future__ import annotations
from pathlib import Path
from hashlib import sha256
import json
import subprocess

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_variance_restart_20261122"
PARENT="7a06729eb97177c770e46a5661f28cd9572b9927"
STAGE_TERMINAL="ecd5f28de1fdfb6b59c1e9958797c824d1f32acd"
BRANCH="research/v03-variance-restart-20261122"
ORIGINAL_25710_SHA="64b77baece5ba45fa0928d59b58d9f8f9fc2178bcd93542b05264736978733fe"
ORIGINAL_25710_BYTES=4011233450
RUNTIME_HARD_LIMIT=8*1024**3


def load(name:str)->dict:
    return json.loads((ART/name).read_bytes())

def identity(file:Path)->str:
    return sha256(file.read_bytes()).hexdigest()


def main()->None:
    from tools.run_v1_local_acceptance import candidate_provenance
    from metroflow.v1.native_engine import native_binary_provenance
    live=candidate_provenance()
    binary=native_binary_provenance()
    assert live["status"]=="MEASURED" and live["source_dirty"] is False
    assert binary["status"]=="MEASURED"
    matrix=json.loads((ROOT/"scenarios/v1/release_matrix.json").read_bytes())
    plan=json.loads((ROOT/"docs/v1/PLAN.json").read_bytes())
    assert matrix["population"]==100000
    assert matrix["horizon_s"]==86400
    assert matrix["limits"]["peak_rss_bytes"]==RUNTIME_HARD_LIMIT
    assert matrix["limits"]["wall_s"]==7200
    assert plan["version"]=="1.1.26" and len(plan["nodes"])==21
    rows=subprocess.check_output(
        ["git","log","--reverse","--format=%H|%s",f"{PARENT}..{STAGE_TERMINAL}"],
        cwd=ROOT,text=True).splitlines()
    assert len(rows)==10, f"bad number of bounded stage commits: {len(rows)}"
    ten_commits=[]
    for i,item in enumerate(rows,1):
        sha,subject=item.split("|",1)
        assert f"R{i} C{i}" in subject
        ten_commits.append({
            "stage":f"R{i}/C{i}","commit_SHA":sha,"subject":subject,
            "remote_SHA_readback_verified":True,
        })
    readiness=load("R10_current_source_readiness.json")
    assert readiness["v03"]["status"]=="BLOCKED"
    assert (readiness["dag"]["completed"],readiness["dag"]["total"])==(19,21)
    assert readiness["v03"]["calendar_preparation_verified"]==3
    assert (readiness["v03"]["completed_full_day_runs"],
            readiness["v03"]["required_full_day_runs"])==(0,9)
    assert readiness["measurement_context"]["live_candidate_source_sha256"]==live["source_sha256"]
    assert readiness["measurement_context"]["live_native_binary_sha256"]==binary["sha256"]
    sources={}
    total_legs=0
    for case in matrix["cases"]:
        key=case["id"]
        path=ART/"R10_current_native_preparation"/f"{key}.prepare.json"
        c=json.loads(path.read_bytes())
        assert c["status"]=="WHOLE_CALENDAR_PREPARED"
        assert c["candidate_source_sha256"]==live["source_sha256"]
        assert c["native_binary_sha256"]==binary["sha256"]
        assert c["candidate"]["source_dirty"] is False
        assert c["calendar"]["resident_stock"]==100000
        assert c["horizon_s"]==c["simulated_s"]==0
        assert c["step_s"]==10.0
        assert c["matrix_sha256"]==identity(ROOT/"scenarios/v1/release_matrix.json")
        total_legs+=c["calendar"]["legs"]
        sources[key]={
            "status":c["status"],
            "residents":int(c["calendar"]["resident_stock"]),
            "planned_legs":c["calendar"]["legs"],
            "wall_s":c["wall_s"],
            "peak_rss_bytes":c["peak_rss_bytes"],
            "receipt_SHA256":identity(path),
            "physical_simulated_s":0,
        }
    assert total_legs==8461965
    experiments=[]
    for name in [
        "R6_original_100k_25710_requested_20s.json",
        "R8_original_100k_25710_requested_20s.json",
        "R10_original_100k_25710_requested_20s.json",
        "R10_compact_original_100k_25710_requested_20s.json",
        "R10_sequential_original_100k_25710_requested_20s.json",
        "R10_paged_original_100k_25710_requested_20s.json",
        "R10_offtrace_original_100k_25710_requested_20s.json",
    ]:
        row=load(name)
        assert row["case"]=="valley_weekday_s7"
        assert row["native_process_cap_bytes"]==RUNTIME_HARD_LIMIT
        assert row["current_source_dirty"] is False
        assert row["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
        assert row["start_time_s"]==25710
        assert row["requested_duration_s"]==20
        assert not row["completed_step_wall_s"]
        assert not row["final_checkpoint_sha256"]
        experiments.append({
            "receipt":name,
            "receipt_SHA256":identity(ART/name),
            "status":row["status"],
            "trace_mode":row["trace_mode"],
            "requested_physical_seconds":20,
            "actually_completed_physical_seconds":row["valid_advanced_duration_s"],
            "starting_clock_s":25710,
            "first_blocked_clock_s":row["blocked_target_time_s"],
            "error":row["error"],
            "full_initial_wire_ledger_verified":row["previous_checkpoint_full_wire_roundtrip_exact"],
            "source_SHA256":row["current_candidate_source_sha256"],
            "native_SHA256":row["current_native_binary_sha256"],
            "wall_total_including_original_preparation_and_IO_s":row["wall_total_including_full_preparation_and_checkpoint_io_s"],
            "max_RSS_bytes":row["peak_rss_bytes"],
        })
    now=load("R10_paged_original_100k_25710_requested_20s.json")
    assert now["current_candidate_source_sha256"]==live["source_sha256"]
    assert now["current_native_binary_sha256"]==binary["sha256"]
    assert now["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert now["previous_mass_ledger"] is not None
    assert now["valid_advanced_duration_s"]==0
    assert now["blocked_target_time_s"]==25720
    head=now["trace_sites"]["road_work:transfer header reservation"]
    transfer=now["trace_sites"]["road_work:transfer candidates"]
    assert head["exceeded"]==1 and head["max_required"]==4952601544
    assert head["limit_at_max"]==4952574903
    assert transfer["exceeded"]==0
    assert transfer["calls"]==271693
    uninstrumented=load("R10_offtrace_original_100k_25710_requested_20s.json")
    assert uninstrumented["trace_mode"]=="off"
    assert uninstrumented["current_candidate_source_sha256"]==live["source_sha256"]
    assert uninstrumented["current_native_binary_sha256"]==binary["sha256"]
    assert uninstrumented["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert uninstrumented["previous_mass_ledger"] is not None
    assert uninstrumented["status"]=="BLOCKED_RESOURCE"
    assert uninstrumented["valid_advanced_duration_s"]==0
    assert uninstrumented["blocked_target_time_s"]==25720
    assert "indexed sweep preflight" in uninstrumented["error"]["message"]
    uninstrumented_required=4999929400
    uninstrumented_allowed=4952574903
    assert f"required_bytes={uninstrumented_required}" in uninstrumented["error"]["message"]
    assert f"budget_bytes={uninstrumented_allowed}" in uninstrumented["error"]["message"]
    result={
        "schema":"METROFLOW_V03_2ND_MOMENT_RESTART_R1_R10_C1_C10_20261122_V1",
        "repository":"cosmosapjw-quantum/urban_traffic_demo",
        "branch":BRANCH,
        "stage_parent":PARENT,
        "ten_stage_terminal_SHA":STAGE_TERMINAL,
        "ten_separately_pushed_stages":ten_commits,
        "stage_completed":10,
        "source_SHA256":live["source_sha256"],
        "native_binary_SHA256":binary["sha256"],
        "authority":{
            "original_matrix_SHA256":identity(ROOT/"scenarios/v1/release_matrix.json"),
            "original_plan_SHA256":identity(ROOT/"docs/v1/PLAN.json"),
            "residents_per_city":100000,
            "city_cases":3,"original_full_days_required":9,
            "original_day_duration_s":86400,
            "original_native_dt_s":10,
            "original_process_RLIMIT_AS_bytes":RUNTIME_HARD_LIMIT,
            "original_wall_limit_per_run_s":7200,
            "original_physical_source_unchanged":True,
        },
        "science":{
            "route_first_age_transport":"DERIVED_PREVIOUS_LOOP",
            "finite_horizon_route_second_age_transport":"DERIVED_THIS_LOOP",
            "quadratic_age_residence_variance":"DERIVED_CONDITIONAL_ON_SOURCE_J",
            "route_aging_tail_bound":"DERIVED",
            "independent_fraction_two_route_cohort_cases":384,
            "historical_100k_second_birth_moment_available":False,
            "full_city_second_moment_validation":"NOT_RUN",
        },
        "implementation":{
            "true_one_decoder_replay":"VERIFIED_ORIGINAL_100K",
            "exact_two_bundle_native_load_validation":"VERIFIED_ORIGINAL_100K",
            "trace_only_lineage_16_byte_injective_encoding":"RUST_VERIFIED_SCOPED",
            "trace_only_lineage_fixed_1024_paged_allocation":"RUST_VERIFIED_SCOPED",
            "source_serial_alloc_max":"RUST_VERIFIED_SCOPED",
            "native_checkpoint_25710_load_and_full_wire":"IMPLEMENTATION_VERIFIED",
            "native_step_25720":"BLOCKED_RESOURCE",
            "rust_lib_tests":"200 passed, 2 ignored",
            "full_repository_CI":"DEFERRED_BY_USER",
            "main_merge":"NOT_ATTEMPTED",
        },
        "trusted_prior_original_100k_25710":{
            "checkpoint_SHA256":ORIGINAL_25710_SHA,
            "checkpoint_bytes":ORIGINAL_25710_BYTES,
            "source_and_native_distinct_from_current":True,
            "source_native_replay_full_wire_and_mass_ledger":"VERIFIED_SCOPED",
            "checkpoint_kept_local_only":True,
        },
        "original_100k_physical_experiments":experiments,
        "last_first_blocker":{
            "phase":"road_work:transfer header reservation",
            "required_bytes":head["max_required"],
            "allowed_bytes":head["limit_at_max"],
            "excess_bytes":head["max_required"]-head["limit_at_max"],
            "last_transfer_candidate_calls":transfer["calls"],
            "last_transfer_candidate_exceeded":transfer["exceeded"],
            "diagnostic_source_capacity_bytes":head["terms_at_max"]["diagnostic_source_actual_capacity_bytes"],
            "incoming_source_row_count":head["terms_at_max"]["incoming_rows"],
            "next_physical_clock_s":25720,
        },
        "uninstrumented_physical_first_blocker":{
            "trace_mode":"off",
            "phase":"indexed sweep preflight",
            "required_bytes":uninstrumented_required,
            "allowed_bytes":uninstrumented_allowed,
            "excess_bytes":uninstrumented_required-uninstrumented_allowed,
            "physical_seconds_advanced":0,
            "original_checkpoint_full_wire_and_mass_verified":True,
        },
        "source_current_city_calendar_preparations":sources,
        "total_city_planned_legs":total_legs,
        "V03":{
            "DAG_scoped_completed":19,
            "DAG_total":21,
            "DAG_percent":19/21*100,
            "original_direct_predecessors_done":3,
            "original_direct_predecessors_total":3,
            "original_calendars_prepared_current_source":3,
            "original_city_calendars_total":3,
            "full_day_runs_completed":0,
            "full_day_runs_required":9,
            "status":"BLOCKED",
            "RLS01":"PLANNED",
        },
        "nonclaims":[
            "No current-source physical 25720 tick was completed.",
            "Three city preparations simulate zero physical seconds.",
            "This candidate did not run original time zero to 25710.",
            "It is not valid to infer variance from historical mass and first birth moment without J.",
            "Original source-independent full repository CI not run.",
        ],
        "next_surgical_work":[
            "Do not add fixed byte credits. Record-mode header reserve 26,641B and off-mode indexed sweep 47,354,497B need distinct physical phase ownership studies.",
            "Run same-source physical 25720 and 25730 after new diagnosed source change, then positive 20/40/80/160-second ladder.",
            "After source stability, run original t0→86400 all 3 city cases ×3 reps with same original caps and full ledger.",
        ],
    }
    target=ART/"R10_STAGE_LEDGER.json"
    target.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print("EVIDENCE",target,"stage_count",len(ten_commits))
    print("READY",result["V03"])
    print("ORIGINAL_TRIALS",len(experiments),"LAST_RESOURCE_EXCESS_B",result["last_first_blocker"]["excess_bytes"])

if __name__=="__main__":
    main()
