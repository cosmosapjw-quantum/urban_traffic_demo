"""Terrain-aware deterministic hierarchical street skeleton."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

import numpy as np

from .graph import RoadClass
from .street_plan import PhysicalStreet, PhysicalStreetPlan
from .terrain_field import TerrainField
from .urban_form import UrbanFormField

__all__ = ["build_hierarchical_street_skeleton"]

Cell = tuple[int, int]


@dataclass(frozen=True, slots=True)
class _CandidateEdge:
    distance_m: float
    left: int
    right: int


def build_hierarchical_street_skeleton(
    *,
    terrain: TerrainField,
    urban_form: UrbanFormField,
) -> PhysicalStreetPlan:
    """Connect all centers and boundary gateways without repair-link fallback."""

    if urban_form.terrain_fingerprint != terrain.fingerprint:
        raise ValueError("urban form was not built from the provided terrain")
    center_points = tuple((center.x_m, center.y_m) for center in urban_form.centers)
    gateway_points = tuple(
        _nearest_allowed_point(terrain=terrain, target=point)
        for point in urban_form.gateways_m
    )
    anchor_points = center_points + gateway_points
    candidate_edges = tuple(
        sorted(
            (
                _CandidateEdge(math.dist(anchor_points[left], anchor_points[right]), left, right)
                for left in range(len(anchor_points))
                for right in range(left + 1, len(anchor_points))
            ),
            key=lambda item: (item.distance_m, item.left, item.right),
        )
    )
    tree_edges = _minimum_spanning_tree(
        anchor_count=len(anchor_points),
        candidates=candidate_edges,
    )
    tree_pairs = {(edge.left, edge.right) for edge in tree_edges}
    redundancy_target = max(1, len(anchor_points) // 3)
    redundancy_edges = tuple(
        edge
        for edge in candidate_edges
        if (edge.left, edge.right) not in tree_pairs
    )[:redundancy_target]
    route_edges = tuple(tree_edges) + redundancy_edges
    streets: list[PhysicalStreet] = []
    bridge_group_id = 1
    for route_index, edge in enumerate(route_edges):
        start = _point_to_cell(terrain, anchor_points[edge.left])
        goal = _point_to_cell(terrain, anchor_points[edge.right])
        cells = _astar_cells(
            terrain=terrain,
            urban_form=urban_form,
            start=start,
            goal=goal,
        )
        base_class = (
            RoadClass.EXPRESSWAY
            if edge.left >= len(center_points) or edge.right >= len(center_points)
            else RoadClass.ARTERIAL
        )
        runs = _split_water_runs(terrain=terrain, cells=cells)
        for is_bridge, run_cells in runs:
            road_class = RoadClass.BRIDGE if is_bridge else base_class
            lanes, speed, capacity = _design_values(road_class)
            points = _simplify_points(
                tuple(_cell_to_point(terrain, cell) for cell in run_cells)
            )
            streets.append(
                PhysicalStreet(
                    street_id=len(streets),
                    road_class=road_class,
                    points_m=points,
                    lanes=lanes,
                    free_flow_speed_mps=speed,
                    capacity_veh_per_second=capacity,
                    source_anchor_ids=(edge.left, edge.right),
                    bridge_group_id=bridge_group_id if is_bridge else None,
                    provenance=(
                        "hierarchical_redundancy_v1"
                        if route_index >= len(tree_edges)
                        else "hierarchical_tree_v1"
                    ),
                )
            )
            if is_bridge:
                bridge_group_id += 1
    return PhysicalStreetPlan(
        terrain_fingerprint=terrain.fingerprint,
        urban_form_fingerprint=urban_form.fingerprint,
        style_id=urban_form.style_id,
        anchor_points_m=anchor_points,
        center_anchor_count=len(center_points),
        streets=tuple(streets),
        tree_edge_count=len(tree_edges),
        redundancy_edge_count=len(redundancy_edges),
    )


def _minimum_spanning_tree(
    *,
    anchor_count: int,
    candidates: tuple[_CandidateEdge, ...],
) -> tuple[_CandidateEdge, ...]:
    parent = list(range(anchor_count))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    selected: list[_CandidateEdge] = []
    for edge in candidates:
        left_root = find(edge.left)
        right_root = find(edge.right)
        if left_root == right_root:
            continue
        parent[right_root] = left_root
        selected.append(edge)
        if len(selected) == anchor_count - 1:
            break
    if len(selected) != anchor_count - 1:
        raise ValueError("cannot connect urban anchors")
    return tuple(selected)


def _astar_cells(
    *,
    terrain: TerrainField,
    urban_form: UrbanFormField,
    start: Cell,
    goal: Cell,
) -> tuple[Cell, ...]:
    allowed = terrain.buildable_mask | terrain.water_mask
    if not bool(allowed[start]) or not bool(allowed[goal]):
        raise ValueError("street anchors must map to allowed terrain cells")
    queue: list[tuple[float, float, int, int]] = [(0.0, 0.0, start[0], start[1])]
    best = {start: 0.0}
    previous: dict[Cell, Cell] = {}
    while queue:
        _, cost, row, column = heapq.heappop(queue)
        cell = (row, column)
        if cost != best.get(cell):
            continue
        if cell == goal:
            return _reconstruct_path(previous=previous, goal=goal)
        for next_cell, step_distance in _neighbors(terrain.shape, cell):
            if not bool(allowed[next_cell]):
                continue
            next_cost = cost + step_distance * _cell_cost(
                terrain=terrain,
                urban_form=urban_form,
                cell=next_cell,
            )
            if next_cost >= best.get(next_cell, math.inf):
                continue
            best[next_cell] = next_cost
            previous[next_cell] = cell
            heuristic = math.hypot(goal[0] - next_cell[0], goal[1] - next_cell[1])
            heapq.heappush(
                queue,
                (next_cost + heuristic, next_cost, next_cell[0], next_cell[1]),
            )
    raise ValueError(f"no terrain-aware path between anchor cells {start} and {goal}")


def _cell_cost(
    *,
    terrain: TerrainField,
    urban_form: UrbanFormField,
    cell: Cell,
) -> float:
    water_penalty = 28.0 if bool(terrain.water_mask[cell]) else 0.0
    slope_penalty = float(terrain.slope_rise_per_m[cell]) * 20.0
    development_penalty = (1.0 - float(urban_form.development_intensity[cell])) * 0.35
    return 1.0 + water_penalty + slope_penalty + development_penalty


def _neighbors(shape: tuple[int, int], cell: Cell) -> tuple[tuple[Cell, float], ...]:
    out: list[tuple[Cell, float]] = []
    for row_delta, column_delta in (
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    ):
        row = cell[0] + row_delta
        column = cell[1] + column_delta
        if 0 <= row < shape[0] and 0 <= column < shape[1]:
            out.append(((row, column), math.sqrt(2.0) if row_delta and column_delta else 1.0))
    return tuple(out)


def _reconstruct_path(*, previous: dict[Cell, Cell], goal: Cell) -> tuple[Cell, ...]:
    path = [goal]
    while path[-1] in previous:
        path.append(previous[path[-1]])
    path.reverse()
    return tuple(path)


def _split_water_runs(
    *,
    terrain: TerrainField,
    cells: tuple[Cell, ...],
) -> tuple[tuple[bool, tuple[Cell, ...]], ...]:
    if len(cells) < 2:
        raise ValueError("street route must contain at least two cells")
    runs: list[tuple[bool, list[Cell]]] = []
    for left, right in zip(cells, cells[1:]):
        is_bridge = bool(terrain.water_mask[left] or terrain.water_mask[right])
        if not runs or runs[-1][0] != is_bridge:
            runs.append((is_bridge, [left, right]))
        elif runs[-1][1][-1] != right:
            runs[-1][1].append(right)
    return tuple((is_bridge, tuple(run)) for is_bridge, run in runs)


def _simplify_points(
    points: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    if len(points) <= 2:
        return points
    kept = [points[0]]
    previous_direction: tuple[int, int] | None = None
    for left, right in zip(points, points[1:]):
        direction = (
            int(math.copysign(1, right[0] - left[0])) if right[0] != left[0] else 0,
            int(math.copysign(1, right[1] - left[1])) if right[1] != left[1] else 0,
        )
        if previous_direction is not None and direction != previous_direction:
            kept.append(left)
        previous_direction = direction
    kept.append(points[-1])
    return tuple(kept)


def _nearest_allowed_point(
    *,
    terrain: TerrainField,
    target: tuple[float, float],
) -> tuple[float, float]:
    x_values = terrain.x_coordinates_m.astype(np.float64)
    y_values = terrain.y_coordinates_m.astype(np.float64)
    grid_x, grid_y = np.meshgrid(x_values, y_values)
    allowed = terrain.buildable_mask
    distance = (grid_x - float(target[0])) ** 2 + (grid_y - float(target[1])) ** 2
    distance = np.where(allowed, distance, np.inf)
    index = int(np.argmin(distance))
    if not math.isfinite(float(distance.flat[index])):
        raise ValueError("terrain contains no allowed gateway cell")
    row, column = np.unravel_index(index, terrain.shape)
    return float(grid_x[row, column]), float(grid_y[row, column])


def _point_to_cell(terrain: TerrainField, point: tuple[float, float]) -> Cell:
    column = int(
        np.argmin(np.abs(terrain.x_coordinates_m.astype(np.float64) - float(point[0])))
    )
    row = int(
        np.argmin(np.abs(terrain.y_coordinates_m.astype(np.float64) - float(point[1])))
    )
    return row, column


def _cell_to_point(terrain: TerrainField, cell: Cell) -> tuple[float, float]:
    return (
        float(terrain.x_coordinates_m[cell[1]]),
        float(terrain.y_coordinates_m[cell[0]]),
    )


def _design_values(road_class: RoadClass) -> tuple[int, float, float]:
    if road_class is RoadClass.EXPRESSWAY:
        return 3, 27.8, 1.8
    if road_class is RoadClass.BRIDGE:
        return 2, 19.4, 1.2
    return 2, 16.7, 1.1
