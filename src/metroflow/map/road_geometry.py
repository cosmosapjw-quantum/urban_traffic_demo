"""Typed static road geometry independent from directed runtime topology."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Protocol, Sequence

__all__ = [
    "CenterlineSource",
    "RoadCenterline",
    "LinkGeometryAssignment",
    "RoadGeometryCatalog",
    "build_endpoint_geometry_catalog",
    "validate_geometry_endpoint_anchors",
    "count_interior_centerline_intersections",
    "count_unregistered_centerline_touches",
]

PointM = tuple[float, float]


class CenterlineSource(str, Enum):
    """Provenance class for a static road centerline."""

    SYNTHETIC = "synthetic"
    TENSOR_FIELD = "tensor_field"
    OSM = "osm"
    IMPORTED = "imported"


@dataclass(frozen=True, slots=True)
class RoadCenterline:
    """Physical road centerline with coordinates measured in meters."""

    geometry_id: int
    points_m: tuple[PointM, ...]
    source: CenterlineSource | str = CenterlineSource.SYNTHETIC
    source_ref: str = ""
    layer: int = 0
    corridor_id: int | None = None

    def __post_init__(self) -> None:
        geometry_id = int(self.geometry_id)
        points = _coerce_points_m(self.points_m)
        source = CenterlineSource(self.source)
        source_ref = str(self.source_ref)
        layer = int(self.layer)
        corridor_id = None if self.corridor_id is None else int(self.corridor_id)

        if geometry_id < 0:
            raise ValueError("geometry_id must be >= 0")
        if len(points) < 2:
            raise ValueError("points_m must contain at least two points")
        if any(not math.isfinite(value) for point in points for value in point):
            raise ValueError("points_m coordinates must be finite")
        if any(left == right for left, right in zip(points, points[1:])):
            raise ValueError("points_m must not contain consecutive duplicate points")
        if corridor_id is not None and corridor_id < 0:
            raise ValueError("corridor_id must be >= 0 when provided")

        object.__setattr__(self, "geometry_id", geometry_id)
        object.__setattr__(self, "points_m", points)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "source_ref", source_ref)
        object.__setattr__(self, "layer", layer)
        object.__setattr__(self, "corridor_id", corridor_id)

    @property
    def length_m(self) -> float:
        """Polyline arc length in meters."""

        return float(
            sum(
                math.hypot(right[0] - left[0], right[1] - left[1])
                for left, right in zip(self.points_m, self.points_m[1:])
            )
        )

    @property
    def fingerprint(self) -> str:
        """Stable SHA-256 fingerprint over canonical geometry values."""

        return _sha256_json(self._canonical_payload())

    def _canonical_payload(self) -> dict[str, object]:
        return {
            "geometry_id": self.geometry_id,
            "points_m": self.points_m,
            "source": self.source.value,
            "source_ref": self.source_ref,
            "layer": self.layer,
            "corridor_id": self.corridor_id,
        }


@dataclass(frozen=True, slots=True)
class LinkGeometryAssignment:
    """Orient one directed link along a shared physical centerline."""

    link_id: int
    geometry_id: int
    reversed: bool = False
    lateral_offset_m: float = 0.0

    def __post_init__(self) -> None:
        link_id = int(self.link_id)
        geometry_id = int(self.geometry_id)
        lateral_offset_m = _canonical_float(self.lateral_offset_m)
        if link_id < 0:
            raise ValueError("link_id must be >= 0")
        if geometry_id < 0:
            raise ValueError("geometry_id must be >= 0")
        if not math.isfinite(lateral_offset_m):
            raise ValueError("lateral_offset_m must be finite")
        object.__setattr__(self, "link_id", link_id)
        object.__setattr__(self, "geometry_id", geometry_id)
        object.__setattr__(self, "reversed", bool(self.reversed))
        object.__setattr__(self, "lateral_offset_m", lateral_offset_m)

    def _canonical_payload(self) -> dict[str, object]:
        return {
            "link_id": self.link_id,
            "geometry_id": self.geometry_id,
            "reversed": self.reversed,
            "lateral_offset_m": self.lateral_offset_m,
        }


@dataclass(frozen=True, slots=True)
class RoadGeometryCatalog:
    """Validated immutable catalog of physical centerlines and link mappings."""

    centerlines: tuple[RoadCenterline, ...]
    assignments: tuple[LinkGeometryAssignment, ...]
    _geometry_by_id: Mapping[int, RoadCenterline] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _assignment_by_link_id: Mapping[int, LinkGeometryAssignment] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        centerlines = tuple(sorted(self.centerlines, key=lambda item: item.geometry_id))
        assignments = tuple(sorted(self.assignments, key=lambda item: item.link_id))
        geometry_by_id = {item.geometry_id: item for item in centerlines}
        assignment_by_link_id = {item.link_id: item for item in assignments}

        if len(geometry_by_id) != len(centerlines):
            raise ValueError("duplicate geometry_id values are not allowed")
        if len(assignment_by_link_id) != len(assignments):
            raise ValueError("duplicate link_id geometry assignments are not allowed")
        missing = sorted(
            {
                assignment.geometry_id
                for assignment in assignments
                if assignment.geometry_id not in geometry_by_id
            }
        )
        if missing:
            raise ValueError(f"assignment references missing geometry_id values: {missing}")

        object.__setattr__(self, "centerlines", centerlines)
        object.__setattr__(self, "assignments", assignments)
        object.__setattr__(self, "_geometry_by_id", MappingProxyType(geometry_by_id))
        object.__setattr__(
            self,
            "_assignment_by_link_id",
            MappingProxyType(assignment_by_link_id),
        )

    @property
    def fingerprint(self) -> str:
        """Stable catalog fingerprint independent of input tuple ordering."""

        return _sha256_json(
            {
                "centerlines": [item._canonical_payload() for item in self.centerlines],
                "assignments": [item._canonical_payload() for item in self.assignments],
            }
        )

    def centerline(self, geometry_id: int) -> RoadCenterline:
        try:
            return self._geometry_by_id[int(geometry_id)]
        except KeyError as exc:
            raise KeyError(f"unknown geometry_id {int(geometry_id)}") from exc

    def assignment_for_link(self, link_id: int) -> LinkGeometryAssignment:
        try:
            return self._assignment_by_link_id[int(link_id)]
        except KeyError as exc:
            raise KeyError(f"no geometry assignment for link_id {int(link_id)}") from exc

    def points_for_link(self, link_id: int) -> tuple[PointM, ...]:
        assignment = self.assignment_for_link(link_id)
        points = self.centerline(assignment.geometry_id).points_m
        return tuple(reversed(points)) if assignment.reversed else points


class _NodeLike(Protocol):
    node_id: int
    x: float
    y: float


class _LinkLike(Protocol):
    link_id: int
    src_node_id: int
    dst_node_id: int
    road_class: object
    length_m: float
    bridge_group_id: int | None
    physical_road_id: int | None


def build_endpoint_geometry_catalog(
    *,
    nodes: Sequence[_NodeLike],
    links: Sequence[_LinkLike],
    source: CenterlineSource | str = CenterlineSource.SYNTHETIC,
) -> RoadGeometryCatalog:
    """Build canonical straight centerlines from an endpoint-only topology."""

    node_by_id = {int(node.node_id): node for node in nodes}
    if len(node_by_id) != len(nodes):
        raise ValueError("nodes must have unique node_id values")

    grouped: dict[tuple[object, ...], list[_LinkLike]] = {}
    for link in links:
        src_id = int(link.src_node_id)
        dst_id = int(link.dst_node_id)
        if src_id not in node_by_id or dst_id not in node_by_id:
            raise ValueError(f"link {int(link.link_id)} references a missing endpoint node")
        lo, hi = sorted((src_id, dst_id))
        road_class = getattr(link.road_class, "value", link.road_class)
        bridge_group = -1 if link.bridge_group_id is None else int(link.bridge_group_id)
        physical_road_id = getattr(link, "physical_road_id", None)
        has_explicit_road_id = physical_road_id is not None
        key = (
            ("physical", int(physical_road_id))
            if has_explicit_road_id
            else (
                "inferred",
                lo,
                hi,
                str(road_class),
                bridge_group,
                round(float(link.length_m), 6),
            )
        )
        grouped.setdefault(key, []).append(link)

    centerlines: list[RoadCenterline] = []
    assignments: list[LinkGeometryAssignment] = []
    geometry_id = 0
    for key in sorted(grouped):
        group = tuple(sorted(grouped[key], key=lambda item: int(item.link_id)))
        explicit_physical_id = int(key[1]) if key[0] == "physical" else None
        if explicit_physical_id is not None:
            _validate_explicit_physical_group(group, physical_road_id=explicit_physical_id)
        first = group[0]
        lo, hi = sorted((int(first.src_node_id), int(first.dst_node_id)))
        forward = [item for item in group if int(item.src_node_id) == lo]
        reverse = [item for item in group if int(item.src_node_id) == hi]
        if len(group) > 1 and not (
            len(group) == 2 and len(forward) == 1 and len(reverse) == 1
        ):
            link_ids = [int(item.link_id) for item in group]
            raise ValueError(
                "endpoint geometry cannot infer ambiguous parallel link pairing "
                f"for link_ids {link_ids}"
            )
        pair_count = max(len(forward), len(reverse))
        for ordinal in range(pair_count):
            lo_node = node_by_id[lo]
            hi_node = node_by_id[hi]
            centerlines.append(
                RoadCenterline(
                    geometry_id=geometry_id,
                    points_m=((float(lo_node.x), float(lo_node.y)), (float(hi_node.x), float(hi_node.y))),
                    source=source,
                    source_ref=f"endpoint:{lo}:{hi}:{ordinal}",
                    layer=1 if first.bridge_group_id is not None else 0,
                    corridor_id=explicit_physical_id,
                )
            )
            if ordinal < len(forward):
                assignments.append(
                    LinkGeometryAssignment(
                        link_id=int(forward[ordinal].link_id),
                        geometry_id=geometry_id,
                    )
                )
            if ordinal < len(reverse):
                assignments.append(
                    LinkGeometryAssignment(
                        link_id=int(reverse[ordinal].link_id),
                        geometry_id=geometry_id,
                        reversed=True,
                    )
                )
            geometry_id += 1

    return RoadGeometryCatalog(
        centerlines=tuple(centerlines),
        assignments=tuple(assignments),
    )


def validate_geometry_endpoint_anchors(
    *,
    catalog: RoadGeometryCatalog,
    nodes: Sequence[_NodeLike],
    links: Sequence[_LinkLike],
    tolerance_m: float = 1e-6,
) -> None:
    """Fail when oriented centerline endpoints do not anchor to link nodes."""

    tolerance_m = float(tolerance_m)
    if not math.isfinite(tolerance_m) or tolerance_m < 0.0:
        raise ValueError("tolerance_m must be finite and >= 0")
    node_by_id = {int(node.node_id): node for node in nodes}
    for link in links:
        link_id = int(link.link_id)
        src = node_by_id.get(int(link.src_node_id))
        dst = node_by_id.get(int(link.dst_node_id))
        if src is None or dst is None:
            raise ValueError(f"link {link_id} references a missing endpoint node")
        points = catalog.points_for_link(link_id)
        start_error = math.hypot(points[0][0] - float(src.x), points[0][1] - float(src.y))
        end_error = math.hypot(points[-1][0] - float(dst.x), points[-1][1] - float(dst.y))
        if start_error > tolerance_m or end_error > tolerance_m:
            raise ValueError(
                f"link {link_id} centerline endpoints exceed snap tolerance_m={tolerance_m}"
            )


def count_interior_centerline_intersections(
    catalog: RoadGeometryCatalog,
    *,
    cell_size_m: float = 250.0,
) -> int:
    """Count same-layer proper segment crossings as a diagnostic audit."""

    cell_size_m = float(cell_size_m)
    if not math.isfinite(cell_size_m) or cell_size_m <= 0.0:
        raise ValueError("cell_size_m must be finite and > 0")
    segments: list[tuple[PointM, PointM, int]] = []
    for centerline in catalog.centerlines:
        segments.extend(
            (left, right, centerline.layer)
            for left, right in zip(centerline.points_m, centerline.points_m[1:])
        )
    cells: dict[tuple[int, int], list[int]] = {}
    for index, (left, right, _layer) in enumerate(segments):
        min_x = math.floor(min(left[0], right[0]) / cell_size_m)
        max_x = math.floor(max(left[0], right[0]) / cell_size_m)
        min_y = math.floor(min(left[1], right[1]) / cell_size_m)
        max_y = math.floor(max(left[1], right[1]) / cell_size_m)
        for cell_x in range(min_x, max_x + 1):
            for cell_y in range(min_y, max_y + 1):
                cells.setdefault((cell_x, cell_y), []).append(index)

    checked: set[tuple[int, int]] = set()
    count = 0
    for indices in cells.values():
        unique_indices = tuple(sorted(set(indices)))
        for offset, left_index in enumerate(unique_indices):
            for right_index in unique_indices[offset + 1 :]:
                pair = (left_index, right_index)
                if pair in checked:
                    continue
                checked.add(pair)
                left_a, left_b, left_layer = segments[left_index]
                right_a, right_b, right_layer = segments[right_index]
                if left_layer != right_layer:
                    continue
                if _has_shared_endpoint(left_a, left_b, right_a, right_b):
                    continue
                if _segments_cross_properly(left_a, left_b, right_a, right_b):
                    count += 1
    return count


def count_unregistered_centerline_touches(
    catalog: RoadGeometryCatalog,
    *,
    tolerance_m: float = 0.25,
    cell_size_m: float = 250.0,
) -> int:
    """Count vertices that sit on another centerline's interior without a node.

    Distinct from `count_interior_centerline_intersections`, which needs two
    segments to properly cross. The dominant defect in the grown fabric is not a
    crossing at all: a street *begins* partway along another street, so the two
    touch without intersecting and without sharing a vertex. On the ground it is
    a T-junction; in the graph it is nothing.

    A vertex is only counted when it is far enough from every vertex of the other
    centerline to be a genuinely unregistered contact — a vertex the two streets
    already share is a junction that was recorded properly. Different layers
    never touch, matching the crossing counter's grade-separation rule.

    Returns distinct touching vertices, so a vertex lying on several centerlines
    counts once. Diagnostic only.
    """

    tolerance_m = float(tolerance_m)
    if not math.isfinite(tolerance_m) or tolerance_m <= 0.0:
        raise ValueError("tolerance_m must be finite and > 0")
    cell_size_m = float(cell_size_m)
    if not math.isfinite(cell_size_m) or cell_size_m <= 0.0:
        raise ValueError("cell_size_m must be finite and > 0")

    centerlines = tuple(catalog.centerlines)

    segments: list[tuple[PointM, PointM, int, int]] = []
    for index, centerline in enumerate(centerlines):
        segments.extend(
            (left, right, centerline.layer, index)
            for left, right in zip(centerline.points_m, centerline.points_m[1:])
        )

    cells: dict[tuple[int, int], list[int]] = {}
    for index, (left, right, _layer, _owner) in enumerate(segments):
        min_x = math.floor((min(left[0], right[0]) - tolerance_m) / cell_size_m)
        max_x = math.floor((max(left[0], right[0]) + tolerance_m) / cell_size_m)
        min_y = math.floor((min(left[1], right[1]) - tolerance_m) / cell_size_m)
        max_y = math.floor((max(left[1], right[1]) + tolerance_m) / cell_size_m)
        for cell_x in range(min_x, max_x + 1):
            for cell_y in range(min_y, max_y + 1):
                cells.setdefault((cell_x, cell_y), []).append(index)

    touches = 0
    for owner_index, centerline in enumerate(centerlines):
        for point in centerline.points_m:
            cell = (
                math.floor(point[0] / cell_size_m),
                math.floor(point[1] / cell_size_m),
            )
            candidates = cells.get(cell, ())
            touched = False
            for segment_index in candidates:
                left, right, layer, other_index = segments[segment_index]
                if other_index == owner_index or layer != centerline.layer:
                    continue
                if _point_to_segment_distance(point, left, right) > tolerance_m:
                    continue
                # A shared vertex means the junction was recorded. Only an
                # unrecorded contact is a defect.
                if _touches_a_vertex_of(point, centerlines[other_index], tolerance_m):
                    continue
                touched = True
                break
            if touched:
                touches += 1
    return touches


def _touches_a_vertex_of(
    point: PointM,
    centerline: RoadCenterline,
    tolerance_m: float,
) -> bool:
    return any(
        math.hypot(point[0] - vertex[0], point[1] - vertex[1]) <= tolerance_m
        for vertex in centerline.points_m
    )


def _point_to_segment_distance(point: PointM, left: PointM, right: PointM) -> float:
    dx = right[0] - left[0]
    dy = right[1] - left[1]
    span = dx * dx + dy * dy
    if span <= 0.0:
        return math.hypot(point[0] - left[0], point[1] - left[1])
    position = ((point[0] - left[0]) * dx + (point[1] - left[1]) * dy) / span
    position = min(max(position, 0.0), 1.0)
    return math.hypot(
        point[0] - (left[0] + position * dx),
        point[1] - (left[1] + position * dy),
    )


def _validate_explicit_physical_group(
    group: Sequence[_LinkLike],
    *,
    physical_road_id: int,
) -> None:
    if len(group) not in {1, 2}:
        raise ValueError(
            f"physical_road_id {physical_road_id} must reference one link or one directed pair"
        )
    if len(group) == 1:
        return
    first, second = group
    same_endpoints = (
        int(first.src_node_id) == int(second.dst_node_id)
        and int(first.dst_node_id) == int(second.src_node_id)
    )
    first_class = str(getattr(first.road_class, "value", first.road_class))
    second_class = str(getattr(second.road_class, "value", second.road_class))
    compatible = (
        same_endpoints
        and first_class == second_class
        and first.bridge_group_id == second.bridge_group_id
        and math.isclose(float(first.length_m), float(second.length_m), abs_tol=1e-6)
    )
    if not compatible:
        raise ValueError(
            f"physical_road_id {physical_road_id} references incompatible directed links"
        )


def _has_shared_endpoint(
    left_a: PointM,
    left_b: PointM,
    right_a: PointM,
    right_b: PointM,
) -> bool:
    return any(
        math.isclose(left[0], right[0], abs_tol=1e-8)
        and math.isclose(left[1], right[1], abs_tol=1e-8)
        for left in (left_a, left_b)
        for right in (right_a, right_b)
    )


def _segments_cross_properly(
    left_a: PointM,
    left_b: PointM,
    right_a: PointM,
    right_b: PointM,
) -> bool:
    left_dx = left_b[0] - left_a[0]
    left_dy = left_b[1] - left_a[1]
    right_dx = right_b[0] - right_a[0]
    right_dy = right_b[1] - right_a[1]
    denominator = left_dx * right_dy - left_dy * right_dx
    if math.isclose(denominator, 0.0, abs_tol=1e-12):
        return False
    offset_x = right_a[0] - left_a[0]
    offset_y = right_a[1] - left_a[1]
    left_t = (offset_x * right_dy - offset_y * right_dx) / denominator
    right_t = (offset_x * left_dy - offset_y * left_dx) / denominator
    tolerance = 1e-8
    return (
        tolerance < left_t < 1.0 - tolerance
        and tolerance < right_t < 1.0 - tolerance
    )


def _sha256_json(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _coerce_points_m(values: Sequence[Sequence[float]]) -> tuple[PointM, ...]:
    points: list[PointM] = []
    for index, point in enumerate(values):
        try:
            if len(point) != 2:
                raise ValueError
            x_m = _canonical_float(point[0])
            y_m = _canonical_float(point[1])
        except (IndexError, TypeError, ValueError) as exc:
            raise ValueError(
                f"points_m[{index}] must contain exactly two numeric coordinates"
            ) from exc
        points.append((x_m, y_m))
    return tuple(points)


def _canonical_float(value: float) -> float:
    number = float(value)
    return 0.0 if number == 0.0 else number
