from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import hashlib
import json
from typing import Any

import numpy as np

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
    initial_state_fingerprint: str = ""
    num_steps: int = 0
    rng_key_fingerprint: str = ""
    control_sequence_fingerprint: str = ""


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
    final_state_fingerprint: str = ""
    rng_key_fingerprint: str = ""
    control_sequence_fingerprint: str = ""


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


def make_runtime_replay_boundary(
    state: SimulationState,
    *,
    controls: tuple[SimulationControl, ...] | None = None,
    rng_key: PRNGKeyArray | None = None,
    num_steps: int | None = None,
) -> RuntimeReplayBoundary:
    bind_replay_inputs = any(
        value is not None for value in (controls, rng_key, num_steps)
    )
    if bind_replay_inputs and any(
        value is None for value in (controls, rng_key, num_steps)
    ):
        raise ValueError(
            "controls, rng_key, and num_steps must be provided together"
        )
    controls_tuple = tuple(controls or ())
    step_count = int(num_steps or 0)
    if bind_replay_inputs and len(controls_tuple) != step_count:
        raise ValueError("num_steps must match len(controls)")
    normalized_rng_key = (
        _normalize_runtime_rng_key(rng_key) if bind_replay_inputs else None
    )
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
        initial_state_fingerprint=runtime_state_fingerprint(state),
        edge_backend=state.config.edge_backend,
        flow_backend=state.config.flow_backend,
        routing_backend=state.config.routing_backend,
        agent_backend=state.config.agent_backend,
        num_steps=step_count,
        rng_key_fingerprint=(
            _runtime_value_fingerprint(normalized_rng_key)
            if normalized_rng_key is not None
            else ""
        ),
        control_sequence_fingerprint=(
            _runtime_value_fingerprint(controls_tuple) if bind_replay_inputs else ""
        ),
    )


def replay_simulation_sequence(request: RuntimeReplayRequest) -> RuntimeReplayResultRecord:
    _validate_runtime_replay_request(request)

    current_state = _snapshot_runtime_state(request.initial_state, readonly=False)
    current_key = _normalize_runtime_rng_key(request.rng_key).copy()
    telemetry_log: list[SimulationTelemetry] = []
    for control in request.controls:
        current_state, telemetry, _snapshot, current_key = simulation_step(
            current_state,
            control,
            current_key,
        )
        telemetry_log.append(telemetry)

    sealed_final_state = _snapshot_runtime_state(current_state, readonly=True)
    sealed_final_key = _normalize_runtime_rng_key(current_key).copy()
    sealed_final_key.setflags(write=False)
    route_state = coerce_simulation_route_cache_state(
        sealed_final_state.dynamic.route_candidate_state
    )
    final_cache_fingerprint = runtime_route_cache_fingerprint(
        candidate_sets=route_state.candidate_sets,
        stats=route_state.stats,
        state=sealed_final_state,
    )
    final_metrics = (
        sealed_final_state.dynamic.metrics_state
        if isinstance(sealed_final_state.dynamic.metrics_state, dict)
        else {}
    )
    return RuntimeReplayResultRecord(
        name="replay_simulation_sequence",
        num_steps=request.num_steps,
        transition_count=request.num_steps,
        initial_boundary=request.declared_boundary,
        final_state=sealed_final_state,
        final_tick=sealed_final_state.tick_index,
        final_rng_key=sealed_final_key,
        telemetry_log=tuple(telemetry_log),
        cache_fingerprint=final_cache_fingerprint,
        edge_backend=sealed_final_state.config.edge_backend,
        flow_backend=sealed_final_state.config.flow_backend,
        routing_backend=sealed_final_state.config.routing_backend,
        agent_backend=sealed_final_state.config.agent_backend,
        reroute_decisions_total=int(final_metrics.get("us2_reroute_decisions_total", 0)),
        persistence_decisions_total=int(
            final_metrics.get("us2_persistence_decisions_total", 0)
        ),
        final_state_fingerprint=runtime_state_fingerprint(sealed_final_state),
        rng_key_fingerprint=request.declared_boundary.rng_key_fingerprint,
        control_sequence_fingerprint=(
            request.declared_boundary.control_sequence_fingerprint
        ),
    )


def _validate_runtime_replay_request(request: RuntimeReplayRequest) -> None:
    _validate_replay_name(request.name)
    if request.num_steps < 0:
        raise ValueError("num_steps must be non-negative.")
    if len(request.controls) != request.num_steps:
        raise ValueError("num_steps must match len(controls).")
    expected = make_runtime_replay_boundary(
        request.initial_state,
        controls=request.controls,
        rng_key=request.rng_key,
        num_steps=request.num_steps,
    )
    if request.declared_boundary != expected:
        raise ValueError("declared runtime replay boundary must match the initial state.")


def _normalize_runtime_rng_key(rng_key: PRNGKeyArray | None) -> np.ndarray:
    if rng_key is None:
        raise ValueError("rng_key is required")
    normalized = np.asarray(rng_key, dtype=np.uint32)
    if normalized.shape != (2,):
        raise ValueError("runtime replay rng_key must have shape (2,)")
    return normalized


def _snapshot_runtime_state(
    state: SimulationState,
    *,
    readonly: bool,
) -> SimulationState:
    snapshot = _snapshot_runtime_value(state, readonly=readonly)
    if not isinstance(snapshot, SimulationState):
        raise TypeError("runtime replay snapshot did not produce SimulationState")
    return snapshot


def _snapshot_runtime_value(value: Any, *, readonly: bool) -> Any:
    if value is None or isinstance(value, str | bytes | bool | int | float | Enum):
        return value
    if isinstance(value, np.generic):
        return value.copy()
    if isinstance(value, np.ndarray):
        out = np.array(value, copy=True, order="K")
        if readonly:
            out.setflags(write=False)
        return out
    if is_dataclass(value) and not isinstance(value, type):
        kwargs = {
            item.name: _snapshot_runtime_value(
                getattr(value, item.name),
                readonly=readonly,
            )
            for item in fields(value)
            if item.init
        }
        return type(value)(**kwargs)
    if isinstance(value, Mapping):
        return {
            _snapshot_runtime_value(key, readonly=readonly): _snapshot_runtime_value(
                item_value,
                readonly=readonly,
            )
            for key, item_value in value.items()
        }
    if isinstance(value, tuple):
        return tuple(_snapshot_runtime_value(item, readonly=readonly) for item in value)
    if isinstance(value, list):
        return [_snapshot_runtime_value(item, readonly=readonly) for item in value]
    if isinstance(value, set):
        return {_snapshot_runtime_value(item, readonly=readonly) for item in value}
    if isinstance(value, frozenset):
        return frozenset(
            _snapshot_runtime_value(item, readonly=readonly) for item in value
        )
    if hasattr(value, "__array__") and hasattr(value, "dtype") and hasattr(value, "shape"):
        return _snapshot_runtime_value(np.asarray(value), readonly=readonly)
    raise TypeError(
        "runtime replay snapshot cannot clone "
        f"{type(value).__module__}.{type(value).__qualname__}"
    )


def _runtime_config_fingerprint(state: SimulationState) -> str:
    """Hash the complete runtime config so new fields fail closed by default."""

    return _runtime_value_fingerprint(state.config)


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
        # The generated geometry fingerprint does not encode runtime turn
        # authority or every routing input.  Hash the concrete static runtime
        # references used by the current tick transition as well, so a changed
        # legal turn, link attribute, or runtime-static metadata cannot reuse a
        # stale replay boundary. Population/schedule catalogs are excluded until
        # a SimulationState transition reads them; authoritative trip demand is
        # already covered in the complete dynamic-state fingerprint.
        "runtime_static_refs_fingerprint": _runtime_value_fingerprint(
            {
                "routing_static": {
                    key: value
                    for key, value in routing_static.items()
                    if key not in {"node_zone_by_id", "zone_node_ids"}
                },
                "ui_network_geometry_version": static.ui_network_geometry_version,
                "metadata": static.metadata,
            }
        ),
    }
    stable_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(stable_payload.encode("utf-8")).hexdigest()


def runtime_state_fingerprint(state: SimulationState) -> str:
    """Hash all replay-authoritative runtime state.

    The digest covers complete config and static-input fingerprints plus every
    dynamic state container, including flow residuals, realized sink flow,
    demand lifecycle sets, active-agent packed arrays/plugin memory, events, and
    route-cache contents.  Host timing diagnostics are deliberately excluded:
    they are observations of execution speed, not inputs to deterministic state
    evolution.
    """

    return _runtime_value_fingerprint(
        {
            "config_fingerprint": _runtime_config_fingerprint(state),
            "static_input_fingerprint": _runtime_static_input_fingerprint(state),
            "dynamic": state.dynamic,
            "metadata": state.metadata,
        }
    )


def _runtime_value_fingerprint(value: Any) -> str:
    return _runtime_value_digest(value).hex()


def _runtime_value_digest(value: Any) -> bytes:
    digest = hashlib.sha256()

    if value is None:
        digest.update(b"none")
        return digest.digest()
    if isinstance(value, Enum):
        digest.update(b"enum")
        _digest_add_text(digest, f"{type(value).__module__}.{type(value).__qualname__}")
        digest.update(_runtime_value_digest(value.value))
        return digest.digest()
    if isinstance(value, bool):
        digest.update(b"bool1" if value else b"bool0")
        return digest.digest()
    if isinstance(value, int):
        digest.update(b"int")
        _digest_add_text(digest, str(value))
        return digest.digest()
    if isinstance(value, float):
        digest.update(b"float")
        _digest_add_text(digest, value.hex())
        return digest.digest()
    if isinstance(value, str):
        digest.update(b"str")
        _digest_add_text(digest, value)
        return digest.digest()
    if isinstance(value, bytes):
        digest.update(b"bytes")
        _digest_add_bytes(digest, value)
        return digest.digest()
    if isinstance(value, np.generic):
        return _runtime_value_digest(np.asarray(value))
    if isinstance(value, np.ndarray):
        digest.update(b"ndarray")
        _digest_add_text(digest, repr(tuple(int(size) for size in value.shape)))
        if value.dtype.hasobject:
            digest.update(_runtime_value_digest(value.tolist()))
            return digest.digest()
        array = np.ascontiguousarray(value)
        if array.dtype.byteorder == ">" or (
            array.dtype.byteorder == "=" and not np.little_endian
        ):
            array = array.byteswap().view(array.dtype.newbyteorder("<"))
        normalized_dtype = array.dtype.newbyteorder("<")
        if array.dtype != normalized_dtype:
            array = array.view(normalized_dtype)
        _digest_add_text(digest, normalized_dtype.str)
        _digest_add_text(
            digest,
            repr(np.lib.format.dtype_to_descr(normalized_dtype)),
        )
        _digest_add_text(digest, str(int(normalized_dtype.itemsize)))
        _digest_add_text(digest, str(int(normalized_dtype.alignment)))
        digest.update(b"aligned1" if normalized_dtype.isalignedstruct else b"aligned0")
        digest.update(_runtime_value_digest(dict(normalized_dtype.metadata or {})))
        _digest_add_bytes(digest, array.tobytes(order="C"))
        return digest.digest()
    if is_dataclass(value) and not isinstance(value, type):
        digest.update(b"dataclass")
        _digest_add_text(digest, f"{type(value).__module__}.{type(value).__qualname__}")
        replay_fields = tuple(
            item for item in fields(value) if _is_replay_authoritative_key(item.name)
        )
        digest.update(len(replay_fields).to_bytes(8, byteorder="big"))
        for item in replay_fields:
            _digest_add_text(digest, item.name)
            digest.update(_runtime_value_digest(getattr(value, item.name)))
        return digest.digest()
    if isinstance(value, Mapping):
        digest.update(b"mapping")
        item_digests: list[bytes] = []
        for key, item_value in value.items():
            if isinstance(key, str) and not _is_replay_authoritative_key(key):
                continue
            item_digest = hashlib.sha256()
            item_digest.update(_runtime_value_digest(key))
            item_digest.update(_runtime_value_digest(item_value))
            item_digests.append(item_digest.digest())
        digest.update(len(item_digests).to_bytes(8, byteorder="big"))
        for item_digest in sorted(item_digests):
            digest.update(item_digest)
        return digest.digest()
    if isinstance(value, tuple | list):
        digest.update(b"tuple" if isinstance(value, tuple) else b"list")
        digest.update(len(value).to_bytes(8, byteorder="big"))
        for item in value:
            digest.update(_runtime_value_digest(item))
        return digest.digest()
    if isinstance(value, set | frozenset):
        digest.update(b"frozenset" if isinstance(value, frozenset) else b"set")
        item_digests = sorted(_runtime_value_digest(item) for item in value)
        digest.update(len(item_digests).to_bytes(8, byteorder="big"))
        for item_digest in item_digests:
            digest.update(item_digest)
        return digest.digest()
    if hasattr(value, "__array__") and hasattr(value, "dtype") and hasattr(value, "shape"):
        return _runtime_value_digest(np.asarray(value))
    raise TypeError(
        "runtime replay fingerprint cannot serialize "
        f"{type(value).__module__}.{type(value).__qualname__}"
    )


def _is_replay_authoritative_key(key: str) -> bool:
    return not str(key).endswith(
        ("_seconds_total", "_wall_ns", "_wall_ns_total")
    )


def _digest_add_text(digest: Any, value: str) -> None:
    _digest_add_bytes(digest, str(value).encode("utf-8"))


def _digest_add_bytes(digest: Any, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, byteorder="big"))
    digest.update(value)
