#!/usr/bin/env python3
"""Source-bound original V03 prefix execution with streaming checkpoint evidence.

Keeps the original matrix, full demand, 10 s step and resource limits. Accepts
a verified earlier checkpoint or starts at time zero. Requested horizons and
completed physical horizons are separate. This is not the nine-run release.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from tools.run_v1_local_acceptance import prepare, candidate_provenance, _ledger_error, file_sha256
from metroflow.v1.native_engine import native_binary_provenance
from _metroflow_rust import budget_trace_snapshot

CAP = 8 * 1024**3
READER = """
import gzip,hashlib,json,sys,resource
fifo,out,meta=sys.argv[1:]
digest=hashlib.sha256(); size=0
target=open(out,'wb') if out!='-' else None
compressed=gzip.GzipFile(fileobj=target,mode='wb',compresslevel=1,mtime=0) if target else None
with open(fifo,'rb') as source:
    while True:
        block=source.read(1024*1024)
        if not block:break
        digest.update(block);size+=len(block)
        if compressed:compressed.write(block)
if compressed:compressed.close();target.close()
with open(meta,'w') as f:json.dump(dict(raw_sha256=digest.hexdigest(),raw_bytes=size,reader_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024),f)
"""

def wire_evidence(driver, state, folder, destination=None):
    """Hash original native wire; optionally gzip it without a second raw file."""
    driver.check(state)
    with tempfile.TemporaryDirectory(prefix="wire-", dir=folder) as td:
        td = Path(td)
        fifo, meta = td / "native.pipe", td / "wire.json"
        os.mkfifo(fifo, 0o600)
        output = td / "checkpoint.gz" if destination else "-"
        reader = subprocess.Popen([sys.executable, "-c", READER, str(fifo), str(output), str(meta)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            driver.runtime.native.save(str(fifo), state.runtime_state)
            _, stderr = reader.communicate(timeout=600)
            if reader.returncode:
                raise RuntimeError("checkpoint consumer failed: " + stderr.decode()[-2000:])
            result = json.loads(meta.read_text())
            if destination:
                output.replace(destination)
                result.update(compressed_sha256=file_sha256(destination),
                              compressed_bytes=destination.stat().st_size,
                              path=str(destination.resolve()))
            return result
        finally:
            if reader.poll() is None:
                reader.terminate()
                reader.communicate(timeout=10)

@contextmanager
def raw_checkpoint(path, folder):
    if path.suffix != ".gz":
        yield path
        return
    with tempfile.TemporaryDirectory(prefix="restore-", dir=folder) as td:
        raw = Path(td) / "native.bin"
        with gzip.open(path, "rb") as source, raw.open("wb") as target:
            while block := source.read(1024*1024):
                target.write(block)
        yield raw

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="valley_weekday_s7")
    ap.add_argument("--start-receipt", type=Path)
    ap.add_argument("--checkpoint", type=Path)
    ap.add_argument("--horizons", required=True, help="increasing elapsed physical seconds")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--compare-receipt", type=Path, action="append", default=[],
                    help="verify full wire and physical ledger at that completed absolute horizon")
    args = ap.parse_args()
    horizons = [int(x) for x in args.horizons.split(",")]
    if not horizons or horizons != sorted(set(horizons)) or any(x <= 0 or x % 10 for x in horizons):
        raise ValueError("strictly increasing positive 10-second-aligned horizons required")
    if bool(args.checkpoint) != bool(args.start_receipt):
        raise ValueError("checkpoint and receipt must be supplied together")
    if os.environ.get("METROFLOW_BUDGET_TRACE") != "record":
        raise ValueError("record-only native budget tracing required")
    if os.environ.get("METROFLOW_EXPERIMENTAL_ARC_PAIR_BUDGET") is not None:
        raise ValueError("experimental resource credits are not allowed")
    matrix_file = ROOT / "scenarios/v1/release_matrix.json"
    matrix = json.loads(matrix_file.read_bytes())
    matrix_sha = file_sha256(matrix_file)
    if (matrix["population"], matrix["horizon_s"], matrix["limits"]["peak_rss_bytes"],
        matrix["limits"]["wall_s"]) != (100000, 86400, CAP, 7200):
        raise ValueError("original release scope or limits changed")
    case = next(c for c in matrix["cases"] if c["id"] == args.case)
    source, native = candidate_provenance(), native_binary_provenance()
    if source.get("source_dirty") is not False or native.get("status") != "MEASURED":
        raise ValueError("clean measured current source and native binary required")
    if Path(native["path"]).resolve().parent != (ROOT/"native_binding").resolve():
        raise ValueError("load this worktree's measured native binary")
    comparisons = {}
    for reference_path in args.compare_receipt:
        reference = json.loads(reference_path.read_bytes())
        target = reference.get("completed_time_s")
        if (reference.get("case") != args.case or reference.get("original_matrix_sha256") != matrix_sha
            or reference.get("native_process_cap_bytes") != CAP
            or reference.get("status") not in ("BLOCKED_RESOURCE_WITH_VALID_PREFIX",
                                               "EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON")
            or target is None or not reference.get("final_checkpoint_sha256")
            or not reference.get("completed_mass_ledger") or target in comparisons):
            raise ValueError("comparison receipt lacks a unique original completed-state binding")
        comparisons[target] = (reference_path, reference)
    prev = json.loads(args.start_receipt.read_bytes()) if args.start_receipt else None
    if prev:
        if (prev.get("case") != args.case or prev.get("native_process_cap_bytes") != CAP
            or prev.get("original_matrix_sha256") != matrix_sha
            or prev.get("completed_time_s") is None
            or not prev.get("final_checkpoint_sha256")
            or not prev.get("completed_mass_ledger")):
            raise ValueError("prior receipt lacks a valid original completed-state binding")
        if prev.get("status") not in ("BLOCKED_RESOURCE_WITH_VALID_PREFIX",
                                      "EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON"):
            raise ValueError("prior receipt is not an accepted completed prefix")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    os.environ.update(METROFLOW_V1_ENGINE_BACKEND="rust_whole",
                      METROFLOW_V1_NATIVE_THREADS="1",
                      METROFLOW_V1_STORAGE_POLICY="bounded_bytes_v1")
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    cap = min(CAP, soft) if soft != resource.RLIM_INFINITY else CAP
    if hard != resource.RLIM_INFINITY:
        cap = min(cap, hard)
    resource.setrlimit(resource.RLIMIT_AS, (cap, hard))
    started = time.perf_counter()
    result = dict(schema="METROFLOW_ORIGINAL_PREFIX_V2", created_utc=datetime.now(timezone.utc).isoformat(),
                  case=args.case, native_process_cap_bytes=cap, original_matrix_sha256=matrix_sha,
                  current_candidate_source_sha256=source["source_sha256"],
                  current_native_binary_sha256=native["sha256"],
                  source_commit=source.get("git_commit"), current_source_dirty=False,
                  source=source, native=native, budget_mode="DEFAULT", trace_mode="record",
                  current_source_from_time_zero_verified=prev is None,
                  original_full_day_acceptance="NOT_EVALUATED_9_RUN_RELEASE",
                  requested_horizons_s=horizons, completed_horizons=[], completed_steps=[],
                  comparison_targets_s=sorted(comparisons),
                  previous_checkpoint_full_wire_roundtrip_exact=None,
                  status="ERROR", error=None)
    state = None
    initial = None
    phase = "PREPARE"
    try:
        driver, metadata = prepare(case, matrix, 10.0)
        result["preparation_wall_s"] = time.perf_counter() - started
        result["current_driver_identity"] = driver.identity
        result["input_metadata"] = metadata
        result["calendar"] = driver.plan.summary(driver.cursor)
        if driver.plan.totals()["resident_stock"] != 100000:
            raise ValueError("original resident stock differs")
        phase = "RESTORE" if prev else "INITIAL"
        if prev:
            if driver.identity != prev["current_driver_identity"]:
                raise ValueError("driver/calendar binding differs from checkpoint")
            with raw_checkpoint(args.checkpoint, args.out.parent) as raw:
                if (raw.stat().st_size != prev["final_checkpoint_bytes"]
                    or file_sha256(raw) != prev["final_checkpoint_sha256"]):
                    raise ValueError("checkpoint wire differs from previous measured SHA")
                state = driver.load(raw)
        else:
            state = driver.initial()
        initial = state.time_s
        if prev and initial != prev["completed_time_s"]:
            raise ValueError("restored clock differs")
        if initial + horizons[-1] > 86400:
            raise ValueError("requested horizon exceeds the original day")
        if any(target not in {initial + h for h in horizons}
               or reference["current_driver_identity"] != driver.identity
               for target, (_, reference) in comparisons.items()):
            raise ValueError("comparison horizon or driver binding differs from requested run")
        report = driver.report(state)
        reason = _ledger_error(report, initial, population=100000)
        if reason:
            raise ValueError("initial ledger: " + reason)
        if prev and report["execution"]["ledger"] != prev["completed_mass_ledger"]:
            raise ValueError("restored previous ledger differs")
        result["start_time_s"] = initial
        result["previous_mass_ledger"] = report["execution"]["ledger"]
        if prev:
            phase = "ROUNDTRIP"
            wire = wire_evidence(driver, state, args.out.parent)
            if (wire["raw_sha256"],wire["raw_bytes"]) != (prev["final_checkpoint_sha256"],prev["final_checkpoint_bytes"]):
                raise ValueError("current source checkpoint roundtrip differs")
            result["previous_checkpoint_full_wire_roundtrip_exact"] = True
            result["previous_checkpoint_sha256"] = prev["final_checkpoint_sha256"]
            result["previous_candidate_source_sha256"] = prev.get("current_candidate_source_sha256")
        print("INITIAL_VALID", initial, flush=True)
        result["startup_trace"] = budget_trace_snapshot(reset=True)
        for horizon in horizons:
            target = initial + horizon
            print("START_HORIZON", target, flush=True)
            tick_started = time.perf_counter()
            phase = "ADVANCE_TO_" + str(target)
            try:
                next_state = driver.advance(state, target)
            except Exception as exc:
                # Native may have completed earlier ticks within this call.
                valid = getattr(exc, "checkpoint", None)
                if valid is not None and valid.time_s >= state.time_s:
                    state = valid
                raise
            report = driver.report(next_state)
            reason = _ledger_error(report, target, population=100000)
            if reason:
                raise ValueError("new physical ledger: " + reason)
            state = next_state
            item = dict(elapsed_physical_s=horizon, completed_time_s=state.time_s,
                        segment_wall_s=time.perf_counter()-tick_started,
                        native_tick_wall_s=driver.runtime.last_advance_metrics["tick_times_s"])
            if target in comparisons:
                reference_path, reference = comparisons[target]
                wire = wire_evidence(driver, state, args.out.parent)
                if ((wire["raw_sha256"], wire["raw_bytes"]) !=
                    (reference["final_checkpoint_sha256"], reference["final_checkpoint_bytes"])
                    or report["execution"]["ledger"] != reference["completed_mass_ledger"]):
                    raise ValueError("matched horizon wire or physical ledger differs")
                item["matched_reference"] = dict(path=str(reference_path),
                    receipt_sha256=file_sha256(reference_path), raw_sha256=wire["raw_sha256"],
                    raw_bytes=wire["raw_bytes"], full_wire_and_ledger_exact=True)
            result["completed_horizons"].append(item)
            print("HORIZON_VALID", json.dumps(item), flush=True)
            if time.perf_counter()-started >= matrix["limits"]["wall_s"]:
                raise TimeoutError("original 7200-second wall budget reached")
        result["status"] = "EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON"
    except Exception as exc:
        result["error"] = dict(class_name=type(exc).__name__, message=str(exc), phase=phase)
        is_budget = "budget" in type(exc).__name__.lower() or "budget" in str(exc).lower() or isinstance(exc, TimeoutError)
        result["status"] = ("BLOCKED_RESOURCE_WITH_VALID_PREFIX" if state is not None and initial is not None
                            and state.time_s > initial else "BLOCKED_RESOURCE") if is_budget else "ERROR"
        print("RUN_STOP", json.dumps(result["error"]), flush=True)
    result["trace"] = budget_trace_snapshot(reset=False)
    if state is not None and initial is not None:
        report = driver.report(state)
        reason = _ledger_error(report,state.time_s,population=100000)
        if reason:
            result.update(status="ERROR",error=dict(class_name="LedgerError",message=reason,phase="FINAL_VALID_STATE"))
        else:
            result["completed_time_s"] = state.time_s
            result["valid_advanced_duration_s"] = state.time_s - initial
            result["completed_mass_ledger"] = report["execution"]["ledger"]
            result["final_execution_report"] = report["execution"]
            if state.time_s > initial:
                destination = args.out.with_suffix(".final.bin.gz")
                try:
                    wire = wire_evidence(driver, state, args.out.parent, destination)
                except (MemoryError, OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                    # A validated in-memory frontier and a durable restart point
                    # are different results. Keep the former if save fails.
                    result["checkpoint_error"] = dict(
                        phase="FINAL_SAVE", class_name=type(exc).__name__, message=str(exc)
                    )
                    if result["status"] == "EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON":
                        result["status"] = "EXECUTED_WITHOUT_FINAL_CHECKPOINT"
                else:
                    result.update(final_checkpoint_sha256=wire["raw_sha256"],
                                  final_checkpoint_bytes=wire["raw_bytes"],
                                  checkpoint_compression=wire)
                result["final_trace"] = budget_trace_snapshot(reset=False)
    result["wall_s"] = time.perf_counter()-started
    result["peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    result["checkpoint_reader_peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*1024
    args.out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({k:result.get(k) for k in ("status","start_time_s","completed_time_s",
          "valid_advanced_duration_s","wall_s","peak_rss_bytes","final_checkpoint_sha256","error")}),flush=True)
    return 0 if result["status"] != "ERROR" else 2

if __name__ == "__main__":
    raise SystemExit(main())
