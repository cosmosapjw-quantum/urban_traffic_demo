"""Continue one bound checkpoint for numerical diagnosis, never full acceptance."""
import argparse
import json
import os
from pathlib import Path
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from tools.run_v1_local_acceptance import (
    atomic_json, candidate_provenance, file_sha256, observed_environment,
    peak_rss_bytes, prepare,
)
from metroflow.v1.native_engine import native_binary_provenance
from metroflow.active_suffix.common import BudgetExceeded


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-progress", type=Path, required=True)
    p.add_argument("--end-s", type=float, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--native-threads", type=int, default=1)
    args = p.parse_args()
    if not 1 <= args.native_threads <= 256:
        p.error("--native-threads must be in 1..256")
    source = json.loads(args.source_progress.read_text())
    matrix_path = ROOT / "scenarios/v1/release_matrix.json"
    assert file_sha256(matrix_path) == source["matrix_sha256"]
    assert source["simulated_s"] <= args.end_s <= source["simulated_s"] + 600
    matrix = json.loads(matrix_path.read_text())
    case = next(c for c in matrix["cases"] if c["id"] == source["case"])
    checkpoint = args.source_progress.parent / source["last_valid_checkpoint"]
    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    os.environ.update(METROFLOW_V1_ENGINE_BACKEND="rust_whole",
        METROFLOW_V1_ROUTING_BACKEND="rust", METROFLOW_V1_NATIVE_THREADS=str(args.native_threads),
        METROFLOW_V1_STORAGE_POLICY="bounded_bytes_v1")
    started = time.perf_counter()
    driver, row = prepare(case, matrix, 10.)
    assert driver.identity == source["driver_identity"]
    state = driver.load(checkpoint)
    assert state.time_s == source["simulated_s"]
    result = dict(status="RUNNING", case=source["case"], start_s=state.time_s,
        requested_end_s=args.end_s, native_threads=args.native_threads,
        full_campaign="NOT_RUN_DIAGNOSTIC",
        source_progress_sha256=file_sha256(args.source_progress),
        input_checkpoint_sha256=file_sha256(checkpoint),
        matrix_sha256=source["matrix_sha256"], driver_identity=driver.identity,
        source_inputs=row, candidate=candidate_provenance(),
        runner_sha256=file_sha256(Path(__file__)),
        native_binary=native_binary_provenance(), environment=observed_environment())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(args.out, result)
    began = time.perf_counter()
    try:
        state = driver.advance(state, args.end_s)
        result["status"] = "ADVANCED_SCOPED"
    except (BudgetExceeded, ArithmeticError, ValueError, RuntimeError) as error:
        state = error.checkpoint
        result.update(status="NUMERICAL_ERROR" if isinstance(error, ArithmeticError)
            else "BLOCKED_RESOURCE" if isinstance(error, BudgetExceeded) else "BLOCKED",
            reason=str(error))
    result.update(advance_wall_s=time.perf_counter()-began, simulated_s=state.time_s,
        debug=driver.debug_state(state), report=driver.report(state),
        native_metrics=driver.runtime.last_advance_metrics)
    output_checkpoint = args.out.with_suffix(".checkpoint.bin")
    driver.save(output_checkpoint, state)
    result.update(last_valid_checkpoint=output_checkpoint.name,
        checkpoint_sha256=file_sha256(output_checkpoint),
        wall_s=time.perf_counter()-started, peak_rss_bytes=peak_rss_bytes())
    atomic_json(args.out, result)
    print(json.dumps({k: result.get(k) for k in ("status", "simulated_s", "reason",
        "advance_wall_s", "peak_rss_bytes")}), flush=True)
    return 0 if result["status"] == "ADVANCED_SCOPED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
