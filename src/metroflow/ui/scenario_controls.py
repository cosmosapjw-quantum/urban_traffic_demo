"""US2 demo disruption scenario control presets (T054)."""

from __future__ import annotations

from itertools import count
from dataclasses import dataclass
from typing import Any

from metroflow.flow.events import TrafficEvent, TrafficEventStatus
from metroflow.sim.config import DayType, TimeBand
from metroflow.sim.control import SimulationControl

__all__ = [
    "DisruptionScenarioPreset",
    "list_disruption_scenario_presets",
    "build_disruption_scenario_controls",
]


@dataclass(frozen=True, slots=True)
class DisruptionScenarioPreset:
    """Named UI/demo preset describing a disruption control sequence."""

    preset_id: str
    label: str
    description: str


_PRESETS: tuple[DisruptionScenarioPreset, ...] = (
    DisruptionScenarioPreset(
        preset_id="bridge_closure_peak",
        label="Bridge Closure Peak",
        description="Inject a bridge closure, run several ticks, then clear and request a snapshot.",
    ),
    DisruptionScenarioPreset(
        preset_id="blocked_edge_accident",
        label="Blocked Edge Accident",
        description="Inject a blocked-edge accident on one link and clear after a short disruption window.",
    ),
    DisruptionScenarioPreset(
        preset_id="boundary_toggle_clear",
        label="Boundary Toggle + Clear",
        description="Inject disruption with day/time toggles and explicit clear to exercise boundary behavior.",
    ),
)
_AUTO_EVENT_ID_COUNTER = count(7001)


def list_disruption_scenario_presets() -> tuple[DisruptionScenarioPreset, ...]:
    """Return available disruption scenario presets for demos/UI."""

    return _PRESETS


def build_disruption_scenario_controls(
    preset_id: str,
    *,
    bridge_group_id: int | None = None,
    link_id: int | None = None,
    event_id: int | None = None,
    start_tick: int = 1,
    duration_ticks: int | None = None,
    current_tick: int = 0,
) -> tuple[SimulationControl, ...]:
    """Build a deterministic `SimulationControl` sequence for a demo disruption preset.

    The returned sequence is intended for `run_rollout(...)` or demo loops.
    `TrafficEvent` instances are injected on the first control of the preset.
    `start_tick` is interpreted as a relative offset from `current_tick`.
    """

    preset = _preset_by_id(preset_id)
    current_tick_i = max(0, int(current_tick))
    start_offset_i = max(1, int(start_tick))
    duration_i = _default_duration_for_preset(preset.preset_id) if duration_ticks is None else int(duration_ticks)
    duration_i = max(1, duration_i)
    event_id_i = int(event_id) if event_id is not None else int(next(_AUTO_EVENT_ID_COUNTER))
    start_tick_i = current_tick_i + start_offset_i
    end_tick_i = max(start_tick_i + 1, start_tick_i + duration_i)

    if preset.preset_id == "bridge_closure_peak":
        if bridge_group_id is None:
            raise ValueError("bridge_closure_peak requires bridge_group_id")
        bridge_group_id = int(bridge_group_id)
        if bridge_group_id < 0:
            raise ValueError("bridge_group_id must be >= 0")
        event = _traffic_event(
            event_id=event_id_i,
            event_type="construction",
            start_tick=start_tick_i,
            end_tick=end_tick_i,
            target_scope={"bridge_group_id": bridge_group_id},
            effect_model="closure",
            severity=1.0,
        )
        return (
            SimulationControl(inject_event=event, ui_force_snapshot=True),
            *tuple(SimulationControl.noop() for _ in range(max(0, duration_i - 1))),
            SimulationControl(clear_event_ids=(event_id_i,), ui_force_snapshot=True),
            SimulationControl(ui_force_snapshot=True),
        )

    if preset.preset_id == "blocked_edge_accident":
        if link_id is None:
            raise ValueError("blocked_edge_accident requires link_id")
        link_id = int(link_id)
        if link_id < 0:
            raise ValueError("link_id must be >= 0")
        event = _traffic_event(
            event_id=event_id_i,
            event_type="accident",
            start_tick=start_tick_i,
            end_tick=end_tick_i,
            target_scope={"link_ids": (link_id,)},
            effect_model="closure",
            severity=1.0,
        )
        return (
            SimulationControl(inject_event=event, ui_force_snapshot=True),
            *tuple(SimulationControl.noop() for _ in range(max(0, duration_i - 1))),
            SimulationControl(clear_event_ids=(event_id_i,)),
            SimulationControl(ui_force_snapshot=True),
        )

    if preset.preset_id == "boundary_toggle_clear":
        if link_id is None:
            raise ValueError("boundary_toggle_clear requires link_id")
        link_id = int(link_id)
        if link_id < 0:
            raise ValueError("link_id must be >= 0")
        event = _traffic_event(
            event_id=event_id_i,
            event_type="accident",
            start_tick=start_tick_i,
            end_tick=end_tick_i,
            target_scope={"link_ids": (link_id,)},
            effect_model="closure",
            severity=1.0,
        )
        pad_before_clear = max(0, duration_i - 1)
        return (
            SimulationControl(inject_event=event),
            SimulationControl(set_day_type=DayType.WEEKEND),
            SimulationControl(set_time_band=TimeBand.EVENING),
            *tuple(SimulationControl.noop() for _ in range(pad_before_clear)),
            SimulationControl(
                pause=True,
                set_day_type=DayType.WEEKDAY,
                set_time_band=TimeBand.NIGHT,
                clear_event_ids=(event_id_i,),
                ui_force_snapshot=True,
            ),
            SimulationControl.noop(),
        )

    raise ValueError(f"unsupported preset_id: {preset_id}")


def _traffic_event(
    *,
    event_id: int,
    event_type: str,
    start_tick: int,
    end_tick: int,
    target_scope: dict[str, Any],
    effect_model: str,
    severity: float,
) -> TrafficEvent:
    return TrafficEvent(
        event_id=int(event_id),
        event_type=str(event_type),
        start_tick=int(start_tick),
        end_tick=int(end_tick),
        target_scope=dict(target_scope),
        severity=float(severity),
        effect_model=str(effect_model),
        status=TrafficEventStatus.SCHEDULED,
    )


def _preset_by_id(preset_id: str) -> DisruptionScenarioPreset:
    pid = str(preset_id)
    for preset in _PRESETS:
        if preset.preset_id == pid:
            return preset
    raise ValueError(f"unknown disruption preset: {pid}")


def _default_duration_for_preset(preset_id: str) -> int:
    if preset_id == "bridge_closure_peak":
        return 6
    if preset_id == "blocked_edge_accident":
        return 4
    return 4


def _default_event_id_for_preset(preset_id: str) -> int:
    # Retained for backward compatibility if callers still import this helper.
    if preset_id == "bridge_closure_peak":
        return 7001
    if preset_id == "blocked_edge_accident":
        return 7002
    if preset_id == "boundary_toggle_clear":
        return 7003
    return 7099
