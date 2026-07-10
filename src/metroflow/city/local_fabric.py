from __future__ import annotations

import math
from typing import Any

from .continuous_fabric import (
    build_continuous_fabric_infill,
    split_segments_at_barriers,
)

__all__ = ["build_local_fabric"]

_T_JUNCTION_STAGGER_FRACTION = 0.14


def build_local_fabric(
    *,
    morphology_field: dict[str, Any],
    district_cells: dict[str, Any],
) -> dict[str, Any]:
    street_pattern = str(morphology_field.get("morphology_street_pattern", "radial_ring"))
    if street_pattern != "radial_ring":
        return _build_archetype_local_fabric(
            morphology_field=morphology_field,
            district_cells=district_cells,
            street_pattern=street_pattern,
        )

    cells = tuple(district_cells.get("district_cells", ()) or ())
    local_segments: list[dict[str, Any]] = []
    collector_segments: list[dict[str, Any]] = []
    local_keys: set[tuple[Any, ...]] = set()
    collector_keys: set[tuple[Any, ...]] = set()
    continuous_infill = build_continuous_fabric_infill(
        morphology_field=morphology_field,
        street_pattern=street_pattern,
    )
    continuous_fabric_segment_count = sum(
        _append_segment(
            local_segments,
            local_keys,
            kind="local",
            regime=str(segment["regime"]),
            points=tuple(segment["points"]),
        )
        for segment in continuous_infill["local_segments"]
    )
    interior_mesh_segment_count = 0
    perimeter_segment_count = 0
    collector_spine_segment_count = 0
    same_district_stitch_segment_count = 0
    inter_district_connector_count = 0
    core_fan_segment_count = 0
    downtown_thread_segment_count = 0
    district_transfer_hub_count = 0
    intra_cell_subdivision_count = 0
    perimeter_road_segment_count = 0

    bounds = tuple(district_cells.get("district_cell_bounds", ()) or ())
    min_x, min_y, max_x, max_y = _global_bounds(bounds)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    edge_margin_x = span_x * 0.10
    edge_margin_y = span_y * 0.10
    downtown = tuple(morphology_field.get("downtown_anchor", (0.0, 0.0)))
    max_center_radius = max(
        (
            math.hypot(float(cell["center"][0]) - float(downtown[0]), float(cell["center"][1]) - float(downtown[1]))
            for cell in cells
        ),
        default=1.0,
    )
    center_points_by_district: dict[str, list[tuple[float, float]]] = {}

    for index, cell in enumerate(cells):
        polygon = tuple(cell.get("polygon", ()) or ())
        if len(polygon) < 4:
            continue
        center = (round(float(cell["center"][0]), 3), round(float(cell["center"][1]), 3))
        regime = str(cell["regime"])
        district_id = str(cell["district_id"])
        center_points_by_district.setdefault(district_id, []).append(center)
        density_target = float(cell.get("density_target", 1.0))
        subdivision_points = tuple(
            (round(float(point[0]), 3), round(float(point[1]), 3))
            for point in tuple(cell.get("subdivision_points", ()) or ())
        )
        center_radius = math.hypot(float(center[0]) - float(downtown[0]), float(center[1]) - float(downtown[1]))
        outer_bias = min(center_radius / max(max_center_radius, 1.0), 1.0)

        midpoints: list[tuple[float, float]] = []
        inner_points: list[tuple[float, float]] = []
        exposed_midpoints: list[bool] = []
        for midpoint_index, (left, right) in enumerate(zip(polygon[:-1], polygon[1:])):
            midpoint = (
                round((float(left[0]) + float(right[0])) * 0.5, 3),
                round((float(left[1]) + float(right[1])) * 0.5, 3),
            )
            midpoints.append(midpoint)
            exposed = _is_exposed_point(
                midpoint,
                min_x=min_x,
                max_x=max_x,
                min_y=min_y,
                max_y=max_y,
                margin_x=edge_margin_x,
                margin_y=edge_margin_y,
            )
            exposed_midpoints.append(exposed)
            interior_scale = 0.46 if exposed else (0.66 + density_target * 0.08)
            inner_point = (
                round(float(center[0]) + (float(midpoint[0]) - float(center[0])) * interior_scale, 3),
                round(float(center[1]) + (float(midpoint[1]) - float(center[1])) * interior_scale, 3),
            )
            inner_points.append(inner_point)

            if exposed:
                perimeter_segment_count += 1

            if _append_segment(
                local_segments,
                local_keys,
                kind="local",
                regime=regime,
                points=(center, inner_point),
            ):
                interior_mesh_segment_count += 1

        for point in subdivision_points:
            if _append_segment(
                local_segments,
                local_keys,
                kind="local",
                regime=regime,
                points=(center, point),
            ):
                interior_mesh_segment_count += 1
                intra_cell_subdivision_count += 1

        ordered_subdivision_points = sorted(
            subdivision_points,
            key=lambda point: math.atan2(float(point[1]) - float(center[1]), float(point[0]) - float(center[0])),
        )
        subdivision_hubs = _subdivision_hubs(center=center, subdivision_points=ordered_subdivision_points)
        for hub in subdivision_hubs:
            if _append_segment(
                local_segments,
                local_keys,
                kind="local",
                regime=regime,
                points=(center, hub),
            ):
                interior_mesh_segment_count += 1
                intra_cell_subdivision_count += 1

        for hub, point_group in zip(
            subdivision_hubs,
            _partition_points(ordered_subdivision_points, len(subdivision_hubs)),
        ):
            for point in point_group:
                midpoint = (
                    round((float(hub[0]) + float(point[0])) * 0.5, 3),
                    round((float(hub[1]) + float(point[1])) * 0.5, 3),
                )
                if _append_segment(
                    local_segments,
                    local_keys,
                    kind="local",
                    regime=regime,
                    points=(hub, midpoint, point),
                ):
                    interior_mesh_segment_count += 1
                    intra_cell_subdivision_count += 1

        for left_hub, right_hub in zip(
            subdivision_hubs,
            subdivision_hubs[1:],
        ):
            midpoint = (
                round((float(left_hub[0]) + float(right_hub[0])) * 0.5, 3),
                round((float(left_hub[1]) + float(right_hub[1])) * 0.5, 3),
            )
            if _append_segment(
                local_segments,
                local_keys,
                kind="local",
                regime=regime,
                points=(left_hub, midpoint, right_hub),
            ):
                    interior_mesh_segment_count += 1
                    intra_cell_subdivision_count += 1

        if len(subdivision_hubs) >= 2:
            for left_point, right_point in (
                (ordered_subdivision_points[0], ordered_subdivision_points[-1]),
                (ordered_subdivision_points[len(ordered_subdivision_points) // 2 - 1], ordered_subdivision_points[len(ordered_subdivision_points) // 2]),
            ):
                if _append_segment(
                    local_segments,
                    local_keys,
                    kind="local",
                    regime=regime,
                    points=(left_point, center, right_point),
                ):
                    interior_mesh_segment_count += 1
                    intra_cell_subdivision_count += 1

        gateway_midpoints = [
            midpoint
            for midpoint, exposed in zip(midpoints, exposed_midpoints)
            if not exposed
        ][:2]
        for gateway in gateway_midpoints:
            if _append_segment(
                collector_segments,
                collector_keys,
                kind="collector",
                regime=regime,
                points=(center, gateway),
            ):
                interior_mesh_segment_count += 1
                perimeter_road_segment_count += 1

        if len(inner_points) >= 2:
            toward_core = (
                round(float(center[0]) + (float(downtown[0]) - float(center[0])) * (0.24 + density_target * 0.06), 3),
                round(float(center[1]) + (float(downtown[1]) - float(center[1])) * (0.24 + density_target * 0.06), 3),
            )
            if _append_segment(
                collector_segments,
                collector_keys,
                kind="collector",
                regime=regime,
                points=(
                    inner_points[0],
                    toward_core,
                    inner_points[-1],
                ),
            ):
                interior_mesh_segment_count += 1
                collector_spine_segment_count += 1
                core_fan_segment_count += 1

        if index + 1 < len(cells):
            peer = cells[index + 1]
            if str(peer["district_id"]) == str(cell["district_id"]):
                peer_center = (
                    round(float(peer["center"][0]), 3),
                    round(float(peer["center"][1]), 3),
                )
                if _append_segment(
                    collector_segments,
                    collector_keys,
                    kind="collector",
                    regime=regime,
                    points=(center, peer_center),
                ):
                    interior_mesh_segment_count += 1
                    same_district_stitch_segment_count += 1

        if outer_bias >= 0.72:
            for midpoint, exposed in zip(midpoints, exposed_midpoints):
                if exposed:
                    softened = (
                        round(float(center[0]) + (float(midpoint[0]) - float(center[0])) * 0.34, 3),
                        round(float(center[1]) + (float(midpoint[1]) - float(center[1])) * 0.34, 3),
                    )
                    if _append_segment(
                        local_segments,
                        local_keys,
                        kind="local",
                        regime=regime,
                        points=(center, softened),
                    ):
                        interior_mesh_segment_count += 1

    weave_scores: list[float] = []
    for bound in bounds:
        span_x = max(float(bound[2]) - float(bound[0]), 1.0)
        span_y = max(float(bound[3]) - float(bound[1]), 1.0)
        weave_scores.append((min(span_x, span_y) / max(span_x, span_y)) * 0.50)

    inner_anchors = tuple(
        (
            round(float(anchor[0]), 3),
            round(float(anchor[1]), 3),
        )
        for anchor in tuple(morphology_field.get("inner_anchors", ()) or ())
    )
    corridor_threads: list[dict[str, Any]] = []
    for anchor in inner_anchors:
        bend = (
            round((float(anchor[0]) + float(downtown[0])) * 0.48, 3),
            round((float(anchor[1]) + float(downtown[1])) * 0.48, 3),
        )
        if _append_segment(
            corridor_threads,
            collector_keys,
            kind="collector",
            regime="core_transfer",
            points=(
                (round(float(downtown[0]), 3), round(float(downtown[1]), 3)),
                bend,
                anchor,
            ),
        ):
            interior_mesh_segment_count += 1
            collector_spine_segment_count += 1
            downtown_thread_segment_count += 1

    if len(inner_anchors) >= 4:
        anchor_ring = (
            (inner_anchors[0], inner_anchors[1]),
            (inner_anchors[1], inner_anchors[3]),
            (inner_anchors[3], inner_anchors[2]),
            (inner_anchors[2], inner_anchors[0]),
        )
        for left, right in anchor_ring:
            midpoint = (
                round((float(left[0]) + float(right[0])) * 0.5, 3),
                round((float(left[1]) + float(right[1])) * 0.5, 3),
            )
            if _append_segment(
                corridor_threads,
                collector_keys,
                kind="collector",
                regime="inner_ring_transfer",
                points=(left, midpoint, right),
            ):
                interior_mesh_segment_count += 1
                collector_spine_segment_count += 1

    district_transfer_hubs = _district_transfer_hubs(center_points_by_district=center_points_by_district, downtown=downtown)
    district_transfer_hub_count = len(district_transfer_hubs)
    for district_id, hub in district_transfer_hubs:
        if inner_anchors:
            anchor = min(
                inner_anchors,
                key=lambda point: math.hypot(float(point[0]) - float(hub[0]), float(point[1]) - float(hub[1])),
            )
        else:
            anchor = (round(float(downtown[0]), 3), round(float(downtown[1]), 3))
        bend = (
            round((float(anchor[0]) + float(hub[0])) * 0.5, 3),
            round((float(anchor[1]) + float(hub[1])) * 0.5, 3),
        )
        if _append_segment(
            corridor_threads,
            collector_keys,
            kind="collector",
            regime=f"transfer_{district_id}",
            points=(anchor, bend, hub),
        ):
            interior_mesh_segment_count += 1
            collector_spine_segment_count += 1

        for point in center_points_by_district.get(district_id, ()):
            if point == hub:
                continue
            midpoint = (
                round((float(hub[0]) + float(point[0])) * 0.5, 3),
                round((float(hub[1]) + float(point[1])) * 0.5, 3),
            )
            if _append_segment(
                local_segments,
                local_keys,
                kind="local",
                regime=f"hub_mesh_{district_id}",
                points=(hub, midpoint, point),
            ):
                interior_mesh_segment_count += 1

    ordered_hubs = tuple(
        hub
        for _, hub in sorted(
            district_transfer_hubs,
            key=lambda item: math.atan2(float(item[1][1]) - float(downtown[1]), float(item[1][0]) - float(downtown[0])),
        )
    )
    for left, right in zip(ordered_hubs, ordered_hubs[1:] + ordered_hubs[:1]):
        midpoint = (
            round((float(left[0]) + float(right[0])) * 0.5, 3),
            round((float(left[1]) + float(right[1])) * 0.5, 3),
        )
        if _append_segment(
            collector_segments,
            collector_keys,
            kind="collector",
            regime="hub_ring",
            points=(left, midpoint, right),
        ):
            interior_mesh_segment_count += 1
            inter_district_connector_count += 1

    collector_segments.extend(corridor_threads)

    cross_district_pairs = _nearest_cross_district_pairs(center_points_by_district)
    for left, right in cross_district_pairs:
        midpoint = (
            round((float(left[0]) + float(right[0])) * 0.5, 3),
            round((float(left[1]) + float(right[1])) * 0.5, 3),
        )
        if _append_segment(
            collector_segments,
            collector_keys,
            kind="collector",
            regime="inter_district",
            points=(left, midpoint, right),
        ):
            interior_mesh_segment_count += 1
            inter_district_connector_count += 1

    total_segments = len(local_segments) + len(collector_segments)
    hierarchy_legibility_score = min(
        1.0,
        (collector_spine_segment_count * 0.025)
        + (same_district_stitch_segment_count * 0.015)
        + (inter_district_connector_count * 0.04)
        + (core_fan_segment_count * 0.02)
        + max(0.0, 0.45 - float(perimeter_segment_count / max(total_segments, 1))) * 0.8,
    )
    road_hierarchy_module_signature = tuple(
        label
        for label, active in (
            ("collector_spine", collector_spine_segment_count > 0),
            ("district_stitch", same_district_stitch_segment_count > 0),
            ("inter_district_connector", inter_district_connector_count > 0),
            ("core_fan", core_fan_segment_count > 0),
        )
        if active
    )

    return {
        "engine": "generator_v2_sidecar_local_fabric",
        "scenario_id": morphology_field.get("scenario_id"),
        "style_id": morphology_field.get("style_id"),
        "seed": int(morphology_field.get("seed", 0)),
        "local_segments": tuple(local_segments),
        "collector_segments": tuple(collector_segments),
        "local_segment_count": len(local_segments),
        "collector_segment_count": len(collector_segments),
        "interior_weave_score": float(sum(weave_scores) / max(len(weave_scores), 1)),
        "interior_mesh_segment_count": int(
            interior_mesh_segment_count + continuous_fabric_segment_count
        ),
        "perimeter_segment_count": int(perimeter_segment_count),
        "perimeter_segment_share": float(perimeter_segment_count / max(total_segments, 1)),
        "collector_spine_segment_count": int(collector_spine_segment_count),
        "same_district_stitch_segment_count": int(same_district_stitch_segment_count),
        "inter_district_connector_count": int(inter_district_connector_count),
        "core_fan_segment_count": int(core_fan_segment_count),
        "downtown_thread_segment_count": int(downtown_thread_segment_count),
        "district_transfer_hub_count": int(district_transfer_hub_count),
        "direct_downtown_spoke_share": float(downtown_thread_segment_count / max(len(collector_segments), 1)),
        "intra_cell_subdivision_count": int(intra_cell_subdivision_count),
        "cell_perimeter_road_share": float(perimeter_road_segment_count / max(total_segments, 1)),
        "road_hierarchy_module_signature": road_hierarchy_module_signature,
        "hierarchy_legibility_score": float(hierarchy_legibility_score),
        "continuous_fabric_strategy": str(continuous_infill["strategy"]),
        "continuous_fabric_segment_count": int(continuous_fabric_segment_count),
    }


def _build_archetype_local_fabric(
    *,
    morphology_field: dict[str, Any],
    district_cells: dict[str, Any],
    street_pattern: str,
) -> dict[str, Any]:
    cells = tuple(district_cells.get("district_cells", ()) or ())
    district_centers = tuple(morphology_field.get("district_centers", ()) or ())
    orientations = tuple(morphology_field.get("district_orientations_degrees", ()) or ())
    local_segments: list[dict[str, Any]] = []
    collector_segments: list[dict[str, Any]] = []
    local_keys: set[tuple[Any, ...]] = set()
    collector_keys: set[tuple[Any, ...]] = set()
    continuous_infill = build_continuous_fabric_infill(
        morphology_field=morphology_field,
        street_pattern=street_pattern,
    )
    continuous_fabric_segment_count = sum(
        _append_segment(
            local_segments,
            local_keys,
            kind="local",
            regime=str(segment["regime"]),
            points=tuple(segment["points"]),
        )
        for segment in continuous_infill["local_segments"]
    )
    centers_by_district: dict[str, list[tuple[float, float]]] = {}
    cells_by_district: dict[str, list[dict[str, Any]]] = {}

    for index, cell in enumerate(cells):
        center = _rounded_point(cell["center"])
        polygon = tuple(cell.get("polygon", ()) or ())
        if len(polygon) < 4:
            continue
        district_id = str(cell["district_id"])
        centers_by_district.setdefault(district_id, []).append(center)
        cells_by_district.setdefault(district_id, []).append(cell)
        if street_pattern in {"orthogonal_grid", "multi_grid", "polycentric_mesh"}:
            continue
        elif street_pattern == "corridor_constrained":
            continue
        else:
            subdivision = tuple(_rounded_point(point) for point in cell.get("subdivision_points", ()))
            loop = subdivision[:4]
            if len(loop) >= 3:
                _append_segment(
                    local_segments,
                    local_keys,
                    kind="local",
                    regime=f"organic_loop_{cell['regime']}",
                    points=loop + (loop[0],),
                )
            for point_index, point in enumerate(subdivision):
                bend = (
                    round((center[0] + point[0]) * 0.5 + math.sin(index + point_index) * 5.0, 3),
                    round((center[1] + point[1]) * 0.5 + math.cos(index - point_index) * 5.0, 3),
                )
                _append_segment(
                    local_segments,
                    local_keys,
                    kind="local",
                    regime=f"organic_accretion_{cell['regime']}",
                    points=(center, bend, point),
                )

    for district_id in sorted(cells_by_district):
        district_index = int(district_id.rsplit("_", 1)[-1])
        district_group = cells_by_district[district_id]
        points = tuple(
            _rounded_point(point)
            for cell in district_group
            for point in tuple(cell.get("polygon", ()) or ())[:-1]
        )
        if not points:
            continue
        min_x = min(point[0] for point in points)
        max_x = max(point[0] for point in points)
        min_y = min(point[1] for point in points)
        max_y = max(point[1] for point in points)
        center = (
            round((min_x + max_x) * 0.5, 3),
            round((min_y + max_y) * 0.5, 3),
        )
        half_width = max((max_x - min_x) * 0.56, 30.0)
        half_height = max((max_y - min_y) * 0.56, 30.0)
        orientation = (
            float(orientations[district_index % len(orientations)])
            if orientations
            else 0.0
        )
        if street_pattern == "orthogonal_grid":
            orientation = float(orientations[0]) if orientations else 0.0
        if street_pattern in {"orthogonal_grid", "multi_grid", "polycentric_mesh"}:
            for grid_points in _local_grid_polylines(
                center=center,
                half_width=half_width,
                half_height=half_height,
                angle_degrees=orientation,
                street_pattern=street_pattern,
            ):
                _append_segment(
                    local_segments,
                    local_keys,
                    kind="local",
                    regime=f"district_{street_pattern}",
                    points=grid_points,
                )
        elif street_pattern == "corridor_constrained":
            for offset in (-1.0, -0.5, 0.0, 0.5, 1.0):
                y = round(center[1] + offset * half_height, 3)
                _append_segment(
                    local_segments,
                    local_keys,
                    kind="local",
                    regime="district_corridor_parallel",
                    points=(
                        (round(center[0] - half_width, 3), y),
                        (center[0], y),
                        (round(center[0] + half_width, 3), y),
                    ),
                )
            for offset in (-0.5, 0.5):
                x = round(center[0] + offset * half_width, 3)
                _append_segment(
                    local_segments,
                    local_keys,
                    kind="local",
                    regime="district_corridor_cross",
                    points=(
                        (x, round(center[1] - half_height, 3)),
                        (x, center[1]),
                        (x, round(center[1] + half_height, 3)),
                    ),
                )
            y_values = (-1.0, -0.5, 0.0, 0.5, 1.0)
            for side in (-1.0, 1.0):
                x = round(center[0] + side * half_width, 3)
                _append_segment(
                    local_segments,
                    local_keys,
                    kind="local",
                    regime="district_corridor_return",
                    points=tuple(
                        (x, round(center[1] + offset * half_height, 3))
                        for offset in y_values
                    ),
                )

    same_district_stitch_count = 0
    district_hubs: list[tuple[str, tuple[float, float]]] = []
    for district_id in sorted(centers_by_district):
        centers = tuple(centers_by_district[district_id])
        if not centers:
            continue
        district_index = int(district_id.rsplit("_", 1)[-1])
        anchor = (
            _rounded_point(district_centers[district_index])
            if district_index < len(district_centers)
            else centers[0]
        )
        hub = min(centers, key=lambda point: (_distance(point, anchor), point))
        district_hubs.append((district_id, hub))
        if hub != anchor and _append_segment(
            collector_segments,
            collector_keys,
            kind="collector",
            regime=f"district_gateway_{street_pattern}",
            points=(hub, anchor),
        ):
            same_district_stitch_count += 1
        for left, right in _nearest_tree_edges(centers):
            if _append_segment(
                collector_segments,
                collector_keys,
                kind="collector",
                regime=f"district_mesh_{street_pattern}",
                points=(left, right),
            ):
                same_district_stitch_count += 1
        if street_pattern == "organic_mesh" and len(centers) >= 3:
            ordered_centers = tuple(
                sorted(
                    centers,
                    key=lambda point: math.atan2(point[1] - anchor[1], point[0] - anchor[0]),
                )
            )
            for left, right in zip(ordered_centers, ordered_centers[1:] + ordered_centers[:1]):
                if _append_segment(
                    local_segments,
                    local_keys,
                    kind="local",
                    regime="organic_district_loop",
                    points=(left, right),
                ):
                    same_district_stitch_count += 1

    inter_district_count = 0
    hub_points = tuple(hub for _district_id, hub in district_hubs)
    if street_pattern == "corridor_constrained":
        ordered = tuple(sorted(hub_points, key=lambda point: (point[0], point[1])))
        connector_edges = tuple(zip(ordered, ordered[1:]))
    else:
        connector_edges = _nearest_tree_edges(hub_points)
        if street_pattern == "polycentric_mesh" and len(hub_points) >= 4:
            connector_edges += ((hub_points[0], hub_points[-1]),)
        elif street_pattern == "organic_mesh" and len(hub_points) >= 5:
            connector_edges += (
                (hub_points[0], hub_points[3]),
                (hub_points[1], hub_points[4]),
            )
    for left, right in connector_edges:
        if _append_segment(
            collector_segments,
            collector_keys,
            kind="collector",
            regime=f"inter_district_{street_pattern}",
            points=(left, right),
        ):
            inter_district_count += 1

    if street_pattern == "corridor_constrained":
        barriers = tuple(
            tuple(_rounded_point(point) for point in polyline)
            for polyline in tuple(morphology_field.get("barrier_polylines", ()) or ())
            if len(polyline) >= 2
        )
        local_segments = list(
            split_segments_at_barriers(
                segments=tuple(local_segments),
                barrier_polylines=barriers,
            )
        )
        continuous_fabric_segment_count = sum(
            str(segment["regime"]).startswith("continuous_")
            for segment in local_segments
        )

    total_segments = len(local_segments) + len(collector_segments)
    signature = (
        "district_stitch",
        "inter_district_connector",
        street_pattern,
    )
    return {
        "engine": "generator_v2_archetype_local_fabric",
        "scenario_id": morphology_field.get("scenario_id"),
        "style_id": morphology_field.get("style_id"),
        "seed": int(morphology_field.get("seed", 0)),
        "morphology_street_pattern": street_pattern,
        "local_segments": tuple(local_segments),
        "collector_segments": tuple(collector_segments),
        "local_segment_count": len(local_segments),
        "collector_segment_count": len(collector_segments),
        "interior_weave_score": float(len(local_segments) / max(total_segments, 1)),
        "interior_mesh_segment_count": total_segments,
        "perimeter_segment_count": 0,
        "perimeter_segment_share": 0.0,
        "collector_spine_segment_count": len(collector_segments),
        "same_district_stitch_segment_count": same_district_stitch_count,
        "inter_district_connector_count": inter_district_count,
        "core_fan_segment_count": 0,
        "downtown_thread_segment_count": 0,
        "district_transfer_hub_count": len(district_hubs),
        "direct_downtown_spoke_share": 0.0,
        "intra_cell_subdivision_count": len(local_segments),
        "cell_perimeter_road_share": 0.0,
        "road_hierarchy_module_signature": signature,
        "hierarchy_legibility_score": min(1.0, 0.45 + inter_district_count * 0.05),
        "continuous_fabric_strategy": str(continuous_infill["strategy"]),
        "continuous_fabric_segment_count": int(continuous_fabric_segment_count),
    }


def _local_grid_polylines(
    *,
    center: tuple[float, float],
    half_width: float,
    half_height: float,
    angle_degrees: float,
    street_pattern: str,
) -> tuple[tuple[tuple[float, float], ...], ...]:
    values = (-1.0, -0.5, 0.0, 0.5, 1.0)
    staggered_x = {
        "polycentric_mesh": values,
        "multi_grid": values,
    }.get(street_pattern, ())
    stagger = _T_JUNCTION_STAGGER_FRACTION
    stagger_by_x = {
        x: (-stagger if x == 1.0 else stagger)
        for x in staggered_x
    }
    second_stagger_by_x = {
        x: (stagger if x == -1.0 else -stagger)
        for x in staggered_x
    }

    def row_x_values(y: float) -> tuple[float, ...]:
        if y == 0.0:
            extra = tuple(x + stagger_by_x[x] for x in staggered_x)
        elif y == 0.5:
            extra = tuple(x + second_stagger_by_x[x] for x in staggered_x)
        else:
            extra = ()
        return tuple(sorted(values + extra))

    rows = tuple(
        tuple(
            _rotate_point(
                center,
                x * half_width,
                y * half_height,
                angle_degrees,
            )
            for x in row_x_values(y)
        )
        for y in values
    )
    columns: list[tuple[tuple[float, float], ...]] = []
    for x in values:
        if x not in staggered_x:
            columns.append(
                tuple(
                    _rotate_point(
                        center,
                        x * half_width,
                        y * half_height,
                        angle_degrees,
                    )
                    for y in values
                )
            )
            continue
        columns.append(
            tuple(
                _rotate_point(
                    center,
                    x * half_width,
                    y * half_height,
                    angle_degrees,
                )
                for y in (-1.0, -0.5, 0.0)
            )
        )
        columns.append(
            (
                _rotate_point(
                    center,
                    (x + stagger_by_x[x]) * half_width,
                    0.0,
                    angle_degrees,
                ),
                _rotate_point(
                    center,
                    x * half_width,
                    0.5 * half_height,
                    angle_degrees,
                ),
            )
        )
        columns.append(
            (
                _rotate_point(
                    center,
                    (x + second_stagger_by_x[x]) * half_width,
                    0.5 * half_height,
                    angle_degrees,
                ),
                _rotate_point(
                    center,
                    x * half_width,
                    half_height,
                    angle_degrees,
                ),
            )
        )
    return rows + tuple(columns)


def _rotate_point(
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


def _nearest_tree_edges(
    points: tuple[tuple[float, float], ...],
) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...]:
    if len(points) < 2:
        return ()
    connected = {0}
    remaining = set(range(1, len(points)))
    edges: list[tuple[tuple[float, float], tuple[float, float]]] = []
    while remaining:
        left_index, right_index = min(
            ((left, right) for left in connected for right in remaining),
            key=lambda pair: (_distance(points[pair[0]], points[pair[1]]), pair),
        )
        edges.append((points[left_index], points[right_index]))
        connected.add(right_index)
        remaining.remove(right_index)
    return tuple(edges)


def _rounded_point(point: Any) -> tuple[float, float]:
    return (round(float(point[0]), 3), round(float(point[1]), 3))


def _distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return math.hypot(right[0] - left[0], right[1] - left[1])


def _append_segment(
    target: list[dict[str, Any]],
    keys: set[tuple[Any, ...]],
    *,
    kind: str,
    regime: str,
    points: tuple[tuple[float, float], ...],
) -> bool:
    if len(points) < 2:
        return False
    key = _segment_key(points)
    if key in keys:
        return False
    keys.add(key)
    target.append({"kind": kind, "regime": regime, "points": points})
    return True


def _segment_key(points: tuple[tuple[float, float], ...]) -> tuple[Any, ...]:
    rounded = tuple((round(float(x), 3), round(float(y), 3)) for x, y in points)
    reverse = tuple(reversed(rounded))
    return min(rounded, reverse)


def _global_bounds(
    bounds: tuple[tuple[float, float, float, float], ...],
) -> tuple[float, float, float, float]:
    if not bounds:
        return (-1.0, -1.0, 1.0, 1.0)
    min_x = min(float(bound[0]) for bound in bounds)
    min_y = min(float(bound[1]) for bound in bounds)
    max_x = max(float(bound[2]) for bound in bounds)
    max_y = max(float(bound[3]) for bound in bounds)
    return (min_x, min_y, max_x, max_y)


def _is_exposed_point(
    point: tuple[float, float],
    *,
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    margin_x: float,
    margin_y: float,
) -> bool:
    x, y = float(point[0]), float(point[1])
    return (
        x <= min_x + margin_x
        or x >= max_x - margin_x
        or y <= min_y + margin_y
        or y >= max_y - margin_y
    )


def _nearest_cross_district_pairs(
    centers_by_district: dict[str, list[tuple[float, float]]],
) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...]:
    districts = tuple(sorted(centers_by_district))
    pairs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for left_id, right_id in zip(districts, districts[1:]):
        best_pair: tuple[tuple[float, float], tuple[float, float]] | None = None
        best_distance = float("inf")
        for left in centers_by_district[left_id]:
            for right in centers_by_district[right_id]:
                distance = math.hypot(float(right[0]) - float(left[0]), float(right[1]) - float(left[1]))
                if distance < best_distance:
                    best_distance = distance
                    best_pair = (left, right)
        if best_pair is not None:
            pairs.append(best_pair)
    return tuple(pairs)


def _district_transfer_hubs(
    *,
    center_points_by_district: dict[str, list[tuple[float, float]]],
    downtown: tuple[float, float],
) -> tuple[tuple[str, tuple[float, float]], ...]:
    hubs: list[tuple[str, tuple[float, float]]] = []
    for district_id in sorted(center_points_by_district):
        points = center_points_by_district[district_id]
        if not points:
            continue
        hub = min(
            points,
            key=lambda point: math.hypot(float(point[0]) - float(downtown[0]), float(point[1]) - float(downtown[1])),
        )
        hubs.append((district_id, hub))
    return tuple(hubs)


def _subdivision_hubs(
    *,
    center: tuple[float, float],
    subdivision_points: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    if not subdivision_points:
        return ()
    if len(subdivision_points) == 1:
        return subdivision_points
    left = subdivision_points[0]
    right = subdivision_points[len(subdivision_points) // 2]
    return (
        (
            round((float(center[0]) + float(left[0])) * 0.5, 3),
            round((float(center[1]) + float(left[1])) * 0.5, 3),
        ),
        (
            round((float(center[0]) + float(right[0])) * 0.5, 3),
            round((float(center[1]) + float(right[1])) * 0.5, 3),
        ),
    )


def _partition_points(
    points: tuple[tuple[float, float], ...],
    parts: int,
) -> tuple[tuple[tuple[float, float], ...], ...]:
    if parts <= 1:
        return (points,)
    groups: list[list[tuple[float, float]]] = [[] for _ in range(parts)]
    for index, point in enumerate(points):
        groups[index % parts].append(point)
    return tuple(tuple(group) for group in groups)
