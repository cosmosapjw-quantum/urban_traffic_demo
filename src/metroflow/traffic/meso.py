from dataclasses import dataclass
from typing import Tuple


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
    new_stock = max(stock + inflow - outflow, 0.0)
    new_queue = max(queue + max(inflow - outflow, 0.0), 0.0)
    tt = safe_travel_time(free_flow_time=free_flow_time, queue=new_queue, capacity=capacity)
    return EdgeDynamicState(queue=new_queue, stock=new_stock, travel_time=tt, capacity=capacity)


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
