#!/usr/bin/env python3
"""Exact bounded FIFO marked-rank construction. No native solver imports."""
from fractions import Fraction as Q
from pathlib import Path
from time import perf_counter
import hashlib
import json

GROUPS = ("red", "blue")
SEGMENTS = (
    {"mass": (Q(2), Q(1)), "birth": (Q(0), Q(0)), "target_m": Q(10)},
    {"mass": (Q(1), Q(3)), "birth": (Q(1, 2), Q(1)), "target_m": Q(10)},
    {"mass": (Q(2), Q(1)), "birth": (Q(2), Q(3, 2)), "target_m": Q(10)},
)
RATES = tuple(map(Q, (0, "1/2", "3/2", 2, 0, "1/3", "5/3", 1, 2, 1)))
START_S = Q(3)
CAPACITY = Q(2)
TOTAL = sum(sum(s["mass"]) for s in SEGMENTS)
ZERO = (Q(0), Q(0))

def add(a, b):
    return tuple(x + y for x, y in zip(a, b))

def materialized_fifo():
    # Independent mutable packet oracle: reproduce proportional head splitting.
    queue = [{"mass": list(s["mass"]), "birth": list(s["birth"])} for s in SEGMENTS]
    cumulative_mass, cumulative_birth, cumulative_exit = ZERO, ZERO, ZERO
    t, rank = START_S, Q(0)
    result = []
    partial_events = 0
    for q in RATES:
        remaining, clock = q, t
        while remaining:
            packet = queue[0]
            total = sum(packet["mass"])
            take = min(remaining, total)
            fraction = take / total
            duration = take / q
            emitted_mass = tuple(x * fraction for x in packet["mass"])
            emitted_birth = tuple(x * fraction for x in packet["birth"])
            emitted_exit = tuple(x * (clock + duration / 2) for x in emitted_mass)
            cumulative_mass = add(cumulative_mass, emitted_mass)
            cumulative_birth = add(cumulative_birth, emitted_birth)
            cumulative_exit = add(cumulative_exit, emitted_exit)
            packet["mass"] = [x * (1 - fraction) for x in packet["mass"]]
            packet["birth"] = [x * (1 - fraction) for x in packet["birth"]]
            if take == total:
                queue.pop(0)
            else:
                partial_events += 1
            remaining -= take
            rank += take
            clock += duration
        result.append((rank, cumulative_mass, cumulative_birth, cumulative_exit))
        t += 1
    assert not queue
    return result, partial_events

def immutable_rank_tape():
    # No mutation, emitted Part rows, or dynamic head-remainder calculation.
    # Prefix measures are computed on the original three marked intervals.
    intervals, left = [], Q(0)
    for s in SEGMENTS:
        mass = sum(s["mass"])
        intervals.append((left, left + mass, s))
        left += mass
    cumulative_mass, cumulative_birth, cumulative_exit = ZERO, ZERO, ZERO
    rank, t = Q(0), START_S
    result, views = [], []
    for q in RATES:
        end = rank + q
        for lo, hi, segment in intervals:
            a, b = max(rank, lo), min(end, hi)
            if a >= b:
                continue
            total = hi - lo
            dm = tuple(x * (b - a) / total for x in segment["mass"])
            db = tuple(x * (b - a) / total for x in segment["birth"])
            # t(z) is affine during this constant-service interval.
            t_mean = t + ((a + b) / 2 - rank) / q
            de = tuple(x * t_mean for x in dm)
            cumulative_mass = add(cumulative_mass, dm)
            cumulative_birth = add(cumulative_birth, db)
            cumulative_exit = add(cumulative_exit, de)
        if q:
            views.append((rank, end))
        rank, t = end, t + 1
        result.append((rank, cumulative_mass, cumulative_birth, cumulative_exit))
    assert all(a[1] == b[0] for a, b in zip(views, views[1:]))
    assert views[0][0] == 0 and views[-1][1] == TOTAL
    return result, views, len(intervals)

def encode(x):
    if isinstance(x, Q):
        return str(x)
    if isinstance(x, dict):
        return {k: encode(v) for k, v in x.items()}
    if isinstance(x, (tuple, list)):
        return [encode(v) for v in x]
    return x

def main():
    started = perf_counter()
    oracle, partial_events = materialized_fifo()
    tape, views, segment_count = immutable_rank_tape()
    assert all(0 <= q <= CAPACITY for q in RATES)
    assert oracle == tape
    assert oracle[-1][0] == TOTAL
    expected_mass = tuple(sum(s["mass"][g] for s in SEGMENTS) for g in range(2))
    expected_birth = tuple(sum(s["birth"][g] for s in SEGMENTS) for g in range(2))
    assert oracle[-1][1] == expected_mass
    assert oracle[-1][2] == expected_birth
    for row in oracle:
        assert sum(row[1]) == row[0]
        assert 0 <= row[0] <= TOTAL
    # Bounded falsifier of homogeneous global averaging, not of rank profiles.
    exact_prefix_red = SEGMENTS[0]["mass"][0] / sum(SEGMENTS[0]["mass"])
    mean_prefix_red = expected_mass[0] / TOTAL
    assert exact_prefix_red - mean_prefix_red == Q(1, 6)
    # Different source compositions genuinely occur; old proportional merge fails.
    compositions = [tuple(m / sum(s["mass"]) for m in s["mass"]) for s in SEGMENTS]
    assert compositions[0] != compositions[1] and compositions[1] != compositions[2]
    final = oracle[-1]
    residence = tuple(e - b for e, b in zip(final[3], final[2]))
    payload = {
        "status": "EXACT_RATIONAL_BOUNDED_CONSTRUCTION_VERIFIED",
        "scope": "Prescribed causal scalar service; finite marked FIFO profile. Not native V03 or network complexity evidence.",
        "base_commit": "90bfca2c2ddf081cbdf40d11b95ff820837d03b5",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "units": {"mass": "veh", "birth_moment": "veh*s", "exit_moment": "veh*s", "target": "m", "rate": "veh/s"},
        "input": {"segments": SEGMENTS, "service_rates": RATES, "one_window_s": Q(1), "service_start_s": START_S, "all_input_ready_at_start": True, "capacity_veh_s": CAPACITY},
        "windows": [{"end_s": START_S + i + 1, "discharged_rank": row[0], "group_mass": row[1], "group_birth": row[2], "group_exit": row[3]} for i, row in enumerate(oracle)],
        "comparison": {"oracle_equals_tape_every_window": oracle == tape, "windows": len(oracle), "independent_scalar_equalities": len(oracle) * 7, "total_mass": TOTAL, "final_group_mass": final[1], "final_group_birth": final[2], "final_group_exit": final[3], "final_group_residence": residence, "zero_service_windows": sum(q == 0 for q in RATES), "materialized_partial_events": partial_events},
        "representation": {"immutable_input_profile_segments": segment_count, "nonzero_output_views": len(views), "contiguous_concatenation": (views[0][0], views[-1][1]), "retained_internal_profile_segments": segment_count, "uniform_composition_merges_possible_between_neighbors": 0, "native_allocation_or_speedup_measurement": False},
        "bounded_closure_counterexample": {"query_prefix_veh": Q(1), "exact_red_veh": exact_prefix_red, "global_mean_red_veh": mean_prefix_red, "absolute_error_veh": exact_prefix_red - mean_prefix_red, "interpretation": "Total/group/birth conservation alone does not identify FIFO prefix composition."},
        "wall_s": perf_counter() - started,
    }
    output = Path(__file__).with_name("MODEL_RANK_CALC.json")
    output.write_text(json.dumps(encode(payload), indent=2) + "\n")
    print(json.dumps(encode({"status": payload["status"], "comparison": payload["comparison"], "representation": payload["representation"], "counterexample": payload["bounded_closure_counterexample"], "wall_s": payload["wall_s"], "json": output.name}), indent=2))

if __name__ == "__main__":
    main()
