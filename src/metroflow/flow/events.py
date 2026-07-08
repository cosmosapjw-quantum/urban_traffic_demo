"""Traffic event models and scheduler state transitions (US2/T048)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from math import isfinite
from typing import Any, Mapping

__all__ = [
    "TrafficEventStatus",
    "TrafficEvent",
    "TrafficEventSchedulerState",
    "advance_traffic_event_scheduler",
]


class StrEnum(str, Enum):
    """Local string enum base for stable packet/model serialization values."""


class TrafficEventStatus(StrEnum):
    """Lifecycle status of a scheduled traffic event."""

    SCHEDULED = "scheduled"
    ACTIVE = "active"
    CLEARED = "cleared"


@dataclass(slots=True)
class TrafficEvent:
    """Traffic event model matching the feature data model contract."""

    event_id: int
    event_type: str
    start_tick: int
    end_tick: int
    target_scope: Mapping[str, Any] | dict[str, Any]
    severity: float
    effect_model: str
    status: TrafficEventStatus | str = TrafficEventStatus.SCHEDULED

    def __post_init__(self) -> None:
        self.event_id = int(self.event_id)
        self.event_type = str(self.event_type)
        self.start_tick = int(self.start_tick)
        self.end_tick = int(self.end_tick)
        self.target_scope = dict(self.target_scope)
        self.severity = float(self.severity)
        self.effect_model = str(self.effect_model)
        self.status = TrafficEventStatus(self.status)

        if self.event_id < 0:
            raise ValueError("event_id must be >= 0")
        if not self.event_type:
            raise ValueError("event_type must not be empty")
        if not self.effect_model:
            raise ValueError("effect_model must not be empty")
        if not self.target_scope:
            raise ValueError("target_scope must not be empty")
        if self.start_tick < 0 or self.end_tick < 0:
            raise ValueError("start_tick/end_tick must be >= 0")
        if self.start_tick >= self.end_tick:
            raise ValueError("start_tick must be < end_tick")
        if not isfinite(self.severity):
            raise ValueError("severity must be finite")
        if not 0.0 <= self.severity <= 1.0:
            raise ValueError("severity must be in [0, 1]")


@dataclass(slots=True)
class TrafficEventSchedulerState:
    """Scheduler state container for pending/active/cleared events."""

    scheduled_events: tuple[TrafficEvent, ...] = ()
    active_events: tuple[TrafficEvent, ...] = ()
    cleared_events: tuple[TrafficEvent, ...] = ()

    def __post_init__(self) -> None:
        self.scheduled_events = _coerce_event_bucket(
            self.scheduled_events,
            expected_status=TrafficEventStatus.SCHEDULED,
            bucket_name="scheduled_events",
        )
        self.active_events = _coerce_event_bucket(
            self.active_events,
            expected_status=TrafficEventStatus.ACTIVE,
            bucket_name="active_events",
        )
        self.cleared_events = _coerce_event_bucket(
            self.cleared_events,
            expected_status=TrafficEventStatus.CLEARED,
            bucket_name="cleared_events",
        )
        _validate_unique_event_ids_across_buckets(
            self.scheduled_events,
            self.active_events,
            self.cleared_events,
        )


@dataclass(slots=True)
class _TrafficEventSchedulerAdvancePlan:
    """Host-side advance plan prior to `TrafficEventSchedulerState` materialization."""

    scheduled_events: tuple[TrafficEvent, ...]
    active_events: tuple[TrafficEvent, ...]
    cleared_events: tuple[TrafficEvent, ...]


def advance_traffic_event_scheduler(
    state: TrafficEventSchedulerState | Mapping[str, Any],
    *,
    current_tick: int,
    clear_event_ids: tuple[int, ...] = (),
) -> TrafficEventSchedulerState:
    """Advance event scheduler state for the given tick.

    Rules (minimal T048 contract):
    - `scheduled -> active` when `current_tick >= start_tick` and not expired
    - `active -> cleared` when explicitly cleared or `current_tick > end_tick`
    - `scheduled -> cleared` when explicitly cleared before activation or when
      the tick has moved beyond `end_tick` before activation
    - Cleared events are kept as history with `status=cleared` (deduplicated by id)
    """

    scheduler_state = _coerce_scheduler_state(state)
    tick = int(current_tick)
    if tick < 0:
        raise ValueError("current_tick must be >= 0")
    clear_ids = {int(event_id) for event_id in tuple(clear_event_ids)}
    if any(event_id < 0 for event_id in clear_ids):
        raise ValueError("clear_event_ids must contain non-negative ids")

    plan = _plan_traffic_event_scheduler_advance(
        scheduler_state=scheduler_state,
        tick=tick,
        clear_ids=clear_ids,
    )
    return TrafficEventSchedulerState(
        scheduled_events=plan.scheduled_events,
        active_events=plan.active_events,
        cleared_events=plan.cleared_events,
    )


def _plan_traffic_event_scheduler_advance(
    *,
    scheduler_state: TrafficEventSchedulerState,
    tick: int,
    clear_ids: set[int],
) -> _TrafficEventSchedulerAdvancePlan:
    """Build the next scheduler buckets (host-side; Python object model)."""

    next_scheduled: list[TrafficEvent] = []
    next_active: list[TrafficEvent] = []
    cleared_history: list[TrafficEvent] = list(scheduler_state.cleared_events)
    cleared_index = {event.event_id: idx for idx, event in enumerate(cleared_history)}

    def add_cleared(event: TrafficEvent) -> None:
        cleared = _with_status(event, TrafficEventStatus.CLEARED)
        existing_idx = cleared_index.get(cleared.event_id)
        if existing_idx is not None:
            cleared_history[existing_idx] = cleared
        else:
            cleared_index[cleared.event_id] = len(cleared_history)
            cleared_history.append(cleared)

    for event in scheduler_state.scheduled_events:
        if event.event_id in clear_ids:
            add_cleared(event)
            continue
        if tick > event.end_tick:
            add_cleared(event)
            continue
        if tick >= event.start_tick:
            next_active.append(_with_status(event, TrafficEventStatus.ACTIVE))
            continue
        next_scheduled.append(_with_status(event, TrafficEventStatus.SCHEDULED))

    for event in scheduler_state.active_events:
        if event.event_id in clear_ids or tick > event.end_tick:
            add_cleared(event)
            continue
        next_active.append(_with_status(event, TrafficEventStatus.ACTIVE))

    # Preserve stable input iteration order for deterministic replay under the
    # same seed/input sequence while avoiding repeated per-tick sort costs.
    return _TrafficEventSchedulerAdvancePlan(
        scheduled_events=tuple(next_scheduled),
        active_events=tuple(next_active),
        cleared_events=tuple(cleared_history),
    )


def _coerce_event(event: TrafficEvent | Mapping[str, Any]) -> TrafficEvent:
    if isinstance(event, TrafficEvent):
        return event
    return TrafficEvent(**dict(event))


def _coerce_scheduler_state(
    state: TrafficEventSchedulerState | Mapping[str, Any],
) -> TrafficEventSchedulerState:
    if isinstance(state, TrafficEventSchedulerState):
        return state
    return TrafficEventSchedulerState(**dict(state))


def _with_status(event: TrafficEvent, status: TrafficEventStatus) -> TrafficEvent:
    if event.status is status:
        return event
    return replace(event, status=status)


def _coerce_event_bucket(
    events: tuple[TrafficEvent, ...] | tuple[Mapping[str, Any], ...] | list[Any],
    *,
    expected_status: TrafficEventStatus,
    bucket_name: str,
) -> tuple[TrafficEvent, ...]:
    out = tuple(_coerce_event(ev) for ev in events)
    for ev in out:
        if ev.status is not expected_status:
            raise ValueError(
                f"{bucket_name} contains event_id={ev.event_id} with status={ev.status.value}, "
                f"expected {expected_status.value}"
            )
    return out


def _validate_unique_event_ids_across_buckets(*buckets: tuple[TrafficEvent, ...]) -> None:
    seen: set[int] = set()
    for bucket in buckets:
        for ev in bucket:
            if ev.event_id in seen:
                raise ValueError(f"duplicate event_id across scheduler buckets: {ev.event_id}")
            seen.add(ev.event_id)
