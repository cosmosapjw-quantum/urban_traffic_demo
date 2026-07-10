"""Congestion-aware dynamic-potential baseline routing helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from heapq import heappop, heappush
from time import perf_counter
from typing import Any, Literal

import numpy as np

from metroflow.backends.rust_cpu import (
    compute_dynamic_potential_node_costs_rust,
    compute_greedy_route_candidate_rust,
    compute_next_link_action_costs_rust,
    rust_routing_backend_available,
)
from metroflow.city.graph import RoadNetworkCSR
from metroflow.flow.state import LinkState

__all__ = [
    "DynamicPotentialState",
    "BaselineNextLinkScores",
    "RoutingBackend",
    "ROUTING_BACKENDS",
    "compute_dynamic_potential_state",
    "compute_next_link_action_costs_core",
    "score_legal_next_links",
    "build_greedy_route_candidate",
]

Array = np.ndarray
RoutingBackend = Literal["baseline", "rust_cpu", "auto"]
ROUTING_BACKENDS = ("baseline", "rust_cpu", "auto")
_INF_COST = 1e12
_TURN_SUCCESSOR_CACHE: dict[
    tuple[int, int, int],
    tuple[dict[int, tuple[int, ...]], dict[int, tuple[int, ...]]],
] = {}
_OUTGOING_LINK_LOOKUP_CACHE: dict[tuple[int, int, int], tuple[tuple[int, ...], ...]] = {}
_STATIC_BLOCKABLE_MASK_CACHE: dict[tuple[int, int], np.ndarray] = {}
_REVERSE_GRAPH_CACHE: dict[tuple[int, int, int], tuple[np.ndarray, np.ndarray, np.ndarray]] = {}


@dataclass(slots=True)
class DynamicPotentialState:
    """Destination-anchored node cost-to-go field for baseline routing."""

    destination_node_id: int
    destination_node_index: int
    node_cost_to_go: Array
    link_travel_time_cost: Array
    blocked_link_mask: Array
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.destination_node_id = int(self.destination_node_id)
        self.destination_node_index = int(self.destination_node_index)
        self.node_cost_to_go = np.asarray(self.node_cost_to_go, dtype=np.float32)
        self.link_travel_time_cost = np.asarray(self.link_travel_time_cost, dtype=np.float32)
        self.blocked_link_mask = np.asarray(self.blocked_link_mask, dtype=np.bool_)
        if not isinstance(self.metadata, dict):
            self.metadata = dict(self.metadata)
        if self.node_cost_to_go.ndim != 1:
            raise ValueError("node_cost_to_go must be 1-D")
        if self.link_travel_time_cost.ndim != 1 or self.blocked_link_mask.ndim != 1:
            raise ValueError("link arrays must be 1-D")
        if self.link_travel_time_cost.shape != self.blocked_link_mask.shape:
            raise ValueError("link_travel_time_cost and blocked_link_mask must have same shape")
        if self.destination_node_index < 0 or self.destination_node_index >= int(self.node_cost_to_go.shape[0]):
            raise ValueError("destination_node_index out of range")


@dataclass(slots=True)
class BaselineNextLinkScores:
    """Sorted legal next-link action costs for a node decision context."""

    current_node_id: int
    destination_node_id: int
    incoming_link_id: int | None
    candidate_link_ids: tuple[int, ...]
    action_costs: tuple[float, ...]
    best_link_id: int | None
    best_cost: float | None


def compute_dynamic_potential_state(
    network: RoadNetworkCSR,
    *,
    destination_node_id: int,
    link_state: LinkState | None = None,
    link_travel_time_cost: Array | None = None,
    routing_backend: RoutingBackend = "baseline",
    cache: dict[Any, DynamicPotentialState] | None = None,
    cache_key: Any | None = None,
    stats: dict[str, Any] | None = None,
) -> DynamicPotentialState:
    """Compute a congestion-aware shortest-path cost-to-go field to destination.

    When `link_state` is provided, current `travel_time_cost` drives the
    baseline potential and links with zero effective capacity are treated as
    blocked if the static link is blockable. A supplied cache is used only
    when `cache_key` is explicit; callers own generation-based invalidation.
    """

    if not isinstance(network, RoadNetworkCSR):
        raise TypeError("network must be a RoadNetworkCSR")
    _validate_routing_backend(routing_backend)
    effective_cache_key = None
    if cache is not None and cache_key is not None:
        effective_cache_key = (
            "dynamic_potential_backend",
            str(routing_backend),
            cache_key,
        )
        cached = cache.get(effective_cache_key)
        if cached is not None:
            if stats is not None:
                stats["dynamic_potential_cache_hits_total"] = int(
                    stats.get("dynamic_potential_cache_hits_total", 0)
                ) + 1
            return cached
    started = perf_counter()
    dest_idx = network.node_id_to_index[int(destination_node_id)]
    costs = _resolve_link_costs(
        network,
        link_state=link_state,
        link_travel_time_cost=link_travel_time_cost,
    )
    blocked = _resolve_blocked_link_mask(network, link_state=link_state, size=network.link_count)
    node_cost, actual_backend, fallback_reason = _compute_node_cost_to_go(
        network,
        costs=costs,
        blocked=blocked,
        destination_node_index=dest_idx,
        routing_backend=routing_backend,
    )

    state = DynamicPotentialState(
        destination_node_id=int(destination_node_id),
        destination_node_index=dest_idx,
        node_cost_to_go=node_cost,
        link_travel_time_cost=costs,
        blocked_link_mask=blocked,
        metadata={
            "link_count": network.link_count,
            "node_count": network.node_count,
            "cache_key": effective_cache_key,
            "routing_backend": actual_backend,
            "routing_backend_requested": str(routing_backend),
            **(
                {"routing_backend_fallback": fallback_reason}
                if fallback_reason is not None
                else {}
            ),
        },
    )
    if cache is not None and effective_cache_key is not None:
        cache[effective_cache_key] = state
    if stats is not None:
        stats["dynamic_potential_recompute_total"] = int(
            stats.get("dynamic_potential_recompute_total", 0)
        ) + 1
        stats["dynamic_potential_recompute_seconds_total"] = float(
            stats.get("dynamic_potential_recompute_seconds_total", 0.0)
        ) + max(perf_counter() - started, 0.0)
    return state


def _validate_routing_backend(routing_backend: str) -> None:
    if routing_backend not in ROUTING_BACKENDS:
        raise ValueError("routing_backend must be one of: baseline, rust_cpu, auto")


def _compute_node_cost_to_go(
    network: RoadNetworkCSR,
    *,
    costs: Array,
    blocked: Array,
    destination_node_index: int,
    routing_backend: RoutingBackend,
) -> tuple[Array, str, str | None]:
    if routing_backend == "auto" and not rust_routing_backend_available():
        return (
            _reverse_dijkstra_node_costs(
                network,
                costs=costs,
                blocked=blocked,
                destination_node_index=destination_node_index,
            ),
            "baseline",
            "rust_cpu_unavailable",
        )
    if routing_backend in {"rust_cpu", "auto"}:
        try:
            return (
                compute_dynamic_potential_node_costs_rust(
                    node_count=network.node_count,
                    incoming_indptr=network.incoming_indptr,
                    incoming_link_indices=network.incoming_link_indices,
                    link_src_node_index=network.link_src_node_index,
                    link_travel_time_cost=costs,
                    blocked_link_mask=blocked,
                    destination_node_index=destination_node_index,
                ),
                "rust_cpu",
                None,
            )
        except RuntimeError:
            if routing_backend == "rust_cpu":
                raise
            return (
                _reverse_dijkstra_node_costs(
                    network,
                    costs=costs,
                    blocked=blocked,
                    destination_node_index=destination_node_index,
                ),
                "baseline",
                "rust_cpu_failed",
            )
    return (
        _reverse_dijkstra_node_costs(
            network,
            costs=costs,
            blocked=blocked,
            destination_node_index=destination_node_index,
        ),
        "baseline",
        None,
    )


def score_legal_next_links(
    network: RoadNetworkCSR,
    potential_state: DynamicPotentialState,
    *,
    current_node_id: int,
    incoming_link_id: int | None = None,
    routing_backend: RoutingBackend = "baseline",
) -> BaselineNextLinkScores:
    """Score legal next links by `link_cost + potential(dst_node)` (lower is better)."""

    _validate_routing_backend(routing_backend)
    node_index = network.node_id_to_index[int(current_node_id)]
    outgoing_idx = _outgoing_link_indices_for_node(network, node_index)
    allowed_idx = _filter_legal_turn_successors(
        network,
        outgoing_idx=outgoing_idx,
        incoming_link_id=incoming_link_id,
    )

    raw_costs = _compute_next_link_action_costs_for_backend(
        candidate_link_indices=tuple(int(x) for x in allowed_idx),
        link_dst_node_index=network.link_dst_node_index,
        node_cost_to_go=potential_state.node_cost_to_go,
        link_travel_time_cost=potential_state.link_travel_time_cost,
        blocked_link_mask=potential_state.blocked_link_mask,
        routing_backend=routing_backend,
    )
    scored: list[tuple[float, int]] = []
    for i, link_index in enumerate(allowed_idx):
        total_cost = float(raw_costs[i]) if len(raw_costs) > 0 else _INF_COST
        if (not np.isfinite(raw_costs[i])) or total_cost >= _INF_COST * 0.5:
            continue
        scored.append((total_cost, int(network.links[link_index].link_id)))

    scored.sort(key=lambda x: (x[0], x[1]))
    candidate_link_ids = tuple(link_id for _cost, link_id in scored)
    action_costs = tuple(float(cost) for cost, _link_id in scored)
    best_link_id = candidate_link_ids[0] if candidate_link_ids else None
    best_cost = action_costs[0] if action_costs else None
    return BaselineNextLinkScores(
        current_node_id=int(current_node_id),
        destination_node_id=potential_state.destination_node_id,
        incoming_link_id=None if incoming_link_id is None else int(incoming_link_id),
        candidate_link_ids=candidate_link_ids,
        action_costs=action_costs,
        best_link_id=best_link_id,
        best_cost=best_cost,
    )


def _compute_next_link_action_costs_for_backend(
    *,
    candidate_link_indices: tuple[int, ...],
    link_dst_node_index: Array,
    node_cost_to_go: Array,
    link_travel_time_cost: Array,
    blocked_link_mask: Array,
    routing_backend: RoutingBackend,
) -> np.ndarray:
    if routing_backend == "auto" and not rust_routing_backend_available():
        return _compute_next_link_action_costs_host(
            candidate_link_indices=candidate_link_indices,
            link_dst_node_index=link_dst_node_index,
            node_cost_to_go=node_cost_to_go,
            link_travel_time_cost=link_travel_time_cost,
            blocked_link_mask=blocked_link_mask,
        )
    if routing_backend in {"rust_cpu", "auto"}:
        try:
            return compute_next_link_action_costs_rust(
                candidate_link_indices=candidate_link_indices,
                link_dst_node_index=link_dst_node_index,
                node_cost_to_go=node_cost_to_go,
                link_travel_time_cost=link_travel_time_cost,
                blocked_link_mask=blocked_link_mask,
            )
        except RuntimeError:
            if routing_backend == "rust_cpu":
                raise
    return _compute_next_link_action_costs_host(
        candidate_link_indices=candidate_link_indices,
        link_dst_node_index=link_dst_node_index,
        node_cost_to_go=node_cost_to_go,
        link_travel_time_cost=link_travel_time_cost,
        blocked_link_mask=blocked_link_mask,
    )


def build_greedy_route_candidate(
    network: RoadNetworkCSR,
    potential_state: DynamicPotentialState,
    *,
    origin_node_id: int,
    incoming_link_id: int | None = None,
    max_hops: int | None = None,
    routing_backend: RoutingBackend = "baseline",
) -> tuple[int, ...]:
    """Build a deterministic greedy route candidate from dynamic potential scores."""

    _validate_routing_backend(routing_backend)
    destination_node_id = potential_state.destination_node_id
    if int(origin_node_id) == int(destination_node_id):
        return ()
    hop_limit = max(1, int(max_hops)) if max_hops is not None else max(1, network.link_count + 1)

    if routing_backend == "auto" and not rust_routing_backend_available():
        return _build_greedy_route_candidate_baseline(
            network,
            potential_state,
            origin_node_id=int(origin_node_id),
            incoming_link_id=incoming_link_id,
            hop_limit=hop_limit,
        )

    if routing_backend in {"rust_cpu", "auto"}:
        try:
            return _build_greedy_route_candidate_rust(
                network,
                potential_state,
                origin_node_id=int(origin_node_id),
                incoming_link_id=incoming_link_id,
                hop_limit=hop_limit,
            )
        except RuntimeError:
            if routing_backend == "rust_cpu":
                raise

    return _build_greedy_route_candidate_baseline(
        network,
        potential_state,
        origin_node_id=int(origin_node_id),
        incoming_link_id=incoming_link_id,
        hop_limit=hop_limit,
    )


def _build_greedy_route_candidate_rust(
    network: RoadNetworkCSR,
    potential_state: DynamicPotentialState,
    *,
    origin_node_id: int,
    incoming_link_id: int | None,
    hop_limit: int,
) -> tuple[int, ...]:
    origin_node_index = network.node_id_to_index[int(origin_node_id)]
    incoming_link_index = -1
    if incoming_link_id is not None:
        maybe_index = network.link_id_to_index.get(int(incoming_link_id))
        if maybe_index is None:
            return ()
        incoming_link_index = int(maybe_index)
    return compute_greedy_route_candidate_rust(
        node_count=network.node_count,
        link_ids=network.link_ids,
        link_dst_node_index=network.link_dst_node_index,
        outgoing_indptr=network.outgoing_indptr,
        outgoing_link_indices=network.outgoing_link_indices,
        turn_from_link_index=network.turn_from_link_index,
        turn_to_link_index=network.turn_to_link_index,
        turn_is_forbidden=network.turn_is_forbidden,
        node_cost_to_go=potential_state.node_cost_to_go,
        link_travel_time_cost=potential_state.link_travel_time_cost,
        blocked_link_mask=potential_state.blocked_link_mask,
        origin_node_index=origin_node_index,
        destination_node_index=potential_state.destination_node_index,
        incoming_link_index=incoming_link_index,
        max_hops=hop_limit,
    )


def _build_greedy_route_candidate_baseline(
    network: RoadNetworkCSR,
    potential_state: DynamicPotentialState,
    *,
    origin_node_id: int,
    incoming_link_id: int | None,
    hop_limit: int,
) -> tuple[int, ...]:
    destination_node_id = potential_state.destination_node_id
    cur_node_id = int(origin_node_id)
    cur_incoming_link_id = None if incoming_link_id is None else int(incoming_link_id)
    visited_nodes = {cur_node_id}
    path: list[int] = []
    outgoing_lookup = _get_outgoing_link_index_lookup(network)
    turn_successor_lookup = _get_turn_successor_lookup(network) if network.turn_count > 0 else None
    dst_node_idx = np.asarray(network.link_dst_node_index, dtype=np.int32)
    node_cost = np.asarray(potential_state.node_cost_to_go, dtype=np.float32)
    link_cost = np.asarray(potential_state.link_travel_time_cost, dtype=np.float32)
    blocked = np.asarray(potential_state.blocked_link_mask, dtype=np.bool_)

    for _ in range(hop_limit):
        next_link_id = _best_legal_next_link_id_host(
            network,
            current_node_id=cur_node_id,
            incoming_link_id=cur_incoming_link_id,
            outgoing_lookup=outgoing_lookup,
            turn_successor_lookup=turn_successor_lookup,
            dst_node_idx=dst_node_idx,
            node_cost=node_cost,
            link_cost=link_cost,
            blocked=blocked,
        )
        if next_link_id is None:
            break
        next_link = network.links[network.link_id_to_index[next_link_id]]
        path.append(next_link.link_id)
        cur_incoming_link_id = next_link.link_id
        cur_node_id = next_link.dst_node_id
        if cur_node_id == destination_node_id:
            return tuple(path)
        if cur_node_id in visited_nodes:
            break
        visited_nodes.add(cur_node_id)
    return ()


def compute_next_link_action_costs_core(
    *,
    candidate_link_indices: Array,
    link_dst_node_index: Array,
    node_cost_to_go: Array,
    link_travel_time_cost: Array,
    blocked_link_mask: Array,
) -> Array:
    """Array-only next-action scoring core for routing extensions."""

    cand = np.asarray(candidate_link_indices, dtype=np.int32)
    if cand.ndim != 1:
        raise ValueError("candidate_link_indices must be 1-D")
    dst_idx = np.asarray(link_dst_node_index, dtype=np.int32)[cand]
    tail = np.asarray(node_cost_to_go, dtype=np.float32)[dst_idx]
    link_cost = np.asarray(link_travel_time_cost, dtype=np.float32)[cand]
    blocked = np.asarray(blocked_link_mask, dtype=np.bool_)[cand]
    total = link_cost + tail
    valid = (~blocked) & np.isfinite(tail) & (tail < (_INF_COST * 0.5))
    return np.where(valid, total, np.asarray(_INF_COST, dtype=np.float32))


def _resolve_link_costs(
    network: RoadNetworkCSR,
    *,
    link_state: LinkState | None,
    link_travel_time_cost: Array | None,
) -> Array:
    if link_state is not None:
        if link_state.link_count != network.link_count:
            raise ValueError("link_state.link_count must match network.link_count")
        return np.maximum(
            np.asarray(link_state.travel_time_cost, dtype=np.float32),
            np.float32(1e-6),
        )
    if link_travel_time_cost is not None:
        arr = np.asarray(link_travel_time_cost, dtype=np.float32)
        if arr.ndim != 1 or int(arr.shape[0]) != network.link_count:
            raise ValueError(f"link_travel_time_cost must have shape ({network.link_count},)")
        return np.maximum(arr, np.float32(1e-6))
    free_flow = [
        max(1e-6, float(link.length_m) / max(1e-6, float(link.free_flow_speed_mps)))
        for link in network.links
    ]
    return np.asarray(free_flow, dtype=np.float32)


def _resolve_blocked_link_mask(
    network: RoadNetworkCSR,
    *,
    link_state: LinkState | None,
    size: int,
) -> Array:
    if link_state is None:
        return np.zeros((size,), dtype=np.bool_)
    static_blockable = _static_blockable_mask(network)
    capacity = np.asarray(link_state.capacity_veh_per_tick, dtype=np.float32)
    incident = np.asarray(link_state.incident_capacity_multiplier, dtype=np.float32)
    blocked = (capacity * incident) <= np.float32(0.0)
    return np.asarray(blocked, dtype=np.bool_) & static_blockable


def _compute_next_link_action_costs_host(
    *,
    candidate_link_indices: tuple[int, ...],
    link_dst_node_index: Array,
    node_cost_to_go: Array,
    link_travel_time_cost: Array,
    blocked_link_mask: Array,
) -> np.ndarray:
    if not candidate_link_indices:
        return np.zeros((0,), dtype=np.float32)
    cand = np.asarray(candidate_link_indices, dtype=np.int32)
    dst_idx = np.asarray(link_dst_node_index, dtype=np.int32)[cand]
    tail = np.asarray(node_cost_to_go, dtype=np.float32)[dst_idx]
    link_cost = np.asarray(link_travel_time_cost, dtype=np.float32)[cand]
    blocked = np.asarray(blocked_link_mask, dtype=np.bool_)[cand]
    total = link_cost + tail
    valid = (~blocked) & np.isfinite(tail) & (tail < (_INF_COST * 0.5))
    return np.where(valid, total, np.float32(_INF_COST))


def _best_legal_next_link_id_host(
    network: RoadNetworkCSR,
    *,
    current_node_id: int,
    incoming_link_id: int | None,
    outgoing_lookup: tuple[tuple[int, ...], ...],
    turn_successor_lookup: tuple[dict[int, tuple[int, ...]], dict[int, tuple[int, ...]]] | None,
    dst_node_idx: np.ndarray,
    node_cost: np.ndarray,
    link_cost: np.ndarray,
    blocked: np.ndarray,
) -> int | None:
    node_index = network.node_id_to_index[int(current_node_id)]
    outgoing_idx = outgoing_lookup[int(node_index)]
    allowed_idx = _filter_legal_turn_successors(
        network,
        outgoing_idx=outgoing_idx,
        incoming_link_id=incoming_link_id,
        turn_successor_lookup=turn_successor_lookup,
    )
    if not allowed_idx:
        return None

    best_cost = float(_INF_COST)
    best_link_id: int | None = None
    for link_index in allowed_idx:
        idx = int(link_index)
        if bool(blocked[idx]):
            continue
        tail = float(node_cost[int(dst_node_idx[idx])])
        if not np.isfinite(tail) or tail >= (_INF_COST * 0.5):
            continue
        total_cost = float(link_cost[idx]) + tail
        if total_cost >= (_INF_COST * 0.5):
            continue
        link_id = int(network.links[idx].link_id)
        if (
            best_link_id is None
            or total_cost < best_cost
            or (total_cost == best_cost and link_id < best_link_id)
        ):
            best_cost = total_cost
            best_link_id = link_id
    return best_link_id


def _reverse_dijkstra_node_costs(
    network: RoadNetworkCSR,
    *,
    costs: Array,
    blocked: Array,
    destination_node_index: int,
) -> Array:
    node_count = network.node_count
    dist = np.full((int(node_count),), np.float32(_INF_COST), dtype=np.float32)
    dist[int(destination_node_index)] = np.float32(0.0)
    heap: list[tuple[float, int]] = [(0.0, int(destination_node_index))]

    incoming_indptr, incoming_link_indices, link_src = _reverse_graph_arrays(network)
    blocked_np = (
        blocked
        if isinstance(blocked, np.ndarray) and blocked.dtype == np.bool_
        else np.asarray(blocked, dtype=np.bool_)
    )
    costs_np = (
        costs
        if isinstance(costs, np.ndarray) and costs.dtype == np.float32
        else np.asarray(costs, dtype=np.float32)
    )

    while heap:
        cur_cost, node_idx = heappop(heap)
        cur_cost32 = np.float32(cur_cost)
        if cur_cost32 > dist[node_idx]:
            continue
        start = int(incoming_indptr[node_idx])
        end = int(incoming_indptr[node_idx + 1])
        for pos in range(start, end):
            link_index = int(incoming_link_indices[pos])
            if blocked_np[link_index]:
                continue
            prev_node_idx = int(link_src[link_index])
            cand = np.float32(cur_cost32 + costs_np[link_index])
            if cand < dist[prev_node_idx]:
                dist[prev_node_idx] = cand
                heappush(heap, (float(cand), prev_node_idx))
    return dist


def _reverse_graph_arrays(network: RoadNetworkCSR) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cache_key = (
        _network_topology_cache_key(network),
        int(network.node_count),
        int(network.link_count),
    )
    cached = _REVERSE_GRAPH_CACHE.get(cache_key)
    if cached is not None:
        return cached
    value = (
        np.asarray(network.incoming_indptr, dtype=np.int32),
        np.asarray(network.incoming_link_indices, dtype=np.int32),
        np.asarray(network.link_src_node_index, dtype=np.int32),
    )
    _REVERSE_GRAPH_CACHE[cache_key] = value
    _prune_small_cache(_REVERSE_GRAPH_CACHE, max_entries=32)
    return value


def _static_blockable_mask(network: RoadNetworkCSR) -> np.ndarray:
    cache_key = (
        _network_topology_cache_key(network),
        int(network.link_count),
    )
    cached = _STATIC_BLOCKABLE_MASK_CACHE.get(cache_key)
    if cached is not None:
        return cached
    value = np.asarray([bool(link.is_blockable) for link in network.links], dtype=np.bool_)
    _STATIC_BLOCKABLE_MASK_CACHE[cache_key] = value
    _prune_small_cache(_STATIC_BLOCKABLE_MASK_CACHE, max_entries=32)
    return value


def _prune_small_cache(cache: dict[Any, Any], *, max_entries: int) -> None:
    while len(cache) > int(max_entries):
        cache.pop(next(iter(cache)))


def _network_topology_cache_key(network: RoadNetworkCSR) -> Any:
    key = getattr(network, "topology_cache_key", None)
    if key is not None:
        return key
    return (
        "road-network-csr-legacy",
        int(network.node_count),
        int(network.link_count),
        int(network.turn_count),
        tuple(int(x) for x in np.asarray(network.link_ids, dtype=np.int32).tolist()),
        tuple(int(x) for x in np.asarray(network.link_src_node_index, dtype=np.int32).tolist()),
        tuple(int(x) for x in np.asarray(network.link_dst_node_index, dtype=np.int32).tolist()),
    )


def _outgoing_link_indices_for_node(network: RoadNetworkCSR, node_index: int) -> tuple[int, ...]:
    lookup = _get_outgoing_link_index_lookup(network)
    return lookup[int(node_index)]


def _get_outgoing_link_index_lookup(network: RoadNetworkCSR) -> tuple[tuple[int, ...], ...]:
    cache_key = (
        _network_topology_cache_key(network),
        int(network.node_count),
        int(network.link_count),
    )
    cached = _OUTGOING_LINK_LOOKUP_CACHE.get(cache_key)
    if cached is not None:
        return cached

    indptr = np.asarray(network.outgoing_indptr, dtype=np.int32)
    link_indices = np.asarray(network.outgoing_link_indices, dtype=np.int32)
    lookup = tuple(
        tuple(int(x) for x in link_indices[int(indptr[n]) : int(indptr[n + 1])].tolist())
        for n in range(int(network.node_count))
    )
    _OUTGOING_LINK_LOOKUP_CACHE[cache_key] = lookup
    return lookup


def _filter_legal_turn_successors(
    network: RoadNetworkCSR,
    *,
    outgoing_idx: tuple[int, ...],
    incoming_link_id: int | None,
    turn_successor_lookup: tuple[dict[int, tuple[int, ...]], dict[int, tuple[int, ...]]] | None = None,
) -> tuple[int, ...]:
    if incoming_link_id is None or not outgoing_idx:
        return outgoing_idx
    if network.turn_count == 0:
        return outgoing_idx
    incoming_index = network.link_id_to_index.get(int(incoming_link_id))
    if incoming_index is None:
        return ()
    all_succ_by_from, allowed_succ_by_from = (
        turn_successor_lookup
        if turn_successor_lookup is not None
        else _get_turn_successor_lookup(network)
    )
    all_successors = all_succ_by_from.get(incoming_index)
    if all_successors is None:
        return ()
    allowed_successors = allowed_succ_by_from.get(incoming_index, ())
    if not allowed_successors:
        return ()
    candidates = set(outgoing_idx)
    return tuple(idx for idx in allowed_successors if idx in candidates)


def _get_turn_successor_lookup(
    network: RoadNetworkCSR,
) -> tuple[dict[int, tuple[int, ...]], dict[int, tuple[int, ...]]]:
    cache_key = (
        _network_topology_cache_key(network),
        int(network.turn_count),
        int(network.link_count),
    )
    cached = _TURN_SUCCESSOR_CACHE.get(cache_key)
    if cached is not None:
        return cached

    turn_from = np.asarray(network.turn_from_link_index, dtype=np.int32)
    turn_to = np.asarray(network.turn_to_link_index, dtype=np.int32)
    turn_forbidden = np.asarray(network.turn_is_forbidden, dtype=np.bool_)

    all_map: dict[int, set[int]] = {}
    allowed_map: dict[int, set[int]] = {}
    for t_idx in range(network.turn_count):
        from_idx = int(turn_from[t_idx])
        to_idx = int(turn_to[t_idx])
        all_map.setdefault(from_idx, set()).add(to_idx)
        if not bool(turn_forbidden[t_idx]):
            allowed_map.setdefault(from_idx, set()).add(to_idx)

    frozen = (
        {k: tuple(sorted(v)) for k, v in all_map.items()},
        {k: tuple(sorted(v)) for k, v in allowed_map.items()},
    )
    _TURN_SUCCESSOR_CACHE[cache_key] = frozen
    return frozen
