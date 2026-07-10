"""Structural quality metrics for generated physical street networks."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from metroflow.city.graph import RoadClass
from metroflow.map.road_geometry import RoadGeometryCatalog

__all__ = [
    "MorphologyQualityMetrics",
    "MorphologyQualityGate",
    "GLOBAL_STREET_CELL_GRID_RESOLUTION",
    "MORPHOLOGY_QUALITY_GATE_THRESHOLDS",
    "compute_morphology_quality_metrics",
    "evaluate_morphology_quality_gate",
]

MORPHOLOGY_QUALITY_GATE_VERSION = "morphology_quality_v2"
GLOBAL_STREET_CELL_GRID_RESOLUTION = 24
GLOBAL_LOCAL_JUNCTION_GRID_RESOLUTION = 12
GLOBAL_LOCAL_JUNCTION_RADIUS_CELLS = 0.5
MORPHOLOGY_QUALITY_GATE_THRESHOLDS = MappingProxyType(
    {
        "minimum_street_density_km_per_km2": 10.0,
        "minimum_block_continuity": 0.85,
        "maximum_dead_end_share": 0.15,
        "minimum_district_quadrant_presence_share": 0.90,
        "maximum_mixed_grid_four_way_share": 0.62,
        "maximum_river_dead_end_share": 0.13,
        "minimum_river_block_continuity": 0.87,
        "minimum_global_local_street_cell_presence_share": 0.40,
        "minimum_global_local_junction_proximity_share": 0.40,
    }
)


class _TopologyLike(Protocol):
    nodes: tuple[Any, ...]
    links: tuple[Any, ...]
    road_geometry: RoadGeometryCatalog | None
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class MorphologyQualityMetrics:
    """Project-owned diagnostics with explicit physical-network units."""

    convex_hull_area_m2: float
    physical_road_length_m: float
    street_density_km_per_km2: float
    block_continuity: float
    bridge_length_share: float
    connector_to_local_length_ratio: float
    median_local_length_m: float
    median_connector_length_m: float
    degree_one_share: float
    degree_two_share: float
    degree_three_share: float
    degree_four_share: float
    degree_five_plus_share: float
    district_quadrant_presence_share: float
    global_street_cell_presence_share: float
    global_local_street_cell_presence_share: float
    coverage_grid_resolution: int
    global_local_junction_proximity_share: float
    junction_grid_resolution: int
    junction_proximity_radius_cells: float
    weak_component_count: int
    district_count: int
    physical_segment_count: int
    evidence_status: str = "diagnostic"

    def __post_init__(self) -> None:
        finite_fields = (
            self.convex_hull_area_m2,
            self.physical_road_length_m,
            self.street_density_km_per_km2,
            self.block_continuity,
            self.bridge_length_share,
            self.connector_to_local_length_ratio,
            self.median_local_length_m,
            self.median_connector_length_m,
            self.degree_one_share,
            self.degree_two_share,
            self.degree_three_share,
            self.degree_four_share,
            self.degree_five_plus_share,
            self.district_quadrant_presence_share,
            self.global_street_cell_presence_share,
            self.global_local_street_cell_presence_share,
            self.global_local_junction_proximity_share,
            self.junction_proximity_radius_cells,
        )
        if not all(math.isfinite(value) for value in finite_fields):
            raise ValueError("morphology quality metric values must be finite")
        if self.convex_hull_area_m2 <= 0.0 or self.physical_road_length_m <= 0.0:
            raise ValueError("morphology area and physical road length must be > 0")
        nonnegative = (
            self.street_density_km_per_km2,
            self.connector_to_local_length_ratio,
            self.median_local_length_m,
            self.median_connector_length_m,
        )
        if any(value < 0.0 for value in nonnegative):
            raise ValueError("morphology density, ratios, and lengths must be >= 0")
        shares = (
            self.block_continuity,
            self.bridge_length_share,
            self.degree_one_share,
            self.degree_two_share,
            self.degree_three_share,
            self.degree_four_share,
            self.degree_five_plus_share,
            self.district_quadrant_presence_share,
            self.global_street_cell_presence_share,
            self.global_local_street_cell_presence_share,
            self.global_local_junction_proximity_share,
        )
        if any(value < 0.0 or value > 1.0 for value in shares):
            raise ValueError("morphology quality shares must be in [0, 1]")
        if not math.isclose(
            self.block_continuity + self.bridge_length_share,
            1.0,
            abs_tol=1e-9,
        ):
            raise ValueError("block_continuity and bridge_length_share must sum to 1")
        if sum(shares[2:7]) > 1.0 + 1e-9:
            raise ValueError("node degree shares must not sum above 1")
        if self.weak_component_count < 1:
            raise ValueError("weak_component_count must be >= 1")
        if self.coverage_grid_resolution < 1:
            raise ValueError("coverage_grid_resolution must be >= 1")
        if self.junction_grid_resolution < 1:
            raise ValueError("junction_grid_resolution must be >= 1")
        if self.junction_proximity_radius_cells <= 0.0:
            raise ValueError("junction_proximity_radius_cells must be > 0")
        if self.district_count < 0:
            raise ValueError("district_count must be >= 0")
        if self.physical_segment_count < 1:
            raise ValueError("physical_segment_count must be >= 1")

    def as_dict(self) -> Mapping[str, int | float | str]:
        return MappingProxyType(
            {
                "convex_hull_area_m2": self.convex_hull_area_m2,
                "physical_road_length_m": self.physical_road_length_m,
                "street_density_km_per_km2": self.street_density_km_per_km2,
                "block_continuity": self.block_continuity,
                "bridge_length_share": self.bridge_length_share,
                "connector_to_local_length_ratio": self.connector_to_local_length_ratio,
                "median_local_length_m": self.median_local_length_m,
                "median_connector_length_m": self.median_connector_length_m,
                "degree_one_share": self.degree_one_share,
                "degree_two_share": self.degree_two_share,
                "degree_three_share": self.degree_three_share,
                "degree_four_share": self.degree_four_share,
                "degree_five_plus_share": self.degree_five_plus_share,
                "district_quadrant_presence_share": self.district_quadrant_presence_share,
                "global_street_cell_presence_share": self.global_street_cell_presence_share,
                "global_local_street_cell_presence_share": self.global_local_street_cell_presence_share,
                "coverage_grid_resolution": self.coverage_grid_resolution,
                "global_local_junction_proximity_share": self.global_local_junction_proximity_share,
                "junction_grid_resolution": self.junction_grid_resolution,
                "junction_proximity_radius_cells": self.junction_proximity_radius_cells,
                "weak_component_count": self.weak_component_count,
                "district_count": self.district_count,
                "physical_segment_count": self.physical_segment_count,
                "evidence_status": self.evidence_status,
            }
        )


@dataclass(frozen=True, slots=True)
class MorphologyQualityGate:
    """Versioned project-owned structural admission result."""

    accepted: bool
    gate_version: str
    gate_scope: str
    style_id: str
    geometry_fingerprint: str
    metrics_digest: str
    failures: tuple[str, ...]

    def as_dict(self) -> Mapping[str, bool | str | tuple[str, ...]]:
        return MappingProxyType(
            {
                "accepted": self.accepted,
                "gate_version": self.gate_version,
                "gate_scope": self.gate_scope,
                "style_id": self.style_id,
                "geometry_fingerprint": self.geometry_fingerprint,
                "metrics_digest": self.metrics_digest,
                "failures": self.failures,
            }
        )


@dataclass(frozen=True, slots=True)
class _PhysicalEdge:
    edge_id: int
    src_node_id: int
    dst_node_id: int
    length_m: float
    road_class: RoadClass
    points_m: tuple[tuple[float, float], ...]


def compute_morphology_quality_metrics(
    topology: _TopologyLike,
) -> MorphologyQualityMetrics:
    """Measure continuity, density, hierarchy, and district quadrant presence."""

    edges = _physical_edges(topology)
    if not edges:
        raise ValueError("road_geometry must contain at least one assigned centerline")
    hull = _convex_hull(
        tuple((float(node.x), float(node.y)) for node in topology.nodes)
    )
    hull_area_m2 = _polygon_area(hull)
    if hull_area_m2 <= 0.0:
        raise ValueError("topology nodes must span a positive convex-hull area")

    total_length = sum(edge.length_m for edge in edges)
    bridge_ids = _undirected_bridge_edge_ids(edges)
    bridge_length = sum(edge.length_m for edge in edges if edge.edge_id in bridge_ids)
    local_lengths = tuple(
        edge.length_m for edge in edges if edge.road_class == RoadClass.LOCAL
    )
    connector_lengths = tuple(
        edge.length_m for edge in edges if edge.road_class != RoadClass.LOCAL
    )
    degree_by_node = {int(node.node_id): 0 for node in topology.nodes}
    for edge in edges:
        degree_by_node[edge.src_node_id] = degree_by_node.get(edge.src_node_id, 0) + 1
        degree_by_node[edge.dst_node_id] = degree_by_node.get(edge.dst_node_id, 0) + 1
    degrees = tuple(degree_by_node.values())
    node_count = max(len(degrees), 1)
    district_envelopes = _coerce_polygons(
        topology.metadata.get("district_envelopes", ())
    )
    weak_component_count = _weak_component_count(
        edges=edges,
        node_ids=tuple(int(node.node_id) for node in topology.nodes),
    )
    global_street_cell_presence_share = _global_street_cell_presence(
        edges=edges,
        hull=hull,
        resolution=GLOBAL_STREET_CELL_GRID_RESOLUTION,
    )
    global_local_street_cell_presence_share = _global_street_cell_presence(
        edges=tuple(edge for edge in edges if edge.road_class == RoadClass.LOCAL),
        hull=hull,
        resolution=GLOBAL_STREET_CELL_GRID_RESOLUTION,
    )
    global_local_junction_proximity_share = _global_local_junction_proximity(
        edges=edges,
        node_points={
            int(node.node_id): (float(node.x), float(node.y))
            for node in topology.nodes
        },
        hull=hull,
        resolution=GLOBAL_LOCAL_JUNCTION_GRID_RESOLUTION,
        radius_cells=GLOBAL_LOCAL_JUNCTION_RADIUS_CELLS,
    )

    return MorphologyQualityMetrics(
        convex_hull_area_m2=float(hull_area_m2),
        physical_road_length_m=float(total_length),
        street_density_km_per_km2=float(total_length * 1_000.0 / hull_area_m2),
        block_continuity=float(1.0 - bridge_length / total_length),
        bridge_length_share=float(bridge_length / total_length),
        connector_to_local_length_ratio=float(
            sum(connector_lengths) / max(sum(local_lengths), 1e-12)
        ),
        median_local_length_m=_median_or_zero(local_lengths),
        median_connector_length_m=_median_or_zero(connector_lengths),
        degree_one_share=float(sum(value == 1 for value in degrees) / node_count),
        degree_two_share=float(sum(value == 2 for value in degrees) / node_count),
        degree_three_share=float(sum(value == 3 for value in degrees) / node_count),
        degree_four_share=float(sum(value == 4 for value in degrees) / node_count),
        degree_five_plus_share=float(sum(value >= 5 for value in degrees) / node_count),
        district_quadrant_presence_share=_district_quadrant_coverage(
            edges=edges,
            district_envelopes=district_envelopes,
        ),
        global_street_cell_presence_share=global_street_cell_presence_share,
        global_local_street_cell_presence_share=(
            global_local_street_cell_presence_share
        ),
        coverage_grid_resolution=GLOBAL_STREET_CELL_GRID_RESOLUTION,
        global_local_junction_proximity_share=(
            global_local_junction_proximity_share
        ),
        junction_grid_resolution=GLOBAL_LOCAL_JUNCTION_GRID_RESOLUTION,
        junction_proximity_radius_cells=GLOBAL_LOCAL_JUNCTION_RADIUS_CELLS,
        weak_component_count=weak_component_count,
        district_count=len(district_envelopes),
        physical_segment_count=len(edges),
    )


def evaluate_morphology_quality_gate(
    *,
    style_id: str,
    geometry_fingerprint: str,
    metrics: MorphologyQualityMetrics,
) -> MorphologyQualityGate:
    """Evaluate broad synthetic-fabric thresholds without empirical fitting."""

    style = str(style_id)
    thresholds = MORPHOLOGY_QUALITY_GATE_THRESHOLDS
    failures: list[str] = []
    if metrics.coverage_grid_resolution != GLOBAL_STREET_CELL_GRID_RESOLUTION:
        failures.append(
            f"coverage_grid_resolution must equal {GLOBAL_STREET_CELL_GRID_RESOLUTION}"
        )
    if metrics.junction_grid_resolution != GLOBAL_LOCAL_JUNCTION_GRID_RESOLUTION:
        failures.append(
            "junction_grid_resolution must equal "
            f"{GLOBAL_LOCAL_JUNCTION_GRID_RESOLUTION}"
        )
    if not math.isclose(
        metrics.junction_proximity_radius_cells,
        GLOBAL_LOCAL_JUNCTION_RADIUS_CELLS,
        abs_tol=1e-12,
    ):
        failures.append(
            "junction_proximity_radius_cells must equal "
            f"{GLOBAL_LOCAL_JUNCTION_RADIUS_CELLS:g}"
        )
    if metrics.weak_component_count != 1:
        failures.append("weak_component_count must equal 1")
    if (
        metrics.global_local_street_cell_presence_share
        < thresholds["minimum_global_local_street_cell_presence_share"]
    ):
        failures.append(
            "global_local_street_cell_presence_share must be >= "
            f"{thresholds['minimum_global_local_street_cell_presence_share']:g}"
        )
    if (
        metrics.global_local_junction_proximity_share
        < thresholds["minimum_global_local_junction_proximity_share"]
    ):
        failures.append(
            "global_local_junction_proximity_share must be >= "
            f"{thresholds['minimum_global_local_junction_proximity_share']:g}"
        )
    if (
        metrics.street_density_km_per_km2
        < thresholds["minimum_street_density_km_per_km2"]
    ):
        failures.append(
            "street_density_km_per_km2 must be >= "
            f"{thresholds['minimum_street_density_km_per_km2']:g}"
        )
    if metrics.block_continuity < thresholds["minimum_block_continuity"]:
        failures.append(
            "block_continuity must be >= "
            f"{thresholds['minimum_block_continuity']:g}"
        )
    maximum_dead_end_share = (
        thresholds["maximum_river_dead_end_share"]
        if style == "river_constrained"
        else thresholds["maximum_dead_end_share"]
    )
    if metrics.degree_one_share > maximum_dead_end_share:
        failures.append(f"degree_one_share must be <= {maximum_dead_end_share:g}")
    if (
        metrics.district_count
        and metrics.district_quadrant_presence_share
        < thresholds["minimum_district_quadrant_presence_share"]
    ):
        failures.append(
            "district_quadrant_presence_share must be >= "
            f"{thresholds['minimum_district_quadrant_presence_share']:g}"
        )
    if style in {"polycentric_tod", "superblock_mixed"} and (
        metrics.degree_four_share > thresholds["maximum_mixed_grid_four_way_share"]
    ):
        failures.append(
            "degree_four_share must be <= "
            f"{thresholds['maximum_mixed_grid_four_way_share']:g} for mixed-grid styles"
        )
    if (
        style == "river_constrained"
        and metrics.block_continuity
        < thresholds["minimum_river_block_continuity"]
    ):
        failures.append(
            "river_constrained block_continuity must be >= "
            f"{thresholds['minimum_river_block_continuity']:g}"
        )

    metric_payload = dict(metrics.as_dict())
    metrics_digest = hashlib.sha256(
        json.dumps(
            metric_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return MorphologyQualityGate(
        accepted=not failures,
        gate_version=MORPHOLOGY_QUALITY_GATE_VERSION,
        gate_scope=(
            "weak_connectivity_block_density_intersection_mix_"
            "global_local_cell_presence_junction_proximity"
        ),
        style_id=style,
        geometry_fingerprint=str(geometry_fingerprint),
        metrics_digest=metrics_digest,
        failures=tuple(failures),
    )


def _physical_edges(topology: _TopologyLike) -> tuple[_PhysicalEdge, ...]:
    geometry = topology.road_geometry
    if not isinstance(geometry, RoadGeometryCatalog):
        raise ValueError("road_geometry is required for morphology quality metrics")
    link_by_id = {int(link.link_id): link for link in topology.links}
    assignments_by_geometry: dict[int, list[Any]] = {}
    for assignment in geometry.assignments:
        assignments_by_geometry.setdefault(int(assignment.geometry_id), []).append(
            assignment
        )
    edges: list[_PhysicalEdge] = []
    for centerline in geometry.centerlines:
        assignments = assignments_by_geometry.get(int(centerline.geometry_id), [])
        if not assignments:
            continue
        canonical = min(assignments, key=lambda item: int(item.link_id))
        link = link_by_id.get(int(canonical.link_id))
        if link is None:
            raise ValueError(
                f"geometry assignment references missing link {int(canonical.link_id)}"
            )
        edges.append(
            _PhysicalEdge(
                edge_id=int(centerline.geometry_id),
                src_node_id=int(link.src_node_id),
                dst_node_id=int(link.dst_node_id),
                length_m=float(centerline.length_m),
                road_class=RoadClass(link.road_class),
                points_m=tuple(
                    (float(point[0]), float(point[1]))
                    for point in centerline.points_m
                ),
            )
        )
    return tuple(edges)


def _undirected_bridge_edge_ids(edges: tuple[_PhysicalEdge, ...]) -> set[int]:
    adjacency: dict[int, list[tuple[int, int]]] = {}
    for edge in edges:
        adjacency.setdefault(edge.src_node_id, []).append(
            (edge.dst_node_id, edge.edge_id)
        )
        adjacency.setdefault(edge.dst_node_id, []).append(
            (edge.src_node_id, edge.edge_id)
        )
    discovery: dict[int, int] = {}
    low: dict[int, int] = {}
    parent_node: dict[int, int | None] = {}
    parent_edge: dict[int, int | None] = {}
    bridges: set[int] = set()
    clock = 0

    for root_id in sorted(adjacency):
        if root_id in discovery:
            continue
        parent_node[root_id] = None
        parent_edge[root_id] = None
        discovery[root_id] = clock
        low[root_id] = clock
        clock += 1
        stack: list[tuple[int, int]] = [(root_id, 0)]
        while stack:
            node_id, next_index = stack[-1]
            neighbors = adjacency.get(node_id, ())
            if next_index < len(neighbors):
                neighbor_id, edge_id = neighbors[next_index]
                stack[-1] = (node_id, next_index + 1)
                if edge_id == parent_edge[node_id]:
                    continue
                if neighbor_id not in discovery:
                    parent_node[neighbor_id] = node_id
                    parent_edge[neighbor_id] = edge_id
                    discovery[neighbor_id] = clock
                    low[neighbor_id] = clock
                    clock += 1
                    stack.append((neighbor_id, 0))
                    continue
                low[node_id] = min(low[node_id], discovery[neighbor_id])
                continue

            stack.pop()
            parent_id = parent_node[node_id]
            if parent_id is None:
                continue
            low[parent_id] = min(low[parent_id], low[node_id])
            if low[node_id] > discovery[parent_id]:
                edge_id = parent_edge[node_id]
                if edge_id is not None:
                    bridges.add(edge_id)
    return bridges


def _weak_component_count(
    *,
    edges: tuple[_PhysicalEdge, ...],
    node_ids: tuple[int, ...],
) -> int:
    adjacency: dict[int, list[int]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        adjacency.setdefault(edge.src_node_id, []).append(edge.dst_node_id)
        adjacency.setdefault(edge.dst_node_id, []).append(edge.src_node_id)
    visited: set[int] = set()
    component_count = 0
    for root_id in sorted(adjacency):
        if root_id in visited:
            continue
        component_count += 1
        visited.add(root_id)
        stack = [root_id]
        while stack:
            node_id = stack.pop()
            for neighbor_id in adjacency[node_id]:
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)
                stack.append(neighbor_id)
    return component_count


def _global_street_cell_presence(
    *,
    edges: tuple[_PhysicalEdge, ...],
    hull: tuple[tuple[float, float], ...],
    resolution: int,
) -> float:
    min_x = min(point[0] for point in hull)
    max_x = max(point[0] for point in hull)
    min_y = min(point[1] for point in hull)
    max_y = max(point[1] for point in hull)
    cell_width = (max_x - min_x) / resolution
    cell_height = (max_y - min_y) / resolution
    eligible = {
        (x_index, y_index)
        for y_index in range(resolution)
        for x_index in range(resolution)
        if _point_in_polygon_or_boundary(
            (
                min_x + (x_index + 0.5) * cell_width,
                min_y + (y_index + 0.5) * cell_height,
            ),
            hull,
        )
    }
    if not eligible:
        return 0.0

    occupied: set[tuple[int, int]] = set()
    for edge in edges:
        for left, right in zip(edge.points_m, edge.points_m[1:]):
            x_span_cells = abs(right[0] - left[0]) / cell_width
            y_span_cells = abs(right[1] - left[1]) / cell_height
            sample_count = max(1, int(math.ceil(max(x_span_cells, y_span_cells) * 2.0)))
            for sample_index in range(sample_count + 1):
                share = sample_index / sample_count
                x = left[0] + (right[0] - left[0]) * share
                y = left[1] + (right[1] - left[1]) * share
                x_index = min(
                    resolution - 1,
                    max(0, int((x - min_x) / cell_width)),
                )
                y_index = min(
                    resolution - 1,
                    max(0, int((y - min_y) / cell_height)),
                )
                cell = (x_index, y_index)
                if cell in eligible:
                    occupied.add(cell)
    return float(len(occupied) / len(eligible))


def _global_local_junction_proximity(
    *,
    edges: tuple[_PhysicalEdge, ...],
    node_points: dict[int, tuple[float, float]],
    hull: tuple[tuple[float, float], ...],
    resolution: int,
    radius_cells: float,
) -> float:
    local_degree = {node_id: 0 for node_id in node_points}
    for edge in edges:
        if edge.road_class != RoadClass.LOCAL:
            continue
        local_degree[edge.src_node_id] = local_degree.get(edge.src_node_id, 0) + 1
        local_degree[edge.dst_node_id] = local_degree.get(edge.dst_node_id, 0) + 1
    junctions = tuple(
        node_points[node_id]
        for node_id, degree in local_degree.items()
        if degree >= 3
    )
    if not junctions:
        return 0.0

    min_x = min(point[0] for point in hull)
    max_x = max(point[0] for point in hull)
    min_y = min(point[1] for point in hull)
    max_y = max(point[1] for point in hull)
    cell_width = (max_x - min_x) / resolution
    cell_height = (max_y - min_y) / resolution
    radius_m = math.hypot(cell_width, cell_height) * radius_cells
    eligible_centers = tuple(
        center
        for y_index in range(resolution)
        for x_index in range(resolution)
        for center in (
            (
                min_x + (x_index + 0.5) * cell_width,
                min_y + (y_index + 0.5) * cell_height,
            ),
        )
        if _point_in_polygon_or_boundary(center, hull)
    )
    if not eligible_centers:
        return 0.0
    covered_count = sum(
        any(math.dist(center, junction) <= radius_m for junction in junctions)
        for center in eligible_centers
    )
    return float(covered_count / len(eligible_centers))


def _convex_hull(
    points: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    unique = sorted(set(points))
    if len(unique) < 3:
        return tuple(unique)

    def cross(
        origin: tuple[float, float],
        left: tuple[float, float],
        right: tuple[float, float],
    ) -> float:
        return (left[0] - origin[0]) * (right[1] - origin[1]) - (
            left[1] - origin[1]
        ) * (right[0] - origin[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return tuple(lower[:-1] + upper[:-1])


def _polygon_area(points: tuple[tuple[float, float], ...]) -> float:
    if len(points) < 3:
        return 0.0
    return abs(
        sum(
            left[0] * right[1] - right[0] * left[1]
            for left, right in zip(points, points[1:] + points[:1])
        )
    ) * 0.5


def _coerce_polygons(value: Any) -> tuple[tuple[tuple[float, float], ...], ...]:
    polygons: list[tuple[tuple[float, float], ...]] = []
    for raw_polygon in tuple(value or ()):
        polygon = tuple((float(point[0]), float(point[1])) for point in raw_polygon)
        if len(polygon) >= 3:
            polygons.append(polygon)
    return tuple(polygons)


def _district_quadrant_coverage(
    *,
    edges: tuple[_PhysicalEdge, ...],
    district_envelopes: tuple[tuple[tuple[float, float], ...], ...],
) -> float:
    if not district_envelopes:
        return 0.0
    sample_points = tuple(
        point
        for edge in edges
        for left, right in zip(edge.points_m, edge.points_m[1:])
        for point in (
            left,
            right,
            ((left[0] + right[0]) * 0.5, (left[1] + right[1]) * 0.5),
        )
    )
    coverage: list[float] = []
    for polygon in district_envelopes:
        xs = tuple(point[0] for point in polygon)
        ys = tuple(point[1] for point in polygon)
        center_x = (min(xs) + max(xs)) * 0.5
        center_y = (min(ys) + max(ys)) * 0.5
        occupied: set[tuple[int, int]] = set()
        for point in sample_points:
            if not _point_in_polygon_or_boundary(point, polygon):
                continue
            occupied.add((int(point[0] >= center_x), int(point[1] >= center_y)))
        coverage.append(len(occupied) / 4.0)
    return float(sum(coverage) / len(coverage))


def _point_in_polygon_or_boundary(
    point: tuple[float, float],
    polygon: tuple[tuple[float, float], ...],
) -> bool:
    x, y = point
    inside = False
    pairs = zip(polygon, polygon[1:] + polygon[:1])
    for left, right in pairs:
        cross = (right[0] - left[0]) * (y - left[1]) - (
            right[1] - left[1]
        ) * (x - left[0])
        if abs(cross) <= 1e-9 and min(left[0], right[0]) - 1e-9 <= x <= max(
            left[0], right[0]
        ) + 1e-9 and min(left[1], right[1]) - 1e-9 <= y <= max(
            left[1], right[1]
        ) + 1e-9:
            return True
        if (left[1] > y) != (right[1] > y):
            crossing_x = (right[0] - left[0]) * (y - left[1]) / (
                right[1] - left[1]
            ) + left[0]
            if x < crossing_x:
                inside = not inside
    return inside


def _median_or_zero(values: tuple[float, ...]) -> float:
    return float(statistics.median(values)) if values else 0.0
