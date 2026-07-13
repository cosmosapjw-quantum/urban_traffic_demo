from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest


def _spatial_runtime_state(*, first_link_queue: float = 0.0, first_link_storage: float = 13.0):
    from tests.test_runtime_spine import _runtime_spine_state

    from metroflow.flow.state import LinkState
    from metroflow.sim.config import SimulationConfig
    from metroflow.traffic.spatial_queue import compute_link_storage_capacity

    state = _runtime_spine_state(
        queue_vehicles=(first_link_queue, 0.0),
        capacity_veh_per_tick=(2.0, 2.0),
    )
    road_csr = state.static.routing_static["road_csr"]
    storage = compute_link_storage_capacity(road_csr, jam_spacing_m=7.5).copy()
    storage[0] = np.float32(first_link_storage)
    storage.flags.writeable = False
    link_state = state.dynamic.flow_link_state
    next_link_state = LinkState.from_internal_arrays(
        queue_vehicles=link_state.queue_vehicles,
        inflow_vehicles=link_state.inflow_vehicles,
        outflow_vehicles=link_state.outflow_vehicles,
        travel_time_cost=link_state.travel_time_cost,
        capacity_veh_per_tick=link_state.capacity_veh_per_tick,
        incident_capacity_multiplier=link_state.incident_capacity_multiplier,
        capacity_violation_flags=link_state.capacity_violation_flags,
        metadata={
            **link_state.metadata,
            "traffic_model": "spatial_queue_v1",
            "storage_capacity_vehicles": storage,
            "storage_capacity_unit": "vehicles",
            "jam_spacing_m": 7.5,
        },
    )
    return replace(
        state.with_dynamic_updates(flow_link_state=next_link_state),
        config=SimulationConfig(
            active_agent_capacity=4,
            traffic_model="spatial_queue_v1",
        ),
    )


def test_spatial_queue_config_is_explicit_and_numpy_only() -> None:
    from metroflow.sim.config import SimulationConfig

    assert SimulationConfig().traffic_model == "point_queue_v1"
    assert SimulationConfig().jam_spacing_m == 7.5
    spatial = SimulationConfig(traffic_model="spatial_queue_v1")
    assert spatial.flow_backend == "baseline"
    with pytest.raises(ValueError, match="traffic_model"):
        SimulationConfig(traffic_model="teleport_v1")
    with pytest.raises(ValueError, match="flow_backend=baseline"):
        SimulationConfig(
            traffic_model="spatial_queue_v1",
            flow_backend="rust_cpu",
        )


def test_link_storage_uses_explicit_length_lanes_and_jam_spacing() -> None:
    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr
    from metroflow.traffic.spatial_queue import compute_link_storage_capacity

    road_csr = build_road_network_csr(
        nodes=(Node(0), Node(1), Node(2)),
        links=(
            RoadLink(0, 0, 1, RoadClass.LOCAL, 75.0, 10.0, 1.0, lanes=1),
            RoadLink(1, 1, 2, RoadClass.ARTERIAL, 150.0, 15.0, 2.0, lanes=2),
        ),
    )

    storage = compute_link_storage_capacity(road_csr, jam_spacing_m=7.5)

    assert storage.dtype == np.float32
    assert storage.tolist() == [10.0, 40.0]
    assert not storage.flags.writeable


def test_spatial_runtime_initialization_derives_storage_from_compiled_links() -> None:
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.init import build_initial_simulation_state
    from metroflow.traffic.spatial_queue import compute_link_storage_capacity

    bundle = build_initial_simulation_state(
        config=SimulationConfig(
            population_target=100,
            active_agent_capacity=16,
            traffic_model="spatial_queue_v1",
            jam_spacing_m=8.0,
        ),
        scenario_seed=17,
        eager_trip_generation=False,
    )
    road_csr = bundle.state.static.routing_static["road_csr"]
    link_state = bundle.state.dynamic.flow_link_state

    assert link_state.metadata["traffic_model"] == "spatial_queue_v1"
    assert link_state.metadata["storage_capacity_unit"] == "vehicles"
    assert link_state.metadata["jam_spacing_m"] == 8.0
    assert np.array_equal(
        link_state.metadata["storage_capacity_vehicles"],
        compute_link_storage_capacity(road_csr, jam_spacing_m=8.0),
    )


def test_spatial_receiving_storage_blocks_and_then_allows_one_turn() -> None:
    from metroflow.flow.engine import update_link_node_flow
    from metroflow.flow.state import LinkState, NodeState

    link_state = LinkState(
        queue_vehicles=np.asarray([1.0, 2.0], dtype=np.float32),
        inflow_vehicles=np.zeros(2, dtype=np.float32),
        outflow_vehicles=np.zeros(2, dtype=np.float32),
        travel_time_cost=np.ones(2, dtype=np.float32),
        capacity_veh_per_tick=np.ones(2, dtype=np.float32),
        incident_capacity_multiplier=np.ones(2, dtype=np.float32),
    )
    node_state = NodeState(
        turn_from_link_index=np.asarray([0], dtype=np.int32),
        turn_to_link_index=np.asarray([1], dtype=np.int32),
        turn_demand=np.asarray([1.0], dtype=np.float32),
        turn_supply=np.zeros(1, dtype=np.float32),
        turn_flow=np.zeros(1, dtype=np.float32),
        signal_phase_index=np.zeros(3, dtype=np.int32),
        signal_phase_timer=np.zeros(3, dtype=np.int32),
        metadata={
            "runtime_sink_demand_by_link_index": np.zeros(2, dtype=np.float32),
        },
    )

    blocked = update_link_node_flow(
        link_state,
        node_state,
        discrete_agent_authority=True,
        storage_capacity_vehicles=np.asarray([2.0, 2.0], dtype=np.float32),
    )
    admitted = update_link_node_flow(
        replace(link_state, queue_vehicles=np.asarray([1.0, 1.0], dtype=np.float32)),
        node_state,
        discrete_agent_authority=True,
        storage_capacity_vehicles=np.asarray([2.0, 2.0], dtype=np.float32),
    )

    assert blocked.node_state.turn_flow.tolist() == [0.0]
    assert blocked.link_state.queue_vehicles.tolist() == [1.0, 2.0]
    assert blocked.link_state.metadata["runtime_spillback_blocked_turn_count"] == 1
    assert admitted.node_state.turn_flow.tolist() == [1.0]
    assert admitted.link_state.queue_vehicles.tolist() == [0.0, 2.0]


def test_spatial_receiving_storage_serializes_competing_turns() -> None:
    from metroflow.flow.engine import update_link_node_flow
    from metroflow.flow.state import LinkState, NodeState

    link_state = LinkState(
        queue_vehicles=np.asarray([1.0, 1.0, 1.0], dtype=np.float32),
        inflow_vehicles=np.zeros(3, dtype=np.float32),
        outflow_vehicles=np.zeros(3, dtype=np.float32),
        travel_time_cost=np.ones(3, dtype=np.float32),
        capacity_veh_per_tick=np.ones(3, dtype=np.float32),
        incident_capacity_multiplier=np.ones(3, dtype=np.float32),
    )
    node_state = NodeState(
        turn_from_link_index=np.asarray([0, 1], dtype=np.int32),
        turn_to_link_index=np.asarray([2, 2], dtype=np.int32),
        turn_demand=np.ones(2, dtype=np.float32),
        turn_supply=np.zeros(2, dtype=np.float32),
        turn_flow=np.zeros(2, dtype=np.float32),
        signal_phase_index=np.zeros(4, dtype=np.int32),
        signal_phase_timer=np.zeros(4, dtype=np.int32),
        metadata={
            "runtime_sink_demand_by_link_index": np.zeros(3, dtype=np.float32),
        },
    )

    result = update_link_node_flow(
        link_state,
        node_state,
        discrete_agent_authority=True,
        storage_capacity_vehicles=np.asarray([1.0, 1.0, 2.0], dtype=np.float32),
    )

    assert result.node_state.turn_flow.tolist() == [1.0, 0.0]
    assert result.link_state.queue_vehicles.tolist() == [0.0, 1.0, 2.0]
    assert float(np.sum(result.link_state.inflow_vehicles)) == 1.0


def test_spatial_progress_requires_physical_link_travel_time() -> None:
    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr
    from metroflow.sim.active_agents import ActiveAgentSlot, allocate_active_agent_slot, create_active_agent_pool
    from metroflow.traffic.spatial_queue import advance_agent_link_progress

    road_csr = build_road_network_csr(
        nodes=(Node(0), Node(1)),
        links=(RoadLink(0, 0, 1, RoadClass.LOCAL, 100.0, 10.0, 1.0),),
    )
    pool, slot_id = allocate_active_agent_slot(
        create_active_agent_pool(2),
        ActiveAgentSlot.spawn(
            citizen_id=1,
            trip_id=2,
            current_link_id=0,
            dest_node_id=1,
            behavior_profile_id=0,
        ),
    )

    for _ in range(9):
        pool, counters = advance_agent_link_progress(
            pool,
            road_csr=road_csr,
            tick_seconds=1.0,
        )
    assert float(pool.progress_01[slot_id]) == pytest.approx(0.9)
    assert counters["active_agent_exit_queue_count"] == 0
    pool, counters = advance_agent_link_progress(
        pool,
        road_csr=road_csr,
        tick_seconds=1.0,
    )
    assert float(pool.progress_01[slot_id]) == pytest.approx(1.0)
    assert counters["active_agent_exit_queue_count"] == 1
    pool, counters = advance_agent_link_progress(
        pool,
        road_csr=road_csr,
        tick_seconds=1.0,
    )
    assert counters["active_agent_progressed_this_tick"] == 0
    assert counters["active_agent_exit_queue_count"] == 1


def test_runtime_spatial_agent_cannot_teleport_across_links() -> None:
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.step import simulation_step

    state = _spatial_runtime_state()
    key = key_from_seed(5)
    state, first_telemetry, _snapshot, key = simulation_step(
        state,
        SimulationControl(),
        key,
    )
    assert state.dynamic.active_agent_pool.alive_count == 1
    assert state.dynamic.active_agent_pool.current_link_id[0].item() == 10
    assert state.dynamic.active_agent_pool.progress_01[0].item() == 0.0
    assert first_telemetry.active_agent_moved_this_tick == 0

    for _ in range(9):
        state, telemetry, _snapshot, key = simulation_step(
            state,
            SimulationControl(),
            key,
        )
    assert state.dynamic.active_agent_pool.current_link_id[0].item() == 10
    assert state.dynamic.active_agent_pool.progress_01[0].item() == pytest.approx(0.9)
    assert telemetry.active_agent_moved_this_tick == 0

    state, telemetry, _snapshot, key = simulation_step(
        state,
        SimulationControl(),
        key,
    )
    assert state.dynamic.active_agent_pool.current_link_id[0].item() == 11
    assert state.dynamic.active_agent_pool.progress_01[0].item() == 0.0
    assert telemetry.active_agent_moved_this_tick == 1
    assert state.dynamic.flow_link_state.queue_vehicles.tolist() == [0.0, 1.0]

    for _ in range(9):
        state, telemetry, _snapshot, key = simulation_step(
            state,
            SimulationControl(),
            key,
        )
    assert state.dynamic.active_agent_pool.alive_count == 1
    state, telemetry, _snapshot, key = simulation_step(
        state,
        SimulationControl(),
        key,
    )
    assert state.dynamic.active_agent_pool.alive_count == 0
    assert telemetry.trip_completed_this_tick == 1
    assert state.dynamic.flow_link_state.queue_vehicles.tolist() == [0.0, 0.0]


def test_runtime_spatial_source_admission_waits_when_first_link_is_full() -> None:
    from metroflow.demand.trips import TripRequest, TripRequestStatus
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.step import simulation_step

    state = _spatial_runtime_state(first_link_storage=1.0)
    state, first_telemetry, _snapshot, key = simulation_step(
        state,
        SimulationControl(),
        key_from_seed(7),
    )
    assert state.dynamic.active_agent_pool.alive_count == 1
    assert state.dynamic.flow_link_state.queue_vehicles.tolist() == [1.0, 0.0]
    assert state.dynamic.invariant_state.ok
    base_trip = state.dynamic.demand_state["trip_requests"][0]
    second_trip = TripRequest(
        trip_request_id=2,
        citizen_id=202,
        origin_poi_id=base_trip.origin_poi_id,
        dest_poi_id=base_trip.dest_poi_id,
        planned_depart_tick=state.tick_index,
        day_type=base_trip.day_type,
        time_band=base_trip.time_band,
        status=TripRequestStatus.QUEUED,
    )
    state = state.with_dynamic_updates(
        demand_state={
            **state.dynamic.demand_state,
            "trip_requests": (base_trip, second_trip),
            "queued_trip_requests": 1,
            "pending_trip_requests": 1,
            "activated_trip_requests": 0,
        },
        metrics_state={
            **state.dynamic.metrics_state,
            "generated_trip_total": 2,
            "pending_trip_requests": 1,
        },
    )
    next_state, telemetry, _snapshot, _key = simulation_step(
        state,
        SimulationControl(),
        key,
    )

    assert next_state.dynamic.active_agent_pool.alive_count == 1
    assert next_state.dynamic.flow_link_state.queue_vehicles.tolist() == [1.0, 0.0]
    assert telemetry.trip_source_spillback_wait_this_tick == 1
    assert next_state.dynamic.demand_state["pending_trip_requests"] == 1
    assert next_state.dynamic.invariant_state.ok


def test_spatial_storage_excess_is_an_invariant_violation() -> None:
    from metroflow.sim.invariants import validate_invariants

    state = _spatial_runtime_state(first_link_queue=2.0, first_link_storage=1.0)

    report = validate_invariants(state)

    assert not report.ok
    assert "finite_link_storage" in report.checks_run
    assert any(
        violation.code == "finite_link_storage_exceeded"
        for violation in report.violations
    )


def test_runtime_spatial_pause_preserves_progress_and_replay_is_deterministic() -> None:
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.replay import (
        RuntimeReplayRequest,
        make_runtime_replay_boundary,
        replay_simulation_sequence,
    )
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.step import simulation_step

    state = _spatial_runtime_state()
    state, _telemetry, _snapshot, key = simulation_step(
        state,
        SimulationControl(),
        key_from_seed(11),
    )
    paused, _telemetry, _snapshot, _key = simulation_step(
        state,
        SimulationControl(pause=True),
        key,
    )
    assert np.array_equal(
        paused.dynamic.active_agent_pool.progress_01,
        state.dynamic.active_agent_pool.progress_01,
    )

    controls = tuple(SimulationControl() for _ in range(12))
    replay_key = key_from_seed(13)
    boundary = make_runtime_replay_boundary(
        _spatial_runtime_state(),
        controls=controls,
        rng_key=replay_key,
        num_steps=len(controls),
    )
    request = RuntimeReplayRequest(
        name="replay_spatial_queue",
        initial_state=_spatial_runtime_state(),
        declared_boundary=boundary,
        controls=controls,
        rng_key=replay_key,
        num_steps=len(controls),
    )
    first = replay_simulation_sequence(request)
    second = replay_simulation_sequence(request)

    assert first.initial_boundary.traffic_model == "spatial_queue_v1"
    assert first.traffic_model == "spatial_queue_v1"
    assert first.telemetry_log[0].as_dict()["traffic_model"] == "spatial_queue_v1"
    assert "active_agent_progressed_this_tick" in first.telemetry_log[0].as_replay_dict()
    assert tuple(item.as_replay_dict() for item in first.telemetry_log) == tuple(
        item.as_replay_dict() for item in second.telemetry_log
    )
    assert first.final_state_fingerprint == second.final_state_fingerprint


def test_replay_config_fingerprint_changes_with_traffic_model() -> None:
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.replay import make_runtime_replay_boundary

    spatial = _spatial_runtime_state()
    point = replace(
        spatial,
        config=SimulationConfig(active_agent_capacity=4),
    )

    assert make_runtime_replay_boundary(spatial).config_fingerprint != (
        make_runtime_replay_boundary(point).config_fingerprint
    )


def test_measured_runtime_benchmark_preserves_spatial_model_metadata() -> None:
    from metroflow.metrics.benchmarks import (
        MeasuredRuntimeBenchmarkConfig,
        run_measured_runtime_spine_benchmark,
    )
    from metroflow.sim.rng import key_from_seed

    result = run_measured_runtime_spine_benchmark(
        _spatial_runtime_state(),
        key_from_seed(19),
        MeasuredRuntimeBenchmarkConfig(
            workload_name="spatial-queue-runtime",
            num_steps=1,
        ),
    )

    assert result.traffic_model == "spatial_queue_v1"
