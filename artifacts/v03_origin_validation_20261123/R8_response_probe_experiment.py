#!/usr/bin/env python3
"""Bounded finite-response memory experiment; no production native changes."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from metroflow.v1.finite_response_probe_certificate import (
    CompletedPassage, ResponseProbeCertificate,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("R8_response_probe_experiment.json")
MANIFEST = Path(__file__).with_name("R8_response_probe_manifest.json")
MODULE = ROOT / "src/metroflow/v1/finite_response_probe_certificate.py"
TEST = ROOT / "tests/research/test_v03_finite_response_probe_20261123.py"
INPUTS = (MODULE, TEST, Path(__file__))
TOLERANCE = D("2e-11")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decimal_root(distance, length, a=D(1), b=D(3), precision=70):
    with localcontext() as ctx:
        ctx.prec = precision
        lo, hi = length / b, length / a
        for _ in range(220):
            if hi - lo < D("1e-55"):
                break
            mid = (lo + hi) / 2
            if distance(mid) < length:
                lo = mid
            else:
                hi = mid
        return +((lo + hi) / 2)


def independent_formula(mean, entry, length):
    # Separate high-precision evaluation of the eliminated-endpoint formula.
    with localcontext() as ctx:
        ctx.prec = 70
        alpha = D(".5") / (D(".5").exp() - 1)
        elapsed = (entry - D(15)) / 10
        memory = alpha * (-elapsed).exp()
        low = lambda h: h + (mean - 1) * 10 * memory * (1 - (-h / 10).exp())
        high = lambda h: 3 * h - (3 - mean) * 10 * memory * (1 - (-h / 10).exp())
        return decimal_root(high, length), decimal_root(low, length)


def main():
    started = time.perf_counter()
    created = datetime.now(timezone.utc).isoformat()
    before = {str(p.relative_to(ROOT)): sha(p) for p in INPUTS}
    rows = []
    precision_errors = []
    cases = 0

    # Withheld constant solutions: true v=V is used only by the oracle.
    for true_speed in ("1.25", "2", "2.75"):
        speed = D(true_speed)
        probe = CompletedPassage("homogeneous-A", 10, 15, 16, float(5 * speed))
        certificate = ResponseProbeCertificate("homogeneous-A", probe, 16, 10, 1, 3)
        for entry in (16, 17, 20, 25, 40):
            for length in (2, 5, 10, 20):
                band = certificate.duration_bounds(entry, length)
                exact_duration = D(length) / speed
                independent_lo, independent_hi = independent_formula(speed, D(entry), D(length))
                assert D(str(band.lower_s)) <= exact_duration + TOLERANCE
                assert exact_duration <= D(str(band.upper_s)) + TOLERANCE
                assert abs(D(str(band.lower_s)) - independent_lo) <= TOLERANCE
                assert abs(D(str(band.upper_s)) - independent_hi) <= TOLERANCE
                assert length / 3 <= band.lower_s <= band.upper_s <= length
                precision_errors.extend((abs(D(str(band.lower_s)) - independent_lo),
                                         abs(D(str(band.upper_s)) - independent_hi)))
                rows.append(dict(kind="withheld_constant_solution", true_speed_m_s=true_speed,
                                 entry_s=entry, length_m=length, duration_bounds=asdict(band),
                                 actual_duration_s=str(exact_duration),
                                 independent_lower_root_s=str(independent_lo),
                                 independent_upper_root_s=str(independent_hi)))
                cases += 1

    # Same completed v=2 probe, unknown future target switches at decision d=16.
    probe = CompletedPassage("homogeneous-A", 10, 15, 16, 10)
    certificate = ResponseProbeCertificate("homogeneous-A", probe, 16, 10, 1, 3)
    for future_target in (1, 3):
        for entry in (16, 20, 40):
            for length in (2, 5, 10, 20):
                with localcontext() as ctx:
                    ctx.prec = 70
                    q, t, ell = D(future_target), D(entry), D(length)
                    # v(d)=2, then V=q. This future field is withheld from the certificate.
                    at_entry = q + (2 - q) * (-(t - 16) / 10).exp()
                    distance = lambda h: q * h + (at_entry - q) * 10 * (1 - (-h / 10).exp())
                    actual = decimal_root(distance, ell)
                band = certificate.duration_bounds(entry, length)
                assert D(str(band.lower_s)) <= actual + TOLERANCE
                assert actual <= D(str(band.upper_s)) + TOLERANCE
                rows.append(dict(kind="withheld_future_target_switch", future_target_m_s=future_target,
                                 entry_s=entry, length_m=length, duration_bounds=asdict(band),
                                 actual_duration_s=str(actual),
                                 future_target_passed_to_predictor=False))
                cases += 1

    band = certificate.duration_bounds(16, 10)
    baseline = {"A": 10.0, "B": 7.0}
    upgraded = {"A": band.upper_s, "B": 7.0}
    truth = {"A": 5.0, "B": 7.0}
    baseline_selected = min(baseline, key=baseline.get)
    upgraded_selected = min(upgraded, key=upgraded.get)
    exact_lower_distance = F(7) + F(17010, 5057)
    assert exact_lower_distance > 10
    assert baseline_selected == "B" and upgraded_selected == "A"
    assert band.upper_s < 7
    assert cases == 84 and len(rows) == 84
    after = {str(p.relative_to(ROOT)): sha(p) for p in INPUTS}
    assert before == after
    result = {
        "schema": "V03_FINITE_RESPONSE_PROBE_UPGRADE_V1",
        "evidence": ["derived analytic bounds", "numerically checked f64/high-precision roots",
                     "exact rational proof of strict route dominance"],
        "status": "FINITE_ASSERTIONS_PASSED",
        "created_utc": created,
        "claim_scope": "positive spatially homogeneous finite-response fields, exact matched passage, fixed forcing bounds/context",
        "inputs": {"relaxation_s": 10, "forcing_speed_interval_m_s": [1, 3],
                   "probe_entry_s": 10, "probe_exit_s": 15, "probe_delivered_s": 16,
                   "decision_s": 16, "routing_probe_length_m": 10},
        "memory_weight": certificate.memory_weight,
        "exit_speed_interval_m_s": certificate.exit_speed_bounds_m_s,
        "decision_speed_interval_m_s": certificate.decision_speed_bounds_m_s,
        "routing_A_duration_bounds_s": [band.lower_s, band.upper_s],
        "routing_arrival_clock_bounds_s": [16 + band.lower_s, 16 + band.upper_s],
        "constant_solution_checks": 60,
        "withheld_future_target_switch_checks": 24,
        "total_withheld_checks": cases,
        "high_precision_root_comparisons": len(precision_errors),
        "high_precision_decimal_digits": 70,
        "max_float_endpoint_difference_s": str(max(precision_errors)),
        "floating_comparison_tolerance_s": str(TOLERANCE),
        "float_output_is_formal_directed_interval": False,
        "route_choice": {
            "legal_graph": "two declared parallel routes from O to D; A=10m unknown bounded field, B=14m constant2m/s",
            "baseline_global_duration_bounds_s": {"A": [10 / 3, 10], "B": [7, 7]},
            "baseline_upper_selected": baseline_selected,
            "upgraded_upper_selected": upgraded_selected,
            "actual_durations_s": truth,
            "baseline_actual_regret_s": truth[baseline_selected] - min(truth.values()),
            "upgraded_actual_regret_s": truth[upgraded_selected] - min(truth.values()),
            "numerical_upper_margin_vs_B_s": 7 - band.upper_s,
            "exact_comparison": {
                "statement": "D_lower(7)>7+17010/5057>10 metres, hence the analytic A upper duration is strictly below7s",
                "rational_lower_distance_m": str(exact_lower_distance),
                "rational_surplus_m": str(exact_lower_distance - 10),
                "relies_on_bisection_rounding": False,
            },
        },
        "old_gamma_interpretation": {
            "comparison": "with Gamma=b/a and completed probe, Gamma-envelope future duration >=length/a; no improvement over the known global speed ceiling",
            "old_gamma_theorems_invalidated": False,
            "new_information_used": "known relaxation tau and a matched completed transit integral",
        },
        "source_sha256_before": before,
        "source_sha256_after": after,
        "rows": rows,
        "wall_s": time.perf_counter() - started,
        "native_city_execution": False,
        "V03_full_day_campaign_credit": 0,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                            text=True, capture_output=True, check=True).stdout
    hardware = next((line.split(":", 1)[1].strip() for line in
                     Path("/proc/cpuinfo").read_text().splitlines()
                     if line.startswith("model name")), "NOT_OBSERVED")
    manifest = {
        "schema_version": 2,
        "claim_id": "V03_FINITE_RESPONSE_CAUSAL_PROBE_UPGRADE_20261123",
        "repository": {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                                         cwd=ROOT, text=True).strip(),
                       "dirty": bool(status)},
        "command": ["env", "PYTHONDONTWRITEBYTECODE=1", "PYTHONPATH=src:.",
                    "timeout", "60s", "python3", str(Path(__file__).relative_to(ROOT))],
        "environment": {"software": [{"name": "Python", "version": platform.python_version()},
                                     {"name": "Decimal", "version": "Python standard library"}],
                        "hardware": hardware},
        "mathematics": {
            "assertion_tested": "84 withheld finite-response passages obey analytic bounds;120 floating endpoints agree with independent Decimal roots within2e-11s; exact rational inequality gives route dominance",
            "coefficient_domain": "binary64 implementation;70-digit Decimal cross-check; exact Fraction route comparison",
            "conventions": "SI seconds/metres/metres-per-second, exact completed matched probes, positive spatially homogeneous fixed traffic context",
            "inputs": result["inputs"],
            "bounds": {"constant_cases": 60, "future_switch_cases": 24,
                       "root_comparison_tolerance_s": "2e-11", "relaxation_s": 10},
            "non_claims": ["global floating directed-rounding certification", "native queue/spillback ETA",
                           "whole-city calibration", "production routing activation", "V03 full-day acceptance"],
        },
        "randomness": {"used": False, "generator": "", "seed": None},
        "run": {"started_at": created, "runtime_seconds": result["wall_s"],
                "exit_status": 0, "status": "completed",
                "resource_limits": {"wall_seconds": 60, "memory_bytes": None, "cpu_seconds": None,
                                    "max_cores": None, "max_threads": None}},
        "outputs": [{"path": str(OUT.relative_to(ROOT)), "sha256": sha(OUT), "kind": "result"}],
        "checks": ["84 actual withheld cases enumerated", "120 Decimal endpoint comparisons",
                   "known global interval nesting", "strict rational dominance", "same inputs before/after"],
        "result": "implementation and finite assertion verified in the stated range; universal bounds supplied by derivation",
        "residual_risks": ["forcing-bound certification and matched boundary instrumentation remain absent for general native city queues",
                           "floating approximations are not formal interval arithmetic"],
        "input_artifacts": [{"path": name, "sha256": value, "sha256_after": after[name]}
                            for name, value in before.items()],
        "declared_results": [str(OUT.relative_to(ROOT))],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: result[k] for k in ("status", "total_withheld_checks",
          "high_precision_root_comparisons", "max_float_endpoint_difference_s",
          "routing_A_duration_bounds_s", "route_choice", "wall_s")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
