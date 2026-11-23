"""Reproducible lightweight calculations for the theory-only R1--R10 packet.

Pure Python standard library. No MetroFlow import, city run, native build,
performance claim, or production algorithm implementation is involved.
"""
from __future__ import annotations

from decimal import Decimal as D, getcontext
from fractions import Fraction as F
from math import exp, sqrt
from pathlib import Path
import hashlib
import json
import platform
import time

getcontext().prec = 60
started = time.perf_counter()


def add(*vectors):
    return tuple(sum(items, F(0)) for items in zip(*vectors))


def scale(a, vector):
    return tuple(a * x for x in vector)


u = (tuple(map(F, (4, 2, 0))), tuple(map(F, (8, 10, 0))))
v = (tuple(map(F, (0, 2, 2))), tuple(map(F, (0, 12, 16))))
ribbons = [
    (F(10), F(12), scale(F(1, 2), u[0]), scale(F(1, 2), u[1])),
    (F(12), F(14), scale(F(1, 2), u[0]), scale(F(1, 2), u[1])),
    (F(11), F(13), v[0], v[1]),
]
slabs = []
for a, b in zip(range(10, 14), range(11, 15)):
    mass = tuple(F(0) for _ in range(3))
    birth = tuple(F(0) for _ in range(3))
    for left, right, m, bm in ribbons:
        overlap = max(F(0), min(F(b), right) - max(F(a), left))
        coefficient = overlap / (right - left)
        mass, birth = add(mass, scale(coefficient, m)), add(birth, scale(coefficient, bm))
    slabs.append({"a": a, "b": b, "mass": mass, "birth": birth})
assert add(*(s["mass"] for s in slabs)) == add(u[0], v[0])
assert add(*(s["birth"] for s in slabs)) == add(u[1], v[1])
head = slabs[1]
total = sum(head["mass"])
beta = ((head["mass"][0] + head["mass"][2]) / total, head["mass"][1] / total)
rate = min(F(4), F(2) / beta[0], F(1) / beta[1])
duration = F(3, 7)
fraction = rate * duration / total
served_m = scale(fraction, head["mass"])
served_b = scale(fraction, head["birth"])
assert beta == (F(4, 7), F(3, 7))
assert rate == F(7, 3) and fraction == F(2, 7)
assert served_m == (F(2, 7), F(3, 7), F(2, 7))
assert served_b == (F(4, 7), F(17, 7), F(16, 7))

# Lossless physical quotient/fiber worked example.
qm = tuple(map(F, (3, 1, 2, 2)))
qb = tuple(map(F, (6, 4, 2, 10)))
first_m, first_b = scale(F(1, 4), qm), scale(F(1, 4), qb)
persons = 2 * first_m[0] + first_m[1]
cargo = 400 * first_m[2] + 600 * first_m[3]
merged_m = (first_m[0], first_m[1] + 2)
merged_b = (first_b[0], first_b[1] + 12)
fiber = tuple(x / sum(merged_m) for x in merged_m)
assert persons == F(7, 4) and cargo == 500
assert fiber == (F(1, 4), F(3, 4))
assert scale(F(1, 2), merged_m) == (F(3, 8), F(9, 8))
assert scale(F(1, 2), merged_b) == (F(3, 4), F(13, 2))

# A Mixed head must retain the joint label/time measure, not detached clocks.
mixed_a = ((F(1), F(1, 2)), (F(2), F(3, 2)))
mixed_b = ((F(1), F(3, 2)), (F(2), F(1, 2)))
assert sum(m for _, m in mixed_a) == sum(m for _, m in mixed_b) == 2
mixed_query = tuple(sum(m for t, m in rows if t <= F(3, 2)) for rows in (mixed_a, mixed_b))
assert mixed_query == (F(1, 2), F(3, 2))

# Equal mass and first age moment do not determine eligibility.
ages = (((F(0), F(1, 2)), (F(2), F(1, 2))), ((F(1), F(1)),))
age_moments = [tuple(sum(w * a**k for a, w in row) for k in range(2)) for row in ages]
eligible = [sum(w for a, w in row if a >= F(3, 2)) for row in ages]
assert age_moments == [(F(1), F(1)), (F(1), F(1))]
assert eligible == [F(1, 2), F(0)]

# Two explicit null directions realize the positive feature-elimination proof.
points = tuple(F(i, 4) for i in range(5))
weights = [F(1, 5)] * 5
feature = lambda ws: tuple(sum(w * p**k for p, w in zip(points, ws)) for k in range(3))
original_features = feature(weights)
elimination = []
for direction in ((1, -3, 3, -1, 0), (1, -2, 0, 2, -1)):
    assert all(sum(F(a) * p**k for a, p in zip(direction, points)) == 0 for k in range(3))
    amount = min(w / a for w, a in zip(weights, direction) if a > 0)
    weights = [w - amount * a for w, a in zip(weights, direction)]
    assert min(weights) >= 0 and feature(weights) == original_features
    elimination.append({"amount": amount, "weights": list(weights)})
assert weights == [F(0), F(2, 3), F(0), F(0), F(1, 3)]
original_cubic = sum(p**3 / 5 for p in points)
new_cubic = sum(w * p**3 for p, w in zip(points, weights))
cubic_error = abs(new_cubic - original_cubic)
assert cubic_error == F(1, 32)
# g=p^3, matched-feature approximation g0=(3/2)p^2-(1/2)p.
# max|g-g0|=sqrt(3)/36 on [0,1], from its two stationary points.
residual = sqrt(3) / 36
assert float(cubic_error) <= 2 * residual

# The all-at-once reset counterexample is exact at an intermediate time.
epsilon = F(1, 100)
query_time = 1 + epsilon / 2
jump_values = (int(query_time >= 1), int(query_time >= 1 + epsilon))
assert jump_values == (1, 0)

# Initial eligible stock needs the empty-history capacity candidate.
initial_stock = F(2)
stock_samples = []
for t in (F(0), F(1, 2), F(1), F(2)):
    # E=2+t, C=3t. E-C=2-2t, so infimum occurs at t.
    raw_candidate = initial_stock + t
    proper_departure = min(3 * t, raw_candidate)
    stock_samples.append({"t": t, "raw_empty_queue_formula": raw_candidate, "departure": proper_departure})
assert stock_samples[0]["departure"] == 0 and stock_samples[0]["raw_empty_queue_formula"] == 2

# Decimal verifies analytic flux moments under a small refinement experiment.
true_moment = D(1) + (-D(2)).exp()
refinement = []
for n in (1, 2, 4, 8, 16, 32):
    h = D(2) / n
    mid = sum(h * (1 - (-(D(i) + D("0.5")) * h).exp()) for i in range(n))
    integral_parts = sum(h + (-(D(i) + 1) * h).exp() - (-D(i) * h).exp() for i in range(n))
    assert abs(integral_parts - true_moment) < D("1e-56")
    error = abs(mid - true_moment)
    bound = D(2) * h**2 / 24  # r=1, T=2, sup|v''|<=1
    assert error <= bound
    refinement.append({"pieces": n, "midpoint_error": str(error), "curvature_bound": str(bound),
                       "integral_subdivision_residual": str(abs(integral_parts - true_moment))})
ratios = [D(a["midpoint_error"]) / D(b["midpoint_error"]) for a, b in zip(refinement, refinement[1:])]

# General latent phases, including the lambda=0 limiting branch.
def latent_integral(a, b, p0, target, lam):
    if lam == 0:
        return p0 * (b - a)
    return target * (b - a) + (p0 - target) * (-lam * a).exp() * (1 - (-lam * (b-a)).exp()) / lam

latent_residuals = []
for lam in (D(0), D("0.1"), D(2)):
    p0, target, a, split, b = D("0.2"), D("0.7"), D("0.3"), D("0.9"), D("1.7")
    whole = latent_integral(a, b, p0, target, lam)
    pieces = latent_integral(a, split, p0, target, lam) + latent_integral(split, b, p0, target, lam)
    assert abs(whole-pieces) < D("1e-56")
    latent_residuals.append({"lambda": str(lam), "residual": str(abs(whole-pieces))})

# Guard algebra is a counterfactual cost identity, not a new runtime result.
terms = dict(base=2602210912, events=1485159656, incoming=950538768, index=13723920)
allowance = 5025214575
assert sum(terms.values()) == 5051633256
assert sum(terms.values()) - terms["index"] - allowance == 12694761
payload_difference = 923664448 - 464781312
assert payload_difference == 458883136

def encode(value):
    if isinstance(value, F):
        return str(value)
    raise TypeError(type(value).__name__)

receipt = {
    "status": "NUMERICALLY_CHECKED_THEORETICAL_INSTANCES",
    "scope": "small exact-rational and high-precision mathematical calculations only",
    "production_change": "NOT_RUN", "native_city_execution": "NOT_RUN",
    "python": platform.python_version(),
    "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "overlay": {"slabs": slabs, "beta": beta, "rate": rate, "served_mass": served_m, "served_birth": served_b},
    "quotient": {"first_mass": first_m, "first_birth": first_b, "persons": persons,
                 "cargo_kg": cargo, "merged_fiber": fiber, "second_mass": scale(F(1,2), merged_m)},
    "mixed_joint_endpoint_counterexample": {"total_mass": "2", "endpoint_prefix_amounts": mixed_query},
    "moment_eligibility_counterexample": {"matched_moments": age_moments, "eligibility": eligible},
    "positive_reconstruction": {"features": original_features, "steps": elimination,
                                "final_atoms": 2, "cubic_error": cubic_error,
                                "consumer_residual": residual, "bound_2M_epsilon": 2*residual},
    "jump_counterexample": {"event_time_shift": epsilon, "same_time_error": 1},
    "initial_stock": stock_samples,
    "analytic_speed_moment": str(true_moment),
    "midpoint_refinement": refinement, "midpoint_error_ratios": [str(x) for x in ratios],
    "latent_subdivision": latent_residuals,
    "guard_algebra": {"terms": terms, "allowance": allowance,
                     "excess_after_zero_index": 12694761, "conditional_observer_payload_difference": payload_difference},
    "calculation_wall_seconds": time.perf_counter() - started,
}
out = Path(__file__).with_name("R7_reconstruction_examples.json")
out.write_text(json.dumps(receipt, default=encode, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: receipt[k] for k in ("status", "python", "script_sha256",
    "positive_reconstruction", "midpoint_refinement", "calculation_wall_seconds")}, default=encode, indent=2))
