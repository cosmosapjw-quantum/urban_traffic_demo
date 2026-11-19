#!/usr/bin/env python3
"""Original-old/native versus indexed-sweep V03 exact 25,600s checkpoint oracle.

Execute THIS SCRIPT with the PARENT worktree's Python venv and old Rust native
extension. The original worktree remains read-only; all output stays in the
sweep research worktree. Full 86,400s x9 release remains NOT_RUN. The old and
new native binaries intentionally have different content digests.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time


def digest(path:Path)->str:
    sha=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4*1024*1024),b""):
            sha.update(block)
    return sha.hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--old-root",required=True,type=Path)
    ap.add_argument("--new-root",required=True,type=Path)
    ap.add_argument("--out",required=True,type=Path)
    args=ap.parse_args()
    old=args.old_root.resolve()
    new=args.new_root.resolve()
    if not old.is_dir() or not new.is_dir():
        raise ValueError("old/new source roots absent")
    sys.path.insert(0,str(old))
    sys.path.insert(1,str(old/"src"))
    os.environ["METROFLOW_V1_ENGINE_BACKEND"]="rust_whole"
    os.environ["METROFLOW_V1_NATIVE_THREADS"]="1"
    os.environ["METROFLOW_V1_STORAGE_POLICY"]="bounded_bytes_v1"
    from tools.run_v1_local_acceptance import prepare,candidate_provenance,_ledger_error
    from metroflow.v1.native_engine import native_binary_provenance

    matrix_bytes=(old/"scenarios/v1/release_matrix.json").read_bytes()
    new_matrix_bytes=(new/"scenarios/v1/release_matrix.json").read_bytes()
    if matrix_bytes!=new_matrix_bytes:
        raise ValueError("original and candidate source matrix bytes differ")
    matrix=json.loads(matrix_bytes)
    sha_matrix=hashlib.sha256(matrix_bytes).hexdigest()
    case=next(x for x in matrix["cases"] if x["id"]=="valley_weekday_s7")
    old_prefix=old/"artifacts/kcmb_v03_physics_20261119/prefix"
    new_prefix=new/"artifacts/v03_fifo_interval_sweep_20261119/prefix"
    old_start_receipt=json.loads((old_prefix/"valley_weekday_s7.native_fresh_25300.json").read_bytes())
    new_stop_receipt=json.loads((new_prefix/"valley_weekday_s7.native_sweep_25600.json").read_bytes())
    if old_start_receipt["simulated_s"]!=25300 or (
        new_stop_receipt["completed_time_s"]!=25600):
        raise ValueError("source/target physical clocks differ")
    if old_start_receipt["matrix_sha256"]!=sha_matrix or (
        new_stop_receipt["matrix_sha256"]!=sha_matrix):
        raise ValueError("source release matrix identity invalid")
    old_binary=native_binary_provenance()
    old_source=candidate_provenance()
    if old_binary["sha256"]!=old_start_receipt["native_binary_sha256"]:
        raise ValueError("old Python environment did not load OLD reference native binary")
    if old_source["source_sha256"]!=old_start_receipt["candidate_source_sha256"]:
        raise ValueError("old source code no longer matches original prepared model")
    if new_stop_receipt["native_binary_sha256"]==old_binary["sha256"]:
        raise ValueError("candidate optimized native binary unexpectedly same as old")
    if old_start_receipt["source_sha256"]!=new_stop_receipt["source_sha256"]:
        raise ValueError("physical initial source changed between versions")
    limit=matrix["limits"]["peak_rss_bytes"]
    soft,hard=resource.getrlimit(resource.RLIMIT_AS)
    if soft!=resource.RLIM_INFINITY:
        limit=min(limit,soft)
    resource.setrlimit(resource.RLIMIT_AS,(limit,hard))
    start=time.perf_counter()
    driver,meta=prepare(case,matrix,10.0)
    if driver.identity!=old_start_receipt["driver_identity"] or (
        driver.identity!=new_stop_receipt["driver_identity"]):
        raise ValueError("old and new native physical driver identity differs")
    input_checkpoint=old_prefix/"valley_weekday_s7.native_fresh_25300.final.bin"
    if digest(input_checkpoint)!=old_start_receipt["final_checkpoint_sha256"]:
        raise ValueError("old 25,300s checkpoint file bytes mismatch source receipt")
    state=driver.load(input_checkpoint)
    if state.time_s!=25300:
        raise ValueError("old input checkpoint physical timestamp differs")
    initial_report=driver.report(state)
    initial_error=_ledger_error(initial_report,state.time_s,population=100000)
    if initial_error is not None:
        raise ValueError("source original physical mass ledger invalid: "+initial_error)
    next_state=driver.advance(state,25600.)
    report=driver.report(next_state)
    error=_ledger_error(report,next_state.time_s,population=100000)
    if error is not None:
        raise ValueError("old original 25,600s physical mass ledger invalid: "+error)
    if next_state.time_s!=25600.:
        raise ValueError("old source physical clock did not reach target")
    elapsed=time.perf_counter()-start
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    args.out.parent.mkdir(parents=True,exist_ok=True)
    temp=args.out.with_suffix(".reference_tmp.bin")
    driver.save(temp,next_state)
    final_digest=digest(temp)
    final_size=temp.stat().st_size
    temp.unlink()
    new_digest=new_stop_receipt["last_valid_checkpoint_sha256"]
    ledger_equal=(report["execution"]["ledger"]==new_stop_receipt["mass_ledger"])
    binary_equal=(final_digest==new_digest)
    result={
       "schema":"V03_ORIGINAL_VS_INDEXED_SWEEP_25600_V1",
       "case":"valley_weekday_s7",
       "original_reference_root":str(old),
       "candidate_research_root":str(new),
       "reference_start_time_s":25300.,
       "reference_end_time_s":25600.,
       "native_old_sha256":old_binary["sha256"],
       "native_candidate_sha256":new_stop_receipt["native_binary_sha256"],
       "matrix_sha256":sha_matrix,
       "old_candidate_source_sha256":old_source["source_sha256"],
       "new_candidate_source_sha256":new_stop_receipt["candidate_source_sha256"],
       "physical_source_sha256":old_start_receipt["source_sha256"],
       "driver_identity":driver.identity,
       "old_reference_output_checkpoint_sha256":final_digest,
       "new_sweep_checkpoint_sha256":new_digest,
       "old_reference_checkpoint_bytes":final_size,
       "new_sweep_checkpoint_bytes":new_stop_receipt["last_valid_checkpoint_bytes"],
       "physical_ledger_exact_equal":ledger_equal,
       "byte_identical_native_checkpoint":binary_equal,
       "old_original_elapsed_seconds":elapsed,
       "new_candidate_elapsed_seconds":new_stop_receipt["elapsed_seconds"],
       "old_original_peak_rss_bytes":rss,
       "new_candidate_peak_rss_bytes":new_stop_receipt["max_rss_bytes"],
       "original_process_address_space_limit_bytes":limit,
       "original_full_day_accepted":False,
       "whole_city_100k_population_preserved":True,
       "reference_binary_saved_to_git":False,
       "status":"BIT_IDENTICAL_CONGESTED_PREFIX" if binary_equal and ledger_equal else "CONGESTED_PREFIX_MISMATCH",
       "created_at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
      "status":result["status"],
      "actual_simulated_s":next_state.time_s,
      "old_elapsed_s":round(elapsed,2),
      "new_elapsed_s":round(new_stop_receipt["elapsed_seconds"],2),
      "old_gib":round(rss/1024**3,3),
      "new_gib":round(new_stop_receipt["max_rss_bytes"]/1024**3,3),
      "checkpoint_sha_match":binary_equal,
      "ledger_match":ledger_equal
    },sort_keys=True),flush=True)
    if not binary_equal or not ledger_equal:
        raise ArithmeticError("original V03 congestion checkpoint differs under interval event sweep")


if __name__=="__main__":
    main()
