#!/usr/bin/env python3
"""Measured marked-rank cuts and repeated multi-input merge experiments.

This is a Python exact-rational research benchmark, not a native V03 run.
Each mode uses the same generated source and service schedule. Construction
and all-output moment observation are timed separately. Child processes isolate
peak RSS. tracemalloc includes experiment allocations, not import-time memory.
"""
from __future__ import annotations

import argparse
from collections import deque
from fractions import Fraction as F
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
from time import perf_counter
import tracemalloc

from metroflow.v1.rank_profile_transport import (
    MarkedMass, RankProfile, RankSegment, ServiceWindow,
    concat_adjacent, merge_streams, representation_stats, serve_windows,
    transport_moments,
)


def encode(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    return value


def make_profile(mark_count):
    return RankProfile(tuple(
        RankSegment(tuple(
            MarkedMass(str(i), F((i + j) % 5 + 1),
                       F((i + j) % 5 + 1) * F(i + j, 10))
            for i in range(mark_count)
        ), F(0), (F(0), F(0)))
        for j in range(3)
    ))


def direct_linear_service_moments(profile, start):
    """Closed-form independent oracle for T(z)=start+z at rate1."""
    totals, rank = {}, F(0)
    for segment in profile.segments:
        mean = start + rank + segment.mass / 2
        for part in segment.parts:
            m, b, e = totals.get(part.mark, (F(0), F(0), F(0)))
            totals[part.mark] = (
                m + part.mass, b + part.birth_moment, e + part.mass * mean
            )
        rank += segment.mass
    return totals


def materialize(profile, schedule):
    """Independent mutable head/remnant oracle; deliberately retains cut rows."""
    queue = deque([
        [[part.mark, part.mass, part.birth_moment] for part in segment.parts]
        for segment in profile.segments
    ])
    packets = []
    for window in schedule:
        remaining = window.rate * (window.end - window.start)
        clock = window.start
        while remaining:
            rows = queue[0]
            mass = sum(row[1] for row in rows)
            take = min(remaining, mass)
            fraction = take / mass
            end = clock + take / window.rate
            emitted = tuple(
                (mark, m * fraction, b * fraction) for mark, m, b in rows
            )
            packets.append((clock, end, emitted))
            if take == mass:
                queue.popleft()
            else:
                queue[0] = [[mark, m * (1 - fraction), b * (1 - fraction)]
                            for mark, m, b in rows]
            remaining -= take
            clock = end
    assert not queue
    return packets


def observe_materialized(packets):
    totals = {}
    for first, last, rows in packets:
        if first < 0:
            raise ValueError("arrival boundary is zero in this fixture")
        mean = (first + last) / 2
        for mark, mass, birth in rows:
            m, b, e = totals.get(mark, (F(0), F(0), F(0)))
            totals[mark] = (m + mass, b + birth, e + mass * mean)
    return totals


def cut_worker(size, mark_count, mode):
    tracemalloc.start()
    started = perf_counter()
    profile = make_profile(mark_count)
    step = profile.mass / size
    schedule = tuple(ServiceWindow(
        10 + i * step, 10 + (i + 1) * step, F(1)
    ) for i in range(size))
    input_wall = perf_counter() - started
    started = perf_counter()
    if mode == "views":
        output = serve_windows(profile.view(), schedule, require_complete=True)
    else:
        output = materialize(profile, schedule)
    construct_wall = perf_counter() - started
    gc.collect()
    retained_after_build, build_peak = tracemalloc.get_traced_memory()
    started = perf_counter()
    if mode == "views":
        result = transport_moments(output)
        observed = {
            item.mark: (item.mass, item.birth_moment, item.exit_moment)
            for item in result.marks
        }
    else:
        observed = observe_materialized(output)
    observe_wall = perf_counter() - started
    expected = direct_linear_service_moments(profile, F(10))
    assert observed == expected
    if mode == "views":
        views = tuple(s.view for s in output)
        counts = representation_stats(views)
        joined = concat_adjacent(views)
        assert joined.moments() == profile.view().moments()
        counts["retained_materialized_output_mark_rows"] = 0
        counts["same_parent_concatenated_view_count"] = 1
    else:
        counts = {
            "profile_owners": 1, "stored_profile_segments": len(profile.segments),
            "essential_profile_segments": profile.essential_segments,
            "view_count": 0, "materialized_packet_count": len(output),
            "retained_materialized_output_mark_rows": sum(len(p[2]) for p in output),
            "unique_materialized_output_mark_owners": len({
                id(row) for packet in output for row in packet[2]
            }),
            "profile_dag_depth": 1, "view_profile_depth": 0,
        }
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "status": "EXACT_OBSERVABLES_EQUAL",
        "kind": "cuts", "mode": mode, "cuts": size, "marks": mark_count,
        "physical_fixture_duration_s": profile.mass,
        "input_wall_s": input_wall, "construct_wall_s": construct_wall,
        "observe_all_outputs_wall_s": observe_wall,
        "construct_plus_observe_wall_s": construct_wall + observe_wall,
        "traced_retained_after_build_bytes": retained_after_build,
        "traced_build_peak_bytes": build_peak,
        "traced_final_retained_bytes": current,
        "traced_whole_experiment_peak_bytes": peak,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "owners": counts, "moments": observed,
        "measurement_scope": "Fresh Python process; tracemalloc includes generated profile/schedule/output, excludes import baseline. RSS includes whole process. Exact clock T(z)=10+z; no native solver."
    }


def slow_prefix(profile, amount):
    """Independent sequential source-row restriction, not RankView queries."""
    result = {}
    remaining = amount
    for segment in profile.segments:
        if remaining == 0:
            break
        take = min(remaining, segment.mass)
        fraction = take / segment.mass
        for p in segment.parts:
            m, b = result.get(p.mark, (F(0), F(0)))
            result[p.mark] = (m + fraction * p.mass, b + fraction * p.birth_moment)
        remaining -= take
    assert remaining == 0
    return result


def inverse_two_input_prefix(profile, base, delay, target):
    """Independent W inverse with two uniform total-rate streams."""
    intervals = ((base, base + 1), (base + delay, base + delay + 1))
    edges = sorted({t for pair in intervals for t in pair})
    cumulative = F(0)
    time = edges[0]
    for first, last in zip(edges, edges[1:]):
        rate = sum(profile.mass for a, b in intervals if a <= first < b)
        next_mass = cumulative + rate * (last - first)
        if target <= next_mass and rate:
            time = first + (target - cumulative) / rate
            break
        cumulative = next_mass
    result = {}
    for a, b in intervals:
        amount = profile.mass * min(F(1), max(F(0), time - a))
        for mark, (m, birth) in slow_prefix(profile, amount).items():
            old_m, old_b = result.get(mark, (F(0), F(0)))
            result[mark] = (old_m + m, old_b + birth)
    return {mark: values for mark, values in result.items() if values[0]}


def merge_worker(levels):
    tracemalloc.start()
    profile = RankProfile((
        RankSegment((MarkedMass("r", 1, 1),), 0, (0, 0)),
        RankSegment((MarkedMass("b", 1, 2),), 0, (0, 0)),
    ))
    history = []
    accumulated = 0.0
    for level in range(1, levels + 1):
        base, delay = F(2 * level + 2), F(1, 2 * level + 3)
        left = serve_windows(profile.view(), (
            ServiceWindow(base, base + 1, profile.mass),
        ), require_complete=True)
        right = serve_windows(profile.view(), (
            ServiceWindow(base + delay, base + delay + 1, profile.mass),
        ), require_complete=True)
        started = perf_counter()
        merged = merge_streams((left, right), target_at_end=lambda t: F(0))
        wall = perf_counter() - started
        accumulated += wall
        # Distinct scalar source rows drive an independently inverted W(t).
        checked = 0
        for fraction in (F(0), F(1, 7), F(1, 2), F(6, 7), F(1)):
            rank = merged.mass * fraction
            actual = merged.view(0, rank).moments()
            expected = inverse_two_input_prefix(profile, base, delay, rank)
            assert actual == expected
            checked += 1
        history.append({
            "level": level, "input_segments_per_stream": len(profile.segments),
            "output_stored_segments": len(merged.segments),
            "output_essential_segments": merged.essential_segments,
            "output_mass_veh": merged.mass, "merge_wall_s": wall,
            "exact_prefix_queries": checked,
        })
        profile = merged
        del left, right, merged
    gc.collect()
    retained, peak = tracemalloc.get_traced_memory()
    counts = representation_stats((profile.view(),))
    final = profile.view().moments()
    tracemalloc.stop()
    return {
        "status": "EXACT_MULTI_INPUT_PREFIXES_EQUAL",
        "kind": "merges", "levels": levels,
        "accumulated_merge_wall_s": accumulated,
        "traced_retained_state_and_receipt_bytes": retained,
        "traced_peak_bytes": peak,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "owners": counts, "history": history, "final_moments": final,
        "measurement_scope": "Repeated two-input phase-shifted merge; both input streams duplicate the preceding cohort measure, so mass and number of source streams grow. Physical knots are kept; no fixed-demand or native scaling claim.",
    }


def orchestrate(args):
    root = Path(__file__).resolve().parents[2]
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    module = root / "src/metroflow/v1/rank_profile_transport.py"
    report = {
        "status": "RUNNING",
        "source_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python": sys.version, "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "scope": "Exact-rational reference, no native V03 or full-day readiness credit.",
        "worker_timeout_s": args.timeout,
        "cut_results": [], "merge_results": [],
    }
    def save():
        out.write_text(json.dumps(encode(report), indent=2) + "\n")
    save()
    cases = [("cuts", mode, n) for n in args.cuts for mode in ("views", "materialized")]
    cases += [("merges", "views", n) for n in args.merge_levels]
    for kind, mode, size in cases:
        name = f"R7_rank_{kind}_{mode}_{size}"
        command = [
            sys.executable, str(Path(__file__).resolve()),
            "--worker", kind, "--mode", mode, "--size", str(size),
            "--marks", str(args.marks),
        ]
        started = perf_counter()
        try:
            process = subprocess.run(command, text=True, capture_output=True,
                                     timeout=args.timeout, cwd=root)
            raw = "COMMAND: " + " ".join(command) + "\nEXIT: " + str(process.returncode)
            raw += "\nWALL_S: " + str(perf_counter() - started)
            raw += "\nSTDOUT:\n" + process.stdout + "\nSTDERR:\n" + process.stderr
            (out.parent / (name + ".txt")).write_text(raw)
            if process.returncode:
                report["status"] = "FAILED_WORKER"
                report["failed_case"] = name
                save()
                raise RuntimeError(f"{name} failed; see raw receipt")
            result = json.loads(process.stdout)
        except subprocess.TimeoutExpired as exc:
            report["status"] = "BOUNDED_TIMEOUT"
            report["failed_case"] = name
            (out.parent / (name + ".txt")).write_text(
                "COMMAND: " + " ".join(command) + "\nTIMEOUT_S: " + str(args.timeout)
                + "\n" + str(exc)
            )
            save()
            print(json.dumps(encode(report)))
            return 2
        result["process_wall_s"] = perf_counter() - started
        (out.parent / (name + ".json")).write_text(json.dumps(result, indent=2) + "\n")
        report["cut_results" if kind == "cuts" else "merge_results"].append(result)
        save()
        print(f"{name}: {result['status']} process_wall={result['process_wall_s']:.6f}s", flush=True)
    for n in args.cuts:
        pair = [r for r in report["cut_results"] if r["cuts"] == n]
        assert pair[0]["moments"] == pair[1]["moments"]
    report["status"] = "BOUNDED_EXACT_REFERENCE_EXPERIMENTS_COMPLETE"
    save()
    print("REPORT", out)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=("cuts", "merges"))
    parser.add_argument("--mode", choices=("views", "materialized"), default="views")
    parser.add_argument("--size", type=int, default=1000)
    parser.add_argument("--marks", type=int, default=8)
    parser.add_argument("--cuts", type=int, nargs="+", default=(1000, 8000, 32000))
    parser.add_argument("--merge-levels", type=int, nargs="+", default=(1, 2, 4, 6, 8))
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--output", default="artifacts/v03_constructive_remodel_20261123/R7_rank_experiments.json")
    args = parser.parse_args()
    if args.size < 1 or args.marks < 1 or any(n < 1 for n in (*args.cuts, *args.merge_levels)):
        parser.error("positive experiment sizes required")
    if args.worker == "cuts":
        print(json.dumps(encode(cut_worker(args.size, args.marks, args.mode))))
        return 0
    if args.worker == "merges":
        print(json.dumps(encode(merge_worker(args.size))))
        return 0
    return orchestrate(args)


if __name__ == "__main__":
    raise SystemExit(main())
