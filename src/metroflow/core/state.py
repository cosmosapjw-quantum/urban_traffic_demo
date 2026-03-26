from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Tuple


@dataclass(frozen=True)
class GraphState:
    version: int = 0
    num_nodes: int = 0
    num_edges: int = 0
    edge_src: Tuple[int, ...] = field(default_factory=tuple)
    edge_dst: Tuple[int, ...] = field(default_factory=tuple)
    edge_class: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TrafficState:
    step: int = 0
    edge_queue: Tuple[float, ...] = field(default_factory=tuple)
    edge_stock: Tuple[float, ...] = field(default_factory=tuple)
    edge_travel_time: Tuple[float, ...] = field(default_factory=tuple)
    movement_queue: Tuple[float, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DemandState:
    population: int = 100_000
    active_trip_count: int = 0


@dataclass(frozen=True)
class AccessibilityState:
    version: int = 0
    lagged_snapshot_step: int = -1
    zonal_costs: Tuple[Tuple[float, ...], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LandUseState:
    version: int = 0
    zone_labels: Tuple[str, ...] = field(default_factory=tuple)
    housing_capacity: Tuple[float, ...] = field(default_factory=tuple)
    jobs_capacity: Tuple[float, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PolicyState:
    version: int = 0
    last_learning_step: int = -1


@dataclass(frozen=True)
class ReplayState:
    seed: int = 0
    journal_length: int = 0


@dataclass(frozen=True)
class WorldState:
    graph: GraphState
    traffic: TrafficState
    demand: DemandState
    accessibility: AccessibilityState
    landuse: LandUseState
    policy: PolicyState
    replay: ReplayState


def make_empty_world_state(seed: int = 0) -> WorldState:
    return WorldState(
        graph=GraphState(),
        traffic=TrafficState(),
        demand=DemandState(),
        accessibility=AccessibilityState(),
        landuse=LandUseState(),
        policy=PolicyState(),
        replay=ReplayState(seed=seed),
    )


def with_graph_version_bump(world: WorldState) -> WorldState:
    return replace(
        world,
        graph=replace(world.graph, version=world.graph.version + 1),
        accessibility=replace(world.accessibility, version=world.accessibility.version + 1),
    )


def with_landuse_version_bump(world: WorldState) -> WorldState:
    return replace(
        world,
        landuse=replace(world.landuse, version=world.landuse.version + 1),
        accessibility=replace(world.accessibility, version=world.accessibility.version + 1),
    )


def with_policy_version_bump(world: WorldState) -> WorldState:
    return replace(
        world,
        policy=replace(world.policy, version=world.policy.version + 1),
    )
