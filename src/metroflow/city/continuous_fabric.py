"""Style-aware local-street infill for continuous generated city fabric."""

from __future__ import annotations

import math
from typing import Any

__all__ = ["build_continuous_fabric_infill", "split_segments_at_barriers"]

_GRID_AXIS_VALUES = (
    -0.82,
    -0.656,
    -0.492,
    -0.328,
    -0.164,
    0.0,
    0.164,
    0.328,
    0.492,
    0.656,
    0.82,
)
_RADIAL_SCALES = (0.24, 0.42, 0.60, 0.78)
_RADIAL_ANGLE_COUNT = 16
_CORRIDOR_SAMPLE_SPACING_M = 260.0
_CORRIDOR_OFFSETS_M = (-130.0, 130.0)
_RIVER_BARRIER_CLEARANCE_M = 190.0


def build_continuous_fabric_infill(
    *,
    morphology_field: dict[str, Any],
    street_pattern: str,
) -> dict[str, Any]:
    """Build deterministic local-only infill without mutating topology state."""

    pattern = str(street_pattern)
    if pattern == "orthogonal_grid":
        segments = _global_grid_segments(morphology_field)
        strategy = "global_orthogonal_lattice"
    elif pattern == "radial_ring":
        segments = _radial_mesh_segments(morphology_field)
        strategy = "radial_ring_mesh"
    elif pattern == "polycentric_mesh":
        segments = _district_tree_band_segments(morphology_field)
        strategy = "district_tree_bands"
    elif pattern == "multi_grid":
        segments = _global_rotated_grid_segments(morphology_field)
        strategy = "global_rotated_superblock_grid"
    elif pattern in {"corridor_constrained", "organic_mesh"}:
        segments = _corridor_band_segments(
            morphology_field,
            respect_barrier=(pattern == "corridor_constrained"),
        )
        strategy = "barrier_aware_corridor_bands" if pattern == "corridor_constrained" else "corridor_bands"
    else:
        raise ValueError(f"unsupported continuous-fabric street pattern: {pattern}")
    return {
        "strategy": strategy,
        "local_segments": segments,
        "segment_count": len(segments),
    }


def split_segments_at_barriers(
    *,
    segments: tuple[dict[str, Any], ...],
    barrier_polylines: tuple[tuple[tuple[float, float], ...], ...],
) -> tuple[dict[str, Any], ...]:
    """Remove crossing edges while preserving local runs on each barrier side."""

    if not barrier_polylines:
        raise ValueError("barrier-aware local fabric requires a valid barrier polyline")
    result: list[dict[str, Any]] = []
    seen: set[tuple[tuple[float, float], ...]] = set()
    for segment in segments:
        points = tuple((float(point[0]), float(point[1])) for point in segment["points"])
        runs: list[tuple[tuple[float, float], ...]] = []
        current = [points[0]]
        for left, right in zip(points, points[1:]):
            crosses = any(
                _polylines_intersect((left, right), barrier)
                for barrier in barrier_polylines
            )
            if crosses:
                if len(current) >= 2:
                    runs.append(tuple(current))
                current = [right]
            else:
                current.append(right)
        if len(current) >= 2:
            runs.append(tuple(current))
        for run in runs:
            reverse = tuple(reversed(run))
            key = min(run, reverse)
            if key in seen:
                continue
            seen.add(key)
            result.append(
                {
                    "kind": str(segment.get("kind", "local")),
                    "regime": str(segment["regime"]),
                    "points": run,
                }
            )
    return tuple(result)


def _district_tree_band_segments(
    morphology_field: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    centers = tuple(
        (float(point[0]), float(point[1]))
        for point in tuple(morphology_field.get("district_centers", ()) or ())
    )
    if len(centers) < 2:
        return ()
    connected = {0}
    remaining = set(range(1, len(centers)))
    corridors: list[tuple[tuple[float, float], tuple[float, float]]] = []
    while remaining:
        left_index, right_index = min(
            (
                (left_index, right_index)
                for left_index in connected
                for right_index in remaining
            ),
            key=lambda pair: (math.dist(centers[pair[0]], centers[pair[1]]), pair),
        )
        corridors.append((centers[left_index], centers[right_index]))
        connected.add(right_index)
        remaining.remove(right_index)
    proxy_field = {
        "corridor_influence_polylines": tuple(corridors),
        "barrier_polylines": (),
    }
    return _corridor_band_segments(proxy_field, respect_barrier=False)


def _global_rotated_grid_segments(
    morphology_field: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    min_x, max_x, min_y, max_y = _render_bounds(morphology_field)
    center = ((min_x + max_x) * 0.5, (min_y + max_y) * 0.5)
    half_width = (max_x - min_x) * 0.34
    half_height = (max_y - min_y) * 0.34
    orientations = tuple(
        float(value)
        for value in tuple(
            morphology_field.get("district_orientations_degrees", ()) or ()
        )
    )
    angle = orientations[0] if orientations else 11.0
    values = (-1.0, -2.0 / 3.0, -1.0 / 3.0, 0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0)

    def point(x: float, y: float) -> tuple[float, float]:
        radians = math.radians(angle)
        return (
            round(
                center[0]
                + x * half_width * math.cos(radians)
                - y * half_height * math.sin(radians),
                3,
            ),
            round(
                center[1]
                + x * half_width * math.sin(radians)
                + y * half_height * math.cos(radians),
                3,
            ),
        )

    rows = tuple(
        {
            "kind": "local",
            "regime": "continuous_rotated_superblock_row",
            "points": tuple(point(x, y) for x in values),
        }
        for y in values
    )
    columns = tuple(
        {
            "kind": "local",
            "regime": "continuous_rotated_superblock_column",
            "points": tuple(point(x, y) for y in values),
        }
        for x in values
    )
    return rows + columns


def _global_grid_segments(
    morphology_field: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    min_x, max_x, min_y, max_y = _render_bounds(morphology_field)
    x_values = tuple(_interpolate(min_x, max_x, value) for value in _GRID_AXIS_VALUES)
    y_values = tuple(_interpolate(min_y, max_y, value) for value in _GRID_AXIS_VALUES)
    rows = tuple(
        {
            "kind": "local",
            "regime": "continuous_global_grid_row",
            "points": tuple((x, y) for x in x_values),
        }
        for y in y_values
    )
    columns = tuple(
        {
            "kind": "local",
            "regime": "continuous_global_grid_column",
            "points": tuple((x, y) for y in y_values),
        }
        for x in x_values
    )
    return rows + columns


def _radial_mesh_segments(
    morphology_field: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    min_x, max_x, min_y, max_y = _render_bounds(morphology_field)
    center = tuple(morphology_field.get("downtown_anchor", (0.0, 0.0)))
    center_x = float(center[0])
    center_y = float(center[1])
    radius_x = min(center_x - min_x, max_x - center_x)
    radius_y = min(center_y - min_y, max_y - center_y)
    angles = tuple(
        index * math.tau / _RADIAL_ANGLE_COUNT
        for index in range(_RADIAL_ANGLE_COUNT)
    )
    rings = tuple(
        {
            "kind": "local",
            "regime": "continuous_radial_ring",
            "points": tuple(
                _radial_point(
                    center_x=center_x,
                    center_y=center_y,
                    radius_x=radius_x,
                    radius_y=radius_y,
                    scale=scale,
                    angle=angle,
                )
                for angle in angles + (angles[0],)
            ),
        }
        for scale in _RADIAL_SCALES
    )
    rays = tuple(
        {
            "kind": "local",
            "regime": "continuous_radial_ray",
            "points": tuple(
                _radial_point(
                    center_x=center_x,
                    center_y=center_y,
                    radius_x=radius_x,
                    radius_y=radius_y,
                    scale=scale,
                    angle=angle,
                )
                for scale in _RADIAL_SCALES
            ),
        }
        for angle in angles
    )
    return rings + rays


def _corridor_band_segments(
    morphology_field: dict[str, Any],
    *,
    respect_barrier: bool,
) -> tuple[dict[str, Any], ...]:
    corridors = tuple(
        tuple((float(point[0]), float(point[1])) for point in polyline)
        for polyline in tuple(
            morphology_field.get("corridor_influence_polylines", ()) or ()
        )
        if len(polyline) >= 2
    )
    barriers = tuple(
        tuple((float(point[0]), float(point[1])) for point in polyline)
        for polyline in tuple(morphology_field.get("barrier_polylines", ()) or ())
        if len(polyline) >= 2
    )
    if respect_barrier and not barriers:
        raise ValueError("corridor_constrained requires a valid barrier polyline")
    segments: list[dict[str, Any]] = []
    for corridor_index, corridor in enumerate(corridors):
        samples = _resample_polyline(corridor, spacing_m=_CORRIDOR_SAMPLE_SPACING_M)
        if len(samples) < 2:
            continue
        offset_rows = tuple(
            tuple(
                _offset_sample(samples, index=index, offset_m=offset)
                for index in range(len(samples))
            )
            for offset in _CORRIDOR_OFFSETS_M
        )
        allowed = tuple(
            not respect_barrier
            or not barriers
            or min(_point_polyline_distance(point, barrier) for barrier in barriers)
            >= _RIVER_BARRIER_CLEARANCE_M
            for point in samples
        )
        for offset_index, row in enumerate(offset_rows):
            for run in _allowed_runs(row, allowed):
                if len(run) >= 2 and not (
                    respect_barrier
                    and any(_polylines_intersect(run, barrier) for barrier in barriers)
                ):
                    segments.append(
                        {
                            "kind": "local",
                            "regime": f"continuous_corridor_band_{corridor_index}_{offset_index}",
                            "points": run,
                        }
                    )
        for sample_index, is_allowed in enumerate(allowed):
            if not is_allowed or sample_index % 3:
                continue
            cross_points = tuple(row[sample_index] for row in offset_rows)
            if respect_barrier and any(
                _polylines_intersect(cross_points, barrier) for barrier in barriers
            ):
                continue
            segments.append(
                {
                    "kind": "local",
                    "regime": f"continuous_corridor_cross_{corridor_index}",
                    "points": cross_points,
                }
            )
    return tuple(segments)


def _resample_polyline(
    points: tuple[tuple[float, float], ...],
    *,
    spacing_m: float,
) -> tuple[tuple[float, float], ...]:
    samples: list[tuple[float, float]] = [points[0]]
    for left, right in zip(points, points[1:]):
        distance = math.dist(left, right)
        steps = max(1, int(math.ceil(distance / spacing_m)))
        samples.extend(
            (
                round(left[0] + (right[0] - left[0]) * step / steps, 3),
                round(left[1] + (right[1] - left[1]) * step / steps, 3),
            )
            for step in range(1, steps + 1)
        )
    return tuple(samples)


def _offset_sample(
    samples: tuple[tuple[float, float], ...],
    *,
    index: int,
    offset_m: float,
) -> tuple[float, float]:
    left = samples[max(0, index - 1)]
    right = samples[min(len(samples) - 1, index + 1)]
    dx = right[0] - left[0]
    dy = right[1] - left[1]
    length = max(math.hypot(dx, dy), 1e-12)
    return (
        round(samples[index][0] - dy * offset_m / length, 3),
        round(samples[index][1] + dx * offset_m / length, 3),
    )


def _allowed_runs(
    points: tuple[tuple[float, float], ...],
    allowed: tuple[bool, ...],
) -> tuple[tuple[tuple[float, float], ...], ...]:
    runs: list[tuple[tuple[float, float], ...]] = []
    current: list[tuple[float, float]] = []
    for point, is_allowed in zip(points, allowed, strict=True):
        if is_allowed:
            current.append(point)
        elif current:
            runs.append(tuple(current))
            current = []
    if current:
        runs.append(tuple(current))
    return tuple(runs)


def _point_polyline_distance(
    point: tuple[float, float],
    polyline: tuple[tuple[float, float], ...],
) -> float:
    return min(
        _point_segment_distance(point, left, right)
        for left, right in zip(polyline, polyline[1:])
    )


def _point_segment_distance(
    point: tuple[float, float],
    left: tuple[float, float],
    right: tuple[float, float],
) -> float:
    dx = right[0] - left[0]
    dy = right[1] - left[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= 1e-12:
        return math.dist(point, left)
    share = ((point[0] - left[0]) * dx + (point[1] - left[1]) * dy) / length_squared
    share = min(1.0, max(0.0, share))
    projection = (left[0] + dx * share, left[1] + dy * share)
    return math.dist(point, projection)


def _polylines_intersect(
    left: tuple[tuple[float, float], ...],
    right: tuple[tuple[float, float], ...],
) -> bool:
    return any(
        _segments_intersect(left_start, left_end, right_start, right_end)
        for left_start, left_end in zip(left, left[1:])
        for right_start, right_end in zip(right, right[1:])
    )


def _segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    def orientation(
        left: tuple[float, float],
        middle: tuple[float, float],
        right: tuple[float, float],
    ) -> float:
        return (middle[0] - left[0]) * (right[1] - left[1]) - (
            middle[1] - left[1]
        ) * (right[0] - left[0])

    ab_c = orientation(a, b, c)
    ab_d = orientation(a, b, d)
    cd_a = orientation(c, d, a)
    cd_b = orientation(c, d, b)
    if (ab_c < 0.0) != (ab_d < 0.0) and (cd_a < 0.0) != (cd_b < 0.0):
        return True

    def on_segment(
        left: tuple[float, float],
        middle: tuple[float, float],
        right: tuple[float, float],
    ) -> bool:
        return (
            min(left[0], right[0]) - 1e-9
            <= middle[0]
            <= max(left[0], right[0]) + 1e-9
            and min(left[1], right[1]) - 1e-9
            <= middle[1]
            <= max(left[1], right[1]) + 1e-9
        )

    return (
        (abs(ab_c) <= 1e-9 and on_segment(a, c, b))
        or (abs(ab_d) <= 1e-9 and on_segment(a, d, b))
        or (abs(cd_a) <= 1e-9 and on_segment(c, a, d))
        or (abs(cd_b) <= 1e-9 and on_segment(c, b, d))
    )


def _radial_point(
    *,
    center_x: float,
    center_y: float,
    radius_x: float,
    radius_y: float,
    scale: float,
    angle: float,
) -> tuple[float, float]:
    return (
        round(center_x + math.cos(angle) * radius_x * scale, 3),
        round(center_y + math.sin(angle) * radius_y * scale, 3),
    )


def _render_bounds(
    morphology_field: dict[str, Any],
) -> tuple[float, float, float, float]:
    bounds = tuple(morphology_field.get("render_bounds", ()) or ())
    if len(bounds) != 4:
        raise ValueError("morphology render_bounds must contain four values")
    min_x, max_x, min_y, max_y = (float(value) for value in bounds)
    if min_x >= max_x or min_y >= max_y:
        raise ValueError("morphology render_bounds must have positive extent")
    return min_x, max_x, min_y, max_y


def _interpolate(minimum: float, maximum: float, normalized: float) -> float:
    center = (minimum + maximum) * 0.5
    half_extent = (maximum - minimum) * 0.5
    return round(center + normalized * half_extent, 3)
