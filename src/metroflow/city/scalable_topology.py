"""Standalone deterministic Task3 S2 physical-topology kernel."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from metroflow.city.scale import CityScaleSpec

SCHEMA_VERSION = "tmfcg_s2_v1"
TILE_SIZE_M = 2_000.0
TERRAIN_CELL_SIZE_M = 50.0
MAX_JUNCTIONS = 120_000
MAX_PHYSICAL_ROADS = 300_000
MAX_SURFACE_DEGREE = 4
STYLE_IDS = ("grid_core",)


class RoadHierarchy(str, Enum):
    EXPRESSWAY = "expressway"
    ARTERIAL = "arterial"
    COLLECTOR = "collector"
    LOCAL = "local"


class FacilityKind(str, Enum):
    SURFACE = "surface"
    MAINLINE = "mainline"
    RAMP = "ramp"
    BRIDGE = "bridge"
    TUNNEL = "tunnel"


def _require_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    return int(value)


def _require_digest(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a SHA-256 string")
    digest = str(value)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{name} must be a lowercase 64-character SHA-256 digest")
    return digest


def _snapshot_str(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return str(value)


def _snapshot_optional_str(name: str, value: object) -> str | None:
    if value is None:
        return None
    return _snapshot_str(name, value)


def _snapshot_int_pair(name: str, value: object) -> tuple[int, int]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError(f"{name} must contain exactly two integers")
    return (_require_int(name, value[0]), _require_int(name, value[1]))


def _snapshot_tuple(name: str, value: object) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")
    return tuple(value)


def _snapshot_scale_spec(scale_spec: object) -> ScalableScaleSnapshot:
    if type(scale_spec) is not CityScaleSpec:
        raise TypeError("scale_spec must be an exact CityScaleSpec")
    return ScalableScaleSnapshot(
        scale_spec.target_population,
        scale_spec.urbanized_area_km2,
    )


def _profile_for(facility: FacilityKind, hierarchy: RoadHierarchy) -> str:
    if facility is FacilityKind.RAMP:
        return "v2:ramp"
    return f"v2:{facility.value}:{hierarchy.value}"


@dataclass(frozen=True, slots=True)
class ScalableScaleSnapshot:
    target_population: int
    urbanized_area_km2: float

    def __post_init__(self) -> None:
        population = _require_int("target_population", self.target_population)
        if type(self.urbanized_area_km2) not in (int, float):
            raise TypeError("urbanized_area_km2 must be a number")
        area = float(self.urbanized_area_km2)
        if not isfinite(area) or area <= 0:
            raise ValueError("urbanized_area_km2 must be finite and positive")
        object.__setattr__(self, "target_population", population)
        object.__setattr__(self, "urbanized_area_km2", area)


@dataclass(frozen=True, slots=True)
class PhysicalNodeRecord:
    node_id: int
    semantic_id: str
    x_mm: int
    y_mm: int
    layer: int
    semantic_role: str = ""

    def __post_init__(self) -> None:
        node_id = _require_int("node_id", self.node_id)
        if node_id < 0:
            raise ValueError("node_id must be non-negative")
        object.__setattr__(self, "node_id", node_id)
        object.__setattr__(self, "semantic_id", _require_digest("semantic_id", self.semantic_id))
        object.__setattr__(self, "x_mm", _require_int("x_mm", self.x_mm))
        object.__setattr__(self, "y_mm", _require_int("y_mm", self.y_mm))
        object.__setattr__(self, "layer", _require_int("layer", self.layer))
        object.__setattr__(
            self, "semantic_role", _snapshot_str("semantic_role", self.semantic_role)
        )

    @property
    def point_mm(self) -> tuple[int, int]:
        return (self.x_mm, self.y_mm)


@dataclass(frozen=True, slots=True)
class RowIntervalAuthority:
    row_y_mm: int
    left_x_mm: int
    tile_left_mm: int
    tile_right_mm: int
    owner_cell: tuple[int, int]
    nominal_spacing_mm: int
    realized_spacing_mm: int
    seam_truncated: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_y_mm", _require_int("row_y_mm", self.row_y_mm))
        object.__setattr__(self, "left_x_mm", _require_int("left_x_mm", self.left_x_mm))
        object.__setattr__(self, "tile_left_mm", _require_int("tile_left_mm", self.tile_left_mm))
        object.__setattr__(self, "tile_right_mm", _require_int("tile_right_mm", self.tile_right_mm))
        object.__setattr__(self, "owner_cell", _snapshot_int_pair("owner_cell", self.owner_cell))
        nominal = _require_int("nominal_spacing_mm", self.nominal_spacing_mm)
        realized = _require_int("realized_spacing_mm", self.realized_spacing_mm)
        if nominal <= 0 or realized <= 0:
            raise ValueError("row interval spacing must be positive")
        object.__setattr__(self, "nominal_spacing_mm", nominal)
        object.__setattr__(self, "realized_spacing_mm", realized)
        if type(self.seam_truncated) is not bool:
            raise TypeError("seam_truncated must be bool")


@dataclass(frozen=True, slots=True)
class PhysicalRoadRecord:
    road_id: int
    semantic_id: str
    start_node_id: int
    end_node_id: int
    points_mm: tuple[tuple[int, int], ...]
    hierarchy: RoadHierarchy
    facility: FacilityKind
    layer: int
    access_directions: frozenset[str]
    layer_transition: tuple[int, int] | None
    structure_group: str | None
    failure_group: str | None
    profile_id: str
    provenance: str
    semantic_role: str = ""
    row_interval: RowIntervalAuthority | None = None

    def __post_init__(self) -> None:
        road_id = _require_int("road_id", self.road_id)
        start_node_id = _require_int("start_node_id", self.start_node_id)
        end_node_id = _require_int("end_node_id", self.end_node_id)
        if road_id < 0 or start_node_id < 0 or end_node_id < 0:
            raise ValueError("road and endpoint IDs must be non-negative")
        if start_node_id == end_node_id:
            raise ValueError("road endpoints must be distinct")
        object.__setattr__(self, "road_id", road_id)
        object.__setattr__(self, "start_node_id", start_node_id)
        object.__setattr__(self, "end_node_id", end_node_id)
        object.__setattr__(self, "semantic_id", _require_digest("semantic_id", self.semantic_id))

        raw_points = _snapshot_tuple("points_mm", self.points_mm)
        points = tuple(_snapshot_int_pair("points_mm", point) for point in raw_points)
        if len(points) < 2 or len(set(points)) < 2:
            raise ValueError("points_mm must contain at least two distinct points")
        if any(left == right for left, right in zip(points, points[1:])):
            raise ValueError("points_mm must not contain adjacent duplicates")
        object.__setattr__(self, "points_mm", points)

        try:
            hierarchy = RoadHierarchy(self.hierarchy)
        except (TypeError, ValueError) as error:
            raise ValueError("hierarchy is invalid") from error
        try:
            facility = FacilityKind(self.facility)
        except (TypeError, ValueError) as error:
            raise ValueError("facility is invalid") from error
        object.__setattr__(self, "hierarchy", hierarchy)
        object.__setattr__(self, "facility", facility)
        object.__setattr__(self, "layer", _require_int("layer", self.layer))

        if not isinstance(self.access_directions, frozenset):
            raise TypeError("access_directions must be a frozenset")
        directions = frozenset(
            _snapshot_str("access_directions", direction) for direction in self.access_directions
        )
        if not directions or not directions <= {"forward", "reverse"}:
            raise ValueError("access_directions must be a non-empty closed direction set")
        object.__setattr__(self, "access_directions", directions)

        transition = self.layer_transition
        if transition is not None:
            transition = _snapshot_int_pair("layer_transition", transition)
        if facility is FacilityKind.RAMP and transition is None:
            raise ValueError("ramps require an explicit layer_transition")
        if facility is not FacilityKind.RAMP and transition is not None:
            raise ValueError("only ramps may define layer_transition")
        object.__setattr__(self, "layer_transition", transition)
        object.__setattr__(
            self,
            "structure_group",
            _snapshot_optional_str("structure_group", self.structure_group),
        )
        object.__setattr__(
            self,
            "failure_group",
            _snapshot_optional_str("failure_group", self.failure_group),
        )
        profile_id = _snapshot_str("profile_id", self.profile_id)
        if profile_id != _profile_for(facility, hierarchy):
            raise ValueError("profile_id does not match facility and hierarchy")
        object.__setattr__(self, "profile_id", profile_id)
        object.__setattr__(self, "provenance", _snapshot_str("provenance", self.provenance))
        object.__setattr__(
            self, "semantic_role", _snapshot_str("semantic_role", self.semantic_role)
        )
        if self.row_interval is not None and type(self.row_interval) is not RowIntervalAuthority:
            raise TypeError("row_interval must be an exact RowIntervalAuthority")

    @property
    def canonical_key(self) -> tuple[int, int, tuple[tuple[int, int], ...], int]:
        if self.start_node_id <= self.end_node_id:
            points = self.points_mm
        else:
            points = tuple(reversed(self.points_mm))
        return (
            min(self.start_node_id, self.end_node_id),
            max(self.start_node_id, self.end_node_id),
            points,
            self.layer,
        )
