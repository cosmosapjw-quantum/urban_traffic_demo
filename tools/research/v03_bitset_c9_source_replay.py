#!/usr/bin/env python3
"""Bounded experimental original-physics Valley t=25650→25700 continuation.

Single source-locked opt-in diagnosis, never V03 release acceptance.
Preserves the original 100k residents, 10s clock, 8 GiB address-space,
5,242,806,391-byte native budget and original model/f64 event order.
Never enable diagnostic 'observe' override or modify model coefficients.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import resource
import sys
from time import perf_counter
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]

from tools.run_v1_local_acceptance import prepare,candidate_provenance,_ledger_error
from metroflow.v1.native_engine import native_binary_provenance
from _metroflow_rust import budget_trace_snapshot

ART=ROOT/"artifacts/v03_bitset_physical_20261120"
INITIAL_TIME=25650.0
TARGET_TIME=25700.0
CASE_ID="valley_weekday_s7"


def sha_file(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def main()->dict:
    if os.environ.get("METROFLOW_BUDGET_TRACE")!="record":
        raise ValueError("record-only native trace required; do not use observe")
    if os.environ.get("METROFLOW_EXPERIMENTAL_ARC_PAIR_BUDGET") is not None:
        raise ValueError("default physical native execution must not enable Arc-pair credit")
    original=ART/"C8_BITSET_ORIGINAL_DEFAULT_25650.json"
    source=ART/"C8_BITSET_ORIGINAL_DEFAULT_25650.final.bin"
    old=json.loads(original.read_bytes())
    if old["status"]!="EXECUTED_SOURCE_BOUND_25650_SCOPED" or old["reached_end_s"]!=INITIAL_TIME:
        raise ValueError("unverified original preceding 25,650s state")
    if old["original_native_cap_bytes"]!=5242806391 or old["original_8GiB_process_cap_bytes"]!=8*1024**3:
        raise ValueError("release resource budget was changed")
    if source.stat().st_size!=old["checkpoint_bytes"] or sha_file(source)!=old["final_checkpoint_sha256"]:
        raise ValueError("local native checkpoint source bytes are invalid")
    mat_file=ROOT/"scenarios/v1/release_matrix.json"
    raw=mat_file.read_bytes()
    matrix=json.loads(raw)
    matrix_sha=hashlib.sha256(raw).hexdigest()
    assert old["original_matrix_sha256"]==matrix_sha
    assert matrix["population"]==100000 and matrix["horizon_s"]==86400
    assert matrix["limits"]["peak_rss_bytes"]==8*1024**3
    original_case=next(c for c in matrix["cases"] if c["id"]==CASE_ID)
    current_src=candidate_provenance()
    current_native=native_binary_provenance()
    if (current_src.get("status")!="MEASURED" or
        current_src.get("source_dirty") is not False or
        current_native.get("status")!="MEASURED"):
        raise ValueError("current source/native fingerprint unavailable or dirty")
    if current_src["source_sha256"]!=old["source_sha256"] or current_native["sha256"]!=old["loaded_native_sha256"]:
        raise ValueError("native executable differs from source of 25,650s checkpoint")
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
    start=perf_counter()
    stage="PREPARE"
    problem=None
    status="INCONCLUSIVE"
    output=None
    final_sha=None
    final_bytes=None
    ledger=None
    initial_debug=None
    trace=None
    driver_identity=None
    try:
        driver,meta=prepare(original_case,matrix,10.0)
        driver_identity=driver.identity
        assert driver_identity==old["original_driver_identity"]
        assert meta["source_sha256"] and meta["patch_sha256"]
        stage="CHECKPOINT_LOAD"
        snap=driver.load(source)
        if snap.time_s!=INITIAL_TIME:
            raise ValueError("native checkpoint clock changed")
        if _ledger_error(driver.report(snap),INITIAL_TIME,population=100000) is not None:
            raise ValueError("original source ledger invalid after restore")
        initial_debug=driver.debug_state(snap)["road"]
        trace_start=budget_trace_snapshot(reset=True)
        if trace_start["mode"]!="record":
            raise ValueError("trace recorder not operating safely")
        stage="PHYSICAL_ADVANCE"
        end=driver.advance(snap,TARGET_TIME)
        if end.time_s!=TARGET_TIME:
            raise ValueError("native physical result ended at another clock")
        report=driver.report(end)
        err=_ledger_error(report,TARGET_TIME,population=100000)
        if err:
            raise ValueError("physical mass ledger invalid: "+err)
        ledger=report["execution"]["ledger"]
        stage="CHECKPOINT_SERIALIZATION"
        output=ART/"C9_BITSET_DEFAULT_25700.final.bin"
        driver.save(output,end)
        final_sha=sha_file(output)
        final_bytes=output.stat().st_size
        status="EXECUTED_BOUNDED_25700"
    except Exception as exc:
        problem={"class":type(exc).__name__,"message":str(exc),"stage":stage}
        status="BLOCKED_"+type(exc).__name__
    wall=perf_counter()-start
    if stage not in ("PREPARE","CHECKPOINT_LOAD"):
        trace=budget_trace_snapshot(reset=False)
    else:
        # The phase that failed may not have permitted recorder initialization.
        trace=None
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    obj={
        "schema":"V03_INDEX_BITMAP_POST_25650_SOURCE_LOCKED_20261120_V1",
        "source_case":CASE_ID,
        "original_population":100000,
        "start_time_s":INITIAL_TIME,
        "target_time_s":TARGET_TIME,
        "status":status,
        "error":problem,
        "last_attempt_phase":stage,
        "actual_reached_target":status=="EXECUTED_BOUNDED_25700",
        "loaded_candidate_source_sha256":current_src["source_sha256"],
        "loaded_native_binary_sha256":current_native["sha256"],
        "input_checkpoint_sha256":old["final_checkpoint_sha256"],
        "input_checkpoint_bytes":old["checkpoint_bytes"],
        "current_driver_identity":driver_identity,
        "original_matrix_sha256":matrix_sha,
        # This was the *effective phase* allowance at the preceding 25,600s
        # call. The original engine recomputes later road phase allowances
        # from its fixed global pool minus dynamically reserved buffers.
        "previous_25600_effective_road_phase_allowance_bytes":old["original_native_cap_bytes"],
        "current_transfer_guard_effective_allowance_bytes":(
            trace["sites"].get("road_work:transfer candidates",{}).get("limit_at_max")
            if trace is not None else None
        ),
        "fixed_original_process_cap_bytes":limit,
        "budget_experimental_mode":"OFF",
        "trace_mode":"record",
        "trace_sites":trace["sites"] if trace is not None else None,
        "trace_counters":trace["counters"] if trace is not None else None,
        "initial_road_debug":initial_debug,
        "wall_s":wall,
        "process_peak_rss_bytes":rss,
        "final_checkpoint_sha256":final_sha,
        "final_checkpoint_bytes":final_bytes,
        "final_checkpoint_binary_local_only":True,
        "physical_mass_ledger":ledger,
        "original_full_day_acceptance":"BLOCKED_0_OF_9",
        "no_fitted_model_parameters":True,
        "created_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "nonclaims":["No default/native release acceptance; opt-in only",
                     "No universal physical FIFO proof beyond original unchanged code",
                     "No guarantee this bounded time segment predicts full-day completion"],
    }
    ART.mkdir(parents=True,exist_ok=True)
    path=ART/"C9_BITSET_DEFAULT_25700.json"
    path.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({
        "status":status,"stage":stage,"error":problem,
        "wall_s":round(wall,3),"peak_rss_gib":round(rss/1024**3,3),
        "final_checkpoint_gib":round(final_bytes/1024**3,3) if final_bytes else None,
        "final_sha256":final_sha,
        "default_release":"BLOCKED_0_OF_9",
    },sort_keys=True),flush=True)
    return obj


if __name__=="__main__":
    main()
