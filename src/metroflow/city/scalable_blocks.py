"""Static scalable block and DCEL authority."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field, fields
from fractions import Fraction
from functools import cmp_to_key
import hashlib
import json

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
    if type(value) is not tuple or len(value) != 2:
        raise TypeError(f"{name} must be an exact point tuple")
    return (
        _exact_coordinate(value[0], f"{name}[0]"),
        _exact_coordinate(value[1], f"{name}[1]"),
    )


def _is_plain_snapshot(value: object) -> bool:
    if value is None or type(value) in {bool, int, str, float, Fraction}:
        return True
    return type(value) is tuple and all(_is_plain_snapshot(item) for item in value)


def _validate_nested_snapshot(value: object) -> None:
    if not _is_plain_snapshot(value):
        raise TypeError("nested authority snapshot must use exact immutable values")


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

    def __post_init__(self) -> None:
        _validate_nested_snapshot(tuple(getattr(self, item.name) for item in fields(self)))
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
            _plain_digest(getattr(self, name), name)
        _plain_str(self.facility, "facility")
        if type(self.points_mm) is not tuple:
            raise TypeError("nested authority snapshot must use exact immutable values")
        for index, point in enumerate(self.points_mm):
            exact = _exact_point(point, f"points_mm[{index}]")
            if any(type(coordinate) is not int for coordinate in exact):
                raise TypeError("embedding points must use plain integers")


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

    def __post_init__(self) -> None:
        _validate_nested_snapshot(tuple(getattr(self, item.name) for item in fields(self)))
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
        _plain_digest(self.semantic_id, "semantic_id")
        if type(self.points_mm) is not tuple:
            raise TypeError("nested authority snapshot must use exact immutable values")
        for index, point in enumerate(self.points_mm):
            _exact_point(point, f"points_mm[{index}]")


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

    def __post_init__(self) -> None:
        _validate_nested_snapshot(tuple(getattr(self, item.name) for item in fields(self)))
        for name in ("boundary_id", "signed_twice_area_mm2", "component_id"):
            _plain_int(getattr(self, name), name)
        _plain_digest(self.semantic_id, "semantic_id")
        _plain_str(self.role, "role")
        if type(self.half_edge_ids) is not tuple or any(
            type(value) is not int for value in self.half_edge_ids
        ):
            raise TypeError("half_edge_ids must be a tuple of plain integers")
        if type(self.polygon_mm) is not tuple:
            raise TypeError("polygon_mm must be an exact tuple")
        for index, point in enumerate(self.polygon_mm):
            _exact_point(point, f"polygon_mm[{index}]")
        _exact_point(self.interior_witness_mm, "interior_witness_mm")


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

    def __post_init__(self) -> None:
        _validate_nested_snapshot(tuple(getattr(self, item.name) for item in fields(self)))
        _plain_int(self.face_id, "face_id")
        _plain_digest(self.semantic_id, "semantic_id")
        _plain_digest(self.source_fingerprint, "source_fingerprint")
        if type(self.is_unbounded) is not bool:
            raise TypeError("is_unbounded must be a plain bool")
        _plain_str(self.role, "role")
        if self.outer_boundary_id is not None:
            _plain_int(self.outer_boundary_id, "outer_boundary_id")
        for name in ("hole_boundary_ids", "unbounded_component_boundary_ids"):
            value = getattr(self, name)
            if type(value) is not tuple or any(type(item) is not int for item in value):
                raise TypeError(f"{name} must be a tuple of plain integers")
        if self.owner_tile is not None:
            _exact_point(self.owner_tile, "owner_tile")
        if self.interior_witness_mm is not None:
            _exact_point(self.interior_witness_mm, "interior_witness_mm")
        for name in ("void_road_semantic_ids", "void_ramp_semantic_ids"):
            value = getattr(self, name)
            if type(value) is not tuple:
                raise TypeError("nested authority snapshot must use exact immutable values")
            for semantic_id in value:
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

    def __post_init__(self) -> None:
        _validate_nested_snapshot(tuple(getattr(self, item.name) for item in fields(self)))
        for name in ("ramp_incidence_id", "source_road_id", "start_node_id", "end_node_id"):
            _plain_int(getattr(self, name), name)
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

    def __post_init__(self) -> None:
        _validate_nested_snapshot(tuple(getattr(self, item.name) for item in fields(self)))
        for name in ("block_id", "parent_face_id", "primary_access_node_id"):
            _plain_int(getattr(self, name), name)
        _plain_digest(self.semantic_id, "semantic_id")
        _plain_digest(self.source_fingerprint, "source_fingerprint")
        _plain_str(self.subdivision_schema, "subdivision_schema")
        if type(self.net_area_mm2) is not Fraction:
            raise TypeError("net_area_mm2 must be an exact Fraction")
        if type(self.perimeter_m) is not float:
            raise TypeError("perimeter_m must be a plain float")
        _exact_point(self.interior_witness_mm, "interior_witness_mm")


@dataclass(frozen=True, slots=True)
class V2BlockAccessIndex:
    block_to_road_ids: tuple[tuple[int, tuple[int, ...]], ...]
    block_to_node_ids: tuple[tuple[int, tuple[int, ...]], ...]
    road_to_block_ids: tuple[tuple[int, tuple[int, ...]], ...]
    node_to_block_ids: tuple[tuple[int, tuple[int, ...]], ...]
    primary_access_by_block: tuple[tuple[int, int], ...]
    incidence_visit_count: int

    def __post_init__(self) -> None:
        _validate_nested_snapshot(tuple(getattr(self, item.name) for item in fields(self)))
        _plain_int(self.incidence_visit_count, "incidence_visit_count")


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

    def __post_init__(self) -> None:
        _validate_nested_snapshot(tuple(getattr(self, item.name) for item in fields(self)))
        for name in ("clip_id", "face_id", "diagnostic_twice_area_mm2"):
            _plain_int(getattr(self, name), name)
        _plain_digest(self.face_semantic_id, "face_semantic_id")
        _exact_point(self.tile_coordinate, "tile_coordinate")
        if type(self.exact_net_area_mm2) is not Fraction:
            raise TypeError("exact_net_area_mm2 must be an exact Fraction")
        if type(self.is_owner) is not bool:
            raise TypeError("is_owner must be a plain bool")


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

    def __post_init__(self) -> None:
        _validate_nested_snapshot(
            tuple(
                getattr(self, item.name)
                for item in fields(self)
                if item.name
                not in {
                    "embedding_edges",
                    "ramp_incidence",
                    "half_edges",
                    "boundaries",
                    "faces",
                    "blocks",
                    "access_index",
                    "tile_clips",
                }
            )
        )
        for name in ("schema_version", "embedding_policy", "tile_policy", "subdivision_schema"):
            _plain_str(getattr(self, name), name)
        _plain_digest(self.source_network_fingerprint, "source_network_fingerprint")
        _plain_digest(self.fingerprint, "fingerprint", allow_empty=True)
        _validate_embedding_geometry(self)
        _validate_embedding_permutations(self)


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
                road.layer_transition,
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
        tuple(extent_mm),
        tuple(tile_coordinates),
        edges,
        ramp_records,
        half_edges,
        boundaries,
        faces,
        (),
        V2BlockAccessIndex((), (), (), (), (), 0),
        (),
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
    raise NotImplementedError("public scalable block builder is not implemented")


def validate_scalable_block_authority(authority: ScalableBlockAuthority) -> None:
    raise NotImplementedError("standalone scalable block validation is not implemented")
