#!/usr/bin/env python3
"""MetroFlow V03 surgical 10-stage provenance and native physics evidence."""
from __future__ import annotations
from pathlib import Path
from hashlib import sha256
import json
import subprocess

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_surgical_residence_20261122"
PARENT="472623f011a3b2e8aca21ed2fb2fa1cbc56d45d4"
STAGE_R10="5348d81650961dc602b257624e373c4a17f863aa"
BRANCH="research/v03-surgical-closure-20261122"
DAYS=86400
REQUIRED=9

def get(name:str)->dict:
    return json.loads((ART/name).read_bytes())

def digest(file:Path)->str:
    return sha256(file.read_bytes()).hexdigest()

def main()->None:
    from metroflow.v1.native_engine import native_binary_provenance
    from tools.run_v1_local_acceptance import candidate_provenance
    source=candidate_provenance()
    binary=native_binary_provenance()
    assert source["status"]=="MEASURED" and source["source_dirty"] is False
    assert binary["status"]=="MEASURED"
    base=subprocess.check_output(
        ["git","log","--reverse","--format=%H|%s",f"{PARENT}..{STAGE_R10}"],
        cwd=ROOT,text=True).splitlines()
    assert len(base)==10,base
    stages=[dict(stage=f"R{i}/C{i}",sha=line.split("|",1)[0],
                 subject=line.split("|",1)[1],published_remote_SHA_readback=True)
            for i,line in enumerate(base,1)]
    authority=json.loads((ROOT/"scenarios/v1/release_matrix.json").read_bytes())
    assert authority["population"]==100000 and authority["horizon_s"]==DAYS
    assert authority["limits"]["peak_rss_bytes"]==8*1024**3
    assert authority["limits"]["wall_s"]==7200
    matrix_sha=digest(ROOT/"scenarios/v1/release_matrix.json")
    plan=json.loads((ROOT/"docs/v1/PLAN.json").read_bytes())
    assert len(plan["nodes"])==21 and plan["version"]=="1.1.26"
    readiness=get("R10_current_source_readiness.json")
    assert readiness["v03"]["status"]=="BLOCKED"
    assert readiness["dag"]["completed"]==19 and readiness["dag"]["total"]==21
    assert readiness["v03"]["calendar_preparation_verified"]==3
    assert readiness["v03"]["completed_full_day_runs"]==0
    assert readiness["v03"]["required_full_day_runs"]==REQUIRED
    assert readiness["measurement_context"]["live_candidate_source_sha256"]==source["source_sha256"]
    assert readiness["measurement_context"]["live_native_binary_sha256"]==binary["sha256"]
    original_cases={}
    leg_total=0
    for case in authority["cases"]:
        case_id=case["id"]
        f=ART/"R10_current_native_preparation"/(case_id+".prepare.json")
        row=json.loads(f.read_bytes())
        assert row["status"]=="WHOLE_CALENDAR_PREPARED"
        assert row["horizon_s"]==row["simulated_s"]==0
        assert row["calendar"]["resident_stock"]==100000
        assert row["candidate_source_sha256"]==source["source_sha256"]
        assert row["native_binary_sha256"]==binary["sha256"]
        assert row["candidate"]["source_dirty"] is False
        assert row["matrix_sha256"]==matrix_sha
        original_cases[case_id]=dict(status=row["status"],residents=100000,
            legs=row["calendar"]["legs"],prep_wall_s=row["wall_s"],
            prep_peak_rss_bytes=row["peak_rss_bytes"],receipt_sha256=digest(f))
        leg_total+=row["calendar"]["legs"]
    assert leg_total==8461965
    receipts=[
        "R6_original_100k_25700_10s.json",
        "R8_original_100k_25700_10s.json",
        "R9_original_100k_25700_10s.json",
        "R10_original_100k_25700_10s.json",
        "R10_postcapture_original_100k_10s.json",
        "R10_postrestore_original_100k_10s.json",
        "R10_same_native_25710_requested_20s.json",
        "R10_same_process_25700_requested_20s.json",
    ]
    physical=[]
    for name in receipts:
        f=ART/name
        if not f.is_file():continue
        d=json.loads(f.read_bytes())
        assert d["case"]=="valley_weekday_s7"
        assert d["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
        assert d["native_process_cap_bytes"]==8*1024**3
        physical.append(dict(name=name,status=d["status"],
            requested_physical_s=d.get("requested_duration_s"),
            actually_completed_physical_s=d.get("valid_advanced_duration_s"),
            start_time_s=d.get("start_time_s"),last_completed_time_s=d.get("completed_time_s"),
            next_blocked_time_s=d.get("blocked_target_time_s"),
            error=d.get("error"),
            step_wall_s=d.get("completed_step_wall_s"),
            total_wall_s=d.get("wall_total_including_full_preparation_and_checkpoint_io_s"),
            peak_rss_bytes=d.get("peak_rss_bytes"),
            full_checkpoint_SHA256=d.get("final_checkpoint_sha256"),
            full_checkpoint_bytes=d.get("final_checkpoint_bytes"),
            source_sha256=d["current_candidate_source_sha256"],
            native_sha256=d["current_native_binary_sha256"],
            restored_original_wire=d.get("previous_checkpoint_full_wire_roundtrip_exact"),
            receipt_sha256=digest(f)))
    successful=get("R10_postrestore_original_100k_10s.json")
    assert successful["status"]=="EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON"
    assert successful["error"] is None
    assert successful["valid_advanced_duration_s"]==10
    assert successful["completed_time_s"]==25710
    assert successful["final_checkpoint_sha256"]=="64b77baece5ba45fa0928d59b58d9f8f9fc2178bcd93542b05264736978733fe"
    assert successful["final_checkpoint_bytes"]==4011233450
    assert successful["current_candidate_source_sha256"]==source["source_sha256"]
    assert successful["current_native_binary_sha256"]==binary["sha256"]
    summary={
        "schema":"METROFLOW_V03_SURGICAL_10_STAGE_RESEARCH_20261122_V1",
        "repository":"cosmosapjw-quantum/urban_traffic_demo",
        "research_branch":BRANCH,
        "source_stage_parent":PARENT,"stage_r10_terminal":STAGE_R10,
        "ten_separate_stage_commits_remote_verified":stages,
        "number_of_stages":10,
        "current_source_sha256":source["source_sha256"],
        "current_native_sha256":binary["sha256"],
        "matrix_sha256":matrix_sha,
        "plan_sha256":digest(ROOT/"docs/v1/PLAN.json"),
        "immutable_policy":{"residents_per_case":100000,"case_count":3,
            "repeats_per_case":3,"full_day_seconds":86400,
            "native_physical_step_seconds":10,
            "process_rlimit_as_bytes":8*1024**3,
            "maximum_wall_seconds":7200},
        "science":{"transient_route_age_stock_identity":"DERIVED_EXACT",
            "finite_route_cohort_exact_rational_tests":360,
            "time_origin_covariance":"DERIVED_AND_FINITE_CHECKED",
            "global_first_literature_claim":"NOT_CLAIMED",
            "full_original_city_theory_validation":"NOT_PERFORMED"},
        "implementation":{"optional_nonphysics_keyset_intern":
            "SOURCE_VERIFIED_SCOPED",
            "three_real_source_owner_service_finish":"IMPLEMENTATION_VERIFIED_SCOPED",
            "checkpoint_arc_identity":"IMPLEMENTATION_VERIFIED_SCOPED",
            "outer_capture_source_owner":"IMPLEMENTATION_VERIFIED_SCOPED",
            "source_snapshot_restore_owner":"IMPLEMENTATION_VERIFIED_SCOPED",
            "full_repo_CI":"DEFERRED_BY_USER"},
        "actual_original_100k_experiments":physical,
        "valid_source_original_25710":{
            "status":"EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON",
            "physically_completed_seconds":10,
            "native_original_clock_s":25710,
            "checkpoint_sha256":successful["final_checkpoint_sha256"],
            "checkpoint_bytes":successful["final_checkpoint_bytes"],
            "checkpoint_saved_locally_only":True,
            "original_mass_ledger_verified":True,
            "whole_24_hour_day_accepted":False},
        "source_pinned_city_preparations":original_cases,
        "total_original_planned_legs":leg_total,
        "canonical_readiness":{"scoped_DAG_completed":19,"DAG_total":21,
            "DAG_scoped_percent":19/21*100,
            "V03_dependencies_completed":3,"V03_dependencies_total":3,
            "fresh_same_source_city_calendars_prepared":3,
            "fresh_same_source_city_calendars_required":3,
            "full_24h_100k_runs_completed":0,"full_24h_100k_runs_required":REQUIRED,
            "V03":"BLOCKED","RLS01":"PLANNED"},
        "remaining_true_gates":[
            "Uninterrupted original 100k Valley 24h and full 3-city x 3 repeat acceptance NOT RUN",
            "Same-native reload and additional simulation past 25710 has not been established",
            "No restored source simulation from time zero for current candidate",
            "No global full repository CI or main merge"],
    }
    path=ART/"R10_STAGE_LEDGER.json"
    path.write_text(json.dumps(summary,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print("R10_STAGE_LEDGER",path,"stages",len(stages))
    print("V03",summary["canonical_readiness"])
    print("PHYSICAL",[(x["name"],x["status"],x["actually_completed_physical_s"])
                        for x in physical])
if __name__=="__main__":
    main()
