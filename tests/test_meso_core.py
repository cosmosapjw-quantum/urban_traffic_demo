from dataclasses import replace

import pytest

from metroflow.core.state import GraphState, TrafficState, make_empty_world_state
from metroflow.traffic.meso import evolve_edges_fast_tick, project_feasible_movements, update_edge_state


def make_materialized_graph(num_edges: int) -> GraphState:
    return GraphState(
        num_nodes=max(num_edges + 1, 0),
        num_edges=num_edges,
        edge_src=tuple(range(num_edges)),
        edge_dst=tuple(range(1, num_edges + 1)),
        edge_class=("road",) * num_edges,
    )


def test_update_edge_state_nonnegative():
    st = update_edge_state(queue=0.0, stock=1.0, inflow=2.0, outflow=1.0, free_flow_time=10.0, capacity=2.0)
    assert st.queue >= 0.0
    assert st.stock >= 0.0
    assert st.travel_time >= 10.0


def test_update_edge_state_respects_storage_and_capacity():
    st = update_edge_state(queue=1.0, stock=2.0, inflow=3.0, outflow=10.0, free_flow_time=5.0, capacity=2.0)
    assert st.stock == 3.0
    assert st.queue <= st.stock


def test_project_feasible_movements():
    out = project_feasible_movements((3.0, 2.0), (1.0, 3.0), (2.0, 2.0))
    assert out == (1.0, 2.0)


def test_evolve_edges_fast_tick_updates_all_edges():
    world = replace(
        make_empty_world_state(seed=11),
        graph=make_materialized_graph(2),
        traffic=TrafficState(
            step=3,
            edge_queue=(0.0, 1.0),
            edge_stock=(1.0, 2.0),
            edge_travel_time=(5.0, 7.0),
        ),
    )

    world2 = evolve_edges_fast_tick(
        world,
        edge_inflow_veh_per_tick=(2.0, 0.5),
        edge_outflow_veh_per_tick=(1.0, 1.5),
        edge_free_flow_time_ticks=(10.0, 12.0),
        edge_capacity_veh_per_tick=(2.0, 4.0),
    )

    assert world2.traffic.step == 4
    assert world2.traffic.edge_queue == (1.0, 1.0)
    assert world2.traffic.edge_stock == (2.0, 1.0)
    assert world2.traffic.edge_travel_time == (10.5, 12.25)
    assert world2.graph == world.graph
    assert world2.demand == world.demand
    assert world2.accessibility == world.accessibility
    assert world2.landuse == world.landuse
    assert world2.policy == world.policy
    assert world2.replay == world.replay


def test_evolve_edges_fast_tick_uses_baseline_fallback():
    world = replace(
        make_empty_world_state(),
        graph=make_materialized_graph(2),
        traffic=TrafficState(
            step=0,
            edge_queue=(0.0, 0.0),
            edge_stock=(1.0, 3.0),
            edge_travel_time=(0.0, 0.0),
        ),
    )

    world2 = evolve_edges_fast_tick(world)

    assert world2.traffic.step == 1
    assert world2.traffic.edge_queue == (0.0, 0.0)
    assert world2.traffic.edge_stock == (1.0, 3.0)
    assert world2.traffic.edge_travel_time == (1.0, 1.0)


def test_evolve_edges_fast_tick_rejects_bad_tuple_lengths():
    world = replace(
        make_empty_world_state(),
        graph=make_materialized_graph(2),
        traffic=TrafficState(
            edge_queue=(0.0, 0.0),
            edge_stock=(0.0, 0.0),
            edge_travel_time=(1.0, 1.0),
        ),
    )

    with pytest.raises(ValueError, match="edge_inflow_veh_per_tick length must match graph.num_edges."):
        evolve_edges_fast_tick(world, edge_inflow_veh_per_tick=(1.0,))


def test_evolve_edges_fast_tick_is_deterministic():
    world = replace(
        make_empty_world_state(seed=5),
        graph=make_materialized_graph(2),
        traffic=TrafficState(
            step=1,
            edge_queue=(0.0, 2.0),
            edge_stock=(1.0, 3.0),
            edge_travel_time=(4.0, 6.0),
        ),
    )
    kwargs = {
        "edge_inflow_veh_per_tick": (2.0, 1.0),
        "edge_outflow_veh_per_tick": (1.0, 0.5),
        "edge_free_flow_time_ticks": (8.0, 9.0),
        "edge_capacity_veh_per_tick": (2.0, 1.5),
    }

    world2 = evolve_edges_fast_tick(world, **kwargs)
    world3 = evolve_edges_fast_tick(world, **kwargs)

    assert world2 == world3
