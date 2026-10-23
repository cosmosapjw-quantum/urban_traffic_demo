"""City APIs resolved on first access, without eager optional dependencies.

Public names and defining modules are retained. Importing an unrelated research
submodule does not require NumPy/JAX or initialize production city generators.
"""
from importlib import import_module

_LAZY_EXPORT_MODULE = {'BlockLandUse': '.block_land_use', 'BlockLandUseType': '.block_land_use', 'BlockPOI': '.block_land_use', 'BlockPOIType': '.block_land_use', 'BridgeCrossing': '.graph', 'CityBlock': '.planar_blocks', 'CityBlockCatalog': '.planar_blocks', 'CityBlueprint': '.blueprint', 'GateDecision': '.contracts', 'GateThresholds': '.contracts', 'GateVersions': '.contracts', 'GeneratedCityMap': '.blueprint', 'GenerationPipeline': '.generator_v2', 'GeneratorV2': '.generator_v2', 'LandUseCatalog': '.block_land_use', 'MORPHOLOGY_ARCHETYPES': '.morphology_reference', 'MorphologyArchetype': '.morphology_reference', 'MorphologyQualityGate': '.morphology_quality', 'MorphologyQualityMetrics': '.morphology_quality', 'Node': '.graph', 'NodeKind': '.graph', 'PhysicalStreet': '.street_plan', 'PhysicalStreetPlan': '.street_plan', 'PreviewCityTopology': '.generated_map', 'RealisticCityQualityResult': '.blueprint', 'RealisticStreetNetwork': '.realistic_local_fabric', 'RoadClass': '.graph', 'RoadLink': '.graph', 'RoadNetworkCSR': '.graph', 'StreetNetworkMorphometrics': '.morphology_metrics', 'TerrainField': '.terrain_field', 'TopologyValidationIssue': '.graph', 'TopologyValidationReport': '.graph', 'TurnAuthorityCatalog': '.turn_compiler', 'TurnMovement': '.graph', 'TurnType': '.graph', 'UrbanCenter': '.urban_form', 'UrbanFormField': '.urban_form', 'WeakConnectivityRepairResult': '.connectivity', 'WeakConnectivityReport': '.connectivity', 'analyze_weak_connectivity': '.connectivity', 'build_block_land_use_catalog': '.block_land_use', 'build_continuous_local_fabric': '.realistic_local_fabric', 'build_hierarchical_street_skeleton': '.hierarchical_streets', 'build_road_network_csr': '.graph', 'build_terrain_field': '.terrain_field', 'build_urban_form_field': '.urban_form', 'compile_planar_city_blocks': '.planar_blocks', 'compile_turn_authority': '.turn_compiler', 'compute_morphology_quality_metrics': '.morphology_quality', 'compute_street_network_morphometrics': '.morphology_metrics', 'empirical_street_network_references': '.morphology_reference', 'evaluate_morphology_quality_gate': '.morphology_quality', 'generate_city_map': '.realistic_city', 'get_morphology_archetype': '.morphology_reference', 'repair_weak_connectivity': '.connectivity', 'validate_road_network_topology': '.graph'}

__all__ = ['BlockLandUse', 'BlockLandUseType', 'BlockPOI', 'BlockPOIType', 'BridgeCrossing', 'CityBlock', 'CityBlockCatalog', 'CityBlueprint', 'GateDecision', 'GateThresholds', 'GateVersions', 'GenerationPipeline', 'GeneratedCityMap', 'GeneratorV2', 'LandUseCatalog', 'MORPHOLOGY_ARCHETYPES', 'MorphologyArchetype', 'MorphologyQualityMetrics', 'MorphologyQualityGate', 'Node', 'NodeKind', 'PhysicalStreet', 'PhysicalStreetPlan', 'PreviewCityTopology', 'RoadClass', 'RoadLink', 'RoadNetworkCSR', 'RealisticStreetNetwork', 'RealisticCityQualityResult', 'StreetNetworkMorphometrics', 'TerrainField', 'TopologyValidationIssue', 'TopologyValidationReport', 'TurnAuthorityCatalog', 'TurnMovement', 'TurnType', 'UrbanCenter', 'UrbanFormField', 'WeakConnectivityRepairResult', 'WeakConnectivityReport', 'analyze_weak_connectivity', 'build_block_land_use_catalog', 'build_road_network_csr', 'build_hierarchical_street_skeleton', 'build_continuous_local_fabric', 'build_terrain_field', 'build_urban_form_field', 'compute_street_network_morphometrics', 'compute_morphology_quality_metrics', 'compile_turn_authority', 'compile_planar_city_blocks', 'empirical_street_network_references', 'evaluate_morphology_quality_gate', 'generate_city_map', 'get_morphology_archetype', 'repair_weak_connectivity', 'validate_road_network_topology']


def __getattr__(name: str):
    module_name = _LAZY_EXPORT_MODULE.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
