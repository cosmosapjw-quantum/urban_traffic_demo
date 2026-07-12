from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest


def _closure_state(
    *,
    branch: bool = False,
    queue: tuple[float, ...] | None = None,
    capacity: tuple[float, ...] | None = None,
    active_paths: tuple[tuple[int, ...], ...] = (),
    current_ptrs: tuple[int, ...] = (),
    turn_priority: tuple[float, ...] | None = None,
    queued_trip: bool = False,
    agent_backend: str = "baseline",
    flow_backend: str = "baseline",
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
    from metroflow.sim.state import (
        SimulationDynamicRefs,
        SimulationState,
        SimulationStaticRefs,
    )

    links = [
        RoadLink(10, 1, 2, RoadClass.ARTERIAL, 100.0, 10.0, 1.0),
        RoadLink(11, 2, 3, RoadClass.ARTERIAL, 100.0, 10.0, 1.0),
    ]
    turns = [TurnMovement(10, 11, TurnType.THROUGH)]
    nodes = [Node(1), Node(2), Node(3)]
    if branch:
        nodes.append(Node(4))
        links.append(RoadLink(12, 2, 4, RoadClass.ARTERIAL, 100.0, 10.0, 1.0))
        turns.append(TurnMovement(10, 12, TurnType.RIGHT))
    road_csr = build_road_network_csr(nodes=nodes, links=links, turns=turns)
    link_count = road_csr.link_count
    turn_count = road_csr.turn_count
    queue_values = queue if queue is not None else tuple(0.0 for _ in range(link_count))
    capacity_values = capacity if capacity is not None else tuple(1.0 for _ in range(link_count))
    link_state = LinkState(
        queue_vehicles=np.asarray(queue_values, dtype=np.float32),
        inflow_vehicles=np.zeros((link_count,), dtype=np.float32),
        outflow_vehicles=np.zeros((link_count,), dtype=np.float32),
        travel_time_cost=np.ones((link_count,), dtype=np.float32),
        capacity_veh_per_tick=np.asarray(capacity_values, dtype=np.float32),
        incident_capacity_multiplier=np.ones((link_count,), dtype=np.float32),
        metadata={"free_flow_travel_time_cost": np.ones((link_count,), dtype=np.float32)},
    )
    priorities = (
        np.asarray(turn_priority, dtype=np.float32)
        if turn_priority is not None
        else np.ones((turn_count,), dtype=np.float32)
    )
    node_state = NodeState(
        turn_from_link_index=road_csr.turn_from_link_index,
        turn_to_link_index=road_csr.turn_to_link_index,
        turn_demand=np.zeros((turn_count,), dtype=np.float32),
        turn_supply=np.zeros((turn_count,), dtype=np.float32),
        turn_flow=np.zeros((turn_count,), dtype=np.float32),
        signal_phase_index=np.zeros((road_csr.node_count,), dtype=np.int32),
        signal_phase_timer=np.zeros((road_csr.node_count,), dtype=np.int32),
        metadata={
            "turn_base_priority": priorities,
            "turn_is_forbidden": np.zeros((turn_count,), dtype=np.bool_),
        },
    )

    path_specs = list(active_paths)
    if queued_trip and not path_specs:
        path_specs = [(10, 11)]
    trips = []
    for index, path in enumerate(path_specs, start=1):
        trips.append(
            TripRequest(
                trip_request_id=index,
                citizen_id=100 + index,
                origin_poi_id=1,
                dest_poi_id=3 if path[-1] == 11 else 4,
                planned_depart_tick=0,
                day_type=DayType.WEEKDAY,
                time_band=TimeBand.MORNING,
                status=(
                    TripRequestStatus.QUEUED
                    if queued_trip
                    else TripRequestStatus.ACTIVATED
                ),
            )
        )

    pool = create_active_agent_pool(max(4, len(active_paths) + 1))
    plugin_memory = {}
    for index, path in enumerate(active_paths, start=1):
        ptr = int(current_ptrs[index - 1])
        payload = ActiveAgentSlot.spawn(
            citizen_id=100 + index,
            trip_id=index,
            current_link_id=int(path[ptr]),
            dest_node_id=3 if path[-1] == 11 else 4,
            behavior_profile_id=0,
            remaining_route_ptr=ptr,
        )
        pool, slot_id = allocate_active_agent_slot(pool, payload)
        plugin_memory[int(slot_id)] = {
            "route_path": tuple(path),
            "origin_poi_id": 1,
            "dest_poi_id": 3 if path[-1] == 11 else 4,
            "trip_request_id": index,
        }
    if plugin_memory:
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
            plugin_memory=plugin_memory,
        )

    allocated_ids = tuple(range(1, len(active_paths) + 1))
    demand_state = {
        "trip_requests": tuple(trips),
        "queued_trip_requests": 1 if queued_trip else 0,
        "activated_trip_requests": 0 if queued_trip else 0,
        "pending_trip_requests": 1 if queued_trip else 0,
        "allocated_trip_request_ids": allocated_ids,
        "completed_trip_request_ids": (),
        "failed_trip_request_ids": (),
    }
    config = SimulationConfig(
        active_agent_capacity=pool.capacity,
        agent_backend=agent_backend,
        flow_backend=flow_backend,
    )
    return SimulationState(
        config=config,
        static=SimulationStaticRefs(
            scenario_id="runtime-flow-closure",
            pois=(
                POI(1, 1, POIType.HOME, node_id=1),
                POI(3, 2, POIType.WORKPLACE, node_id=3),
                *( (POI(4, 3, POIType.WORKPLACE, node_id=4),) if branch else () ),
            ),
            routing_static={"road_csr": road_csr},
        ),
        dynamic=SimulationDynamicRefs(
            demand_state=demand_state,
            active_agent_pool=pool,
            flow_link_state=link_state,
            flow_node_state=node_state,
            route_candidate_state=create_simulation_route_cache_state(),
            metrics_state={
                "generated_trip_total": len(trips),
                "completed_trips_total": 0,
                "failed_trips_total": 0,
                "pending_trip_requests": demand_state["pending_trip_requests"],
                "capacity_violation_count": 0,
            },
        ),
    )


def _step(state, key_seed: int = 7):
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.step import simulation_step

    return simulation_step(state, SimulationControl(), key_from_seed(key_seed))


def test_branching_commit_consumes_only_matching_turn_token() -> None:
    state = _closure_state(
        branch=True,
        queue=(2.0, 0.0, 0.0),
        capacity=(1.0, 1.0, 1.0),
        active_paths=((10, 11), (10, 12)),
        current_ptrs=(0, 0),
        turn_priority=(0.0, 1.0),
    )

    next_state, telemetry, _snapshot, _key = _step(state)

    pool = next_state.dynamic.active_agent_pool
    assert pool.current_link_id[:2].tolist() == [10, 12]
    assert pool.remaining_route_ptr[:2].tolist() == [0, 1]
    assert next_state.dynamic.flow_node_state.turn_flow.tolist() == [0.0, 1.0]
    assert next_state.dynamic.flow_link_state.queue_vehicles.tolist() == [1.0, 0.0, 1.0]
    assert telemetry.active_agent_moved_this_tick == 1
    assert next_state.dynamic.invariant_state.ok


def test_fractional_capacity_uses_deterministic_half_plus_half_residual() -> None:
    state = _closure_state(
        queue=(1.0, 0.0),
        capacity=(0.5, 1.0),
        active_paths=((10, 11),),
        current_ptrs=(0,),
    )

    first, first_telemetry, _snapshot, key = _step(state)
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.step import simulation_step

    second, second_telemetry, _snapshot, _key = simulation_step(
        first,
        SimulationControl(),
        key,
    )

    assert first.dynamic.active_agent_pool.current_link_id[0] == 10
    assert first.dynamic.flow_node_state.turn_flow.tolist() == [0.0]
    assert first.dynamic.flow_link_state.metadata["runtime_link_service_residual"][0] == pytest.approx(0.5)
    assert first_telemetry.active_agent_moved_this_tick == 0
    assert second.dynamic.active_agent_pool.current_link_id[0] == 11
    assert second.dynamic.flow_node_state.turn_flow.tolist() == [1.0]
    assert second.dynamic.flow_link_state.queue_vehicles.tolist() == [0.0, 1.0]
    assert second_telemetry.active_agent_moved_this_tick == 1
    assert second.dynamic.invariant_state.ok


def test_final_link_sink_atomically_removes_agent_and_queue_vehicle() -> None:
    state = _closure_state(
        queue=(0.0, 1.0),
        capacity=(1.0, 1.0),
        active_paths=((10, 11),),
        current_ptrs=(1,),
    )

    next_state, telemetry, _snapshot, _key = _step(state)

    assert next_state.dynamic.active_agent_pool.alive_count == 0
    assert next_state.dynamic.flow_link_state.queue_vehicles.tolist() == [0.0, 0.0]
    assert next_state.dynamic.flow_link_state.outflow_vehicles.tolist() == [0.0, 1.0]
    assert next_state.dynamic.demand_state["completed_trip_request_ids"] == (1,)
    assert telemetry.trip_completed_this_tick == 1
    assert next_state.dynamic.invariant_state.ok


def test_allocation_is_unadmitted_pending_to_active_and_cannot_move_same_tick() -> None:
    state = _closure_state(queued_trip=True)

    next_state, telemetry, _snapshot, _key = _step(state)

    assert next_state.dynamic.active_agent_pool.alive_count == 1
    assert next_state.dynamic.active_agent_pool.current_link_id[0] == 10
    assert next_state.dynamic.flow_link_state.queue_vehicles.tolist() == [1.0, 0.0]
    assert next_state.dynamic.demand_state["pending_trip_requests"] == 0
    assert next_state.dynamic.demand_state["activated_trip_requests"] == 0
    assert next_state.dynamic.demand_state["allocated_trip_request_ids"] == (1,)
    assert telemetry.active_agent_moved_this_tick == 0
    assert next_state.dynamic.invariant_state.ok


def test_missing_compiled_turn_and_explicit_rust_agent_contract_fail_closed() -> None:
    from metroflow.flow.state import NodeState
    from metroflow.sim.routing_runtime import rebuild_runtime_turn_demand

    state = _closure_state(
        queue=(1.0, 0.0),
        active_paths=((10, 11),),
        current_ptrs=(0,),
    )
    node = state.dynamic.flow_node_state
    empty_node = NodeState(
        turn_from_link_index=(),
        turn_to_link_index=(),
        turn_demand=(),
        turn_supply=(),
        turn_flow=(),
        signal_phase_index=node.signal_phase_index,
        signal_phase_timer=node.signal_phase_timer,
    )
    with pytest.raises(RuntimeError, match="no unique legal compiled turn"):
        rebuild_runtime_turn_demand(state.with_dynamic_updates(flow_node_state=empty_node))

    invalid_sink = _closure_state(
        queue=(1.0, 0.0),
        active_paths=((10,),),
        current_ptrs=(0,),
    )
    with pytest.raises(RuntimeError, match="does not terminate.*destination"):
        rebuild_runtime_turn_demand(invalid_sink)

    rust_state = replace(state, config=replace(state.config, agent_backend="rust_cpu"))
    with pytest.raises(RuntimeError, match="per-turn token contract"):
        _step(rust_state)

    rust_flow_state = replace(state, config=replace(state.config, flow_backend="rust_cpu"))
    with pytest.raises(RuntimeError, match="discrete-agent authority contract"):
        _step(rust_flow_state)

    auto_state = replace(
        state,
        config=replace(state.config, flow_backend="auto", agent_backend="auto"),
    )
    auto_next, _telemetry, _snapshot, _key = _step(auto_state)
    assert auto_next.dynamic.invariant_state.ok


def test_idle_or_removed_intent_residuals_are_cleared_not_banked() -> None:
    from metroflow.flow.engine import update_link_node_flow
    from metroflow.flow.state import LinkState, NodeState

    links = LinkState(
        queue_vehicles=(0.0, 0.0),
        inflow_vehicles=(0.0, 0.0),
        outflow_vehicles=(0.0, 0.0),
        travel_time_cost=(1.0, 1.0),
        capacity_veh_per_tick=(0.5, 1.0),
        incident_capacity_multiplier=(1.0, 1.0),
        metadata={
            "free_flow_travel_time_cost": np.ones((2,), dtype=np.float32),
            "runtime_link_service_residual": np.asarray((0.5, 0.0), dtype=np.float32),
            "runtime_link_receiving_residual": np.asarray((0.0, 0.5), dtype=np.float32),
        },
    )
    nodes = NodeState(
        turn_from_link_index=(0,),
        turn_to_link_index=(1,),
        turn_demand=(0.0,),
        turn_supply=(0.0,),
        turn_flow=(0.0,),
        signal_phase_index=(0, 0),
        signal_phase_timer=(0, 0),
        metadata={
            "runtime_turn_flow_residual": np.asarray((0.75,), dtype=np.float32),
            "runtime_sink_demand_by_link_index": np.zeros((2,), dtype=np.float32),
            "runtime_sink_flow_residual": np.asarray((0.25, 0.0), dtype=np.float32),
        },
    )

    result = update_link_node_flow(
        links,
        nodes,
        discrete_agent_authority=True,
    )

    assert result.link_state.metadata["runtime_link_service_residual"].tolist() == [0.0, 0.0]
    assert result.link_state.metadata["runtime_link_receiving_residual"].tolist() == [0.0, 0.0]
    assert result.node_state.metadata["runtime_turn_flow_residual"].tolist() == [0.0]
    assert result.node_state.metadata["runtime_sink_flow_residual"].tolist() == [0.0, 0.0]
    assert result.node_state.metadata["runtime_sink_flow_by_link_index"].tolist() == [0.0, 0.0]


def test_eager_demand_switch_is_independent_of_learning_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from metroflow.sim import step as step_module
    from metroflow.sim.config import SimulationConfig

    captured: list[bool] = []

    def fake_build_initial_simulation_state(**kwargs):
        captured.append(bool(kwargs["eager_trip_generation"]))
        return SimpleNamespace(state="state", rng_key="key")

    monkeypatch.setattr(
        step_module,
        "build_initial_simulation_state",
        fake_build_initial_simulation_state,
    )

    step_module.init_simulation(
        SimulationConfig(learning_enabled=True, eager_trip_generation=False),
        1,
    )
    step_module.init_simulation(
        SimulationConfig(learning_enabled=False, eager_trip_generation=True),
        2,
    )

    assert captured == [False, True]
