"""Paired original-checkpoint experiment. Experimental output is excluded from release receipts."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
CAP = 8 * 1024**3


def emit(path, **data):
    with path.open("a") as out:
        print(json.dumps(data, allow_nan=False), file=out, flush=True)


def run_child(args):
    from run_v03_prefix import wire_evidence
    from tools.run_v1_local_acceptance import prepare, candidate_provenance, _ledger_error, file_sha256
    from metroflow.v1.native_engine import native_binary_provenance
    from _metroflow_rust import budget_trace_snapshot

    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    actual_cap = min([CAP] + [x for x in (soft, hard) if x != resource.RLIM_INFINITY])
    resource.setrlimit(resource.RLIMIT_AS, (actual_cap, hard))
    reference = json.loads(args.reference.read_text())
    matrix_path = ROOT / "scenarios/v1/release_matrix.json"
    matrix = json.loads(matrix_path.read_text())
    assert file_sha256(matrix_path) == reference["original_matrix_sha256"]
    assert actual_cap == reference["native_process_cap_bytes"] == matrix["limits"]["peak_rss_bytes"]
    assert args.raw.stat().st_size == reference["final_checkpoint_bytes"]
    assert file_sha256(args.raw) == reference["final_checkpoint_sha256"]
    case = next(c for c in matrix["cases"] if c["id"] == reference["case"])
    source = candidate_provenance()
    native = native_binary_provenance()
    assert source["source_dirty"] is False and native["status"] == "MEASURED"
    trace = budget_trace_snapshot(reset=True)
    assert trace["mode"] == args.mode and trace["alloc_counting"]
    emit(args.events, phase="binding", mode=args.mode, source=source["source_sha256"],
         binary=native["sha256"], commit=source["git_commit"], reference_sha=file_sha256(args.reference),
         raw_sha=reference["final_checkpoint_sha256"], address_cap=actual_cap,
         matrix_sha=reference["original_matrix_sha256"], selected_case=case["id"])
    driver, _ = prepare(case, matrix, 10.)
    assert driver.identity == reference["current_driver_identity"]
    state = driver.load(args.raw)
    start = state.time_s
    ledger = driver.report(state)["execution"]["ledger"]
    assert start == reference["completed_time_s"] and ledger == reference["completed_mass_ledger"]
    emit(args.events, phase="restored", time_s=start, original_ledger_exact=True)
    for step in range(1, args.steps + 1):
        target = start + step * 10.
        budget_trace_snapshot(reset=True)
        emit(args.events, phase="attempt", time_s=target)
        clock = time.perf_counter()
        try:
            state = driver.advance(state, target)
        except Exception as error:
            emit(args.events, phase="rejected", target=target, error_type=type(error).__name__,
                 error=str(error), trace=budget_trace_snapshot(reset=False))
            return 3 if isinstance(error, MemoryError) or "budget" in (str(error) + type(error).__name__).lower() else 4
        report = driver.report(state)
        issue = _ledger_error(report, target, population=100000)
        if issue:
            raise ValueError(issue)
        trace = budget_trace_snapshot(reset=False)
        emit(args.events, phase="validated", time_s=target, tick_wall_s=time.perf_counter()-clock,
             ledger=report["execution"]["ledger"], trace=trace)
        if step in args.hash_steps:
            wire = wire_evidence(driver, state, args.events.parent)
            emit(args.events, phase="wire", time_s=target, **wire)
    return 0


def supervise(args):
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists() or args.events.exists():
        raise FileExistsError("choose a new output for each attempt")
    env = dict(os.environ, METROFLOW_BUDGET_TRACE=args.mode, METROFLOW_V1_ENGINE_BACKEND="rust_whole",
               METROFLOW_V1_NATIVE_THREADS="1", METROFLOW_V1_STORAGE_POLICY="bounded_bytes_v1",
               OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    env.pop("METROFLOW_EXPERIMENTAL_ARC_PAIR_BUDGET", None)
    clock = time.monotonic()
    peak = dict(VmPeak=0, VmHWM=0)
    expired = False
    with args.out.with_suffix(".log").open("w") as log:
        child = subprocess.Popen([sys.executable, __file__, *sys.argv[1:], "--child"], env=env,
                                 stdout=log, stderr=subprocess.STDOUT)
        while child.poll() is None:
            try:
                for row in Path(f"/proc/{child.pid}/status").read_text().splitlines():
                    key, _, value = row.partition(":")
                    if key in peak:
                        peak[key] = max(peak[key], int(value.split()[0])*1024)
            except (OSError, ProcessLookupError):
                pass
            if time.monotonic() - clock > args.wall_limit:
                child.kill()
                expired = True
                break
            time.sleep(.2)
        rc = child.wait()
    rows = [json.loads(line) for line in args.events.read_text().splitlines()] if args.events.exists() else []
    complete = [x["time_s"] for x in rows if x["phase"]=="validated"]
    evidence = dict(mode=args.mode, child_exit=rc, wall_limit_hit=expired, wall_s=time.monotonic()-clock,
                    validated_times_s=complete, sampled_process_high_water_bytes=peak,
                    last_event=rows[-1]["phase"] if rows else None, original_release_eligible=False,
                    events=args.events.name, argv=sys.argv[1:])
    args.out.write_text(json.dumps(evidence, indent=2)+"\n")
    print(json.dumps(evidence), flush=True)
    return 0 if rc in (0,3) else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["observe","record"], required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--hash-steps", type=int, nargs="*", default=[1])
    parser.add_argument("--wall-limit", type=int, default=1200)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.steps <= 0 or args.wall_limit <= 0 or any(not 1 <= n <= args.steps for n in args.hash_steps):
        parser.error("invalid experiment horizon")
    args.events = args.out.with_suffix(".jsonl")
    sys.exit(run_child(args) if args.child else supervise(args))
