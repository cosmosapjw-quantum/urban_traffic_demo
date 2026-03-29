from dataclasses import FrozenInstanceError, replace

import pytest

from metroflow.core.cache import (
    accessibility_cache_token,
    build_cache_registry,
    invalidate_on_graph_edit,
    invalidate_on_landuse_edit,
    invalidate_on_policy_edit,
    policy_cache_token,
    route_cache_token,
)
from metroflow.core.state import make_empty_world_state, with_graph_version_bump
from metroflow.core.contracts import default_simulation_config, validate_time_scale_separation, validate_state_contract
from metroflow.core.state import AccessibilityState, GraphState, LandUseState, TrafficState
from metroflow.traffic.meso import evolve_edges_fast_tick


def make_materialized_graph(num_edges: int) -> GraphState:
    return GraphState(
        num_nodes=max(num_edges + 1, 0),
        num_edges=num_edges,
        edge_src=tuple(range(num_edges)),
        edge_dst=tuple(range(1, num_edges + 1)),
        edge_class=("road",) * num_edges,
    )


def test_make_empty_world_state():
    world = make_empty_world_state(seed=42)
    assert world.replay.seed == 42
    assert world.graph.version == 0
    with pytest.raises(FrozenInstanceError):
        world.graph.version = 3


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


def test_cache_invalidation_tokens_follow_declared_rules():
    world = replace(
        make_empty_world_state(),
        graph=GraphState(version=1),
        accessibility=AccessibilityState(version=4, graph_version=1, landuse_version=2),
        landuse=LandUseState(version=2),
    )

    graph_edit = invalidate_on_graph_edit(world)
    landuse_edit = invalidate_on_landuse_edit(world)
    policy_edit = invalidate_on_policy_edit(world)

    assert route_cache_token(graph_edit) == (2, 0)
    assert accessibility_cache_token(graph_edit) == (2, 2, 5)
    assert accessibility_cache_token(landuse_edit) == (1, 3, 5)
    assert policy_cache_token(policy_edit) == 1
    assert build_cache_registry(graph_edit).tags["accessibility"] == 5


def test_fast_tick_edge_evolution_preserves_state_contract():
    world = replace(
        make_empty_world_state(),
        graph=make_materialized_graph(2),
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
        graph=make_materialized_graph(1),
        traffic=traffic,
    )

    with pytest.raises(ValueError, match=message):
        validate_state_contract(world)


def test_validate_state_contract_rejects_non_empty_graph_without_materialized_metadata():
    world = replace(
        make_empty_world_state(),
        graph=GraphState(num_nodes=2, num_edges=1),
        traffic=TrafficState(
            edge_queue=(0.0,),
            edge_stock=(0.0,),
            edge_travel_time=(1.0,),
        ),
    )

    with pytest.raises(ValueError, match="edge_src length must match graph.num_edges."):
        validate_state_contract(world)


def test_validate_state_contract_rejects_invalid_zone_shapes_and_lag():
    world = replace(
        make_empty_world_state(),
        landuse=LandUseState(
            zone_labels=("A", "B"),
            housing_capacity=(10.0, 20.0),
            jobs_capacity=(12.0, 18.0),
        ),
        accessibility=AccessibilityState(
            lagged_snapshot_step=0,
            zonal_costs=((1.0, 2.0), (3.0, 4.0)),
        ),
    )

    with pytest.raises(ValueError, match="Accessibility snapshot must be lagged"):
        validate_state_contract(world)


def test_validate_state_contract_rejects_cleared_payload_without_reset_lagged_step():
    world = replace(
        make_empty_world_state(),
        landuse=LandUseState(
            zone_labels=("A",),
            housing_capacity=(10.0,),
            jobs_capacity=(12.0,),
        ),
        accessibility=AccessibilityState(
            lagged_snapshot_step=0,
            zonal_costs=(),
        ),
    )

    with pytest.raises(ValueError, match="Cleared accessibility payload must reset lagged_snapshot_step to -1."):
        validate_state_contract(world)
