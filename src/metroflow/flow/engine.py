"""Baseline link-queue + node-model flow updates."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
from typing import Any, Literal

import numpy as np

from metroflow.backends.rust_cpu import compute_baseline_flow_arrays_rust
from metroflow.flow.state import LinkState, NodeState, validate_link_state, validate_node_state

__all__ = [
    "BaselineFlowUpdateResult",
    "FLOW_UPDATE_BACKENDS",
    "FlowUpdateBackend",
    "compute_baseline_flow_arrays",
    "compute_baseline_flow_arrays_core",
    "update_link_node_flow",
]

Array = np.ndarray
FlowUpdateBackend = Literal["baseline", "rust_cpu", "auto"]
FLOW_UPDATE_BACKENDS = ("baseline", "rust_cpu", "auto")
_FREE_FLOW_TRAVEL_TIME_KEY = "free_flow_travel_time_cost"


@dataclass(slots=True)
class BaselineFlowUpdateResult:
    """Container for updated flow state after one baseline allocation step."""

    link_state: LinkState
    node_state: NodeState


def update_link_node_flow(
    link_state: LinkState,
    node_state: NodeState,
    *,
    validate: bool = False,
    flow_backend: FlowUpdateBackend = "baseline",
    discrete_agent_authority: bool = False,
) -> BaselineFlowUpdateResult:
    """Apply a simplified node-turn allocation and link queue update.

    The baseline model treats `node_state.turn_demand` as the desired movement
    volume for the current tick, then allocates feasible `turn_flow` while
    respecting upstream effective capacity, downstream receiving supply, and
    optional turn metadata (`turn_base_priority`, `turn_is_forbidden`).
    """

    if validate:
        _validate_turn_index_ranges(node_state, link_state.link_count)

    if discrete_agent_authority and flow_backend == "rust_cpu":
        raise RuntimeError(
            "Rust CPU flow backend does not implement the per-turn discrete-agent "
            "authority contract"
        )
    resolved_flow_backend: FlowUpdateBackend = (
        "baseline" if discrete_agent_authority and flow_backend == "auto" else flow_backend
    )
    arrays = compute_baseline_flow_arrays(
        link_state=link_state,
        node_state=node_state,
        flow_backend=resolved_flow_backend,
    )
    next_link_metadata = dict(link_state.metadata)
    next_link_metadata[_FREE_FLOW_TRAVEL_TIME_KEY] = arrays["base_travel_time_cost"]
    next_node_metadata = dict(node_state.metadata)
    if discrete_agent_authority:
        arrays, authority_metadata = _apply_discrete_agent_flow_authority(
            arrays=arrays,
            link_state=link_state,
            node_state=node_state,
        )
        next_link_metadata.update(authority_metadata["link"])
        next_node_metadata.update(authority_metadata["node"])

    next_link_state = LinkState(
        queue_vehicles=arrays["queue_vehicles_next"],
        inflow_vehicles=arrays["inflow_vehicles_next"],
        outflow_vehicles=arrays["outflow_vehicles_next"],
        travel_time_cost=arrays["travel_time_cost_next"],
        capacity_veh_per_tick=link_state.capacity_veh_per_tick,
        incident_capacity_multiplier=link_state.incident_capacity_multiplier,
        capacity_violation_flags=arrays["capacity_violation_flags_next"],
        metadata=next_link_metadata,
    )
    next_node_state = NodeState(
        turn_from_link_index=node_state.turn_from_link_index,
        turn_to_link_index=node_state.turn_to_link_index,
        turn_demand=arrays["turn_demand_next"],
        turn_supply=arrays["turn_supply_next"],
        turn_flow=arrays["turn_flow_next"],
        signal_phase_index=node_state.signal_phase_index,
        signal_phase_timer=arrays["signal_phase_timer_next"],
        metadata=next_node_metadata,
    )

    if validate:
        link_issues = validate_link_state(next_link_state)
        node_issues = validate_node_state(next_node_state)
        if link_issues or node_issues:
            raise ValueError(
                "invalid flow update result: "
                + "; ".join((*link_issues, *node_issues))
            )

    return BaselineFlowUpdateResult(link_state=next_link_state, node_state=next_node_state)


def _apply_discrete_agent_flow_authority(
    *,
    arrays: dict[str, Array],
    link_state: LinkState,
    node_state: NodeState,
) -> tuple[dict[str, Array], dict[str, dict[str, Array]]]:
    """Convert fractional node allocations into deterministic vehicle tokens.

    The continuous node model remains the allocator, but the queue and active-agent
    runtime share one integer authority.  Fractional service and turn allocations are
    carried deterministically across ticks. Final-link sink demand participates in
    the same deficit scheduler as internal turns, so neither movement class can
    starve the other and completing an agent removes its queue vehicle in the same
    flow transaction.
    """

    queue_now = np.maximum(np.asarray(link_state.queue_vehicles, dtype=np.float32), 0.0)
    effective_capacity = np.maximum(
        np.asarray(link_state.effective_capacity_vehicles, dtype=np.float32),
        0.0,
    )
    from_idx = np.asarray(node_state.turn_from_link_index, dtype=np.int32)
    to_idx = np.asarray(node_state.turn_to_link_index, dtype=np.int32)
    turn_demand = np.maximum(np.asarray(node_state.turn_demand, dtype=np.float32), 0.0)
    fractional_turn_flow = np.maximum(
        np.asarray(arrays["turn_flow_next"], dtype=np.float32),
        0.0,
    )
    fractional_turn_supply = np.maximum(
        np.asarray(arrays["turn_supply_next"], dtype=np.float32),
        0.0,
    )
    link_count = int(queue_now.shape[0])
    turn_count = int(turn_demand.shape[0])
    prior_discrete_authority = bool(
        link_state.metadata.get("runtime_discrete_agent_authority", False)
    )

    prior_turn_credit = _metadata_vector(
        node_state.metadata,
        "runtime_turn_flow_residual",
        turn_count,
        allow_negative=True,
        required=prior_discrete_authority,
    )
    prior_service_credit = _metadata_vector(
        link_state.metadata,
        "runtime_link_service_residual",
        link_count,
        required=prior_discrete_authority,
        upper_bound=1.0,
    )
    prior_receiving_credit = _metadata_vector(
        link_state.metadata,
        "runtime_link_receiving_residual",
        link_count,
        required=prior_discrete_authority,
        upper_bound=1.0,
    )
    prior_sink_credit = _metadata_vector(
        node_state.metadata,
        "runtime_sink_flow_residual",
        link_count,
        allow_negative=True,
        required=prior_discrete_authority,
    )
    if prior_discrete_authority:
        prior_service_tokens = _metadata_vector(
            link_state.metadata,
            "runtime_link_service_tokens",
            link_count,
            required=True,
        )
        prior_receiving_tokens = _metadata_vector(
            link_state.metadata,
            "runtime_link_receiving_tokens",
            link_count,
            required=True,
        )
        prior_link_sink_flow = _metadata_vector(
            link_state.metadata,
            "runtime_sink_flow_vehicles",
            link_count,
            required=True,
        )
        prior_node_sink_flow = _metadata_vector(
            node_state.metadata,
            "runtime_sink_flow_by_link_index",
            link_count,
            required=True,
        )
        for key, values in (
            ("runtime_link_service_tokens", prior_service_tokens),
            ("runtime_link_receiving_tokens", prior_receiving_tokens),
            ("runtime_sink_flow_vehicles", prior_link_sink_flow),
            ("runtime_sink_flow_by_link_index", prior_node_sink_flow),
        ):
            if bool(np.any(np.abs(values - np.rint(values)) > 1.0e-6)):
                raise ValueError(f"{key} must contain integer vehicle tokens")
        if not bool(np.array_equal(prior_link_sink_flow, prior_node_sink_flow)):
            raise ValueError(
                "runtime link/node sink flow token metadata must match exactly"
            )
    sink_demand = _metadata_vector(
        node_state.metadata,
        "runtime_sink_demand_by_link_index",
        link_count,
    )
    sink_demand = np.floor(np.maximum(sink_demand, 0.0) + 1.0e-6).astype(np.int64)

    eligible_turn_demand = (turn_demand > 0.0) & (fractional_turn_flow > 0.0)
    has_turn_demand = np.zeros((link_count,), dtype=np.bool_)
    has_receiving_demand = np.zeros((link_count,), dtype=np.bool_)
    if turn_count:
        np.logical_or.at(has_turn_demand, from_idx, eligible_turn_demand)
        np.logical_or.at(has_receiving_demand, to_idx, eligible_turn_demand)
    has_sending_demand = has_turn_demand | (sink_demand > 0)
    service_accrued = np.zeros((link_count,), dtype=np.float64)
    service_accrued[has_sending_demand] = np.asarray(
        prior_service_credit[has_sending_demand],
        dtype=np.float64,
    )
    service_accrued[has_sending_demand] += np.asarray(
        effective_capacity[has_sending_demand],
        dtype=np.float64,
    )
    service_tokens = np.floor(service_accrued + 1.0e-9).astype(np.int64)
    next_service_credit = service_accrued - service_tokens
    receiving_accrued = np.zeros((link_count,), dtype=np.float64)
    receiving_accrued[has_receiving_demand] = np.asarray(
        prior_receiving_credit[has_receiving_demand],
        dtype=np.float64,
    )
    receiving_accrued[has_receiving_demand] += np.asarray(
        effective_capacity[has_receiving_demand],
        dtype=np.float64,
    )
    receiving_tokens = np.floor(receiving_accrued + 1.0e-9).astype(np.int64)
    next_receiving_credit = receiving_accrued - receiving_tokens

    internal_demand_by_source = _segment_sum(
        np.where(eligible_turn_demand, turn_demand, 0.0),
        from_idx,
        link_count,
    ).astype(np.float64)
    fractional_internal_by_source = _segment_sum(
        fractional_turn_flow,
        from_idx,
        link_count,
    ).astype(np.float64)
    sink_demand_f64 = np.asarray(sink_demand, dtype=np.float64)
    total_service_demand = internal_demand_by_source + sink_demand_f64
    desired_internal_credit = np.divide(
        np.asarray(effective_capacity, dtype=np.float64)
        * internal_demand_by_source,
        total_service_demand,
        out=np.zeros((link_count,), dtype=np.float64),
        where=total_service_demand > 0.0,
    )
    internal_credit_budget = np.minimum(
        desired_internal_credit,
        fractional_internal_by_source,
    )
    sink_credit_budget = np.minimum(
        sink_demand_f64,
        np.maximum(
            np.asarray(effective_capacity, dtype=np.float64)
            - internal_credit_budget,
            0.0,
        ),
    )
    turn_credit_increment = np.zeros((turn_count,), dtype=np.float64)
    if turn_count:
        source_fractional_total = fractional_internal_by_source[from_idx]
        turn_credit_increment = np.divide(
            np.asarray(fractional_turn_flow, dtype=np.float64)
            * internal_credit_budget[from_idx],
            source_fractional_total,
            out=np.zeros((turn_count,), dtype=np.float64),
            where=source_fractional_total > 0.0,
        )
    turn_accrued = np.where(
        turn_demand > 0.0,
        np.asarray(prior_turn_credit, dtype=np.float64)
        + turn_credit_increment,
        0.0,
    )
    sink_accrued = np.where(
        sink_demand > 0,
        np.asarray(prior_sink_credit, dtype=np.float64) + sink_credit_budget,
        0.0,
    )
    realized_turn = np.zeros((turn_count,), dtype=np.int64)
    sink_flow = np.zeros((link_count,), dtype=np.int64)
    remaining_service = service_tokens.copy()
    remaining_receiving = receiving_tokens.copy()
    remaining_vehicles = np.floor(queue_now + 1.0e-6).astype(np.int64)
    remaining_turn_demand = np.floor(turn_demand + 1.0e-6).astype(np.int64)
    remaining_sink_demand = sink_demand.copy()
    next_turn_credit = turn_accrued.copy()
    next_sink_credit = sink_accrued.copy()

    # Deficit-style apportionment preserves fractional turn shares and gives
    # final-link sinks a bounded share of the same source-service authority.
    # The second tuple item is the deterministic class tie-break: sink before
    # turn when credits are equal, then source/turn row index.
    service_heap: list[tuple[float, int, int]] = [
        (-float(next_turn_credit[turn_index]), 1, int(turn_index))
        for turn_index in np.nonzero(eligible_turn_demand)[0].tolist()
    ]
    service_heap.extend(
        (-float(next_sink_credit[source]), 0, int(source))
        for source in np.nonzero(sink_demand > 0)[0].tolist()
    )
    heapq.heapify(service_heap)
    while service_heap:
        _negative_score, movement_class, movement_index = heapq.heappop(service_heap)
        if movement_class == 0:
            source = int(movement_index)
            if (
                remaining_sink_demand[source] <= 0
                or remaining_service[source] <= 0
                or remaining_vehicles[source] <= 0
            ):
                continue
            sink_flow[source] += 1
            remaining_sink_demand[source] -= 1
            remaining_service[source] -= 1
            remaining_vehicles[source] -= 1
            next_sink_credit[source] -= 1.0
            if (
                remaining_sink_demand[source] > 0
                and remaining_service[source] > 0
                and remaining_vehicles[source] > 0
            ):
                heapq.heappush(
                    service_heap,
                    (-float(next_sink_credit[source]), 0, source),
                )
            continue

        turn_index = int(movement_index)
        source = int(from_idx[turn_index])
        destination = int(to_idx[turn_index])
        if (
            remaining_turn_demand[turn_index] <= 0
            or remaining_service[source] <= 0
            or remaining_vehicles[source] <= 0
            or remaining_receiving[destination] <= 0
        ):
            continue
        realized_turn[turn_index] += 1
        remaining_turn_demand[turn_index] -= 1
        remaining_service[source] -= 1
        remaining_receiving[destination] -= 1
        remaining_vehicles[source] -= 1
        next_turn_credit[turn_index] -= 1.0
        if (
            remaining_turn_demand[turn_index] > 0
            and remaining_service[source] > 0
            and remaining_vehicles[source] > 0
            and remaining_receiving[destination] > 0
        ):
            heapq.heappush(
                service_heap,
                (-float(next_turn_credit[turn_index]), 1, turn_index),
            )

    realized_turn_f = np.asarray(realized_turn, dtype=np.float32)
    sink_flow_f = np.asarray(sink_flow, dtype=np.float32)
    internal_outflow = _segment_sum(realized_turn_f, from_idx, link_count)
    inflow = _segment_sum(realized_turn_f, to_idx, link_count)
    outflow = internal_outflow + sink_flow_f
    queue_next = np.maximum(0.0, queue_now - outflow + inflow)
    base_travel_time = np.asarray(arrays["base_travel_time_cost"], dtype=np.float32)

    next_arrays = dict(arrays)
    next_arrays.update(
        {
            "turn_supply_next": realized_turn_f,
            "turn_flow_next": realized_turn_f,
            "inflow_vehicles_next": inflow,
            "outflow_vehicles_next": outflow,
            "queue_vehicles_next": queue_next,
            "travel_time_cost_next": _update_travel_time_cost(
                base_travel_time,
                queue_next,
                effective_capacity,
            ),
            "capacity_violation_flags_next": (
                outflow
                > (np.asarray(service_tokens, dtype=np.float32) + 1.0e-6)
            )
            | (
                inflow
                > (np.asarray(receiving_tokens, dtype=np.float32) + 1.0e-6)
            ),
        }
    )
    metadata = {
        "link": {
            "runtime_discrete_agent_authority": True,
            "runtime_link_service_residual": np.asarray(
                next_service_credit,
                dtype=np.float32,
            ),
            "runtime_link_service_tokens": np.asarray(
                service_tokens,
                dtype=np.float32,
            ),
            "runtime_link_receiving_residual": np.asarray(
                next_receiving_credit,
                dtype=np.float32,
            ),
            "runtime_link_receiving_tokens": np.asarray(
                receiving_tokens,
                dtype=np.float32,
            ),
            "runtime_sink_flow_vehicles": sink_flow_f,
        },
        "node": {
            "runtime_fractional_turn_supply": fractional_turn_supply,
            "runtime_fractional_turn_flow": fractional_turn_flow,
            "runtime_turn_flow_residual": np.asarray(
                next_turn_credit,
                dtype=np.float32,
            ),
            "runtime_sink_flow_residual": np.asarray(
                next_sink_credit,
                dtype=np.float32,
            ),
            "runtime_sink_flow_by_link_index": sink_flow_f,
        },
    }
    return next_arrays, metadata


def _metadata_vector(
    metadata: dict[str, Any],
    key: str,
    size: int,
    *,
    allow_negative: bool = False,
    required: bool = False,
    upper_bound: float | None = None,
) -> Array:
    raw = metadata.get(key)
    if raw is None:
        if required:
            raise ValueError(f"{key} is required by prior discrete-agent authority")
        return np.zeros((int(size),), dtype=np.float32)
    values = np.asarray(raw, dtype=np.float32)
    if values.ndim == 0:
        values = np.full((int(size),), float(values), dtype=np.float32)
    elif values.shape != (int(size),):
        raise ValueError(f"{key} must be scalar or shape ({int(size)},)")
    if not bool(np.all(np.isfinite(values))):
        raise ValueError(f"{key} must contain only finite values")
    if not allow_negative and bool(np.any(values < 0.0)):
        raise ValueError(f"{key} must be non-negative")
    if upper_bound is not None and bool(
        np.any(values > (float(upper_bound) + 1.0e-6))
    ):
        raise ValueError(f"{key} must be <= {float(upper_bound)}")
    return values


def compute_baseline_flow_arrays(
    *,
    link_state: LinkState,
    node_state: NodeState,
    flow_backend: FlowUpdateBackend = "baseline",
) -> dict[str, Array]:
    """Compute baseline node/link flow arrays (numeric core, JAX-portable)."""

    if link_state.link_count == 0 and node_state.turn_count > 0:
        raise ValueError("NodeState turns require non-empty LinkState")

    turn_demand = np.maximum(np.asarray(node_state.turn_demand, dtype=np.float32), 0.0)
    turn_count = int(turn_demand.shape[0])
    turn_priority = _read_turn_metadata(
        node_state.metadata,
        "turn_base_priority",
        turn_count,
        dtype=np.float32,
        default=1.0,
    )
    turn_is_forbidden = _read_turn_metadata(
        node_state.metadata,
        "turn_is_forbidden",
        turn_count,
        dtype=np.bool_,
        default=False,
    )
    base_travel_time_cost = _read_link_base_travel_time(link_state)
    arrays = compute_baseline_flow_arrays_core(
        queue_vehicles=link_state.queue_vehicles,
        effective_capacity_vehicles=link_state.effective_capacity_vehicles,
        turn_from_link_index=node_state.turn_from_link_index,
        turn_to_link_index=node_state.turn_to_link_index,
        turn_demand=turn_demand,
        signal_phase_timer=node_state.signal_phase_timer,
        base_travel_time_cost=base_travel_time_cost,
        turn_priority=turn_priority,
        turn_is_forbidden=turn_is_forbidden,
        flow_backend=flow_backend,
    )
    arrays["base_travel_time_cost"] = base_travel_time_cost
    return arrays


def compute_baseline_flow_arrays_core(
    *,
    queue_vehicles: Array,
    effective_capacity_vehicles: Array,
    turn_from_link_index: Array,
    turn_to_link_index: Array,
    turn_demand: Array,
    signal_phase_timer: Array,
    base_travel_time_cost: Array,
    turn_priority: Array | None = None,
    turn_is_forbidden: Array | None = None,
    flow_backend: FlowUpdateBackend = "baseline",
) -> dict[str, Array]:
    """Array-only baseline flow update core (JIT-friendly entry point)."""

    _validate_flow_backend(flow_backend)
    queue_now = np.maximum(np.asarray(queue_vehicles, dtype=np.float32), 0.0)
    effective_capacity = np.maximum(np.asarray(effective_capacity_vehicles, dtype=np.float32), 0.0)
    from_idx = np.asarray(turn_from_link_index, dtype=np.int32)
    to_idx = np.asarray(turn_to_link_index, dtype=np.int32)
    turn_demand = np.maximum(np.asarray(turn_demand, dtype=np.float32), 0.0)
    signal_phase_timer = np.asarray(signal_phase_timer, dtype=np.int32)
    base_travel_time_cost = np.maximum(np.asarray(base_travel_time_cost, dtype=np.float32), 1e-3)
    turn_count = int(turn_demand.shape[0])

    if turn_priority is None:
        turn_priority = np.ones((turn_count,), dtype=np.float32)
    else:
        turn_priority = np.maximum(np.asarray(turn_priority, dtype=np.float32), 0.0)
    if turn_is_forbidden is None:
        turn_is_forbidden = np.zeros((turn_count,), dtype=np.bool_)
    else:
        turn_is_forbidden = np.asarray(turn_is_forbidden, dtype=np.bool_)

    if flow_backend in {"rust_cpu", "auto"}:
        try:
            return _compute_baseline_flow_arrays_rust(
                queue_vehicles=queue_now,
                effective_capacity_vehicles=effective_capacity,
                turn_from_link_index=from_idx,
                turn_to_link_index=to_idx,
                turn_demand=turn_demand,
                signal_phase_timer=signal_phase_timer,
                base_travel_time_cost=base_travel_time_cost,
                turn_priority=turn_priority,
                turn_is_forbidden=turn_is_forbidden,
            )
        except RuntimeError:
            if flow_backend == "rust_cpu":
                raise

    return _compute_baseline_flow_arrays_numpy_core(
        queue_vehicles=queue_now,
        effective_capacity_vehicles=effective_capacity,
        turn_from_link_index=from_idx,
        turn_to_link_index=to_idx,
        turn_demand=turn_demand,
        signal_phase_timer=signal_phase_timer,
        base_travel_time_cost=base_travel_time_cost,
        turn_priority=turn_priority,
        turn_is_forbidden=turn_is_forbidden,
    )


def _compute_baseline_flow_arrays_numpy_core(
    *,
    queue_vehicles: Array,
    effective_capacity_vehicles: Array,
    turn_from_link_index: Array,
    turn_to_link_index: Array,
    turn_demand: Array,
    signal_phase_timer: Array,
    base_travel_time_cost: Array,
    turn_priority: Array,
    turn_is_forbidden: Array,
) -> dict[str, Array]:
    queue_now = np.asarray(queue_vehicles, dtype=np.float32)
    effective_capacity = np.asarray(effective_capacity_vehicles, dtype=np.float32)
    from_idx = np.asarray(turn_from_link_index, dtype=np.int32)
    to_idx = np.asarray(turn_to_link_index, dtype=np.int32)
    turn_demand = np.asarray(turn_demand, dtype=np.float32)
    link_count = int(queue_now.shape[0])
    turn_count = int(turn_demand.shape[0])

    zeros_link = np.zeros((link_count,), dtype=np.float32)
    zeros_turn = np.zeros((turn_count,), dtype=np.float32)

    if link_count == 0:
        return {
            "turn_demand_next": turn_demand,
            "turn_supply_next": zeros_turn,
            "turn_flow_next": zeros_turn,
            "inflow_vehicles_next": zeros_link,
            "outflow_vehicles_next": zeros_link,
            "queue_vehicles_next": zeros_link,
            "travel_time_cost_next": _update_travel_time_cost(base_travel_time_cost, zeros_link, zeros_link),
            "capacity_violation_flags_next": np.zeros((0,), dtype=np.bool_),
            "signal_phase_timer_next": np.asarray(signal_phase_timer, dtype=np.int32) + 1,
        }
    if turn_count == 0:
        return {
            "turn_demand_next": turn_demand,
            "turn_supply_next": zeros_turn,
            "turn_flow_next": zeros_turn,
            "inflow_vehicles_next": zeros_link,
            "outflow_vehicles_next": zeros_link,
            "queue_vehicles_next": queue_now,
            "travel_time_cost_next": _update_travel_time_cost(base_travel_time_cost, queue_now, effective_capacity),
            "capacity_violation_flags_next": np.zeros((link_count,), dtype=np.bool_),
            "signal_phase_timer_next": np.asarray(signal_phase_timer, dtype=np.int32) + 1,
        }

    priority_weight = np.where(turn_is_forbidden, 0.0, np.maximum(turn_priority, 0.0))
    weighted_demand = np.where(turn_demand > 0, turn_demand * priority_weight, 0.0)

    from_available_link = np.minimum(queue_now, effective_capacity)
    # Point-queue baseline: capacity is a per-tick service/admission rate, not
    # a finite vehicle-storage bound.  Subtracting queue vehicles from
    # vehicles/tick is dimensionally invalid.  Spillback requires a separate
    # storage/jam-occupancy authority and is intentionally not implied here.
    receiving_supply_link = effective_capacity

    weighted_by_from = _segment_sum(weighted_demand, from_idx, link_count)
    weighted_by_to = _segment_sum(weighted_demand, to_idx, link_count)
    from_den = weighted_by_from[from_idx]
    to_den = weighted_by_to[to_idx]
    from_share = np.divide(
        weighted_demand,
        from_den,
        out=np.zeros_like(weighted_demand, dtype=np.float32),
        where=from_den > 0,
    )
    to_share = np.divide(
        weighted_demand,
        to_den,
        out=np.zeros_like(weighted_demand, dtype=np.float32),
        where=to_den > 0,
    )

    turn_supply = np.minimum(
        from_available_link[from_idx] * from_share,
        receiving_supply_link[to_idx] * to_share,
    )
    turn_flow = np.where(turn_is_forbidden, 0.0, np.minimum(turn_demand, turn_supply))

    outflow = _segment_sum(turn_flow, from_idx, link_count)
    inflow = _segment_sum(turn_flow, to_idx, link_count)
    queue_next = np.maximum(0.0, queue_now - outflow + inflow)

    return {
        "turn_demand_next": turn_demand,
        "turn_supply_next": np.maximum(turn_supply, 0.0),
        "turn_flow_next": np.maximum(turn_flow, 0.0),
        "inflow_vehicles_next": inflow,
        "outflow_vehicles_next": outflow,
        "queue_vehicles_next": queue_next,
        "travel_time_cost_next": _update_travel_time_cost(base_travel_time_cost, queue_next, effective_capacity),
        "capacity_violation_flags_next": outflow > (effective_capacity + 1e-6),
        "signal_phase_timer_next": np.asarray(signal_phase_timer, dtype=np.int32) + 1,
    }


def _validate_flow_backend(flow_backend: str) -> None:
    if flow_backend not in FLOW_UPDATE_BACKENDS:
        raise ValueError("flow_backend must be one of: baseline, rust_cpu, auto.")


def _compute_baseline_flow_arrays_rust(
    *,
    queue_vehicles: Array,
    effective_capacity_vehicles: Array,
    turn_from_link_index: Array,
    turn_to_link_index: Array,
    turn_demand: Array,
    signal_phase_timer: Array,
    base_travel_time_cost: Array,
    turn_priority: Array,
    turn_is_forbidden: Array,
) -> dict[str, Array]:
    return compute_baseline_flow_arrays_rust(
        queue_vehicles=queue_vehicles,
        effective_capacity_vehicles=effective_capacity_vehicles,
        turn_from_link_index=turn_from_link_index,
        turn_to_link_index=turn_to_link_index,
        turn_demand=turn_demand,
        signal_phase_timer=signal_phase_timer,
        base_travel_time_cost=base_travel_time_cost,
        turn_priority=turn_priority,
        turn_is_forbidden=turn_is_forbidden,
    )


def _read_turn_metadata(
    metadata: dict[str, Any],
    key: str,
    size: int,
    *,
    dtype: Any,
    default: float | bool,
) -> Array:
    raw = metadata.get(key)
    if raw is None:
        return np.full((size,), default, dtype=dtype)
    arr = np.asarray(raw, dtype=dtype)
    if arr.ndim == 0:
        return np.full((size,), arr, dtype=dtype)
    if arr.ndim != 1 or int(arr.shape[0]) != size:
        raise ValueError(f"{key} must be scalar or shape ({size},)")
    return arr


def _read_link_base_travel_time(link_state: LinkState) -> Array:
    raw = link_state.metadata.get(_FREE_FLOW_TRAVEL_TIME_KEY)
    if raw is None:
        return np.asarray(link_state.travel_time_cost, dtype=np.float32)
    arr = np.asarray(raw, dtype=np.float32)
    if arr.ndim == 0:
        return np.full((link_state.link_count,), arr, dtype=np.float32)
    if arr.ndim != 1 or int(arr.shape[0]) != link_state.link_count:
        raise ValueError(
            f"{_FREE_FLOW_TRAVEL_TIME_KEY} must be scalar or shape ({link_state.link_count},)"
        )
    return arr


def _validate_turn_index_ranges(node_state: NodeState, link_count: int) -> None:
    link_count = int(link_count)
    if link_count == 0 and node_state.turn_count > 0:
        raise ValueError("NodeState turns require non-empty LinkState")
    if node_state.turn_count == 0:
        return
    from_idx = np.asarray(node_state.turn_from_link_index)
    to_idx = np.asarray(node_state.turn_to_link_index)
    if bool(np.any(from_idx < 0)) or bool(np.any(from_idx >= link_count)):
        raise ValueError("turn_from_link_index contains out-of-range link indices")
    if bool(np.any(to_idx < 0)) or bool(np.any(to_idx >= link_count)):
        raise ValueError("turn_to_link_index contains out-of-range link indices")


def _segment_sum(values: Array, indices: Array, num_segments: int) -> Array:
    out = np.zeros((int(num_segments),), dtype=np.float32)
    np.add.at(out, np.asarray(indices, dtype=np.int32), np.asarray(values, dtype=np.float32))
    return out


def _update_travel_time_cost(
    base_cost: Array,
    queue_vehicles: Array,
    effective_capacity: Array,
) -> Array:
    base = np.maximum(np.asarray(base_cost, dtype=np.float32), 1e-3)
    queue = np.maximum(np.asarray(queue_vehicles, dtype=np.float32), 0.0)
    cap = np.maximum(np.asarray(effective_capacity, dtype=np.float32), 1e-3)
    # ``base`` and the returned generalized cost are simulation ticks.
    # queue [veh] / capacity [veh/tick] is an additive waiting time [tick].
    queue_delay_ticks = queue / cap
    return base + queue_delay_ticks
