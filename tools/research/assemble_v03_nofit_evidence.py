#!/usr/bin/env python3
"""Audit actual original V03 100k calendar preparation plus a NO-FIT probe envelope.

Original V03 exact road FIFO and opt-in KCMB are different physical models.
Read source/provenance from actual receipts. Never promote 3 preparations or
a bounded prefix into 9 completed 24h acceptance runs.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys

# Direct offline CLI execution must find the connected original project tools,
# not only the editable metroflow package.
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]

from metroflow.v1.v03_readiness import assess_v03_readiness
from metroflow.v1.kcmb_probe_envelope import affine_probe_speed_envelope
from metroflow.v1.chicago_observations import parse_observation_days
from tools.run_v1_local_acceptance import candidate_provenance
from metroflow.v1.native_engine import native_binary_provenance


def _read_json(path):
    return json.loads(Path(path).read_bytes())


def verify_prefix_replay(start:dict, fresh:dict, resumed:dict)->dict:
    """Strong local receipt comparison; validate actual bytes separately.

    Identical f64 replay checkpoints can only be asserted when the *original*
    native driver/matrix/binary and the exact 23k source snapshot agree, and
    a resumed 25.3k state matches a fresh 25.3k run byte-for-byte.
    """
    expected_case="valley_weekday_s7"
    if (start.get("case"),fresh.get("case"),resumed.get("case"))!=(
            expected_case,expected_case,expected_case):
        raise ValueError("replay original case identity differs")
    if start.get("status")!="EXECUTED_FOR_REVIEW" or (
        fresh.get("status")!="EXECUTED_FOR_REVIEW") or (
        resumed.get("status")!="EXECUTED_BOUNDED_PREFIX"):
        raise ValueError("replay original physical execution status invalid")
    if (start.get("simulated_s")!=23000 or
        fresh.get("simulated_s")!=25300 or
        resumed.get("completed_time_s")!=25300 or
        resumed.get("start_time_s")!=23000):
        raise ValueError("replay bounded physical prefix clock differs")
    for field in ("matrix_sha256","source_sha256","patch_sha256",
                  "candidate_source_sha256","native_binary_sha256","driver_identity"):
        values=(start.get(field),fresh.get(field),resumed.get(field))
        if len(set(values))!=1 or not isinstance(values[0],str) or len(values[0])!=64:
            raise ValueError("replay physical source/native identity differs: "+field)
    if start.get("final_checkpoint_sha256")!=resumed.get("source_checkpoint_sha256"):
        raise ValueError("replay source binary checkpoint digest differs")
    final_sha=fresh.get("final_checkpoint_sha256")
    if not isinstance(final_sha,str) or len(final_sha)!=64 or (
        final_sha!=resumed.get("last_valid_checkpoint_sha256")):
        raise ValueError("replay final binary checkpoint SHA mismatch")
    if not resumed.get("exact_binary_source_roundtrip"):
        raise ValueError("replay source checkpoint roundtrip identity not established")
    if resumed.get("physical_ledger_check")!="PASS_SCOPED" or (
        resumed.get("mass_ledger")!=fresh.get("report",{}).get("execution",{}).get("ledger")):
        raise ValueError("replay physical mass ledger mismatch")
    ledger=resumed["mass_ledger"]
    if not resumed.get("nonzero_physical_traffic_observed") or not (
        ledger.get("vehicles",{}).get("requested",0)>0 and
        ledger.get("vehicles",{}).get("released",0)>0):
        raise ValueError("replay physical nonzero traffic missing")
    if (resumed.get("full_day_24h_acceptance")!="NOT_RUN" or
        resumed.get("address_space_limit_bytes")!=8*1024**3):
        raise ValueError("replay release acceptance or original process resource contract changed")
    if resumed.get("resident_stock")!=100000 or (
        fresh.get("report",{}).get("calendar",{}).get("calendar",{}).get("resident_stock")!=100000):
        raise ValueError("replay original 100k source population not preserved")
    return {
        "status":"EXACT_REPLAY_BYTE_IDENTICAL_SCOPED",
        "case":expected_case,
        "source_start_s":23000,
        "simulated_s":25300.,
        "fresh_checkpoint_sha256":final_sha,
        "resumed_checkpoint_sha256":resumed["last_valid_checkpoint_sha256"],
        "source_checkpoint_sha256":start["final_checkpoint_sha256"],
        "ledger_equal":True,
        "nonzero_traffic_verified":True,
        "full_day_24h_accepted":False,
        "fresh_wall_seconds":fresh.get("wall_s"),
        "resumed_wall_seconds":resumed.get("elapsed_seconds"),
        "fresh_peak_rss_bytes":fresh.get("peak_rss_bytes"),
        "resumed_peak_rss_bytes":resumed.get("max_rss_bytes"),
        "native_binary_sha256":resumed["native_binary_sha256"],
        "driver_identity":resumed["driver_identity"],
    }


def build_evidence(root:Path,preparation_dir:Path)->dict:
    root=Path(root).resolve()
    prep=Path(preparation_dir).resolve()
    matrix_path=root/"scenarios/v1/release_matrix.json"
    matrix_bytes=matrix_path.read_bytes()
    matrix=_read_json(matrix_path)
    plan_path=root/"docs/v1/PLAN.json"
    plan=_read_json(plan_path)
    receipts=[]
    case_rows={}
    source_hashes=[]
    binary_hashes=[]
    matrix_hashes=[]
    for case in matrix["cases"]:
        name=case["id"]
        file=prep/(name+".prepare.json")
        if not file.exists():
            continue
        r=_read_json(file)
        if r.get("case")!=name:
            raise ValueError("original preparation source case differs")
        receipts.append(r)
        source_hashes.append(r.get("candidate_source_sha256"))
        binary_hashes.append(r.get("native_binary_sha256"))
        matrix_hashes.append(r.get("matrix_sha256"))
        cal=r.get("calendar",{})
        case_rows[name]={
            "status":r.get("status"),
            "resident_stock":cal.get("resident_stock"),
            "calendar_legs":cal.get("legs"),
            "calendar_persons":cal.get("persons"),
            "calendar_vehicles":cal.get("vehicles"),
            "calendar_cargo_kg":cal.get("cargo_kg"),
            "peak_rss_bytes":r.get("peak_rss_bytes"),
            "wall_s":r.get("wall_s"),
            "original_engine":r.get("engine_backend"),
            "native_storage_policy":r.get("native_storage",{}).get("policy"),
            "file_sha256":sha256(file.read_bytes()).hexdigest(),
            "source_candidate_sha256":r.get("candidate_source_sha256"),
            "native_binary_sha256":r.get("native_binary_sha256"),
        }
    matrix_digest=sha256(matrix_bytes).hexdigest()
    live_source=candidate_provenance()
    live_binary=native_binary_provenance()
    if live_source.get("status")!="MEASURED" or live_binary.get("status")!="MEASURED":
        raise ValueError("original whole-native source/binary content provenance unavailable")
    live_source_sha=live_source["source_sha256"]
    live_binary_sha=live_binary["sha256"]
    readiness=assess_v03_readiness(
        plan,matrix,matrix_sha256=matrix_digest,preparation_receipts=receipts,
        live_candidate_source_sha256=live_source_sha,
        live_native_binary_sha256=live_binary_sha)
    same_source=(len(receipts)==len(matrix["cases"]) and
                 len(set(source_hashes))==1 and source_hashes[0]==live_source_sha)
    same_binary=(len(receipts)==len(matrix["cases"]) and
                 len(set(binary_hashes))==1 and binary_hashes[0]==live_binary_sha)
    same_matrix=len(receipts)==len(matrix["cases"]) and len(set(matrix_hashes))==1 and (
        matrix_hashes[0]==matrix_digest)
    # The previously executed bus-class KCMB scenario used deliberately assumed
    # micro rates, speed U, population and boundary source. This NEW envelope
    # chooses NO sampling weights but remains conditional on those assumptions.
    old_model=root/"artifacts/kcmb_probe_20261119/CHICAGO_BUS_PROBE_SCENARIOS.json"
    old=_read_json(old_model)
    if old.get("city_observation_mechanism")!="UNKNOWN_NOT_CLAIMED_AFFINE":
        raise ValueError("prior CTA sampling uncertainty incorrectly resolved")
    envs={}
    for backend in ("python","rust"):
        b=old["backend_results"][backend]
        y=b["end_observed_mass_moment"]
        U=b["conditional_scenario_parameters"]["vmax_mps"]
        envs[backend]=affine_probe_speed_envelope(y,U)
    env=envs["python"]
    diff=max(abs(a-b) for a,b in zip(
        (env.min_speed_mps,env.max_speed_mps),
        (envs["rust"].min_speed_mps,envs["rust"].max_speed_mps)
    ))
    if diff>1e-9:
        raise ValueError("Python/Rust no-fit kinetic observation interval differs")
    source_manifest=_read_json(root/"artifacts/kcmb_field_20261119/SOURCE_MANIFEST.json")
    sources={}
    for item in source_manifest["source_requests"]:
        raw=(root/item["file"]).read_bytes()
        if sha256(raw).hexdigest()!=item["sha256"]:
            raise ValueError("actual Chicago historical source hash differs")
        sources[item["split"]]=(item["date_local"],json.loads(raw))
    d_cal,cal=sources["calibration"];d_hold,hold=sources["holdout"]
    obs=parse_observation_days(cal,hold,calibration_day=d_cal,holdout_day=d_hold)
    speeds=[v.speed_mps for v in obs.holdout]
    inside=sum(env.min_speed_mps-1e-12<=v<=env.max_speed_mps+1e-12 for v in speeds)
    prefix_result=None
    prefix_dir=root/"artifacts/kcmb_v03_physics_20261119/prefix"
    start_path=prefix_dir/"valley_weekday_s7.native_23000.json"
    fresh_path=prefix_dir/"valley_weekday_s7.native_fresh_25300.json"
    resumed_path=prefix_dir/"valley_weekday_s7.native_resumed_25300.json"
    if start_path.is_file() and fresh_path.is_file() and resumed_path.is_file():
        start_receipt=_read_json(start_path)
        fresh_receipt=_read_json(fresh_path)
        resumed_receipt=_read_json(resumed_path)
        prefix_result=verify_prefix_replay(
            start_receipt,fresh_receipt,resumed_receipt)
        if (not same_binary or not same_source or not same_matrix or
            prefix_result["native_binary_sha256"]!=live_binary_sha or
            fresh_receipt["matrix_sha256"]!=matrix_digest):
            prefix_result={
                "status":"BLOCKED_ORIGINAL_V03_PREPARATION_PROVENANCE_MISMATCH",
                "reason":"three-city preparation/source/native binary identity differs from running checkout",
                "full_day_24h_accepted":False,
                "local_checkpoint_bytes_verified":False,
            }
        if prefix_result["status"]!="BLOCKED_ORIGINAL_V03_PREPARATION_PROVENANCE_MISMATCH":
            checkpoint_files=(
                (prefix_dir/"valley_weekday_s7.native_23000.final.bin",
                 start_receipt["final_checkpoint_sha256"]),
                (prefix_dir/"valley_weekday_s7.native_fresh_25300.final.bin",
                 prefix_result["fresh_checkpoint_sha256"]),
                (prefix_dir/"valley_weekday_s7.native_resumed_25300.final.bin",
                 prefix_result["resumed_checkpoint_sha256"]),
            )
            available=all(path.is_file() for path,expected in checkpoint_files)
            if available:
                for path,expected in checkpoint_files:
                    if sha256(path.read_bytes()).hexdigest()!=expected:
                        raise ValueError("original V03 replay checkpoint bytes/identity not verified: "+path.name)
                prefix_result["local_checkpoint_bytes_verified"]=True
                prefix_result["local_checkpoint_files"]=tuple(str(path.relative_to(root))
                                                             for path,sha in checkpoint_files)
                prefix_result["binary_bytes_published_to_git"]=False
            else:
                # A Git clone intentionally omits oversized local native checkpoint
                # bytes; the committed receipt hashes alone do not independently
                # verify checkpoint file contents on this machine.
                prefix_result["status"]="REPLAY_RECEIPTS_MATCH_LOCAL_BINARY_BYTES_UNAVAILABLE"
                prefix_result["local_checkpoint_bytes_verified"]=False
                prefix_result["local_checkpoint_files"]=()
                prefix_result["binary_bytes_published_to_git"]=False
        prefix_result["source_receipt_sha256"]={
            "start":sha256(start_path.read_bytes()).hexdigest(),
            "fresh":sha256(fresh_path.read_bytes()).hexdigest(),
            "resumed":sha256(resumed_path.read_bytes()).hexdigest(),
        }
    return {
        "schema":"KCMB_NOFIT_ORIGINAL_V03_READINESS_SCOPED_V1",
        "plan_source_sha256":sha256(plan_path.read_bytes()).hexdigest(),
        "matrix_source_sha256":matrix_digest,
        "readiness":readiness,
        "case_preparations":case_rows,
        "preparation_source_consistency":{
            "live_candidate_source_sha256":live_source_sha,
            "live_native_binary_sha256":live_binary_sha,
            "same_native_binary":same_binary,
            "same_candidate_source":same_source,
            "same_release_matrix":same_matrix,
            "joint_3city_preparation_eligible":bool(
                same_binary and same_source and same_matrix and
                readiness["v03"]["calendar_preparation_verified"]==len(matrix["cases"])),
        },
        "physical_prefix_continuation":prefix_result,
        "hypothetical_probe_observation_envelope":{
            "min_speed_mps":env.min_speed_mps,
            "max_speed_mps":env.max_speed_mps,
            "vertex_speeds_mps":env.vertex_speeds_mps,
            "population_mean_speed_mps":env.population_mean_speed_mps,
            "all_affine_weights_admissible_no_fit":True,
            "source_model_parameters_are_assumed":True,
            "model_sampling_rule_verified_by_city":False,
            "python_rust_max_endpoint_discrepancy_mps":diff,
            "real_holdout_bins_within_envelope":inside,
            "real_holdout_total_bins":len(speeds),
            "scientific_limit":"very broad conditional band is not empirical predictive validation",
            "parent_scenario_source_sha256":sha256(old_model.read_bytes()).hexdigest(),
        },
        "v03_original_physics_accepted":False,
        "original_24h_completed_runs":0,
        "host_memory_reference_is_64gib":False,
        "no_new_fitted_physical_or_probe_coefficients":True,
        "execution_limitation":"prepared full calendars and bounded original-physics prefix only, no 24h campaign",
    }


def main()->None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prep-dir",required=True)
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    root=Path(__file__).resolve().parents[2]
    prep=Path(args.prep_dir)
    prep=prep if prep.is_absolute() else root/prep
    result=build_evidence(root,prep)
    dest=Path(args.output)
    dest=dest if dest.is_absolute() else root/dest
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
    r=result["readiness"]["v03"]
    print(json.dumps({
        "project_dag":str(result["readiness"]["dag"]["completed"])+"/"+str(result["readiness"]["dag"]["total"]),
        "original_prepared":str(r["calendar_preparation_verified"])+"/"+str(r["calendar_preparation_total"]),
        "full_days":str(r["completed_full_day_runs"])+"/"+str(r["required_full_day_runs"]),
        "consistent_native_preparation":result["preparation_source_consistency"]["joint_3city_preparation_eligible"],
        "nofit_conditional_mps":[result["hypothetical_probe_observation_envelope"]["min_speed_mps"],
                                result["hypothetical_probe_observation_envelope"]["max_speed_mps"]],
        "actual_original_prefix":result["physical_prefix_continuation"]["status"] if result["physical_prefix_continuation"] else "NOT_RUN",
        "V03":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
