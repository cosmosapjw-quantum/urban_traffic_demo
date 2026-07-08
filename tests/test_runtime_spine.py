from __future__ import annotations

import numpy as np
import pytest


def _runtime_spine_state(
    *,
    disconnected: bool = False,
    queue_vehicles: tuple[float, ...] = (3.0, 0.0),
    capacity_veh_per_tick: tuple[float, ...] = (2.0, 2.0),
    turn_demand: tuple[float, ...] = (2.0,),
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
    from metroflow.demand.trips import TripRequest
    from metroflow.flow.state import LinkState, NodeState
    from metroflow.sim.active_agents import create_active_agent_pool
    from metroflow.sim.config import DayType, SimulationConfig, TimeBand
    from metroflow.sim.state import SimulationDynamicRefs, SimulationState, SimulationStaticRefs

    links = () if disconnected else (
        RoadLink(10, 1, 2, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
        RoadLink(11, 2, 3, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
    )
    turns = () if disconnected else (TurnMovement(10, 11, TurnType.THROUGH),)
    road_csr = build_road_network_csr(
        nodes=(Node(1), Node(2), Node(3)),
        links=links,
        turns=turns,
    )
    link_count = road_csr.link_count
    turn_count = road_csr.turn_count
    link_state = LinkState(
        queue_vehicles=np.asarray(() if disconnected else queue_vehicles, dtype=np.float32),
        inflow_vehicles=np.zeros((link_count,), dtype=np.float32),
        outflow_vehicles=np.zeros((link_count,), dtype=np.float32),
        travel_time_cost=np.ones((link_count,), dtype=np.float32),
        capacity_veh_per_tick=np.asarray(
            () if disconnected else capacity_veh_per_tick,
            dtype=np.float32,
        ),
        incident_capacity_multiplier=np.ones((link_count,), dtype=np.float32),
        metadata={"free_flow_travel_time_cost": np.ones((link_count,), dtype=np.float32)},
    )
    node_state = NodeState(
        turn_from_link_index=road_csr.turn_from_link_index,
        turn_to_link_index=road_csr.turn_to_link_index,
        turn_demand=np.asarray(() if disconnected else turn_demand, dtype=np.float32),
        turn_supply=np.zeros((turn_count,), dtype=np.float32),
        turn_flow=np.zeros((turn_count,), dtype=np.float32),
        signal_phase_index=np.zeros((road_csr.node_count,), dtype=np.int32),
        signal_phase_timer=np.zeros((road_csr.node_count,), dtype=np.int32),
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
    config = SimulationConfig(active_agent_capacity=4)
    return SimulationState(
        config=config,
        static=SimulationStaticRefs(
            scenario_id="runtime-spine-test",
            pois=(
                POI(1, 1, POIType.HOME, node_id=1),
                POI(2, 2, POIType.WORKPLACE, node_id=3),
            ),
            routing_static={"road_csr": road_csr},
            ui_network_geometry_version="runtime-spine-geom",
        ),
        dynamic=SimulationDynamicRefs(
            demand_state={
                "trip_requests": (trip,),
                "queued_trip_requests": 1,
                "pending_trip_requests": 1,
                "activated_trip_requests": 0,
            },
            active_agent_pool=create_active_agent_pool(4),
            flow_link_state=link_state,
            flow_node_state=node_state,
            metrics_state={
                "tick_index": 0,
                "queued_trip_requests": 1,
                "pending_trip_requests": 1,
                "completed_trips_total": 0,
                "failed_trips_total": 0,
                "generated_trip_total": 1,
                "capacity_violation_count": 0,
            },
        ),
    )


def test_simulation_config_exposes_runtime_spine_defaults_and_validates_backends() -> None:
    from metroflow.sim.config import SimulationConfig

    config = SimulationConfig()

    assert config.edge_backend == "baseline"
    assert config.flow_backend == "baseline"
    assert config.routing_backend == "baseline"
    assert config.route_max_candidates == 1
    assert config.route_max_hops == 64
    assert config.route_refresh_interval_ticks == 8

    with pytest.raises(ValueError, match="edge_backend"):
        SimulationConfig(edge_backend="bogus")
    with pytest.raises(ValueError, match="flow_backend"):
        SimulationConfig(flow_backend="bogus")
    with pytest.raises(ValueError, match="routing_backend"):
        SimulationConfig(routing_backend="jax")
    with pytest.raises(ValueError, match="route_max_candidates"):
        SimulationConfig(route_max_candidates=2)


def test_simulation_step_updates_flow_after_events_and_records_runtime_telemetry() -> None:
    from metroflow.flow.events import TrafficEvent
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.step import simulation_step

    state = _runtime_spine_state()
    blocked = TrafficEvent(
        event_id=7,
        event_type="accident",
        start_tick=0,
        end_tick=5,
        target_scope={"link_ids": (10,)},
        severity=1.0,
        effect_model="closure",
    )

    next_state, telemetry, _snapshot, _key = simulation_step(
        state,
        SimulationControl(inject_event=blocked),
        key_from_seed(3),
    )

    link_state = next_state.dynamic.flow_link_state
    assert link_state.incident_capacity_multiplier.tolist() == [0.0, 1.0]
    assert link_state.queue_vehicles.tolist() == [3.0, 0.0]
    assert telemetry.flow_backend == "baseline"
    assert telemetry.flow_update_wall_ns >= 0
    assert telemetry.queue_vehicles_total == 3.0
    assert next_state.dynamic.metrics_state["flow_backend"] == "baseline"
    assert next_state.dynamic.metadata["us2_active_event_affected_link_ids"] == (10,)


def test_simulation_step_refreshes_route_cache_and_moves_active_agent_deterministically() -> None:
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.step import simulation_step

    state = _runtime_spine_state(capacity_veh_per_tick=(2.0, 10.0))

    first_state, first_telemetry, _snapshot, key = simulation_step(
        state,
        SimulationControl(),
        key_from_seed(5),
    )

    route_state = first_state.dynamic.route_candidate_state
    assert route_state is not None
    assert route_state.candidate_sets[(1, 2)].candidate_paths == ((10, 11),)
    assert first_state.dynamic.active_agent_pool.alive_count == 1
    assert first_state.dynamic.active_agent_pool.current_link_id[0].item() == 10
    assert first_state.dynamic.active_agent_pool.remaining_route_ptr[0].item() == 0
    assert first_telemetry.active_agent_moved_this_tick == 0
    assert first_telemetry.route_candidate_refresh_total == 1
    assert first_telemetry.dynamic_potential_recompute_total == 1

    second_state, second_telemetry, _snapshot, _key = simulation_step(
        first_state,
        SimulationControl(),
        key,
    )

    assert second_state.dynamic.active_agent_pool.alive_count == 1
    assert second_state.dynamic.active_agent_pool.current_link_id[0].item() == 11
    assert second_state.dynamic.active_agent_pool.remaining_route_ptr[0].item() == 1
    assert second_telemetry.active_agent_moved_this_tick == 1
    assert second_state.dynamic.metrics_state["route_candidate_reuse_total"] >= 1

    third_state, third_telemetry, _snapshot, _key = simulation_step(
        second_state,
        SimulationControl(),
        _key,
    )

    assert third_state.dynamic.active_agent_pool.alive_count == 0
    assert third_telemetry.trip_completed_this_tick == 1
    assert third_state.dynamic.metrics_state["completed_trips_total"] == 1


def test_simulation_step_blocks_active_agent_movement_without_flow_outflow_budget() -> None:
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.step import simulation_step

    state = _runtime_spine_state(
        queue_vehicles=(0.0, 0.0),
        capacity_veh_per_tick=(2.0, 10.0),
        turn_demand=(0.0,),
    )

    first_state, first_telemetry, _snapshot, key = simulation_step(
        state,
        SimulationControl(),
        key_from_seed(7),
    )
    second_state, second_telemetry, _snapshot, _key = simulation_step(
        first_state,
        SimulationControl(),
        key,
    )

    assert first_state.dynamic.active_agent_pool.alive_count == 1
    assert first_state.dynamic.active_agent_pool.current_link_id[0].item() == 10
    assert first_telemetry.active_agent_moved_this_tick == 0
    assert first_state.dynamic.flow_link_state.queue_vehicles.tolist() == [1.0, 0.0]
    assert first_state.dynamic.flow_link_state.travel_time_cost[0].item() == pytest.approx(
        1.0 * (1.0 + (1.0 / (2.0 + 1e-3)))
    )
    assert first_telemetry.queue_vehicles_total == 1.0
    assert second_state.dynamic.active_agent_pool.alive_count == 1
    assert second_state.dynamic.active_agent_pool.current_link_id[0].item() == 10
    assert second_state.dynamic.active_agent_pool.remaining_route_ptr[0].item() == 0
    assert second_telemetry.active_agent_moved_this_tick == 0
    assert second_telemetry.trip_completed_this_tick == 0
    assert second_state.dynamic.flow_link_state.queue_vehicles.tolist() == [1.0, 0.0]


def test_simulation_step_completes_agent_already_resident_on_final_link() -> None:
    from dataclasses import replace

    from metroflow.demand.trips import TripRequestStatus
    from metroflow.sim.active_agents import ActiveAgentSlot, ActiveAgentPool, allocate_active_agent_slot
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.routing_runtime import refresh_runtime_route_candidates
    from metroflow.sim.step import simulation_step

    state = _runtime_spine_state(capacity_veh_per_tick=(2.0, 10.0))
    activated_trips = tuple(
        replace(trip, status=TripRequestStatus.ACTIVATED)
        for trip in state.dynamic.demand_state["trip_requests"]
    )
    route_state, _counters = refresh_runtime_route_candidates(
        state.with_dynamic_updates(
            demand_state={
                **state.dynamic.demand_state,
                "trip_requests": activated_trips,
                "activated_trip_requests": 1,
                "pending_trip_requests": 1,
            }
        ),
        force_refresh=True,
    )

    payload = ActiveAgentSlot.spawn(
        citizen_id=101,
        trip_id=1,
        current_link_id=11,
        dest_node_id=3,
        behavior_profile_id=0,
        remaining_route_ptr=1,
    )
    pool, slot_id = allocate_active_agent_slot(state.dynamic.active_agent_pool, payload)
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
                "route_path": (10, 11),
                "origin_poi_id": 1,
                "dest_poi_id": 2,
                "trip_request_id": 1,
            }
        },
    )
    ready_state = state.with_dynamic_updates(
        active_agent_pool=pool,
        route_candidate_state=route_state,
        demand_state={
            **state.dynamic.demand_state,
            "trip_requests": activated_trips,
            "allocated_trip_request_ids": (1,),
            "activated_trip_requests": 1,
            "pending_trip_requests": 1,
        },
    )

    next_state, telemetry, _snapshot, _key = simulation_step(
        ready_state,
        SimulationControl(),
        key_from_seed(19),
    )

    assert next_state.dynamic.active_agent_pool.alive_count == 0
    assert telemetry.trip_completed_this_tick == 1
    assert next_state.dynamic.metrics_state["completed_trips_total"] == 1


def test_simulation_step_fails_no_route_trip_without_allocating_agent() -> None:
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.step import simulation_step

    state = _runtime_spine_state(disconnected=True)

    next_state, telemetry, _snapshot, _key = simulation_step(
        state,
        SimulationControl(),
        key_from_seed(9),
    )

    assert next_state.dynamic.active_agent_pool.alive_count == 0
    assert telemetry.trip_failed_this_tick == 1
    assert next_state.dynamic.metrics_state["failed_trips_total"] == 1
    assert next_state.dynamic.route_candidate_state.candidate_sets[(1, 2)].candidate_paths == ()


def test_runtime_replay_records_backend_and_cache_fingerprints() -> None:
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.replay import (
        RuntimeReplayRequest,
        make_runtime_replay_boundary,
        replay_simulation_sequence,
    )
    from metroflow.sim.rng import key_from_seed

    state = _runtime_spine_state()
    boundary = make_runtime_replay_boundary(state)
    result = replay_simulation_sequence(
        RuntimeReplayRequest(
            name="replay_runtime_spine",
            initial_state=state,
            declared_boundary=boundary,
            controls=(SimulationControl(),),
            rng_key=key_from_seed(11),
            num_steps=1,
        )
    )

    assert result.name == "replay_simulation_sequence"
    assert result.final_tick == 1
    assert result.initial_boundary.flow_backend == "baseline"
    assert result.initial_boundary.routing_backend == "baseline"
    assert result.cache_fingerprint
    assert len(result.telemetry_log) == 1


def test_measured_runtime_spine_benchmark_preserves_runtime_backend_metadata() -> None:
    from metroflow.metrics.benchmarks import (
        MeasuredRuntimeBenchmarkConfig,
        MeasuredRuntimeBenchmarkResult,
        run_measured_runtime_spine_benchmark,
    )
    from metroflow.sim.rng import key_from_seed

    state = _runtime_spine_state()
    result = run_measured_runtime_spine_benchmark(
        state,
        key_from_seed(17),
        MeasuredRuntimeBenchmarkConfig(workload_name="runtime-spine", num_steps=2),
    )

    assert isinstance(result, MeasuredRuntimeBenchmarkResult)
    assert result.name == "measured_runtime_spine"
    assert result.flow_backend == "baseline"
    assert result.routing_backend == "baseline"
    assert result.route_candidate_refresh_total >= 1
    assert result.final_tick == 2
