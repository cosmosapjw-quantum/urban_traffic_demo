"""Simulation control input and telemetry dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Mapping

from metroflow.sim.config import DayType, TimeBand

__all__ = [
    "SimulationControl",
    "SimulationTelemetry",
]


@dataclass(slots=True)
class SimulationControl:
    """Per-tick control input for the simulation step contract."""

    pause: bool = False
    set_day_type: DayType | None = None
    set_time_band: TimeBand | None = None
    inject_event: Any | tuple[Any, ...] | None = None
    clear_event_ids: tuple[int, ...] = field(default_factory=tuple)
    ui_force_snapshot: bool = False

    def __post_init__(self) -> None:
        if self.set_day_type is not None:
            self.set_day_type = DayType(self.set_day_type)
        if self.set_time_band is not None:
            self.set_time_band = TimeBand(self.set_time_band)
        self.pause = bool(self.pause)
        self.ui_force_snapshot = bool(self.ui_force_snapshot)
        self.clear_event_ids = tuple(int(event_id) for event_id in self.clear_event_ids)
        if any(event_id < 0 for event_id in self.clear_event_ids):
            raise ValueError("clear_event_ids must contain non-negative ids")
        if self.inject_event is not None and isinstance(self.inject_event, list):
            self.inject_event = tuple(self.inject_event)

    @classmethod
    def noop(cls) -> "SimulationControl":
        """Return a control object representing no requested changes."""

        return cls()

    def is_noop(self) -> bool:
        """Whether this control carries no mutation or UI requests."""

        return (
            not self.pause
            and self.set_day_type is None
            and self.set_time_band is None
            and self.inject_event is None
            and not self.clear_event_ids
            and not self.ui_force_snapshot
        )


@dataclass(slots=True)
class SimulationTelemetry:
    """Per-tick telemetry emitted by the simulation step contract."""

    tick_index: int
    active_agent_count: int
    trip_generated_this_tick: int = 0
    trip_completed_this_tick: int = 0
    trip_failed_this_tick: int = 0
    capacity_violation_count_delta: int = 0
    negative_queue_detected: bool = False
    policy_mix_lambda: float = 0.0
    adaptive_fallback_triggered: bool = False
    ui_snapshot_emitted: bool = False
    flow_backend: str = "baseline"
    routing_backend: str = "baseline"
    agent_backend: str = "baseline"
    flow_update_wall_ns: int = 0
    active_agent_update_wall_ns: int = 0
    reroute_decision_wall_ns: int = 0
    queue_vehicles_total: float = 0.0
    outflow_vehicles_total: float = 0.0
    route_candidate_refresh_total: int = 0
    route_candidate_reuse_total: int = 0
    dynamic_potential_recompute_total: int = 0
    dynamic_potential_cache_hits_total: int = 0
    dynamic_potential_cache_pruned_total: int = 0
    dynamic_potential_cache_entry_count: int = 0
    active_agent_moved_this_tick: int = 0
    active_agent_sink_wait_this_tick: int = 0
    active_agent_rerouted_this_tick: int = 0
    active_agent_reroute_cooldown_this_tick: int = 0

    def __post_init__(self) -> None:
        self.tick_index = int(self.tick_index)
        self.active_agent_count = int(self.active_agent_count)
        self.trip_generated_this_tick = int(self.trip_generated_this_tick)
        self.trip_completed_this_tick = int(self.trip_completed_this_tick)
        self.trip_failed_this_tick = int(self.trip_failed_this_tick)
        self.capacity_violation_count_delta = int(self.capacity_violation_count_delta)
        self.policy_mix_lambda = float(self.policy_mix_lambda)
        self.negative_queue_detected = bool(self.negative_queue_detected)
        self.adaptive_fallback_triggered = bool(self.adaptive_fallback_triggered)
        self.ui_snapshot_emitted = bool(self.ui_snapshot_emitted)
        self.flow_backend = str(self.flow_backend)
        self.routing_backend = str(self.routing_backend)
        self.agent_backend = str(self.agent_backend)
        self.flow_update_wall_ns = int(self.flow_update_wall_ns)
        self.active_agent_update_wall_ns = int(self.active_agent_update_wall_ns)
        self.reroute_decision_wall_ns = int(self.reroute_decision_wall_ns)
        self.queue_vehicles_total = float(self.queue_vehicles_total)
        self.outflow_vehicles_total = float(self.outflow_vehicles_total)
        self.route_candidate_refresh_total = int(self.route_candidate_refresh_total)
        self.route_candidate_reuse_total = int(self.route_candidate_reuse_total)
        self.dynamic_potential_recompute_total = int(self.dynamic_potential_recompute_total)
        self.dynamic_potential_cache_hits_total = int(self.dynamic_potential_cache_hits_total)
        self.dynamic_potential_cache_pruned_total = int(
            self.dynamic_potential_cache_pruned_total
        )
        self.dynamic_potential_cache_entry_count = int(
            self.dynamic_potential_cache_entry_count
        )
        self.active_agent_moved_this_tick = int(self.active_agent_moved_this_tick)
        self.active_agent_sink_wait_this_tick = int(self.active_agent_sink_wait_this_tick)
        self.active_agent_rerouted_this_tick = int(self.active_agent_rerouted_this_tick)
        self.active_agent_reroute_cooldown_this_tick = int(
            self.active_agent_reroute_cooldown_this_tick
        )

        _validate_non_negative(self.tick_index, "tick_index")
        _validate_non_negative(self.active_agent_count, "active_agent_count")
        _validate_non_negative(self.trip_generated_this_tick, "trip_generated_this_tick")
        _validate_non_negative(self.trip_completed_this_tick, "trip_completed_this_tick")
        _validate_non_negative(self.trip_failed_this_tick, "trip_failed_this_tick")
        _validate_non_negative(
            self.capacity_violation_count_delta,
            "capacity_violation_count_delta",
        )
        _validate_non_negative(self.flow_update_wall_ns, "flow_update_wall_ns")
        _validate_non_negative(
            self.active_agent_update_wall_ns,
            "active_agent_update_wall_ns",
        )
        _validate_non_negative(
            self.reroute_decision_wall_ns,
            "reroute_decision_wall_ns",
        )
        _validate_non_negative(
            self.route_candidate_refresh_total,
            "route_candidate_refresh_total",
        )
        _validate_non_negative(
            self.route_candidate_reuse_total,
            "route_candidate_reuse_total",
        )
        _validate_non_negative(
            self.dynamic_potential_recompute_total,
            "dynamic_potential_recompute_total",
        )
        _validate_non_negative(
            self.dynamic_potential_cache_hits_total,
            "dynamic_potential_cache_hits_total",
        )
        _validate_non_negative(
            self.dynamic_potential_cache_pruned_total,
            "dynamic_potential_cache_pruned_total",
        )
        _validate_non_negative(
            self.dynamic_potential_cache_entry_count,
            "dynamic_potential_cache_entry_count",
        )
        _validate_non_negative(
            self.active_agent_moved_this_tick,
            "active_agent_moved_this_tick",
        )
        _validate_non_negative(
            self.active_agent_sink_wait_this_tick,
            "active_agent_sink_wait_this_tick",
        )
        _validate_non_negative(
            self.active_agent_rerouted_this_tick,
            "active_agent_rerouted_this_tick",
        )
        _validate_non_negative(
            self.active_agent_reroute_cooldown_this_tick,
            "active_agent_reroute_cooldown_this_tick",
        )
        if self.queue_vehicles_total < 0.0:
            raise ValueError("queue_vehicles_total must be >= 0")
        if self.outflow_vehicles_total < 0.0:
            raise ValueError("outflow_vehicles_total must be >= 0")
        if not 0.0 <= self.policy_mix_lambda <= 1.0:
            raise ValueError("policy_mix_lambda must be in [0, 1]")

    def as_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict with stable contract key names."""

        return {
            "tick_index": self.tick_index,
            "active_agent_count": self.active_agent_count,
            "trip_generated_this_tick": self.trip_generated_this_tick,
            "trip_completed_this_tick": self.trip_completed_this_tick,
            "trip_failed_this_tick": self.trip_failed_this_tick,
            "capacity_violation_count_delta": self.capacity_violation_count_delta,
            "negative_queue_detected": self.negative_queue_detected,
            "policy_mix_lambda": self.policy_mix_lambda,
            "adaptive_fallback_triggered": self.adaptive_fallback_triggered,
            "ui_snapshot_emitted": self.ui_snapshot_emitted,
            "flow_backend": self.flow_backend,
            "routing_backend": self.routing_backend,
            "agent_backend": self.agent_backend,
            "flow_update_wall_ns": self.flow_update_wall_ns,
            "active_agent_update_wall_ns": self.active_agent_update_wall_ns,
            "reroute_decision_wall_ns": self.reroute_decision_wall_ns,
            "queue_vehicles_total": self.queue_vehicles_total,
            "outflow_vehicles_total": self.outflow_vehicles_total,
            "route_candidate_refresh_total": self.route_candidate_refresh_total,
            "route_candidate_reuse_total": self.route_candidate_reuse_total,
            "dynamic_potential_recompute_total": self.dynamic_potential_recompute_total,
            "dynamic_potential_cache_hits_total": self.dynamic_potential_cache_hits_total,
            "dynamic_potential_cache_pruned_total": self.dynamic_potential_cache_pruned_total,
            "dynamic_potential_cache_entry_count": self.dynamic_potential_cache_entry_count,
            "active_agent_moved_this_tick": self.active_agent_moved_this_tick,
            "active_agent_sink_wait_this_tick": self.active_agent_sink_wait_this_tick,
            "active_agent_rerouted_this_tick": self.active_agent_rerouted_this_tick,
            "active_agent_reroute_cooldown_this_tick": self.active_agent_reroute_cooldown_this_tick,
        }

    def as_replay_dict(self) -> dict[str, Any]:
        """Serialize deterministic telemetry fields, excluding wall-clock diagnostics."""

        payload = self.as_dict()
        for key in (
            "flow_update_wall_ns",
            "active_agent_update_wall_ns",
            "reroute_decision_wall_ns",
        ):
            payload.pop(key, None)
        return payload

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "SimulationTelemetry":
        """Construct telemetry from a mapping with contract field names."""

        missing = tuple(key for key in cls.required_keys() if key not in data)
        if missing:
            raise KeyError(f"missing telemetry keys: {', '.join(missing)}")
        known_fields = tuple(item.name for item in fields(cls))
        return cls(**{key: data[key] for key in known_fields if key in data})

    @staticmethod
    def required_keys() -> tuple[str, ...]:
        """Return the expected telemetry keys from the step contract."""

        return (
            "tick_index",
            "active_agent_count",
            "trip_generated_this_tick",
            "trip_completed_this_tick",
            "trip_failed_this_tick",
            "capacity_violation_count_delta",
            "negative_queue_detected",
            "policy_mix_lambda",
            "adaptive_fallback_triggered",
            "ui_snapshot_emitted",
        )


def _validate_non_negative(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
