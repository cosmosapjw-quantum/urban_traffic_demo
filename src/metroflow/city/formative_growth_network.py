"""Causal planar growth and bounded loop closure in pure Python."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
from typing import Sequence

from metroflow.city.formative_growth_model import (
    FormationCentre,
    FormationConfig,
    FormationNode,
    _EPS,
)

__all__ = [
    "build_causal_growth_network",
    "repair_local_connectivity",
    "close_dangling_stubs",
    "distance",
    "orientation_alignment",
    "segments_cross",
]

@dataclass(slots=True)
class _MutableEdge:
    u: int
    v: int
    birth_epoch: int
    role: str
    score: float

    @property
    def key(self) -> tuple[int, int]:
        return (min(self.u, self.v), max(self.u, self.v))


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        parent = self.parent
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(self, a: int, b: int) -> bool:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        return True


def _distance(a: FormationNode, b: FormationNode) -> float:
    return math.hypot(a.x_m - b.x_m, a.y_m - b.y_m)

def _build_causal_growth_network(
    cfg: FormationConfig,
    nodes: Sequence[FormationNode],
    centres: Sequence[FormationCentre],
) -> list[_MutableEdge]:
    """Build the street graph in chronological order.

    Epoch zero receives an orientation-aware planar spanning backbone.  Each
    later node then attaches to the already existing graph through exactly one
    growth connection before any same-epoch loop closure is considered.  The
    construction therefore never lets future settlements alter an earlier
    connectivity decision.
    """

    edges: list[_MutableEdge] = []
    existing: set[tuple[int, int]] = set()
    degree = [0] * len(nodes)
    active: list[int] = []
    target_edges = max(len(nodes) - 1, int(round(0.5 * cfg.target_mean_degree * len(nodes))))
    total_loop_target = max(0, target_edges - (len(nodes) - 1))
    loop_count = 0

    for epoch in range(cfg.epochs):
        newborn = [node.node_id for node in nodes if node.birth_epoch == epoch]
        if epoch == 0:
            active.extend(newborn)
            initial = _planar_oriented_spanning_tree(cfg, nodes, centres, active)
            for edge in initial:
                edges.append(edge)
                existing.add(edge.key)
                degree[edge.u] += 1
                degree[edge.v] += 1
        else:
            for node_id in newborn:
                parent = _choose_growth_parent(
                    cfg, nodes, centres, node_id, active, edges, degree
                )
                if parent is None:
                    raise RuntimeError(
                        f"unable to attach growth node {node_id} without violating planarity"
                    )
                edge = _MutableEdge(
                    node_id, parent, epoch, "growth_connection", 0.0
                )
                edges.append(edge)
                existing.add(edge.key)
                degree[node_id] += 1
                degree[parent] += 1
                active.append(node_id)

        if len(active) < 3:
            continue
        cumulative_target = int(
            round(total_loop_target * (len(active) / len(nodes)) ** 1.18)
        )
        epoch_budget = max(0, cumulative_target - loop_count)
        if epoch_budget <= 0:
            continue
        added = _add_active_epoch_loops(
            cfg=cfg,
            nodes=nodes,
            centres=centres,
            active_ids=tuple(active),
            epoch=epoch,
            budget=epoch_budget,
            edges=edges,
            existing=existing,
            degree=degree,
        )
        loop_count += added

    return edges

def _planar_oriented_spanning_tree(
    cfg: FormationConfig,
    nodes: Sequence[FormationNode],
    centres: Sequence[FormationCentre],
    node_ids: Sequence[int],
) -> list[_MutableEdge]:
    if len(node_ids) <= 1:
        return []
    local_index = {node_id: i for i, node_id in enumerate(node_ids)}
    candidates: list[tuple[float, float, int, int]] = []
    for pos, i in enumerate(node_ids):
        for j in node_ids[pos + 1 :]:
            length = _distance(nodes[i], nodes[j])
            alignment = _orientation_alignment(nodes[i], nodes[j], centres)
            cost = length * (1.0 + 1.35 * (1.0 - alignment))
            candidates.append((cost, length, i, j))
    candidates.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    uf = _UnionFind(len(node_ids))
    out: list[_MutableEdge] = []
    for _cost, _length, i, j in candidates:
        if uf.find(local_index[i]) == uf.find(local_index[j]):
            continue
        if _edge_crosses_existing(nodes, i, j, out):
            continue
        uf.union(local_index[i], local_index[j])
        out.append(_MutableEdge(i, j, 0, "initial_backbone", 0.0))
        if len(out) == len(node_ids) - 1:
            return out
    # A crossing-free Euclidean fallback is deterministic and should only be
    # needed for degenerate point arrangements.
    for _cost, length, i, j in sorted(candidates, key=lambda row: (row[1], row[2], row[3])):
        if uf.find(local_index[i]) == uf.find(local_index[j]):
            continue
        if _edge_crosses_existing(nodes, i, j, out):
            continue
        uf.union(local_index[i], local_index[j])
        out.append(_MutableEdge(i, j, 0, "initial_backbone", 0.0))
        if len(out) == len(node_ids) - 1:
            return out
    raise RuntimeError("epoch-zero nodes could not be connected planarly")

def _choose_growth_parent(
    cfg: FormationConfig,
    nodes: Sequence[FormationNode],
    centres: Sequence[FormationCentre],
    node_id: int,
    active_ids: Sequence[int],
    edges: Sequence[_MutableEdge],
    degree: Sequence[int],
) -> int | None:
    node = nodes[node_id]
    candidates: list[tuple[float, float, int]] = []
    for other_id in active_ids:
        other = nodes[other_id]
        length = _distance(node, other)
        alignment = _orientation_alignment(node, other, centres)
        # Mild preferential attachment protects historical paths without
        # collapsing the graph onto one hub.
        attachment = 1.0 + 0.055 * math.sqrt(max(0, degree[other_id]))
        age_bonus = 1.0 + 0.035 * max(0, node.birth_epoch - other.birth_epoch)
        cost = length * (1.0 + 2.20 * (1.0 - alignment)) / (attachment * age_bonus)
        candidates.append((cost, length, other_id))
    candidates.sort(key=lambda row: (row[0], row[1], row[2]))
    for _cost, _length, other_id in candidates:
        if degree[other_id] >= cfg.max_node_degree + 1:
            continue
        if not _edge_crosses_existing(nodes, node_id, other_id, edges):
            return other_id
    # Connectivity is a hard invariant.  Relax the degree cap, but never
    # planarity, before declaring failure.
    for _cost, _length, other_id in candidates:
        if not _edge_crosses_existing(nodes, node_id, other_id, edges):
            return other_id
    return None

def _gabriel_candidates_for_ids(
    cfg: FormationConfig,
    nodes: Sequence[FormationNode],
    node_ids: Sequence[int],
    existing: set[tuple[int, int]],
) -> list[tuple[float, int, int]]:
    out: list[tuple[float, int, int]] = []
    ids = tuple(sorted(node_ids))
    for pos, i in enumerate(ids):
        a = nodes[i]
        for j in ids[pos + 1 :]:
            key = (i, j)
            if key in existing:
                continue
            b = nodes[j]
            d2 = (a.x_m - b.x_m) ** 2 + (a.y_m - b.y_m) ** 2
            if d2 > cfg.max_local_edge_m ** 2:
                continue
            mid_x = 0.5 * (a.x_m + b.x_m)
            mid_y = 0.5 * (a.y_m + b.y_m)
            radius2 = 0.25 * d2
            empty = True
            for k in ids:
                if k == i or k == j:
                    continue
                c = nodes[k]
                if (c.x_m - mid_x) ** 2 + (c.y_m - mid_y) ** 2 < radius2 - 1.0e-7:
                    empty = False
                    break
            if empty:
                out.append((math.sqrt(d2), i, j))
    return out

def _add_active_epoch_loops(
    *,
    cfg: FormationConfig,
    nodes: Sequence[FormationNode],
    centres: Sequence[FormationCentre],
    active_ids: Sequence[int],
    epoch: int,
    budget: int,
    edges: list[_MutableEdge],
    existing: set[tuple[int, int]],
    degree: list[int],
) -> int:
    scored: list[tuple[float, int, int]] = []
    for length, i, j in _gabriel_candidates_for_ids(cfg, nodes, active_ids, existing):
        if degree[i] >= cfg.max_node_degree or degree[j] >= cfg.max_node_degree:
            continue
        if _edge_crosses_existing(nodes, i, j, edges):
            continue
        graph_distance = _shortest_path_length(nodes, edges, i, j)
        if not math.isfinite(graph_distance):
            continue
        detour = graph_distance / max(length, 1.0)
        alignment = _orientation_alignment(nodes[i], nodes[j], centres)
        density = _local_density([nodes[k] for k in active_ids], active_ids.index(i), active_ids.index(j))
        birth = max(nodes[i].birth_epoch, nodes[j].birth_epoch)
        maturity = 1.0 - birth / max(cfg.epochs - 1, 1)
        threshold = 1.68 + 0.42 * (birth / max(cfg.epochs - 1, 1)) - 0.24 * maturity - 0.020 * min(density, 18)
        utility = (detour - 1.0) + 0.30 * maturity + 0.55 * alignment + 0.018 * min(density, 18) - 0.08 * (length / cfg.max_local_edge_m)
        if detour >= threshold and (
            alignment >= cfg.orientation_alignment_floor or detour >= threshold + 0.65
        ):
            scored.append((utility, i, j))
    scored.sort(key=lambda row: (-row[0], row[1], row[2]))
    added = 0
    for score, i, j in scored:
        if added >= budget:
            break
        if degree[i] >= cfg.max_node_degree or degree[j] >= cfg.max_node_degree:
            continue
        if (min(i, j), max(i, j)) in existing:
            continue
        if _edge_crosses_existing(nodes, i, j, edges):
            continue
        edge = _MutableEdge(i, j, epoch, "loop", score)
        edges.append(edge)
        existing.add(edge.key)
        degree[i] += 1
        degree[j] += 1
        added += 1
    return added

def _gabriel_candidates(
    cfg: FormationConfig,
    nodes: Sequence[FormationNode],
    existing: set[tuple[int, int]],
) -> list[tuple[float, int, int]]:
    out: list[tuple[float, int, int]] = []
    for i, a in enumerate(nodes):
        for j in range(i + 1, len(nodes)):
            key = (i, j)
            if key in existing:
                continue
            b = nodes[j]
            d2 = (a.x_m - b.x_m) ** 2 + (a.y_m - b.y_m) ** 2
            if d2 > cfg.max_local_edge_m ** 2:
                continue
            mid_x = 0.5 * (a.x_m + b.x_m)
            mid_y = 0.5 * (a.y_m + b.y_m)
            radius2 = 0.25 * d2
            empty = True
            for k, c in enumerate(nodes):
                if k == i or k == j:
                    continue
                if (c.x_m - mid_x) ** 2 + (c.y_m - mid_y) ** 2 < radius2 - 1.0e-7:
                    empty = False
                    break
            if empty:
                out.append((math.sqrt(d2), i, j))
    return out

def _shortest_path_length(
    nodes: Sequence[FormationNode],
    edges: Sequence[_MutableEdge],
    start: int,
    goal: int,
) -> float:
    adj = [[] for _ in nodes]
    for edge in edges:
        length = _distance(nodes[edge.u], nodes[edge.v])
        adj[edge.u].append((edge.v, length))
        adj[edge.v].append((edge.u, length))
    distances = [math.inf] * len(nodes)
    distances[start] = 0.0
    heap: list[tuple[float, int]] = [(0.0, start)]
    while heap:
        dist, u = heapq.heappop(heap)
        if dist != distances[u]:
            continue
        if u == goal:
            return dist
        for v, weight in adj[u]:
            new = dist + weight
            if new + _EPS < distances[v]:
                distances[v] = new
                heapq.heappush(heap, (new, v))
    return math.inf

def _orientation_alignment(
    a: FormationNode,
    b: FormationNode,
    centres: Sequence[FormationCentre],
) -> float:
    """Return local order, not global single-grid order.

    The historical core may be radial/tangential, while later districts are
    evaluated against their own survey axes.  This lets a polycentric city be
    globally high-entropy yet locally coherent.
    """

    angle = math.atan2(b.y_m - a.y_m, b.x_m - a.x_m)
    mid_x = 0.5 * (a.x_m + b.x_m)
    mid_y = 0.5 * (a.y_m + b.y_m)
    centre = min(centres, key=lambda c: math.hypot(mid_x - c.x_m, mid_y - c.y_m))
    distance = math.hypot(mid_x - centre.x_m, mid_y - centre.y_m)
    directions = [
        centre.local_grid_angle_rad,
        centre.local_grid_angle_rad + math.pi / 2.0,
    ]
    if centre.centre_id == 0 and distance <= 900.0:
        radial = math.atan2(mid_y - centre.y_m, mid_x - centre.x_m)
        directions.extend((radial, radial + math.pi / 2.0))
    return max(abs(math.cos(angle - direction)) for direction in directions)

def _local_density(nodes: Sequence[FormationNode], i: int, j: int, radius_m: float = 650.0) -> int:
    x = 0.5 * (nodes[i].x_m + nodes[j].x_m)
    y = 0.5 * (nodes[i].y_m + nodes[j].y_m)
    r2 = radius_m * radius_m
    return sum((n.x_m - x) ** 2 + (n.y_m - y) ** 2 <= r2 for n in nodes)

def _segments_cross(
    a: FormationNode,
    b: FormationNode,
    c: FormationNode,
    d: FormationNode,
) -> bool:
    if len({a.node_id, b.node_id, c.node_id, d.node_id}) < 4:
        return False

    def orient(p: FormationNode, q: FormationNode, r: FormationNode) -> float:
        return (q.x_m - p.x_m) * (r.y_m - p.y_m) - (q.y_m - p.y_m) * (r.x_m - p.x_m)

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    return (o1 * o2 < -1.0e-7) and (o3 * o4 < -1.0e-7)

def _edge_crosses_existing(
    nodes: Sequence[FormationNode],
    u: int,
    v: int,
    edges: Sequence[_MutableEdge],
) -> bool:
    a, b = nodes[u], nodes[v]
    return any(_segments_cross(a, b, nodes[e.u], nodes[e.v]) for e in edges)

def _repair_local_connectivity(
    cfg: FormationConfig,
    nodes: Sequence[FormationNode],
    centres: Sequence[FormationCentre],
    edges: list[_MutableEdge],
) -> None:
    """Repair only severe local detours and isolated leaf pairs after growth.

    This is a bounded constructive repair, not a generic optimiser.  It preserves
    planarity, degree caps and the formation history while reducing tree-like
    artefacts left by the epoch budgets.
    """

    existing = {edge.key for edge in edges}
    degree = [0] * len(nodes)
    for edge in edges:
        degree[edge.u] += 1
        degree[edge.v] += 1
    candidates = _gabriel_candidates(cfg, nodes, existing)
    scored: list[tuple[float, int, int]] = []
    for length, i, j in candidates:
        if degree[i] >= cfg.max_node_degree or degree[j] >= cfg.max_node_degree:
            continue
        if _edge_crosses_existing(nodes, i, j, edges):
            continue
        graph_distance = _shortest_path_length(nodes, edges, i, j)
        if not math.isfinite(graph_distance):
            continue
        detour = graph_distance / max(length, 1.0)
        leaf_bonus = 0.45 if degree[i] == 1 or degree[j] == 1 else 0.0
        alignment = _orientation_alignment(nodes[i], nodes[j], centres)
        score = detour - 1.0 + leaf_bonus + 0.20 * alignment
        if detour >= 2.65 or (leaf_bonus and detour >= 1.85):
            scored.append((score, i, j))
    scored.sort(key=lambda row: (-row[0], row[1], row[2]))
    repair_budget = max(2, len(nodes) // 45)
    for score, i, j in scored[:repair_budget]:
        if degree[i] >= cfg.max_node_degree or degree[j] >= cfg.max_node_degree:
            continue
        if _edge_crosses_existing(nodes, i, j, edges):
            continue
        edges.append(
            _MutableEdge(i, j, max(nodes[i].birth_epoch, nodes[j].birth_epoch), "repair_loop", score)
        )
        degree[i] += 1
        degree[j] += 1
        existing.add((min(i, j), max(i, j)))

def _close_dangling_stubs(
    cfg: FormationConfig,
    nodes: Sequence[FormationNode],
    centres: Sequence[FormationCentre],
    edges: list[_MutableEdge],
) -> None:
    """Turn a bounded fraction of severe leaves into local loops.

    Historical cities retain some cul-de-sacs, so the routine does not eliminate
    leaves globally.  It closes only leaves with a nearby planar alternative and
    a substantial current detour.
    """

    degree = [0] * len(nodes)
    incident: list[list[int]] = [[] for _ in nodes]
    existing = {edge.key for edge in edges}
    for edge_index, edge in enumerate(edges):
        degree[edge.u] += 1
        degree[edge.v] += 1
        incident[edge.u].append(edge_index)
        incident[edge.v].append(edge_index)
    leaves = [i for i, value in enumerate(degree) if value == 1]
    candidates: list[tuple[float, int, int]] = []
    for leaf in leaves:
        parent_edge = edges[incident[leaf][0]]
        parent = parent_edge.v if parent_edge.u == leaf else parent_edge.u
        parent_length = _distance(nodes[leaf], nodes[parent])
        search_radius = min(cfg.max_local_edge_m, max(260.0, 1.65 * parent_length))
        for other in range(len(nodes)):
            if other in (leaf, parent) or degree[other] >= cfg.max_node_degree:
                continue
            key = (min(leaf, other), max(leaf, other))
            if key in existing:
                continue
            length = _distance(nodes[leaf], nodes[other])
            if length > search_radius:
                continue
            if _edge_crosses_existing(nodes, leaf, other, edges):
                continue
            alignment = _orientation_alignment(nodes[leaf], nodes[other], centres)
            if alignment < max(0.50, cfg.orientation_alignment_floor):
                continue
            detour = _shortest_path_length(nodes, edges, leaf, other) / max(length, 1.0)
            if detour < 1.65:
                continue
            score = detour - 1.0 + 0.35 * alignment - 0.12 * length / search_radius
            candidates.append((score, leaf, other))
    candidates.sort(key=lambda row: (-row[0], row[1], row[2]))
    budget = max(1, int(round(0.48 * len(leaves))))
    used_leaves: set[int] = set()
    for score, leaf, other in candidates:
        if len(used_leaves) >= budget:
            break
        if leaf in used_leaves or degree[leaf] != 1 or degree[other] >= cfg.max_node_degree:
            continue
        if _edge_crosses_existing(nodes, leaf, other, edges):
            continue
        edge = _MutableEdge(
            leaf, other, max(nodes[leaf].birth_epoch, nodes[other].birth_epoch),
            "culdesac_closure", score,
        )
        edges.append(edge)
        existing.add(edge.key)
        degree[leaf] += 1
        degree[other] += 1
        used_leaves.add(leaf)

build_causal_growth_network = _build_causal_growth_network
repair_local_connectivity = _repair_local_connectivity
close_dangling_stubs = _close_dangling_stubs
distance = _distance
orientation_alignment = _orientation_alignment
segments_cross = _segments_cross
