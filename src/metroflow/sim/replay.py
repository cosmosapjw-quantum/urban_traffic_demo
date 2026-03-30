from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from metroflow.core.contracts import TickSchedule, validate_state_contract
from metroflow.core.journal import InterventionJournal
from metroflow.core.state import WorldState
from metroflow.sim.orchestrator import step_world


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


def make_replay_boundary(world: WorldState, journal: InterventionJournal) -> ReplayBoundary:
    validate_state_contract(world)
    return ReplayBoundary(
        seed=world.replay.seed,
        initial_traffic_step=world.traffic.step,
        graph_version=world.graph.version,
        landuse_version=world.landuse.version,
        accessibility_version=world.accessibility.version,
        policy_version=world.policy.version,
        journal_length=world.replay.journal_length,
        journal_fingerprint=journal_fingerprint(journal),
    )


def _validate_replay_name(name: str) -> None:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("replay request name must be non-empty.")
    if not name.startswith(("replay_", "replay-")):
        raise ValueError("replay request name must carry an explicit replay label.")


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
    )
