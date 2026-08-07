"""Invariant validation/report structures and core checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

import numpy as np

from metroflow.flow.state import LinkState, NodeState
from metroflow.sim.active_agents import ActiveAgentPool
from metroflow.sim.state import SimulationState

__all__ = [
    "InvariantSeverity",
    "InvariantViolation",
    "InvariantCounters",
    "InvariantReport",
    "ConservationSnapshot",
    "check_conservation_hook",
    "check_non_negative_queue",
    "check_finite_link_storage",
    "check_capacity_violation_flags",
    "validate_invariants",
]


class InvariantSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(slots=True)
class InvariantViolation:
    """Structured invariant violation record for telemetry and summaries."""

    code: str
    message: str
    severity: InvariantSeverity = InvariantSeverity.ERROR
    check_name: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.code = str(self.code)
        self.message = str(self.message)
        if not isinstance(self.severity, InvariantSeverity):
            self.severity = InvariantSeverity(self.severity)
        if self.check_name is not None:
            self.check_name = str(self.check_name)
        if not isinstance(self.details, dict):
            self.details = dict(self.details)


@dataclass(slots=True)
class InvariantCounters:
    """Aggregated invariant counts suitable for `RunSummary` serialization."""

    total_checks_run: int = 0
    total_violations: int = 0
    conservation_violations: int = 0
    negative_queue_violations: int = 0
    capacity_flag_violations: int = 0
    active_agent_pool_violations: int = 0
    other_violations: int = 0

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:  # type: ignore[attr-defined]
            value = int(getattr(self, field_name))
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")
            setattr(self, field_name, value)

    def as_dict(self) -> dict[str, int]:
        return {
            "total_checks_run": self.total_checks_run,
            "total_violations": self.total_violations,
            "conservation_violations": self.conservation_violations,
            "negative_queue_violations": self.negative_queue_violations,
            "capacity_flag_violations": self.capacity_flag_violations,
            "active_agent_pool_violations": self.active_agent_pool_violations,
            "other_violations": self.other_violations,
        }


@dataclass(slots=True)
class InvariantReport:
    """Per-tick invariant validation report."""

    tick_index: int = 0
    checks_run: tuple[str, ...] = field(default_factory=tuple)
    checks_skipped: tuple[str, ...] = field(default_factory=tuple)
    violations: tuple[InvariantViolation, ...] = field(default_factory=tuple)
    counters: InvariantCounters = field(default_factory=InvariantCounters)

    def __post_init__(self) -> None:
        self.tick_index = int(self.tick_index)
        if self.tick_index < 0:
            raise ValueError("tick_index must be >= 0")
        if not isinstance(self.counters, InvariantCounters):
            self.counters = InvariantCounters(**dict(self.counters))
        self.checks_run = tuple(str(x) for x in self.checks_run)
        self.checks_skipped = tuple(str(x) for x in self.checks_skipped)
        self.violations = tuple(
            v if isinstance(v, InvariantViolation) else InvariantViolation(**dict(v))
            for v in self.violations
        )

    @property
    def ok(self) -> bool:
        return not self.violations

    def invariant_violation_counts(self) -> dict[str, int]:
        """Return `RunSummary`-friendly invariant violation counters."""

        return self.counters.as_dict()


@dataclass(slots=True)
class ConservationSnapshot:
    """Counts required for conservation reconciliation hook checks."""

    generated_total: int
    pending_trip_requests: int
    active_agents: int
    completed_trips_total: int
    failed_trips_total: int

    def __post_init__(self) -> None:
        self.generated_total = int(self.generated_total)
        self.pending_trip_requests = int(self.pending_trip_requests)
        self.active_agents = int(self.active_agents)
        self.completed_trips_total = int(self.completed_trips_total)
        self.failed_trips_total = int(self.failed_trips_total)
        for field_name in self.__dataclass_fields__:  # type: ignore[attr-defined]
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be >= 0")

    @property
    def reconciled_total(self) -> int:
        return (
            self.pending_trip_requests
            + self.active_agents
            + self.completed_trips_total
            + self.failed_trips_total
        )


def check_conservation_hook(
    snapshot: ConservationSnapshot,
    *,
    tolerance: int = 0,
) -> tuple[InvariantViolation, ...]:
    """Check conservation reconciliation for generated/pending/active/completed/failed."""

    tolerance = int(tolerance)
    if tolerance < 0:
        raise ValueError("tolerance must be >= 0")

    delta = snapshot.generated_total - snapshot.reconciled_total
    if abs(delta) <= tolerance:
        return ()
    return (
        InvariantViolation(
            code="conservation_mismatch",
            check_name="conservation",
            message="Generated trip total does not reconcile with staged counts",
            details={
                "generated_total": snapshot.generated_total,
                "reconciled_total": snapshot.reconciled_total,
                "delta": delta,
                "tolerance": tolerance,
            },
        ),
    )


def check_non_negative_queue(
    queue_values: Iterable[float] | Any,
    *,
    field_name: str = "queue_vehicles",
) -> tuple[InvariantViolation, ...]:
    """Check queue values for negatives and return structured violations."""

    arr = np.asarray(queue_values, dtype=np.float32)
    if arr.ndim == 0:
        arr = arr.reshape((1,))
    finite_mask = np.isfinite(arr)
    if not bool(np.all(finite_mask)):
        first_index = int(np.nonzero(~finite_mask)[0][0])
        return (
            InvariantViolation(
                code="non_finite_queue_detected",
                check_name="non_negative_queue",
                message="Queue values must be finite",
                details={
                    "field_name": field_name,
                    "non_finite_count": int(np.sum(~finite_mask)),
                    "first_non_finite_index": first_index,
                },
            ),
        )
    negative_mask = arr < 0
    if not bool(np.any(negative_mask)):
        return ()

    negative_indices = np.nonzero(negative_mask)[0]
    first_index = int(negative_indices[0])
    min_value = float(np.min(arr))
    negative_count = int(np.sum(negative_mask))
    return (
        InvariantViolation(
            code="negative_queue_detected",
            check_name="non_negative_queue",
            message="Queue values must remain non-negative",
            details={
                "field_name": field_name,
                "negative_count": negative_count,
                "first_negative_index": first_index,
                "min_value": min_value,
            },
        ),
    )


def check_finite_link_storage(
    queue_values: Iterable[float] | Any,
    storage_capacity_values: Iterable[float] | Any,
    *,
    tolerance: float = 1e-6,
) -> tuple[InvariantViolation, ...]:
    """Validate spatial-queue storage authority and occupied mass."""

    queue = np.asarray(queue_values, dtype=np.float32)
    storage = np.asarray(storage_capacity_values, dtype=np.float32)
    if queue.ndim != 1 or storage.shape != queue.shape:
        return (
            InvariantViolation(
                code="finite_link_storage_shape_mismatch",
                check_name="finite_link_storage",
                message="Spatial link storage must match the one-dimensional link queue",
                details={
                    "queue_shape": tuple(int(value) for value in queue.shape),
                    "storage_shape": tuple(int(value) for value in storage.shape),
                },
            ),
        )
    invalid_storage = ~np.isfinite(storage) | (storage < 1.0)
    if bool(np.any(invalid_storage)):
        first = int(np.nonzero(invalid_storage)[0][0])
        return (
            InvariantViolation(
                code="finite_link_storage_invalid",
                check_name="finite_link_storage",
                message="Spatial link storage must be finite and at least one vehicle",
                details={
                    "invalid_count": int(np.sum(invalid_storage)),
                    "first_link_index": first,
                    "first_storage_capacity": float(storage[first]),
                },
            ),
        )
    exceeded = queue > storage + float(tolerance)
    if not bool(np.any(exceeded)):
        return ()
    first = int(np.nonzero(exceeded)[0][0])
    return (
        InvariantViolation(
            code="finite_link_storage_exceeded",
            check_name="finite_link_storage",
            message="Spatial link occupancy must not exceed finite vehicle storage",
            details={
                "exceeded_count": int(np.sum(exceeded)),
                "first_link_index": first,
                "queue_vehicles": float(queue[first]),
                "storage_capacity_vehicles": float(storage[first]),
                "tolerance": float(tolerance),
            },
        ),
    )


def check_capacity_violation_flags(
    outflow_values: Iterable[float] | Any,
    effective_capacity_values: Iterable[float] | Any,
    *,
    inflow_values: Iterable[float] | Any | None = None,
    receiving_capacity_values: Iterable[float] | Any | None = None,
    flag_values: Iterable[bool] | Any | None = None,
    flagged_count: int | None = None,
    tolerance: float = 1e-6,
) -> tuple[InvariantViolation, ...]:
    """Check source/receiving capacity and exact violation-flag accounting."""

    outflow = np.asarray(outflow_values, dtype=np.float32)
    capacity = np.asarray(effective_capacity_values, dtype=np.float32)
    if outflow.shape != capacity.shape:
        raise ValueError("outflow_values and effective_capacity_values must have same shape")

    finite_arrays: dict[str, np.ndarray] = {
        "outflow_values": outflow,
        "effective_capacity_values": capacity,
    }
    if (inflow_values is None) != (receiving_capacity_values is None):
        raise ValueError(
            "inflow_values and receiving_capacity_values must be provided together"
        )
    if inflow_values is not None and receiving_capacity_values is not None:
        inflow = np.asarray(inflow_values, dtype=np.float32)
        receiving_capacity = np.asarray(receiving_capacity_values, dtype=np.float32)
        if inflow.shape != capacity.shape or receiving_capacity.shape != capacity.shape:
            raise ValueError(
                "inflow_values and receiving_capacity_values must match capacity shape"
            )
        finite_arrays["inflow_values"] = inflow
        finite_arrays["receiving_capacity_values"] = receiving_capacity
    non_finite_counts = {
        name: int(np.sum(~np.isfinite(values)))
        for name, values in finite_arrays.items()
        if bool(np.any(~np.isfinite(values)))
    }
    if non_finite_counts:
        return (
            InvariantViolation(
                code="non_finite_capacity_authority",
                check_name="capacity_flags",
                message="Capacity authority and realized flow must be finite",
                details={"non_finite_counts": non_finite_counts},
            ),
        )

    outbound_exceed_mask = outflow > (capacity + float(tolerance))
    inbound_exceed_mask = np.zeros_like(outbound_exceed_mask, dtype=np.bool_)
    if inflow_values is not None and receiving_capacity_values is not None:
        inbound_exceed_mask = inflow > (
            receiving_capacity + float(tolerance)
        )
    exceed_mask = outbound_exceed_mask | inbound_exceed_mask
    exceed_count = int(np.sum(exceed_mask))
    violations: list[InvariantViolation] = []
    if flagged_count is not None:
        flagged_count = int(flagged_count)
        if flagged_count < 0:
            raise ValueError("flagged_count must be >= 0")
        if flagged_count != exceed_count:
            violations.append(
                InvariantViolation(
                    code="capacity_flag_count_mismatch",
                    check_name="capacity_flags",
                    message=(
                        "Capacity violation counter does not match observed exceedances"
                    ),
                    details={
                        "observed_exceed_count": exceed_count,
                        "flagged_count": flagged_count,
                        "tolerance": float(tolerance),
                    },
                )
            )
    if flag_values is not None:
        flags = np.asarray(flag_values, dtype=np.bool_)
        if flags.shape != exceed_mask.shape:
            raise ValueError("flag_values must match capacity shape")
        mismatch = np.nonzero(flags != exceed_mask)[0]
        if mismatch.size:
            violations.append(
                InvariantViolation(
                    code="capacity_flag_mask_mismatch",
                    check_name="capacity_flags",
                    message=(
                        "Per-link capacity flags must match source or receiving "
                        "token exceedances"
                    ),
                    details={
                        "mismatch_count": int(mismatch.size),
                        "first_mismatch_index": int(mismatch[0]),
                        "tolerance": float(tolerance),
                    },
                )
            )
    if exceed_count:
        violations.append(
            InvariantViolation(
                code="capacity_exceeded",
                check_name="capacity_flags",
                message="Flow must not exceed source-service or receiving capacity",
                details={
                    "exceed_count": exceed_count,
                    "outbound_exceed_count": int(np.sum(outbound_exceed_mask)),
                    "inbound_exceed_count": int(np.sum(inbound_exceed_mask)),
                    "first_exceed_index": int(np.nonzero(exceed_mask)[0][0]),
                    "tolerance": float(tolerance),
                },
            )
        )
    return tuple(violations)


def validate_invariants(state: SimulationState) -> InvariantReport:
    """Validate core invariants from a `SimulationState` using available refs.

    This is a foundational, duck-typed validator. It runs checks opportunistically
    when referenced state pieces exist and records skipped checks otherwise.
    """

    checks_run: list[str] = []
    checks_skipped: list[str] = []
    violations: list[InvariantViolation] = []

    dynamic = state.dynamic
    tick_index = state.tick_index

    checks_run.append("active_agent_pool_consistency")
    pool = dynamic.active_agent_pool
    if isinstance(pool, ActiveAgentPool):
        for issue in _validate_active_agent_pool_fast(pool):
            violations.append(
                InvariantViolation(
                    code="active_agent_pool_inconsistent",
                    check_name="active_agent_pool_consistency",
                    message=issue,
                )
            )
    else:
        checks_skipped.append("active_agent_pool_consistency")
        checks_run.pop()

    checks_run.append("non_negative_queue")
    queue_values = _lookup_attr_or_key(dynamic.flow_link_state, "queue_vehicles")
    if queue_values is None:
        checks_skipped.append("non_negative_queue")
        checks_run.pop()
    else:
        violations.extend(check_non_negative_queue(queue_values))

    checks_run.append("finite_link_storage")
    storage_violations = _check_runtime_finite_link_storage(state)
    if storage_violations is None:
        checks_skipped.append("finite_link_storage")
        checks_run.pop()
    else:
        violations.extend(storage_violations)

    checks_run.append("runtime_vehicle_queue_authority")
    authority_violations = _check_runtime_vehicle_queue_authority(state)
    if authority_violations is None:
        checks_skipped.append("runtime_vehicle_queue_authority")
        checks_run.pop()
    else:
        violations.extend(authority_violations)

    checks_run.append("runtime_token_authority")
    token_violations = _check_runtime_token_authority(state)
    if token_violations is None:
        checks_skipped.append("runtime_token_authority")
        checks_run.pop()
    else:
        violations.extend(token_violations)

    checks_run.append("capacity_flags")
    outflow_values = _lookup_attr_or_key(dynamic.flow_link_state, "outflow_vehicles")
    inflow_values = _lookup_attr_or_key(dynamic.flow_link_state, "inflow_vehicles")
    capacity_values = _resolve_effective_capacity_values(dynamic.flow_link_state)
    if outflow_values is None or capacity_values is None:
        checks_skipped.append("capacity_flags")
        checks_run.pop()
    else:
        raw_flags = _lookup_attr_or_key(dynamic.flow_link_state, "capacity_violation_flags")
        receiving_capacity_values = _resolve_receiving_capacity_values(
            dynamic.flow_link_state
        )
        if inflow_values is None:
            receiving_capacity_values = None
        violations.extend(
            check_capacity_violation_flags(
                outflow_values,
                capacity_values,
                inflow_values=(
                    inflow_values
                    if receiving_capacity_values is not None
                    else None
                ),
                receiving_capacity_values=receiving_capacity_values,
                flag_values=raw_flags,
            )
        )

    checks_run.append("trip_lifecycle_disjoint")
    lifecycle_violations = _check_trip_lifecycle_disjoint(state)
    if lifecycle_violations is None:
        checks_skipped.append("trip_lifecycle_disjoint")
        checks_run.pop()
    else:
        violations.extend(lifecycle_violations)

    checks_run.append("conservation")
    conservation = _extract_conservation_snapshot(state)
    if conservation is None:
        checks_skipped.append("conservation")
        checks_run.pop()
    else:
        violations.extend(check_conservation_hook(conservation))

    counters = _build_counters(checks_run, violations)
    return InvariantReport(
        tick_index=tick_index,
        checks_run=tuple(checks_run),
        checks_skipped=tuple(checks_skipped),
        violations=tuple(violations),
        counters=counters,
    )


def _build_counters(
    checks_run: list[str],
    violations: list[InvariantViolation],
) -> InvariantCounters:
    counters = InvariantCounters(total_checks_run=len(checks_run))
    counters.total_violations = len(violations)
    for violation in violations:
        if violation.check_name == "conservation":
            counters.conservation_violations += 1
        elif violation.check_name == "non_negative_queue":
            counters.negative_queue_violations += 1
        elif violation.check_name == "capacity_flags":
            counters.capacity_flag_violations += 1
        elif violation.check_name == "active_agent_pool_consistency":
            counters.active_agent_pool_violations += 1
        else:
            counters.other_violations += 1
    return counters


def _resolve_effective_capacity_values(flow_link_state: Any) -> Any | None:
    if flow_link_state is None:
        return None
    if isinstance(flow_link_state, LinkState):
        runtime_tokens = flow_link_state.metadata.get("runtime_link_service_tokens")
        if runtime_tokens is not None:
            values = np.asarray(runtime_tokens, dtype=np.float32)
            if values.shape != (flow_link_state.link_count,):
                raise ValueError("runtime_link_service_tokens shape mismatch")
            return values
        base_capacity = np.asarray(flow_link_state.capacity_veh_per_tick, dtype=np.float32)
        multiplier = np.asarray(flow_link_state.incident_capacity_multiplier, dtype=np.float32)
        return base_capacity * multiplier
    direct = _lookup_attr_or_key(flow_link_state, "effective_capacity_vehicles")
    if direct is not None:
        return direct

    base_capacity = _lookup_attr_or_key(flow_link_state, "capacity_veh_per_tick")
    if base_capacity is None:
        return None
    multiplier = _lookup_attr_or_key(flow_link_state, "incident_capacity_multiplier")
    if multiplier is None:
        return base_capacity
    return np.asarray(base_capacity, dtype=np.float32) * np.asarray(multiplier, dtype=np.float32)


def _resolve_receiving_capacity_values(flow_link_state: Any) -> Any | None:
    if flow_link_state is None:
        return None
    if isinstance(flow_link_state, LinkState):
        runtime_tokens = flow_link_state.metadata.get(
            "runtime_link_receiving_tokens"
        )
        if runtime_tokens is not None:
            values = np.asarray(runtime_tokens, dtype=np.float32)
            if values.shape != (flow_link_state.link_count,):
                raise ValueError("runtime_link_receiving_tokens shape mismatch")
            return values
        base_capacity = np.asarray(
            flow_link_state.capacity_veh_per_tick,
            dtype=np.float32,
        )
        multiplier = np.asarray(
            flow_link_state.incident_capacity_multiplier,
            dtype=np.float32,
        )
        return base_capacity * multiplier
    return _resolve_effective_capacity_values(flow_link_state)


def _check_runtime_token_authority(
    state: SimulationState,
) -> tuple[InvariantViolation, ...] | None:
    link_state = state.dynamic.flow_link_state
    if (
        not isinstance(link_state, LinkState)
        or not bool(
            link_state.metadata.get("runtime_discrete_agent_authority", False)
        )
    ):
        return None

    node_state = state.dynamic.flow_node_state
    violations: list[InvariantViolation] = []

    def add_invalid(key: str, reason: str, **details: Any) -> None:
        violations.append(
            InvariantViolation(
                code="runtime_token_metadata_invalid",
                check_name="runtime_token_authority",
                message="Discrete runtime token/residual metadata must fail closed",
                details={"key": key, "reason": reason, **details},
            )
        )

    def check_vector(
        metadata: Mapping[str, Any],
        key: str,
        size: int,
        *,
        require_integral: bool = False,
        require_non_negative: bool = False,
        unit_residual: bool = False,
        upper_bound: float | None = None,
    ) -> np.ndarray | None:
        raw = metadata.get(key)
        if raw is None:
            add_invalid(key, "missing")
            return None
        values = np.asarray(raw, dtype=np.float32)
        if values.shape != (int(size),):
            add_invalid(
                key,
                "shape_mismatch",
                expected_shape=(int(size),),
                actual_shape=tuple(int(value) for value in values.shape),
            )
            return None
        if not bool(np.all(np.isfinite(values))):
            add_invalid(
                key,
                "non_finite",
                non_finite_count=int(np.sum(~np.isfinite(values))),
            )
            return None
        if require_non_negative and bool(np.any(values < 0.0)):
            add_invalid(key, "negative")
        if require_integral and bool(
            np.any(np.abs(values - np.rint(values)) > 1.0e-6)
        ):
            add_invalid(key, "non_integral")
        if unit_residual and (
            bool(np.any(values < 0.0))
            or bool(np.any(values >= 1.0))
        ):
            add_invalid(key, "outside_unit_residual_range")
        if upper_bound is not None and bool(np.any(values > float(upper_bound))):
            add_invalid(key, "above_upper_bound", upper_bound=float(upper_bound))
        return values

    check_vector(
        link_state.metadata,
        "runtime_link_service_tokens",
        link_state.link_count,
        require_integral=True,
        require_non_negative=True,
    )
    check_vector(
        link_state.metadata,
        "runtime_link_receiving_tokens",
        link_state.link_count,
        require_integral=True,
        require_non_negative=True,
    )
    check_vector(
        link_state.metadata,
        "runtime_link_service_residual",
        link_state.link_count,
        unit_residual=True,
    )
    authority_version = int(
        link_state.metadata.get("runtime_token_authority_version", 1)
    )
    if authority_version >= 2:
        check_vector(
            link_state.metadata,
            "runtime_link_service_token_carry",
            link_state.link_count,
            require_integral=True,
            require_non_negative=True,
            upper_bound=1.0,
        )
    check_vector(
        link_state.metadata,
        "runtime_link_receiving_residual",
        link_state.link_count,
        unit_residual=True,
    )
    if authority_version >= 2:
        check_vector(
            link_state.metadata,
            "runtime_link_receiving_token_carry",
            link_state.link_count,
            require_integral=True,
            require_non_negative=True,
            upper_bound=1.0,
        )
    link_sink_flow = check_vector(
        link_state.metadata,
        "runtime_sink_flow_vehicles",
        link_state.link_count,
        require_integral=True,
        require_non_negative=True,
    )
    if not isinstance(node_state, NodeState):
        add_invalid("flow_node_state", "missing_node_state")
        return tuple(violations)

    check_vector(
        node_state.metadata,
        "runtime_turn_flow_residual",
        node_state.turn_count,
    )
    check_vector(
        node_state.metadata,
        "runtime_sink_flow_residual",
        link_state.link_count,
    )
    node_sink_flow = check_vector(
        node_state.metadata,
        "runtime_sink_flow_by_link_index",
        link_state.link_count,
        require_integral=True,
        require_non_negative=True,
    )
    if (
        link_sink_flow is not None
        and node_sink_flow is not None
        and not bool(np.array_equal(link_sink_flow, node_sink_flow))
    ):
        add_invalid(
            "runtime_sink_flow_by_link_index",
            "link_node_sink_flow_mismatch",
        )
    turn_flow = np.asarray(node_state.turn_flow, dtype=np.float32)
    if not bool(np.all(np.isfinite(turn_flow))):
        add_invalid(
            "turn_flow",
            "non_finite",
            non_finite_count=int(np.sum(~np.isfinite(turn_flow))),
        )
    elif bool(np.any(np.abs(turn_flow - np.rint(turn_flow)) > 1.0e-6)):
        add_invalid("turn_flow", "non_integral")
    inflow = np.asarray(link_state.inflow_vehicles, dtype=np.float32)
    outflow = np.asarray(link_state.outflow_vehicles, dtype=np.float32)
    queue = np.asarray(link_state.queue_vehicles, dtype=np.float32)
    for key, values in (
        ("inflow_vehicles", inflow),
        ("outflow_vehicles", outflow),
        ("queue_vehicles", queue),
    ):
        if not bool(np.all(np.isfinite(values))):
            add_invalid(
                key,
                "non_finite",
                non_finite_count=int(np.sum(~np.isfinite(values))),
            )
    if turn_flow.shape == (node_state.turn_count,):
        internal_outflow = np.zeros((link_state.link_count,), dtype=np.float32)
        internal_inflow = np.zeros((link_state.link_count,), dtype=np.float32)
        np.add.at(internal_outflow, node_state.turn_from_link_index, turn_flow)
        np.add.at(internal_inflow, node_state.turn_to_link_index, turn_flow)
        if link_sink_flow is not None and not bool(
            np.array_equal(outflow, internal_outflow + link_sink_flow)
        ):
            add_invalid("outflow_vehicles", "turn_and_sink_flow_mismatch")
        if not bool(np.array_equal(inflow, internal_inflow)):
            add_invalid("inflow_vehicles", "turn_flow_mismatch")

    transition_active = bool(
        state.dynamic.metadata.get("runtime_transition_authority_active", False)
    )
    transition_tick = int(
        state.dynamic.metadata.get("runtime_transition_counter_tick", -1)
    )
    if transition_active and transition_tick == int(state.tick_index):
        input_queue = check_vector(
            link_state.metadata,
            "runtime_flow_input_queue_vehicles",
            link_state.link_count,
            require_non_negative=True,
        )
        witness_tick = int(link_state.metadata.get("runtime_transition_tick", -1))
        if witness_tick != int(state.tick_index):
            add_invalid(
                "runtime_transition_tick",
                "tick_mismatch",
                expected_tick=int(state.tick_index),
                actual_tick=witness_tick,
            )
        if input_queue is not None and bool(np.all(np.isfinite(input_queue))):
            expected_queue = input_queue - outflow + inflow
            mismatch = np.nonzero(np.abs(queue - expected_queue) > 1.0e-6)[0]
            if mismatch.size:
                add_invalid(
                    "queue_vehicles",
                    "transition_mass_mismatch",
                    mismatch_count=int(mismatch.size),
                    first_link_index=int(mismatch[0]),
                )
        completed_count = int(
            state.dynamic.metadata.get(
                "runtime_transition_completed_trip_count",
                0,
            )
        )
        sink_flow_total = int(
            np.rint(np.sum(link_sink_flow)) if link_sink_flow is not None else 0
        )
        if completed_count != sink_flow_total:
            add_invalid(
                "runtime_transition_completed_trip_count",
                "sink_completion_mismatch",
                completed_trip_count=completed_count,
                sink_flow_total=sink_flow_total,
            )
    return tuple(violations)


def _validate_active_agent_pool_fast(pool: ActiveAgentPool) -> tuple[str, ...]:
    issues: list[str] = []

    alive_mask = np.asarray(pool.alive_mask, dtype=np.bool_)
    alive_count_from_mask = int(np.sum(alive_mask))
    if int(pool.alive_count) != alive_count_from_mask:
        issues.append("alive_count != sum(alive_mask)")

    if int(pool.free_slot_count) + int(pool.alive_count) != int(pool.capacity):
        issues.append("free_slot_count + alive_count != capacity")

    free_stack = np.asarray(pool.free_slot_stack, dtype=np.int32)
    free_slot_count = int(pool.free_slot_count)
    free_ids = tuple(int(x) for x in free_stack[:free_slot_count].tolist())
    if len(set(free_ids)) != len(free_ids):
        issues.append("duplicate slot ids in free_slot_stack")
    if any(slot_id < 0 or slot_id >= int(pool.capacity) for slot_id in free_ids):
        issues.append("free_slot_stack contains out-of-range slot ids")

    alive_ids = {idx for idx, is_alive in enumerate(alive_mask.tolist()) if bool(is_alive)}
    if alive_ids.intersection(free_ids):
        issues.append("slot ids appear in both alive set and free_slot_stack")

    for slot_id in sorted(alive_ids):
        memory = pool.plugin_memory.get(int(slot_id))
        if not isinstance(memory, Mapping):
            issues.append(f"alive slot {slot_id} has no route plugin memory")
            continue
        try:
            memory_trip_id = int(memory.get("trip_request_id"))
        except (TypeError, ValueError):
            issues.append(f"alive slot {slot_id} has invalid route-memory trip id")
            continue
        packed_trip_id = int(pool.trip_id[slot_id])
        if memory_trip_id != packed_trip_id:
            issues.append(
                f"alive slot {slot_id} route-memory trip id != packed trip id"
            )

    progress = np.asarray(pool.progress_01, dtype=np.float32)
    if not bool(np.all(np.isfinite(progress))):
        issues.append("progress_01 contains non-finite values")
    elif bool(np.any(progress < 0.0)) or bool(np.any(progress > 1.0)):
        issues.append("progress_01 contains values outside [0, 1]")

    cooldown = np.asarray(pool.reroute_cooldown_ticks, dtype=np.int32)
    if bool(np.any(cooldown < 0)):
        issues.append("reroute_cooldown_ticks contains negative values")

    return tuple(issues)


def _check_runtime_vehicle_queue_authority(
    state: SimulationState,
) -> tuple[InvariantViolation, ...] | None:
    link_state = state.dynamic.flow_link_state
    pool = state.dynamic.active_agent_pool
    routing_static = state.static.routing_static
    road_csr = (
        routing_static.get("road_csr")
        if isinstance(routing_static, Mapping)
        else getattr(routing_static, "road_csr", None)
    )
    if (
        not isinstance(link_state, LinkState)
        or not bool(link_state.metadata.get("runtime_discrete_agent_authority", False))
        or not isinstance(pool, ActiveAgentPool)
        or road_csr is None
    ):
        return None
    link_id_to_index = dict(getattr(road_csr, "link_id_to_index", {}) or {})
    expected = np.zeros((link_state.link_count,), dtype=np.float32)
    alive_mask = np.asarray(pool.alive_mask, dtype=np.bool_)
    for slot_id, alive in enumerate(alive_mask.tolist()):
        if not bool(alive):
            continue
        link_id = int(pool.current_link_id[slot_id])
        link_index = link_id_to_index.get(link_id)
        if link_index is None:
            return (
                InvariantViolation(
                    code="active_agent_unknown_link",
                    check_name="runtime_vehicle_queue_authority",
                    message="Active agent references a link absent from the runtime network",
                    details={"slot_id": int(slot_id), "link_id": link_id},
                ),
            )
        expected[int(link_index)] += np.float32(1.0)
    observed = np.asarray(link_state.queue_vehicles, dtype=np.float32)
    if not bool(np.all(np.isfinite(observed))):
        return (
            InvariantViolation(
                code="runtime_vehicle_queue_non_finite",
                check_name="runtime_vehicle_queue_authority",
                message="Per-link queue authority must be finite",
                details={
                    "non_finite_count": int(np.sum(~np.isfinite(observed))),
                },
            ),
        )
    mismatch = np.nonzero(np.abs(observed - expected) > 1.0e-6)[0]
    if mismatch.size == 0:
        return ()
    first = int(mismatch[0])
    return (
        InvariantViolation(
            code="runtime_vehicle_queue_mismatch",
            check_name="runtime_vehicle_queue_authority",
            message="Per-link queue vehicles must equal resident active agents",
            details={
                "mismatch_count": int(mismatch.size),
                "first_link_index": first,
                "observed_queue": float(observed[first]),
                "expected_active_agents": float(expected[first]),
                "queue_total": float(np.sum(observed)),
                "active_agent_total": int(pool.alive_count),
            },
        ),
    )


def _check_runtime_finite_link_storage(
    state: SimulationState,
) -> tuple[InvariantViolation, ...] | None:
    if state.config.traffic_model != "spatial_queue_v1":
        return None
    link_state = state.dynamic.flow_link_state
    if not isinstance(link_state, LinkState):
        return (
            InvariantViolation(
                code="finite_link_storage_authority_missing",
                check_name="finite_link_storage",
                message="Spatial traffic mode requires link-state storage authority",
            ),
        )
    storage = link_state.metadata.get("storage_capacity_vehicles")
    if storage is None:
        return (
            InvariantViolation(
                code="finite_link_storage_authority_missing",
                check_name="finite_link_storage",
                message="Spatial traffic mode requires per-link storage capacity",
            ),
        )
    return check_finite_link_storage(link_state.queue_vehicles, storage)


def _extract_conservation_snapshot(state: SimulationState) -> ConservationSnapshot | None:
    dynamic = state.dynamic
    lifecycle = _trip_lifecycle_sets(state)
    if lifecycle is not None:
        generated_ids, pending_ids, active_ids, completed_ids, failed_ids = lifecycle
        return ConservationSnapshot(
            generated_total=len(generated_ids),
            pending_trip_requests=len(pending_ids),
            active_agents=len(active_ids),
            completed_trips_total=len(completed_ids),
            failed_trips_total=len(failed_ids),
        )

    metrics_state = dynamic.metrics_state
    active_agents = _lookup_attr_or_key(dynamic.active_agent_pool, "alive_count")
    generated_total = _lookup_first(
        metrics_state, dynamic.invariant_state, keys=("generated_trip_total",)
    )
    pending_trip_requests = _lookup_first(
        dynamic.demand_state, metrics_state, keys=("pending_trip_requests",)
    )
    completed_total = _lookup_first(metrics_state, keys=("completed_trips_total",))
    failed_total = _lookup_first(metrics_state, keys=("failed_trips_total",))
    if any(
        value is None
        for value in (
            generated_total,
            pending_trip_requests,
            active_agents,
            completed_total,
            failed_total,
        )
    ):
        return None
    return ConservationSnapshot(
        generated_total=int(generated_total),
        pending_trip_requests=int(pending_trip_requests),
        active_agents=int(active_agents),
        completed_trips_total=int(completed_total),
        failed_trips_total=int(failed_total),
    )


def _trip_lifecycle_sets(
    state: SimulationState,
) -> tuple[set[int], set[int], set[int], set[int], set[int]] | None:
    demand_state = state.dynamic.demand_state
    pool = state.dynamic.active_agent_pool
    if not isinstance(demand_state, Mapping) or "trip_requests" not in demand_state:
        return None
    if not isinstance(pool, ActiveAgentPool):
        return None
    trips = tuple(demand_state.get("trip_requests", ()))
    generated_ids = {
        int(_lookup_attr_or_key(trip, "trip_request_id"))
        for trip in trips
    }
    allocated_ids = {
        int(value) for value in tuple(demand_state.get("allocated_trip_request_ids", ()))
    }
    completed_ids = {
        int(value) for value in tuple(demand_state.get("completed_trip_request_ids", ()))
    }
    failed_ids = {
        int(value) for value in tuple(demand_state.get("failed_trip_request_ids", ()))
    }
    alive_mask = np.asarray(pool.alive_mask, dtype=np.bool_)
    active_ids = {
        int(pool.trip_id[index])
        for index, alive in enumerate(alive_mask.tolist())
        if bool(alive)
    }
    pending_ids: set[int] = set()
    for trip in trips:
        trip_id = int(_lookup_attr_or_key(trip, "trip_request_id"))
        status = _lookup_attr_or_key(trip, "status")
        status_value = str(getattr(status, "value", status))
        if (
            status_value in {"queued", "activated"}
            and trip_id not in allocated_ids
            and trip_id not in completed_ids
            and trip_id not in failed_ids
        ):
            pending_ids.add(trip_id)
    return generated_ids, pending_ids, active_ids, completed_ids, failed_ids


def _check_trip_lifecycle_disjoint(
    state: SimulationState,
) -> tuple[InvariantViolation, ...] | None:
    lifecycle = _trip_lifecycle_sets(state)
    if lifecycle is None:
        return None
    generated_ids, pending_ids, active_ids, completed_ids, failed_ids = lifecycle
    stages = {
        "pending": pending_ids,
        "active": active_ids,
        "completed": completed_ids,
        "failed": failed_ids,
    }
    violations: list[InvariantViolation] = []
    names = tuple(stages)
    for left_index, left_name in enumerate(names):
        for right_name in names[left_index + 1 :]:
            overlap = stages[left_name].intersection(stages[right_name])
            if overlap:
                violations.append(
                    InvariantViolation(
                        code="trip_lifecycle_overlap",
                        check_name="trip_lifecycle_disjoint",
                        message="Trip lifecycle stages must be pairwise disjoint",
                        details={
                            "left_stage": left_name,
                            "right_stage": right_name,
                            "trip_request_ids": tuple(sorted(overlap)),
                        },
                    )
                )
    staged_ids = pending_ids | active_ids | completed_ids | failed_ids
    if staged_ids != generated_ids:
        violations.append(
            InvariantViolation(
                code="trip_lifecycle_partition_mismatch",
                check_name="trip_lifecycle_disjoint",
                message="Trip lifecycle stages must partition generated request ids",
                details={
                    "missing_ids": tuple(sorted(generated_ids - staged_ids)),
                    "unknown_ids": tuple(sorted(staged_ids - generated_ids)),
                },
            )
        )
    demand_state = state.dynamic.demand_state
    declared_pending = int(demand_state.get("pending_trip_requests", len(pending_ids)))
    if declared_pending != len(pending_ids):
        violations.append(
            InvariantViolation(
                code="pending_trip_count_mismatch",
                check_name="trip_lifecycle_disjoint",
                message="pending_trip_requests does not match the unadmitted pending id set",
                details={
                    "declared_pending": declared_pending,
                    "derived_pending": len(pending_ids),
                },
            )
        )
    return tuple(violations)


def _lookup_first(*sources: Any, keys: tuple[str, ...]) -> Any | None:
    for source in sources:
        for key in keys:
            value = _lookup_attr_or_key(source, key)
            if value is not None:
                return value
    return None


def _lookup_attr_or_key(source: Any, key: str) -> Any | None:
    if source is None:
        return None
    if isinstance(source, Mapping):
        return source.get(key)
    try:
        return getattr(source, key)
    except AttributeError:
        return None
