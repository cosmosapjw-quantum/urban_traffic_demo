from dataclasses import dataclass, replace
from typing import Optional, Tuple

from metroflow.core.state import WorldState


@dataclass(frozen=True)
class EdgeDynamicState:
    queue: float
    stock: float
    travel_time: float
    capacity: float


def safe_travel_time(free_flow_time: float, queue: float, capacity: float, eps: float = 1e-6) -> float:
    if capacity < 0:
        raise ValueError("capacity must be non-negative")
    return free_flow_time + queue / max(capacity, eps)


def update_edge_state(
    queue: float,
    stock: float,
    inflow: float,
    outflow: float,
    free_flow_time: float,
    capacity: float,
) -> EdgeDynamicState:
    if queue < 0.0:
        raise ValueError("queue must be non-negative")
    if stock < 0.0:
        raise ValueError("stock must be non-negative")
    if queue > stock:
        raise ValueError("queue must not exceed stock")
    if inflow < 0.0:
        raise ValueError("inflow must be non-negative")
    if outflow < 0.0:
        raise ValueError("outflow must be non-negative")
    if free_flow_time < 0.0:
        raise ValueError("free_flow_time must be non-negative")

    available_mass = stock + inflow
    feasible_outflow = 0.0 if capacity <= 0.0 else min(outflow, available_mass, capacity)
    new_stock = available_mass - feasible_outflow
    queued_mass = queue + max(inflow - feasible_outflow, 0.0)
    new_queue = min(max(queued_mass, 0.0), new_stock)
    tt = safe_travel_time(free_flow_time=free_flow_time, queue=new_queue, capacity=capacity)
    return EdgeDynamicState(queue=new_queue, stock=new_stock, travel_time=tt, capacity=capacity)


def _normalize_edge_values(
    values: Optional[Tuple[float, ...]],
    num_edges: int,
    default: float,
    name: str,
) -> Tuple[float, ...]:
    if values is None:
        return (default,) * num_edges
    if len(values) != num_edges:
        raise ValueError(f"{name} length must match graph.num_edges.")
    return values


def evolve_edges_fast_tick(
    world: WorldState,
    edge_inflow_veh_per_tick: Optional[Tuple[float, ...]] = None,
    edge_outflow_veh_per_tick: Optional[Tuple[float, ...]] = None,
    edge_free_flow_time_ticks: Optional[Tuple[float, ...]] = None,
    edge_capacity_veh_per_tick: Optional[Tuple[float, ...]] = None,
) -> WorldState:
    num_edges = world.graph.num_edges
    next_step = world.traffic.step + 1

    if num_edges == 0:
        return replace(world, traffic=replace(world.traffic, step=next_step))

    if len(world.traffic.edge_queue) != num_edges:
        raise ValueError("edge_queue length must match graph.num_edges.")
    if len(world.traffic.edge_stock) != num_edges:
        raise ValueError("edge_stock length must match graph.num_edges.")
    if len(world.traffic.edge_travel_time) != num_edges:
        raise ValueError("edge_travel_time length must match graph.num_edges.")

    inflow = _normalize_edge_values(edge_inflow_veh_per_tick, num_edges, 0.0, "edge_inflow_veh_per_tick")
    outflow = _normalize_edge_values(edge_outflow_veh_per_tick, num_edges, 0.0, "edge_outflow_veh_per_tick")
    free_flow = _normalize_edge_values(edge_free_flow_time_ticks, num_edges, 1.0, "edge_free_flow_time_ticks")
    capacity = _normalize_edge_values(edge_capacity_veh_per_tick, num_edges, 1.0, "edge_capacity_veh_per_tick")

    next_queue = []
    next_stock = []
    next_travel_time = []
    for edge_idx in range(num_edges):
        edge_state = update_edge_state(
            queue=world.traffic.edge_queue[edge_idx],
            stock=world.traffic.edge_stock[edge_idx],
            inflow=inflow[edge_idx],
            outflow=outflow[edge_idx],
            free_flow_time=free_flow[edge_idx],
            capacity=capacity[edge_idx],
        )
        next_queue.append(edge_state.queue)
        next_stock.append(edge_state.stock)
        next_travel_time.append(edge_state.travel_time)

    return replace(
        world,
        traffic=replace(
            world.traffic,
            step=next_step,
            edge_queue=tuple(next_queue),
            edge_stock=tuple(next_stock),
            edge_travel_time=tuple(next_travel_time),
        ),
    )


def project_feasible_movements(
    sending: Tuple[float, ...],
    receiving: Tuple[float, ...],
    movement_cap: Tuple[float, ...],
) -> Tuple[float, ...]:
    n = min(len(sending), len(receiving), len(movement_cap))
    out = []
    for i in range(n):
        out.append(max(min(sending[i], receiving[i], movement_cap[i]), 0.0))
    return tuple(out)
