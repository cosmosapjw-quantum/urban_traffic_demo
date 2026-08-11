from importlib import import_module

from .contracts import GateDecision as GateDecision
from .contracts import GateThresholds as GateThresholds
from .contracts import GateVersions as GateVersions
from .connectivity import WeakConnectivityRepairResult as WeakConnectivityRepairResult
from .connectivity import WeakConnectivityReport as WeakConnectivityReport
from .connectivity import analyze_weak_connectivity as analyze_weak_connectivity
from .connectivity import repair_weak_connectivity as repair_weak_connectivity
from .generated_map import PreviewCityTopology as PreviewCityTopology
from .graph import BridgeCrossing as BridgeCrossing
from .graph import Node as Node
from .graph import NodeKind as NodeKind
from .graph import RoadClass as RoadClass
from .graph import RoadLink as RoadLink
from .graph import RoadNetworkCSR as RoadNetworkCSR
from .graph import TopologyValidationIssue as TopologyValidationIssue
from .graph import TopologyValidationReport as TopologyValidationReport
from .graph import TurnMovement as TurnMovement
from .graph import TurnType as TurnType
from .graph import build_road_network_csr as build_road_network_csr
from .graph import validate_road_network_topology as validate_road_network_topology
from .hierarchical_streets import (
    build_hierarchical_street_skeleton as build_hierarchical_street_skeleton,
)
from .morphology_metrics import StreetNetworkMorphometrics as StreetNetworkMorphometrics
from .morphology_metrics import (
    compute_street_network_morphometrics as compute_street_network_morphometrics,
)
from .morphology_quality import MorphologyQualityMetrics as MorphologyQualityMetrics
from .morphology_quality import MorphologyQualityGate as MorphologyQualityGate
from .morphology_quality import (
    compute_morphology_quality_metrics as compute_morphology_quality_metrics,
)
from .morphology_quality import (
    evaluate_morphology_quality_gate as evaluate_morphology_quality_gate,
)
from .morphology_reference import MORPHOLOGY_ARCHETYPES as MORPHOLOGY_ARCHETYPES
from .morphology_reference import MorphologyArchetype as MorphologyArchetype
from .morphology_reference import (
    empirical_street_network_references as empirical_street_network_references,
)
from .morphology_reference import get_morphology_archetype as get_morphology_archetype
from .realistic_local_fabric import RealisticStreetNetwork as RealisticStreetNetwork
from .realistic_local_fabric import (
    build_continuous_local_fabric as build_continuous_local_fabric,
)
from .street_plan import PhysicalStreet as PhysicalStreet
from .street_plan import PhysicalStreetPlan as PhysicalStreetPlan
from .terrain_field import TerrainField as TerrainField
from .terrain_field import build_terrain_field as build_terrain_field
from .turn_compiler import TurnAuthorityCatalog as TurnAuthorityCatalog
from .turn_compiler import compile_turn_authority as compile_turn_authority
from .urban_form import UrbanCenter as UrbanCenter
from .urban_form import UrbanFormField as UrbanFormField
from .urban_form import build_urban_form_field as build_urban_form_field

_LAZY_EXPORT_MODULE = {
    "BlockLandUse": ".block_land_use",
    "BlockLandUseType": ".block_land_use",
    "BlockPOI": ".block_land_use",
    "BlockPOIType": ".block_land_use",
    "LandUseCatalog": ".block_land_use",
    "build_block_land_use_catalog": ".block_land_use",
    "CityBlock": ".planar_blocks",
    "CityBlockCatalog": ".planar_blocks",
    "compile_planar_city_blocks": ".planar_blocks",
    "GenerationPipeline": ".generator_v2",
    "GeneratorV2": ".generator_v2",
}


__all__ = [
    "BlockLandUse",
    "BlockLandUseType",
    "BlockPOI",
    "BlockPOIType",
    "BridgeCrossing",
    "CityBlock",
    "CityBlockCatalog",
    "CityBlueprint",
    "GateDecision",
    "GateThresholds",
    "GateVersions",
    "GenerationPipeline",
    "GeneratedCityMap",
    "GeneratorV2",
    "LandUseCatalog",
    "MORPHOLOGY_ARCHETYPES",
    "MorphologyArchetype",
    "MorphologyQualityMetrics",
    "MorphologyQualityGate",
    "Node",
    "NodeKind",
    "PhysicalStreet",
    "PhysicalStreetPlan",
    "PreviewCityTopology",
    "RoadClass",
    "RoadLink",
    "RoadNetworkCSR",
    "RealisticStreetNetwork",
    "RealisticCityQualityResult",
    "StreetNetworkMorphometrics",
    "TerrainField",
    "TopologyValidationIssue",
    "TopologyValidationReport",
    "TurnAuthorityCatalog",
    "TurnMovement",
    "TurnType",
    "UrbanCenter",
    "UrbanFormField",
    "WeakConnectivityRepairResult",
    "WeakConnectivityReport",
    "analyze_weak_connectivity",
    "build_block_land_use_catalog",
    "build_road_network_csr",
    "build_hierarchical_street_skeleton",
    "build_continuous_local_fabric",
    "build_terrain_field",
    "build_urban_form_field",
    "compute_street_network_morphometrics",
    "compute_morphology_quality_metrics",
    "compile_turn_authority",
    "compile_planar_city_blocks",
    "empirical_street_network_references",
    "evaluate_morphology_quality_gate",
    "generate_city_map",
    "get_morphology_archetype",
    "repair_weak_connectivity",
    "validate_road_network_topology",
]


def __getattr__(name: str):
    if name in _LAZY_EXPORT_MODULE:
        module_name = _LAZY_EXPORT_MODULE[name]
        return getattr(import_module(module_name, __name__), name)
    if name in {"CityBlueprint", "GeneratedCityMap", "RealisticCityQualityResult"}:
        from .blueprint import (
            CityBlueprint,
            GeneratedCityMap,
            RealisticCityQualityResult,
        )

        return {
            "CityBlueprint": CityBlueprint,
            "GeneratedCityMap": GeneratedCityMap,
            "RealisticCityQualityResult": RealisticCityQualityResult,
        }[name]
    if name == "generate_city_map":
        from .realistic_city import generate_city_map

        return generate_city_map
    raise AttributeError(name)
