from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json

from metroflow.core.contracts import TickSchedule, validate_state_contract
from metroflow.core.journal import InterventionJournal
from metroflow.core.state import WorldState
from metroflow.sim.control import SimulationControl, SimulationTelemetry
from metroflow.sim.orchestrator import step_world
from metroflow.sim.rng import PRNGKeyArray
from metroflow.sim.routing_runtime import (
    coerce_simulation_route_cache_state,
    runtime_route_cache_fingerprint,
)
from metroflow.sim.state import SimulationState
from metroflow.sim.step import simulation_step
from metroflow.traffic.meso import EDGE_EVOLUTION_BACKENDS, EdgeEvolutionBackend


@dataclass(frozen=True)
class ReplayInputSignatureRecord:
    seed: int
    num_steps: int
    journal_fingerprint: str
    input_fingerprint: str


@dataclass(frozen=True)
class ReplayBoundary:
    seed: int
    initial_traffic_step: int
    graph_version: int
    landuse_version: int
    accessibility_version: int
    policy_version: int
    journal_length: int
    journal_fingerprint: str
    edge_backend: EdgeEvolutionBackend = "baseline"


@dataclass(frozen=True)
class ReplayStepInput:
    edge_inflow_veh_per_tick: tuple[float, ...] | None = None
    edge_outflow_veh_per_tick: tuple[float, ...] | None = None
    edge_free_flow_time_ticks: tuple[float, ...] | None = None
    edge_capacity_veh_per_tick: tuple[float, ...] | None = None
    zonal_travel_times: tuple[tuple[float, ...], ...] | None = None
    zone_opportunities: tuple[float, ...] | None = None


@dataclass(frozen=True)
class ReplayRequest:
    name: str
    initial_world: WorldState
    declared_boundary: ReplayBoundary
    journal: InterventionJournal
    schedule: TickSchedule
    num_steps: int
    step_inputs: tuple[ReplayStepInput, ...]
    edge_backend: EdgeEvolutionBackend = "baseline"


@dataclass(frozen=True)
class ReplayResultRecord:
    name: str
    num_steps: int
    schedule: TickSchedule
    journal_fingerprint: str
    transition_count: int
    initial_boundary: ReplayBoundary
    final_world: WorldState
    final_traffic_step: int
    edge_backend: EdgeEvolutionBackend = "baseline"


@dataclass(frozen=True)
class RuntimeReplayBoundary:
    scenario_id: str
    random_seed: int
    initial_tick: int
    config_fingerprint: str
    cache_fingerprint: str
    edge_backend: str = "baseline"
    flow_backend: str = "baseline"
    routing_backend: str = "baseline"
    agent_backend: str = "baseline"
    static_input_fingerprint: str = ""


@dataclass(frozen=True)
class RuntimeReplayRequest:
    name: str
    initial_state: SimulationState
    declared_boundary: RuntimeReplayBoundary
    controls: tuple[SimulationControl, ...]
    rng_key: PRNGKeyArray
    num_steps: int


@dataclass(frozen=True)
class RuntimeReplayResultRecord:
    name: str
    num_steps: int
    transition_count: int
    initial_boundary: RuntimeReplayBoundary
    final_state: SimulationState
    final_tick: int
    final_rng_key: PRNGKeyArray
    telemetry_log: tuple[SimulationTelemetry, ...]
    cache_fingerprint: str
    edge_backend: str = "baseline"
    flow_backend: str = "baseline"
    routing_backend: str = "baseline"
    agent_backend: str = "baseline"
    reroute_decisions_total: int = 0
    persistence_decisions_total: int = 0


def journal_fingerprint(journal: InterventionJournal) -> str:
    stable_payload = json.dumps(
        [
            {"step": record.step, "kind": record.kind, "payload": record.payload}
            for record in journal.records
        ],
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(stable_payload.encode("utf-8")).hexdigest()


def replay_input_fingerprint(
    seed: int,
    num_steps: int,
    journal: InterventionJournal,
    declared_observation: str,
) -> str:
    payload = json.dumps(
        {
            "seed": seed,
            "num_steps": num_steps,
            "journal_fingerprint": journal_fingerprint(journal),
            "declared_observation": declared_observation,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_replay_input_signature(
    world: WorldState,
    num_steps: int,
    input_fingerprint: str | float,
    journal: InterventionJournal | None = None,
) -> ReplayInputSignatureRecord:
    if num_steps < 0:
        raise ValueError("num_steps must be non-negative.")
    if journal is None:
        journal = InterventionJournal()
    return ReplayInputSignatureRecord(
        seed=world.replay.seed,
        num_steps=num_steps,
        journal_fingerprint=journal_fingerprint(journal),
        input_fingerprint=str(input_fingerprint),
    )


def make_replay_boundary(
    world: WorldState,
    journal: InterventionJournal,
    edge_backend: EdgeEvolutionBackend = "baseline",
) -> ReplayBoundary:
    validate_state_contract(world)
    _validate_replay_edge_backend(edge_backend)
    return ReplayBoundary(
        seed=world.replay.seed,
        initial_traffic_step=world.traffic.step,
        graph_version=world.graph.version,
        landuse_version=world.landuse.version,
        accessibility_version=world.accessibility.version,
        policy_version=world.policy.version,
        journal_length=world.replay.journal_length,
        journal_fingerprint=journal_fingerprint(journal),
        edge_backend=edge_backend,
    )


def _validate_replay_name(name: str) -> None:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("replay request name must be non-empty.")
    if not name.startswith(("replay_", "replay-")):
        raise ValueError("replay request name must carry an explicit replay label.")


def _validate_replay_edge_backend(edge_backend: str) -> None:
    if edge_backend not in EDGE_EVOLUTION_BACKENDS:
        raise ValueError("edge_backend must be one of: baseline, rust_cpu, jax, auto.")


def _validate_replay_boundary(boundary: ReplayBoundary, world: WorldState, journal: InterventionJournal) -> None:
    if (
        boundary.seed != world.replay.seed
        or boundary.initial_traffic_step != world.traffic.step
        or boundary.graph_version != world.graph.version
        or boundary.landuse_version != world.landuse.version
        or boundary.accessibility_version != world.accessibility.version
        or boundary.policy_version != world.policy.version
        or boundary.journal_length != world.replay.journal_length
    ):
        raise ValueError("declared replay boundary must match the supplied initial world.")
    if boundary.journal_length != len(journal.records) or boundary.journal_fingerprint != journal_fingerprint(journal):
        raise ValueError("declared replay boundary must match the supplied ordered journal.")


def _validate_replay_request(request: ReplayRequest) -> None:
    _validate_replay_name(request.name)
    if request.declared_boundary is None:
        raise ValueError("declared_boundary is required.")
    if request.journal is None:
        raise ValueError("journal is required.")
    if request.schedule is None:
        raise ValueError("schedule is required.")
    if request.step_inputs is None:
        raise ValueError("step_inputs are required.")
    if request.num_steps < 0:
        raise ValueError("num_steps must be non-negative.")
    if len(request.step_inputs) != request.num_steps:
        raise ValueError("num_steps must match len(step_inputs).")
    _validate_replay_edge_backend(request.edge_backend)
    if request.declared_boundary.edge_backend != request.edge_backend:
        raise ValueError("declared replay boundary edge_backend must match the replay request.")
    validate_state_contract(request.initial_world)
    _validate_replay_boundary(request.declared_boundary, request.initial_world, request.journal)


def replay_step_world_sequence(request: ReplayRequest) -> ReplayResultRecord:
    _validate_replay_request(request)

    current_world = request.initial_world
    for step_input in request.step_inputs:
        current_world = step_world(
            current_world,
            schedule=request.schedule,
            edge_inflow_veh_per_tick=step_input.edge_inflow_veh_per_tick,
            edge_outflow_veh_per_tick=step_input.edge_outflow_veh_per_tick,
            edge_free_flow_time_ticks=step_input.edge_free_flow_time_ticks,
            edge_capacity_veh_per_tick=step_input.edge_capacity_veh_per_tick,
            edge_backend=request.edge_backend,
            zonal_travel_times=step_input.zonal_travel_times,
            zone_opportunities=step_input.zone_opportunities,
        )

    return ReplayResultRecord(
        name="replay_step_world_sequence",
        num_steps=request.num_steps,
        schedule=request.schedule,
        journal_fingerprint=journal_fingerprint(request.journal),
        transition_count=request.num_steps,
        initial_boundary=request.declared_boundary,
        final_world=current_world,
        final_traffic_step=current_world.traffic.step,
        edge_backend=request.edge_backend,
    )


def make_runtime_replay_boundary(state: SimulationState) -> RuntimeReplayBoundary:
    route_state = coerce_simulation_route_cache_state(state.dynamic.route_candidate_state)
    return RuntimeReplayBoundary(
        scenario_id=str(state.static.scenario_id),
        random_seed=int(state.config.random_seed),
        initial_tick=int(state.tick_index),
        config_fingerprint=_runtime_config_fingerprint(state),
        cache_fingerprint=runtime_route_cache_fingerprint(
            candidate_sets=route_state.candidate_sets,
            stats=route_state.stats,
            state=state,
        ),
        static_input_fingerprint=_runtime_static_input_fingerprint(state),
        edge_backend=state.config.edge_backend,
        flow_backend=state.config.flow_backend,
        routing_backend=state.config.routing_backend,
        agent_backend=state.config.agent_backend,
    )


def replay_simulation_sequence(request: RuntimeReplayRequest) -> RuntimeReplayResultRecord:
    _validate_runtime_replay_request(request)

    current_state = request.initial_state
    current_key = request.rng_key
    telemetry_log: list[SimulationTelemetry] = []
    for control in request.controls:
        current_state, telemetry, _snapshot, current_key = simulation_step(
            current_state,
            control,
            current_key,
        )
        telemetry_log.append(telemetry)

    route_state = coerce_simulation_route_cache_state(current_state.dynamic.route_candidate_state)
    final_cache_fingerprint = runtime_route_cache_fingerprint(
        candidate_sets=route_state.candidate_sets,
        stats=route_state.stats,
        state=current_state,
    )
    final_metrics = (
        current_state.dynamic.metrics_state
        if isinstance(current_state.dynamic.metrics_state, dict)
        else {}
    )
    return RuntimeReplayResultRecord(
        name="replay_simulation_sequence",
        num_steps=request.num_steps,
        transition_count=request.num_steps,
        initial_boundary=request.declared_boundary,
        final_state=current_state,
        final_tick=current_state.tick_index,
        final_rng_key=current_key,
        telemetry_log=tuple(telemetry_log),
        cache_fingerprint=final_cache_fingerprint,
        edge_backend=current_state.config.edge_backend,
        flow_backend=current_state.config.flow_backend,
        routing_backend=current_state.config.routing_backend,
        agent_backend=current_state.config.agent_backend,
        reroute_decisions_total=int(final_metrics.get("us2_reroute_decisions_total", 0)),
        persistence_decisions_total=int(
            final_metrics.get("us2_persistence_decisions_total", 0)
        ),
    )


def _validate_runtime_replay_request(request: RuntimeReplayRequest) -> None:
    _validate_replay_name(request.name)
    if request.num_steps < 0:
        raise ValueError("num_steps must be non-negative.")
    if len(request.controls) != request.num_steps:
        raise ValueError("num_steps must match len(controls).")
    expected = make_runtime_replay_boundary(request.initial_state)
    if request.declared_boundary != expected:
        raise ValueError("declared runtime replay boundary must match the initial state.")


def _runtime_config_fingerprint(state: SimulationState) -> str:
    cfg = state.config
    payload = {
        "population_target": cfg.population_target,
        "tick_seconds": cfg.tick_seconds,
        "active_agent_capacity": cfg.active_agent_capacity,
        "random_seed": cfg.random_seed,
        "learning_enabled": cfg.learning_enabled,
        "ctm_mode_enabled": cfg.ctm_mode_enabled,
        "edge_backend": cfg.edge_backend,
        "flow_backend": cfg.flow_backend,
        "routing_backend": cfg.routing_backend,
        "agent_backend": cfg.agent_backend,
        "route_max_candidates": cfg.route_max_candidates,
        "route_max_hops": cfg.route_max_hops,
        "route_refresh_interval_ticks": cfg.route_refresh_interval_ticks,
        "route_path_size_gamma": cfg.route_path_size_gamma,
    }
    stable_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(stable_payload.encode("utf-8")).hexdigest()


def _runtime_static_input_fingerprint(state: SimulationState) -> str:
    """Hash replay-relevant static city inputs independently of runtime config."""

    static = state.static
    topology = static.city_topology
    geometry = getattr(topology, "road_geometry", None)
    routing_static = (
        static.routing_static if isinstance(static.routing_static, Mapping) else {}
    )
    node_zone_by_id = routing_static.get("node_zone_by_id", {})
    zone_node_ids = routing_static.get("zone_node_ids", {})
    metadata = static.metadata if isinstance(static.metadata, dict) else {}
    payload = {
        "scenario_id": str(static.scenario_id),
        "actual_road_geometry_fingerprint": str(
            getattr(geometry, "fingerprint", "")
        ),
        "declared_road_geometry_fingerprint": str(
            metadata.get("road_geometry_fingerprint", "")
        ),
        "zoning_placement_fingerprint": str(
            metadata.get("zoning_placement_fingerprint", "")
        ),
        "zone_poi_coupling": {
            key: str(metadata.get(key, ""))
            for key in (
                "zone_poi_coupling_requested_mode",
                "zone_poi_coupling_resolved_mode",
                "zone_poi_coupling_fallback_reason",
                "zone_poi_coupling_gate_version",
                "zone_poi_coupling_gate_digest",
                "zone_poi_coupling_anchor_digest",
            )
        },
        "zones": [
            {
                "zone_id": int(zone.zone_id),
                "zone_type": str(getattr(zone.zone_type, "value", zone.zone_type)),
                "centroid_x": float(zone.centroid_x),
                "centroid_y": float(zone.centroid_y),
                "population_capacity": int(zone.population_capacity),
                "job_capacity": int(zone.job_capacity),
                "leisure_capacity": int(zone.leisure_capacity),
            }
            for zone in sorted(tuple(static.zones or ()), key=lambda item: item.zone_id)
        ],
        "pois": [
            {
                "poi_id": int(poi.poi_id),
                "zone_id": int(poi.zone_id),
                "poi_type": str(getattr(poi.poi_type, "value", poi.poi_type)),
                "node_id": int(poi.node_id),
                "capacity_hint": int(poi.capacity_hint),
            }
            for poi in sorted(tuple(static.pois or ()), key=lambda item: item.poi_id)
        ],
        "node_zone_by_id": sorted(
            (int(node_id), int(zone_id))
            for node_id, zone_id in (
                node_zone_by_id.items()
                if isinstance(node_zone_by_id, Mapping)
                else ()
            )
        ),
        "zone_node_ids": [
            (zone_id, tuple(sorted(node_ids)))
            for zone_id, node_ids in sorted(
                (
                    (int(raw_zone_id), tuple(int(node_id) for node_id in node_ids))
                    for raw_zone_id, node_ids in (
                        zone_node_ids.items()
                        if isinstance(zone_node_ids, Mapping)
                        else ()
                    )
                ),
                key=lambda item: item[0],
            )
        ],
    }
    stable_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(stable_payload.encode("utf-8")).hexdigest()
