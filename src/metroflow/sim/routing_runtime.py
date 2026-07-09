"""Runtime route-cache and coarse active-agent movement helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from math import isfinite, log
from typing import Any, Mapping

import numpy as np

from metroflow.backends.rust_cpu import (
    advance_active_agents_rust,
    rust_agent_backend_available,
    rust_routing_backend_available,
    select_route_candidate_index_rust,
)
from metroflow.demand.trips import TripRequest, TripRequestStatus
from metroflow.flow.state import LinkState
from metroflow.routing.candidates import (
    RouteCandidateRefreshPolicy,
    RouteCandidateSet,
    create_route_candidate_set,
    refresh_od_route_candidate_set,
)
from metroflow.routing.behavior_profiles import RouteChoiceProfile
from metroflow.routing.reroute_policy import decide_reroute_vs_persist
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


@dataclass(frozen=True, slots=True)
class _SelectedCandidateRoute:
    candidate_index: int
    candidate_id: int
    candidate_count: int
    path: tuple[int, ...]
    path_cost: float
    path_size_factor: float
    utility: float
    selection_backend: str


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
            routing_backend=state.config.routing_backend,
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
) -> tuple[ActiveAgentPool | None, dict[str, int], dict[str, Any], LinkState | None]:
    """Allocate activated trips to cached routes and move active agents one link."""

    pool = state.dynamic.active_agent_pool
    if not isinstance(pool, ActiveAgentPool):
        return None, _agent_tick_counters(), _demand_mapping(state), state.dynamic.flow_link_state
    route_state = coerce_simulation_route_cache_state(state.dynamic.route_candidate_state)
    demand_state = dict(_demand_mapping(state))
    trips = tuple(demand_state.get("trip_requests", ()))
    if not trips:
        return pool, _agent_tick_counters(), demand_state, state.dynamic.flow_link_state

    allocated_ids = _id_set(demand_state.get("allocated_trip_request_ids", ()))
    completed_ids = _id_set(demand_state.get("completed_trip_request_ids", ()))
    failed_ids = _id_set(demand_state.get("failed_trip_request_ids", ()))

    pool_after_alloc = pool
    plugin_memory = dict(pool_after_alloc.plugin_memory)
    counters = _agent_tick_counters()
    pois_by_id = _pois_by_id(state)
    newly_allocated_slot_ids: set[int] = set()
    source_queue_increments_by_link_id: dict[int, int] = {}

    for trip in _activated_trip_requests(trips):
        trip_id = int(trip.trip_request_id)
        if trip_id in allocated_ids or trip_id in completed_ids or trip_id in failed_ids:
            continue
        if pool_after_alloc.free_slot_count <= 0:
            break
        od = _trip_od_nodes(trip, pois_by_id)
        candidate_set = route_state.candidate_sets.get(od[0]) if od is not None else None
        selection = _select_candidate_route(
            candidate_set,
            path_size_gamma=state.config.route_path_size_gamma,
            routing_backend=state.config.routing_backend,
        )
        if selection is None:
            failed_ids.add(trip_id)
            counters["trip_failed_this_tick"] += 1
            continue
        path = selection.path
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
            **_selected_candidate_memory(selection),
        }
        pool_after_alloc = _replace_pool_plugin_memory(pool_after_alloc, plugin_memory)
        allocated_ids.add(trip_id)
        newly_allocated_slot_ids.add(int(slot_id))
        source_queue_increments_by_link_id[int(path[0])] = (
            source_queue_increments_by_link_id.get(int(path[0]), 0) + 1
        )
        counters["trip_allocated_this_tick"] += 1

    pool_after_reroute, reroute_counters = _apply_runtime_reroute_policy(
        state,
        pool_after_alloc,
        skip_slot_ids=newly_allocated_slot_ids,
    )
    counters.update({key: counters.get(key, 0) + value for key, value in reroute_counters.items()})
    moved_pool, moved_counters, completed_now = _advance_pool_along_cached_routes(
        pool_after_reroute,
        movement_budget_by_link_id=_movement_budget_by_link_id(state),
        completion_budget_by_link_id=_sink_discharge_budget_by_link_id(state),
        skip_slot_ids=newly_allocated_slot_ids,
        agent_backend=state.config.agent_backend,
    )
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
    return (
        moved_pool,
        counters,
        demand_state,
        _apply_source_queue_increments(state, source_queue_increments_by_link_id),
    )


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
                "metadata": _stable_fingerprint_metadata(value.metadata),
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


def _stable_fingerprint_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    stable: dict[str, Any] = {}
    for key, value in sorted(dict(metadata or {}).items()):
        converted = _stable_fingerprint_value(value)
        if converted is not None:
            stable[str(key)] = converted
    return stable


def _stable_fingerprint_value(value: Any) -> Any:
    if isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, tuple | list):
        converted = [_stable_fingerprint_value(item) for item in value]
        return [item for item in converted if item is not None]
    return None


def _validate_routing_backend(routing_backend: str) -> None:
    if routing_backend not in {"baseline", "rust_cpu", "auto"}:
        raise ValueError("routing_backend must be one of: baseline, rust_cpu, auto")


def _validate_agent_backend(agent_backend: str) -> None:
    if agent_backend not in {"baseline", "rust_cpu", "auto"}:
        raise ValueError("agent_backend must be one of: baseline, rust_cpu, auto")


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
        "active_agent_sink_wait_this_tick": 0,
        "active_agent_rerouted_this_tick": 0,
        "active_agent_reroute_cooldown_this_tick": 0,
    }


def _advance_pool_along_cached_routes(
    pool: ActiveAgentPool,
    *,
    movement_budget_by_link_id: Mapping[int, int],
    completion_budget_by_link_id: Mapping[int, int] | None = None,
    skip_slot_ids: set[int] | None = None,
    agent_backend: str = "baseline",
) -> tuple[ActiveAgentPool, dict[str, int], set[int]]:
    _validate_agent_backend(agent_backend)
    if agent_backend in {"rust_cpu", "auto"}:
        if not rust_agent_backend_available():
            if agent_backend == "rust_cpu":
                raise RuntimeError(
                    "Rust CPU active-agent backend unavailable. Build it with: "
                    ".venv/bin/python -m maturin develop --manifest-path "
                    "crates/metroflow-rust/Cargo.toml"
                )
        else:
            try:
                return _advance_pool_along_cached_routes_rust(
                    pool,
                    movement_budget_by_link_id=movement_budget_by_link_id,
                    completion_budget_by_link_id=completion_budget_by_link_id,
                    skip_slot_ids=skip_slot_ids,
                )
            except RuntimeError:
                if agent_backend == "rust_cpu":
                    raise

    counters = _agent_tick_counters()
    completed_trip_ids: set[int] = set()
    skip_slots = {int(slot_id) for slot_id in (skip_slot_ids or set())}
    remaining_budget = {
        int(link_id): max(0, int(count))
        for link_id, count in dict(movement_budget_by_link_id).items()
    }
    remaining_completion_budget = {
        int(link_id): max(0, int(count))
        for link_id, count in dict(completion_budget_by_link_id or {}).items()
    }
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

    def release_slot(slot_id: int) -> None:
        nonlocal free_count, alive_count
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

    for slot_id in [idx for idx, alive in enumerate(alive_mask.tolist()) if bool(alive)]:
        if int(slot_id) in skip_slots:
            continue
        slot_memory = plugin_memory.get(int(slot_id), {})
        path = tuple(int(x) for x in tuple(slot_memory.get("route_path", ())))
        ptr = int(route_ptr[slot_id])
        if not path:
            release_slot(int(slot_id))
            continue
        current_link_id = int(current_link[slot_id])
        if ptr >= len(path) - 1:
            if remaining_completion_budget.get(current_link_id, 0) <= 0:
                counters["active_agent_sink_wait_this_tick"] += 1
                continue
            remaining_completion_budget[current_link_id] = (
                remaining_completion_budget[current_link_id] - 1
            )
            release_slot(int(slot_id))
            continue
        if remaining_budget.get(current_link_id, 0) <= 0:
            continue
        remaining_budget[current_link_id] = remaining_budget[current_link_id] - 1
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


def _advance_pool_along_cached_routes_rust(
    pool: ActiveAgentPool,
    *,
    movement_budget_by_link_id: Mapping[int, int],
    completion_budget_by_link_id: Mapping[int, int] | None = None,
    skip_slot_ids: set[int] | None = None,
) -> tuple[ActiveAgentPool, dict[str, int], set[int]]:
    counters = _agent_tick_counters()
    skip_slots = {int(slot_id) for slot_id in (skip_slot_ids or set())}
    alive_mask = np.asarray(pool.alive_mask, dtype=np.bool_)
    slot_ids = tuple(int(idx) for idx, alive in enumerate(alive_mask.tolist()) if bool(alive))
    route_offsets: list[int] = [0]
    route_link_ids: list[int] = []
    plugin_memory = dict(pool.plugin_memory)
    for slot_id in slot_ids:
        slot_memory = plugin_memory.get(int(slot_id), {})
        path = tuple(int(x) for x in tuple(slot_memory.get("route_path", ())))
        route_link_ids.extend(path)
        route_offsets.append(len(route_link_ids))

    movement_items = tuple(
        (int(link_id), max(0, int(count)))
        for link_id, count in sorted(dict(movement_budget_by_link_id).items())
    )
    completion_items = tuple(
        (int(link_id), max(0, int(count)))
        for link_id, count in sorted(dict(completion_budget_by_link_id or {}).items())
    )
    plan = advance_active_agents_rust(
        slot_ids=slot_ids,
        trip_ids=tuple(int(pool.trip_id[slot_id]) for slot_id in slot_ids),
        current_link_ids=tuple(int(pool.current_link_id[slot_id]) for slot_id in slot_ids),
        route_ptrs=tuple(int(pool.remaining_route_ptr[slot_id]) for slot_id in slot_ids),
        cooldown_ticks=tuple(int(pool.reroute_cooldown_ticks[slot_id]) for slot_id in slot_ids),
        route_offsets=tuple(route_offsets),
        route_link_ids=tuple(route_link_ids),
        movement_budget_link_ids=tuple(link_id for link_id, _count in movement_items),
        movement_budget_counts=tuple(count for _link_id, count in movement_items),
        completion_budget_link_ids=tuple(link_id for link_id, _count in completion_items),
        completion_budget_counts=tuple(count for _link_id, count in completion_items),
        skip_slot_ids=tuple(sorted(skip_slots)),
    )
    _validate_agent_action_plan(plan, slot_count=len(slot_ids))

    free_stack = np.asarray(pool.free_slot_stack, dtype=np.int32).copy()
    alive_mask_next = alive_mask.copy()
    citizen = np.asarray(pool.citizen_id, dtype=np.int32).copy()
    trip = np.asarray(pool.trip_id, dtype=np.int32).copy()
    current_link = np.asarray(pool.current_link_id, dtype=np.int32).copy()
    progress = np.asarray(pool.progress_01, dtype=np.float32).copy()
    route_ptr = np.asarray(pool.remaining_route_ptr, dtype=np.int32).copy()
    dest = np.asarray(pool.dest_node_id, dtype=np.int32).copy()
    behavior = np.asarray(pool.behavior_profile_id, dtype=np.int32).copy()
    cooldown = np.asarray(pool.reroute_cooldown_ticks, dtype=np.int32).copy()
    free_count = int(pool.free_slot_count)
    alive_count = int(pool.alive_count)

    next_current = np.asarray(plan["next_current_link_ids"], dtype=np.int32)
    next_ptr = np.asarray(plan["next_route_ptrs"], dtype=np.int32)
    next_cooldown = np.asarray(plan["next_cooldown_ticks"], dtype=np.int32)
    for pos, slot_id in enumerate(slot_ids):
        current_link[slot_id] = next_current[pos]
        route_ptr[slot_id] = next_ptr[pos]
        cooldown[slot_id] = next_cooldown[pos]

    moved_slot_ids = tuple(int(slot_id) for slot_id in plan["moved_slot_ids"].tolist())
    for slot_id in moved_slot_ids:
        progress[slot_id] = 0.0
    counters["active_agent_moved_this_tick"] = len(moved_slot_ids)
    sink_wait_slot_ids = tuple(
        int(slot_id) for slot_id in plan["sink_wait_slot_ids"].tolist()
    )
    counters["active_agent_sink_wait_this_tick"] = len(sink_wait_slot_ids)

    completed_trip_ids = {
        int(trip_id) for trip_id in np.asarray(plan["completed_trip_ids"], dtype=np.int32).tolist()
    }
    released_slot_ids = tuple(
        int(slot_id) for slot_id in plan["released_slot_ids"].tolist()
    )
    for slot_id in released_slot_ids:
        if not 0 <= slot_id < pool.capacity:
            raise RuntimeError("Rust CPU active-agent backend failed: released slot out of range")
        plugin_memory.pop(int(slot_id), None)
        alive_mask_next[slot_id] = False
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

    return (
        ActiveAgentPool.from_internal_arrays(
            capacity=pool.capacity,
            free_slot_stack=free_stack,
            free_slot_count=free_count,
            alive_mask=alive_mask_next,
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


def _validate_agent_action_plan(plan: Mapping[str, np.ndarray], *, slot_count: int) -> None:
    for key in ("next_current_link_ids", "next_route_ptrs", "next_cooldown_ticks"):
        values = np.asarray(plan[key], dtype=np.int32)
        if values.shape != (slot_count,):
            raise RuntimeError(
                f"Rust CPU active-agent backend failed: {key} length mismatch"
            )


def _movement_budget_by_link_id(state: SimulationState) -> dict[int, int]:
    road_csr = _road_csr_from_state(state)
    link_state = state.dynamic.flow_link_state
    link_id_to_index = dict(getattr(road_csr, "link_id_to_index", {}) or {})
    outflow = np.asarray(getattr(link_state, "outflow_vehicles", ()), dtype=np.float32)
    if outflow.ndim != 1 or not link_id_to_index:
        return {}
    budget: dict[int, int] = {}
    for link_id, link_index in link_id_to_index.items():
        idx = int(link_index)
        if 0 <= idx < int(outflow.shape[0]):
            budget[int(link_id)] = int(np.floor(max(0.0, float(outflow[idx])) + 1e-6))
    return budget


def _sink_discharge_budget_by_link_id(state: SimulationState) -> dict[int, int]:
    road_csr = _road_csr_from_state(state)
    link_state = state.dynamic.flow_link_state
    link_id_to_index = dict(getattr(road_csr, "link_id_to_index", {}) or {})
    effective_capacity = np.asarray(
        getattr(link_state, "effective_capacity_vehicles", ()),
        dtype=np.float32,
    )
    if effective_capacity.ndim != 1 or not link_id_to_index:
        return {}
    budget: dict[int, int] = {}
    for link_id, link_index in link_id_to_index.items():
        idx = int(link_index)
        if 0 <= idx < int(effective_capacity.shape[0]):
            budget[int(link_id)] = int(
                np.floor(max(0.0, float(effective_capacity[idx])) + 1e-6)
            )
    return budget


def _apply_runtime_reroute_policy(
    state: SimulationState,
    pool: ActiveAgentPool,
    *,
    skip_slot_ids: set[int] | None = None,
) -> tuple[ActiveAgentPool, dict[str, int]]:
    counters = _agent_tick_counters()
    trigger = _runtime_reroute_trigger(state)
    if trigger is None or pool.alive_count <= 0:
        return pool, counters
    road_csr = _road_csr_from_state(state)
    link_state = state.dynamic.flow_link_state
    if road_csr is None or not isinstance(link_state, LinkState):
        return pool, counters

    skip = {int(slot_id) for slot_id in (skip_slot_ids or set())}
    cooldown = np.asarray(pool.reroute_cooldown_ticks, dtype=np.int32).copy()
    plugin_memory = dict(pool.plugin_memory)
    changed = False

    for slot_id, alive in enumerate(np.asarray(pool.alive_mask, dtype=np.bool_).tolist()):
        if not alive or slot_id in skip:
            continue
        if int(cooldown[slot_id]) > 0:
            cooldown[slot_id] = np.int32(max(0, int(cooldown[slot_id]) - 1))
            counters["active_agent_reroute_cooldown_this_tick"] += 1
            changed = True
            continue

        memory = _slot_plugin_memory(plugin_memory, slot_id)
        current_link_id = int(pool.current_link_id[slot_id])
        path = tuple(int(link_id) for link_id in tuple(memory.get("route_path", ())))
        route_ptr = int(pool.remaining_route_ptr[slot_id])
        existing_tail = _remaining_route_tail_after_current(
            path=path,
            route_ptr=route_ptr,
            current_link_id=current_link_id,
        )
        if not existing_tail:
            continue
        selection = _build_reroute_tail_selection(
            state=state,
            road_csr=road_csr,
            link_state=link_state,
            current_link_id=current_link_id,
            destination_node_id=int(pool.dest_node_id[slot_id]),
        )
        candidate_tail = () if selection is None else selection.path
        if not candidate_tail or candidate_tail == existing_tail:
            continue

        decision = decide_reroute_vs_persist(
            profile=_route_choice_profile_for_slot(state, int(pool.behavior_profile_id[slot_id])),
            current_remaining_cost=_path_link_cost(
                road_csr=road_csr,
                link_state=link_state,
                path=existing_tail,
            ),
            candidate_remaining_cost=_path_link_cost(
                road_csr=road_csr,
                link_state=link_state,
                path=candidate_tail,
            ),
            incident_active=True,
            reroute_cooldown_ticks=0,
            routing_backend=state.config.routing_backend,
        )
        cooldown[slot_id] = np.int32(decision.next_reroute_cooldown_ticks)
        memory.update(
            {
                "last_reroute_tick": int(state.tick_index),
                "last_reroute_trigger": trigger,
                "last_reroute_reason": decision.reason.value,
                "last_reroute_improvement_ratio": float(decision.improvement_ratio),
            }
        )
        if decision.should_reroute:
            memory["route_path"] = _route_prefix_through_current(
                path=path,
                route_ptr=route_ptr,
                current_link_id=current_link_id,
            ) + candidate_tail
            memory.update(_selected_candidate_memory(selection))
            counters["active_agent_rerouted_this_tick"] += 1
        plugin_memory[int(slot_id)] = memory
        changed = True

    if not changed:
        return pool, counters
    return _replace_pool_reroute_state(pool, cooldown=cooldown, plugin_memory=plugin_memory), counters


def _runtime_reroute_trigger(state: SimulationState) -> str | None:
    if _active_events(state):
        return "incident"
    interval = max(1, int(state.config.route_refresh_interval_ticks))
    if int(state.tick_index) % interval == 0:
        return "refresh_interval"
    return None


def _slot_plugin_memory(plugin_memory: Mapping[Any, Any], slot_id: int) -> dict[str, Any]:
    raw = dict(plugin_memory).get(int(slot_id), {})
    return dict(raw) if isinstance(raw, Mapping) else {}


def _remaining_route_tail_after_current(
    *,
    path: tuple[int, ...],
    route_ptr: int,
    current_link_id: int,
) -> tuple[int, ...]:
    ptr = int(route_ptr)
    if 0 <= ptr < len(path) and int(path[ptr]) == int(current_link_id):
        return tuple(path[ptr + 1 :])
    try:
        idx = tuple(path).index(int(current_link_id))
    except ValueError:
        return ()
    return tuple(path[idx + 1 :])


def _route_prefix_through_current(
    *,
    path: tuple[int, ...],
    route_ptr: int,
    current_link_id: int,
) -> tuple[int, ...]:
    ptr = int(route_ptr)
    if 0 <= ptr < len(path) and int(path[ptr]) == int(current_link_id):
        return tuple(path[: ptr + 1])
    try:
        idx = tuple(path).index(int(current_link_id))
    except ValueError:
        return (int(current_link_id),)
    return tuple(path[: idx + 1])


def _build_reroute_tail_selection(
    *,
    state: SimulationState,
    road_csr: Any,
    link_state: LinkState,
    current_link_id: int,
    destination_node_id: int,
) -> _SelectedCandidateRoute | None:
    link_index = dict(getattr(road_csr, "link_id_to_index", {}) or {}).get(int(current_link_id))
    if link_index is None:
        return None
    if int(destination_node_id) not in dict(getattr(road_csr, "node_id_to_index", {}) or {}):
        return None
    current_link = tuple(getattr(road_csr, "links", ()))[int(link_index)]
    origin_node_id = int(current_link.dst_node_id)
    if origin_node_id == int(destination_node_id):
        return None
    candidate_set = create_route_candidate_set(
        road_csr=road_csr,
        link_state=link_state,
        od_key=(origin_node_id, int(destination_node_id)),
        origin_node_id=origin_node_id,
        destination_node_id=int(destination_node_id),
        current_tick=int(state.tick_index),
        incoming_link_id=int(current_link_id),
        max_candidates=max(1, int(state.config.route_max_candidates)),
        max_hops=max(1, int(state.config.route_max_hops)),
        routing_backend=state.config.routing_backend,
    )
    return _select_candidate_route(
        candidate_set,
        path_size_gamma=state.config.route_path_size_gamma,
        routing_backend=state.config.routing_backend,
    )


def _selected_candidate_memory(selection: _SelectedCandidateRoute) -> dict[str, Any]:
    return {
        "selected_candidate_index": selection.candidate_index,
        "selected_candidate_id": selection.candidate_id,
        "selected_candidate_count": selection.candidate_count,
        "selected_candidate_path_cost": selection.path_cost,
        "selected_candidate_path_size_factor": selection.path_size_factor,
        "selected_candidate_utility": selection.utility,
        "selected_candidate_selection_backend": selection.selection_backend,
    }


def _path_link_cost(
    *,
    road_csr: Any,
    link_state: LinkState,
    path: tuple[int, ...],
) -> float:
    link_id_to_index = dict(getattr(road_csr, "link_id_to_index", {}) or {})
    costs = np.asarray(link_state.travel_time_cost, dtype=np.float32)
    total = 0.0
    for link_id in tuple(path):
        idx = link_id_to_index.get(int(link_id))
        if idx is None or int(idx) < 0 or int(idx) >= int(costs.shape[0]):
            return float("inf")
        value = float(costs[int(idx)])
        if not np.isfinite(value) or value <= 0.0:
            return float("inf")
        total += value
    return float(total)


def _route_choice_profile_for_slot(
    state: SimulationState,
    behavior_profile_id: int,
) -> RouteChoiceProfile:
    profiles = _route_choice_profile_lookup(state)
    profile_id = int(behavior_profile_id)
    if profile_id in profiles:
        return profiles[profile_id]
    return RouteChoiceProfile(
        behavior_profile_id=profile_id,
        delay_sensitivity=1.25,
        reroute_willingness=0.65,
        persistence_bias=0.5,
        exploration_bias=0.1,
    )


def _route_choice_profile_lookup(state: SimulationState) -> dict[int, RouteChoiceProfile]:
    metadata = state.static.metadata if isinstance(state.static.metadata, Mapping) else {}
    raw_profiles = metadata.get("route_choice_profiles", metadata.get("behavior_profiles", ()))
    if isinstance(raw_profiles, Mapping) and "behavior_profile_id" in raw_profiles:
        candidates = (raw_profiles,)
    elif isinstance(raw_profiles, Mapping):
        candidates = tuple(raw_profiles.values())
    else:
        try:
            candidates = tuple(raw_profiles or ())
        except TypeError:
            candidates = (raw_profiles,)
    out: dict[int, RouteChoiceProfile] = {}
    for raw in candidates:
        profile = _coerce_route_choice_profile(raw)
        if profile is not None:
            out[int(profile.behavior_profile_id)] = profile
    return out


def _coerce_route_choice_profile(raw: Any) -> RouteChoiceProfile | None:
    if isinstance(raw, RouteChoiceProfile):
        return raw
    if isinstance(raw, Mapping):
        return RouteChoiceProfile(**dict(raw))
    attrs = {
        name: getattr(raw, name)
        for name in (
            "behavior_profile_id",
            "delay_sensitivity",
            "reroute_willingness",
            "persistence_bias",
            "exploration_bias",
        )
        if hasattr(raw, name)
    }
    if len(attrs) == 5:
        return RouteChoiceProfile(**attrs)
    return None


def _replace_pool_reroute_state(
    pool: ActiveAgentPool,
    *,
    cooldown: np.ndarray,
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
        reroute_cooldown_ticks=cooldown,
        plugin_memory=plugin_memory,
    )


def _apply_source_queue_increments(
    state: SimulationState,
    increments_by_link_id: Mapping[int, int],
) -> LinkState | None:
    link_state = state.dynamic.flow_link_state
    if not isinstance(link_state, LinkState) or not increments_by_link_id:
        return link_state
    road_csr = _road_csr_from_state(state)
    link_id_to_index = dict(getattr(road_csr, "link_id_to_index", {}) or {})
    queue = np.asarray(link_state.queue_vehicles, dtype=np.float32).copy()
    for link_id, count in sorted(dict(increments_by_link_id).items()):
        idx = link_id_to_index.get(int(link_id))
        if idx is None:
            raise ValueError("allocated route source link is missing from road_csr")
        queue[int(idx)] += np.float32(max(0, int(count)))
    return LinkState.from_internal_arrays(
        queue_vehicles=queue,
        inflow_vehicles=link_state.inflow_vehicles,
        outflow_vehicles=link_state.outflow_vehicles,
        travel_time_cost=_travel_time_cost_for_queue(link_state, queue),
        capacity_veh_per_tick=link_state.capacity_veh_per_tick,
        incident_capacity_multiplier=link_state.incident_capacity_multiplier,
        capacity_violation_flags=link_state.capacity_violation_flags,
        metadata=link_state.metadata,
    )


def _travel_time_cost_for_queue(link_state: LinkState, queue_vehicles: np.ndarray) -> np.ndarray:
    raw_base = link_state.metadata.get("free_flow_travel_time_cost")
    if raw_base is None:
        base = np.asarray(link_state.travel_time_cost, dtype=np.float32)
    else:
        base = np.asarray(raw_base, dtype=np.float32)
    if base.ndim == 0:
        base = np.full((link_state.link_count,), float(base), dtype=np.float32)
    base = np.maximum(base, np.float32(1e-3))
    queue = np.maximum(np.asarray(queue_vehicles, dtype=np.float32), np.float32(0.0))
    capacity = np.maximum(
        np.asarray(link_state.effective_capacity_vehicles, dtype=np.float32),
        np.float32(1e-3),
    )
    return base * (np.float32(1.0) + (queue / (capacity + np.float32(1e-3))))


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
    selection = _select_candidate_route(candidate_set)
    return () if selection is None else selection.path


def _select_candidate_route(
    candidate_set: RouteCandidateSet | None,
    *,
    path_size_gamma: float = 0.0,
    routing_backend: str = "baseline",
) -> _SelectedCandidateRoute | None:
    if candidate_set is None or not candidate_set.candidate_paths:
        return None
    candidate_paths = tuple(tuple(int(x) for x in path) for path in candidate_set.candidate_paths)
    viable_indices = tuple(index for index, path in enumerate(candidate_paths) if path)
    if not viable_indices:
        return None
    metadata = candidate_set.metadata if isinstance(candidate_set.metadata, Mapping) else {}
    costs = tuple(float(x) for x in tuple(metadata.get("candidate_path_costs", ()) or ()))
    path_sizes = tuple(
        float(x) for x in tuple(metadata.get("candidate_path_size_factors", ()) or ())
    )
    candidate_ids = tuple(int(x) for x in candidate_set.candidate_ids)
    selected_index, selected_utility, selection_backend = _select_candidate_route_index(
        candidate_ids=candidate_ids,
        candidate_paths=candidate_paths,
        viable_indices=viable_indices,
        costs=costs,
        path_sizes=path_sizes,
        path_size_gamma=path_size_gamma,
        routing_backend=routing_backend,
    )
    if selected_index < 0:
        return None
    path = candidate_paths[selected_index]
    path_cost = costs[selected_index] if selected_index < len(costs) else 0.0
    path_size_factor = path_sizes[selected_index] if selected_index < len(path_sizes) else 1.0
    return _SelectedCandidateRoute(
        candidate_index=selected_index,
        candidate_id=(
            candidate_ids[selected_index] if selected_index < len(candidate_ids) else selected_index
        ),
        candidate_count=len(candidate_paths),
        path=path,
        path_cost=path_cost,
        path_size_factor=path_size_factor,
        utility=selected_utility,
        selection_backend=selection_backend,
    )


def _select_candidate_route_index(
    *,
    candidate_ids: tuple[int, ...],
    candidate_paths: tuple[tuple[int, ...], ...],
    viable_indices: tuple[int, ...],
    costs: tuple[float, ...],
    path_sizes: tuple[float, ...],
    path_size_gamma: float,
    routing_backend: str,
) -> tuple[int, float, str]:
    if routing_backend == "auto" and not rust_routing_backend_available():
        selected_index, utility = _select_candidate_route_index_host(
            candidate_ids=candidate_ids,
            candidate_paths=candidate_paths,
            viable_indices=viable_indices,
            costs=costs,
            path_sizes=path_sizes,
            path_size_gamma=path_size_gamma,
        )
        return selected_index, utility, "python_host_candidate_selection"
    if routing_backend in {"rust_cpu", "auto"}:
        try:
            selected_index, utility = select_route_candidate_index_rust(
                candidate_ids=candidate_ids,
                candidate_paths=candidate_paths,
                candidate_path_costs=costs,
                candidate_path_size_factors=path_sizes,
                path_size_gamma=path_size_gamma,
            )
            if selected_index < 0:
                return -1, 0.0, "rust_cpu_candidate_selection"
            if selected_index not in viable_indices:
                raise RuntimeError(
                    "Rust CPU routing backend failed: selected candidate index is not viable"
                )
            return int(selected_index), float(utility), "rust_cpu_candidate_selection"
        except RuntimeError:
            if routing_backend == "rust_cpu":
                raise
    selected_index, utility = _select_candidate_route_index_host(
        candidate_ids=candidate_ids,
        candidate_paths=candidate_paths,
        viable_indices=viable_indices,
        costs=costs,
        path_sizes=path_sizes,
        path_size_gamma=path_size_gamma,
    )
    return selected_index, utility, "python_host_candidate_selection"


def _select_candidate_route_index_host(
    *,
    candidate_ids: tuple[int, ...],
    candidate_paths: tuple[tuple[int, ...], ...],
    viable_indices: tuple[int, ...],
    costs: tuple[float, ...],
    path_sizes: tuple[float, ...],
    path_size_gamma: float,
) -> tuple[int, float]:
    if len(costs) >= len(candidate_paths):
        utilities = tuple(
            _candidate_path_utility(
                cost=costs[idx],
                path_size_factor=path_sizes[idx] if idx < len(path_sizes) else 1.0,
                path_size_gamma=path_size_gamma,
            )
            for idx in range(len(candidate_paths))
        )
        selected_index = max(
            viable_indices,
            key=lambda idx: (
                utilities[idx],
                -(candidate_ids[idx] if idx < len(candidate_ids) else idx),
                tuple(-link_id for link_id in candidate_paths[idx]),
            ),
        )
        return selected_index, utilities[selected_index]
    return viable_indices[0], 0.0


def _candidate_path_utility(
    *,
    cost: float,
    path_size_factor: float,
    path_size_gamma: float,
) -> float:
    cost_f = float(cost)
    if not isfinite(cost_f):
        return float("-inf")
    path_size_raw = float(path_size_factor)
    path_size = path_size_raw if isfinite(path_size_raw) and path_size_raw > 0.0 else 1.0e-12
    return -cost_f + max(0.0, float(path_size_gamma)) * log(path_size)


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
