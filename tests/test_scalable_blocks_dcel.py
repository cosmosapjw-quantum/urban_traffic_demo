from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from fractions import Fraction
import hashlib
import json
import subprocess
import sys

import pytest


SOURCE_FINGERPRINT = hashlib.sha256(b"task3b-source-fixture").hexdigest()


def test_scalable_blocks_module_import_exists() -> None:
    import metroflow.city as city

    assert city.__name__ == "metroflow.city"

    import metroflow.city.scalable_blocks as blocks

    assert blocks.__name__ == "metroflow.city.scalable_blocks"


def test_fresh_scalable_blocks_import_does_not_load_legacy_compilers() -> None:
    legacy_modules = (
        "metroflow.city.block_land_use",
        "metroflow.city.planar_blocks",
        "metroflow.city.planarization",
        "metroflow.city.topology_finalizer",
        "metroflow.city.generator_v2",
    )
    script = f"""
import json
import sys
import metroflow.city.scalable_blocks
print(json.dumps([name for name in {list(legacy_modules)!r} if name in sys.modules]))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == []


def test_lazy_city_exports_preserve_identity_all_and_unknown_attribute() -> None:
    legacy_modules = (
        "metroflow.city.block_land_use",
        "metroflow.city.planar_blocks",
        "metroflow.city.planarization",
        "metroflow.city.topology_finalizer",
        "metroflow.city.generator_v2",
    )
    lazy_exports = {
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
    script = f"""
import hashlib
import importlib
import json
import sys

import metroflow.city.scalable_blocks as blocks
import metroflow.city as city

legacy_modules = {list(legacy_modules)!r}
expected_map = {lazy_exports!r}
payload = {{
    "loaded_before": [name for name in legacy_modules if name in sys.modules],
    "lazy_map": city.__dict__.get("_LAZY_EXPORT_MODULE"),
}}
if not payload["loaded_before"] and payload["lazy_map"] == expected_map:
    identities = {{}}
    from_identities = {{}}
    for name, module_name in expected_map.items():
        direct = getattr(importlib.import_module(module_name, city.__name__), name)
        identities[name] = getattr(city, name) is direct
        namespace = {{}}
        exec(f"from metroflow.city import {{name}}", namespace)
        from_identities[name] = namespace[name] is direct
    from metroflow.city.blueprint import (
        CityBlueprint,
        GeneratedCityMap,
        RealisticCityQualityResult,
    )
    from metroflow.city.realistic_city import generate_city_map
    payload.update(
        identities=identities,
        from_identities=from_identities,
        existing_lazy={{
            "CityBlueprint": city.CityBlueprint is CityBlueprint,
            "GeneratedCityMap": city.GeneratedCityMap is GeneratedCityMap,
            "RealisticCityQualityResult": (
                city.RealisticCityQualityResult is RealisticCityQualityResult
            ),
            "generate_city_map": city.generate_city_map is generate_city_map,
        }},
        unknown=(
            "no error"
            if hasattr(city, "definitely_not_a_city_export")
            else "definitely_not_a_city_export"
        ),
        task3b_exported=any(
            name in city.__all__
            for name in blocks.__dict__.get("__all__", ())
        ),
    )
payload["all_sha256"] = hashlib.sha256(
    json.dumps(city.__all__, separators=(",", ":")).encode()
).hexdigest()
print(json.dumps(payload, sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["lazy_map"] == lazy_exports
    assert payload["loaded_before"] == []
    assert all(payload["identities"].values())
    assert all(payload["from_identities"].values())
    assert all(payload["existing_lazy"].values())
    assert payload["unknown"] == "definitely_not_a_city_export"
    assert not payload["task3b_exported"]
    assert (
        payload["all_sha256"]
        == hashlib.sha256(
            json.dumps(
                [
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
                ],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    )


def test_scalable_blocks_public_api_exists() -> None:
    import metroflow.city.scalable_blocks as blocks
    from metroflow.city.scalable_blocks import (
        ScalableBlockAuthority,
        V2Block,
        V2BlockAccessIndex,
        V2EmbeddingEdge,
        V2Face,
        V2FaceBoundary,
        V2FaceTileClip,
        V2HalfEdge,
        V2RampIncidence,
        build_scalable_block_authority,
        validate_scalable_block_authority,
    )

    assert blocks.__all__ == [
        "ScalableBlockAuthority",
        "V2Block",
        "V2BlockAccessIndex",
        "V2EmbeddingEdge",
        "V2Face",
        "V2FaceBoundary",
        "V2FaceTileClip",
        "V2HalfEdge",
        "V2RampIncidence",
        "build_scalable_block_authority",
        "validate_scalable_block_authority",
    ]
    assert (
        blocks.SCHEMA_VERSION,
        blocks.SUBDIVISION_SCHEMA,
        blocks.EMBEDDING_POLICY,
        blocks.TILE_POLICY,
        blocks.TILE_SIZE_MM,
    ) == (
        "scalable_blocks_dcel_v1",
        "face_cell_v1",
        "layer0_surface_bridge_v1",
        "bounded_exact_fraction_half_open_v1",
        2_000_000,
    )
    assert blocks.PointMM == tuple[int, int]
    assert blocks.FractionPoint == tuple[Fraction, Fraction]
    assert blocks.ExactCoordinateMM == int | Fraction
    assert blocks.ExactPointMM == tuple[int | Fraction, int | Fraction]
    assert all(
        value is not None
        for value in (
            ScalableBlockAuthority,
            V2Block,
            V2BlockAccessIndex,
            V2EmbeddingEdge,
            V2Face,
            V2FaceBoundary,
            V2FaceTileClip,
            V2HalfEdge,
            V2RampIncidence,
            build_scalable_block_authority,
            validate_scalable_block_authority,
        )
    )


def test_authority_records_are_deeply_frozen() -> None:
    from metroflow.city.scalable_blocks import (
        ScalableBlockAuthority,
        V2Block,
        V2BlockAccessIndex,
        V2EmbeddingEdge,
        V2Face,
        V2FaceBoundary,
        V2FaceTileClip,
        V2HalfEdge,
        V2RampIncidence,
    )

    digest = SOURCE_FINGERPRINT
    layouts = {
        V2EmbeddingEdge: (
            "embedding_edge_id",
            "semantic_id",
            "source_road_id",
            "source_road_semantic_id",
            "start_node_id",
            "end_node_id",
            "start_node_semantic_id",
            "end_node_semantic_id",
            "points_mm",
            "layer",
            "facility",
            "source_fingerprint",
        ),
        V2HalfEdge: (
            "half_edge_id",
            "semantic_id",
            "embedding_edge_id",
            "source_road_id",
            "origin_node_id",
            "destination_node_id",
            "points_mm",
            "twin_id",
            "next_id",
            "prev_id",
            "left_face_id",
        ),
        V2FaceBoundary: (
            "boundary_id",
            "semantic_id",
            "half_edge_ids",
            "polygon_mm",
            "signed_twice_area_mm2",
            "component_id",
            "role",
            "interior_witness_mm",
        ),
        V2Face: (
            "face_id",
            "semantic_id",
            "is_unbounded",
            "role",
            "outer_boundary_id",
            "hole_boundary_ids",
            "unbounded_component_boundary_ids",
            "owner_tile",
            "interior_witness_mm",
            "void_road_semantic_ids",
            "void_ramp_semantic_ids",
            "source_fingerprint",
        ),
        V2RampIncidence: (
            "ramp_incidence_id",
            "semantic_id",
            "source_road_id",
            "source_road_semantic_id",
            "start_node_id",
            "end_node_id",
            "start_node_semantic_id",
            "end_node_semantic_id",
            "source_fingerprint",
        ),
        V2Block: (
            "block_id",
            "semantic_id",
            "parent_face_id",
            "subdivision_schema",
            "outer_polygon_mm",
            "hole_polygons_mm",
            "net_area_mm2",
            "perimeter_squared_terms",
            "perimeter_m",
            "frontage_road_ids",
            "access_node_ids",
            "primary_access_node_id",
            "interior_witness_mm",
            "source_fingerprint",
        ),
        V2BlockAccessIndex: (
            "block_to_road_ids",
            "block_to_node_ids",
            "road_to_block_ids",
            "node_to_block_ids",
            "primary_access_by_block",
            "incidence_visit_count",
        ),
        V2FaceTileClip: (
            "clip_id",
            "face_id",
            "face_semantic_id",
            "tile_coordinate",
            "diagnostic_polygons_mm",
            "exact_net_area_mm2",
            "diagnostic_twice_area_mm2",
            "is_owner",
        ),
        ScalableBlockAuthority: (
            "schema_version",
            "source_network_fingerprint",
            "embedding_policy",
            "tile_policy",
            "subdivision_schema",
            "extent_mm",
            "tile_coordinates",
            "embedding_edges",
            "ramp_incidence",
            "half_edges",
            "boundaries",
            "faces",
            "blocks",
            "access_index",
            "tile_clips",
            "vertex_count",
            "edge_count",
            "face_count",
            "component_count",
            "euler_lhs",
            "euler_rhs",
            "boundary_half_edge_occurrence_count",
            "fingerprint",
        ),
    }
    for record_type, expected in layouts.items():
        assert tuple(field.name for field in fields(record_type)) == expected
        assert record_type.__slots__ == expected

    records = (
        V2EmbeddingEdge(
            0, digest, 0, digest, 0, 1, digest, digest, ((0, 0), (1, 0)), 0, "surface", digest
        ),
        V2HalfEdge(0, digest, 0, 0, 0, 1, ((0, 0), (1, 0)), 1, 0, 0, 0),
        V2FaceBoundary(
            0, digest, (0,), ((0, 0), (1, 0), (0, 0)), 0, 0, "OUTER", (Fraction(0), Fraction(0))
        ),
        V2Face(0, digest, True, "UNBOUNDED", None, (), (0,), None, None, (), (), digest),
        V2RampIncidence(0, digest, 0, digest, 0, 1, digest, digest, digest),
        V2Block(
            0,
            digest,
            0,
            "face_cell_v1",
            ((0, 0), (1, 0), (0, 0)),
            (),
            Fraction(0),
            (1, 1),
            2.0,
            (0,),
            (0, 1),
            0,
            (Fraction(0), Fraction(0)),
            digest,
        ),
        V2BlockAccessIndex(
            ((0, (0,)),), ((0, (0, 1)),), ((0, (0,)),), ((0, (0,)), (1, (0,))), ((0, 0),), 4
        ),
        V2FaceTileClip(0, 0, digest, (0, 0), (((0, 0), (1, 0), (0, 0)),), Fraction(0), 0, True),
    )
    for record in records:
        assert not hasattr(record, "__dict__")
        first_field = fields(type(record))[0].name
        with pytest.raises(FrozenInstanceError):
            setattr(record, first_field, getattr(record, first_field))

    class TupleProxy(tuple):
        pass

    with pytest.raises(TypeError, match="nested authority snapshot"):
        replace(records[0], points_mm=TupleProxy(records[0].points_mm))
    with pytest.raises(TypeError, match="nested authority snapshot"):
        replace(records[5], hole_polygons_mm=[])
    with pytest.raises(TypeError, match="nested authority snapshot"):
        replace(records[6], block_to_road_ids={0: (0,)})
    with pytest.raises(TypeError, match="plain integer"):
        replace(records[1], half_edge_id=True)
