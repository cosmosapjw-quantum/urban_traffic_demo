#!/usr/bin/env python3
"""Bounded exact V03 25600->25650 replay for old vs Arc native binaries.

Uses original source checkouts and original driver. Writes ONLY evidence in
the isolated research worktree. Both runs start from 866763962-byte original
native 25600 checkpoint whose SHA is identical between baseline and Arc.
Original 100k population, 10s clock, 8 GiB process and 86400s release matrix
remain frozen; 25650s is NOT V03 full-day acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time


def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as src:
        for block in iter(lambda:src.read(4*1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root",required=True,type=Path)
    ap.add_argument("--variant",required=True,choices=["old","arc"])
    ap.add_argument("--old-receipt",required=True,type=Path)
    ap.add_argument("--arc-bridge",required=True,type=Path)
    ap.add_argument("--input-checkpoint",required=True,type=Path)
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--checkpoint-out",required=True,type=Path)
    args=ap.parse_args()
    root=args.root.resolve()
    sys.path[:0]=[str(root),str(root/"src")]
    from tools.run_v1_local_acceptance import prepare,candidate_provenance,_ledger_error
    from metroflow.v1.native_engine import native_binary_provenance

    raw=(root/"scenarios/v1/release_matrix.json").read_bytes()
    matrix=json.loads(raw)
    source_matrix_sha=hashlib.sha256(raw).hexdigest()
    old=json.loads(args.old_receipt.read_bytes())
    arc=json.loads(args.arc_bridge.read_bytes())
    case=next((c for c in matrix["cases"] if c["id"]=="valley_weekday_s7"),None)
    if not case or matrix["population"]!=100000 or matrix["horizon_s"]!=86400:
        raise ValueError("original 100k/86400s release matrix changed")
    if (old["case"]!="valley_weekday_s7" or
        old["completed_time_s"]!=25600 or
        old["matrix_sha256"]!=source_matrix_sha):
        raise ValueError("incorrect original source 25600 receipt")
    # Original continuation receipts need not have an explicit step_s:
    # the original native driver identity pins the canonical f64 clock.
    if old.get("last_valid_checkpoint_sha256")!=arc.get("new_arc_checkpoint_sha256"):
        raise ValueError("original and Arc at 25600 checkpoints are not same bytes")
    incoming_sha=digest(args.input_checkpoint)
    if incoming_sha!=old["last_valid_checkpoint_sha256"]:
        raise ValueError("actual source checkpoint bytes SHA mismatch")
    if (arc["source_timestamp"]!=25300 or arc["destination_timestamp"]!=25600 or
        arc["status"]!="BYTE_IDENTICAL_SCOPED" or
        arc["matrix_sha256"]!=source_matrix_sha or
        arc["full_checkpoint_byte_equal"] is not True):
        raise ValueError("candidate Arc receipt does not bind initial clock/matrix")
    source=candidate_provenance()
    binary=native_binary_provenance()
    if source.get("status")!="MEASURED" or source.get("source_dirty") is not False or binary.get("status")!="MEASURED":
        raise ValueError("candidate source/native unmeasurable or dirty")
    expected_src=(old["candidate_source_sha256"] if args.variant=="old" else
                  arc["current_arc_candidate_source_sha256"])
    expected_native=(old["native_binary_sha256"] if args.variant=="old" else
                     arc["new_arc_binary_sha256"])
    if source["source_sha256"]!=expected_src or binary["sha256"]!=expected_native:
        raise ValueError("source/native executable provenance differs for "+args.variant)
    os.environ.update(
        METROFLOW_V1_ENGINE_BACKEND="rust_whole",
        METROFLOW_V1_NATIVE_THREADS="1",
        METROFLOW_V1_STORAGE_POLICY="bounded_bytes_v1",
    )
    limit=matrix["limits"]["peak_rss_bytes"]
    soft,hard=resource.getrlimit(resource.RLIMIT_AS)
    if soft!=resource.RLIM_INFINITY:
        limit=min(limit,soft)
    resource.setrlimit(resource.RLIMIT_AS,(limit,hard))
    start_wall=time.perf_counter()
    runner,meta=prepare(case,matrix,10.0)
    if runner.identity!=old["driver_identity"]:
        raise ValueError("original driver identity differs")
    if meta["source_sha256"]!=old["source_sha256"] or meta["patch_sha256"]!=old["patch_sha256"]:
        raise ValueError("source demand/patch identity differs")
    state=runner.load(args.input_checkpoint)
    if state.time_s!=25600:
        raise ValueError("checkpoint time not 25600")
    begin=runner.report(state)
    if _ledger_error(begin,25600,population=100000) is not None:
        raise ValueError("restored original physical mass ledger failed")
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.checkpoint_out.parent.mkdir(parents=True,exist_ok=True)
    tmp=args.checkpoint_out.with_suffix(".roundtrip.tmp")
    runner.save(tmp,state)
    roundtrip=digest(tmp)
    tmp.unlink()
    if roundtrip!=incoming_sha:
        raise ValueError("same physical checkpoint failed byte roundtrip under this binary")
    failure=None
    newstate=None
    try:
        newstate=runner.advance(state,25650.0)
        if newstate.time_s!=25650.0:
            raise ValueError("advance did not reach 25650")
        report=runner.report(newstate)
        err=_ledger_error(report,25650,population=100000)
        if err is not None:
            raise ValueError("original physics ledger failed: "+err)
        runner.save(args.checkpoint_out,newstate)
        endsha=digest(args.checkpoint_out)
        bytes_out=args.checkpoint_out.stat().st_size
        status="EXECUTED_BOUNDED_PHYSICAL_PREFIX"
    except Exception as exc:
        status="FAILED_"+type(exc).__name__
        failure=str(exc)
        report=None
        endsha=None
        bytes_out=None
    wall=time.perf_counter()-start_wall
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    result={
        "schema":"V03_ORIGINAL_25600_TO_25650_EXACT_SOURCE_REPLAY_20261120_V1",
        "variant":args.variant,
        "status":status,
        "error":failure,
        "source_root":str(root),
        "case":"valley_weekday_s7",
        "resident_stock":100000,
        "initial_time_s":25600.0,
        "target_time_s":25650.0,
        "final_time_s":newstate.time_s if newstate is not None else None,
        "source_sha256":source["source_sha256"],
        "native_binary_sha256":binary["sha256"],
        "matrix_sha256":source_matrix_sha,
        "driver_identity":runner.identity,
        "source_checkpoint_sha256":incoming_sha,
        "source_roundtrip_byte_identical":True,
        "final_checkpoint_sha256":endsha,
        "final_checkpoint_bytes":bytes_out,
        "mass_ledger":report["execution"]["ledger"] if report is not None else None,
        "full_report_execution":report["execution"] if report is not None else None,
        "elapsed_s":wall,
        "process_peak_rss_bytes":rss,
        "process_address_space_limit_bytes":limit,
        "original_24h_accepted":False,
        "original_release_runs_completed":0,
        "new_fitted_physical_parameters":[],
        "created_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"variant":args.variant,"status":status,"final_time":result["final_time_s"],
                      "elapsed_s":round(wall,3),"peak_rss_gib":round(rss/1024**3,3),
                      "final_checkpoint_mb":round(bytes_out/1024**2,2) if bytes_out is not None else None,
                      "checkpoint_sha":endsha,"error":failure},sort_keys=True),flush=True)
    if failure:
        raise RuntimeError("bounded original source V03 "+args.variant+" could not complete 25650: "+failure)


if __name__=="__main__":
    main()
