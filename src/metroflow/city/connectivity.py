"""Weak-connectivity analysis and deterministic repair for generated cities."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from typing import Any, Sequence

from metroflow.city.graph import Node, RoadClass, RoadLink

__all__ = [
    "WeakConnectivityReport",
    "WeakConnectivityRepairResult",
    "analyze_weak_connectivity",
    "repair_weak_connectivity",
]


@dataclass(frozen=True, slots=True)
class WeakConnectivityReport:
    """Weak component summary for a road graph."""

    component_node_ids: tuple[tuple[int, ...], ...]
    node_component_id_by_node_id: dict[int, int]

    @property
    def component_count(self) -> int:
        return len(self.component_node_ids)

    @property
    def component_sizes(self) -> tuple[int, ...]:
        return tuple(len(component) for component in self.component_node_ids)


@dataclass(frozen=True, slots=True)
class WeakConnectivityRepairResult:
    """Road graph plus deterministic stitch links added to make it connected."""

    nodes: tuple[Node, ...]
    links: tuple[RoadLink, ...]
    repair_link_ids: tuple[int, ...]
    before: WeakConnectivityReport
    after: WeakConnectivityReport
    metadata: dict[str, Any]


def analyze_weak_connectivity(
    *,
    nodes: Sequence[Node],
    links: Sequence[RoadLink],
) -> WeakConnectivityReport:
    """Return weak components sorted by size descending, then min node id."""

    node_ids = tuple(int(node.node_id) for node in tuple(nodes))
    adjacency = {node_id: set() for node_id in node_ids}
    for link in tuple(links):
        src = int(link.src_node_id)
        dst = int(link.dst_node_id)
        if src not in adjacency or dst not in adjacency:
            continue
        adjacency[src].add(dst)
        adjacency[dst].add(src)

    visited: set[int] = set()
    components: list[tuple[int, ...]] = []
    for node_id in sorted(adjacency):
        if node_id in visited:
            continue
        queue: deque[int] = deque([node_id])
        visited.add(node_id)
        component: list[int] = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in sorted(adjacency[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        components.append(tuple(sorted(component)))

    components.sort(key=lambda item: (-len(item), item[0] if item else -1))
    component_by_node_id: dict[int, int] = {}
    for component_id, component in enumerate(components):
        for node_id in component:
            component_by_node_id[int(node_id)] = int(component_id)
    return WeakConnectivityReport(
        component_node_ids=tuple(components),
        node_component_id_by_node_id=component_by_node_id,
    )


def repair_weak_connectivity(
    *,
    nodes: Sequence[Node],
    links: Sequence[RoadLink],
    road_class: RoadClass = RoadClass.COLLECTOR,
    lanes: int = 1,
    speed_mps: float = 11.0,
    capacity_veh_per_tick: float = 8.0,
) -> WeakConnectivityRepairResult:
    """Connect every non-main weak component to the main component."""

    nodes_t = tuple(nodes)
    links_t = tuple(links)
    before = analyze_weak_connectivity(nodes=nodes_t, links=links_t)
    if before.component_count <= 1:
        metadata = _repair_metadata(before=before, after=before, repair_link_ids=())
        return WeakConnectivityRepairResult(
            nodes=nodes_t,
            links=links_t,
            repair_link_ids=(),
            before=before,
            after=before,
            metadata=metadata,
        )

    nodes_by_id = {int(node.node_id): node for node in nodes_t}
    main_component = before.component_node_ids[0]
    next_link_id = max((int(link.link_id) for link in links_t), default=-1) + 1
    repaired_links = list(links_t)
    repair_link_ids: list[int] = []

    for component in before.component_node_ids[1:]:
        small_node_id, main_node_id = _nearest_component_pair(
            nodes_by_id=nodes_by_id,
            small_component=component,
            main_component=main_component,
        )
        forward = _stitch_link(
            link_id=next_link_id,
            src_node=nodes_by_id[small_node_id],
            dst_node=nodes_by_id[main_node_id],
            road_class=road_class,
            lanes=lanes,
            speed_mps=speed_mps,
            capacity_veh_per_tick=capacity_veh_per_tick,
        )
        reverse = _stitch_link(
            link_id=next_link_id + 1,
            src_node=nodes_by_id[main_node_id],
            dst_node=nodes_by_id[small_node_id],
            road_class=road_class,
            lanes=lanes,
            speed_mps=speed_mps,
            capacity_veh_per_tick=capacity_veh_per_tick,
        )
        repaired_links.extend((forward, reverse))
        repair_link_ids.extend((forward.link_id, reverse.link_id))
        next_link_id += 2

    links_repaired = tuple(repaired_links)
    after = analyze_weak_connectivity(nodes=nodes_t, links=links_repaired)
    return WeakConnectivityRepairResult(
        nodes=nodes_t,
        links=links_repaired,
        repair_link_ids=tuple(repair_link_ids),
        before=before,
        after=after,
        metadata=_repair_metadata(
            before=before,
            after=after,
            repair_link_ids=tuple(repair_link_ids),
        ),
    )


def _nearest_component_pair(
    *,
    nodes_by_id: dict[int, Node],
    small_component: tuple[int, ...],
    main_component: tuple[int, ...],
) -> tuple[int, int]:
    candidates: list[tuple[float, int, int]] = []
    for small_node_id in small_component:
        small_node = nodes_by_id[int(small_node_id)]
        for main_node_id in main_component:
            main_node = nodes_by_id[int(main_node_id)]
            distance = math.hypot(
                float(small_node.x) - float(main_node.x),
                float(small_node.y) - float(main_node.y),
            )
            candidates.append((distance, int(small_node_id), int(main_node_id)))
    _distance, small_node_id, main_node_id = min(candidates)
    return small_node_id, main_node_id


def _stitch_link(
    *,
    link_id: int,
    src_node: Node,
    dst_node: Node,
    road_class: RoadClass,
    lanes: int,
    speed_mps: float,
    capacity_veh_per_tick: float,
) -> RoadLink:
    length = math.hypot(float(dst_node.x) - float(src_node.x), float(dst_node.y) - float(src_node.y))
    return RoadLink(
        link_id=int(link_id),
        src_node_id=int(src_node.node_id),
        dst_node_id=int(dst_node.node_id),
        road_class=road_class,
        length_m=max(length, 1.0),
        free_flow_speed_mps=float(speed_mps),
        capacity_veh_per_tick=float(capacity_veh_per_tick),
        lanes=int(lanes),
    )


def _repair_metadata(
    *,
    before: WeakConnectivityReport,
    after: WeakConnectivityReport,
    repair_link_ids: tuple[int, ...],
) -> dict[str, Any]:
    return {
        "weak_component_count_before_repair": before.component_count,
        "weak_component_sizes_before_repair": before.component_sizes,
        "connectivity_repair_link_count": len(repair_link_ids),
        "connectivity_repair_link_ids": tuple(int(link_id) for link_id in repair_link_ids),
        "weak_component_count_after_repair": after.component_count,
        "weak_component_sizes_after_repair": after.component_sizes,
    }
