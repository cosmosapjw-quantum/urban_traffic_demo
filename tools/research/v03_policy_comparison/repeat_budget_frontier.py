"""Repeat a validated larger-budget tick and retain its exact native checkpoint."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
from tempfile import TemporaryDirectory
import time

from compare_internal_budget import GiB, PHYSICAL_KEYS, build_driver, compare_physics, digest, rebind


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "raw", "reference", "trial", "output", "checkpoint"):
        parser.add_argument("--"+name, required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.checkpoint.exists():
        raise FileExistsError("refusing to replace an existing receipt or checkpoint")
    records = [json.loads(line) for line in args.trial.read_text().splitlines()]
    trial = next(row for row in records if row["phase"] == "bound")
    final = [row for row in records if row["phase"] == "validated"][-1]
    budget = trial["budget"]
    assert budget == 15*GiB//2 and trial["outer_bytes"] == 8*GiB
    resource.setrlimit(resource.RLIMIT_AS, (8*GiB, 8*GiB))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    sys.path[:0] = [str(args.repo), str(args.repo/"src")]
    from tools.research.run_v03_prefix import wire_evidence
    from tools.run_v1_local_acceptance import _ledger_error
    from metroflow.v1.native_engine import native_binary_provenance
    from _metroflow_rust import budget_trace_snapshot

    t0 = time.monotonic()
    assert native_binary_provenance()["sha256"] == trial["native"]["sha256"]
    assert digest(args.reference) == trial["reference_sha256"]
    matrix_path = args.repo/"scenarios/v1/release_matrix.json"
    assert digest(matrix_path) == trial["matrix_sha256"]
    assert budget_trace_snapshot(reset=True)["mode"] == "record"
    assert os.getenv("METROFLOW_TRACE_SOURCE_ATTRIBUTION") == trial["source_attribution"]
    reference = json.loads(args.reference.read_text())
    matrix = json.loads(matrix_path.read_text())
    case = next(row for row in matrix["cases"] if row["id"] == trial["case"])
    driver = build_driver(case, matrix, budget)
    with TemporaryDirectory(dir=args.output.parent) as folder:
        raw = Path(folder)/"rebound.bin"
        binding = rebind(args.raw, raw, budget, reference["final_checkpoint_sha256"])
        orig_binding = next(row for row in records if row["phase"] == "rebound")
        assert all(orig_binding[k] == v for k, v in binding.items())
        assert binding["new_native_identity"] == driver.runtime.identity
        state = driver.load(raw)
        compare_physics(driver.report(state)["execution"], reference["final_execution_report"])
    completed = []
    for target in (r["time_s"] for r in records if r["phase"] == "validated"):
        state = driver.advance(state, target)
        report = driver.report(state)
        issue = _ledger_error(report, target, population=100000)
        if issue:
            raise ValueError(issue)
        actual = next(r["physical"] for r in records if r.get("time_s") == target and r["phase"] == "validated")
        compare_physics(report["execution"], actual)
        completed.append(target)
    assert completed[-1] == state.time_s == final["time_s"]
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    wire = wire_evidence(driver, state, args.checkpoint.parent, args.checkpoint)
    with gzip.open(args.checkpoint, "rb") as restored:
        raw_hash = hashlib.file_digest(restored, "sha256").hexdigest()
    assert raw_hash == wire["raw_sha256"]
    args.output.write_text(json.dumps(dict(schema="metroflow.research.budget-checkpoint-repeat.v1",
        native_sha256=trial["native"]["sha256"], trial_sha256=digest(args.trial),
        script_sha256=digest(Path(__file__)), matrix_sha256=trial["matrix_sha256"],
        internal_bytes=budget, outer_bytes=8*GiB, input_bindings=binding, reached_s=completed,
        compared_physical_fields=PHYSICAL_KEYS, wire=wire, gunzip_rehash=True,
        release_eligible=False, wall_s=time.monotonic()-t0,
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024), indent=2)+"\n")


if __name__ == "__main__":
    main()
