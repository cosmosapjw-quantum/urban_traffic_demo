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


def _runtime_state_with_agent_on_final_link(*, final_link_capacity: float):
    from dataclasses import replace

    from metroflow.demand.trips import TripRequestStatus
    from metroflow.sim.active_agents import ActiveAgentSlot, ActiveAgentPool, allocate_active_agent_slot

    state = _runtime_spine_state(capacity_veh_per_tick=(2.0, final_link_capacity))
    activated_trips = tuple(
        replace(trip, status=TripRequestStatus.ACTIVATED)
        for trip in state.dynamic.demand_state["trip_requests"]
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
    return state.with_dynamic_updates(
        active_agent_pool=pool,
        demand_state={
            **state.dynamic.demand_state,
            "trip_requests": activated_trips,
            "allocated_trip_request_ids": (1,),
            "activated_trip_requests": 1,
            "pending_trip_requests": 1,
        },
    )


def _runtime_reroute_state(*, reroute_cooldown_ticks: int = 0):
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
    from metroflow.flow.events import TrafficEvent, TrafficEventSchedulerState
    from metroflow.flow.state import LinkState, NodeState
    from metroflow.routing.behavior_profiles import RouteChoiceProfile
    from metroflow.sim.active_agents import ActiveAgentSlot, create_active_agent_pool, allocate_active_agent_slot
    from metroflow.sim.config import DayType, SimulationConfig, TimeBand
    from metroflow.sim.routing_runtime import create_simulation_route_cache_state
    from metroflow.sim.state import SimulationDynamicRefs, SimulationState, SimulationStaticRefs

    road_csr = build_road_network_csr(
        nodes=(Node(1), Node(2), Node(3), Node(4)),
        links=(
            RoadLink(10, 1, 2, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
            RoadLink(11, 2, 3, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
            RoadLink(12, 3, 4, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
            RoadLink(20, 2, 4, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
        ),
        turns=(
            TurnMovement(10, 11, TurnType.THROUGH),
            TurnMovement(10, 20, TurnType.RIGHT),
            TurnMovement(11, 12, TurnType.THROUGH),
        ),
    )
    link_state = LinkState(
        queue_vehicles=np.zeros((road_csr.link_count,), dtype=np.float32),
        inflow_vehicles=np.zeros((road_csr.link_count,), dtype=np.float32),
        outflow_vehicles=np.zeros((road_csr.link_count,), dtype=np.float32),
        travel_time_cost=np.asarray((1.0, 100.0, 100.0, 1.0), dtype=np.float32),
        capacity_veh_per_tick=np.full((road_csr.link_count,), 2.0, dtype=np.float32),
        incident_capacity_multiplier=np.ones((road_csr.link_count,), dtype=np.float32),
        metadata={
            "free_flow_travel_time_cost": np.ones((road_csr.link_count,), dtype=np.float32),
            "runtime_flow_generation": 0,
            "runtime_incident_generation": 1,
        },
    )
    node_state = NodeState(
        turn_from_link_index=road_csr.turn_from_link_index,
        turn_to_link_index=road_csr.turn_to_link_index,
        turn_demand=np.zeros((road_csr.turn_count,), dtype=np.float32),
        turn_supply=np.zeros((road_csr.turn_count,), dtype=np.float32),
        turn_flow=np.zeros((road_csr.turn_count,), dtype=np.float32),
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
        status=TripRequestStatus.ACTIVATED,
    )
    pool = create_active_agent_pool(4)
    payload = ActiveAgentSlot.spawn(
        citizen_id=101,
        trip_id=1,
        current_link_id=10,
        dest_node_id=4,
        behavior_profile_id=0,
        remaining_route_ptr=0,
        reroute_cooldown_ticks=reroute_cooldown_ticks,
    )
    pool, slot_id = allocate_active_agent_slot(pool, payload)
    pool.plugin_memory[int(slot_id)] = {
        "route_path": (10, 11, 12),
        "origin_poi_id": 1,
        "dest_poi_id": 2,
        "trip_request_id": 1,
    }
    active_event = TrafficEvent(
        event_id=5,
        event_type="accident",
        start_tick=0,
        end_tick=20,
        target_scope={"link_ids": (11,)},
        severity=1.0,
        effect_model="closure",
        status="active",
    )
    return SimulationState(
        config=SimulationConfig(active_agent_capacity=4),
        static=SimulationStaticRefs(
            scenario_id="runtime-reroute-test",
            pois=(
                POI(1, 1, POIType.HOME, node_id=1),
                POI(2, 2, POIType.WORKPLACE, node_id=4),
            ),
            routing_static={"road_csr": road_csr},
            ui_network_geometry_version="runtime-reroute-geom",
            metadata={
                "route_choice_profiles": (
                    RouteChoiceProfile(
                        behavior_profile_id=0,
                        delay_sensitivity=2.0,
                        reroute_willingness=1.0,
                        persistence_bias=0.0,
                        exploration_bias=0.5,
                    ),
                )
            },
        ),
        dynamic=SimulationDynamicRefs(
            demand_state={
                "trip_requests": (trip,),
                "allocated_trip_request_ids": (1,),
                "queued_trip_requests": 0,
                "pending_trip_requests": 1,
                "activated_trip_requests": 1,
            },
            active_agent_pool=pool,
            flow_link_state=link_state,
            flow_node_state=node_state,
            event_state=TrafficEventSchedulerState(active_events=(active_event,)),
            route_candidate_state=create_simulation_route_cache_state(),
            metrics_state={
                "tick_index": 8,
                "queued_trip_requests": 0,
                "pending_trip_requests": 1,
                "completed_trips_total": 0,
                "failed_trips_total": 0,
                "generated_trip_total": 1,
                "capacity_violation_count": 0,
            },
        ),
    ).with_clock(tick_index=8)


def _runtime_ranked_reroute_state():
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
    from metroflow.flow.events import TrafficEvent, TrafficEventSchedulerState
    from metroflow.flow.state import LinkState, NodeState
    from metroflow.routing.behavior_profiles import RouteChoiceProfile
    from metroflow.sim.active_agents import ActiveAgentSlot, create_active_agent_pool, allocate_active_agent_slot
    from metroflow.sim.config import DayType, SimulationConfig, TimeBand
    from metroflow.sim.routing_runtime import create_simulation_route_cache_state
    from metroflow.sim.state import SimulationDynamicRefs, SimulationState, SimulationStaticRefs

    road_csr = build_road_network_csr(
        nodes=(Node(1), Node(2), Node(3), Node(4), Node(5), Node(6), Node(7)),
        links=(
            RoadLink(10, 1, 2, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
            RoadLink(11, 2, 3, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
            RoadLink(12, 3, 6, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
            RoadLink(20, 2, 4, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
            RoadLink(21, 4, 6, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
            RoadLink(22, 4, 7, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
            RoadLink(23, 7, 6, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
            RoadLink(30, 2, 5, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
            RoadLink(31, 5, 6, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
        ),
        turns=(
            TurnMovement(10, 11, TurnType.THROUGH),
            TurnMovement(11, 12, TurnType.THROUGH),
            TurnMovement(10, 20, TurnType.RIGHT),
            TurnMovement(20, 21, TurnType.THROUGH),
            TurnMovement(20, 22, TurnType.LEFT),
            TurnMovement(22, 23, TurnType.THROUGH),
            TurnMovement(10, 30, TurnType.LEFT),
            TurnMovement(30, 31, TurnType.THROUGH),
        ),
    )
    link_state = LinkState(
        queue_vehicles=np.zeros((road_csr.link_count,), dtype=np.float32),
        inflow_vehicles=np.zeros((road_csr.link_count,), dtype=np.float32),
        outflow_vehicles=np.zeros((road_csr.link_count,), dtype=np.float32),
        travel_time_cost=np.asarray(
            (1.0, 5.0, 5.0, 2.0, 2.0, 2.5, 2.5, 2.5, 2.5),
            dtype=np.float32,
        ),
        capacity_veh_per_tick=np.full((road_csr.link_count,), 2.0, dtype=np.float32),
        incident_capacity_multiplier=np.ones((road_csr.link_count,), dtype=np.float32),
        metadata={
            "free_flow_travel_time_cost": np.ones((road_csr.link_count,), dtype=np.float32),
            "runtime_flow_generation": 0,
            "runtime_incident_generation": 1,
        },
    )
    node_state = NodeState(
        turn_from_link_index=road_csr.turn_from_link_index,
        turn_to_link_index=road_csr.turn_to_link_index,
        turn_demand=np.zeros((road_csr.turn_count,), dtype=np.float32),
        turn_supply=np.zeros((road_csr.turn_count,), dtype=np.float32),
        turn_flow=np.zeros((road_csr.turn_count,), dtype=np.float32),
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
        status=TripRequestStatus.ACTIVATED,
    )
    pool = create_active_agent_pool(4)
    payload = ActiveAgentSlot.spawn(
        citizen_id=101,
        trip_id=1,
        current_link_id=10,
        dest_node_id=6,
        behavior_profile_id=0,
        remaining_route_ptr=0,
    )
    pool, slot_id = allocate_active_agent_slot(pool, payload)
    pool.plugin_memory[int(slot_id)] = {
        "route_path": (10, 11, 12),
        "origin_poi_id": 1,
        "dest_poi_id": 2,
        "trip_request_id": 1,
    }
    active_event = TrafficEvent(
        event_id=6,
        event_type="accident",
        start_tick=0,
        end_tick=20,
        target_scope={"link_ids": (11,)},
        severity=1.0,
        effect_model="closure",
        status="active",
    )
    return SimulationState(
        config=SimulationConfig(
            active_agent_capacity=4,
            route_max_candidates=3,
            route_path_size_gamma=4.0,
        ),
        static=SimulationStaticRefs(
            scenario_id="runtime-ranked-reroute-test",
            pois=(
                POI(1, 1, POIType.HOME, node_id=1),
                POI(2, 2, POIType.WORKPLACE, node_id=6),
            ),
            routing_static={"road_csr": road_csr},
            ui_network_geometry_version="runtime-ranked-reroute-geom",
            metadata={
                "route_choice_profiles": (
                    RouteChoiceProfile(
                        behavior_profile_id=0,
                        delay_sensitivity=2.0,
                        reroute_willingness=1.0,
                        persistence_bias=0.0,
                        exploration_bias=0.5,
                    ),
                )
            },
        ),
        dynamic=SimulationDynamicRefs(
            demand_state={
                "trip_requests": (trip,),
                "allocated_trip_request_ids": (1,),
                "queued_trip_requests": 0,
                "pending_trip_requests": 1,
                "activated_trip_requests": 1,
            },
            active_agent_pool=pool,
            flow_link_state=link_state,
            flow_node_state=node_state,
            event_state=TrafficEventSchedulerState(active_events=(active_event,)),
            route_candidate_state=create_simulation_route_cache_state(),
            metrics_state={
                "tick_index": 8,
                "queued_trip_requests": 0,
                "pending_trip_requests": 1,
                "completed_trips_total": 0,
                "failed_trips_total": 0,
                "generated_trip_total": 1,
                "capacity_violation_count": 0,
            },
        ),
    ).with_clock(tick_index=8)


def test_simulation_config_exposes_runtime_spine_defaults_and_validates_backends() -> None:
    from metroflow.sim.config import SimulationConfig

    config = SimulationConfig()

    assert config.edge_backend == "baseline"
    assert config.flow_backend == "baseline"
    assert config.routing_backend == "baseline"
    assert config.route_max_candidates == 1
    assert config.route_max_hops == 64
    assert config.route_refresh_interval_ticks == 8
    assert config.route_path_size_gamma == 0.0
    assert SimulationConfig(route_max_candidates=2).route_max_candidates == 2
    assert SimulationConfig(route_path_size_gamma=1.5).route_path_size_gamma == 1.5

    with pytest.raises(ValueError, match="edge_backend"):
        SimulationConfig(edge_backend="bogus")
    with pytest.raises(ValueError, match="flow_backend"):
        SimulationConfig(flow_backend="bogus")
    with pytest.raises(ValueError, match="routing_backend"):
        SimulationConfig(routing_backend="jax")
    with pytest.raises(ValueError, match="route_max_candidates"):
        SimulationConfig(route_max_candidates=0)
    with pytest.raises(ValueError, match="route_path_size_gamma"):
        SimulationConfig(route_path_size_gamma=-0.1)


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


def test_runtime_final_link_completion_waits_for_sink_discharge_capacity() -> None:
    from metroflow.sim.routing_runtime import advance_runtime_active_agents

    state = _runtime_state_with_agent_on_final_link(final_link_capacity=0.0)

    next_pool, counters, demand_state, _link_state = advance_runtime_active_agents(state)

    assert next_pool.alive_count == 1
    assert next_pool.current_link_id[0].item() == 11
    assert counters["trip_completed_this_tick"] == 0
    assert counters["active_agent_sink_wait_this_tick"] == 1
    assert demand_state.get("completed_trip_request_ids", ()) == ()


def test_simulation_step_reports_final_link_sink_wait_telemetry() -> None:
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.step import simulation_step

    state = _runtime_state_with_agent_on_final_link(final_link_capacity=0.0)

    next_state, telemetry, _snapshot, _key = simulation_step(
        state,
        SimulationControl(),
        key_from_seed(29),
    )

    assert next_state.dynamic.active_agent_pool.alive_count == 1
    assert telemetry.trip_completed_this_tick == 0
    assert telemetry.active_agent_sink_wait_this_tick == 1
    assert next_state.dynamic.metrics_state["active_agent_sink_wait_this_tick"] == 1


def test_simulation_telemetry_mapping_round_trip_preserves_runtime_counters() -> None:
    from metroflow.sim.control import SimulationTelemetry

    telemetry = SimulationTelemetry(
        tick_index=3,
        active_agent_count=2,
        flow_backend="rust_cpu",
        routing_backend="rust_cpu",
        flow_update_wall_ns=55,
        active_agent_moved_this_tick=4,
        active_agent_sink_wait_this_tick=3,
        active_agent_rerouted_this_tick=2,
        active_agent_reroute_cooldown_this_tick=1,
    )

    round_tripped = SimulationTelemetry.from_mapping(telemetry.as_dict())

    assert round_tripped.flow_backend == "rust_cpu"
    assert round_tripped.routing_backend == "rust_cpu"
    assert round_tripped.flow_update_wall_ns == 55
    assert round_tripped.active_agent_moved_this_tick == 4
    assert round_tripped.active_agent_sink_wait_this_tick == 3
    assert round_tripped.active_agent_rerouted_this_tick == 2
    assert round_tripped.active_agent_reroute_cooldown_this_tick == 1


def test_runtime_reroute_replaces_remaining_tail_on_incident() -> None:
    from metroflow.sim.routing_runtime import advance_runtime_active_agents

    state = _runtime_reroute_state()

    pool, counters, _demand_state, _link_state = advance_runtime_active_agents(state)

    assert pool.plugin_memory[0]["route_path"] == (10, 20)
    assert pool.reroute_cooldown_ticks[0].item() == 3
    assert counters["active_agent_rerouted_this_tick"] == 1
    assert counters["active_agent_reroute_cooldown_this_tick"] == 0
    assert counters["active_agent_moved_this_tick"] == 0


def test_runtime_reroute_cooldown_preserves_existing_tail() -> None:
    from metroflow.sim.routing_runtime import advance_runtime_active_agents

    state = _runtime_reroute_state(reroute_cooldown_ticks=2)

    pool, counters, _demand_state, _link_state = advance_runtime_active_agents(state)

    assert pool.plugin_memory[0]["route_path"] == (10, 11, 12)
    assert pool.reroute_cooldown_ticks[0].item() == 1
    assert counters["active_agent_rerouted_this_tick"] == 0
    assert counters["active_agent_reroute_cooldown_this_tick"] == 1


def test_runtime_reroute_applies_ranked_path_size_candidate_selection() -> None:
    from metroflow.sim.routing_runtime import advance_runtime_active_agents

    state = _runtime_ranked_reroute_state()

    pool, counters, _demand_state, _link_state = advance_runtime_active_agents(state)

    memory = pool.plugin_memory[0]
    assert memory["route_path"] == (10, 30, 31)
    assert memory["selected_candidate_index"] == 1
    assert memory["selected_candidate_id"] == 1
    assert memory["selected_candidate_count"] == 3
    assert memory["selected_candidate_path_cost"] == pytest.approx(5.0)
    assert memory["selected_candidate_path_size_factor"] == pytest.approx(1.0)
    assert memory["selected_candidate_utility"] == pytest.approx(-5.0)
    assert memory["last_reroute_reason"] == "reroute"
    assert counters["active_agent_rerouted_this_tick"] == 1


def test_runtime_reroute_counters_accumulate_for_run_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.sim import step as step_module
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.run_summary import build_baseline_run_summary

    state = _runtime_spine_state()

    def fake_advance_runtime_active_agents(state):
        return (
            state.dynamic.active_agent_pool,
            {
                "active_agent_rerouted_this_tick": 2,
                "active_agent_reroute_cooldown_this_tick": 1,
            },
            state.dynamic.demand_state,
            state.dynamic.flow_link_state,
        )

    monkeypatch.setattr(
        step_module,
        "advance_runtime_active_agents",
        fake_advance_runtime_active_agents,
    )

    next_state, telemetry, _snapshot, _key = step_module.simulation_step(
        state,
        SimulationControl(),
        key_from_seed(23),
    )
    summary = build_baseline_run_summary(next_state)

    assert telemetry.active_agent_rerouted_this_tick == 2
    assert telemetry.active_agent_reroute_cooldown_this_tick == 1
    assert next_state.dynamic.metrics_state["us2_reroute_decisions_total"] == 2
    assert next_state.dynamic.metrics_state["us2_persistence_decisions_total"] == 1
    assert summary.reroute_decisions_total == 2
    assert summary.persistence_decisions_total == 1
    assert summary.disruption_response_metrics_available is True


def test_runtime_sink_wait_counters_accumulate_for_run_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.sim import step as step_module
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.run_summary import build_baseline_run_summary

    state = _runtime_spine_state()

    def fake_advance_runtime_active_agents(state):
        return (
            state.dynamic.active_agent_pool,
            {"active_agent_sink_wait_this_tick": 3},
            state.dynamic.demand_state,
            state.dynamic.flow_link_state,
        )

    monkeypatch.setattr(
        step_module,
        "advance_runtime_active_agents",
        fake_advance_runtime_active_agents,
    )

    next_state, telemetry, _snapshot, _key = step_module.simulation_step(
        state,
        SimulationControl(),
        key_from_seed(31),
    )
    summary = build_baseline_run_summary(next_state)

    assert telemetry.active_agent_sink_wait_this_tick == 3
    assert next_state.dynamic.metrics_state["active_agent_sink_wait_total"] == 3
    assert summary.active_agent_sink_wait_total == 3


def test_runtime_route_timing_stats_propagate_to_run_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.sim import step as step_module
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.routing_runtime import SimulationRouteCacheState
    from metroflow.sim.run_summary import build_baseline_run_summary

    state = _runtime_spine_state()

    def fake_refresh_runtime_route_candidates(_state):
        return (
            SimulationRouteCacheState(
                stats={
                    "route_candidate_refresh_total": 2,
                    "route_candidate_reuse_total": 1,
                    "dynamic_potential_recompute_total": 3,
                    "dynamic_potential_cache_hits_total": 4,
                    "route_candidate_refresh_seconds_total": 0.125,
                    "dynamic_potential_recompute_seconds_total": 0.25,
                    "routing_compile_seconds_estimate_total": 0.5,
                }
            ),
            {},
        )

    def fake_advance_runtime_active_agents(state):
        return (
            state.dynamic.active_agent_pool,
            {},
            state.dynamic.demand_state,
            state.dynamic.flow_link_state,
        )

    monkeypatch.setattr(
        step_module,
        "refresh_runtime_route_candidates",
        fake_refresh_runtime_route_candidates,
    )
    monkeypatch.setattr(
        step_module,
        "advance_runtime_active_agents",
        fake_advance_runtime_active_agents,
    )

    next_state, _telemetry, _snapshot, _key = step_module.simulation_step(
        state,
        SimulationControl(),
        key_from_seed(37),
    )
    summary = build_baseline_run_summary(next_state)

    assert next_state.dynamic.metrics_state["route_candidate_refresh_seconds_total"] == 0.125
    assert next_state.dynamic.metrics_state["dynamic_potential_recompute_seconds_total"] == 0.25
    assert next_state.dynamic.metrics_state["routing_compile_seconds_estimate_total"] == 0.5
    assert summary.route_candidate_refresh_seconds_total == 0.125
    assert summary.dynamic_potential_recompute_seconds_total == 0.25
    assert summary.routing_compile_seconds_estimate_total == 0.5


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


def test_active_agent_allocation_records_selected_candidate_metadata() -> None:
    from dataclasses import replace

    from metroflow.demand.trips import TripRequestStatus
    from metroflow.routing.candidates import RouteCandidateSet
    from metroflow.sim.routing_runtime import (
        SimulationRouteCacheState,
        advance_runtime_active_agents,
    )

    state = _runtime_spine_state()
    activated_trips = tuple(
        replace(trip, status=TripRequestStatus.ACTIVATED)
        for trip in state.dynamic.demand_state["trip_requests"]
    )
    candidate_set = RouteCandidateSet(
        od_key=(1, 2),
        candidate_ids=(7, 8),
        candidate_paths=((10,), (10, 11)),
        last_refresh_tick=0,
        metadata={
            "candidate_path_costs": (3.0, 2.0),
            "candidate_path_size_factors": (1.0, 0.75),
        },
    )
    state = state.with_dynamic_updates(
        demand_state={
            **state.dynamic.demand_state,
            "trip_requests": activated_trips,
            "queued_trip_requests": 0,
            "pending_trip_requests": 1,
            "activated_trip_requests": 1,
        },
        route_candidate_state=SimulationRouteCacheState(
            candidate_sets={(1, 2): candidate_set},
        ),
    )

    pool, counters, demand_state, _link_state = advance_runtime_active_agents(state)

    assert pool is not None
    assert counters["trip_allocated_this_tick"] == 1
    assert demand_state["allocated_trip_request_ids"] == (1,)
    memory = pool.plugin_memory[0]
    assert memory["route_path"] == (10, 11)
    assert memory["selected_candidate_index"] == 1
    assert memory["selected_candidate_id"] == 8
    assert memory["selected_candidate_count"] == 2
    assert memory["selected_candidate_path_cost"] == 2.0
    assert memory["selected_candidate_path_size_factor"] == 0.75


def test_active_agent_allocation_applies_path_size_correction_when_configured() -> None:
    from dataclasses import replace

    from metroflow.demand.trips import TripRequestStatus
    from metroflow.routing.candidates import RouteCandidateSet
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.routing_runtime import (
        SimulationRouteCacheState,
        advance_runtime_active_agents,
    )

    state = _runtime_spine_state()
    state.config = SimulationConfig(
        active_agent_capacity=4,
        route_path_size_gamma=2.0,
    )
    activated_trips = tuple(
        replace(trip, status=TripRequestStatus.ACTIVATED)
        for trip in state.dynamic.demand_state["trip_requests"]
    )
    candidate_set = RouteCandidateSet(
        od_key=(1, 2),
        candidate_ids=(7, 8),
        candidate_paths=((10,), (10, 11)),
        last_refresh_tick=0,
        metadata={
            "candidate_path_costs": (2.0, 3.0),
            "candidate_path_size_factors": (0.2, 1.0),
        },
    )
    state = state.with_dynamic_updates(
        demand_state={
            **state.dynamic.demand_state,
            "trip_requests": activated_trips,
            "queued_trip_requests": 0,
            "pending_trip_requests": 1,
            "activated_trip_requests": 1,
        },
        route_candidate_state=SimulationRouteCacheState(
            candidate_sets={(1, 2): candidate_set},
        ),
    )

    pool, counters, _demand_state, _link_state = advance_runtime_active_agents(state)

    assert pool is not None
    assert counters["trip_allocated_this_tick"] == 1
    memory = pool.plugin_memory[0]
    assert memory["route_path"] == (10, 11)
    assert memory["selected_candidate_index"] == 1
    assert memory["selected_candidate_id"] == 8
    assert memory["selected_candidate_utility"] == pytest.approx(-3.0)


def test_candidate_route_selection_uses_explicit_rust_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.routing.candidates import RouteCandidateSet
    from metroflow.sim import routing_runtime

    candidate_set = RouteCandidateSet(
        od_key=(1, 2),
        candidate_ids=(7, 8),
        candidate_paths=((10,), (10, 11)),
        last_refresh_tick=0,
        metadata={
            "candidate_path_costs": (2.0, 3.0),
            "candidate_path_size_factors": (0.2, 1.0),
        },
    )
    calls = []

    def fake_select_route_candidate_index_rust(**kwargs):
        calls.append(kwargs)
        return 1, -3.0

    monkeypatch.setattr(
        routing_runtime,
        "select_route_candidate_index_rust",
        fake_select_route_candidate_index_rust,
        raising=False,
    )

    selection = routing_runtime._select_candidate_route(
        candidate_set,
        path_size_gamma=2.0,
        routing_backend="rust_cpu",
    )

    assert calls
    assert calls[0]["candidate_paths"] == ((10,), (10, 11))
    assert selection is not None
    assert selection.candidate_index == 1
    assert selection.candidate_id == 8
    assert selection.path == (10, 11)
    assert selection.utility == pytest.approx(-3.0)
    assert selection.selection_backend == "rust_cpu_candidate_selection"


def test_auto_candidate_route_selection_falls_back_to_host_when_rust_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.routing.candidates import RouteCandidateSet
    from metroflow.sim import routing_runtime

    candidate_set = RouteCandidateSet(
        od_key=(1, 2),
        candidate_ids=(7, 8),
        candidate_paths=((10,), (10, 11)),
        last_refresh_tick=0,
        metadata={
            "candidate_path_costs": (2.0, 3.0),
            "candidate_path_size_factors": (0.2, 1.0),
        },
    )

    def fake_select_route_candidate_index_rust(**_kwargs):
        raise RuntimeError("Rust CPU routing backend failed: synthetic selection failure")

    monkeypatch.setattr(routing_runtime, "rust_routing_backend_available", lambda: True)
    monkeypatch.setattr(
        routing_runtime,
        "select_route_candidate_index_rust",
        fake_select_route_candidate_index_rust,
        raising=False,
    )

    selection = routing_runtime._select_candidate_route(
        candidate_set,
        path_size_gamma=2.0,
        routing_backend="auto",
    )

    assert selection is not None
    assert selection.candidate_index == 1
    assert selection.candidate_id == 8
    assert selection.utility == pytest.approx(-3.0)
    assert selection.selection_backend == "python_host_candidate_selection"


def test_rust_candidate_route_selection_matches_baseline_when_extension_is_available() -> None:
    from metroflow.backends.rust_cpu import rust_routing_backend_available
    from metroflow.routing.candidates import RouteCandidateSet
    from metroflow.sim import routing_runtime

    if not rust_routing_backend_available():
        pytest.skip("_metroflow_rust extension with route selection is not importable")

    candidate_set = RouteCandidateSet(
        od_key=(1, 2),
        candidate_ids=(7, 8, 9),
        candidate_paths=((10,), (10, 11), (20,)),
        last_refresh_tick=0,
        metadata={
            "candidate_path_costs": (2.0, 3.0, 3.0),
            "candidate_path_size_factors": (0.2, 1.0, 1.0),
        },
    )

    baseline = routing_runtime._select_candidate_route(
        candidate_set,
        path_size_gamma=2.0,
        routing_backend="baseline",
    )
    accelerated = routing_runtime._select_candidate_route(
        candidate_set,
        path_size_gamma=2.0,
        routing_backend="rust_cpu",
    )

    assert accelerated is not None
    assert baseline is not None
    assert accelerated.candidate_index == baseline.candidate_index
    assert accelerated.candidate_id == baseline.candidate_id
    assert accelerated.path == baseline.path
    assert accelerated.path_cost == pytest.approx(baseline.path_cost)
    assert accelerated.path_size_factor == pytest.approx(baseline.path_size_factor)
    assert accelerated.utility == pytest.approx(baseline.utility)
    assert accelerated.selection_backend == "rust_cpu_candidate_selection"
    assert baseline.selection_backend == "python_host_candidate_selection"


def test_runtime_route_refresh_propagates_configured_routing_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    from metroflow.demand.trips import TripRequestStatus
    from metroflow.routing.candidates import RouteCandidateSet
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim import routing_runtime

    state = _runtime_spine_state()
    state.config = SimulationConfig(active_agent_capacity=4, routing_backend="rust_cpu")
    activated_trips = tuple(
        replace(trip, status=TripRequestStatus.ACTIVATED)
        for trip in state.dynamic.demand_state["trip_requests"]
    )
    state = state.with_dynamic_updates(
        demand_state={
            **state.dynamic.demand_state,
            "trip_requests": activated_trips,
            "activated_trip_requests": 1,
        }
    )
    calls = []

    def fake_refresh(existing, **kwargs):
        calls.append(kwargs["routing_backend"])
        return RouteCandidateSet(
            od_key=kwargs["od_key"],
            candidate_ids=(0,),
            candidate_paths=((10, 11),),
            last_refresh_tick=kwargs["current_tick"],
        )

    monkeypatch.setattr(routing_runtime, "refresh_od_route_candidate_set", fake_refresh)

    route_state, counters = routing_runtime.refresh_runtime_route_candidates(
        state,
        force_refresh=True,
    )

    assert calls == ["rust_cpu"]
    assert route_state.candidate_sets[(1, 2)].candidate_paths == ((10, 11),)
    assert counters["route_candidate_refresh_this_tick"] == 0


def test_runtime_route_cache_fingerprint_includes_candidate_backend_metadata() -> None:
    from metroflow.routing.candidates import RouteCandidateSet
    from metroflow.sim.routing_runtime import runtime_route_cache_fingerprint

    baseline_set = RouteCandidateSet(
        od_key=(1, 2),
        candidate_ids=(0,),
        candidate_paths=((10, 11),),
        last_refresh_tick=0,
        metadata={
            "routing_backend": "baseline",
            "routing_backend_requested": "auto",
            "routing_backend_fallback": "rust_cpu_unavailable",
        },
    )
    rust_set = RouteCandidateSet(
        od_key=(1, 2),
        candidate_ids=(0,),
        candidate_paths=((10, 11),),
        last_refresh_tick=0,
        metadata={
            "routing_backend": "rust_cpu",
            "routing_backend_requested": "auto",
        },
    )

    assert runtime_route_cache_fingerprint(candidate_sets={(1, 2): baseline_set}) != (
        runtime_route_cache_fingerprint(candidate_sets={(1, 2): rust_set})
    )


def test_runtime_replay_boundary_fingerprints_path_size_policy() -> None:
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.replay import make_runtime_replay_boundary

    baseline_state = _runtime_spine_state()
    corrected_state = _runtime_spine_state()
    corrected_state.config = SimulationConfig(
        active_agent_capacity=4,
        route_path_size_gamma=2.0,
    )

    assert make_runtime_replay_boundary(baseline_state).config_fingerprint != (
        make_runtime_replay_boundary(corrected_state).config_fingerprint
    )


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


def test_runtime_replay_records_reroute_counter_totals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.sim import replay as replay_module
    from metroflow.sim.control import SimulationControl, SimulationTelemetry
    from metroflow.sim.replay import (
        RuntimeReplayRequest,
        make_runtime_replay_boundary,
        replay_simulation_sequence,
    )
    from metroflow.sim.rng import key_from_seed

    state = _runtime_spine_state()

    def fake_simulation_step(state, _control, key):
        metrics = dict(state.dynamic.metrics_state)
        metrics["us2_reroute_decisions_total"] = 3
        metrics["us2_persistence_decisions_total"] = 2
        next_state = state.with_clock(tick_index=state.tick_index + 1).with_dynamic_updates(
            metrics_state=metrics
        )
        return (
            next_state,
            SimulationTelemetry(
                tick_index=next_state.tick_index,
                active_agent_count=0,
                active_agent_rerouted_this_tick=3,
                active_agent_reroute_cooldown_this_tick=2,
            ),
            None,
            key,
        )

    monkeypatch.setattr(replay_module, "simulation_step", fake_simulation_step)

    result = replay_simulation_sequence(
        RuntimeReplayRequest(
            name="replay_runtime_reroute_counters",
            initial_state=state,
            declared_boundary=make_runtime_replay_boundary(state),
            controls=(SimulationControl(),),
            rng_key=key_from_seed(29),
            num_steps=1,
        )
    )

    assert result.reroute_decisions_total == 3
    assert result.persistence_decisions_total == 2
    assert result.telemetry_log[0].active_agent_rerouted_this_tick == 3
    assert result.telemetry_log[0].active_agent_reroute_cooldown_this_tick == 2


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
