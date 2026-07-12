"""Probe generated-runtime movement closure or reproduce its historical stall."""

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
    steps: int = 20,
) -> dict[str, Any]:
    """Run a small generated workload and report stall and closure predicates."""

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
    road_csr = state.static.routing_static["road_csr"]
    initial = {
        "trip_count": len(bundle.trip_requests.trip_requests),
        "turn_count": int(road_csr.turn_count),
        "permitted_turn_count": int((~road_csr.turn_is_forbidden).sum()),
        "turn_demand_total": float(state.dynamic.flow_node_state.turn_demand.sum()),
        "queue_vehicles_total": float(state.dynamic.flow_link_state.queue_vehicles.sum()),
    }

    tick_rows: list[dict[str, int | float]] = []
    route_length_by_trip_id: dict[int, int] = {}
    control = SimulationControl.noop()
    for _ in range(step_count):
        state, telemetry, _, rng_key = simulation_step(state, control, rng_key)
        pool = state.dynamic.active_agent_pool
        for slot_id, alive in enumerate(pool.alive_mask.tolist()):
            if not bool(alive):
                continue
            memory = pool.plugin_memory.get(int(slot_id), {})
            route_length_by_trip_id[int(pool.trip_id[slot_id])] = len(
                tuple(memory.get("route_path", ()))
            )
        agent_count_by_link = [0] * int(road_csr.link_count)
        for slot_id, alive in enumerate(pool.alive_mask.tolist()):
            if not bool(alive):
                continue
            link_id = int(pool.current_link_id[slot_id])
            agent_count_by_link[int(road_csr.link_id_to_index[link_id])] += 1
        queue_by_link = state.dynamic.flow_link_state.queue_vehicles
        maximum_link_mass_delta = max(
            (
                abs(float(queue_by_link[index]) - float(agent_count_by_link[index]))
                for index in range(int(road_csr.link_count))
            ),
            default=0.0,
        )
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
                "invariant_ok": bool(state.dynamic.invariant_state.ok),
                "maximum_link_agent_mass_delta": maximum_link_mass_delta,
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
    completed_total = sum(int(row["completed_trip_count"]) for row in tick_rows)
    failed_total = sum(int(row["failed_trip_count"]) for row in tick_rows)
    final_demand_state = state.dynamic.demand_state
    completed_ids = {
        int(value)
        for value in tuple(final_demand_state.get("completed_trip_request_ids", ()))
    }
    failed_ids = {
        int(value)
        for value in tuple(final_demand_state.get("failed_trip_request_ids", ()))
    }
    failure_reasons = {
        int(trip_id): str(reason)
        for trip_id, reason in dict(
            final_demand_state.get("failed_trip_reason_by_id", {}) or {}
        ).items()
    }
    completed_multihop_count = sum(
        1 for trip_id in completed_ids if route_length_by_trip_id.get(trip_id, 0) > 1
    )
    failures_classified_no_route = all(
        failure_reasons.get(trip_id) == "no_route_candidate" for trip_id in failed_ids
    )
    closure_verified = bool(
        initial["trip_count"] > 0
        and initial["turn_count"] > 0
        and tick_rows
        and any(row["turn_demand_total"] > 0.0 for row in tick_rows)
        and any(row["outflow_vehicles_total"] > 0.0 for row in tick_rows)
        and any(row["moved_agent_count"] > 0 for row in tick_rows)
        and all(bool(row["invariant_ok"]) for row in tick_rows)
        and all(
            float(row["maximum_link_agent_mass_delta"]) <= 1.0e-6
            for row in tick_rows
        )
        and int(tick_rows[-1]["active_agent_count"]) == 0
        and float(tick_rows[-1]["queue_vehicles_total"]) == 0.0
        and completed_total + failed_total == int(initial["trip_count"])
        and completed_total > 0
        and completed_multihop_count > 0
        and failures_classified_no_route
    )
    return {
        "schema_version": "metroflow.runtime-self-drive-probe.v2",
        "scenario_seed": int(scenario_seed),
        "steps": step_count,
        "initial": initial,
        "ticks": tick_rows,
        "runtime_closure_blocker_reproduced": blocker_reproduced,
        "runtime_closure_verified": closure_verified,
        "completed_trip_count_total": completed_total,
        "failed_trip_count_total": failed_total,
        "completed_multihop_trip_count_total": completed_multihop_count,
        "failures_classified_no_route": failures_classified_no_route,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-seed", type=int, default=41)
    parser.add_argument("--steps", type=int, default=20)
    expectation = parser.add_mutually_exclusive_group()
    expectation.add_argument(
        "--expect-stalled",
        action="store_true",
        help="fail unless the historical zero-turn-demand blocker is reproduced",
    )
    expectation.add_argument(
        "--expect-closed",
        action="store_true",
        help="fail unless generated trips move, terminate, and conserve link mass",
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
    if args.expect_closed and not result["runtime_closure_verified"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
