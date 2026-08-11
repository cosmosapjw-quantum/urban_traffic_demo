"""Static scalable block and DCEL authority."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field, fields, is_dataclass, replace
from fractions import Fraction
from functools import cmp_to_key
import hashlib
import json
import math

from metroflow.city.scalable_topology import (
    FacilityKind,
    PhysicalNodeRecord,
    PhysicalRoadRecord,
    RoadHierarchy,
    ScalableStreetNetwork,
    audit_physical_records,
)

__all__ = [
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

SCHEMA_VERSION = "scalable_blocks_dcel_v1"
SUBDIVISION_SCHEMA = "face_cell_v1"
EMBEDDING_POLICY = "layer0_surface_bridge_v1"
TILE_POLICY = "bounded_exact_fraction_half_open_v1"
TILE_SIZE_MM = 2_000_000

PointMM = tuple[int, int]
FractionPoint = tuple[Fraction, Fraction]
ExactCoordinateMM = int | Fraction
ExactPointMM = tuple[ExactCoordinateMM, ExactCoordinateMM]


def _plain_int(value: object, name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be a plain integer")
    return value


def _plain_str(value: object, name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{name} must be a plain string")
    return value


def _plain_digest(value: object, name: str, *, allow_empty: bool = False) -> str:
    value = _plain_str(value, name)
    if allow_empty and value == "":
        return value
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _exact_coordinate(value: object, name: str) -> ExactCoordinateMM:
    if type(value) is int or type(value) is Fraction:
        return value
    raise TypeError(f"{name} must be an exact coordinate")


def _exact_point(value: object, name: str) -> ExactPointMM:
    value = _plain_tuple(value, name)
    if len(value) != 2:
        raise TypeError(f"{name} must be an exact point tuple")
    return (
        _exact_coordinate(value[0], f"{name}[0]"),
        _exact_coordinate(value[1], f"{name}[1]"),
    )


def _plain_tuple(value: object, name: str) -> tuple:
    if type(value) is not tuple:
        raise TypeError(f"{name} nested authority snapshot must use an exact tuple")
    return value


def _plain_point(value: object, name: str) -> PointMM:
    value = _plain_tuple(value, name)
    if len(value) != 2:
        raise TypeError(f"{name} must be a two-coordinate plain-integer point")
    return (_plain_int(value[0], f"{name}[0]"), _plain_int(value[1], f"{name}[1]"))


@dataclass(frozen=True, slots=True)
class V2EmbeddingEdge:
    embedding_edge_id: int
    semantic_id: str
    source_road_id: int
    source_road_semantic_id: str
    start_node_id: int
    end_node_id: int
    start_node_semantic_id: str
    end_node_semantic_id: str
    points_mm: tuple[PointMM, ...]
    layer: int
    facility: str
    source_fingerprint: str

    def _validate_types(self) -> None:
        if type(self) is not V2EmbeddingEdge:
            raise TypeError("embedding edge must be an exact V2EmbeddingEdge")
        for name in (
            "embedding_edge_id",
            "source_road_id",
            "start_node_id",
            "end_node_id",
            "layer",
        ):
            _plain_int(getattr(self, name), name)
        for name in (
            "semantic_id",
            "source_road_semantic_id",
            "start_node_semantic_id",
            "end_node_semantic_id",
            "source_fingerprint",
        ):
            _plain_str(getattr(self, name), name)
        _plain_str(self.facility, "facility")
        _plain_tuple(self.points_mm, "points_mm")
        for index, point in enumerate(self.points_mm):
            _plain_point(point, f"points_mm[{index}]")

    def __post_init__(self) -> None:
        self._validate_types()
        for name in (
            "semantic_id",
            "source_road_semantic_id",
            "start_node_semantic_id",
            "end_node_semantic_id",
            "source_fingerprint",
        ):
            _plain_digest(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class V2HalfEdge:
    half_edge_id: int
    semantic_id: str
    embedding_edge_id: int
    source_road_id: int
    origin_node_id: int
    destination_node_id: int
    points_mm: tuple[PointMM, ...]
    twin_id: int
    next_id: int
    prev_id: int
    left_face_id: int

    def _validate_types(self) -> None:
        if type(self) is not V2HalfEdge:
            raise TypeError("half edge must be an exact V2HalfEdge")
        for name in (
            "half_edge_id",
            "embedding_edge_id",
            "source_road_id",
            "origin_node_id",
            "destination_node_id",
            "twin_id",
            "next_id",
            "prev_id",
            "left_face_id",
        ):
            _plain_int(getattr(self, name), name)
        _plain_str(self.semantic_id, "semantic_id")
        _plain_tuple(self.points_mm, "points_mm")
        for index, point in enumerate(self.points_mm):
            _plain_point(point, f"points_mm[{index}]")

    def __post_init__(self) -> None:
        self._validate_types()
        _plain_digest(self.semantic_id, "semantic_id")


@dataclass(frozen=True, slots=True)
class V2FaceBoundary:
    boundary_id: int
    semantic_id: str
    half_edge_ids: tuple[int, ...]
    polygon_mm: tuple[PointMM, ...]
    signed_twice_area_mm2: int
    component_id: int
    role: str
    interior_witness_mm: ExactPointMM

    def _validate_types(self) -> None:
        if type(self) is not V2FaceBoundary:
            raise TypeError("boundary must be an exact V2FaceBoundary")
        for name in ("boundary_id", "signed_twice_area_mm2", "component_id"):
            _plain_int(getattr(self, name), name)
        _plain_str(self.semantic_id, "semantic_id")
        _plain_str(self.role, "role")
        _plain_tuple(self.half_edge_ids, "half_edge_ids")
        for index, value in enumerate(self.half_edge_ids):
            _plain_int(value, f"half_edge_ids[{index}]")
        _plain_tuple(self.polygon_mm, "polygon_mm")
        for index, point in enumerate(self.polygon_mm):
            _plain_point(point, f"polygon_mm[{index}]")
        _exact_point(self.interior_witness_mm, "interior_witness_mm")

    def __post_init__(self) -> None:
        self._validate_types()
        _plain_digest(self.semantic_id, "semantic_id")


@dataclass(frozen=True, slots=True)
class V2Face:
    face_id: int
    semantic_id: str
    is_unbounded: bool
    role: str
    outer_boundary_id: int | None
    hole_boundary_ids: tuple[int, ...]
    unbounded_component_boundary_ids: tuple[int, ...]
    owner_tile: tuple[int, int] | None
    interior_witness_mm: ExactPointMM | None
    void_road_semantic_ids: tuple[str, ...]
    void_ramp_semantic_ids: tuple[str, ...]
    source_fingerprint: str

    def _validate_types(self) -> None:
        if type(self) is not V2Face:
            raise TypeError("face must be an exact V2Face")
        _plain_int(self.face_id, "face_id")
        _plain_str(self.semantic_id, "semantic_id")
        _plain_str(self.source_fingerprint, "source_fingerprint")
        if type(self.is_unbounded) is not bool:
            raise TypeError("is_unbounded must be a plain bool")
        _plain_str(self.role, "role")
        if self.outer_boundary_id is not None:
            _plain_int(self.outer_boundary_id, "outer_boundary_id")
        for name in ("hole_boundary_ids", "unbounded_component_boundary_ids"):
            value = getattr(self, name)
            _plain_tuple(value, name)
            for index, item in enumerate(value):
                _plain_int(item, f"{name}[{index}]")
        if self.owner_tile is not None:
            _plain_point(self.owner_tile, "owner_tile")
        if self.interior_witness_mm is not None:
            _exact_point(self.interior_witness_mm, "interior_witness_mm")
        for name in ("void_road_semantic_ids", "void_ramp_semantic_ids"):
            value = getattr(self, name)
            _plain_tuple(value, name)
            for index, semantic_id in enumerate(value):
                _plain_str(semantic_id, f"{name}[{index}]")

    def __post_init__(self) -> None:
        self._validate_types()
        _plain_digest(self.semantic_id, "semantic_id")
        _plain_digest(self.source_fingerprint, "source_fingerprint")
        for name in ("void_road_semantic_ids", "void_ramp_semantic_ids"):
            for semantic_id in getattr(self, name):
                _plain_digest(semantic_id, name)


@dataclass(frozen=True, slots=True)
class V2RampIncidence:
    ramp_incidence_id: int
    semantic_id: str
    source_road_id: int
    source_road_semantic_id: str
    start_node_id: int
    end_node_id: int
    start_node_semantic_id: str
    end_node_semantic_id: str
    source_fingerprint: str

    def _validate_types(self) -> None:
        if type(self) is not V2RampIncidence:
            raise TypeError("ramp incidence must be an exact V2RampIncidence")
        for name in ("ramp_incidence_id", "source_road_id", "start_node_id", "end_node_id"):
            _plain_int(getattr(self, name), name)
        for name in (
            "semantic_id",
            "source_road_semantic_id",
            "start_node_semantic_id",
            "end_node_semantic_id",
            "source_fingerprint",
        ):
            _plain_str(getattr(self, name), name)

    def __post_init__(self) -> None:
        self._validate_types()
        for name in (
            "semantic_id",
            "source_road_semantic_id",
            "start_node_semantic_id",
            "end_node_semantic_id",
            "source_fingerprint",
        ):
            _plain_digest(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class V2Block:
    block_id: int
    semantic_id: str
    parent_face_id: int
    subdivision_schema: str
    outer_polygon_mm: tuple[PointMM, ...]
    hole_polygons_mm: tuple[tuple[PointMM, ...], ...]
    net_area_mm2: Fraction
    perimeter_squared_terms: tuple[int, ...]
    perimeter_m: float = field(compare=False)
    frontage_road_ids: tuple[int, ...]
    access_node_ids: tuple[int, ...]
    primary_access_node_id: int
    interior_witness_mm: ExactPointMM
    source_fingerprint: str

    def _validate_types(self) -> None:
        if type(self) is not V2Block:
            raise TypeError("block must be an exact V2Block")
        for name in ("block_id", "parent_face_id", "primary_access_node_id"):
            _plain_int(getattr(self, name), name)
        _plain_str(self.semantic_id, "semantic_id")
        _plain_str(self.source_fingerprint, "source_fingerprint")
        _plain_str(self.subdivision_schema, "subdivision_schema")
        _plain_tuple(self.outer_polygon_mm, "outer_polygon_mm")
        for index, point in enumerate(self.outer_polygon_mm):
            _plain_point(point, f"outer_polygon_mm[{index}]")
        _plain_tuple(self.hole_polygons_mm, "hole_polygons_mm")
        for ring_index, polygon in enumerate(self.hole_polygons_mm):
            _plain_tuple(polygon, f"hole_polygons_mm[{ring_index}]")
            for point_index, point in enumerate(polygon):
                _plain_point(point, f"hole_polygons_mm[{ring_index}][{point_index}]")
        if type(self.net_area_mm2) is not Fraction:
            raise TypeError("net_area_mm2 must be an exact Fraction")
        _plain_tuple(self.perimeter_squared_terms, "perimeter_squared_terms")
        for index, value in enumerate(self.perimeter_squared_terms):
            _plain_int(value, f"perimeter_squared_terms[{index}]")
        if type(self.perimeter_m) is not float:
            raise TypeError("perimeter_m must be a plain float")
        for name in ("frontage_road_ids", "access_node_ids"):
            values = _plain_tuple(getattr(self, name), name)
            for index, value in enumerate(values):
                _plain_int(value, f"{name}[{index}]")
        _exact_point(self.interior_witness_mm, "interior_witness_mm")

    def __post_init__(self) -> None:
        self._validate_types()
        _plain_digest(self.semantic_id, "semantic_id")
        _plain_digest(self.source_fingerprint, "source_fingerprint")


@dataclass(frozen=True, slots=True)
class V2BlockAccessIndex:
    block_to_road_ids: tuple[tuple[int, tuple[int, ...]], ...]
    block_to_node_ids: tuple[tuple[int, tuple[int, ...]], ...]
    road_to_block_ids: tuple[tuple[int, tuple[int, ...]], ...]
    node_to_block_ids: tuple[tuple[int, tuple[int, ...]], ...]
    primary_access_by_block: tuple[tuple[int, int], ...]
    incidence_visit_count: int

    def _validate_types(self) -> None:
        if type(self) is not V2BlockAccessIndex:
            raise TypeError("access_index must be an exact V2BlockAccessIndex")
        for name in (
            "block_to_road_ids",
            "block_to_node_ids",
            "road_to_block_ids",
            "node_to_block_ids",
        ):
            rows = _plain_tuple(getattr(self, name), name)
            for row_index, row in enumerate(rows):
                row = _plain_tuple(row, f"{name}[{row_index}]")
                if len(row) != 2:
                    raise TypeError(f"{name}[{row_index}] must contain a key and values")
                _plain_int(row[0], f"{name}[{row_index}][0]")
                values = _plain_tuple(row[1], f"{name}[{row_index}][1]")
                for value_index, value in enumerate(values):
                    _plain_int(value, f"{name}[{row_index}][1][{value_index}]")
        rows = _plain_tuple(self.primary_access_by_block, "primary_access_by_block")
        for row_index, row in enumerate(rows):
            row = _plain_tuple(row, f"primary_access_by_block[{row_index}]")
            if len(row) != 2:
                raise TypeError(f"primary_access_by_block[{row_index}] must contain two integers")
            for value_index, value in enumerate(row):
                _plain_int(value, f"primary_access_by_block[{row_index}][{value_index}]")
        _plain_int(self.incidence_visit_count, "incidence_visit_count")

    def __post_init__(self) -> None:
        self._validate_types()


@dataclass(frozen=True, slots=True)
class V2FaceTileClip:
    clip_id: int
    face_id: int
    face_semantic_id: str
    tile_coordinate: tuple[int, int]
    diagnostic_polygons_mm: tuple[tuple[PointMM, ...], ...]
    exact_net_area_mm2: Fraction
    diagnostic_twice_area_mm2: int
    is_owner: bool

    def _validate_types(self) -> None:
        if type(self) is not V2FaceTileClip:
            raise TypeError("tile clip must be an exact V2FaceTileClip")
        for name in ("clip_id", "face_id", "diagnostic_twice_area_mm2"):
            _plain_int(getattr(self, name), name)
        _plain_str(self.face_semantic_id, "face_semantic_id")
        _plain_point(self.tile_coordinate, "tile_coordinate")
        _plain_tuple(self.diagnostic_polygons_mm, "diagnostic_polygons_mm")
        for ring_index, polygon in enumerate(self.diagnostic_polygons_mm):
            _plain_tuple(polygon, f"diagnostic_polygons_mm[{ring_index}]")
            for point_index, point in enumerate(polygon):
                _plain_point(point, f"diagnostic_polygons_mm[{ring_index}][{point_index}]")
        if type(self.exact_net_area_mm2) is not Fraction:
            raise TypeError("exact_net_area_mm2 must be an exact Fraction")
        if type(self.is_owner) is not bool:
            raise TypeError("is_owner must be a plain bool")

    def __post_init__(self) -> None:
        self._validate_types()
        _plain_digest(self.face_semantic_id, "face_semantic_id")


@dataclass(frozen=True, slots=True)
class ScalableBlockAuthority:
    schema_version: str
    source_network_fingerprint: str
    embedding_policy: str
    tile_policy: str
    subdivision_schema: str
    extent_mm: tuple[int, int, int, int]
    tile_coordinates: tuple[tuple[int, int], ...]
    embedding_edges: tuple[V2EmbeddingEdge, ...]
    ramp_incidence: tuple[V2RampIncidence, ...]
    half_edges: tuple[V2HalfEdge, ...]
    boundaries: tuple[V2FaceBoundary, ...]
    faces: tuple[V2Face, ...]
    blocks: tuple[V2Block, ...]
    access_index: V2BlockAccessIndex
    tile_clips: tuple[V2FaceTileClip, ...]
    vertex_count: int
    edge_count: int
    face_count: int
    component_count: int
    euler_lhs: int
    euler_rhs: int
    boundary_half_edge_occurrence_count: int
    fingerprint: str = ""

    def _validate_types(self) -> None:
        if type(self) is not ScalableBlockAuthority:
            raise TypeError("authority must be an exact ScalableBlockAuthority")
        for name in (
            "schema_version",
            "source_network_fingerprint",
            "embedding_policy",
            "tile_policy",
            "subdivision_schema",
            "fingerprint",
        ):
            _plain_str(getattr(self, name), name)
        extent = _plain_tuple(self.extent_mm, "extent_mm")
        if len(extent) != 4:
            raise TypeError("extent_mm must contain four plain integers")
        for index, value in enumerate(extent):
            _plain_int(value, f"extent_mm[{index}]")
        _plain_tuple(self.tile_coordinates, "tile_coordinates")
        for index, point in enumerate(self.tile_coordinates):
            _plain_point(point, f"tile_coordinates[{index}]")
        collections = (
            ("embedding_edges", self.embedding_edges, V2EmbeddingEdge),
            ("ramp_incidence", self.ramp_incidence, V2RampIncidence),
            ("half_edges", self.half_edges, V2HalfEdge),
            ("boundaries", self.boundaries, V2FaceBoundary),
            ("faces", self.faces, V2Face),
            ("blocks", self.blocks, V2Block),
            ("tile_clips", self.tile_clips, V2FaceTileClip),
        )
        for name, values, expected_type in collections:
            _plain_tuple(values, name)
            for index, value in enumerate(values):
                if type(value) is not expected_type:
                    raise TypeError(f"{name}[{index}] contains a non-exact authority record")
                value._validate_types()
        if type(self.access_index) is not V2BlockAccessIndex:
            raise TypeError("access_index contains a non-exact authority record")
        self.access_index._validate_types()
        for name in (
            "vertex_count",
            "edge_count",
            "face_count",
            "component_count",
            "euler_lhs",
            "euler_rhs",
            "boundary_half_edge_occurrence_count",
        ):
            _plain_int(getattr(self, name), name)

    def __post_init__(self) -> None:
        validate_scalable_block_authority(self)


@dataclass(slots=True)
class _DirectedDraft:
    semantic_id: str
    embedding_edge_id: int
    source_road_id: int
    origin_node_id: int
    destination_node_id: int
    points_mm: tuple[PointMM, ...]
    twin_id: int = -1
    next_id: int = -1
    prev_id: int = -1
    left_face_id: int = -1


@dataclass(slots=True)
class _BoundaryDraft:
    semantic_id: str
    half_edge_ids: tuple[int, ...]
    polygon_mm: tuple[PointMM, ...]
    signed_twice_area_mm2: int
    component_id: int
    role: str
    interior_witness_mm: ExactPointMM


@dataclass(slots=True)
class _FaceDraft:
    semantic_id: str
    is_unbounded: bool
    role: str
    outer_boundary_index: int | None
    hole_boundary_indices: tuple[int, ...]
    unbounded_boundary_indices: tuple[int, ...]
    interior_witness_mm: ExactPointMM | None
    void_road_semantic_ids: tuple[str, ...] = ()
    void_ramp_semantic_ids: tuple[str, ...] = ()


def _digest(tag: str, payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(
        SCHEMA_VERSION.encode() + b":" + tag.encode() + b":" + encoded
    ).hexdigest()


def _require_unique_semantics(values: tuple[str, ...], name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {name} semantic id")


def _embedding_edges(
    nodes: tuple[PhysicalNodeRecord, ...],
    roads: tuple[PhysicalRoadRecord, ...],
    source_fingerprint: str,
) -> tuple[V2EmbeddingEdge, ...]:
    by_id = {node.node_id: node for node in nodes}
    selected: list[tuple[str, PhysicalRoadRecord, PhysicalNodeRecord, PhysicalNodeRecord]] = []
    for road in roads:
        if (
            road.layer != 0
            or road.layer_transition is not None
            or road.facility not in {FacilityKind.SURFACE, FacilityKind.BRIDGE}
        ):
            continue
        start, end = by_id.get(road.start_node_id), by_id.get(road.end_node_id)
        if start is None or end is None:
            raise ValueError("embedding road endpoint is absent")
        semantic_id = _digest(
            "embedding-edge",
            (
                road.semantic_id,
                start.semantic_id,
                end.semantic_id,
                road.points_mm,
                road.layer,
                road.facility.value,
                source_fingerprint,
            ),
        )
        selected.append((semantic_id, road, start, end))
    selected.sort(key=lambda item: item[0])
    _require_unique_semantics(tuple(item[0] for item in selected), "embedding edge")
    return tuple(
        V2EmbeddingEdge(
            embedding_edge_id=index,
            semantic_id=semantic_id,
            source_road_id=road.road_id,
            source_road_semantic_id=road.semantic_id,
            start_node_id=start.node_id,
            end_node_id=end.node_id,
            start_node_semantic_id=start.semantic_id,
            end_node_semantic_id=end.semantic_id,
            points_mm=road.points_mm,
            layer=road.layer,
            facility=road.facility.value,
            source_fingerprint=source_fingerprint,
        )
        for index, (semantic_id, road, start, end) in enumerate(selected)
    )


def _ramp_incidence(
    nodes: tuple[PhysicalNodeRecord, ...],
    roads: tuple[PhysicalRoadRecord, ...],
    source_fingerprint: str,
) -> tuple[V2RampIncidence, ...]:
    by_id = {node.node_id: node for node in nodes}
    selected: list[tuple[str, PhysicalRoadRecord, PhysicalNodeRecord, PhysicalNodeRecord]] = []
    for road in roads:
        if road.facility is not FacilityKind.RAMP:
            continue
        start, end = by_id.get(road.start_node_id), by_id.get(road.end_node_id)
        if start is None or end is None:
            raise ValueError("ramp endpoint is absent")
        semantic_id = _digest(
            "ramp-incidence",
            (
                road.semantic_id,
                start.semantic_id,
                end.semantic_id,
                source_fingerprint,
            ),
        )
        selected.append((semantic_id, road, start, end))
    selected.sort(key=lambda item: item[0])
    _require_unique_semantics(tuple(item[0] for item in selected), "ramp incidence")
    return tuple(
        V2RampIncidence(
            index,
            semantic_id,
            road.road_id,
            road.semantic_id,
            start.node_id,
            end.node_id,
            start.semantic_id,
            end.semantic_id,
            source_fingerprint,
        )
        for index, (semantic_id, road, start, end) in enumerate(selected)
    )


def _ray(half_edge: _DirectedDraft) -> tuple[int, int]:
    left, right = half_edge.points_mm[0], half_edge.points_mm[1]
    return (right[0] - left[0], right[1] - left[1])


def _ray_half(ray: tuple[int, int]) -> int:
    x_value, y_value = ray
    return 0 if y_value > 0 or (y_value == 0 and x_value >= 0) else 1


def _compare_rays(left: tuple[int, int], right: tuple[int, int]) -> int:
    left_half, right_half = _ray_half(left), _ray_half(right)
    if left_half != right_half:
        return -1 if left_half < right_half else 1
    cross = left[0] * right[1] - left[1] * right[0]
    if cross:
        return -1 if cross > 0 else 1
    left_length = left[0] * left[0] + left[1] * left[1]
    right_length = right[0] * right[0] + right[1] * right[1]
    return (left_length > right_length) - (left_length < right_length)


def _same_ray(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] * right[1] == left[1] * right[0] and left[0] * right[0] + left[1] * right[1] > 0


def _directed_embedding(edges: tuple[V2EmbeddingEdge, ...]) -> list[_DirectedDraft]:
    directed: list[_DirectedDraft] = []
    for edge in edges:
        for direction, origin, destination, points in (
            ("forward", edge.start_node_id, edge.end_node_id, edge.points_mm),
            ("reverse", edge.end_node_id, edge.start_node_id, tuple(reversed(edge.points_mm))),
        ):
            directed.append(
                _DirectedDraft(
                    _digest("half-edge", (edge.semantic_id, direction)),
                    edge.embedding_edge_id,
                    edge.source_road_id,
                    origin,
                    destination,
                    points,
                )
            )
    directed.sort(key=lambda item: item.semantic_id)
    _require_unique_semantics(tuple(item.semantic_id for item in directed), "half edge")
    by_edge: dict[int, list[int]] = defaultdict(list)
    for half_edge_id, half_edge in enumerate(directed):
        by_edge[half_edge.embedding_edge_id].append(half_edge_id)
    for pair in by_edge.values():
        if len(pair) != 2:
            raise ValueError("embedding edge must emit exactly two half-edges")
        directed[pair[0]].twin_id = pair[1]
        directed[pair[1]].twin_id = pair[0]

    outgoing: dict[int, list[int]] = defaultdict(list)
    for half_edge_id, half_edge in enumerate(directed):
        outgoing[half_edge.origin_node_id].append(half_edge_id)
    for half_edge_ids in outgoing.values():
        half_edge_ids.sort(
            key=cmp_to_key(
                lambda left, right: _compare_rays(_ray(directed[left]), _ray(directed[right]))
            )
        )
        for left, right in zip(half_edge_ids, half_edge_ids[1:]):
            if _same_ray(_ray(directed[left]), _ray(directed[right])):
                raise ValueError("duplicate outgoing ray")
    for half_edge_id, half_edge in enumerate(directed):
        destination_order = outgoing[half_edge.destination_node_id]
        twin_position = destination_order.index(half_edge.twin_id)
        half_edge.next_id = destination_order[(twin_position - 1) % len(destination_order)]
    for half_edge_id, half_edge in enumerate(directed):
        next_edge = directed[half_edge.next_id]
        if next_edge.prev_id != -1:
            raise ValueError("half-edge next permutation is not injective")
        next_edge.prev_id = half_edge_id
    return directed


def _embedding_components(edges: tuple[V2EmbeddingEdge, ...]) -> tuple[dict[int, int], int]:
    adjacency: dict[int, set[int]] = defaultdict(set)
    for edge in edges:
        adjacency[edge.start_node_id].add(edge.end_node_id)
        adjacency[edge.end_node_id].add(edge.start_node_id)
    component_by_node: dict[int, int] = {}
    for origin in sorted(adjacency):
        if origin in component_by_node:
            continue
        component_id = len(set(component_by_node.values()))
        component_by_node[origin] = component_id
        queue = deque((origin,))
        while queue:
            node_id = queue.popleft()
            for neighbor in sorted(adjacency[node_id]):
                if neighbor not in component_by_node:
                    component_by_node[neighbor] = component_id
                    queue.append(neighbor)
    return component_by_node, len(set(component_by_node.values()))


def _cycle_polygon(
    half_edge_ids: tuple[int, ...], directed: list[_DirectedDraft]
) -> tuple[PointMM, ...]:
    polygon: list[PointMM] = []
    for half_edge_id in half_edge_ids:
        points = directed[half_edge_id].points_mm
        if not polygon:
            polygon.extend(points)
        elif polygon[-1] == points[0]:
            polygon.extend(points[1:])
        else:
            polygon.extend(points)
    if polygon and polygon[-1] != polygon[0]:
        polygon.append(polygon[0])
    return tuple(polygon)


def _signed_area2(polygon: tuple[ExactPointMM, ...]) -> ExactCoordinateMM:
    return sum(left[0] * right[1] - right[0] * left[1] for left, right in zip(polygon, polygon[1:]))


def _point_status(point: ExactPointMM, polygon: tuple[ExactPointMM, ...]) -> int:
    inside = False
    point_x, point_y = point
    for left, right in zip(polygon, polygon[1:]):
        cross = (right[0] - left[0]) * (point_y - left[1]) - (right[1] - left[1]) * (
            point_x - left[0]
        )
        if (
            cross == 0
            and min(left[0], right[0]) <= point_x <= max(left[0], right[0])
            and min(left[1], right[1]) <= point_y <= max(left[1], right[1])
        ):
            return 0
        if (left[1] > point_y) == (right[1] > point_y):
            continue
        intersection_x = Fraction(left[0]) + (point_y - left[1]) * (right[0] - left[0]) / (
            right[1] - left[1]
        )
        if intersection_x > point_x:
            inside = not inside
    return 1 if inside else -1


def _strictly_contains_ring(outer: tuple[PointMM, ...], inner: tuple[PointMM, ...]) -> bool:
    return all(_point_status(point, outer) == 1 for point in inner[:-1])


def _group_oriented_rings(
    boundaries: list[_BoundaryDraft],
) -> tuple[tuple[int, ...], dict[int, tuple[int, ...]], tuple[int, ...]]:
    positive = tuple(
        index for index, boundary in enumerate(boundaries) if boundary.signed_twice_area_mm2 > 0
    )
    negative = tuple(
        index for index, boundary in enumerate(boundaries) if boundary.signed_twice_area_mm2 < 0
    )
    holes_by_outer: dict[int, list[int]] = defaultdict(list)
    unbounded: list[int] = []
    for inner_index in negative:
        inner = boundaries[inner_index]
        candidates = [
            outer_index
            for outer_index in positive
            if abs(boundaries[outer_index].signed_twice_area_mm2) > abs(inner.signed_twice_area_mm2)
            and _strictly_contains_ring(boundaries[outer_index].polygon_mm, inner.polygon_mm)
        ]
        if not candidates:
            unbounded.append(inner_index)
            continue
        owner = min(
            candidates,
            key=lambda index: (
                abs(boundaries[index].signed_twice_area_mm2),
                boundaries[index].semantic_id,
            ),
        )
        holes_by_outer[owner].append(inner_index)
    return (
        positive,
        {
            index: tuple(sorted(values, key=lambda value: boundaries[value].semantic_id))
            for index, values in holes_by_outer.items()
        },
        tuple(sorted(unbounded, key=lambda index: boundaries[index].semantic_id)),
    )


def _canonical_polygon(polygon: tuple[PointMM, ...], *, clockwise: bool) -> tuple[PointMM, ...]:
    points = polygon[:-1] if polygon and polygon[0] == polygon[-1] else polygon
    if not points:
        return ()
    closed = (*points, points[0])
    if (_signed_area2(closed) < 0) != clockwise:
        points = tuple(reversed(points))
    chosen = min(points[index:] + points[:index] for index in range(len(points)))
    return (*chosen, chosen[0])


def _interior_witness(
    outer: tuple[PointMM, ...], holes: tuple[tuple[PointMM, ...], ...]
) -> ExactPointMM:
    vertices = outer[:-1]
    centroid = (
        round(Fraction(sum(point[0] for point in vertices), len(vertices))),
        round(Fraction(sum(point[1] for point in vertices), len(vertices))),
    )
    candidates: set[PointMM] = {centroid}
    ordinates = sorted(
        {point[1] for point in vertices} | {point[1] for hole in holes for point in hole[:-1]}
    )
    for ordinate in ordinates:
        candidates.update(((centroid[0], ordinate - 1), (centroid[0], ordinate + 1)))
    for lower, upper in zip(ordinates, ordinates[1:]):
        if upper - lower > 1:
            candidates.add((centroid[0], (lower + upper) // 2))
    for left, right in zip(outer, outer[1:]):
        midpoint = ((left[0] + right[0]) // 2, (left[1] + right[1]) // 2)
        delta_x, delta_y = right[0] - left[0], right[1] - left[1]
        candidates.add(
            (
                midpoint[0] + (0 if delta_y == 0 else -1 if delta_y > 0 else 1),
                midpoint[1] + (0 if delta_x == 0 else 1 if delta_x > 0 else -1),
            )
        )
    valid = [
        point
        for point in candidates
        if _point_status(point, outer) == 1
        and all(_point_status(point, hole) == -1 for hole in holes)
    ]
    if valid:
        return min(valid)

    rational_candidates: list[ExactPointMM] = []
    for ordinate in (
        Fraction(lower + upper, 2)
        for lower, upper in zip(ordinates, ordinates[1:])
        if lower < upper
    ):
        intersections: set[Fraction] = set()
        for ring in (outer, *holes):
            for left, right in zip(ring, ring[1:]):
                if (left[1] > ordinate) == (right[1] > ordinate):
                    continue
                intersections.add(
                    Fraction(left[0])
                    + (ordinate - left[1]) * (right[0] - left[0]) / (right[1] - left[1])
                )
        ordered = sorted(intersections)
        for left_x, right_x in zip(ordered, ordered[1:]):
            point = ((left_x + right_x) / 2, ordinate)
            if (
                left_x < right_x
                and _point_status(point, outer) == 1
                and all(_point_status(point, hole) == -1 for hole in holes)
            ):
                rational_candidates.append(point)
    if not rational_candidates:
        raise ValueError("bounded face has no canonical exact interior witness")
    return min(rational_candidates)


def _trace_boundaries(
    directed: list[_DirectedDraft], component_by_node: dict[int, int]
) -> list[_BoundaryDraft]:
    boundaries: list[_BoundaryDraft] = []
    visited: set[int] = set()
    for start in range(len(directed)):
        if start in visited:
            continue
        cycle: list[int] = []
        current = start
        while current not in visited:
            visited.add(current)
            cycle.append(current)
            current = directed[current].next_id
        if current != start:
            raise ValueError("half-edge permutation does not close its boundary")
        half_edge_ids = tuple(cycle)
        polygon = _cycle_polygon(half_edge_ids, directed)
        area = _signed_area2(polygon)
        if area == 0:
            raise ValueError("zero-area boundary carrier")
        if area > 0 and (len(polygon) < 4 or len(set(polygon[:-1])) != len(polygon) - 1):
            raise ValueError("non-simple bounded face carrier")
        if area:
            polygon = _canonical_polygon(polygon, clockwise=area < 0)
            area = _signed_area2(polygon)
        witness_points = polygon[:-1] if len(polygon) > 1 else polygon
        divisor = max(1, len(witness_points))
        witness = (
            _interior_witness(polygon, ())
            if area > 0
            else (
                Fraction(sum(point[0] for point in witness_points), divisor),
                Fraction(sum(point[1] for point in witness_points), divisor),
            )
        )
        semantic_id = _digest(
            "boundary",
            tuple(directed[index].semantic_id for index in half_edge_ids),
        )
        boundaries.append(
            _BoundaryDraft(
                semantic_id,
                half_edge_ids,
                polygon,
                area,
                component_by_node[directed[start].origin_node_id],
                "OUTER" if area > 0 else "UNBOUNDED_COMPONENT",
                witness,
            )
        )
    _require_unique_semantics(tuple(item.semantic_id for item in boundaries), "boundary")
    return boundaries


def _reject_geometry_audit(
    nodes: tuple[PhysicalNodeRecord, ...], roads: tuple[PhysicalRoadRecord, ...]
) -> None:
    audit = audit_physical_records(nodes, roads)
    violations = (
        ("endpoint", audit.endpoint_anchor_mismatch_count),
        ("self-intersection", audit.self_intersection_count),
        ("crossing", audit.same_layer_proper_crossing_count),
        ("overlap", audit.collinear_overlap_count),
        ("T-touch", audit.t_touch_count),
        ("nonadjacent weld", audit.nonadjacent_weld_count),
        ("duplicate road", audit.duplicate_road_count),
        ("different-layer junction", audit.different_layer_false_junction_count),
    )
    for label, count in violations:
        if count:
            raise ValueError(f"embedding geometry audit {label}: {count}")


def _validate_embedding_geometry(authority: ScalableBlockAuthority) -> None:
    node_values: dict[int, tuple[str, PointMM, int]] = {}
    for edge in authority.embedding_edges:
        for node_id, semantic_id, point in (
            (edge.start_node_id, edge.start_node_semantic_id, edge.points_mm[0]),
            (edge.end_node_id, edge.end_node_semantic_id, edge.points_mm[-1]),
        ):
            value = (semantic_id, point, edge.layer)
            if node_id in node_values and node_values[node_id] != value:
                raise ValueError("embedding geometry audit endpoint authority mismatch")
            node_values[node_id] = value
    nodes = tuple(
        PhysicalNodeRecord(node_id, semantic_id, point[0], point[1], layer, "task3b")
        for node_id, (semantic_id, point, layer) in sorted(node_values.items())
    )
    roads = tuple(
        PhysicalRoadRecord(
            edge.source_road_id,
            edge.source_road_semantic_id,
            edge.start_node_id,
            edge.end_node_id,
            edge.points_mm,
            RoadHierarchy.LOCAL,
            FacilityKind(edge.facility),
            edge.layer,
            frozenset({"forward", "reverse"}),
            None,
            None,
            None,
            f"v2:{edge.facility}:local",
            "task3b-authority",
        )
        for edge in authority.embedding_edges
    )
    _reject_geometry_audit(nodes, roads)


def _validate_embedding_permutations(authority: ScalableBlockAuthority) -> None:
    half_edges = authority.half_edges
    outgoing: dict[int, list[int]] = defaultdict(list)
    for half_edge_id, half_edge in enumerate(half_edges):
        if half_edge.half_edge_id != half_edge_id:
            raise ValueError("canonical ray rotation dense ID mismatch")
        if not 0 <= half_edge.twin_id < len(half_edges):
            raise ValueError("canonical ray rotation twin out of range")
        twin = half_edges[half_edge.twin_id]
        if twin.twin_id != half_edge_id or twin.points_mm != tuple(reversed(half_edge.points_mm)):
            raise ValueError("canonical ray rotation twin mismatch")
        outgoing[half_edge.origin_node_id].append(half_edge_id)
    for half_edge_ids in outgoing.values():
        half_edge_ids.sort(
            key=cmp_to_key(
                lambda left, right: _compare_rays(_ray(half_edges[left]), _ray(half_edges[right]))
            )
        )
        for left, right in zip(half_edge_ids, half_edge_ids[1:]):
            if _same_ray(_ray(half_edges[left]), _ray(half_edges[right])):
                raise ValueError("duplicate outgoing ray")
    for half_edge_id, half_edge in enumerate(half_edges):
        destination_order = outgoing[half_edge.destination_node_id]
        twin_position = destination_order.index(half_edge.twin_id)
        expected_next = destination_order[(twin_position - 1) % len(destination_order)]
        if half_edge.next_id != expected_next:
            raise ValueError("canonical ray rotation mismatch")
        if not 0 <= half_edge.prev_id < len(half_edges):
            raise ValueError("canonical ray rotation prev out of range")
        if half_edges[half_edge.next_id].prev_id != half_edge_id:
            raise ValueError("canonical ray rotation inverse mismatch")


def _validate_extent(extent: object) -> tuple[int, int, int, int]:
    if type(extent) is not tuple or len(extent) != 4:
        raise ValueError("extent must contain four integer-mm values")
    result = tuple(_plain_int(value, "extent") for value in extent)
    if result[0] >= result[1] or result[2] >= result[3]:
        raise ValueError("extent must be ordered")
    return result


def _canonical_tile_domain(
    extent: tuple[int, int, int, int],
) -> tuple[tuple[int, int], ...]:
    minimum_x, maximum_x, minimum_y, maximum_y = extent
    return tuple(
        (tile_x, tile_y)
        for tile_y in range(
            math.floor(minimum_y / TILE_SIZE_MM),
            math.floor(maximum_y / TILE_SIZE_MM) + 1,
        )
        for tile_x in range(
            math.floor(minimum_x / TILE_SIZE_MM),
            math.floor(maximum_x / TILE_SIZE_MM) + 1,
        )
    )


def _tile_rectangle(
    coordinate: tuple[int, int], extent: tuple[int, int, int, int]
) -> tuple[int, int, int, int] | None:
    tile_x, tile_y = coordinate
    left = max(extent[0], tile_x * TILE_SIZE_MM)
    right = min(extent[1], (tile_x + 1) * TILE_SIZE_MM)
    bottom = max(extent[2], tile_y * TILE_SIZE_MM)
    top = min(extent[3], (tile_y + 1) * TILE_SIZE_MM)
    return None if left >= right or bottom >= top else (left, right, bottom, top)


def _clip_walk(
    polygon: tuple[PointMM, ...], rectangle: tuple[int, int, int, int]
) -> tuple[FractionPoint, ...]:
    vertices = [(Fraction(x_value), Fraction(y_value)) for x_value, y_value in polygon[:-1]]
    left, right, bottom, top = rectangle
    for axis, bound, keep_greater in (
        (0, Fraction(left), True),
        (0, Fraction(right), False),
        (1, Fraction(bottom), True),
        (1, Fraction(top), False),
    ):
        if not vertices:
            break
        output: list[FractionPoint] = []
        previous = vertices[-1]
        previous_inside = previous[axis] >= bound if keep_greater else previous[axis] <= bound
        for current in vertices:
            current_inside = current[axis] >= bound if keep_greater else current[axis] <= bound
            if current_inside != previous_inside:
                delta = current[axis] - previous[axis]
                parameter = (bound - previous[axis]) / delta
                output.append(
                    (
                        previous[0] + parameter * (current[0] - previous[0]),
                        previous[1] + parameter * (current[1] - previous[1]),
                    )
                )
            if current_inside:
                output.append(current)
            previous, previous_inside = current, current_inside
        vertices = output
    cleaned: list[FractionPoint] = []
    for point in vertices:
        if not cleaned or cleaned[-1] != point:
            cleaned.append(point)
    if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
        cleaned.pop()
    return () if len(cleaned) < 3 else (*cleaned, cleaned[0])


def _point_on_fraction_segment(
    point: FractionPoint, start: FractionPoint, end: FractionPoint
) -> bool:
    return (
        (end[0] - start[0]) * (point[1] - start[1]) == (end[1] - start[1]) * (point[0] - start[0])
        and min(start[0], end[0]) <= point[0] <= max(start[0], end[0])
        and min(start[1], end[1]) <= point[1] <= max(start[1], end[1])
    )


def _split_clipped_walk(
    walk: tuple[FractionPoint, ...],
) -> tuple[tuple[FractionPoint, ...], ...]:
    if not walk:
        return ()
    vertices = tuple(sorted(set(walk[:-1])))
    directed: Counter[tuple[FractionPoint, FractionPoint]] = Counter()
    for start, end in zip(walk, walk[1:]):
        on_segment = [point for point in vertices if _point_on_fraction_segment(point, start, end)]
        delta_x, delta_y = end[0] - start[0], end[1] - start[1]
        if abs(delta_x) >= abs(delta_y):
            on_segment.sort(
                key=lambda point: (point[0] - start[0]) / delta_x if delta_x else Fraction()
            )
        else:
            on_segment.sort(key=lambda point: (point[1] - start[1]) / delta_y)
        for left, right in zip(on_segment, on_segment[1:]):
            if left != right:
                directed[(left, right)] += 1
    for edge in tuple(directed):
        reverse = (edge[1], edge[0])
        cancellation = min(directed[edge], directed.get(reverse, 0))
        directed[edge] -= cancellation
        directed[reverse] -= cancellation
    remaining = Counter({edge: count for edge, count in directed.items() if count})
    outgoing: Counter[FractionPoint] = Counter()
    incoming: Counter[FractionPoint] = Counter()
    for (start, end), count in remaining.items():
        outgoing[start] += count
        incoming[end] += count
    if outgoing != incoming:
        raise ValueError("clipped polygon components have inconsistent incidence")
    cycles: list[tuple[FractionPoint, ...]] = []
    while remaining:
        start, current = min(edge for edge, count in remaining.items() if count)
        cycle = [start, current]
        remaining[(start, current)] -= 1
        if remaining[(start, current)] == 0:
            del remaining[(start, current)]
        while current != start:
            choices = sorted(
                end for (origin, end), count in remaining.items() if origin == current and count
            )
            if not choices:
                raise ValueError("clipped polygon component is not closed")
            following = choices[0]
            remaining[(current, following)] -= 1
            if remaining[(current, following)] == 0:
                del remaining[(current, following)]
            current = following
            cycle.append(current)
        if len(set(cycle[:-1])) < 3 or _signed_area2(tuple(cycle)) == 0:
            continue
        body = tuple(cycle[:-1])
        if _signed_area2(tuple(cycle)) < 0:
            body = tuple(reversed(body))
        chosen = min(body[index:] + body[:index] for index in range(len(body)))
        cycles.append((*chosen, chosen[0]))
    return tuple(sorted(cycles))


def _clip_ring_parts(
    polygon: tuple[PointMM, ...], rectangle: tuple[int, int, int, int]
) -> tuple[tuple[FractionPoint, ...], ...]:
    return _split_clipped_walk(_clip_walk(polygon, rectangle))


def _fraction_area(polygon: tuple[FractionPoint, ...]) -> Fraction:
    return Fraction(abs(_signed_area2(polygon)), 2) if polygon else Fraction()


def _diagnostic_ring(polygon: tuple[FractionPoint, ...]) -> tuple[PointMM, ...]:
    points: list[PointMM] = []
    for x_value, y_value in polygon[:-1]:
        point = (round(x_value), round(y_value))
        if not points or points[-1] != point:
            points.append(point)
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    if len(set(points)) < 3:
        raise ValueError("positive exact clip collapses in diagnostic integer-mm geometry")
    ring = _canonical_polygon((*points, points[0]), clockwise=False)
    if _signed_area2(ring) == 0:
        raise ValueError("positive exact clip collapses in diagnostic integer-mm geometry")
    return ring


def _build_tile_clips(
    faces: tuple[V2Face, ...],
    boundaries: tuple[V2FaceBoundary, ...],
    tiles: tuple[tuple[int, int], ...],
    tile_order: tuple[tuple[int, int], ...],
    extent: tuple[int, int, int, int],
) -> tuple[tuple[V2FaceTileClip, ...], dict[int, tuple[int, int]]]:
    boundary_by_id = {boundary.boundary_id: boundary for boundary in boundaries}
    pending = []
    owner_by_face: dict[int, tuple[int, int]] = {}
    for face in faces:
        if face.is_unbounded:
            continue
        outer = boundary_by_id[face.outer_boundary_id].polygon_mm
        holes = tuple(boundary_by_id[index].polygon_mm for index in face.hole_boundary_ids)
        positive_tiles: list[tuple[int, int]] = []
        covered_area = Fraction()
        for coordinate in tile_order:
            rectangle = _tile_rectangle(coordinate, extent)
            if rectangle is None:
                continue
            outer_parts = _clip_ring_parts(outer, rectangle)
            outer_area = sum((_fraction_area(part) for part in outer_parts), Fraction())
            hole_parts = tuple(_clip_ring_parts(hole, rectangle) for hole in holes)
            net_area = outer_area - sum(
                (_fraction_area(part) for parts in hole_parts for part in parts), Fraction()
            )
            if net_area < 0:
                raise ValueError("hole clip area exceeds outer clip area")
            if net_area == 0:
                continue
            covered_area += net_area
            diagnostic_outer = tuple(_diagnostic_ring(part) for part in outer_parts)
            diagnostic_holes = tuple(
                _diagnostic_ring(part) for parts in hole_parts for part in parts
            )
            diagnostic_area = sum(abs(_signed_area2(part)) for part in diagnostic_outer) - sum(
                abs(_signed_area2(part)) for part in diagnostic_holes
            )
            pending.append(
                (
                    face,
                    coordinate,
                    (*diagnostic_outer, *diagnostic_holes),
                    net_area,
                    diagnostic_area,
                )
            )
            positive_tiles.append(coordinate)
        if not positive_tiles:
            raise ValueError("bounded face has no positive-area canonical tile clip")
        face_area = Fraction(
            abs(_signed_area2(outer)) - sum(abs(_signed_area2(hole)) for hole in holes), 2
        )
        if covered_area != face_area:
            raise ValueError("clip area conservation mismatch")
        owner_by_face[face.face_id] = min(positive_tiles)
    pending.sort(key=lambda item: (item[0].semantic_id, item[1], item[2]))
    return (
        tuple(
            V2FaceTileClip(
                index,
                face.face_id,
                face.semantic_id,
                coordinate,
                diagnostic,
                net_area,
                diagnostic_area,
                coordinate == owner_by_face[face.face_id],
            )
            for index, (face, coordinate, diagnostic, net_area, diagnostic_area) in enumerate(
                pending
            )
        ),
        owner_by_face,
    )


def _build_blocks(
    faces: tuple[V2Face, ...],
    boundaries: tuple[V2FaceBoundary, ...],
    half_edges: tuple[V2HalfEdge, ...],
    embedding_edges: tuple[V2EmbeddingEdge, ...],
    source_fingerprint: str,
) -> tuple[V2Block, ...]:
    boundary_by_id = {boundary.boundary_id: boundary for boundary in boundaries}
    node_semantic_by_id: dict[int, str] = {}
    for edge in embedding_edges:
        node_semantic_by_id[edge.start_node_id] = edge.start_node_semantic_id
        node_semantic_by_id[edge.end_node_id] = edge.end_node_semantic_id
    drafts = []
    for face in faces:
        if face.role != "DEVELOPABLE" or face.outer_boundary_id is None:
            continue
        outer_boundary = boundary_by_id[face.outer_boundary_id]
        hole_boundaries = tuple(
            boundary_by_id[boundary_id] for boundary_id in face.hole_boundary_ids
        )
        outer_polygon = _canonical_polygon(outer_boundary.polygon_mm, clockwise=False)
        hole_polygons = tuple(
            sorted(
                (
                    _canonical_polygon(boundary.polygon_mm, clockwise=False)
                    for boundary in hole_boundaries
                )
            )
        )
        polygons = (outer_polygon, *hole_polygons)
        perimeter_squared_terms = tuple(
            (right[0] - left[0]) ** 2 + (right[1] - left[1]) ** 2
            for polygon in polygons
            for left, right in zip(polygon, polygon[1:])
        )
        boundary_half_edge_ids = tuple(
            half_edge_id
            for boundary in (outer_boundary, *hole_boundaries)
            for half_edge_id in boundary.half_edge_ids
        )
        frontage_road_ids = tuple(
            sorted({half_edges[index].source_road_id for index in boundary_half_edge_ids})
        )
        access_node_ids = tuple(
            sorted(
                {
                    node_id
                    for index in boundary_half_edge_ids
                    for node_id in (
                        half_edges[index].origin_node_id,
                        half_edges[index].destination_node_id,
                    )
                }
            )
        )
        primary_access_node_id = min(
            access_node_ids,
            key=lambda node_id: (node_semantic_by_id[node_id], node_id),
        )
        net_area = Fraction(
            abs(outer_boundary.signed_twice_area_mm2)
            - sum(abs(boundary.signed_twice_area_mm2) for boundary in hole_boundaries),
            2,
        )
        semantic_id = _digest(
            "block",
            (
                face.semantic_id,
                SUBDIVISION_SCHEMA,
                outer_polygon,
                hole_polygons,
                (net_area.numerator, net_area.denominator),
                perimeter_squared_terms,
                frontage_road_ids,
                tuple(node_semantic_by_id[node_id] for node_id in access_node_ids),
                node_semantic_by_id[primary_access_node_id],
                source_fingerprint,
            ),
        )
        drafts.append(
            (
                semantic_id,
                face.face_id,
                outer_polygon,
                hole_polygons,
                net_area,
                perimeter_squared_terms,
                frontage_road_ids,
                access_node_ids,
                primary_access_node_id,
                face.interior_witness_mm,
            )
        )
    drafts.sort(key=lambda item: item[0])
    _require_unique_semantics(tuple(item[0] for item in drafts), "block")
    return tuple(
        V2Block(
            block_id,
            semantic_id,
            parent_face_id,
            SUBDIVISION_SCHEMA,
            outer_polygon,
            hole_polygons,
            net_area,
            perimeter_squared_terms,
            sum(math.sqrt(value) for value in perimeter_squared_terms) / 1_000.0,
            frontage_road_ids,
            access_node_ids,
            primary_access_node_id,
            interior_witness,
            source_fingerprint,
        )
        for block_id, (
            semantic_id,
            parent_face_id,
            outer_polygon,
            hole_polygons,
            net_area,
            perimeter_squared_terms,
            frontage_road_ids,
            access_node_ids,
            primary_access_node_id,
            interior_witness,
        ) in enumerate(drafts)
    )


def _build_access_index(blocks: tuple[V2Block, ...]) -> V2BlockAccessIndex:
    road_to_blocks: dict[int, list[int]] = defaultdict(list)
    node_to_blocks: dict[int, list[int]] = defaultdict(list)
    incidence_visit_count = 0
    for block in blocks:
        for road_id in block.frontage_road_ids:
            road_to_blocks[road_id].append(block.block_id)
            incidence_visit_count += 1
        for node_id in block.access_node_ids:
            node_to_blocks[node_id].append(block.block_id)
            incidence_visit_count += 1
    return V2BlockAccessIndex(
        tuple((block.block_id, block.frontage_road_ids) for block in blocks),
        tuple((block.block_id, block.access_node_ids) for block in blocks),
        tuple((key, tuple(sorted(values))) for key, values in sorted(road_to_blocks.items())),
        tuple((key, tuple(sorted(values))) for key, values in sorted(node_to_blocks.items())),
        tuple((block.block_id, block.primary_access_node_id) for block in blocks),
        incidence_visit_count,
    )


def _build_block_authority_from_records(
    *,
    nodes,
    roads,
    source_network_fingerprint,
    extent_mm,
    tile_coordinates,
    tile_order=None,
) -> ScalableBlockAuthority:
    if type(nodes) is not tuple or any(type(node) is not PhysicalNodeRecord for node in nodes):
        raise TypeError("nodes must contain exact PhysicalNodeRecord values")
    if type(roads) is not tuple or any(type(road) is not PhysicalRoadRecord for road in roads):
        raise TypeError("roads must contain exact PhysicalRoadRecord values")
    source_fingerprint = _plain_digest(source_network_fingerprint, "source_network_fingerprint")
    extent = _validate_extent(extent_mm)
    canonical_tiles = _canonical_tile_domain(extent)
    if (
        type(tile_coordinates) is not tuple
        or any(
            type(coordinate) is not tuple
            or len(coordinate) != 2
            or any(type(value) is not int for value in coordinate)
            for coordinate in tile_coordinates
        )
        or len(tile_coordinates) != len(canonical_tiles)
        or set(tile_coordinates) != set(canonical_tiles)
    ):
        raise ValueError("tile_coordinates must equal the canonical tile domain")
    traversal = canonical_tiles if tile_order is None else tile_order
    if (
        type(traversal) is not tuple
        or any(
            type(coordinate) is not tuple
            or len(coordinate) != 2
            or any(type(value) is not int for value in coordinate)
            for coordinate in traversal
        )
        or len(traversal) != len(canonical_tiles)
        or set(traversal) != set(canonical_tiles)
    ):
        raise ValueError("tile_order must be a canonical tile permutation")
    selected_roads = tuple(
        road
        for road in roads
        if road.layer == 0
        and road.layer_transition is None
        and road.facility in {FacilityKind.SURFACE, FacilityKind.BRIDGE}
    )
    selected_node_ids = {
        node_id for road in selected_roads for node_id in (road.start_node_id, road.end_node_id)
    }
    edges = _embedding_edges(nodes, roads, source_fingerprint)
    ramp_records = _ramp_incidence(nodes, roads, source_fingerprint)
    if any(
        not (extent[0] <= point[0] <= extent[1] and extent[2] <= point[1] <= extent[3])
        for edge in edges
        for point in edge.points_mm
    ):
        raise ValueError("embedding point outside authority extent")
    directed = _directed_embedding(edges)
    _reject_geometry_audit(
        tuple(node for node in nodes if node.node_id in selected_node_ids),
        selected_roads,
    )
    component_by_node, component_count = _embedding_components(edges)
    boundary_drafts = _trace_boundaries(directed, component_by_node)

    positive_indices, holes_by_outer, unbounded_indices = _group_oriented_rings(boundary_drafts)
    for index in positive_indices:
        boundary_drafts[index].role = "OUTER"
    for values in holes_by_outer.values():
        for index in values:
            boundary_drafts[index].role = "HOLE"
    for index in unbounded_indices:
        boundary_drafts[index].role = "UNBOUNDED_COMPONENT"
    face_drafts = [
        _FaceDraft(
            _digest(
                "face",
                (
                    "unbounded",
                    tuple(
                        sorted(boundary_drafts[index].semantic_id for index in unbounded_indices)
                    ),
                ),
            ),
            True,
            "UNBOUNDED",
            None,
            (),
            unbounded_indices,
            None,
        )
    ]
    for index in positive_indices:
        hole_indices = holes_by_outer.get(index, ())
        witness = _interior_witness(
            boundary_drafts[index].polygon_mm,
            tuple(boundary_drafts[value].polygon_mm for value in hole_indices),
        )
        boundary_drafts[index].interior_witness_mm = witness
        face_drafts.append(
            _FaceDraft(
                _digest(
                    "face",
                    (
                        "bounded",
                        boundary_drafts[index].semantic_id,
                        tuple(boundary_drafts[value].semantic_id for value in hole_indices),
                    ),
                ),
                False,
                "DEVELOPABLE",
                index,
                hole_indices,
                (),
                witness,
            )
        )
    bridge_semantic_by_road_id = {
        edge.source_road_id: edge.source_road_semantic_id
        for edge in edges
        if edge.facility == FacilityKind.BRIDGE.value
    }
    for face in face_drafts:
        if face.is_unbounded or face.outer_boundary_index is None:
            continue
        boundary_indices = (face.outer_boundary_index, *face.hole_boundary_indices)
        half_edge_ids = {
            half_edge_id
            for boundary_index in boundary_indices
            for half_edge_id in boundary_drafts[boundary_index].half_edge_ids
        }
        road_ids = {directed[index].source_road_id for index in half_edge_ids}
        node_ids = {
            node_id
            for index in half_edge_ids
            for node_id in (
                directed[index].origin_node_id,
                directed[index].destination_node_id,
            )
        }
        face.void_road_semantic_ids = tuple(
            sorted(
                semantic_id
                for road_id, semantic_id in bridge_semantic_by_road_id.items()
                if road_id in road_ids
            )
        )
        face.void_ramp_semantic_ids = tuple(
            sorted(
                ramp.source_road_semantic_id
                for ramp in ramp_records
                if ramp.start_node_id in node_ids or ramp.end_node_id in node_ids
            )
        )
        if face.void_road_semantic_ids and face.void_ramp_semantic_ids:
            raise ValueError("bounded face has simultaneous bridge and ramp void reasons")
        if face.void_road_semantic_ids:
            face.role = "BARRIER_VOID"
        elif face.void_ramp_semantic_ids:
            face.role = "INTERCHANGE_VOID"
        face.semantic_id = _digest(
            "face",
            (
                "bounded",
                boundary_drafts[face.outer_boundary_index].semantic_id,
                tuple(boundary_drafts[index].semantic_id for index in face.hole_boundary_indices),
                face.role,
                face.void_road_semantic_ids,
                face.void_ramp_semantic_ids,
            ),
        )
    face_drafts.sort(key=lambda face: face.semantic_id)
    _require_unique_semantics(tuple(face.semantic_id for face in face_drafts), "face")

    boundary_order = sorted(
        range(len(boundary_drafts)), key=lambda index: boundary_drafts[index].semantic_id
    )
    boundary_id_by_index = {old: new for new, old in enumerate(boundary_order)}
    face_id_by_boundary: dict[int, int] = {}
    for face_id, face in enumerate(face_drafts):
        for boundary_index in face.unbounded_boundary_indices:
            face_id_by_boundary[boundary_index] = face_id
        if face.outer_boundary_index is not None:
            face_id_by_boundary[face.outer_boundary_index] = face_id
        for boundary_index in face.hole_boundary_indices:
            face_id_by_boundary[boundary_index] = face_id
    boundary_index_by_half_edge = {
        half_edge_id: boundary_index
        for boundary_index, boundary in enumerate(boundary_drafts)
        for half_edge_id in boundary.half_edge_ids
    }
    for half_edge_id, half_edge in enumerate(directed):
        half_edge.left_face_id = face_id_by_boundary[boundary_index_by_half_edge[half_edge_id]]

    half_edges = tuple(
        V2HalfEdge(
            half_edge_id,
            half_edge.semantic_id,
            half_edge.embedding_edge_id,
            half_edge.source_road_id,
            half_edge.origin_node_id,
            half_edge.destination_node_id,
            half_edge.points_mm,
            half_edge.twin_id,
            half_edge.next_id,
            half_edge.prev_id,
            half_edge.left_face_id,
        )
        for half_edge_id, half_edge in enumerate(directed)
    )
    boundaries = tuple(
        V2FaceBoundary(
            boundary_id,
            boundary_drafts[old_index].semantic_id,
            boundary_drafts[old_index].half_edge_ids,
            boundary_drafts[old_index].polygon_mm,
            boundary_drafts[old_index].signed_twice_area_mm2,
            boundary_drafts[old_index].component_id,
            boundary_drafts[old_index].role,
            boundary_drafts[old_index].interior_witness_mm,
        )
        for boundary_id, old_index in enumerate(boundary_order)
    )
    faces = tuple(
        V2Face(
            face_id,
            face.semantic_id,
            face.is_unbounded,
            face.role,
            None
            if face.outer_boundary_index is None
            else boundary_id_by_index[face.outer_boundary_index],
            tuple(boundary_id_by_index[index] for index in face.hole_boundary_indices),
            tuple(boundary_id_by_index[index] for index in face.unbounded_boundary_indices),
            None,
            face.interior_witness_mm,
            face.void_road_semantic_ids,
            face.void_ramp_semantic_ids,
            source_fingerprint,
        )
        for face_id, face in enumerate(face_drafts)
    )
    tile_clips, owner_by_face = _build_tile_clips(
        faces, boundaries, canonical_tiles, traversal, extent
    )
    faces = tuple(replace(face, owner_tile=owner_by_face.get(face.face_id)) for face in faces)
    blocks = _build_blocks(faces, boundaries, half_edges, edges, source_fingerprint)
    access_index = _build_access_index(blocks)
    vertex_count = len(
        {node_id for edge in edges for node_id in (edge.start_node_id, edge.end_node_id)}
    )
    edge_count, face_count = len(edges), len(faces)
    euler_lhs, euler_rhs = vertex_count - edge_count + face_count, 1 + component_count
    if euler_lhs != euler_rhs:
        raise ValueError("DCEL Euler authority mismatch")
    return ScalableBlockAuthority(
        SCHEMA_VERSION,
        source_fingerprint,
        EMBEDDING_POLICY,
        TILE_POLICY,
        SUBDIVISION_SCHEMA,
        extent,
        canonical_tiles,
        edges,
        ramp_records,
        half_edges,
        boundaries,
        faces,
        blocks,
        access_index,
        tile_clips,
        vertex_count,
        edge_count,
        face_count,
        component_count,
        euler_lhs,
        euler_rhs,
        len(half_edges),
    )


def build_scalable_block_authority(
    network: ScalableStreetNetwork,
) -> ScalableBlockAuthority:
    if type(network) is not ScalableStreetNetwork:
        raise TypeError("network must be an exact ScalableStreetNetwork")
    admitted = ScalableStreetNetwork(
        **{item.name: getattr(network, item.name) for item in fields(ScalableStreetNetwork)}
    )
    return _build_block_authority_from_records(
        nodes=admitted.nodes,
        roads=admitted.roads,
        source_network_fingerprint=admitted.fingerprint,
        extent_mm=admitted.extent_mm,
        tile_coordinates=admitted.tile_coordinates,
    )


def _record_payload(value: object) -> object:
    if type(value) is Fraction:
        return ("Fraction", value.numerator, value.denominator)
    if type(value) is tuple:
        return tuple(_record_payload(item) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return (
            type(value).__name__,
            tuple(
                (item.name, _record_payload(getattr(value, item.name)))
                for item in fields(value)
                if not (
                    (type(value) is V2Block and item.name == "perimeter_m")
                    or (type(value) is ScalableBlockAuthority and item.name == "fingerprint")
                )
            ),
        )
    if value is None or type(value) in {bool, int, str, float}:
        return value
    raise TypeError("authority fingerprint contains a non-canonical value")


def _authority_fingerprint(authority: ScalableBlockAuthority) -> str:
    return _digest("authority", _record_payload(authority))


def _validate_authority_structure(authority: ScalableBlockAuthority) -> None:
    authority._validate_types()
    _plain_digest(authority.source_network_fingerprint, "source_network_fingerprint")
    _plain_digest(authority.fingerprint, "fingerprint", allow_empty=True)
    if (
        authority.schema_version != SCHEMA_VERSION
        or authority.embedding_policy != EMBEDDING_POLICY
        or authority.tile_policy != TILE_POLICY
        or authority.subdivision_schema != SUBDIVISION_SCHEMA
    ):
        raise ValueError("authority policy or schema mismatch")
    extent = _validate_extent(authority.extent_mm)
    if authority.tile_coordinates != _canonical_tile_domain(extent):
        raise ValueError("tile_coordinates must equal the canonical tile domain")

    collections = (
        ("embedding edge", authority.embedding_edges, V2EmbeddingEdge, "embedding_edge_id"),
        ("ramp incidence", authority.ramp_incidence, V2RampIncidence, "ramp_incidence_id"),
        ("half edge", authority.half_edges, V2HalfEdge, "half_edge_id"),
        ("boundary", authority.boundaries, V2FaceBoundary, "boundary_id"),
        ("face", authority.faces, V2Face, "face_id"),
        ("block", authority.blocks, V2Block, "block_id"),
        ("tile clip", authority.tile_clips, V2FaceTileClip, "clip_id"),
    )
    for label, values, expected_type, identifier in collections:
        for dense_id, value in enumerate(values):
            value.__post_init__()
            if getattr(value, identifier) != dense_id:
                raise ValueError(f"{label} dense ID mismatch")
    authority.access_index.__post_init__()

    semantic_groups = (
        ("embedding edge", authority.embedding_edges),
        ("ramp incidence", authority.ramp_incidence),
        ("half edge", authority.half_edges),
        ("boundary", authority.boundaries),
        ("face", authority.faces),
        ("block", authority.blocks),
    )
    for label, values in semantic_groups:
        semantic_ids = tuple(value.semantic_id for value in values)
        if len(semantic_ids) != len(set(semantic_ids)):
            raise ValueError(f"semantic collision in {label} records")
        if label != "face" and semantic_ids != tuple(sorted(semantic_ids)):
            raise ValueError(f"{label} semantic order mismatch")

    edge_count, half_edge_count = len(authority.embedding_edges), len(authority.half_edges)
    boundary_count, face_count = len(authority.boundaries), len(authority.faces)
    block_count = len(authority.blocks)
    for edge in authority.embedding_edges:
        if edge.source_road_id < 0 or edge.start_node_id < 0 or edge.end_node_id < 0:
            raise ValueError("embedding edge reference out of range")
        if edge.layer != 0 or edge.facility not in {
            FacilityKind.SURFACE.value,
            FacilityKind.BRIDGE.value,
        }:
            raise ValueError("embedding edge violates layer/facility policy")
        if edge.source_fingerprint != authority.source_network_fingerprint:
            raise ValueError("embedding edge source fingerprint mismatch")
    source_road_ids = {edge.source_road_id for edge in authority.embedding_edges}
    source_road_semantics = {edge.source_road_semantic_id for edge in authority.embedding_edges}
    node_semantic_by_id: dict[int, str] = {}
    node_id_by_semantic: dict[str, int] = {}
    for edge in authority.embedding_edges:
        for node_id, semantic_id in (
            (edge.start_node_id, edge.start_node_semantic_id),
            (edge.end_node_id, edge.end_node_semantic_id),
        ):
            node_semantic_by_id.setdefault(node_id, semantic_id)
            node_id_by_semantic.setdefault(semantic_id, node_id)
    for ramp in authority.ramp_incidence:
        if (
            ramp.start_node_id == ramp.end_node_id
            or ramp.source_road_id in source_road_ids
            or ramp.source_road_semantic_id in source_road_semantics
        ):
            raise ValueError("ramp incidence authority mismatch")
        source_road_ids.add(ramp.source_road_id)
        source_road_semantics.add(ramp.source_road_semantic_id)
        for node_id, semantic_id in (
            (ramp.start_node_id, ramp.start_node_semantic_id),
            (ramp.end_node_id, ramp.end_node_semantic_id),
        ):
            if (
                node_semantic_by_id.get(node_id, semantic_id) != semantic_id
                or node_id_by_semantic.get(semantic_id, node_id) != node_id
            ):
                raise ValueError("ramp incidence authority mismatch")
            node_semantic_by_id[node_id] = semantic_id
            node_id_by_semantic[semantic_id] = node_id
        if ramp.source_road_id < 0 or ramp.start_node_id < 0 or ramp.end_node_id < 0:
            raise ValueError("ramp incidence reference out of range")
        if ramp.source_fingerprint != authority.source_network_fingerprint:
            raise ValueError("ramp incidence source fingerprint mismatch")
    for half_edge in authority.half_edges:
        if not 0 <= half_edge.embedding_edge_id < edge_count:
            raise ValueError("half edge embedding reference out of range")
        if any(
            not 0 <= value < half_edge_count
            for value in (half_edge.twin_id, half_edge.next_id, half_edge.prev_id)
        ):
            raise ValueError("half edge permutation reference out of range")
        if not 0 <= half_edge.left_face_id < face_count:
            raise ValueError("half edge face reference out of range")
        if (
            min(half_edge.source_road_id, half_edge.origin_node_id, half_edge.destination_node_id)
            < 0
        ):
            raise ValueError("half edge source reference out of range")
    for boundary in authority.boundaries:
        if not boundary.half_edge_ids or any(
            not 0 <= value < half_edge_count for value in boundary.half_edge_ids
        ):
            raise ValueError("boundary half edge reference out of range")
        if not 0 <= boundary.component_id < authority.component_count:
            raise ValueError("boundary component reference out of range")
        if boundary.role not in {"OUTER", "HOLE", "UNBOUNDED_COMPONENT"}:
            raise ValueError("boundary role mismatch")
    for face in authority.faces:
        references = (
            (() if face.outer_boundary_id is None else (face.outer_boundary_id,))
            + face.hole_boundary_ids
            + face.unbounded_component_boundary_ids
        )
        if any(not 0 <= value < boundary_count for value in references):
            raise ValueError("face boundary reference out of range")
        if face.owner_tile is not None and face.owner_tile not in authority.tile_coordinates:
            raise ValueError("face owner tile reference out of range")
        if face.role not in {"UNBOUNDED", "DEVELOPABLE", "BARRIER_VOID", "INTERCHANGE_VOID"}:
            raise ValueError("face role mismatch")
        if face.source_fingerprint != authority.source_network_fingerprint:
            raise ValueError("face source fingerprint mismatch")
    for block in authority.blocks:
        if not 0 <= block.parent_face_id < face_count:
            raise ValueError("block parent face reference out of range")
        if (
            min((*block.frontage_road_ids, *block.access_node_ids, block.primary_access_node_id))
            < 0
        ):
            raise ValueError("block source reference out of range")
        if block.subdivision_schema != SUBDIVISION_SCHEMA:
            raise ValueError("block subdivision schema mismatch")
        if block.source_fingerprint != authority.source_network_fingerprint:
            raise ValueError("block source fingerprint mismatch")
    for clip in authority.tile_clips:
        if not 0 <= clip.face_id < face_count:
            raise ValueError("tile clip face reference out of range")
        if clip.tile_coordinate not in authority.tile_coordinates:
            raise ValueError("tile clip tile reference out of range")

    index = authority.access_index
    for mapping_name in ("block_to_road_ids", "block_to_node_ids", "primary_access_by_block"):
        mapping = getattr(index, mapping_name)
        if tuple(item[0] for item in mapping) != tuple(range(block_count)):
            raise ValueError("access index block reference out of range")
    for mapping_name in ("road_to_block_ids", "node_to_block_ids"):
        mapping = getattr(index, mapping_name)
        if any(
            key < 0 or any(not 0 <= value < block_count for value in values)
            for key, values in mapping
        ):
            raise ValueError("access index reverse reference out of range")
    if any(
        any(value < 0 for value in values)
        for mapping in (index.block_to_road_ids, index.block_to_node_ids)
        for _, values in mapping
    ) or any(value < 0 for _, value in index.primary_access_by_block):
        raise ValueError("access index source reference out of range")

    vertices = {
        node_id
        for edge in authority.embedding_edges
        for node_id in (edge.start_node_id, edge.end_node_id)
    }
    component_count = _embedding_components(authority.embedding_edges)[1]
    occurrences = sum(len(boundary.half_edge_ids) for boundary in authority.boundaries)
    expected = (
        len(vertices),
        edge_count,
        face_count,
        component_count,
        len(vertices) - edge_count + face_count,
        1 + component_count,
        occurrences,
    )
    actual = (
        authority.vertex_count,
        authority.edge_count,
        authority.face_count,
        authority.component_count,
        authority.euler_lhs,
        authority.euler_rhs,
        authority.boundary_half_edge_occurrence_count,
    )
    if actual != expected or half_edge_count != 2 * edge_count or occurrences != half_edge_count:
        raise ValueError("DCEL count or Euler authority mismatch")


def _validate_record_semantics(authority: ScalableBlockAuthority) -> None:
    for edge in authority.embedding_edges:
        expected = _digest(
            "embedding-edge",
            (
                edge.source_road_semantic_id,
                edge.start_node_semantic_id,
                edge.end_node_semantic_id,
                edge.points_mm,
                edge.layer,
                edge.facility,
                edge.source_fingerprint,
            ),
        )
        if edge.semantic_id != expected:
            raise ValueError("embedding edge semantic mismatch")
    for ramp in authority.ramp_incidence:
        expected = _digest(
            "ramp-incidence",
            (
                ramp.source_road_semantic_id,
                ramp.start_node_semantic_id,
                ramp.end_node_semantic_id,
                ramp.source_fingerprint,
            ),
        )
        if ramp.semantic_id != expected:
            raise ValueError("ramp incidence semantic mismatch")
    for half_edge in authority.half_edges:
        edge = authority.embedding_edges[half_edge.embedding_edge_id]
        if half_edge.source_road_id != edge.source_road_id or (
            half_edge.origin_node_id,
            half_edge.destination_node_id,
            half_edge.points_mm,
        ) not in {
            (edge.start_node_id, edge.end_node_id, edge.points_mm),
            (edge.end_node_id, edge.start_node_id, tuple(reversed(edge.points_mm))),
        }:
            raise ValueError("half edge does not match embedding edge")
        direction = "forward" if half_edge.points_mm == edge.points_mm else "reverse"
        if half_edge.semantic_id != _digest("half-edge", (edge.semantic_id, direction)):
            raise ValueError("half edge semantic mismatch")


def _validate_canonical_face_partition(authority: ScalableBlockAuthority) -> None:
    components, _ = _embedding_components(authority.embedding_edges)
    drafts = _trace_boundaries(list(authority.half_edges), components)
    positive, holes_by_outer, unbounded = _group_oriented_rings(drafts)
    for index in positive:
        drafts[index].role = "OUTER"
        drafts[index].interior_witness_mm = _interior_witness(
            drafts[index].polygon_mm,
            tuple(drafts[value].polygon_mm for value in holes_by_outer.get(index, ())),
        )
    for values in holes_by_outer.values():
        for index in values:
            drafts[index].role = "HOLE"
    for index in unbounded:
        drafts[index].role = "UNBOUNDED_COMPONENT"
    drafts.sort(key=lambda boundary: boundary.semantic_id)
    expected_boundaries = tuple(
        V2FaceBoundary(
            boundary_id,
            boundary.semantic_id,
            boundary.half_edge_ids,
            boundary.polygon_mm,
            boundary.signed_twice_area_mm2,
            boundary.component_id,
            boundary.role,
            boundary.interior_witness_mm,
        )
        for boundary_id, boundary in enumerate(drafts)
    )
    if len(authority.boundaries) != len(expected_boundaries):
        raise ValueError("canonical boundary cycle reconstruction mismatch")
    for actual, expected in zip(authority.boundaries, expected_boundaries):
        names = tuple(item.name for item in fields(actual) if item.name != "interior_witness_mm")
        if tuple(getattr(actual, name) for name in names) != tuple(
            getattr(expected, name) for name in names
        ):
            raise ValueError("canonical boundary cycle reconstruction mismatch")
        if actual.interior_witness_mm != expected.interior_witness_mm:
            raise ValueError("boundary witness reconstruction mismatch")

    positive, holes_by_outer, unbounded = _group_oriented_rings(drafts)

    face_specs = [
        (
            _digest(
                "face",
                ("unbounded", tuple(sorted(drafts[index].semantic_id for index in unbounded))),
            ),
            True,
            "UNBOUNDED",
            None,
            (),
            unbounded,
            None,
            (),
            (),
        )
    ]
    bridge_by_road = {
        edge.source_road_id: edge.source_road_semantic_id
        for edge in authority.embedding_edges
        if edge.facility == FacilityKind.BRIDGE.value
    }
    for outer_index in positive:
        hole_indices = holes_by_outer.get(outer_index, ())
        boundary_indices = (outer_index, *hole_indices)
        half_edge_ids = {
            half_edge_id
            for boundary_index in boundary_indices
            for half_edge_id in drafts[boundary_index].half_edge_ids
        }
        road_ids = {authority.half_edges[index].source_road_id for index in half_edge_ids}
        node_ids = {
            node_id
            for index in half_edge_ids
            for node_id in (
                authority.half_edges[index].origin_node_id,
                authority.half_edges[index].destination_node_id,
            )
        }
        void_roads = tuple(
            sorted(semantic for road_id, semantic in bridge_by_road.items() if road_id in road_ids)
        )
        void_ramps = tuple(
            sorted(
                ramp.source_road_semantic_id
                for ramp in authority.ramp_incidence
                if ramp.start_node_id in node_ids or ramp.end_node_id in node_ids
            )
        )
        if void_roads and void_ramps:
            raise ValueError("bounded face has simultaneous bridge and ramp void reasons")
        role = "BARRIER_VOID" if void_roads else "INTERCHANGE_VOID" if void_ramps else "DEVELOPABLE"
        witness = _interior_witness(
            drafts[outer_index].polygon_mm,
            tuple(drafts[index].polygon_mm for index in hole_indices),
        )
        face_specs.append(
            (
                _digest(
                    "face",
                    (
                        "bounded",
                        drafts[outer_index].semantic_id,
                        tuple(drafts[index].semantic_id for index in hole_indices),
                        role,
                        void_roads,
                        void_ramps,
                    ),
                ),
                False,
                role,
                outer_index,
                hole_indices,
                (),
                witness,
                void_roads,
                void_ramps,
            )
        )
    for actual in authority.faces:
        matches = [
            spec
            for spec in face_specs
            if (spec[1], spec[3]) == (actual.is_unbounded, actual.outer_boundary_id)
        ]
        if len(matches) != 1:
            raise ValueError("canonical face and hole partition mismatch")
        if actual.void_road_semantic_ids != matches[0][7]:
            raise ValueError("void road reason mismatch")
        if actual.void_ramp_semantic_ids != matches[0][8]:
            raise ValueError("void ramp reason mismatch")

    face_specs.sort(key=lambda item: item[0])
    if len(face_specs) != len(authority.faces):
        raise ValueError("canonical face partition mismatch")
    boundary_face: dict[int, int] = {}
    for face_id, (actual, spec) in enumerate(zip(authority.faces, face_specs)):
        (
            semantic_id,
            is_unbounded,
            role,
            outer_boundary_id,
            hole_boundary_ids,
            unbounded_boundary_ids,
            witness,
            void_roads,
            void_ramps,
        ) = spec
        if (
            actual.semantic_id,
            actual.is_unbounded,
            actual.role,
            actual.outer_boundary_id,
            actual.hole_boundary_ids,
            actual.unbounded_component_boundary_ids,
            actual.interior_witness_mm,
        ) != (
            semantic_id,
            is_unbounded,
            role,
            outer_boundary_id,
            hole_boundary_ids,
            unbounded_boundary_ids,
            witness,
        ):
            raise ValueError("canonical face and hole partition mismatch")
        for boundary_id in (
            (() if outer_boundary_id is None else (outer_boundary_id,))
            + hole_boundary_ids
            + unbounded_boundary_ids
        ):
            boundary_face[boundary_id] = face_id
    for boundary_id, boundary in enumerate(authority.boundaries):
        if any(
            authority.half_edges[index].left_face_id != boundary_face[boundary_id]
            for index in boundary.half_edge_ids
        ):
            raise ValueError("half edge left face partition mismatch")


def _validate_tile_clips_against_faces(authority: ScalableBlockAuthority) -> None:
    expected_clips, owners = _build_tile_clips(
        authority.faces,
        authority.boundaries,
        authority.tile_coordinates,
        authority.tile_coordinates,
        authority.extent_mm,
    )
    if any(
        not (
            authority.extent_mm[0] <= point[0] <= authority.extent_mm[1]
            and authority.extent_mm[2] <= point[1] <= authority.extent_mm[3]
        )
        for edge in authority.embedding_edges
        for point in edge.points_mm
    ):
        raise ValueError("embedding point outside authority extent")
    if authority.tile_clips != expected_clips:
        raise ValueError("canonical tile clip reconstruction mismatch")
    if any(face.owner_tile != owners.get(face.face_id) for face in authority.faces):
        raise ValueError("canonical face owner tile mismatch")


def _validate_blocks_against_faces(authority: ScalableBlockAuthority) -> None:
    expected = _build_blocks(
        authority.faces,
        authority.boundaries,
        authority.half_edges,
        authority.embedding_edges,
        authority.source_network_fingerprint,
    )
    if authority.blocks != expected:
        raise ValueError("block does not match canonical parent face and holes")
    if authority.access_index != _build_access_index(expected):
        raise ValueError("canonical block access index mismatch")


def validate_scalable_block_authority(authority: ScalableBlockAuthority) -> None:
    _validate_authority_structure(authority)
    _validate_embedding_geometry(authority)
    _validate_embedding_permutations(authority)
    _validate_record_semantics(authority)
    _validate_canonical_face_partition(authority)
    _validate_tile_clips_against_faces(authority)
    _validate_blocks_against_faces(authority)
    fingerprint = _authority_fingerprint(authority)
    if authority.fingerprint:
        if authority.fingerprint != fingerprint:
            raise ValueError("authority fingerprint mismatch")
    else:
        object.__setattr__(authority, "fingerprint", fingerprint)
