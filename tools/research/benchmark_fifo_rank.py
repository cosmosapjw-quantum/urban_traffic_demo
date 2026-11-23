"""Bounded adapter benchmark; it does not measure the native traffic engine.

Input JSON accepts {"rows":[{tag,offset,mass,birth,a,b}, ...], ...metadata...}
or a list of row dictionaries/six-element arrays. Optional service_fractions
are used only with --observed-fractions. Default fraction schedules are synthetic
half-service replays on the supplied composition, explicitly labelled as such.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
from pathlib import Path
import time
import tracemalloc
import platform
import metroflow.v1.fifo_rank as adapter_module

from metroflow.v1.fifo_rank import CompositionRoot, RankSpan, SourceRow


def load_rows(path, head_index=0):
    if path is None:
        payload = {"rows": [
            {"tag": 7, "offset": 2, "mass": 2.0, "birth": 6.0, "a": 1.0, "b": 8.0},
            {"tag": 3, "offset": 5, "mass": 3.0, "birth": 21.0, "a": 1.0, "b": 8.0},
            {"tag": 7, "offset": 2, "mass": 1.0, "birth": 2.0, "a": 1.0, "b": 8.0},
        ], "origin": "explicit synthetic three-row control"}
        file_sha = None
    else:
        data = path.read_bytes()
        payload = json.loads(data)
        file_sha = hashlib.sha256(data).hexdigest()
    selected_head = None
    if isinstance(payload, dict) and "heads" in payload:
        if not 0 <= head_index < len(payload["heads"]):
            raise ValueError("head-index outside supplied native samples")
        selected_head = payload["heads"][head_index]
        raw = selected_head["rows"]
    else:
        raw = payload["rows"] if isinstance(payload, dict) else payload
    rows = []
    for row in raw:
        args = ([row[k] for k in ("tag", "offset", "mass", "birth")]
                + [row.get("a"), row.get("b")]) if isinstance(row, dict) else row
        if len(args) != 6:
            raise ValueError("source rows must have six fields")
        tag, offset, mass, birth, a, b = args
        rows.append(SourceRow(tag, offset, float(mass), float(birth), a, b))
    metadata = ({k: v for k, v in payload.items()
                 if k not in ("rows", "heads", "service_fractions")}
                if isinstance(payload, dict) else {})
    if selected_head is not None:
        metadata["selected_head_index"] = head_index
        metadata["selected_head"] = {k: v for k, v in selected_head.items()
                                     if k not in ("rows", "service_fractions")}
    source = selected_head if selected_head is not None else payload
    observed = source.get("service_fractions") if isinstance(source, dict) else None
    return CompositionRoot.from_rows(rows), metadata, file_sha, observed


def schedule(steps, observed=None):
    if observed is not None:
        yield from observed
    else:
        for k in range(steps):
            yield 1.0 / (2 * steps - k)


def measure(fn):
    gc.collect()
    tracemalloc.start()
    started = time.perf_counter()
    value = fn()
    elapsed = time.perf_counter() - started
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return value, {"wall_s": elapsed, "tracemalloc_retained_bytes": current,
                   "tracemalloc_peak_bytes": peak}


def eager(root, steps, keep_every, observed):
    # Reproduce source-remainder mass/birth arithmetic, retaining only sampled
    # immutable old snapshots. This is an arithmetic reference, not native timing.
    rows = [(float(r.mass), float(r.birth)) for r in root.rows]
    snapshots = []
    for k, fraction in enumerate(schedule(steps, observed), 1):
        if not math.isfinite(fraction) or not 0 <= fraction <= 1:
            raise ValueError("nonphysical observed source fraction")
        rows = [(m * (1 - fraction), b * (1 - fraction)) for m, b in rows]
        if keep_every and k % keep_every == 0:
            snapshots.append(rows)
    return rows, len(snapshots)


def rank(root, steps, keep_every, observed):
    span = RankSpan.full(root)
    snapshots = []
    roundoff = 0.0
    max_roundoff = 0.0
    for k, fraction in enumerate(schedule(steps, observed), 1):
        split = span.take_fraction(float(fraction), root.total_mass)
        roundoff += abs(split.roundoff_mass)
        max_roundoff = max(max_roundoff, abs(split.roundoff_mass))
        span = split.remainder
        if keep_every and k % keep_every == 0:
            snapshots.append(span)
    assert all(s.root is root and s.root.rows is root.rows for s in snapshots)
    rows = [(float(r.mass), float(r.birth)) for r in span.iter_rows()]
    return rows, len(snapshots), roundoff, max_roundoff


def keyed(root, pairs):
    values = {}
    for row, pair in zip(root.rows, pairs):
        values.setdefault((row.tag, row.offset), []).append(pair)
    return {key: (math.fsum(v[0] for v in pairs), math.fsum(v[1] for v in pairs))
            for key, pairs in values.items()}


def run(root, steps, keep_every, observed):
    (eager_rows, eager_snapshots), em = measure(lambda: eager(root, steps, keep_every, observed))
    (rank_rows, rank_snapshots, roundoff, max_roundoff), rm = measure(
        lambda: rank(root, steps, keep_every, observed))
    e, r = keyed(root, eager_rows), keyed(root, rank_rows)
    source = keyed(root, [(float(v.mass), float(v.birth)) for v in root.rows])
    differences = [{"tag": k[0], "offset": k[1],
                    "mass_abs": abs(e[k][0] - r[k][0]),
                    "birth_abs": abs(e[k][1] - r[k][1]),
                    "mass_tolerance": 1e-9 * max(1.0, source[k][0]),
                    "birth_tolerance": 1e-8 * max(1.0, source[k][1])}
                   for k in e]
    passed = all(d["mass_abs"] <= d["mass_tolerance"]
                 and d["birth_abs"] <= d["birth_tolerance"] for d in differences)
    if observed is None:
        half_errors = [{"tag": k[0], "offset": k[1],
                        "mass_abs": abs(r[k][0] - source[k][0] / 2),
                        "birth_abs": abs(r[k][1] - source[k][1] / 2)} for k in r]
        passed = passed and all(d["mass_abs"] <= 1e-9 * max(1.0, source[(d["tag"], d["offset"])][0])
                                 and d["birth_abs"] <= 1e-8 * max(1.0, source[(d["tag"], d["offset"])][1])
                                 for d in half_errors)
    else:
        half_errors = None
    return {"subdivisions": steps, "source_rows": len(root.rows),
            "snapshots_kept": {"eager": eager_snapshots, "rank": rank_snapshots},
            "eager": em, "rank": rm,
            "eager_over_rank_wall_ratio": em["wall_s"] / rm["wall_s"],
            "eager_over_rank_peak_ratio": em["tracemalloc_peak_bytes"] / max(1, rm["tracemalloc_peak_bytes"]),
            "max_mass_abs_difference": max((d["mass_abs"] for d in differences), default=0),
            "max_birth_abs_difference": max((d["birth_abs"] for d in differences), default=0),
            "per_key_differences": differences,
            "manual_half_service_oracle_errors": half_errors,
            "rank_roundoff_abs_sum": roundoff, "rank_roundoff_abs_max": max_roundoff,
            "numerically_checked_at_explicit_adapter_tolerances": passed,
            "source_shared_on_every_retained_split": True,
            "eager_row_payloads_constructed": len(root.rows) * (steps + 1),
            "rank_row_payloads_constructed_during_service": 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path)
    p.add_argument("--head-index", type=int, default=0,
                   help="select one full original head from a native heads-list payload")
    p.add_argument("--steps", default="1000,10000,100000")
    p.add_argument("--keep-every", type=int, default=1000)
    p.add_argument("--observed-fractions", action="store_true")
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    if args.keep_every < 0:
        p.error("keep-every must be nonnegative")
    root, metadata, sha, observed = load_rows(args.input, args.head_index)
    if args.observed_fractions:
        if not observed:
            p.error("observed-fractions requires a nonempty service_fractions input")
        steps = [len(observed)]
    else:
        observed = None
        steps = [int(v) for v in args.steps.split(",")]
        if not steps or any(v <= 0 for v in steps):
            p.error("steps must contain positive integers")
    report = {
        "schema": "METROFLOW_CONDITIONAL_FIFO_RANK_ADAPTER_BENCHMARK_V1",
        "input_sha256": sha, "input_metadata": metadata,
        "implementation": {"adapter_sha256":hashlib.sha256(Path(adapter_module.__file__).read_bytes()).hexdigest(), "benchmark_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "python":platform.python_version(), "machine":platform.machine()},
        "fraction_schedule": ("supplied source observations" if observed is not None else
                              "synthetic f_k=1/(2K-k); exact-real final remainder is one half"),
        "arithmetic": "binary64 collapsed rank, not byte identity",
        "tolerance_scope": "per-key mass 1e-9*max(1,source mass), birth first moment 1e-8*max(1,source birth); these are adapter checks, not the city residence-time acceptance test",
        "measurement_scope": "Python remainder adapter only; native event production, node rates, interval overlay and full-day traffic NOT MEASURED",
        "memory_scope": "incremental Python tracemalloc; shared source root predates measurement; not native RSS",
        "timing_scope": "wall time while tracemalloc is enabled; includes allocation-instrumentation overhead and is not native engine timing",
        "runs": [run(root, n, args.keep_every, observed) for n in steps],
        "V03_full_day_evidence": False}
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.out:
        args.out.write_text(text)
    print(text)
    return 0 if all(r["numerically_checked_at_explicit_adapter_tolerances"] for r in report["runs"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
