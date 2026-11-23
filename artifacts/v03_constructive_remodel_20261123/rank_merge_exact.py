#!/usr/bin/env python3
"""Bounded exact multi-input marked-rank merge and partition-covariance check."""
from fractions import Fraction as Q
from pathlib import Path
from time import perf_counter
import hashlib
import json

MARKS = ("U:red", "U:blue", "V:red", "V:blue")
BIRTH = tuple(map(Q, (1, 2, 0, 3)))
RATE0 = (Q(1), Q(0), Q(1, 4), Q(3, 4))
RATE1 = (Q(0), Q(2), Q(1, 4), Q(3, 4))
COARSE = tuple(map(Q, (4, 5, 6)))
REFINED = tuple(map(Q, (4, "17/4", "19/4", 5, "41/8", "11/2", 6)))

def cumulative(t):
    before = min(Q(1), max(Q(0), t - 4))
    after = min(Q(1), max(Q(0), t - 5))
    return tuple(a * before + b * after for a, b in zip(RATE0, RATE1))

def profiles(partition):
    out, rank = [], Q(0)
    for a, b in zip(partition, partition[1:]):
        dm = tuple(y - x for x, y in zip(cumulative(a), cumulative(b)))
        mass = sum(dm)
        out.append((rank, rank + mass, dm, tuple(m * birth for m, birth in zip(dm, BIRTH))))
        rank += mass
    return out

def prefix(profile, rank):
    mass, birth = [Q(0)] * 4, [Q(0)] * 4
    for a, b, dm, db in profile:
        f = max(Q(0), min(rank, b) - a) / (b - a)
        for i in range(4):
            mass[i] += f * dm[i]
            birth[i] += f * db[i]
    return tuple(mass), tuple(birth)

def rank_time(z):
    return 4 + z / 2 if z <= 2 else 5 + (z - 2) / 3

def encode(x):
    if isinstance(x, Q): return str(x)
    if isinstance(x, dict): return {k: encode(v) for k, v in x.items()}
    if isinstance(x, (tuple, list)): return [encode(v) for v in x]
    return x

def main():
    started = perf_counter()
    coarse, refined = profiles(COARSE), profiles(REFINED)
    queries = tuple(Q(i, 10) for i in range(51))
    previous_u = previous_v = Q(0)
    for z in queries:
        cm, cb = prefix(coarse, z)
        fm, fb = prefix(refined, z)
        direct = cumulative(rank_time(z))
        assert cm == fm == direct
        assert cb == fb == tuple(m * birth for m, birth in zip(direct, BIRTH))
        assert sum(cm) == z
        # Each upstream's own admitted rank remains nondecreasing.
        u, v = cm[0] + cm[1], cm[2] + cm[3]
        assert u >= previous_u and v >= previous_v
        previous_u, previous_v = u, v
    total_mass, total_birth = prefix(coarse, Q(5))
    one_mass, _ = prefix(coarse, Q(1))
    red_exact = one_mass[0] + one_mass[2]
    red_global = (total_mass[0] + total_mass[2]) / 5
    assert red_exact == Q(5, 8) and red_global == Q(3, 10)
    result = {
        "status": "EXACT_RATIONAL_MULTI_INPUT_MERGE_CHECKED",
        "base_commit": "90bfca2c2ddf081cbdf40d11b95ff820837d03b5",
        "scope": "Two upstream prescribed flows, exact same-boundary exchangeable merge. No downstream solver or network complexity bound.",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "marks": MARKS,
        "units": {"rank": "veh", "clock": "s", "birth_moment": "veh*s"},
        "upstream_time_windows": COARSE,
        "rates_per_mark": (RATE0, RATE1),
        "birth_clock_per_mark": BIRTH,
        "coarse_profile": coarse,
        "refined_profile_segments": len(refined),
        "original_profile_segments": len(coarse),
        "query_count": len(queries),
        "exact_scalar_comparisons_mass_and_birth_between_partitions": len(queries) * 8,
        "upstream_fifo_prefix_monotonicity_checked": True,
        "final_mark_mass": total_mass,
        "final_mark_birth": total_birth,
        "prefix_one_mark_mass": one_mass,
        "nonconstant_profile_preserved": True,
        "homogeneous_averaging_counterexample": {"first_one_red_exact": red_exact, "first_one_red_global_average": red_global, "error_veh": red_exact - red_global},
        "wall_s": perf_counter() - started,
    }
    Path(__file__).with_name("MODEL_RANK_MERGE_CALC.json").write_text(json.dumps(encode(result), indent=2) + "\n")
    print(json.dumps(encode(result), indent=2))

if __name__ == "__main__":
    main()
