"""Core simulation state containers (static + dynamic references)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from metroflow.sim.config import DayType, SimulationConfig, TimeBand

__all__ = [
    "SimulationClockState",
    "SimulationStaticRefs",
    "SimulationDynamicRefs",
    "SimulationState",
]


@dataclass(slots=True)
class SimulationClockState:
    """Mutable simulation clock/control context tracked across ticks."""

    tick_index: int = 0
    day_type: DayType = DayType.WEEKDAY
    time_band: TimeBand = TimeBand.MORNING

    def __post_init__(self) -> None:
        self.tick_index = int(self.tick_index)
        self.day_type = DayType(self.day_type)
        self.time_band = TimeBand(self.time_band)
        if self.tick_index < 0:
            raise ValueError("tick_index must be >= 0")


@dataclass(slots=True)
class SimulationStaticRefs:
    """Static references built at init time and reused across simulation steps."""

    scenario_id: str = "unknown"
    city_topology: Any = None
    zones: Any = None
    pois: Any = None
    population: Any = None
    schedule_templates: Any = None
    routing_static: Any = None
    ui_network_geometry_version: int | str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.scenario_id = str(self.scenario_id)
        if not isinstance(self.metadata, dict):
            self.metadata = dict(self.metadata)


@dataclass(slots=True)
class SimulationDynamicRefs:
    """Dynamic references updated by the step pipeline each tick."""

    clock_state: SimulationClockState = field(default_factory=SimulationClockState)
    demand_state: Any = None
    active_agent_pool: Any = None
    flow_link_state: Any = None
    flow_node_state: Any = None
    event_state: Any = None
    routing_baseline_state: Any = None
    route_candidate_state: Any = None
    adaptive_learning_state: Any = None
    policy_blend_state: Any = None
    metrics_state: Any = None
    invariant_state: Any = None
    ui_state: Any = None
    last_ui_snapshot_source: Any = None
    fallback_state: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.clock_state, SimulationClockState):
            self.clock_state = SimulationClockState(**dict(self.clock_state))
        if not isinstance(self.metadata, dict):
            self.metadata = dict(self.metadata)


@dataclass(slots=True)
class SimulationState:
    """Top-level state wrapper separating static vs dynamic references.

    This container is intentionally shallow for T010: follow-on tasks fill the
    concrete state objects referenced here (flow/link, active-agent pool, etc.).
    """

    config: SimulationConfig = field(default_factory=SimulationConfig)
    static: SimulationStaticRefs = field(default_factory=SimulationStaticRefs)
    dynamic: SimulationDynamicRefs = field(default_factory=SimulationDynamicRefs)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.config, SimulationConfig):
            self.config = SimulationConfig(**dict(self.config))
        if not isinstance(self.static, SimulationStaticRefs):
            self.static = SimulationStaticRefs(**dict(self.static))
        if not isinstance(self.dynamic, SimulationDynamicRefs):
            self.dynamic = SimulationDynamicRefs(**dict(self.dynamic))
        if not isinstance(self.metadata, dict):
            self.metadata = dict(self.metadata)

    @property
    def tick_index(self) -> int:
        return self.dynamic.clock_state.tick_index

    @property
    def day_type(self) -> DayType:
        return self.dynamic.clock_state.day_type

    @property
    def time_band(self) -> TimeBand:
        return self.dynamic.clock_state.time_band

    def with_clock(
        self,
        *,
        tick_index: int | None = None,
        day_type: DayType | str | None = None,
        time_band: TimeBand | str | None = None,
    ) -> "SimulationState":
        """Return a new state with updated clock values (pure-step friendly)."""

        clock = self.dynamic.clock_state
        next_clock = replace(
            clock,
            tick_index=clock.tick_index if tick_index is None else tick_index,
            day_type=clock.day_type if day_type is None else day_type,
            time_band=clock.time_band if time_band is None else time_band,
        )
        next_dynamic = replace(self.dynamic, clock_state=next_clock)
        return replace(self, dynamic=next_dynamic)

    def with_dynamic_updates(self, **updates: Any) -> "SimulationState":
        """Return a new state with selected dynamic references replaced."""

        valid_fields = set(self.dynamic.__dataclass_fields__)  # type: ignore[attr-defined]
        unknown = tuple(sorted(set(updates) - valid_fields))
        if unknown:
            raise KeyError(f"unknown dynamic fields: {', '.join(unknown)}")
        next_dynamic = replace(self.dynamic, **updates)
        return replace(self, dynamic=next_dynamic)

    def to_ref_dict(self) -> dict[str, Any]:
        """Debug-oriented shallow export of the main state containers."""

        return {
            "config": self.config,
            "static": self.static,
            "dynamic": self.dynamic,
            "metadata": dict(self.metadata),
        }
