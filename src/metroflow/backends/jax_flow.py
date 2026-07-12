"""Lazy optional JAX kernels for dense-flow benchmark experiments."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter_ns
from typing import Any, Literal, Mapping

import numpy as np

__all__ = [
    "JaxDenseFlowResult",
    "JaxFlowExecutionMode",
    "JaxFlowUnavailableError",
    "jax_flow_backend_available",
    "run_dense_flow_jax",
    "warm_up_jax_flow_runtime",
]

JaxFlowExecutionMode = Literal["host_step_loop", "device_chunk"]


class JaxFlowUnavailableError(RuntimeError):
    """Raised when the optional JAX/device requirement is unavailable."""


@dataclass(frozen=True, slots=True)
class JaxDenseFlowResult:
    output: Mapping[str, np.ndarray]
    execution_mode: str
    num_steps: int
    input_copy_wall_ns: int
    first_call_wall_ns: int
    steady_state_wall_ns: int
    output_copy_wall_ns: int
    device_platform: str
    device_kind: str
    jax_version: str


def jax_flow_backend_available(*, require_gpu: bool = False) -> bool:
    """Return whether optional JAX, and optionally a GPU device, is available."""

    try:
        import jax
    except ImportError:
        return False
    try:
        devices = tuple(jax.devices())
    except Exception:
        return False
    return bool(
        devices
        and (
            not require_gpu
            or any(str(getattr(device, "platform", "")) == "gpu" for device in devices)
        )
    )


def warm_up_jax_flow_runtime(*, require_gpu: bool = False) -> tuple[int, str, str, str]:
    """Initialize optional JAX/device runtime outside per-shape kernel timings."""

    start_ns = perf_counter_ns()
    try:
        import jax
        import jax.numpy as jnp
    except ImportError as exc:
        raise JaxFlowUnavailableError(
            "JAX dense flow backend unavailable. Install metroflow[jax]."
        ) from exc
    devices = tuple(jax.devices())
    if require_gpu:
        devices = tuple(
            device
            for device in devices
            if str(getattr(device, "platform", "")) == "gpu"
        )
    if not devices:
        requirement = "GPU " if require_gpu else ""
        raise JaxFlowUnavailableError(f"JAX {requirement}device unavailable")
    device = devices[0]
    value = jax.device_put(np.zeros((1,), dtype=np.float32), device=device)
    value = jax.jit(lambda item: item + jnp.asarray(1.0, dtype=jnp.float32))(value)
    jax.block_until_ready(value)
    return (
        max(0, perf_counter_ns() - start_ns),
        str(getattr(device, "platform", "unknown")),
        str(getattr(device, "device_kind", device)),
        str(getattr(jax, "__version__", "unknown")),
    )


def run_dense_flow_jax(
    *,
    queue_vehicles: Any,
    effective_capacity_vehicles: Any,
    base_travel_time_cost: Any,
    turn_from_link_index: Any,
    turn_to_link_index: Any,
    turn_demand: Any,
    turn_priority: Any,
    turn_is_forbidden: Any,
    signal_phase_timer: Any,
    num_steps: int,
    execution_mode: JaxFlowExecutionMode = "host_step_loop",
    require_gpu: bool = False,
) -> JaxDenseFlowResult:
    """Execute the dense-flow equations without changing runtime backend authority."""

    arrays = _normalize_inputs(
        queue_vehicles=queue_vehicles,
        effective_capacity_vehicles=effective_capacity_vehicles,
        base_travel_time_cost=base_travel_time_cost,
        turn_from_link_index=turn_from_link_index,
        turn_to_link_index=turn_to_link_index,
        turn_demand=turn_demand,
        turn_priority=turn_priority,
        turn_is_forbidden=turn_is_forbidden,
        signal_phase_timer=signal_phase_timer,
    )
    steps = int(num_steps)
    if steps < 1:
        raise ValueError("num_steps must be >= 1")
    if execution_mode not in {"host_step_loop", "device_chunk"}:
        raise ValueError("execution_mode must be one of: host_step_loop, device_chunk")

    try:
        import jax
        import jax.numpy as jnp
    except ImportError as exc:
        raise JaxFlowUnavailableError(
            "JAX dense flow backend unavailable. Install metroflow[jax]."
        ) from exc

    try:
        devices = tuple(jax.devices())
        if require_gpu:
            devices = tuple(
                device
                for device in devices
                if str(getattr(device, "platform", "")) == "gpu"
            )
        if not devices:
            requirement = "GPU " if require_gpu else ""
            raise JaxFlowUnavailableError(f"JAX {requirement}device unavailable")
        device = devices[0]

        input_start_ns = perf_counter_ns()
        device_arrays = {
            key: jax.device_put(value, device=device)
            for key, value in arrays.items()
        }
        jax.block_until_ready(tuple(device_arrays.values()))
        input_copy_ns = max(0, perf_counter_ns() - input_start_ns)
        step = _build_step_function(jnp)

        if execution_mode == "host_step_loop":
            result, first_ns, steady_ns = _run_host_step_loop(
                jax,
                step=step,
                device_arrays=device_arrays,
                num_steps=steps,
            )
        else:
            result, first_ns, steady_ns = _run_device_chunk(
                jax,
                jnp,
                step=step,
                device_arrays=device_arrays,
                num_steps=steps,
            )

        output_start_ns = perf_counter_ns()
        output = _output_to_numpy(result)
        output_copy_ns = max(0, perf_counter_ns() - output_start_ns)
        return JaxDenseFlowResult(
            output=output,
            execution_mode=str(execution_mode),
            num_steps=steps,
            input_copy_wall_ns=input_copy_ns,
            first_call_wall_ns=first_ns,
            steady_state_wall_ns=steady_ns,
            output_copy_wall_ns=output_copy_ns,
            device_platform=str(getattr(device, "platform", "unknown")),
            device_kind=str(getattr(device, "device_kind", device)),
            jax_version=str(getattr(jax, "__version__", "unknown")),
        )
    except JaxFlowUnavailableError:
        raise
    except Exception as exc:
        raise RuntimeError(f"JAX dense flow backend failed: {exc}") from exc


def _normalize_inputs(**raw: Any) -> dict[str, np.ndarray]:
    arrays = {
        "queue_vehicles": _array(raw["queue_vehicles"], np.float32),
        "effective_capacity_vehicles": _array(
            raw["effective_capacity_vehicles"],
            np.float32,
        ),
        "base_travel_time_cost": _array(raw["base_travel_time_cost"], np.float32),
        "turn_from_link_index": _array(raw["turn_from_link_index"], np.int32),
        "turn_to_link_index": _array(raw["turn_to_link_index"], np.int32),
        "turn_demand": _array(raw["turn_demand"], np.float32),
        "turn_priority": _array(raw["turn_priority"], np.float32),
        "turn_is_forbidden": _array(raw["turn_is_forbidden"], np.bool_),
        "signal_phase_timer": _array(raw["signal_phase_timer"], np.int32),
    }
    if any(array.ndim != 1 for array in arrays.values()):
        raise ValueError("JAX dense flow input arrays must be 1-D")
    link_count = int(arrays["queue_vehicles"].shape[0])
    if link_count < 1:
        raise ValueError("queue_vehicles must not be empty")
    for key in (
        "effective_capacity_vehicles",
        "base_travel_time_cost",
        "signal_phase_timer",
    ):
        if int(arrays[key].shape[0]) != link_count:
            raise ValueError(f"{key} length must match queue_vehicles")
    turn_count = int(arrays["turn_demand"].shape[0])
    for key in (
        "turn_from_link_index",
        "turn_to_link_index",
        "turn_priority",
        "turn_is_forbidden",
    ):
        if int(arrays[key].shape[0]) != turn_count:
            raise ValueError(f"{key} length must match turn_demand")
    for key in ("turn_from_link_index", "turn_to_link_index"):
        values = arrays[key]
        if values.size and (int(values.min()) < 0 or int(values.max()) >= link_count):
            raise ValueError(f"{key} contains an out-of-range link index")
    numeric_nonnegative = (
        "queue_vehicles",
        "effective_capacity_vehicles",
        "base_travel_time_cost",
        "turn_demand",
        "turn_priority",
    )
    if any(
        not np.all(np.isfinite(arrays[key])) or np.any(arrays[key] < 0.0)
        for key in numeric_nonnegative
    ):
        raise ValueError("JAX dense flow numeric inputs must be finite and non-negative")
    return arrays


def _array(value: Any, dtype: Any) -> np.ndarray:
    return np.ascontiguousarray(np.asarray(value, dtype=dtype))


def _build_step_function(jnp: Any):
    def step(
        queue_now,
        signal_timer_now,
        capacity,
        base_travel_time,
        from_index,
        to_index,
        demand,
        priority,
        forbidden,
    ):
        priority_weight = jnp.where(forbidden, 0.0, jnp.maximum(priority, 0.0))
        weighted_demand = jnp.where(demand > 0.0, demand * priority_weight, 0.0)
        weighted_by_from = jnp.zeros_like(queue_now).at[from_index].add(
            weighted_demand
        )
        weighted_by_to = jnp.zeros_like(queue_now).at[to_index].add(weighted_demand)
        from_den = weighted_by_from[from_index]
        to_den = weighted_by_to[to_index]
        from_share = jnp.where(from_den > 0.0, weighted_demand / from_den, 0.0)
        to_share = jnp.where(to_den > 0.0, weighted_demand / to_den, 0.0)
        from_available = jnp.minimum(queue_now, capacity)
        # Point-queue capacity is an admission rate, not finite link storage.
        receiving_supply = capacity
        turn_supply = jnp.minimum(
            from_available[from_index] * from_share,
            receiving_supply[to_index] * to_share,
        )
        turn_flow = jnp.where(forbidden, 0.0, jnp.minimum(demand, turn_supply))
        outflow = jnp.zeros_like(queue_now).at[from_index].add(turn_flow)
        inflow = jnp.zeros_like(queue_now).at[to_index].add(turn_flow)
        queue_next = jnp.maximum(0.0, queue_now - outflow + inflow)
        safe_base_travel_time = jnp.maximum(base_travel_time, 1e-3)
        safe_travel_capacity = jnp.maximum(capacity, 1e-3)
        travel_time = safe_base_travel_time + queue_next / safe_travel_capacity
        return (
            queue_next,
            inflow,
            outflow,
            travel_time,
            outflow > (capacity + 1e-6),
            demand,
            jnp.maximum(turn_supply, 0.0),
            jnp.maximum(turn_flow, 0.0),
            signal_timer_now + 1,
        )

    return step


def _run_host_step_loop(
    jax: Any,
    *,
    step: Any,
    device_arrays: Mapping[str, Any],
    num_steps: int,
) -> tuple[Any, int, int]:
    compiled_step = jax.jit(step)
    queue = device_arrays["queue_vehicles"]
    signal_timer = device_arrays["signal_phase_timer"]
    step_args = (
        device_arrays["effective_capacity_vehicles"],
        device_arrays["base_travel_time_cost"],
        device_arrays["turn_from_link_index"],
        device_arrays["turn_to_link_index"],
        device_arrays["turn_demand"],
        device_arrays["turn_priority"],
        device_arrays["turn_is_forbidden"],
    )
    first_start_ns = perf_counter_ns()
    result = compiled_step(queue, signal_timer, *step_args)
    jax.block_until_ready(result)
    first_ns = max(0, perf_counter_ns() - first_start_ns)
    queue = result[0]
    signal_timer = result[-1]
    steady_start_ns = perf_counter_ns()
    for _ in range(int(num_steps) - 1):
        result = compiled_step(queue, signal_timer, *step_args)
        queue = result[0]
        signal_timer = result[-1]
    jax.block_until_ready(result)
    steady_ns = max(0, perf_counter_ns() - steady_start_ns)
    return result, first_ns, steady_ns


def _run_device_chunk(
    jax: Any,
    jnp: Any,
    *,
    step: Any,
    device_arrays: Mapping[str, Any],
    num_steps: int,
) -> tuple[Any, int, int]:
    queue_initial = device_arrays["queue_vehicles"]
    timer_initial = device_arrays["signal_phase_timer"]

    def chunk(
        queue_start,
        timer_start,
        capacity,
        base_travel_time,
        from_index,
        to_index,
        demand_now,
        priority,
        forbidden,
    ):
        initial = (
            queue_start,
            timer_start,
            jnp.zeros_like(queue_start),
            jnp.zeros_like(queue_start),
            base_travel_time,
            jnp.zeros_like(queue_start, dtype=jnp.bool_),
            demand_now,
            jnp.zeros_like(demand_now),
            jnp.zeros_like(demand_now),
        )

        def body(_index, carry):
            result = step(
                carry[0],
                carry[1],
                capacity,
                base_travel_time,
                from_index,
                to_index,
                demand_now,
                priority,
                forbidden,
            )
            return (
                result[0],
                result[8],
                result[1],
                result[2],
                result[3],
                result[4],
                result[5],
                result[6],
                result[7],
            )

        final = jax.lax.fori_loop(0, int(num_steps), body, initial)
        return (
            final[0],
            final[2],
            final[3],
            final[4],
            final[5],
            final[6],
            final[7],
            final[8],
            final[1],
        )

    compiled_chunk = jax.jit(chunk)
    chunk_args = (
        queue_initial,
        timer_initial,
        device_arrays["effective_capacity_vehicles"],
        device_arrays["base_travel_time_cost"],
        device_arrays["turn_from_link_index"],
        device_arrays["turn_to_link_index"],
        device_arrays["turn_demand"],
        device_arrays["turn_priority"],
        device_arrays["turn_is_forbidden"],
    )
    first_start_ns = perf_counter_ns()
    first_result = compiled_chunk(*chunk_args)
    jax.block_until_ready(first_result)
    first_ns = max(0, perf_counter_ns() - first_start_ns)
    steady_start_ns = perf_counter_ns()
    result = compiled_chunk(*chunk_args)
    jax.block_until_ready(result)
    steady_ns = max(0, perf_counter_ns() - steady_start_ns)
    return result, first_ns, steady_ns


def _output_to_numpy(result: Any) -> dict[str, np.ndarray]:
    return {
        "queue_vehicles": np.asarray(result[0], dtype=np.float32),
        "inflow_vehicles": np.asarray(result[1], dtype=np.float32),
        "outflow_vehicles": np.asarray(result[2], dtype=np.float32),
        "travel_time_cost": np.asarray(result[3], dtype=np.float32),
        "capacity_violation_flags": np.asarray(result[4], dtype=np.bool_),
        "turn_demand": np.asarray(result[5], dtype=np.float32),
        "turn_supply": np.asarray(result[6], dtype=np.float32),
        "turn_flow": np.asarray(result[7], dtype=np.float32),
        "signal_phase_timer": np.asarray(result[8], dtype=np.int32),
    }
