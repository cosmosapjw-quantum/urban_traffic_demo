from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict
from .state import WorldState, with_graph_version_bump, with_landuse_version_bump, with_policy_version_bump


@dataclass(frozen=True)
class CacheRegistry:
    route_cache_version: int = 0
    accessibility_cache_version: int = 0
    policy_cache_version: int = 0
    tags: Dict[str, int] = field(default_factory=dict)


def invalidate_on_graph_edit(world: WorldState) -> WorldState:
    return with_graph_version_bump(world)


def invalidate_on_landuse_edit(world: WorldState) -> WorldState:
    return with_landuse_version_bump(world)


def invalidate_on_policy_edit(world: WorldState) -> WorldState:
    return with_policy_version_bump(world)
