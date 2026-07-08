"""Invariant validation/report structures and core checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

import numpy as np

from metroflow.flow.state import LinkState
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


def check_capacity_violation_flags(
    outflow_values: Iterable[float] | Any,
    effective_capacity_values: Iterable[float] | Any,
    *,
    flagged_count: int | None = None,
    tolerance: float = 1e-6,
) -> tuple[InvariantViolation, ...]:
    """Check capacity exceedances and optional flag-count accounting."""

    outflow = np.asarray(outflow_values, dtype=np.float32)
    capacity = np.asarray(effective_capacity_values, dtype=np.float32)
    if outflow.shape != capacity.shape:
        raise ValueError("outflow_values and effective_capacity_values must have same shape")

    exceed_mask = outflow > (capacity + float(tolerance))
    exceed_count = int(np.sum(exceed_mask))
    if flagged_count is None:
        return ()
    flagged_count = int(flagged_count)
    if flagged_count < 0:
        raise ValueError("flagged_count must be >= 0")
    if flagged_count == exceed_count:
        return ()

    return (
        InvariantViolation(
            code="capacity_flag_count_mismatch",
            check_name="capacity_flags",
            message="Capacity violation counter does not match observed exceedances",
            details={
                "observed_exceed_count": exceed_count,
                "flagged_count": flagged_count,
                "tolerance": float(tolerance),
            },
        ),
    )


def validate_invariants(state: SimulationState) -> InvariantReport:
    """Validate core invariants from a `SimulationState` using available refs.

    This is a foundational, duck-typed validator. It runs checks opportunistically
    when referenced state pieces exist and records skipped checks otherwise.
    """

    checks_run: list[str] = []
    checks_skipped: list[str] = []
    violations: list[InvariantViolation] = []

    dynamic = state.dynamic
    metrics_state = dynamic.metrics_state
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

    checks_run.append("capacity_flags")
    outflow_values = _lookup_attr_or_key(dynamic.flow_link_state, "outflow_vehicles")
    capacity_values = _resolve_effective_capacity_values(dynamic.flow_link_state)
    if outflow_values is None or capacity_values is None:
        checks_skipped.append("capacity_flags")
        checks_run.pop()
    else:
        flagged_count = _lookup_attr_or_key(metrics_state, "capacity_violation_count")
        violations.extend(
            check_capacity_violation_flags(
                outflow_values,
                capacity_values,
                flagged_count=flagged_count,
            )
        )

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

    progress = np.asarray(pool.progress_01, dtype=np.float32)
    if bool(np.any(progress < 0.0)) or bool(np.any(progress > 1.0)):
        issues.append("progress_01 contains values outside [0, 1]")

    cooldown = np.asarray(pool.reroute_cooldown_ticks, dtype=np.int32)
    if bool(np.any(cooldown < 0)):
        issues.append("reroute_cooldown_ticks contains negative values")

    return tuple(issues)


def _extract_conservation_snapshot(state: SimulationState) -> ConservationSnapshot | None:
    dynamic = state.dynamic
    metrics_state = dynamic.metrics_state

    active_agents = _lookup_attr_or_key(dynamic.active_agent_pool, "alive_count")
    if active_agents is None and isinstance(dynamic.active_agent_pool, ActiveAgentPool):
        active_agents = dynamic.active_agent_pool.alive_count

    generated_total = _lookup_first(
        metrics_state,
        dynamic.invariant_state,
        dynamic.metadata,
        state.metadata,
        keys=("generated_trip_total", "trip_generation_total"),
    )
    pending_trip_requests = _lookup_first(
        dynamic.demand_state,
        metrics_state,
        dynamic.metadata,
        state.metadata,
        keys=("pending_trip_requests", "queued_trip_requests"),
    )
    completed_total = _lookup_first(
        metrics_state,
        dynamic.invariant_state,
        keys=("completed_trips_total",),
    )
    failed_total = _lookup_first(
        metrics_state,
        dynamic.invariant_state,
        keys=("failed_trips_total",),
    )

    values = (
        generated_total,
        pending_trip_requests,
        active_agents,
        completed_total,
        failed_total,
    )
    if any(value is None for value in values):
        return None
    return ConservationSnapshot(
        generated_total=int(generated_total),
        pending_trip_requests=int(pending_trip_requests),
        active_agents=int(active_agents),
        completed_trips_total=int(completed_total),
        failed_trips_total=int(failed_total),
    )


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
