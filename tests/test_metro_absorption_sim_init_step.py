from __future__ import annotations

import sys


def test_initial_simulation_state_wires_city_demand_flow_without_donor_path() -> None:
    assert not any(path.endswith("/metro/src") for path in sys.path)

    from metroflow.flow.state import LinkState, NodeState
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.init import build_initial_simulation_state

    bundle = build_initial_simulation_state(
        config=SimulationConfig(
            population_target=120,
            active_agent_capacity=16,
            ui_stream_enabled=True,
        ),
        scenario_seed=21,
        eager_trip_generation=True,
    )
    state = bundle.state
    road_csr = state.static.routing_static["road_csr"]

    assert state.tick_index == 0
    assert state.static.scenario_id == "synthetic-21"
    assert bundle.zoning.validate(topology=bundle.city_topology) == ()
    assert bundle.population.citizens
    assert bundle.trip_requests.trip_requests
    assert isinstance(state.dynamic.flow_link_state, LinkState)
    assert isinstance(state.dynamic.flow_node_state, NodeState)
    assert state.dynamic.flow_link_state.link_count == road_csr.link_count
    assert state.dynamic.flow_node_state.node_count == road_csr.node_count
    assert state.static.ui_network_geometry_version.startswith("city-21-")
    assert state.dynamic.metrics_state["generated_trip_total"] == len(
        bundle.trip_requests.trip_requests
    )


def test_simulation_step_applies_control_immutably_and_emits_forced_snapshot() -> None:
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.init import build_initial_simulation_state
    from metroflow.sim.step import simulation_step

    bundle = build_initial_simulation_state(
        config=SimulationConfig(population_target=80, active_agent_capacity=8),
        scenario_seed=22,
        eager_trip_generation=True,
    )

    next_state, telemetry, snapshot, next_key = simulation_step(
        bundle.state,
        SimulationControl(set_time_band="night", ui_force_snapshot=True),
        bundle.rng_key,
    )

    assert bundle.state.tick_index == 0
    assert next_state.tick_index == 1
    assert next_state.time_band.value == "night"
    assert telemetry.tick_index == 1
    assert telemetry.ui_snapshot_emitted is True
    assert snapshot is not None
    assert snapshot["clock_state"]["sim_tick"] == 1
    assert next_key.shape == bundle.rng_key.shape
    assert next_key.tolist() != bundle.rng_key.tolist()


def test_simulation_step_pause_does_not_advance_tick() -> None:
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.init import build_initial_simulation_state
    from metroflow.sim.step import simulation_step

    bundle = build_initial_simulation_state(
        config=SimulationConfig(population_target=80, active_agent_capacity=8),
        scenario_seed=23,
        eager_trip_generation=False,
    )

    paused_state, telemetry, snapshot, _next_key = simulation_step(
        bundle.state,
        SimulationControl(pause=True, set_day_type="weekend"),
        bundle.rng_key,
    )

    assert paused_state.tick_index == 0
    assert paused_state.day_type.value == "weekend"
    assert telemetry.tick_index == 0
    assert telemetry.ui_snapshot_emitted is False
    assert snapshot is None
