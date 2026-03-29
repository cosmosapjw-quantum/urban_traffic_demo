from dataclasses import replace

from metroflow.core.state import GraphState, TrafficState, make_empty_world_state
from metroflow.traffic.meso import evolve_edges_fast_tick


def make_materialized_graph(num_edges: int) -> GraphState:
    return GraphState(
        num_nodes=max(num_edges + 1, 0),
        num_edges=num_edges,
        edge_src=tuple(range(num_edges)),
        edge_dst=tuple(range(1, num_edges + 1)),
        edge_class=("road",) * num_edges,
    )


def test_evolve_edges_fast_tick_clips_outflow_to_available_mass():
    world = replace(
        make_empty_world_state(),
        graph=make_materialized_graph(1),
        traffic=TrafficState(
            step=4,
            edge_queue=(1.0,),
            edge_stock=(1.0,),
            edge_travel_time=(3.0,),
        ),
    )

    world2 = evolve_edges_fast_tick(
        world,
        edge_inflow_veh_per_tick=(0.0,),
        edge_outflow_veh_per_tick=(10.0,),
        edge_free_flow_time_ticks=(2.0,),
        edge_capacity_veh_per_tick=(1.0,),
    )

    assert world2.traffic.step == 5
    assert world2.traffic.edge_stock == (0.0,)
    assert world2.traffic.edge_queue == (0.0,)
    assert world2.traffic.edge_travel_time == (2.0,)


def test_evolve_edges_fast_tick_keeps_blocked_edge_zero_discharge_and_finite_travel_time():
    world = replace(
        make_empty_world_state(),
        graph=make_materialized_graph(1),
        traffic=TrafficState(
            step=0,
            edge_queue=(1.0,),
            edge_stock=(2.0,),
            edge_travel_time=(1.0,),
        ),
    )

    world2 = evolve_edges_fast_tick(
        world,
        edge_inflow_veh_per_tick=(1.0,),
        edge_outflow_veh_per_tick=(2.0,),
        edge_free_flow_time_ticks=(3.0,),
        edge_capacity_veh_per_tick=(0.0,),
    )

    assert world2.traffic.step == 1
    assert world2.traffic.edge_stock == (3.0,)
    assert world2.traffic.edge_queue == (2.0,)
    assert world2.traffic.edge_travel_time[0] > 1_000.0


def test_evolve_edges_fast_tick_zero_edge_world_only_advances_step():
    world = replace(
        make_empty_world_state(seed=99),
        graph=GraphState(num_edges=0),
        traffic=TrafficState(step=7),
    )

    world2 = evolve_edges_fast_tick(world)

    assert world2.traffic.step == 8
    assert world2.graph == world.graph
    assert world2.traffic.edge_queue == ()
    assert world2.traffic.edge_stock == ()
    assert world2.traffic.edge_travel_time == ()


def test_evolve_edges_fast_tick_is_deterministic_under_conservation_stress():
    world = replace(
        make_empty_world_state(seed=12),
        graph=make_materialized_graph(1),
        traffic=TrafficState(
            step=2,
            edge_queue=(0.5,),
            edge_stock=(1.0,),
            edge_travel_time=(4.0,),
        ),
    )
    kwargs = {
        "edge_inflow_veh_per_tick": (0.25,),
        "edge_outflow_veh_per_tick": (3.0,),
        "edge_free_flow_time_ticks": (6.0,),
        "edge_capacity_veh_per_tick": (0.5,),
    }

    world2 = evolve_edges_fast_tick(world, **kwargs)
    world3 = evolve_edges_fast_tick(world, **kwargs)

    assert world2 == world3
