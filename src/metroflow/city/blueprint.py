"""Composed immutable records for realistic generated city maps."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from .block_land_use import LandUseCatalog
from .generated_map import PreviewCityTopology
from .graph import RoadNetworkCSR
from .planar_blocks import CityBlockCatalog
from .realistic_local_fabric import RealisticStreetNetwork
from .street_plan import PhysicalStreetPlan
from .terrain_field import TerrainField
from .urban_form import UrbanFormField
from .zones import ZoningPlacementResult, zoning_placement_fingerprint

__all__ = ["CityBlueprint", "GeneratedCityMap", "RealisticCityQualityResult"]


@dataclass(frozen=True, slots=True)
class CityBlueprint:
    schema_version: str
    scenario_id: str
    seed: int
    style_id: str
    width_m: float
    height_m: float
    terrain: TerrainField
    urban_form: UrbanFormField
    street_skeleton: PhysicalStreetPlan
    street_network: RealisticStreetNetwork
    blocks: CityBlockCatalog
    land_use: LandUseCatalog
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        schema_version = str(self.schema_version).strip()
        scenario_id = str(self.scenario_id).strip()
        style_id = str(self.style_id).strip()
        width_m = float(self.width_m)
        height_m = float(self.height_m)
        if not schema_version or not scenario_id or not style_id:
            raise ValueError("blueprint schema, scenario, and style must be non-empty")
        if not all(
            math.isfinite(value) and value > 0.0 for value in (width_m, height_m)
        ):
            raise ValueError("blueprint dimensions must be finite and > 0 meters")
        if self.terrain.style_id != style_id or self.urban_form.style_id != style_id:
            raise ValueError("blueprint terrain and urban form styles do not match")
        if self.terrain.seed != int(self.seed):
            raise ValueError("blueprint seed does not match terrain")
        if self.street_skeleton.style_id != style_id or self.street_network.style_id != style_id:
            raise ValueError("blueprint street stage styles do not match")
        if not math.isclose(self.terrain.width_m, width_m) or not math.isclose(
            self.terrain.height_m,
            height_m,
        ):
            raise ValueError("blueprint dimensions do not match terrain")
        if self.urban_form.terrain_fingerprint != self.terrain.fingerprint:
            raise ValueError("blueprint urban form does not match terrain")
        if self.street_skeleton.terrain_fingerprint != self.terrain.fingerprint:
            raise ValueError("blueprint street skeleton does not match terrain")
        if self.street_skeleton.urban_form_fingerprint != self.urban_form.fingerprint:
            raise ValueError("blueprint street skeleton does not match urban form")
        if self.street_network.skeleton_fingerprint != self.street_skeleton.fingerprint:
            raise ValueError("blueprint street network does not match skeleton")
        if self.blocks.street_network_fingerprint != self.street_network.fingerprint:
            raise ValueError("blueprint blocks do not match street network")
        if self.land_use.block_catalog_fingerprint != self.blocks.fingerprint:
            raise ValueError("blueprint land use does not match blocks")
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "scenario_id", scenario_id)
        object.__setattr__(self, "seed", int(self.seed))
        object.__setattr__(self, "style_id", style_id)
        object.__setattr__(self, "width_m", width_m)
        object.__setattr__(self, "height_m", height_m)
        object.__setattr__(self, "fingerprint", _blueprint_fingerprint(self))


@dataclass(frozen=True, slots=True)
class RealisticCityQualityResult:
    passed: bool
    failure_codes: tuple[str, ...]
    metrics: Mapping[str, int | float | str]
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.passed, bool):
            raise ValueError("quality passed must be a bool")
        failure_codes = tuple(sorted({str(value) for value in self.failure_codes}))
        metrics = MappingProxyType(
            {str(key): value for key, value in dict(self.metrics).items()}
        )
        if self.passed == bool(failure_codes):
            raise ValueError("quality passed and failure_codes are inconsistent")
        if not metrics:
            raise ValueError("quality metrics must not be empty")
        object.__setattr__(self, "failure_codes", failure_codes)
        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(self, "fingerprint", _quality_fingerprint(self))


@dataclass(frozen=True, slots=True)
class GeneratedCityMap:
    blueprint: CityBlueprint
    topology: PreviewCityTopology
    road_csr: RoadNetworkCSR
    zoning: ZoningPlacementResult
    quality: RealisticCityQualityResult
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.quality.passed:
            raise ValueError("generated city map requires a passing quality result")
        if self.topology.metadata.get("city_blueprint_fingerprint") != (
            self.blueprint.fingerprint
        ):
            raise ValueError("topology does not match city blueprint")
        if self.road_csr.node_count != len(self.topology.nodes) or (
            self.road_csr.link_count != len(self.topology.links)
        ):
            raise ValueError("road CSR does not cover generated topology")
        if self.road_csr.turn_count != len(self.topology.turns):
            raise ValueError("road CSR turn count does not match topology")
        if tuple(node.node_id for node in self.road_csr.nodes) != tuple(
            node.node_id for node in self.topology.nodes
        ):
            raise ValueError("road CSR nodes do not match topology authority")
        if tuple(link.link_id for link in self.road_csr.links) != tuple(
            link.link_id for link in self.topology.links
        ):
            raise ValueError("road CSR links do not match topology authority")
        if tuple(
            (turn.from_link_id, turn.to_link_id, turn.turn_type)
            for turn in self.road_csr.turns
        ) != tuple(
            (turn.from_link_id, turn.to_link_id, turn.turn_type)
            for turn in self.topology.turns
        ):
            raise ValueError("road CSR turns do not match topology authority")
        zoning_fingerprint = zoning_placement_fingerprint(self.zoning)
        if self.zoning.metadata.get("zoning_placement_fingerprint") != (
            zoning_fingerprint
        ):
            raise ValueError("generated zoning fingerprint is inconsistent")
        if self.zoning.metadata.get("land_use_catalog_fingerprint") != (
            self.blueprint.land_use.fingerprint
        ):
            raise ValueError("generated zoning does not match blueprint land use")
        object.__setattr__(self, "fingerprint", _generated_map_fingerprint(self))


def _blueprint_fingerprint(blueprint: CityBlueprint) -> str:
    return _sha256(
        {
            "schema_version": blueprint.schema_version,
            "scenario_id": blueprint.scenario_id,
            "seed": blueprint.seed,
            "style_id": blueprint.style_id,
            "extent_m": (blueprint.width_m, blueprint.height_m),
            "terrain": blueprint.terrain.fingerprint,
            "urban_form": blueprint.urban_form.fingerprint,
            "street_skeleton": blueprint.street_skeleton.fingerprint,
            "street_network": blueprint.street_network.fingerprint,
            "blocks": blueprint.blocks.fingerprint,
            "land_use": blueprint.land_use.fingerprint,
        }
    )


def _quality_fingerprint(quality: RealisticCityQualityResult) -> str:
    return _sha256(
        {
            "schema": "realistic_city_quality_v1",
            "passed": quality.passed,
            "failure_codes": quality.failure_codes,
            "metrics": dict(quality.metrics),
        }
    )


def _generated_map_fingerprint(generated: GeneratedCityMap) -> str:
    geometry = generated.topology.road_geometry
    return _sha256(
        {
            "schema": "generated_city_map_v1",
            "blueprint": generated.blueprint.fingerprint,
            "geometry": getattr(geometry, "fingerprint", ""),
            "zoning": generated.zoning.metadata["zoning_placement_fingerprint"],
            "quality": generated.quality.fingerprint,
            "node_count": generated.road_csr.node_count,
            "link_count": generated.road_csr.link_count,
            "turn_count": generated.road_csr.turn_count,
        }
    )


def _sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
