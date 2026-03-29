from __future__ import annotations

from dataclasses import dataclass
from .units import UnitsConfig, validate_units_config
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
    validate_units_config(config.units)
    if config.schedule.fast_every <= 0:
        raise ValueError("fast_every must be positive.")
    if config.schedule.medium_every <= 0:
        raise ValueError("medium_every must be positive.")
    if config.schedule.slow_every <= 0:
        raise ValueError("slow_every must be positive.")
    if not (config.schedule.fast_every <= config.schedule.medium_every <= config.schedule.slow_every):
        raise ValueError("Invalid multirate ordering: fast <= medium <= slow must hold.")


def validate_state_contract(world: WorldState) -> None:
    if world.graph.version < 0:
        raise ValueError("Graph version must be non-negative.")
    if world.graph.num_nodes < 0:
        raise ValueError("graph.num_nodes must be non-negative.")
    if world.graph.num_edges < 0:
        raise ValueError("graph.num_edges must be non-negative.")
    if len(world.graph.edge_src) != world.graph.num_edges:
        raise ValueError("edge_src length must match graph.num_edges.")
    if len(world.graph.edge_dst) != world.graph.num_edges:
        raise ValueError("edge_dst length must match graph.num_edges.")
    if len(world.graph.edge_class) != world.graph.num_edges:
        raise ValueError("edge_class length must match graph.num_edges.")
    if any(src < 0 or src >= world.graph.num_nodes for src in world.graph.edge_src):
        raise ValueError("edge_src values must reference valid graph nodes.")
    if any(dst < 0 or dst >= world.graph.num_nodes for dst in world.graph.edge_dst):
        raise ValueError("edge_dst values must reference valid graph nodes.")

    if world.graph.num_edges != len(world.traffic.edge_queue):
        raise ValueError("Edge queue length must match graph.num_edges.")
    if world.graph.num_edges != len(world.traffic.edge_stock):
        raise ValueError("Edge stock length must match graph.num_edges.")
    if world.graph.num_edges != len(world.traffic.edge_travel_time):
        raise ValueError("Edge travel-time length must match graph.num_edges.")
    if any(movement < 0.0 for movement in world.traffic.movement_queue):
        raise ValueError("Movement queue values must be non-negative.")
    if any(queue < 0.0 for queue in world.traffic.edge_queue):
        raise ValueError("Edge queue values must be non-negative.")
    if any(stock < 0.0 for stock in world.traffic.edge_stock):
        raise ValueError("Edge stock values must be non-negative.")
    if any(travel_time < 0.0 for travel_time in world.traffic.edge_travel_time):
        raise ValueError("Edge travel-time values must be non-negative.")
    if any(queue > stock for queue, stock in zip(world.traffic.edge_queue, world.traffic.edge_stock)):
        raise ValueError("Edge queue must not exceed edge stock.")
    if world.demand.population < 0:
        raise ValueError("Population must be non-negative.")
    if world.demand.active_trip_count < 0:
        raise ValueError("Active trip count must be non-negative.")
    if world.demand.active_trip_count > world.demand.population:
        raise ValueError("Active trip count must not exceed population.")
    if world.accessibility.version < 0:
        raise ValueError("Accessibility version must be non-negative.")
    if world.accessibility.graph_version < 0:
        raise ValueError("Accessibility graph_version must be non-negative.")
    if world.accessibility.landuse_version < 0:
        raise ValueError("Accessibility landuse_version must be non-negative.")
    if world.landuse.version < 0:
        raise ValueError("Land-use version must be non-negative.")
    if world.policy.version < 0:
        raise ValueError("Policy version must be non-negative.")
    if world.replay.journal_length < 0:
        raise ValueError("Replay journal_length must be non-negative.")

    zone_count = len(world.landuse.zone_labels)
    if len(world.landuse.housing_capacity) != zone_count:
        raise ValueError("housing_capacity length must match zone_labels length.")
    if len(world.landuse.jobs_capacity) != zone_count:
        raise ValueError("jobs_capacity length must match zone_labels length.")
    if any(capacity < 0.0 for capacity in world.landuse.housing_capacity):
        raise ValueError("Housing capacity values must be non-negative.")
    if any(capacity < 0.0 for capacity in world.landuse.jobs_capacity):
        raise ValueError("Jobs capacity values must be non-negative.")
    if len(world.accessibility.zonal_costs) not in (0, zone_count):
        raise ValueError("Accessibility zonal_costs dimension must match zone_labels length.")
    if any(len(row) != zone_count for row in world.accessibility.zonal_costs):
        raise ValueError("Accessibility zonal_cost rows must match zone_labels length.")
    if any(cost < 0.0 for row in world.accessibility.zonal_costs for cost in row):
        raise ValueError("Accessibility zonal_costs must be non-negative.")
    if not world.accessibility.zonal_costs and world.accessibility.lagged_snapshot_step != -1:
        raise ValueError("Cleared accessibility payload must reset lagged_snapshot_step to -1.")
    if world.accessibility.zonal_costs and world.accessibility.lagged_snapshot_step >= world.traffic.step:
        raise ValueError("Accessibility snapshot must be lagged relative to traffic.step.")
