#!/usr/bin/env python3
"""Original V03 Arc-native restore and replay of source-verified 25,300s state.

This is a bounded ORIGINAL physics experiment, not V03 full-day acceptance.
The pre-Arc checkpoint is consumed ONLY after exact binary SHA/physical source
checks. The new native executable uses the original matrix, physical driver,
fixed 10s step, 8GiB process limit, and exact marked FIFO state.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
from tools.run_v1_local_acceptance import prepare,candidate_provenance,_ledger_error
from metroflow.v1.native_engine import native_binary_provenance

BASE="artifacts/v03_fifo_service_stream_20261120"
CASE="valley_weekday_s7"


def digest(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as src:
        for piece in iter(lambda:src.read(4*1024*1024),b""):
            h.update(piece)
    return h.hexdigest()


def run()->dict:
    path=ROOT/BASE
    oldprefix=path/"prefix"
    newprefix=path/"arc_prefix"
    newprefix.mkdir(parents=True,exist_ok=True)
    source=oldprefix/"valley_weekday_s7.native_stream_25300.final.bin"
    old_start=json.loads((oldprefix/"valley_weekday_s7.native_stream_25300.json").read_bytes())
    old_end=json.loads((oldprefix/"valley_weekday_s7.native_stream_25600.json").read_bytes())
    matrix_file=ROOT/"scenarios/v1/release_matrix.json"
    data=matrix_file.read_bytes()
    matrix=json.loads(data)
    case=next((x for x in matrix["cases"] if x["id"]==CASE),None)
    if case is None or matrix["population"]!=100000 or matrix["horizon_s"]!=86400:
        raise ValueError("original source-bound 100k matrix contract missing")
    if old_start["simulated_s"]!=25300 or old_end["completed_time_s"]!=25600:
        raise ValueError("original reference time window changed")
    if old_start["final_checkpoint_sha256"]!=digest(source):
        raise ValueError("source binary checkpoint bytes mismatched original receipt")
    if old_start["final_checkpoint_sha256"]!=old_end["source_checkpoint_sha256"]:
        raise ValueError("source/checkpoint lineage mismatch")
    if old_start["matrix_sha256"]!=digest(matrix_file) or (
        old_end["matrix_sha256"]!=digest(matrix_file)):
        raise ValueError("original release matrix bytes mismatch")
    current_src=candidate_provenance()
    current_bin=native_binary_provenance()
    if current_src.get("status")!="MEASURED" or current_src.get("source_dirty") is not False or (
        current_bin.get("status")!="MEASURED"):
        raise ValueError("current candidate/native source is not measured/clean")
    if current_bin["sha256"]==old_start["native_binary_sha256"]:
        raise ValueError("Arc candidate binary unexpectedly equal to pre-Arc binary")
    os.environ.update(
        METROFLOW_V1_ENGINE_BACKEND="rust_whole",
        METROFLOW_V1_NATIVE_THREADS="1",
        METROFLOW_V1_STORAGE_POLICY="bounded_bytes_v1",
    )
    limit=matrix["limits"]["peak_rss_bytes"]
    old_soft,hard=resource.getrlimit(resource.RLIMIT_AS)
    if old_soft!=resource.RLIM_INFINITY:
        limit=min(limit,old_soft)
    resource.setrlimit(resource.RLIMIT_AS,(limit,hard))
    start=perf_counter()
    driver,meta=prepare(case,matrix,10.0)
    if driver.identity!=old_start["driver_identity"] or driver.identity!=old_end["driver_identity"]:
        raise ValueError("physical driver/clock identity not compatible")
    if meta["source_sha256"]!=old_start["source_sha256"] or (
        meta["patch_sha256"]!=old_start["patch_sha256"]):
        raise ValueError("original city/calendar/patch data changed")
    checkpoint=driver.load(source)
    if checkpoint.time_s!=25300:
        raise ValueError("checkpoint physical clock mismatch")
    initial_ledger=driver.report(checkpoint)
    if _ledger_error(initial_ledger,25300,population=100000) is not None:
        raise ValueError("original source 25,300s mass ledger invalid")
    exported=newprefix/"valley_weekday_s7.native_arc_roundtrip_25300.bin"
    driver.save(exported,checkpoint)
    roundtrip_sha=digest(exported)
    exported.unlink()
    if roundtrip_sha!=old_start["final_checkpoint_sha256"]:
        raise ValueError("new Arc code cannot reproduce pre-Arc native checkpoint bytes")
    init_bytes=source.stat().st_size
    physical=driver.advance(checkpoint,25600.0)
    result=driver.report(physical)
    if physical.time_s!=25600:
        raise ValueError("Arc native engine did not reach 25,600s")
    err=_ledger_error(result,25600,population=100000)
    if err is not None:
        raise ValueError("Arc physical mass ledger invalid: "+err)
    output=newprefix/"valley_weekday_s7.native_arc_25600.final.bin"
    driver.save(output,physical)
    sha=digest(output)
    match=(sha==old_end["last_valid_checkpoint_sha256"] and
           result["execution"]["ledger"]==old_end["mass_ledger"])
    duration=perf_counter()-start
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    doc={
      "schema":"V03_C9_ARC_VS_PREARC_ORIGINAL_PHYSICAL_REPLAY_20261120_V1",
      "status":"BYTE_IDENTICAL_SCOPED" if match else "PHYSICAL_CHECKPOINT_MISMATCH",
      "original_source_model":"RUST_WHOLE_100000_VALLEY",
      "original_full_day_accepted":False,
      "source_timestamp":25300.0,
      "destination_timestamp":25600.0,
      "original_86400s_day_required":86400,
      "original_source_binary_sha256":old_start["native_binary_sha256"],
      "new_arc_binary_sha256":current_bin["sha256"],
      "current_arc_candidate_source_sha256":current_src["source_sha256"],
      "matrix_sha256":digest(matrix_file),
      "same_physical_driver_identity":True,
      "initial_checkpoint_bytes":init_bytes,
      "original_source_25300_checkpoint_sha256":old_start["final_checkpoint_sha256"],
      "cross_binary_restore_save_25300_byte_equal":True,
      "new_arc_checkpoint_sha256":sha,
      "reference_25600_checkpoint_sha256":old_end["last_valid_checkpoint_sha256"],
      "new_arc_checkpoint_bytes":output.stat().st_size,
      "reference_25600_checkpoint_bytes":old_end["last_valid_checkpoint_bytes"],
      "mass_ledger_exact_equal":result["execution"]["ledger"]==old_end["mass_ledger"],
      "full_checkpoint_byte_equal":sha==old_end["last_valid_checkpoint_sha256"],
      "old_reference_elapsed_s":old_end["elapsed_seconds"],
      "new_arc_including_rebuild_and_decode_wall_s":duration,
      "old_reference_rss_bytes":old_end["max_rss_bytes"],
      "new_arc_process_peak_rss_bytes":rss,
      "address_space_limit_bytes":limit,
      "new_arc_checkpoint_binary_local_only":True,
      "new_fitted_parameters":[],
      "claim_limit":"single 25300->25600 source-matched original physical continuation; benchmark includes full plan reconstruction & checkpoint load",
    }
    out=newprefix/"C9_ARC_PHYSICAL_REPLAY.json"
    out.write_text(json.dumps(doc,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":doc["status"],"checkpoint_match":doc["full_checkpoint_byte_equal"],
                      "ledger_equal":doc["mass_ledger_exact_equal"],"elapsed_s":round(duration,3),
                      "peak_rss_gib":round(rss/1024**3,3),
                      "checkpoint_mb":round(output.stat().st_size/1024**2,2)},sort_keys=True),flush=True)
    if not match or rss>matrix["limits"]["peak_rss_bytes"]:
        raise ArithmeticError("Arc candidate failed original V03 physical/8GiB condition")
    return doc


if __name__=="__main__":
    run()
