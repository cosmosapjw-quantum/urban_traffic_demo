from dataclasses import replace

import pytest

from metroflow.core.contracts import TickSchedule
from metroflow.core.state import (
    AccessibilityState,
    GraphState,
    LandUseState,
    PolicyState,
    ReplayState,
    TrafficState,
    make_empty_world_state,
)
from metroflow.sim.orchestrator import step_world


def make_world(num_edges: int = 2, step: int = 0) -> object:
    return replace(
        make_empty_world_state(seed=17),
        graph=GraphState(num_edges=num_edges),
        traffic=TrafficState(
            step=step,
            edge_queue=(0.0,) * num_edges,
            edge_stock=(1.0,) * num_edges,
            edge_travel_time=(1.0,) * num_edges,
        ),
    )


def test_step_world_executes_fast_tick_edge_evolution_with_overrides():
    world = make_world()
    schedule = TickSchedule(fast_every=1, medium_every=5, slow_every=20)

    world2 = step_world(
        world,
        schedule=schedule,
        edge_inflow_veh_per_tick=(2.0, 0.5),
        edge_outflow_veh_per_tick=(1.0, 0.25),
        edge_free_flow_time_ticks=(5.0, 6.0),
        edge_capacity_veh_per_tick=(2.0, 4.0),
    )

    assert world2.traffic.step == 1
    assert world2.traffic.edge_queue == (1.0, 0.25)
    assert world2.traffic.edge_stock == (2.0, 1.25)
    assert world2.traffic.edge_travel_time == (5.5, 6.0625)


def test_step_world_passes_optional_edge_inputs_to_helper(monkeypatch: pytest.MonkeyPatch):
    world = make_world()
    schedule = TickSchedule()
    captured: dict[str, object] = {}

    def fake_evolve(current_world, **kwargs):
        captured["world"] = current_world
        captured["kwargs"] = kwargs
        return current_world

    monkeypatch.setattr("metroflow.sim.orchestrator.evolve_edges_fast_tick", fake_evolve)

    result = step_world(
        world,
        schedule=schedule,
        edge_inflow_veh_per_tick=(1.0, 2.0),
        edge_outflow_veh_per_tick=(0.5, 0.25),
        edge_free_flow_time_ticks=(3.0, 4.0),
        edge_capacity_veh_per_tick=(5.0, 6.0),
    )

    assert result is world
    assert captured["world"] is world
    assert captured["kwargs"] == {
        "edge_inflow_veh_per_tick": (1.0, 2.0),
        "edge_outflow_veh_per_tick": (0.5, 0.25),
        "edge_free_flow_time_ticks": (3.0, 4.0),
        "edge_capacity_veh_per_tick": (5.0, 6.0),
    }


def test_step_world_rejects_override_length_mismatch():
    world = make_world()

    with pytest.raises(ValueError, match="edge_inflow_veh_per_tick length must match graph.num_edges."):
        step_world(
            world,
            schedule=TickSchedule(),
            edge_inflow_veh_per_tick=(1.0,),
        )


def test_step_world_is_deterministic_for_equivalent_inputs():
    world = make_world(step=2)
    schedule = TickSchedule(fast_every=1, medium_every=5, slow_every=20)
    kwargs = {
        "edge_inflow_veh_per_tick": (1.0, 0.25),
        "edge_outflow_veh_per_tick": (0.5, 0.25),
        "edge_free_flow_time_ticks": (7.0, 8.0),
        "edge_capacity_veh_per_tick": (2.0, 3.0),
    }

    world2 = step_world(world, schedule=schedule, **kwargs)
    world3 = step_world(world, schedule=schedule, **kwargs)

    assert world2 == world3


def test_step_world_rejects_invalid_incoming_world_before_fast_tick():
    world = replace(
        make_world(num_edges=1),
        traffic=TrafficState(
            step=0,
            edge_queue=(-1.0,),
            edge_stock=(1.0,),
            edge_travel_time=(1.0,),
        ),
    )

    with pytest.raises(ValueError, match="Edge queue values must be non-negative."):
        step_world(world, schedule=TickSchedule())


def test_step_world_rejects_invalid_produced_world(monkeypatch: pytest.MonkeyPatch):
    world = make_world(num_edges=1)

    def fake_evolve(current_world, **kwargs):
        return replace(
            current_world,
            traffic=replace(
                current_world.traffic,
                step=current_world.traffic.step + 1,
                edge_queue=(2.0,),
                edge_stock=(1.0,),
                edge_travel_time=(1.0,),
            ),
        )

    monkeypatch.setattr("metroflow.sim.orchestrator.evolve_edges_fast_tick", fake_evolve)

    with pytest.raises(ValueError, match="Edge queue must not exceed edge stock."):
        step_world(world, schedule=TickSchedule())


def test_step_world_fast_only_cadence_keeps_lagged_state_unchanged():
    world = replace(
        make_world(step=1),
        accessibility=AccessibilityState(version=3, lagged_snapshot_step=8, zonal_costs=((1.0, 2.0),)),
        landuse=LandUseState(
            version=4,
            zone_labels=("core",),
            housing_capacity=(100.0,),
            jobs_capacity=(120.0,),
        ),
        policy=PolicyState(version=5, last_learning_step=11),
        replay=ReplayState(seed=17, journal_length=9),
    )
    schedule = TickSchedule(fast_every=1, medium_every=3, slow_every=5)

    world2 = step_world(
        world,
        schedule=schedule,
        edge_inflow_veh_per_tick=(0.5, 0.0),
        edge_outflow_veh_per_tick=(0.25, 0.0),
        edge_free_flow_time_ticks=(2.0, 3.0),
        edge_capacity_veh_per_tick=(1.0, 1.0),
    )

    assert world2.accessibility == world.accessibility
    assert world2.landuse == world.landuse
    assert world2.policy == world.policy
    assert world2.replay == world.replay
