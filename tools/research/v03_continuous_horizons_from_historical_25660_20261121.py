#!/usr/bin/env python3
"""Exact original 100k Valley current-native continuous horizon staircase.

Each invocation loads one SHA-bound completed checkpoint, validates binary wire,
advances one original 10s tick at a time and writes only the last valid state.
A blocked tick is not counted as completed. Original V03 full day always 0/9.
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
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from tools.run_v1_local_acceptance import (  # noqa: E402
    prepare, candidate_provenance, _ledger_error, file_sha256,
)
from metroflow.v1.native_engine import native_binary_provenance  # noqa: E402
from _metroflow_rust import budget_trace_snapshot  # noqa: E402

CASE = "valley_weekday_s7"
CAP = 8 * 1024**3
TICK = 10


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-receipt", required=True, type=Path)
    parser.add_argument("--start-checkpoint", required=True, type=Path)
    parser.add_argument("--duration-s", required=True, type=int)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    if not (10 <= args.duration_s <= 86400 and args.duration_s % TICK == 0):
        raise ValueError("duration must be an increasing integral 10-second horizon")
    if os.environ.get("METROFLOW_BUDGET_TRACE") != "record":
        raise ValueError("original record-only budget trace required")
    if os.environ.get("METROFLOW_EXPERIMENTAL_ARC_PAIR_BUDGET") is not None:
        raise ValueError("experimental shared-Arc budget credit forbidden")

    prev = json.loads(args.start_receipt.read_bytes())
    # A real, independently validated older original-physics native checkpoint
    # can seed a new same-candidate continuous run. This does NOT validate
    # that this candidate itself ran original t=0 up to this starting clock.
    historical_origin = prev.get("status") == "EXECUTED_ORIGINAL_100K_ONE_TICK_CROSS_BINARY"
    historical_source_identity = None
    if historical_origin:
        historical_source_identity={
            "source_sha256":prev["current_candidate_sha256"],
            "native_sha256":prev["current_native_sha256"],
            "source_status":prev["status"],
        }
        if (prev.get("process_cap_bytes") != CAP
            or prev.get("budget_experimental_override") != "OFF"):
            raise ValueError("historical source original cap/allowance mismatch")
        prev={
            **prev,
            "native_process_cap_bytes":prev["process_cap_bytes"],
            "budget_mode":"DEFAULT",
            "original_matrix_sha256":prev["matrix_sha256"],
            "final_checkpoint_sha256":prev["new_checkpoint_sha256"],
            "final_checkpoint_bytes":prev["new_checkpoint_bytes"],
            "completed_mass_ledger":prev["completed_ledger"],
        }
    valid_sources = (
        "EXECUTED_ORIGINAL_100K_KEYSET_25700_CROSS_BINARY",
        "EXECUTED_ORIGINAL_100K_ONE_TICK_CROSS_BINARY",
        "EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON",
    )
    if (prev.get("status") not in valid_sources
            or prev.get("case") != CASE
            or prev.get("completed_time_s") is None
            or prev.get("native_process_cap_bytes") != CAP
            or prev.get("budget_mode") != "DEFAULT"
            or prev.get("final_checkpoint_sha256") is None):
        raise ValueError("starting receipt is not an admitted completed original 100k tick")
    if (not args.start_checkpoint.is_file()
            or args.start_checkpoint.stat().st_size != prev["final_checkpoint_bytes"]
            or file_sha256(args.start_checkpoint) != prev["final_checkpoint_sha256"]):
        raise ValueError("starting original checkpoint is not byte-identical")

    original_bytes = (ROOT / "scenarios/v1/release_matrix.json").read_bytes()
    matrix_sha = hashlib.sha256(original_bytes).hexdigest()
    matrix = json.loads(original_bytes)
    if (matrix_sha != prev["original_matrix_sha256"]
            or matrix["population"] != 100000
            or matrix["horizon_s"] != 86400
            or matrix["limits"]["peak_rss_bytes"] != CAP
            or matrix["limits"]["wall_s"] != 7200):
        raise ValueError("original release matrix or caps changed")
    case = next(x for x in matrix["cases"] if x["id"] == CASE)
    source = candidate_provenance()
    native = native_binary_provenance()
    if (source.get("status") != "MEASURED" or source.get("source_dirty") is not False
            or native.get("status") != "MEASURED"
            or (not historical_origin and (
                source["source_sha256"] != prev["current_candidate_source_sha256"]
                or native["sha256"] != prev["current_native_binary_sha256"]))
            or (historical_origin and (
                source["source_sha256"] == historical_source_identity["source_sha256"]
                or native["sha256"] == historical_source_identity["native_sha256"]))
            or Path(native["path"]).resolve().parent != (ROOT/"native_binding").resolve()):
        raise ValueError("only the exact current native may continue this original checkpoint")

    os.environ.update(
        METROFLOW_V1_ENGINE_BACKEND="rust_whole",
        METROFLOW_V1_NATIVE_THREADS="1",
        METROFLOW_V1_STORAGE_POLICY="bounded_bytes_v1",
    )
    soft,hard = resource.getrlimit(resource.RLIMIT_AS)
    limit = CAP if soft == resource.RLIM_INFINITY else min(CAP,soft)
    if hard != resource.RLIM_INFINITY:
        limit = min(limit,hard)
    resource.setrlimit(resource.RLIMIT_AS,(limit,hard))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out_checkpoint = args.out.with_suffix(".final.bin")
    started = time.perf_counter()
    original_t = float(prev["completed_time_s"])
    requested_end = original_t + args.duration_s
    if requested_end > matrix["horizon_s"]:
        raise ValueError("requested run exceeds the original physical day")
    stage="PREPARE"
    old_wire=None
    initial_mass=None
    final_mass=None
    valid_clock=None
    previous_driver=None
    step_results=[]
    failing_step=None
    failure=None
    output_sha=None
    output_size=None
    status="INCONCLUSIVE"
    trace=None

    try:
        driver,metadata = prepare(case,matrix,10.0)
        previous_driver = driver.identity
        if (driver.identity != prev["current_driver_identity"]
                or driver.plan.totals()["resident_stock"] != 100000
                or not metadata.get("source_sha256")
                or not metadata.get("patch_sha256")):
            raise ValueError("original full-city driver/calendar identity mismatch")
        stage="RESTORE_PREVIOUS_COMPLETE_STATE"
        state=driver.load(args.start_checkpoint)
        if state.time_s != original_t:
            raise ValueError("original checkpoint stored clock differs")
        report=driver.report(state)
        if (reason:=_ledger_error(report,original_t,population=100000)) is not None:
            raise ValueError("starting conservation ledger invalid: "+reason)
        initial_mass=report["execution"]["ledger"]
        if initial_mass != prev["completed_mass_ledger"]:
            raise ValueError("current-native previous physical ledger differs")
        final_mass=initial_mass
        valid_clock=original_t

        stage="VERIFY_FULL_WIRE_ROUNDTRIP"
        with tempfile.TemporaryDirectory(dir=args.out.parent) as td:
            tmp=Path(td)/"original_exact_checkpoint.bin"
            driver.save(tmp,state)
            old_wire=(tmp.stat().st_size==prev["final_checkpoint_bytes"]
                      and file_sha256(tmp)==prev["final_checkpoint_sha256"])
        if not old_wire:
            raise ValueError("full checkpoint wire not identical after current-native restore")
        print("HORIZON_INITIAL_WIRE_LEDGER_VERIFIED",original_t,flush=True)
        if budget_trace_snapshot(reset=True)["mode"] != "record":
            raise ValueError("record-only native guard unavailable")

        for i in range(args.duration_s//TICK):
            next_t=original_t + (i+1)*TICK
            if time.perf_counter()-started >= matrix["limits"]["wall_s"]:
                failure={"class":"WallCap","message":"original 7200s wall cap","phase":"PHYSICS"}
                failing_step=next_t
                break
            stage=f"ADVANCE_TO_{next_t:g}"
            start_tick=time.perf_counter()
            try:
                nxt=driver.advance(state,next_t)
            except Exception as exc:
                failure={"class":type(exc).__name__,"message":str(exc),"phase":stage}
                failing_step=next_t
                break
            if nxt.time_s != next_t:
                raise ValueError("native physics advanced to wrong original clock")
            report=driver.report(nxt)
            if (reason:=_ledger_error(report,next_t,population=100000)) is not None:
                raise ValueError("new original physical conservation failed: "+reason)
            state=nxt
            valid_clock=next_t
            final_mass=report["execution"]["ledger"]
            item={"completed_time_s":next_t,"wall_s":time.perf_counter()-start_tick}
            step_results.append(item)
            print("PHYSICAL_TICK_VALID",json.dumps(item,sort_keys=True),flush=True)

        trace=budget_trace_snapshot(reset=False)
        if valid_clock>original_t:
            stage="SAVE_LAST_VALID_CURRENT_NATIVE_CHECKPOINT"
            driver.save(out_checkpoint,state)
            output_size=out_checkpoint.stat().st_size
            output_sha=file_sha256(out_checkpoint)
        if valid_clock==requested_end and failure is None:
            status="EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON"
        elif failure is not None:
            status=("BLOCKED_RESOURCE_WITH_VALID_PREFIX"
                    if valid_clock>original_t else "BLOCKED_RESOURCE")
        else:
            status="INCONCLUSIVE"
    except Exception as exc:
        failure={"class":type(exc).__name__,"message":str(exc),"phase":stage}
        status="ERROR"
        trace=budget_trace_snapshot(reset=False)

    elapsed=time.perf_counter()-started
    receipt={
        "schema":"V03_ORIGINAL_100K_CONTINUOUS_ESCALATING_HORIZON_V1",
        "created_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "case":CASE,"status":status,"error":failure,
        "start_time_s":original_t,"requested_duration_s":args.duration_s,
        "requested_end_s":requested_end,"completed_time_s":valid_clock,
        "valid_advanced_duration_s":None if valid_clock is None else valid_clock-original_t,
        "blocked_target_time_s":failing_step,
        "completed_step_wall_s":step_results,
        "previous_checkpoint_cross_native":historical_origin,
        "historical_native_source_identity":historical_source_identity,
        "original_candidate_from_time_zero_verified":False,
        "previous_full_checkpoint_sha256":prev["final_checkpoint_sha256"],
        "previous_full_checkpoint_bytes":prev["final_checkpoint_bytes"],
        "previous_checkpoint_full_wire_roundtrip_exact":old_wire,
        "previous_mass_ledger":initial_mass,
        "completed_mass_ledger":final_mass,
        "final_checkpoint_sha256":output_sha,
        "final_checkpoint_bytes":output_size,
        "final_checkpoint_local_only":True,
        "current_candidate_source_sha256":source["source_sha256"],
        "current_native_binary_sha256":native["sha256"],
        "current_source_dirty":source["source_dirty"],
        "current_driver_identity":previous_driver,
        "original_matrix_sha256":matrix_sha,
        "native_process_cap_bytes":limit,
        "trace_mode":"record","original_full_day_acceptance":"BLOCKED_0_OF_9",
        "wall_total_including_full_preparation_and_checkpoint_io_s":elapsed,
        "peak_rss_bytes":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        "trace_sites":trace.get("sites") if trace else None,
        "trace_counters":trace.get("counters") if trace else None,
    }
    args.out.write_text(json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({
        "status":status,"requested_duration_s":args.duration_s,
        "valid_advanced_duration_s":receipt["valid_advanced_duration_s"],
        "end_time_s":valid_clock,"blocked_target_time_s":failing_step,
        "wall_s":round(elapsed,3),"peak_rss_gib":round(receipt["peak_rss_bytes"]/2**30,3),
        "final_checkpoint_sha256":output_sha,
        "error":failure,
    },sort_keys=True),flush=True)
    return 0 if status in ("EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON",
                           "BLOCKED_RESOURCE_WITH_VALID_PREFIX","BLOCKED_RESOURCE") else 2


if __name__=="__main__":
    raise SystemExit(main())
