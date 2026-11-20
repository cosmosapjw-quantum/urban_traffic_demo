#!/usr/bin/env python3
"""Original Valley FIFO 25,650 -> 25,700s cross-binary wire-equivalence probe.

Not a source-locked continuation: old/native checkpoint origin is recorded
separately from the current native source. No native budget overrides.
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
START = 25650.0
END = 25700.0
CAP = 8 * 1024**3


def validate_old_source(old: dict, checkpoint: Path, matrix_sha: str) -> None:
    """Fail-closed binding to an independently measured historical source."""
    if (old.get("status") != "EXECUTED_SOURCE_BOUND_25650_SCOPED"
            or old.get("reached_end_s") != START
            or old.get("original_matrix_sha256") != matrix_sha
            or old.get("original_8GiB_process_cap_bytes") != CAP
            or old.get("original_native_cap_bytes") != 5242806391):
        raise ValueError("historical source/cap/clock binding mismatch")
    if (not checkpoint.is_file()
            or checkpoint.stat().st_size != old.get("checkpoint_bytes")
            or file_sha256(checkpoint) != old.get("final_checkpoint_sha256")):
        raise ValueError("historical checkpoint bytes do not match verified SHA")
    for field in ("source_sha256", "loaded_native_sha256",
                  "original_driver_identity", "final_checkpoint_sha256"):
        v = old.get(field)
        if not isinstance(v, str) or not v:
            raise ValueError(f"historical reference missing {field}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-receipt", type=Path, required=True)
    parser.add_argument("--old-checkpoint", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if os.getenv("METROFLOW_BUDGET_TRACE") != "record":
        raise ValueError("record-only trace required, not observe")
    if os.getenv("METROFLOW_EXPERIMENTAL_ARC_PAIR_BUDGET") is not None:
        raise ValueError("Arc-pair budget experimental override not allowed")
    matrix_file = ROOT / "scenarios/v1/release_matrix.json"
    matrix_bytes = matrix_file.read_bytes()
    matrix_sha = hashlib.sha256(matrix_bytes).hexdigest()
    matrix = json.loads(matrix_bytes)
    if (matrix.get("population") != 100000 or matrix.get("horizon_s") != 86400
            or matrix["limits"].get("peak_rss_bytes") != CAP
            or matrix["limits"].get("wall_s") != 7200 or matrix.get("repeat") != 3):
        raise ValueError("original V03 physical/resource matrix has drifted")
    case = next(x for x in matrix["cases"] if x["id"] == CASE)
    old = json.loads(args.old_receipt.read_bytes())
    validate_old_source(old, args.old_checkpoint, matrix_sha)
    source_now = candidate_provenance()
    native_now = native_binary_provenance()
    if (source_now.get("status") != "MEASURED"
            or source_now.get("source_dirty") is not False
            or native_now.get("status") != "MEASURED"):
        raise ValueError("current original-scoped source/native fingerprint invalid")
    if Path(native_now["path"]).resolve().parent != (ROOT / "native_binding").resolve():
        raise ValueError("native imported from a different worktree")
    if native_now["sha256"] == old["loaded_native_sha256"]:
        raise ValueError("cross-version probe requires a distinct new binary")

    os.environ.update(
        METROFLOW_V1_ENGINE_BACKEND="rust_whole",
        METROFLOW_V1_NATIVE_THREADS="1",
        METROFLOW_V1_STORAGE_POLICY="bounded_bytes_v1",
    )
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    process_limit = min(CAP, soft) if soft != resource.RLIM_INFINITY else CAP
    if hard != resource.RLIM_INFINITY:
        process_limit = min(process_limit, hard)
    resource.setrlimit(resource.RLIMIT_AS, (process_limit, hard))
    args.out.parent.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    status = "INCONCLUSIVE"
    phase = "PREPARING"
    error = None
    new_checkpoint_sha = None
    new_checkpoint_bytes = None
    reencoded_same = None
    current_driver_id = None
    initial_ledger = None
    final_ledger = None
    completed_time = None
    trace = None
    try:
        driver, meta = prepare(case, matrix, 10.0)
        current_driver_id = driver.identity
        if current_driver_id != old["original_driver_identity"]:
            raise ValueError("old/new original city driver identity differs")
        if not meta.get("source_sha256") or not meta.get("patch_sha256"):
            raise ValueError("source city/patch provenance missing")
        if driver.plan.totals()["resident_stock"] != 100000:
            raise ValueError("original city resident count changed")
        phase = "RESTORE"
        state = driver.load(args.old_checkpoint)
        if state.time_s != START:
            raise ValueError("historical restored physical clock differs")
        old_report = driver.report(state)
        if (msg := _ledger_error(old_report, START, population=100000)) is not None:
            raise ValueError("historical state mass ledger invalid: " + msg)
        initial_ledger = old_report["execution"]["ledger"]
        phase = "EXACT_WIRE_ROUNDTRIP"
        with tempfile.TemporaryDirectory(dir=args.out.parent) as tmp:
            dest = Path(tmp) / "roundtrip.bin"
            driver.save(dest, state)
            reencoded_same = (dest.stat().st_size == old["checkpoint_bytes"]
                              and file_sha256(dest) == old["final_checkpoint_sha256"])
        if not reencoded_same:
            raise ValueError("cross-binary checkpoint serialization changed")
        print("CROSS_BINARY_WIRE_EQUALITY_VERIFIED", flush=True)
        if budget_trace_snapshot(reset=True)["mode"] != "record":
            raise ValueError("native budget trace record mode unavailable")
        phase = "PHYSICAL_25650_TO_25700"
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
            completed_time = result.time_s
            if completed_time != END:
                raise ValueError("native physical step reached unexpected clock")
            report = driver.report(result)
            if (msg := _ledger_error(report, END, population=100000)) is not None:
                raise ValueError("new physical ledger invalid: " + msg)
            final_ledger = report["execution"]["ledger"]
            phase = "SAVE_COMPLETE_CHECKPOINT"
            dest = args.out.with_suffix(".final.bin")
            driver.save(dest, result)
            new_checkpoint_bytes = dest.stat().st_size
            new_checkpoint_sha = file_sha256(dest)
            status = "EXECUTED_BOUNDED_PHYSICAL_CROSS_BINARY"
    except Exception as exc:
        if error is None:
            error = {"class": type(exc).__name__, "message": str(exc), "phase": phase}
            status = "BLOCKED_" + type(exc).__name__
    elapsed = time.perf_counter() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    receipt = {
        "schema": "V03_EXACT_VIEW_CROSS_BINARY_PROBE_V1",
        "case": CASE,
        "status": status, "phase": phase, "error": error,
        "old_source_sha256": old["source_sha256"],
        "old_native_binary_sha256": old["loaded_native_sha256"],
        "current_source_sha256": source_now["source_sha256"],
        "current_native_binary_sha256": native_now["sha256"],
        "current_git_commit": source_now.get("git_commit"),
        "current_source_dirty": source_now.get("source_dirty"),
        "input_checkpoint_sha256": old["final_checkpoint_sha256"],
        "input_checkpoint_bytes": old["checkpoint_bytes"],
        "matrix_sha256": matrix_sha,
        "old_driver_identity": old["original_driver_identity"],
        "current_driver_identity": current_driver_id,
        "start_time_s": START, "target_time_s": END,
        "completed_time_s": completed_time,
        "roundtrip_wire_identity": reencoded_same,
        "start_ledger": initial_ledger, "final_ledger": final_ledger,
        "trace_mode": "record",
        "trace_sites": trace.get("sites") if isinstance(trace, dict) else None,
        "trace_counters": trace.get("counters") if isinstance(trace, dict) else None,
        "process_address_space_cap_bytes": process_limit,
        "wall_s": elapsed, "peak_rss_bytes": rss,
        "final_checkpoint_sha256": new_checkpoint_sha,
        "final_checkpoint_bytes": new_checkpoint_bytes,
        "original_source_bound_current_prefix": False,
        "model_parameters_changed": False,
        "original_V03_full_day_acceptance": "BLOCKED_0_OF_9",
        "evidence_class": "EXPERIMENTAL_CROSS_VERSION_WIRE_EQUIVALENCE",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    args.out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True)+"\n")
    print(json.dumps({
        "status": status, "phase": phase,
        "roundtrip_equal": reencoded_same, "error": error,
        "wall_s": round(elapsed, 3),
        "rss_gib": round(rss/1024**3, 3),
        "completed_time_s": completed_time,
        "original_full_day_runs": "0/9",
    }, sort_keys=True), flush=True)
    # Negative resource result is an accurately recorded scientific outcome.
    return 0 if status in ("BLOCKED_RESOURCE", "EXECUTED_BOUNDED_PHYSICAL_CROSS_BINARY") else 2


if __name__ == "__main__":
    raise SystemExit(main())
