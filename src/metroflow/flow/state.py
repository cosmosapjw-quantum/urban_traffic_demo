"""Link/node flow state containers for the baseline traffic engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

__all__ = [
    "LinkState",
    "NodeState",
    "create_link_state",
    "create_node_state",
    "validate_link_state",
    "validate_node_state",
]

Array = np.ndarray


@dataclass(slots=True)
class LinkState:
    """Per-link dynamic flow state for a simulation tick."""

    queue_vehicles: Array
    inflow_vehicles: Array
    outflow_vehicles: Array
    travel_time_cost: Array
    capacity_veh_per_tick: Array
    incident_capacity_multiplier: Array
    capacity_violation_flags: Array | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.queue_vehicles = np.asarray(self.queue_vehicles, dtype=np.float32)
        self.inflow_vehicles = np.asarray(self.inflow_vehicles, dtype=np.float32)
        self.outflow_vehicles = np.asarray(self.outflow_vehicles, dtype=np.float32)
        self.travel_time_cost = np.asarray(self.travel_time_cost, dtype=np.float32)
        self.capacity_veh_per_tick = np.asarray(self.capacity_veh_per_tick, dtype=np.float32)
        self.incident_capacity_multiplier = np.asarray(
            self.incident_capacity_multiplier,
            dtype=np.float32,
        )
        if self.capacity_violation_flags is None:
            self.capacity_violation_flags = np.zeros_like(self.queue_vehicles, dtype=np.bool_)
        else:
            self.capacity_violation_flags = np.asarray(
                self.capacity_violation_flags,
                dtype=np.bool_,
            )
        if not isinstance(self.metadata, dict):
            self.metadata = dict(self.metadata)

        _validate_same_shape(
            self.queue_vehicles,
            self.inflow_vehicles,
            self.outflow_vehicles,
            self.travel_time_cost,
            self.capacity_veh_per_tick,
            self.incident_capacity_multiplier,
            self.capacity_violation_flags,
        )
        if self.queue_vehicles.ndim != 1:
            raise ValueError("LinkState arrays must be 1-D")
        if bool(np.any(self.queue_vehicles < 0)):
            raise ValueError("queue_vehicles must be >= 0")
        if bool(np.any(self.inflow_vehicles < 0)):
            raise ValueError("inflow_vehicles must be >= 0")
        if bool(np.any(self.outflow_vehicles < 0)):
            raise ValueError("outflow_vehicles must be >= 0")
        if bool(np.any(self.travel_time_cost <= 0)):
            raise ValueError("travel_time_cost must be > 0")
        if bool(np.any(self.capacity_veh_per_tick < 0)):
            raise ValueError("capacity_veh_per_tick must be >= 0")
        if bool(np.any(self.incident_capacity_multiplier < 0)) or bool(
            np.any(self.incident_capacity_multiplier > 1)
        ):
            raise ValueError("incident_capacity_multiplier must be in [0, 1]")

    @property
    def link_count(self) -> int:
        return int(self.queue_vehicles.shape[0])

    @property
    def effective_capacity_vehicles(self) -> Array:
        return self.capacity_veh_per_tick * self.incident_capacity_multiplier

    @property
    def capacity_violation_count(self) -> int:
        return int(np.sum(self.capacity_violation_flags))

    @classmethod
    def from_internal_arrays(
        cls,
        *,
        queue_vehicles: Any,
        inflow_vehicles: Any,
        outflow_vehicles: Any,
        travel_time_cost: Any,
        capacity_veh_per_tick: Any,
        incident_capacity_multiplier: Any,
        capacity_violation_flags: Any,
        metadata: dict[str, Any] | None = None,
    ) -> "LinkState":
        """Build LinkState without JAX coercion for trusted hotpath internals."""

        queue = np.asarray(queue_vehicles, dtype=np.float32)
        inflow = np.asarray(inflow_vehicles, dtype=np.float32)
        outflow = np.asarray(outflow_vehicles, dtype=np.float32)
        travel = np.asarray(travel_time_cost, dtype=np.float32)
        capacity = np.asarray(capacity_veh_per_tick, dtype=np.float32)
        incident = np.asarray(incident_capacity_multiplier, dtype=np.float32)
        flags = np.asarray(capacity_violation_flags, dtype=np.bool_)
        _validate_same_shape_numpy(
            queue,
            inflow,
            outflow,
            travel,
            capacity,
            incident,
            flags,
        )
        if queue.ndim != 1:
            raise ValueError("LinkState arrays must be 1-D")
        out_obj = object.__new__(cls)
        out_obj.queue_vehicles = queue
        out_obj.inflow_vehicles = inflow
        out_obj.outflow_vehicles = outflow
        out_obj.travel_time_cost = travel
        out_obj.capacity_veh_per_tick = capacity
        out_obj.incident_capacity_multiplier = incident
        out_obj.capacity_violation_flags = flags
        out_obj.metadata = dict(metadata or {})
        return out_obj


@dataclass(slots=True)
class NodeState:
    """Per-turn / per-node dynamic state for junction allocation updates."""

    turn_from_link_index: Array
    turn_to_link_index: Array
    turn_demand: Array
    turn_supply: Array
    turn_flow: Array
    signal_phase_index: Array
    signal_phase_timer: Array
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.turn_from_link_index = np.asarray(self.turn_from_link_index, dtype=np.int32)
        self.turn_to_link_index = np.asarray(self.turn_to_link_index, dtype=np.int32)
        self.turn_demand = np.asarray(self.turn_demand, dtype=np.float32)
        self.turn_supply = np.asarray(self.turn_supply, dtype=np.float32)
        self.turn_flow = np.asarray(self.turn_flow, dtype=np.float32)
        self.signal_phase_index = np.asarray(self.signal_phase_index, dtype=np.int32)
        self.signal_phase_timer = np.asarray(self.signal_phase_timer, dtype=np.int32)
        if not isinstance(self.metadata, dict):
            self.metadata = dict(self.metadata)

        _validate_same_shape(
            self.turn_from_link_index,
            self.turn_to_link_index,
            self.turn_demand,
            self.turn_supply,
            self.turn_flow,
        )
        if self.turn_demand.ndim != 1:
            raise ValueError("NodeState turn arrays must be 1-D")
        if self.signal_phase_index.ndim != 1 or self.signal_phase_timer.ndim != 1:
            raise ValueError("NodeState signal phase arrays must be 1-D")
        if bool(np.any(self.turn_demand < 0)):
            raise ValueError("turn_demand must be >= 0")
        if bool(np.any(self.turn_supply < 0)):
            raise ValueError("turn_supply must be >= 0")
        if bool(np.any(self.turn_flow < 0)):
            raise ValueError("turn_flow must be >= 0")
        if bool(np.any(self.signal_phase_timer < 0)):
            raise ValueError("signal_phase_timer must be >= 0")

    @property
    def turn_count(self) -> int:
        return int(self.turn_demand.shape[0])

    @property
    def node_count(self) -> int:
        return int(self.signal_phase_index.shape[0])

    @property
    def signal_phase_state(self) -> dict[str, Array]:
        """Convenience view matching the data-model's simplified signal state concept."""

        return {
            "phase_index": self.signal_phase_index,
            "phase_timer": self.signal_phase_timer,
        }

    @classmethod
    def from_internal_arrays(
        cls,
        *,
        turn_from_link_index: Any,
        turn_to_link_index: Any,
        turn_demand: Any,
        turn_supply: Any,
        turn_flow: Any,
        signal_phase_index: Any,
        signal_phase_timer: Any,
        metadata: dict[str, Any] | None = None,
    ) -> "NodeState":
        """Build NodeState without JAX coercion for trusted hotpath internals."""

        from_idx = np.asarray(turn_from_link_index, dtype=np.int32)
        to_idx = np.asarray(turn_to_link_index, dtype=np.int32)
        demand = np.asarray(turn_demand, dtype=np.float32)
        supply = np.asarray(turn_supply, dtype=np.float32)
        flow = np.asarray(turn_flow, dtype=np.float32)
        phase_index = np.asarray(signal_phase_index, dtype=np.int32)
        phase_timer = np.asarray(signal_phase_timer, dtype=np.int32)
        _validate_same_shape_numpy(from_idx, to_idx, demand, supply, flow)
        if demand.ndim != 1:
            raise ValueError("NodeState turn arrays must be 1-D")
        if phase_index.ndim != 1 or phase_timer.ndim != 1:
            raise ValueError("NodeState signal phase arrays must be 1-D")
        out_obj = object.__new__(cls)
        out_obj.turn_from_link_index = from_idx
        out_obj.turn_to_link_index = to_idx
        out_obj.turn_demand = demand
        out_obj.turn_supply = supply
        out_obj.turn_flow = flow
        out_obj.signal_phase_index = phase_index
        out_obj.signal_phase_timer = phase_timer
        out_obj.metadata = dict(metadata or {})
        return out_obj


def create_link_state(
    link_count: int,
    *,
    travel_time_cost: float | Array = 1.0,
    capacity_veh_per_tick: float | Array = 1.0,
) -> LinkState:
    """Create a zeroed `LinkState` for `link_count` links."""

    link_count = int(link_count)
    if link_count < 0:
        raise ValueError("link_count must be >= 0")
    zeros = np.zeros((link_count,), dtype=np.float32)
    ones = np.ones((link_count,), dtype=np.float32)
    travel = _broadcast_1d_numpy(travel_time_cost, link_count, dtype=np.float32)
    capacity = _broadcast_1d_numpy(capacity_veh_per_tick, link_count, dtype=np.float32)
    return LinkState.from_internal_arrays(
        queue_vehicles=zeros,
        inflow_vehicles=zeros,
        outflow_vehicles=zeros,
        travel_time_cost=travel,
        capacity_veh_per_tick=capacity,
        incident_capacity_multiplier=ones,
        capacity_violation_flags=np.zeros((link_count,), dtype=np.bool_),
    )


def create_node_state(
    turn_from_link_index: Array | list[int] | tuple[int, ...],
    turn_to_link_index: Array | list[int] | tuple[int, ...],
    *,
    node_count: int,
) -> NodeState:
    """Create a zeroed `NodeState` for a fixed turn list and node count."""

    node_count = int(node_count)
    if node_count < 0:
        raise ValueError("node_count must be >= 0")
    from_idx = np.asarray(turn_from_link_index, dtype=np.int32)
    to_idx = np.asarray(turn_to_link_index, dtype=np.int32)
    if from_idx.shape != to_idx.shape:
        raise ValueError("turn_from_link_index and turn_to_link_index must have same shape")
    if from_idx.ndim != 1:
        raise ValueError("turn link index arrays must be 1-D")
    turn_count = int(from_idx.shape[0])
    zeros_turn = np.zeros((turn_count,), dtype=np.float32)
    return NodeState.from_internal_arrays(
        turn_from_link_index=from_idx,
        turn_to_link_index=to_idx,
        turn_demand=zeros_turn,
        turn_supply=zeros_turn,
        turn_flow=zeros_turn,
        signal_phase_index=np.zeros((node_count,), dtype=np.int32),
        signal_phase_timer=np.zeros((node_count,), dtype=np.int32),
    )


def validate_link_state(link_state: LinkState) -> tuple[str, ...]:
    """Return validation issues (empty tuple if valid) for `LinkState`."""

    issues: list[str] = []
    if bool(np.any(link_state.queue_vehicles < 0)):
        issues.append("queue_vehicles contains negative values")
    if bool(np.any(link_state.outflow_vehicles < 0)):
        issues.append("outflow_vehicles contains negative values")
    if bool(np.any(link_state.inflow_vehicles < 0)):
        issues.append("inflow_vehicles contains negative values")
    if bool(np.any(link_state.travel_time_cost <= 0)):
        issues.append("travel_time_cost contains non-positive values")
    if bool(np.any(link_state.incident_capacity_multiplier < 0)) or bool(
        np.any(link_state.incident_capacity_multiplier > 1)
    ):
        issues.append("incident_capacity_multiplier contains values outside [0, 1]")
    capacity_authority = link_state.effective_capacity_vehicles
    if bool(link_state.metadata.get("runtime_discrete_agent_authority", False)):
        raw_service_tokens = link_state.metadata.get("runtime_link_service_tokens")
        if raw_service_tokens is None:
            issues.append(
                "runtime_link_service_tokens missing for discrete-agent authority"
            )
        else:
            service_tokens = np.asarray(raw_service_tokens, dtype=np.float32)
            if service_tokens.shape != (link_state.link_count,):
                issues.append("runtime_link_service_tokens shape mismatch")
            elif not bool(np.all(np.isfinite(service_tokens))):
                issues.append("runtime_link_service_tokens contains non-finite values")
            elif bool(np.any(service_tokens < 0.0)):
                issues.append("runtime_link_service_tokens contains negative values")
            elif bool(np.any(np.abs(service_tokens - np.rint(service_tokens)) > 1e-6)):
                issues.append("runtime_link_service_tokens contains non-integral values")
            else:
                capacity_authority = service_tokens
    observed_capacity_exceed = link_state.outflow_vehicles > (capacity_authority + 1e-6)
    expected_flags = int(np.sum(observed_capacity_exceed))
    actual_flags = int(np.sum(link_state.capacity_violation_flags))
    if actual_flags < expected_flags:
        issues.append("capacity_violation_flags under-report outflow > effective capacity")
    return tuple(issues)


def validate_node_state(node_state: NodeState, *, tolerance: float = 1e-6) -> tuple[str, ...]:
    """Return validation issues (empty tuple if valid) for `NodeState`."""

    issues: list[str] = []
    if bool(np.any(node_state.turn_demand < 0)):
        issues.append("turn_demand contains negative values")
    if bool(np.any(node_state.turn_supply < 0)):
        issues.append("turn_supply contains negative values")
    if bool(np.any(node_state.turn_flow < 0)):
        issues.append("turn_flow contains negative values")
    if bool(np.any(node_state.turn_flow - node_state.turn_demand > float(tolerance))):
        issues.append("turn_flow exceeds turn_demand")
    if bool(np.any(node_state.turn_flow - node_state.turn_supply > float(tolerance))):
        issues.append("turn_flow exceeds turn_supply")
    if bool(np.any(node_state.signal_phase_timer < 0)):
        issues.append("signal_phase_timer contains negative values")
    return tuple(issues)


def _validate_same_shape(*arrays: Array) -> None:
    shapes = {tuple(np.asarray(array).shape) for array in arrays}
    if len(shapes) != 1:
        raise ValueError(f"all arrays must have the same shape, got {sorted(shapes)}")


def _validate_same_shape_numpy(*arrays: np.ndarray) -> None:
    shapes = {tuple(np.asarray(array).shape) for array in arrays}
    if len(shapes) != 1:
        raise ValueError(f"all arrays must have the same shape, got {sorted(shapes)}")


def _broadcast_1d(value: float | Array, size: int, *, dtype: Any) -> Array:
    arr = np.asarray(value, dtype=dtype)
    if arr.ndim == 0:
        return np.full((size,), arr, dtype=dtype)
    if arr.ndim == 1 and int(arr.shape[0]) == size:
        return arr
    raise ValueError(f"value must be scalar or shape ({size},), got {tuple(arr.shape)}")


def _broadcast_1d_numpy(value: float | Array, size: int, *, dtype: Any) -> np.ndarray:
    arr = np.asarray(value, dtype=dtype)
    if arr.ndim == 0:
        return np.full((size,), arr, dtype=dtype)
    if arr.ndim == 1 and int(arr.shape[0]) == size:
        return arr
    raise ValueError(f"value must be scalar or shape ({size},), got {tuple(arr.shape)}")
