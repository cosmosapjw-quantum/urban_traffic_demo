"""Baseline simulation initialization wiring city, demand, flow, and UI state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from metroflow.city.generator_v2 import GeneratorV2, PreviewCityTopology
from metroflow.city.zones import ZoningPlacementResult, generate_zones_and_pois
from metroflow.demand.population import PopulationGenerationResult, generate_citizen_population
from metroflow.demand.trips import TripRequestGenerationResult, generate_trip_requests
from metroflow.flow.state import LinkState, NodeState
from metroflow.sim.active_agents import create_active_agent_pool
from metroflow.sim.config import CityGenerationConfig, SimulationConfig
from metroflow.sim.invariants import InvariantReport
from metroflow.sim.rng import PRNGKeyArray, key_from_seed
from metroflow.sim.routing_runtime import create_simulation_route_cache_state
from metroflow.sim.state import (
    SimulationClockState,
    SimulationDynamicRefs,
    SimulationState,
    SimulationStaticRefs,
)
from metroflow.ui.stream_buffer import UISnapshotStreamBuffer

__all__ = [
    "SimulationInitBundle",
    "build_initial_simulation_state",
]


@dataclass(slots=True)
class SimulationInitBundle:
    """Initialized baseline scenario bundle."""

    state: SimulationState
    rng_key: PRNGKeyArray
    city_topology: PreviewCityTopology
    zoning: ZoningPlacementResult
    population: PopulationGenerationResult
    trip_requests: TripRequestGenerationResult


def build_initial_simulation_state(
    *,
    config: SimulationConfig | None = None,
    scenario_seed: int = 0,
    city_config: CityGenerationConfig | None = None,
    eager_trip_generation: bool = False,
) -> SimulationInitBundle:
    """Build a deterministic baseline simulation state without donor-folder dependencies."""

    sim_config = config if config is not None else SimulationConfig()
    city_cfg = city_config if city_config is not None else CityGenerationConfig()
    scenario_seed = int(scenario_seed)
    rng_key = key_from_seed(scenario_seed)
    scenario_id = f"synthetic-{scenario_seed}"

    clock_state = SimulationClockState(
        tick_index=0,
        day_type=sim_config.day_type_set[0],
        time_band=sim_config.time_bands[0],
    )
    topology = GeneratorV2().generate_preview_topology(
        {
            "scenario_id": (
                "synthetic_100k"
                if sim_config.population_target >= 100_000
                else "synthetic_smoke"
            ),
            "seed": scenario_seed,
        }
    )
    road_csr = topology.build_csr(validate=True, require_weak_connectivity=True)
    zoning = generate_zones_and_pois(
        topology,
        config=city_cfg,
        seed=scenario_seed,
        population_target=sim_config.population_target,
        validate=True,
    )
    population = generate_citizen_population(
        zoning,
        config=sim_config,
        seed=scenario_seed,
        population_target=sim_config.population_target,
    )
    trip_requests = _build_initial_trip_requests(
        population=population,
        zoning=zoning,
        config=sim_config,
        seed=scenario_seed,
        day_type=clock_state.day_type,
        time_band=clock_state.time_band,
        start_tick=clock_state.tick_index,
        eager_trip_generation=eager_trip_generation,
    )
    flow_link_state = _build_initial_link_state(road_csr)
    flow_node_state = _build_initial_node_state(road_csr)
    geometry_version = f"city-{scenario_seed}-n{road_csr.node_count}-l{road_csr.link_count}"

    dynamic = SimulationDynamicRefs(
        clock_state=clock_state,
        demand_state=_build_initial_demand_state(trip_requests),
        active_agent_pool=create_active_agent_pool(sim_config.active_agent_capacity),
        flow_link_state=flow_link_state,
        flow_node_state=flow_node_state,
        route_candidate_state=create_simulation_route_cache_state(),
        metrics_state=_initial_metrics_state(trip_requests),
        invariant_state=InvariantReport(tick_index=0),
        ui_state=(
            UISnapshotStreamBuffer(
                tick_seconds=sim_config.tick_seconds,
                hz_limit=sim_config.ui_stream_hz_limit,
            )
            if sim_config.ui_stream_enabled
            else None
        ),
        metadata={
            "scenario_seed": scenario_seed,
            "init_builder": "sim.init.build_initial_simulation_state",
        },
    )
    state = SimulationState(
        config=sim_config,
        static=SimulationStaticRefs(
            scenario_id=scenario_id,
            city_topology=topology,
            zones=zoning.zones,
            pois=zoning.pois,
            population=population.citizens,
            schedule_templates=population.schedule_templates,
            routing_static={
                "road_csr": road_csr,
                "node_zone_by_id": dict(zoning.node_zone_by_id),
                "zone_node_ids": dict(zoning.zone_node_ids),
            },
            ui_network_geometry_version=geometry_version,
            metadata={
                "scenario_seed": scenario_seed,
                "city_node_count": road_csr.node_count,
                "city_link_count": road_csr.link_count,
                "trip_request_count_init": len(trip_requests.trip_requests),
                "eager_trip_generation": int(bool(eager_trip_generation)),
                "city_topology_engine": str(topology.metadata.get("engine", "")),
            },
        ),
        dynamic=dynamic,
        metadata={"scenario_seed": scenario_seed},
    )
    return SimulationInitBundle(
        state=state,
        rng_key=rng_key,
        city_topology=topology,
        zoning=zoning,
        population=population,
        trip_requests=trip_requests,
    )


def _build_initial_trip_requests(
    *,
    population: PopulationGenerationResult,
    zoning: ZoningPlacementResult,
    config: SimulationConfig,
    seed: int,
    day_type: Any,
    time_band: Any,
    start_tick: int,
    eager_trip_generation: bool,
) -> TripRequestGenerationResult:
    if not eager_trip_generation:
        return TripRequestGenerationResult(
            trip_requests=(),
            metadata={
                "seed": int(seed),
                "day_type": str(getattr(day_type, "value", day_type)),
                "time_band": str(getattr(time_band, "value", time_band)),
                "trip_request_count": 0,
                "eager_trip_generation": 0,
            },
        )
    return generate_trip_requests(
        population,
        zoning,
        config,
        seed=seed,
        day_type=day_type,
        time_band=time_band,
        start_tick=start_tick,
        jitter_max_ticks=0,
    )


def _build_initial_link_state(road_csr: Any) -> LinkState:
    travel_time_cost = np.asarray(
        [
            max(1e-3, float(link.length_m) / max(1e-3, float(link.free_flow_speed_mps)))
            for link in road_csr.links
        ],
        dtype=np.float32,
    )
    capacity = np.asarray(
        [max(0.0, float(link.capacity_veh_per_tick)) for link in road_csr.links],
        dtype=np.float32,
    )
    link_count = int(road_csr.link_count)
    zeros = np.zeros((link_count,), dtype=np.float32)
    ones = np.ones((link_count,), dtype=np.float32)
    return LinkState(
        queue_vehicles=zeros,
        inflow_vehicles=zeros,
        outflow_vehicles=zeros,
        travel_time_cost=travel_time_cost,
        capacity_veh_per_tick=capacity,
        incident_capacity_multiplier=ones,
        capacity_violation_flags=np.zeros((link_count,), dtype=np.bool_),
        metadata={
            "free_flow_travel_time_cost": travel_time_cost,
            "runtime_flow_generation": 0,
            "runtime_incident_generation": 0,
        },
    )


def _build_initial_node_state(road_csr: Any) -> NodeState:
    turn_count = int(road_csr.turn_count)
    node_count = int(road_csr.node_count)
    zeros_turn = np.zeros((turn_count,), dtype=np.float32)
    return NodeState(
        turn_from_link_index=road_csr.turn_from_link_index,
        turn_to_link_index=road_csr.turn_to_link_index,
        turn_demand=zeros_turn,
        turn_supply=zeros_turn,
        turn_flow=zeros_turn,
        signal_phase_index=np.zeros((node_count,), dtype=np.int32),
        signal_phase_timer=np.zeros((node_count,), dtype=np.int32),
        metadata={
            "turn_base_priority": np.asarray(road_csr.turn_base_priority, dtype=np.float32),
            "turn_is_forbidden": np.asarray(road_csr.turn_is_forbidden, dtype=np.bool_),
        },
    )


def _build_initial_demand_state(trips: TripRequestGenerationResult) -> dict[str, Any]:
    trip_requests = tuple(trips.trip_requests)
    queued_count = sum(1 for trip in trip_requests if str(trip.status.value) == "queued")
    return {
        "trip_requests": trip_requests,
        "queued_trip_requests": queued_count,
        "pending_trip_requests": queued_count,
        "activated_trip_requests": 0,
        "last_generation_metadata": dict(trips.metadata),
    }


def _initial_metrics_state(trips: TripRequestGenerationResult) -> dict[str, Any]:
    generated_total = len(trips.trip_requests)
    return {
        "tick_index": 0,
        "active_agents": 0,
        "queued_trip_requests": generated_total,
        "pending_trip_requests": generated_total,
        "completed_trips_total": 0,
        "failed_trips_total": 0,
        "capacity_violation_count": 0,
        "capacity_violation_count_delta": 0,
        "negative_queue_detected": False,
        "ui_packets_emitted": 0,
        "generated_trip_total": generated_total,
        "flow_backend": "baseline",
        "routing_backend": "baseline",
        "agent_backend": "baseline",
        "flow_update_wall_ns": 0,
        "flow_update_wall_ns_total": 0,
        "active_agent_update_wall_ns": 0,
        "active_agent_update_wall_ns_total": 0,
        "reroute_decision_wall_ns": 0,
        "reroute_decision_wall_ns_total": 0,
        "active_agent_allocation_wall_ns": 0,
        "active_agent_allocation_wall_ns_total": 0,
        "active_agent_candidate_selection_wall_ns": 0,
        "active_agent_candidate_selection_wall_ns_total": 0,
        "active_agent_pool_write_wall_ns": 0,
        "active_agent_pool_write_wall_ns_total": 0,
        "active_agent_movement_wall_ns": 0,
        "active_agent_movement_wall_ns_total": 0,
        "queue_vehicles_total": 0.0,
        "outflow_vehicles_total": 0.0,
        "route_candidate_refresh_total": 0,
        "route_candidate_reuse_total": 0,
        "dynamic_potential_recompute_total": 0,
        "dynamic_potential_cache_hits_total": 0,
        "dynamic_potential_cache_pruned_total": 0,
        "dynamic_potential_cache_entry_count": 0,
        "route_candidate_refresh_seconds_total": 0.0,
        "route_candidate_potential_seconds_total": 0.0,
        "route_candidate_path_build_seconds_total": 0.0,
        "route_candidate_metadata_seconds_total": 0.0,
        "dynamic_potential_recompute_seconds_total": 0.0,
        "routing_compile_seconds_estimate_total": 0.0,
        "active_agent_moved_this_tick": 0,
        "active_agent_sink_wait_this_tick": 0,
        "active_agent_sink_wait_total": 0,
        "active_agent_rerouted_this_tick": 0,
        "active_agent_reroute_cooldown_this_tick": 0,
        "us2_reroute_decisions_total": 0,
        "us2_persistence_decisions_total": 0,
    }
