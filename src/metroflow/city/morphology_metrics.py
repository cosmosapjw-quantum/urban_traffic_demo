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
) -> StreetNetworkMorphometrics:
    """Compute Boeing-compatible diagnostic metrics on physical centerlines."""

    geometry = topology.road_geometry
    if not isinstance(geometry, RoadGeometryCatalog):
        raise ValueError("road_geometry is required for street-network morphometrics")
    centerlines = tuple(geometry.centerlines)
    if not centerlines:
        raise ValueError("road_geometry must contain at least one centerline")

    orientation_counts = [0] * 36
    lengths: list[float] = []
    straight_lengths: list[float] = []
    for centerline in centerlines:
        start = centerline.points_m[0]
        end = centerline.points_m[-1]
        dx = float(end[0]) - float(start[0])
        dy = float(end[1]) - float(start[1])
        straight = math.hypot(dx, dy)
        if straight <= 0.0:
            continue
        bearing = math.degrees(math.atan2(dx, dy)) % 360.0
        for value in (bearing, (bearing + 180.0) % 360.0):
            orientation_counts[int(((value + 5.0) % 360.0) // 10.0)] += 1
        lengths.append(float(centerline.length_m))
        straight_lengths.append(straight)
    if not lengths:
        raise ValueError("road_geometry contains no measurable centerlines")

    total_orientations = sum(orientation_counts)
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

    degree_by_node_id = {int(node.node_id): 0 for node in topology.nodes}
    link_by_id = {int(link.link_id): link for link in topology.links}
    seen_pairs: set[tuple[int, int, int]] = set()
    for assignment in geometry.assignments:
        link = link_by_id.get(int(assignment.link_id))
        if link is None:
            raise ValueError(f"geometry assignment references missing link {assignment.link_id}")
        left = min(int(link.src_node_id), int(link.dst_node_id))
        right = max(int(link.src_node_id), int(link.dst_node_id))
        key = (int(assignment.geometry_id), left, right)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        degree_by_node_id[left] = degree_by_node_id.get(left, 0) + 1
        degree_by_node_id[right] = degree_by_node_id.get(right, 0) + 1

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
