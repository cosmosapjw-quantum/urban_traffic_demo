#!/usr/bin/env python3
"""Source-bound original 100k continuation with explicit native-call cadence.

The original physical dt stays 10s. A call may cover multiple dt steps; on a
failed call only previously returned, ledger-checked states receive credit.
Historical seeds are exact complete receipt+checkpoint pins, never arbitrary
cross-version data. This is not a current-candidate time-zero execution.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
CASE = "valley_weekday_s7"
CAP = 8 * 1024**3
TICK = 10
SCHEMA = "V03_ORIGIN_VALIDATION_CONTINUATION_V1"
MATRIX_SHA = "1eb90b60d260feff915b785ed4d425dde0bcc1601ad3ad8200640c73d765655a"
DRIVER = "e77f5efaad25b7df237d91523146baacb8cbe3170bbb86594bdc0885c498fac4"
OLD_SOURCE = "7e8b92020076e01283d532cf0e5825cb30167a533949e6bc6fd071f7b7d8cfe2"
OLD_NATIVE = "baa3e4ce4f775df5cf3973e749357cc2d5a29cefbf1683355638a0de5b6a5606"
# receipt SHA -> (validated clock, complete bytes, wire SHA, source SHA, native SHA)
PINS = {
    "a338e34cd445a66bd025e017aca01356d89db04bb77a1dac7400f3a4af7c9cbf":
        (25730.0, 5523765378, "c8335535408e13266bb4b5f15b10d0854701e644421ae3e8183d7c468d9183c9", OLD_SOURCE, OLD_NATIVE),
    "cfba815ece86d0f632de5d51220c90aded20f299c20d15e1562ccc6a1b868bcf":
        (25660.0, 1912366706, "bbdc75baef04e522e8fe6e668561f41fc4987507469eeebd97c60c9291dfb7b0", OLD_SOURCE, OLD_NATIVE),
    # This-session saved 25690 state: reproduce the observed 40s save failure
    # after the capture-only source repair, without replaying unchanged 10/20s.
    "fb6b74b7af38592003d1af169d8c029b9ceb394194e3217d6011d0865dc95732":
        (25690.0, 2949231402, "db5b6b53f728d892ad53b9e7126d08e73b877f055e2e6e78443f1c0851b7bd10",
         "78b49811dd84544e3c5dcd4281c3918fc41384fc1815941792a90ccc58bde3f7",
         "3bec7cd5cb788047c95a1f55464af9baed28699ace086bc8fd13fe342c2b08d5"),
    # Final prior-loop candidate: saved 40s prefix and later fresh full-wire
    # verification. The next returned 25740 state failed SAVE and is not a pin.
    "4bace2763e79ed16e3b103d69ab358e30a38f15c45d536015a8d4f29c0c9de59":
        (25730.0, 5523765378, "c8335535408e13266bb4b5f15b10d0854701e644421ae3e8183d7c468d9183c9",
         "e6a49b7c0cd598ff480a1d3a421fa9e8ae57f227c311d514556a394f137b29db",
         "6a6d48c8986ce1ffe1108afa145707b556345f0e7572c7c4f34e7e64b19da808"),
}


def predecessor(raw: bytes, source_sha: str, native_sha: str) -> tuple[dict, bool]:
    """Admit only exact historical pins or a saved same-source valid prefix."""
    r = json.loads(raw)
    pin = PINS.get(hashlib.sha256(raw).hexdigest())
    complete = r.get("status") == "EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON"
    partial = (r.get("schema") == SCHEMA
               and r.get("status") == "BLOCKED_RESOURCE_WITH_VALID_PREFIX"
               and isinstance(r.get("error"), dict))
    if not (complete or partial):
        raise ValueError("predecessor must contain a verified saved physical prefix")
    if (r.get("case") != CASE or r.get("trace_mode") != "off"
            or r.get("diagnostic_only") is not False
            or r.get("current_source_dirty") is not False
            or r.get("native_process_cap_bytes") != CAP
            or r.get("original_matrix_sha256") != MATRIX_SHA
            or r.get("current_driver_identity") != DRIVER
            or r.get("previous_checkpoint_full_wire_roundtrip_exact") is not True
            or r.get("completed_mass_ledger") is None
            or not isinstance(r.get("final_checkpoint_sha256"), str)
            or len(r["final_checkpoint_sha256"]) != 64
            or not isinstance(r.get("final_checkpoint_bytes"), int)
            or r["final_checkpoint_bytes"] <= 0
            or not isinstance(r.get("valid_advanced_duration_s"), (int, float))
            or r["valid_advanced_duration_s"] <= 0
            or r.get("original_full_day_acceptance") != "BLOCKED_0_OF_9"):
        raise ValueError("predecessor physical/cap/identity contract mismatch")
    if r.get("completed_time_s") != r.get("start_time_s") + r["valid_advanced_duration_s"]:
        raise ValueError("predecessor returned physical clock mismatch")
    if complete and (r.get("error") is not None or
                     r.get("requested_duration_s") != r["valid_advanced_duration_s"]):
        raise ValueError("incomplete run mislabeled as completed")
    if pin:
        if ((r["completed_time_s"], r["final_checkpoint_bytes"],
             r["final_checkpoint_sha256"]) != pin[:3]
                or r["current_candidate_source_sha256"] != pin[3]
                or r["current_native_binary_sha256"] != pin[4]):
            raise ValueError("pinned historical metadata differs")
    elif (r.get("schema") != SCHEMA or
          r.get("current_candidate_source_sha256") != source_sha or
          r.get("current_native_binary_sha256") != native_sha):
        raise ValueError("unpinned cross-native/source predecessor forbidden")
    return r, bool(pin and (source_sha != pin[3] or native_sha != pin[4]))


def next_target(clock: float, end: float, cadence: str, span: int) -> float:
    if cadence == "hourly":
        return min(end, (math.floor(clock / 3600) + 1) * 3600)
    return min(end, clock + (TICK if cadence == "tick" else span))


def main() -> int:
    from tools.run_v1_local_acceptance import prepare, candidate_provenance, _ledger_error, file_sha256
    from metroflow.v1.native_engine import native_binary_provenance
    from _metroflow_rust import budget_trace_snapshot

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start-receipt", required=True, type=Path)
    p.add_argument("--start-checkpoint", required=True, type=Path)
    p.add_argument("--duration-s", required=True, type=int)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--cadence", choices=("tick", "window", "hourly"), default="tick")
    p.add_argument("--call-span-s", type=int, default=10)
    a = p.parse_args()
    if (a.duration_s < 0 or a.duration_s > 86400 or a.duration_s % TICK
            or not TICK <= a.call_span_s <= 3600 or a.call_span_s % TICK):
        raise ValueError("duration and span must preserve integral 10s dt")
    if (os.environ.get("METROFLOW_BUDGET_TRACE") != "off"
            or os.environ.get("METROFLOW_EXPERIMENTAL_ARC_PAIR_BUDGET") is not None):
        raise ValueError("trace must be off; experimental budget override forbidden")
    source, native = candidate_provenance(), native_binary_provenance()
    if (source.get("status") != "MEASURED" or source.get("source_dirty") is not False
            or native.get("status") != "MEASURED"
            or Path(native["path"]).resolve().parent != (ROOT / "native_binding").resolve()):
        raise ValueError("clean candidate and worktree-native binding required")
    raw = a.start_receipt.read_bytes()
    prev, cross = predecessor(raw, source["source_sha256"], native["sha256"])
    if (not a.start_checkpoint.is_file()
            or a.start_checkpoint.stat().st_size != prev["final_checkpoint_bytes"]
            or file_sha256(a.start_checkpoint) != prev["final_checkpoint_sha256"]):
        raise ValueError("complete predecessor checkpoint bytes differ")
    matrix_bytes = (ROOT / "scenarios/v1/release_matrix.json").read_bytes()
    matrix = json.loads(matrix_bytes)
    if (hashlib.sha256(matrix_bytes).hexdigest() != MATRIX_SHA
            or matrix["population"] != 100000 or matrix["horizon_s"] != 86400
            or matrix["limits"]["peak_rss_bytes"] != CAP or matrix["limits"]["wall_s"] != 7200):
        raise ValueError("original acceptance changed")
    start = float(prev["completed_time_s"])
    end = start + a.duration_s
    if end > 86400:
        raise ValueError("run must remain inside original physical day")
    os.environ.update(METROFLOW_V1_ENGINE_BACKEND="rust_whole",
                      METROFLOW_V1_NATIVE_THREADS="1",
                      METROFLOW_V1_STORAGE_POLICY="bounded_bytes_v1")
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    limit = CAP if soft == resource.RLIM_INFINITY else min(CAP, soft)
    if hard != resource.RLIM_INFINITY:
        limit = min(limit, hard)
    resource.setrlimit(resource.RLIMIT_AS, (limit, hard))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = a.out.with_suffix(".final.bin")
    started = time.perf_counter()
    clock = None
    initial_ledger = ledger = None
    exact_wire = None
    final_sha = final_bytes = None
    calls = []
    failure = None
    blocked = None
    phase = "PREPARE"
    status = "ERROR"
    driver = None
    native_metrics = None
    try:
        case = next(c for c in matrix["cases"] if c["id"] == CASE)
        driver, metadata = prepare(case, matrix, float(TICK))
        if (driver.identity != DRIVER or driver.plan.totals()["resident_stock"] != 100000
                or not metadata.get("source_sha256") or not metadata.get("patch_sha256")):
            raise ValueError("original driver/calendar differs")
        phase = "RESTORE"
        state = driver.load(a.start_checkpoint)
        report = driver.report(state)
        reason = _ledger_error(report, start, population=100000)
        if state.time_s != start or reason is not None:
            raise ValueError("restored clock/ledger invalid: " + str(reason))
        initial_ledger = ledger = report["execution"]["ledger"]
        if ledger != prev["completed_mass_ledger"]:
            raise ValueError("restored original mass ledger differs")
        clock = start
        phase = "FULL_WIRE_ROUNDTRIP"
        with tempfile.TemporaryDirectory(dir=a.out.parent) as td:
            wire = Path(td) / "complete.bin"
            driver.save(wire, state)
            exact_wire = (wire.stat().st_size == prev["final_checkpoint_bytes"]
                          and file_sha256(wire) == prev["final_checkpoint_sha256"])
        if not exact_wire:
            raise ValueError("restored full wire differs")
        print("INITIAL_WIRE_LEDGER_VERIFIED", start, flush=True)
        if budget_trace_snapshot(reset=True)["mode"] != "off":
            raise ValueError("trace mode changed")
        while clock < end:
            target = next_target(clock, end, a.cadence, a.call_span_s)
            if time.perf_counter() - started >= 7200:
                failure = {"class": "WallCap", "message": "original 7200s wall cap", "phase": "ADVANCE"}
                blocked = target
                break
            phase = "ADVANCE"
            tick_start = time.perf_counter()
            try:
                nxt = driver.advance(state, target)
            except Exception as exc:
                failure = {"class": type(exc).__name__, "message": str(exc), "phase": phase}
                blocked = target
                break
            if nxt.time_s != target:
                raise ValueError("returned native clock differs")
            report = driver.report(nxt)
            if (reason := _ledger_error(report, target, population=100000)) is not None:
                raise ValueError("new conservation ledger invalid: " + reason)
            samples = driver.runtime.last_advance_metrics["tick_times_s"]
            if (len(samples) != round((target - clock) / TICK)
                    or any(not math.isfinite(s) or s < 0 for s in samples)):
                raise ValueError("native internal dt sample count differs")
            item = {"start_time_s": clock, "completed_time_s": target,
                    "wall_s": time.perf_counter() - tick_start,
                    "native_tick_wall_s": samples, "native_ticks": len(samples)}
            state, clock, ledger = nxt, target, report["execution"]["ledger"]
            calls.append(item)
            print("RETURNED_PHYSICAL_PREFIX_VALID", json.dumps(item), flush=True)
        if clock > start:
            phase = "SAVE_VALID_PREFIX"
            driver.save(checkpoint, state)
            final_bytes, final_sha = checkpoint.stat().st_size, file_sha256(checkpoint)
        status = ("RESTORE_ONLY_VERIFIED" if a.duration_s == 0 and failure is None else
                  "EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON" if clock == end and failure is None else
                  "BLOCKED_RESOURCE_WITH_VALID_PREFIX" if failure is not None and clock > start else
                  "BLOCKED_RESOURCE" if failure is not None else "INCONCLUSIVE")
    except Exception as exc:
        status = "ERROR"
        failure = {"class": type(exc).__name__, "message": str(exc), "phase": phase}
    if driver is not None:
        try:
            native_metrics = driver.runtime.phase_metrics()
        except Exception as exc:
            native_metrics = {"status": "NOT_OBSERVED", "error": str(exc)}
    r = {
        "schema": SCHEMA, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "case": CASE, "status": status, "error": failure, "blocked_target_time_s": blocked,
        "runner_sha256": file_sha256(Path(__file__)), "start_receipt_sha256": hashlib.sha256(raw).hexdigest(),
        "start_time_s": start, "requested_duration_s": a.duration_s, "requested_end_s": end,
        "completed_time_s": clock, "valid_advanced_duration_s": None if clock is None else clock - start,
        "native_call_cadence": a.cadence, "native_call_span_s": a.call_span_s if a.cadence == "window" else None,
        "physical_dt_s": TICK, "completed_native_calls": calls, "native_phase_metrics": native_metrics,
        "failed_native_call_internal_ticks_receive_physical_credit": False,
        "previous_checkpoint_cross_native": cross, "original_candidate_from_time_zero_verified": False,
        "previous_full_checkpoint_sha256": prev["final_checkpoint_sha256"],
        "previous_checkpoint_full_wire_roundtrip_exact": exact_wire,
        "previous_mass_ledger": initial_ledger, "completed_mass_ledger": ledger,
        "final_checkpoint_sha256": final_sha, "final_checkpoint_bytes": final_bytes,
        "final_checkpoint_local_only": True,
        "current_candidate_source_sha256": source["source_sha256"],
        "current_native_binary_sha256": native["sha256"], "current_source_dirty": source["source_dirty"],
        "current_git_commit": source.get("git_commit"), "current_driver_identity": DRIVER,
        "original_matrix_sha256": MATRIX_SHA, "native_process_cap_bytes": limit,
        "trace_mode": "off", "diagnostic_only": False, "budget_mode": "DEFAULT",
        "original_full_day_acceptance": "BLOCKED_0_OF_9",
        "wall_total_including_full_preparation_and_checkpoint_io_s": time.perf_counter() - started,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
    }
    a.out.write_text(json.dumps(r, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps({k: r[k] for k in ("status", "completed_time_s", "valid_advanced_duration_s",
                                     "blocked_target_time_s", "error", "peak_rss_bytes",
                                     "wall_total_including_full_preparation_and_checkpoint_io_s")}), flush=True)
    return 0 if status in ("RESTORE_ONLY_VERIFIED", "EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON") else 2


if __name__ == "__main__":
    raise SystemExit(main())
