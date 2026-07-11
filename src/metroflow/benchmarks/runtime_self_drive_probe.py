"""Reproduce the generated-runtime movement-closure audit finding."""

from __future__ import annotations

import argparse
import json
from typing import Any

from metroflow.sim.config import SimulationConfig
from metroflow.sim.control import SimulationControl
from metroflow.sim.init import build_initial_simulation_state
from metroflow.sim.step import simulation_step

__all__ = ["run_runtime_self_drive_probe"]


def run_runtime_self_drive_probe(
    *,
    scenario_seed: int = 41,
    steps: int = 3,
) -> dict[str, Any]:
    """Run a small generated workload and report whether the audited stall remains."""

    step_count = int(steps)
    if step_count <= 0:
        raise ValueError("steps must be > 0")

    config = SimulationConfig(
        population_target=100,
        active_agent_capacity=100,
        max_trip_spawns_per_tick=100,
    )
    bundle = build_initial_simulation_state(
        config=config,
        scenario_seed=int(scenario_seed),
        eager_trip_generation=True,
    )
    state = bundle.state
    rng_key = bundle.rng_key
    initial = {
        "trip_count": len(bundle.trip_requests.trip_requests),
        "turn_demand_total": float(state.dynamic.flow_node_state.turn_demand.sum()),
        "queue_vehicles_total": float(state.dynamic.flow_link_state.queue_vehicles.sum()),
    }

    tick_rows: list[dict[str, int | float]] = []
    control = SimulationControl.noop()
    for _ in range(step_count):
        state, telemetry, _, rng_key = simulation_step(state, control, rng_key)
        tick_rows.append(
            {
                "tick_index": state.tick_index,
                "active_agent_count": telemetry.active_agent_count,
                "moved_agent_count": telemetry.active_agent_moved_this_tick,
                "completed_trip_count": telemetry.trip_completed_this_tick,
                "failed_trip_count": telemetry.trip_failed_this_tick,
                "turn_demand_total": float(
                    state.dynamic.flow_node_state.turn_demand.sum()
                ),
                "outflow_vehicles_total": float(
                    state.dynamic.flow_link_state.outflow_vehicles.sum()
                ),
                "queue_vehicles_total": float(
                    state.dynamic.flow_link_state.queue_vehicles.sum()
                ),
            }
        )

    blocker_reproduced = bool(
        initial["trip_count"] > 0
        and tick_rows
        and tick_rows[-1]["active_agent_count"] > 0
        and tick_rows[-1]["queue_vehicles_total"] > 0.0
        and all(row["turn_demand_total"] == 0.0 for row in tick_rows)
        and all(row["outflow_vehicles_total"] == 0.0 for row in tick_rows)
        and all(row["moved_agent_count"] == 0 for row in tick_rows)
    )
    return {
        "schema_version": "metroflow.runtime-self-drive-probe.v1",
        "scenario_seed": int(scenario_seed),
        "steps": step_count,
        "initial": initial,
        "ticks": tick_rows,
        "runtime_closure_blocker_reproduced": blocker_reproduced,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-seed", type=int, default=41)
    parser.add_argument("--steps", type=int, default=3)
    parser.add_argument(
        "--expect-stalled",
        action="store_true",
        help="fail unless the audited zero-turn-demand movement blocker is reproduced",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = run_runtime_self_drive_probe(
        scenario_seed=args.scenario_seed,
        steps=args.steps,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.expect_stalled and not result["runtime_closure_blocker_reproduced"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
