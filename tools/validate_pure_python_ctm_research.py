#!/usr/bin/env python3
"""Bounded seed/load validation matrix for the pure-Python CTM research lane."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from metroflow.pure_traffic.ctm import simulate
from metroflow.pure_traffic.scenarios import build_diamond_bottleneck_scenario


CASES = tuple(
    (seed, vehicles, release_batch, ticks)
    for seed in (7, 41, 97)
    for vehicles, release_batch, ticks in (
        (120, 2, 120),
        (240, 4, 180),
        (320, 4, 220),
    )
)


def _forbidden_scan() -> dict[str, object]:
    paths = (
        ROOT / "src/metroflow/pure_traffic/ctm.py",
        ROOT / "src/metroflow/pure_traffic/scenarios.py",
        ROOT / "tools/run_pure_python_ctm_research.py",
    )
    forbidden_modules = {"jax", "cupy", "torch"}
    forbidden_names = {"cuda", "gpu"}
    findings: list[dict[str, object]] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0].lower()
                    if root in forbidden_modules:
                        findings.append(
                            {
                                "path": str(path.relative_to(ROOT)),
                                "line": node.lineno,
                                "token": root,
                                "kind": "import",
                            }
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0].lower()
                if root in forbidden_modules:
                    findings.append(
                        {
                            "path": str(path.relative_to(ROOT)),
                            "line": node.lineno,
                            "token": root,
                            "kind": "from_import",
                        }
                    )
            elif isinstance(node, ast.Name) and node.id.lower() in forbidden_names:
                findings.append(
                    {
                        "path": str(path.relative_to(ROOT)),
                        "line": node.lineno,
                        "token": node.id.lower(),
                        "kind": "runtime_name",
                    }
                )
    return {"status": "PASS" if not findings else "FAIL", "findings": findings}


def _run_case(seed: int, vehicles: int, release_batch: int, ticks: int) -> dict[str, object]:
    scenario = build_diamond_bottleneck_scenario(
        seed=seed,
        vehicles=vehicles,
        release_batch=release_batch,
        node_policy="weighted_fair",
        fifo_mode="movement",
        movement_age_priority=True,
    )
    started = perf_counter()
    result = simulate(
        scenario.network,
        scenario.requests,
        scenario.config,
        ticks=ticks,
        incidents=scenario.incidents,
    )
    elapsed = perf_counter() - started
    clear_tick = next(
        (
            snapshot.tick
            for snapshot in result.snapshots
            if snapshot.completed_count == vehicles
        ),
        None,
    )
    max_cell_ratio = max(
        ratio
        for snapshot in result.snapshots
        for ratios in snapshot.link_cell_occupancy_ratio.values()
        for ratio in ratios
    )
    residuals = (
        *result.final_state.entry_residuals,
        *result.final_state.exit_residuals,
        *result.final_state.movement_residuals,
        *(
            value
            for values in result.final_state.internal_residuals
            for value in values
        ),
    )
    passed = (
        result.final_state.mass_balance_error == 0
        and result.node_holding_events == 0
        and result.final_state.completed_count == vehicles
        and result.final_state.pending_count == 0
        and result.final_state.active_count == 0
        and clear_tick is not None
        and max_cell_ratio <= 1.0 + 1.0e-12
        and all(0.0 <= value < 1.0 for value in residuals)
        and all(value > 0.0 for value in result.completed_travel_times_s)
    )
    return {
        "seed": seed,
        "vehicles": vehicles,
        "release_batch": release_batch,
        "ticks": ticks,
        "status": "PASS" if passed else "FAIL",
        "elapsed_s": elapsed,
        "fingerprint": result.fingerprint,
        "clear_tick": clear_tick,
        "mass_balance_error": result.final_state.mass_balance_error,
        "holding_events": result.node_holding_events,
        "max_cell_occupancy_ratio": max_cell_ratio,
        "max_pending": max(snapshot.pending_count for snapshot in result.snapshots),
        "peak_active": max(snapshot.active_count for snapshot in result.snapshots),
        "maximum_travel_time_s": max(result.completed_travel_times_s),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = [_run_case(*case) for case in CASES]
    replay_scenario = build_diamond_bottleneck_scenario(
        seed=20261023,
        vehicles=120,
        release_batch=2,
    )
    first = simulate(
        replay_scenario.network,
        replay_scenario.requests,
        replay_scenario.config,
        ticks=120,
        incidents=replay_scenario.incidents,
    )
    second = simulate(
        replay_scenario.network,
        replay_scenario.requests,
        replay_scenario.config,
        ticks=120,
        incidents=replay_scenario.incidents,
    )
    replay_pass = first.fingerprint == second.fingerprint and first.snapshots == second.snapshots
    scan = _forbidden_scan()
    payload = {
        "schema_version": "pure_python_ctm_validation_v1",
        "base_commit": "01c80b432344f94209daaa198bb1eb007839fc7f",
        "all_pass": all(case["status"] == "PASS" for case in cases)
        and replay_pass
        and scan["status"] == "PASS",
        "case_count": len(cases),
        "cases": cases,
        "replay": {
            "status": "PASS" if replay_pass else "FAIL",
            "fingerprint": first.fingerprint,
        },
        "accelerator_scan": scan,
        "max_elapsed_s": max(float(case["elapsed_s"]) for case in cases),
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
