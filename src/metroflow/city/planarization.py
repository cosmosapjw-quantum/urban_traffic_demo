"""Deterministically split proper same-layer endpoint-road crossings."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Sequence

from metroflow.map.road_geometry import (
    RoadGeometryCatalog,
    build_endpoint_geometry_catalog,
    count_interior_centerline_intersections,
)

from .graph import Node, RoadLink

__all__ = ["PlanarizationResult", "planarize_endpoint_topology"]

PointM = tuple[float, float]
_SPLIT_TOLERANCE = 1e-8


@dataclass(frozen=True, slots=True)
class PlanarizationResult:
    nodes: tuple[Node, ...]
    links: tuple[RoadLink, ...]
    old_link_to_new_link_ids: Mapping[int, tuple[int, ...]] = field(
        default_factory=dict
    )
    proper_intersection_count_before: int = 0
    proper_intersection_count_after: int = 0
    added_intersection_node_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "links", tuple(self.links))
        object.__setattr__(
            self,
            "old_link_to_new_link_ids",
            MappingProxyType(
                {
                    int(link_id): tuple(int(value) for value in values)
                    for link_id, values in self.old_link_to_new_link_ids.items()
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class _Segment:
    geometry_id: int
    start: PointM
    end: PointM
    layer: int


@dataclass(frozen=True, slots=True)
class _Crossing:
    left_geometry_id: int
    right_geometry_id: int
    left_t: float
    right_t: float
    point: PointM


def planarize_endpoint_topology(
    *,
    nodes: Sequence[Node],
    links: Sequence[RoadLink],
    road_geometry: RoadGeometryCatalog,
    cell_size_m: float = 250.0,
    _remaining_passes: int = 5,
) -> PlanarizationResult:
    """Split straight physical roads at proper crossings on the same layer."""

    nodes = tuple(nodes)
    links = tuple(links)
    if not nodes or not links:
        raise ValueError("planarization requires non-empty nodes and links")
    if not isinstance(road_geometry, RoadGeometryCatalog):
        raise TypeError("road_geometry must be a RoadGeometryCatalog")
    cell_size = float(cell_size_m)
    if not math.isfinite(cell_size) or cell_size <= 0.0:
        raise ValueError("cell_size_m must be finite and > 0")
    link_by_id = {int(link.link_id): link for link in links}
    if len(link_by_id) != len(links):
        raise ValueError("links must have unique link_id values")
    if {item.link_id for item in road_geometry.assignments} != set(link_by_id):
        raise ValueError("road geometry assignments must exactly cover links")

    segments = tuple(
        _centerline_segment(centerline.geometry_id, centerline.points_m, centerline.layer)
        for centerline in road_geometry.centerlines
    )
    crossings = _find_proper_crossings(segments, cell_size_m=cell_size)
    if not crossings:
        identity_map = {link.link_id: (link.link_id,) for link in links}
        return PlanarizationResult(
            nodes=nodes,
            links=links,
            old_link_to_new_link_ids=identity_map,
        )

    endpoint_nodes = _geometry_endpoint_node_ids(
        road_geometry=road_geometry,
        links=link_by_id,
    )
    output_nodes = list(nodes)
    next_node_id = max(node.node_id for node in nodes) + 1
    crossing_node_by_coordinate: dict[tuple[float, float], int] = {}
    split_nodes_by_geometry: dict[int, list[tuple[float, int]]] = {
        geometry_id: [(0.0, endpoint_pair[0]), (1.0, endpoint_pair[1])]
        for geometry_id, endpoint_pair in endpoint_nodes.items()
    }
    resolved_crossings: list[
        tuple[_Crossing, float, float, tuple[float, float]]
    ] = []
    endpoint_ids_by_coordinate: dict[tuple[float, float], set[int]] = {}
    point_by_coordinate: dict[tuple[float, float], PointM] = {}
    for crossing in sorted(
        crossings,
        key=lambda item: (
            round(item.point[0], 9),
            round(item.point[1], 9),
            item.left_geometry_id,
            item.right_geometry_id,
        ),
    ):
        left_t, left_endpoint_id = _snap_endpoint_position(
            crossing.left_t,
            endpoint_nodes[crossing.left_geometry_id],
        )
        right_t, right_endpoint_id = _snap_endpoint_position(
            crossing.right_t,
            endpoint_nodes[crossing.right_geometry_id],
        )
        endpoint_ids = {
            node_id
            for node_id in (left_endpoint_id, right_endpoint_id)
            if node_id is not None
        }
        # Pairwise intersection arithmetic can disagree at the sub-micron scale.
        coordinate_key = (round(crossing.point[0], 6), round(crossing.point[1], 6))
        endpoint_ids_by_coordinate.setdefault(coordinate_key, set()).update(endpoint_ids)
        point_by_coordinate.setdefault(coordinate_key, crossing.point)
        resolved_crossings.append((crossing, left_t, right_t, coordinate_key))

    parent = {coordinate_key: coordinate_key for coordinate_key in point_by_coordinate}
    positions_by_geometry: dict[int, list[tuple[float, tuple[float, float]]]] = {}
    for crossing, left_t, right_t, coordinate_key in resolved_crossings:
        positions_by_geometry.setdefault(crossing.left_geometry_id, []).append(
            (left_t, coordinate_key)
        )
        positions_by_geometry.setdefault(crossing.right_geometry_id, []).append(
            (right_t, coordinate_key)
        )
    for positions in positions_by_geometry.values():
        ordered = sorted(positions)
        for (left_t, left_key), (right_t, right_key) in zip(ordered, ordered[1:]):
            if math.isclose(left_t, right_t, abs_tol=_SPLIT_TOLERANCE):
                _union_keys(parent, left_key, right_key)

    endpoint_ids_by_root: dict[tuple[float, float], set[int]] = {}
    point_by_root: dict[tuple[float, float], PointM] = {}
    for coordinate_key in sorted(point_by_coordinate):
        root = _find_key(parent, coordinate_key)
        endpoint_ids_by_root.setdefault(root, set()).update(
            endpoint_ids_by_coordinate[coordinate_key]
        )
        point_by_root.setdefault(root, point_by_coordinate[coordinate_key])
    node_id_by_root: dict[tuple[float, float], int] = {}
    for root in sorted(point_by_root):
        endpoint_ids = endpoint_ids_by_root[root]
        if len(endpoint_ids) > 1:
            raise ValueError("one geometric crossing resolves to multiple endpoint nodes")
        if endpoint_ids:
            node_id = next(iter(endpoint_ids))
        else:
            point = point_by_root[root]
            node_id = next_node_id
            next_node_id += 1
            output_nodes.append(Node(node_id=node_id, x=point[0], y=point[1]))
        node_id_by_root[root] = node_id
    for coordinate_key in point_by_coordinate:
        crossing_node_by_coordinate[coordinate_key] = node_id_by_root[
            _find_key(parent, coordinate_key)
        ]

    for crossing, left_t, right_t, coordinate_key in resolved_crossings:
        node_id = crossing_node_by_coordinate[coordinate_key]
        split_nodes_by_geometry[crossing.left_geometry_id].append(
            (left_t, node_id)
        )
        split_nodes_by_geometry[crossing.right_geometry_id].append(
            (right_t, node_id)
        )

    assignments_by_geometry: dict[int, list[object]] = {}
    for assignment in road_geometry.assignments:
        assignments_by_geometry.setdefault(assignment.geometry_id, []).append(assignment)
    output_links: list[RoadLink] = []
    mapped_ids: dict[int, list[int]] = {link.link_id: [] for link in links}
    next_physical_road_id = 0
    for centerline in road_geometry.centerlines:
        split_nodes = _deduplicate_split_nodes(
            split_nodes_by_geometry[centerline.geometry_id],
            geometry_id=centerline.geometry_id,
        )
        intervals: list[tuple[int, int, float, int]] = []
        for (left_t, left_node_id), (right_t, right_node_id) in zip(
            split_nodes,
            split_nodes[1:],
        ):
            length_fraction = right_t - left_t
            geometric_length_m = centerline.length_m * length_fraction
            if geometric_length_m <= 1e-9 or left_node_id == right_node_id:
                raise ValueError(
                    "planarization produced a degenerate physical segment: "
                    f"geometry_id={centerline.geometry_id}, "
                    f"left=({left_t}, {left_node_id}), "
                    f"right=({right_t}, {right_node_id})"
                )
            intervals.append(
                (
                    left_node_id,
                    right_node_id,
                    length_fraction,
                    next_physical_road_id,
                )
            )
            next_physical_road_id += 1

        for assignment in sorted(
            assignments_by_geometry.get(centerline.geometry_id, ()),
            key=lambda item: int(item.link_id),
        ):
            source_link = link_by_id[int(assignment.link_id)]
            ordered_intervals = tuple(reversed(intervals)) if assignment.reversed else tuple(intervals)
            for (
                left_node_id,
                right_node_id,
                length_fraction,
                physical_road_id,
            ) in ordered_intervals:
                src_node_id, dst_node_id = (
                    (right_node_id, left_node_id)
                    if assignment.reversed
                    else (left_node_id, right_node_id)
                )
                link_id = len(output_links)
                output_links.append(
                    RoadLink(
                        link_id=link_id,
                        src_node_id=src_node_id,
                        dst_node_id=dst_node_id,
                        road_class=source_link.road_class,
                        length_m=source_link.length_m * length_fraction,
                        free_flow_speed_mps=source_link.free_flow_speed_mps,
                        capacity_veh_per_tick=source_link.capacity_veh_per_tick,
                        lanes=source_link.lanes,
                        bridge_group_id=source_link.bridge_group_id,
                        is_blockable=source_link.is_blockable,
                        physical_road_id=physical_road_id,
                    )
                )
                mapped_ids[source_link.link_id].append(link_id)

    output_node_tuple = tuple(output_nodes)
    output_link_tuple = tuple(output_links)
    output_geometry = build_endpoint_geometry_catalog(
        nodes=output_node_tuple,
        links=output_link_tuple,
    )
    remaining = count_interior_centerline_intersections(output_geometry)
    if remaining:
        if _remaining_passes <= 0:
            raise ValueError(
                f"planarization left {remaining} proper same-layer intersections"
            )
        refinement = planarize_endpoint_topology(
            nodes=output_node_tuple,
            links=output_link_tuple,
            road_geometry=output_geometry,
            cell_size_m=cell_size,
            _remaining_passes=_remaining_passes - 1,
        )
        composed_mapping = {
            old_link_id: tuple(
                refined_link_id
                for intermediate_link_id in intermediate_link_ids
                for refined_link_id in refinement.old_link_to_new_link_ids[
                    intermediate_link_id
                ]
            )
            for old_link_id, intermediate_link_ids in mapped_ids.items()
        }
        return PlanarizationResult(
            nodes=refinement.nodes,
            links=refinement.links,
            old_link_to_new_link_ids=composed_mapping,
            proper_intersection_count_before=len(crossings),
            proper_intersection_count_after=(
                refinement.proper_intersection_count_after
            ),
            added_intersection_node_count=len(refinement.nodes) - len(nodes),
        )
    return PlanarizationResult(
        nodes=output_node_tuple,
        links=output_link_tuple,
        old_link_to_new_link_ids={
            link_id: tuple(values) for link_id, values in mapped_ids.items()
        },
        proper_intersection_count_before=len(crossings),
        proper_intersection_count_after=remaining,
        added_intersection_node_count=len(output_nodes) - len(nodes),
    )


def _centerline_segment(
    geometry_id: int,
    points: tuple[PointM, ...],
    layer: int,
) -> _Segment:
    if len(points) != 2:
        raise ValueError("endpoint topology planarization requires two-point centerlines")
    return _Segment(int(geometry_id), points[0], points[1], int(layer))


def _find_proper_crossings(
    segments: tuple[_Segment, ...],
    *,
    cell_size_m: float,
) -> tuple[_Crossing, ...]:
    cells: dict[tuple[int, int], list[int]] = {}
    for index, segment in enumerate(segments):
        min_x = math.floor(min(segment.start[0], segment.end[0]) / cell_size_m)
        max_x = math.floor(max(segment.start[0], segment.end[0]) / cell_size_m)
        min_y = math.floor(min(segment.start[1], segment.end[1]) / cell_size_m)
        max_y = math.floor(max(segment.start[1], segment.end[1]) / cell_size_m)
        for cell_x in range(min_x, max_x + 1):
            for cell_y in range(min_y, max_y + 1):
                cells.setdefault((cell_x, cell_y), []).append(index)

    checked: set[tuple[int, int]] = set()
    crossings: list[_Crossing] = []
    for cell in sorted(cells):
        indices = tuple(sorted(set(cells[cell])))
        for offset, left_index in enumerate(indices):
            for right_index in indices[offset + 1 :]:
                pair = (left_index, right_index)
                if pair in checked:
                    continue
                checked.add(pair)
                left = segments[left_index]
                right = segments[right_index]
                if left.layer != right.layer or _has_shared_endpoint(left, right):
                    continue
                intersection = _proper_intersection(left, right)
                if intersection is not None:
                    point, left_t, right_t = intersection
                    crossings.append(
                        _Crossing(
                            left.geometry_id,
                            right.geometry_id,
                            left_t,
                            right_t,
                            point,
                        )
                    )
    return tuple(crossings)


def _proper_intersection(
    left: _Segment,
    right: _Segment,
) -> tuple[PointM, float, float] | None:
    first = _orientation(left.start, left.end, right.start)
    second = _orientation(left.start, left.end, right.end)
    third = _orientation(right.start, right.end, left.start)
    fourth = _orientation(right.start, right.end, left.end)
    if not (first * second < 0.0 and third * fourth < 0.0):
        return None
    left_dx = left.end[0] - left.start[0]
    left_dy = left.end[1] - left.start[1]
    right_dx = right.end[0] - right.start[0]
    right_dy = right.end[1] - right.start[1]
    denominator = left_dx * right_dy - left_dy * right_dx
    if denominator == 0.0:
        return None
    offset_x = right.start[0] - left.start[0]
    offset_y = right.start[1] - left.start[1]
    left_t = (offset_x * right_dy - offset_y * right_dx) / denominator
    right_t = (offset_x * left_dy - offset_y * left_dx) / denominator
    left_t = max(0.0, min(1.0, left_t))
    right_t = max(0.0, min(1.0, right_t))
    point = (
        left.start[0] + left_t * left_dx,
        left.start[1] + left_t * left_dy,
    )
    return point, left_t, right_t


def _orientation(a: PointM, b: PointM, c: PointM) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _has_shared_endpoint(left: _Segment, right: _Segment) -> bool:
    return bool({left.start, left.end} & {right.start, right.end})


def _geometry_endpoint_node_ids(
    *,
    road_geometry: RoadGeometryCatalog,
    links: Mapping[int, RoadLink],
) -> dict[int, tuple[int, int]]:
    out: dict[int, tuple[int, int]] = {}
    for assignment in road_geometry.assignments:
        link = links[assignment.link_id]
        endpoint_pair = (
            (link.dst_node_id, link.src_node_id)
            if assignment.reversed
            else (link.src_node_id, link.dst_node_id)
        )
        existing = out.get(assignment.geometry_id)
        if existing is not None and existing != endpoint_pair:
            raise ValueError("geometry assignments disagree on canonical endpoints")
        out[assignment.geometry_id] = endpoint_pair
    if set(out) != {item.geometry_id for item in road_geometry.centerlines}:
        raise ValueError("every centerline must have at least one link assignment")
    return out


def _deduplicate_split_nodes(
    values: list[tuple[float, int]],
    *,
    geometry_id: int,
) -> tuple[tuple[float, int], ...]:
    out: list[tuple[float, int]] = []
    for t, node_id in sorted(values):
        if out and out[-1][1] == node_id:
            continue
        if out and math.isclose(out[-1][0], t, abs_tol=_SPLIT_TOLERANCE):
            if out[-1][1] != node_id:
                raise ValueError(
                    "one split position resolved to multiple node ids: "
                    f"geometry_id={geometry_id}, left={out[-1]}, "
                    f"right={(t, node_id)}"
                )
            continue
        out.append((t, node_id))
    return tuple(out)


def _snap_endpoint_position(
    t: float,
    endpoint_node_ids: tuple[int, int],
) -> tuple[float, int | None]:
    if math.isclose(t, 0.0, abs_tol=_SPLIT_TOLERANCE):
        return 0.0, endpoint_node_ids[0]
    if math.isclose(t, 1.0, abs_tol=_SPLIT_TOLERANCE):
        return 1.0, endpoint_node_ids[1]
    return t, None


def _find_key(
    parent: dict[tuple[float, float], tuple[float, float]],
    key: tuple[float, float],
) -> tuple[float, float]:
    root = key
    while parent[root] != root:
        root = parent[root]
    while parent[key] != key:
        next_key = parent[key]
        parent[key] = root
        key = next_key
    return root


def _union_keys(
    parent: dict[tuple[float, float], tuple[float, float]],
    left: tuple[float, float],
    right: tuple[float, float],
) -> None:
    left_root = _find_key(parent, left)
    right_root = _find_key(parent, right)
    if left_root == right_root:
        return
    lower, upper = sorted((left_root, right_root))
    parent[upper] = lower
