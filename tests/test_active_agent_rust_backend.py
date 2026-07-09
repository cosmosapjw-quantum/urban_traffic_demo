from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest


def _agent_backend_state(
    *,
    agent_backend: str = "baseline",
    outflow_vehicles: tuple[float, ...] = (1.0, 0.0),
    sink_capacity: tuple[float, ...] = (1.0, 1.0),
    route_ptr: int = 0,
    current_link_id: int = 10,
    path: tuple[int, ...] = (10, 11),
):
    from metroflow.city.graph import (
        Node,
        RoadClass,
        RoadLink,
        TurnMovement,
        TurnType,
        build_road_network_csr,
    )
    from metroflow.city.zones import POI, POIType
    from metroflow.demand.trips import TripRequest, TripRequestStatus
    from metroflow.flow.state import LinkState, NodeState
    from metroflow.sim.active_agents import (
        ActiveAgentPool,
        ActiveAgentSlot,
        allocate_active_agent_slot,
        create_active_agent_pool,
    )
    from metroflow.sim.config import DayType, SimulationConfig, TimeBand
    from metroflow.sim.routing_runtime import create_simulation_route_cache_state
    from metroflow.sim.state import SimulationDynamicRefs, SimulationState, SimulationStaticRefs

    road_csr = build_road_network_csr(
        nodes=(Node(1), Node(2), Node(3)),
        links=(
            RoadLink(10, 1, 2, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
            RoadLink(11, 2, 3, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
        ),
        turns=(TurnMovement(10, 11, TurnType.THROUGH),),
    )
    link_state = LinkState(
        queue_vehicles=np.zeros((2,), dtype=np.float32),
        inflow_vehicles=np.zeros((2,), dtype=np.float32),
        outflow_vehicles=np.asarray(outflow_vehicles, dtype=np.float32),
        travel_time_cost=np.ones((2,), dtype=np.float32),
        capacity_veh_per_tick=np.asarray(sink_capacity, dtype=np.float32),
        incident_capacity_multiplier=np.ones((2,), dtype=np.float32),
        metadata={
            "free_flow_travel_time_cost": np.ones((2,), dtype=np.float32),
            "runtime_flow_generation": 0,
            "runtime_incident_generation": 0,
        },
    )
    node_state = NodeState(
        turn_from_link_index=road_csr.turn_from_link_index,
        turn_to_link_index=road_csr.turn_to_link_index,
        turn_demand=np.zeros((1,), dtype=np.float32),
        turn_supply=np.zeros((1,), dtype=np.float32),
        turn_flow=np.zeros((1,), dtype=np.float32),
        signal_phase_index=np.zeros((3,), dtype=np.int32),
        signal_phase_timer=np.zeros((3,), dtype=np.int32),
        metadata={
            "turn_base_priority": np.asarray(road_csr.turn_base_priority, dtype=np.float32),
            "turn_is_forbidden": np.asarray(road_csr.turn_is_forbidden, dtype=np.bool_),
        },
    )
    trip = TripRequest(
        trip_request_id=1,
        citizen_id=101,
        origin_poi_id=1,
        dest_poi_id=2,
        planned_depart_tick=0,
        day_type=DayType.WEEKDAY,
        time_band=TimeBand.MORNING,
    )
    trip = replace(trip, status=TripRequestStatus.ACTIVATED)
    pool, slot_id = allocate_active_agent_slot(
        create_active_agent_pool(4),
        ActiveAgentSlot.spawn(
            citizen_id=101,
            trip_id=1,
            current_link_id=current_link_id,
            dest_node_id=3,
            behavior_profile_id=0,
            remaining_route_ptr=route_ptr,
        ),
    )
    pool = ActiveAgentPool.from_internal_arrays(
        capacity=pool.capacity,
        free_slot_stack=pool.free_slot_stack,
        free_slot_count=pool.free_slot_count,
        alive_mask=pool.alive_mask,
        alive_count=pool.alive_count,
        citizen_id=pool.citizen_id,
        trip_id=pool.trip_id,
        current_link_id=pool.current_link_id,
        progress_01=pool.progress_01,
        remaining_route_ptr=pool.remaining_route_ptr,
        dest_node_id=pool.dest_node_id,
        behavior_profile_id=pool.behavior_profile_id,
        reroute_cooldown_ticks=pool.reroute_cooldown_ticks,
        plugin_memory={
            int(slot_id): {
                "route_path": path,
                "origin_poi_id": 1,
                "dest_poi_id": 2,
                "trip_request_id": 1,
            }
        },
    )
    return SimulationState(
        config=SimulationConfig(active_agent_capacity=4, agent_backend=agent_backend),
        static=SimulationStaticRefs(
            scenario_id="agent-backend-test",
            pois=(
                POI(1, 1, POIType.HOME, node_id=1),
                POI(2, 2, POIType.WORKPLACE, node_id=3),
            ),
            routing_static={"road_csr": road_csr},
            ui_network_geometry_version="agent-backend-geom",
        ),
        dynamic=SimulationDynamicRefs(
            demand_state={
                "trip_requests": (trip,),
                "queued_trip_requests": 0,
                "pending_trip_requests": 1,
                "activated_trip_requests": 1,
                "allocated_trip_request_ids": (1,),
            },
            active_agent_pool=pool,
            flow_link_state=link_state,
            flow_node_state=node_state,
            route_candidate_state=create_simulation_route_cache_state(),
            metrics_state={
                "tick_index": 0,
                "queued_trip_requests": 0,
                "pending_trip_requests": 1,
                "completed_trips_total": 0,
                "failed_trips_total": 0,
                "generated_trip_total": 1,
                "capacity_violation_count": 0,
            },
        ),
    )


def _without_timing(counters: dict[str, int]) -> dict[str, int]:
    return {
        key: value
        for key, value in counters.items()
        if key
        not in {
            "active_agent_allocation_wall_ns",
            "active_agent_candidate_selection_wall_ns",
            "active_agent_movement_wall_ns",
            "active_agent_pool_write_wall_ns",
            "reroute_decision_wall_ns",
        }
    }


def test_simulation_config_accepts_agent_backend_and_rejects_unknown() -> None:
    from metroflow.sim.config import SimulationConfig

    assert SimulationConfig().agent_backend == "baseline"
    assert SimulationConfig(agent_backend="rust_cpu").agent_backend == "rust_cpu"
    assert SimulationConfig(agent_backend="auto").agent_backend == "auto"
    with pytest.raises(ValueError, match="agent_backend must be one of"):
        SimulationConfig(agent_backend="torch_cuda")


def test_explicit_rust_agent_backend_unavailable_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.sim import routing_runtime

    monkeypatch.setattr(routing_runtime, "rust_agent_backend_available", lambda: False)
    state = _agent_backend_state(agent_backend="rust_cpu")

    with pytest.raises(RuntimeError, match="Rust CPU active-agent backend unavailable"):
        routing_runtime.advance_runtime_active_agents(state)


def test_auto_agent_backend_falls_back_to_baseline_when_rust_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.sim import routing_runtime

    monkeypatch.setattr(routing_runtime, "rust_agent_backend_available", lambda: False)
    baseline_state = _agent_backend_state(agent_backend="baseline")
    auto_state = _agent_backend_state(agent_backend="auto")

    baseline_pool, baseline_counters, baseline_demand, _ = (
        routing_runtime.advance_runtime_active_agents(baseline_state)
    )
    auto_pool, auto_counters, auto_demand, _ = routing_runtime.advance_runtime_active_agents(auto_state)

    assert _without_timing(auto_counters) == _without_timing(baseline_counters)
    assert auto_demand["completed_trip_request_ids"] == baseline_demand["completed_trip_request_ids"]
    np.testing.assert_array_equal(auto_pool.current_link_id, baseline_pool.current_link_id)
    np.testing.assert_array_equal(auto_pool.remaining_route_ptr, baseline_pool.remaining_route_ptr)
    assert auto_pool.alive_count == baseline_pool.alive_count


def test_rust_agent_backend_matches_baseline_movement_when_extension_available() -> None:
    from metroflow.backends.rust_cpu import rust_agent_backend_available
    from metroflow.sim.routing_runtime import advance_runtime_active_agents

    if not rust_agent_backend_available():
        pytest.skip("Rust extension is not built with active-agent backend")

    baseline_state = _agent_backend_state(agent_backend="baseline")
    rust_state = _agent_backend_state(agent_backend="rust_cpu")

    baseline_pool, baseline_counters, baseline_demand, _ = advance_runtime_active_agents(
        baseline_state
    )
    rust_pool, rust_counters, rust_demand, _ = advance_runtime_active_agents(rust_state)

    assert _without_timing(rust_counters) == _without_timing(baseline_counters)
    assert rust_demand["completed_trip_request_ids"] == baseline_demand["completed_trip_request_ids"]
    np.testing.assert_array_equal(rust_pool.current_link_id, baseline_pool.current_link_id)
    np.testing.assert_array_equal(rust_pool.remaining_route_ptr, baseline_pool.remaining_route_ptr)
    np.testing.assert_array_equal(rust_pool.reroute_cooldown_ticks, baseline_pool.reroute_cooldown_ticks)
    assert rust_pool.plugin_memory == baseline_pool.plugin_memory


def test_rust_agent_backend_matches_baseline_final_link_sink_wait_when_available() -> None:
    from metroflow.backends.rust_cpu import rust_agent_backend_available
    from metroflow.sim.routing_runtime import advance_runtime_active_agents

    if not rust_agent_backend_available():
        pytest.skip("Rust extension is not built with active-agent backend")

    kwargs = {
        "outflow_vehicles": (0.0, 0.0),
        "sink_capacity": (1.0, 0.0),
        "route_ptr": 1,
        "current_link_id": 11,
    }
    baseline_pool, baseline_counters, baseline_demand, _ = advance_runtime_active_agents(
        _agent_backend_state(agent_backend="baseline", **kwargs)
    )
    rust_pool, rust_counters, rust_demand, _ = advance_runtime_active_agents(
        _agent_backend_state(agent_backend="rust_cpu", **kwargs)
    )

    assert _without_timing(rust_counters) == _without_timing(baseline_counters)
    assert rust_demand["completed_trip_request_ids"] == baseline_demand.get(
        "completed_trip_request_ids",
        (),
    )
    np.testing.assert_array_equal(rust_pool.current_link_id, baseline_pool.current_link_id)
    assert rust_pool.alive_count == baseline_pool.alive_count == 1


def test_rust_agent_action_wrapper_returns_copy_boundary_action_plan_when_available() -> None:
    from metroflow.backends.rust_cpu import (
        advance_active_agents_rust,
        rust_agent_backend_available,
    )

    if not rust_agent_backend_available():
        pytest.skip("Rust extension is not built with active-agent backend")

    plan = advance_active_agents_rust(
        slot_ids=(0, 1),
        trip_ids=(101, 102),
        current_link_ids=(10, 11),
        route_ptrs=(0, 1),
        cooldown_ticks=(2, 0),
        route_offsets=(0, 2, 4),
        route_link_ids=(10, 11, 10, 11),
        movement_budget_link_ids=(10,),
        movement_budget_counts=(1,),
        completion_budget_link_ids=(11,),
        completion_budget_counts=(0,),
        skip_slot_ids=(),
    )

    np.testing.assert_array_equal(plan["next_current_link_ids"], np.asarray((11, 11), dtype=np.int32))
    np.testing.assert_array_equal(plan["next_route_ptrs"], np.asarray((1, 1), dtype=np.int32))
    np.testing.assert_array_equal(plan["next_cooldown_ticks"], np.asarray((1, 0), dtype=np.int32))
    np.testing.assert_array_equal(plan["moved_slot_ids"], np.asarray((0,), dtype=np.int32))
    np.testing.assert_array_equal(plan["sink_wait_slot_ids"], np.asarray((1,), dtype=np.int32))
    assert plan["released_slot_ids"].size == 0
    assert plan["completed_trip_ids"].size == 0
