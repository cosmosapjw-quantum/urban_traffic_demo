from __future__ import annotations

import importlib
from dataclasses import fields, is_dataclass, replace
from fractions import Fraction
import inspect
import math
import sys
from types import MappingProxyType

import numpy as np
import pytest

from metroflow.city.graph import NodeKind, RoadClass
from metroflow.city.scale import CityScaleSpec
from metroflow.city.scalable_blocks import build_scalable_block_authority
from metroflow.city.scalable_topology import (
    ScalableTerrainField,
    build_scalable_street_network,
)
from metroflow.city.scalable_topology_adapter import (
    compile_scalable_topology,
    require_valid_scalable_compiled_topology,
)


@pytest.fixture(scope="module")
def canonical_scalable_sources() -> tuple[object, object, object, object]:
    scale = CityScaleSpec(100_000, 15.0)
    network = build_scalable_street_network(scale, "grid_core", 17)
    blocks = build_scalable_block_authority(network)
    compiled = compile_scalable_topology(network, block_authority=blocks)
    return scale, network, blocks, compiled


@pytest.fixture(scope="module")
def river_scalable_sources() -> tuple[object, object, object, object]:
    scale = CityScaleSpec(100_000, 15.0)
    network = build_scalable_street_network(scale, "river_constrained", 17)
    blocks = build_scalable_block_authority(network)
    compiled = compile_scalable_topology(network, block_authority=blocks)
    return scale, network, blocks, compiled


def test_scalable_authority_public_api_is_exact() -> None:
    authority = importlib.import_module("metroflow.city.scalable_authority")

    assert authority.__all__ == (
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


def test_scalable_authority_public_schema_is_exact() -> None:
    authority = importlib.import_module("metroflow.city.scalable_authority")

    expected_literals = {
        "STATIC_AUTHORITY_SCHEMA": "scalable_static_authority_v1",
        "LAND_USE_POLICY": "scalable_v2_land_use_v1",
        "ALLOCATION_POLICY": "scalable_v2_capacity_allocation_v1",
        "TAZ_POLICY": "scalable_v2_taz_morton_v1",
        "POI_POLICY": "scalable_v2_aggregate_poi_v1",
        "FINGERPRINT_SET_SCHEMA": "scalable_map_fingerprint_v3",
        "IMMUTABLE_CSR_SCHEMA": "immutable_road_network_csr_v1",
        "ROUTING_KEY_SCHEMA": "scalable_v2_routing_static_key_v1",
        "STATIC_CONFIG_NODE_SCHEMA": "scalable_v2_static_config_node_v1",
        "GEOMETRY_NODE_SCHEMA": "scalable_v2_geometry_node_v1",
        "TOPOLOGY_NODE_SCHEMA": "scalable_v2_topology_node_v1",
        "LINK_ATTRIBUTES_NODE_SCHEMA": "scalable_v2_link_attributes_node_v1",
        "TURN_AUTHORITY_NODE_SCHEMA": "scalable_v2_turn_authority_node_v1",
        "BLOCKS_ACCESS_NODE_SCHEMA": "scalable_v2_blocks_access_node_v1",
        "LAND_USE_ZONING_NODE_SCHEMA": "scalable_v2_land_use_zoning_node_v1",
        "ROUTING_STATIC_NODE_SCHEMA": "scalable_v2_routing_static_node_v1",
        "ACCESSIBILITY_STATIC_NODE_SCHEMA": "scalable_v2_accessibility_static_node_v1",
        "REPLAY_STATIC_NODE_SCHEMA": "scalable_v2_replay_static_node_v1",
        "COMPOSITE_NODE_SCHEMA": "scalable_v2_composite_node_v1",
        "ROUTING_POLICY": "task4_legal_turn_csr_v1",
        "ACCESS_DIRECTION_POLICY": "task4_declared_forward_reverse_v1",
        "CLOSURE_CAPABILITY_POLICY": "task4_blockable_failure_group_v1",
        "STATIC_BUILDER_BACKEND": "python_numpy_baseline_static_v1",
        "CAPACITY_REFERENCE_TICK_SECONDS": 1.0,
        "CAPACITY_SOURCE_UNIT": "vehicles_per_second",
    }
    assert {name: getattr(authority, name) for name in expected_literals} == expected_literals

    assert tuple((member.name, member.value) for member in authority.V2LandUseType) == (
        ("RESIDENTIAL", "residential"),
        ("COMMERCIAL", "commercial"),
        ("INDUSTRIAL", "industrial"),
        ("MIXED_USE", "mixed_use"),
    )
    assert tuple((member.name, member.value) for member in authority.V2PoiKind) == (
        ("HOME", "home"),
        ("WORKPLACE", "workplace"),
        ("LEISURE", "leisure"),
    )

    expected_annotations = {
        "BlockLandUseV2": {
            "block_id": "int",
            "block_semantic_id": "str",
            "parent_face_id": "int",
            "land_use_type": "V2LandUseType",
            "outer_polygon_mm": "tuple[tuple[int, int], ...]",
            "hole_polygons_mm": "tuple[tuple[tuple[int, int], ...], ...]",
            "exact_net_area_mm2": "Fraction",
            "frontage_road_ids": "tuple[int, ...]",
            "access_node_ids": "tuple[int, ...]",
            "primary_access_node_id": "int",
            "interior_witness_mm": "tuple[int | Fraction, int | Fraction]",
            "terrain_cell": "tuple[int, int]",
            "terrain_intensity": "float",
            "terrain_intensity_hex": "str",
            "centrality_score": "float",
            "exposure_score": "float",
            "raw_resident_weight": "float",
            "raw_home_weight": "float",
            "raw_job_weight": "float",
            "raw_leisure_weight": "float",
            "raw_resident_ratio": "tuple[int, int]",
            "raw_home_ratio": "tuple[int, int]",
            "raw_job_ratio": "tuple[int, int]",
            "raw_leisure_ratio": "tuple[int, int]",
            "final_resident_capacity": "int",
            "final_home_capacity": "int",
            "final_job_capacity": "int",
            "final_leisure_capacity": "int",
            "taz_id": "int",
            "source_network_fingerprint": "str",
            "source_blocks_fingerprint": "str",
            "policy_version": "str",
            "fingerprint": "str",
        },
        "PopulationCapacityCertificate": {
            "schema_version": "str",
            "target_population": "int",
            "job_target": "int",
            "worker_share_numerator": "int",
            "worker_share_denominator": "int",
            "resident_raw_total_ratio": "tuple[int, int]",
            "home_raw_total_ratio": "tuple[int, int]",
            "job_raw_total_ratio": "tuple[int, int]",
            "leisure_raw_total_ratio": "tuple[int, int]",
            "resident_multiplier_ratio": "tuple[int, int]",
            "home_multiplier_ratio": "tuple[int, int]",
            "job_multiplier_ratio": "tuple[int, int]",
            "leisure_multiplier_ratio": "tuple[int, int]",
            "resident_capacity_total": "int",
            "home_capacity_total": "int",
            "job_capacity_total": "int",
            "leisure_capacity_total": "int",
            "taz_count": "int",
            "allocated_block_count": "int",
            "capacity_cap_applied": "bool",
            "silent_cap_count": "int",
            "dropped_capacity_count": "int",
            "allocation_fingerprint": "str",
            "source_network_fingerprint": "str",
            "source_blocks_fingerprint": "str",
            "source_compiled_fingerprint": "str",
            "land_use_policy_version": "str",
            "allocation_policy_version": "str",
            "fingerprint": "str",
        },
        "V2Taz": {
            "taz_id": "int",
            "semantic_id": "str",
            "block_ids": "tuple[int, ...]",
            "block_semantic_ids": "tuple[str, ...]",
            "frontage_road_ids": "tuple[int, ...]",
            "access_node_ids": "tuple[int, ...]",
            "resident_capacity_total": "int",
            "home_capacity_total": "int",
            "job_capacity_total": "int",
            "leisure_capacity_total": "int",
            "fingerprint": "str",
        },
        "V2TazCatalog": {
            "schema_version": "str",
            "tazs": "tuple[V2Taz, ...]",
            "block_taz_by_id": "tuple[tuple[int, int], ...]",
            "node_owner_by_id": "tuple[tuple[int, int], ...]",
            "node_conflicts": "tuple[tuple[int, tuple[tuple[str, int], ...], int], ...]",
            "target_taz_count": "int",
            "source_blocks_fingerprint": "str",
            "source_allocation_fingerprint": "str",
            "assignment_fingerprint": "str",
            "fingerprint": "str",
        },
        "V2Poi": {
            "poi_id": "int",
            "semantic_id": "str",
            "poi_kind": "V2PoiKind",
            "block_id": "int",
            "block_semantic_id": "str",
            "location_witness_mm": "tuple[int | Fraction, int | Fraction]",
            "access_node_id": "int",
            "taz_id": "int",
            "capacity": "int",
            "source_allocation_fingerprint": "str",
            "fingerprint": "str",
        },
        "V2PoiCatalog": {
            "schema_version": "str",
            "pois": "tuple[V2Poi, ...]",
            "home_capacity_total": "int",
            "workplace_capacity_total": "int",
            "leisure_capacity_total": "int",
            "source_allocation_fingerprint": "str",
            "source_taz_fingerprint": "str",
            "fingerprint": "str",
        },
        "MapFingerprintSetV3": {
            "schema_version": "str",
            "config": "str",
            "geometry": "str",
            "topology": "str",
            "link_attributes": "str",
            "turn_authority": "str",
            "blocks_access": "str",
            "land_use_zoning": "str",
            "routing_static": "str",
            "accessibility_static": "str",
            "replay_static": "str",
            "composite": "str",
        },
        "RoutingStaticDependencyKey": {
            "schema_version": "str",
            "routing_static_fingerprint": "str",
            "routing_policy_version": "str",
            "access_direction_policy_version": "str",
            "closure_capability_policy_version": "str",
            "source_csr_fingerprint": "str",
            "fingerprint": "str",
        },
        "ImmutableNode": {
            "node_id": "int",
            "kind": "NodeKind",
            "x": "float",
            "y": "float",
            "zone_id": "int | None",
            "signal_group_id": "int | None",
        },
        "ImmutableRoadLink": {
            "link_id": "int",
            "src_node_id": "int",
            "dst_node_id": "int",
            "road_class": "RoadClass",
            "length_m": "float",
            "free_flow_speed_mps": "float",
            "capacity_veh_per_tick": "float",
            "lanes": "int",
            "bridge_group_id": "int | None",
            "is_blockable": "bool",
            "physical_road_id": "int | None",
        },
        "ImmutableTurnMovement": {
            "from_link_id": "int",
            "to_link_id": "int",
            "turn_type": "TurnType",
            "base_priority": "float",
            "signal_phase_id": "int | None",
        },
        "ImmutableBridgeCrossing": {
            "bridge_group_id": "int",
            "link_ids": "tuple[int, ...]",
            "barrier_id": "int",
            "crossing_name": "str",
            "bottleneck_rank_hint": "int | None",
        },
        "ImmutableRoadNetworkCSR": {
            "schema_version": "str",
            "nodes": "tuple[ImmutableNode, ...]",
            "links": "tuple[ImmutableRoadLink, ...]",
            "turns": "tuple[ImmutableTurnMovement, ...]",
            "bridge_crossings": "tuple[ImmutableBridgeCrossing, ...]",
            "node_id_to_index": "Mapping[int, int]",
            "link_id_to_index": "Mapping[int, int]",
            "turn_pair_to_index": "Mapping[tuple[int, int], int]",
            "node_ids": "np.ndarray",
            "link_ids": "np.ndarray",
            "link_src_node_index": "np.ndarray",
            "link_dst_node_index": "np.ndarray",
            "outgoing_indptr": "np.ndarray",
            "outgoing_link_indices": "np.ndarray",
            "incoming_indptr": "np.ndarray",
            "incoming_link_indices": "np.ndarray",
            "turn_from_link_index": "np.ndarray",
            "turn_to_link_index": "np.ndarray",
            "turn_base_priority": "np.ndarray",
            "turn_is_forbidden": "np.ndarray",
            "topology_cache_key": "tuple[object, ...]",
            "content_fingerprint": "str",
        },
        "ScalableStaticAuthority": {
            "schema_version": "str",
            "scale_spec": "CityScaleSpec",
            "style_id": "str",
            "seed": "int",
            "extent_mm": "tuple[int, int, int, int]",
            "width_m": "float",
            "height_m": "float",
            "centers_mm": "tuple[tuple[int, int], ...]",
            "source_network_schema_version": "str",
            "source_blocks_schema_version": "str",
            "source_compiled_schema_version": "str",
            "numeric_profile_policy_version": "str",
            "source_network_fingerprint": "str",
            "source_blocks_fingerprint": "str",
            "source_compiled_fingerprint": "str",
            "source_terrain_fingerprint": "str",
            "source_scale_fingerprint": "str",
            "source_style_fingerprint": "str",
            "source_geometry_fingerprint": "str",
            "source_section_fingerprint": "str",
            "source_node_interface_fingerprint": "str",
            "source_turn_authority_fingerprint": "str",
            "numeric_profiles": "tuple[ScalableNumericProfile, ...]",
            "road_crosswalk": "tuple[ScalableRoadCrosswalk, ...]",
            "structure_group_crosswalk": "tuple[ScalableGroupCrosswalk, ...]",
            "failure_group_crosswalk": "tuple[ScalableGroupCrosswalk, ...]",
            "block_access_index": "V2BlockAccessIndex",
            "block_land_use": "tuple[BlockLandUseV2, ...]",
            "capacity_certificate": "PopulationCapacityCertificate",
            "taz_catalog": "V2TazCatalog",
            "poi_catalog": "V2PoiCatalog",
            "fingerprints": "MapFingerprintSetV3",
            "road_csr": "ImmutableRoadNetworkCSR",
            "routing_dependency_key": "RoutingStaticDependencyKey",
            "fingerprint": "str",
        },
    }
    for class_name, annotations in expected_annotations.items():
        record_type = getattr(authority, class_name)
        assert is_dataclass(record_type), class_name
        assert record_type.__dataclass_params__.frozen is True
        assert "__slots__" in record_type.__dict__
        assert record_type.__annotations__ == annotations
        assert tuple(field.name for field in fields(record_type)) == tuple(annotations)

