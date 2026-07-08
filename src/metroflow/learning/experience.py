"""Simulator-only experience extraction for online learning updates (T065)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from metroflow.sim.control import SimulationTelemetry
from metroflow.sim.state import SimulationState

__all__ = [
    "LearningExperience",
    "create_learning_experience",
    "build_learning_experience",
    "compute_trip_outcome_reward",
    "extract_online_experience_batch",
    "build_experience_batch",
]


@dataclass(slots=True)
class LearningExperience:
    """One simulator-derived online learning sample for a completed/failed trip."""

    tick_index: int
    od_key: tuple[Any, Any]
    trip_id: int
    outcome: str
    reward: float
    chosen_candidate_id: int | None = None
    chosen_arm_index: int | None = None
    observed_travel_time: float | None = None
    policy_mix_lambda: float = 0.0
    adaptive_fallback_triggered: bool = False
    context_summary: dict[str, Any] = field(default_factory=dict)
    event_context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tick_index = int(self.tick_index)
        self.od_key = tuple(self.od_key)  # type: ignore[assignment]
        self.trip_id = int(self.trip_id)
        self.outcome = str(self.outcome).strip().lower()
        self.reward = float(self.reward)
        if self.chosen_candidate_id is not None:
            self.chosen_candidate_id = int(self.chosen_candidate_id)
        if self.chosen_arm_index is not None:
            self.chosen_arm_index = int(self.chosen_arm_index)
        if self.observed_travel_time is not None:
            self.observed_travel_time = float(self.observed_travel_time)
        self.policy_mix_lambda = float(self.policy_mix_lambda)
        self.adaptive_fallback_triggered = bool(self.adaptive_fallback_triggered)
        if not isinstance(self.context_summary, dict):
            self.context_summary = dict(self.context_summary)
        if not isinstance(self.event_context, dict):
            self.event_context = dict(self.event_context)
        if not isinstance(self.metadata, dict):
            self.metadata = dict(self.metadata)

        if self.tick_index < 0:
            raise ValueError("tick_index must be >= 0")
        if len(self.od_key) != 2:
            raise ValueError("od_key must contain exactly (origin, destination)")
        if self.trip_id < 0:
            raise ValueError("trip_id must be >= 0")
        if self.outcome not in {"completed", "failed"}:
            raise ValueError("outcome must be one of {'completed', 'failed'}")
        if not (-1.0 <= self.reward <= 1.0):
            raise ValueError("reward must be in [-1, 1]")
        if self.observed_travel_time is not None and self.observed_travel_time < 0.0:
            raise ValueError("observed_travel_time must be >= 0")
        if not 0.0 <= self.policy_mix_lambda <= 1.0:
            raise ValueError("policy_mix_lambda must be in [0, 1]")


def compute_trip_outcome_reward(
    *,
    outcome: str,
    observed_travel_time: float | None = None,
    baseline_travel_time: float | None = None,
) -> float:
    """Map simulator trip outcomes into a bounded reproducible reward signal.

    Completed trips receive a positive reward in `(0, 1]` that decays with
    travel time. Failed trips receive a negative reward in `[-1, 0)`.
    """

    outcome_key = str(outcome).strip().lower()
    travel_time = None if observed_travel_time is None else max(0.0, float(observed_travel_time))
    baseline_time = None if baseline_travel_time is None else max(1.0e-6, float(baseline_travel_time))

    if outcome_key == "completed":
        if travel_time is None:
            return 1.0
        if baseline_time is not None:
            ratio = travel_time / baseline_time
            return max(0.0, min(1.0, 1.0 / (1.0 + ratio)))
        return max(0.0, min(1.0, 1.0 / (1.0 + travel_time)))
    if outcome_key == "failed":
        if travel_time is None:
            return -1.0
        if baseline_time is not None:
            ratio = travel_time / baseline_time
            return max(-1.0, min(0.0, -1.0 + (1.0 / (1.0 + ratio))))
        return max(-1.0, min(0.0, -1.0 + (1.0 / (1.0 + travel_time))))
    raise ValueError("outcome must be one of {'completed', 'failed'}")


def create_learning_experience(
    *,
    tick_index: int,
    od_key: tuple[Any, Any],
    trip_id: int,
    outcome: str,
    chosen_candidate_id: int | None = None,
    chosen_arm_index: int | None = None,
    observed_travel_time: float | None = None,
    baseline_travel_time: float | None = None,
    policy_mix_lambda: float = 0.0,
    adaptive_fallback_triggered: bool = False,
    context_summary: Mapping[str, Any] | None = None,
    event_context: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> LearningExperience:
    """Create a validated simulator-only learning sample."""

    reward = compute_trip_outcome_reward(
        outcome=outcome,
        observed_travel_time=observed_travel_time,
        baseline_travel_time=baseline_travel_time,
    )
    return LearningExperience(
        tick_index=tick_index,
        od_key=od_key,
        trip_id=trip_id,
        outcome=outcome,
        reward=reward,
        chosen_candidate_id=chosen_candidate_id,
        chosen_arm_index=chosen_arm_index,
        observed_travel_time=observed_travel_time,
        policy_mix_lambda=policy_mix_lambda,
        adaptive_fallback_triggered=adaptive_fallback_triggered,
        context_summary={} if context_summary is None else dict(context_summary),
        event_context={} if event_context is None else dict(event_context),
        metadata={} if metadata is None else dict(metadata),
    )


def build_learning_experience(**kwargs) -> LearningExperience:
    """Alias for `create_learning_experience`."""

    return create_learning_experience(**kwargs)


def extract_online_experience_batch(
    *,
    state: SimulationState | Mapping[str, Any],
    telemetry: SimulationTelemetry | Mapping[str, Any] | None = None,
    outcome_rows: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = (),
) -> tuple[LearningExperience, ...]:
    """Extract online-only learning samples from simulator outcomes.

    `outcome_rows` is the handoff boundary from the step loop and should contain
    only completed/failed trip outcomes plus any chosen route identifiers known
    at decision time. If no outcomes are available this returns an empty batch.
    """

    sim_state = _coerce_state(state)
    telemetry_obj = _coerce_telemetry(telemetry, fallback_tick=sim_state.tick_index)
    context_summary = _build_context_summary(sim_state, telemetry_obj)
    event_context = _build_event_context(sim_state)

    experiences: list[LearningExperience] = []
    for raw in outcome_rows:
        outcome = str(raw.get("outcome", "")).strip().lower()
        if outcome not in {"completed", "failed"}:
            continue
        raw_context_summary = raw.get("context_summary")
        row_context = (
            context_summary
            if not raw_context_summary
            else {**context_summary, **dict(raw_context_summary)}
        )
        raw_event_context = raw.get("event_context")
        row_event_context = (
            event_context
            if not raw_event_context
            else {**event_context, **dict(raw_event_context)}
        )
        raw_metadata = raw.get("metadata")
        try:
            experiences.append(
                create_learning_experience(
                    tick_index=int(raw.get("tick_index", telemetry_obj.tick_index)),
                    od_key=tuple(raw.get("od_key", ())),
                    trip_id=int(raw.get("trip_id")),
                    outcome=outcome,
                    chosen_candidate_id=_optional_int(raw.get("chosen_candidate_id")),
                    chosen_arm_index=_optional_int(raw.get("chosen_arm_index")),
                    observed_travel_time=_optional_float(raw.get("observed_travel_time")),
                    baseline_travel_time=_optional_float(raw.get("baseline_travel_time")),
                    policy_mix_lambda=float(raw.get("policy_mix_lambda", telemetry_obj.policy_mix_lambda)),
                    adaptive_fallback_triggered=bool(
                        raw.get("adaptive_fallback_triggered", telemetry_obj.adaptive_fallback_triggered)
                    ),
                    context_summary=row_context,
                    event_context=row_event_context,
                    metadata={} if raw_metadata is None else dict(raw_metadata),
                )
            )
        except (TypeError, ValueError):
            continue
    return tuple(experiences)


def build_experience_batch(**kwargs) -> tuple[LearningExperience, ...]:
    """Alias for `extract_online_experience_batch`."""

    return extract_online_experience_batch(**kwargs)


def _coerce_state(state: SimulationState | Mapping[str, Any]) -> SimulationState:
    if isinstance(state, SimulationState):
        return state
    return SimulationState(**dict(state))


def _coerce_telemetry(
    telemetry: SimulationTelemetry | Mapping[str, Any] | None,
    *,
    fallback_tick: int,
) -> SimulationTelemetry:
    if isinstance(telemetry, SimulationTelemetry):
        return telemetry
    if isinstance(telemetry, Mapping):
        return SimulationTelemetry(
            tick_index=int(telemetry.get("tick_index", fallback_tick)),
            active_agent_count=int(telemetry.get("active_agent_count", 0)),
            trip_generated_this_tick=int(telemetry.get("trip_generated_this_tick", 0)),
            trip_completed_this_tick=int(telemetry.get("trip_completed_this_tick", 0)),
            trip_failed_this_tick=int(telemetry.get("trip_failed_this_tick", 0)),
            capacity_violation_count_delta=int(telemetry.get("capacity_violation_count_delta", 0)),
            negative_queue_detected=bool(telemetry.get("negative_queue_detected", False)),
            policy_mix_lambda=float(telemetry.get("policy_mix_lambda", 0.0)),
            adaptive_fallback_triggered=bool(telemetry.get("adaptive_fallback_triggered", False)),
            ui_snapshot_emitted=bool(telemetry.get("ui_snapshot_emitted", False)),
        )
    return SimulationTelemetry(
        tick_index=int(fallback_tick),
        active_agent_count=0,
    )


def _build_context_summary(
    state: SimulationState,
    telemetry: SimulationTelemetry,
) -> dict[str, Any]:
    metrics_state = state.dynamic.metrics_state if isinstance(state.dynamic.metrics_state, Mapping) else {}
    return {
        "tick_index": int(telemetry.tick_index),
        "active_agent_count": int(telemetry.active_agent_count),
        "trip_completed_this_tick": int(telemetry.trip_completed_this_tick),
        "trip_failed_this_tick": int(telemetry.trip_failed_this_tick),
        "capacity_violation_count_delta": int(telemetry.capacity_violation_count_delta),
        "negative_queue_detected": bool(telemetry.negative_queue_detected),
        "queued_trip_requests": int(metrics_state.get("queued_trip_requests", 0)),
        "pending_trip_requests": int(metrics_state.get("pending_trip_requests", 0)),
    }


def _build_event_context(state: SimulationState) -> dict[str, Any]:
    metadata = state.dynamic.metadata if isinstance(state.dynamic.metadata, Mapping) else {}
    event_state = state.dynamic.event_state
    if isinstance(event_state, Mapping):
        active_events = tuple(event_state.get("active_events", ()))
    else:
        active_events = tuple(getattr(event_state, "active_events", ()) or ())
    return {
        "active_event_ids": tuple(_event_id(ev) for ev in active_events),
        "affected_link_ids": tuple(int(v) for v in metadata.get("us2_active_event_affected_link_ids", ())),
    }


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _event_id(event: object) -> int:
    if isinstance(event, Mapping):
        return int(event.get("event_id", -1))
    return int(getattr(event, "event_id", -1))
