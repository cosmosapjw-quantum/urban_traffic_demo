from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Literal, Optional, Tuple

from metroflow.backends.rust_cpu import evolve_edges_fast_tick_rust
from metroflow.core.state import WorldState

EdgeEvolutionBackend = Literal["baseline", "rust_cpu", "jax", "auto"]
EDGE_EVOLUTION_BACKENDS = ("baseline", "rust_cpu", "jax", "auto")


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


def _validate_edge_backend(edge_backend: str) -> None:
    if edge_backend not in EDGE_EVOLUTION_BACKENDS:
        raise ValueError("edge_backend must be one of: baseline, rust_cpu, jax, auto.")


def _validate_edge_batch_for_accelerator(
    queue: Tuple[float, ...],
    stock: Tuple[float, ...],
    inflow: Tuple[float, ...],
    outflow: Tuple[float, ...],
    free_flow: Tuple[float, ...],
    capacity: Tuple[float, ...],
) -> None:
    if any(value < 0.0 for value in queue):
        raise ValueError("queue must be non-negative")
    if any(value < 0.0 for value in stock):
        raise ValueError("stock must be non-negative")
    if any(q > s for q, s in zip(queue, stock)):
        raise ValueError("queue must not exceed stock")
    if any(value < 0.0 for value in inflow):
        raise ValueError("inflow must be non-negative")
    if any(value < 0.0 for value in outflow):
        raise ValueError("outflow must be non-negative")
    if any(value < 0.0 for value in free_flow):
        raise ValueError("free_flow_time must be non-negative")
    if any(value < 0.0 for value in capacity):
        raise ValueError("capacity must be non-negative")


@lru_cache(maxsize=1)
def _compiled_jax_edge_kernel():
    import jax
    import jax.numpy as jnp

    jax.config.update("jax_enable_x64", True)

    def kernel(queue, stock, inflow, outflow, free_flow, capacity):
        available_mass = stock + inflow
        feasible_outflow = jnp.where(
            capacity <= 0.0,
            0.0,
            jnp.minimum(jnp.minimum(outflow, available_mass), capacity),
        )
        next_stock = available_mass - feasible_outflow
        queued_mass = queue + jnp.maximum(inflow - feasible_outflow, 0.0)
        next_queue = jnp.minimum(jnp.maximum(queued_mass, 0.0), next_stock)
        next_travel_time = free_flow + next_queue / jnp.maximum(capacity, 1e-6)
        return next_queue, next_stock, next_travel_time

    return jax.jit(kernel)


def _evolve_edges_fast_tick_jax(
    queue: Tuple[float, ...],
    stock: Tuple[float, ...],
    inflow: Tuple[float, ...],
    outflow: Tuple[float, ...],
    free_flow: Tuple[float, ...],
    capacity: Tuple[float, ...],
) -> tuple[Tuple[float, ...], Tuple[float, ...], Tuple[float, ...]]:
    _validate_edge_batch_for_accelerator(queue, stock, inflow, outflow, free_flow, capacity)
    try:
        import jax.numpy as jnp

        kernel = _compiled_jax_edge_kernel()
        next_queue, next_stock, next_travel_time = kernel(
            jnp.asarray(queue),
            jnp.asarray(stock),
            jnp.asarray(inflow),
            jnp.asarray(outflow),
            jnp.asarray(free_flow),
            jnp.asarray(capacity),
        )
        return (
            tuple(float(value) for value in next_queue.tolist()),
            tuple(float(value) for value in next_stock.tolist()),
            tuple(float(value) for value in next_travel_time.tolist()),
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "JAX edge backend unavailable. Install metroflow[jax] to use edge_backend='jax'."
        ) from exc
    except Exception as exc:
        raise RuntimeError("JAX edge backend failed.") from exc


def _evolve_edges_fast_tick_rust(
    queue: Tuple[float, ...],
    stock: Tuple[float, ...],
    inflow: Tuple[float, ...],
    outflow: Tuple[float, ...],
    free_flow: Tuple[float, ...],
    capacity: Tuple[float, ...],
) -> tuple[Tuple[float, ...], Tuple[float, ...], Tuple[float, ...]]:
    _validate_edge_batch_for_accelerator(queue, stock, inflow, outflow, free_flow, capacity)
    return evolve_edges_fast_tick_rust(queue, stock, inflow, outflow, free_flow, capacity)


def evolve_edges_fast_tick(
    world: WorldState,
    edge_inflow_veh_per_tick: Optional[Tuple[float, ...]] = None,
    edge_outflow_veh_per_tick: Optional[Tuple[float, ...]] = None,
    edge_free_flow_time_ticks: Optional[Tuple[float, ...]] = None,
    edge_capacity_veh_per_tick: Optional[Tuple[float, ...]] = None,
    edge_backend: EdgeEvolutionBackend = "baseline",
) -> WorldState:
    _validate_edge_backend(edge_backend)
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

    accelerated = None
    if edge_backend in {"rust_cpu", "auto"}:
        try:
            accelerated = _evolve_edges_fast_tick_rust(
                world.traffic.edge_queue,
                world.traffic.edge_stock,
                inflow,
                outflow,
                free_flow,
                capacity,
            )
        except RuntimeError:
            if edge_backend == "rust_cpu":
                raise

    if accelerated is None and edge_backend in {"jax", "auto"}:
        try:
            accelerated = _evolve_edges_fast_tick_jax(
                world.traffic.edge_queue,
                world.traffic.edge_stock,
                inflow,
                outflow,
                free_flow,
                capacity,
            )
        except RuntimeError:
            if edge_backend == "jax":
                raise

    if accelerated is None:
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
        next_queue_values = tuple(next_queue)
        next_stock_values = tuple(next_stock)
        next_travel_time_values = tuple(next_travel_time)
    else:
        next_queue_values, next_stock_values, next_travel_time_values = accelerated

    return replace(
        world,
        traffic=replace(
            world.traffic,
            step=next_step,
            edge_queue=next_queue_values,
            edge_stock=next_stock_values,
            edge_travel_time=next_travel_time_values,
        ),
    )


def project_feasible_movements(
    sending: Tuple[float, ...],
    receiving: Tuple[float, ...],
    movement_cap: Tuple[float, ...],
) -> Tuple[float, ...]:
    if not (len(sending) == len(receiving) == len(movement_cap)):
        raise ValueError("movement arrays must have matching lengths.")
    n = len(sending)
    out = []
    for i in range(n):
        out.append(max(min(sending[i], receiving[i], movement_cap[i]), 0.0))
    return tuple(out)
