#!/usr/bin/env python3
"""Source-locked original Valley 100k 25700 to 25710, exact Arc owner identity.

Requires a SHA-locked previously verified source checkpoint; current source
and native library must be clean and DIFFERENT. Checks source-matched driver,
full checkpoint wire, mass ledger and fixed original 8GiB budget.
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
START = 25700.0
END = 25710.0
CAP = 8 * 1024**3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-receipt", required=True, type=Path)
    parser.add_argument("--start-checkpoint", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    if os.environ.get("METROFLOW_BUDGET_TRACE") != "record":
        raise ValueError("native record-only trace required")
    if os.environ.get("METROFLOW_EXPERIMENTAL_ARC_PAIR_BUDGET") is not None:
        raise ValueError("no Arc-pair experimental allowance")
    previous = json.loads(args.start_receipt.read_bytes())
    if (previous.get("status") != "EXECUTED_ORIGINAL_100K_KEYSET_25700_CROSS_BINARY"
            or previous.get("case") != CASE
            or previous.get("completed_time_s") != START
            or previous.get("native_process_cap_bytes") != CAP
            or previous.get("budget_mode") != "DEFAULT"):
        raise ValueError("new-native original 25700 source receipt is invalid")
    if (not args.start_checkpoint.is_file()
            or args.start_checkpoint.stat().st_size != previous["final_checkpoint_bytes"]
            or file_sha256(args.start_checkpoint) != previous["final_checkpoint_sha256"]):
        raise ValueError("new-native 25700 file does not match the measured receipt")

    matrix_path = ROOT / "scenarios/v1/release_matrix.json"
    original_matrix = matrix_path.read_bytes()
    matrix_sha = hashlib.sha256(original_matrix).hexdigest()
    matrix = json.loads(original_matrix)
    if (matrix_sha != previous["original_matrix_sha256"]
            or matrix.get("population") != 100000
            or matrix.get("horizon_s") != 86400
            or matrix["limits"]["peak_rss_bytes"] != CAP
            or matrix["limits"]["wall_s"] != 7200):
        raise ValueError("original matrix drift")
    case = next(c for c in matrix["cases"] if c["id"] == CASE)

    source = candidate_provenance()
    native = native_binary_provenance()
    if (source.get("status") != "MEASURED"
            or source.get("source_dirty") is not False
            or native.get("status") != "MEASURED"
            or source["source_sha256"] == previous["current_candidate_source_sha256"]
            or native["sha256"] == previous["current_native_binary_sha256"]
            or Path(native["path"]).resolve().parent != (ROOT / "native_binding").resolve()):
        raise ValueError("the new keyset candidate must differ from original source/native")

    os.environ.update(
        METROFLOW_V1_ENGINE_BACKEND="rust_whole",
        METROFLOW_V1_NATIVE_THREADS="1",
        METROFLOW_V1_STORAGE_POLICY="bounded_bytes_v1",
    )
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    limit = min(CAP, soft) if soft != resource.RLIM_INFINITY else CAP
    if hard != resource.RLIM_INFINITY:
        limit = min(limit, hard)
    resource.setrlimit(resource.RLIMIT_AS, (limit, hard))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    dest = args.out.with_suffix(".final.bin")

    phase = "PREPARE"
    status = "INCONCLUSIVE"
    error = None
    old_wire_roundtrip = None
    driver_id = None
    initial_ledger = None
    final_ledger = None
    initial_road_capacity_bytes = None
    initial_road_part_count = None
    initial_debug_keysets = None
    final_time = None
    final_sha = None
    final_bytes = None
    trace = None
    started = time.perf_counter()
    try:
        driver, meta = prepare(case, matrix, 10.0)
        driver_id = driver.identity
        if (driver_id != previous["current_driver_identity"]
                or not meta["source_sha256"]
                or driver.plan.totals()["resident_stock"] != 100000):
            raise ValueError("current native driver/calendar source binding invalid")
        phase = "LOAD_CURRENT_NATIVE_CHECKPOINT"
        state = driver.load(args.start_checkpoint)
        if state.time_s != START:
            raise ValueError("new-native restored checkpoint clock invalid")
        report = driver.report(state)
        if (reason := _ledger_error(report, START, population=100000)) is not None:
            raise ValueError("restored current native state ledger invalid: " + reason)
        initial_ledger = report["execution"]["ledger"]
        road=driver.debug_state(state)["road"]
        initial_road_capacity_bytes=road["vector_capacity_bytes"]
        initial_road_part_count=road["cell_parts"]+road["pending_parts"]
        initial_debug_keysets=road["ordered_keyset_census"]
        if initial_ledger != previous["completed_mass_ledger"]:
            raise ValueError("current native checkpoint mass ledger differs from original")
        phase = "CURRENT_SOURCE_EXACT_WIRE_ROUNDTRIP"
        with tempfile.TemporaryDirectory(dir=args.out.parent) as folder:
            temporary = Path(folder) / "current_native_roundtrip.bin"
            driver.save(temporary, state)
            old_wire_roundtrip = (
                temporary.stat().st_size == previous["final_checkpoint_bytes"]
                and file_sha256(temporary) == previous["final_checkpoint_sha256"]
            )
        if not old_wire_roundtrip:
            raise ValueError("current native 25700 checkpoint wire roundtrip mismatch")
        print("CURRENT_SOURCE_25700_WIRE_AND_LEDGER_VERIFIED", flush=True)
        if budget_trace_snapshot(reset=True)["mode"] != "record":
            raise ValueError("record-only budget tracing unavailable")

        phase = "PHYSICAL_25700_TO_25710"
        try:
            result = driver.advance(state, END)
        except Exception as exc:
            if "budget" not in type(exc).__name__.lower() and "budget" not in str(exc).lower():
                raise
            error = {"class": type(exc).__name__, "message": str(exc), "phase": phase}
            status = "BLOCKED_RESOURCE"
            result = None
        trace = budget_trace_snapshot(reset=False)
        if result is not None:
            final_time = result.time_s
            if final_time != END:
                raise ValueError("current native tick ended at wrong time")
            last = driver.report(result)
            if (reason := _ledger_error(last, END, population=100000)) is not None:
                raise ValueError("new 25710 native physical ledger invalid: " + reason)
            final_ledger = last["execution"]["ledger"]
            phase = "SAVE_CURRENT_SOURCE_25710"
            driver.save(dest, result)
            final_bytes = dest.stat().st_size
            final_sha = file_sha256(dest)
            status = "EXECUTED_ORIGINAL_100K_KEYSET_25710_CROSS_BINARY"
    except Exception as exc:
        if error is None:
            error = {"class": type(exc).__name__, "message": str(exc), "phase": phase}
            status = "BLOCKED_" + type(exc).__name__
    if trace is None:
        trace = budget_trace_snapshot(reset=False)
    elapsed = time.perf_counter() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    receipt = {
        "schema": "V03_FIFO_CLOSURE_DEFAULT_EXACT_ARC_25710_V1",
        "case": CASE,
        "status": status, "phase": phase, "error": error,
        "input_checkpoint_sha256": previous["final_checkpoint_sha256"],
        "input_checkpoint_size_bytes": previous["final_checkpoint_bytes"],
        "previous_candidate_source_sha256": previous["current_candidate_source_sha256"],
        "previous_native_binary_sha256": previous["current_native_binary_sha256"],
        "cross_binary_origin": True,
        "original_current_source_from_time_0_verified": False,
        "current_candidate_source_sha256": source["source_sha256"],
        "current_native_binary_sha256": native["sha256"],
        "current_source_dirty": source.get("source_dirty"),
        "current_git_commit": source.get("git_commit"),
        "original_matrix_sha256": matrix_sha,
        "previous_driver_identity": previous["current_driver_identity"],
        "current_driver_identity": driver_id,
        "starting_checkpoint_roundtrip_exact": old_wire_roundtrip,
        "start_time_s": START, "end_time_s": END,
        "completed_time_s": final_time,
        "input_mass_ledger": initial_ledger,
        "actual_decoded_road_vector_capacity_bytes": initial_road_capacity_bytes,
        "actual_decoded_road_part_count": initial_road_part_count,
        "remaining_not_yet_shared_keysets": initial_debug_keysets,
        "completed_mass_ledger": final_ledger,
        "final_checkpoint_sha256": final_sha,
        "final_checkpoint_bytes": final_bytes,
        "local_checkpoint_only": True,
        "native_process_cap_bytes": limit,
        "budget_mode": "DEFAULT",
        "trace_sites": trace.get("sites"),
        "trace_counters": trace.get("counters"),
        "rss_peak_bytes": rss, "wall_s": elapsed,
        "original_full_day_acceptance": "BLOCKED_0_OF_9",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({
        "status": status, "completed_time_s": final_time, "error": error,
        "roundtrip_25700": old_wire_roundtrip,
        "wall_s": round(elapsed, 3), "rss_peak_gib": round(rss / 2**30, 3),
        "final_checkpoint_sha": final_sha,
    }, sort_keys=True), flush=True)
    return 0 if status in ("BLOCKED_RESOURCE", "EXECUTED_ORIGINAL_100K_KEYSET_25710_CROSS_BINARY") else 2


if __name__ == "__main__":
    raise SystemExit(main())
