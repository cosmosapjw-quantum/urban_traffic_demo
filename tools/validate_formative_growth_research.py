#!/usr/bin/env python3
"""Run a bounded pure-Python seed/scale validation matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import fmean
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from metroflow.city.formative_growth import FormationConfig, generate_formative_city


CASES = (
    (120, 12.0, 7),
    (120, 12.0, 41),
    (120, 12.0, 97),
    (220, 20.0, 7),
    (220, 20.0, 41),
    (220, 20.0, 97),
    (320, 25.0, 7),
    (320, 25.0, 41),
    (320, 25.0, 97),
)

RANGE_FIELDS = (
    "mean_degree",
    "dead_end_share",
    "road_density_km_per_km2",
    "orientation_entropy_normalized",
    "local_orientation_coherence",
    "age_radius_spearman",
)


def _case_result(node_count: int, area_km2: float, seed: int) -> dict[str, object]:
    started = perf_counter()
    city = generate_formative_city(
        FormationConfig(
            seed=seed,
            node_count=node_count,
            urbanized_area_km2=area_km2,
        )
    )
    elapsed_s = perf_counter() - started
    metrics = city.metrics
    audit = city.audit
    return {
        "seed": seed,
        "node_count": node_count,
        "area_km2": area_km2,
        "fingerprint": city.fingerprint,
        "elapsed_s": elapsed_s,
        "status": audit["status"],
        "errors": audit["error_count"],
        "warnings": audit["warning_count"],
        "edge_count": metrics["edge_count"],
        "mean_degree": metrics["mean_degree"],
        "dead_end_share": metrics["dead_end_share"],
        "cycle_rank": metrics["cycle_rank"],
        "block_count": metrics["block_count"],
        "road_density_km_per_km2": metrics["road_density_km_per_km2"],
        "orientation_entropy_normalized": metrics[
            "orientation_entropy_normalized"
        ],
        "local_orientation_coherence": metrics["local_orientation_coherence"],
        "age_radius_spearman": metrics["age_radius_spearman"],
        "crossing_count": metrics["crossing_count"],
        "primary_components": metrics["primary_components"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cases = [_case_result(*case) for case in CASES]
    elapsed = [float(case["elapsed_s"]) for case in cases]
    payload = {
        "schema_version": "formative_growth_validation_v1",
        "all_pass": all(
            case["status"] == "PASS"
            and int(case["crossing_count"]) == 0
            and int(case["primary_components"]) == 1
            for case in cases
        ),
        "cases": cases,
        "max_elapsed_s": max(elapsed),
        "mean_elapsed_s": fmean(elapsed),
        "ranges": {
            field: [
                min(float(case[field]) for case in cases),
                max(float(case[field]) for case in cases),
            ]
            for field in RANGE_FIELDS
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(payload, allow_nan=False, indent=2, sort_keys=True))
    return 0 if payload["all_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
