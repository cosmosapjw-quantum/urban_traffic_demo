from importlib import import_module

import numpy as np
import pytest


def test_city_graph_csr_builds_explicit_road_topology():
    graph = import_module("metroflow.city.graph")

    csr = graph.build_road_network_csr(
        nodes=(graph.Node(1), graph.Node(2), graph.Node(3)),
        links=(
            graph.RoadLink(10, 1, 2, graph.RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            graph.RoadLink(11, 2, 3, graph.RoadClass.BRIDGE, 80.0, 8.0, 3.0, bridge_group_id=1),
        ),
        turns=(graph.TurnMovement(10, 11, graph.TurnType.THROUGH),),
    )

    assert csr.node_count == 3
    assert csr.link_count == 2
    assert csr.turn_count == 1
    assert csr.link_id_to_index[11] == 1
    assert isinstance(csr.node_ids, np.ndarray)
    assert isinstance(csr.link_src_node_index, np.ndarray)


def test_flow_engine_updates_link_and_node_state_with_capacity_bounds():
    flow_state = import_module("metroflow.flow.state")
    flow_engine = import_module("metroflow.flow.engine")

    links = flow_state.LinkState(
        queue_vehicles=(4.0, 0.0),
        inflow_vehicles=(0.0, 0.0),
        outflow_vehicles=(0.0, 0.0),
        travel_time_cost=(2.0, 2.0),
        capacity_veh_per_tick=(2.0, 2.0),
        incident_capacity_multiplier=(1.0, 1.0),
    )
    nodes = flow_state.NodeState(
        turn_from_link_index=(0,),
        turn_to_link_index=(1,),
        turn_demand=(3.0,),
        turn_supply=(0.0,),
        turn_flow=(0.0,),
        signal_phase_index=(0,),
        signal_phase_timer=(0,),
    )

    result = flow_engine.update_link_node_flow(links, nodes, validate=True)

    assert tuple(float(x) for x in result.node_state.turn_flow.tolist()) == (2.0,)
    assert tuple(float(x) for x in result.link_state.queue_vehicles.tolist()) == (2.0, 2.0)
    assert result.link_state.capacity_violation_count == 0
    assert isinstance(result.link_state.queue_vehicles, np.ndarray)
    assert isinstance(result.node_state.turn_flow, np.ndarray)


def test_active_agent_pool_allocates_reads_and_releases_slots():
    active_agents = import_module("metroflow.sim.active_agents")

    pool = active_agents.create_active_agent_pool(2)
    payload = active_agents.ActiveAgentSlot.spawn(
        citizen_id=7,
        trip_id=11,
        current_link_id=3,
        dest_node_id=9,
        behavior_profile_id=1,
    )

    allocated, slot_id = active_agents.allocate_active_agent_slot(pool, payload)
    read_back = active_agents.read_active_agent_slot(allocated, slot_id)
    released = active_agents.release_active_agent_slot(allocated, slot_id)

    assert allocated.alive_count == 1
    assert read_back.citizen_id == 7
    assert released.alive_count == 0
    assert released.free_slot_count == 2
    assert isinstance(allocated.alive_mask, np.ndarray)
    assert isinstance(released.free_slot_stack, np.ndarray)


def test_learning_ucb_and_policy_blend_keep_baseline_fallback():
    config = import_module("metroflow.sim.config")
    od_ucb = import_module("metroflow.learning.od_ucb")
    policy_blend = import_module("metroflow.learning.policy_blend")

    state = od_ucb.create_od_ucb_state(od_key=("home", "work"), arm_count=2)
    assert od_ucb.select_ucb_arm(state=state) == 0

    updated = od_ucb.update_od_ucb_state(state=state, arm_index=0, reward=1.0, current_tick=5)
    assert int(updated.pull_count[0]) == 1
    assert float(updated.estimated_reward[0]) == pytest.approx(1.0)

    blend_state = policy_blend.PolicyBlendState(lambda_mix=0.5, baseline_only_mode=False)
    fallback = policy_blend.apply_policy_blend_control(
        blend_state,
        target_lambda=0.5,
        bounds=config.LearningMixBounds(lambda_min=0.0, lambda_max=1.0),
        learning_enabled=True,
        adaptive_output_valid=False,
    )

    assert fallback.baseline_only_mode is True
    assert fallback.fallback_reason == policy_blend.PolicyBlendFallbackReason.INVALID_OUTPUT


def test_rng_contract_uses_host_uint32_arrays_without_jax_runtime_type():
    rng = import_module("metroflow.sim.rng")

    key = rng.key_from_seed(0x1_0000_0001)
    next_state_key, use_now_key = rng.next_key(key)
    folded = rng.fold_in_path(key, "route", 7)

    assert isinstance(key, np.ndarray)
    assert key.dtype == np.dtype("uint32")
    assert key.shape == (2,)
    assert key.tolist() == [0, 1]
    assert isinstance(next_state_key, np.ndarray)
    assert next_state_key.tolist() == [0, 2]
    assert use_now_key.tolist() == next_state_key.tolist()
    assert isinstance(folded, np.ndarray)
    assert folded.dtype == np.dtype("uint32")
    assert folded.shape == (2,)
    assert rng.fold_in_path(key, "route", 7).tolist() == folded.tolist()
