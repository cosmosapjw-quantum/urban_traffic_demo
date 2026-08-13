"""Immutable capacity-only authority for scalable synthetic cities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
import math
from typing import Mapping

import numpy as np

from metroflow.city.graph import NodeKind, RoadClass, TurnType
from metroflow.city.scale import CityScaleSpec
from metroflow.city.scalable_blocks import ScalableBlockAuthority, V2BlockAccessIndex
from metroflow.city.scalable_topology import ScalableStreetNetwork, ScalableTerrainField
from metroflow.city.scalable_topology_adapter import (
    ScalableCompiledTopology,
    ScalableGroupCrosswalk,
    ScalableNumericProfile,
    ScalableRoadCrosswalk,
)

__all__ = (
    "BlockLandUseV2",
    "ImmutableBridgeCrossing",
    "ImmutableNode",
    "ImmutableRoadLink",
    "ImmutableRoadNetworkCSR",
    "ImmutableTurnMovement",
    "MapFingerprintSetV3",
    "PopulationCapacityCertificate",
    "RoutingStaticDependencyKey",
    "ScalableStaticAuthority",
    "V2LandUseType",
    "V2Poi",
    "V2PoiCatalog",
    "V2PoiKind",
    "V2Taz",
    "V2TazCatalog",
    "build_scalable_static_authority",
    "require_valid_scalable_static_authority",
)

STATIC_AUTHORITY_SCHEMA = "scalable_static_authority_v1"
LAND_USE_POLICY = "scalable_v2_land_use_v1"
ALLOCATION_POLICY = "scalable_v2_capacity_allocation_v1"
TAZ_POLICY = "scalable_v2_taz_morton_v1"
POI_POLICY = "scalable_v2_aggregate_poi_v1"
FINGERPRINT_SET_SCHEMA = "scalable_map_fingerprint_v3"
IMMUTABLE_CSR_SCHEMA = "immutable_road_network_csr_v1"
ROUTING_KEY_SCHEMA = "scalable_v2_routing_static_key_v1"
STATIC_CONFIG_NODE_SCHEMA = "scalable_v2_static_config_node_v1"
GEOMETRY_NODE_SCHEMA = "scalable_v2_geometry_node_v1"
TOPOLOGY_NODE_SCHEMA = "scalable_v2_topology_node_v1"
LINK_ATTRIBUTES_NODE_SCHEMA = "scalable_v2_link_attributes_node_v1"
TURN_AUTHORITY_NODE_SCHEMA = "scalable_v2_turn_authority_node_v1"
BLOCKS_ACCESS_NODE_SCHEMA = "scalable_v2_blocks_access_node_v1"
LAND_USE_ZONING_NODE_SCHEMA = "scalable_v2_land_use_zoning_node_v1"
ROUTING_STATIC_NODE_SCHEMA = "scalable_v2_routing_static_node_v1"
ACCESSIBILITY_STATIC_NODE_SCHEMA = "scalable_v2_accessibility_static_node_v1"
REPLAY_STATIC_NODE_SCHEMA = "scalable_v2_replay_static_node_v1"
COMPOSITE_NODE_SCHEMA = "scalable_v2_composite_node_v1"
ROUTING_POLICY = "task4_legal_turn_csr_v1"
ACCESS_DIRECTION_POLICY = "task4_declared_forward_reverse_v1"
CLOSURE_CAPABILITY_POLICY = "task4_blockable_failure_group_v1"
STATIC_BUILDER_BACKEND = "python_numpy_baseline_static_v1"
CAPACITY_REFERENCE_TICK_SECONDS = 1.0
CAPACITY_SOURCE_UNIT = "vehicles_per_second"


class V2LandUseType(str, Enum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    MIXED_USE = "mixed_use"


class V2PoiKind(str, Enum):
    HOME = "home"
    WORKPLACE = "workplace"
    LEISURE = "leisure"


_RAW_RATES = {
    V2LandUseType.RESIDENTIAL: (95, 95, 0, 25),
    V2LandUseType.COMMERCIAL: (0, 0, 170, 70),
    V2LandUseType.INDUSTRIAL: (0, 0, 90, 0),
    V2LandUseType.MIXED_USE: (75, 75, 95, 55),
}


def _plain_nonnegative_int(value: object, name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be a built-in integer")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return value


def _digest_text(value: object, name: str) -> str:
    if type(value) is not str or len(value) != 64:
        raise TypeError(f"{name} must be a 64-character built-in string")
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be lowercase hexadecimal")
    return value


def _exact_fraction(value: object, name: str) -> Fraction:
    if type(value) is int:
        return Fraction(value)
    if type(value) is Fraction:
        return value
    raise TypeError(f"{name} must be an exact integer or Fraction")


def _exact_witness(
    witness_mm: object,
    name: str = "witness_mm",
) -> tuple[Fraction, Fraction]:
    if type(witness_mm) is not tuple or len(witness_mm) != 2:
        raise TypeError(f"{name} must be a built-in two-item tuple")
    return (
        _exact_fraction(witness_mm[0], f"{name}[0]"),
        _exact_fraction(witness_mm[1], f"{name}[1]"),
    )


def _exact_extent(extent_mm: object) -> tuple[int, int, int, int]:
    if type(extent_mm) is not tuple or len(extent_mm) != 4:
        raise TypeError("extent_mm must be a built-in four-item tuple")
    if any(type(value) is not int for value in extent_mm):
        raise TypeError("extent_mm values must be built-in integers")
    xmin, ymin, xmax, ymax = extent_mm
    if xmax <= xmin or ymax <= ymin:
        raise ValueError("extent_mm must have positive width and height")
    return xmin, ymin, xmax, ymax


def _morton_code(x: int, y: int) -> int:
    result = 0
    for bit in range(max(x.bit_length(), y.bit_length())):
        result |= ((x >> bit) & 1) << (2 * bit)
        result |= ((y >> bit) & 1) << (2 * bit + 1)
    return result


@dataclass(frozen=True, slots=True)
class BlockLandUseV2:
    block_id: int
    block_semantic_id: str
    parent_face_id: int
    land_use_type: V2LandUseType
    outer_polygon_mm: tuple[tuple[int, int], ...]
    hole_polygons_mm: tuple[tuple[tuple[int, int], ...], ...]
    exact_net_area_mm2: Fraction
    frontage_road_ids: tuple[int, ...]
    access_node_ids: tuple[int, ...]
    primary_access_node_id: int
    interior_witness_mm: tuple[int | Fraction, int | Fraction]
    terrain_cell: tuple[int, int]
    terrain_intensity: float
    terrain_intensity_hex: str
    centrality_score: float
    exposure_score: float
    raw_resident_weight: float
    raw_home_weight: float
    raw_job_weight: float
    raw_leisure_weight: float
    raw_resident_ratio: tuple[int, int]
    raw_home_ratio: tuple[int, int]
    raw_job_ratio: tuple[int, int]
    raw_leisure_ratio: tuple[int, int]
    final_resident_capacity: int
    final_home_capacity: int
    final_job_capacity: int
    final_leisure_capacity: int
    taz_id: int
    source_network_fingerprint: str
    source_blocks_fingerprint: str
    policy_version: str
    fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class PopulationCapacityCertificate:
    schema_version: str
    target_population: int
    job_target: int
    worker_share_numerator: int
    worker_share_denominator: int
    resident_raw_total_ratio: tuple[int, int]
    home_raw_total_ratio: tuple[int, int]
    job_raw_total_ratio: tuple[int, int]
    leisure_raw_total_ratio: tuple[int, int]
    resident_multiplier_ratio: tuple[int, int]
    home_multiplier_ratio: tuple[int, int]
    job_multiplier_ratio: tuple[int, int]
    leisure_multiplier_ratio: tuple[int, int]
    resident_capacity_total: int
    home_capacity_total: int
    job_capacity_total: int
    leisure_capacity_total: int
    taz_count: int
    allocated_block_count: int
    capacity_cap_applied: bool
    silent_cap_count: int
    dropped_capacity_count: int
    allocation_fingerprint: str
    source_network_fingerprint: str
    source_blocks_fingerprint: str
    source_compiled_fingerprint: str
    land_use_policy_version: str
    allocation_policy_version: str
    fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class V2Taz:
    taz_id: int
    semantic_id: str
    block_ids: tuple[int, ...]
    block_semantic_ids: tuple[str, ...]
    frontage_road_ids: tuple[int, ...]
    access_node_ids: tuple[int, ...]
    resident_capacity_total: int
    home_capacity_total: int
    job_capacity_total: int
    leisure_capacity_total: int
    fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class V2TazCatalog:
    schema_version: str
    tazs: tuple[V2Taz, ...]
    block_taz_by_id: tuple[tuple[int, int], ...]
    node_owner_by_id: tuple[tuple[int, int], ...]
    node_conflicts: tuple[tuple[int, tuple[tuple[str, int], ...], int], ...]
    target_taz_count: int
    source_blocks_fingerprint: str
    source_allocation_fingerprint: str
    assignment_fingerprint: str
    fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class V2Poi:
    poi_id: int
    semantic_id: str
    poi_kind: V2PoiKind
    block_id: int
    block_semantic_id: str
    location_witness_mm: tuple[int | Fraction, int | Fraction]
    access_node_id: int
    taz_id: int
    capacity: int
    source_allocation_fingerprint: str
    fingerprint: str = ""

    def __post_init__(self) -> None:
        raise NotImplementedError(
            "S5A_RECORD_OWNER_RED: V2Poi validation is not implemented"
        )


@dataclass(frozen=True, slots=True)
class V2PoiCatalog:
    schema_version: str
    pois: tuple[V2Poi, ...]
    home_capacity_total: int
    workplace_capacity_total: int
    leisure_capacity_total: int
    source_allocation_fingerprint: str
    source_taz_fingerprint: str
    fingerprint: str = ""

    def __post_init__(self) -> None:
        raise NotImplementedError(
            "S8B_OWNER_RED: nested POI catalog identity is not implemented"
        )


@dataclass(frozen=True, slots=True)
class MapFingerprintSetV3:
    schema_version: str
    config: str
    geometry: str
    topology: str
    link_attributes: str
    turn_authority: str
    blocks_access: str
    land_use_zoning: str
    routing_static: str
    accessibility_static: str
    replay_static: str
    composite: str

    def __post_init__(self) -> None:
        raise NotImplementedError(
            "S5B_RECORD_OWNER_RED: MapFingerprintSetV3 validation is not implemented"
        )


@dataclass(frozen=True, slots=True)
class RoutingStaticDependencyKey:
    schema_version: str
    routing_static_fingerprint: str
    routing_policy_version: str
    access_direction_policy_version: str
    closure_capability_policy_version: str
    source_csr_fingerprint: str
    fingerprint: str = ""

    def __post_init__(self) -> None:
        raise NotImplementedError(
            "S8A_OWNER_RED: routing dependency identity is not implemented"
        )


@dataclass(frozen=True, slots=True)
class ImmutableNode:
    node_id: int
    kind: NodeKind
    x: float
    y: float
    zone_id: int | None
    signal_group_id: int | None


@dataclass(frozen=True, slots=True)
class ImmutableRoadLink:
    link_id: int
    src_node_id: int
    dst_node_id: int
    road_class: RoadClass
    length_m: float
    free_flow_speed_mps: float
    capacity_veh_per_tick: float
    lanes: int
    bridge_group_id: int | None
    is_blockable: bool
    physical_road_id: int | None


@dataclass(frozen=True, slots=True)
class ImmutableTurnMovement:
    from_link_id: int
    to_link_id: int
    turn_type: TurnType
    base_priority: float
    signal_phase_id: int | None


@dataclass(frozen=True, slots=True)
class ImmutableBridgeCrossing:
    bridge_group_id: int
    link_ids: tuple[int, ...]
    barrier_id: int
    crossing_name: str
    bottleneck_rank_hint: int | None


@dataclass(frozen=True, slots=True)
class ImmutableRoadNetworkCSR:
    schema_version: str
    nodes: tuple[ImmutableNode, ...]
    links: tuple[ImmutableRoadLink, ...]
    turns: tuple[ImmutableTurnMovement, ...]
    bridge_crossings: tuple[ImmutableBridgeCrossing, ...]
    node_id_to_index: Mapping[int, int]
    link_id_to_index: Mapping[int, int]
    turn_pair_to_index: Mapping[tuple[int, int], int]
    node_ids: np.ndarray
    link_ids: np.ndarray
    link_src_node_index: np.ndarray
    link_dst_node_index: np.ndarray
    outgoing_indptr: np.ndarray
    outgoing_link_indices: np.ndarray
    incoming_indptr: np.ndarray
    incoming_link_indices: np.ndarray
    turn_from_link_index: np.ndarray
    turn_to_link_index: np.ndarray
    turn_base_priority: np.ndarray
    turn_is_forbidden: np.ndarray
    topology_cache_key: tuple[object, ...]
    content_fingerprint: str = ""

    def __post_init__(self) -> None:
        raise NotImplementedError(
            "S7_OWNER_RED: immutable CSR validation is not implemented"
        )


@dataclass(frozen=True, slots=True)
class ScalableStaticAuthority:
    schema_version: str
    scale_spec: CityScaleSpec
    style_id: str
    seed: int
    extent_mm: tuple[int, int, int, int]
    width_m: float
    height_m: float
    centers_mm: tuple[tuple[int, int], ...]
    source_network_schema_version: str
    source_blocks_schema_version: str
    source_compiled_schema_version: str
    numeric_profile_policy_version: str
    source_network_fingerprint: str
    source_blocks_fingerprint: str
    source_compiled_fingerprint: str
    source_terrain_fingerprint: str
    source_scale_fingerprint: str
    source_style_fingerprint: str
    source_geometry_fingerprint: str
    source_section_fingerprint: str
    source_node_interface_fingerprint: str
    source_turn_authority_fingerprint: str
    numeric_profiles: tuple[ScalableNumericProfile, ...]
    road_crosswalk: tuple[ScalableRoadCrosswalk, ...]
    structure_group_crosswalk: tuple[ScalableGroupCrosswalk, ...]
    failure_group_crosswalk: tuple[ScalableGroupCrosswalk, ...]
    block_access_index: V2BlockAccessIndex
    block_land_use: tuple[BlockLandUseV2, ...]
    capacity_certificate: PopulationCapacityCertificate
    taz_catalog: V2TazCatalog
    poi_catalog: V2PoiCatalog
    fingerprints: MapFingerprintSetV3
    road_csr: ImmutableRoadNetworkCSR
    routing_dependency_key: RoutingStaticDependencyKey
    fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class _CopiedTask4:
    numeric_profiles: tuple[ScalableNumericProfile, ...]
    road_crosswalk: tuple[ScalableRoadCrosswalk, ...]
    structure_group_crosswalk: tuple[ScalableGroupCrosswalk, ...]
    failure_group_crosswalk: tuple[ScalableGroupCrosswalk, ...]
    block_access_index: V2BlockAccessIndex
    road_csr: ImmutableRoadNetworkCSR


def _copy_task4_authorities(
    *,
    blocks: ScalableBlockAuthority,
    compiled: ScalableCompiledTopology,
) -> _CopiedTask4:
    raise NotImplementedError(
        "S11_COPY_OWNER_RED: Task4 immutable copy validation is not implemented"
    )


def _raw_capacity_ratios(
    *,
    exact_net_area_mm2: Fraction,
    terrain_intensity: float,
    land_use_type: V2LandUseType,
) -> tuple[Fraction, Fraction, Fraction, Fraction]:
    if type(exact_net_area_mm2) is not Fraction:
        raise TypeError("exact_net_area_mm2 must be an exact Fraction")
    if exact_net_area_mm2 <= 0:
        raise ValueError("exact_net_area_mm2 must be positive")
    if type(terrain_intensity) is not float:
        raise TypeError("terrain_intensity must be a built-in float")
    if not 0.0 <= terrain_intensity <= 1.0:
        raise ValueError("terrain_intensity must be finite and in [0, 1]")
    if type(land_use_type) is not V2LandUseType:
        raise TypeError("land_use_type must be an exact V2LandUseType")
    intensity = Fraction(*terrain_intensity.as_integer_ratio())
    intensity_scale = Fraction(45, 100) + Fraction(55, 100) * intensity
    area_hectares = exact_net_area_mm2 / 10_000_000_000
    return tuple(
        area_hectares * rate * intensity_scale for rate in _RAW_RATES[land_use_type]
    )  # type: ignore[return-value]


def _require_implied_multiplier(
    *,
    target: int,
    raw_total: Fraction | float,
    enforce_authoritative_bounds: bool,
) -> Fraction:
    target = _plain_nonnegative_int(target, "target")
    if type(enforce_authoritative_bounds) is not bool:
        raise TypeError("enforce_authoritative_bounds must be a built-in bool")
    if type(raw_total) is Fraction:
        raw = raw_total
    elif type(raw_total) is float:
        if raw_total != raw_total or raw_total in (float("inf"), float("-inf")):
            raise ValueError("raw_total must be finite")
        raw = Fraction(*raw_total.as_integer_ratio())
    else:
        raise TypeError("raw_total must be an exact Fraction or built-in float")
    if raw < 0:
        raise ValueError("raw_total must be nonnegative")
    if raw == 0:
        if target == 0:
            return Fraction(0)
        raise ValueError("positive target requires a positive raw pool")
    if target == 0:
        if enforce_authoritative_bounds:
            raise ValueError("zero authoritative target requires a zero raw pool")
        return Fraction(0)
    multiplier = Fraction(target, 1) / raw
    if enforce_authoritative_bounds and not Fraction(1, 4) <= multiplier <= Fraction(3):
        raise ValueError("implied multiplier must be in [1/4, 3]")
    return multiplier


def _apportion_exact_channel(
    *,
    target: int,
    weighted_rows: tuple[tuple[str, Fraction], ...],
) -> tuple[tuple[str, int], ...]:
    target = _plain_nonnegative_int(target, "target")
    if type(weighted_rows) is not tuple:
        raise TypeError("weighted_rows must be a built-in tuple")
    parsed: list[tuple[str, Fraction]] = []
    seen: set[str] = set()
    for row in weighted_rows:
        if type(row) is not tuple or len(row) != 2:
            raise TypeError("each weighted row must be a two-item built-in tuple")
        key = _digest_text(row[0], "weight key")
        weight = row[1]
        if type(weight) is not Fraction:
            raise TypeError("weights must be exact Fractions")
        if weight < 0:
            raise ValueError("weights must be nonnegative")
        if key in seen:
            raise ValueError("weight keys must be unique")
        seen.add(key)
        parsed.append((key, weight))
    parsed.sort(key=lambda item: item[0])
    total = sum((weight for _, weight in parsed), Fraction(0))
    if total == 0:
        if target != 0:
            raise ValueError("positive target requires a positive weighted pool")
        return tuple((key, 0) for key, _ in parsed)
    quotas = [(key, Fraction(target) * weight / total) for key, weight in parsed]
    allocated = {key: quota.numerator // quota.denominator for key, quota in quotas}
    remainder = target - sum(allocated.values())
    ranked = sorted(
        quotas,
        key=lambda item: (-(item[1] - allocated[item[0]]), item[0]),
    )
    for key, _ in ranked[:remainder]:
        allocated[key] += 1
    return tuple((key, allocated[key]) for key, _ in parsed)


def _sample_terrain_at_exact_witness(
    *,
    terrain: ScalableTerrainField,
    witness_mm: tuple[int | Fraction, int | Fraction],
) -> tuple[tuple[int, int], float]:
    if type(terrain) is not ScalableTerrainField:
        raise TypeError("terrain must be an exact ScalableTerrainField")
    wx, wy = _exact_witness(witness_mm)
    cell_size_m = terrain.cell_size_m
    if type(cell_size_m) is not float or not math.isfinite(cell_size_m) or cell_size_m <= 0:
        raise ValueError("terrain cell size must be a positive built-in float")
    numerator, denominator = cell_size_m.as_integer_ratio()
    cell_size_mm = Fraction(numerator * 1_000, denominator)
    cell_x = math.floor(wx / cell_size_mm)
    cell_y = math.floor(wy / cell_size_mm)
    center_x_m = float((Fraction(cell_x) + Fraction(1, 2)) * cell_size_mm / 1_000)
    center_y_m = float((Fraction(cell_y) + Fraction(1, 2)) * cell_size_mm / 1_000)
    intensity = terrain.intensity_at(center_x_m, center_y_m)
    if terrain.cell_key_at(center_x_m, center_y_m) != (cell_x, cell_y):
        raise ValueError("terrain cell center does not round-trip to its exact key")
    if type(intensity) is not float or not math.isfinite(intensity) or not 0.0 <= intensity <= 1.0:
        raise ValueError("terrain intensity must be a finite built-in float in [0, 1]")
    return (cell_x, cell_y), intensity


def _centrality_score_mm(
    *,
    witness_mm: tuple[int | Fraction, int | Fraction],
    centers_mm: tuple[tuple[int, int], ...],
    width_m: float,
    height_m: float,
) -> float:
    wx, wy = _exact_witness(witness_mm)
    if type(centers_mm) is not tuple or not centers_mm:
        raise TypeError("centers_mm must be a nonempty built-in tuple")
    centers: list[tuple[int, int]] = []
    for center in centers_mm:
        if (
            type(center) is not tuple
            or len(center) != 2
            or type(center[0]) is not int
            or type(center[1]) is not int
        ):
            raise TypeError("each center must be a built-in integer pair")
        centers.append(center)
    if type(width_m) is not float or type(height_m) is not float:
        raise TypeError("width_m and height_m must be built-in floats")
    if not all(math.isfinite(value) and value > 0.0 for value in (width_m, height_m)):
        raise ValueError("width_m and height_m must be finite and positive")
    scale_mm = float(
        Fraction(28, 100)
        * 1_000
        * Fraction(*max(width_m, height_m).as_integer_ratio())
    )
    score = max(
        math.exp(-math.hypot(float(wx - cx), float(wy - cy)) / scale_mm)
        for cx, cy in centers
    )
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ValueError("centrality score must be finite and in [0, 1]")
    return score


def _morton_witness_key(
    *,
    witness_mm: tuple[int | Fraction, int | Fraction],
    extent_mm: tuple[int, int, int, int],
) -> tuple[int, Fraction, Fraction]:
    wx, wy = _exact_witness(witness_mm)
    xmin, ymin, xmax, ymax = _exact_extent(extent_mm)
    if not Fraction(xmin) <= wx <= Fraction(xmax) or not Fraction(ymin) <= wy <= Fraction(ymax):
        raise ValueError("witness must lie inside the inclusive extent")
    dx = wx - xmin
    dy = wy - ymin
    return _morton_code(math.floor(dx), math.floor(dy)), dx, dy


def _partition_morton_rows(
    *,
    rows: tuple[tuple[int, str, tuple[int | Fraction, int | Fraction]], ...],
    extent_mm: tuple[int, int, int, int],
    taz_count: int,
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    if type(rows) is not tuple:
        raise TypeError("rows must be a built-in tuple")
    taz_count = _plain_nonnegative_int(taz_count, "taz_count")
    if taz_count < 1:
        raise ValueError("taz_count must be positive")
    _exact_extent(extent_mm)
    parsed: list[tuple[int, Fraction, Fraction, str, int]] = []
    block_ids: set[int] = set()
    semantic_ids: set[str] = set()
    for row in rows:
        if type(row) is not tuple or len(row) != 3:
            raise TypeError("each Morton row must be a built-in three-item tuple")
        block_id = _plain_nonnegative_int(row[0], "block_id")
        semantic_id = _digest_text(row[1], "block_semantic_id")
        if block_id in block_ids or semantic_id in semantic_ids:
            raise ValueError("Morton rows require unique block and semantic IDs")
        block_ids.add(block_id)
        semantic_ids.add(semantic_id)
        morton, dx, dy = _morton_witness_key(witness_mm=row[2], extent_mm=extent_mm)
        parsed.append((morton, dx, dy, semantic_id, block_id))
    if len(parsed) < taz_count:
        raise ValueError("TAZ count cannot exceed addressable block count")
    parsed.sort()
    q, r = divmod(len(parsed), taz_count)
    result: list[tuple[int, tuple[int, ...]]] = []
    start = 0
    for taz_id in range(taz_count):
        size = q + (1 if taz_id < r else 0)
        result.append((taz_id, tuple(row[4] for row in parsed[start : start + size])))
        start += size
    return tuple(result)


def _taz_count_policy_unbounded(population: int) -> int:
    if type(population) is not int:
        raise TypeError("population must be a built-in integer")
    if population <= 0:
        raise ValueError("population must be positive")
    return min(512, max(64, (population + 2_499) // 2_500))


def _land_use_counts(block_count: int) -> tuple[int, int, int, int]:
    block_count = _plain_nonnegative_int(block_count, "block_count")
    commercial = max(1, round(Fraction(12 * block_count, 100)))
    industrial = max(1, round(Fraction(12 * block_count, 100)))
    mixed = max(1, round(Fraction(23 * block_count, 100)))
    residential = block_count - commercial - industrial - mixed
    if residential < 1:
        raise ValueError("block count cannot retain all four land-use types")
    return commercial, industrial, mixed, residential


def _frontage_adjacency_from_index(
    *,
    developable_block_ids: tuple[int, ...],
    road_to_block_ids: tuple[tuple[int, tuple[int, ...]], ...],
) -> tuple[tuple[tuple[int, tuple[int, ...]], ...], int]:
    raise NotImplementedError("S4A_OWNER_RED: land-use classification is not implemented")


def _classify_land_use_rows(
    *,
    feature_rows: tuple[tuple[int, str, float, float, float], ...],
    road_to_block_ids: tuple[tuple[int, tuple[int, ...]], ...],
) -> tuple[tuple[int, V2LandUseType], ...]:
    raise NotImplementedError("S4A_OWNER_RED: land-use classification is not implemented")


def _node_taz_ownership_from_index(
    *,
    block_rows: tuple[tuple[str, int, tuple[int, ...]], ...],
) -> tuple[
    tuple[tuple[int, int], ...],
    tuple[tuple[int, tuple[tuple[str, int], ...], int], ...],
    int,
]:
    raise NotImplementedError("S4B_OWNER_RED: node TAZ ownership is not implemented")


def _aggregate_poi_rows(
    *,
    block_rows: tuple[
        tuple[
            int,
            str,
            tuple[int | Fraction, int | Fraction],
            int,
            int,
            int,
            int,
            int,
        ],
        ...,
    ],
    source_allocation_fingerprint: str,
) -> tuple[V2Poi, ...]:
    raise NotImplementedError("S5A_OWNER_RED: aggregate POI rows are not implemented")


def _compose_map_fingerprint_set_v3(
    *,
    config: str,
    geometry: str,
    topology: str,
    link_attributes: str,
    turn_authority: str,
    blocks_access: str,
    land_use_zoning: str,
) -> MapFingerprintSetV3:
    raise NotImplementedError("S5B_OWNER_RED: v3 fingerprint composition is not implemented")


def _seal_c_array(source: np.ndarray) -> np.ndarray:
    raise NotImplementedError("S6_OWNER_RED: irreversible C-array sealing is not implemented")


def _admit_scalable_sources(
    scale_spec: CityScaleSpec,
    style_id: str,
    seed: int,
    network: ScalableStreetNetwork,
    blocks: ScalableBlockAuthority,
    compiled: ScalableCompiledTopology,
) -> CityScaleSpec:
    raise NotImplementedError(
        "S9_OWNER_RED: exact source admission types are not implemented"
    )


def _derive_scalable_static_authority(
    *,
    scale_spec: CityScaleSpec,
    style_id: str,
    seed: int,
    network: ScalableStreetNetwork,
    blocks: ScalableBlockAuthority,
    compiled: ScalableCompiledTopology,
) -> ScalableStaticAuthority:
    raise NotImplementedError(
        "S11_OWNER_RED: static authority derivation is not implemented"
    )


def build_scalable_static_authority(
    scale_spec: CityScaleSpec,
    style_id: str,
    seed: int,
    network: ScalableStreetNetwork,
    blocks: ScalableBlockAuthority,
    compiled: ScalableCompiledTopology,
) -> ScalableStaticAuthority:
    normalized_scale = _admit_scalable_sources(
        scale_spec,
        style_id,
        seed,
        network,
        blocks,
        compiled,
    )
    return _derive_scalable_static_authority(
        scale_spec=normalized_scale,
        style_id=style_id,
        seed=seed,
        network=network,
        blocks=blocks,
        compiled=compiled,
    )


def require_valid_scalable_static_authority(
    authority: ScalableStaticAuthority,
    *,
    scale_spec: CityScaleSpec,
    style_id: str,
    seed: int,
    network: ScalableStreetNetwork,
    blocks: ScalableBlockAuthority,
    compiled: ScalableCompiledTopology,
) -> None:
    if type(authority) is not ScalableStaticAuthority:
        raise TypeError("authority must be an exact ScalableStaticAuthority")
    raise NotImplementedError(
        "S12_OWNER_RED: standalone static-authority validation is not implemented"
    )
