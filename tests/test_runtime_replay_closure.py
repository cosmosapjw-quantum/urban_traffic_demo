from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest


def _compact_runtime_state():
    from metroflow.flow.state import LinkState, NodeState
    from metroflow.sim.active_agents import (
        ActiveAgentPool,
        ActiveAgentSlot,
        allocate_active_agent_slot,
        create_active_agent_pool,
    )
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.routing_runtime import create_simulation_route_cache_state
    from metroflow.sim.state import SimulationDynamicRefs, SimulationState

    pool, slot_id = allocate_active_agent_slot(
        create_active_agent_pool(2),
        ActiveAgentSlot.spawn(
            citizen_id=7,
            trip_id=11,
            current_link_id=10,
            dest_node_id=3,
            behavior_profile_id=0,
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
        plugin_memory={slot_id: {"route_path": (10, 11)}},
    )
    link_state = LinkState(
        queue_vehicles=(1.0, 0.0),
        inflow_vehicles=(0.0, 0.0),
        outflow_vehicles=(0.0, 0.0),
        travel_time_cost=(1.0, 1.0),
        capacity_veh_per_tick=(0.5, 1.0),
        incident_capacity_multiplier=(1.0, 1.0),
        metadata={
            "free_flow_travel_time_cost": np.ones((2,), dtype=np.float32),
            "runtime_link_service_residual": np.asarray((0.5, 0.0), dtype=np.float32),
            "runtime_link_service_tokens": np.asarray((0.0, 0.0), dtype=np.float32),
            "runtime_link_receiving_residual": np.asarray(
                (0.0, 0.5), dtype=np.float32
            ),
            "runtime_link_receiving_tokens": np.asarray(
                (0.0, 0.0), dtype=np.float32
            ),
        },
    )
    node_state = NodeState(
        turn_from_link_index=(0,),
        turn_to_link_index=(1,),
        turn_demand=(1.0,),
        turn_supply=(0.5,),
        turn_flow=(0.0,),
        signal_phase_index=(0, 0),
        signal_phase_timer=(0, 0),
        metadata={
            "runtime_turn_flow_residual": np.asarray((0.5,), dtype=np.float32),
            "runtime_sink_flow_residual": np.asarray(
                (0.25, 0.0), dtype=np.float32
            ),
            "runtime_sink_flow_by_link_index": np.zeros((2,), dtype=np.float32),
        },
    )
    demand_state = {
        "allocated_trip_request_ids": (11,),
        "completed_trip_request_ids": (),
        "failed_trip_request_ids": (),
        "pending_trip_requests": 0,
    }
    return SimulationState(
        config=SimulationConfig(population_target=100, active_agent_capacity=2),
        dynamic=SimulationDynamicRefs(
            demand_state=demand_state,
            active_agent_pool=pool,
            flow_link_state=link_state,
            flow_node_state=node_state,
            route_candidate_state=create_simulation_route_cache_state(),
            metrics_state={
                "completed_trips_total": 0,
                "flow_update_wall_ns": 0,
                "route_candidate_refresh_seconds_total": 0.0,
            },
        ),
    )


def test_runtime_state_fingerprint_covers_discrete_closure_authority() -> None:
    from metroflow.sim.active_agents import ActiveAgentPool
    from metroflow.sim.replay import runtime_state_fingerprint

    state = _compact_runtime_state()
    baseline = runtime_state_fingerprint(state)

    link_state = state.dynamic.flow_link_state
    link_metadata = dict(link_state.metadata)
    link_metadata["runtime_link_service_residual"] = np.asarray(
        (0.25, 0.0), dtype=np.float32
    )
    changed_link = state.with_dynamic_updates(
        flow_link_state=replace(link_state, metadata=link_metadata)
    )
    receiving_metadata = dict(link_state.metadata)
    receiving_metadata["runtime_link_receiving_residual"] = np.asarray(
        (0.0, 0.25), dtype=np.float32
    )
    changed_receiving = state.with_dynamic_updates(
        flow_link_state=replace(link_state, metadata=receiving_metadata)
    )
    receiving_token_metadata = dict(link_state.metadata)
    receiving_token_metadata["runtime_link_receiving_tokens"] = np.asarray(
        (0.0, 1.0), dtype=np.float32
    )
    changed_receiving_tokens = state.with_dynamic_updates(
        flow_link_state=replace(link_state, metadata=receiving_token_metadata)
    )

    node_state = state.dynamic.flow_node_state
    turn_metadata = dict(node_state.metadata)
    turn_metadata["runtime_turn_flow_residual"] = np.asarray((0.25,), dtype=np.float32)
    changed_turn = state.with_dynamic_updates(
        flow_node_state=replace(node_state, metadata=turn_metadata)
    )
    sink_metadata = dict(node_state.metadata)
    sink_metadata["runtime_sink_flow_by_link_index"] = np.asarray(
        (0.0, 1.0), dtype=np.float32
    )
    changed_sink = state.with_dynamic_updates(
        flow_node_state=replace(node_state, metadata=sink_metadata)
    )
    sink_residual_metadata = dict(node_state.metadata)
    sink_residual_metadata["runtime_sink_flow_residual"] = np.asarray(
        (0.5, 0.0), dtype=np.float32
    )
    changed_sink_residual = state.with_dynamic_updates(
        flow_node_state=replace(node_state, metadata=sink_residual_metadata)
    )

    demand_state = dict(state.dynamic.demand_state)
    demand_state["completed_trip_request_ids"] = (11,)
    changed_lifecycle = state.with_dynamic_updates(demand_state=demand_state)

    pool = state.dynamic.active_agent_pool
    current_link = np.asarray(pool.current_link_id, dtype=np.int32).copy()
    current_link[0] = 11
    changed_pool = ActiveAgentPool.from_internal_arrays(
        capacity=pool.capacity,
        free_slot_stack=pool.free_slot_stack,
        free_slot_count=pool.free_slot_count,
        alive_mask=pool.alive_mask,
        alive_count=pool.alive_count,
        citizen_id=pool.citizen_id,
        trip_id=pool.trip_id,
        current_link_id=current_link,
        progress_01=pool.progress_01,
        remaining_route_ptr=pool.remaining_route_ptr,
        dest_node_id=pool.dest_node_id,
        behavior_profile_id=pool.behavior_profile_id,
        reroute_cooldown_ticks=pool.reroute_cooldown_ticks,
        plugin_memory=pool.plugin_memory,
    )
    changed_agent = state.with_dynamic_updates(active_agent_pool=changed_pool)

    observed = {
        runtime_state_fingerprint(candidate)
        for candidate in (
            state,
            changed_link,
            changed_receiving,
            changed_receiving_tokens,
            changed_turn,
            changed_sink,
            changed_sink_residual,
            changed_lifecycle,
            changed_agent,
        )
    }
    assert len(observed) == 9
    assert baseline in observed


def test_runtime_state_fingerprint_excludes_only_host_timing_diagnostics() -> None:
    from metroflow.sim.replay import runtime_state_fingerprint

    state = _compact_runtime_state()
    changed_metrics = dict(state.dynamic.metrics_state)
    changed_metrics.update(
        {
            "flow_update_wall_ns": 999_999,
            "route_candidate_refresh_seconds_total": 12.5,
        }
    )
    timing_only = state.with_dynamic_updates(metrics_state=changed_metrics)
    assert runtime_state_fingerprint(timing_only) == runtime_state_fingerprint(state)

    changed_metrics["completed_trips_total"] = 1
    authoritative_change = state.with_dynamic_updates(metrics_state=changed_metrics)
    assert runtime_state_fingerprint(authoritative_change) != runtime_state_fingerprint(
        state
    )


def test_runtime_replay_rejects_stale_discrete_residual_boundary() -> None:
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.replay import (
        RuntimeReplayRequest,
        make_runtime_replay_boundary,
        replay_simulation_sequence,
    )
    from metroflow.sim.rng import key_from_seed

    state = _compact_runtime_state()
    stale_boundary = make_runtime_replay_boundary(state)
    link_state = state.dynamic.flow_link_state
    metadata = dict(link_state.metadata)
    metadata["runtime_link_service_residual"] = np.asarray(
        (0.25, 0.0), dtype=np.float32
    )
    changed = state.with_dynamic_updates(
        flow_link_state=replace(link_state, metadata=metadata)
    )

    with pytest.raises(ValueError, match="declared runtime replay boundary"):
        replay_simulation_sequence(
            RuntimeReplayRequest(
                name="replay_stale_discrete_residual",
                initial_state=changed,
                declared_boundary=stale_boundary,
                controls=(SimulationControl.noop(),),
                rng_key=key_from_seed(7),
                num_steps=1,
            )
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("ui_stream_enabled", True),
        ("ui_stream_hz_limit", 2.0),
        ("max_trip_spawns_per_tick", 7),
        ("learning_enabled", True),
    ),
)
def test_runtime_replay_boundary_fingerprints_complete_config(
    field_name: str,
    value: object,
) -> None:
    from metroflow.sim.replay import make_runtime_replay_boundary

    state = _compact_runtime_state()
    changed = replace(state, config=replace(state.config, **{field_name: value}))
    assert make_runtime_replay_boundary(changed).config_fingerprint != (
        make_runtime_replay_boundary(state).config_fingerprint
    )


def test_runtime_replay_boundary_fingerprints_compiled_turn_authority() -> None:
    from metroflow.city.graph import (
        Node,
        RoadClass,
        RoadLink,
        TurnMovement,
        TurnType,
        build_road_network_csr,
    )
    from metroflow.sim.replay import make_runtime_replay_boundary
    from metroflow.sim.state import SimulationStaticRefs

    nodes = (Node(1), Node(2), Node(3))
    links = (
        RoadLink(10, 1, 2, RoadClass.ARTERIAL, 100.0, 10.0, 1.0),
        RoadLink(11, 2, 3, RoadClass.ARTERIAL, 100.0, 10.0, 1.0),
    )
    permitted = build_road_network_csr(
        nodes,
        links,
        (TurnMovement(10, 11, TurnType.THROUGH),),
    )
    forbidden = build_road_network_csr(
        nodes,
        links,
        (TurnMovement(10, 11, TurnType.U_TURN_FORBIDDEN),),
    )
    state = _compact_runtime_state()
    permitted_state = replace(
        state,
        static=SimulationStaticRefs(routing_static={"road_csr": permitted}),
    )
    forbidden_state = replace(
        state,
        static=SimulationStaticRefs(routing_static={"road_csr": forbidden}),
    )

    assert make_runtime_replay_boundary(permitted_state).static_input_fingerprint != (
        make_runtime_replay_boundary(forbidden_state).static_input_fingerprint
    )


def test_runtime_replay_boundary_binds_controls_rng_and_step_count() -> None:
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.replay import (
        RuntimeReplayRequest,
        make_runtime_replay_boundary,
        replay_simulation_sequence,
    )
    from metroflow.sim.rng import key_from_seed

    state = _compact_runtime_state()
    controls = (SimulationControl.noop(),)
    replay_key = key_from_seed(7)
    boundary = make_runtime_replay_boundary(
        state,
        controls=controls,
        rng_key=replay_key,
        num_steps=1,
    )

    assert boundary.num_steps == 1
    assert boundary.rng_key_fingerprint
    assert boundary.control_sequence_fingerprint
    with pytest.raises(ValueError, match="declared runtime replay boundary"):
        replay_simulation_sequence(
            RuntimeReplayRequest(
                name="replay_control_mismatch",
                initial_state=state,
                declared_boundary=boundary,
                controls=(SimulationControl(pause=True),),
                rng_key=replay_key,
                num_steps=1,
            )
        )
    with pytest.raises(ValueError, match="declared runtime replay boundary"):
        replay_simulation_sequence(
            RuntimeReplayRequest(
                name="replay_rng_mismatch",
                initial_state=state,
                declared_boundary=boundary,
                controls=controls,
                rng_key=key_from_seed(8),
                num_steps=1,
            )
        )


def test_runtime_state_fingerprint_distinguishes_structured_dtypes() -> None:
    from metroflow.sim.replay import runtime_state_fingerprint

    state = _compact_runtime_state()
    first_dtype = np.dtype([("a", np.int32), ("b", np.int32)])
    second_dtype = np.dtype([("x", np.int64)])
    first = replace(
        state,
        metadata={"structured": np.zeros((1,), dtype=first_dtype)},
    )
    second = replace(
        state,
        metadata={"structured": np.zeros((1,), dtype=second_dtype)},
    )

    assert first_dtype.str == second_dtype.str == "|V8"
    assert runtime_state_fingerprint(first) != runtime_state_fingerprint(second)


def test_runtime_replay_result_isolated_from_mutable_input_aliases() -> None:
    from metroflow.sim.replay import (
        RuntimeReplayRequest,
        make_runtime_replay_boundary,
        replay_simulation_sequence,
        runtime_state_fingerprint,
    )
    from metroflow.sim.rng import key_from_seed

    state = _compact_runtime_state()
    controls = ()
    replay_key = key_from_seed(9)
    boundary = make_runtime_replay_boundary(
        state,
        controls=controls,
        rng_key=replay_key,
        num_steps=0,
    )
    result = replay_simulation_sequence(
        RuntimeReplayRequest(
            name="replay_sealed_result",
            initial_state=state,
            declared_boundary=boundary,
            controls=controls,
            rng_key=replay_key,
            num_steps=0,
        )
    )
    sealed_capacity = result.final_state.dynamic.flow_link_state.capacity_veh_per_tick
    original_value = float(sealed_capacity[0])

    state.dynamic.flow_link_state.capacity_veh_per_tick[0] += np.float32(5.0)

    assert float(sealed_capacity[0]) == original_value
    assert result.final_state_fingerprint == runtime_state_fingerprint(result.final_state)
    with pytest.raises(ValueError, match="read-only"):
        sealed_capacity[0] = np.float32(99.0)


def test_seed41_generated_closure_replay_has_exact_state_digest() -> None:
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.init import build_initial_simulation_state
    from metroflow.sim.replay import (
        RuntimeReplayRequest,
        make_runtime_replay_boundary,
        replay_simulation_sequence,
        runtime_state_fingerprint,
    )

    def run_once():
        bundle = build_initial_simulation_state(
            config=SimulationConfig(
                population_target=100,
                active_agent_capacity=100,
                max_trip_spawns_per_tick=100,
                eager_trip_generation=True,
            ),
            scenario_seed=41,
            eager_trip_generation=True,
        )
        controls = tuple(SimulationControl.noop() for _ in range(20))
        boundary = make_runtime_replay_boundary(
            bundle.state,
            controls=controls,
            rng_key=bundle.rng_key,
            num_steps=len(controls),
        )
        result = replay_simulation_sequence(
            RuntimeReplayRequest(
                name="replay_seed41_runtime_closure",
                initial_state=bundle.state,
                declared_boundary=boundary,
                controls=controls,
                rng_key=bundle.rng_key,
                num_steps=len(controls),
            )
        )
        return bundle, result

    first_bundle, first = run_once()
    second_bundle, second = run_once()

    assert first.initial_boundary == second.initial_boundary
    assert first.final_state_fingerprint == second.final_state_fingerprint
    assert first.final_state_fingerprint == runtime_state_fingerprint(first.final_state)
    assert tuple(item.as_replay_dict() for item in first.telemetry_log) == tuple(
        item.as_replay_dict() for item in second.telemetry_log
    )
    assert np.array_equal(first.final_rng_key, second.final_rng_key)

    final = first.final_state
    demand = final.dynamic.demand_state
    trip_count = len(first_bundle.trip_requests.trip_requests)
    terminal_ids = set(demand["completed_trip_request_ids"]) | set(
        demand["failed_trip_request_ids"]
    )
    assert len(terminal_ids) == trip_count
    assert final.dynamic.active_agent_pool.alive_count == 0
    assert float(final.dynamic.flow_link_state.queue_vehicles.sum()) == 0.0
    assert "runtime_link_service_residual" in final.dynamic.flow_link_state.metadata
    assert "runtime_link_receiving_residual" in final.dynamic.flow_link_state.metadata
    assert "runtime_link_receiving_tokens" in final.dynamic.flow_link_state.metadata
    assert "runtime_turn_flow_residual" in final.dynamic.flow_node_state.metadata
    assert "runtime_sink_flow_residual" in final.dynamic.flow_node_state.metadata
    assert "runtime_sink_flow_by_link_index" in final.dynamic.flow_node_state.metadata
    assert second_bundle.trip_requests.metadata == first_bundle.trip_requests.metadata
