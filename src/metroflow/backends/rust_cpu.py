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
RUST_ROUTING_BACKEND_UNAVAILABLE = (
    "Rust CPU routing backend unavailable. Build it with: "
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


def rust_routing_backend_available() -> bool:
    try:
        rust_extension = _load_rust_extension(RUST_ROUTING_BACKEND_UNAVAILABLE)
    except RuntimeError:
        return False
    return (
        hasattr(rust_extension, "compute_dynamic_potential_node_costs")
        and hasattr(rust_extension, "compute_greedy_route_candidate")
        and hasattr(rust_extension, "compute_next_link_action_costs")
        and hasattr(rust_extension, "compute_ranked_route_candidates")
        and hasattr(rust_extension, "compute_route_candidate_metadata")
        and hasattr(rust_extension, "select_route_candidate_index")
    )


def rust_reroute_backend_available() -> bool:
    try:
        rust_extension = _load_rust_extension(RUST_ROUTING_BACKEND_UNAVAILABLE)
    except RuntimeError:
        return False
    return hasattr(rust_extension, "compute_reroute_decision_batch")


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


def _as_f32_routing_list(values: Sequence[float], name: str) -> list[float]:
    try:
        array = np.ascontiguousarray(values, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Rust CPU routing backend failed: {name} must be numeric.") from exc
    if array.ndim != 1:
        raise RuntimeError(f"Rust CPU routing backend failed: {name} must be one-dimensional.")
    return array.tolist()


def _as_i32_routing_list(values: Sequence[int], name: str) -> list[int]:
    try:
        array = np.ascontiguousarray(values, dtype=np.int32)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Rust CPU routing backend failed: {name} must be integer.") from exc
    if array.ndim != 1:
        raise RuntimeError(f"Rust CPU routing backend failed: {name} must be one-dimensional.")
    return array.tolist()


def _as_bool_routing_list(values: Sequence[bool], name: str) -> list[bool]:
    try:
        array = np.ascontiguousarray(values, dtype=np.bool_)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Rust CPU routing backend failed: {name} must be boolean.") from exc
    if array.ndim != 1:
        raise RuntimeError(f"Rust CPU routing backend failed: {name} must be one-dimensional.")
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


def compute_dynamic_potential_node_costs_rust(
    *,
    node_count: int,
    incoming_indptr: Sequence[int],
    incoming_link_indices: Sequence[int],
    link_src_node_index: Sequence[int],
    link_travel_time_cost: Sequence[float],
    blocked_link_mask: Sequence[bool],
    destination_node_index: int,
) -> np.ndarray:
    rust_extension = _load_rust_extension(RUST_ROUTING_BACKEND_UNAVAILABLE)
    try:
        node_cost_to_go = rust_extension.compute_dynamic_potential_node_costs(
            int(node_count),
            _as_i32_routing_list(incoming_indptr, "incoming_indptr"),
            _as_i32_routing_list(incoming_link_indices, "incoming_link_indices"),
            _as_i32_routing_list(link_src_node_index, "link_src_node_index"),
            _as_f32_routing_list(link_travel_time_cost, "link_travel_time_cost"),
            _as_bool_routing_list(blocked_link_mask, "blocked_link_mask"),
            int(destination_node_index),
        )
    except AttributeError as exc:
        raise RuntimeError(RUST_ROUTING_BACKEND_UNAVAILABLE) from exc
    except ValueError as exc:
        raise RuntimeError(f"Rust CPU routing backend failed: {exc}") from exc

    return np.asarray(node_cost_to_go, dtype=np.float32)


def compute_greedy_route_candidate_rust(
    *,
    node_count: int,
    link_ids: Sequence[int],
    link_dst_node_index: Sequence[int],
    outgoing_indptr: Sequence[int],
    outgoing_link_indices: Sequence[int],
    turn_from_link_index: Sequence[int],
    turn_to_link_index: Sequence[int],
    turn_is_forbidden: Sequence[bool],
    node_cost_to_go: Sequence[float],
    link_travel_time_cost: Sequence[float],
    blocked_link_mask: Sequence[bool],
    origin_node_index: int,
    destination_node_index: int,
    incoming_link_index: int,
    max_hops: int,
) -> tuple[int, ...]:
    rust_extension = _load_rust_extension(RUST_ROUTING_BACKEND_UNAVAILABLE)
    try:
        path = rust_extension.compute_greedy_route_candidate(
            int(node_count),
            _as_i32_routing_list(link_ids, "link_ids"),
            _as_i32_routing_list(link_dst_node_index, "link_dst_node_index"),
            _as_i32_routing_list(outgoing_indptr, "outgoing_indptr"),
            _as_i32_routing_list(outgoing_link_indices, "outgoing_link_indices"),
            _as_i32_routing_list(turn_from_link_index, "turn_from_link_index"),
            _as_i32_routing_list(turn_to_link_index, "turn_to_link_index"),
            _as_bool_routing_list(turn_is_forbidden, "turn_is_forbidden"),
            _as_f32_routing_list(node_cost_to_go, "node_cost_to_go"),
            _as_f32_routing_list(link_travel_time_cost, "link_travel_time_cost"),
            _as_bool_routing_list(blocked_link_mask, "blocked_link_mask"),
            int(origin_node_index),
            int(destination_node_index),
            int(incoming_link_index),
            int(max_hops),
        )
    except AttributeError as exc:
        raise RuntimeError(RUST_ROUTING_BACKEND_UNAVAILABLE) from exc
    except ValueError as exc:
        raise RuntimeError(f"Rust CPU routing backend failed: {exc}") from exc

    return tuple(int(link_id) for link_id in path)


def compute_ranked_route_candidates_rust(
    *,
    node_count: int,
    link_ids: Sequence[int],
    link_dst_node_index: Sequence[int],
    outgoing_indptr: Sequence[int],
    outgoing_link_indices: Sequence[int],
    turn_from_link_index: Sequence[int],
    turn_to_link_index: Sequence[int],
    turn_is_forbidden: Sequence[bool],
    node_cost_to_go: Sequence[float],
    link_travel_time_cost: Sequence[float],
    blocked_link_mask: Sequence[bool],
    origin_node_index: int,
    destination_node_index: int,
    incoming_link_index: int,
    max_hops: int,
    max_candidates: int,
) -> tuple[tuple[int, ...], ...]:
    rust_extension = _load_rust_extension(RUST_ROUTING_BACKEND_UNAVAILABLE)
    try:
        paths = rust_extension.compute_ranked_route_candidates(
            int(node_count),
            _as_i32_routing_list(link_ids, "link_ids"),
            _as_i32_routing_list(link_dst_node_index, "link_dst_node_index"),
            _as_i32_routing_list(outgoing_indptr, "outgoing_indptr"),
            _as_i32_routing_list(outgoing_link_indices, "outgoing_link_indices"),
            _as_i32_routing_list(turn_from_link_index, "turn_from_link_index"),
            _as_i32_routing_list(turn_to_link_index, "turn_to_link_index"),
            _as_bool_routing_list(turn_is_forbidden, "turn_is_forbidden"),
            _as_f32_routing_list(node_cost_to_go, "node_cost_to_go"),
            _as_f32_routing_list(link_travel_time_cost, "link_travel_time_cost"),
            _as_bool_routing_list(blocked_link_mask, "blocked_link_mask"),
            int(origin_node_index),
            int(destination_node_index),
            int(incoming_link_index),
            int(max_hops),
            int(max_candidates),
        )
    except AttributeError as exc:
        raise RuntimeError(RUST_ROUTING_BACKEND_UNAVAILABLE) from exc
    except ValueError as exc:
        raise RuntimeError(f"Rust CPU routing backend failed: {exc}") from exc

    return tuple(tuple(int(link_id) for link_id in path) for path in paths)


def compute_route_candidate_metadata_rust(
    *,
    link_ids: Sequence[int],
    link_length_m: Sequence[float],
    link_travel_time_cost: Sequence[float],
    candidate_paths: Sequence[Sequence[int]],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    rust_extension = _load_rust_extension(RUST_ROUTING_BACKEND_UNAVAILABLE)
    try:
        costs, path_size_factors = rust_extension.compute_route_candidate_metadata(
            _as_i32_routing_list(link_ids, "link_ids"),
            _as_f32_routing_list(link_length_m, "link_length_m"),
            _as_f32_routing_list(link_travel_time_cost, "link_travel_time_cost"),
            [
                _as_i32_routing_list(path, "candidate_path")
                for path in candidate_paths
            ],
        )
    except AttributeError as exc:
        raise RuntimeError(RUST_ROUTING_BACKEND_UNAVAILABLE) from exc
    except ValueError as exc:
        raise RuntimeError(f"Rust CPU routing backend failed: {exc}") from exc

    return (
        tuple(float(value) for value in costs),
        tuple(float(value) for value in path_size_factors),
    )


def compute_next_link_action_costs_rust(
    *,
    candidate_link_indices: Sequence[int],
    link_dst_node_index: Sequence[int],
    node_cost_to_go: Sequence[float],
    link_travel_time_cost: Sequence[float],
    blocked_link_mask: Sequence[bool],
) -> np.ndarray:
    rust_extension = _load_rust_extension(RUST_ROUTING_BACKEND_UNAVAILABLE)
    try:
        costs = rust_extension.compute_next_link_action_costs(
            _as_i32_routing_list(candidate_link_indices, "candidate_link_indices"),
            _as_i32_routing_list(link_dst_node_index, "link_dst_node_index"),
            _as_f32_routing_list(node_cost_to_go, "node_cost_to_go"),
            _as_f32_routing_list(link_travel_time_cost, "link_travel_time_cost"),
            _as_bool_routing_list(blocked_link_mask, "blocked_link_mask"),
        )
    except AttributeError as exc:
        raise RuntimeError(RUST_ROUTING_BACKEND_UNAVAILABLE) from exc
    except ValueError as exc:
        raise RuntimeError(f"Rust CPU routing backend failed: {exc}") from exc

    return np.asarray(costs, dtype=np.float32)


def select_route_candidate_index_rust(
    *,
    candidate_ids: Sequence[int],
    candidate_paths: Sequence[Sequence[int]],
    candidate_path_costs: Sequence[float],
    candidate_path_size_factors: Sequence[float],
    path_size_gamma: float,
) -> tuple[int, float]:
    rust_extension = _load_rust_extension(RUST_ROUTING_BACKEND_UNAVAILABLE)
    try:
        selected_index, utility = rust_extension.select_route_candidate_index(
            _as_i32_routing_list(candidate_ids, "candidate_ids"),
            [
                _as_i32_routing_list(path, "candidate_path")
                for path in candidate_paths
            ],
            _as_f32_routing_list(candidate_path_costs, "candidate_path_costs"),
            _as_f32_routing_list(
                candidate_path_size_factors,
                "candidate_path_size_factors",
            ),
            float(path_size_gamma),
        )
    except AttributeError as exc:
        raise RuntimeError(RUST_ROUTING_BACKEND_UNAVAILABLE) from exc
    except ValueError as exc:
        raise RuntimeError(f"Rust CPU routing backend failed: {exc}") from exc

    return int(selected_index), float(utility)


def compute_reroute_decision_rust(
    *,
    reroute_willingness,
    delay_sensitivity,
    exploration_bias,
    persistence_bias,
    improvement_ratio,
) -> tuple[np.ndarray, np.ndarray]:
    rust_extension = _load_rust_extension(RUST_ROUTING_BACKEND_UNAVAILABLE)
    try:
        broadcast = np.broadcast_arrays(
            np.asarray(reroute_willingness, dtype=np.float32),
            np.asarray(delay_sensitivity, dtype=np.float32),
            np.asarray(exploration_bias, dtype=np.float32),
            np.asarray(persistence_bias, dtype=np.float32),
            np.asarray(improvement_ratio, dtype=np.float32),
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Rust CPU reroute backend failed: inputs must broadcast.") from exc

    shape = broadcast[0].shape
    try:
        should, score = rust_extension.compute_reroute_decision_batch(
            np.ascontiguousarray(broadcast[0], dtype=np.float32).ravel().tolist(),
            np.ascontiguousarray(broadcast[1], dtype=np.float32).ravel().tolist(),
            np.ascontiguousarray(broadcast[2], dtype=np.float32).ravel().tolist(),
            np.ascontiguousarray(broadcast[3], dtype=np.float32).ravel().tolist(),
            np.ascontiguousarray(broadcast[4], dtype=np.float32).ravel().tolist(),
        )
    except AttributeError as exc:
        raise RuntimeError(RUST_ROUTING_BACKEND_UNAVAILABLE) from exc
    except ValueError as exc:
        raise RuntimeError(f"Rust CPU reroute backend failed: {exc}") from exc

    return (
        np.asarray(should, dtype=np.bool_).reshape(shape),
        np.asarray(score, dtype=np.float32).reshape(shape),
    )
