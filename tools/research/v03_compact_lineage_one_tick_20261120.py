#!/usr/bin/env python3
"""Bounded original Valley 100k, independently verified 25650->25660 tick.

The source checkpoint is from a separate historical native version. This
records both exact source identities and never counts as source-from-zero V03
or as a full-day acceptance. Default 8GiB/7200s matrix and FIFO unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
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
from tools.research.v03_exact_view_cross_binary_probe_20261120 import (  # noqa: E402
    validate_old_source,
)
from _metroflow_rust import budget_trace_snapshot  # noqa: E402

CASE = "valley_weekday_s7"
START = 25650.0
END = 25660.0
PROCESS_CAP = 8 * 1024**3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-receipt", required=True, type=Path)
    parser.add_argument("--old-checkpoint", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if os.environ.get("METROFLOW_BUDGET_TRACE") != "record":
        raise ValueError("record-only original guard tracing is required")
    if os.environ.get("METROFLOW_EXPERIMENTAL_ARC_PAIR_BUDGET") is not None:
        raise ValueError("experimental Arc-pair resource credit is forbidden")

    matrix_path = ROOT / "scenarios/v1/release_matrix.json"
    source_matrix = matrix_path.read_bytes()
    matrix_sha = hashlib.sha256(source_matrix).hexdigest()
    matrix = json.loads(source_matrix)
    if (matrix.get("population") != 100000
            or matrix.get("horizon_s") != 86400
            or matrix["limits"].get("peak_rss_bytes") != PROCESS_CAP
            or matrix["limits"].get("wall_s") != 7200):
        raise ValueError("original original-city physical matrix drift")
    case = next(c for c in matrix["cases"] if c["id"] == CASE)
    historical = json.loads(args.old_receipt.read_bytes())
    validate_old_source(historical, args.old_checkpoint, matrix_sha)
    src = candidate_provenance()
    native = native_binary_provenance()
    if (src.get("status") != "MEASURED"
            or src.get("source_dirty") is not False
            or native.get("status") != "MEASURED"
            or Path(native["path"]).resolve().parent != (ROOT / "native_binding").resolve()):
        raise ValueError("current original native source or compiled binary not bound")

    os.environ.update(
        METROFLOW_V1_ENGINE_BACKEND="rust_whole",
        METROFLOW_V1_NATIVE_THREADS="1",
        METROFLOW_V1_STORAGE_POLICY="bounded_bytes_v1",
    )
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    limit = min(PROCESS_CAP, soft) if soft != resource.RLIM_INFINITY else PROCESS_CAP
    if hard != resource.RLIM_INFINITY:
        limit = min(limit, hard)
    resource.setrlimit(resource.RLIMIT_AS, (limit, hard))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    dest = args.out.with_suffix(".final.bin")
    phase = "PREPARE"
    status = "INCONCLUSIVE"
    error = None
    roundtrip_equal = None
    time_completed = None
    current_driver_id = None
    input_ledger = None
    final_ledger = None
    final_checkpoint_sha = None
    final_checkpoint_size = None
    trace = None
    started = time.perf_counter()
    try:
        driver, metadata = prepare(case, matrix, 10.0)
        current_driver_id = driver.identity
        if driver.identity != historical["original_driver_identity"]:
            raise ValueError("historical full-city driver identity mismatch")
        if (driver.plan.totals().get("resident_stock") != 100000
                or not metadata.get("source_sha256")
                or not metadata.get("patch_sha256")):
            raise ValueError("original source calendar mismatch")
        phase = "RESTORE_HISTORICAL"
        old = driver.load(args.old_checkpoint)
        if old.time_s != START:
            raise ValueError("historical source checkpoint clock mismatch")
        first_report = driver.report(old)
        if (reason := _ledger_error(first_report, START, population=100000)) is not None:
            raise ValueError("historical physical ledger invalid: " + reason)
        input_ledger = first_report["execution"]["ledger"]

        phase = "VERIFY_ORIGINAL_WIRE"
        with tempfile.TemporaryDirectory(dir=args.out.parent) as staging:
            tmp = Path(staging) / "old_source_exact_roundtrip.bin"
            driver.save(tmp, old)
            roundtrip_equal = (
                tmp.stat().st_size == historical["checkpoint_bytes"]
                and file_sha256(tmp) == historical["final_checkpoint_sha256"]
            )
        if not roundtrip_equal:
            raise ValueError("historical old checkpoint wire differed after new-native decode")
        print("EXACT_ORIGINAL_SOURCE_WIRE_VERIFIED", flush=True)
        if budget_trace_snapshot(reset=True)["mode"] != "record":
            raise ValueError("non-record budget trace observed")

        phase = "PHYSICAL_25650_TO_25660"
        current = driver.advance(old, END)
        time_completed = current.time_s
        if time_completed != END:
            raise ValueError("original 10s tick ended at wrong clock")
        final_report = driver.report(current)
        if (reason := _ledger_error(final_report, END, population=100000)) is not None:
            raise ValueError("post-tick physical mass ledger invalid: " + reason)
        final_ledger = final_report["execution"]["ledger"]
        phase = "SAVE_CURRENT_SOURCE_25660"
        driver.save(dest, current)
        final_checkpoint_size = dest.stat().st_size
        final_checkpoint_sha = file_sha256(dest)
        status = "EXECUTED_ORIGINAL_100K_ONE_TICK_CROSS_BINARY"
        trace = budget_trace_snapshot(reset=False)
    except Exception as exc:
        error = {"class": type(exc).__name__, "message": str(exc), "phase": phase}
        status = "BLOCKED_" + type(exc).__name__
        trace = budget_trace_snapshot(reset=False)
    elapsed = time.perf_counter() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    receipt = {
        "schema": "V03_COMPACT_LINEAGE_ORIGINAL_ONE_TICK_CROSS_BINARY_V1",
        "case": CASE,
        "status": status,
        "phase": phase,
        "error": error,
        "historical_source_sha256": historical["source_sha256"],
        "historical_native_sha256": historical["loaded_native_sha256"],
        "historical_input_checkpoint_sha256": historical["final_checkpoint_sha256"],
        "historical_input_checkpoint_bytes": historical["checkpoint_bytes"],
        "current_candidate_sha256": src["source_sha256"],
        "current_candidate_git_commit": src.get("git_commit"),
        "current_source_dirty": src.get("source_dirty"),
        "current_native_sha256": native["sha256"],
        "matrix_sha256": matrix_sha,
        "original_driver_identity": historical["original_driver_identity"],
        "current_driver_identity": current_driver_id,
        "historical_roundtrip_wire_exact": roundtrip_equal,
        "start_time_s": START,
        "target_time_s": END,
        "completed_time_s": time_completed,
        "start_ledger": input_ledger,
        "completed_ledger": final_ledger,
        "new_checkpoint_sha256": final_checkpoint_sha,
        "new_checkpoint_bytes": final_checkpoint_size,
        "new_checkpoint_local_only": True,
        "process_cap_bytes": limit,
        "budget_experimental_override": "OFF",
        "trace_mode": "record",
        "trace_sites": trace.get("sites") if isinstance(trace, dict) else None,
        "trace_counters": trace.get("counters") if isinstance(trace, dict) else None,
        "peak_rss_bytes": rss,
        "wall_s": elapsed,
        "full_original_24h_acceptance": "BLOCKED_0_OF_9",
        "original_current_native_0_to_25650_path_verified": False,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    args.out.write_text(json.dumps(receipt, sort_keys=True, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "status": status, "completed_time_s": time_completed, "error": error,
        "checkpoint_size_bytes": final_checkpoint_size,
        "checkpoint_sha256": final_checkpoint_sha,
        "wall_s": round(elapsed, 3),
        "peak_rss_gib": round(rss / 2**30, 3),
    }, sort_keys=True), flush=True)
    return 0 if status == "EXECUTED_ORIGINAL_100K_ONE_TICK_CROSS_BINARY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
