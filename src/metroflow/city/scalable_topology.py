"""Standalone deterministic Task3 S2 physical-topology kernel."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from math import isfinite
from typing import Sequence

from metroflow.city.scale import CityScaleSpec

SCHEMA_VERSION = "tmfcg_s2_v1"
TILE_SIZE_M = 2_000.0
TERRAIN_CELL_SIZE_M = 50.0
MAX_JUNCTIONS = 120_000
MAX_PHYSICAL_ROADS = 300_000
MAX_SURFACE_DEGREE = 4
STYLE_IDS = (
    "ring_radial",
    "grid_core",
    "polycentric_tod",
    "river_constrained",
    "superblock_mixed",
    "organic",
)


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


def _node_semantic_id(
    seed: int,
    style_id: str,
    role: str,
    x_mm: int,
    y_mm: int,
    layer: int,
) -> str:
    return _semantic_id((SCHEMA_VERSION, "node", seed, style_id, role, (x_mm, y_mm, layer)))


def _road_semantic_id(
    seed: int,
    style_id: str,
    role: str,
    start_semantic_id: str,
    end_semantic_id: str,
    points_mm: tuple[tuple[int, int], ...],
    hierarchy: RoadHierarchy,
    facility: FacilityKind,
    layer: int,
    directions: frozenset[str],
    transition: tuple[int, int] | None,
    structure_group: str | None,
    failure_group: str | None,
    profile_id: str,
    provenance: str,
    row_interval: RowIntervalAuthority | None = None,
) -> str:
    ordered_directions = tuple(sorted(directions))
    reversed_directions = tuple(
        sorted(
            "reverse"
            if direction == "forward"
            else "forward"
            if direction == "reverse"
            else direction
            for direction in ordered_directions
        )
    )
    orientation = min(
        (start_semantic_id, end_semantic_id, points_mm, ordered_directions),
        (
            end_semantic_id,
            start_semantic_id,
            tuple(reversed(points_mm)),
            reversed_directions,
        ),
    )
    return _semantic_id(
        (
            SCHEMA_VERSION,
            "road",
            seed,
            style_id,
            role,
            orientation,
            hierarchy.value,
            facility.value,
            layer,
            transition,
            structure_group,
            failure_group,
            profile_id,
            provenance,
            _row_interval_content(row_interval),
        )
    )


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


@dataclass(frozen=True, slots=True)
class StructuralAudit:
    is_connected: bool
    same_layer_proper_crossing_count: int
    t_touch_count: int
    collinear_overlap_count: int
    self_intersection_count: int
    nonadjacent_weld_count: int
    duplicate_road_count: int
    different_layer_false_junction_count: int
    endpoint_anchor_mismatch_count: int
    center_disjoint_gateway_path_count: int
    river_cross_bank_group_count: int
    river_group_removal_failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScalableStreetNetwork:
    scale_spec: ScalableScaleSnapshot
    style_id: str
    seed: int
    schema_version: str
    scale_fingerprint: str
    style_fingerprint: str
    extent_mm: tuple[int, int, int, int]
    width_m: float
    height_m: float
    centers: tuple[tuple[int, int], ...]
    gateway_node_ids: tuple[int, ...]
    nodes: tuple[PhysicalNodeRecord, ...]
    roads: tuple[PhysicalRoadRecord, ...]
    endpoint_incidence: tuple[tuple[int, tuple[int, ...]], ...]
    terrain: ScalableTerrainField
    tile_coordinates: tuple[tuple[int, int], ...]
    seam_diagnostics: tuple[tuple[str, int], ...]
    hidden_repair_count: int
    fingerprint: str

    def __post_init__(self) -> None:
        if type(self) is not ScalableStreetNetwork:
            raise TypeError("network must be an exact ScalableStreetNetwork")
        if type(self.scale_spec) is not ScalableScaleSnapshot:
            raise TypeError("scale_spec must be an exact ScalableScaleSnapshot")
        if type(self.terrain) is not ScalableTerrainField:
            raise TypeError("terrain must be an exact ScalableTerrainField")
        style_id = _snapshot_str("style_id", self.style_id)
        if style_id not in STYLE_IDS:
            raise ValueError("style_id must be supported")
        schema_version = _snapshot_str("schema_version", self.schema_version)
        if schema_version != SCHEMA_VERSION:
            raise ValueError("schema_version is not canonical")
        object.__setattr__(self, "style_id", style_id)
        object.__setattr__(self, "seed", _require_int("network seed", self.seed))
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(
            self, "scale_fingerprint", _require_digest("scale_fingerprint", self.scale_fingerprint)
        )
        object.__setattr__(
            self, "style_fingerprint", _require_digest("style_fingerprint", self.style_fingerprint)
        )
        object.__setattr__(self, "fingerprint", _require_digest("fingerprint", self.fingerprint))
        extent = _snapshot_tuple("extent_mm", self.extent_mm)
        if len(extent) != 4:
            raise ValueError("extent_mm must contain four integers")
        object.__setattr__(
            self, "extent_mm", tuple(_require_int("extent_mm", value) for value in extent)
        )
        if type(self.width_m) not in (int, float) or type(self.height_m) not in (int, float):
            raise TypeError("network dimensions must be exact built-in numbers")
        object.__setattr__(self, "width_m", float(self.width_m))
        object.__setattr__(self, "height_m", float(self.height_m))
        object.__setattr__(
            self,
            "centers",
            tuple(
                _snapshot_int_pair("center", center)
                for center in _snapshot_tuple("centers", self.centers)
            ),
        )
        object.__setattr__(
            self,
            "gateway_node_ids",
            tuple(
                _require_int("gateway_node_id", value)
                for value in _snapshot_tuple("gateway_node_ids", self.gateway_node_ids)
            ),
        )
        nodes = _snapshot_tuple("nodes", self.nodes)
        roads = _snapshot_tuple("roads", self.roads)
        if any(type(node) is not PhysicalNodeRecord for node in nodes):
            raise TypeError("nodes must contain exact PhysicalNodeRecord values")
        if any(type(road) is not PhysicalRoadRecord for road in roads):
            raise TypeError("roads must contain exact PhysicalRoadRecord values")
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "roads", roads)
        incidence = tuple(
            (
                _require_int("incidence node_id", node_id),
                tuple(_require_int("incidence road_id", road_id) for road_id in road_ids),
            )
            for node_id, road_ids in _snapshot_tuple("endpoint_incidence", self.endpoint_incidence)
        )
        object.__setattr__(self, "endpoint_incidence", incidence)
        object.__setattr__(
            self,
            "tile_coordinates",
            tuple(
                _snapshot_int_pair("tile coordinate", value)
                for value in _snapshot_tuple("tile_coordinates", self.tile_coordinates)
            ),
        )
        object.__setattr__(
            self,
            "seam_diagnostics",
            tuple(
                (_snapshot_str("diagnostic name", name), _require_int("diagnostic count", count))
                for name, count in _snapshot_tuple("seam_diagnostics", self.seam_diagnostics)
            ),
        )
        hidden_repair_count = _require_int("hidden_repair_count", self.hidden_repair_count)
        if hidden_repair_count != 0:
            raise ValueError("hidden_repair_count must be zero")
        object.__setattr__(self, "hidden_repair_count", hidden_repair_count)
        by_id = {node.node_id: node for node in self.nodes}
        _validate_terrain_network_authority(self)
        _validate_canonical_generated_authority(self, by_id)
        _validate_exact_canonical_record_set(self, by_id)


def audit_physical_records(
    nodes: Sequence[PhysicalNodeRecord], roads: Sequence[PhysicalRoadRecord]
) -> StructuralAudit:
    node_records, road_records = tuple(nodes), tuple(roads)
    node_ids = [node.node_id for node in node_records]
    node_semantics = [node.semantic_id for node in node_records]
    if len(node_ids) != len(set(node_ids)) or len(node_semantics) != len(set(node_semantics)):
        raise ValueError("duplicate node dense or semantic id")
    road_ids = [road.road_id for road in road_records]
    road_semantics = [road.semantic_id for road in road_records]
    if len(road_ids) != len(set(road_ids)) or len(road_semantics) != len(set(road_semantics)):
        raise ValueError("duplicate road dense or semantic id")
    by_id = {node.node_id: node for node in node_records}
    incidence: dict[int, list[int]] = defaultdict(list)
    anchor_mismatches = false_layer_junctions = duplicates = 0
    duplicate_keys: set[tuple[object, ...]] = set()
    segments: list[tuple[int, int, int, tuple[int, int], tuple[int, int]]] = []
    for road in road_records:
        start, end = by_id.get(road.start_node_id), by_id.get(road.end_node_id)
        if start is None or end is None:
            anchor_mismatches += 2
        else:
            anchor_mismatches += int(start.point_mm != road.points_mm[0])
            anchor_mismatches += int(end.point_mm != road.points_mm[-1])
            incidence[start.node_id].append(road.road_id)
            incidence[end.node_id].append(road.road_id)
            endpoint_layers = (start.layer, end.layer)
            if road.facility is FacilityKind.RAMP:
                if road.layer_transition is None or frozenset(endpoint_layers) != frozenset(
                    road.layer_transition
                ):
                    false_layer_junctions += 1
            elif any(layer != road.layer for layer in endpoint_layers):
                false_layer_junctions += 1
        duplicates += int(road.canonical_key in duplicate_keys)
        duplicate_keys.add(road.canonical_key)
        segments.extend(
            (road.road_id, road.layer, index, left, right)
            for index, (left, right) in enumerate(zip(road.points_mm, road.points_mm[1:]))
        )
    proper, touches, overlaps, self_intersections = _segment_audit(segments)
    vertex_touches, vertex_welds = _polyline_vertex_audit(road_records)
    return StructuralAudit(
        _is_connected(tuple(node_ids), incidence, road_records),
        proper,
        touches + vertex_touches,
        overlaps,
        self_intersections,
        _nonadjacent_welds(node_records) + vertex_welds,
        duplicates,
        false_layer_junctions,
        anchor_mismatches,
        0,
        0,
        (),
    )


def audit_structural_network(network: ScalableStreetNetwork) -> StructuralAudit:
    base = audit_physical_records(network.nodes, network.roads)
    center_paths = sum(_two_gateway_paths(network, center) for center in network.centers)
    river_group_count, river_failures = _river_group_audit(network)
    return StructuralAudit(
        base.is_connected,
        base.same_layer_proper_crossing_count,
        base.t_touch_count,
        base.collinear_overlap_count,
        base.self_intersection_count,
        base.nonadjacent_weld_count,
        base.duplicate_road_count,
        base.different_layer_false_junction_count,
        base.endpoint_anchor_mismatch_count,
        center_paths,
        river_group_count,
        river_failures,
    )


def _is_connected(
    node_ids: tuple[int, ...],
    incidence: dict[int, list[int]],
    roads: Sequence[PhysicalRoadRecord],
) -> bool:
    if not node_ids:
        return False
    roads_by_id = {road.road_id: road for road in roads}
    seen, queue = {node_ids[0]}, deque((node_ids[0],))
    while queue:
        node_id = queue.popleft()
        for road_id in incidence.get(node_id, ()):
            road = roads_by_id[road_id]
            other = road.end_node_id if road.start_node_id == node_id else road.start_node_id
            if other not in seen:
                seen.add(other)
                queue.append(other)
    return len(seen) == len(node_ids)


def _segment_audit(
    segments: Sequence[tuple[int, int, int, tuple[int, int], tuple[int, int]]],
) -> tuple[int, int, int, int]:
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, (_road_id, _layer, _segment_index, left, right) in enumerate(segments):
        for cell in _segment_supercover_cells(left, right, 250_000):
            buckets[cell].append(index)
    checked: set[tuple[int, int]] = set()
    proper = touches = overlaps = self_intersections = 0
    for entries in buckets.values():
        for offset, left_index in enumerate(entries):
            for right_index in entries[offset + 1 :]:
                pair = tuple(sorted((left_index, right_index)))
                if pair in checked:
                    continue
                checked.add(pair)
                left_road, left_layer, left_segment, a, b = segments[left_index]
                right_road, right_layer, right_segment, c, d = segments[right_index]
                if left_layer != right_layer:
                    continue
                same_road = left_road == right_road
                if same_road and abs(left_segment - right_segment) <= 1:
                    continue
                if _proper_intersection(a, b, c, d):
                    if same_road:
                        self_intersections += 1
                    else:
                        proper += 1
                overlaps += int(_collinear_overlap(a, b, c, d))
                touches += sum(
                    _point_in_open_segment(point, other_left, other_right)
                    for point, other_left, other_right in (
                        (a, c, d),
                        (b, c, d),
                        (c, a, b),
                        (d, a, b),
                    )
                )
    return (proper, touches, overlaps, self_intersections)


def _segment_supercover_cells(
    left: tuple[int, int], right: tuple[int, int], cell_mm: int
) -> tuple[tuple[int, int], ...]:
    cell_mm = _require_int("cell_mm", cell_mm)
    if cell_mm <= 0:
        raise ValueError("cell_mm must be positive")
    dx, dy = right[0] - left[0], right[1] - left[1]
    events = {Fraction(0), Fraction(1)}
    for start, delta in ((left[0], dx), (left[1], dy)):
        if delta == 0:
            continue
        low, high = sorted((start, start + delta))
        for grid_line in range(low // cell_mm + 1, (high - 1) // cell_mm + 1):
            event = Fraction(grid_line * cell_mm - start, delta)
            if 0 < event < 1:
                events.add(event)
    ordered = sorted(events)
    cells: set[tuple[int, int]] = set()

    def add_point(x: Fraction, y: Fraction) -> None:
        x_denominator, y_denominator = x.denominator * cell_mm, y.denominator * cell_mm
        x_cell, y_cell = x.numerator // x_denominator, y.numerator // y_denominator
        x_cells = (x_cell - 1, x_cell) if x.numerator % x_denominator == 0 else (x_cell,)
        y_cells = (y_cell - 1, y_cell) if y.numerator % y_denominator == 0 else (y_cell,)
        cells.update((cell_x, cell_y) for cell_x in x_cells for cell_y in y_cells)

    for event in ordered:
        add_point(Fraction(left[0]) + event * dx, Fraction(left[1]) + event * dy)
    for first, second in zip(ordered, ordered[1:]):
        middle = (first + second) / 2
        add_point(Fraction(left[0]) + middle * dx, Fraction(left[1]) + middle * dy)
    return tuple(sorted(cells))


def _proper_intersection(a, b, c, d) -> bool:
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    ab_c, ab_d = orient(a, b, c), orient(a, b, d)
    cd_a, cd_b = orient(c, d, a), orient(c, d, b)
    if 0 in (ab_c, ab_d, cd_a, cd_b):
        return False
    return (ab_c > 0) != (ab_d > 0) and (cd_a > 0) != (cd_b > 0)


def _point_in_open_segment(point, left, right) -> bool:
    if (right[0] - left[0]) * (point[1] - left[1]) != (right[1] - left[1]) * (point[0] - left[0]):
        return False
    return (
        point not in (left, right)
        and min(left[0], right[0]) <= point[0] <= max(left[0], right[0])
        and min(left[1], right[1]) <= point[1] <= max(left[1], right[1])
    )


def _collinear_overlap(a, b, c, d) -> bool:
    cross_c = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    cross_d = (b[0] - a[0]) * (d[1] - a[1]) - (b[1] - a[1]) * (d[0] - a[0])
    if cross_c != 0 or cross_d != 0:
        return False
    if abs(b[0] - a[0]) >= abs(b[1] - a[1]):
        first, second = sorted((a[0], b[0])), sorted((c[0], d[0]))
    else:
        first, second = sorted((a[1], b[1])), sorted((c[1], d[1]))
    return max(first[0], second[0]) < min(first[1], second[1])


def _nonadjacent_welds(nodes: Sequence[PhysicalNodeRecord]) -> int:
    positions: dict[tuple[int, int, int], int] = defaultdict(int)
    for node in nodes:
        positions[(node.x_mm, node.y_mm, node.layer)] += 1
    return sum(count * (count - 1) // 2 for count in positions.values())


def _polyline_vertex_audit(roads: Sequence[PhysicalRoadRecord]) -> tuple[int, int]:
    interior: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    endpoints: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    welds = 0
    for road in roads:
        seen: set[tuple[int, int]] = set()
        for point in road.points_mm:
            welds += int(point in seen)
            seen.add(point)
        endpoints[(road.layer, *road.points_mm[0])].append(road.road_id)
        endpoints[(road.layer, *road.points_mm[-1])].append(road.road_id)
        for point in road.points_mm[1:-1]:
            interior[(road.layer, *point)].append(road.road_id)
    touches = 0
    for key, owners in interior.items():
        unique_owners = set(owners)
        welds += len(unique_owners) * (len(unique_owners) - 1) // 2
        touches += sum(road_id not in unique_owners for road_id in endpoints.get(key, ()))
    return (touches, welds)


def _road_self_intersections(road: PhysicalRoadRecord) -> int:
    segments = tuple(zip(road.points_mm, road.points_mm[1:]))
    return sum(
        _proper_intersection(left_a, left_b, right_a, right_b)
        for index, (left_a, left_b) in enumerate(segments)
        for right_a, right_b in segments[index + 2 :]
    )


@dataclass(frozen=True, slots=True)
class _NodeSpec:
    semantic_id: str
    x_mm: int
    y_mm: int
    layer: int
    semantic_role: str


@dataclass(frozen=True, slots=True)
class _RoadSpec:
    semantic_id: str
    start_semantic_id: str
    end_semantic_id: str
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
    semantic_role: str
    row_interval: RowIntervalAuthority | None


@dataclass(frozen=True, slots=True)
class _CanonicalGeneratedSpecs:
    nodes: tuple[_NodeSpec, ...]
    roads: tuple[_RoadSpec, ...]
    gateway_semantic_ids: tuple[str, ...]
    centers: tuple[tuple[int, int], ...]


def _centers(
    x_values: tuple[int, ...],
    y_values: tuple[int, ...],
    style_id: str,
    area_km2: float,
) -> tuple[tuple[int, int], ...]:
    if style_id in {"ring_radial", "grid_core", "organic"}:
        count = 1
    elif style_id in {"polycentric_tod", "superblock_mixed"}:
        count = max(3, min(8, round(area_km2 / 50.0)))
    else:
        count = max(2, min(5, round(area_km2 / 80.0)))
    center_y = min(y_values, key=abs)
    if count == 1:
        return ((min(x_values, key=abs), center_y),)
    return tuple(
        (x_values[round((index + 1) * (len(x_values) - 1) / (count + 1))], center_y)
        for index in range(count)
    )


def _surface_hierarchy(
    row: int,
    column: int,
    left_x: int,
    left_y: int,
    right_x: int,
    right_y: int,
    style_id: str,
    centers: tuple[tuple[int, int], ...],
    horizontal: bool,
) -> RoadHierarchy:
    if style_id == "ring_radial" and (
        (horizontal and left_y == centers[0][1])
        or (not horizontal and left_x == right_x == centers[0][0])
    ):
        return RoadHierarchy.ARTERIAL
    if style_id == "polycentric_tod":
        distance = min(
            min(
                (left_x - center_x) ** 2 + (left_y - center_y) ** 2,
                (right_x - center_x) ** 2 + (right_y - center_y) ** 2,
            )
            for center_x, center_y in centers
        )
        if distance < 900_000**2:
            return RoadHierarchy.ARTERIAL
    if style_id == "superblock_mixed":
        midpoint_x = (left_x + right_x) // 2
        midpoint_y = (left_y + right_y) // 2
        district = math.floor(midpoint_x / 2_000_000) + math.floor(midpoint_y / 2_000_000)
        if (district % 2 == 0) == horizontal:
            return RoadHierarchy.COLLECTOR
        if row % 9 == 0 or column % 9 == 0:
            return RoadHierarchy.ARTERIAL
        return RoadHierarchy.LOCAL
    if row % 9 == 0 or column % 9 == 0:
        return RoadHierarchy.ARTERIAL
    if row % 3 == 0 or column % 3 == 0:
        return RoadHierarchy.COLLECTOR
    return RoadHierarchy.LOCAL


def _surface_semantic_role(
    base_role: str,
    left_x: int,
    left_y: int,
    right_x: int,
    right_y: int,
    style_id: str,
    centers: tuple[tuple[int, int], ...],
    hierarchy: RoadHierarchy,
) -> str:
    if style_id == "polycentric_tod" and hierarchy is RoadHierarchy.ARTERIAL:
        center_index = min(
            range(len(centers)),
            key=lambda index: min(
                (left_x - centers[index][0]) ** 2 + (left_y - centers[index][1]) ** 2,
                (right_x - centers[index][0]) ** 2 + (right_y - centers[index][1]) ** 2,
            ),
        )
        return f"polycentric-center-{center_index}-{base_role}"
    if style_id == "superblock_mixed" and hierarchy is RoadHierarchy.COLLECTOR:
        orientation = "horizontal" if left_y == right_y else "vertical"
        return f"superblock-{orientation}-collector"
    return base_role


def _organic_connector_points(
    seed: int,
    start: tuple[int, int],
    end: tuple[int, int],
    extent: tuple[int, int, int, int],
) -> tuple[tuple[int, int], ...]:
    payload = f"{seed}:{start[0]}:{start[1]}:{end[0]}:{end[1]}".encode()
    raw = int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")
    displacement = 1 + raw % 5_000
    if raw & 1:
        displacement = -displacement
    midpoint_x = (start[0] + end[0]) // 2
    midpoint_y = (start[1] + end[1]) // 2
    min_x, max_x, min_y, max_y = extent
    if not min_x <= midpoint_x + displacement <= max_x:
        displacement = -displacement
    midpoint = (midpoint_x + displacement, midpoint_y)
    if not (min_x <= midpoint[0] <= max_x and min_y <= midpoint[1] <= max_y):
        raise ValueError("organic connector midpoint cannot fit declared extent")
    return (start, midpoint, end)


def _canonical_generated_specs(
    scale_spec: ScalableScaleSnapshot,
    style_id: str,
    seed: int,
    terrain: ScalableTerrainField,
    extent: tuple[int, int, int, int],
) -> _CanonicalGeneratedSpecs:
    if style_id not in STYLE_IDS:
        raise ValueError("style_id must be supported by the topology generator")
    y_values = _local_axis(extent[2], extent[3], terrain, "y")
    row_x_values = {
        y_mm: tuple(
            x_mm
            for x_mm in _local_axis(extent[0], extent[1], terrain, "x", fixed_mm=y_mm)
            if style_id != "river_constrained" or x_mm != terrain.barrier_seam_x_mm
        )
        for y_mm in y_values
    }
    center_row = min(y_values, key=abs)
    centers = _centers(row_x_values[center_row], y_values, style_id, scale_spec.urbanized_area_km2)
    node_by_key: dict[tuple[int, int, int], _NodeSpec] = {}
    road_specs: list[_RoadSpec] = []

    def node_at(x_mm: int, y_mm: int, layer: int, role: str) -> _NodeSpec:
        key = (x_mm, y_mm, layer)
        existing = node_by_key.get(key)
        if existing is not None:
            return existing
        spec = _NodeSpec(
            _node_semantic_id(seed, style_id, role, x_mm, y_mm, layer),
            x_mm,
            y_mm,
            layer,
            role,
        )
        node_by_key[key] = spec
        return spec

    def road_between(
        role: str,
        start: _NodeSpec,
        end: _NodeSpec,
        hierarchy: RoadHierarchy,
        facility: FacilityKind,
        layer: int,
        *,
        transition: tuple[int, int] | None = None,
        structure_group: str | None = None,
        failure_group: str | None = None,
        row_interval: RowIntervalAuthority | None = None,
        points: tuple[tuple[int, int], ...] | None = None,
    ) -> None:
        points = points or ((start.x_mm, start.y_mm), (end.x_mm, end.y_mm))
        directions = frozenset({"forward", "reverse"})
        profile = _profile_for(facility, hierarchy)
        provenance = "tmfcg_s2_construction"
        semantic_id = _road_semantic_id(
            seed,
            style_id,
            role,
            start.semantic_id,
            end.semantic_id,
            points,
            hierarchy,
            facility,
            layer,
            directions,
            transition,
            structure_group,
            failure_group,
            profile,
            provenance,
            row_interval,
        )
        road_specs.append(
            _RoadSpec(
                semantic_id,
                start.semantic_id,
                end.semantic_id,
                points,
                hierarchy,
                facility,
                layer,
                directions,
                transition,
                structure_group,
                failure_group,
                profile,
                provenance,
                role,
                row_interval,
            )
        )

    surface = {
        (x_mm, y_mm): node_at(x_mm, y_mm, 0, "surface")
        for y_mm in y_values
        for x_mm in row_x_values[y_mm]
    }
    for row, y_mm in enumerate(y_values):
        values = row_x_values[y_mm]
        for column, (left, right) in enumerate(zip(values, values[1:])):
            if style_id == "river_constrained" and left < 0 < right:
                continue
            hierarchy = _surface_hierarchy(
                row, column, left, y_mm, right, y_mm, style_id, centers, True
            )
            role = _surface_semantic_role(
                "surface-horizontal",
                left,
                y_mm,
                right,
                y_mm,
                style_id,
                centers,
                hierarchy,
            )
            road_between(
                role,
                surface[(left, y_mm)],
                surface[(right, y_mm)],
                hierarchy,
                FacilityKind.SURFACE,
                0,
                row_interval=_row_interval_authority(left, right, y_mm, terrain, extent),
            )
    for row, (lower_y, upper_y) in enumerate(zip(y_values, y_values[1:])):
        lower, upper = row_x_values[lower_y], row_x_values[upper_y]
        row_pairs = ((lower, upper),)
        if style_id == "river_constrained":
            row_pairs = (
                (
                    tuple(x_mm for x_mm in lower if x_mm < 0),
                    tuple(x_mm for x_mm in upper if x_mm < 0),
                ),
                (
                    tuple(x_mm for x_mm in lower if x_mm > 0),
                    tuple(x_mm for x_mm in upper if x_mm > 0),
                ),
            )
        for lower_bank, upper_bank in row_pairs:
            for column, (lower_index, upper_index) in enumerate(
                _monotone_partial_match(lower_bank, upper_bank)
            ):
                lower_x, upper_x = lower_bank[lower_index], upper_bank[upper_index]
                hierarchy = _surface_hierarchy(
                    row,
                    column,
                    lower_x,
                    lower_y,
                    upper_x,
                    upper_y,
                    style_id,
                    centers,
                    False,
                )
                role = _surface_semantic_role(
                    "surface-vertical",
                    lower_x,
                    lower_y,
                    upper_x,
                    upper_y,
                    style_id,
                    centers,
                    hierarchy,
                )
                points = None
                if style_id == "organic":
                    role = "organic-connector"
                    points = _organic_connector_points(
                        seed, (lower_x, lower_y), (upper_x, upper_y), extent
                    )
                road_between(
                    role,
                    surface[(lower_x, lower_y)],
                    surface[(upper_x, upper_y)],
                    hierarchy,
                    FacilityKind.SURFACE,
                    0,
                    points=points,
                )

    if style_id == "river_constrained":
        bridge_rows = tuple(
            sorted({len(y_values) // 4, len(y_values) // 2, 3 * len(y_values) // 4})
        )
        for group_index, row_index in enumerate(bridge_rows):
            y_mm = y_values[row_index]
            row_values = row_x_values[y_mm]
            left_x = max(x_mm for x_mm in row_values if x_mm < 0)
            right_x = min(x_mm for x_mm in row_values if x_mm > 0)
            group = f"river-bridge-group-{group_index}"
            road_between(
                "river-bridge",
                surface[(left_x, y_mm)],
                surface[(right_x, y_mm)],
                RoadHierarchy.ARTERIAL,
                FacilityKind.BRIDGE,
                0,
                structure_group=group,
                failure_group=group,
            )

    min_x, max_x, min_y, max_y = extent
    gateway_points = (
        (min_x, min_y),
        (0, min_y),
        (max_x, min_y),
        (max_x, 0),
        (max_x, max_y),
        (0, max_y),
        (min_x, max_y),
        (min_x, 0),
    )
    upper_nodes = tuple(node_at(x_mm, y_mm, 1, "mainline-gateway") for x_mm, y_mm in gateway_points)
    for start, end in zip(upper_nodes, upper_nodes[1:] + upper_nodes[:1]):
        road_between(
            "perimeter-mainline",
            start,
            end,
            RoadHierarchy.EXPRESSWAY,
            FacilityKind.MAINLINE,
            1,
        )

    surface_degree: dict[str, int] = defaultdict(int)
    for road in road_specs:
        if road.facility in {FacilityKind.SURFACE, FacilityKind.BRIDGE}:
            surface_degree[road.start_semantic_id] += 1
            surface_degree[road.end_semantic_id] += 1

    def horizontal_neighbour(anchor: _NodeSpec) -> _NodeSpec | None:
        values = row_x_values[anchor.y_mm]
        index = values.index(anchor.x_mm)
        if style_id == "river_constrained":
            direction = -1 if anchor.x_mm < 0 else 1
        elif anchor.x_mm == min_x or (anchor.x_mm not in {min_x, max_x} and anchor.x_mm <= 0):
            direction = 1
        else:
            direction = -1
        neighbour_index = index + direction
        if not 0 <= neighbour_index < len(values):
            return None
        return surface[(values[neighbour_index], anchor.y_mm)]

    reserved_anchors: set[str] = set()
    surface_segments = tuple(
        (left, right)
        for road in road_specs
        if road.layer == 0
        for left, right in zip(road.points_mm, road.points_mm[1:])
    )
    for index, upper in enumerate(upper_nodes):
        candidates = []
        for anchor in surface.values():
            if anchor.x_mm not in {min_x, max_x} and anchor.y_mm not in {min_y, max_y}:
                continue
            neighbour = horizontal_neighbour(anchor)
            if (
                neighbour is None
                or anchor.semantic_id in reserved_anchors
                or neighbour.semantic_id in reserved_anchors
                or surface_degree[anchor.semantic_id] > 3
                or surface_degree[neighbour.semantic_id] > 3
            ):
                continue
            distance = (anchor.x_mm - upper.x_mm) ** 2 + (anchor.y_mm - upper.y_mm) ** 2
            candidates.append((distance, anchor.semantic_id, anchor, neighbour))
        if not candidates:
            raise ValueError("mainline gateway lacks a bounded surface access triangle")

        def carrier_is_clear(
            access_point: tuple[int, int],
            candidate_anchor: _NodeSpec,
            candidate_neighbour: _NodeSpec,
        ) -> bool:
            for endpoint in (
                (candidate_anchor.x_mm, candidate_anchor.y_mm),
                (candidate_neighbour.x_mm, candidate_neighbour.y_mm),
            ):
                for left, right in surface_segments:
                    if (
                        _proper_intersection(access_point, endpoint, left, right)
                        or _collinear_overlap(access_point, endpoint, left, right)
                        or _point_in_open_segment(access_point, left, right)
                        or _point_in_open_segment(endpoint, left, right)
                        or _point_in_open_segment(left, access_point, endpoint)
                        or _point_in_open_segment(right, access_point, endpoint)
                    ):
                        return False
            return True

        selection = None
        for _, _, candidate_anchor, candidate_neighbour in sorted(
            candidates,
            key=lambda item: (item[0], item[1]),
        ):
            y_index = y_values.index(candidate_anchor.y_mm)
            if candidate_anchor.y_mm == min_y:
                dy = (y_values[y_index + 1] - candidate_anchor.y_mm) // 3
            elif candidate_anchor.y_mm == max_y:
                dy = (y_values[y_index - 1] - candidate_anchor.y_mm) // 3
            elif candidate_anchor.y_mm <= 0:
                dy = (y_values[y_index + 1] - candidate_anchor.y_mm) // 3
            else:
                dy = (y_values[y_index - 1] - candidate_anchor.y_mm) // 3
            if dy == 0:
                continue
            for numerator, denominator in ((1, 3), (1, 2), (2, 3)):
                candidate_point = (
                    candidate_anchor.x_mm
                    + (candidate_neighbour.x_mm - candidate_anchor.x_mm) * numerator // denominator,
                    candidate_anchor.y_mm + dy,
                )
                if carrier_is_clear(
                    candidate_point,
                    candidate_anchor,
                    candidate_neighbour,
                ):
                    selection = (
                        candidate_anchor,
                        candidate_neighbour,
                        candidate_point,
                    )
                    break
            if selection is not None:
                break
        if selection is None:
            raise ValueError("surface access triangle cannot avoid existing surface geometry")
        anchor, neighbour, access_point = selection
        reserved_anchors.update((anchor.semantic_id, neighbour.semantic_id))
        access = node_at(*access_point, 0, f"ramp-access-{index}")
        road_between(
            "mainline-ramp",
            access,
            upper,
            RoadHierarchy.ARTERIAL,
            FacilityKind.RAMP,
            1,
            transition=(0, 1),
        )
        road_between(
            "surface-access-primary",
            access,
            anchor,
            RoadHierarchy.ARTERIAL,
            FacilityKind.SURFACE,
            0,
        )
        road_between(
            "surface-access-secondary",
            access,
            neighbour,
            RoadHierarchy.ARTERIAL,
            FacilityKind.SURFACE,
            0,
        )
        surface_segments += (
            (access_point, (anchor.x_mm, anchor.y_mm)),
            (access_point, (neighbour.x_mm, neighbour.y_mm)),
        )
    return _CanonicalGeneratedSpecs(
        tuple(sorted(node_by_key.values(), key=lambda item: item.semantic_id)),
        tuple(sorted(road_specs, key=lambda item: item.semantic_id)),
        tuple(gateway.semantic_id for gateway in upper_nodes),
        centers,
    )


def _row_interval_content(authority: RowIntervalAuthority | None) -> tuple | None:
    if authority is None:
        return None
    return (
        authority.row_y_mm,
        authority.left_x_mm,
        authority.tile_left_mm,
        authority.tile_right_mm,
        authority.owner_cell,
        authority.nominal_spacing_mm,
        authority.realized_spacing_mm,
        authority.seam_truncated,
    )


def _node_content(node: PhysicalNodeRecord) -> tuple:
    return (node.node_id, node.semantic_id, node.x_mm, node.y_mm, node.layer, node.semantic_role)


def _road_content(road: PhysicalRoadRecord) -> tuple:
    return (
        road.road_id,
        road.semantic_id,
        road.start_node_id,
        road.end_node_id,
        road.points_mm,
        road.hierarchy.value,
        road.facility.value,
        road.layer,
        tuple(sorted(road.access_directions)),
        road.layer_transition,
        road.structure_group,
        road.failure_group,
        road.profile_id,
        road.provenance,
        road.semantic_role,
        _row_interval_content(road.row_interval),
    )


def _style_fingerprint(
    style_id: str,
    seed: int,
    centers: Sequence[tuple[int, int]],
    nodes: Sequence[PhysicalNodeRecord],
    roads: Sequence[PhysicalRoadRecord],
) -> str:
    return _semantic_id(
        (
            SCHEMA_VERSION,
            "style",
            style_id,
            seed,
            tuple(centers),
            tuple(_node_content(node) for node in nodes),
            tuple(_road_content(road) for road in roads),
        )
    )


def _endpoint_incidence(
    nodes: Sequence[PhysicalNodeRecord], roads: Sequence[PhysicalRoadRecord]
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    values: dict[int, list[int]] = {node.node_id: [] for node in nodes}
    for road in roads:
        values[road.start_node_id].append(road.road_id)
        values[road.end_node_id].append(road.road_id)
    return tuple((node_id, tuple(sorted(road_ids))) for node_id, road_ids in sorted(values.items()))


def _computed_seam_diagnostics(
    extent: tuple[int, int, int, int],
    nodes: Sequence[PhysicalNodeRecord],
    terrain: ScalableTerrainField,
    tiles: Sequence[tuple[int, int]],
) -> tuple[tuple[str, int], ...]:
    surface = tuple(node for node in nodes if node.layer == 0)
    x_coordinates = {node.x_mm for node in surface}
    y_coordinates = {node.y_mm for node in surface}
    x_seams = set(_seam_coordinates(extent[0], extent[1]))
    y_seams = set(_seam_coordinates(extent[2], extent[3]))
    barrier = terrain.barrier_seam_x_mm
    expected_x = x_seams - ({barrier} if barrier is not None else set())
    mismatch_count = len(expected_x - x_coordinates) + len(y_seams - y_coordinates)
    return (
        ("barrier_seam_exception_count", int(barrier is not None)),
        ("seam_mismatch_count", mismatch_count),
        ("tile_count", len(tuple(tiles))),
    )


def _crosses_barrier(road: PhysicalRoadRecord, barrier_x_mm: int) -> bool:
    barrier_x_mm = _require_int("barrier_x_mm", barrier_x_mm)
    return any(
        left[0] != right[0] and min(left[0], right[0]) <= barrier_x_mm <= max(left[0], right[0])
        for left, right in zip(road.points_mm, road.points_mm[1:])
    )


def _roads_cross_bank_connected(
    network: ScalableStreetNetwork, roads: Sequence[PhysicalRoadRecord]
) -> bool:
    nodes = {node.node_id: node for node in network.nodes}
    adjacency: dict[int, set[int]] = defaultdict(set)
    for road in roads:
        adjacency[road.start_node_id].add(road.end_node_id)
        adjacency[road.end_node_id].add(road.start_node_id)
    left = next(
        (node_id for node_id, node in nodes.items() if node.x_mm < 0 and node_id in adjacency),
        None,
    )
    if left is None:
        return False
    seen, queue = {left}, deque((left,))
    while queue:
        node_id = queue.popleft()
        for other in adjacency[node_id]:
            if other not in seen:
                seen.add(other)
                queue.append(other)
    return any(nodes[node_id].x_mm > 0 for node_id in seen)


def _river_bridge_groups(network: ScalableStreetNetwork) -> frozenset[str]:
    barrier = network.terrain.barrier_seam_x_mm
    if barrier is None:
        raise ValueError("river network requires explicit barrier seam authority")
    crossing_roads = tuple(
        road for road in network.roads if road.layer == 0 and _crosses_barrier(road, barrier)
    )
    if any(road.facility is not FacilityKind.BRIDGE for road in crossing_roads):
        raise ValueError("river barrier may be crossed only by bridge records")
    groups = frozenset(
        road.failure_group for road in crossing_roads if road.failure_group is not None
    )
    if len(groups) < 3:
        raise ValueError("river requires at least three independent bridge failure groups")
    for group in groups:
        members = tuple(road for road in crossing_roads if road.failure_group == group)
        if not _roads_cross_bank_connected(network, members):
            raise ValueError("each river bridge group must complete a cross-bank connection")
    return groups


def _surface_cross_bank_connected(network: ScalableStreetNetwork, *, excluded_group: str) -> bool:
    nodes = {node.node_id: node for node in network.nodes if node.layer == 0}
    roads = tuple(
        road
        for road in network.roads
        if road.facility in {FacilityKind.SURFACE, FacilityKind.BRIDGE}
        and road.failure_group != excluded_group
    )
    adjacency: dict[int, set[int]] = defaultdict(set)
    for road in roads:
        adjacency[road.start_node_id].add(road.end_node_id)
        adjacency[road.end_node_id].add(road.start_node_id)
    left = next((node_id for node_id, node in nodes.items() if node.x_mm < 0), None)
    if left is None:
        return False
    seen, queue = {left}, deque((left,))
    while queue:
        node_id = queue.popleft()
        for other in adjacency[node_id]:
            if other not in seen:
                seen.add(other)
                queue.append(other)
    return any(nodes[node_id].x_mm > 0 for node_id in seen)


def _effective_failure_group(road: PhysicalRoadRecord) -> str:
    return road.failure_group or f"road:{road.semantic_id}"


def _path_to_gateway(
    network: ScalableStreetNetwork,
    start: int,
    excluded: set[int],
    targets: set[int],
) -> tuple[tuple[int, ...], int] | None:
    roads = {road.road_id: road for road in network.roads}
    incidence = dict(network.endpoint_incidence)
    previous: dict[int, tuple[int, int] | None] = {start: None}
    queue = deque((start,))
    reached = None
    while queue:
        node_id = queue.popleft()
        if node_id in targets and node_id != start:
            reached = node_id
            break
        for road_id in incidence.get(node_id, ()):
            if road_id in excluded:
                continue
            road = roads[road_id]
            other = road.end_node_id if road.start_node_id == node_id else road.start_node_id
            if other not in previous:
                previous[other] = (node_id, road_id)
                queue.append(other)
    if reached is None:
        return None
    target = reached
    path = []
    while previous[target] is not None:
        parent, road_id = previous[target]
        path.append(road_id)
        target = parent
    return (tuple(path), reached)


def _two_gateway_paths(network: ScalableStreetNetwork, center: tuple[int, int]) -> bool:
    center_id = next(
        (node.node_id for node in network.nodes if node.layer == 0 and node.point_mm == center),
        None,
    )
    if center_id is None:
        return False
    first = _path_to_gateway(network, center_id, set(), set(network.gateway_node_ids))
    if first is None:
        return False
    first_roads, first_gateway = first
    roads = {road.road_id: road for road in network.roads}
    excluded_groups = {_effective_failure_group(roads[road_id]) for road_id in first_roads}
    excluded_roads = {
        road.road_id for road in network.roads if _effective_failure_group(road) in excluded_groups
    }
    return (
        _path_to_gateway(
            network,
            center_id,
            excluded_roads,
            set(network.gateway_node_ids) - {first_gateway},
        )
        is not None
    )


def _river_group_audit(network: ScalableStreetNetwork) -> tuple[int, tuple[str, ...]]:
    if network.style_id != "river_constrained":
        return (0, ())
    groups = _river_bridge_groups(network)
    failures = tuple(
        group
        for group in sorted(groups)
        if not _surface_cross_bank_connected(network, excluded_group=group)
    )
    return (len(groups), failures)


def _network_fingerprint(
    scale_spec: ScalableScaleSnapshot,
    style_id: str,
    seed: int,
    extent_mm: tuple[int, int, int, int],
    centers: Sequence[tuple[int, int]],
    gateway_node_ids: Sequence[int],
    nodes: Sequence[PhysicalNodeRecord],
    roads: Sequence[PhysicalRoadRecord],
    incidence: Sequence[tuple[int, tuple[int, ...]]],
    terrain: ScalableTerrainField,
    tiles: Sequence[tuple[int, int]],
    diagnostics: Sequence[tuple[str, int]],
    hidden_repair_count: int,
) -> str:
    return _semantic_id(
        (
            SCHEMA_VERSION,
            (scale_spec.target_population, scale_spec.urbanized_area_km2),
            style_id,
            seed,
            extent_mm,
            tuple(centers),
            tuple(gateway_node_ids),
            tuple(_node_content(node) for node in nodes),
            tuple(_road_content(road) for road in roads),
            tuple(incidence),
            (
                terrain.width_m,
                terrain.height_m,
                terrain.cell_size_m,
                terrain.tile_size_m,
                terrain.seed,
                terrain.style_id,
                terrain.barrier_seam_x_mm,
                terrain.fingerprint,
            ),
            tuple(tiles),
            tuple(diagnostics),
            hidden_repair_count,
        )
    )


def _validate_terrain_network_authority(network: ScalableStreetNetwork) -> None:
    width_mm, height_mm = _extent_mm(network.scale_spec.urbanized_area_km2)
    min_x, min_y = -width_mm // 2, -height_mm // 2
    expected_extent = (min_x, min_x + width_mm, min_y, min_y + height_mm)
    if network.extent_mm != expected_extent:
        raise ValueError("network extent does not match immutable scale authority")
    if (network.width_m, network.height_m) != (width_mm / 1_000.0, height_mm / 1_000.0):
        raise ValueError("network dimensions do not match extent authority")

    terrain = network.terrain
    if terrain.seed != network.seed:
        raise ValueError("terrain seed must equal network seed")
    if terrain.style_id != network.style_id:
        raise ValueError("terrain style must equal network style")
    if (terrain.width_m, terrain.height_m) != (network.width_m, network.height_m):
        raise ValueError("terrain dimensions must equal network extent")
    if terrain.cell_size_m != TERRAIN_CELL_SIZE_M:
        raise ValueError("terrain cell size is not canonical")
    if terrain.tile_size_m != TILE_SIZE_M:
        raise ValueError("terrain tile size is not canonical")
    expected_barrier = 0 if network.style_id == "river_constrained" else None
    if terrain.barrier_seam_x_mm != expected_barrier:
        raise ValueError("terrain barrier does not match style authority")
    expected_terrain_fingerprint = _terrain_fingerprint(
        terrain.width_m,
        terrain.height_m,
        terrain.seed,
        terrain.style_id,
        terrain.barrier_seam_x_mm,
        terrain.cell_size_m,
        terrain.tile_size_m,
    )
    if terrain.fingerprint != expected_terrain_fingerprint:
        raise ValueError("terrain fingerprint does not match terrain content")
    expected_scale_fingerprint = _semantic_id(
        (
            SCHEMA_VERSION,
            "scale",
            network.scale_spec.target_population,
            network.scale_spec.urbanized_area_km2,
        )
    )
    if network.scale_fingerprint != expected_scale_fingerprint:
        raise ValueError("scale fingerprint does not match immutable scale content")
    if network.tile_coordinates != _tile_domain(network.extent_mm):
        raise ValueError("tile coordinates do not match the exact extent domain")
    diagnostics = _computed_seam_diagnostics(
        network.extent_mm,
        network.nodes,
        terrain,
        network.tile_coordinates,
    )
    if network.seam_diagnostics != diagnostics:
        raise ValueError("seam diagnostics do not match constructed terrain authority")
    min_x, max_x, min_y, max_y = network.extent_mm
    if any(
        not (min_x <= node.x_mm <= max_x and min_y <= node.y_mm <= max_y) for node in network.nodes
    ) or any(
        not (min_x <= x_mm <= max_x and min_y <= y_mm <= max_y)
        for road in network.roads
        for x_mm, y_mm in road.points_mm
    ):
        raise ValueError("generated geometry lies outside immutable extent authority")


def _validate_exact_canonical_record_set(
    network: ScalableStreetNetwork,
    by_id: dict[int, PhysicalNodeRecord],
) -> None:
    if tuple(node.node_id for node in network.nodes) != tuple(range(len(network.nodes))):
        raise ValueError("node dense ids are not canonical")
    if tuple(road.road_id for road in network.roads) != tuple(range(len(network.roads))):
        raise ValueError("road dense ids are not canonical")
    if tuple(node.semantic_id for node in network.nodes) != tuple(
        sorted(node.semantic_id for node in network.nodes)
    ):
        raise ValueError("node semantic order is not canonical")
    if tuple(road.semantic_id for road in network.roads) != tuple(
        sorted(road.semantic_id for road in network.roads)
    ):
        raise ValueError("road semantic order is not canonical")
    if network.endpoint_incidence != _endpoint_incidence(network.nodes, network.roads):
        raise ValueError("endpoint incidence does not match exact record authority")

    expected = _canonical_generated_specs(
        network.scale_spec,
        network.style_id,
        network.seed,
        network.terrain,
        network.extent_mm,
    )
    actual_nodes = tuple(
        _NodeSpec(
            node.semantic_id,
            node.x_mm,
            node.y_mm,
            node.layer,
            node.semantic_role,
        )
        for node in network.nodes
    )
    if actual_nodes != expected.nodes:
        raise ValueError("node record set does not match complete canonical construction")
    try:
        actual_roads = tuple(
            _RoadSpec(
                road.semantic_id,
                by_id[road.start_node_id].semantic_id,
                by_id[road.end_node_id].semantic_id,
                road.points_mm,
                road.hierarchy,
                road.facility,
                road.layer,
                road.access_directions,
                road.layer_transition,
                road.structure_group,
                road.failure_group,
                road.profile_id,
                road.provenance,
                road.semantic_role,
                road.row_interval,
            )
            for road in network.roads
        )
        gateway_semantics = tuple(
            by_id[node_id].semantic_id for node_id in network.gateway_node_ids
        )
    except KeyError as error:
        raise ValueError("record set references a noncanonical node id") from error
    if actual_roads != expected.roads:
        raise ValueError("road record set does not match complete canonical construction")
    if gateway_semantics != expected.gateway_semantic_ids:
        raise ValueError("gateway set does not match complete canonical construction")
    if network.centers != expected.centers:
        raise ValueError("center set does not match complete canonical construction")


def _validate_canonical_generated_authority(
    network: ScalableStreetNetwork,
    by_id: dict[int, PhysicalNodeRecord],
) -> None:
    """Check each present generated record against deterministic construction."""
    for node in network.nodes:
        expected_semantic_id = _node_semantic_id(
            network.seed,
            network.style_id,
            node.semantic_role,
            node.x_mm,
            node.y_mm,
            node.layer,
        )
        if node.semantic_id != expected_semantic_id:
            raise ValueError("node semantic identity does not match canonical content")

    for road in network.roads:
        start = by_id.get(road.start_node_id)
        end = by_id.get(road.end_node_id)
        if start is None or end is None:
            raise ValueError("road endpoint does not name a canonical node")
        expected_semantic_id = _road_semantic_id(
            network.seed,
            network.style_id,
            road.semantic_role,
            start.semantic_id,
            end.semantic_id,
            road.points_mm,
            road.hierarchy,
            road.facility,
            road.layer,
            road.access_directions,
            road.layer_transition,
            road.structure_group,
            road.failure_group,
            road.profile_id,
            road.provenance,
            road.row_interval,
        )
        if road.semantic_id != expected_semantic_id:
            raise ValueError("road semantic identity does not match canonical content")

    style_fingerprint = _style_fingerprint(
        network.style_id,
        network.seed,
        network.centers,
        network.nodes,
        network.roads,
    )
    if network.style_fingerprint != style_fingerprint:
        raise ValueError("style fingerprint does not match canonical record content")
    network_fingerprint = _network_fingerprint(
        network.scale_spec,
        network.style_id,
        network.seed,
        network.extent_mm,
        network.centers,
        network.gateway_node_ids,
        network.nodes,
        network.roads,
        network.endpoint_incidence,
        network.terrain,
        network.tile_coordinates,
        network.seam_diagnostics,
        network.hidden_repair_count,
    )
    if network.fingerprint != network_fingerprint:
        raise ValueError("network fingerprint does not match canonical record content")

    expected = _canonical_generated_specs(
        network.scale_spec,
        network.style_id,
        network.seed,
        network.terrain,
        network.extent_mm,
    )
    expected_nodes = {node.semantic_id: node for node in expected.nodes}
    for node in network.nodes:
        spec = expected_nodes.get(node.semantic_id)
        if spec is None or (
            node.x_mm,
            node.y_mm,
            node.layer,
            node.semantic_role,
        ) != (spec.x_mm, spec.y_mm, spec.layer, spec.semantic_role):
            raise ValueError("node role or geometry is not present canonical construction")

    expected_roads = {road.semantic_id: road for road in expected.roads}
    for road in network.roads:
        spec = expected_roads.get(road.semantic_id)
        if spec is None:
            raise ValueError("road role or geometry is not present canonical construction")
        actual = (
            by_id[road.start_node_id].semantic_id,
            by_id[road.end_node_id].semantic_id,
            road.points_mm,
            road.hierarchy,
            road.facility,
            road.layer,
            road.access_directions,
            road.layer_transition,
            road.structure_group,
            road.failure_group,
            road.profile_id,
            road.provenance,
            road.semantic_role,
            road.row_interval,
        )
        canonical = (
            spec.start_semantic_id,
            spec.end_semantic_id,
            spec.points_mm,
            spec.hierarchy,
            spec.facility,
            spec.layer,
            spec.access_directions,
            spec.layer_transition,
            spec.structure_group,
            spec.failure_group,
            spec.profile_id,
            spec.provenance,
            spec.semantic_role,
            spec.row_interval,
        )
        if actual != canonical:
            raise ValueError("road fields do not match present canonical construction")

    gateway_semantics = tuple(by_id[node_id].semantic_id for node_id in network.gateway_node_ids)
    if gateway_semantics != expected.gateway_semantic_ids:
        raise ValueError("gateway order does not match canonical construction")
    if network.centers != expected.centers:
        raise ValueError("centers do not match canonical construction")


def _validate_network_authority(network: ScalableStreetNetwork) -> None:
    if type(network) is not ScalableStreetNetwork:
        raise TypeError("network must be an exact ScalableStreetNetwork")
    if len(network.nodes) > MAX_JUNCTIONS:
        raise ValueError("network exceeds junction budget")
    if len(network.roads) > MAX_PHYSICAL_ROADS:
        raise ValueError("network exceeds physical-road budget")
    if len(network.gateway_node_ids) != 8 or len(set(network.gateway_node_ids)) != 8:
        raise ValueError("network requires exactly eight distinct gateways")
    by_id = {node.node_id: node for node in network.nodes}
    if any(
        node_id not in by_id or by_id[node_id].layer != 1 for node_id in network.gateway_node_ids
    ):
        raise ValueError("gateway authority must name layer-1 mainline nodes")

    _validate_terrain_network_authority(network)
    _validate_canonical_generated_authority(network, by_id)
    _validate_exact_canonical_record_set(network, by_id)
    for road in network.roads:
        if road.row_interval is not None:
            _validate_row_interval_authority(road, network.terrain, network.extent_mm)
    if dict(network.seam_diagnostics)["seam_mismatch_count"] != 0:
        raise ValueError("network has an unowned terrain seam mismatch")

    audit = audit_structural_network(network)
    unresolved = (
        audit.same_layer_proper_crossing_count,
        audit.t_touch_count,
        audit.collinear_overlap_count,
        audit.self_intersection_count,
        audit.nonadjacent_weld_count,
        audit.duplicate_road_count,
        audit.different_layer_false_junction_count,
        audit.endpoint_anchor_mismatch_count,
    )
    if not audit.is_connected or any(unresolved):
        raise ValueError("network records fail reject-only structural audit")
    maximum_degree = max(
        (len(road_ids) for _node_id, road_ids in network.endpoint_incidence),
        default=0,
    )
    if maximum_degree > MAX_SURFACE_DEGREE:
        raise ValueError("network exceeds maximum surface degree")
    if audit.center_disjoint_gateway_path_count != len(network.centers):
        raise ValueError("centers require two failure-group-disjoint gateway paths")
    if network.style_id == "river_constrained" and (
        audit.river_cross_bank_group_count < 3 or audit.river_group_removal_failures
    ):
        raise ValueError("river bridge failure-group authority is incomplete")


def build_scalable_street_network(
    scale_spec: object,
    style_id: str,
    seed: int,
    *,
    tile_order: Sequence[tuple[int, int]] | None = None,
) -> ScalableStreetNetwork:
    snapshot = _snapshot_scale_spec(scale_spec)
    style_id = _snapshot_str("style_id", style_id)
    if style_id not in STYLE_IDS:
        raise ValueError(f"style_id must be one of: {', '.join(STYLE_IDS)}")
    seed = _require_int("seed", seed)
    width_mm, height_mm = _extent_mm(snapshot.urbanized_area_km2)
    min_x, min_y = -width_mm // 2, -height_mm // 2
    extent = (min_x, min_x + width_mm, min_y, min_y + height_mm)
    tiles = _tile_domain(extent)
    _validate_tile_order(tiles, tile_order)
    terrain = ScalableTerrainField(
        width_mm / 1_000.0,
        height_mm / 1_000.0,
        TERRAIN_CELL_SIZE_M,
        TILE_SIZE_M,
        seed,
        style_id,
        0 if style_id == "river_constrained" else None,
        _terrain_fingerprint(
            width_mm / 1_000.0,
            height_mm / 1_000.0,
            seed,
            style_id,
            0 if style_id == "river_constrained" else None,
        ),
    )
    canonical = _canonical_generated_specs(snapshot, style_id, seed, terrain, extent)
    nodes = tuple(
        PhysicalNodeRecord(
            index, spec.semantic_id, spec.x_mm, spec.y_mm, spec.layer, spec.semantic_role
        )
        for index, spec in enumerate(canonical.nodes)
    )
    if len(nodes) > MAX_JUNCTIONS:
        raise ValueError(f"junction budget exceeded: {len(nodes)} > {MAX_JUNCTIONS}")
    node_ids = {node.semantic_id: node.node_id for node in nodes}
    roads = tuple(
        PhysicalRoadRecord(
            index,
            spec.semantic_id,
            node_ids[spec.start_semantic_id],
            node_ids[spec.end_semantic_id],
            spec.points_mm,
            spec.hierarchy,
            spec.facility,
            spec.layer,
            spec.access_directions,
            spec.layer_transition,
            spec.structure_group,
            spec.failure_group,
            spec.profile_id,
            spec.provenance,
            spec.semantic_role,
            spec.row_interval,
        )
        for index, spec in enumerate(canonical.roads)
    )
    if len(roads) > MAX_PHYSICAL_ROADS:
        raise ValueError(f"road budget exceeded: {len(roads)} > {MAX_PHYSICAL_ROADS}")
    incidence = _endpoint_incidence(nodes, roads)
    gateway_node_ids = tuple(node_ids[value] for value in canonical.gateway_semantic_ids)
    diagnostics = _computed_seam_diagnostics(extent, nodes, terrain, tiles)
    scale_fingerprint = _semantic_id(
        (SCHEMA_VERSION, "scale", snapshot.target_population, snapshot.urbanized_area_km2)
    )
    style_fingerprint = _style_fingerprint(style_id, seed, canonical.centers, nodes, roads)
    fingerprint = _network_fingerprint(
        snapshot,
        style_id,
        seed,
        extent,
        canonical.centers,
        gateway_node_ids,
        nodes,
        roads,
        incidence,
        terrain,
        tiles,
        diagnostics,
        0,
    )
    network = ScalableStreetNetwork(
        snapshot,
        style_id,
        seed,
        SCHEMA_VERSION,
        scale_fingerprint,
        style_fingerprint,
        extent,
        width_mm / 1_000.0,
        height_mm / 1_000.0,
        canonical.centers,
        gateway_node_ids,
        nodes,
        roads,
        incidence,
        terrain,
        tiles,
        diagnostics,
        0,
        fingerprint,
    )
    _validate_network_authority(network)
    return network
