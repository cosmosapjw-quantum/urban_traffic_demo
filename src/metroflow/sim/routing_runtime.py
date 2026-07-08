"""Runtime route-cache and coarse active-agent movement helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Mapping

import numpy as np

from metroflow.demand.trips import TripRequest, TripRequestStatus
from metroflow.routing.candidates import (
    RouteCandidateRefreshPolicy,
    RouteCandidateSet,
    refresh_od_route_candidate_set,
)
from metroflow.sim.active_agents import (
    ActiveAgentPool,
    ActiveAgentSlot,
    allocate_active_agent_slot,
)
from metroflow.sim.state import SimulationState

__all__ = [
    "SimulationRouteCacheState",
    "create_simulation_route_cache_state",
    "coerce_simulation_route_cache_state",
    "runtime_route_cache_fingerprint",
    "refresh_runtime_route_candidates",
    "advance_runtime_active_agents",
]


@dataclass(slots=True)
class SimulationRouteCacheState:
    """Runtime-owned OD route candidate and dynamic-potential cache state."""

    candidate_sets: dict[tuple[int, int], RouteCandidateSet] = field(default_factory=dict)
    potential_cache: dict[Any, Any] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)
    cache_generation: int = 0
    last_signature: str = ""

    def __post_init__(self) -> None:
        self.candidate_sets = {
            (int(k[0]), int(k[1])): v for k, v in dict(self.candidate_sets).items()
        }
        self.potential_cache = dict(self.potential_cache)
        self.stats = dict(self.stats)
        self.cache_generation = int(self.cache_generation)
        self.last_signature = str(self.last_signature)
        if self.cache_generation < 0:
            raise ValueError("cache_generation must be >= 0")


def create_simulation_route_cache_state() -> SimulationRouteCacheState:
    """Create an empty runtime route-cache state."""

    return SimulationRouteCacheState()


def coerce_simulation_route_cache_state(raw: Any) -> SimulationRouteCacheState:
    """Coerce optional dynamic route-cache state to the concrete runtime container."""

    if raw is None:
        return create_simulation_route_cache_state()
    if isinstance(raw, SimulationRouteCacheState):
        return raw
    if isinstance(raw, Mapping):
        return SimulationRouteCacheState(**dict(raw))
    raise TypeError("route_candidate_state must be a SimulationRouteCacheState or mapping")


def refresh_runtime_route_candidates(
    state: SimulationState,
    *,
    force_refresh: bool = False,
) -> tuple[SimulationRouteCacheState, dict[str, int]]:
    """Refresh/reuse OD route candidates for currently activated trips."""

    _validate_routing_backend(state.config.routing_backend)
    route_state = coerce_simulation_route_cache_state(state.dynamic.route_candidate_state)
    road_csr = _road_csr_from_state(state)
    link_state = state.dynamic.flow_link_state
    if road_csr is None or link_state is None:
        return route_state, _route_tick_counters(route_state.stats)

    demand_state = _demand_mapping(state)
    trips = _route_relevant_trip_requests(demand_state)
    if not trips:
        return route_state, _route_tick_counters(route_state.stats)

    pois_by_id = _pois_by_id(state)
    active_event_count = len(_active_events(state))
    policy = RouteCandidateRefreshPolicy(
        refresh_interval_ticks=state.config.route_refresh_interval_ticks,
        max_candidates=state.config.route_max_candidates,
        max_hops=state.config.route_max_hops,
    )
    stats = dict(route_state.stats)
    candidate_sets = dict(route_state.candidate_sets)
    potential_cache = dict(route_state.potential_cache)
    before = dict(stats)

    for trip in trips:
        od = _trip_od_nodes(trip, pois_by_id)
        if od is None:
            continue
        od_key, origin_node_id, destination_node_id = od
        cache_key = _route_potential_cache_key(
            state=state,
            destination_node_id=destination_node_id,
        )
        candidate_sets[od_key] = refresh_od_route_candidate_set(
            candidate_sets.get(od_key),
            road_csr=road_csr,
            link_state=link_state,
            od_key=od_key,
            origin_node_id=origin_node_id,
            destination_node_id=destination_node_id,
            current_tick=state.tick_index,
            incident_active=active_event_count > 0,
            force_refresh=force_refresh,
            policy=policy,
            potential_cache=potential_cache,
            cache_key=cache_key,
            stats=stats,
        )

    next_state = SimulationRouteCacheState(
        candidate_sets=candidate_sets,
        potential_cache=potential_cache,
        stats=stats,
        cache_generation=route_state.cache_generation + 1,
        last_signature=runtime_route_cache_fingerprint(
            candidate_sets=candidate_sets,
            stats=stats,
            state=state,
        ),
    )
    return next_state, _route_tick_counters(stats, before=before)


def advance_runtime_active_agents(
    state: SimulationState,
) -> tuple[ActiveAgentPool | None, dict[str, int], dict[str, Any]]:
    """Allocate activated trips to cached routes and move active agents one link."""

    pool = state.dynamic.active_agent_pool
    if not isinstance(pool, ActiveAgentPool):
        return None, _agent_tick_counters(), _demand_mapping(state)
    route_state = coerce_simulation_route_cache_state(state.dynamic.route_candidate_state)
    demand_state = dict(_demand_mapping(state))
    trips = tuple(demand_state.get("trip_requests", ()))
    if not trips:
        return pool, _agent_tick_counters(), demand_state

    allocated_ids = _id_set(demand_state.get("allocated_trip_request_ids", ()))
    completed_ids = _id_set(demand_state.get("completed_trip_request_ids", ()))
    failed_ids = _id_set(demand_state.get("failed_trip_request_ids", ()))

    pool_after_alloc = pool
    plugin_memory = dict(pool_after_alloc.plugin_memory)
    counters = _agent_tick_counters()
    pois_by_id = _pois_by_id(state)

    for trip in _activated_trip_requests(trips):
        trip_id = int(trip.trip_request_id)
        if trip_id in allocated_ids or trip_id in completed_ids or trip_id in failed_ids:
            continue
        if pool_after_alloc.free_slot_count <= 0:
            break
        od = _trip_od_nodes(trip, pois_by_id)
        candidate_set = route_state.candidate_sets.get(od[0]) if od is not None else None
        path = _first_candidate_path(candidate_set)
        if not path:
            failed_ids.add(trip_id)
            counters["trip_failed_this_tick"] += 1
            continue
        _od_key, _origin_node_id, destination_node_id = od
        payload = ActiveAgentSlot.spawn(
            citizen_id=trip.citizen_id,
            trip_id=trip_id,
            current_link_id=path[0],
            dest_node_id=destination_node_id,
            behavior_profile_id=0,
            remaining_route_ptr=0,
        )
        pool_after_alloc, slot_id = allocate_active_agent_slot(pool_after_alloc, payload)
        plugin_memory = dict(pool_after_alloc.plugin_memory)
        plugin_memory[int(slot_id)] = {
            "route_path": path,
            "origin_poi_id": int(trip.origin_poi_id),
            "dest_poi_id": int(trip.dest_poi_id),
            "trip_request_id": trip_id,
        }
        pool_after_alloc = _replace_pool_plugin_memory(pool_after_alloc, plugin_memory)
        allocated_ids.add(trip_id)
        counters["trip_allocated_this_tick"] += 1

    moved_pool, moved_counters, completed_now = _advance_pool_along_cached_routes(pool_after_alloc)
    counters.update({key: counters.get(key, 0) + value for key, value in moved_counters.items()})
    completed_ids.update(completed_now)
    counters["trip_completed_this_tick"] += len(completed_now)

    demand_state.update(
        {
            "allocated_trip_request_ids": tuple(sorted(allocated_ids)),
            "completed_trip_request_ids": tuple(sorted(completed_ids)),
            "failed_trip_request_ids": tuple(sorted(failed_ids)),
        }
    )
    demand_state.update(_demand_lifecycle_counts(trips, completed_ids, failed_ids))
    return moved_pool, counters, demand_state


def runtime_route_cache_fingerprint(
    *,
    candidate_sets: Mapping[tuple[int, int], RouteCandidateSet] | None = None,
    stats: Mapping[str, Any] | None = None,
    state: SimulationState | None = None,
) -> str:
    """Build a stable replay fingerprint for runtime route-cache state."""

    payload = {
        "candidate_sets": [
            {
                "od_key": list(key),
                "candidate_ids": list(value.candidate_ids),
                "candidate_paths": [list(path) for path in value.candidate_paths],
                "last_refresh_tick": value.last_refresh_tick,
            }
            for key, value in sorted(dict(candidate_sets or {}).items())
        ],
        "stats": {
            str(key): stats[key]
            for key in sorted(dict(stats or {}))
            if isinstance(stats[key], (int, float, str, bool))
        },
        "state": _state_cache_signature(state) if state is not None else None,
    }
    stable = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _validate_routing_backend(routing_backend: str) -> None:
    if routing_backend == "rust_cpu":
        raise RuntimeError(
            "Rust CPU routing backend unavailable; dynamic-potential Dijkstra is not implemented"
        )
    if routing_backend not in {"baseline", "auto"}:
        raise ValueError("routing_backend must be one of: baseline, rust_cpu, auto")


def _route_tick_counters(
    stats: Mapping[str, Any],
    *,
    before: Mapping[str, Any] | None = None,
) -> dict[str, int]:
    prior = dict(before or {})
    return {
        "route_candidate_refresh_this_tick": int(
            stats.get("route_candidate_refresh_total", 0)
        )
        - int(prior.get("route_candidate_refresh_total", 0)),
        "route_candidate_reuse_this_tick": int(
            stats.get("route_candidate_reuse_total", 0)
        )
        - int(prior.get("route_candidate_reuse_total", 0)),
        "dynamic_potential_recompute_this_tick": int(
            stats.get("dynamic_potential_recompute_total", 0)
        )
        - int(prior.get("dynamic_potential_recompute_total", 0)),
        "dynamic_potential_cache_hits_this_tick": int(
            stats.get("dynamic_potential_cache_hits_total", 0)
        )
        - int(prior.get("dynamic_potential_cache_hits_total", 0)),
    }


def _agent_tick_counters() -> dict[str, int]:
    return {
        "trip_allocated_this_tick": 0,
        "trip_completed_this_tick": 0,
        "trip_failed_this_tick": 0,
        "active_agent_moved_this_tick": 0,
    }


def _advance_pool_along_cached_routes(
    pool: ActiveAgentPool,
) -> tuple[ActiveAgentPool, dict[str, int], set[int]]:
    counters = _agent_tick_counters()
    completed_trip_ids: set[int] = set()
    free_stack = np.asarray(pool.free_slot_stack, dtype=np.int32).copy()
    alive_mask = np.asarray(pool.alive_mask, dtype=np.bool_).copy()
    citizen = np.asarray(pool.citizen_id, dtype=np.int32).copy()
    trip = np.asarray(pool.trip_id, dtype=np.int32).copy()
    current_link = np.asarray(pool.current_link_id, dtype=np.int32).copy()
    progress = np.asarray(pool.progress_01, dtype=np.float32).copy()
    route_ptr = np.asarray(pool.remaining_route_ptr, dtype=np.int32).copy()
    dest = np.asarray(pool.dest_node_id, dtype=np.int32).copy()
    behavior = np.asarray(pool.behavior_profile_id, dtype=np.int32).copy()
    cooldown = np.asarray(pool.reroute_cooldown_ticks, dtype=np.int32).copy()
    plugin_memory = dict(pool.plugin_memory)
    free_count = int(pool.free_slot_count)
    alive_count = int(pool.alive_count)

    for slot_id in [idx for idx, alive in enumerate(alive_mask.tolist()) if bool(alive)]:
        slot_memory = plugin_memory.get(int(slot_id), {})
        path = tuple(int(x) for x in tuple(slot_memory.get("route_path", ())))
        ptr = int(route_ptr[slot_id])
        if not path or ptr >= len(path) - 1:
            completed_trip_ids.add(int(trip[slot_id]))
            plugin_memory.pop(int(slot_id), None)
            alive_mask[slot_id] = False
            citizen[slot_id] = -1
            trip[slot_id] = -1
            current_link[slot_id] = -1
            progress[slot_id] = 0.0
            route_ptr[slot_id] = 0
            dest[slot_id] = -1
            behavior[slot_id] = -1
            cooldown[slot_id] = 0
            free_stack[free_count] = int(slot_id)
            free_count += 1
            alive_count -= 1
            continue
        next_ptr = ptr + 1
        route_ptr[slot_id] = next_ptr
        current_link[slot_id] = path[next_ptr]
        progress[slot_id] = 0.0
        cooldown[slot_id] = max(0, int(cooldown[slot_id]) - 1)
        counters["active_agent_moved_this_tick"] += 1

    return (
        ActiveAgentPool.from_internal_arrays(
            capacity=pool.capacity,
            free_slot_stack=free_stack,
            free_slot_count=free_count,
            alive_mask=alive_mask,
            alive_count=alive_count,
            citizen_id=citizen,
            trip_id=trip,
            current_link_id=current_link,
            progress_01=progress,
            remaining_route_ptr=route_ptr,
            dest_node_id=dest,
            behavior_profile_id=behavior,
            reroute_cooldown_ticks=cooldown,
            plugin_memory=plugin_memory,
        ),
        counters,
        completed_trip_ids,
    )


def _replace_pool_plugin_memory(
    pool: ActiveAgentPool,
    plugin_memory: dict[Any, Any],
) -> ActiveAgentPool:
    return ActiveAgentPool.from_internal_arrays(
        capacity=pool.capacity,
        free_slot_stack=pool.free_slot_stack,
        free_slot_count=pool.free_slot_count,
        alive_mask=pool.alive_mask,
        alive_count=pool.alive_count,
        citizen_id=pool.citizen_id,
        trip_id=pool.trip_id,
        current_link_id=pool.current_link_id,
        progress_01=pool.progress_01,
        remaining_route_ptr=pool.remaining_route_ptr,
        dest_node_id=pool.dest_node_id,
        behavior_profile_id=pool.behavior_profile_id,
        reroute_cooldown_ticks=pool.reroute_cooldown_ticks,
        plugin_memory=plugin_memory,
    )


def _route_relevant_trip_requests(demand_state: Mapping[str, Any]) -> tuple[TripRequest, ...]:
    completed_ids = _id_set(demand_state.get("completed_trip_request_ids", ()))
    failed_ids = _id_set(demand_state.get("failed_trip_request_ids", ()))
    trips = []
    for raw_trip in tuple(demand_state.get("trip_requests", ())):
        trip = _coerce_trip(raw_trip)
        if trip.status is not TripRequestStatus.ACTIVATED:
            continue
        trip_id = int(trip.trip_request_id)
        if trip_id not in completed_ids and trip_id not in failed_ids:
            trips.append(trip)
    return tuple(sorted(trips, key=lambda item: int(item.trip_request_id)))


def _activated_trip_requests(trips: tuple[Any, ...]) -> tuple[TripRequest, ...]:
    out = []
    for raw_trip in trips:
        trip = _coerce_trip(raw_trip)
        if trip.status is TripRequestStatus.ACTIVATED:
            out.append(trip)
    return tuple(sorted(out, key=lambda item: int(item.trip_request_id)))


def _coerce_trip(raw: Any) -> TripRequest:
    if isinstance(raw, TripRequest):
        return raw
    return TripRequest(**dict(raw))


def _trip_od_nodes(
    trip: TripRequest,
    pois_by_id: Mapping[int, Any],
) -> tuple[tuple[int, int], int, int] | None:
    origin_poi = pois_by_id.get(int(trip.origin_poi_id))
    dest_poi = pois_by_id.get(int(trip.dest_poi_id))
    if origin_poi is None or dest_poi is None:
        return None
    od_key = (int(trip.origin_poi_id), int(trip.dest_poi_id))
    return od_key, int(origin_poi.node_id), int(dest_poi.node_id)


def _first_candidate_path(candidate_set: RouteCandidateSet | None) -> tuple[int, ...]:
    if candidate_set is None or not candidate_set.candidate_paths:
        return ()
    return tuple(int(x) for x in candidate_set.candidate_paths[0])


def _demand_lifecycle_counts(
    trips: tuple[Any, ...],
    completed_ids: set[int],
    failed_ids: set[int],
) -> dict[str, int]:
    queued = 0
    activated = 0
    for raw_trip in trips:
        trip = _coerce_trip(raw_trip)
        trip_id = int(trip.trip_request_id)
        if trip_id in completed_ids or trip_id in failed_ids:
            continue
        if trip.status is TripRequestStatus.QUEUED:
            queued += 1
        elif trip.status is TripRequestStatus.ACTIVATED:
            activated += 1
    return {
        "queued_trip_requests": queued,
        "activated_trip_requests": activated,
        "pending_trip_requests": queued + activated,
    }


def _id_set(raw: Any) -> set[int]:
    return {int(value) for value in tuple(raw or ())}


def _road_csr_from_state(state: SimulationState) -> Any:
    routing_static = state.static.routing_static
    if isinstance(routing_static, Mapping):
        return routing_static.get("road_csr")
    return getattr(routing_static, "road_csr", None)


def _demand_mapping(state: SimulationState) -> dict[str, Any]:
    if isinstance(state.dynamic.demand_state, Mapping):
        return dict(state.dynamic.demand_state)
    return {}


def _pois_by_id(state: SimulationState) -> dict[int, Any]:
    return {int(poi.poi_id): poi for poi in tuple(state.static.pois or ())}


def _active_events(state: SimulationState) -> tuple[Any, ...]:
    event_state = state.dynamic.event_state
    if isinstance(event_state, Mapping):
        return tuple(event_state.get("active_events", ()) or ())
    return tuple(getattr(event_state, "active_events", ()) or ())


def _route_potential_cache_key(
    *,
    state: SimulationState,
    destination_node_id: int,
) -> tuple[Any, ...]:
    return (
        "runtime_dynamic_potential",
        _state_cache_signature(state),
        int(destination_node_id),
        int(state.config.route_max_hops),
        int(state.config.route_max_candidates),
    )


def _state_cache_signature(state: SimulationState | None) -> tuple[Any, ...] | None:
    if state is None:
        return None
    link_state = state.dynamic.flow_link_state
    link_metadata = getattr(link_state, "metadata", {}) if link_state is not None else {}
    if not isinstance(link_metadata, Mapping):
        link_metadata = {}
    road_csr = _road_csr_from_state(state)
    return (
        str(state.static.ui_network_geometry_version or state.static.scenario_id),
        int(getattr(road_csr, "node_count", 0) or 0),
        int(getattr(road_csr, "link_count", 0) or 0),
        int(link_metadata.get("runtime_flow_generation", 0)),
        int(link_metadata.get("runtime_incident_generation", 0)),
    )
