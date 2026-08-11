from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from fractions import Fraction
import hashlib
import json
import subprocess
import sys

import pytest


SOURCE_FINGERPRINT = hashlib.sha256(b"task3b-source-fixture").hexdigest()


def _node(node_id: int, x_mm: int, y_mm: int, *, layer: int = 0):
    from metroflow.city.scalable_topology import PhysicalNodeRecord

    return PhysicalNodeRecord(
        node_id,
        hashlib.sha256(f"fixture-node-{node_id}".encode()).hexdigest(),
        x_mm,
        y_mm,
        layer,
        "fixture",
    )


def _road(
    road_id: int,
    start_node_id: int,
    end_node_id: int,
    points_mm: tuple[tuple[int, int], ...],
    *,
    facility: str = "surface",
    layer: int = 0,
    layer_transition: tuple[int, int] | None = None,
):
    from metroflow.city.scalable_topology import (
        FacilityKind,
        PhysicalRoadRecord,
        RoadHierarchy,
    )

    facility_kind = FacilityKind(facility)
    profile_id = (
        "v2:ramp" if facility_kind is FacilityKind.RAMP else f"v2:{facility_kind.value}:local"
    )
    return PhysicalRoadRecord(
        road_id,
        hashlib.sha256(f"fixture-road-{road_id}".encode()).hexdigest(),
        start_node_id,
        end_node_id,
        points_mm,
        RoadHierarchy.LOCAL,
        facility_kind,
        layer,
        frozenset({"forward", "reverse"}),
        layer_transition,
        f"structure-{road_id}" if facility_kind is FacilityKind.BRIDGE else None,
        f"failure-{road_id}" if facility_kind is FacilityKind.BRIDGE else None,
        profile_id,
        "task3b-test",
    )


def _square_fixture(
    *,
    x0: int = 0,
    y0: int = 0,
    size: int = 1_000,
    node_base: int = 0,
    road_base: int = 0,
    bridge_road_offset: int | None = None,
):
    points = (
        (x0, y0),
        (x0 + size, y0),
        (x0 + size, y0 + size),
        (x0, y0 + size),
    )
    nodes = tuple(_node(node_base + index, x_mm, y_mm) for index, (x_mm, y_mm) in enumerate(points))
    roads = tuple(
        _road(
            road_base + offset,
            node_base + left,
            node_base + right,
            (points[left], points[right]),
            facility="bridge" if bridge_road_offset == offset else "surface",
        )
        for offset, (left, right) in enumerate(((0, 1), (1, 2), (2, 3), (3, 0)))
    )
    return nodes, roads


def _build_raw(
    nodes,
    roads,
    *,
    extent_mm=(0, 1_999_999, 0, 1_999_999),
    tile_coordinates=((0, 0),),
    tile_order=None,
):
    from metroflow.city.scalable_blocks import _build_block_authority_from_records

    return _build_block_authority_from_records(
        nodes=tuple(nodes),
        roads=tuple(roads),
        source_network_fingerprint=SOURCE_FINGERPRINT,
        extent_mm=extent_mm,
        tile_coordinates=tuple(tile_coordinates),
        tile_order=tile_order,
    )


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


def test_square_has_total_dcel_and_one_unbounded_face() -> None:
    nodes, roads = _square_fixture()
    roads = (
        _road(0, 0, 1, ((0, 0), (500, 0), (1_000, 0))),
        *roads[1:],
    )
    authority = _build_raw(nodes, roads)

    assert (
        authority.vertex_count,
        authority.edge_count,
        authority.face_count,
        authority.component_count,
        authority.euler_lhs,
        authority.euler_rhs,
    ) == (4, 4, 2, 1, 2, 2)
    assert len(authority.half_edges) == 8
    assert authority.boundary_half_edge_occurrence_count == 8
    assert sum(len(boundary.half_edge_ids) for boundary in authority.boundaries) == 8
    assert {edge.points_mm for edge in authority.embedding_edges} >= {
        ((0, 0), (500, 0), (1_000, 0))
    }
    assert {edge.points_mm for edge in authority.half_edges} >= {
        ((0, 0), (500, 0), (1_000, 0)),
        ((1_000, 0), (500, 0), (0, 0)),
    }
    for half_edge in authority.half_edges:
        twin = authority.half_edges[half_edge.twin_id]
        assert twin.twin_id == half_edge.half_edge_id
        assert authority.half_edges[half_edge.next_id].prev_id == half_edge.half_edge_id
        assert authority.half_edges[half_edge.prev_id].next_id == half_edge.half_edge_id
    unbounded = [face for face in authority.faces if face.is_unbounded]
    bounded = [face for face in authority.faces if not face.is_unbounded]
    assert len(unbounded) == len(bounded) == 1
    assert unbounded[0].outer_boundary_id is None
    assert bounded[0].role == "DEVELOPABLE"


def test_adjacent_and_disconnected_squares_have_exact_euler_faces() -> None:
    adjacent_points = ((0, 0), (1_000, 0), (2_000, 0), (0, 1_000), (1_000, 1_000), (2_000, 1_000))
    adjacent_nodes = tuple(_node(index, *point) for index, point in enumerate(adjacent_points))
    adjacent_pairs = ((0, 1), (1, 2), (3, 4), (4, 5), (0, 3), (1, 4), (2, 5))
    adjacent_roads = tuple(
        _road(index, left, right, (adjacent_points[left], adjacent_points[right]))
        for index, (left, right) in enumerate(adjacent_pairs)
    )
    first_nodes, first_roads = _square_fixture()
    second_nodes, second_roads = _square_fixture(x0=3_000, node_base=4, road_base=4)

    adjacent = _build_raw(adjacent_nodes, adjacent_roads)
    disconnected = _build_raw(first_nodes + second_nodes, first_roads + second_roads)

    assert (
        adjacent.vertex_count,
        adjacent.edge_count,
        adjacent.face_count,
        adjacent.component_count,
        adjacent.euler_lhs,
        adjacent.euler_rhs,
    ) == (6, 7, 3, 1, 2, 2)
    assert (
        disconnected.vertex_count,
        disconnected.edge_count,
        disconnected.face_count,
        disconnected.component_count,
        disconnected.euler_lhs,
        disconnected.euler_rhs,
    ) == (8, 8, 3, 2, 3, 3)
    assert sum(not face.is_unbounded for face in adjacent.faces) == 2
    assert sum(not face.is_unbounded for face in disconnected.faces) == 2


def test_duplicate_ray_kernel_fails_closed() -> None:
    nodes = (_node(0, 0, 0), _node(1, 1_000, 0), _node(2, 2_000, 0))
    roads = (
        _road(0, 0, 1, ((0, 0), (1_000, 0))),
        _road(1, 0, 2, ((0, 0), (2_000, 0))),
    )

    with pytest.raises(ValueError, match="duplicate outgoing ray"):
        _build_raw(nodes, roads)


def test_equal_coordinates_on_an_excluded_layer_do_not_create_dcel_incidence() -> None:
    nodes, roads = _square_fixture()
    extra_nodes = tuple(
        _node(4 + index, node.x_mm, node.y_mm, layer=1) for index, node in enumerate(nodes)
    )
    excluded = tuple(
        _road(
            4 + index,
            4 + index,
            4 + ((index + 1) % 4),
            (extra_nodes[index].point_mm, extra_nodes[(index + 1) % 4].point_mm),
            facility="tunnel",
            layer=1,
        )
        for index in range(4)
    )

    baseline = _build_raw(nodes, roads)
    candidate = _build_raw(nodes + extra_nodes, roads + excluded)

    assert candidate.embedding_edges == baseline.embedding_edges
    assert candidate.half_edges == baseline.half_edges
    assert candidate.boundaries == baseline.boundaries
    assert candidate.faces == baseline.faces
    assert (
        candidate.vertex_count,
        candidate.edge_count,
        candidate.face_count,
        candidate.component_count,
        candidate.euler_lhs,
        candidate.euler_rhs,
        candidate.boundary_half_edge_occurrence_count,
    ) == (
        baseline.vertex_count,
        baseline.edge_count,
        baseline.face_count,
        baseline.component_count,
        baseline.euler_lhs,
        baseline.euler_rhs,
        baseline.boundary_half_edge_occurrence_count,
    )
