"""Typed physical street plans before topology compilation."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field

from .graph import RoadClass

__all__ = ["PhysicalStreet", "PhysicalStreetPlan"]


@dataclass(frozen=True, slots=True)
class PhysicalStreet:
    street_id: int
    road_class: RoadClass | str
    points_m: tuple[tuple[float, float], ...]
    lanes: int
    free_flow_speed_mps: float
    capacity_veh_per_second: float
    source_anchor_ids: tuple[int, int] | None
    bridge_group_id: int | None = None
    provenance: str = "hierarchical_skeleton_v1"

    def __post_init__(self) -> None:
        street_id = int(self.street_id)
        road_class = RoadClass(self.road_class)
        points = tuple((float(x), float(y)) for x, y in self.points_m)
        lanes = int(self.lanes)
        speed = float(self.free_flow_speed_mps)
        capacity = float(self.capacity_veh_per_second)
        anchors = (
            None
            if self.source_anchor_ids is None
            else tuple(int(value) for value in self.source_anchor_ids)
        )
        bridge_group_id = (
            None if self.bridge_group_id is None else int(self.bridge_group_id)
        )
        if street_id < 0:
            raise ValueError("street_id must be >= 0")
        if len(points) < 2 or any(
            not math.isfinite(value) for point in points for value in point
        ):
            raise ValueError("physical street requires at least two finite points")
        if any(left == right for left, right in zip(points, points[1:])):
            raise ValueError("physical street cannot contain repeated adjacent points")
        if lanes < 1 or not math.isfinite(speed) or speed <= 0.0:
            raise ValueError("street lanes and speed must be positive")
        if not math.isfinite(capacity) or capacity <= 0.0:
            raise ValueError("street capacity_veh_per_second must be positive")
        if anchors is not None and (len(anchors) != 2 or anchors[0] == anchors[1]):
            raise ValueError("source_anchor_ids must contain two distinct IDs")
        if road_class is RoadClass.BRIDGE and bridge_group_id is None:
            raise ValueError("bridge streets require bridge_group_id")
        if road_class is not RoadClass.BRIDGE and bridge_group_id is not None:
            raise ValueError("only bridge streets may have bridge_group_id")
        object.__setattr__(self, "street_id", street_id)
        object.__setattr__(self, "road_class", road_class)
        object.__setattr__(self, "points_m", points)
        object.__setattr__(self, "lanes", lanes)
        object.__setattr__(self, "free_flow_speed_mps", speed)
        object.__setattr__(self, "capacity_veh_per_second", capacity)
        object.__setattr__(self, "source_anchor_ids", anchors)
        object.__setattr__(self, "bridge_group_id", bridge_group_id)
        object.__setattr__(self, "provenance", str(self.provenance))

    @property
    def length_m(self) -> float:
        return float(
            sum(
                math.dist(left, right)
                for left, right in zip(self.points_m, self.points_m[1:])
            )
        )


@dataclass(frozen=True, slots=True)
class PhysicalStreetPlan:
    terrain_fingerprint: str
    urban_form_fingerprint: str
    style_id: str
    anchor_points_m: tuple[tuple[float, float], ...]
    center_anchor_count: int
    streets: tuple[PhysicalStreet, ...]
    tree_edge_count: int
    redundancy_edge_count: int
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        anchors = tuple((float(x), float(y)) for x, y in self.anchor_points_m)
        streets = tuple(sorted(self.streets, key=lambda item: item.street_id))
        if len(anchors) < 2 or any(
            not math.isfinite(value) for point in anchors for value in point
        ):
            raise ValueError("street plan requires finite anchors")
        if not 1 <= int(self.center_anchor_count) <= len(anchors):
            raise ValueError("center_anchor_count is outside anchor range")
        if not streets:
            raise ValueError("street plan must contain streets")
        if len({street.street_id for street in streets}) != len(streets):
            raise ValueError("physical street IDs must be unique")
        if int(self.tree_edge_count) != len(anchors) - 1:
            raise ValueError("tree_edge_count must equal anchor_count - 1")
        if int(self.redundancy_edge_count) < 0:
            raise ValueError("redundancy_edge_count must be >= 0")
        if any(street.source_anchor_ids is None for street in streets):
            raise ValueError("skeleton streets require source_anchor_ids")
        logical_pairs = {
            tuple(sorted(street.source_anchor_ids))
            for street in streets
            if street.source_anchor_ids is not None
        }
        if any(
            anchor_id < 0 or anchor_id >= len(anchors)
            for street in streets
            for anchor_id in (street.source_anchor_ids or ())
        ):
            raise ValueError("street source anchor is outside anchor range")
        if len(logical_pairs) != int(self.tree_edge_count) + int(
            self.redundancy_edge_count
        ):
            raise ValueError("logical street edge count does not match plan counts")
        adjacency = {index: set() for index in range(len(anchors))}
        for left, right in logical_pairs:
            adjacency[left].add(right)
            adjacency[right].add(left)
        reached = {0}
        frontier = [0]
        while frontier:
            current = frontier.pop()
            for neighbor in adjacency[current] - reached:
                reached.add(neighbor)
                frontier.append(neighbor)
        if len(reached) != len(anchors):
            raise ValueError("physical street plan anchors must be connected")
        bridge_group_ids = tuple(
            street.bridge_group_id
            for street in streets
            if street.bridge_group_id is not None
        )
        if len(set(bridge_group_ids)) != len(bridge_group_ids):
            raise ValueError("bridge_group_id values must be unique")
        object.__setattr__(self, "terrain_fingerprint", str(self.terrain_fingerprint))
        object.__setattr__(self, "urban_form_fingerprint", str(self.urban_form_fingerprint))
        object.__setattr__(self, "style_id", str(self.style_id))
        object.__setattr__(self, "anchor_points_m", anchors)
        object.__setattr__(self, "center_anchor_count", int(self.center_anchor_count))
        object.__setattr__(self, "streets", streets)
        object.__setattr__(self, "tree_edge_count", int(self.tree_edge_count))
        object.__setattr__(self, "redundancy_edge_count", int(self.redundancy_edge_count))
        object.__setattr__(self, "fingerprint", _street_plan_fingerprint(self))


def _street_plan_fingerprint(plan: PhysicalStreetPlan) -> str:
    payload = {
        "schema": "physical_street_plan_v1",
        "terrain": plan.terrain_fingerprint,
        "urban_form": plan.urban_form_fingerprint,
        "style_id": plan.style_id,
        "anchors": plan.anchor_points_m,
        "center_anchor_count": plan.center_anchor_count,
        "tree_edge_count": plan.tree_edge_count,
        "redundancy_edge_count": plan.redundancy_edge_count,
        "streets": [
            {
                "street_id": street.street_id,
                "road_class": street.road_class.value,
                "points_m": street.points_m,
                "lanes": street.lanes,
                "free_flow_speed_mps": street.free_flow_speed_mps,
                "capacity_veh_per_second": street.capacity_veh_per_second,
                "source_anchor_ids": street.source_anchor_ids,
                "bridge_group_id": street.bridge_group_id,
                "provenance": street.provenance,
            }
            for street in plan.streets
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
