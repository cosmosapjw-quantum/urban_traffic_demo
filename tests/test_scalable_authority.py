from __future__ import annotations

import importlib
from dataclasses import MISSING, fields, is_dataclass, replace
from fractions import Fraction
import inspect
import json
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

    expected_defaults = {
        "BlockLandUseV2": {"fingerprint": ""},
        "PopulationCapacityCertificate": {"fingerprint": ""},
        "V2Taz": {"fingerprint": ""},
        "V2TazCatalog": {"fingerprint": ""},
        "V2Poi": {"fingerprint": ""},
        "V2PoiCatalog": {"fingerprint": ""},
        "MapFingerprintSetV3": {},
        "RoutingStaticDependencyKey": {"fingerprint": ""},
        "ImmutableNode": {},
        "ImmutableRoadLink": {},
        "ImmutableTurnMovement": {},
        "ImmutableBridgeCrossing": {},
        "ImmutableRoadNetworkCSR": {"content_fingerprint": ""},
        "ScalableStaticAuthority": {"fingerprint": ""},
    }
    for class_name, expected in expected_defaults.items():
        record_fields = fields(getattr(authority, class_name))
        observed = {
            field.name: field.default
            for field in record_fields
            if field.default is not MISSING
        }
        assert observed == expected
        assert all(field.default_factory is MISSING for field in record_fields)

    builder = inspect.signature(authority.build_scalable_static_authority)
    assert tuple(builder.parameters) == (
        "scale_spec",
        "style_id",
        "seed",
        "network",
        "blocks",
        "compiled",
    )
    assert all(
        parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        for parameter in builder.parameters.values()
    )
    assert all(
        parameter.default is inspect.Parameter.empty
        for parameter in builder.parameters.values()
    )
    assert builder.return_annotation == "ScalableStaticAuthority"

    validator = inspect.signature(authority.require_valid_scalable_static_authority)
    assert tuple(validator.parameters) == (
        "authority",
        "scale_spec",
        "style_id",
        "seed",
        "network",
        "blocks",
        "compiled",
    )
    assert validator.parameters["authority"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert all(
        validator.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        for name in ("scale_spec", "style_id", "seed", "network", "blocks", "compiled")
    )
    assert all(
        parameter.default is inspect.Parameter.empty
        for parameter in validator.parameters.values()
    )
    assert validator.return_annotation == "None"


def test_exact_raw_weights_multiplier_and_largest_remainder_are_order_independent() -> None:
    authority = importlib.import_module("metroflow.city.scalable_authority")

    assert authority._raw_capacity_ratios(
        exact_net_area_mm2=Fraction(10_000_000_000),
        terrain_intensity=0.5,
        land_use_type=authority.V2LandUseType.RESIDENTIAL,
    ) == (Fraction(551, 8), Fraction(551, 8), Fraction(0), Fraction(145, 8))
    with pytest.raises(TypeError):
        authority._raw_capacity_ratios(
            exact_net_area_mm2=10_000_000_000,
            terrain_intensity=0.5,
            land_use_type=authority.V2LandUseType.RESIDENTIAL,
        )

    assert authority._require_implied_multiplier(
        target=1,
        raw_total=Fraction(4),
        enforce_authoritative_bounds=True,
    ) == Fraction(1, 4)
    assert authority._require_implied_multiplier(
        target=3,
        raw_total=Fraction(1),
        enforce_authoritative_bounds=True,
    ) == Fraction(3)
    assert authority._require_implied_multiplier(
        target=0,
        raw_total=Fraction(0),
        enforce_authoritative_bounds=True,
    ) == Fraction(0)
    with pytest.raises(ValueError):
        authority._require_implied_multiplier(
            target=1,
            raw_total=Fraction(4_000_001, 1_000_000),
            enforce_authoritative_bounds=True,
        )
    with pytest.raises(ValueError):
        authority._require_implied_multiplier(
            target=3_000_001,
            raw_total=Fraction(1_000_000),
            enforce_authoritative_bounds=True,
        )
    with pytest.raises(ValueError):
        authority._require_implied_multiplier(
            target=1,
            raw_total=Fraction(0),
            enforce_authoritative_bounds=True,
        )

    keys = ("0" * 64, "1" * 64, "2" * 64)
    forward = tuple((key, Fraction(1)) for key in keys)
    reverse = tuple(reversed(forward))
    expected = ((keys[0], 2), (keys[1], 2), (keys[2], 1))
    assert authority._apportion_exact_channel(target=5, weighted_rows=forward) == expected
    assert authority._apportion_exact_channel(target=5, weighted_rows=reverse) == expected
    with pytest.raises(ValueError):
        authority._apportion_exact_channel(
            target=1,
            weighted_rows=((keys[0], Fraction(1)), (keys[0], Fraction(2))),
        )


def test_fraction_witness_terrain_centrality_and_morton_are_exact() -> None:
    authority = importlib.import_module("metroflow.city.scalable_authority")
    terrain = ScalableTerrainField(
        width_m=100.0,
        height_m=100.0,
        cell_size_m=50.0,
        tile_size_m=2_000.0,
        seed=17,
        style_id="grid_core",
        barrier_seam_x_mm=None,
        fingerprint="a" * 64,
    )

    negative = authority._sample_terrain_at_exact_witness(
        terrain=terrain,
        witness_mm=(Fraction(-1, 2), Fraction(49_999, 2)),
    )
    left = authority._sample_terrain_at_exact_witness(
        terrain=terrain,
        witness_mm=(49_999, 0),
    )
    right = authority._sample_terrain_at_exact_witness(
        terrain=terrain,
        witness_mm=(50_000, 0),
    )
    assert negative == ((-1, 0), terrain.intensity_at(-25.0, 25.0))
    assert left == ((0, 0), terrain.intensity_at(25.0, 25.0))
    assert right == ((1, 0), terrain.intensity_at(75.0, 25.0))

    assert authority._centrality_score_mm(
        witness_mm=(1_000, 0),
        centers_mm=((0, 0),),
        width_m=100.0,
        height_m=50.0,
    ) == math.exp(-1.0 / 28.0)

    extent = (-100, -100, 100, 100)
    assert authority._morton_witness_key(
        witness_mm=(Fraction(-199, 2), Fraction(-199, 2)),
        extent_mm=extent,
    ) == (0, Fraction(1, 2), Fraction(1, 2))
    assert authority._morton_witness_key(
        witness_mm=(Fraction(-197, 2), Fraction(-199, 2)),
        extent_mm=extent,
    ) == (1, Fraction(3, 2), Fraction(1, 2))
    with pytest.raises(ValueError):
        authority._morton_witness_key(witness_mm=(-101, 0), extent_mm=extent)

    rows = tuple((index, str(index) * 64, (index & 1, index >> 1)) for index in range(5))
    expected = ((0, (0, 1, 2)), (1, (3, 4)))
    assert authority._partition_morton_rows(
        rows=rows,
        extent_mm=(0, 0, 10, 10),
        taz_count=2,
    ) == expected
    assert authority._partition_morton_rows(
        rows=tuple(reversed(rows)),
        extent_mm=(0, 0, 10, 10),
        taz_count=2,
    ) == expected

    assert authority._taz_count_policy_unbounded(100_000) == 64
    assert authority._taz_count_policy_unbounded(160_000) == 64
    assert authority._taz_count_policy_unbounded(160_001) == 65
    scalar_callable = authority._taz_count_policy_unbounded
    scalar_call_count = 0

    def invoke_scalar_policy(value: int) -> int:
        nonlocal scalar_call_count
        assert scalar_callable is authority._taz_count_policy_unbounded
        assert type(value) is int and value == 1_000_000
        scalar_call_count += 1
        return scalar_callable(value)

    scalar_result = invoke_scalar_policy(1_000_000)
    assert scalar_result == 400
    assert scalar_call_count == 1
    assert authority._taz_count_policy_unbounded(1_280_001) == 512
    print(
        "PR88_SCALAR_POLICY_LEDGER="
        + json.dumps(
            {
                "callable": (
                    "metroflow.city.scalable_authority._taz_count_policy_unbounded"
                ),
                "owner": "test_fraction_witness_terrain_centrality_and_morton_are_exact",
                "argument": 1_000_000,
                "call_count": scalar_call_count,
                "result": scalar_result,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def test_land_use_classifier_uses_exact_scores_and_frozen_indexed_adjacency() -> None:
    authority = importlib.import_module("metroflow.city.scalable_authority")
    assert authority._land_use_counts(4) == (1, 1, 1, 1)
    assert authority._land_use_counts(7) == (1, 1, 2, 3)
    assert authority._land_use_counts(12) == (1, 1, 3, 7)
    assert authority._land_use_counts(50) == (6, 6, 12, 26)

    reverse_index = ((10, (1, 5)), (11, (1, 7)), (12, (5, 6)))
    adjacency, visits = authority._frontage_adjacency_from_index(
        developable_block_ids=tuple(range(12)),
        road_to_block_ids=reverse_index,
    )
    assert visits == 6
    assert dict(adjacency) == {
        0: (),
        1: (5, 7),
        2: (),
        3: (),
        4: (),
        5: (1, 6),
        6: (5,),
        7: (1,),
        8: (),
        9: (),
        10: (),
        11: (),
    }

    exact_score_rows = (
        (0, "0" * 64, 0.5, 0.5, 0.5),
        (1, "f" * 64, 0.5, 0.5, math.nextafter(0.5, 1.0)),
        (2, "2" * 64, 0.0, 0.0, 1.0),
        (3, "3" * 64, 0.0, 1.0, 0.0),
    )
    assert authority._classify_land_use_rows(
        feature_rows=exact_score_rows,
        road_to_block_ids=(),
    ) == (
        (0, authority.V2LandUseType.MIXED_USE),
        (1, authority.V2LandUseType.COMMERCIAL),
        (2, authority.V2LandUseType.INDUSTRIAL),
        (3, authority.V2LandUseType.RESIDENTIAL),
    )

    uniform = tuple((index, f"{index:x}" * 64, 0.5, 0.5, 0.5) for index in range(12))
    expected = (
        (0, authority.V2LandUseType.COMMERCIAL),
        (1, authority.V2LandUseType.INDUSTRIAL),
        (2, authority.V2LandUseType.MIXED_USE),
        (3, authority.V2LandUseType.MIXED_USE),
        (4, authority.V2LandUseType.MIXED_USE),
        (5, authority.V2LandUseType.MIXED_USE),
        (6, authority.V2LandUseType.RESIDENTIAL),
        (7, authority.V2LandUseType.MIXED_USE),
        (8, authority.V2LandUseType.RESIDENTIAL),
        (9, authority.V2LandUseType.RESIDENTIAL),
        (10, authority.V2LandUseType.RESIDENTIAL),
        (11, authority.V2LandUseType.RESIDENTIAL),
    )
    assert authority._classify_land_use_rows(
        feature_rows=uniform,
        road_to_block_ids=reverse_index,
    ) == expected
    assert authority._classify_land_use_rows(
        feature_rows=tuple(reversed(uniform)),
        road_to_block_ids=tuple(reversed(reverse_index)),
    ) == expected
    with pytest.raises(ValueError):
        authority._classify_land_use_rows(
            feature_rows=uniform[:4],
            road_to_block_ids=((99, (1, 3)),),
        )


def test_node_taz_ownership_uses_semantic_candidate_order() -> None:
    authority = importlib.import_module("metroflow.city.scalable_authority")
    rows = (
        ("b" * 64, 2, (9, 4)),
        ("a" * 64, 1, (9, 3)),
        ("c" * 64, 0, (9, 4)),
    )
    owners, conflicts, visits = authority._node_taz_ownership_from_index(block_rows=rows)
    assert owners == ((3, 1), (4, 2), (9, 1))
    assert conflicts == (
        (4, (("b" * 64, 2), ("c" * 64, 0)), 2),
        (9, (("a" * 64, 1), ("b" * 64, 2), ("c" * 64, 0)), 1),
    )
    assert visits == 6
    assert authority._node_taz_ownership_from_index(
        block_rows=tuple(
            (semantic, taz, tuple(reversed(nodes)))
            for semantic, taz, nodes in reversed(rows)
        )
    ) == (owners, conflicts, visits)


def test_aggregate_poi_rows_are_positive_only_dense_and_permutation_invariant() -> None:
    authority = importlib.import_module("metroflow.city.scalable_authority")
    semantic_id = "f34defc55844a111316184c9c245d6ce9cab0c22c44e0e4d43ef2aaf07727d3c"
    with pytest.raises(ValueError, match="semantic"):
        authority.V2Poi(
            poi_id=0,
            semantic_id="0" + semantic_id[1:],
            poi_kind=authority.V2PoiKind.HOME,
            block_id=7,
            block_semantic_id="a" * 64,
            location_witness_mm=(Fraction(1, 3), Fraction(2, 5)),
            access_node_id=9,
            taz_id=2,
            capacity=5,
            source_allocation_fingerprint="d" * 64,
        )
    valid = authority.V2Poi(
        poi_id=0,
        semantic_id=semantic_id,
        poi_kind=authority.V2PoiKind.HOME,
        block_id=7,
        block_semantic_id="a" * 64,
        location_witness_mm=(Fraction(1, 3), Fraction(2, 5)),
        access_node_id=9,
        taz_id=2,
        capacity=5,
        source_allocation_fingerprint="d" * 64,
    )
    assert valid.semantic_id == semantic_id
    assert len(valid.fingerprint) == 64

    allocation = "d" * 64
    rows = (
        (7, "a" * 64, (Fraction(1, 3), Fraction(2, 5)), 9, 2, 5, 0, 3),
        (2, "b" * 64, (-1, 0), 4, 1, 0, 7, 0),
        (5, "c" * 64, (0, 0), 6, 0, 0, 0, 0),
    )
    pois = authority._aggregate_poi_rows(
        block_rows=rows,
        source_allocation_fingerprint=allocation,
    )
    assert authority._aggregate_poi_rows(
        block_rows=tuple(reversed(rows)),
        source_allocation_fingerprint=allocation,
    ) == pois
    assert tuple(
        (
            poi.poi_id,
            poi.semantic_id,
            poi.poi_kind,
            poi.block_id,
            poi.location_witness_mm,
            poi.access_node_id,
            poi.taz_id,
            poi.capacity,
            poi.source_allocation_fingerprint,
        )
        for poi in pois
    ) == (
        (
            0,
            "228b7e6bc20e596370c4bea495b7f29f8d998a9a798049813e8bcef9041ae636",
            authority.V2PoiKind.WORKPLACE,
            2,
            (-1, 0),
            4,
            1,
            7,
            allocation,
        ),
        (
            1,
            "bb6edbdcc58ed582b3eb5ca5202117a61e621581c26e9e9129c450120e0e9bae",
            authority.V2PoiKind.LEISURE,
            7,
            (Fraction(1, 3), Fraction(2, 5)),
            9,
            2,
            3,
            allocation,
        ),
        (
            2,
            "f34defc55844a111316184c9c245d6ce9cab0c22c44e0e4d43ef2aaf07727d3c",
            authority.V2PoiKind.HOME,
            7,
            (Fraction(1, 3), Fraction(2, 5)),
            9,
            2,
            5,
            allocation,
        ),
    )
    assert all(poi.fingerprint and len(poi.fingerprint) == 64 for poi in pois)
    changed = authority._aggregate_poi_rows(
        block_rows=(
            (7, "a" * 64, (9, 9), 99, 8, 50, 0, 30),
            rows[1],
            rows[2],
        ),
        source_allocation_fingerprint="e" * 64,
    )
    assert {
        (poi.block_semantic_id, poi.poi_kind): poi.semantic_id for poi in changed
    } == {(poi.block_semantic_id, poi.poi_kind): poi.semantic_id for poi in pois}
    assert tuple(poi.fingerprint for poi in changed) != tuple(
        poi.fingerprint for poi in pois
    )
    with pytest.raises(ValueError):
        authority._aggregate_poi_rows(
            block_rows=(rows[0], replace_tuple_head(rows[1], 7)),
            source_allocation_fingerprint=allocation,
        )


def replace_tuple_head(row: tuple[object, ...], value: object) -> tuple[object, ...]:
    return (value, *row[1:])


def test_fingerprint_composer_derives_exact_branched_nodes_and_rejects_forgery() -> None:
    authority = importlib.import_module("metroflow.city.scalable_authority")
    values = {
        "schema_version": authority.FINGERPRINT_SET_SCHEMA,
        "config": "0" * 64,
        "geometry": "1" * 64,
        "topology": "2" * 64,
        "link_attributes": "3" * 64,
        "turn_authority": "4" * 64,
        "blocks_access": "5" * 64,
        "land_use_zoning": "6" * 64,
        "routing_static": "5e9b604f7117caca2315ffb79292a26d6f0a69685bb7b4fc5cb5be197e8940d0",
        "accessibility_static": "91476e01c4b06f13a3f0a1341fbef17c1f98b32d8aa0690763a04f00925df31c",
        "replay_static": "aa30b408815861f90678a1d0e0bc8cd08d413bf9e8bc13c637b6464383570e9f",
        "composite": "079d0d53943c3416bc20cb4a7be58064cba31bbec0bc866fee3d5b5d31e0b4cb",
    }
    with pytest.raises(ValueError, match="routing_static"):
        authority.MapFingerprintSetV3(
            **{**values, "routing_static": "f" + values["routing_static"][1:]}
        )
    direct = authority.MapFingerprintSetV3(**values)
    assert direct.routing_static == values["routing_static"]

    origins = {
        "config": "0" * 64,
        "geometry": "1" * 64,
        "topology": "2" * 64,
        "link_attributes": "3" * 64,
        "turn_authority": "4" * 64,
        "blocks_access": "5" * 64,
        "land_use_zoning": "6" * 64,
    }
    base = authority._compose_map_fingerprint_set_v3(**origins)
    assert (
        base.routing_static,
        base.accessibility_static,
        base.replay_static,
        base.composite,
    ) == (
        "5e9b604f7117caca2315ffb79292a26d6f0a69685bb7b4fc5cb5be197e8940d0",
        "91476e01c4b06f13a3f0a1341fbef17c1f98b32d8aa0690763a04f00925df31c",
        "aa30b408815861f90678a1d0e0bc8cd08d413bf9e8bc13c637b6464383570e9f",
        "079d0d53943c3416bc20cb4a7be58064cba31bbec0bc866fee3d5b5d31e0b4cb",
    )

    expected_changed = {
        "config": {"config", "replay_static", "composite"},
        "geometry": {
            "geometry",
            "routing_static",
            "accessibility_static",
            "replay_static",
            "composite",
        },
        "topology": {
            "topology",
            "routing_static",
            "accessibility_static",
            "replay_static",
            "composite",
        },
        "link_attributes": {
            "link_attributes",
            "routing_static",
            "accessibility_static",
            "replay_static",
            "composite",
        },
        "turn_authority": {
            "turn_authority",
            "routing_static",
            "accessibility_static",
            "replay_static",
            "composite",
        },
        "blocks_access": {"blocks_access", "replay_static", "composite"},
        "land_use_zoning": {
            "land_use_zoning",
            "accessibility_static",
            "replay_static",
            "composite",
        },
    }
    fingerprint_fields = tuple(
        field.name for field in fields(authority.MapFingerprintSetV3)
    )
    for origin, wanted in expected_changed.items():
        changed_origins = {**origins, origin: "a" * 64}
        candidate = authority._compose_map_fingerprint_set_v3(**changed_origins)
        actual = {
            name
            for name in fingerprint_fields
            if getattr(candidate, name) != getattr(base, name)
        }
        assert actual == wanted

    with pytest.raises(ValueError):
        replace(base, routing_static="f" * 64)
    with pytest.raises(TypeError):
        authority._compose_map_fingerprint_set_v3(
            **{**origins, "geometry": object()}
        )
    with pytest.raises(ValueError):
        authority._compose_map_fingerprint_set_v3(
            **{**origins, "geometry": "not-a-digest"}
        )


@pytest.mark.parametrize(
    "source",
    (
        np.asarray([1, 2, 3], dtype=np.int32),
        np.asarray([-0.0, 1.25], dtype=np.float32),
        np.asarray([True, False], dtype=np.bool_),
        np.asarray([], dtype=np.int32),
    ),
)
def test_seal_c_array_is_bytes_backed_non_aliasing_and_irreversible(
    source: np.ndarray,
) -> None:
    authority = importlib.import_module("metroflow.city.scalable_authority")
    before = source.tobytes(order="C")
    sealed = authority._seal_c_array(source)

    assert type(sealed) is np.ndarray
    assert sealed.dtype == source.dtype
    assert sealed.shape == source.shape
    assert sealed.flags.c_contiguous
    assert sealed.flags.writeable is False
    assert sealed.tobytes(order="C") == before
    assert not np.shares_memory(source, sealed)
    terminal: object = sealed
    while type(terminal) is np.ndarray:
        terminal = terminal.base
    assert type(terminal) is bytes

    if sealed.size:
        with pytest.raises(ValueError):
            sealed.flat[0] = sealed.flat[0]
        with pytest.raises(ValueError):
            sealed[:] = sealed
    with pytest.raises(ValueError):
        sealed.setflags(write=True)
    with pytest.raises(ValueError):
        authority._seal_c_array(np.asarray([[1, 2], [3, 4]], dtype=np.int32).T)


def test_immutable_csr_copies_maps_arrays_and_validates_outgoing_contract() -> None:
    authority = importlib.import_module("metroflow.city.scalable_authority")
    nodes = (
        authority.ImmutableNode(0, NodeKind.INTERSECTION, 0.0, -0.0, None, None),
        authority.ImmutableNode(1, NodeKind.INTERSECTION, 1.0, 0.0, None, None),
    )
    links = (
        authority.ImmutableRoadLink(
            0,
            0,
            1,
            RoadClass.LOCAL,
            1.0,
            10.0,
            0.5,
            1,
            None,
            True,
            7,
        ),
    )
    source_maps = ({0: 0, 1: 1}, {0: 0}, {})
    source_arrays = {
        "node_ids": np.asarray([0, 1], dtype=np.int32),
        "link_ids": np.asarray([0], dtype=np.int32),
        "link_src_node_index": np.asarray([0], dtype=np.int32),
        "link_dst_node_index": np.asarray([1], dtype=np.int32),
        "outgoing_indptr": np.asarray([0, 1, 1], dtype=np.int32),
        "outgoing_link_indices": np.asarray([0], dtype=np.int32),
        "incoming_indptr": np.asarray([0, 0, 1], dtype=np.int32),
        "incoming_link_indices": np.asarray([0], dtype=np.int32),
        "turn_from_link_index": np.asarray([], dtype=np.int32),
        "turn_to_link_index": np.asarray([], dtype=np.int32),
        "turn_base_priority": np.asarray([], dtype=np.float32),
        "turn_is_forbidden": np.asarray([], dtype=np.bool_),
    }
    csr = authority.ImmutableRoadNetworkCSR(
        schema_version=authority.IMMUTABLE_CSR_SCHEMA,
        nodes=nodes,
        links=links,
        turns=(),
        bridge_crossings=(),
        node_id_to_index=source_maps[0],
        link_id_to_index=source_maps[1],
        turn_pair_to_index=source_maps[2],
        **source_arrays,
        topology_cache_key=("road-network-csr-v1", 1, -0.0, (True, None, "x")),
    )

    assert type(csr.node_id_to_index) is MappingProxyType
    assert type(csr.link_id_to_index) is MappingProxyType
    assert type(csr.turn_pair_to_index) is MappingProxyType
    assert csr.node_count == 2
    assert csr.link_count == 1
    assert csr.turn_count == 0
    assert csr.outgoing_links_for_node(0) == links
    assert csr.outgoing_links_for_node(1) == ()
    assert len(csr.content_fingerprint) == 64
    for name, source in source_arrays.items():
        sealed = getattr(csr, name)
        assert type(sealed) is np.ndarray
        assert not np.shares_memory(source, sealed)
        assert sealed.flags.writeable is False
        terminal: object = sealed
        while type(terminal) is np.ndarray:
            terminal = terminal.base
        assert type(terminal) is bytes

    source_maps[0][0] = 99
    source_maps[1][0] = 99
    source_maps[2][(0, 0)] = 99
    source_arrays["node_ids"][0] = 99
    assert dict(csr.node_id_to_index) == {0: 0, 1: 1}
    assert dict(csr.link_id_to_index) == {0: 0}
    assert dict(csr.turn_pair_to_index) == {}
    assert csr.node_ids.tolist() == [0, 1]

    for invalid in (True, np.int64(0), 99):
        with pytest.raises((TypeError, KeyError)):
            csr.outgoing_links_for_node(invalid)
    with pytest.raises(ValueError):
        replace(csr, content_fingerprint="f" * 64)


def test_exact_math_hostile_float_collapse_and_binary_cell_oracles() -> None:
    authority = importlib.import_module("metroflow.city.scalable_authority")
    expected_raw = {
        authority.V2LandUseType.RESIDENTIAL: (
            Fraction(551, 8),
            Fraction(551, 8),
            Fraction(0),
            Fraction(145, 8),
        ),
        authority.V2LandUseType.COMMERCIAL: (
            Fraction(0),
            Fraction(0),
            Fraction(493, 4),
            Fraction(203, 4),
        ),
        authority.V2LandUseType.INDUSTRIAL: (
            Fraction(0),
            Fraction(0),
            Fraction(261, 4),
            Fraction(0),
        ),
        authority.V2LandUseType.MIXED_USE: (
            Fraction(435, 8),
            Fraction(435, 8),
            Fraction(551, 8),
            Fraction(319, 8),
        ),
    }
    for land_use, expected in expected_raw.items():
        assert authority._raw_capacity_ratios(
            exact_net_area_mm2=Fraction(10_000_000_000),
            terrain_intensity=0.5,
            land_use_type=land_use,
        ) == expected

    assert authority._require_implied_multiplier(
        target=1,
        raw_total=Fraction(100),
        enforce_authoritative_bounds=False,
    ) == Fraction(1, 100)
    for invalid in (True, np.float64(1.0), float("nan"), float("inf"), -1.0):
        with pytest.raises((TypeError, ValueError)):
            authority._require_implied_multiplier(
                target=1,
                raw_total=invalid,
                enforce_authoritative_bounds=True,
            )

    key_a, key_f = "0" * 64, "f" * 64
    assert authority._apportion_exact_channel(
        target=1,
        weighted_rows=(
            (key_f, Fraction(2**53 + 1)),
            (key_a, Fraction(2**53)),
        ),
    ) == ((key_a, 0), (key_f, 1))

    terrain = ScalableTerrainField(
        width_m=1.0,
        height_m=1.0,
        cell_size_m=0.1,
        tile_size_m=2_000.0,
        seed=17,
        style_id="grid_core",
        barrier_seam_x_mm=None,
        fingerprint="b" * 64,
    )
    exact_cell_mm = Fraction(*terrain.cell_size_m.as_integer_ratio()) * 1_000
    epsilon = Fraction(1, 10**9)
    assert authority._sample_terrain_at_exact_witness(
        terrain=terrain,
        witness_mm=(exact_cell_mm - epsilon, 0),
    )[0] == (0, 0)
    assert authority._sample_terrain_at_exact_witness(
        terrain=terrain,
        witness_mm=(exact_cell_mm, 0),
    )[0] == (1, 0)

    extent = (-2, -2, 3, 3)
    assert authority._morton_witness_key(witness_mm=(-1, 0), extent_mm=extent)[0] == 9
    assert authority._morton_witness_key(witness_mm=(0, -1), extent_mm=extent)[0] == 6
    with pytest.raises(ValueError):
        authority._partition_morton_rows(
            rows=((0, "0" * 64, (0, 0)),),
            extent_mm=extent,
            taz_count=2,
        )


def test_routing_key_and_poi_catalog_recompute_nested_identity() -> None:
    authority = importlib.import_module("metroflow.city.scalable_authority")
    routing = "a" * 64
    first = authority.RoutingStaticDependencyKey(
        schema_version=authority.ROUTING_KEY_SCHEMA,
        routing_static_fingerprint=routing,
        routing_policy_version=authority.ROUTING_POLICY,
        access_direction_policy_version=authority.ACCESS_DIRECTION_POLICY,
        closure_capability_policy_version=authority.CLOSURE_CAPABILITY_POLICY,
        source_csr_fingerprint="b" * 64,
    )
    second = replace(first, source_csr_fingerprint="c" * 64, fingerprint="")
    assert first.fingerprint != second.fingerprint
    with pytest.raises(ValueError):
        replace(second, fingerprint=first.fingerprint)

    allocation = "d" * 64
    pois = authority._aggregate_poi_rows(
        block_rows=(
            (7, "a" * 64, (Fraction(1, 3), Fraction(2, 5)), 9, 2, 5, 0, 3),
            (2, "b" * 64, (-1, 0), 4, 1, 0, 7, 0),
        ),
        source_allocation_fingerprint=allocation,
    )
    catalog = authority.V2PoiCatalog(
        schema_version=authority.POI_POLICY,
        pois=pois,
        home_capacity_total=5,
        workplace_capacity_total=7,
        leisure_capacity_total=3,
        source_allocation_fingerprint=allocation,
        source_taz_fingerprint="e" * 64,
    )
    assert len(catalog.fingerprint) == 64
    object.__setattr__(pois[0], "fingerprint", "f" * 64)
    with pytest.raises(ValueError):
        authority.V2PoiCatalog(
            schema_version=authority.POI_POLICY,
            pois=pois,
            home_capacity_total=5,
            workplace_capacity_total=7,
            leisure_capacity_total=3,
            source_allocation_fingerprint=allocation,
            source_taz_fingerprint="e" * 64,
        )


def test_public_boundaries_reject_behavior_subclasses_before_read(
    canonical_scalable_sources: tuple[object, object, object, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = importlib.import_module("metroflow.city.scalable_authority")
    scale, network, blocks, compiled = canonical_scalable_sources
    upstream_calls = 0

    def forbidden_upstream(*args: object, **kwargs: object) -> None:
        nonlocal upstream_calls
        upstream_calls += 1
        raise AssertionError("upstream validator ran for a behavior-bearing input")

    monkeypatch.setattr(
        authority,
        "require_valid_scalable_compiled_topology",
        forbidden_upstream,
        raising=False,
    )

    class EvilScale(CityScaleSpec):
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(f"read EvilScale.{name}")

    class EvilNetwork(type(network)):
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(f"read EvilNetwork.{name}")

    class EvilBlocks(type(blocks)):
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(f"read EvilBlocks.{name}")

    class EvilCompiled(type(compiled)):
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(f"read EvilCompiled.{name}")

    class EvilAuthority(authority.ScalableStaticAuthority):
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(f"read EvilAuthority.{name}")

    class EvilStr(str):
        def __str__(self) -> str:
            raise AssertionError("coerced EvilStr")

    invalid_builds = (
        (object.__new__(EvilScale), "grid_core", 17, network, blocks, compiled),
        (scale, EvilStr("grid_core"), 17, network, blocks, compiled),
        (scale, "grid_core", True, network, blocks, compiled),
        (scale, "grid_core", 17, object.__new__(EvilNetwork), blocks, compiled),
        (scale, "grid_core", 17, network, object.__new__(EvilBlocks), compiled),
        (scale, "grid_core", 17, network, blocks, object.__new__(EvilCompiled)),
    )
    for arguments in invalid_builds:
        with pytest.raises(TypeError):
            authority.build_scalable_static_authority(*arguments)
    with pytest.raises(TypeError):
        authority.require_valid_scalable_static_authority(
            object.__new__(EvilAuthority),
            scale_spec=scale,
            style_id="grid_core",
            seed=17,
            network=network,
            blocks=blocks,
            compiled=compiled,
        )
    assert upstream_calls == 0

    class EvilPoi(authority.V2Poi):
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(f"read EvilPoi.{name}")

    class SwitchingTuple(tuple):
        def __iter__(self):
            raise AssertionError("iterated SwitchingTuple")

    class EvilFraction(Fraction):
        def as_integer_ratio(self) -> tuple[int, int]:
            raise AssertionError("coerced EvilFraction")

    with pytest.raises(TypeError):
        authority.V2PoiCatalog(
            schema_version=authority.POI_POLICY,
            pois=(object.__new__(EvilPoi),),
            home_capacity_total=0,
            workplace_capacity_total=0,
            leisure_capacity_total=0,
            source_allocation_fingerprint="a" * 64,
            source_taz_fingerprint="b" * 64,
        )
    with pytest.raises(TypeError):
        authority._aggregate_poi_rows(
            block_rows=SwitchingTuple(),
            source_allocation_fingerprint="a" * 64,
        )
    with pytest.raises(TypeError):
        authority._raw_capacity_ratios(
            exact_net_area_mm2=EvilFraction(1),
            terrain_intensity=0.5,
            land_use_type=authority.V2LandUseType.RESIDENTIAL,
        )
