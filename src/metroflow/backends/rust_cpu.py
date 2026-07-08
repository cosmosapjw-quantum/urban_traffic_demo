from __future__ import annotations

from collections.abc import Sequence
from types import ModuleType

import numpy as np

RUST_EDGE_BACKEND_UNAVAILABLE = (
    "Rust CPU edge backend unavailable. Build it with: "
    ".venv/bin/python -m maturin develop --manifest-path crates/metroflow-rust/Cargo.toml"
)
RUST_FLOW_BACKEND_UNAVAILABLE = (
    "Rust CPU flow backend unavailable. Build it with: "
    ".venv/bin/python -m maturin develop --manifest-path crates/metroflow-rust/Cargo.toml"
)


def _load_rust_extension(unavailable_message: str) -> ModuleType:
    try:
        import _metroflow_rust
    except ImportError as exc:
        raise RuntimeError(unavailable_message) from exc
    return _metroflow_rust


def rust_edge_backend_available() -> bool:
    try:
        _load_rust_extension(RUST_EDGE_BACKEND_UNAVAILABLE)
    except RuntimeError:
        return False
    return True


def rust_flow_backend_available() -> bool:
    try:
        rust_extension = _load_rust_extension(RUST_FLOW_BACKEND_UNAVAILABLE)
    except RuntimeError:
        return False
    return hasattr(rust_extension, "compute_baseline_flow_arrays_batch")


def _as_f64_list(values: Sequence[float], name: str) -> list[float]:
    try:
        array = np.ascontiguousarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Rust CPU edge backend failed: {name} must be numeric.") from exc
    if array.ndim != 1:
        raise RuntimeError(f"Rust CPU edge backend failed: {name} must be one-dimensional.")
    return array.tolist()


def _as_f32_list(values: Sequence[float], name: str) -> list[float]:
    try:
        array = np.ascontiguousarray(values, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Rust CPU flow backend failed: {name} must be numeric.") from exc
    if array.ndim != 1:
        raise RuntimeError(f"Rust CPU flow backend failed: {name} must be one-dimensional.")
    return array.tolist()


def _as_i32_list(values: Sequence[int], name: str) -> list[int]:
    try:
        array = np.ascontiguousarray(values, dtype=np.int32)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Rust CPU flow backend failed: {name} must be integer.") from exc
    if array.ndim != 1:
        raise RuntimeError(f"Rust CPU flow backend failed: {name} must be one-dimensional.")
    return array.tolist()


def _as_bool_list(values: Sequence[bool], name: str) -> list[bool]:
    try:
        array = np.ascontiguousarray(values, dtype=np.bool_)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Rust CPU flow backend failed: {name} must be boolean.") from exc
    if array.ndim != 1:
        raise RuntimeError(f"Rust CPU flow backend failed: {name} must be one-dimensional.")
    return array.tolist()


def evolve_edges_fast_tick_rust(
    queue: Sequence[float],
    stock: Sequence[float],
    inflow: Sequence[float],
    outflow: Sequence[float],
    free_flow: Sequence[float],
    capacity: Sequence[float],
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    rust_extension = _load_rust_extension(RUST_EDGE_BACKEND_UNAVAILABLE)
    try:
        next_queue, next_stock, next_travel_time = rust_extension.evolve_edges_batch(
            _as_f64_list(queue, "queue"),
            _as_f64_list(stock, "stock"),
            _as_f64_list(inflow, "inflow"),
            _as_f64_list(outflow, "outflow"),
            _as_f64_list(free_flow, "free_flow"),
            _as_f64_list(capacity, "capacity"),
        )
    except ValueError as exc:
        raise RuntimeError(f"Rust CPU edge backend failed: {exc}") from exc

    return (
        tuple(float(value) for value in next_queue),
        tuple(float(value) for value in next_stock),
        tuple(float(value) for value in next_travel_time),
    )


def compute_baseline_flow_arrays_rust(
    *,
    queue_vehicles: Sequence[float],
    effective_capacity_vehicles: Sequence[float],
    turn_from_link_index: Sequence[int],
    turn_to_link_index: Sequence[int],
    turn_demand: Sequence[float],
    signal_phase_timer: Sequence[int],
    base_travel_time_cost: Sequence[float],
    turn_priority: Sequence[float],
    turn_is_forbidden: Sequence[bool],
) -> dict[str, np.ndarray]:
    rust_extension = _load_rust_extension(RUST_FLOW_BACKEND_UNAVAILABLE)
    try:
        (
            turn_demand_next,
            turn_supply_next,
            turn_flow_next,
            inflow_vehicles_next,
            outflow_vehicles_next,
            queue_vehicles_next,
            travel_time_cost_next,
            capacity_violation_flags_next,
            signal_phase_timer_next,
        ) = rust_extension.compute_baseline_flow_arrays_batch(
            _as_f32_list(queue_vehicles, "queue_vehicles"),
            _as_f32_list(effective_capacity_vehicles, "effective_capacity_vehicles"),
            _as_i32_list(turn_from_link_index, "turn_from_link_index"),
            _as_i32_list(turn_to_link_index, "turn_to_link_index"),
            _as_f32_list(turn_demand, "turn_demand"),
            _as_i32_list(signal_phase_timer, "signal_phase_timer"),
            _as_f32_list(base_travel_time_cost, "base_travel_time_cost"),
            _as_f32_list(turn_priority, "turn_priority"),
            _as_bool_list(turn_is_forbidden, "turn_is_forbidden"),
        )
    except AttributeError as exc:
        raise RuntimeError(RUST_FLOW_BACKEND_UNAVAILABLE) from exc
    except ValueError as exc:
        raise RuntimeError(f"Rust CPU flow backend failed: {exc}") from exc

    return {
        "turn_demand_next": np.asarray(turn_demand_next, dtype=np.float32),
        "turn_supply_next": np.asarray(turn_supply_next, dtype=np.float32),
        "turn_flow_next": np.asarray(turn_flow_next, dtype=np.float32),
        "inflow_vehicles_next": np.asarray(inflow_vehicles_next, dtype=np.float32),
        "outflow_vehicles_next": np.asarray(outflow_vehicles_next, dtype=np.float32),
        "queue_vehicles_next": np.asarray(queue_vehicles_next, dtype=np.float32),
        "travel_time_cost_next": np.asarray(travel_time_cost_next, dtype=np.float32),
        "capacity_violation_flags_next": np.asarray(capacity_violation_flags_next, dtype=np.bool_),
        "signal_phase_timer_next": np.asarray(signal_phase_timer_next, dtype=np.int32),
    }
