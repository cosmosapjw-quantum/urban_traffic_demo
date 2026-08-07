"""Dependency-free morphometrics for generated physical street networks."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from metroflow.map.road_geometry import RoadGeometryCatalog

__all__ = ["StreetNetworkMorphometrics", "compute_street_network_morphometrics"]


class _TopologyLike(Protocol):
    nodes: tuple[Any, ...]
    links: tuple[Any, ...]
    road_geometry: RoadGeometryCatalog | None


@dataclass(frozen=True, slots=True)
class StreetNetworkMorphometrics:
    orientation_entropy: float
    orientation_order: float
    median_segment_length_m: float
    circuity: float
    mean_node_degree: float
    dead_end_share: float
    four_way_share: float
    physical_segment_count: int
    orientation_bin_count: int = 36
    evidence_status: str = "diagnostic"

    def as_dict(self) -> Mapping[str, int | float | str]:
        return MappingProxyType(
            {
                "orientation_entropy": self.orientation_entropy,
                "orientation_order": self.orientation_order,
                "median_segment_length_m": self.median_segment_length_m,
                "circuity": self.circuity,
                "mean_node_degree": self.mean_node_degree,
                "dead_end_share": self.dead_end_share,
                "four_way_share": self.four_way_share,
                "physical_segment_count": self.physical_segment_count,
                "orientation_bin_count": self.orientation_bin_count,
                "evidence_status": self.evidence_status,
            }
        )


def compute_street_network_morphometrics(
    topology: _TopologyLike,
    *,
    simplify_interstitial_nodes: bool = False,
) -> StreetNetworkMorphometrics:
    """Compute Boeing-compatible diagnostic metrics on physical centerlines.

    The pinned empirical corpus reports OSMnx values measured after
    ``simplify_graph`` contracts degree-2 interstitial nodes. Pass
    ``simplify_interstitial_nodes=True`` to measure the same way; otherwise every
    compiled node is counted and node spacing, rather than morphology, controls
    ``mean_node_degree`` and ``dead_end_share``.
    """

    geometry = topology.road_geometry
    if not isinstance(geometry, RoadGeometryCatalog):
        raise ValueError("road_geometry is required for street-network morphometrics")
    centerlines = tuple(geometry.centerlines)
    if not centerlines:
        raise ValueError("road_geometry must contain at least one centerline")

    if simplify_interstitial_nodes:
        segments, degree_by_node_id = _simplified_segments(topology, geometry)
    else:
        segments, degree_by_node_id = _compiled_segments(topology, geometry)

    orientation_counts = [0] * 36
    lengths: list[float] = []
    straight_lengths: list[float] = []
    for arc_length_m, start, end, bearing_pairs in segments:
        for left, right in bearing_pairs:
            dx = float(right[0]) - float(left[0])
            dy = float(right[1]) - float(left[1])
            if math.hypot(dx, dy) <= 0.0:
                continue
            bearing = math.degrees(math.atan2(dx, dy)) % 360.0
            for value in (bearing, (bearing + 180.0) % 360.0):
                orientation_counts[int(((value + 5.0) % 360.0) // 10.0)] += 1
        straight = math.hypot(float(end[0]) - float(start[0]), float(end[1]) - float(start[1]))
        if straight <= 0.0:
            # A junction-free ring has no chord. It still has length and must
            # stay countable, but it carries no circuity signal.
            lengths.append(float(arc_length_m))
            continue
        lengths.append(float(arc_length_m))
        straight_lengths.append(straight)
    if not lengths:
        raise ValueError("road_geometry contains no measurable centerlines")

    total_orientations = sum(orientation_counts)
    if total_orientations == 0:
        raise ValueError("road_geometry contains no orientable centerlines")
    entropy = -sum(
        probability * math.log(probability)
        for count in orientation_counts
        if count
        for probability in (count / total_orientations,)
    )
    grid_entropy = math.log(4.0)
    maximum_entropy = math.log(36.0)
    orientation_order = 1.0 - (
        (entropy - grid_entropy) / (maximum_entropy - grid_entropy)
    ) ** 2
    orientation_order = min(max(orientation_order, 0.0), 1.0)

    degrees = tuple(degree_by_node_id.values())
    node_count = max(len(degrees), 1)
    return StreetNetworkMorphometrics(
        orientation_entropy=float(entropy),
        orientation_order=float(orientation_order),
        median_segment_length_m=float(statistics.median(lengths)),
        circuity=float(sum(lengths) / max(sum(straight_lengths), 1e-12)),
        mean_node_degree=float(sum(degrees) / node_count),
        dead_end_share=float(sum(degree == 1 for degree in degrees) / node_count),
        four_way_share=float(sum(degree == 4 for degree in degrees) / node_count),
        physical_segment_count=len(lengths),
    )


_PointM = tuple[float, float]
# One measured street: arc length in meters, chord endpoints, and the sub-segment
# endpoint pairs whose bearings enter the orientation histogram.
_Segment = tuple[float, _PointM, _PointM, tuple[tuple[_PointM, _PointM], ...]]


def _undirected_edges(
    topology: _TopologyLike,
    geometry: RoadGeometryCatalog,
) -> tuple[tuple[int, int, float], ...]:
    """Collapse directed link pairs into unique undirected physical segments."""

    link_by_id = {int(link.link_id): link for link in topology.links}
    seen_pairs: set[tuple[int, int, int]] = set()
    edges: list[tuple[int, int, float]] = []
    for assignment in geometry.assignments:
        link = link_by_id.get(int(assignment.link_id))
        if link is None:
            raise ValueError(f"geometry assignment references missing link {assignment.link_id}")
        left = min(int(link.src_node_id), int(link.dst_node_id))
        right = max(int(link.src_node_id), int(link.dst_node_id))
        geometry_id = int(assignment.geometry_id)
        key = (geometry_id, left, right)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        edges.append((left, right, float(geometry.centerline(geometry_id).length_m)))
    return tuple(edges)


def _compiled_segments(
    topology: _TopologyLike,
    geometry: RoadGeometryCatalog,
) -> tuple[tuple[_Segment, ...], dict[int, int]]:
    """Measure every compiled node and centerline as-is."""

    degree_by_node_id = {int(node.node_id): 0 for node in topology.nodes}
    for left, right, _length_m in _undirected_edges(topology, geometry):
        degree_by_node_id[left] = degree_by_node_id.get(left, 0) + 1
        degree_by_node_id[right] = degree_by_node_id.get(right, 0) + 1

    segments = tuple(
        (
            float(centerline.length_m),
            centerline.points_m[0],
            centerline.points_m[-1],
            ((centerline.points_m[0], centerline.points_m[-1]),),
        )
        for centerline in geometry.centerlines
    )
    return segments, degree_by_node_id


def _simplified_segments(
    topology: _TopologyLike,
    geometry: RoadGeometryCatalog,
) -> tuple[tuple[_Segment, ...], dict[int, int]]:
    """Contract degree-2 interstitial nodes, as OSMnx `simplify_graph` does.

    Chains between junctions or dead ends become a single measured street whose
    length is the summed arc length of its members. Interstitial and isolated
    nodes leave the measured node set entirely.
    """

    point_by_node_id = {
        int(node.node_id): (float(node.x), float(node.y)) for node in topology.nodes
    }
    edges = _undirected_edges(topology, geometry)

    compiled_degree: dict[int, int] = {}
    adjacency: dict[int, list[int]] = {}
    for index, (left, right, _length_m) in enumerate(edges):
        for node_id in (left, right):
            compiled_degree[node_id] = compiled_degree.get(node_id, 0) + 1
            adjacency.setdefault(node_id, []).append(index)

    segments: list[_Segment] = []
    degree_by_node_id: dict[int, int] = {}
    consumed: set[int] = set()

    def _other(edge_index: int, node_id: int) -> int:
        left, right, _length_m = edges[edge_index]
        return right if left == node_id else left

    def _emit(
        start_node_id: int,
        end_node_id: int,
        arc_length_m: float,
        members: list[int],
    ) -> None:
        segments.append(
            (
                arc_length_m,
                point_by_node_id[start_node_id],
                point_by_node_id[end_node_id],
                tuple(
                    (point_by_node_id[edges[index][0]], point_by_node_id[edges[index][1]])
                    for index in members
                ),
            )
        )
        for node_id in (start_node_id, end_node_id):
            degree_by_node_id[node_id] = degree_by_node_id.get(node_id, 0) + 1

    anchors = sorted(
        node_id for node_id, degree in compiled_degree.items() if degree != 2
    )
    for anchor in anchors:
        for start_edge in adjacency[anchor]:
            if start_edge in consumed:
                continue
            arc_length_m = 0.0
            members: list[int] = []
            previous_node_id = anchor
            edge_index = start_edge
            while True:
                consumed.add(edge_index)
                members.append(edge_index)
                arc_length_m += edges[edge_index][2]
                next_node_id = _other(edge_index, previous_node_id)
                if compiled_degree.get(next_node_id, 0) != 2:
                    break
                onward = [
                    candidate
                    for candidate in adjacency[next_node_id]
                    if candidate not in consumed
                ]
                if not onward:
                    break
                edge_index = onward[0]
                previous_node_id = next_node_id
            _emit(anchor, next_node_id, arc_length_m, members)

    # Whatever survives is a ring of degree-2 nodes with no junction to anchor
    # it. Keep its lowest node id so the ring stays measurable and deterministic.
    for index, (left, right, _length_m) in enumerate(edges):
        if index in consumed:
            continue
        anchor = min(left, right)
        arc_length_m = 0.0
        members = []
        previous_node_id = anchor
        edge_index = index
        while True:
            consumed.add(edge_index)
            members.append(edge_index)
            arc_length_m += edges[edge_index][2]
            next_node_id = _other(edge_index, previous_node_id)
            onward = [
                candidate
                for candidate in adjacency[next_node_id]
                if candidate not in consumed
            ]
            if not onward:
                break
            edge_index = onward[0]
            previous_node_id = next_node_id
        _emit(anchor, anchor, arc_length_m, members)

    return tuple(segments), degree_by_node_id
