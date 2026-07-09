"""OD route candidate set state and refresh policy helpers (T062)."""

from __future__ import annotations

from dataclasses import dataclass, field
from heapq import heappop, heappush
from math import isfinite
from time import perf_counter
from typing import Any

from metroflow.backends.rust_cpu import (
    compute_route_candidate_metadata_rust,
    compute_ranked_route_candidates_rust,
    rust_routing_backend_available,
)
from metroflow.routing.dynamic_potential import (
    build_greedy_route_candidate,
    compute_dynamic_potential_state,
    score_legal_next_links,
)

__all__ = [
    "RouteCandidateSet",
    "RouteCandidateRefreshPolicy",
    "create_route_candidate_set",
    "build_route_candidate_set",
    "refresh_od_route_candidate_set",
    "should_refresh_route_candidate_set",
]

_INF_COST = 1e12


@dataclass(slots=True)
class RouteCandidateSet:
    """Candidate routes for one OD key (data-model aligned)."""

    od_key: tuple[Any, Any]
    candidate_ids: tuple[int, ...]
    candidate_paths: tuple[tuple[int, ...], ...]
    last_refresh_tick: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.od_key = tuple(self.od_key)  # type: ignore[assignment]
        if len(self.od_key) != 2:
            raise ValueError("od_key must contain exactly (origin, destination)")
        self.candidate_ids = tuple(int(x) for x in self.candidate_ids)
        self.candidate_paths = tuple(tuple(int(link_id) for link_id in path) for path in self.candidate_paths)
        self.last_refresh_tick = int(self.last_refresh_tick)
        if self.last_refresh_tick < 0:
            raise ValueError("last_refresh_tick must be >= 0")
        if len(self.candidate_ids) != len(self.candidate_paths):
            raise ValueError("candidate_ids and candidate_paths must have the same length")
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("candidate_ids must be unique")
        if any(candidate_id < 0 for candidate_id in self.candidate_ids):
            raise ValueError("candidate_ids must be non-negative")
        for path in self.candidate_paths:
            if any(link_id < 0 for link_id in path):
                raise ValueError("candidate_paths must contain non-negative link ids")
        if not isinstance(self.metadata, dict):
            self.metadata = dict(self.metadata)


@dataclass(slots=True)
class RouteCandidateRefreshPolicy:
    """Minimal refresh policy for OD candidate sets (US3 foundation)."""

    refresh_interval_ticks: int = 8
    force_refresh_on_incident: bool = True
    max_candidates: int = 1
    max_hops: int = 64

    def __post_init__(self) -> None:
        self.refresh_interval_ticks = int(self.refresh_interval_ticks)
        self.force_refresh_on_incident = bool(self.force_refresh_on_incident)
        self.max_candidates = int(self.max_candidates)
        self.max_hops = int(self.max_hops)
        if self.refresh_interval_ticks < 1:
            raise ValueError("refresh_interval_ticks must be >= 1")
        if self.max_candidates < 1:
            raise ValueError("max_candidates must be >= 1")
        if self.max_hops < 1:
            raise ValueError("max_hops must be >= 1")


def should_refresh_route_candidate_set(
    candidate_set: RouteCandidateSet | None,
    *,
    current_tick: int,
    incident_active: bool = False,
    force_refresh: bool = False,
    policy: RouteCandidateRefreshPolicy | None = None,
) -> bool:
    """Return whether an OD candidate set should be refreshed this tick."""

    if force_refresh or candidate_set is None:
        return True
    refresh_policy = policy or RouteCandidateRefreshPolicy()
    if incident_active and refresh_policy.force_refresh_on_incident:
        return True
    tick = int(current_tick)
    if tick < int(candidate_set.last_refresh_tick):
        return True
    return (tick - int(candidate_set.last_refresh_tick)) >= refresh_policy.refresh_interval_ticks


def create_route_candidate_set(
    *,
    road_csr,
    link_state,
    od_key: tuple[Any, Any],
    origin_node_id: int,
    destination_node_id: int,
    current_tick: int,
    incoming_link_id: int | None = None,
    max_candidates: int = 1,
    max_hops: int = 64,
    routing_backend: str = "baseline",
    potential_cache: dict[Any, Any] | None = None,
    cache_key: Any | None = None,
    stats: dict[str, Any] | None = None,
) -> RouteCandidateSet:
    """Build a deterministic baseline candidate set from dynamic potential.

    Candidate generation is deterministic. `max_candidates=1` preserves the
    original greedy baseline path; larger values enumerate ranked loopless paths
    using the dynamic-potential cost-to-go field as a host-side heuristic.
    """

    return build_route_candidate_set(
        road_csr=road_csr,
        link_state=link_state,
        od_key=od_key,
        origin_node_id=origin_node_id,
        destination_node_id=destination_node_id,
        current_tick=current_tick,
        incoming_link_id=incoming_link_id,
        max_candidates=max_candidates,
        max_hops=max_hops,
        routing_backend=routing_backend,
        potential_cache=potential_cache,
        cache_key=cache_key,
        stats=stats,
    )


def build_route_candidate_set(**kwargs) -> RouteCandidateSet:
    """Alias for `create_route_candidate_set` implementation."""

    road_csr = kwargs["road_csr"]
    link_state = kwargs["link_state"]
    od_key = tuple(kwargs["od_key"])
    origin_node_id = int(kwargs["origin_node_id"])
    destination_node_id = int(kwargs["destination_node_id"])
    current_tick = int(kwargs["current_tick"])
    incoming_link_id = kwargs.get("incoming_link_id")
    max_candidates = int(kwargs.get("max_candidates", 1))
    max_hops = int(kwargs.get("max_hops", 64))
    routing_backend = str(kwargs.get("routing_backend", "baseline"))
    potential_cache = kwargs.get("potential_cache")
    cache_key = kwargs.get("cache_key")
    stats = kwargs.get("stats")
    started = perf_counter()

    if max_candidates < 1:
        raise ValueError("max_candidates must be >= 1")

    paths: tuple[tuple[int, ...], ...] = ()
    candidate_enumeration_backend = "backend_greedy_route_candidate"
    potential_state = None
    potential_metadata: dict[str, Any] = {}
    if max_candidates >= 1:
        effective_cache_key = cache_key
        if effective_cache_key is None:
            effective_cache_key = (
                "route_candidate_set",
                int(destination_node_id),
                id(road_csr),
                id(link_state),
            )
        potential_started = perf_counter()
        potential_state = compute_dynamic_potential_state(
            network=road_csr,
            link_state=link_state,
            destination_node_id=destination_node_id,
            routing_backend=routing_backend,
            cache=potential_cache,
            cache_key=effective_cache_key,
            stats=stats,
        )
        _add_stats_seconds(
            stats,
            "route_candidate_potential_seconds_total",
            max(perf_counter() - potential_started, 0.0),
        )
        potential_metadata = dict(potential_state.metadata)
        path_started = perf_counter()
        if max_candidates == 1:
            path = build_greedy_route_candidate(
                network=road_csr,
                potential_state=potential_state,
                origin_node_id=origin_node_id,
                incoming_link_id=incoming_link_id,
                max_hops=max_hops,
                routing_backend=routing_backend,
            )
            paths = (tuple(int(x) for x in path),) if path else ()
        else:
            paths, candidate_enumeration_backend = _build_ranked_route_candidate_paths(
                road_csr=road_csr,
                potential_state=potential_state,
                origin_node_id=origin_node_id,
                destination_node_id=destination_node_id,
                incoming_link_id=incoming_link_id,
                max_candidates=max_candidates,
                max_hops=max_hops,
                routing_backend=routing_backend,
            )
        _add_stats_seconds(
            stats,
            "route_candidate_path_build_seconds_total",
            max(perf_counter() - path_started, 0.0),
        )

    candidate_ids: tuple[int, ...]
    candidate_paths: tuple[tuple[int, ...], ...]
    if paths:
        candidate_ids = tuple(range(len(paths)))
        candidate_paths = paths
    else:
        candidate_ids = ()
        candidate_paths = ()
    candidate_metadata_backend = "python_host_candidate_metadata"
    if potential_state is not None:
        metadata_started = perf_counter()
        (
            candidate_path_costs,
            candidate_path_size_factors,
            candidate_metadata_backend,
        ) = _candidate_path_metadata(
            road_csr=road_csr,
            candidate_paths=candidate_paths,
            link_travel_time_cost=potential_state.link_travel_time_cost,
            routing_backend=routing_backend,
        )
        _add_stats_seconds(
            stats,
            "route_candidate_metadata_seconds_total",
            max(perf_counter() - metadata_started, 0.0),
        )
    else:
        candidate_path_costs = ()
        candidate_path_size_factors = ()

    candidate_set = RouteCandidateSet(
        od_key=od_key,
        candidate_ids=candidate_ids,
        candidate_paths=candidate_paths,
        last_refresh_tick=current_tick,
        metadata={
            "origin_node_id": origin_node_id,
            "destination_node_id": destination_node_id,
            "max_candidates_requested": max_candidates,
            "max_candidates_returned": len(candidate_paths),
            "max_hops": max_hops,
            "candidate_path_costs": candidate_path_costs,
            "candidate_path_size_factors": candidate_path_size_factors,
            "candidate_metadata_backend": candidate_metadata_backend,
            "candidate_generation_mode": (
                "baseline_greedy_single" if max_candidates == 1 else "baseline_ranked_k"
            ),
            "candidate_enumeration_backend": candidate_enumeration_backend,
            "routing_backend": str(potential_metadata.get("routing_backend", routing_backend)),
            "routing_backend_requested": str(
                potential_metadata.get("routing_backend_requested", routing_backend)
            ),
            **(
                {
                    "routing_backend_fallback": str(
                        potential_metadata["routing_backend_fallback"]
                    )
                }
                if "routing_backend_fallback" in potential_metadata
                else {}
            ),
        },
    )
    if stats is not None:
        stats["route_candidate_refresh_total"] = int(stats.get("route_candidate_refresh_total", 0)) + 1
        stats["route_candidate_refresh_seconds_total"] = float(
            stats.get("route_candidate_refresh_seconds_total", 0.0)
        ) + max(perf_counter() - started, 0.0)
    return candidate_set


def _add_stats_seconds(
    stats: dict[str, Any] | None,
    key: str,
    seconds: float,
) -> None:
    if stats is None:
        return
    stats[str(key)] = float(stats.get(str(key), 0.0)) + max(float(seconds), 0.0)


def _build_ranked_route_candidate_paths(
    *,
    road_csr,
    potential_state,
    origin_node_id: int,
    destination_node_id: int,
    incoming_link_id: int | None,
    max_candidates: int,
    max_hops: int,
    routing_backend: str,
) -> tuple[tuple[tuple[int, ...], ...], str]:
    if routing_backend == "auto" and not rust_routing_backend_available():
        return (
            _build_ranked_route_candidate_paths_host(
                road_csr=road_csr,
                potential_state=potential_state,
                origin_node_id=origin_node_id,
                destination_node_id=destination_node_id,
                incoming_link_id=incoming_link_id,
                max_candidates=max_candidates,
                max_hops=max_hops,
                routing_backend=routing_backend,
            ),
            "python_host_ranked_k",
        )
    if routing_backend in {"rust_cpu", "auto"}:
        try:
            return (
                _build_ranked_route_candidate_paths_rust(
                    road_csr=road_csr,
                    potential_state=potential_state,
                    origin_node_id=origin_node_id,
                    destination_node_id=destination_node_id,
                    incoming_link_id=incoming_link_id,
                    max_candidates=max_candidates,
                    max_hops=max_hops,
                ),
                "rust_cpu_ranked_k",
            )
        except RuntimeError:
            if routing_backend == "rust_cpu":
                raise
            return (
                _build_ranked_route_candidate_paths_host(
                    road_csr=road_csr,
                    potential_state=potential_state,
                    origin_node_id=origin_node_id,
                    destination_node_id=destination_node_id,
                    incoming_link_id=incoming_link_id,
                    max_candidates=max_candidates,
                    max_hops=max_hops,
                    routing_backend=routing_backend,
                ),
                "python_host_ranked_k",
            )
    return (
        _build_ranked_route_candidate_paths_host(
            road_csr=road_csr,
            potential_state=potential_state,
            origin_node_id=origin_node_id,
            destination_node_id=destination_node_id,
            incoming_link_id=incoming_link_id,
            max_candidates=max_candidates,
            max_hops=max_hops,
            routing_backend=routing_backend,
        ),
        "python_host_ranked_k",
    )


def _build_ranked_route_candidate_paths_rust(
    *,
    road_csr,
    potential_state,
    origin_node_id: int,
    destination_node_id: int,
    incoming_link_id: int | None,
    max_candidates: int,
    max_hops: int,
) -> tuple[tuple[int, ...], ...]:
    origin_node_index = int(road_csr.node_id_to_index[int(origin_node_id)])
    destination_node_index = int(road_csr.node_id_to_index[int(destination_node_id)])
    incoming_link_index = -1
    if incoming_link_id is not None:
        maybe_index = road_csr.link_id_to_index.get(int(incoming_link_id))
        if maybe_index is None:
            return ()
        incoming_link_index = int(maybe_index)
    return compute_ranked_route_candidates_rust(
        node_count=road_csr.node_count,
        link_ids=road_csr.link_ids,
        link_dst_node_index=road_csr.link_dst_node_index,
        outgoing_indptr=road_csr.outgoing_indptr,
        outgoing_link_indices=road_csr.outgoing_link_indices,
        turn_from_link_index=road_csr.turn_from_link_index,
        turn_to_link_index=road_csr.turn_to_link_index,
        turn_is_forbidden=road_csr.turn_is_forbidden,
        node_cost_to_go=potential_state.node_cost_to_go,
        link_travel_time_cost=potential_state.link_travel_time_cost,
        blocked_link_mask=potential_state.blocked_link_mask,
        origin_node_index=origin_node_index,
        destination_node_index=destination_node_index,
        incoming_link_index=incoming_link_index,
        max_hops=max_hops,
        max_candidates=max_candidates,
    )


def _build_ranked_route_candidate_paths_host(
    *,
    road_csr,
    potential_state,
    origin_node_id: int,
    destination_node_id: int,
    incoming_link_id: int | None,
    max_candidates: int,
    max_hops: int,
    routing_backend: str,
) -> tuple[tuple[int, ...], ...]:
    if int(origin_node_id) == int(destination_node_id):
        return ()

    link_cost = potential_state.link_travel_time_cost
    node_cost = potential_state.node_cost_to_go
    paths: list[tuple[int, ...]] = []
    seen_paths: set[tuple[int, ...]] = set()
    heap: list[tuple[float, float, int, tuple[int, ...], int, int | None, tuple[int, ...]]] = []
    serial = 0
    heappush(
        heap,
        (
            0.0,
            0.0,
            serial,
            (),
            int(origin_node_id),
            None if incoming_link_id is None else int(incoming_link_id),
            (int(origin_node_id),),
        ),
    )

    max_expansions = max(max_candidates * max(16, int(road_csr.link_count) * 4), 1)
    expansions = 0
    while heap and len(paths) < int(max_candidates) and expansions < max_expansions:
        _estimated_cost, path_cost, _serial, path, current_node_id, last_link_id, visited = heappop(heap)
        expansions += 1
        if current_node_id == int(destination_node_id) and path:
            if path not in seen_paths:
                seen_paths.add(path)
                paths.append(path)
            continue
        if len(path) >= int(max_hops):
            continue

        scores = score_legal_next_links(
            road_csr,
            potential_state,
            current_node_id=current_node_id,
            incoming_link_id=last_link_id,
            routing_backend=routing_backend,
        )
        for link_id in scores.candidate_link_ids:
            link_index = int(road_csr.link_id_to_index[int(link_id)])
            link = road_csr.links[link_index]
            next_node_id = int(link.dst_node_id)
            if next_node_id in visited:
                continue
            step_cost = float(link_cost[link_index])
            if not isfinite(step_cost) or step_cost >= (_INF_COST * 0.5):
                continue
            node_index = int(road_csr.node_id_to_index[next_node_id])
            tail_cost = 0.0 if next_node_id == int(destination_node_id) else float(node_cost[node_index])
            if not isfinite(tail_cost) or tail_cost >= (_INF_COST * 0.5):
                continue
            next_path = path + (int(link_id),)
            next_path_cost = path_cost + step_cost
            serial += 1
            heappush(
                heap,
                (
                    next_path_cost + tail_cost,
                    next_path_cost,
                    serial,
                    next_path,
                    next_node_id,
                    int(link_id),
                    visited + (next_node_id,),
                ),
            )

    return tuple(paths)


def _candidate_path_metadata(
    *,
    road_csr,
    candidate_paths: tuple[tuple[int, ...], ...],
    link_travel_time_cost,
    routing_backend: str,
) -> tuple[tuple[float, ...], tuple[float, ...], str]:
    if routing_backend == "auto" and not rust_routing_backend_available():
        return (
            _candidate_path_costs(
                road_csr=road_csr,
                candidate_paths=candidate_paths,
                link_travel_time_cost=link_travel_time_cost,
            ),
            _candidate_path_size_factors(
                road_csr=road_csr,
                candidate_paths=candidate_paths,
            ),
            "python_host_candidate_metadata",
        )
    if routing_backend in {"rust_cpu", "auto"}:
        try:
            costs, path_size_factors = compute_route_candidate_metadata_rust(
                link_ids=road_csr.link_ids,
                link_length_m=tuple(float(link.length_m) for link in road_csr.links),
                link_travel_time_cost=link_travel_time_cost,
                candidate_paths=candidate_paths,
            )
            return costs, path_size_factors, "rust_cpu_candidate_metadata"
        except RuntimeError:
            if routing_backend == "rust_cpu":
                raise
    return (
        _candidate_path_costs(
            road_csr=road_csr,
            candidate_paths=candidate_paths,
            link_travel_time_cost=link_travel_time_cost,
        ),
        _candidate_path_size_factors(
            road_csr=road_csr,
            candidate_paths=candidate_paths,
        ),
        "python_host_candidate_metadata",
    )


def _candidate_path_costs(
    *,
    road_csr,
    candidate_paths: tuple[tuple[int, ...], ...],
    link_travel_time_cost,
) -> tuple[float, ...]:
    costs: list[float] = []
    for path in candidate_paths:
        cost = 0.0
        for link_id in path:
            link_index = int(road_csr.link_id_to_index[int(link_id)])
            cost += float(link_travel_time_cost[link_index])
        costs.append(float(cost))
    return tuple(costs)


def _candidate_path_size_factors(
    *,
    road_csr,
    candidate_paths: tuple[tuple[int, ...], ...],
) -> tuple[float, ...]:
    usage_count: dict[int, int] = {}
    for path in candidate_paths:
        for link_id in path:
            link_id_i = int(link_id)
            usage_count[link_id_i] = usage_count.get(link_id_i, 0) + 1

    factors: list[float] = []
    for path in candidate_paths:
        lengths = tuple(
            max(1.0e-6, float(road_csr.links[int(road_csr.link_id_to_index[int(link_id)])].length_m))
            for link_id in path
        )
        total_length = sum(lengths)
        if total_length <= 0.0:
            factors.append(1.0)
            continue
        factor = 0.0
        for link_id, length_m in zip(path, lengths, strict=True):
            factor += (length_m / total_length) * (1.0 / max(usage_count[int(link_id)], 1))
        factors.append(max(float(factor), 1.0e-12))
    return tuple(factors)


def refresh_od_route_candidate_set(
    existing: RouteCandidateSet | None,
    *,
    road_csr,
    link_state,
    od_key: tuple[Any, Any],
    origin_node_id: int,
    destination_node_id: int,
    current_tick: int,
    incoming_link_id: int | None = None,
    incident_active: bool = False,
    force_refresh: bool = False,
    policy: RouteCandidateRefreshPolicy | None = None,
    routing_backend: str = "baseline",
    potential_cache: dict[Any, Any] | None = None,
    cache_key: Any | None = None,
    stats: dict[str, Any] | None = None,
) -> RouteCandidateSet:
    """Refresh an OD candidate set if policy requires, else return existing."""

    refresh_policy = policy or RouteCandidateRefreshPolicy()
    od_key_t = tuple(od_key)
    if existing is not None and tuple(existing.od_key) != od_key_t:
        existing = None
    elif existing is not None:
        existing_origin = int((existing.metadata or {}).get("origin_node_id", origin_node_id))
        existing_dest = int((existing.metadata or {}).get("destination_node_id", destination_node_id))
        if existing_origin != int(origin_node_id) or existing_dest != int(destination_node_id):
            existing = None

    if not should_refresh_route_candidate_set(
        existing,
        current_tick=current_tick,
        incident_active=incident_active,
        force_refresh=force_refresh,
        policy=refresh_policy,
    ):
        if stats is not None:
            stats["route_candidate_reuse_total"] = int(stats.get("route_candidate_reuse_total", 0)) + 1
        return existing  # type: ignore[return-value]

    return create_route_candidate_set(
        road_csr=road_csr,
        link_state=link_state,
        od_key=od_key_t,
        origin_node_id=origin_node_id,
        destination_node_id=destination_node_id,
        current_tick=current_tick,
        incoming_link_id=incoming_link_id,
        max_candidates=refresh_policy.max_candidates,
        max_hops=refresh_policy.max_hops,
        routing_backend=routing_backend,
        potential_cache=potential_cache,
        cache_key=cache_key,
        stats=stats,
    )
