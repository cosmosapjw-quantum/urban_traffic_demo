#!/usr/bin/env python3
"""Reproducible immutable-source MetroFlow V03 age-excess R1-R10 evidence ledger."""
from __future__ import annotations
from pathlib import Path
from hashlib import sha256
import json
import subprocess

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_age_loss_checkpoint_20261122"
BASE="e1b9e98a49556c2ae2deb9445cde755488ccd84b"
TEN_TERMINAL="b54e45d1d73502ee52f39968d6829325859809b2"
BRANCH="research/v03-age-loss-checkpoint-20261122"
CAP=8*1024**3
ORIGINAL_25720="447570b8721b17fa19edf159bc4c474cfd6ad41dc936ab0b0114d902e36f0bf9"

def read(name:str)->dict:
    return json.loads((ART/name).read_bytes())

def digest(path:Path)->str:
    return sha256(path.read_bytes()).hexdigest()

def main()->None:
    from tools.run_v1_local_acceptance import candidate_provenance
    from metroflow.v1.native_engine import native_binary_provenance
    src=candidate_provenance()
    native=native_binary_provenance()
    assert src["status"]=="MEASURED" and src["source_dirty"] is False
    assert native["status"]=="MEASURED"
    matrix=json.loads((ROOT/"scenarios/v1/release_matrix.json").read_bytes())
    plan=json.loads((ROOT/"docs/v1/PLAN.json").read_bytes())
    assert matrix["population"]==100000 and matrix["horizon_s"]==86400
    assert matrix["limits"]["peak_rss_bytes"]==CAP
    assert matrix["limits"]["wall_s"]==7200
    assert len(plan["nodes"])==21 and plan["version"]=="1.1.26"
    rows=subprocess.check_output(
        ["git","log","--reverse","--format=%H|%s",f"{BASE}..{TEN_TERMINAL}"],
        cwd=ROOT,text=True).splitlines()
    assert len(rows)==10,len(rows)
    remote_line=subprocess.check_output(
        ["git","ls-remote","origin",f"refs/heads/{BRANCH}"],cwd=ROOT,text=True).strip()
    remote_head,remote_ref=remote_line.split()
    assert remote_ref==f"refs/heads/{BRANCH}"
    stage=[]
    for i,row in enumerate(rows,1):
        sha,title=row.split("|",1)
        assert f"R{i} C{i}" in title,(i,title)
        subprocess.run(["git","merge-base","--is-ancestor",sha,remote_head],
                       cwd=ROOT,check=True)
        stage.append({"stage":f"R{i}/C{i}","commit_SHA":sha,"subject":title,
                      "published_in_verified_remote_ancestry":True})
    assert stage[-1]["commit_SHA"]==TEN_TERMINAL
    readiness=read("R10_final_source_readiness.json")
    assert readiness["v03"]["status"]=="BLOCKED"
    assert (readiness["dag"]["completed"],readiness["dag"]["total"])==(19,21)
    assert readiness["v03"]["calendar_preparation_verified"]==3
    assert (readiness["v03"]["completed_full_day_runs"],
            readiness["v03"]["required_full_day_runs"])==(0,9)
    assert readiness["measurement_context"]["live_candidate_source_sha256"]==src["source_sha256"]
    assert readiness["measurement_context"]["live_native_binary_sha256"]==native["sha256"]
    original_preps={}
    legs=0
    for item in matrix["cases"]:
        key=item["id"]
        path=ART/"R10_final_native_preparation"/f"{key}.prepare.json"
        x=json.loads(path.read_bytes())
        assert x["status"]=="WHOLE_CALENDAR_PREPARED"
        assert x["candidate_source_sha256"]==src["source_sha256"]
        assert x["native_binary_sha256"]==native["sha256"]
        assert x["candidate"]["source_dirty"] is False
        assert x["calendar"]["resident_stock"]==100000
        assert x["simulated_s"]==x["horizon_s"]==0
        assert x["matrix_sha256"]==digest(ROOT/"scenarios/v1/release_matrix.json")
        legs+=x["calendar"]["legs"]
        original_preps[key]={
            "status":x["status"],"resident_stock":int(x["calendar"]["resident_stock"]),
            "legs":x["calendar"]["legs"],"wall_s":x["wall_s"],
            "peak_rss_bytes":x["peak_rss_bytes"],"physical_simulated_s":0,
            "receipt_SHA256":digest(path)}
    assert legs==8461965
    samples=[]
    for name in (
        "R6_original_100k_25710_off_requested_20s.json",
        "R7_25720_replay_original_100k_requested_10s.json",
        "R7_guard_values_100k_25720_requested_10s.json",
        "R9_original_100k_25720_off_requested_20s.json",
        "R9_service_corrected_25720_requested_20s.json",
        "R10_compact_destination_25720_requested_20s.json",
        "R10_current_native_25710_requested_10s.json",
    ):
        d=read(name)
        assert d["case"]=="valley_weekday_s7"
        assert d["native_process_cap_bytes"]==CAP
        assert d["trace_mode"]=="off" and d["current_source_dirty"] is False
        assert d["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
        samples.append({
            "receipt":name,"receipt_SHA256":digest(ART/name),
            "source_SHA256":d["current_candidate_source_sha256"],
            "native_SHA256":d["current_native_binary_sha256"],
            "status":d["status"],"error":d.get("error"),
            "from_physical_s":d["start_time_s"],
            "requested_duration_s":d["requested_duration_s"],
            "valid_advanced_duration_s":d.get("valid_advanced_duration_s"),
            "completed_clock_s":d.get("completed_time_s"),
            "next_blocked_clock_s":d.get("blocked_target_time_s"),
            "input_full_wire_roundtrip_verified":d.get("previous_checkpoint_full_wire_roundtrip_exact"),
            "reported_cross_native":d.get("previous_checkpoint_cross_native"),
            "cross_native_from_actual_hashes":(
                d["historical_native_source_identity"]["native_sha256"]
                != d["current_native_binary_sha256"]
                if d.get("historical_native_source_identity") else None),
            "output_checkpoint_SHA256":d.get("final_checkpoint_sha256"),
            "output_checkpoint_bytes":d.get("final_checkpoint_bytes"),
            "step_wall_s":d.get("completed_step_wall_s"),
            "wall_total_including_restore_and_IO_s":d.get("wall_total_including_full_preparation_and_checkpoint_io_s"),
            "peak_RSS_bytes":d.get("peak_rss_bytes")
        })
    first=read("R6_original_100k_25710_off_requested_20s.json")
    assert first["status"]=="BLOCKED_RESOURCE_WITH_VALID_PREFIX"
    assert first["completed_time_s"]==25720 and first["valid_advanced_duration_s"]==10
    assert first["final_checkpoint_sha256"]==ORIGINAL_25720
    assert first["final_checkpoint_bytes"]==4677350066
    assert first["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert first["completed_mass_ledger"] is not None
    original_bin=ART/"R6_original_100k_25710_off_requested_20s.final.bin"
    assert original_bin.stat().st_size==4677350066
    latest=read("R10_compact_destination_25720_requested_20s.json")
    assert latest["current_candidate_source_sha256"]==src["source_sha256"]
    assert latest["current_native_binary_sha256"]==native["sha256"]
    assert latest["start_time_s"]==25720
    assert latest["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert latest["previous_mass_ledger"]==first["completed_mass_ledger"]
    completed_seconds=latest.get("valid_advanced_duration_s")
    if completed_seconds is None:
        completed_seconds=0
    assert 0<=completed_seconds<=latest["requested_duration_s"]
    # A final stored file may be a valid prefix even if the full requested
    # horizon ended BLOCKED_RESOURCE_WITH_VALID_PREFIX.
    if completed_seconds>0:
        assert latest["final_checkpoint_sha256"] is not None
        checkpoint=ART/"R10_compact_destination_25720_requested_20s.final.bin"
        assert checkpoint.stat().st_size==latest["final_checkpoint_bytes"]
    else:
        assert latest["final_checkpoint_sha256"] is None
    confirmation=read("R10_current_native_25710_requested_10s.json")
    assert confirmation["current_candidate_source_sha256"]==src["source_sha256"]
    assert confirmation["current_native_binary_sha256"]==native["sha256"]
    if confirmation.get("valid_advanced_duration_s")==10:
        assert confirmation["completed_time_s"]==25720
        assert confirmation["final_checkpoint_sha256"]==ORIGINAL_25720
        assert confirmation["final_checkpoint_bytes"]==4677350066
    science_log=ART/"R10_closeout_scientific_tests.log"
    rust_log=ART/"R10_closeout_rust_tests.log"
    assert "23 passed" in science_log.read_text()
    assert "224 passed; 0 failed; 2 ignored" in rust_log.read_text()
    ledger={
        "schema":"METROFLOW_V03_AGE_EXCESS_R1_R10_C1_C10_FINAL_20261122_V1",
        "repository":"cosmosapjw-quantum/urban_traffic_demo",
        "branch":BRANCH,
        "source_clean_SHA256":src["source_sha256"],
        "source_identity_scope":src["scope"],
        "scientific_observer_file":"src/metroflow/v1/age_excess_transport.py",
        "scientific_observer_SHA256":digest(ROOT/"src/metroflow/v1/age_excess_transport.py"),
        "remote_publication_readback":{"head":remote_head,"ref":remote_ref},
        "native_binary_SHA256":native["sha256"],
        "research_parent_SHA":BASE,
        "stage_terminal_SHA":TEN_TERMINAL,
        "ten_separately_pushed_stages":stage,
        "stage_count":10,
        "original_release_matrix_SHA256":digest(ROOT/"scenarios/v1/release_matrix.json"),
        "original_plan_SHA256":digest(ROOT/"docs/v1/PLAN.json"),
        "unchanged_source_policy":{
            "residents_per_city":100000,"original_city_cases":3,
            "required_city_repeats":3,"physical_step_seconds":10,
            "full_day_physical_seconds":86400,"full_day_100k_required_runs":9,
            "process_RLIMIT_AS_bytes":CAP,"per_run_wall_cap_seconds":7200
        },
        "scientific_claims":{
            "finite_horizon_route_age_excess_conservation":"DERIVED_EXACT",
            "one_sided_delay_stoploss_survival_atoms":"DERIVED_EXACT",
            "checkpoint_age_excess_window_stitching":"DERIVED_EXACT",
            "finite_horizon_censored_tail_upper_bound":"DERIVED_EXACT",
            "independent_exact_fraction_cohort_cases":2880,
            "exact_censored_tail_comparisons":7875,
            "internal_transfer_and_unentered_source_contract":"IMPLEMENTED_EXACT_ORACLE",
            "window_source_denominator":"LEFT_PLUS_RIGHT_MINUS_SHARED_ENDPOINT_STOCK",
            "general_measure_extension_requires":"finite first-age moment and entering age-excess integral",
            "native_original_microscopic_birth_measure_available":False,
            "full_original_city_age_excess_observation":"NOT_PERFORMED",
            "global_originality_claim":"NOT_ASSERTED"
        },
        "implementation_findings":{
            "real_source_snapshot_stage_arc_pool":"IMPLEMENTATION_VERIFIED_ORIGINAL_100K",
            "original_25720_physical_tick":"PHYSICAL_TICK_AND_SAVED_SCOPED",
            "old_original_25720_independent_checkpoint_reload":"VERIFIED_ORIGINAL_100K",
            "original_25730_physical_step":(
                "PHYSICAL_TICK_VALID_SCOPED" if completed_seconds>=10
                else "BLOCKED_UNRESOLVED"),
            "R10_32bit_header_projection":"RUST_VERIFIED_SCOPED",
            "full_repository_CI":"DEFERRED_BY_USER",
            "main_branch_merge":"NOT_REQUESTED"
        },
        "original_valid_100k_25720":{
            "physical_clock_s":25720,
            "preceding_physically_completed_s":10,
            "checkpoint_bytes":first["final_checkpoint_bytes"],
            "checkpoint_SHA256":first["final_checkpoint_sha256"],
            "saved_checkpoint_local_only":True,
            "mass_ledger_vehicles_persons_cargo":first["completed_mass_ledger"],
            "original_full_day_accepted":False
        },
        "original_source_native_100k_experiments":samples,
        "current_native_25710_to_25720_confirmation":{
            "status":confirmation["status"],
            "valid_advanced_duration_s":confirmation.get("valid_advanced_duration_s"),
            "completed_clock_s":confirmation.get("completed_time_s"),
            "output_checkpoint_SHA256":confirmation.get("final_checkpoint_sha256"),
            "wire_identical_to_R6":confirmation.get("final_checkpoint_sha256")==ORIGINAL_25720,
            "error":confirmation.get("error"),
        },
        "bounded_independent_review":{
            "science_agent":"/root/age_excess_audit",
            "runtime_agent":"/root/runtime_frontier_audit",
            "status":"COMPLETED_READ_ONLY_AND_INTEGRATED",
            "closed_science_findings":["duplicate thresholds","internal versus external flux",
                "unentered assigned source denominator","window denominator duplication",
                "general measure first-moment integrability"],
            "remaining_runtime_obligations":["original t25730 under current cap",
                "persistent compact event storage is unimplemented",
                "original call-input sharing proof for multi-tick native calls"],
        },
        "verification":{
            "python_related_passed":23,"python_scientific_passed":21,
            "python_receipt_binding_passed":2,"rust_library_passed":224,
            "rust_library_ignored":2,"rust_library_failed":0,
            "python_log_SHA256":digest(science_log),"rust_log_SHA256":digest(rust_log),
            "full_repository_CI":"DEFERRED_BY_USER",
        },
        "horizon_escalation":{
            "tested_requested_seconds":[10,20],
            "larger_40_80_160_seconds":"NOT_RUN_PRECEDING_20S_BLOCKED",
            "latest_t25730_failure_class":"LIVE_STORAGE_BUDGET_GUARD_NOT_OBSERVED_OOM",
        },
        "final_new_real_original_100k_observation":{
            "start_clock_s":latest["start_time_s"],
            "requested_physical_duration_s":latest["requested_duration_s"],
            "completed_physical_duration_s":completed_seconds,
            "last_valid_clock_s":latest.get("completed_time_s"),
            "next_blocked_clock_s":latest.get("blocked_target_time_s"),
            "error":latest.get("error"),
            "output_checkpoint_SHA256":latest.get("final_checkpoint_sha256"),
            "output_checkpoint_bytes":latest.get("final_checkpoint_bytes"),
        },
        "final_source_three_city_preparations":original_preps,
        "total_original_planned_legs":legs,
        "canonical_readiness":{
            "scoped_DAG_nodes_completed":19,"DAG_node_total":21,
            "scoped_percent":100*19/21,
            "V03_direct_prerequisites":3,"V03_direct_prerequisites_total":3,
            "current_source_original_city_calendars_prepared":3,
            "current_source_original_city_calendars_required":3,
            "original_full_day_100k_runs_completed":0,
            "original_full_day_100k_runs_required":9,
            "V03":"BLOCKED","RLS01":"PLANNED",
        },
        "nonclaims":[
            "No complete original full-day V03 100k acceptance was performed.",
            "The current source has not independently replayed original t0 to t25720.",
            "Calendar preparation does not simulate any physical seconds.",
            "The new stop-loss age observer has not been instrumented on historical native traffic data.",
            "No unverified byte credits or lowered physical time/number of residents were used.",
        ]
    }
    path=ART/"R10_STAGE_LEDGER.json"
    path.write_text(json.dumps(ledger,sort_keys=True,ensure_ascii=False,indent=2)+"\n")
    print("STAGES",len(stage),"SOURCE",ledger["source_clean_SHA256"])
    print("PHYSICS",ledger["final_new_real_original_100k_observation"])
    print("V03",ledger["canonical_readiness"])
    print("LEDGER",path)

if __name__=="__main__":
    main()
