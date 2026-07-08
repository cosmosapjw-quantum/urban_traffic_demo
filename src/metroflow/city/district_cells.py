from __future__ import annotations

import math
from typing import Any

__all__ = ["build_district_cells"]


def build_district_cells(*, morphology_field: dict[str, Any]) -> dict[str, Any]:
    centers = tuple(morphology_field.get("district_centers", ()) or ())
    bounds = tuple(morphology_field.get("district_envelope_bounds", ()) or ())
    seed = int(morphology_field.get("seed", 0))
    phase = (seed % 23) * 0.053

    district_cells: list[dict[str, Any]] = []
    district_cell_bounds: list[tuple[float, float, float, float]] = []
    irregularity_scores: list[float] = []
    regimes = ("civic_core", "mixed_midrise", "residential_edge", "commercial_spine")

    for district_index, (center, bound) in enumerate(zip(centers, bounds)):
        district_id = f"district_{district_index}"
        local_offsets = _cell_offsets(district_index)
        span_x = max(float(bound[2]) - float(bound[0]), 1.0)
        span_y = max(float(bound[3]) - float(bound[1]), 1.0)
        for cell_index, (offset_x, offset_y) in enumerate(local_offsets):
            cx = float(center[0]) + (offset_x * span_x * 0.28) + math.sin(phase + district_index + cell_index) * span_x * 0.03
            cy = float(center[1]) + (offset_y * span_y * 0.26) + math.cos(phase - district_index + cell_index) * span_y * 0.03
            skew_x = math.sin(phase + district_index * 0.41 + cell_index) * span_x * 0.06
            skew_y = math.cos(phase - district_index * 0.37 + cell_index) * span_y * 0.05
            cell_polygon = _cell_polygon(
                center=(cx, cy),
                span_x=span_x * (0.18 if district_index == 0 else 0.15),
                span_y=span_y * (0.17 if district_index == 0 else 0.14),
                skew_x=skew_x,
                skew_y=skew_y,
                phase=phase + district_index * 0.18 + cell_index * 0.31,
            )
            subdivision_points = _subdivision_points(
                polygon=cell_polygon,
                center=(cx, cy),
                phase=phase + district_index * 0.23 + cell_index * 0.17,
            )
            xs = [point[0] for point in cell_polygon]
            ys = [point[1] for point in cell_polygon]
            district_cell_bounds.append((min(xs), min(ys), max(xs), max(ys)))
            irregularity_scores.append(
                ((abs(skew_x) / max(span_x, 1.0)) + (abs(skew_y) / max(span_y, 1.0))) * 2.8
            )
            district_cells.append(
                {
                    "cell_id": f"{district_id}_cell_{cell_index}",
                    "district_id": district_id,
                    "regime": regimes[(district_index + cell_index) % len(regimes)],
                    "center": (round(cx, 3), round(cy, 3)),
                    "polygon": cell_polygon,
                    "subdivision_points": subdivision_points,
                    "density_target": round(1.35 - min(abs(offset_x) + abs(offset_y), 1.0) * 0.32, 3),
                }
            )

    max_span = max(
        max(float(bound[2]) - float(bound[0]), float(bound[3]) - float(bound[1]))
        for bound in bounds
    ) if bounds else 1.0
    outer_cell_share = sum(
        1
        for cell in district_cells
        if math.hypot(float(cell["center"][0]), float(cell["center"][1])) >= max_span * 0.95
    ) / max(len(district_cells), 1)

    return {
        "engine": "generator_v2_sidecar_district_cells",
        "scenario_id": morphology_field.get("scenario_id"),
        "style_id": morphology_field.get("style_id"),
        "seed": seed,
        "district_cells": tuple(district_cells),
        "district_cell_bounds": tuple(district_cell_bounds),
        "district_regimes": tuple(sorted({str(cell["regime"]) for cell in district_cells})),
        "outer_cell_share": float(outer_cell_share),
        "cell_irregularity_score": float(sum(irregularity_scores) / max(len(irregularity_scores), 1)),
    }


def _cell_offsets(district_index: int) -> tuple[tuple[float, float], ...]:
    if district_index == 0:
        return ((-0.42, -0.24), (0.30, -0.18), (-0.18, 0.34), (0.26, 0.30))
    variants = (
        ((-0.34, -0.14), (0.20, -0.04), (0.16, 0.30)),
        ((-0.26, 0.12), (0.12, -0.28), (0.28, 0.18)),
        ((-0.22, -0.30), (0.24, -0.02), (-0.04, 0.28)),
    )
    return variants[district_index % len(variants)]


def _cell_polygon(
    *,
    center: tuple[float, float],
    span_x: float,
    span_y: float,
    skew_x: float,
    skew_y: float,
    phase: float,
) -> tuple[tuple[float, float], ...]:
    points: list[tuple[float, float]] = []
    for step in range(5):
        angle = (math.tau * step) / 5.0
        radial = 0.82 + 0.14 * math.sin(angle * 2.0 + phase)
        x = center[0] + math.cos(angle) * span_x * radial + skew_x * math.sin(angle)
        y = center[1] + math.sin(angle) * span_y * radial + skew_y * math.cos(angle)
        points.append((round(x, 3), round(y, 3)))
    points.append(points[0])
    return tuple(points)


def _subdivision_points(
    *,
    polygon: tuple[tuple[float, float], ...],
    center: tuple[float, float],
    phase: float,
) -> tuple[tuple[float, float], ...]:
    points: list[tuple[float, float]] = []
    for index, vertex in enumerate(polygon[:-1]):
        weight = 0.38 + ((index % 2) * 0.06)
        x = float(center[0]) + (float(vertex[0]) - float(center[0])) * weight
        y = float(center[1]) + (float(vertex[1]) - float(center[1])) * weight
        x += math.sin(phase + index * 0.41) * 8.0
        y += math.cos(phase - index * 0.37) * 8.0
        points.append((round(x, 3), round(y, 3)))
    return tuple(points)
