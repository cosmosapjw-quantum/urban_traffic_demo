from __future__ import annotations

import numpy as np
import pytest


def test_point_queue_uses_rate_supply_and_additive_waiting_ticks() -> None:
    from metroflow.flow.engine import update_link_node_flow
    from metroflow.flow.state import LinkState, NodeState

    link_state = LinkState(
        queue_vehicles=(1.0, 2.0),
        inflow_vehicles=(0.0, 0.0),
        outflow_vehicles=(0.0, 0.0),
        travel_time_cost=(2.0, 4.0),
        capacity_veh_per_tick=(1.0, 2.0),
        incident_capacity_multiplier=(1.0, 1.0),
        metadata={
            "free_flow_travel_time_cost": np.asarray((2.0, 4.0), dtype=np.float32),
            "travel_time_cost_unit": "simulation_ticks",
        },
    )
    node_state = NodeState(
        turn_from_link_index=(0,),
        turn_to_link_index=(1,),
        turn_demand=(1.0,),
        turn_supply=(0.0,),
        turn_flow=(0.0,),
        signal_phase_index=(0, 0),
        signal_phase_timer=(0, 0),
    )

    result = update_link_node_flow(link_state, node_state, validate=True)

    # A point queue has no implicit finite storage cap: an existing downstream
    # queue equal to its service rate does not make receiving supply vanish.
    assert result.node_state.turn_flow.tolist() == [1.0]
    assert result.link_state.queue_vehicles.tolist() == [0.0, 3.0]
    # t = t_ff + q / mu, with every term expressed in simulation ticks.
    assert result.link_state.travel_time_cost.tolist() == pytest.approx([2.0, 5.5])


def test_runtime_link_units_rescale_with_tick_duration() -> None:
    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr
    from metroflow.sim.init import _build_initial_link_state

    road_csr = build_road_network_csr(
        nodes=(Node(1), Node(2, x=100.0)),
        links=(
            RoadLink(
                10,
                1,
                2,
                RoadClass.ARTERIAL,
                length_m=100.0,
                free_flow_speed_mps=10.0,
                capacity_veh_per_tick=2.0,
            ),
        ),
    )

    one_second = _build_initial_link_state(road_csr, tick_seconds=1.0)
    two_seconds = _build_initial_link_state(road_csr, tick_seconds=2.0)

    assert one_second.travel_time_cost.tolist() == pytest.approx([10.0])
    assert two_seconds.travel_time_cost.tolist() == pytest.approx([5.0])
    assert one_second.capacity_veh_per_tick.tolist() == pytest.approx([2.0])
    assert two_seconds.capacity_veh_per_tick.tolist() == pytest.approx([4.0])
    assert one_second.travel_time_cost[0] * 1.0 == pytest.approx(
        two_seconds.travel_time_cost[0] * 2.0
    )
    assert one_second.capacity_veh_per_tick[0] / 1.0 == pytest.approx(
        two_seconds.capacity_veh_per_tick[0] / 2.0
    )
    assert two_seconds.metadata["travel_time_cost_unit"] == "simulation_ticks"
    assert two_seconds.metadata["tick_seconds"] == 2.0


def test_discrete_merge_shares_one_downstream_receiving_token() -> None:
    from metroflow.flow.engine import update_link_node_flow
    from metroflow.flow.state import LinkState, NodeState

    link_state = LinkState(
        queue_vehicles=(1.0, 1.0, 0.0),
        inflow_vehicles=(0.0, 0.0, 0.0),
        outflow_vehicles=(0.0, 0.0, 0.0),
        travel_time_cost=(1.0, 1.0, 1.0),
        capacity_veh_per_tick=(1.0, 1.0, 1.0),
        incident_capacity_multiplier=(1.0, 1.0, 1.0),
        metadata={
            "free_flow_travel_time_cost": np.ones((3,), dtype=np.float32),
        },
    )
    node_state = NodeState(
        turn_from_link_index=(0, 1),
        turn_to_link_index=(2, 2),
        turn_demand=(1.0, 1.0),
        turn_supply=(0.0, 0.0),
        turn_flow=(0.0, 0.0),
        signal_phase_index=(0, 0, 0, 0),
        signal_phase_timer=(0, 0, 0, 0),
    )

    first = update_link_node_flow(
        link_state,
        node_state,
        discrete_agent_authority=True,
        validate=True,
    )

    assert first.node_state.turn_flow.tolist() == [1.0, 0.0]
    assert first.link_state.inflow_vehicles.tolist() == [0.0, 0.0, 1.0]
    assert first.link_state.queue_vehicles.tolist() == [0.0, 1.0, 1.0]
    assert first.link_state.metadata["runtime_link_receiving_tokens"].tolist() == [
        0.0,
        0.0,
        1.0,
    ]
    assert not bool(np.any(first.link_state.capacity_violation_flags))

    second_node = NodeState(
        turn_from_link_index=first.node_state.turn_from_link_index,
        turn_to_link_index=first.node_state.turn_to_link_index,
        turn_demand=(0.0, 1.0),
        turn_supply=first.node_state.turn_supply,
        turn_flow=first.node_state.turn_flow,
        signal_phase_index=first.node_state.signal_phase_index,
        signal_phase_timer=first.node_state.signal_phase_timer,
        metadata=first.node_state.metadata,
    )
    second = update_link_node_flow(
        first.link_state,
        second_node,
        discrete_agent_authority=True,
        validate=True,
    )

    assert second.node_state.turn_flow.tolist() == [0.0, 1.0]
    assert second.link_state.inflow_vehicles.tolist() == [0.0, 0.0, 1.0]
    assert second.link_state.queue_vehicles.tolist() == [0.0, 0.0, 2.0]
    assert not bool(np.any(second.link_state.capacity_violation_flags))


def test_discrete_sink_cannot_starve_behind_sustained_internal_turn_demand() -> None:
    from metroflow.flow.engine import update_link_node_flow
    from metroflow.flow.state import LinkState, NodeState

    links = LinkState(
        queue_vehicles=(10.0, 0.0),
        inflow_vehicles=(0.0, 0.0),
        outflow_vehicles=(0.0, 0.0),
        travel_time_cost=(1.0, 1.0),
        capacity_veh_per_tick=(1.0, 1.0),
        incident_capacity_multiplier=(1.0, 1.0),
        metadata={"free_flow_travel_time_cost": np.ones((2,), dtype=np.float32)},
    )
    nodes = NodeState(
        turn_from_link_index=(0,),
        turn_to_link_index=(1,),
        turn_demand=(4.0,),
        turn_supply=(0.0,),
        turn_flow=(0.0,),
        signal_phase_index=(0, 0, 0),
        signal_phase_timer=(0, 0, 0),
        metadata={
            "runtime_sink_demand_by_link_index": np.asarray(
                (1.0, 0.0), dtype=np.float32
            )
        },
    )

    sink_flows: list[float] = []
    for _ in range(3):
        result = update_link_node_flow(
            links,
            nodes,
            discrete_agent_authority=True,
            validate=True,
        )
        sink_flow = float(
            result.node_state.metadata["runtime_sink_flow_by_link_index"][0]
        )
        sink_flows.append(sink_flow)
        assert result.link_state.outflow_vehicles[0] <= 1.0
        links = result.link_state
        nodes = result.node_state

    assert sink_flows == [0.0, 0.0, 1.0]


def test_discrete_fractional_capacity_validates_accumulated_service_token() -> None:
    from metroflow.flow.engine import update_link_node_flow
    from metroflow.flow.state import LinkState, NodeState, validate_link_state

    links = LinkState(
        queue_vehicles=(1.0, 0.0),
        inflow_vehicles=(0.0, 0.0),
        outflow_vehicles=(0.0, 0.0),
        travel_time_cost=(1.0, 1.0),
        capacity_veh_per_tick=(0.25, 0.25),
        incident_capacity_multiplier=(1.0, 1.0),
        metadata={"free_flow_travel_time_cost": np.ones((2,), dtype=np.float32)},
    )
    nodes = NodeState(
        turn_from_link_index=(0,),
        turn_to_link_index=(1,),
        turn_demand=(1.0,),
        turn_supply=(0.0,),
        turn_flow=(0.0,),
        signal_phase_index=(0, 0, 0),
        signal_phase_timer=(0, 0, 0),
    )

    for _ in range(4):
        result = update_link_node_flow(
            links,
            nodes,
            discrete_agent_authority=True,
            validate=True,
        )
        links, nodes = result.link_state, result.node_state

    assert links.outflow_vehicles.tolist() == [1.0, 0.0]
    assert links.metadata["runtime_link_service_tokens"].tolist() == [1.0, 0.0]
    assert validate_link_state(links) == ()


def test_discrete_asymmetric_fractional_capacities_do_not_phase_starve() -> None:
    from metroflow.flow.engine import update_link_node_flow
    from metroflow.flow.state import LinkState, NodeState

    links = LinkState(
        queue_vehicles=(10.0, 0.0),
        inflow_vehicles=(0.0, 0.0),
        outflow_vehicles=(0.0, 0.0),
        travel_time_cost=(1.0, 1.0),
        capacity_veh_per_tick=(0.6, 0.4),
        incident_capacity_multiplier=(1.0, 1.0),
        metadata={"free_flow_travel_time_cost": np.ones((2,), dtype=np.float32)},
    )
    nodes = NodeState(
        turn_from_link_index=(0,),
        turn_to_link_index=(1,),
        turn_demand=(10.0,),
        turn_supply=(0.0,),
        turn_flow=(0.0,),
        signal_phase_index=(0, 0),
        signal_phase_timer=(0, 0),
    )

    realized = 0.0
    for _ in range(10):
        result = update_link_node_flow(
            links,
            nodes,
            discrete_agent_authority=True,
            validate=True,
        )
        realized += float(result.node_state.turn_flow[0])
        links, nodes = result.link_state, result.node_state

    assert realized == 4.0
    assert links.metadata["runtime_link_service_token_carry"].tolist() == [1.0, 0.0]


def test_discrete_residual_one_cannot_mint_closed_link_capacity() -> None:
    from dataclasses import replace

    from metroflow.flow.engine import update_link_node_flow
    from metroflow.flow.state import LinkState, NodeState

    links = LinkState(
        queue_vehicles=(1.0,),
        inflow_vehicles=(0.0,),
        outflow_vehicles=(0.0,),
        travel_time_cost=(1.0,),
        capacity_veh_per_tick=(0.0,),
        incident_capacity_multiplier=(0.0,),
        metadata={"free_flow_travel_time_cost": np.ones((1,), dtype=np.float32)},
    )
    nodes = NodeState(
        turn_from_link_index=(),
        turn_to_link_index=(),
        turn_demand=(),
        turn_supply=(),
        turn_flow=(),
        signal_phase_index=(0,),
        signal_phase_timer=(0,),
        metadata={
            "runtime_sink_demand_by_link_index": np.asarray(
                (1.0,), dtype=np.float32
            )
        },
    )
    initialized = update_link_node_flow(
        links,
        nodes,
        discrete_agent_authority=True,
        validate=True,
    )
    corrupted_metadata = dict(initialized.link_state.metadata)
    corrupted_metadata["runtime_link_service_residual"] = np.asarray(
        (1.0,), dtype=np.float32
    )

    with pytest.raises(ValueError, match=r"runtime_link_service_residual must be < 1.0"):
        update_link_node_flow(
            replace(initialized.link_state, metadata=corrupted_metadata),
            initialized.node_state,
            discrete_agent_authority=True,
        )

    corrupted_carry = dict(initialized.link_state.metadata)
    corrupted_carry["runtime_link_service_token_carry"] = np.asarray(
        (2.0,), dtype=np.float32
    )
    with pytest.raises(ValueError, match=r"runtime_link_service_token_carry must be <= 1.0"):
        update_link_node_flow(
            replace(initialized.link_state, metadata=corrupted_carry),
            initialized.node_state,
            discrete_agent_authority=True,
        )


@pytest.mark.parametrize("tick_seconds", [float("nan"), float("inf")])
def test_runtime_tick_seconds_must_be_finite(tick_seconds: float) -> None:
    from metroflow.sim.config import SimulationConfig

    with pytest.raises(ValueError, match="tick_seconds must be finite and > 0"):
        SimulationConfig(tick_seconds=tick_seconds)


def test_runtime_invariant_rejects_downstream_receiving_token_excess() -> None:
    from metroflow.flow.state import LinkState
    from metroflow.sim.invariants import validate_invariants
    from metroflow.sim.state import SimulationDynamicRefs, SimulationState

    corrupted = LinkState(
        queue_vehicles=(0.0, 2.0),
        inflow_vehicles=(0.0, 2.0),
        outflow_vehicles=(0.0, 0.0),
        travel_time_cost=(1.0, 3.0),
        capacity_veh_per_tick=(1.0, 1.0),
        incident_capacity_multiplier=(1.0, 1.0),
        capacity_violation_flags=(False, False),
        metadata={
            "runtime_link_service_tokens": np.asarray(
                (1.0, 1.0), dtype=np.float32
            ),
            "runtime_link_receiving_tokens": np.asarray(
                (0.0, 1.0), dtype=np.float32
            ),
        },
    )

    report = validate_invariants(
        SimulationState(
            dynamic=SimulationDynamicRefs(flow_link_state=corrupted),
        )
    )

    assert not report.ok
    codes = {violation.code for violation in report.violations}
    assert "capacity_flag_mask_mismatch" in codes
    assert "capacity_exceeded" in codes


def test_discrete_runtime_rejects_non_finite_or_missing_token_authority() -> None:
    from dataclasses import replace

    from metroflow.flow.engine import update_link_node_flow
    from metroflow.flow.state import LinkState, NodeState
    from metroflow.sim.invariants import validate_invariants
    from metroflow.sim.state import SimulationDynamicRefs, SimulationState

    links = LinkState(
        queue_vehicles=(1.0, 0.0),
        inflow_vehicles=(0.0, 0.0),
        outflow_vehicles=(0.0, 0.0),
        travel_time_cost=(1.0, 1.0),
        capacity_veh_per_tick=(1.0, 1.0),
        incident_capacity_multiplier=(1.0, 1.0),
        metadata={"free_flow_travel_time_cost": np.ones((2,), dtype=np.float32)},
    )
    nodes = NodeState(
        turn_from_link_index=(0,),
        turn_to_link_index=(1,),
        turn_demand=(1.0,),
        turn_supply=(0.0,),
        turn_flow=(0.0,),
        signal_phase_index=(0, 0, 0),
        signal_phase_timer=(0, 0, 0),
    )
    valid = update_link_node_flow(
        links,
        nodes,
        discrete_agent_authority=True,
        validate=True,
    )

    non_finite_prior = dict(valid.link_state.metadata)
    non_finite_prior["runtime_link_service_residual"] = np.asarray(
        (np.nan, 0.0), dtype=np.float32
    )
    with pytest.raises(ValueError, match="only finite"):
        update_link_node_flow(
            replace(valid.link_state, metadata=non_finite_prior),
            valid.node_state,
            discrete_agent_authority=True,
        )

    non_finite_tokens = dict(valid.link_state.metadata)
    non_finite_tokens["runtime_link_receiving_tokens"] = np.asarray(
        (0.0, np.nan), dtype=np.float32
    )
    non_finite_state = SimulationState(
        dynamic=SimulationDynamicRefs(
            flow_link_state=replace(valid.link_state, metadata=non_finite_tokens),
            flow_node_state=valid.node_state,
        )
    )
    report = validate_invariants(non_finite_state)
    assert not report.ok
    assert {violation.code for violation in report.violations} >= {
        "runtime_token_metadata_invalid",
        "non_finite_capacity_authority",
    }

    missing_tokens = dict(valid.link_state.metadata)
    missing_tokens.pop("runtime_link_receiving_tokens")
    with pytest.raises(ValueError, match="required by prior discrete-agent authority"):
        update_link_node_flow(
            replace(valid.link_state, metadata=missing_tokens),
            valid.node_state,
            discrete_agent_authority=True,
        )
    missing_state = SimulationState(
        dynamic=SimulationDynamicRefs(
            flow_link_state=replace(valid.link_state, metadata=missing_tokens),
            flow_node_state=valid.node_state,
        )
    )
    missing_report = validate_invariants(missing_state)
    assert not missing_report.ok
    assert any(
        violation.code == "runtime_token_metadata_invalid"
        and violation.details.get("key") == "runtime_link_receiving_tokens"
        and violation.details.get("reason") == "missing"
        for violation in missing_report.violations
    )
