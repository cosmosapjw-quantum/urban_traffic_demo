"""Simulation configuration dataclasses and enums."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping

__all__ = [
    "DayType",
    "TimeBand",
    "RoadHierarchyClass",
    "ZoneType",
    "LearningMixBounds",
    "SimulationConfig",
    "CityGenerationConfig",
]

EDGE_RUNTIME_BACKENDS = ("baseline", "rust_cpu", "jax", "auto")
FLOW_RUNTIME_BACKENDS = ("baseline", "rust_cpu", "auto")
ROUTING_RUNTIME_BACKENDS = ("baseline", "rust_cpu", "auto")


class StrEnum(str, Enum):
    """Small local base class for string enums with clean repr/serialization."""


class DayType(StrEnum):
    WEEKDAY = "weekday"
    WEEKEND = "weekend"


class TimeBand(StrEnum):
    MORNING = "morning"
    LUNCH = "lunch"
    EVENING = "evening"
    NIGHT = "night"


class RoadHierarchyClass(StrEnum):
    LOCAL = "local"
    ARTERIAL = "arterial"
    EXPRESSWAY = "expressway"


class ZoneType(StrEnum):
    RESIDENTIAL = "residential"
    CBD_COMMERCIAL = "cbd_commercial"
    INDUSTRIAL = "industrial"
    MIXED_USE = "mixed_use"


@dataclass(slots=True)
class LearningMixBounds:
    """Adaptive-policy mix bounds for baseline/adaptive routing blending."""

    lambda_min: float = 0.0
    lambda_max: float = 1.0

    def __post_init__(self) -> None:
        self.lambda_min = float(self.lambda_min)
        self.lambda_max = float(self.lambda_max)
        if not 0.0 <= self.lambda_min <= 1.0:
            raise ValueError("lambda_min must be in [0, 1]")
        if not 0.0 <= self.lambda_max <= 1.0:
            raise ValueError("lambda_max must be in [0, 1]")
        if self.lambda_min > self.lambda_max:
            raise ValueError("lambda_min must be <= lambda_max")


@dataclass(slots=True)
class SimulationConfig:
    """Top-level runtime configuration for a simulation run."""

    population_target: int = 100_000
    tick_seconds: float = 1.0
    active_agent_capacity: int = 20_000
    random_seed: int = 42
    day_type_set: tuple[DayType, ...] = (DayType.WEEKDAY, DayType.WEEKEND)
    time_bands: tuple[TimeBand, ...] = (
        TimeBand.MORNING,
        TimeBand.LUNCH,
        TimeBand.EVENING,
        TimeBand.NIGHT,
    )
    ui_stream_enabled: bool = False
    ui_stream_hz_limit: float = 5.0
    learning_enabled: bool = False
    learning_mix_bounds: LearningMixBounds = field(default_factory=LearningMixBounds)
    ctm_mode_enabled: bool = False
    max_trip_spawns_per_tick: int = 512
    edge_backend: str = "baseline"
    flow_backend: str = "baseline"
    routing_backend: str = "baseline"
    route_max_candidates: int = 1
    route_max_hops: int = 64
    route_refresh_interval_ticks: int = 8
    route_path_size_gamma: float = 0.0

    def __post_init__(self) -> None:
        self.population_target = int(self.population_target)
        self.active_agent_capacity = int(self.active_agent_capacity)
        self.random_seed = int(self.random_seed)
        self.tick_seconds = float(self.tick_seconds)
        self.ui_stream_hz_limit = float(self.ui_stream_hz_limit)
        self.max_trip_spawns_per_tick = int(self.max_trip_spawns_per_tick)
        self.edge_backend = str(self.edge_backend)
        self.flow_backend = str(self.flow_backend)
        self.routing_backend = str(self.routing_backend)
        self.route_max_candidates = int(self.route_max_candidates)
        self.route_max_hops = int(self.route_max_hops)
        self.route_refresh_interval_ticks = int(self.route_refresh_interval_ticks)
        self.route_path_size_gamma = float(self.route_path_size_gamma)
        self.day_type_set = _coerce_enum_tuple(self.day_type_set, DayType)
        self.time_bands = _coerce_enum_tuple(self.time_bands, TimeBand)

        if self.population_target < 1:
            raise ValueError("population_target must be >= 1")
        if self.active_agent_capacity <= 0:
            raise ValueError("active_agent_capacity must be > 0")
        if self.tick_seconds <= 0:
            raise ValueError("tick_seconds must be > 0")
        if self.ui_stream_hz_limit <= 0:
            raise ValueError("ui_stream_hz_limit must be > 0")
        if self.max_trip_spawns_per_tick <= 0:
            raise ValueError("max_trip_spawns_per_tick must be > 0")
        if self.edge_backend not in EDGE_RUNTIME_BACKENDS:
            raise ValueError("edge_backend must be one of: baseline, rust_cpu, jax, auto")
        if self.flow_backend not in FLOW_RUNTIME_BACKENDS:
            raise ValueError("flow_backend must be one of: baseline, rust_cpu, auto")
        if self.routing_backend not in ROUTING_RUNTIME_BACKENDS:
            raise ValueError("routing_backend must be one of: baseline, rust_cpu, auto")
        if self.route_max_candidates < 1:
            raise ValueError("route_max_candidates must be >= 1")
        if self.route_max_hops < 1:
            raise ValueError("route_max_hops must be >= 1")
        if self.route_refresh_interval_ticks < 1:
            raise ValueError("route_refresh_interval_ticks must be >= 1")
        if self.route_path_size_gamma < 0.0:
            raise ValueError("route_path_size_gamma must be >= 0")
        if not self.day_type_set:
            raise ValueError("day_type_set must not be empty")
        if not self.time_bands:
            raise ValueError("time_bands must not be empty")
        if not isinstance(self.learning_mix_bounds, LearningMixBounds):
            self.learning_mix_bounds = LearningMixBounds(**dict(self.learning_mix_bounds))


@dataclass(slots=True)
class CityGenerationConfig:
    """Synthetic city generation configuration for topology/zones/POIs."""

    road_hierarchy_profile: dict[RoadHierarchyClass, float] = field(
        default_factory=lambda: {
            RoadHierarchyClass.LOCAL: 0.7,
            RoadHierarchyClass.ARTERIAL: 0.2,
            RoadHierarchyClass.EXPRESSWAY: 0.1,
        }
    )
    ring_road_count: int = 1
    radial_corridor_count: int = 4
    barrier_count: int = 1
    bridge_count: int = 3
    interchange_density_profile: str = "medium"
    zone_mix_targets: dict[ZoneType, float] = field(
        default_factory=lambda: {
            ZoneType.RESIDENTIAL: 0.4,
            ZoneType.CBD_COMMERCIAL: 0.2,
            ZoneType.INDUSTRIAL: 0.2,
            ZoneType.MIXED_USE: 0.2,
        }
    )
    poi_density_profile: str = "baseline"

    def __post_init__(self) -> None:
        self.road_hierarchy_profile = _coerce_share_mapping(
            self.road_hierarchy_profile,
            RoadHierarchyClass,
        )
        self.zone_mix_targets = _coerce_share_mapping(self.zone_mix_targets, ZoneType)

        self.ring_road_count = int(self.ring_road_count)
        self.radial_corridor_count = int(self.radial_corridor_count)
        self.barrier_count = int(self.barrier_count)
        self.bridge_count = int(self.bridge_count)

        if self.ring_road_count < 0:
            raise ValueError("ring_road_count must be >= 0")
        if self.radial_corridor_count < 1:
            raise ValueError("radial_corridor_count must be >= 1")
        if self.barrier_count < 1:
            raise ValueError("barrier_count must be >= 1")
        if not 3 <= self.bridge_count <= 5:
            raise ValueError("bridge_count must be in [3, 5]")

        _validate_shares(self.zone_mix_targets, "zone_mix_targets")
        if set(self.zone_mix_targets) != set(ZoneType):
            raise ValueError("zone_mix_targets must include all zone types")

        if self.road_hierarchy_profile:
            _validate_non_negative_shares(
                self.road_hierarchy_profile,
                "road_hierarchy_profile",
            )


def _coerce_enum_tuple(
    values: Iterable[DayType | TimeBand | str],
    enum_type: type[DayType] | type[TimeBand],
) -> tuple[DayType, ...] | tuple[TimeBand, ...]:
    return tuple(enum_type(value) for value in values)


def _coerce_share_mapping(
    values: Mapping[str, float] | Mapping[StrEnum, float],
    enum_type: type[RoadHierarchyClass] | type[ZoneType],
) -> dict[RoadHierarchyClass, float] | dict[ZoneType, float]:
    return {enum_type(key): float(value) for key, value in values.items()}


def _validate_shares(values: Mapping[StrEnum, float], field_name: str) -> None:
    _validate_non_negative_shares(values, field_name)
    total = sum(values.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"{field_name} shares must sum to 1.0 (got {total})")


def _validate_non_negative_shares(values: Mapping[StrEnum, float], field_name: str) -> None:
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    if any(value < 0 for value in values.values()):
        raise ValueError(f"{field_name} shares must be non-negative")
