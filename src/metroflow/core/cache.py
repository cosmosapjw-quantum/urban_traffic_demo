from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple
from .state import WorldState, with_graph_version_bump, with_landuse_version_bump, with_policy_version_bump


@dataclass(frozen=True)
class CacheRegistry:
    route_cache_version: int = 0
    accessibility_cache_version: int = 0
    policy_cache_version: int = 0
    tags: Dict[str, int] = field(default_factory=dict)


def build_cache_registry(world: WorldState) -> CacheRegistry:
    return CacheRegistry(
        route_cache_version=world.graph.version,
        accessibility_cache_version=max(world.accessibility.version, world.graph.version, world.landuse.version),
        policy_cache_version=world.policy.version,
        tags={
            "graph": world.graph.version,
            "landuse": world.landuse.version,
            "policy": world.policy.version,
            "accessibility": world.accessibility.version,
        },
    )


def route_cache_token(world: WorldState) -> Tuple[int, int]:
    return (world.graph.version, world.policy.version)


def accessibility_cache_token(world: WorldState) -> Tuple[int, int, int]:
    return (world.graph.version, world.landuse.version, world.accessibility.version)


def policy_cache_token(world: WorldState) -> int:
    return world.policy.version


def invalidate_on_graph_edit(world: WorldState) -> WorldState:
    return with_graph_version_bump(world)


def invalidate_on_landuse_edit(world: WorldState) -> WorldState:
    return with_landuse_version_bump(world)


def invalidate_on_policy_edit(world: WorldState) -> WorldState:
    return with_policy_version_bump(world)
