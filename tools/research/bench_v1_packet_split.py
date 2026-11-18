#!/usr/bin/env python3
"""Bounded *scoped* benchmark of one congested V1Road partial-service step.

No production changes, whole-city claims, or altered model assumptions.
Repeatedly restores the same input checkpoint; restore is excluded from timing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import time
from pathlib import Path

from _metroflow_rust import V1Road


def make_probe(tags: int) -> V1Road:
    road = V1Road(
        "research-partial-service-v1", 1.0,
        [[30.0, 20.0, 100.0, 0.5, 1000.0, 1.0]],
        [None],
        [([0], 0) for _ in range(tags)],
        [[20.0, 1.0, 2.0, 3.0, 2.0, 1.0, 4.0, 0.5, 0.2, 0.3, 4.0, 10.0, 6.0]],
        [[0]], [], 200000, 200000, True,
    )
    road.configure_storage_budget(128 * 1024 ** 2)
    road.step(1.0, [(i, 0.25, 0.0, None, None) for i in range(tags)])
    for _ in range(3):
        road.step(1.0, [])
    return road


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=150)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--tags", type=int, default=128)
    args = parser.parse_args()
    if min(args.repeats, args.trials, args.tags) < 1:
        parser.error("positive workload parameters required")
    road = make_probe(args.tags)
    baseline = road.snapshot()
    if road.packet_storage_counts()[2] != args.tags:
        raise RuntimeError("fixture did not retain all tagged parts")
    result_samples = []
    digest = None
    for _trial in range(args.trials):
        ns = []
        for _ in range(args.repeats):
            road.restore(baseline)
            start = time.perf_counter_ns()
            events = road.step(1.0, [])
            ns.append(time.perf_counter_ns() - start)
            if len(events) != args.tags:
                raise RuntimeError("not a partial-service workload")
        outcome = (road.snapshot(), events)
        observed_hash = hashlib.sha256(repr(outcome).encode("utf-8")).hexdigest()
        if digest is not None and digest != observed_hash:
            raise RuntimeError("nondeterministic public state or event record")
        digest = observed_hash
        result_samples.append({
            "median_step_ns": statistics.median(ns),
            "mean_step_ns": statistics.mean(ns),
            "p90_step_ns": sorted(ns)[int(0.9 * (len(ns) - 1))],
        })
    result = {
        "script": "tools/research/bench_v1_packet_split.py",
        "fixture": "one cell, 0.5 veh/s exit, 128 MiB cap, partial FIFO",
        "tags": args.tags, "repeats": args.repeats, "trials": args.trials,
        "python": platform.python_version(), "processor": platform.processor(),
        "checkpoint_sha256_repr": hashlib.sha256(repr(baseline).encode()).hexdigest(),
        "after_step_sha256_repr": digest,
        "packet_counts_before": make_probe(args.tags).packet_storage_counts(),
        "median_of_trial_medians_ns": statistics.median(s["median_step_ns"] for s in result_samples),
        "samples": result_samples,
        "interpretation": "only a small, identical-input 1-tick hot-path benchmark; not 24h or network-level measurement",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "median_step_us": round(result["median_of_trial_medians_ns"] / 1000, 4),
        "checksum": digest, "n": args.tags, "repeats": args.repeats,
    }))


if __name__ == "__main__":
    main()
