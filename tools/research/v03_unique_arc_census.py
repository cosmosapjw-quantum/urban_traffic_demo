#!/usr/bin/env python3
"""Source-bound diagnostic census of exact original V03 100k native snapshots.

Only calls read-only debug_state after original complete checkpoint load.
Neither physical transition, native budget, traffic coefficient nor source
calendar is changed. Large reference checkpoint binaries remain local only.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
from tools.run_v1_local_acceptance import prepare,candidate_provenance,_ledger_error
from metroflow.v1.native_engine import native_binary_provenance

PREVIOUS=Path("/home/cosmosapjw/worktrees/urban-traffic-v03-service-stream-20261120")
ART=ROOT/"artifacts/v03_fifo_unique_accounting_20261120"


def digest(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(4*1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def run()->dict:
    matrix_path=ROOT/"scenarios/v1/release_matrix.json"
    matrix_bytes=matrix_path.read_bytes()
    matrix=json.loads(matrix_bytes)
    prev_matrix=PREVIOUS/"scenarios/v1/release_matrix.json"
    if matrix_bytes!=prev_matrix.read_bytes():
        raise ValueError("original V03 release matrix changed")
    if matrix["population"]!=100000 or matrix["horizon_s"]!=86400 or (
       matrix["limits"]["peak_rss_bytes"]!=8*1024**3):
        raise ValueError("original V03 100k input/day/resource cap missing")
    case=next(c for c in matrix["cases"] if c["id"]=="valley_weekday_s7")
    live_src=candidate_provenance()
    live_native=native_binary_provenance()
    if (live_src.get("status")!="MEASURED" or
        live_src.get("source_dirty") is not False or
        live_native.get("status")!="MEASURED"):
        raise ValueError("current source/native SHA unverified")
    os.environ.update(
        METROFLOW_V1_ENGINE_BACKEND="rust_whole",
        METROFLOW_V1_NATIVE_THREADS="1",
        METROFLOW_V1_STORAGE_POLICY="bounded_bytes_v1",
    )
    limit=matrix["limits"]["peak_rss_bytes"]
    soft,hard=resource.getrlimit(resource.RLIMIT_AS)
    if soft!=resource.RLIM_INFINITY:
        limit=min(soft,limit)
    resource.setrlimit(resource.RLIMIT_AS,(limit,hard))
    start=time.perf_counter()
    driver,meta=prepare(case,matrix,10.0)
    out={}
    for tm in (25300,25600):
        suffix="native_stream_25300" if tm==25300 else "native_arc_25600"
        folder="prefix" if tm==25300 else "arc_prefix"
        root=PREVIOUS/"artifacts/v03_fifo_service_stream_20261120"/folder
        receipt_file=root/("valley_weekday_s7."+suffix+".json")
        checkpoint=root/("valley_weekday_s7."+suffix+".final.bin")
        if tm==25600:
            receipt_file=root/"C9_ARC_PHYSICAL_REPLAY.json"
        ref=json.loads(receipt_file.read_bytes())
        source_sha=(ref["final_checkpoint_sha256"] if tm==25300 else
                    ref["new_arc_checkpoint_sha256"])
        if digest(checkpoint)!=source_sha:
            raise ValueError("real source checkpoint digest differs")
        if tm==25300:
            expected_driver=ref["driver_identity"]
            if driver.identity!=expected_driver:
                raise ValueError("physical driver identity mismatch")
            if meta["source_sha256"]!=ref["source_sha256"] or (
                meta["patch_sha256"]!=ref["patch_sha256"]):
                raise ValueError("physical source/patch changed")
        snap=driver.load(checkpoint)
        if snap.time_s!=tm:
            raise ValueError("original snapshot time mismatch")
        err=_ledger_error(driver.report(snap),tm,population=100000)
        if err is not None:
            raise ValueError("loaded original physical mass ledger failed: "+err)
        debug=driver.debug_state(snap)
        road=debug["road"]
        census=road["arc_backing_census"]
        if census["owner_count"]!=road["cell_packets"]+road["pending_packets"]:
            raise ValueError("arc census did not enumerate all original road packet owners")
        if (census["owner_payload_bytes"]<
            census["unique_payload_bytes"] or
            census["owner_payload_bytes"]-census["unique_payload_bytes"]!=
            census["duplicate_payload_bytes"]):
            raise ValueError("identity math for actual Arc backing invalid")
        if census["owner_payload_bytes"]>road["vector_capacity_bytes"]:
            raise ValueError("source debug stats cannot bound reported capacity")
        out[str(tm)]={
            "simulated_time_s":tm,
            "original_source_checkpoint_sha256":source_sha,
            "original_checkpoint_bytes":checkpoint.stat().st_size,
            "original_full_calendar_residents":100000,
            "source_driver_identity":driver.identity,
            "road_packet_rows":road["cell_parts"]+road["pending_parts"],
            "road_packet_count":road["cell_packets"]+road["pending_packets"],
            "road_vector_capacity_bytes_per_owner":road["vector_capacity_bytes"],
            "arc_backing_census":census,
            "seconds_elapsed_since_start":time.perf_counter()-start,
        }
        print("ARC_CENSUS",tm,json.dumps(out[str(tm)]["arc_backing_census"],sort_keys=True),
              "physical_rows",out[str(tm)]["road_packet_rows"],flush=True)
    result={
      "schema":"V03_100K_UNIQUE_ARC_BACKING_READONLY_CENSUS_20261120_V1",
      "current_source_sha256":live_src["source_sha256"],
      "current_native_sha256":live_native["sha256"],
      "original_release_matrix_sha256":hashlib.sha256(matrix_bytes).hexdigest(),
      "original_physical_case":"valley_weekday_s7",
      "original_native_internal_budget_bytes":5242806391,
      "process_address_space_limit_bytes":limit,
      "observed_state_times_s":[25300,25600],
      "measurements":out,
      "claim_scope":"within each one loaded RoadState, no simultaneous input/current/candidate union census",
      "original_model_physics_advanced":False,
      "road_work_budget_modified":False,
      "unique_arc_control_96bytes_estimate":"DIAGNOSTIC_ALLOWANCE_NOT_RSS_UPPER_BOUND",
      "original_24h_completed_runs":0,
      "original_24h_required_runs":9,
      "elapsed_total_s":time.perf_counter()-start,
    }
    ART.mkdir(parents=True,exist_ok=True)
    dest=ART/"C2_ACTUAL_25600_BACKING_CENSUS.json"
    dest.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+"\n")
    print("READONLY_CENSUS_COMPLETED",dest,"ELAPSED",result["elapsed_total_s"])
    return result

if __name__=="__main__":
    run()
