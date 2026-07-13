"""Orientation-field local fabric tied to the hierarchical street plan."""

from __future__ import annotations

import hashlib
import heapq
import json
import math
from dataclasses import dataclass, field

import numpy as np

from .graph import RoadClass
from .street_plan import PhysicalStreet, PhysicalStreetPlan
from .terrain_field import TerrainField
from .urban_form import UrbanFormField

__all__ = ["RealisticStreetNetwork", "build_continuous_local_fabric"]

Cell = tuple[int, int]


@dataclass(frozen=True, slots=True)
class RealisticStreetNetwork:
    skeleton_fingerprint: str
    terrain_fingerprint: str
    urban_form_fingerprint: str
    style_id: str
    streets: tuple[PhysicalStreet, ...]
    skeleton_street_count: int
    local_street_count: int
    collector_street_count: int
    local_component_direct_attachment_count: int
    local_component_count_before_connectors: int
    max_developed_access_distance_m: float
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        streets = tuple(sorted(self.streets, key=lambda item: item.street_id))
        if not streets or len({street.street_id for street in streets}) != len(streets):
            raise ValueError("realistic street network requires unique streets")
        if tuple(street.street_id for street in streets) != tuple(range(len(streets))):
            raise ValueError("realistic street IDs must be dense and zero-based")
        expected = (
            int(self.skeleton_street_count)
            + int(self.local_street_count)
            + int(self.collector_street_count)
        )
        if expected != len(streets):
            raise ValueError("street class counts do not cover network streets")
        skeleton_end = int(self.skeleton_street_count)
        local_end = skeleton_end + int(self.local_street_count)
        if any(
            street.source_anchor_ids is None for street in streets[:skeleton_end]
        ):
            raise ValueError("skeleton street range requires anchor provenance")
        if any(
            street.road_class is not RoadClass.LOCAL
            or street.source_anchor_ids is not None
            for street in streets[skeleton_end:local_end]
        ):
            raise ValueError("local street range has invalid class or provenance")
        if any(
            street.road_class is not RoadClass.COLLECTOR
            or street.source_anchor_ids is not None
            for street in streets[local_end:]
        ):
            raise ValueError("collector street range has invalid class or provenance")
        access_distance = float(self.max_developed_access_distance_m)
        if not math.isfinite(access_distance) or access_distance < 0.0:
            raise ValueError("max developed access distance must be finite and >= 0")
        if access_distance > 400.0:
            raise ValueError("max developed access distance exceeds 400 meters")
        if int(self.local_component_count_before_connectors) < 1:
            raise ValueError("local fabric must contain at least one component")
        if int(self.local_component_direct_attachment_count) < 0 or (
            int(self.collector_street_count)
            + int(self.local_component_direct_attachment_count)
            != int(self.local_component_count_before_connectors)
        ):
            raise ValueError(
                "each local component requires one collector or direct attachment"
            )
        object.__setattr__(self, "skeleton_fingerprint", str(self.skeleton_fingerprint))
        object.__setattr__(self, "terrain_fingerprint", str(self.terrain_fingerprint))
        object.__setattr__(self, "urban_form_fingerprint", str(self.urban_form_fingerprint))
        object.__setattr__(self, "style_id", str(self.style_id))
        object.__setattr__(self, "streets", streets)
        object.__setattr__(self, "skeleton_street_count", int(self.skeleton_street_count))
        object.__setattr__(self, "local_street_count", int(self.local_street_count))
        object.__setattr__(self, "collector_street_count", int(self.collector_street_count))
        object.__setattr__(
            self,
            "local_component_direct_attachment_count",
            int(self.local_component_direct_attachment_count),
        )
        object.__setattr__(
            self,
            "local_component_count_before_connectors",
            int(self.local_component_count_before_connectors),
        )
        object.__setattr__(self, "max_developed_access_distance_m", access_distance)
        object.__setattr__(self, "fingerprint", _network_fingerprint(self))


def build_continuous_local_fabric(
    *,
    terrain: TerrainField,
    urban_form: UrbanFormField,
    skeleton: PhysicalStreetPlan,
    block_spacing_m: float = 150.0,
) -> RealisticStreetNetwork:
    """Grow connected local fabric and reject inaccessible developed cells."""

    spacing = float(block_spacing_m)
    if not math.isfinite(spacing) or not 80.0 <= spacing <= 220.0:
        raise ValueError("block_spacing_m must be in [80, 220]")
    if urban_form.terrain_fingerprint != terrain.fingerprint:
        raise ValueError("urban form was not built from the provided terrain")
    if skeleton.terrain_fingerprint != terrain.fingerprint:
        raise ValueError("street skeleton was not built from the provided terrain")
    if skeleton.urban_form_fingerprint != urban_form.fingerprint:
        raise ValueError("street skeleton was not built from the provided urban form")
    row_step = max(2, int(round(spacing / terrain.cell_size_y_m)))
    column_step = max(2, int(round(spacing / terrain.cell_size_x_m)))
    node_cells = tuple(
        (row, column)
        for row in range(row_step // 2, terrain.shape[0], row_step)
        for column in range(column_step // 2, terrain.shape[1], column_step)
        if bool(terrain.buildable_mask[row, column])
        and float(urban_form.development_intensity[row, column]) >= 0.08
    )
    if len(node_cells) < 4:
        raise ValueError("development field contains too few local fabric nodes")
    node_set = set(node_cells)
    local_edges: set[tuple[Cell, Cell]] = set()
    offsets = (
        (0, column_step),
        (row_step, 0),
        (row_step, column_step),
        (row_step, -column_step),
    )
    for cell in node_cells:
        for row_delta, column_delta in offsets:
            neighbor = (cell[0] + row_delta, cell[1] + column_delta)
            if neighbor not in node_set:
                continue
            if _orientation_alignment(
                urban_form=urban_form,
                left=cell,
                right=neighbor,
                terrain=terrain,
            ) < 0.76:
                continue
            line_cells = _line_cells(cell, neighbor)
            if not all(bool(terrain.buildable_mask[item]) for item in line_cells):
                continue
            if np.mean(
                [float(urban_form.development_intensity[item]) for item in line_cells]
            ) < 0.055:
                continue
            local_edges.add(tuple(sorted((cell, neighbor))))
    components = _components(node_cells=node_cells, edges=tuple(local_edges))
    if not local_edges or not components:
        raise ValueError("orientation field produced no local street fabric")
    skeleton_points = tuple(
        point
        for street in skeleton.streets
        if street.road_class is not RoadClass.BRIDGE
        for point in street.points_m
    )
    if not skeleton_points:
        raise ValueError("street skeleton contains no buildable connector target")
    streets: list[PhysicalStreet] = [
        _reindexed_street(street, street_id=index)
        for index, street in enumerate(skeleton.streets)
    ]
    for left, right in sorted(local_edges):
        streets.append(
            PhysicalStreet(
                street_id=len(streets),
                road_class=RoadClass.LOCAL,
                points_m=(_cell_to_point(terrain, left), _cell_to_point(terrain, right)),
                lanes=1,
                free_flow_speed_mps=8.3,
                capacity_veh_per_second=0.45,
                source_anchor_ids=None,
                provenance="orientation_local_fabric_v1",
            )
        )
    collector_count = 0
    direct_attachment_count = 0
    for component in components:
        local_cell, skeleton_point = _nearest_buildable_connector(
            terrain=terrain,
            component=component,
            skeleton_points=skeleton_points,
        )
        local_point = _cell_to_point(terrain, local_cell)
        if local_point == skeleton_point:
            direct_attachment_count += 1
            continue
        streets.append(
            PhysicalStreet(
                street_id=len(streets),
                road_class=RoadClass.COLLECTOR,
                points_m=(local_point, skeleton_point),
                lanes=1,
                free_flow_speed_mps=11.1,
                capacity_veh_per_second=0.70,
                source_anchor_ids=None,
                provenance="local_component_connector_v1",
            )
        )
        collector_count += 1
    access_distance = _max_developed_access_distance(
        terrain=terrain,
        urban_form=urban_form,
        streets=tuple(streets[len(skeleton.streets) :]),
    )
    return RealisticStreetNetwork(
        skeleton_fingerprint=skeleton.fingerprint,
        terrain_fingerprint=terrain.fingerprint,
        urban_form_fingerprint=urban_form.fingerprint,
        style_id=urban_form.style_id,
        streets=tuple(streets),
        skeleton_street_count=len(skeleton.streets),
        local_street_count=len(local_edges),
        collector_street_count=collector_count,
        local_component_direct_attachment_count=direct_attachment_count,
        local_component_count_before_connectors=len(components),
        max_developed_access_distance_m=access_distance,
    )


def _orientation_alignment(
    *,
    urban_form: UrbanFormField,
    left: Cell,
    right: Cell,
    terrain: TerrainField,
) -> float:
    midpoint = ((left[0] + right[0]) // 2, (left[1] + right[1]) // 2)
    dx = (right[1] - left[1]) * terrain.cell_size_x_m
    dy = (right[0] - left[0]) * terrain.cell_size_y_m
    length = max(math.hypot(dx, dy), 1e-12)
    direction_x = dx / length
    direction_y = dy / length
    orientation_x = float(urban_form.orientation_x[midpoint])
    orientation_y = float(urban_form.orientation_y[midpoint])
    parallel = abs(direction_x * orientation_x + direction_y * orientation_y)
    perpendicular = abs(-direction_x * orientation_y + direction_y * orientation_x)
    return max(parallel, perpendicular)


def _components(
    *,
    node_cells: tuple[Cell, ...],
    edges: tuple[tuple[Cell, Cell], ...],
) -> tuple[tuple[Cell, ...], ...]:
    adjacency = {cell: set() for cell in node_cells}
    for left, right in edges:
        adjacency[left].add(right)
        adjacency[right].add(left)
    unseen = {cell for cell, neighbors in adjacency.items() if neighbors}
    components: list[tuple[Cell, ...]] = []
    while unseen:
        start = min(unseen)
        reached = {start}
        frontier = [start]
        while frontier:
            current = frontier.pop()
            for neighbor in adjacency[current] - reached:
                reached.add(neighbor)
                frontier.append(neighbor)
        unseen -= reached
        components.append(tuple(sorted(reached)))
    return tuple(components)


def _nearest_buildable_connector(
    *,
    terrain: TerrainField,
    component: tuple[Cell, ...],
    skeleton_points: tuple[tuple[float, float], ...],
) -> tuple[Cell, tuple[float, float]]:
    candidates = sorted(
        (
            (math.dist(_cell_to_point(terrain, cell), point), cell, point)
            for cell in component
            for point in skeleton_points
        ),
        key=lambda item: (item[0], item[1], item[2]),
    )
    for _, cell, point in candidates:
        point_cell = _point_to_cell(terrain, point)
        if all(
            bool(terrain.buildable_mask[item])
            for item in _line_cells(cell, point_cell)
        ):
            return cell, _cell_to_point(terrain, point_cell)
    raise ValueError("local component cannot reach the hierarchical skeleton")


def _max_developed_access_distance(
    *,
    terrain: TerrainField,
    urban_form: UrbanFormField,
    streets: tuple[PhysicalStreet, ...],
) -> float:
    source_cells = {
        cell
        for street in streets
        for left, right in zip(street.points_m, street.points_m[1:])
        for cell in _line_cells(
            _point_to_cell(terrain, left),
            _point_to_cell(terrain, right),
        )
    }
    if not source_cells:
        raise ValueError("local street network contains no rasterized cells")
    distances = np.full(terrain.shape, np.inf, dtype=np.float64)
    queue: list[tuple[float, int, int]] = []
    for row, column in sorted(source_cells):
        distances[row, column] = 0.0
        heapq.heappush(queue, (0.0, row, column))
    while queue:
        distance, row, column = heapq.heappop(queue)
        if distance != float(distances[row, column]):
            continue
        for next_cell, step_distance in _distance_neighbors(
            terrain=terrain,
            cell=(row, column),
        ):
            if not bool(terrain.buildable_mask[next_cell]):
                continue
            next_distance = distance + step_distance
            if next_distance >= float(distances[next_cell]):
                continue
            distances[next_cell] = next_distance
            heapq.heappush(
                queue,
                (next_distance, next_cell[0], next_cell[1]),
            )
    developed = terrain.buildable_mask & (urban_form.development_intensity >= 0.08)
    if not bool(np.any(developed)):
        raise ValueError("urban form contains no developed cells")
    maximum = float(np.max(distances[developed]))
    if not math.isfinite(maximum):
        raise ValueError("developed cells are disconnected from local streets")
    return maximum


def _distance_neighbors(
    *,
    terrain: TerrainField,
    cell: Cell,
) -> tuple[tuple[Cell, float], ...]:
    out: list[tuple[Cell, float]] = []
    for row_delta, column_delta in ((-1, 0), (0, -1), (0, 1), (1, 0)):
        row = cell[0] + row_delta
        column = cell[1] + column_delta
        if 0 <= row < terrain.shape[0] and 0 <= column < terrain.shape[1]:
            distance = (
                terrain.cell_size_y_m if row_delta else terrain.cell_size_x_m
            )
            out.append(((row, column), distance))
    return tuple(out)


def _line_cells(left: Cell, right: Cell) -> tuple[Cell, ...]:
    count = max(abs(right[0] - left[0]), abs(right[1] - left[1])) + 1
    rows = np.rint(np.linspace(left[0], right[0], count)).astype(np.int32)
    columns = np.rint(np.linspace(left[1], right[1], count)).astype(np.int32)
    return tuple(dict.fromkeys(zip(rows.tolist(), columns.tolist())))


def _cell_to_point(terrain: TerrainField, cell: Cell) -> tuple[float, float]:
    return (
        float(terrain.x_coordinates_m[cell[1]]),
        float(terrain.y_coordinates_m[cell[0]]),
    )


def _point_to_cell(terrain: TerrainField, point: tuple[float, float]) -> Cell:
    column = int(np.argmin(np.abs(terrain.x_coordinates_m - float(point[0]))))
    row = int(np.argmin(np.abs(terrain.y_coordinates_m - float(point[1]))))
    return row, column


def _reindexed_street(street: PhysicalStreet, *, street_id: int) -> PhysicalStreet:
    return PhysicalStreet(
        street_id=street_id,
        road_class=street.road_class,
        points_m=street.points_m,
        lanes=street.lanes,
        free_flow_speed_mps=street.free_flow_speed_mps,
        capacity_veh_per_second=street.capacity_veh_per_second,
        source_anchor_ids=street.source_anchor_ids,
        bridge_group_id=street.bridge_group_id,
        provenance=street.provenance,
    )


def _network_fingerprint(network: RealisticStreetNetwork) -> str:
    payload = {
        "schema": "realistic_street_network_v1",
        "skeleton": network.skeleton_fingerprint,
        "terrain": network.terrain_fingerprint,
        "urban_form": network.urban_form_fingerprint,
        "style_id": network.style_id,
        "counts": (
            network.skeleton_street_count,
            network.local_street_count,
            network.collector_street_count,
            network.local_component_direct_attachment_count,
            network.local_component_count_before_connectors,
        ),
        "max_developed_access_distance_m": network.max_developed_access_distance_m,
        "streets": [
            (
                street.street_id,
                street.road_class.value,
                street.points_m,
                street.lanes,
                street.free_flow_speed_mps,
                street.capacity_veh_per_second,
                street.source_anchor_ids,
                street.bridge_group_id,
                street.provenance,
            )
            for street in network.streets
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
