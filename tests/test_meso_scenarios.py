from dataclasses import replace

from metroflow.core.state import GraphState, TrafficState, make_empty_world_state
from metroflow.traffic.meso import evolve_edges_fast_tick, project_feasible_movements


def make_materialized_graph(num_edges: int) -> GraphState:
    return GraphState(
        num_nodes=max(num_edges + 1, 0),
        num_edges=num_edges,
        edge_src=tuple(range(num_edges)),
        edge_dst=tuple(range(1, num_edges + 1)),
        edge_class=("road",) * num_edges,
    )


def test_bridge_bottleneck_constrains_outflow_conservatively():
    world = replace(
        make_empty_world_state(),
        graph=make_materialized_graph(1),
        traffic=TrafficState(edge_queue=(0.0,), edge_stock=(5.0,), edge_travel_time=(1.0,)),
    )

    next_world = evolve_edges_fast_tick(
        world,
        edge_inflow_veh_per_tick=(2.0,),
        edge_outflow_veh_per_tick=(4.0,),
        edge_free_flow_time_ticks=(3.0,),
        edge_capacity_veh_per_tick=(1.0,),
    )

    assert next_world.traffic.edge_stock == (6.0,)
    assert next_world.traffic.edge_queue == (1.0,)


def test_merge_projection_respects_shared_receiving_budget():
    movements = project_feasible_movements((3.0, 4.0), (2.0, 2.0), (5.0, 1.0))
    assert movements == (2.0, 1.0)


def test_bypass_path_can_avoid_blocked_edge_pressure():
    blocked = evolve_edges_fast_tick(
        replace(
            make_empty_world_state(),
            graph=make_materialized_graph(2),
            traffic=TrafficState(edge_queue=(0.0, 0.0), edge_stock=(2.0, 2.0), edge_travel_time=(1.0, 1.0)),
        ),
        edge_inflow_veh_per_tick=(2.0, 2.0),
        edge_outflow_veh_per_tick=(5.0, 1.0),
        edge_free_flow_time_ticks=(2.0, 2.0),
        edge_capacity_veh_per_tick=(0.0, 3.0),
    )

    assert blocked.traffic.edge_travel_time[0] != blocked.traffic.edge_travel_time[1]
    assert blocked.traffic.edge_travel_time[0] > blocked.traffic.edge_travel_time[1]
