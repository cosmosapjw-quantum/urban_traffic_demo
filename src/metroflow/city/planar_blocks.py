"""Planar physical-street compilation and bounded urban block extraction."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from metroflow.map.road_geometry import (
    build_endpoint_geometry_catalog,
    count_interior_centerline_intersections,
)

from .graph import Node, RoadLink
from .planarization import planarize_endpoint_topology
from .realistic_local_fabric import RealisticStreetNetwork

__all__ = ["CityBlock", "CityBlockCatalog", "compile_planar_city_blocks"]

PointM = tuple[float, float]
_MINIMUM_BLOCK_AREA_M2 = 100.0
_MINIMUM_SEGMENT_LENGTH_M = 10.0
_MAXIMUM_SHORT_SEGMENT_SHARE = 0.02
_MINIMUM_MEDIAN_BLOCK_AREA_M2 = 3_000.0
_MAXIMUM_MEDIAN_BLOCK_AREA_M2 = 30_000.0
_MAXIMUM_P95_BLOCK_AREA_M2 = 120_000.0


@dataclass(frozen=True, slots=True)
class CityBlock:
    block_id: int
    polygon_m: tuple[PointM, ...]
    area_m2: float
    perimeter_m: float
    frontage_street_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        block_id = int(self.block_id)
        polygon = tuple((float(x), float(y)) for x, y in self.polygon_m)
        area = float(self.area_m2)
        perimeter = float(self.perimeter_m)
        frontage = tuple(sorted({int(value) for value in self.frontage_street_ids}))
        if block_id < 0:
            raise ValueError("block_id must be >= 0")
        if len(polygon) < 4 or polygon[0] != polygon[-1]:
            raise ValueError("block polygon must be a closed ring")
        if len(set(polygon[:-1])) != len(polygon) - 1:
            raise ValueError("block polygon must not repeat boundary points")
        if any(not math.isfinite(value) for point in polygon for value in point):
            raise ValueError("block polygon coordinates must be finite")
        if not _is_simple_polygon(polygon):
            raise ValueError("block polygon must be simple")
        if not math.isfinite(area) or area <= 0.0:
            raise ValueError("block area_m2 must be finite and > 0")
        if not math.isfinite(perimeter) or perimeter <= 0.0:
            raise ValueError("block perimeter_m must be finite and > 0")
        computed_area = _signed_area(polygon)
        computed_perimeter = sum(
            math.dist(left, right) for left, right in zip(polygon, polygon[1:])
        )
        if computed_area <= 0.0 or not math.isclose(
            area,
            computed_area,
            rel_tol=1e-9,
            abs_tol=1e-6,
        ):
            raise ValueError("block area_m2 does not match polygon geometry")
        if not math.isclose(
            perimeter,
            computed_perimeter,
            rel_tol=1e-9,
            abs_tol=1e-6,
        ):
            raise ValueError("block perimeter_m does not match polygon geometry")
        if not frontage or any(value < 0 for value in frontage):
            raise ValueError("block frontage_street_ids must be non-empty")
        object.__setattr__(self, "block_id", block_id)
        object.__setattr__(self, "polygon_m", polygon)
        object.__setattr__(self, "area_m2", area)
        object.__setattr__(self, "perimeter_m", perimeter)
        object.__setattr__(self, "frontage_street_ids", frontage)

    @property
    def centroid_m(self) -> PointM:
        cross_terms = tuple(
            left[0] * right[1] - right[0] * left[1]
            for left, right in zip(self.polygon_m, self.polygon_m[1:])
        )
        denominator = 6.0 * self.area_m2
        return (
            sum(
                (left[0] + right[0]) * cross
                for left, right, cross in zip(
                    self.polygon_m,
                    self.polygon_m[1:],
                    cross_terms,
                )
            )
            / denominator,
            sum(
                (left[1] + right[1]) * cross
                for left, right, cross in zip(
                    self.polygon_m,
                    self.polygon_m[1:],
                    cross_terms,
                )
            )
            / denominator,
        )


@dataclass(frozen=True, slots=True)
class CityBlockCatalog:
    street_network_fingerprint: str
    nodes: tuple[Node, ...]
    links: tuple[RoadLink, ...]
    blocks: tuple[CityBlock, ...]
    new_link_to_street_id: Mapping[int, int] = field(default_factory=dict)
    proper_intersection_count_before: int = 0
    proper_intersection_count_after: int = 0
    physical_segment_count: int = 0
    short_segment_share: float = 0.0
    median_block_area_m2: float = 0.0
    p95_block_area_m2: float = 0.0
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        nodes = tuple(sorted(self.nodes, key=lambda item: item.node_id))
        links = tuple(sorted(self.links, key=lambda item: item.link_id))
        blocks = tuple(sorted(self.blocks, key=lambda item: item.block_id))
        mapping = MappingProxyType(
            {int(key): int(value) for key, value in self.new_link_to_street_id.items()}
        )
        if not nodes or not links or not blocks:
            raise ValueError("city block catalog requires nodes, links, and blocks")
        if tuple(node.node_id for node in nodes) != tuple(range(len(nodes))):
            raise ValueError("node IDs must be dense and zero-based")
        if tuple(link.link_id for link in links) != tuple(range(len(links))):
            raise ValueError("link IDs must be dense and zero-based")
        if tuple(block.block_id for block in blocks) != tuple(range(len(blocks))):
            raise ValueError("block IDs must be dense and zero-based")
        node_ids = {node.node_id for node in nodes}
        if any(
            link.src_node_id not in node_ids or link.dst_node_id not in node_ids
            for link in links
        ):
            raise ValueError("planar link references a missing node")
        if set(mapping) != {link.link_id for link in links}:
            raise ValueError("street provenance must cover every planar link")
        geometry = build_endpoint_geometry_catalog(nodes=nodes, links=links)
        actual_intersections = count_interior_centerline_intersections(geometry)
        if int(self.proper_intersection_count_after) != 0 or actual_intersections != 0:
            raise ValueError("planar block catalog cannot retain proper intersections")
        physical_lengths = _physical_segment_lengths(links)
        physical_segment_count = int(self.physical_segment_count)
        if physical_segment_count != len(physical_lengths):
            raise ValueError("physical_segment_count does not match planar links")
        computed_short_share = sum(
            length < _MINIMUM_SEGMENT_LENGTH_M for length in physical_lengths
        ) / len(physical_lengths)
        short_share = float(self.short_segment_share)
        if not math.isclose(short_share, computed_short_share, abs_tol=1e-12):
            raise ValueError("short_segment_share does not match planar links")
        if not 0.0 <= short_share <= _MAXIMUM_SHORT_SEGMENT_SHARE:
            raise ValueError("physical segments shorter than 10m exceed 2%")
        _validate_block_frontage(
            nodes=nodes,
            links=links,
            blocks=blocks,
            link_to_street_id=mapping,
        )
        areas = sorted(block.area_m2 for block in blocks)
        computed_median_area = float(statistics.median(areas))
        computed_p95_area = _percentile(areas, 0.95)
        median_area = float(self.median_block_area_m2)
        p95_area = float(self.p95_block_area_m2)
        if not math.isclose(median_area, computed_median_area, abs_tol=1e-6):
            raise ValueError("median_block_area_m2 does not match blocks")
        if not math.isclose(p95_area, computed_p95_area, abs_tol=1e-6):
            raise ValueError("p95_block_area_m2 does not match blocks")
        if not _MINIMUM_MEDIAN_BLOCK_AREA_M2 <= median_area <= _MAXIMUM_MEDIAN_BLOCK_AREA_M2:
            raise ValueError("median block area is outside [3000, 30000] m2")
        if not 0.0 < p95_area <= _MAXIMUM_P95_BLOCK_AREA_M2:
            raise ValueError("p95 block area exceeds 120000 m2")
        object.__setattr__(self, "street_network_fingerprint", str(self.street_network_fingerprint))
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "links", links)
        object.__setattr__(self, "blocks", blocks)
        object.__setattr__(self, "new_link_to_street_id", mapping)
        object.__setattr__(self, "proper_intersection_count_before", int(self.proper_intersection_count_before))
        object.__setattr__(self, "proper_intersection_count_after", 0)
        object.__setattr__(self, "physical_segment_count", physical_segment_count)
        object.__setattr__(self, "short_segment_share", short_share)
        object.__setattr__(self, "median_block_area_m2", median_area)
        object.__setattr__(self, "p95_block_area_m2", p95_area)
        object.__setattr__(self, "fingerprint", _catalog_fingerprint(self))


def compile_planar_city_blocks(
    network: RealisticStreetNetwork,
) -> CityBlockCatalog:
    """Compile directed planar links and extract all bounded half-edge faces."""

    nodes, links, old_link_to_street_id = _endpoint_topology(network)
    nodes, links, old_link_to_street_id = _split_links_at_existing_nodes(
        nodes=nodes,
        links=links,
        link_to_street_id=old_link_to_street_id,
    )
    geometry = build_endpoint_geometry_catalog(nodes=nodes, links=links)
    planarized = planarize_endpoint_topology(
        nodes=nodes,
        links=links,
        road_geometry=geometry,
    )
    planar_geometry = build_endpoint_geometry_catalog(
        nodes=planarized.nodes,
        links=planarized.links,
    )
    remaining = count_interior_centerline_intersections(planar_geometry)
    if remaining:
        raise ValueError(f"planar block compilation retained {remaining} intersections")
    new_link_to_street_id = {
        new_link_id: old_link_to_street_id[old_link_id]
        for old_link_id, new_link_ids in planarized.old_link_to_new_link_ids.items()
        for new_link_id in new_link_ids
    }
    snapped_nodes, snapped_links, new_link_to_street_id = _snap_planar_graph(
        nodes=planarized.nodes,
        links=planarized.links,
        link_to_street_id=new_link_to_street_id,
        decimal_places=2,
    )
    snapped_nodes, snapped_links, new_link_to_street_id = (
        _collapse_short_planar_links(
            nodes=snapped_nodes,
            links=snapped_links,
            link_to_street_id=new_link_to_street_id,
            minimum_length_m=_MINIMUM_SEGMENT_LENGTH_M,
        )
    )
    blocks = _extract_blocks(
        nodes=snapped_nodes,
        links=snapped_links,
        link_to_street_id=new_link_to_street_id,
    )
    physical_lengths = _physical_segment_lengths(snapped_links)
    short_share = sum(
        length < _MINIMUM_SEGMENT_LENGTH_M for length in physical_lengths
    ) / len(physical_lengths)
    areas = sorted(block.area_m2 for block in blocks)
    median_area = float(statistics.median(areas))
    p95_area = _percentile(areas, 0.95)
    return CityBlockCatalog(
        street_network_fingerprint=network.fingerprint,
        nodes=snapped_nodes,
        links=snapped_links,
        blocks=blocks,
        new_link_to_street_id=new_link_to_street_id,
        proper_intersection_count_before=planarized.proper_intersection_count_before,
        proper_intersection_count_after=planarized.proper_intersection_count_after,
        physical_segment_count=len(physical_lengths),
        short_segment_share=short_share,
        median_block_area_m2=median_area,
        p95_block_area_m2=p95_area,
    )


def _endpoint_topology(
    network: RealisticStreetNetwork,
) -> tuple[tuple[Node, ...], tuple[RoadLink, ...], dict[int, int]]:
    nodes: list[Node] = []
    node_id_by_coordinate: dict[tuple[float, float], int] = {}
    links: list[RoadLink] = []
    link_to_street_id: dict[int, int] = {}
    physical_road_id = 0

    def node_id(point: PointM) -> int:
        key = (round(float(point[0]), 2), round(float(point[1]), 2))
        existing = node_id_by_coordinate.get(key)
        if existing is not None:
            return existing
        value = len(nodes)
        node_id_by_coordinate[key] = value
        nodes.append(Node(node_id=value, x=key[0], y=key[1]))
        return value

    for street in network.streets:
        for left_point, right_point in zip(street.points_m, street.points_m[1:]):
            left_node_id = node_id(left_point)
            right_node_id = node_id(right_point)
            if left_node_id == right_node_id:
                raise ValueError("street segment collapsed after coordinate normalization")
            length_m = math.dist(left_point, right_point)
            for src_node_id, dst_node_id in (
                (left_node_id, right_node_id),
                (right_node_id, left_node_id),
            ):
                link_id = len(links)
                links.append(
                    RoadLink(
                        link_id=link_id,
                        src_node_id=src_node_id,
                        dst_node_id=dst_node_id,
                        road_class=street.road_class,
                        length_m=length_m,
                        free_flow_speed_mps=street.free_flow_speed_mps,
                        capacity_veh_per_tick=street.capacity_veh_per_second,
                        lanes=street.lanes,
                        bridge_group_id=street.bridge_group_id,
                        physical_road_id=physical_road_id,
                    )
                )
                link_to_street_id[link_id] = street.street_id
            physical_road_id += 1
    return tuple(nodes), tuple(links), link_to_street_id


def _snap_planar_graph(
    *,
    nodes: tuple[Node, ...],
    links: tuple[RoadLink, ...],
    link_to_street_id: Mapping[int, int],
    decimal_places: int,
    _remaining_passes: int = 4,
) -> tuple[tuple[Node, ...], tuple[RoadLink, ...], dict[int, int]]:
    canonical_node_id_by_key: dict[tuple[float, float], int] = {}
    old_to_new_node_id: dict[int, int] = {}
    output_nodes: list[Node] = []
    for node in sorted(nodes, key=lambda item: item.node_id):
        key = (round(node.x, decimal_places), round(node.y, decimal_places))
        canonical = canonical_node_id_by_key.get(key)
        if canonical is None:
            canonical = len(output_nodes)
            canonical_node_id_by_key[key] = canonical
            output_nodes.append(
                Node(
                    node_id=canonical,
                    kind=node.kind,
                    x=key[0],
                    y=key[1],
                    zone_id=node.zone_id,
                    signal_group_id=node.signal_group_id,
                )
            )
        old_to_new_node_id[node.node_id] = canonical
    physical_id_by_key: dict[tuple[object, ...], int] = {}
    output_links: list[RoadLink] = []
    output_provenance: dict[int, int] = {}
    seen_directed: set[tuple[object, ...]] = set()
    for link in sorted(links, key=lambda item: item.link_id):
        src_node_id = old_to_new_node_id[link.src_node_id]
        dst_node_id = old_to_new_node_id[link.dst_node_id]
        if src_node_id == dst_node_id:
            continue
        street_id = int(link_to_street_id[link.link_id])
        physical_key = (
            min(src_node_id, dst_node_id),
            max(src_node_id, dst_node_id),
            street_id,
            link.road_class.value,
            link.bridge_group_id,
        )
        physical_road_id = physical_id_by_key.setdefault(
            physical_key,
            len(physical_id_by_key),
        )
        directed_key = (src_node_id, dst_node_id, *physical_key[2:])
        if directed_key in seen_directed:
            continue
        seen_directed.add(directed_key)
        src = output_nodes[src_node_id]
        dst = output_nodes[dst_node_id]
        length_m = math.dist((src.x, src.y), (dst.x, dst.y))
        if length_m <= 0.0:
            continue
        link_id = len(output_links)
        output_links.append(
            RoadLink(
                link_id=link_id,
                src_node_id=src_node_id,
                dst_node_id=dst_node_id,
                road_class=link.road_class,
                length_m=length_m,
                free_flow_speed_mps=link.free_flow_speed_mps,
                capacity_veh_per_tick=link.capacity_veh_per_tick,
                lanes=link.lanes,
                bridge_group_id=link.bridge_group_id,
                is_blockable=link.is_blockable,
                physical_road_id=physical_road_id,
            )
        )
        output_provenance[link_id] = street_id
    snapped_nodes = tuple(output_nodes)
    snapped_links = tuple(output_links)
    snapped_geometry = build_endpoint_geometry_catalog(
        nodes=snapped_nodes,
        links=snapped_links,
    )
    remaining = count_interior_centerline_intersections(snapped_geometry)
    if remaining:
        if _remaining_passes <= 0:
            raise ValueError(
                "coordinate snapping and planarization did not converge"
            )
        refined = planarize_endpoint_topology(
            nodes=snapped_nodes,
            links=snapped_links,
            road_geometry=snapped_geometry,
        )
        refined_provenance = {
            refined_link_id: output_provenance[old_link_id]
            for old_link_id, refined_link_ids in refined.old_link_to_new_link_ids.items()
            for refined_link_id in refined_link_ids
        }
        if refined.proper_intersection_count_after:
            raise ValueError(
                "post-snap planarization retained proper intersections"
            )
        return _snap_planar_graph(
            nodes=refined.nodes,
            links=refined.links,
            link_to_street_id=refined_provenance,
            decimal_places=decimal_places,
            _remaining_passes=_remaining_passes - 1,
        )
    if not snapped_links:
        raise ValueError("coordinate snapping removed every planar link")
    return snapped_nodes, snapped_links, output_provenance


def _split_links_at_existing_nodes(
    *,
    nodes: tuple[Node, ...],
    links: tuple[RoadLink, ...],
    link_to_street_id: Mapping[int, int],
    cell_size_m: float = 250.0,
    tolerance_m: float = 0.02,
) -> tuple[tuple[Node, ...], tuple[RoadLink, ...], dict[int, int]]:
    """Split links where an existing same-layer node forms a T-junction."""

    node_by_id = {node.node_id: node for node in nodes}
    layer_tokens_by_node_id: dict[int, set[int | None]] = {
        node.node_id: set() for node in nodes
    }
    for link in links:
        layer_tokens_by_node_id[link.src_node_id].add(link.bridge_group_id)
        layer_tokens_by_node_id[link.dst_node_id].add(link.bridge_group_id)
    node_ids_by_cell: dict[tuple[int, int], list[int]] = {}
    for node in nodes:
        cell = (
            math.floor(node.x / cell_size_m),
            math.floor(node.y / cell_size_m),
        )
        node_ids_by_cell.setdefault(cell, []).append(node.node_id)
    for node_ids in node_ids_by_cell.values():
        node_ids.sort()

    physical_id_by_key: dict[tuple[object, ...], int] = {}
    output_links: list[RoadLink] = []
    output_provenance: dict[int, int] = {}
    seen_directed: set[tuple[object, ...]] = set()
    for link in sorted(links, key=lambda item: item.link_id):
        src = node_by_id[link.src_node_id]
        dst = node_by_id[link.dst_node_id]
        delta_x = dst.x - src.x
        delta_y = dst.y - src.y
        squared_length = delta_x * delta_x + delta_y * delta_y
        if squared_length <= 0.0:
            raise ValueError("endpoint topology contains a zero-length link")
        min_cell_x = math.floor((min(src.x, dst.x) - tolerance_m) / cell_size_m)
        max_cell_x = math.floor((max(src.x, dst.x) + tolerance_m) / cell_size_m)
        min_cell_y = math.floor((min(src.y, dst.y) - tolerance_m) / cell_size_m)
        max_cell_y = math.floor((max(src.y, dst.y) + tolerance_m) / cell_size_m)
        candidate_node_ids = {
            node_id
            for cell_x in range(min_cell_x, max_cell_x + 1)
            for cell_y in range(min_cell_y, max_cell_y + 1)
            for node_id in node_ids_by_cell.get((cell_x, cell_y), ())
        }
        split_points: list[tuple[float, int]] = [
            (0.0, link.src_node_id),
            (1.0, link.dst_node_id),
        ]
        for node_id in sorted(candidate_node_ids):
            if node_id in {link.src_node_id, link.dst_node_id}:
                continue
            if link.bridge_group_id not in layer_tokens_by_node_id[node_id]:
                continue
            node = node_by_id[node_id]
            parameter = (
                (node.x - src.x) * delta_x + (node.y - src.y) * delta_y
            ) / squared_length
            if not 0.0 < parameter < 1.0:
                continue
            projected = (
                src.x + parameter * delta_x,
                src.y + parameter * delta_y,
            )
            if math.dist((node.x, node.y), projected) <= tolerance_m:
                split_points.append((parameter, node_id))
        split_points.sort(key=lambda item: (item[0], item[1]))
        street_id = int(link_to_street_id[link.link_id])
        for (_, left_node_id), (_, right_node_id) in zip(
            split_points,
            split_points[1:],
        ):
            if left_node_id == right_node_id:
                continue
            physical_key = (
                min(left_node_id, right_node_id),
                max(left_node_id, right_node_id),
                street_id,
                link.road_class.value,
                link.bridge_group_id,
            )
            physical_road_id = physical_id_by_key.setdefault(
                physical_key,
                len(physical_id_by_key),
            )
            directed_key = (left_node_id, right_node_id, *physical_key[2:])
            if directed_key in seen_directed:
                continue
            seen_directed.add(directed_key)
            left = node_by_id[left_node_id]
            right = node_by_id[right_node_id]
            output_link_id = len(output_links)
            output_links.append(
                RoadLink(
                    link_id=output_link_id,
                    src_node_id=left_node_id,
                    dst_node_id=right_node_id,
                    road_class=link.road_class,
                    length_m=math.dist((left.x, left.y), (right.x, right.y)),
                    free_flow_speed_mps=link.free_flow_speed_mps,
                    capacity_veh_per_tick=link.capacity_veh_per_tick,
                    lanes=link.lanes,
                    bridge_group_id=link.bridge_group_id,
                    is_blockable=link.is_blockable,
                    physical_road_id=physical_road_id,
                )
            )
            output_provenance[output_link_id] = street_id
    if not output_links:
        raise ValueError("T-junction normalization removed every link")
    return nodes, tuple(output_links), output_provenance


def _extract_blocks(
    *,
    nodes: tuple[Node, ...],
    links: tuple[RoadLink, ...],
    link_to_street_id: Mapping[int, int],
) -> tuple[CityBlock, ...]:
    node_by_id = {node.node_id: node for node in nodes}
    edge_to_street_ids: dict[tuple[int, int], set[int]] = {}
    for link in links:
        edge = tuple(sorted((link.src_node_id, link.dst_node_id)))
        edge_to_street_ids.setdefault(edge, set()).add(link_to_street_id[link.link_id])
    adjacency: dict[int, set[int]] = {node_id: set() for node_id in node_by_id}
    for left, right in edge_to_street_ids:
        adjacency[left].add(right)
        adjacency[right].add(left)
    ordered_neighbors = {
        node_id: tuple(
            sorted(
                neighbors,
                key=lambda neighbor: math.atan2(
                    node_by_id[neighbor].y - node_by_id[node_id].y,
                    node_by_id[neighbor].x - node_by_id[node_id].x,
                ),
            )
        )
        for node_id, neighbors in adjacency.items()
    }
    visited: set[tuple[int, int]] = set()
    faces: list[tuple[tuple[int, ...], float]] = []
    for start in sorted(
        (left, right) for left, neighbors in adjacency.items() for right in neighbors
    ):
        if start in visited:
            continue
        face_walk = _prune_face_spurs(
            _trace_face(
                start=start,
                ordered_neighbors=ordered_neighbors,
                visited=visited,
            )
        )
        for face in _split_face_walk(face_walk):
            if len(face) < 3:
                continue
            polygon = tuple(
                (node_by_id[node_id].x, node_by_id[node_id].y)
                for node_id in face
            )
            signed_area = _signed_area((*polygon, polygon[0]))
            if signed_area > 1e-6:
                faces.append((face, signed_area))
    blocks: list[CityBlock] = []
    for face, area in sorted(faces, key=lambda item: _face_sort_key(item[0], node_by_id)):
        polygon = tuple((node_by_id[node_id].x, node_by_id[node_id].y) for node_id in face)
        closed_polygon = (*polygon, polygon[0])
        if area < _MINIMUM_BLOCK_AREA_M2:
            raise ValueError(f"planar compilation produced tiny block area {area:.3f} m2")
        frontage = {
            street_id
            for left, right in zip(face, (*face[1:], face[0]))
            for street_id in edge_to_street_ids[tuple(sorted((left, right)))]
        }
        blocks.append(
            CityBlock(
                block_id=len(blocks),
                polygon_m=closed_polygon,
                area_m2=area,
                perimeter_m=sum(
                    math.dist(left, right)
                    for left, right in zip(closed_polygon, closed_polygon[1:])
                ),
                frontage_street_ids=tuple(frontage),
            )
        )
    if not blocks:
        raise ValueError("planar street graph contains no bounded blocks")
    return tuple(blocks)


def _collapse_short_planar_links(
    *,
    nodes: tuple[Node, ...],
    links: tuple[RoadLink, ...],
    link_to_street_id: Mapping[int, int],
    minimum_length_m: float,
    _remaining_passes: int = 4,
) -> tuple[tuple[Node, ...], tuple[RoadLink, ...], dict[int, int]]:
    node_by_id = {node.node_id: node for node in nodes}
    parent = {node.node_id: node.node_id for node in nodes}

    def find(node_id: int) -> int:
        while parent[node_id] != node_id:
            parent[node_id] = parent[parent[node_id]]
            node_id = parent[node_id]
        return node_id

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        lower, upper = sorted((left_root, right_root))
        parent[upper] = lower

    for link in links:
        src = node_by_id[link.src_node_id]
        dst = node_by_id[link.dst_node_id]
        if math.dist((src.x, src.y), (dst.x, dst.y)) < minimum_length_m:
            union(link.src_node_id, link.dst_node_id)
    groups: dict[int, list[Node]] = {}
    for node in nodes:
        groups.setdefault(find(node.node_id), []).append(node)
    if all(len(group) == 1 for group in groups.values()):
        return nodes, links, dict(link_to_street_id)
    output_nodes: list[Node] = []
    old_to_new_node_id: dict[int, int] = {}
    for root in sorted(groups):
        group = sorted(groups[root], key=lambda item: item.node_id)
        representative = group[0]
        node_id = len(output_nodes)
        output_nodes.append(
            Node(
                node_id=node_id,
                kind=representative.kind,
                x=round(sum(node.x for node in group) / len(group), 2),
                y=round(sum(node.y for node in group) / len(group), 2),
                zone_id=representative.zone_id,
                signal_group_id=representative.signal_group_id,
            )
        )
        for node in group:
            old_to_new_node_id[node.node_id] = node_id
    output_links: list[RoadLink] = []
    output_provenance: dict[int, int] = {}
    physical_id_by_key: dict[tuple[object, ...], int] = {}
    seen_directed: set[tuple[object, ...]] = set()
    for link in sorted(links, key=lambda item: item.link_id):
        src_node_id = old_to_new_node_id[link.src_node_id]
        dst_node_id = old_to_new_node_id[link.dst_node_id]
        if src_node_id == dst_node_id:
            continue
        street_id = int(link_to_street_id[link.link_id])
        physical_key = (
            min(src_node_id, dst_node_id),
            max(src_node_id, dst_node_id),
            street_id,
            link.road_class.value,
            link.bridge_group_id,
        )
        physical_road_id = physical_id_by_key.setdefault(
            physical_key,
            len(physical_id_by_key),
        )
        directed_key = (src_node_id, dst_node_id, *physical_key[2:])
        if directed_key in seen_directed:
            continue
        seen_directed.add(directed_key)
        src = output_nodes[src_node_id]
        dst = output_nodes[dst_node_id]
        length_m = math.dist((src.x, src.y), (dst.x, dst.y))
        if length_m <= 0.0:
            continue
        link_id = len(output_links)
        output_links.append(
            RoadLink(
                link_id=link_id,
                src_node_id=src_node_id,
                dst_node_id=dst_node_id,
                road_class=link.road_class,
                length_m=length_m,
                free_flow_speed_mps=link.free_flow_speed_mps,
                capacity_veh_per_tick=link.capacity_veh_per_tick,
                lanes=link.lanes,
                bridge_group_id=link.bridge_group_id,
                is_blockable=link.is_blockable,
                physical_road_id=physical_road_id,
            )
        )
        output_provenance[link_id] = street_id
    if not output_links:
        raise ValueError("short-segment collapse removed every planar link")
    collapsed_nodes = tuple(output_nodes)
    collapsed_links = tuple(output_links)
    geometry = build_endpoint_geometry_catalog(
        nodes=collapsed_nodes,
        links=collapsed_links,
    )
    remaining = count_interior_centerline_intersections(geometry)
    if remaining:
        if _remaining_passes <= 0:
            raise ValueError("short-segment normalization did not converge")
        refined = planarize_endpoint_topology(
            nodes=collapsed_nodes,
            links=collapsed_links,
            road_geometry=geometry,
        )
        refined_provenance = {
            new_link_id: output_provenance[old_link_id]
            for old_link_id, new_link_ids in refined.old_link_to_new_link_ids.items()
            for new_link_id in new_link_ids
        }
        snapped_nodes, snapped_links, snapped_provenance = _snap_planar_graph(
            nodes=refined.nodes,
            links=refined.links,
            link_to_street_id=refined_provenance,
            decimal_places=2,
        )
        return _collapse_short_planar_links(
            nodes=snapped_nodes,
            links=snapped_links,
            link_to_street_id=snapped_provenance,
            minimum_length_m=minimum_length_m,
            _remaining_passes=_remaining_passes - 1,
        )
    if any(link.length_m < minimum_length_m for link in collapsed_links):
        if _remaining_passes <= 0:
            raise ValueError("short physical segments remain after normalization")
        return _collapse_short_planar_links(
            nodes=collapsed_nodes,
            links=collapsed_links,
            link_to_street_id=output_provenance,
            minimum_length_m=minimum_length_m,
            _remaining_passes=_remaining_passes - 1,
        )
    return collapsed_nodes, collapsed_links, output_provenance


def _trace_face(
    *,
    start: tuple[int, int],
    ordered_neighbors: Mapping[int, tuple[int, ...]],
    visited: set[tuple[int, int]],
) -> tuple[int, ...]:
    face: list[int] = []
    edge = start
    limit = sum(len(neighbors) for neighbors in ordered_neighbors.values()) + 1
    for _ in range(limit):
        if edge in visited and edge != start:
            return ()
        visited.add(edge)
        left, right = edge
        face.append(left)
        neighbors = ordered_neighbors[right]
        if not neighbors:
            return ()
        incoming_index = neighbors.index(left)
        next_node = neighbors[(incoming_index - 1) % len(neighbors)]
        edge = (right, next_node)
        if edge == start:
            return tuple(face)
    raise ValueError("half-edge face traversal exceeded deterministic limit")


def _prune_face_spurs(face: tuple[int, ...]) -> tuple[int, ...]:
    """Remove tree-edge out-and-back walks from a half-edge face boundary."""

    output = list(face)
    changed = True
    while changed and len(output) >= 3:
        changed = False
        for index in range(len(output)):
            if output[index - 1] != output[(index + 1) % len(output)]:
                continue
            del output[index]
            del output[(index - 1) % len(output)]
            changed = True
            break
    return tuple(output)


def _split_face_walk(face: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
    """Split a face walk into simple cycles at articulation vertices."""

    first_index_by_node: dict[int, int] = {}
    for index, node_id in enumerate(face):
        first_index = first_index_by_node.get(node_id)
        if first_index is None:
            first_index_by_node[node_id] = index
            continue
        cycle = face[first_index:index]
        remainder = (*face[:first_index], *face[index:])
        output: list[tuple[int, ...]] = []
        if len(cycle) >= 3:
            output.extend(_split_face_walk(cycle))
        if len(remainder) >= 3:
            output.extend(_split_face_walk(remainder))
        return tuple(output)
    return (face,) if len(face) >= 3 else ()


def _validate_block_frontage(
    *,
    nodes: tuple[Node, ...],
    links: tuple[RoadLink, ...],
    blocks: tuple[CityBlock, ...],
    link_to_street_id: Mapping[int, int],
) -> None:
    node_id_by_point = {(node.x, node.y): node.node_id for node in nodes}
    street_ids_by_edge: dict[tuple[int, int], set[int]] = {}
    for link in links:
        edge = tuple(sorted((link.src_node_id, link.dst_node_id)))
        street_ids_by_edge.setdefault(edge, set()).add(
            int(link_to_street_id[link.link_id])
        )
    for block in blocks:
        boundary_street_ids: set[int] = set()
        for left_point, right_point in zip(
            block.polygon_m,
            block.polygon_m[1:],
        ):
            try:
                edge = tuple(
                    sorted(
                        (
                            node_id_by_point[left_point],
                            node_id_by_point[right_point],
                        )
                    )
                )
                boundary_street_ids.update(street_ids_by_edge[edge])
            except KeyError as error:
                raise ValueError(
                    f"block {block.block_id} boundary is not a planar road edge"
                ) from error
        if tuple(sorted(boundary_street_ids)) != block.frontage_street_ids:
            raise ValueError(
                f"block {block.block_id} frontage does not match planar road edges"
            )


def _physical_segment_lengths(links: tuple[RoadLink, ...]) -> tuple[float, ...]:
    lengths: dict[int, float] = {}
    for link in links:
        if link.physical_road_id is None:
            raise ValueError("planar links require physical_road_id")
        existing = lengths.setdefault(link.physical_road_id, link.length_m)
        if not math.isclose(existing, link.length_m, abs_tol=1e-6):
            raise ValueError("directed physical-road lengths disagree")
    return tuple(lengths[key] for key in sorted(lengths))


def _signed_area(polygon: tuple[PointM, ...]) -> float:
    return 0.5 * sum(
        left[0] * right[1] - right[0] * left[1]
        for left, right in zip(polygon, polygon[1:])
    )


def _is_simple_polygon(polygon: tuple[PointM, ...]) -> bool:
    edge_count = len(polygon) - 1
    for left_index in range(edge_count):
        left_edge = (polygon[left_index], polygon[left_index + 1])
        for right_index in range(left_index + 1, edge_count):
            if right_index in {
                left_index,
                left_index + 1,
            } or (left_index == 0 and right_index == edge_count - 1):
                continue
            right_edge = (polygon[right_index], polygon[right_index + 1])
            if _segments_intersect(left_edge, right_edge):
                return False
    return True


def _segments_intersect(
    left: tuple[PointM, PointM],
    right: tuple[PointM, PointM],
) -> bool:
    def orientation(first: PointM, second: PointM, third: PointM) -> float:
        return (second[0] - first[0]) * (third[1] - first[1]) - (
            second[1] - first[1]
        ) * (third[0] - first[0])

    left_first = orientation(left[0], left[1], right[0])
    left_second = orientation(left[0], left[1], right[1])
    right_first = orientation(right[0], right[1], left[0])
    right_second = orientation(right[0], right[1], left[1])
    tolerance = 1e-9
    if any(
        abs(value) <= tolerance
        for value in (left_first, left_second, right_first, right_second)
    ):
        return _segments_touch_or_overlap(left, right, tolerance=tolerance)
    return (left_first > 0.0) != (left_second > 0.0) and (
        right_first > 0.0
    ) != (right_second > 0.0)


def _segments_touch_or_overlap(
    left: tuple[PointM, PointM],
    right: tuple[PointM, PointM],
    *,
    tolerance: float,
) -> bool:
    def on_segment(first: PointM, second: PointM, point: PointM) -> bool:
        cross = (second[0] - first[0]) * (point[1] - first[1]) - (
            second[1] - first[1]
        ) * (point[0] - first[0])
        return abs(cross) <= tolerance and (
            min(first[0], second[0]) - tolerance
            <= point[0]
            <= max(first[0], second[0]) + tolerance
            and min(first[1], second[1]) - tolerance
            <= point[1]
            <= max(first[1], second[1]) + tolerance
        )

    return any(
        on_segment(first, second, point)
        for first, second, point in (
            (left[0], left[1], right[0]),
            (left[0], left[1], right[1]),
            (right[0], right[1], left[0]),
            (right[0], right[1], left[1]),
        )
    )


def _face_sort_key(
    face: tuple[int, ...],
    node_by_id: Mapping[int, Node],
) -> tuple[float, float, tuple[int, ...]]:
    points = tuple((node_by_id[node_id].x, node_by_id[node_id].y) for node_id in face)
    return (
        round(sum(point[1] for point in points) / len(points), 6),
        round(sum(point[0] for point in points) / len(points), 6),
        face,
    )


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    position = (len(values) - 1) * float(quantile)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(values[lower])
    weight = position - lower
    return float(values[lower] * (1.0 - weight) + values[upper] * weight)


def _catalog_fingerprint(catalog: CityBlockCatalog) -> str:
    payload = {
        "schema": "city_block_catalog_v1",
        "street_network": catalog.street_network_fingerprint,
        "nodes": [(node.node_id, node.x, node.y) for node in catalog.nodes],
        "links": [
            (
                link.link_id,
                link.src_node_id,
                link.dst_node_id,
                link.road_class.value,
                link.length_m,
                link.free_flow_speed_mps,
                link.capacity_veh_per_tick,
                link.lanes,
                link.bridge_group_id,
                link.physical_road_id,
                catalog.new_link_to_street_id[link.link_id],
            )
            for link in catalog.links
        ],
        "blocks": [
            (
                block.block_id,
                block.polygon_m,
                block.area_m2,
                block.perimeter_m,
                block.frontage_street_ids,
            )
            for block in catalog.blocks
        ],
        "proper_intersection_count_before": catalog.proper_intersection_count_before,
        "physical_segment_count": catalog.physical_segment_count,
        "short_segment_share": catalog.short_segment_share,
        "median_block_area_m2": catalog.median_block_area_m2,
        "p95_block_area_m2": catalog.p95_block_area_m2,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
