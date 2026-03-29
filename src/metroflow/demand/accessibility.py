from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Tuple

from metroflow.core.state import WorldState


@dataclass(frozen=True)
class AccessibilitySnapshot:
    computed_at_step: int
    graph_version: int
    landuse_version: int
    zonal_costs: Tuple[Tuple[float, ...], ...] = tuple()


def compute_accessibility_placeholder() -> AccessibilitySnapshot:
    return AccessibilitySnapshot(computed_at_step=0, graph_version=0, landuse_version=0, zonal_costs=tuple())


def compute_accessibility_snapshot(
    *,
    step_idx: int,
    graph_version: int,
    landuse_version: int,
    zonal_travel_times: Tuple[Tuple[float, ...], ...],
    zone_opportunities: Tuple[float, ...],
) -> AccessibilitySnapshot:
    zone_count = len(zone_opportunities)
    if len(zonal_travel_times) != zone_count:
        raise ValueError("zonal_travel_times dimension must match zone_opportunities length.")
    if any(len(row) != zone_count for row in zonal_travel_times):
        raise ValueError("zonal_travel_times rows must match zone_opportunities length.")
    if any(travel_time < 0.0 for row in zonal_travel_times for travel_time in row):
        raise ValueError("zonal_travel_times must be non-negative.")
    if any(opportunity < 0.0 for opportunity in zone_opportunities):
        raise ValueError("zone_opportunities must be non-negative.")

    zonal_costs = []
    for row in zonal_travel_times:
        zonal_costs.append(
            tuple(travel_time / max(zone_opportunities[idx], 1.0) for idx, travel_time in enumerate(row))
        )
    return AccessibilitySnapshot(
        computed_at_step=step_idx,
        graph_version=graph_version,
        landuse_version=landuse_version,
        zonal_costs=tuple(zonal_costs),
    )


def snapshot_is_stale(snapshot: AccessibilitySnapshot, world: WorldState) -> bool:
    return (
        snapshot.graph_version != world.graph.version
        or snapshot.landuse_version != world.landuse.version
    )


def update_accessibility_cache(world: WorldState, snapshot: AccessibilitySnapshot) -> WorldState:
    lagged_snapshot_step = snapshot.computed_at_step if snapshot.zonal_costs else -1
    return replace(
        world,
        accessibility=replace(
            world.accessibility,
            version=world.accessibility.version + 1,
            lagged_snapshot_step=lagged_snapshot_step,
            graph_version=snapshot.graph_version,
            landuse_version=snapshot.landuse_version,
            zonal_costs=snapshot.zonal_costs,
        ),
    )
