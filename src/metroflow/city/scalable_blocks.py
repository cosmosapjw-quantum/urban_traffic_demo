"""Static scalable block and DCEL authority."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from fractions import Fraction

from metroflow.city.scalable_topology import ScalableStreetNetwork

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


def build_scalable_block_authority(
    network: ScalableStreetNetwork,
) -> ScalableBlockAuthority:
    raise NotImplementedError("public scalable block builder is not implemented")


def validate_scalable_block_authority(authority: ScalableBlockAuthority) -> None:
    raise NotImplementedError("standalone scalable block validation is not implemented")
