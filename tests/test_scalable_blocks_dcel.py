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
        payload["all_sha256"] == "d9ecd1fafb10ff370d8a5662392ba29891bb527823cd88ae977fbb6fc0c54171"
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
        V2EmbeddingEdge: "embedding_edge_id semantic_id source_road_id source_road_semantic_id start_node_id end_node_id start_node_semantic_id end_node_semantic_id points_mm layer facility source_fingerprint",
        V2HalfEdge: "half_edge_id semantic_id embedding_edge_id source_road_id origin_node_id destination_node_id points_mm twin_id next_id prev_id left_face_id",
        V2FaceBoundary: "boundary_id semantic_id half_edge_ids polygon_mm signed_twice_area_mm2 component_id role interior_witness_mm",
        V2Face: "face_id semantic_id is_unbounded role outer_boundary_id hole_boundary_ids unbounded_component_boundary_ids owner_tile interior_witness_mm void_road_semantic_ids void_ramp_semantic_ids source_fingerprint",
        V2RampIncidence: "ramp_incidence_id semantic_id source_road_id source_road_semantic_id start_node_id end_node_id start_node_semantic_id end_node_semantic_id source_fingerprint",
        V2Block: "block_id semantic_id parent_face_id subdivision_schema outer_polygon_mm hole_polygons_mm net_area_mm2 perimeter_squared_terms perimeter_m frontage_road_ids access_node_ids primary_access_node_id interior_witness_mm source_fingerprint",
        V2BlockAccessIndex: "block_to_road_ids block_to_node_ids road_to_block_ids node_to_block_ids primary_access_by_block incidence_visit_count",
        V2FaceTileClip: "clip_id face_id face_semantic_id tile_coordinate diagnostic_polygons_mm exact_net_area_mm2 diagnostic_twice_area_mm2 is_owner",
        ScalableBlockAuthority: "schema_version source_network_fingerprint embedding_policy tile_policy subdivision_schema extent_mm tile_coordinates embedding_edges ramp_incidence half_edges boundaries faces blocks access_index tile_clips vertex_count edge_count face_count component_count euler_lhs euler_rhs boundary_half_edge_occurrence_count fingerprint",
    }
    for record_type, names in layouts.items():
        expected = tuple(names.split())
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


def test_positive_half_square_uses_an_exact_rational_interior_witness() -> None:
    nodes = tuple(
        _node(index, x_mm, y_mm) for index, (x_mm, y_mm) in enumerate(((0, 0), (1, 0), (0, 1)))
    )
    roads = tuple(
        _road(index, left, right, (nodes[left].point_mm, nodes[right].point_mm))
        for index, (left, right) in enumerate(((0, 1), (1, 2), (2, 0)))
    )

    authority = _build_raw(nodes, roads)
    bounded = next(face for face in authority.faces if not face.is_unbounded)

    assert bounded.interior_witness_mm == (Fraction(1, 4), Fraction(1, 2))


def test_boundary_cycles_are_bound_to_the_authoritative_next_permutation() -> None:
    nodes, roads = _square_fixture()
    authority = _build_raw(nodes, roads)
    incoming_by_node = {}
    for half_edge in authority.half_edges:
        incoming_by_node.setdefault(half_edge.destination_node_id, []).append(half_edge)
    left, right = next(
        tuple(incoming)
        for incoming in incoming_by_node.values()
        if len(incoming) == 2 and incoming[0].next_id != incoming[1].next_id
    )
    left_target = authority.half_edges[left.next_id]
    right_target = authority.half_edges[right.next_id]
    replacements = {
        left.half_edge_id: replace(left, next_id=right_target.half_edge_id),
        right.half_edge_id: replace(right, next_id=left_target.half_edge_id),
        left_target.half_edge_id: replace(left_target, prev_id=right.half_edge_id),
        right_target.half_edge_id: replace(right_target, prev_id=left.half_edge_id),
    }
    changed = tuple(
        replacements.get(half_edge.half_edge_id, half_edge) for half_edge in authority.half_edges
    )

    with pytest.raises(ValueError, match="canonical ray rotation"):
        replace(authority, half_edges=changed, fingerprint="")


def test_standalone_authority_reaudits_cross_component_embedding_geometry() -> None:
    first_nodes, first_roads = _square_fixture()
    second_nodes, second_roads = _square_fixture(x0=3_000, node_base=4, road_base=4)
    authority = _build_raw(first_nodes + second_nodes, first_roads + second_roads)
    edge = authority.embedding_edges[0]
    forged_edge = replace(edge, points_mm=((500, -500), (500, 4_000)))
    forged_edges = tuple(
        forged_edge if candidate.embedding_edge_id == edge.embedding_edge_id else candidate
        for candidate in authority.embedding_edges
    )

    with pytest.raises(ValueError, match="embedding geometry audit"):
        replace(authority, embedding_edges=forged_edges, fingerprint="")


def test_nested_annulus_preserves_exact_face_hole_partition() -> None:
    outer_nodes, outer_roads = _square_fixture(size=10_000)
    inner_nodes, inner_roads = _square_fixture(
        x0=3_000, y0=3_000, size=4_000, node_base=4, road_base=4
    )

    canonical = _build_raw(outer_nodes + inner_nodes, outer_roads + inner_roads)
    reversed_input = _build_raw(
        tuple(reversed(outer_nodes + inner_nodes)),
        tuple(reversed(outer_roads + inner_roads)),
    )
    annulus = next(face for face in canonical.faces if face.hole_boundary_ids)
    boundary_by_id = {boundary.boundary_id: boundary for boundary in canonical.boundaries}
    outer = boundary_by_id[annulus.outer_boundary_id]
    hole = boundary_by_id[annulus.hole_boundary_ids[0]]
    unbounded = next(face for face in canonical.faces if face.is_unbounded)

    assert outer.signed_twice_area_mm2 == 200_000_000
    assert hole.signed_twice_area_mm2 == -32_000_000
    assert len(unbounded.unbounded_component_boundary_ids) == 1
    assert canonical.faces == reversed_input.faces
    assert canonical.boundaries == reversed_input.boundaries


@pytest.mark.parametrize(
    ("nodes", "roads", "message"),
    (
        (
            (_node(0, 0, 0), _node(1, 10, 10), _node(2, 0, 10), _node(3, 10, 0)),
            (_road(0, 0, 1, ((0, 0), (10, 10))), _road(1, 2, 3, ((0, 10), (10, 0)))),
            "crossing",
        ),
        (
            (_node(0, 0, 0), _node(1, 10, 0), _node(2, 5, 0), _node(3, 5, 5)),
            (_road(0, 0, 1, ((0, 0), (10, 0))), _road(1, 2, 3, ((5, 0), (5, 5)))),
            "T-touch",
        ),
        (
            (_node(0, 0, 0), _node(1, 10, 0), _node(2, 5, 0), _node(3, 15, 0)),
            (_road(0, 0, 1, ((0, 0), (10, 0))), _road(1, 2, 3, ((5, 0), (15, 0)))),
            "overlap",
        ),
        (
            (_node(0, 0, 0), _node(1, 10, 0)),
            (_road(0, 0, 1, ((1, 0), (10, 0))),),
            "endpoint",
        ),
        (
            (_node(0, 0, 0), _node(1, 10, 0)),
            (_road(0, 0, 1, ((0, 0), (10, 10), (0, 10), (10, 0))),),
            "self-intersection",
        ),
    ),
)
def test_malformed_geometry_fails_closed_without_repair(nodes, roads, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _build_raw(nodes, roads)


def test_internal_cut_edge_rejects_non_simple_bounded_carrier() -> None:
    nodes, roads = _square_fixture()
    nodes = nodes + (_node(4, 500, 500),)
    roads = roads + (_road(4, 0, 4, ((0, 0), (500, 500))),)

    with pytest.raises(ValueError, match="non-simple bounded face carrier"):
        _build_raw(nodes, roads)


def test_bridge_and_ramp_faces_retain_exact_void_roles_and_reasons() -> None:
    bridge_nodes, bridge_roads = _square_fixture(bridge_road_offset=0)
    bridge = _build_raw(bridge_nodes, bridge_roads)
    bridge_face = next(face for face in bridge.faces if not face.is_unbounded)

    ramp_nodes, surface_roads = _square_fixture()
    ramp_nodes = ramp_nodes + (_node(4, -1_000, 0, layer=1),)
    ramp = _road(
        4,
        0,
        4,
        ((0, 0), (-1_000, 0)),
        facility="ramp",
        layer_transition=(0, 1),
    )
    ramp_authority = _build_raw(ramp_nodes, surface_roads + (ramp,))
    ramp_face = next(face for face in ramp_authority.faces if not face.is_unbounded)

    assert {
        "bridge": (
            bridge_face.role,
            bridge_face.void_road_semantic_ids,
            bridge_face.void_ramp_semantic_ids,
        ),
        "ramp": (
            ramp_face.role,
            ramp_face.void_road_semantic_ids,
            ramp_face.void_ramp_semantic_ids,
            tuple(item.source_road_semantic_id for item in ramp_authority.ramp_incidence),
        ),
    } == {
        "bridge": ("BARRIER_VOID", (bridge_roads[0].semantic_id,), ()),
        "ramp": ("INTERCHANGE_VOID", (), (ramp.semantic_id,), (ramp.semantic_id,)),
    }


def test_bridge_or_ramp_void_retains_ordinary_neighbor_and_both_rejects() -> None:
    points = (
        (0, 0),
        (1_000, 0),
        (2_000, 0),
        (0, 1_000),
        (1_000, 1_000),
        (2_000, 1_000),
    )
    nodes = tuple(_node(index, *point) for index, point in enumerate(points))
    pairs = ((0, 1), (1, 2), (3, 4), (4, 5), (0, 3), (1, 4), (2, 5))
    surface = tuple(
        _road(index, left, right, (points[left], points[right]))
        for index, (left, right) in enumerate(pairs)
    )
    bridge_roads = (
        _road(0, 0, 1, (points[0], points[1]), facility="bridge"),
        *surface[1:],
    )
    ramp_node = _node(6, -1_000, 0, layer=1)
    ramp = _road(7, 0, 6, (points[0], ramp_node.point_mm), facility="ramp", layer_transition=(0, 1))
    bridge = _build_raw(nodes, bridge_roads)
    ramp_authority = _build_raw(nodes + (ramp_node,), surface + (ramp,))
    both_error = None
    try:
        _build_raw(nodes + (ramp_node,), bridge_roads + (ramp,))
    except ValueError as error:
        both_error = str(error)

    assert {
        "bridge_roles": sorted(face.role for face in bridge.faces if not face.is_unbounded),
        "ramp_roles": sorted(face.role for face in ramp_authority.faces if not face.is_unbounded),
        "both_error": both_error,
    } == {
        "bridge_roles": ["BARRIER_VOID", "DEVELOPABLE"],
        "ramp_roles": ["DEVELOPABLE", "INTERCHANGE_VOID"],
        "both_error": "bounded face has simultaneous bridge and ramp void reasons",
    }


def test_developable_faces_each_emit_one_exact_block() -> None:
    nodes, roads = _square_fixture()
    authority = _build_raw(nodes, roads)
    face = next(face for face in authority.faces if not face.is_unbounded)

    assert len(authority.blocks) == 1
    block = authority.blocks[0]
    assert (block.parent_face_id, block.subdivision_schema) == (face.face_id, "face_cell_v1")
    assert block.outer_polygon_mm == (
        (0, 0),
        (1_000, 0),
        (1_000, 1_000),
        (0, 1_000),
        (0, 0),
    )
    assert block.hole_polygons_mm == ()
    assert block.net_area_mm2 == Fraction(1_000_000)
    assert block.perimeter_squared_terms == (1_000_000,) * 4
    assert block.frontage_road_ids == (0, 1, 2, 3)
    assert block.access_node_ids == (0, 1, 2, 3)
    assert block.interior_witness_mm == face.interior_witness_mm


def test_primary_access_ties_are_resolved_by_node_semantic_id() -> None:
    nodes, roads = _square_fixture()
    semantic_ids = ("f" * 64, "e" * 64, "d" * 64, "0" * 64)
    nodes = tuple(replace(node, semantic_id=semantic_ids[node.node_id]) for node in nodes)

    authority = _build_raw(nodes, roads)

    assert authority.blocks[0].primary_access_node_id == 3


def test_nested_annulus_block_preserves_hole_area_perimeter_and_incidence() -> None:
    outer_nodes, outer_roads = _square_fixture(size=10_000)
    inner_nodes, inner_roads = _square_fixture(
        x0=3_000, y0=3_000, size=4_000, node_base=4, road_base=4
    )

    authority = _build_raw(outer_nodes + inner_nodes, outer_roads + inner_roads)
    annulus = next(block for block in authority.blocks if block.hole_polygons_mm)

    assert annulus.net_area_mm2 == Fraction(84_000_000)
    assert annulus.hole_polygons_mm == (
        ((3_000, 3_000), (7_000, 3_000), (7_000, 7_000), (3_000, 7_000), (3_000, 3_000)),
    )
    assert annulus.perimeter_squared_terms == (100_000_000,) * 4 + (16_000_000,) * 4
    assert annulus.frontage_road_ids == tuple(range(8))
    assert annulus.access_node_ids == tuple(range(8))


def test_oblique_perimeter_is_symbolic_and_diagnostic_float_is_not_identity() -> None:
    nodes = tuple(
        _node(index, *point) for index, point in enumerate(((0, 0), (7, 0), (7, 3), (2, 3)))
    )
    roads = tuple(
        _road(index, left, right, (nodes[left].point_mm, nodes[right].point_mm))
        for index, (left, right) in enumerate(((0, 1), (1, 2), (2, 3), (3, 0)))
    )

    block = _build_raw(nodes, roads).blocks[0]

    assert block.perimeter_squared_terms == (49, 9, 25, 13)
    assert block.perimeter_m == pytest.approx((7 + 3 + 5 + 13**0.5) / 1_000)
    assert replace(block, perimeter_m=block.perimeter_m + 1.0) == block


def test_access_index_is_exact_bidirectional_and_primary_is_deterministic() -> None:
    points = ((0, 0), (1_000, 0), (2_000, 0), (0, 1_000), (1_000, 1_000), (2_000, 1_000))
    nodes = tuple(_node(index, *point) for index, point in enumerate(points))
    pairs = ((0, 1), (1, 2), (3, 4), (4, 5), (0, 3), (1, 4), (2, 5))
    roads = tuple(
        _road(index, left, right, (points[left], points[right]))
        for index, (left, right) in enumerate(pairs)
    )
    authority = _build_raw(nodes, roads)
    index = authority.access_index
    block_to_roads, block_to_nodes = dict(index.block_to_road_ids), dict(index.block_to_node_ids)
    road_to_blocks, node_to_blocks = dict(index.road_to_block_ids), dict(index.node_to_block_ids)

    assert len(authority.blocks) == 2
    for block in authority.blocks:
        assert block_to_roads[block.block_id] == block.frontage_road_ids
        assert block_to_nodes[block.block_id] == block.access_node_ids
        assert dict(index.primary_access_by_block)[block.block_id] == block.primary_access_node_id
        assert all(block.block_id in road_to_blocks[value] for value in block.frontage_road_ids)
        assert all(block.block_id in node_to_blocks[value] for value in block.access_node_ids)
    assert index.incidence_visit_count == sum(
        len(block.frontage_road_ids) + len(block.access_node_ids) for block in authority.blocks
    )


def test_void_faces_emit_no_blocks_while_ordinary_neighbors_do() -> None:
    points = ((0, 0), (1_000, 0), (2_000, 0), (0, 1_000), (1_000, 1_000), (2_000, 1_000))
    nodes = tuple(_node(index, *point) for index, point in enumerate(points))
    pairs = ((0, 1), (1, 2), (3, 4), (4, 5), (0, 3), (1, 4), (2, 5))
    roads = tuple(
        _road(
            index,
            left,
            right,
            (points[left], points[right]),
            facility="bridge" if index == 0 else "surface",
        )
        for index, (left, right) in enumerate(pairs)
    )

    authority = _build_raw(nodes, roads)
    developable_ids = {face.face_id for face in authority.faces if face.role == "DEVELOPABLE"}

    assert len(authority.blocks) == 1
    assert {block.parent_face_id for block in authority.blocks} == developable_ids
    assert all(
        face.role != "DEVELOPABLE"
        for face in authority.faces
        if face.face_id not in developable_ids
    )


def test_square_tile_ownership_and_raw_tile_domains_fail_closed() -> None:
    nodes, roads = _square_fixture()
    authority = _build_raw(nodes, roads)
    face = next(face for face in authority.faces if not face.is_unbounded)
    errors = []
    for kwargs in (
        {"tile_coordinates": ()},
        {"tile_coordinates": ((0, 0), (0, 0))},
        {"tile_order": ()},
        {"tile_order": ((1, 0),)},
    ):
        try:
            _build_raw(nodes, roads, **kwargs)
        except ValueError as error:
            errors.append(str(error))

    assert (
        face.owner_tile,
        tuple((clip.tile_coordinate, clip.is_owner) for clip in authority.tile_clips),
        errors,
    ) == (
        (0, 0),
        (((0, 0), True),),
        [
            "tile_coordinates must equal the canonical tile domain",
            "tile_coordinates must equal the canonical tile domain",
            "tile_order must be a canonical tile permutation",
            "tile_order must be a canonical tile permutation",
        ],
    )


def test_tile_clip_uses_exact_fraction_area_and_not_rounded_diagnostic_area() -> None:
    points = ((1_999_999, 0), (2_000_001, 0), (2_000_001, 3))
    nodes = tuple(_node(index, *point) for index, point in enumerate(points))
    roads = tuple(
        _road(index, left, right, (points[left], points[right]))
        for index, (left, right) in enumerate(((0, 1), (1, 2), (2, 0)))
    )
    authority = _build_raw(
        nodes,
        roads,
        extent_mm=(0, 3_999_999, 0, 4),
        tile_coordinates=((0, 0), (1, 0)),
        tile_order=((1, 0), (0, 0)),
    )
    face = next(face for face in authority.faces if not face.is_unbounded)
    clips = tuple(clip for clip in authority.tile_clips if clip.face_id == face.face_id)

    assert tuple((clip.tile_coordinate, clip.exact_net_area_mm2) for clip in clips) == (
        ((0, 0), Fraction(3, 4)),
        ((1, 0), Fraction(9, 4)),
    )
    assert face.owner_tile == (0, 0)
    assert sum((clip.exact_net_area_mm2 for clip in clips), Fraction()) == 3
    assert clips[0].diagnostic_twice_area_mm2 != 2 * clips[0].exact_net_area_mm2


def test_concave_clip_splits_disconnected_components_without_zero_width_bridge() -> None:
    points = (
        (0, 0),
        (1_500_000, 0),
        (1_500_000, 3_999_999),
        (1_000_000, 3_999_999),
        (1_000_000, 1_000_000),
        (500_000, 1_000_000),
        (500_000, 3_999_999),
        (0, 3_999_999),
    )
    nodes = tuple(_node(index, *point) for index, point in enumerate(points))
    roads = tuple(
        _road(index, index, (index + 1) % len(points), (point, points[(index + 1) % len(points)]))
        for index, point in enumerate(points)
    )
    authority = _build_raw(
        nodes,
        roads,
        extent_mm=(0, 1_999_999, 0, 3_999_999),
        tile_coordinates=((0, 0), (0, 1)),
    )
    face = next(face for face in authority.faces if not face.is_unbounded)
    clip = next(
        clip
        for clip in authority.tile_clips
        if clip.face_id == face.face_id and clip.tile_coordinate == (0, 1)
    )

    assert len(clip.diagnostic_polygons_mm) == 2
    assert all(
        ring[0] == ring[-1] and len(set(ring[:-1])) == 4 for ring in clip.diagnostic_polygons_mm
    )


def test_nested_annulus_tile_ownership_is_input_order_invariant() -> None:
    outer_nodes, outer_roads = _square_fixture(size=10_000)
    inner_nodes, inner_roads = _square_fixture(
        x0=3_000, y0=3_000, size=4_000, node_base=4, road_base=4
    )
    canonical = _build_raw(outer_nodes + inner_nodes, outer_roads + inner_roads)
    reverse = _build_raw(
        tuple(reversed(outer_nodes + inner_nodes)),
        tuple(reversed(outer_roads + inner_roads)),
        tile_order=((0, 0),),
    )

    assert canonical == reverse
    assert all(face.owner_tile == (0, 0) for face in canonical.faces if not face.is_unbounded)


def test_exact_clips_cover_annulus_across_four_tiles_and_ignore_traversal() -> None:
    outer_nodes, outer_roads = _square_fixture(x0=500_000, y0=500_000, size=3_000_000)
    inner_nodes, inner_roads = _square_fixture(
        x0=1_500_000, y0=1_500_000, size=1_000_000, node_base=4, road_base=4
    )
    tiles = ((0, 0), (1, 0), (0, 1), (1, 1))
    values = outer_nodes + inner_nodes, outer_roads + inner_roads
    canonical = _build_raw(
        *values,
        extent_mm=(0, 3_999_999, 0, 3_999_999),
        tile_coordinates=tiles,
        tile_order=tiles,
    )
    reverse = _build_raw(
        tuple(reversed(values[0])),
        tuple(reversed(values[1])),
        extent_mm=(0, 3_999_999, 0, 3_999_999),
        tile_coordinates=tuple(reversed(tiles)),
        tile_order=tuple(reversed(tiles)),
    )
    annulus = next(block for block in canonical.blocks if block.hole_polygons_mm)
    clips = tuple(clip for clip in canonical.tile_clips if clip.face_id == annulus.parent_face_id)

    assert canonical == reverse
    assert len(clips) == 4 and sum(clip.is_owner for clip in clips) == 1
    assert sum((clip.exact_net_area_mm2 for clip in clips), Fraction()) == annulus.net_area_mm2
    assert next(clip.tile_coordinate for clip in clips if clip.is_owner) == (0, 0)


def test_seam_only_contact_emits_no_clip_and_diagnostic_collapse_rejects() -> None:
    nodes, roads = _square_fixture(x0=1_000_000, size=1_000_000)
    authority = _build_raw(
        nodes,
        roads,
        extent_mm=(0, 3_999_999, 0, 1_999_999),
        tile_coordinates=((0, 0), (1, 0)),
    )
    face = next(face for face in authority.faces if not face.is_unbounded)
    tiny = ((1_999_999, 0), (2_000_003, 0), (2_000_003, 2))
    tiny_nodes = tuple(_node(index, *point) for index, point in enumerate(tiny))
    tiny_roads = tuple(
        _road(index, left, right, (tiny[left], tiny[right]))
        for index, (left, right) in enumerate(((0, 1), (1, 2), (2, 0)))
    )
    error = None
    try:
        _build_raw(
            tiny_nodes,
            tiny_roads,
            extent_mm=(0, 3_999_999, 0, 3),
            tile_coordinates=((0, 0), (1, 0)),
        )
    except ValueError as caught:
        error = str(caught)

    assert (
        tuple(
            clip.tile_coordinate for clip in authority.tile_clips if clip.face_id == face.face_id
        ),
        error,
    ) == (((0, 0),), "positive exact clip collapses in diagnostic integer-mm geometry")


def test_nested_records_and_forged_void_reasons_are_revalidated() -> None:
    import metroflow.city.scalable_blocks as blocks

    nodes, roads = _square_fixture()
    authority = _build_raw(nodes, roads)
    edge, bounded = (
        authority.embedding_edges[0],
        next(face for face in authority.faces if not face.is_unbounded),
    )

    class EvilEdge(blocks.V2EmbeddingEdge):
        pass

    class TupleProxy(tuple):
        pass

    evil = EvilEdge(**{item.name: getattr(edge, item.name) for item in fields(type(edge))})
    nested = object.__new__(blocks.V2EmbeddingEdge)
    for item in fields(type(edge)):
        object.__setattr__(
            nested,
            item.name,
            TupleProxy(edge.points_mm) if item.name == "points_mm" else getattr(edge, item.name),
        )
    boundary = authority.boundaries[bounded.outer_boundary_id]
    false_reason = ("a" * 64,)
    payload = ("bounded", boundary.semantic_id, (), "BARRIER_VOID", false_reason, ())
    forged_semantic = hashlib.sha256(
        blocks.SCHEMA_VERSION.encode()
        + b":face:"
        + json.dumps(payload, separators=(",", ":")).encode()
    ).hexdigest()
    forged_face = replace(
        bounded,
        semantic_id=forged_semantic,
        role="BARRIER_VOID",
        void_road_semantic_ids=false_reason,
    )
    forged_faces = tuple(forged_face if face is bounded else face for face in authority.faces)
    forged_clips = tuple(
        replace(clip, face_semantic_id=forged_semantic) if clip.face_id == bounded.face_id else clip
        for clip in authority.tile_clips
    )
    candidates = (
        ("non-exact authority record", {"embedding_edges": (evil, *authority.embedding_edges[1:])}),
        (
            "nested authority snapshot",
            {"embedding_edges": (nested, *authority.embedding_edges[1:])},
        ),
        (
            "void road reason",
            {
                "faces": forged_faces,
                "blocks": (),
                "access_index": blocks.V2BlockAccessIndex((), (), (), (), (), 0),
                "tile_clips": forged_clips,
            },
        ),
    )
    failures = []
    for label, changes in candidates:
        try:
            replace(authority, **changes, fingerprint="")
        except (TypeError, ValueError) as error:
            assert label in str(error)
        else:
            failures.append(f"DID NOT RAISE {label}")
    assert failures == []
    blocks.validate_scalable_block_authority(authority)


def test_negative_dense_references_never_alias_python_tuple_indices() -> None:
    import metroflow.city.scalable_blocks as blocks

    nodes, roads = _square_fixture()
    authority = _build_raw(nodes, roads)
    candidates = (
        {
            "half_edges": (
                replace(authority.half_edges[0], left_face_id=-1),
                *authority.half_edges[1:],
            )
        },
        {
            "boundaries": (
                replace(authority.boundaries[0], half_edge_ids=(-1,)),
                *authority.boundaries[1:],
            )
        },
        {
            "faces": tuple(
                replace(face, outer_boundary_id=-1) if not face.is_unbounded else face
                for face in authority.faces
            )
        },
        {"blocks": (replace(authority.blocks[0], parent_face_id=-1),)},
        {"tile_clips": (replace(authority.tile_clips[0], face_id=-1),)},
    )
    failures = []
    for changes in candidates:
        try:
            replace(authority, **changes, fingerprint="")
        except ValueError as error:
            assert "out of range" in str(error)
        else:
            failures.append("DID NOT RAISE negative dense reference")
    assert failures == []
    blocks.validate_scalable_block_authority(authority)


def test_semantic_collision_fails_closed() -> None:
    nodes, roads = _square_fixture()
    square = _build_raw(nodes, roads)
    points = ((0, 0), (1_000, 0), (2_000, 0), (0, 1_000), (1_000, 1_000), (2_000, 1_000))
    grid_nodes = tuple(_node(index, *point) for index, point in enumerate(points))
    pairs = ((0, 1), (1, 2), (3, 4), (4, 5), (0, 3), (1, 4), (2, 5))
    grid = _build_raw(
        grid_nodes,
        tuple(
            _road(index, left, right, (points[left], points[right]))
            for index, (left, right) in enumerate(pairs)
        ),
    )
    candidates = (
        (
            square,
            {
                "embedding_edges": (
                    square.embedding_edges[0],
                    replace(
                        square.embedding_edges[1], semantic_id=square.embedding_edges[0].semantic_id
                    ),
                    *square.embedding_edges[2:],
                )
            },
        ),
        (
            grid,
            {
                "blocks": (
                    grid.blocks[0],
                    replace(grid.blocks[1], semantic_id=grid.blocks[0].semantic_id),
                )
            },
        ),
    )
    failures = []
    for authority, changes in candidates:
        try:
            replace(authority, **changes, fingerprint="")
        except ValueError as error:
            assert "semantic collision" in str(error)
        else:
            failures.append("DID NOT RAISE semantic collision")
    assert failures == []


def test_resealed_hole_omission_is_rejected() -> None:
    import metroflow.city.scalable_blocks as blocks

    outer_nodes, outer_roads = _square_fixture(size=10_000)
    inner_nodes, inner_roads = _square_fixture(
        x0=3_000, y0=3_000, size=4_000, node_base=4, road_base=4
    )
    authority = _build_raw(outer_nodes + inner_nodes, outer_roads + inner_roads)
    annulus = next(block for block in authority.blocks if block.hole_polygons_mm)
    forged = replace(
        annulus,
        hole_polygons_mm=(),
        net_area_mm2=Fraction(100_000_000),
        perimeter_squared_terms=annulus.perimeter_squared_terms[:4],
        frontage_road_ids=annulus.frontage_road_ids[:4],
        access_node_ids=annulus.access_node_ids[:4],
    )

    with pytest.raises(ValueError, match="block.*face|hole|canonical"):
        replace(
            authority,
            blocks=tuple(forged if block is annulus else block for block in authority.blocks),
            fingerprint="",
        )
    blocks.validate_scalable_block_authority(authority)
