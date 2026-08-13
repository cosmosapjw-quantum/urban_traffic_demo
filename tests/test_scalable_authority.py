from __future__ import annotations

import importlib


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
