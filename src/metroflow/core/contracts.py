from __future__ import annotations

from dataclasses import dataclass
from .units import UnitsConfig
from .state import WorldState


@dataclass(frozen=True)
class TickSchedule:
    fast_every: int = 1
    medium_every: int = 10
    slow_every: int = 100


@dataclass(frozen=True)
class SimulationConfig:
    units: UnitsConfig
    schedule: TickSchedule
    forbid_same_tick_feedback: bool = True


def default_simulation_config() -> SimulationConfig:
    return SimulationConfig(
        units=UnitsConfig(),
        schedule=TickSchedule(),
        forbid_same_tick_feedback=True,
    )


def validate_time_scale_separation(config: SimulationConfig) -> None:
    if not (config.schedule.fast_every <= config.schedule.medium_every <= config.schedule.slow_every):
        raise ValueError("Invalid multirate ordering: fast <= medium <= slow must hold.")


def validate_state_contract(world: WorldState) -> None:
    if world.graph.num_edges != len(world.traffic.edge_queue) and world.graph.num_edges != 0:
        raise ValueError("Edge queue length must match graph.num_edges.")
    if world.graph.num_edges != len(world.traffic.edge_stock) and world.graph.num_edges != 0:
        raise ValueError("Edge stock length must match graph.num_edges.")
    if world.graph.num_edges != len(world.traffic.edge_travel_time) and world.graph.num_edges != 0:
        raise ValueError("Edge travel-time length must match graph.num_edges.")
