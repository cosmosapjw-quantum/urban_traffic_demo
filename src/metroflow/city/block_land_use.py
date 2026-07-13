"""Block-authoritative land use, capacities, and POI placement."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import string
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from .graph import RoadClass
from .planar_blocks import CityBlock, CityBlockCatalog
from .realistic_local_fabric import RealisticStreetNetwork
from .terrain_field import TerrainField
from .urban_form import UrbanFormField
__all__ = [
    "BlockLandUse",
    "BlockLandUseType",
    "BlockPOI",
    "BlockPOIType",
    "LandUseCatalog",
    "build_block_land_use_catalog",
]

PointM = tuple[float, float]


class StrEnum(str, Enum):
    """Small local string enum base."""


class BlockLandUseType(StrEnum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    MIXED_USE = "mixed_use"
    INDUSTRIAL = "industrial"
    OPEN_SPACE = "open_space"


class BlockPOIType(StrEnum):
    HOME = "home"
    WORKPLACE = "workplace"
    LEISURE = "leisure"


@dataclass(frozen=True, slots=True)
class BlockLandUse:
    block_id: int
    land_use_type: BlockLandUseType | str
    polygon_m: tuple[PointM, ...]
    centroid_m: PointM
    area_m2: float
    frontage_street_ids: tuple[int, ...]
    access_node_id: int | None
    development_intensity: float
    centrality_score: float
    arterial_exposure: float
    slope_rise_per_m: float
    population_capacity: int
    job_capacity: int
    leisure_capacity: int

    def __post_init__(self) -> None:
        block_id = int(self.block_id)
        land_use_type = BlockLandUseType(self.land_use_type)
        polygon = tuple((float(x), float(y)) for x, y in self.polygon_m)
        centroid = (float(self.centroid_m[0]), float(self.centroid_m[1]))
        area_m2 = float(self.area_m2)
        frontage = tuple(sorted({int(value) for value in self.frontage_street_ids}))
        access_node_id = (
            None if self.access_node_id is None else int(self.access_node_id)
        )
        features = (
            float(self.development_intensity),
            float(self.centrality_score),
            float(self.arterial_exposure),
        )
        slope = float(self.slope_rise_per_m)
        capacities = (
            int(self.population_capacity),
            int(self.job_capacity),
            int(self.leisure_capacity),
        )
        if block_id < 0:
            raise ValueError("block_id must be >= 0")
        if len(polygon) < 4 or polygon[0] != polygon[-1]:
            raise ValueError("land-use polygon must be a closed block ring")
        if not all(math.isfinite(value) for point in polygon for value in point):
            raise ValueError("land-use polygon coordinates must be finite")
        if not all(math.isfinite(value) for value in (*centroid, area_m2, slope)):
            raise ValueError("land-use geometry and slope must be finite")
        if area_m2 <= 0.0 or slope < 0.0:
            raise ValueError("land-use area must be > 0 and slope must be >= 0")
        if any(not 0.0 <= value <= 1.0 for value in features):
            raise ValueError("land-use scores must be in [0, 1]")
        if not frontage or any(value < 0 for value in frontage):
            raise ValueError("land-use block requires street frontage")
        if any(value < 0 for value in capacities):
            raise ValueError("land-use capacities must be >= 0")
        validated_block = CityBlock(
            block_id=block_id,
            polygon_m=polygon,
            area_m2=area_m2,
            perimeter_m=sum(
                math.dist(left, right)
                for left, right in zip(polygon, polygon[1:])
            ),
            frontage_street_ids=frontage,
        )
        if not all(
            math.isclose(
                supplied,
                computed,
                rel_tol=1e-9,
                abs_tol=1e-6,
            )
            for supplied, computed in zip(centroid, validated_block.centroid_m)
        ):
            raise ValueError("land-use centroid does not match block polygon")
        if land_use_type is BlockLandUseType.OPEN_SPACE:
            if access_node_id is not None or any(capacities):
                raise ValueError("open-space blocks cannot have access or capacity")
        else:
            if access_node_id is None:
                raise ValueError("developed blocks require access and capacity")
            expected_capacities = _capacities(
                area_m2=area_m2,
                development_intensity=features[0],
                land_use_type=land_use_type,
            )
            if capacities != expected_capacities:
                raise ValueError("land-use capacities do not match area-based rates")
        object.__setattr__(self, "block_id", block_id)
        object.__setattr__(self, "land_use_type", land_use_type)
        object.__setattr__(self, "polygon_m", polygon)
        object.__setattr__(self, "centroid_m", centroid)
        object.__setattr__(self, "area_m2", area_m2)
        object.__setattr__(self, "frontage_street_ids", frontage)
        object.__setattr__(self, "access_node_id", access_node_id)
        object.__setattr__(self, "development_intensity", features[0])
        object.__setattr__(self, "centrality_score", features[1])
        object.__setattr__(self, "arterial_exposure", features[2])
        object.__setattr__(self, "slope_rise_per_m", slope)
        object.__setattr__(self, "population_capacity", capacities[0])
        object.__setattr__(self, "job_capacity", capacities[1])
        object.__setattr__(self, "leisure_capacity", capacities[2])

    @property
    def is_developed(self) -> bool:
        return self.land_use_type is not BlockLandUseType.OPEN_SPACE


@dataclass(frozen=True, slots=True)
class BlockPOI:
    poi_id: int
    block_id: int
    poi_type: BlockPOIType | str
    x_m: float
    y_m: float
    access_node_id: int
    capacity_hint: int

    def __post_init__(self) -> None:
        poi_id = int(self.poi_id)
        block_id = int(self.block_id)
        poi_type = BlockPOIType(self.poi_type)
        x_m = float(self.x_m)
        y_m = float(self.y_m)
        access_node_id = int(self.access_node_id)
        capacity_hint = int(self.capacity_hint)
        if poi_id < 0 or block_id < 0 or access_node_id < 0:
            raise ValueError("POI and access identifiers must be >= 0")
        if not math.isfinite(x_m) or not math.isfinite(y_m):
            raise ValueError("POI coordinates must be finite")
        if capacity_hint <= 0:
            raise ValueError("POI capacity_hint must be > 0")
        object.__setattr__(self, "poi_id", poi_id)
        object.__setattr__(self, "block_id", block_id)
        object.__setattr__(self, "poi_type", poi_type)
        object.__setattr__(self, "x_m", x_m)
        object.__setattr__(self, "y_m", y_m)
        object.__setattr__(self, "access_node_id", access_node_id)
        object.__setattr__(self, "capacity_hint", capacity_hint)


@dataclass(frozen=True, slots=True)
class LandUseCatalog:
    terrain_fingerprint: str
    urban_form_fingerprint: str
    street_network_fingerprint: str
    block_catalog_fingerprint: str
    blocks: tuple[BlockLandUse, ...]
    pois: tuple[BlockPOI, ...]
    developed_block_count: int
    industrial_residential_shared_edge_count: int
    essential_access_ratio: float
    median_developed_density_per_hectare: float
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        source_fingerprints = (
            str(self.terrain_fingerprint),
            str(self.urban_form_fingerprint),
            str(self.street_network_fingerprint),
            str(self.block_catalog_fingerprint),
        )
        if any(
            len(value) != 64 or any(character not in string.hexdigits for character in value)
            for value in source_fingerprints
        ):
            raise ValueError("land-use source fingerprints must be SHA-256 digests")
        blocks = tuple(sorted(self.blocks, key=lambda item: item.block_id))
        pois = tuple(sorted(self.pois, key=lambda item: item.poi_id))
        if not blocks or tuple(item.block_id for item in blocks) != tuple(
            range(len(blocks))
        ):
            raise ValueError("land-use blocks must be non-empty with dense IDs")
        if tuple(item.poi_id for item in pois) != tuple(range(len(pois))):
            raise ValueError("land-use POIs must have dense zero-based IDs")
        developed = tuple(item for item in blocks if item.is_developed)
        if int(self.developed_block_count) != len(developed) or not developed:
            raise ValueError("developed_block_count does not match land-use blocks")
        block_by_id = {item.block_id: item for item in blocks}
        poi_types_by_block: dict[int, set[BlockPOIType]] = {
            item.block_id: set() for item in blocks
        }
        poi_capacities_by_block: dict[int, dict[BlockPOIType, int]] = {
            item.block_id: {} for item in blocks
        }
        for poi in pois:
            block = block_by_id.get(poi.block_id)
            if block is None or not block.is_developed:
                raise ValueError("POI references a missing or open-space block")
            if poi.access_node_id != block.access_node_id:
                raise ValueError("POI access node does not match its block")
            if not math.isclose(poi.x_m, block.centroid_m[0], abs_tol=1e-9) or not math.isclose(
                poi.y_m,
                block.centroid_m[1],
                abs_tol=1e-9,
            ):
                raise ValueError("POI coordinates do not match block centroid")
            if poi.poi_type in poi_types_by_block[poi.block_id]:
                raise ValueError("land-use block cannot repeat a POI type")
            poi_types_by_block[poi.block_id].add(poi.poi_type)
            poi_capacities_by_block[poi.block_id][poi.poi_type] = poi.capacity_hint
        if {poi.poi_type for poi in pois} != set(BlockPOIType):
            raise ValueError("land-use catalog requires home, workplace, and leisure POIs")
        for block in developed:
            expected_mix = dict(_poi_mix(block))
            if poi_types_by_block[block.block_id] != set(expected_mix):
                raise ValueError("developed block POI mix does not match land use")
            if poi_capacities_by_block[block.block_id] != expected_mix:
                raise ValueError("developed block POI capacities are inconsistent")
        residential = tuple(
            item
            for item in developed
            if item.land_use_type is BlockLandUseType.RESIDENTIAL
        )
        accessible_residential = sum(
            {BlockPOIType.HOME, BlockPOIType.LEISURE}
            <= poi_types_by_block[item.block_id]
            for item in residential
        )
        computed_access_ratio = accessible_residential / max(len(residential), 1)
        essential_ratio = float(self.essential_access_ratio)
        if not math.isclose(essential_ratio, computed_access_ratio, abs_tol=1e-12):
            raise ValueError("essential_access_ratio does not match residential POIs")
        adjacency = _block_adjacency(blocks)
        computed_shared_count = _industrial_residential_shared_edge_count(
            land_use_by_block_id={
                item.block_id: item.land_use_type for item in blocks
            },
            adjacency=adjacency,
        )
        if int(self.industrial_residential_shared_edge_count) != computed_shared_count:
            raise ValueError("industrial-residential adjacency metric is inconsistent")
        if computed_shared_count != 0:
            raise ValueError("industrial and residential blocks cannot share an edge")
        densities = sorted(
            (
                item.population_capacity
                + item.job_capacity
                + item.leisure_capacity
            )
            / (item.area_m2 / 10_000.0)
            for item in developed
        )
        median_density = float(statistics.median(densities))
        if not math.isclose(
            float(self.median_developed_density_per_hectare),
            median_density,
            abs_tol=1e-9,
        ):
            raise ValueError("median developed density does not match block capacities")
        object.__setattr__(self, "terrain_fingerprint", source_fingerprints[0])
        object.__setattr__(self, "urban_form_fingerprint", source_fingerprints[1])
        object.__setattr__(self, "street_network_fingerprint", source_fingerprints[2])
        object.__setattr__(self, "block_catalog_fingerprint", source_fingerprints[3])
        object.__setattr__(self, "blocks", blocks)
        object.__setattr__(self, "pois", pois)
        object.__setattr__(self, "developed_block_count", len(developed))
        object.__setattr__(
            self,
            "industrial_residential_shared_edge_count",
            computed_shared_count,
        )
        object.__setattr__(self, "essential_access_ratio", essential_ratio)
        object.__setattr__(
            self,
            "median_developed_density_per_hectare",
            median_density,
        )
        object.__setattr__(self, "fingerprint", _catalog_fingerprint(self))


@dataclass(frozen=True, slots=True)
class _BlockFeature:
    block: CityBlock
    development_intensity: float
    centrality_score: float
    arterial_exposure: float
    slope_rise_per_m: float
    buildable: bool
    access_node_id: int


def build_block_land_use_catalog(
    *,
    terrain: TerrainField,
    urban_form: UrbanFormField,
    street_network: RealisticStreetNetwork,
    block_catalog: CityBlockCatalog,
) -> LandUseCatalog:
    """Build functional block assignments from accepted city-stage authorities."""

    _validate_source_chain(
        terrain=terrain,
        urban_form=urban_form,
        street_network=street_network,
        block_catalog=block_catalog,
    )
    features = _build_features(
        terrain=terrain,
        urban_form=urban_form,
        street_network=street_network,
        block_catalog=block_catalog,
    )
    adjacency = _block_adjacency(tuple(feature.block for feature in features))
    land_use_by_block_id = _assign_land_use(features=features, adjacency=adjacency)
    blocks = tuple(
        _build_block_assignment(
            feature=feature,
            land_use_type=land_use_by_block_id[feature.block.block_id],
        )
        for feature in features
    )
    pois = _build_pois(blocks)
    shared_edge_count = _industrial_residential_shared_edge_count(
        land_use_by_block_id=land_use_by_block_id,
        adjacency=adjacency,
    )
    residential_ids = {
        item.block_id
        for item in blocks
        if item.land_use_type is BlockLandUseType.RESIDENTIAL
    }
    poi_types_by_block: dict[int, set[BlockPOIType]] = {
        block_id: set() for block_id in residential_ids
    }
    for poi in pois:
        if poi.block_id in poi_types_by_block:
            poi_types_by_block[poi.block_id].add(poi.poi_type)
    essential_ratio = sum(
        {BlockPOIType.HOME, BlockPOIType.LEISURE} <= poi_types
        for poi_types in poi_types_by_block.values()
    ) / max(len(residential_ids), 1)
    developed = tuple(item for item in blocks if item.is_developed)
    densities = tuple(
        (
            item.population_capacity + item.job_capacity + item.leisure_capacity
        )
        / (item.area_m2 / 10_000.0)
        for item in developed
    )
    return LandUseCatalog(
        terrain_fingerprint=terrain.fingerprint,
        urban_form_fingerprint=urban_form.fingerprint,
        street_network_fingerprint=street_network.fingerprint,
        block_catalog_fingerprint=block_catalog.fingerprint,
        blocks=blocks,
        pois=pois,
        developed_block_count=len(developed),
        industrial_residential_shared_edge_count=shared_edge_count,
        essential_access_ratio=essential_ratio,
        median_developed_density_per_hectare=float(statistics.median(densities)),
    )


def _validate_source_chain(
    *,
    terrain: TerrainField,
    urban_form: UrbanFormField,
    street_network: RealisticStreetNetwork,
    block_catalog: CityBlockCatalog,
) -> None:
    if urban_form.terrain_fingerprint != terrain.fingerprint:
        raise ValueError("urban form does not match terrain")
    if street_network.terrain_fingerprint != terrain.fingerprint:
        raise ValueError("street network does not match terrain")
    if street_network.urban_form_fingerprint != urban_form.fingerprint:
        raise ValueError("street network does not match urban form")
    if block_catalog.street_network_fingerprint != street_network.fingerprint:
        raise ValueError("block catalog does not match street network")
    if not (terrain.style_id == urban_form.style_id == street_network.style_id):
        raise ValueError("city-stage morphology styles do not match")


def _build_features(
    *,
    terrain: TerrainField,
    urban_form: UrbanFormField,
    street_network: RealisticStreetNetwork,
    block_catalog: CityBlockCatalog,
) -> tuple[_BlockFeature, ...]:
    node_id_by_point = {(node.x, node.y): node.node_id for node in block_catalog.nodes}
    street_by_id = {street.street_id: street for street in street_network.streets}
    features: list[_BlockFeature] = []
    for block in block_catalog.blocks:
        row, column = _terrain_index(terrain, block.centroid_m)
        intensity = float(urban_form.development_intensity[row, column])
        slope = float(terrain.slope_rise_per_m[row, column])
        buildable = bool(terrain.buildable_mask[row, column]) and intensity >= 0.05
        centrality = max(
            center.weight
            * math.exp(
                -math.dist(block.centroid_m, (center.x_m, center.y_m))
                / (0.28 * max(terrain.width_m, terrain.height_m))
            )
            for center in urban_form.centers
        )
        centrality = min(max(float(centrality), 0.0), 1.0)
        exposure = max(
            _road_exposure(street_by_id[street_id].road_class)
            for street_id in block.frontage_street_ids
        )
        boundary_node_ids = tuple(
            node_id_by_point[point] for point in block.polygon_m[:-1]
        )
        access_node_id = min(
            boundary_node_ids,
            key=lambda node_id: (
                math.dist(
                    block.centroid_m,
                    (
                        block_catalog.nodes[node_id].x,
                        block_catalog.nodes[node_id].y,
                    ),
                ),
                node_id,
            ),
        )
        features.append(
            _BlockFeature(
                block=block,
                development_intensity=intensity,
                centrality_score=centrality,
                arterial_exposure=exposure,
                slope_rise_per_m=slope,
                buildable=buildable,
                access_node_id=access_node_id,
            )
        )
    return tuple(features)


def _assign_land_use(
    *,
    features: tuple[_BlockFeature, ...],
    adjacency: dict[int, set[int]],
) -> dict[int, BlockLandUseType]:
    assignments = {
        feature.block.block_id: BlockLandUseType.OPEN_SPACE for feature in features
    }
    developed = tuple(feature for feature in features if feature.buildable)
    if len(developed) < 4:
        raise ValueError("block land use requires at least four developable blocks")
    commercial_count = max(1, int(round(len(developed) * 0.12)))
    industrial_count = max(1, int(round(len(developed) * 0.12)))
    mixed_count = max(1, int(round(len(developed) * 0.23)))
    commercial = _take_ranked(
        developed,
        count=commercial_count,
        excluded=set(),
        score=lambda feature: (
            0.55 * feature.centrality_score
            + 0.30 * feature.development_intensity
            + 0.15 * feature.arterial_exposure
        ),
    )
    industrial = _take_ranked(
        developed,
        count=industrial_count,
        excluded=commercial,
        score=lambda feature: (
            0.50 * feature.arterial_exposure
            + 0.35 * (1.0 - feature.centrality_score)
            + 0.15 * (1.0 - feature.development_intensity)
        ),
    )
    mixed = _take_ranked(
        developed,
        count=mixed_count,
        excluded=commercial | industrial,
        score=lambda feature: (
            0.45 * feature.centrality_score
            + 0.35 * feature.development_intensity
            + 0.20 * feature.arterial_exposure
        ),
    )
    for block_id in commercial:
        assignments[block_id] = BlockLandUseType.COMMERCIAL
    for block_id in industrial:
        assignments[block_id] = BlockLandUseType.INDUSTRIAL
    for block_id in mixed:
        assignments[block_id] = BlockLandUseType.MIXED_USE
    for feature in developed:
        block_id = feature.block.block_id
        if assignments[block_id] is BlockLandUseType.OPEN_SPACE:
            assignments[block_id] = BlockLandUseType.RESIDENTIAL
    for industrial_id in sorted(industrial):
        for neighbor_id in adjacency[industrial_id]:
            if assignments[neighbor_id] is BlockLandUseType.RESIDENTIAL:
                assignments[neighbor_id] = BlockLandUseType.MIXED_USE
    required = {
        BlockLandUseType.RESIDENTIAL,
        BlockLandUseType.COMMERCIAL,
        BlockLandUseType.MIXED_USE,
        BlockLandUseType.INDUSTRIAL,
    }
    if not required <= set(assignments.values()):
        raise ValueError("land-use assignment must retain all functional types")
    return assignments


def _take_ranked(
    features: tuple[_BlockFeature, ...],
    *,
    count: int,
    excluded: set[int],
    score: Callable[[_BlockFeature], float],
) -> set[int]:
    eligible = (
        feature for feature in features if feature.block.block_id not in excluded
    )
    ranked = sorted(
        eligible,
        key=lambda feature: (-score(feature), feature.block.block_id),
    )
    return {feature.block.block_id for feature in ranked[:count]}


def _build_block_assignment(
    *,
    feature: _BlockFeature,
    land_use_type: BlockLandUseType,
) -> BlockLandUse:
    if land_use_type is BlockLandUseType.OPEN_SPACE:
        capacities = (0, 0, 0)
        access_node_id = None
    else:
        capacities = _capacities(
            area_m2=feature.block.area_m2,
            development_intensity=feature.development_intensity,
            land_use_type=land_use_type,
        )
        access_node_id = feature.access_node_id
    return BlockLandUse(
        block_id=feature.block.block_id,
        land_use_type=land_use_type,
        polygon_m=feature.block.polygon_m,
        centroid_m=feature.block.centroid_m,
        area_m2=feature.block.area_m2,
        frontage_street_ids=feature.block.frontage_street_ids,
        access_node_id=access_node_id,
        development_intensity=feature.development_intensity,
        centrality_score=feature.centrality_score,
        arterial_exposure=feature.arterial_exposure,
        slope_rise_per_m=feature.slope_rise_per_m,
        population_capacity=capacities[0],
        job_capacity=capacities[1],
        leisure_capacity=capacities[2],
    )


def _capacities(
    *,
    area_m2: float,
    development_intensity: float,
    land_use_type: BlockLandUseType,
) -> tuple[int, int, int]:
    rates_per_hectare = {
        BlockLandUseType.RESIDENTIAL: (95.0, 0.0, 25.0),
        BlockLandUseType.COMMERCIAL: (0.0, 170.0, 70.0),
        BlockLandUseType.INDUSTRIAL: (0.0, 90.0, 0.0),
        BlockLandUseType.MIXED_USE: (75.0, 95.0, 55.0),
    }[land_use_type]
    scale = 0.45 + 0.55 * float(development_intensity)
    hectares = float(area_m2) / 10_000.0
    values = tuple(
        0 if rate == 0.0 else max(1, int(round(hectares * rate * scale)))
        for rate in rates_per_hectare
    )
    return values[0], values[1], values[2]


def _build_pois(blocks: tuple[BlockLandUse, ...]) -> tuple[BlockPOI, ...]:
    pois: list[BlockPOI] = []
    for block in blocks:
        if not block.is_developed or block.access_node_id is None:
            continue
        for poi_type, capacity_hint in _poi_mix(block):
            pois.append(
                BlockPOI(
                    poi_id=len(pois),
                    block_id=block.block_id,
                    poi_type=poi_type,
                    x_m=block.centroid_m[0],
                    y_m=block.centroid_m[1],
                    access_node_id=block.access_node_id,
                    capacity_hint=capacity_hint,
                )
            )
    return tuple(pois)


def _poi_mix(block: BlockLandUse) -> tuple[tuple[BlockPOIType, int], ...]:
    if block.land_use_type is BlockLandUseType.RESIDENTIAL:
        return (
            (BlockPOIType.HOME, block.population_capacity),
            (BlockPOIType.LEISURE, block.leisure_capacity),
        )
    if block.land_use_type is BlockLandUseType.COMMERCIAL:
        return (
            (BlockPOIType.WORKPLACE, block.job_capacity),
            (BlockPOIType.LEISURE, block.leisure_capacity),
        )
    if block.land_use_type is BlockLandUseType.INDUSTRIAL:
        return ((BlockPOIType.WORKPLACE, block.job_capacity),)
    if block.land_use_type is BlockLandUseType.MIXED_USE:
        return (
            (BlockPOIType.HOME, block.population_capacity),
            (BlockPOIType.WORKPLACE, block.job_capacity),
            (BlockPOIType.LEISURE, block.leisure_capacity),
        )
    return ()


def _block_adjacency(
    blocks: tuple[CityBlock | BlockLandUse, ...],
) -> dict[int, set[int]]:
    edge_to_block_ids: dict[tuple[PointM, PointM], list[int]] = {}
    adjacency = {block.block_id: set() for block in blocks}
    for block in blocks:
        for left, right in zip(block.polygon_m, block.polygon_m[1:]):
            edge = tuple(sorted((left, right)))
            edge_to_block_ids.setdefault(edge, []).append(block.block_id)
    for block_ids in edge_to_block_ids.values():
        unique_ids = sorted(set(block_ids))
        for index, left_id in enumerate(unique_ids):
            for right_id in unique_ids[index + 1 :]:
                adjacency[left_id].add(right_id)
                adjacency[right_id].add(left_id)
    return adjacency


def _industrial_residential_shared_edge_count(
    *,
    land_use_by_block_id: dict[int, BlockLandUseType],
    adjacency: dict[int, set[int]],
) -> int:
    return sum(
        1
        for left_id, neighbors in adjacency.items()
        for right_id in neighbors
        if left_id < right_id
        and {
            land_use_by_block_id[left_id],
            land_use_by_block_id[right_id],
        }
        == {BlockLandUseType.INDUSTRIAL, BlockLandUseType.RESIDENTIAL}
    )


def _terrain_index(terrain: TerrainField, point: PointM) -> tuple[int, int]:
    column = int(
        round((point[0] + terrain.width_m * 0.5) / terrain.cell_size_x_m)
    )
    row = int(
        round((point[1] + terrain.height_m * 0.5) / terrain.cell_size_y_m)
    )
    return (
        min(max(row, 0), terrain.shape[0] - 1),
        min(max(column, 0), terrain.shape[1] - 1),
    )


def _road_exposure(road_class: RoadClass) -> float:
    return {
        RoadClass.LOCAL: 0.0,
        RoadClass.COLLECTOR: 0.35,
        RoadClass.ARTERIAL: 0.80,
        RoadClass.EXPRESSWAY: 1.0,
        RoadClass.RAMP: 0.90,
        RoadClass.BRIDGE: 0.80,
    }[road_class]


def _catalog_fingerprint(catalog: LandUseCatalog) -> str:
    payload = {
        "schema": "block_land_use_catalog_v1",
        "terrain": catalog.terrain_fingerprint,
        "urban_form": catalog.urban_form_fingerprint,
        "street_network": catalog.street_network_fingerprint,
        "block_catalog": catalog.block_catalog_fingerprint,
        "blocks": [
            (
                item.block_id,
                item.land_use_type.value,
                item.polygon_m,
                item.centroid_m,
                item.area_m2,
                item.frontage_street_ids,
                item.access_node_id,
                item.development_intensity,
                item.centrality_score,
                item.arterial_exposure,
                item.slope_rise_per_m,
                item.population_capacity,
                item.job_capacity,
                item.leisure_capacity,
            )
            for item in catalog.blocks
        ],
        "pois": [
            (
                poi.poi_id,
                poi.block_id,
                poi.poi_type.value,
                poi.x_m,
                poi.y_m,
                poi.access_node_id,
                poi.capacity_hint,
            )
            for poi in catalog.pois
        ],
        "developed_block_count": catalog.developed_block_count,
        "industrial_residential_shared_edge_count": (
            catalog.industrial_residential_shared_edge_count
        ),
        "essential_access_ratio": catalog.essential_access_ratio,
        "median_developed_density_per_hectare": (
            catalog.median_developed_density_per_hectare
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
