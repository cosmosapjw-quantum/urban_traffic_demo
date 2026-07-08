"""OD route candidate set state and refresh policy helpers (T062)."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from metroflow.routing.dynamic_potential import (
    build_greedy_route_candidate,
    compute_dynamic_potential_state,
)

__all__ = [
    "RouteCandidateSet",
    "RouteCandidateRefreshPolicy",
    "create_route_candidate_set",
    "build_route_candidate_set",
    "refresh_od_route_candidate_set",
    "should_refresh_route_candidate_set",
]


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

    T062 intentionally emits a single baseline candidate path (`candidate_id=0`)
    while preserving the RouteCandidateSet container and refresh policy boundary
    for later multi-arm US3 candidate generation (`T064+`).
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

    if max_candidates > 1:
        raise ValueError("T062 supports only a single baseline candidate; use max_candidates=1")

    path = ()
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
        potential_state = compute_dynamic_potential_state(
            network=road_csr,
            link_state=link_state,
            destination_node_id=destination_node_id,
            routing_backend=routing_backend,
            cache=potential_cache,
            cache_key=effective_cache_key,
            stats=stats,
        )
        potential_metadata = dict(potential_state.metadata)
        path = build_greedy_route_candidate(
            network=road_csr,
            potential_state=potential_state,
            origin_node_id=origin_node_id,
            incoming_link_id=incoming_link_id,
            max_hops=max_hops,
            routing_backend=routing_backend,
        )

    candidate_ids: tuple[int, ...]
    candidate_paths: tuple[tuple[int, ...], ...]
    if path:
        candidate_ids = (0,)
        candidate_paths = (tuple(int(x) for x in path),)
    else:
        candidate_ids = ()
        candidate_paths = ()

    candidate_set = RouteCandidateSet(
        od_key=od_key,
        candidate_ids=candidate_ids,
        candidate_paths=candidate_paths,
        last_refresh_tick=current_tick,
        metadata={
            "origin_node_id": origin_node_id,
            "destination_node_id": destination_node_id,
            "max_candidates_requested": max_candidates,
            "max_hops": max_hops,
            "candidate_generation_mode": "baseline_greedy_single",
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
