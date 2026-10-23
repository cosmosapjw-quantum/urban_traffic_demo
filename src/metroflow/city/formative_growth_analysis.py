"""Planar faces, morphometrics, and adversarial structural audit."""

from __future__ import annotations

import hashlib
import math
import statistics
from typing import Mapping, Sequence

from metroflow.city.formative_growth_model import (
    FormationBlock,
    FormationCentre,
    FormationConfig,
    FormationEdge,
    FormationNode,
    _EPS,
)
from metroflow.city.formative_growth_network import (
    orientation_alignment as _orientation_alignment,
    segments_cross as _segments_cross,
)

__all__ = ["extract_planar_blocks", "compute_formation_metrics", "audit_formation_map"]

def _polygon_area(points: Sequence[tuple[float, float]]) -> float:
    return 0.5 * sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True)
    )

def _polygon_centroid(points: Sequence[tuple[float, float]], signed_area: float) -> tuple[float, float]:
    if abs(signed_area) < _EPS:
        return (
            sum(x for x, _ in points) / len(points),
            sum(y for _, y in points) / len(points),
        )
    factor = 1.0 / (6.0 * signed_area)
    cx = factor * sum(
        (x1 + x2) * (x1 * y2 - x2 * y1)
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True)
    )
    cy = factor * sum(
        (y1 + y2) * (x1 * y2 - x2 * y1)
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True)
    )
    return cx, cy

def _canonical_cycle(cycle: Sequence[int]) -> tuple[int, ...]:
    seq = tuple(cycle)
    rotations = [seq[i:] + seq[:i] for i in range(len(seq))]
    reverse = tuple(reversed(seq))
    rotations.extend(reverse[i:] + reverse[:i] for i in range(len(reverse)))
    return min(rotations)

def extract_planar_blocks(
    cfg: FormationConfig,
    nodes: Sequence[FormationNode],
    edges: Sequence[FormationEdge],
    centres: Sequence[FormationCentre],
) -> list[FormationBlock]:
    neighbours: dict[int, list[int]] = {n.node_id: [] for n in nodes}
    for edge in edges:
        neighbours[edge.u].append(edge.v)
        neighbours[edge.v].append(edge.u)
    for node_id, values in neighbours.items():
        origin = nodes[node_id]
        values.sort(key=lambda v: math.atan2(nodes[v].y_m - origin.y_m, nodes[v].x_m - origin.x_m))

    visited: set[tuple[int, int]] = set()
    cycles: dict[tuple[int, ...], tuple[int, ...]] = {}
    for edge in edges:
        for start in ((edge.u, edge.v), (edge.v, edge.u)):
            if start in visited:
                continue
            u, v = start
            cycle: list[int] = []
            current = (u, v)
            for _ in range(max(8, 4 * len(edges))):
                if current in visited:
                    break
                visited.add(current)
                a, b = current
                cycle.append(a)
                around = neighbours[b]
                if not around:
                    break
                try:
                    incoming_index = around.index(a)
                except ValueError:
                    break
                # Immediate clockwise neighbour keeps the face on the left.
                c = around[(incoming_index - 1) % len(around)]
                current = (b, c)
                if current == start:
                    if len(cycle) >= 3:
                        canonical = _canonical_cycle(cycle)
                        cycles[canonical] = tuple(cycle)
                    break

    max_area = cfg.urbanized_area_km2 * 1_000_000.0 * cfg.max_block_area_fraction
    raw: list[tuple[tuple[int, ...], float, float, float]] = []
    for cycle in cycles.values():
        points = [(nodes[i].x_m, nodes[i].y_m) for i in cycle]
        signed = _polygon_area(points)
        # With the traversal convention, bounded faces are counter-clockwise.
        if signed <= cfg.min_block_area_m2 or signed >= max_area:
            continue
        cx, cy = _polygon_centroid(points, signed)
        raw.append((cycle, signed, cx, cy))
    raw.sort(key=lambda row: (round(row[2], 6), round(row[3], 6), row[0]))

    blocks: list[FormationBlock] = []
    primary_midpoints = [
        (
            0.5 * (nodes[e.u].x_m + nodes[e.v].x_m),
            0.5 * (nodes[e.u].y_m + nodes[e.v].y_m),
        )
        for e in edges
        if e.hierarchy == "primary"
    ]
    for block_id, (cycle, area, cx, cy) in enumerate(raw):
        nearest = min(centres, key=lambda c: math.hypot(cx - c.x_m, cy - c.y_m))
        dist = math.hypot(cx - nearest.x_m, cy - nearest.y_m)
        arterial_dist = min(
            (math.hypot(cx - x, cy - y) for x, y in primary_midpoints),
            default=math.inf,
        )
        mean_birth = sum(nodes[i].birth_epoch for i in cycle) / len(cycle)
        if nearest.centre_id == 0 and dist < 720.0:
            land_use = "commercial"
        elif arterial_dist < 190.0 and dist < 1_500.0:
            land_use = "mixed"
        elif cx > 0.79 * math.sqrt(cfg.urbanized_area_km2 * 1_000_000.0 * cfg.aspect_ratio) and cy < 0.46 * (
            math.sqrt(cfg.urbanized_area_km2 * 1_000_000.0 * cfg.aspect_ratio) / cfg.aspect_ratio
        ):
            land_use = "industrial"
        elif area > 130_000.0 and int(hashlib.sha256(f"{cfg.seed}:{block_id}:park".encode()).hexdigest()[:8], 16) % 11 == 0:
            land_use = "park"
        elif dist < 1_000.0:
            land_use = "mixed"
        else:
            land_use = "residential"
        blocks.append(
            FormationBlock(
                block_id=block_id,
                node_ids=tuple(cycle),
                area_m2=area,
                centroid_x_m=cx,
                centroid_y_m=cy,
                land_use=land_use,
                mean_birth_epoch=mean_birth,
            )
        )
    return blocks

def _rank(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: (values[i], i))
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        rank = 0.5 * (i + j - 1) + 1.0
        for k in range(i, j):
            ranks[order[k]] = rank
        i = j
    return ranks

def _pearson(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b) or len(a) < 2:
        return 0.0
    ma = statistics.fmean(a)
    mb = statistics.fmean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da > 0.0 and db > 0.0 else 0.0

def _orientation_entropy(nodes: Sequence[FormationNode], edges: Sequence[FormationEdge], bins: int = 18) -> float:
    counts = [0] * bins
    for edge in edges:
        a, b = nodes[edge.u], nodes[edge.v]
        angle = math.atan2(b.y_m - a.y_m, b.x_m - a.x_m) % math.pi
        counts[min(bins - 1, int(angle / math.pi * bins))] += 1
    total = sum(counts)
    if total == 0:
        return 0.0
    return -sum((c / total) * math.log(c / total) for c in counts if c)

def _crossing_count(nodes: Sequence[FormationNode], edges: Sequence[FormationEdge]) -> int:
    count = 0
    for i, edge in enumerate(edges):
        for other in edges[i + 1 :]:
            if _segments_cross(nodes[edge.u], nodes[edge.v], nodes[other.u], nodes[other.v]):
                count += 1
    return count

def _component_count(node_count: int, edges: Sequence[FormationEdge], *, hierarchy: str | None = None) -> int:
    selected = [e for e in edges if hierarchy is None or e.hierarchy == hierarchy]
    active_nodes = {e.u for e in selected} | {e.v for e in selected}
    if not active_nodes:
        return 0
    adj = {i: [] for i in active_nodes}
    for edge in selected:
        adj[edge.u].append(edge.v)
        adj[edge.v].append(edge.u)
    seen: set[int] = set()
    components = 0
    for start in sorted(active_nodes):
        if start in seen:
            continue
        components += 1
        stack = [start]
        seen.add(start)
        while stack:
            u = stack.pop()
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
    return components

def compute_formation_metrics(
    cfg: FormationConfig,
    width_m: float,
    height_m: float,
    centres: Sequence[FormationCentre],
    nodes: Sequence[FormationNode],
    edges: Sequence[FormationEdge],
    blocks: Sequence[FormationBlock],
) -> dict[str, float | int | str]:
    degree = [0] * len(nodes)
    for edge in edges:
        degree[edge.u] += 1
        degree[edge.v] += 1
    edge_lengths = [e.length_m for e in edges]
    block_areas = [b.area_m2 for b in blocks]
    main = centres[0]
    radii = [math.hypot(n.x_m - main.x_m, n.y_m - main.y_m) for n in nodes]
    epochs = [float(n.birth_epoch) for n in nodes]
    age_radius_spearman = _pearson(_rank(radii), _rank(epochs))
    orientation_entropy = _orientation_entropy(nodes, edges)
    max_entropy = math.log(18.0)
    local_orientation_coherence = (
        statistics.fmean(_orientation_alignment(nodes[e.u], nodes[e.v], centres) for e in edges)
        if edges else 0.0
    )
    old_lengths = [
        e.length_m for e in edges if max(nodes[e.u].birth_epoch, nodes[e.v].birth_epoch) <= 2
    ]
    fringe_lengths = [
        e.length_m for e in edges if min(nodes[e.u].birth_epoch, nodes[e.v].birth_epoch) >= cfg.epochs - 2
    ]
    total_road_km = sum(edge_lengths) / 1_000.0
    area = width_m * height_m
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "mean_degree": (2.0 * len(edges) / len(nodes)) if nodes else 0.0,
        "dead_end_share": (sum(d == 1 for d in degree) / len(nodes)) if nodes else 0.0,
        "four_way_share": (sum(d == 4 for d in degree) / len(nodes)) if nodes else 0.0,
        "cycle_rank": len(edges) - len(nodes) + 1,
        "block_count": len(blocks),
        "median_block_area_m2": statistics.median(block_areas) if block_areas else 0.0,
        "block_area_cv": (statistics.pstdev(block_areas) / statistics.fmean(block_areas)) if len(block_areas) > 1 else 0.0,
        "median_edge_length_m": statistics.median(edge_lengths) if edge_lengths else 0.0,
        "p90_edge_length_m": statistics.quantiles(edge_lengths, n=10)[8] if len(edge_lengths) >= 10 else (max(edge_lengths) if edge_lengths else 0.0),
        "old_core_median_edge_length_m": statistics.median(old_lengths) if old_lengths else 0.0,
        "fringe_median_edge_length_m": statistics.median(fringe_lengths) if fringe_lengths else 0.0,
        "road_density_km_per_km2": total_road_km / cfg.urbanized_area_km2,
        "orientation_entropy": orientation_entropy,
        "orientation_entropy_normalized": orientation_entropy / max_entropy if max_entropy > 0.0 else 0.0,
        "local_orientation_coherence": local_orientation_coherence,
        "age_radius_spearman": age_radius_spearman,
        "crossing_count": _crossing_count(nodes, edges),
        "connected_components": _component_count(len(nodes), edges),
        "primary_components": _component_count(len(nodes), edges, hierarchy="primary"),
        "primary_edge_share": sum(e.hierarchy == "primary" for e in edges) / len(edges) if edges else 0.0,
        "secondary_edge_share": sum(e.hierarchy == "secondary" for e in edges) / len(edges) if edges else 0.0,
        "formation_model": "causal_exploration_densification_planar_gabriel_v1",
    }

def audit_formation_map(
    cfg: FormationConfig,
    width_m: float,
    height_m: float,
    centres: Sequence[FormationCentre],
    nodes: Sequence[FormationNode],
    edges: Sequence[FormationEdge],
    blocks: Sequence[FormationBlock],
    metrics: Mapping[str, float | int | str],
) -> dict[str, object]:
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, value: object, criterion: str, severity: str = "error") -> None:
        checks.append({
            "name": name,
            "passed": bool(passed),
            "value": value,
            "criterion": criterion,
            "severity": severity,
        })

    add("node_count_exact", int(metrics["node_count"]) == cfg.node_count, metrics["node_count"], f"== {cfg.node_count}")
    add("connected", int(metrics["connected_components"]) == 1, metrics["connected_components"], "== 1")
    add("planar_no_crossings", int(metrics["crossing_count"]) == 0, metrics["crossing_count"], "== 0")
    add("mean_degree_band", 2.45 <= float(metrics["mean_degree"]) <= 3.35, metrics["mean_degree"], "2.45 <= k <= 3.35")
    add("dead_end_band", 0.03 <= float(metrics["dead_end_share"]) <= 0.28, metrics["dead_end_share"], "0.03 <= share <= 0.28", "warning")
    add("loop_presence", int(metrics["cycle_rank"]) >= max(8, cfg.node_count // 8), metrics["cycle_rank"], f">= {max(8, cfg.node_count // 8)}")
    add("bounded_faces", int(metrics["block_count"]) >= max(6, cfg.node_count // 12), metrics["block_count"], f">= {max(6, cfg.node_count // 12)}")
    add("global_orientation_diversity", 0.55 <= float(metrics["orientation_entropy_normalized"]) <= 1.0, metrics["orientation_entropy_normalized"], "0.55 <= H/Hmax <= 1.0", "warning")
    add("local_orientation_coherence", float(metrics["local_orientation_coherence"]) >= 0.72, metrics["local_orientation_coherence"], ">= 0.72", "warning")
    add("outward_age_gradient", float(metrics["age_radius_spearman"]) >= 0.22, metrics["age_radius_spearman"], ">= 0.22", "warning")
    add("road_density_band", 4.0 <= float(metrics["road_density_km_per_km2"]) <= 20.0, metrics["road_density_km_per_km2"], "4 <= km/km2 <= 20", "warning")
    add("hierarchy_present", float(metrics["primary_edge_share"]) >= 0.05 and float(metrics["secondary_edge_share"]) >= 0.12, {"primary": metrics["primary_edge_share"], "secondary": metrics["secondary_edge_share"]}, "primary >= 0.05 and secondary >= 0.12")
    add("primary_backbone_connected", int(metrics["primary_components"]) == 1, metrics["primary_components"], "== 1")
    add("block_area_variation", float(metrics["block_area_cv"]) >= 0.28, metrics["block_area_cv"], ">= 0.28", "warning")

    errors = [c for c in checks if not c["passed"] and c["severity"] == "error"]
    warnings = [c for c in checks if not c["passed"] and c["severity"] == "warning"]
    return {
        "status": "PASS" if not errors else "FAIL",
        "error_count": len(errors),
        "warning_count": len(warnings),
        "checks": checks,
        "scope": "structural plausibility only; not empirical realism validation",
    }
