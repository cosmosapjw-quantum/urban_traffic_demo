"""Deterministic centre and settlement sampling for formative urban growth."""

from __future__ import annotations

import math
import random
from typing import Sequence

from metroflow.city.formative_growth_model import (
    FormationCentre,
    FormationConfig,
    FormationNode,
)

__all__ = ["build_centres", "generate_nodes"]

def _build_centres(
    cfg: FormationConfig,
    width_m: float,
    height_m: float,
    rng: random.Random,
) -> list[FormationCentre]:
    base = [
        (0.43, 0.54, 0, 1.00, math.radians(12.0)),
        (0.72, 0.42, 2, 0.70, math.radians(-18.0)),
        (0.27, 0.28, 3, 0.58, math.radians(37.0)),
        (0.70, 0.74, 4, 0.45, math.radians(8.0)),
        (0.20, 0.70, 4, 0.42, math.radians(-35.0)),
    ]
    keep = 1 + cfg.secondary_centre_count
    centres: list[FormationCentre] = []
    for centre_id, (fx, fy, birth, attraction, angle) in enumerate(base[:keep]):
        jitter_x = rng.uniform(-0.018, 0.018) * width_m
        jitter_y = rng.uniform(-0.018, 0.018) * height_m
        centres.append(
            FormationCentre(
                centre_id=centre_id,
                x_m=min(max((fx * width_m) + jitter_x, 0.08 * width_m), 0.92 * width_m),
                y_m=min(max((fy * height_m) + jitter_y, 0.08 * height_m), 0.92 * height_m),
                birth_epoch=min(birth, cfg.epochs - 1),
                attraction=attraction,
                local_grid_angle_rad=angle + rng.uniform(-0.08, 0.08),
            )
        )
    return centres

def _epoch_counts(node_count: int, epochs: int) -> list[int]:
    weights = [1.00 + 0.18 * e for e in range(epochs)]
    total = sum(weights)
    raw = [node_count * w / total for w in weights]
    counts = [int(math.floor(v)) for v in raw]
    remaining = node_count - sum(counts)
    order = sorted(range(epochs), key=lambda i: (raw[i] - counts[i], -i), reverse=True)
    for i in order[:remaining]:
        counts[i] += 1
    return counts

def _generate_nodes(
    cfg: FormationConfig,
    width_m: float,
    height_m: float,
    centres: Sequence[FormationCentre],
    rng: random.Random,
) -> list[FormationNode]:
    nodes: list[FormationNode] = []
    counts = _epoch_counts(cfg.node_count, cfg.epochs)
    diagonal = math.hypot(width_m, height_m)
    max_radius = 0.53 * diagonal

    # Unborn nuclei must not reserve space in an earlier epoch.  This is a
    # causal intervention contract, not just a timestamp attached after sampling.
    for epoch in range(cfg.epochs):
        born = sorted((c for c in centres if c.birth_epoch == epoch), key=lambda c: c.centre_id)
        inserted = 0
        for centre in born:
            if any(math.hypot(centre.x_m-n.x_m, centre.y_m-n.y_m) < 1e-8 for n in nodes):
                # A new centre can occupy an existing junction; do not create
                # a zero-length duplicate. Allocate its node budget below.
                continue
            nodes.append(FormationNode(len(nodes), centre.x_m, centre.y_m,
                                       epoch, centre.centre_id, "nucleus"))
            inserted += 1
        needed = counts[epoch] - inserted
        if needed <= 0:
            continue
        progress = epoch / max(cfg.epochs - 1, 1)
        p_explore = cfg.exploration_start + (
            cfg.exploration_end - cfg.exploration_start
        ) * progress
        active_centres = [c for c in centres if c.birth_epoch <= epoch]
        attempts = 0
        accepted = 0
        while accepted < needed:
            attempts += 1
            if attempts > max(4_000, needed * 250):
                # Deterministic fail-closed fallback: reduce spacing but retain
                # the same phase and distribution family.
                relaxation = min(0.42, 0.02 * (attempts // max(needed * 20, 1)))
            else:
                relaxation = 0.0

            mode_roll = rng.random()
            if mode_roll < p_explore:
                mode = "exploration"
            elif mode_roll < p_explore + 0.14 and len(active_centres) > 1:
                mode = "corridor"
            else:
                mode = "densification"

            if mode == "corridor":
                a, b = rng.sample(active_centres, 2)
                t = min(max(rng.betavariate(1.8, 1.8), 0.05), 0.95)
                x = (1.0 - t) * a.x_m + t * b.x_m
                y = (1.0 - t) * a.y_m + t * b.y_m
                normal_angle = math.atan2(b.y_m - a.y_m, b.x_m - a.x_m) + math.pi / 2.0
                offset = rng.gauss(0.0, 95.0 + 22.0 * epoch)
                x += offset * math.cos(normal_angle)
                y += offset * math.sin(normal_angle)
                centre = a if t < 0.5 else b
                min_sep = (105.0 + 8.0 * epoch) * (1.0 - relaxation)
            else:
                centre = _weighted_choice(
                    active_centres,
                    [c.attraction * (1.0 + 0.18 * (epoch - c.birth_epoch)) for c in active_centres],
                    rng,
                )
                age = max(0, epoch - centre.birth_epoch)
                if mode == "densification":
                    # Gamma-like radius makes a dense core while retaining a tail.
                    scale = 210.0 + 62.0 * age + 25.0 * epoch
                    radius = min(rng.gammavariate(2.0, scale), 0.31 * diagonal)
                    min_sep = (92.0 + 6.0 * epoch + 4.0 * age) * (1.0 - relaxation)
                else:
                    frontier = (0.14 + 0.37 * progress) * max_radius
                    radius = frontier * rng.uniform(0.78, 1.12)
                    min_sep = (150.0 + 17.0 * epoch) * (1.0 - relaxation)

                if mode == "exploration" and rng.random() < 0.72:
                    axis = centre.local_grid_angle_rad + rng.choice((0.0, math.pi / 2.0, math.pi, -math.pi / 2.0))
                    theta = axis + rng.gauss(0.0, 0.33)
                else:
                    theta = rng.uniform(-math.pi, math.pi)
                anisotropy = 1.0 + 0.34 * math.sin(0.7 * centre.centre_id + 0.5)
                local_x = radius * math.cos(theta) * anisotropy
                local_y = radius * math.sin(theta) / anisotropy
                ca = math.cos(centre.local_grid_angle_rad)
                sa = math.sin(centre.local_grid_angle_rad)
                x = centre.x_m + ca * local_x - sa * local_y
                y = centre.y_m + sa * local_x + ca * local_y

                # Mature districts inherit a local survey frame.  Snapping is
                # partial and jittered, so historical irregularity remains while
                # the network no longer degenerates into an isotropic Voronoi web.
                snap_probability = 0.76 - 0.025 * epoch
                if mode == "densification" and rng.random() < snap_probability:
                    spacing = 135.0 + 11.0 * epoch + 18.0 * centre.birth_epoch
                    dx = x - centre.x_m
                    dy = y - centre.y_m
                    local_x = ca * dx + sa * dy
                    local_y = -sa * dx + ca * dy
                    local_x = round(local_x / spacing) * spacing + rng.gauss(0.0, 0.075 * spacing)
                    local_y = round(local_y / spacing) * spacing + rng.gauss(0.0, 0.075 * spacing)
                    x = centre.x_m + ca * local_x - sa * local_y
                    y = centre.y_m + sa * local_x + ca * local_y

            # A soft superellipse frontier avoids a map-filling rectangle while
            # still admitting polycentric lobes.
            nx = (x - 0.5 * width_m) / (0.49 * width_m)
            ny = (y - 0.5 * height_m) / (0.49 * height_m)
            if abs(nx) ** 3.2 + abs(ny) ** 3.2 > 1.0:
                continue
            if not (0.025 * width_m <= x <= 0.975 * width_m):
                continue
            if not (0.025 * height_m <= y <= 0.975 * height_m):
                continue
            if any(math.hypot(x - n.x_m, y - n.y_m) < min_sep for n in nodes):
                continue

            nodes.append(
                FormationNode(
                    node_id=len(nodes),
                    x_m=x,
                    y_m=y,
                    birth_epoch=epoch,
                    centre_id=centre.centre_id,
                    mode=mode,
                )
            )
            accepted += 1

    nodes.sort(key=lambda n: (n.birth_epoch, n.node_id))
    return [
        FormationNode(
            node_id=i,
            x_m=n.x_m,
            y_m=n.y_m,
            birth_epoch=n.birth_epoch,
            centre_id=n.centre_id,
            mode=n.mode,
        )
        for i, n in enumerate(nodes)
    ]

def _weighted_choice(items: Sequence[FormationCentre], weights: Sequence[float], rng: random.Random) -> FormationCentre:
    total = sum(max(0.0, w) for w in weights)
    if total <= 0.0:
        return items[0]
    target = rng.random() * total
    running = 0.0
    for item, weight in zip(items, weights, strict=True):
        running += max(0.0, weight)
        if target <= running:
            return item
    return items[-1]

build_centres = _build_centres
generate_nodes = _generate_nodes
