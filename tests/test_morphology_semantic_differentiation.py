"""Falsifiers for the structural claims made by the six morphology styles."""

from __future__ import annotations

from collections import defaultdict, deque
import math

import pytest

from metroflow.city.scale import CityScaleSpec
from metroflow.city.scalable_blocks import build_scalable_block_authority
from metroflow.city.scalable_topology import (
    FacilityKind,
    RoadHierarchy,
    build_scalable_street_network,
)


def _ordered_cycle_node_ids(roads: tuple) -> tuple[int, ...]:
    adjacency: dict[int, list[int]] = defaultdict(list)
    for road in roads:
        adjacency[road.start_node_id].append(road.end_node_id)
        adjacency[road.end_node_id].append(road.start_node_id)
    assert adjacency and all(len(neighbours) == 2 for neighbours in adjacency.values())

    start = min(adjacency)
    ordered = [start]
    previous: int | None = None
    current = start
    while True:
        candidates = sorted(node_id for node_id in adjacency[current] if node_id != previous)
        following = candidates[0]
        if following == start:
            break
        assert following not in ordered
        ordered.append(following)
        previous, current = current, following
    assert len(ordered) == len(roads)
    return tuple(ordered)


def _high_hierarchy_path_exists(network, start_id: int, end_id: int) -> bool:
    adjacency: dict[int, set[int]] = defaultdict(set)
    for road in network.roads:
        if road.facility is not FacilityKind.SURFACE or road.hierarchy not in {
            RoadHierarchy.ARTERIAL,
            RoadHierarchy.COLLECTOR,
        }:
            continue
        adjacency[road.start_node_id].add(road.end_node_id)
        adjacency[road.end_node_id].add(road.start_node_id)
    frontier = deque((start_id,))
    visited = {start_id}
    while frontier:
        current = frontier.popleft()
        if current == end_id:
            return True
        for neighbour in adjacency[current] - visited:
            visited.add(neighbour)
            frontier.append(neighbour)
    return False


def test_river_constrained_has_bridge_structures() -> None:
    """river_constrained must contain physical bridge roads and failure groups."""
    scale = CityScaleSpec(100_000, 25.0)
    net = build_scalable_street_network(scale, "river_constrained", seed=17)
    bridge_roads = [
        r for r in net.roads if r.facility == FacilityKind.BRIDGE or "bridge" in r.semantic_id
    ]
    assert len(bridge_roads) >= 3, "must have at least 3 river crossing bridges"


def test_ring_radial_has_concentric_ring_hierarchy() -> None:
    """At least two closed, center-winding, radius-stable orbitals must exist."""
    scale = CityScaleSpec(100_000, 25.0)
    network = build_scalable_street_network(scale, "ring_radial", seed=17)
    center_x, center_y = network.centers[0]
    nodes = {node.node_id: node for node in network.nodes}
    orbital_groups: dict[str, list] = defaultdict(list)
    for road in network.roads:
        if road.semantic_role.startswith("ring-orbital-"):
            orbital_groups[road.semantic_role].append(road)

    mean_radii: list[float] = []
    for roads in orbital_groups.values():
        ordered_ids = _ordered_cycle_node_ids(tuple(roads))
        vectors = tuple(
            (nodes[node_id].x_mm - center_x, nodes[node_id].y_mm - center_y)
            for node_id in ordered_ids
        )
        radii = tuple(math.hypot(x_value, y_value) for x_value, y_value in vectors)
        mean_radius = sum(radii) / len(radii)
        radial_cv = math.sqrt(
            sum((radius - mean_radius) ** 2 for radius in radii) / len(radii)
        ) / mean_radius
        winding_radians = sum(
            math.atan2(left[0] * right[1] - left[1] * right[0], left[0] * right[0] + left[1] * right[1])
            for left, right in zip(vectors, vectors[1:] + vectors[:1])
        )
        assert radial_cv < 0.01
        assert abs(winding_radians / math.tau) == pytest.approx(1.0, abs=1e-9)
        mean_radii.append(mean_radius)

    assert len(mean_radii) >= 2
    assert len({round(radius) for radius in mean_radii}) == len(mean_radii)


def test_polycentric_centers_distributed_in_2d() -> None:
    """Centers must be non-collinear, own catchments, and share a backbone."""
    scale = CityScaleSpec(100_000, 25.0)
    network = build_scalable_street_network(scale, "polycentric_tod", seed=17)
    assert len(network.centers) >= 3
    first, second, third = network.centers[:3]
    twice_area = (second[0] - first[0]) * (third[1] - first[1]) - (
        second[1] - first[1]
    ) * (third[0] - first[0])
    assert twice_area != 0

    catchment_counts = [0] * len(network.centers)
    center_points = set(network.centers)
    for node in network.nodes:
        if node.layer != 0 or (node.x_mm, node.y_mm) in center_points:
            continue
        owner = min(
            range(len(network.centers)),
            key=lambda index: (
                (node.x_mm - network.centers[index][0]) ** 2
                + (node.y_mm - network.centers[index][1]) ** 2,
                index,
            ),
        )
        catchment_counts[owner] += 1
    assert all(count > 0 for count in catchment_counts)

    node_by_point = {
        (node.x_mm, node.y_mm): node.node_id for node in network.nodes if node.layer == 0
    }
    center_node_ids = tuple(node_by_point[center] for center in network.centers)
    assert all(
        _high_hierarchy_path_exists(network, left, right)
        for offset, left in enumerate(center_node_ids)
        for right in center_node_ids[offset + 1 :]
    )


def test_superblock_has_multiple_two_dimensional_high_hierarchy_macrofaces() -> None:
    """Multiple bounded macrofaces must be large along both spatial axes."""
    scale = CityScaleSpec(100_000, 25.0)
    network = build_scalable_street_network(scale, "superblock_mixed", seed=17)
    authority = build_scalable_block_authority(network)
    road_by_id = {road.road_id: road for road in network.roads}

    macroblocks = []
    for block in authority.blocks:
        x_values = [point[0] for point in block.outer_polygon_mm]
        y_values = [point[1] for point in block.outer_polygon_mm]
        width_mm = max(x_values) - min(x_values)
        height_mm = max(y_values) - min(y_values)
        aspect_ratio = max(width_mm, height_mm) / min(width_mm, height_mm)
        if min(width_mm, height_mm) >= 700_000 and aspect_ratio <= 2.5:
            macroblocks.append(block)

    assert len(macroblocks) >= 4
    assert all(
        block.frontage_road_ids
        and all(
            road_by_id[road_id].hierarchy
            in {RoadHierarchy.ARTERIAL, RoadHierarchy.COLLECTOR}
            for road_id in block.frontage_road_ids
        )
        for block in macroblocks
    )


@pytest.mark.parametrize("seed", (17, 29))
def test_superblock_gateway_access_closes_against_an_existing_surface_carrier(
    seed: int,
) -> None:
    """A nominal access triangle cannot be a dangling two-edge spur."""
    scale = CityScaleSpec(100_000, 40.0)
    network = build_scalable_street_network(scale, "superblock_mixed", seed=seed)
    nodes = {node.node_id: node for node in network.nodes}
    anchors_by_access: dict[int, list[int]] = defaultdict(list)
    for road in network.roads:
        if road.semantic_role not in {
            "surface-access-primary",
            "surface-access-secondary",
        }:
            continue
        access_id, anchor_id = (
            (road.start_node_id, road.end_node_id)
            if nodes[road.start_node_id].semantic_role.startswith("ramp-access-")
            else (road.end_node_id, road.start_node_id)
        )
        anchors_by_access[access_id].append(anchor_id)

    carrier_pairs = {
        frozenset((road.start_node_id, road.end_node_id))
        for road in network.roads
        if road.facility is FacilityKind.SURFACE
        and not road.semantic_role.startswith("surface-access-")
    }
    assert len(anchors_by_access) == 8
    assert all(
        len(anchor_ids) == 2 and frozenset(anchor_ids) in carrier_pairs
        for anchor_ids in anchors_by_access.values()
    )


def test_organic_compatibility_style_has_curvilinear_geometry() -> None:
    """The compatibility ID must at least produce deterministic bent carriers."""
    scale = CityScaleSpec(100_000, 25.0)
    network = build_scalable_street_network(scale, "organic", seed=17)
    connectors = [
        road for road in network.roads if road.semantic_role == "organic-connector"
    ]
    bent = [
        road
        for road in connectors
        if any(
            (road.points_mm[-1][0] - road.points_mm[0][0])
            * (point[1] - road.points_mm[0][1])
            != (road.points_mm[-1][1] - road.points_mm[0][1])
            * (point[0] - road.points_mm[0][0])
            for point in road.points_mm[1:-1]
        )
    ]
    assert len(bent) / len(connectors) > 0.9
