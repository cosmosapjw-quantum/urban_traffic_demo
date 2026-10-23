"""Connected road hierarchy classification for formative urban growth."""

from __future__ import annotations

import heapq
import math
from typing import Sequence

from metroflow.city.formative_growth_model import (
    FormationCentre,
    FormationEdge,
    FormationNode,
    _EPS,
)
from metroflow.city.formative_growth_network import _MutableEdge, distance as _distance

__all__ = ["classify_edges"]

def _shortest_path_edge_indices(
    nodes: Sequence[FormationNode],
    edges: Sequence[_MutableEdge],
    source: int,
    target: int,
) -> tuple[int, ...]:
    adj: list[list[tuple[int, float, int]]] = [[] for _ in nodes]
    for edge_index, edge in enumerate(edges):
        weight = _distance(nodes[edge.u], nodes[edge.v])
        adj[edge.u].append((edge.v, weight, edge_index))
        adj[edge.v].append((edge.u, weight, edge_index))
    dist = [math.inf] * len(nodes)
    prev_node = [-1] * len(nodes)
    prev_edge = [-1] * len(nodes)
    dist[source] = 0.0
    heap: list[tuple[float, int]] = [(0.0, source)]
    while heap:
        current_dist, u = heapq.heappop(heap)
        if current_dist != dist[u]:
            continue
        if u == target:
            break
        for v, weight, edge_index in adj[u]:
            next_dist = current_dist + weight
            if next_dist + _EPS < dist[v]:
                dist[v] = next_dist
                prev_node[v] = u
                prev_edge[v] = edge_index
                heapq.heappush(heap, (next_dist, v))
    if not math.isfinite(dist[target]):
        return ()
    path: list[int] = []
    current = target
    while current != source:
        edge_index = prev_edge[current]
        if edge_index < 0:
            return ()
        path.append(edge_index)
        current = prev_node[current]
    path.reverse()
    return tuple(path)

def _shortest_path_edge_indices_oriented(
    nodes: Sequence[FormationNode],
    edges: Sequence[_MutableEdge],
    source: int,
    target: int,
) -> tuple[int, ...]:
    """Shortest path with a fixed corridor-axis turn surrogate.

    The additional factor is dimensionless and non-negative.  It does not claim
    to solve a full elastica problem; it merely avoids promoting highly zigzag
    local paths to the arterial hierarchy.
    """

    sx, sy = nodes[source].x_m, nodes[source].y_m
    tx, ty = nodes[target].x_m, nodes[target].y_m
    axis_norm = math.hypot(tx - sx, ty - sy)
    if axis_norm <= _EPS:
        return ()
    ax = (tx - sx) / axis_norm
    ay = (ty - sy) / axis_norm
    adj: list[list[tuple[int, float, int]]] = [[] for _ in nodes]
    for edge_index, edge in enumerate(edges):
        u = nodes[edge.u]
        v = nodes[edge.v]
        length = _distance(u, v)
        ex = (v.x_m - u.x_m) / max(length, _EPS)
        ey = (v.y_m - u.y_m) / max(length, _EPS)
        alignment = abs(ex * ax + ey * ay)
        weight = length * (1.0 + 0.85 * (1.0 - alignment))
        adj[edge.u].append((edge.v, weight, edge_index))
        adj[edge.v].append((edge.u, weight, edge_index))
    dist = [math.inf] * len(nodes)
    prev_node = [-1] * len(nodes)
    prev_edge = [-1] * len(nodes)
    dist[source] = 0.0
    heap: list[tuple[float, int]] = [(0.0, source)]
    while heap:
        current_dist, u = heapq.heappop(heap)
        if current_dist != dist[u]:
            continue
        if u == target:
            break
        for v, weight, edge_index in adj[u]:
            next_dist = current_dist + weight
            if next_dist + _EPS < dist[v]:
                dist[v] = next_dist
                prev_node[v] = u
                prev_edge[v] = edge_index
                heapq.heappush(heap, (next_dist, v))
    if not math.isfinite(dist[target]):
        return ()
    path: list[int] = []
    current = target
    while current != source:
        edge_index = prev_edge[current]
        if edge_index < 0:
            return ()
        path.append(edge_index)
        current = prev_node[current]
    path.reverse()
    return tuple(path)

def _dijkstra_paths(
    nodes: Sequence[FormationNode],
    edges: Sequence[_MutableEdge],
    source: int,
) -> tuple[list[float], list[int]]:
    adj = [[] for _ in nodes]
    for index, edge in enumerate(edges):
        length = _distance(nodes[edge.u], nodes[edge.v])
        adj[edge.u].append((edge.v, length, index))
        adj[edge.v].append((edge.u, length, index))
    dist = [math.inf] * len(nodes)
    prev_edge = [-1] * len(nodes)
    prev_node = [-1] * len(nodes)
    dist[source] = 0.0
    heap = [(0.0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if d != dist[u]:
            continue
        for v, weight, edge_index in adj[u]:
            nd = d + weight
            if nd + _EPS < dist[v]:
                dist[v] = nd
                prev_edge[v] = edge_index
                prev_node[v] = u
                heapq.heappush(heap, (nd, v))
    return dist, [(prev_node[i] << 32) | (prev_edge[i] & 0xFFFFFFFF) for i in range(len(nodes))]

def _edge_loads(
    nodes: Sequence[FormationNode],
    edges: Sequence[_MutableEdge],
    source_ids: Sequence[int],
) -> list[float]:
    loads = [0.0] * len(edges)
    for source in source_ids:
        _dist, packed = _dijkstra_paths(nodes, edges, source)
        for target in range(len(nodes)):
            if target == source:
                continue
            current = target
            guard = 0
            while current != source and guard < len(nodes):
                prev_node = packed[current] >> 32
                edge_index = packed[current] & 0xFFFFFFFF
                if prev_node < 0 or edge_index >= len(edges):
                    break
                loads[edge_index] += 1.0
                current = prev_node
                guard += 1
    return loads

def _classify_edges(
    nodes: Sequence[FormationNode],
    centres: Sequence[FormationCentre],
    edges: Sequence[_MutableEdge],
) -> list[FormationEdge]:
    centre_nodes = [
        min(range(len(nodes)), key=lambda i: math.hypot(nodes[i].x_m - c.x_m, nodes[i].y_m - c.y_m))
        for c in centres
    ]
    ordered = sorted(range(len(nodes)), key=lambda i: (nodes[i].x_m + nodes[i].y_m, i))
    sample = sorted(set(centre_nodes + [ordered[int(k * (len(ordered) - 1) / 15)] for k in range(16)]))
    loads = _edge_loads(nodes, edges, sample)
    ranked = sorted(range(len(edges)), key=lambda idx: (-loads[idx], idx))

    # The primary network is explicitly a connected historical backbone: paths
    # from the old core to every secondary centre and four urban-frontier gates.
    main = centre_nodes[0]
    gateway_nodes = {
        min(range(len(nodes)), key=lambda i: (nodes[i].x_m, i)),
        max(range(len(nodes)), key=lambda i: (nodes[i].x_m, -i)),
        min(range(len(nodes)), key=lambda i: (nodes[i].y_m, i)),
        max(range(len(nodes)), key=lambda i: (nodes[i].y_m, -i)),
    }
    primary: set[int] = set()
    for target in sorted(set(centre_nodes[1:]) | gateway_nodes):
        primary.update(_shortest_path_edge_indices_oriented(nodes, edges, main, target))
    if not primary and edges:
        primary.add(ranked[0])
    target_primary = max(len(primary), int(round(0.115 * len(edges))))
    primary_nodes = {endpoint for idx in primary for endpoint in (edges[idx].u, edges[idx].v)}
    while len(primary) < target_primary:
        admitted = False
        for idx in ranked:
            if idx in primary:
                continue
            edge = edges[idx]
            if edge.u in primary_nodes or edge.v in primary_nodes:
                primary.add(idx)
                primary_nodes.update((edge.u, edge.v))
                admitted = True
                if len(primary) >= target_primary:
                    break
        if not admitted:
            break

    target_secondary = max(1, int(round(0.27 * len(edges))))
    secondary: set[int] = set()
    for idx in ranked:
        if idx in primary:
            continue
        edge = edges[idx]
        if edge.u in primary_nodes or edge.v in primary_nodes or edge.birth_epoch <= 2:
            secondary.add(idx)
        if len(secondary) >= target_secondary:
            break
    if len(secondary) < target_secondary:
        for idx in ranked:
            if idx not in primary and idx not in secondary:
                secondary.add(idx)
            if len(secondary) >= target_secondary:
                break

    out: list[FormationEdge] = []
    for edge_id, edge in enumerate(edges):
        hierarchy = "primary" if edge_id in primary else ("secondary" if edge_id in secondary else "local")
        out.append(
            FormationEdge(
                edge_id=edge_id,
                u=edge.u,
                v=edge.v,
                birth_epoch=edge.birth_epoch,
                length_m=_distance(nodes[edge.u], nodes[edge.v]),
                hierarchy=hierarchy,
                role=edge.role,
                score=edge.score,
            )
        )
    return out

classify_edges = _classify_edges
