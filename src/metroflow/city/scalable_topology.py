"""Standalone deterministic Task3 S2 physical-topology kernel."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Sequence

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


@dataclass(frozen=True, slots=True)
class ScalableTerrainField:
    width_m: float
    height_m: float
    cell_size_m: float
    tile_size_m: float
    seed: int
    style_id: str
    barrier_seam_x_mm: int | None
    fingerprint: str

    def __post_init__(self) -> None:
        values = (self.width_m, self.height_m, self.cell_size_m, self.tile_size_m)
        if any(type(value) not in (int, float) for value in values):
            raise TypeError("terrain dimensions must be exact built-in numbers")
        width_m, height_m, cell_size_m, tile_size_m = map(float, values)
        if not all(isfinite(value) and value > 0.0 for value in values[:3]):
            raise ValueError("terrain dimensions must be finite and positive")
        if cell_size_m > TERRAIN_CELL_SIZE_M:
            raise ValueError("terrain cell_size_m must be in (0, 50]")
        if not isfinite(tile_size_m) or tile_size_m != TILE_SIZE_M:
            raise ValueError("terrain tile_size_m must be 2000")
        seed = _require_int("terrain seed", self.seed)
        style_id = _snapshot_str("terrain style_id", self.style_id)
        if style_id not in STYLE_IDS:
            raise ValueError("terrain style_id must be a supported style")
        barrier = self.barrier_seam_x_mm
        if barrier is not None:
            barrier = _require_int("barrier_seam_x_mm", barrier)
        if style_id == "river_constrained":
            if barrier != 0:
                raise ValueError("river terrain requires the explicit x=0 barrier seam")
        elif barrier is not None:
            raise ValueError("only river terrain may declare a barrier seam")
        object.__setattr__(self, "width_m", width_m)
        object.__setattr__(self, "height_m", height_m)
        object.__setattr__(self, "cell_size_m", cell_size_m)
        object.__setattr__(self, "tile_size_m", tile_size_m)
        object.__setattr__(self, "seed", seed)
        object.__setattr__(self, "style_id", style_id)
        object.__setattr__(self, "barrier_seam_x_mm", barrier)
        object.__setattr__(self, "fingerprint", _require_digest("fingerprint", self.fingerprint))

    def cell_key_at(self, x_m: float, y_m: float) -> tuple[int, int]:
        return (
            math.floor(float(x_m) / self.cell_size_m),
            math.floor(float(y_m) / self.cell_size_m),
        )

    def intensity_at(self, x_m: float, y_m: float) -> float:
        cell_x, cell_y = self.cell_key_at(x_m, y_m)
        payload = f"{self.seed}:{self.style_id}:{cell_x}:{cell_y}".encode()
        value = int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")
        return 0.12 + 0.56 * value / 4_294_967_295.0

    def spacing_at(self, x_m: float, y_m: float) -> float:
        return max(80.0, min(220.0, 220.0 - 140.0 * math.sqrt(self.intensity_at(x_m, y_m))))

    def is_barrier_at(self, x_m: float, y_m: float) -> bool:
        return (
            self.barrier_seam_x_mm is not None
            and abs(float(x_m) * 1_000.0 - self.barrier_seam_x_mm) < 0.5
        )


def _semantic_id(parts: object) -> str:
    payload = json.dumps(parts, separators=(",", ":"), sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def _terrain_fingerprint(
    width_m: float,
    height_m: float,
    seed: int,
    style_id: str,
    barrier_seam_x_mm: int | None,
    cell_size_m: float = TERRAIN_CELL_SIZE_M,
    tile_size_m: float = TILE_SIZE_M,
) -> str:
    return _semantic_id(
        (
            SCHEMA_VERSION,
            "terrain",
            width_m,
            height_m,
            cell_size_m,
            tile_size_m,
            seed,
            style_id,
            barrier_seam_x_mm,
        )
    )


def _extent_mm(area_km2: float) -> tuple[int, int]:
    if type(area_km2) not in (int, float):
        raise TypeError("area_km2 must be an exact built-in number")
    area = float(area_km2)
    if not isfinite(area) or area <= 0:
        raise ValueError("area_km2 must be finite and positive")
    width_m = math.sqrt(area * 1_000_000.0 * 9.0 / 7.0)
    return (int(round(width_m * 1_000.0)), int(round(width_m * 7.0 / 9.0 * 1_000.0)))


def _tile_domain(extent: tuple[int, int, int, int]) -> tuple[tuple[int, int], ...]:
    if not isinstance(extent, tuple) or len(extent) != 4:
        raise TypeError("extent must be a four-integer tuple")
    min_x, max_x, min_y, max_y = (_require_int("extent", value) for value in extent)
    tile_mm = int(TILE_SIZE_M * 1_000.0)
    return tuple(
        (tile_x, tile_y)
        for tile_y in range(math.floor(min_y / tile_mm), math.floor(max_y / tile_mm) + 1)
        for tile_x in range(math.floor(min_x / tile_mm), math.floor(max_x / tile_mm) + 1)
    )


def _validate_tile_order(
    canonical: tuple[tuple[int, int], ...],
    tile_order: Sequence[tuple[int, int]] | None,
) -> None:
    if tile_order is None:
        return
    supplied = tuple(_snapshot_int_pair("tile_order", pair) for pair in tile_order)
    if len(supplied) != len(canonical) or set(supplied) != set(canonical):
        raise ValueError("tile_order must be an exact permutation of the canonical tile domain")


def _seam_coordinates(minimum: int, maximum: int) -> tuple[int, ...]:
    minimum = _require_int("minimum", minimum)
    maximum = _require_int("maximum", maximum)
    if minimum > maximum:
        raise ValueError("minimum must not exceed maximum")
    tile_mm = int(TILE_SIZE_M * 1_000.0)
    return tuple(
        index * tile_mm
        for index in range(math.ceil(minimum / tile_mm), math.floor(maximum / tile_mm) + 1)
    )


def _local_axis(
    minimum: int,
    maximum: int,
    terrain: ScalableTerrainField,
    axis: str,
    *,
    fixed_mm: int = 0,
) -> tuple[int, ...]:
    minimum = _require_int("minimum", minimum)
    maximum = _require_int("maximum", maximum)
    fixed_mm = _require_int("fixed_mm", fixed_mm)
    if minimum >= maximum:
        raise ValueError("axis extent must be increasing")
    if axis not in {"x", "y"}:
        raise ValueError("axis must be x or y")
    seams = tuple(value for value in _seam_coordinates(minimum, maximum) if value > minimum)
    values = [minimum]
    while values[-1] < maximum:
        current = values[-1]
        if axis == "x":
            spacing_m = terrain.spacing_at(current / 1_000.0, fixed_mm / 1_000.0)
        else:
            spacing_m = terrain.spacing_at(fixed_mm / 1_000.0, current / 1_000.0)
        nominal_right = current + int(round(spacing_m * 1_000.0))
        next_seam = next((seam for seam in seams if seam > current), maximum)
        right = min(nominal_right, next_seam, maximum)
        if right <= current:
            raise ValueError("terrain lattice spacing must advance")
        values.append(right)
    return tuple(values)


def _row_interval_authority(
    left_x_mm: int,
    right_x_mm: int,
    row_y_mm: int,
    terrain: ScalableTerrainField,
    extent: tuple[int, int, int, int],
) -> RowIntervalAuthority:
    left_x_mm = _require_int("left_x_mm", left_x_mm)
    right_x_mm = _require_int("right_x_mm", right_x_mm)
    row_y_mm = _require_int("row_y_mm", row_y_mm)
    if right_x_mm <= left_x_mm:
        raise ValueError("row interval must advance")
    boundaries = tuple(sorted({extent[0], *_seam_coordinates(extent[0], extent[1]), extent[1]}))
    tile_left = max(value for value in boundaries if value <= left_x_mm)
    tile_right = min(value for value in boundaries if value > left_x_mm)
    nominal = int(round(terrain.spacing_at(left_x_mm / 1_000.0, row_y_mm / 1_000.0) * 1_000.0))
    realized = right_x_mm - left_x_mm
    return RowIntervalAuthority(
        row_y_mm,
        left_x_mm,
        tile_left,
        tile_right,
        terrain.cell_key_at(left_x_mm / 1_000.0, row_y_mm / 1_000.0),
        nominal,
        realized,
        right_x_mm == tile_right and realized < nominal,
    )


def _validate_row_interval_authority(
    road: PhysicalRoadRecord,
    terrain: ScalableTerrainField,
    extent: tuple[int, int, int, int],
) -> None:
    authority = road.row_interval
    if authority is None:
        raise ValueError("road has no row interval authority")
    expected = _row_interval_authority(
        authority.left_x_mm,
        authority.left_x_mm + authority.realized_spacing_mm,
        authority.row_y_mm,
        terrain,
        extent,
    )
    if authority != expected:
        raise ValueError("row interval authority does not match terrain owner and seam rule")
    expected_points = (
        (authority.left_x_mm, authority.row_y_mm),
        (authority.left_x_mm + authority.realized_spacing_mm, authority.row_y_mm),
    )
    if road.points_mm != expected_points:
        raise ValueError("horizontal road geometry does not match its row interval authority")


def _monotone_partial_match(
    lower: Sequence[int],
    upper: Sequence[int],
) -> tuple[tuple[int, int], ...]:
    if len(lower) < 2 or len(upper) < 2:
        raise ValueError("row strip requires at least two boundary vertices")
    if len(lower) <= len(upper):
        pairs = tuple(
            (index, round(index * (len(upper) - 1) / (len(lower) - 1)))
            for index in range(len(lower))
        )
    else:
        pairs = tuple(
            (round(index * (len(lower) - 1) / (len(upper) - 1)), index)
            for index in range(len(upper))
        )
    if any(left >= right for (left, _), (right, _) in zip(pairs, pairs[1:])) or any(
        left >= right for (_, left), (_, right) in zip(pairs, pairs[1:])
    ):
        raise ValueError("row strip matching must be strictly monotone")
    return pairs
