from __future__ import annotations

import math
from typing import Any

from .morphology_reference import get_morphology_archetype

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
    archetype = get_morphology_archetype(style_id)
    downtown_anchor, subcenter_anchors, inner_anchors, district_orientations = (
        _build_archetype_anchors(
            style_id=archetype.style_id,
            scenario=scenario,
            seed=int(seed),
            half_w=half_w,
            half_h=half_h,
        )
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

    corridor_polylines = _build_archetype_corridor_polylines(
        style_id=archetype.style_id,
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
    barrier_polyline = (
        _build_barrier_polyline(half_w=half_w, half_h=half_h, phase=phase)
        if archetype.style_id in {"ring_radial", "river_constrained"}
        else ()
    )
    barrier_crossing_candidates = (
        _build_river_crossings(corridor_polylines)
        if archetype.style_id == "river_constrained"
        else _build_barrier_crossings(corridor_polylines, barrier_polyline)
    )

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
        "morphology_center_pattern": archetype.center_pattern,
        "morphology_street_pattern": archetype.street_pattern,
        "morphology_evidence_status": archetype.evidence_status,
        "morphology_reference_cities": archetype.empirical_reference_cities,
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
        "district_orientations_degrees": tuple(district_orientations),
        "outer_envelope_share": float(outer_area / total_area),
        "center_bias": float((downtown_area + inner_area) / total_area),
        "city_mass_width_ratio": float(city_mass_width_ratio),
        "city_mass_height_ratio": float(city_mass_height_ratio),
        "outer_ring_regular_pair_count": int(outer_ring_regular_pair_count),
        "outer_ring_inward_bend_count": int(outer_ring_inward_bend_count),
        "cross_ring_pair_count": int(cross_ring_pair_count),
    }


def _build_archetype_anchors(
    *,
    style_id: str,
    scenario: str,
    seed: int,
    half_w: float,
    half_h: float,
) -> tuple[
    tuple[float, float],
    tuple[tuple[float, float], ...],
    tuple[tuple[float, float], ...],
    tuple[float, ...],
]:
    if style_id == "ring_radial":
        subcenters = _build_subcenter_anchors(
            scenario=scenario,
            half_w=half_w,
            half_h=half_h,
        )
        inner = _build_inner_anchors(
            scenario=scenario,
            half_w=half_w,
            half_h=half_h,
        )
        return (0.0, 0.0), subcenters, inner, (0.0,) * (1 + len(subcenters) + len(inner))

    if style_id == "grid_core":
        scales = (
            (-0.42, -0.36),
            (0.0, -0.36),
            (0.42, -0.36),
            (-0.42, 0.0),
            (0.42, 0.0),
            (-0.42, 0.36),
            (0.0, 0.36),
            (0.42, 0.36),
        )
        subcenters = _scaled_points(scales, half_w=half_w, half_h=half_h)
        inner = _scaled_points(
            ((-0.20, -0.18), (0.20, -0.18), (-0.20, 0.18), (0.20, 0.18)),
            half_w=half_w,
            half_h=half_h,
        )
        angle = float((seed % 5) * 2)
        return (0.0, 0.0), subcenters, inner, (angle,) * 13

    if style_id == "polycentric_tod":
        all_centers = _scaled_points(
            (
                (-0.34, -0.24),
                (0.28, -0.27),
                (-0.30, 0.27),
                (0.31, 0.24),
                (0.0, -0.03),
                (0.03, 0.39),
            ),
            half_w=half_w,
            half_h=half_h,
        )
        downtown = all_centers[0]
        subcenters = all_centers[1:]
        inner = tuple(
            (
                round((left[0] + right[0]) * 0.5, 3),
                round((left[1] + right[1]) * 0.5, 3),
            )
            for left, right in zip(all_centers, all_centers[1:] + all_centers[:1])
        )[:4]
        orientations = tuple(float((seed * 7 + index * 23) % 90) for index in range(10))
        return downtown, subcenters, inner, orientations

    if style_id == "river_constrained":
        centers = _scaled_points(
            (
                (-0.38, -0.20),
                (-0.12, -0.19),
                (0.17, -0.18),
                (0.39, -0.17),
                (-0.31, 0.22),
                (-0.02, 0.21),
                (0.28, 0.23),
            ),
            half_w=half_w,
            half_h=half_h,
        )
        downtown = centers[1]
        subcenters = centers[:1] + centers[2:]
        inner = _scaled_points(
            ((-0.21, -0.04), (0.05, -0.03), (0.30, 0.04), (-0.10, 0.06)),
            half_w=half_w,
            half_h=half_h,
        )
        return downtown, subcenters, inner, (0.0,) * 11

    if style_id == "superblock_mixed":
        centers = _scaled_points(
            (
                (-0.29, -0.25),
                (0.27, -0.24),
                (-0.28, 0.25),
                (0.29, 0.24),
                (0.0, 0.0),
            ),
            half_w=half_w,
            half_h=half_h,
        )
        inner = _scaled_points(
            ((-0.14, -0.11), (0.14, -0.11), (-0.14, 0.12), (0.14, 0.12)),
            half_w=half_w,
            half_h=half_h,
        )
        orientations = tuple((11.0, 11.0, 34.0, 34.0, 58.0, 11.0, 34.0, 58.0, 11.0, 34.0))
        return centers[4], centers[:4], inner, orientations

    # Organic anchors are deterministic accretions rather than an ordered shell.
    points: list[tuple[float, float]] = []
    for index in range(9):
        angle = (index * 2.399963229728653) + seed * 0.071
        radius = 0.13 + index * 0.035
        points.append(
            (
                round(math.cos(angle) * half_w * radius, 3),
                round(math.sin(angle) * half_h * radius * (0.82 + (index % 3) * 0.09), 3),
            )
        )
    downtown = points[2]
    subcenters = tuple(points[:2] + points[3:7])
    inner = tuple(points[7:]) + ((round(-half_w * 0.08, 3), round(half_h * 0.05, 3)),)
    orientations = tuple(float((seed * 13 + index * 37) % 180) for index in range(10))
    return downtown, subcenters, inner, orientations


def _scaled_points(
    scales: tuple[tuple[float, float], ...],
    *,
    half_w: float,
    half_h: float,
) -> tuple[tuple[float, float], ...]:
    return tuple(
        (round(half_w * scale_x, 3), round(half_h * scale_y, 3))
        for scale_x, scale_y in scales
    )


def _build_archetype_corridor_polylines(
    *,
    style_id: str,
    downtown_anchor: tuple[float, float],
    inner_anchors: tuple[tuple[float, float], ...],
    subcenter_anchors: tuple[tuple[float, float], ...],
    half_w: float,
    half_h: float,
    phase: float,
) -> tuple[tuple[tuple[float, float], ...], ...]:
    if style_id == "ring_radial":
        return _build_corridor_polylines(
            downtown_anchor=downtown_anchor,
            inner_anchors=inner_anchors,
            subcenter_anchors=subcenter_anchors,
            half_w=half_w,
            half_h=half_h,
            phase=phase,
        )
    if style_id == "grid_core":
        x_values = tuple(round(half_w * value, 3) for value in (-0.48, -0.24, 0.0, 0.24, 0.48))
        y_values = tuple(round(half_h * value, 3) for value in (-0.44, -0.22, 0.0, 0.22, 0.44))
        return tuple(tuple((x, y) for x in x_values) for y in y_values) + tuple(
            tuple((x, y) for y in y_values) for x in x_values
        )
    if style_id == "river_constrained":
        x_values = tuple(round(half_w * value, 3) for value in (-0.50, -0.26, 0.0, 0.26, 0.50))
        y_values = tuple(round(half_h * value, 3) for value in (-0.30, -0.16, 0.16, 0.30))
        longitudinal = tuple(tuple((x, y) for x in x_values) for y in y_values)
        crossings = tuple(
            ((x, y_values[0]), (x, y_values[1]), (x, y_values[2]), (x, y_values[3]))
            for x in x_values[1:4]
        )
        return longitudinal + crossings
    if style_id == "superblock_mixed":
        centers = (downtown_anchor,) + subcenter_anchors
        polylines: list[tuple[tuple[float, float], ...]] = []
        for index, center in enumerate(centers[:5]):
            polylines.extend(
                _rotated_grid_polylines(
                    center=center,
                    half_width=half_w * 0.13,
                    half_height=half_h * 0.12,
                    angle_degrees=(11.0, 34.0, 58.0)[index % 3],
                )
            )
        for left, right in zip(centers, centers[1:]):
            polylines.append((left, right))
        return tuple(polylines)

    centers = (downtown_anchor,) + subcenter_anchors + inner_anchors
    edges = _nearest_neighbor_edges(centers, extra_edges=(style_id == "polycentric_tod"))
    polylines = []
    for index, (left, right) in enumerate(edges):
        if style_id == "organic":
            dx = float(right[0]) - float(left[0])
            dy = float(right[1]) - float(left[1])
            bend = (
                round((left[0] + right[0]) * 0.5 - dy * (0.08 + (index % 3) * 0.025), 3),
                round((left[1] + right[1]) * 0.5 + dx * (0.08 + (index % 2) * 0.03), 3),
            )
            polylines.append((left, bend, right))
        else:
            polylines.append((left, right))
    return tuple(polylines)


def _rotated_grid_polylines(
    *,
    center: tuple[float, float],
    half_width: float,
    half_height: float,
    angle_degrees: float,
) -> tuple[tuple[tuple[float, float], ...], ...]:
    values = (-1.0, 0.0, 1.0)
    rows = tuple(
        tuple(_rotate_local_point(center, x * half_width, y * half_height, angle_degrees) for x in values)
        for y in values
    )
    columns = tuple(
        tuple(_rotate_local_point(center, x * half_width, y * half_height, angle_degrees) for y in values)
        for x in values
    )
    return rows + columns


def _rotate_local_point(
    center: tuple[float, float],
    x: float,
    y: float,
    angle_degrees: float,
) -> tuple[float, float]:
    angle = math.radians(angle_degrees)
    return (
        round(center[0] + x * math.cos(angle) - y * math.sin(angle), 3),
        round(center[1] + x * math.sin(angle) + y * math.cos(angle), 3),
    )


def _nearest_neighbor_edges(
    points: tuple[tuple[float, float], ...],
    *,
    extra_edges: bool,
) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...]:
    if len(points) < 2:
        return ()
    connected = {0}
    remaining = set(range(1, len(points)))
    edges: list[tuple[tuple[float, float], tuple[float, float]]] = []
    while remaining:
        left_index, right_index = min(
            (
                (left, right)
                for left in connected
                for right in remaining
            ),
            key=lambda pair: (
                math.hypot(
                    points[pair[1]][0] - points[pair[0]][0],
                    points[pair[1]][1] - points[pair[0]][1],
                ),
                pair,
            ),
        )
        edges.append((points[left_index], points[right_index]))
        connected.add(right_index)
        remaining.remove(right_index)
    if extra_edges and len(points) >= 5:
        edges.extend(((points[0], points[3]), (points[1], points[4]), (points[2], points[5])))
    return tuple(edges)


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


def _build_river_crossings(
    corridor_polylines: tuple[tuple[tuple[float, float], ...], ...],
) -> tuple[tuple[float, float], ...]:
    candidates: list[tuple[float, float]] = []
    for polyline in corridor_polylines:
        if len(polyline) < 4:
            continue
        lower_bank = polyline[1]
        upper_bank = polyline[2]
        if not math.isclose(float(lower_bank[0]), float(upper_bank[0]), abs_tol=1e-9):
            continue
        candidates.append(
            (
                round(float(lower_bank[0]), 3),
                round((float(lower_bank[1]) + float(upper_bank[1])) * 0.5, 3),
            )
        )
    return tuple(candidates)
