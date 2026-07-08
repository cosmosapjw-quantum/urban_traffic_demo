from __future__ import annotations

import math
from typing import Any

__all__ = ["build_morphology_field"]


def build_morphology_field(
    *,
    scenario_id: str,
    seed: int,
    style_id: str,
    width: int,
    height: int,
) -> dict[str, Any]:
    scenario = str(scenario_id)
    half_w = float(width) * 0.5
    half_h = float(height) * 0.5
    phase = (int(seed) % 19) * 0.071

    downtown_anchor = (0.0, 0.0)
    subcenter_anchors = _build_subcenter_anchors(
        scenario=scenario,
        half_w=half_w,
        half_h=half_h,
    )
    inner_anchors = _build_inner_anchors(
        scenario=scenario,
        half_w=half_w,
        half_h=half_h,
    )
    district_anchors = (downtown_anchor,) + subcenter_anchors + inner_anchors

    district_envelopes: list[tuple[tuple[float, float], ...]] = []
    district_bounds: list[tuple[float, float, float, float]] = []
    envelope_areas: list[float] = []
    for index, anchor in enumerate(district_anchors):
        if index == 0:
            radius_x = half_w * 0.20
            radius_y = half_h * 0.17
        elif index <= len(subcenter_anchors):
            radius_x = half_w * (0.115 + ((index % 3) * 0.010))
            radius_y = half_h * (0.105 + ((index % 2) * 0.015))
        else:
            radius_x = half_w * (0.145 + ((index % 2) * 0.010))
            radius_y = half_h * (0.125 + ((index % 2) * 0.014))
        skew_x = (index - 2) * half_w * 0.010
        skew_y = ((index % 2) - 0.5) * half_h * 0.018
        envelope = _organic_envelope(
            center=anchor,
            radius_x=radius_x,
            radius_y=radius_y,
            phase=phase + index * 0.27,
            skew_x=skew_x,
            skew_y=skew_y,
        )
        district_envelopes.append(envelope)
        xs = [point[0] for point in envelope]
        ys = [point[1] for point in envelope]
        district_bounds.append((min(xs), min(ys), max(xs), max(ys)))
        envelope_areas.append((max(xs) - min(xs)) * (max(ys) - min(ys)))

    corridor_polylines = _build_corridor_polylines(
        downtown_anchor=downtown_anchor,
        inner_anchors=inner_anchors,
        subcenter_anchors=subcenter_anchors,
        half_w=half_w,
        half_h=half_h,
        phase=phase,
    )
    outer_ring_regular_pair_count = 0
    outer_ring_inward_bend_count = 0
    cross_ring_pair_count = 0
    subcenter_anchor_set = {tuple(anchor) for anchor in subcenter_anchors}
    for polyline in corridor_polylines:
        if len(polyline) != 3:
            continue
        left, bend, right = polyline
        if tuple(left) not in subcenter_anchor_set or tuple(right) not in subcenter_anchor_set:
            continue
        left_radius = math.hypot(float(left[0]), float(left[1]))
        right_radius = math.hypot(float(right[0]), float(right[1]))
        bend_radius = math.hypot(float(bend[0]), float(bend[1]))
        average_radius = max((left_radius + right_radius) * 0.5, 1.0)
        if bend_radius / average_radius <= 0.72:
            outer_ring_inward_bend_count += 1
        if (left[0] < 0.0) == (right[0] < 0.0) and abs(float(left[1]) - float(right[1])) <= half_h * 0.22:
            outer_ring_regular_pair_count += 1
        else:
            cross_ring_pair_count += 1
    barrier_polyline = _build_barrier_polyline(half_w=half_w, half_h=half_h, phase=phase)
    barrier_crossing_candidates = _build_barrier_crossings(corridor_polylines, barrier_polyline)

    total_area = sum(envelope_areas) or 1.0
    downtown_area = envelope_areas[0] if envelope_areas else 0.0
    outer_area = sum(envelope_areas[1 : 1 + len(subcenter_anchors)])
    inner_area = sum(envelope_areas[1 + len(subcenter_anchors) :])
    mass_min_x = min(bound[0] for bound in district_bounds)
    mass_min_y = min(bound[1] for bound in district_bounds)
    mass_max_x = max(bound[2] for bound in district_bounds)
    mass_max_y = max(bound[3] for bound in district_bounds)
    city_mass_width_ratio = (mass_max_x - mass_min_x) / max(half_w * 1.96, 1.0)
    city_mass_height_ratio = (mass_max_y - mass_min_y) / max(half_h * 1.96, 1.0)

    return {
        "engine": "generator_v2_sidecar_morphology",
        "scenario_id": scenario,
        "style_id": str(style_id),
        "seed": int(seed),
        "render_bounds": (-half_w * 0.98, half_w * 0.98, -half_h * 0.98, half_h * 0.98),
        "district_envelopes": tuple(district_envelopes),
        "district_envelope_bounds": tuple(district_bounds),
        "district_centers": tuple(district_anchors),
        "corridor_polylines": tuple(corridor_polylines),
        "corridor_influence_polylines": tuple(corridor_polylines),
        "barrier_polylines": (barrier_polyline,),
        "barrier_crossing_candidates": tuple(barrier_crossing_candidates),
        "downtown_anchor": downtown_anchor,
        "subcenter_anchors": tuple(subcenter_anchors),
        "inner_anchors": tuple(inner_anchors),
        "outer_envelope_share": float(outer_area / total_area),
        "center_bias": float((downtown_area + inner_area) / total_area),
        "city_mass_width_ratio": float(city_mass_width_ratio),
        "city_mass_height_ratio": float(city_mass_height_ratio),
        "outer_ring_regular_pair_count": int(outer_ring_regular_pair_count),
        "outer_ring_inward_bend_count": int(outer_ring_inward_bend_count),
        "cross_ring_pair_count": int(cross_ring_pair_count),
    }


def _build_subcenter_anchors(
    *,
    scenario: str,
    half_w: float,
    half_h: float,
) -> tuple[tuple[float, float], ...]:
    if scenario == "synthetic_100k":
        scales = (
            (-0.40, 0.23),
            (-0.28, 0.37),
            (0.12, 0.43),
            (0.39, 0.18),
            (-0.43, -0.16),
            (-0.14, -0.35),
            (0.24, -0.38),
            (0.36, -0.24),
        )
    else:
        scales = (
            (-0.36, 0.22),
            (-0.24, 0.33),
            (0.12, 0.38),
            (0.34, 0.18),
            (-0.38, -0.14),
            (-0.12, -0.31),
            (0.22, -0.33),
            (0.32, -0.22),
        )
    return tuple((round(half_w * scale_x, 3), round(half_h * scale_y, 3)) for scale_x, scale_y in scales)


def _build_inner_anchors(
    *,
    scenario: str,
    half_w: float,
    half_h: float,
) -> tuple[tuple[float, float], ...]:
    vertical = 0.16 if scenario == "synthetic_100k" else 0.14
    horizontal = 0.18 if scenario == "synthetic_100k" else 0.16
    return (
        (-half_w * horizontal, half_h * vertical),
        (half_w * horizontal, half_h * vertical * 0.92),
        (-half_w * horizontal * 0.96, -half_h * vertical),
        (half_w * horizontal * 1.04, -half_h * vertical * 0.88),
    )


def _organic_envelope(
    *,
    center: tuple[float, float],
    radius_x: float,
    radius_y: float,
    phase: float,
    skew_x: float,
    skew_y: float,
) -> tuple[tuple[float, float], ...]:
    points: list[tuple[float, float]] = []
    for step in range(8):
        angle = (math.tau * step) / 8.0
        radial = 0.88 + 0.18 * math.sin(angle * 2.0 + phase) + 0.08 * math.cos(angle * 3.0 - phase)
        x = center[0] + math.cos(angle) * radius_x * radial + skew_x * math.sin(angle)
        y = center[1] + math.sin(angle) * radius_y * radial + skew_y * math.cos(angle)
        points.append((round(x, 3), round(y, 3)))
    points.append(points[0])
    return tuple(points)


def _build_corridor_polylines(
    *,
    downtown_anchor: tuple[float, float],
    inner_anchors: tuple[tuple[float, float], ...],
    subcenter_anchors: tuple[tuple[float, float], ...],
    half_w: float,
    half_h: float,
    phase: float,
) -> tuple[tuple[tuple[float, float], ...], ...]:
    corridors: list[tuple[tuple[float, float], ...]] = []
    for index, anchor in enumerate(inner_anchors):
        bend = (
            round((anchor[0] * 0.58) + math.sin(phase + index) * half_w * 0.020, 3),
            round((anchor[1] * 0.54) + math.cos(phase - index) * half_h * 0.024, 3),
        )
        corridors.append((downtown_anchor, bend, anchor))

    anchor_groups = (
        (0, 1),
        (2, 3),
        (4, 5),
        (6, 7),
    )
    for inner_index, subcenter_indices in enumerate(anchor_groups):
        inner_anchor = inner_anchors[inner_index % len(inner_anchors)]
        for spoke_index, subcenter_index in enumerate(subcenter_indices):
            anchor = subcenter_anchors[subcenter_index]
            bend = (
                round((inner_anchor[0] + anchor[0]) * 0.5 + math.sin(phase + subcenter_index) * half_w * 0.022, 3),
                round((inner_anchor[1] + anchor[1]) * 0.5 + math.cos(phase - subcenter_index) * half_h * 0.026, 3),
            )
            if spoke_index == 1:
                bend = (
                    round(bend[0] + math.copysign(half_w * 0.018, anchor[0] - inner_anchor[0]), 3),
                    round(bend[1] + math.copysign(half_h * 0.016, anchor[1] - inner_anchor[1]), 3),
                )
            corridors.append((inner_anchor, bend, anchor))

    inner_ring_pairs = (
        (inner_anchors[0], inner_anchors[1]),
        (inner_anchors[1], inner_anchors[3]),
        (inner_anchors[3], inner_anchors[2]),
        (inner_anchors[2], inner_anchors[0]),
    )
    for index, (left, right) in enumerate(inner_ring_pairs):
        midpoint = (
            round((left[0] + right[0]) * 0.5 + math.sin(phase + index * 0.37) * half_w * 0.018, 3),
            round((left[1] + right[1]) * 0.5 + math.cos(phase - index * 0.29) * half_h * 0.018, 3),
        )
        corridors.append((left, midpoint, right))

    regular_ring_pairs = (
        (subcenter_anchors[0], subcenter_anchors[1]),
        (subcenter_anchors[6], subcenter_anchors[7]),
    )
    broken_fringe_pairs = (
        (subcenter_anchors[1], subcenter_anchors[3]),
        (subcenter_anchors[0], subcenter_anchors[2]),
        (subcenter_anchors[4], subcenter_anchors[6]),
        (subcenter_anchors[5], subcenter_anchors[7]),
        (subcenter_anchors[0], subcenter_anchors[5]),
        (subcenter_anchors[2], subcenter_anchors[7]),
        (subcenter_anchors[3], subcenter_anchors[6]),
    )
    for index, (left, right) in enumerate(regular_ring_pairs):
        midpoint = (
            round((left[0] + right[0]) * 0.5 + math.sin(phase + index * 0.31) * half_w * 0.020, 3),
            round((left[1] + right[1]) * 0.5 + math.cos(phase - index * 0.27) * half_h * 0.022, 3),
        )
        midpoint = (
            round(midpoint[0] * 0.82, 3),
            round(midpoint[1] * 0.82, 3),
        )
        corridors.append((left, midpoint, right))
    for index, (left, right) in enumerate(broken_fringe_pairs):
        midpoint = (
            round((left[0] + right[0]) * 0.5 + math.sin(phase + index * 0.29) * half_w * 0.030, 3),
            round((left[1] + right[1]) * 0.5 + math.cos(phase - index * 0.23) * half_h * 0.034, 3),
        )
        inward_pull = 0.30 + ((index % 3) * 0.04)
        midpoint = (
            round(midpoint[0] * (1.0 - inward_pull), 3),
            round(midpoint[1] * (1.0 - inward_pull), 3),
        )
        corridors.append((left, midpoint, right))
    return tuple(corridors)


def _build_barrier_polyline(*, half_w: float, half_h: float, phase: float) -> tuple[tuple[float, float], ...]:
    points: list[tuple[float, float]] = []
    for step in range(11):
        frac = step / 10.0
        x = -half_w * 0.72 + frac * half_w * 1.44
        y = (
            math.sin((frac * math.pi * 1.45) + phase) * half_h * 0.07
            + math.cos((frac * math.pi * 0.55) - phase) * half_h * 0.03
        )
        points.append((round(x, 3), round(y, 3)))
    return tuple(points)


def _build_barrier_crossings(
    corridor_polylines: tuple[tuple[tuple[float, float], ...], ...],
    barrier_polyline: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    if not barrier_polyline:
        return ()
    candidates: list[tuple[float, float]] = []
    for polyline in corridor_polylines[:4]:
        if len(polyline) < 2:
            continue
        left = polyline[0]
        right = polyline[1]
        candidates.append(
            (
                round((float(left[0]) + float(right[0])) * 0.5, 3),
                round((float(left[1]) + float(right[1])) * 0.5, 3),
            )
        )
    return tuple(candidates)
