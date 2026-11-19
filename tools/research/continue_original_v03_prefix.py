#!/usr/bin/env python3
"""Bounded re-entry to ORIGINAL exact V03 native FIFO physics from a real checkpoint.

The existing full 100k calendar is independently reconstructed from the same
source. Binary checkpoint and original physical driver identity are verified
before advancing. RLIMIT_AS=8GiB remains. This does not grant full-day acceptance
or change the original 21-node DAG, release matrix, model or fitted coefficients.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import os
import resource
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
from tools.run_v1_local_acceptance import prepare, candidate_provenance, _ledger_error, file_sha256
from metroflow.v1.native_engine import native_binary_provenance
from metroflow.active_suffix.common import BudgetExceeded


def canonical_step_seconds(value):
    """Preserve argparse(float) native static JSON identity in fresh processes."""
    if isinstance(value,bool) or not isinstance(value,(int,float)):
        raise ValueError("positive finite physical step seconds required")
    dt=float(value)
    if not math.isfinite(dt) or dt<=0:
        raise ValueError("positive finite physical step seconds required")
    return dt


def validate_start_binding(
    row,
    *,
    case: str,
    matrix_sha: str,
    driver_identity: str,
    native_binary_sha: str,
    candidate_source_sha: str,
    expected_time_s: float,
) -> str:
    if not isinstance(row,dict) or row.get("status")!="EXECUTED_FOR_REVIEW" or (
        row.get("engine_backend")!="rust_whole"):
        raise ValueError("source prefix execution status/backend binding invalid")
    for name,expected in (
        ("case",case),
        ("matrix_sha256",matrix_sha),
        ("driver_identity",driver_identity),
        ("native_binary_sha256",native_binary_sha),
        ("candidate_source_sha256",candidate_source_sha),
    ):
        if row.get(name)!=expected:
            raise ValueError("source/native prefix binding differs: "+name)
    if row.get("address_space_limit_bytes")!=8*1024**3:
        raise ValueError("original 8GiB process resource binding differs")
    if row.get("step_s")!=10 or row.get("horizon_s")!=expected_time_s or (
        row.get("simulated_s")!=expected_time_s):
        raise ValueError("prefix time-grid/physical clock binding differs")
    if row.get("candidate",{}).get("source_dirty") is not False:
        raise ValueError("prefix source provenance dirty or not verified")
    if not isinstance(row.get("final_checkpoint_sha256"),str) or (
        len(row["final_checkpoint_sha256"])!=64):
        raise ValueError("prefix binary checkpoint source SHA missing")
    if row.get("report",{}).get("calendar",{}).get("calendar",{}).get("resident_stock")!=100000:
        raise ValueError("source prefix does not preserve 100k resident calendar")
    return "ORIGINAL_V03_PREFIX_BINDING_VERIFIED"


def bounded_sweep_target_seconds(start_s:float, end_s:float, full_horizon_s:float)->float:
    """Strict research-only 25,600s extension, not a V03 release horizon."""
    if (not math.isfinite(start_s) or not math.isfinite(end_s) or
        not math.isfinite(full_horizon_s) or not start_s<end_s<=25600 or
        end_s%10!=0 or end_s>=full_horizon_s):
        raise ValueError("bounded original V03 sweep prefix target invalid (max 25600s)")
    return end_s


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case",required=True)
    ap.add_argument("--start-receipt",required=True,type=Path)
    ap.add_argument("--start-checkpoint",required=True,type=Path)
    ap.add_argument("--until-s",required=True,type=float)
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--checkpoint-out",required=True,type=Path)
    args=ap.parse_args()
    src=json.loads(args.start_receipt.read_bytes())
    matrix_path=ROOT/"scenarios/v1/release_matrix.json"
    raw=matrix_path.read_bytes()
    matrix_sha=hashlib.sha256(raw).hexdigest()
    matrix=json.loads(raw)
    case=next((c for c in matrix["cases"] if c["id"]==args.case),None)
    if case is None:
        raise ValueError("case absent from original release matrix")
    t0=float(src["simulated_s"])
    bounded_sweep_target_seconds(t0,args.until_s,matrix["horizon_s"])
    source_sha=candidate_provenance()
    if source_sha["status"]!="MEASURED":
        raise ValueError("native source provenance could not be measured")
    native_sha=native_binary_provenance()
    os.environ["METROFLOW_V1_ENGINE_BACKEND"]="rust_whole"
    os.environ["METROFLOW_V1_NATIVE_THREADS"]="1"
    os.environ["METROFLOW_V1_STORAGE_POLICY"]="bounded_bytes_v1"
    max_bytes=matrix["limits"]["peak_rss_bytes"]
    current_soft,current_hard=resource.getrlimit(resource.RLIMIT_AS)
    if current_soft!=resource.RLIM_INFINITY:
        max_bytes=min(max_bytes,current_soft)
    resource.setrlimit(resource.RLIMIT_AS,(max_bytes,current_hard))
    start=time.perf_counter()
    driver,meta=prepare(case,matrix,canonical_step_seconds(10))
    expected_identity=driver.identity
    status=validate_start_binding(
        src,case=case["id"],matrix_sha=matrix_sha,
        driver_identity=expected_identity,
        native_binary_sha=native_sha["sha256"],
        candidate_source_sha=source_sha["source_sha256"],
        expected_time_s=t0,
    )
    prev_digest=file_sha256(args.start_checkpoint)
    if prev_digest!=src["final_checkpoint_sha256"]:
        raise ValueError("original binary prefix checkpoint SHA mismatch")
    previous=driver.load(args.start_checkpoint)
    if previous.time_s!=t0:
        raise ValueError("resumed physical state timestamp differs")
    old_report=driver.report(previous)
    if _ledger_error(old_report,t0,population=100000) is not None:
        raise ValueError("initial restored physical mass ledger is invalid")
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.checkpoint_out.parent.mkdir(parents=True,exist_ok=True)
    # Lossless binary roundtrip on the exact original source. Avoid retaining
    # a second giant checkpoint file: stage in output directory, then unlink.
    tmp=args.checkpoint_out.with_suffix(".roundtrip_tmp.bin")
    driver.save(tmp,previous)
    roundtrip_same=file_sha256(tmp)==prev_digest
    tmp.unlink(missing_ok=True)
    if not roundtrip_same:
        raise ValueError("restored original native state differs byte-for-byte")
    verdict="EXECUTED_BOUNDED_PREFIX"
    reason=None
    try:
        nxt=driver.advance(previous,args.until_s)
    except BudgetExceeded as exc:
        verdict="BLOCKED_RESOURCE"
        reason=str(exc)
        nxt=getattr(exc,"checkpoint",None)
        if nxt is None:
            raise
    report=driver.report(nxt)
    error=_ledger_error(report,nxt.time_s,population=100000)
    if error is not None:
        raise ValueError("continuation physics ledger invalid: "+error)
    driver.save(args.checkpoint_out,nxt)
    ledger=report["execution"]["ledger"]
    active_traffic=any(ledger[k]["requested"]>0 or ledger[k]["released"]>0 for k in (
        "persons","vehicles","cargo_kg"))
    elapsed=time.perf_counter()-start
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    receipt={
      "status":verdict,"source_binding":status,"case":case["id"],
      "parent_receipt_path":str(args.start_receipt),
      "source_checkpoint_path":str(args.start_checkpoint),
      "original_full_calendar_legs":driver.plan.totals()["legs"],
      "resident_stock":driver.plan.totals()["resident_stock"],
      "matrix_sha256":matrix_sha,"source_sha256":meta["source_sha256"],
      "patch_sha256":meta["patch_sha256"],
      "candidate_source_sha256":source_sha["source_sha256"],
      "native_binary_sha256":native_sha["sha256"],
      "driver_identity":driver.identity,
      "start_time_s":t0,"intended_end_time_s":args.until_s,
      "completed_time_s":nxt.time_s,
      "whole_native_stage":True,
      "source_checkpoint_bytes":args.start_checkpoint.stat().st_size,
      "source_checkpoint_sha256":prev_digest,
      "exact_binary_source_roundtrip":roundtrip_same,
      "last_valid_checkpoint":str(args.checkpoint_out),
      "last_valid_checkpoint_sha256":file_sha256(args.checkpoint_out),
      "last_valid_checkpoint_bytes":args.checkpoint_out.stat().st_size,
      "mass_ledger":ledger,
      "nonzero_physical_traffic_observed":active_traffic,
      "physical_ledger_check":"PASS_SCOPED",
      "elapsed_seconds":elapsed,
      "max_rss_bytes":rss,
      "address_space_limit_bytes":max_bytes,
      "block_reason":reason,
      "full_day_24h_acceptance":"NOT_RUN",
      "source_100k_population_reduced":False,
      "code_or_numerical_tolerance_modified":False,
    }
    args.out.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
      "case":case["id"],
      "status":verdict,
      "simulated_s":nxt.time_s,
      "nonzero_traffic":active_traffic,
      "max_rss_gib":round(rss/1024**3,3),
      "elapsed_s":round(elapsed,2),
      "checkpoint_byte_identity":roundtrip_same,
      "full_day":False,
    }),flush=True)


if __name__=="__main__":
    main()
