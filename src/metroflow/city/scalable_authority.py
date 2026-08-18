"""Immutable capacity-only authority for scalable synthetic cities."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum
from fractions import Fraction
import hashlib
import json
import math
from types import MappingProxyType
from typing import Mapping

import numpy as np

from metroflow.city.graph import NodeKind, RoadClass, TurnType
from metroflow.city.scale import CityScaleSpec
from metroflow.city.scalable_blocks import ScalableBlockAuthority, V2BlockAccessIndex
from metroflow.city.scalable_topology import (
    FacilityKind,
    RoadHierarchy,
    ScalableStreetNetwork,
    ScalableTerrainField,
)
from metroflow.city.scalable_topology_adapter import (
    ScalableCompiledTopology,
    ScalableGroupCrosswalk,
    ScalableNumericProfile,
    ScalableRoadCrosswalk,
    require_valid_scalable_compiled_topology,
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


def _plain_nonnegative_int(value: object, name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be a built-in integer")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return value


def _plain_int(value: object, name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be a built-in integer")
    return value


def _digest_text(value: object, name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{name} must be a built-in string")
    if len(value) != 64 or value != value.lower():
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest") from exc
    return value


def _exact_fraction(value: object, name: str) -> Fraction:
    if type(value) is int:
        if isinstance(value, bool):  # pragma: no cover - bool is excluded by exact type
            raise TypeError(f"{name} must be an exact integer or Fraction")
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


def _canonical_payload(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if type(value) is Fraction:
        return ("fraction", value.numerator, value.denominator)
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("canonical floats must be finite")
        return ("float_hex", value.hex())
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is tuple:
        return tuple(_canonical_payload(item) for item in value)
    raise TypeError(f"unsupported canonical payload type: {type(value).__name__}")


def _sha256_payload(payload: object) -> str:
    encoded = json.dumps(
        _canonical_payload(payload),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _record_payload(record: object) -> tuple[object, ...]:
    values: list[object] = [type(record).__name__]
    for field in fields(record):
        if field.name in ("fingerprint", "content_fingerprint"):
            break
        values.append(getattr(record, field.name))
    return tuple(values)


def _install_record_fingerprint(record: object) -> None:
    expected = _sha256_payload(_record_payload(record))
    supplied = getattr(record, "fingerprint")
    if supplied:
        if _digest_text(supplied, "fingerprint") != expected:
            raise ValueError(f"{type(record).__name__} fingerprint mismatch")
    else:
        object.__setattr__(record, "fingerprint", expected)


def _ratio_pair(value: object, name: str, *, nonnegative: bool = True) -> tuple[int, int]:
    if type(value) is not tuple or len(value) != 2:
        raise TypeError(f"{name} must be a built-in numerator/denominator pair")
    numerator = _plain_int(value[0], f"{name} numerator")
    denominator = _plain_int(value[1], f"{name} denominator")
    if denominator <= 0:
        raise ValueError(f"{name} denominator must be positive")
    fraction = Fraction(numerator, denominator)
    if (fraction.numerator, fraction.denominator) != (numerator, denominator):
        raise ValueError(f"{name} must be reduced")
    if nonnegative and fraction < 0:
        raise ValueError(f"{name} must be nonnegative")
    return numerator, denominator


def _plain_int_tuple(
    value: object,
    name: str,
    *,
    nonempty: bool = False,
    sorted_unique: bool = False,
) -> tuple[int, ...]:
    if type(value) is not tuple:
        raise TypeError(f"{name} must be a built-in tuple")
    result = tuple(_plain_nonnegative_int(item, f"{name} item") for item in value)
    if nonempty and not result:
        raise ValueError(f"{name} must be nonempty")
    if sorted_unique and result != tuple(sorted(set(result))):
        raise ValueError(f"{name} must be sorted and unique")
    return result


def _polygon(value: object, name: str) -> tuple[tuple[int, int], ...]:
    if type(value) is not tuple:
        raise TypeError(f"{name} must be a built-in tuple")
    points: list[tuple[int, int]] = []
    for point in value:
        if type(point) is not tuple or len(point) != 2:
            raise TypeError(f"{name} points must be built-in pairs")
        points.append((_plain_int(point[0], f"{name} x"), _plain_int(point[1], f"{name} y")))
    if len(points) < 4 or points[0] != points[-1]:
        raise ValueError(f"{name} must be a closed polygon")
    return tuple(points)


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


def _morton_code(x: int, y: int) -> int:
    result = 0
    for bit in range(max(x.bit_length(), y.bit_length())):
        result |= ((x >> bit) & 1) << (2 * bit)
        result |= ((y >> bit) & 1) << (2 * bit + 1)
    return result


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
    if type(developable_block_ids) is not tuple:
        raise TypeError("developable_block_ids must be a built-in tuple")
    block_ids = tuple(
        _plain_nonnegative_int(value, "developable block id")
        for value in developable_block_ids
    )
    if len(set(block_ids)) != len(block_ids):
        raise ValueError("developable block IDs must be unique")
    block_id_set = set(block_ids)
    if type(road_to_block_ids) is not tuple:
        raise TypeError("road_to_block_ids must be a built-in tuple")
    adjacency = {block_id: set() for block_id in block_ids}
    road_ids: set[int] = set()
    visit_count = 0
    for row in road_to_block_ids:
        if type(row) is not tuple or len(row) != 2:
            raise TypeError("each road reverse-index row must be a built-in pair")
        road_id = _plain_nonnegative_int(row[0], "road id")
        if road_id in road_ids:
            raise ValueError("road reverse-index IDs must be unique")
        road_ids.add(road_id)
        if type(row[1]) is not tuple:
            raise TypeError("road reverse-index members must be a built-in tuple")
        members = tuple(
            _plain_nonnegative_int(value, "road member block id") for value in row[1]
        )
        if len(set(members)) != len(members):
            raise ValueError("road reverse-index members must be unique")
        if any(member not in block_id_set for member in members):
            raise ValueError("road reverse index references a non-developable block")
        visit_count += len(members)
        for member in members:
            adjacency[member].update(other for other in members if other != member)
    return (
        tuple(
            (block_id, tuple(sorted(adjacency[block_id]))) for block_id in sorted(block_ids)
        ),
        visit_count,
    )


def _exact_score(
    values: tuple[float, float, float],
    coefficients: tuple[Fraction, Fraction, Fraction],
) -> Fraction:
    return sum(
        (
            coefficient * Fraction(*value.as_integer_ratio())
            for value, coefficient in zip(values, coefficients, strict=True)
        ),
        Fraction(0),
    )


def _classify_land_use_rows(
    *,
    feature_rows: tuple[tuple[int, str, float, float, float], ...],
    road_to_block_ids: tuple[tuple[int, tuple[int, ...]], ...],
) -> tuple[tuple[int, V2LandUseType], ...]:
    if type(feature_rows) is not tuple:
        raise TypeError("feature_rows must be a built-in tuple")
    parsed: list[tuple[int, str, float, float, float]] = []
    block_ids: set[int] = set()
    semantic_ids: set[str] = set()
    for row in feature_rows:
        if type(row) is not tuple or len(row) != 5:
            raise TypeError("each feature row must be a built-in five-item tuple")
        block_id = _plain_nonnegative_int(row[0], "block_id")
        semantic_id = _digest_text(row[1], "block_semantic_id")
        if block_id in block_ids or semantic_id in semantic_ids:
            raise ValueError("feature rows require unique block and semantic IDs")
        block_ids.add(block_id)
        semantic_ids.add(semantic_id)
        features: list[float] = []
        for value in row[2:]:
            if type(value) is not float:
                raise TypeError("feature values must be built-in floats")
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError("feature values must be finite and in [0, 1]")
            features.append(value)
        parsed.append((block_id, semantic_id, *features))

    commercial_count, industrial_count, mixed_count, _ = _land_use_counts(len(parsed))
    adjacency_rows, _ = _frontage_adjacency_from_index(
        developable_block_ids=tuple(block_ids),
        road_to_block_ids=road_to_block_ids,
    )

    by_id = {row[0]: row for row in parsed}

    def ranked(
        candidates: set[int],
        coefficients: tuple[Fraction, Fraction, Fraction],
        transform: str,
    ) -> list[int]:
        scored: list[tuple[Fraction, str, int]] = []
        for block_id in candidates:
            _, semantic_id, centrality, intensity, exposure = by_id[block_id]
            if transform == "industrial":
                centrality_ratio = Fraction(*centrality.as_integer_ratio())
                intensity_ratio = Fraction(*intensity.as_integer_ratio())
                exposure_ratio = Fraction(*exposure.as_integer_ratio())
                score = (
                    Fraction(50, 100) * exposure_ratio
                    + Fraction(35, 100) * (1 - centrality_ratio)
                    + Fraction(15, 100) * (1 - intensity_ratio)
                )
            else:
                score = _exact_score((centrality, intensity, exposure), coefficients)
            scored.append((score, semantic_id, block_id))
        return [block_id for _, _, block_id in sorted(scored, key=lambda row: (-row[0], row[1]))]

    available = set(block_ids)
    commercial_ids = set(
        ranked(
            available,
            (Fraction(55, 100), Fraction(30, 100), Fraction(15, 100)),
            "standard",
        )[:commercial_count]
    )
    available -= commercial_ids
    industrial_ids = set(
        ranked(
            available,
            (Fraction(50, 100), Fraction(35, 100), Fraction(15, 100)),
            "industrial",
        )[:industrial_count]
    )
    available -= industrial_ids
    mixed_ids = set(
        ranked(
            available,
            (Fraction(45, 100), Fraction(35, 100), Fraction(20, 100)),
            "standard",
        )[:mixed_count]
    )
    residential_ids = available - mixed_ids

    frozen_adjacency = dict(adjacency_rows)
    converted = {
        block_id
        for block_id in residential_ids
        if any(neighbor in industrial_ids for neighbor in frozen_adjacency[block_id])
    }
    residential_ids -= converted
    mixed_ids |= converted
    if not all((commercial_ids, industrial_ids, mixed_ids, residential_ids)):
        raise ValueError("adjacency conversion must retain all four land-use types")

    assignments = {
        **{block_id: V2LandUseType.COMMERCIAL for block_id in commercial_ids},
        **{block_id: V2LandUseType.INDUSTRIAL for block_id in industrial_ids},
        **{block_id: V2LandUseType.MIXED_USE for block_id in mixed_ids},
        **{block_id: V2LandUseType.RESIDENTIAL for block_id in residential_ids},
    }
    return tuple((block_id, assignments[block_id]) for block_id in sorted(block_ids))


def _node_taz_ownership_from_index(
    *,
    block_rows: tuple[tuple[str, int, tuple[int, ...]], ...],
) -> tuple[
    tuple[tuple[int, int], ...],
    tuple[tuple[int, tuple[tuple[str, int], ...], int], ...],
    int,
]:
    if type(block_rows) is not tuple:
        raise TypeError("block_rows must be a built-in tuple")
    candidates: dict[int, list[tuple[str, int]]] = {}
    semantic_ids: set[str] = set()
    visit_count = 0
    for row in block_rows:
        if type(row) is not tuple or len(row) != 3:
            raise TypeError("each node-owner row must be a built-in three-item tuple")
        semantic_id = _digest_text(row[0], "block_semantic_id")
        if semantic_id in semantic_ids:
            raise ValueError("node-owner rows require unique block semantic IDs")
        semantic_ids.add(semantic_id)
        taz_id = _plain_nonnegative_int(row[1], "taz_id")
        if type(row[2]) is not tuple:
            raise TypeError("access_node_ids must be a built-in tuple")
        node_ids = tuple(_plain_nonnegative_int(node, "access node id") for node in row[2])
        if not node_ids or len(set(node_ids)) != len(node_ids):
            raise ValueError("access node IDs must be nonempty and unique per block")
        for node_id in node_ids:
            candidates.setdefault(node_id, []).append((semantic_id, taz_id))
            visit_count += 1
    owners: list[tuple[int, int]] = []
    conflicts: list[tuple[int, tuple[tuple[str, int], ...], int]] = []
    for node_id in sorted(candidates):
        ordered = tuple(sorted(candidates[node_id]))
        winner = ordered[0][1]
        owners.append((node_id, winner))
        if len(ordered) > 1:
            conflicts.append((node_id, ordered, winner))
    return tuple(owners), tuple(conflicts), visit_count


def _seal_c_array(source: np.ndarray) -> np.ndarray:
    if type(source) is not np.ndarray:
        raise TypeError("source must be an exact NumPy array")
    if not source.flags.c_contiguous:
        raise ValueError("source array must be C-contiguous")
    if source.dtype.hasobject:
        raise TypeError("object arrays cannot be sealed")
    immutable_bytes = bytes(source.tobytes(order="C"))
    sealed = np.frombuffer(immutable_bytes, dtype=source.dtype).reshape(source.shape)
    if sealed.flags.writeable:
        raise AssertionError("bytes-backed arrays must be read-only")
    return sealed


def _plain_float(value: object, name: str, *, positive: bool = False) -> float:
    if type(value) is not float:
        raise TypeError(f"{name} must be a built-in float")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if positive and value <= 0.0:
        raise ValueError(f"{name} must be positive")
    return value


def _optional_nonnegative_int(value: object, name: str) -> int | None:
    return None if value is None else _plain_nonnegative_int(value, name)


def _behavior_free_tuple(value: object, name: str) -> tuple[object, ...]:
    if type(value) is not tuple:
        raise TypeError(f"{name} must be a built-in tuple")

    def validate(item: object) -> object:
        if item is None or type(item) in (bool, int, str):
            return item
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError(f"{name} floats must be finite")
            return item
        if type(item) is tuple:
            return tuple(validate(child) for child in item)
        raise TypeError(f"{name} contains behavior-bearing data")

    return tuple(validate(item) for item in value)


def _link_csr_arrays(
    node_count: int,
    node_indices: tuple[int, ...],
) -> tuple[np.ndarray, np.ndarray]:
    counts = [0] * node_count
    for node_index in node_indices:
        counts[node_index] += 1
    indptr = [0] * (node_count + 1)
    for index, count in enumerate(counts):
        indptr[index + 1] = indptr[index] + count
    write = indptr[:-1].copy()
    indices = [0] * len(node_indices)
    for link_index, node_index in enumerate(node_indices):
        position = write[node_index]
        indices[position] = link_index
        write[node_index] += 1
    return np.asarray(indptr, dtype=np.int32), np.asarray(indices, dtype=np.int32)


def _array_payload(name: str, array: np.ndarray) -> tuple[object, ...]:
    return (
        name,
        array.dtype.str,
        array.shape,
        "C",
        array.nbytes,
        hashlib.sha256(array.tobytes(order="C")).hexdigest(),
    )


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

    def __post_init__(self) -> None:
        if type(self) is not BlockLandUseV2:
            raise TypeError("block land use must be an exact BlockLandUseV2")
        for name in (
            "block_id",
            "parent_face_id",
            "primary_access_node_id",
            "final_resident_capacity",
            "final_home_capacity",
            "final_job_capacity",
            "final_leisure_capacity",
            "taz_id",
        ):
            object.__setattr__(
                self,
                name,
                _plain_nonnegative_int(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "block_semantic_id",
            _digest_text(self.block_semantic_id, "block_semantic_id"),
        )
        if type(self.land_use_type) is not V2LandUseType:
            raise TypeError("land_use_type must be an exact V2LandUseType")
        object.__setattr__(
            self,
            "outer_polygon_mm",
            _polygon(self.outer_polygon_mm, "outer_polygon_mm"),
        )
        if type(self.hole_polygons_mm) is not tuple:
            raise TypeError("hole_polygons_mm must be a built-in tuple")
        object.__setattr__(
            self,
            "hole_polygons_mm",
            tuple(_polygon(hole, "hole_polygon_mm") for hole in self.hole_polygons_mm),
        )
        if type(self.exact_net_area_mm2) is not Fraction:
            raise TypeError("exact_net_area_mm2 must be an exact Fraction")
        if self.exact_net_area_mm2 <= 0:
            raise ValueError("exact_net_area_mm2 must be positive")
        object.__setattr__(
            self,
            "frontage_road_ids",
            _plain_int_tuple(
                self.frontage_road_ids,
                "frontage_road_ids",
                nonempty=True,
                sorted_unique=True,
            ),
        )
        object.__setattr__(
            self,
            "access_node_ids",
            _plain_int_tuple(
                self.access_node_ids,
                "access_node_ids",
                nonempty=True,
                sorted_unique=True,
            ),
        )
        if self.primary_access_node_id not in self.access_node_ids:
            raise ValueError("primary access node must belong to access_node_ids")
        object.__setattr__(
            self,
            "interior_witness_mm",
            _exact_witness(self.interior_witness_mm, "interior_witness_mm"),
        )
        if type(self.terrain_cell) is not tuple or len(self.terrain_cell) != 2:
            raise TypeError("terrain_cell must be a built-in pair")
        object.__setattr__(
            self,
            "terrain_cell",
            (
                _plain_int(self.terrain_cell[0], "terrain_cell x"),
                _plain_int(self.terrain_cell[1], "terrain_cell y"),
            ),
        )
        for name in ("terrain_intensity", "centrality_score", "exposure_score"):
            value = _plain_float(getattr(self, name), name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
            object.__setattr__(self, name, value)
        if type(self.terrain_intensity_hex) is not str:
            raise TypeError("terrain_intensity_hex must be a built-in string")
        if self.terrain_intensity_hex != self.terrain_intensity.hex():
            raise ValueError("terrain_intensity_hex mismatch")
        for float_name, ratio_name in (
            ("raw_resident_weight", "raw_resident_ratio"),
            ("raw_home_weight", "raw_home_ratio"),
            ("raw_job_weight", "raw_job_ratio"),
            ("raw_leisure_weight", "raw_leisure_ratio"),
        ):
            ratio = _ratio_pair(getattr(self, ratio_name), ratio_name)
            raw = _plain_float(getattr(self, float_name), float_name)
            if raw < 0.0 or raw != float(Fraction(*ratio)):
                raise ValueError(f"{float_name} does not match {ratio_name}")
            object.__setattr__(self, ratio_name, ratio)
            object.__setattr__(self, float_name, raw)
        if (
            self.raw_resident_ratio != self.raw_home_ratio
            or self.raw_resident_weight != self.raw_home_weight
            or self.final_resident_capacity != self.final_home_capacity
        ):
            raise ValueError("resident/home channels must be identical")
        for name in ("source_network_fingerprint", "source_blocks_fingerprint"):
            object.__setattr__(self, name, _digest_text(getattr(self, name), name))
        if type(self.policy_version) is not str or self.policy_version != LAND_USE_POLICY:
            raise ValueError("land-use policy mismatch")
        _install_record_fingerprint(self)


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

    def __post_init__(self) -> None:
        if type(self) is not PopulationCapacityCertificate:
            raise TypeError("certificate must be an exact PopulationCapacityCertificate")
        if type(self.schema_version) is not str or self.schema_version != ALLOCATION_POLICY:
            raise ValueError("certificate schema mismatch")
        for name in (
            "target_population",
            "job_target",
            "worker_share_numerator",
            "worker_share_denominator",
            "resident_capacity_total",
            "home_capacity_total",
            "job_capacity_total",
            "leisure_capacity_total",
            "taz_count",
            "allocated_block_count",
            "silent_cap_count",
            "dropped_capacity_count",
        ):
            object.__setattr__(
                self,
                name,
                _plain_nonnegative_int(getattr(self, name), name),
            )
        if (self.worker_share_numerator, self.worker_share_denominator) != (31, 50):
            raise ValueError("worker share must be 31/50")
        if self.job_target != (31 * self.target_population + 49) // 50:
            raise ValueError("job target must be ceil(31P/50)")
        if (
            self.resident_capacity_total != self.target_population
            or self.home_capacity_total != self.target_population
            or self.job_capacity_total != self.job_target
        ):
            raise ValueError("authoritative capacity totals mismatch")
        if self.taz_count != _taz_count_policy_unbounded(self.target_population):
            raise ValueError("certificate TAZ count mismatch")
        if self.allocated_block_count < self.taz_count:
            raise ValueError("allocated block count must cover every TAZ")
        if type(self.capacity_cap_applied) is not bool:
            raise TypeError("capacity_cap_applied must be a built-in bool")
        if self.capacity_cap_applied or self.silent_cap_count or self.dropped_capacity_count:
            raise ValueError("capacity cap/drop invariants must remain false/zero")
        for name in (
            "resident_raw_total_ratio",
            "home_raw_total_ratio",
            "job_raw_total_ratio",
            "leisure_raw_total_ratio",
            "resident_multiplier_ratio",
            "home_multiplier_ratio",
            "job_multiplier_ratio",
            "leisure_multiplier_ratio",
        ):
            object.__setattr__(self, name, _ratio_pair(getattr(self, name), name))
        if (
            self.resident_raw_total_ratio != self.home_raw_total_ratio
            or self.resident_multiplier_ratio != self.home_multiplier_ratio
        ):
            raise ValueError("certificate resident/home ratios must match")
        for name in (
            "allocation_fingerprint",
            "source_network_fingerprint",
            "source_blocks_fingerprint",
            "source_compiled_fingerprint",
        ):
            object.__setattr__(self, name, _digest_text(getattr(self, name), name))
        if (
            type(self.land_use_policy_version) is not str
            or self.land_use_policy_version != LAND_USE_POLICY
            or type(self.allocation_policy_version) is not str
            or self.allocation_policy_version != ALLOCATION_POLICY
        ):
            raise ValueError("certificate policy mismatch")
        _install_record_fingerprint(self)


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

    def __post_init__(self) -> None:
        if type(self) is not V2Taz:
            raise TypeError("TAZ must be an exact V2Taz")
        object.__setattr__(self, "taz_id", _plain_nonnegative_int(self.taz_id, "taz_id"))
        semantic = _digest_text(self.semantic_id, "semantic_id")
        object.__setattr__(self, "semantic_id", semantic)
        block_ids = _plain_int_tuple(self.block_ids, "block_ids", nonempty=True)
        if type(self.block_semantic_ids) is not tuple:
            raise TypeError("block_semantic_ids must be a built-in tuple")
        semantics = tuple(
            _digest_text(value, "block_semantic_id") for value in self.block_semantic_ids
        )
        if len(block_ids) != len(semantics) or len(set(block_ids)) != len(block_ids):
            raise ValueError("TAZ block IDs and semantics must be unique positional pairs")
        if len(set(semantics)) != len(semantics):
            raise ValueError("TAZ block semantic IDs must be unique")
        if tuple(zip(semantics, block_ids, strict=True)) != tuple(
            sorted(zip(semantics, block_ids, strict=True))
        ):
            raise ValueError("TAZ blocks must be ordered by semantic ID then block ID")
        object.__setattr__(self, "block_ids", block_ids)
        object.__setattr__(self, "block_semantic_ids", semantics)
        for name in ("frontage_road_ids", "access_node_ids"):
            object.__setattr__(
                self,
                name,
                _plain_int_tuple(
                    getattr(self, name),
                    name,
                    nonempty=True,
                    sorted_unique=True,
                ),
            )
        for name in (
            "resident_capacity_total",
            "home_capacity_total",
            "job_capacity_total",
            "leisure_capacity_total",
        ):
            object.__setattr__(
                self,
                name,
                _plain_nonnegative_int(getattr(self, name), name),
            )
        if self.resident_capacity_total != self.home_capacity_total:
            raise ValueError("TAZ resident/home capacities must match")
        expected_semantic = _sha256_payload((TAZ_POLICY, self.taz_id, semantics))
        if semantic != expected_semantic:
            raise ValueError("TAZ semantic ID mismatch")
        _install_record_fingerprint(self)


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

    def __post_init__(self) -> None:
        if type(self) is not V2TazCatalog:
            raise TypeError("TAZ catalog must be an exact V2TazCatalog")
        if type(self.schema_version) is not str or self.schema_version != TAZ_POLICY:
            raise ValueError("TAZ catalog schema mismatch")
        if type(self.tazs) is not tuple or any(type(taz) is not V2Taz for taz in self.tazs):
            raise TypeError("tazs must contain exact V2Taz records")
        target = _plain_nonnegative_int(self.target_taz_count, "target_taz_count")
        if target != len(self.tazs) or tuple(taz.taz_id for taz in self.tazs) != tuple(
            range(target)
        ):
            raise ValueError("TAZ IDs must be dense and cover the target count")
        semantic_payload_by_digest: dict[str, tuple[object, ...]] = {}
        content_payload_by_digest: dict[str, tuple[object, ...]] = {}
        for taz in self.tazs:
            semantic_payload = (TAZ_POLICY, taz.taz_id, taz.block_semantic_ids)
            previous_semantic = semantic_payload_by_digest.get(taz.semantic_id)
            if previous_semantic is not None and previous_semantic != semantic_payload:
                raise ValueError("TAZ semantic digest collision")
            semantic_payload_by_digest[taz.semantic_id] = semantic_payload
            content_payload = _record_payload(taz)
            previous_content = content_payload_by_digest.get(taz.fingerprint)
            if previous_content is not None and previous_content != content_payload:
                raise ValueError("TAZ content digest collision")
            content_payload_by_digest[taz.fingerprint] = content_payload
        expected_block_map = tuple(
            sorted(
                (block_id, taz.taz_id)
                for taz in self.tazs
                for block_id in taz.block_ids
            )
        )
        if type(self.block_taz_by_id) is not tuple or self.block_taz_by_id != expected_block_map:
            raise ValueError("block_taz_by_id mismatch")
        if type(self.node_owner_by_id) is not tuple:
            raise TypeError("node_owner_by_id must be a built-in tuple")
        node_owners = tuple(
            (
                _plain_nonnegative_int(node, "owner node id"),
                _plain_nonnegative_int(taz, "owner taz id"),
            )
            for node, taz in self.node_owner_by_id
        )
        if node_owners != tuple(sorted(node_owners)) or len({row[0] for row in node_owners}) != len(
            node_owners
        ):
            raise ValueError("node owners must be unique and sorted")
        if any(taz >= target for _, taz in node_owners):
            raise ValueError("node owner references an unknown TAZ")
        object.__setattr__(self, "node_owner_by_id", node_owners)
        if type(self.node_conflicts) is not tuple:
            raise TypeError("node_conflicts must be a built-in tuple")
        previous_node = -1
        for node, candidates, winner in self.node_conflicts:
            node = _plain_nonnegative_int(node, "conflict node id")
            if node <= previous_node or type(candidates) is not tuple or len(candidates) < 2:
                raise ValueError("node conflicts must be sorted with multiple candidates")
            previous_node = node
            parsed = tuple(
                (
                    _digest_text(semantic, "conflict semantic ID"),
                    _plain_nonnegative_int(taz, "conflict taz ID"),
                )
                for semantic, taz in candidates
            )
            if parsed != tuple(sorted(parsed)) or winner != parsed[0][1]:
                raise ValueError("node conflict winner must use semantic candidate order")
            if dict(node_owners).get(node) != winner:
                raise ValueError("node conflict winner differs from node owner")
        for name in (
            "source_blocks_fingerprint",
            "source_allocation_fingerprint",
            "assignment_fingerprint",
        ):
            object.__setattr__(self, name, _digest_text(getattr(self, name), name))
        expanded = tuple(_record_payload(taz) for taz in self.tazs)
        payload = (
            "V2TazCatalog",
            self.schema_version,
            expanded,
            self.block_taz_by_id,
            self.node_owner_by_id,
            self.node_conflicts,
            target,
            self.source_blocks_fingerprint,
            self.source_allocation_fingerprint,
            self.assignment_fingerprint,
        )
        expected_fingerprint = _sha256_payload(payload)
        if self.fingerprint:
            if _digest_text(self.fingerprint, "fingerprint") != expected_fingerprint:
                raise ValueError("TAZ catalog fingerprint mismatch")
        else:
            object.__setattr__(self, "fingerprint", expected_fingerprint)


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
        if type(self) is not V2Poi:
            raise TypeError("poi must be an exact V2Poi")
        for name in ("poi_id", "block_id", "access_node_id", "taz_id", "capacity"):
            object.__setattr__(
                self,
                name,
                _plain_nonnegative_int(getattr(self, name), name),
            )
        semantic_id = _digest_text(self.semantic_id, "semantic_id")
        block_semantic_id = _digest_text(self.block_semantic_id, "block_semantic_id")
        if type(self.poi_kind) is not V2PoiKind:
            raise TypeError("poi_kind must be an exact V2PoiKind")
        witness = _exact_witness(self.location_witness_mm, "location_witness_mm")
        source = _digest_text(
            self.source_allocation_fingerprint,
            "source_allocation_fingerprint",
        )
        expected_semantic = _sha256_payload(
            (POI_POLICY, block_semantic_id, self.poi_kind.value)
        )
        if semantic_id != expected_semantic:
            raise ValueError("POI semantic ID does not match its stable payload")
        object.__setattr__(self, "semantic_id", semantic_id)
        object.__setattr__(self, "block_semantic_id", block_semantic_id)
        object.__setattr__(self, "location_witness_mm", witness)
        object.__setattr__(self, "source_allocation_fingerprint", source)
        payload = (
            "V2Poi",
            self.poi_id,
            self.semantic_id,
            self.poi_kind,
            self.block_id,
            self.block_semantic_id,
            self.location_witness_mm,
            self.access_node_id,
            self.taz_id,
            self.capacity,
            self.source_allocation_fingerprint,
        )
        expected_fingerprint = _sha256_payload(payload)
        if self.fingerprint:
            if _digest_text(self.fingerprint, "fingerprint") != expected_fingerprint:
                raise ValueError("POI fingerprint does not match canonical content")
        else:
            object.__setattr__(self, "fingerprint", expected_fingerprint)


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
        if type(self) is not V2PoiCatalog:
            raise TypeError("POI catalog must be an exact V2PoiCatalog")
        if type(self.schema_version) is not str or self.schema_version != POI_POLICY:
            raise ValueError("POI catalog schema mismatch")
        if type(self.pois) is not tuple:
            raise TypeError("pois must be a built-in tuple")
        if any(type(poi) is not V2Poi for poi in self.pois):
            raise TypeError("pois must contain exact V2Poi records")
        source = _digest_text(
            self.source_allocation_fingerprint,
            "source_allocation_fingerprint",
        )
        source_taz = _digest_text(self.source_taz_fingerprint, "source_taz_fingerprint")
        if tuple(poi.poi_id for poi in self.pois) != tuple(range(len(self.pois))):
            raise ValueError("POI IDs must be dense and ordered")
        semantics: set[str] = set()
        expanded: list[tuple[object, ...]] = []
        totals = {kind: 0 for kind in V2PoiKind}
        for poi in self.pois:
            semantic = _digest_text(poi.semantic_id, "POI semantic_id")
            if semantic in semantics:
                raise ValueError("POI semantic IDs must be unique")
            semantics.add(semantic)
            if poi.source_allocation_fingerprint != source:
                raise ValueError("POI source allocation fingerprint mismatch")
            expected_semantic = _sha256_payload(
                (POI_POLICY, poi.block_semantic_id, poi.poi_kind.value)
            )
            if semantic != expected_semantic:
                raise ValueError("nested POI semantic ID mismatch")
            payload = (
                "V2Poi",
                poi.poi_id,
                poi.semantic_id,
                poi.poi_kind,
                poi.block_id,
                poi.block_semantic_id,
                poi.location_witness_mm,
                poi.access_node_id,
                poi.taz_id,
                poi.capacity,
                poi.source_allocation_fingerprint,
            )
            if _digest_text(poi.fingerprint, "POI fingerprint") != _sha256_payload(payload):
                raise ValueError("nested POI fingerprint mismatch")
            expanded.append(payload)
            totals[poi.poi_kind] += poi.capacity
        expected_totals = (
            totals[V2PoiKind.HOME],
            totals[V2PoiKind.WORKPLACE],
            totals[V2PoiKind.LEISURE],
        )
        supplied_totals = tuple(
            _plain_nonnegative_int(getattr(self, name), name)
            for name in (
                "home_capacity_total",
                "workplace_capacity_total",
                "leisure_capacity_total",
            )
        )
        if supplied_totals != expected_totals:
            raise ValueError("POI catalog totals do not match member capacities")
        object.__setattr__(self, "source_allocation_fingerprint", source)
        object.__setattr__(self, "source_taz_fingerprint", source_taz)
        payload = (
            "V2PoiCatalog",
            self.schema_version,
            tuple(expanded),
            *supplied_totals,
            source,
            source_taz,
        )
        expected_fingerprint = _sha256_payload(payload)
        if self.fingerprint:
            if _digest_text(self.fingerprint, "fingerprint") != expected_fingerprint:
                raise ValueError("POI catalog fingerprint mismatch")
        else:
            object.__setattr__(self, "fingerprint", expected_fingerprint)


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
        if type(self) is not MapFingerprintSetV3:
            raise TypeError("fingerprint set must be an exact MapFingerprintSetV3")
        if type(self.schema_version) is not str or self.schema_version != FINGERPRINT_SET_SCHEMA:
            raise ValueError("fingerprint-set schema mismatch")
        origins = {
            name: _digest_text(getattr(self, name), name)
            for name in (
                "config",
                "geometry",
                "topology",
                "link_attributes",
                "turn_authority",
                "blocks_access",
                "land_use_zoning",
            )
        }
        expected = _derived_map_nodes(**origins)
        for name, value in expected.items():
            supplied = _digest_text(getattr(self, name), name)
            if supplied != value:
                raise ValueError(f"{name} does not match its origin-node payload")


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
        if type(self) is not RoutingStaticDependencyKey:
            raise TypeError("routing key must be an exact RoutingStaticDependencyKey")
        expected_literals = {
            "schema_version": ROUTING_KEY_SCHEMA,
            "routing_policy_version": ROUTING_POLICY,
            "access_direction_policy_version": ACCESS_DIRECTION_POLICY,
            "closure_capability_policy_version": CLOSURE_CAPABILITY_POLICY,
        }
        for name, expected in expected_literals.items():
            value = getattr(self, name)
            if type(value) is not str or value != expected:
                raise ValueError(f"{name} mismatch")
        routing = _digest_text(
            self.routing_static_fingerprint,
            "routing_static_fingerprint",
        )
        source = _digest_text(self.source_csr_fingerprint, "source_csr_fingerprint")
        object.__setattr__(self, "routing_static_fingerprint", routing)
        object.__setattr__(self, "source_csr_fingerprint", source)
        payload = (
            "RoutingStaticDependencyKey",
            self.schema_version,
            routing,
            self.routing_policy_version,
            self.access_direction_policy_version,
            self.closure_capability_policy_version,
            source,
        )
        expected_fingerprint = _sha256_payload(payload)
        if self.fingerprint:
            if _digest_text(self.fingerprint, "fingerprint") != expected_fingerprint:
                raise ValueError("routing dependency key fingerprint mismatch")
        else:
            object.__setattr__(self, "fingerprint", expected_fingerprint)


@dataclass(frozen=True, slots=True)
class ImmutableNode:
    node_id: int
    kind: NodeKind
    x: float
    y: float
    zone_id: int | None
    signal_group_id: int | None

    def __post_init__(self) -> None:
        if type(self) is not ImmutableNode:
            raise TypeError("node must be an exact ImmutableNode")
        object.__setattr__(self, "node_id", _plain_nonnegative_int(self.node_id, "node_id"))
        if type(self.kind) is not NodeKind:
            raise TypeError("kind must be an exact NodeKind")
        object.__setattr__(self, "x", _plain_float(self.x, "x"))
        object.__setattr__(self, "y", _plain_float(self.y, "y"))
        object.__setattr__(
            self,
            "zone_id",
            _optional_nonnegative_int(self.zone_id, "zone_id"),
        )
        object.__setattr__(
            self,
            "signal_group_id",
            _optional_nonnegative_int(self.signal_group_id, "signal_group_id"),
        )


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

    def __post_init__(self) -> None:
        if type(self) is not ImmutableRoadLink:
            raise TypeError("link must be an exact ImmutableRoadLink")
        for name in ("link_id", "src_node_id", "dst_node_id"):
            object.__setattr__(
                self,
                name,
                _plain_nonnegative_int(getattr(self, name), name),
            )
        if self.src_node_id == self.dst_node_id:
            raise ValueError("link endpoints must differ")
        if type(self.road_class) is not RoadClass:
            raise TypeError("road_class must be an exact RoadClass")
        for name in ("length_m", "free_flow_speed_mps"):
            object.__setattr__(self, name, _plain_float(getattr(self, name), name, positive=True))
        object.__setattr__(
            self,
            "capacity_veh_per_tick",
            _plain_float(self.capacity_veh_per_tick, "capacity_veh_per_tick"),
        )
        if self.capacity_veh_per_tick < 0.0:
            raise ValueError("capacity_veh_per_tick must be nonnegative")
        lanes = _plain_nonnegative_int(self.lanes, "lanes")
        if lanes < 1:
            raise ValueError("lanes must be positive")
        object.__setattr__(self, "lanes", lanes)
        object.__setattr__(
            self,
            "bridge_group_id",
            _optional_nonnegative_int(self.bridge_group_id, "bridge_group_id"),
        )
        if type(self.is_blockable) is not bool:
            raise TypeError("is_blockable must be a built-in bool")
        object.__setattr__(
            self,
            "physical_road_id",
            _optional_nonnegative_int(self.physical_road_id, "physical_road_id"),
        )


@dataclass(frozen=True, slots=True)
class ImmutableTurnMovement:
    from_link_id: int
    to_link_id: int
    turn_type: TurnType
    base_priority: float
    signal_phase_id: int | None

    def __post_init__(self) -> None:
        if type(self) is not ImmutableTurnMovement:
            raise TypeError("turn must be an exact ImmutableTurnMovement")
        for name in ("from_link_id", "to_link_id"):
            object.__setattr__(
                self,
                name,
                _plain_nonnegative_int(getattr(self, name), name),
            )
        if type(self.turn_type) is not TurnType:
            raise TypeError("turn_type must be an exact TurnType")
        object.__setattr__(
            self,
            "base_priority",
            _plain_float(self.base_priority, "base_priority"),
        )
        if self.base_priority < 0.0:
            raise ValueError("base_priority must be nonnegative")
        object.__setattr__(
            self,
            "signal_phase_id",
            _optional_nonnegative_int(self.signal_phase_id, "signal_phase_id"),
        )


@dataclass(frozen=True, slots=True)
class ImmutableBridgeCrossing:
    bridge_group_id: int
    link_ids: tuple[int, ...]
    barrier_id: int
    crossing_name: str
    bottleneck_rank_hint: int | None

    def __post_init__(self) -> None:
        if type(self) is not ImmutableBridgeCrossing:
            raise TypeError("bridge must be an exact ImmutableBridgeCrossing")
        object.__setattr__(
            self,
            "bridge_group_id",
            _plain_nonnegative_int(self.bridge_group_id, "bridge_group_id"),
        )
        if type(self.link_ids) is not tuple:
            raise TypeError("link_ids must be a built-in tuple")
        links = tuple(_plain_nonnegative_int(value, "bridge link id") for value in self.link_ids)
        if not links or len(set(links)) != len(links):
            raise ValueError("bridge link IDs must be nonempty and unique")
        object.__setattr__(self, "link_ids", links)
        object.__setattr__(
            self,
            "barrier_id",
            _plain_nonnegative_int(self.barrier_id, "barrier_id"),
        )
        if type(self.crossing_name) is not str or not self.crossing_name:
            raise TypeError("crossing_name must be a nonempty built-in string")
        object.__setattr__(
            self,
            "bottleneck_rank_hint",
            _optional_nonnegative_int(self.bottleneck_rank_hint, "bottleneck_rank_hint"),
        )


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
        if type(self) is not ImmutableRoadNetworkCSR:
            raise TypeError("road CSR must be an exact ImmutableRoadNetworkCSR")
        if type(self.schema_version) is not str or self.schema_version != IMMUTABLE_CSR_SCHEMA:
            raise ValueError("immutable CSR schema mismatch")
        for name, expected_type in (
            ("nodes", ImmutableNode),
            ("links", ImmutableRoadLink),
            ("turns", ImmutableTurnMovement),
            ("bridge_crossings", ImmutableBridgeCrossing),
        ):
            rows = getattr(self, name)
            if type(rows) is not tuple:
                raise TypeError(f"{name} must be a built-in tuple")
            if any(type(row) is not expected_type for row in rows):
                raise TypeError(f"{name} must contain exact immutable rows")

        node_index = {node.node_id: index for index, node in enumerate(self.nodes)}
        link_index = {link.link_id: index for index, link in enumerate(self.links)}
        if len(node_index) != len(self.nodes) or len(link_index) != len(self.links):
            raise ValueError("node and link IDs must be unique")
        for link in self.links:
            if link.src_node_id not in node_index or link.dst_node_id not in node_index:
                raise ValueError("link references an unknown node")
        expected_pairs: dict[tuple[int, int], int] = {}
        for turn_index, turn in enumerate(self.turns):
            if turn.from_link_id not in link_index or turn.to_link_id not in link_index:
                raise ValueError("turn references an unknown link")
            pair = (turn.from_link_id, turn.to_link_id)
            if turn.turn_type is not TurnType.U_TURN_FORBIDDEN:
                if pair in expected_pairs:
                    raise ValueError("legal turn pairs must be unique")
                expected_pairs[pair] = turn_index

        supplied_maps = (
            ("node_id_to_index", self.node_id_to_index, node_index),
            ("link_id_to_index", self.link_id_to_index, link_index),
            ("turn_pair_to_index", self.turn_pair_to_index, expected_pairs),
        )
        for name, supplied, expected in supplied_maps:
            if type(supplied) not in (dict, MappingProxyType):
                raise TypeError(f"{name} must be a built-in dict or mapping proxy")
            copied = dict(supplied)
            if copied != expected:
                raise ValueError(f"{name} differs from immutable rows")
            object.__setattr__(self, name, MappingProxyType(dict(copied)))

        src = tuple(node_index[link.src_node_id] for link in self.links)
        dst = tuple(node_index[link.dst_node_id] for link in self.links)
        outgoing_indptr, outgoing_indices = _link_csr_arrays(len(self.nodes), src)
        incoming_indptr, incoming_indices = _link_csr_arrays(len(self.nodes), dst)
        expected_arrays = {
            "node_ids": np.asarray([node.node_id for node in self.nodes], dtype=np.int32),
            "link_ids": np.asarray([link.link_id for link in self.links], dtype=np.int32),
            "link_src_node_index": np.asarray(src, dtype=np.int32),
            "link_dst_node_index": np.asarray(dst, dtype=np.int32),
            "outgoing_indptr": outgoing_indptr,
            "outgoing_link_indices": outgoing_indices,
            "incoming_indptr": incoming_indptr,
            "incoming_link_indices": incoming_indices,
            "turn_from_link_index": np.asarray(
                [link_index[turn.from_link_id] for turn in self.turns],
                dtype=np.int32,
            ),
            "turn_to_link_index": np.asarray(
                [link_index[turn.to_link_id] for turn in self.turns],
                dtype=np.int32,
            ),
            "turn_base_priority": np.asarray(
                [turn.base_priority for turn in self.turns],
                dtype=np.float32,
            ),
            "turn_is_forbidden": np.asarray(
                [turn.turn_type is TurnType.U_TURN_FORBIDDEN for turn in self.turns],
                dtype=np.bool_,
            ),
        }
        array_payloads: list[tuple[object, ...]] = []
        for name, expected in expected_arrays.items():
            supplied = getattr(self, name)
            if type(supplied) is not np.ndarray:
                raise TypeError(f"{name} must be an exact NumPy array")
            if (
                supplied.dtype != expected.dtype
                or supplied.shape != expected.shape
                or not supplied.flags.c_contiguous
                or not np.array_equal(supplied, expected)
            ):
                raise ValueError(f"{name} differs from immutable rows")
            sealed = _seal_c_array(supplied)
            object.__setattr__(self, name, sealed)
            array_payloads.append(_array_payload(name, sealed))

        topology_key = _behavior_free_tuple(self.topology_cache_key, "topology_cache_key")
        object.__setattr__(self, "topology_cache_key", topology_key)
        payload = (
            IMMUTABLE_CSR_SCHEMA,
            tuple(
                (node.node_id, node.kind, node.x, node.y, node.zone_id, node.signal_group_id)
                for node in self.nodes
            ),
            tuple(
                (
                    link.link_id,
                    link.src_node_id,
                    link.dst_node_id,
                    link.road_class,
                    link.length_m,
                    link.free_flow_speed_mps,
                    link.capacity_veh_per_tick,
                    link.lanes,
                    link.bridge_group_id,
                    link.is_blockable,
                    link.physical_road_id,
                )
                for link in self.links
            ),
            tuple(
                (
                    turn.from_link_id,
                    turn.to_link_id,
                    turn.turn_type,
                    turn.base_priority,
                    turn.signal_phase_id,
                )
                for turn in self.turns
            ),
            tuple(
                (
                    bridge.bridge_group_id,
                    bridge.link_ids,
                    bridge.barrier_id,
                    bridge.crossing_name,
                    bridge.bottleneck_rank_hint,
                )
                for bridge in self.bridge_crossings
            ),
            tuple(sorted(node_index.items())),
            tuple(sorted(link_index.items())),
            tuple(sorted(expected_pairs.items())),
            tuple(array_payloads),
            topology_key,
        )
        expected_fingerprint = _sha256_payload(payload)
        if self.content_fingerprint:
            if (
                _digest_text(self.content_fingerprint, "content_fingerprint")
                != expected_fingerprint
            ):
                raise ValueError("immutable CSR content fingerprint mismatch")
        else:
            object.__setattr__(self, "content_fingerprint", expected_fingerprint)


    @property
    def node_count(self) -> int:
        return len(self.nodes)


    @property
    def link_count(self) -> int:
        return len(self.links)


    @property
    def turn_count(self) -> int:
        return len(self.turns)

    def outgoing_links_for_node(self, node_id: int) -> tuple[ImmutableRoadLink, ...]:
        if type(node_id) is not int:
            raise TypeError("node_id must be a built-in integer")
        node_index = self.node_id_to_index[node_id]
        start = int(self.outgoing_indptr[node_index])
        end = int(self.outgoing_indptr[node_index + 1])
        return tuple(
            self.links[int(index)] for index in self.outgoing_link_indices[start:end]
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

    def __post_init__(self) -> None:
        if type(self) is not ScalableStaticAuthority:
            raise TypeError("authority must be an exact ScalableStaticAuthority")
        if type(self.schema_version) is not str or self.schema_version != STATIC_AUTHORITY_SCHEMA:
            raise ValueError("static authority schema mismatch")
        if type(self.scale_spec) is not CityScaleSpec:
            raise TypeError("scale_spec must be an exact CityScaleSpec")
        if type(self.style_id) is not str:
            raise TypeError("style_id must be a built-in string")
        object.__setattr__(self, "seed", _plain_int(self.seed, "seed"))
        object.__setattr__(self, "extent_mm", _exact_extent(self.extent_mm))
        object.__setattr__(self, "width_m", _plain_float(self.width_m, "width_m", positive=True))
        object.__setattr__(
            self,
            "height_m",
            _plain_float(self.height_m, "height_m", positive=True),
        )
        if type(self.centers_mm) is not tuple or not self.centers_mm:
            raise TypeError("centers_mm must be a nonempty built-in tuple")
        for center in self.centers_mm:
            if (
                type(center) is not tuple
                or len(center) != 2
                or type(center[0]) is not int
                or type(center[1]) is not int
            ):
                raise TypeError("centers_mm must contain exact integer pairs")
        for name in (
            "source_network_schema_version",
            "source_blocks_schema_version",
            "source_compiled_schema_version",
            "numeric_profile_policy_version",
        ):
            value = getattr(self, name)
            if type(value) is not str or not value:
                raise TypeError(f"{name} must be a nonempty built-in string")
        for name in (
            "source_network_fingerprint",
            "source_blocks_fingerprint",
            "source_compiled_fingerprint",
            "source_terrain_fingerprint",
            "source_scale_fingerprint",
            "source_style_fingerprint",
            "source_geometry_fingerprint",
            "source_section_fingerprint",
            "source_node_interface_fingerprint",
            "source_turn_authority_fingerprint",
        ):
            object.__setattr__(self, name, _digest_text(getattr(self, name), name))
        for name, expected_type in (
            ("numeric_profiles", ScalableNumericProfile),
            ("road_crosswalk", ScalableRoadCrosswalk),
            ("structure_group_crosswalk", ScalableGroupCrosswalk),
            ("failure_group_crosswalk", ScalableGroupCrosswalk),
            ("block_land_use", BlockLandUseV2),
        ):
            rows = getattr(self, name)
            if type(rows) is not tuple or any(type(row) is not expected_type for row in rows):
                raise TypeError(f"{name} must contain exact records")
        if type(self.block_access_index) is not V2BlockAccessIndex:
            raise TypeError("block_access_index must be an exact V2BlockAccessIndex")
        for name, expected_type in (
            ("capacity_certificate", PopulationCapacityCertificate),
            ("taz_catalog", V2TazCatalog),
            ("poi_catalog", V2PoiCatalog),
            ("fingerprints", MapFingerprintSetV3),
            ("road_csr", ImmutableRoadNetworkCSR),
            ("routing_dependency_key", RoutingStaticDependencyKey),
        ):
            if type(getattr(self, name)) is not expected_type:
                raise TypeError(f"{name} must be an exact {expected_type.__name__}")
        if tuple(block.block_id for block in self.block_land_use) != tuple(
            range(len(self.block_land_use))
        ):
            raise ValueError("block land-use IDs must be dense and ordered")
        expected = _sha256_payload(_static_authority_payload(self))
        if self.fingerprint:
            if _digest_text(self.fingerprint, "fingerprint") != expected:
                raise ValueError("static authority fingerprint mismatch")
        else:
            object.__setattr__(self, "fingerprint", expected)


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
    profiles = tuple(
        ScalableNumericProfile(
            profile_id=profile.profile_id,
            lanes_per_direction=profile.lanes_per_direction,
            free_flow_speed_mps=profile.free_flow_speed_mps,
            capacity_veh_per_second=profile.capacity_veh_per_second,
            operational_road_class=profile.operational_road_class,
            section_roadside_profile=profile.section_roadside_profile,
            median_when_bidirectional=profile.median_when_bidirectional,
        )
        for profile in compiled.numeric_profiles
    )
    roads = tuple(
        ScalableRoadCrosswalk(
            physical_road_id=road.physical_road_id,
            road_semantic_id=road.road_semantic_id,
            hierarchy=road.hierarchy,
            facility=road.facility,
            profile_id=road.profile_id,
            layer=road.layer,
            layer_transition=road.layer_transition,
            access_directions=road.access_directions,
            provenance=road.provenance,
            geometry_id=road.geometry_id,
            centerline_source_ref=road.centerline_source_ref,
            forward_link_id=road.forward_link_id,
            reverse_link_id=road.reverse_link_id,
            structure_group=road.structure_group,
            structure_group_id=road.structure_group_id,
            failure_group=road.failure_group,
            bridge_group_id=road.bridge_group_id,
        )
        for road in compiled.road_crosswalk
    )

    def copy_groups(
        values: tuple[ScalableGroupCrosswalk, ...],
    ) -> tuple[ScalableGroupCrosswalk, ...]:
        return tuple(
            ScalableGroupCrosswalk(
                semantic_group=group.semantic_group,
                dense_group_id=group.dense_group_id,
                member_physical_road_ids=tuple(group.member_physical_road_ids),
            )
            for group in values
        )

    source_index = blocks.access_index
    access_index = V2BlockAccessIndex(
        block_to_road_ids=tuple(
            (key, tuple(values)) for key, values in source_index.block_to_road_ids
        ),
        block_to_node_ids=tuple(
            (key, tuple(values)) for key, values in source_index.block_to_node_ids
        ),
        road_to_block_ids=tuple(
            (key, tuple(values)) for key, values in source_index.road_to_block_ids
        ),
        node_to_block_ids=tuple(
            (key, tuple(values)) for key, values in source_index.node_to_block_ids
        ),
        primary_access_by_block=tuple(source_index.primary_access_by_block),
        incidence_visit_count=source_index.incidence_visit_count,
    )
    source_csr = compiled.road_csr
    immutable_csr = ImmutableRoadNetworkCSR(
        schema_version=IMMUTABLE_CSR_SCHEMA,
        nodes=tuple(
            ImmutableNode(
                node_id=node.node_id,
                kind=node.kind,
                x=node.x,
                y=node.y,
                zone_id=node.zone_id,
                signal_group_id=node.signal_group_id,
            )
            for node in source_csr.nodes
        ),
        links=tuple(
            ImmutableRoadLink(
                link_id=link.link_id,
                src_node_id=link.src_node_id,
                dst_node_id=link.dst_node_id,
                road_class=link.road_class,
                length_m=link.length_m,
                free_flow_speed_mps=link.free_flow_speed_mps,
                capacity_veh_per_tick=link.capacity_veh_per_tick,
                lanes=link.lanes,
                bridge_group_id=link.bridge_group_id,
                is_blockable=link.is_blockable,
                physical_road_id=link.physical_road_id,
            )
            for link in source_csr.links
        ),
        turns=tuple(
            ImmutableTurnMovement(
                from_link_id=turn.from_link_id,
                to_link_id=turn.to_link_id,
                turn_type=turn.turn_type,
                base_priority=turn.base_priority,
                signal_phase_id=turn.signal_phase_id,
            )
            for turn in source_csr.turns
        ),
        bridge_crossings=tuple(
            ImmutableBridgeCrossing(
                bridge_group_id=bridge.bridge_group_id,
                link_ids=tuple(bridge.link_ids),
                barrier_id=bridge.barrier_id,
                crossing_name=bridge.crossing_name,
                bottleneck_rank_hint=bridge.bottleneck_rank_hint,
            )
            for bridge in source_csr.bridge_crossings
        ),
        node_id_to_index=source_csr.node_id_to_index,
        link_id_to_index=source_csr.link_id_to_index,
        turn_pair_to_index=source_csr.turn_pair_to_index,
        node_ids=source_csr.node_ids,
        link_ids=source_csr.link_ids,
        link_src_node_index=source_csr.link_src_node_index,
        link_dst_node_index=source_csr.link_dst_node_index,
        outgoing_indptr=source_csr.outgoing_indptr,
        outgoing_link_indices=source_csr.outgoing_link_indices,
        incoming_indptr=source_csr.incoming_indptr,
        incoming_link_indices=source_csr.incoming_link_indices,
        turn_from_link_index=source_csr.turn_from_link_index,
        turn_to_link_index=source_csr.turn_to_link_index,
        turn_base_priority=source_csr.turn_base_priority,
        turn_is_forbidden=source_csr.turn_is_forbidden,
        topology_cache_key=source_csr.topology_cache_key,
    )
    return _CopiedTask4(
        numeric_profiles=profiles,
        road_crosswalk=roads,
        structure_group_crosswalk=copy_groups(compiled.structure_group_crosswalk),
        failure_group_crosswalk=copy_groups(compiled.failure_group_crosswalk),
        block_access_index=access_index,
        road_csr=immutable_csr,
    )


def _admit_scalable_sources(
    scale_spec: CityScaleSpec,
    style_id: str,
    seed: int,
    network: ScalableStreetNetwork,
    blocks: ScalableBlockAuthority,
    compiled: ScalableCompiledTopology,
) -> CityScaleSpec:
    if type(scale_spec) is not CityScaleSpec:
        raise TypeError("scale_spec must be an exact CityScaleSpec")
    if type(style_id) is not str:
        raise TypeError("style_id must be a built-in string")
    if type(seed) is not int:
        raise TypeError("seed must be a built-in integer")
    if type(network) is not ScalableStreetNetwork:
        raise TypeError("network must be an exact ScalableStreetNetwork")
    if type(blocks) is not ScalableBlockAuthority:
        raise TypeError("blocks must be an exact ScalableBlockAuthority")
    if type(compiled) is not ScalableCompiledTopology:
        raise TypeError("compiled must be an exact ScalableCompiledTopology")

    normalized_scale = CityScaleSpec(
        scale_spec.target_population,
        scale_spec.urbanized_area_km2,
    )
    require_valid_scalable_compiled_topology(
        compiled,
        network=network,
        block_authority=blocks,
    )
    if (
        network.scale_spec.target_population != normalized_scale.target_population
        or network.scale_spec.urbanized_area_km2.hex()
        != normalized_scale.urbanized_area_km2.hex()
        or network.style_id != style_id
        or network.seed != seed
    ):
        raise ValueError("scale/style/seed differs from the admitted network")
    if blocks.extent_mm != network.extent_mm:
        raise ValueError("block/network extent mismatch")
    if (
        blocks.source_network_fingerprint != network.fingerprint
        or compiled.source_network_fingerprint != network.fingerprint
        or compiled.source_block_authority_fingerprint != blocks.fingerprint
        or compiled.terrain_fingerprint != network.terrain.fingerprint
        or compiled.scale_fingerprint != network.scale_fingerprint
        or compiled.style_fingerprint != network.style_fingerprint
    ):
        raise ValueError("Task 3/3B/4 source fingerprint chain mismatch")
    return normalized_scale


def _frontage_exposure(
    frontage_road_ids: tuple[int, ...],
    road_by_id: dict[int, ScalableRoadCrosswalk],
) -> float:
    values: list[Fraction] = []
    surface = {
        RoadHierarchy.LOCAL: Fraction(0),
        RoadHierarchy.COLLECTOR: Fraction(35, 100),
        RoadHierarchy.ARTERIAL: Fraction(80, 100),
        RoadHierarchy.EXPRESSWAY: Fraction(1),
    }
    for road_id in frontage_road_ids:
        road = road_by_id.get(road_id)
        if road is None:
            raise ValueError("block frontage references an unknown physical road")
        if road.facility is FacilityKind.SURFACE:
            values.append(surface[road.hierarchy])
        elif road.facility is FacilityKind.BRIDGE:
            values.append(Fraction(80, 100))
        else:
            raise ValueError("developable block frontage uses an ineligible facility")
    if not values:
        raise ValueError("developable block must have positive frontage")
    return float(max(values))


def _upstream_record_payload(record: object) -> tuple[object, ...]:
    return tuple(getattr(record, field.name) for field in fields(record))


def _block_source_payload(block: object) -> tuple[object, ...]:
    return (
        block.block_id,
        block.semantic_id,
        block.parent_face_id,
        block.outer_polygon_mm,
        block.hole_polygons_mm,
        block.net_area_mm2,
        block.frontage_road_ids,
        block.access_node_ids,
        block.primary_access_node_id,
        block.interior_witness_mm,
    )


def _access_index_payload(index: V2BlockAccessIndex) -> tuple[object, ...]:
    return tuple(getattr(index, field.name) for field in fields(index))


def _static_authority_payload(authority: ScalableStaticAuthority) -> tuple[object, ...]:
    return (
        authority.schema_version,
        (
            authority.scale_spec.target_population,
            authority.scale_spec.urbanized_area_km2.hex(),
        ),
        authority.style_id,
        authority.seed,
        authority.extent_mm,
        authority.width_m,
        authority.height_m,
        authority.centers_mm,
        authority.source_network_schema_version,
        authority.source_blocks_schema_version,
        authority.source_compiled_schema_version,
        authority.numeric_profile_policy_version,
        authority.source_network_fingerprint,
        authority.source_blocks_fingerprint,
        authority.source_compiled_fingerprint,
        authority.source_terrain_fingerprint,
        authority.source_scale_fingerprint,
        authority.source_style_fingerprint,
        authority.source_geometry_fingerprint,
        authority.source_section_fingerprint,
        authority.source_node_interface_fingerprint,
        authority.source_turn_authority_fingerprint,
        tuple(_upstream_record_payload(row) for row in authority.numeric_profiles),
        tuple(_upstream_record_payload(row) for row in authority.road_crosswalk),
        tuple(_upstream_record_payload(row) for row in authority.structure_group_crosswalk),
        tuple(_upstream_record_payload(row) for row in authority.failure_group_crosswalk),
        _access_index_payload(authority.block_access_index),
        tuple(block.fingerprint for block in authority.block_land_use),
        authority.capacity_certificate.fingerprint,
        authority.taz_catalog.fingerprint,
        authority.poi_catalog.fingerprint,
        tuple(getattr(authority.fingerprints, field.name) for field in fields(MapFingerprintSetV3)),
        authority.road_csr.content_fingerprint,
        authority.routing_dependency_key.fingerprint,
    )


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
    if type(block_rows) is not tuple:
        raise TypeError("block_rows must be a built-in tuple")
    source = _digest_text(
        source_allocation_fingerprint,
        "source_allocation_fingerprint",
    )
    block_ids: set[int] = set()
    semantic_ids: set[str] = set()
    semantic_payload_by_digest: dict[str, tuple[object, ...]] = {}
    pending: list[
        tuple[
            str,
            V2PoiKind,
            int,
            str,
            tuple[Fraction, Fraction],
            int,
            int,
            int,
        ]
    ] = []
    channels = (
        (V2PoiKind.HOME, 5),
        (V2PoiKind.WORKPLACE, 6),
        (V2PoiKind.LEISURE, 7),
    )
    for row in block_rows:
        if type(row) is not tuple or len(row) != 8:
            raise TypeError("each aggregate POI row must be a built-in eight-item tuple")
        block_id = _plain_nonnegative_int(row[0], "block_id")
        block_semantic_id = _digest_text(row[1], "block_semantic_id")
        if block_id in block_ids or block_semantic_id in semantic_ids:
            raise ValueError("aggregate POI rows require unique block and semantic IDs")
        block_ids.add(block_id)
        semantic_ids.add(block_semantic_id)
        witness = _exact_witness(row[2], "location_witness_mm")
        access_node_id = _plain_nonnegative_int(row[3], "access_node_id")
        taz_id = _plain_nonnegative_int(row[4], "taz_id")
        capacities = tuple(
            _plain_nonnegative_int(row[index], "POI channel capacity")
            for index in range(5, 8)
        )
        for kind, index in channels:
            capacity = capacities[index - 5]
            if capacity == 0:
                continue
            semantic_payload = (POI_POLICY, block_semantic_id, kind.value)
            semantic_id = _sha256_payload(semantic_payload)
            previous = semantic_payload_by_digest.get(semantic_id)
            if previous is not None and previous != semantic_payload:
                raise ValueError("aggregate POI semantic digest collision")
            semantic_payload_by_digest[semantic_id] = semantic_payload
            pending.append(
                (
                    semantic_id,
                    kind,
                    block_id,
                    block_semantic_id,
                    witness,
                    access_node_id,
                    taz_id,
                    capacity,
                )
            )
    pending.sort(key=lambda row: row[0])
    if len({row[0] for row in pending}) != len(pending):
        raise ValueError("aggregate POI semantic IDs must be unique")
    return tuple(
        V2Poi(
            poi_id=poi_id,
            semantic_id=row[0],
            poi_kind=row[1],
            block_id=row[2],
            block_semantic_id=row[3],
            location_witness_mm=row[4],
            access_node_id=row[5],
            taz_id=row[6],
            capacity=row[7],
            source_allocation_fingerprint=source,
        )
        for poi_id, row in enumerate(pending)
    )


def _derived_map_nodes(
    *,
    config: str,
    geometry: str,
    topology: str,
    link_attributes: str,
    turn_authority: str,
    blocks_access: str,
    land_use_zoning: str,
) -> dict[str, str]:
    payloads: list[tuple[str, tuple[object, ...]]] = []
    routing_payload = (
        ROUTING_STATIC_NODE_SCHEMA,
        ROUTING_POLICY,
        ACCESS_DIRECTION_POLICY,
        CLOSURE_CAPABILITY_POLICY,
        geometry,
        topology,
        link_attributes,
        turn_authority,
    )
    routing_static = _sha256_payload(routing_payload)
    payloads.append((routing_static, routing_payload))
    accessibility_payload = (
        ACCESSIBILITY_STATIC_NODE_SCHEMA,
        routing_static,
        land_use_zoning,
    )
    accessibility_static = _sha256_payload(accessibility_payload)
    payloads.append((accessibility_static, accessibility_payload))
    replay_payload = (
        REPLAY_STATIC_NODE_SCHEMA,
        config,
        geometry,
        topology,
        link_attributes,
        turn_authority,
        blocks_access,
        land_use_zoning,
        routing_static,
        accessibility_static,
        STATIC_BUILDER_BACKEND,
    )
    replay_static = _sha256_payload(replay_payload)
    payloads.append((replay_static, replay_payload))
    composite_payload = (
        COMPOSITE_NODE_SCHEMA,
        config,
        geometry,
        topology,
        link_attributes,
        turn_authority,
        blocks_access,
        land_use_zoning,
        routing_static,
        accessibility_static,
        replay_static,
    )
    composite = _sha256_payload(composite_payload)
    payloads.append((composite, composite_payload))
    seen: dict[str, tuple[object, ...]] = {}
    for digest, payload in payloads:
        previous = seen.get(digest)
        if previous is not None and previous != payload:
            raise ValueError("derived fingerprint digest collision")
        seen[digest] = payload
    return {
        "routing_static": routing_static,
        "accessibility_static": accessibility_static,
        "replay_static": replay_static,
        "composite": composite,
    }


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
    origins = {
        name: _digest_text(value, name)
        for name, value in (
            ("config", config),
            ("geometry", geometry),
            ("topology", topology),
            ("link_attributes", link_attributes),
            ("turn_authority", turn_authority),
            ("blocks_access", blocks_access),
            ("land_use_zoning", land_use_zoning),
        )
    }
    derived = _derived_map_nodes(**origins)
    return MapFingerprintSetV3(
        schema_version=FINGERPRINT_SET_SCHEMA,
        **origins,
        **derived,
    )


def _fraction_pair(value: Fraction) -> tuple[int, int]:
    if type(value) is not Fraction:
        raise TypeError("value must be an exact Fraction")
    return value.numerator, value.denominator


def _canonical_network_extent(
    network_extent_mm: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    if type(network_extent_mm) is not tuple or len(network_extent_mm) != 4:
        raise TypeError("network extent must be a built-in four-item tuple")
    xmin, xmax, ymin, ymax = (
        _plain_int(value, "network extent value") for value in network_extent_mm
    )
    return _exact_extent((xmin, ymin, xmax, ymax))


def _allocation_fingerprint(
    *,
    population: int,
    job_target: int,
    leisure_target: int,
    blocks: tuple[BlockLandUseV2, ...],
    raw_totals: tuple[Fraction, Fraction, Fraction, Fraction],
    multipliers: tuple[Fraction, Fraction, Fraction, Fraction],
) -> str:
    ordered_rows = tuple(
        (
            block.block_semantic_id,
            block.raw_resident_ratio,
            block.raw_home_ratio,
            block.raw_job_ratio,
            block.raw_leisure_ratio,
            block.final_resident_capacity,
            block.final_home_capacity,
            block.final_job_capacity,
            block.final_leisure_capacity,
        )
        for block in sorted(blocks, key=lambda item: item.block_semantic_id)
    )
    return _sha256_payload(
        (
            ALLOCATION_POLICY,
            population,
            job_target,
            leisure_target,
            ordered_rows,
            *tuple(_fraction_pair(value) for value in raw_totals),
            *tuple(_fraction_pair(value) for value in multipliers),
            False,
            0,
            0,
        )
    )


def _origin_fingerprints(
    *,
    scale_spec: CityScaleSpec,
    style_id: str,
    seed: int,
    network: ScalableStreetNetwork,
    blocks: ScalableBlockAuthority,
    compiled: ScalableCompiledTopology,
    copied: _CopiedTask4,
    block_land_use: tuple[BlockLandUseV2, ...],
    capacity_certificate: PopulationCapacityCertificate,
    taz_catalog: V2TazCatalog,
    poi_catalog: V2PoiCatalog,
) -> MapFingerprintSetV3:
    csr = copied.road_csr
    config_payload = (
        STATIC_CONFIG_NODE_SCHEMA,
        scale_spec.target_population,
        scale_spec.urbanized_area_km2.hex(),
        style_id,
        seed,
        STATIC_AUTHORITY_SCHEMA,
        LAND_USE_POLICY,
        ALLOCATION_POLICY,
        TAZ_POLICY,
        POI_POLICY,
        FINGERPRINT_SET_SCHEMA,
        IMMUTABLE_CSR_SCHEMA,
        ROUTING_KEY_SCHEMA,
        STATIC_CONFIG_NODE_SCHEMA,
        GEOMETRY_NODE_SCHEMA,
        TOPOLOGY_NODE_SCHEMA,
        LINK_ATTRIBUTES_NODE_SCHEMA,
        TURN_AUTHORITY_NODE_SCHEMA,
        BLOCKS_ACCESS_NODE_SCHEMA,
        LAND_USE_ZONING_NODE_SCHEMA,
        ROUTING_STATIC_NODE_SCHEMA,
        ACCESSIBILITY_STATIC_NODE_SCHEMA,
        REPLAY_STATIC_NODE_SCHEMA,
        COMPOSITE_NODE_SCHEMA,
        ROUTING_POLICY,
        ACCESS_DIRECTION_POLICY,
        CLOSURE_CAPABILITY_POLICY,
        network.schema_version,
        blocks.schema_version,
        compiled.schema_version,
        compiled.numeric_profile_policy_version,
        STATIC_BUILDER_BACKEND,
    )
    config = _sha256_payload(config_payload)
    geometry = _sha256_payload(
        (
            GEOMETRY_NODE_SCHEMA,
            compiled.road_geometry_fingerprint,
            tuple((node.node_id, node.x, node.y) for node in csr.nodes),
        )
    )
    topology = _sha256_payload(
        (
            TOPOLOGY_NODE_SCHEMA,
            tuple((node.node_id, node.kind) for node in csr.nodes),
            tuple(
                (
                    link.link_id,
                    link.src_node_id,
                    link.dst_node_id,
                    link.physical_road_id,
                )
                for link in csr.links
            ),
            _array_payload("node_ids", csr.node_ids),
            _array_payload("link_ids", csr.link_ids),
            _array_payload("link_src_node_index", csr.link_src_node_index),
            _array_payload("link_dst_node_index", csr.link_dst_node_index),
            _array_payload("outgoing_indptr", csr.outgoing_indptr),
            _array_payload("outgoing_link_indices", csr.outgoing_link_indices),
            _array_payload("incoming_indptr", csr.incoming_indptr),
            _array_payload("incoming_link_indices", csr.incoming_link_indices),
        )
    )
    link_attributes = _sha256_payload(
        (
            LINK_ATTRIBUTES_NODE_SCHEMA,
            compiled.road_section_fingerprint,
            tuple(
                (
                    link.link_id,
                    link.src_node_id,
                    link.dst_node_id,
                    link.road_class,
                    link.length_m,
                    link.free_flow_speed_mps,
                    link.capacity_veh_per_tick,
                    link.lanes,
                    link.bridge_group_id,
                    link.is_blockable,
                    link.physical_road_id,
                )
                for link in csr.links
            ),
            tuple(_upstream_record_payload(row) for row in copied.numeric_profiles),
            tuple(_upstream_record_payload(row) for row in copied.road_crosswalk),
            tuple(
                _upstream_record_payload(row)
                for row in copied.structure_group_crosswalk
            ),
            tuple(
                _upstream_record_payload(row)
                for row in copied.failure_group_crosswalk
            ),
            CAPACITY_REFERENCE_TICK_SECONDS,
            CAPACITY_SOURCE_UNIT,
            ACCESS_DIRECTION_POLICY,
            CLOSURE_CAPABILITY_POLICY,
        )
    )
    turn_authority = _sha256_payload(
        (
            TURN_AUTHORITY_NODE_SCHEMA,
            compiled.node_interface_fingerprint,
            compiled.turn_authority_fingerprint,
            tuple(
                (
                    turn.from_link_id,
                    turn.to_link_id,
                    turn.turn_type,
                    turn.base_priority,
                    turn.signal_phase_id,
                )
                for turn in csr.turns
            ),
            _array_payload("turn_from_link_index", csr.turn_from_link_index),
            _array_payload("turn_to_link_index", csr.turn_to_link_index),
            _array_payload("turn_base_priority", csr.turn_base_priority),
            _array_payload("turn_is_forbidden", csr.turn_is_forbidden),
            tuple(sorted(csr.turn_pair_to_index.items())),
        )
    )
    blocks_access = _sha256_payload(
        (
            BLOCKS_ACCESS_NODE_SCHEMA,
            blocks.fingerprint,
            tuple(_block_source_payload(block) for block in blocks.blocks),
            _access_index_payload(copied.block_access_index),
        )
    )
    land_use_zoning = _sha256_payload(
        (
            LAND_USE_ZONING_NODE_SCHEMA,
            LAND_USE_POLICY,
            ALLOCATION_POLICY,
            TAZ_POLICY,
            POI_POLICY,
            scale_spec.target_population,
            scale_spec.urbanized_area_km2.hex(),
            style_id,
            seed,
            network.terrain.fingerprint,
            network.centers,
            blocks_access,
            tuple(block.fingerprint for block in block_land_use),
            capacity_certificate.fingerprint,
            taz_catalog.fingerprint,
            poi_catalog.fingerprint,
        )
    )
    return _compose_map_fingerprint_set_v3(
        config=config,
        geometry=geometry,
        topology=topology,
        link_attributes=link_attributes,
        turn_authority=turn_authority,
        blocks_access=blocks_access,
        land_use_zoning=land_use_zoning,
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
    copied = _copy_task4_authorities(blocks=blocks, compiled=compiled)
    source_blocks = tuple(sorted(blocks.blocks, key=lambda block: block.block_id))
    if tuple(block.block_id for block in source_blocks) != tuple(range(len(source_blocks))):
        raise ValueError("Task 3B block IDs must be dense and ordered")
    extent_mm = _canonical_network_extent(network.extent_mm)
    road_by_id = {road.physical_road_id: road for road in copied.road_crosswalk}
    if len(road_by_id) != len(copied.road_crosswalk):
        raise ValueError("road crosswalk IDs must be unique")

    feature_by_id: dict[int, tuple[tuple[int, int], float, float, float]] = {}
    feature_rows: list[tuple[int, str, float, float, float]] = []
    for block in source_blocks:
        if (
            type(block.net_area_mm2) is not Fraction
            or block.net_area_mm2 <= 0
            or not block.frontage_road_ids
            or not block.access_node_ids
            or block.primary_access_node_id not in block.access_node_ids
        ):
            raise ValueError("Task 3B block is not addressable")
        terrain_cell, intensity = _sample_terrain_at_exact_witness(
            terrain=network.terrain,
            witness_mm=block.interior_witness_mm,
        )
        centrality = _centrality_score_mm(
            witness_mm=block.interior_witness_mm,
            centers_mm=network.centers,
            width_m=network.width_m,
            height_m=network.height_m,
        )
        exposure = _frontage_exposure(block.frontage_road_ids, road_by_id)
        feature_by_id[block.block_id] = (
            terrain_cell,
            intensity,
            centrality,
            exposure,
        )
        feature_rows.append(
            (block.block_id, block.semantic_id, centrality, intensity, exposure)
        )

    classifications = dict(
        _classify_land_use_rows(
            feature_rows=tuple(feature_rows),
            road_to_block_ids=copied.block_access_index.road_to_block_ids,
        )
    )
    raw_by_id: dict[int, tuple[Fraction, Fraction, Fraction, Fraction]] = {}
    for block in source_blocks:
        raw_by_id[block.block_id] = _raw_capacity_ratios(
            exact_net_area_mm2=block.net_area_mm2,
            terrain_intensity=feature_by_id[block.block_id][1],
            land_use_type=classifications[block.block_id],
        )
    raw_totals = tuple(
        sum((raw_by_id[block.block_id][channel] for block in source_blocks), Fraction(0))
        for channel in range(4)
    )
    population = scale_spec.target_population
    job_target = (31 * population + 49) // 50
    leisure_target = round(raw_totals[3])
    targets = (population, population, job_target, leisure_target)
    multipliers = tuple(
        _require_implied_multiplier(
            target=target,
            raw_total=raw_total,
            enforce_authoritative_bounds=channel < 3,
        )
        for channel, (target, raw_total) in enumerate(
            zip(targets, raw_totals, strict=True)
        )
    )
    apportioned = tuple(
        dict(
            _apportion_exact_channel(
                target=target,
                weighted_rows=tuple(
                    (block.semantic_id, raw_by_id[block.block_id][channel])
                    for block in source_blocks
                ),
            )
        )
        for channel, target in enumerate(targets)
    )

    taz_count = _taz_count_policy_unbounded(population)
    partitions = _partition_morton_rows(
        rows=tuple(
            (block.block_id, block.semantic_id, block.interior_witness_mm)
            for block in source_blocks
        ),
        extent_mm=extent_mm,
        taz_count=taz_count,
    )
    taz_by_block = {
        block_id: taz_id for taz_id, member_ids in partitions for block_id in member_ids
    }
    block_land_use = tuple(
        BlockLandUseV2(
            block_id=block.block_id,
            block_semantic_id=block.semantic_id,
            parent_face_id=block.parent_face_id,
            land_use_type=classifications[block.block_id],
            outer_polygon_mm=block.outer_polygon_mm,
            hole_polygons_mm=block.hole_polygons_mm,
            exact_net_area_mm2=block.net_area_mm2,
            frontage_road_ids=block.frontage_road_ids,
            access_node_ids=block.access_node_ids,
            primary_access_node_id=block.primary_access_node_id,
            interior_witness_mm=block.interior_witness_mm,
            terrain_cell=feature_by_id[block.block_id][0],
            terrain_intensity=feature_by_id[block.block_id][1],
            terrain_intensity_hex=feature_by_id[block.block_id][1].hex(),
            centrality_score=feature_by_id[block.block_id][2],
            exposure_score=feature_by_id[block.block_id][3],
            raw_resident_weight=float(raw_by_id[block.block_id][0]),
            raw_home_weight=float(raw_by_id[block.block_id][1]),
            raw_job_weight=float(raw_by_id[block.block_id][2]),
            raw_leisure_weight=float(raw_by_id[block.block_id][3]),
            raw_resident_ratio=_fraction_pair(raw_by_id[block.block_id][0]),
            raw_home_ratio=_fraction_pair(raw_by_id[block.block_id][1]),
            raw_job_ratio=_fraction_pair(raw_by_id[block.block_id][2]),
            raw_leisure_ratio=_fraction_pair(raw_by_id[block.block_id][3]),
            final_resident_capacity=apportioned[0][block.semantic_id],
            final_home_capacity=apportioned[1][block.semantic_id],
            final_job_capacity=apportioned[2][block.semantic_id],
            final_leisure_capacity=apportioned[3][block.semantic_id],
            taz_id=taz_by_block[block.block_id],
            source_network_fingerprint=network.fingerprint,
            source_blocks_fingerprint=blocks.fingerprint,
            policy_version=LAND_USE_POLICY,
        )
        for block in source_blocks
    )
    allocation_fingerprint = _allocation_fingerprint(
        population=population,
        job_target=job_target,
        leisure_target=leisure_target,
        blocks=block_land_use,
        raw_totals=raw_totals,
        multipliers=multipliers,
    )
    certificate = PopulationCapacityCertificate(
        schema_version=ALLOCATION_POLICY,
        target_population=population,
        job_target=job_target,
        worker_share_numerator=31,
        worker_share_denominator=50,
        resident_raw_total_ratio=_fraction_pair(raw_totals[0]),
        home_raw_total_ratio=_fraction_pair(raw_totals[1]),
        job_raw_total_ratio=_fraction_pair(raw_totals[2]),
        leisure_raw_total_ratio=_fraction_pair(raw_totals[3]),
        resident_multiplier_ratio=_fraction_pair(multipliers[0]),
        home_multiplier_ratio=_fraction_pair(multipliers[1]),
        job_multiplier_ratio=_fraction_pair(multipliers[2]),
        leisure_multiplier_ratio=_fraction_pair(multipliers[3]),
        resident_capacity_total=sum(
            block.final_resident_capacity for block in block_land_use
        ),
        home_capacity_total=sum(block.final_home_capacity for block in block_land_use),
        job_capacity_total=sum(block.final_job_capacity for block in block_land_use),
        leisure_capacity_total=sum(
            block.final_leisure_capacity for block in block_land_use
        ),
        taz_count=taz_count,
        allocated_block_count=len(block_land_use),
        capacity_cap_applied=False,
        silent_cap_count=0,
        dropped_capacity_count=0,
        allocation_fingerprint=allocation_fingerprint,
        source_network_fingerprint=network.fingerprint,
        source_blocks_fingerprint=blocks.fingerprint,
        source_compiled_fingerprint=compiled.fingerprint,
        land_use_policy_version=LAND_USE_POLICY,
        allocation_policy_version=ALLOCATION_POLICY,
    )

    land_use_by_id = {block.block_id: block for block in block_land_use}
    tazs: list[V2Taz] = []
    for taz_id, member_ids in partitions:
        members = tuple(
            sorted(
                (land_use_by_id[block_id] for block_id in member_ids),
                key=lambda block: (block.block_semantic_id, block.block_id),
            )
        )
        semantics = tuple(block.block_semantic_id for block in members)
        tazs.append(
            V2Taz(
                taz_id=taz_id,
                semantic_id=_sha256_payload((TAZ_POLICY, taz_id, semantics)),
                block_ids=tuple(block.block_id for block in members),
                block_semantic_ids=semantics,
                frontage_road_ids=tuple(
                    sorted(
                        {
                            road_id
                            for block in members
                            for road_id in block.frontage_road_ids
                        }
                    )
                ),
                access_node_ids=tuple(
                    sorted(
                        {
                            node_id
                            for block in members
                            for node_id in block.access_node_ids
                        }
                    )
                ),
                resident_capacity_total=sum(
                    block.final_resident_capacity for block in members
                ),
                home_capacity_total=sum(block.final_home_capacity for block in members),
                job_capacity_total=sum(block.final_job_capacity for block in members),
                leisure_capacity_total=sum(
                    block.final_leisure_capacity for block in members
                ),
            )
        )
    taz_tuple = tuple(tazs)
    block_taz_by_id = tuple(
        sorted((block.block_id, block.taz_id) for block in block_land_use)
    )
    node_owner_by_id, node_conflicts, _ = _node_taz_ownership_from_index(
        block_rows=tuple(
            (block.block_semantic_id, block.taz_id, block.access_node_ids)
            for block in block_land_use
        )
    )
    assignment_fingerprint = _sha256_payload(
        (
            TAZ_POLICY,
            taz_count,
            blocks.fingerprint,
            allocation_fingerprint,
            tuple(_record_payload(taz) for taz in taz_tuple),
            block_taz_by_id,
            node_owner_by_id,
            node_conflicts,
        )
    )
    taz_catalog = V2TazCatalog(
        schema_version=TAZ_POLICY,
        tazs=taz_tuple,
        block_taz_by_id=block_taz_by_id,
        node_owner_by_id=node_owner_by_id,
        node_conflicts=node_conflicts,
        target_taz_count=taz_count,
        source_blocks_fingerprint=blocks.fingerprint,
        source_allocation_fingerprint=allocation_fingerprint,
        assignment_fingerprint=assignment_fingerprint,
    )
    poi_rows = _aggregate_poi_rows(
        block_rows=tuple(
            (
                block.block_id,
                block.block_semantic_id,
                block.interior_witness_mm,
                block.primary_access_node_id,
                block.taz_id,
                block.final_home_capacity,
                block.final_job_capacity,
                block.final_leisure_capacity,
            )
            for block in block_land_use
        ),
        source_allocation_fingerprint=allocation_fingerprint,
    )
    poi_catalog = V2PoiCatalog(
        schema_version=POI_POLICY,
        pois=poi_rows,
        home_capacity_total=certificate.home_capacity_total,
        workplace_capacity_total=certificate.job_capacity_total,
        leisure_capacity_total=certificate.leisure_capacity_total,
        source_allocation_fingerprint=allocation_fingerprint,
        source_taz_fingerprint=taz_catalog.fingerprint,
    )
    fingerprints = _origin_fingerprints(
        scale_spec=scale_spec,
        style_id=style_id,
        seed=seed,
        network=network,
        blocks=blocks,
        compiled=compiled,
        copied=copied,
        block_land_use=block_land_use,
        capacity_certificate=certificate,
        taz_catalog=taz_catalog,
        poi_catalog=poi_catalog,
    )
    routing_key = RoutingStaticDependencyKey(
        schema_version=ROUTING_KEY_SCHEMA,
        routing_static_fingerprint=fingerprints.routing_static,
        routing_policy_version=ROUTING_POLICY,
        access_direction_policy_version=ACCESS_DIRECTION_POLICY,
        closure_capability_policy_version=CLOSURE_CAPABILITY_POLICY,
        source_csr_fingerprint=copied.road_csr.content_fingerprint,
    )
    return ScalableStaticAuthority(
        schema_version=STATIC_AUTHORITY_SCHEMA,
        scale_spec=scale_spec,
        style_id=style_id,
        seed=seed,
        extent_mm=extent_mm,
        width_m=network.width_m,
        height_m=network.height_m,
        centers_mm=network.centers,
        source_network_schema_version=network.schema_version,
        source_blocks_schema_version=blocks.schema_version,
        source_compiled_schema_version=compiled.schema_version,
        numeric_profile_policy_version=compiled.numeric_profile_policy_version,
        source_network_fingerprint=network.fingerprint,
        source_blocks_fingerprint=blocks.fingerprint,
        source_compiled_fingerprint=compiled.fingerprint,
        source_terrain_fingerprint=network.terrain.fingerprint,
        source_scale_fingerprint=network.scale_fingerprint,
        source_style_fingerprint=network.style_fingerprint,
        source_geometry_fingerprint=compiled.road_geometry_fingerprint,
        source_section_fingerprint=compiled.road_section_fingerprint,
        source_node_interface_fingerprint=compiled.node_interface_fingerprint,
        source_turn_authority_fingerprint=compiled.turn_authority_fingerprint,
        numeric_profiles=copied.numeric_profiles,
        road_crosswalk=copied.road_crosswalk,
        structure_group_crosswalk=copied.structure_group_crosswalk,
        failure_group_crosswalk=copied.failure_group_crosswalk,
        block_access_index=copied.block_access_index,
        block_land_use=block_land_use,
        capacity_certificate=certificate,
        taz_catalog=taz_catalog,
        poi_catalog=poi_catalog,
        fingerprints=fingerprints,
        road_csr=copied.road_csr,
        routing_dependency_key=routing_key,
    )


def _require_current_immutable_csr_content(csr: ImmutableRoadNetworkCSR) -> None:
    if type(csr) is not ImmutableRoadNetworkCSR:
        raise TypeError("road CSR must be an exact ImmutableRoadNetworkCSR")
    for name, expected_type in (
        ("nodes", ImmutableNode),
        ("links", ImmutableRoadLink),
        ("turns", ImmutableTurnMovement),
        ("bridge_crossings", ImmutableBridgeCrossing),
    ):
        rows = getattr(csr, name)
        if type(rows) is not tuple or any(type(row) is not expected_type for row in rows):
            raise TypeError(f"{name} must contain exact immutable rows")
        for row in rows:
            replace(row)

    node_index = {node.node_id: index for index, node in enumerate(csr.nodes)}
    link_index = {link.link_id: index for index, link in enumerate(csr.links)}
    if len(node_index) != len(csr.nodes) or len(link_index) != len(csr.links):
        raise ValueError("immutable CSR IDs must remain unique")
    if any(
        link.src_node_id not in node_index or link.dst_node_id not in node_index
        for link in csr.links
    ):
        raise ValueError("immutable CSR link references an unknown node")
    expected_pairs: dict[tuple[int, int], int] = {}
    for turn_index, turn in enumerate(csr.turns):
        if turn.from_link_id not in link_index or turn.to_link_id not in link_index:
            raise ValueError("immutable CSR turn references an unknown link")
        pair = (turn.from_link_id, turn.to_link_id)
        if turn.turn_type is not TurnType.U_TURN_FORBIDDEN:
            if pair in expected_pairs:
                raise ValueError("immutable CSR legal turn pairs must remain unique")
            expected_pairs[pair] = turn_index
    if any(
        link_id not in link_index
        for bridge in csr.bridge_crossings
        for link_id in bridge.link_ids
    ):
        raise ValueError("immutable bridge references an unknown link")
    for supplied, expected in (
        (csr.node_id_to_index, node_index),
        (csr.link_id_to_index, link_index),
        (csr.turn_pair_to_index, expected_pairs),
    ):
        if type(supplied) is not MappingProxyType or dict(supplied) != expected:
            raise ValueError("immutable CSR mapping differs from its rows")

    src = tuple(node_index[link.src_node_id] for link in csr.links)
    dst = tuple(node_index[link.dst_node_id] for link in csr.links)
    outgoing_indptr, outgoing_indices = _link_csr_arrays(len(csr.nodes), src)
    incoming_indptr, incoming_indices = _link_csr_arrays(len(csr.nodes), dst)
    expected_arrays = {
        "node_ids": np.asarray([node.node_id for node in csr.nodes], dtype=np.int32),
        "link_ids": np.asarray([link.link_id for link in csr.links], dtype=np.int32),
        "link_src_node_index": np.asarray(src, dtype=np.int32),
        "link_dst_node_index": np.asarray(dst, dtype=np.int32),
        "outgoing_indptr": outgoing_indptr,
        "outgoing_link_indices": outgoing_indices,
        "incoming_indptr": incoming_indptr,
        "incoming_link_indices": incoming_indices,
        "turn_from_link_index": np.asarray(
            [link_index[turn.from_link_id] for turn in csr.turns],
            dtype=np.int32,
        ),
        "turn_to_link_index": np.asarray(
            [link_index[turn.to_link_id] for turn in csr.turns],
            dtype=np.int32,
        ),
        "turn_base_priority": np.asarray(
            [turn.base_priority for turn in csr.turns],
            dtype=np.float32,
        ),
        "turn_is_forbidden": np.asarray(
            [turn.turn_type is TurnType.U_TURN_FORBIDDEN for turn in csr.turns],
            dtype=np.bool_,
        ),
    }
    array_payloads: list[tuple[object, ...]] = []
    for name, expected in expected_arrays.items():
        supplied = getattr(csr, name)
        if (
            type(supplied) is not np.ndarray
            or supplied.dtype != expected.dtype
            or supplied.shape != expected.shape
            or not supplied.flags.c_contiguous
            or supplied.flags.writeable
            or not np.array_equal(supplied, expected)
        ):
            raise ValueError(f"{name} differs from immutable CSR rows")
        terminal: object = supplied
        while type(terminal) is np.ndarray:
            terminal = terminal.base
        if type(terminal) is not bytes:
            raise ValueError(f"{name} is not irreversibly bytes-backed")
        array_payloads.append(_array_payload(name, supplied))

    topology_key = _behavior_free_tuple(csr.topology_cache_key, "topology_cache_key")
    payload = (
        IMMUTABLE_CSR_SCHEMA,
        tuple(
            (node.node_id, node.kind, node.x, node.y, node.zone_id, node.signal_group_id)
            for node in csr.nodes
        ),
        tuple(
            (
                link.link_id,
                link.src_node_id,
                link.dst_node_id,
                link.road_class,
                link.length_m,
                link.free_flow_speed_mps,
                link.capacity_veh_per_tick,
                link.lanes,
                link.bridge_group_id,
                link.is_blockable,
                link.physical_road_id,
            )
            for link in csr.links
        ),
        tuple(
            (
                turn.from_link_id,
                turn.to_link_id,
                turn.turn_type,
                turn.base_priority,
                turn.signal_phase_id,
            )
            for turn in csr.turns
        ),
        tuple(
            (
                bridge.bridge_group_id,
                bridge.link_ids,
                bridge.barrier_id,
                bridge.crossing_name,
                bridge.bottleneck_rank_hint,
            )
            for bridge in csr.bridge_crossings
        ),
        tuple(sorted(node_index.items())),
        tuple(sorted(link_index.items())),
        tuple(sorted(expected_pairs.items())),
        tuple(array_payloads),
        topology_key,
    )
    expected_fingerprint = _sha256_payload(payload)
    if _digest_text(csr.content_fingerprint, "content_fingerprint") != expected_fingerprint:
        raise ValueError("immutable CSR current-content fingerprint mismatch")


def _require_current_static_authority_content(
    authority: ScalableStaticAuthority,
) -> None:
    for block in authority.block_land_use:
        replace(block)
    replace(authority.capacity_certificate)
    for taz in authority.taz_catalog.tazs:
        replace(taz)
    replace(authority.taz_catalog)
    for poi in authority.poi_catalog.pois:
        replace(poi)
    replace(authority.poi_catalog)
    replace(authority.fingerprints)
    replace(authority.routing_dependency_key)
    _require_current_immutable_csr_content(authority.road_csr)
    expected_outer = _sha256_payload(_static_authority_payload(authority))
    if _digest_text(authority.fingerprint, "fingerprint") != expected_outer:
        raise ValueError("static authority current-content fingerprint mismatch")


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
    authority = _derive_scalable_static_authority(
        scale_spec=normalized_scale,
        style_id=style_id,
        seed=seed,
        network=network,
        blocks=blocks,
        compiled=compiled,
    )
    from metroflow.city.scalable_validation_receipts import (
        ACCESS_DIRECTION_POLICY,
        ALLOCATION_POLICY,
        CLOSURE_CAPABILITY_POLICY,
        FINGERPRINT_SET_SCHEMA,
        IMMUTABLE_CSR_SCHEMA,
        LAND_USE_POLICY,
        POI_POLICY,
        ROUTING_POLICY,
        TAZ_POLICY,
        _BLOCKS_SEAL_SCHEMA,
        _COMPILED_AGGREGATE_SEAL_SCHEMA,
        _NETWORK_SEAL_SCHEMA,
        _STATIC_CONTENT_SEAL_SCHEMAS,
        _STATIC_RECEIPT_POLICY_VERSION,
        _TASK5_INVOCATION_SEAL_SCHEMA,
        _TASK5_SNAPSHOT_POLICY_VERSION,
        _ValidationReceipt,
        _register_validation_receipt,
    )

    _register_validation_receipt(
        _ValidationReceipt(
            stage_name="static",
            schema_version=authority.schema_version,
            fingerprint=authority.fingerprint,
            policy_versions=(
                ("access_direction_policy", ACCESS_DIRECTION_POLICY),
                ("allocation_policy", ALLOCATION_POLICY),
                ("closure_capability_policy", CLOSURE_CAPABILITY_POLICY),
                ("fingerprint_set_schema", FINGERPRINT_SET_SCHEMA),
                ("immutable_csr_schema", IMMUTABLE_CSR_SCHEMA),
                ("land_use_policy", LAND_USE_POLICY),
                ("poi_policy", POI_POLICY),
                ("receipt_policy", _STATIC_RECEIPT_POLICY_VERSION),
                ("routing_policy", ROUTING_POLICY),
                ("snapshot_policy", _TASK5_SNAPSHOT_POLICY_VERSION),
                ("taz_policy", TAZ_POLICY),
            ),
            source_seal_schemas=(
                ("blocks.current", _BLOCKS_SEAL_SCHEMA),
                ("compiled.aggregate", _COMPILED_AGGREGATE_SEAL_SCHEMA),
                ("invocation.current", _TASK5_INVOCATION_SEAL_SCHEMA),
                ("network.current", _NETWORK_SEAL_SCHEMA),
            ),
            content_seal_schemas=_STATIC_CONTENT_SEAL_SCHEMAS,
        )
    )
    return authority


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
    normalized_scale = _admit_scalable_sources(
        scale_spec,
        style_id,
        seed,
        network,
        blocks,
        compiled,
    )
    expected = _derive_scalable_static_authority(
        scale_spec=normalized_scale,
        style_id=style_id,
        seed=seed,
        network=network,
        blocks=blocks,
        compiled=compiled,
    )
    _require_current_static_authority_content(authority)
    if _static_authority_payload(authority) != _static_authority_payload(expected):
        raise ValueError("static authority differs from the admitted source derivation")


def _capture_verified_task5_source_snapshot_from_receipt(
    scale_spec: CityScaleSpec,
    style_id: str,
    seed: int,
    network: ScalableStreetNetwork,
    blocks: ScalableBlockAuthority,
    compiled: ScalableCompiledTopology,
    *,
    registered_compiled_receipt: object | None = None,
) -> tuple[object, object, object, object]:
    from metroflow.city.scalable_topology_adapter import (
        _TURN_POLICY,
        _require_scalable_source_cross_binding,
    )
    from metroflow.city.scalable_validation_receipts import (
        _BLOCKS_RECEIPT_POLICY_VERSION,
        _BLOCKS_SEAL_SCHEMA,
        _COMPILED_CONTENT_SEAL_SCHEMAS,
        _COMPILED_RECEIPT_POLICY_VERSION,
        _NETWORK_RECEIPT_POLICY_VERSION,
        _NETWORK_SEAL_SCHEMA,
        _ValidationReceipt,
        _VerifiedTask5SourceSnapshot,
    )

    _require_scalable_source_cross_binding(
        network=network,
        blocks=blocks,
    )

    net_rcpt = _ValidationReceipt(
        stage_name="network",
        schema_version=network.schema_version,
        fingerprint=network.fingerprint,
        policy_versions=(("receipt_policy", _NETWORK_RECEIPT_POLICY_VERSION),),
        source_seal_schemas=(),
        content_seal_schemas=(("network.current", _NETWORK_SEAL_SCHEMA),),
    )
    blk_rcpt = _ValidationReceipt(
        stage_name="blocks",
        schema_version=blocks.schema_version,
        fingerprint=blocks.fingerprint,
        policy_versions=(
            ("embedding_policy", blocks.embedding_policy),
            ("receipt_policy", _BLOCKS_RECEIPT_POLICY_VERSION),
            ("subdivision_schema", blocks.subdivision_schema),
            ("tile_policy", blocks.tile_policy),
        ),
        source_seal_schemas=(),
        content_seal_schemas=(("blocks.current", _BLOCKS_SEAL_SCHEMA),),
    )
    if registered_compiled_receipt is not None:
        if type(registered_compiled_receipt) is not _ValidationReceipt:
            raise TypeError("registered_compiled_receipt must be a _ValidationReceipt")
        cmp_rcpt = registered_compiled_receipt
    else:
        cmp_rcpt = _ValidationReceipt(
            stage_name="compiled",
            schema_version=compiled.schema_version,
            fingerprint=compiled.fingerprint,
            policy_versions=(
                (
                    "numeric_profile_policy",
                    compiled.numeric_profile_policy_version,
                ),
                ("receipt_policy", _COMPILED_RECEIPT_POLICY_VERSION),
                ("turn_policy", _TURN_POLICY),
            ),
            source_seal_schemas=(
                ("blocks.current", _BLOCKS_SEAL_SCHEMA),
                ("network.current", _NETWORK_SEAL_SCHEMA),
            ),
            content_seal_schemas=_COMPILED_CONTENT_SEAL_SCHEMAS,
        )
    snapshot = _VerifiedTask5SourceSnapshot(
        network_fingerprint=network.fingerprint,
        blocks_fingerprint=blocks.fingerprint,
        compiled_fingerprint=compiled.fingerprint,
        network_receipt=net_rcpt,  # type: ignore[arg-type]
        blocks_receipt=blk_rcpt,  # type: ignore[arg-type]
        compiled_receipt=cmp_rcpt,  # type: ignore[arg-type]
    )
    return snapshot, net_rcpt, blk_rcpt, cmp_rcpt


def _capture_stable_static_validation_receipt(
    authority: ScalableStaticAuthority,
    *,
    source_snapshot: object,
    compiled: ScalableCompiledTopology,
) -> object:
    from metroflow.city.scalable_validation_receipts import (
        _BLOCKS_SEAL_SCHEMA,
        _COMPILED_AGGREGATE_SEAL_SCHEMA,
        _NETWORK_SEAL_SCHEMA,
        _STATIC_CONTENT_SEAL_SCHEMAS,
        _STATIC_RECEIPT_POLICY_VERSION,
        _TASK5_INVOCATION_SEAL_SCHEMA,
        _TASK5_SNAPSHOT_POLICY_VERSION,
        _ValidationReceipt,
    )

    return _ValidationReceipt(
        stage_name="static",
        schema_version=authority.schema_version,
        fingerprint=authority.fingerprint,
        policy_versions=(
            ("access_direction_policy", ACCESS_DIRECTION_POLICY),
            ("allocation_policy", ALLOCATION_POLICY),
            ("closure_capability_policy", CLOSURE_CAPABILITY_POLICY),
            ("fingerprint_set_schema", FINGERPRINT_SET_SCHEMA),
            ("immutable_csr_schema", IMMUTABLE_CSR_SCHEMA),
            ("land_use_policy", LAND_USE_POLICY),
            ("poi_policy", POI_POLICY),
            ("receipt_policy", _STATIC_RECEIPT_POLICY_VERSION),
            ("routing_policy", ROUTING_POLICY),
            ("snapshot_policy", _TASK5_SNAPSHOT_POLICY_VERSION),
            ("taz_policy", TAZ_POLICY),
        ),
        source_seal_schemas=(
            ("blocks.current", _BLOCKS_SEAL_SCHEMA),
            ("compiled.aggregate", _COMPILED_AGGREGATE_SEAL_SCHEMA),
            ("invocation.current", _TASK5_INVOCATION_SEAL_SCHEMA),
            ("network.current", _NETWORK_SEAL_SCHEMA),
        ),
        content_seal_schemas=_STATIC_CONTENT_SEAL_SCHEMAS,
    )
