"""One source-pinned, zero-advance fresh load of the final original CLI checkpoint."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import resource
import tempfile
import time

from tools.run_v1_local_acceptance import prepare, candidate_provenance, _ledger_error, file_sha256
from metroflow.v1.native_engine import native_binary_provenance

SOURCE = "e6a49b7c0cd598ff480a1d3a421fa9e8ae57f227c311d514556a394f137b29db"
NATIVE = "6a6d48c8986ce1ffe1108afa145707b556345f0e7572c7c4f34e7e64b19da808"
MATRIX = "1eb90b60d260feff915b785ed4d425dde0bcc1601ad3ad8200640c73d765655a"
DRIVER = "e77f5efaad25b7df237d91523146baacb8cbe3170bbb86594bdc0885c498fac4"
CASE = "valley_weekday_s7"
CAP = 8589934592

def require(condition, reason):
    if not condition:
        raise ValueError(reason)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli-dir", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--wrapper-exit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    result = {"schema": "V03_FINAL_CLI_FRESH_CHECKPOINT_V1",
              "advanced_physical_time_s": 0, "status": "ERROR",
              "runner_sha256": file_sha256(Path(__file__))}
    phase = "ADMISSION"
    try:
        require(args.wrapper_exit.is_file(), "original worker has not recorded completion")
        result["original_wrapper_exit"] = int(args.wrapper_exit.read_text().strip())
        receipt_path = args.cli_dir / (args.label + ".json")
        if not receipt_path.exists():
            receipt_path = args.cli_dir / (args.label + ".progress.json")
            result["receipt_kind"] = "last_completed_hourly_progress_only"
        else:
            result["receipt_kind"] = "final_worker_receipt"
        raw = receipt_path.read_bytes()
        receipt = json.loads(raw)
        result.update(receipt_path=str(receipt_path),
                      receipt_sha256=hashlib.sha256(raw).hexdigest())
        require(receipt.get("case") == CASE, "case differs")
        for key, value in (("candidate_source_sha256", SOURCE),
                           ("native_binary_sha256", NATIVE),
                           ("matrix_sha256", MATRIX), ("driver_identity", DRIVER)):
            require(receipt.get(key) == value, "original receipt identity differs: " + key)
        require(os.environ.get("METROFLOW_BUDGET_TRACE") == "off", "trace must be off")
        require(os.environ.get("METROFLOW_EXPERIMENTAL_ARC_PAIR_BUDGET") is None,
                "experimental override forbidden")
        os.environ.update(METROFLOW_V1_ENGINE_BACKEND="rust_whole",
                          METROFLOW_V1_NATIVE_THREADS="1",
                          METROFLOW_V1_STORAGE_POLICY="bounded_bytes_v1")
        source, native = candidate_provenance(), native_binary_provenance()
        require(source.get("source_sha256") == SOURCE and source.get("source_dirty") is False,
                "current source differs or is dirty")
        require(native.get("sha256") == NATIVE, "current native differs")
        require(Path(native["path"]).resolve().parent == Path("native_binding").resolve(),
                "wrong native binding directory")
        matrix_path = Path("scenarios/v1/release_matrix.json")
        require(file_sha256(matrix_path) == MATRIX, "original matrix differs")
        matrix = json.loads(matrix_path.read_text())
        require(matrix["population"] == 100000 and matrix["horizon_s"] == 86400
                and matrix["limits"] == {"wall_s": 7200, "peak_rss_bytes": CAP},
                "original acceptance differs")
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        require(hard == resource.RLIM_INFINITY or hard >= CAP, "host hard limit below original cap")
        require(soft == resource.RLIM_INFINITY or soft >= CAP, "host soft limit below original cap")
        resource.setrlimit(resource.RLIMIT_AS, (CAP, hard))
        last = receipt.get("last_valid")
        if last:
            expected_clock, name = last["time_s"], last["path"]
            expected_report = receipt.get("last_valid_report")
        else:
            expected_clock = receipt["simulated_s"]
            name = receipt.get("last_valid_checkpoint", args.label + ".last_valid.bin")
            expected_report = receipt.get("report")
        require(Path(name).name == name, "checkpoint basename required")
        checkpoint = args.cli_dir / name
        require(checkpoint.is_file(), "no durable checkpoint")
        expected_sha = file_sha256(checkpoint)
        expected_bytes = checkpoint.stat().st_size
        expected_ledger = expected_report["execution"]["ledger"] if expected_report else None
        if expected_report:
            require(expected_report["execution"]["time_s"] == expected_clock,
                    "saved report clock differs")
        require(receipt["simulated_s"] == expected_clock, "receipt clocks differ")
        result.update(checkpoint_path=str(checkpoint), checkpoint_sha256=expected_sha,
                      checkpoint_bytes=expected_bytes, expected_time_s=expected_clock,
                      expected_ledger_available=expected_ledger is not None,
                      current_candidate_source_sha256=SOURCE,
                      current_native_binary_sha256=NATIVE, current_git_commit=source["git_commit"],
                      current_source_dirty=False, original_matrix_sha256=MATRIX,
                      driver_identity=DRIVER, process_cap_bytes=CAP, trace_mode="off")
        phase = "PREPARE"
        case = next(c for c in matrix["cases"] if c["id"] == CASE)
        driver, metadata = prepare(case, matrix, 10.0)
        require(driver.identity == DRIVER and driver.plan.totals()["resident_stock"] == 100000,
                "driver/calendar differs")
        for key in ("source_sha256", "patch_sha256"):
            if receipt.get(key):
                require(receipt[key] == metadata[key], "city input differs: " + key)
        phase = "FRESH_LOAD_RESTORE_VALIDATE"
        state = driver.load(checkpoint)
        driver.check(state)
        restored = driver.report(state)
        require(state.time_s == expected_clock, "fresh restored clock differs")
        require(_ledger_error(restored, expected_clock, population=100000) is None,
                "fresh conservation ledger invalid")
        ledger = restored["execution"]["ledger"]
        if expected_ledger is not None:
            require(ledger == expected_ledger, "saved and fresh ledger differ")
        result.update(restored_time_s=state.time_s, restored_mass_ledger=ledger,
                      prior_report_ledger_exact=(ledger == expected_ledger
                                                 if expected_ledger is not None else None))
        phase = "FULL_WIRE_ROUNDTRIP"
        with tempfile.TemporaryDirectory(dir=args.out.parent) as temporary:
            wire = Path(temporary) / "complete.bin"
            driver.save(wire, state)
            require(wire.stat().st_size == expected_bytes and file_sha256(wire) == expected_sha,
                    "full roundtrip bytes differ")
        require(file_sha256(checkpoint) == expected_sha, "input checkpoint changed")
        require(hashlib.sha256(receipt_path.read_bytes()).hexdigest() == result["receipt_sha256"],
                "input receipt changed")
        result.update(status="FRESH_LOAD_RESTORE_VALIDATION_AND_FULL_WIRE_VERIFIED",
                      full_wire_roundtrip_exact=True, error=None)
    except Exception as exc:
        result["error"] = {"class": type(exc).__name__, "message": str(exc), "phase": phase}
    result["wall_s"] = time.perf_counter() - started
    result["peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    args.out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["status"] == "FRESH_LOAD_RESTORE_VALIDATION_AND_FULL_WIRE_VERIFIED" else 2

if __name__ == "__main__":
    raise SystemExit(main())
