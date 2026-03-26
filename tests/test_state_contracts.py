from dataclasses import replace

import pytest

from metroflow.core.state import make_empty_world_state, with_graph_version_bump
from metroflow.core.contracts import default_simulation_config, validate_time_scale_separation, validate_state_contract
from metroflow.core.state import GraphState, TrafficState
from metroflow.traffic.meso import evolve_edges_fast_tick


def test_make_empty_world_state():
    world = make_empty_world_state(seed=42)
    assert world.replay.seed == 42
    assert world.graph.version == 0


def test_graph_version_bump():
    world = make_empty_world_state()
    world2 = with_graph_version_bump(world)
    assert world2.graph.version == world.graph.version + 1


def test_validate_config():
    config = default_simulation_config()
    validate_time_scale_separation(config)


def test_validate_state_contract_empty():
    world = make_empty_world_state()
    validate_state_contract(world)


def test_fast_tick_edge_evolution_preserves_state_contract():
    world = replace(
        make_empty_world_state(),
        graph=GraphState(num_edges=2),
        traffic=TrafficState(
            edge_queue=(0.0, 0.0),
            edge_stock=(0.0, 1.0),
            edge_travel_time=(1.0, 1.0),
        ),
    )

    world2 = evolve_edges_fast_tick(
        world,
        edge_inflow_veh_per_tick=(1.0, 0.0),
        edge_outflow_veh_per_tick=(0.5, 0.0),
        edge_free_flow_time_ticks=(2.0, 3.0),
        edge_capacity_veh_per_tick=(1.0, 1.0),
    )

    validate_state_contract(world2)


@pytest.mark.parametrize(
    ("traffic", "message"),
    (
        (
            TrafficState(
                edge_queue=(-1.0,),
                edge_stock=(1.0,),
                edge_travel_time=(1.0,),
            ),
            "Edge queue values must be non-negative.",
        ),
        (
            TrafficState(
                edge_queue=(0.0,),
                edge_stock=(-1.0,),
                edge_travel_time=(1.0,),
            ),
            "Edge stock values must be non-negative.",
        ),
        (
            TrafficState(
                edge_queue=(2.0,),
                edge_stock=(1.0,),
                edge_travel_time=(1.0,),
            ),
            "Edge queue must not exceed edge stock.",
        ),
        (
            TrafficState(
                edge_queue=(0.0,),
                edge_stock=(1.0,),
                edge_travel_time=(-1.0,),
            ),
            "Edge travel-time values must be non-negative.",
        ),
    ),
)
def test_validate_state_contract_rejects_invalid_traffic_values(traffic: TrafficState, message: str):
    world = replace(
        make_empty_world_state(),
        graph=GraphState(num_edges=1),
        traffic=traffic,
    )

    with pytest.raises(ValueError, match=message):
        validate_state_contract(world)
