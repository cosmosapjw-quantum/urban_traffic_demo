from __future__ import annotations

from math import sin, tau


def build_backbone(
    *,
    style_id: str,
    seed: int,
    width: int = 5_400,
    height: int = 4_600,
) -> dict[str, object]:
    if style_id == "polycentric_tod":
        return _build_polycentric_mesh(seed=seed, width=width, height=height)
    return _build_ring_radial_backbone(style_id=style_id, seed=seed, width=width, height=height)


def _build_ring_radial_backbone(*, style_id: str, seed: int, width: int, height: int) -> dict[str, object]:
    half_w = float(width) * 0.40
    half_h = float(height) * 0.39
    inner_w = half_w * 0.58
    inner_h = half_h * 0.63
    collector_w = inner_w * 0.54
    collector_h = inner_h * 0.52
    river_bank = max(160.0, float(width) * 0.035)

    west_outer = half_w * 1.00
    east_outer = half_w * 0.88
    west_inner = inner_w * 1.10
    east_inner = inner_w * 0.76
    west_collector = collector_w * 1.18
    east_collector = collector_w * 0.64
    west_bank = river_bank * 1.28
    east_bank = river_bank * 0.72
    x_levels = (
        -west_outer,
        -west_inner,
        -west_collector,
        -west_bank,
        east_bank,
        east_collector,
        east_inner,
        east_outer,
    )
    south_outer = half_h * 0.98
    north_outer = half_h * 0.84
    south_inner = inner_h * 1.09
    north_inner = inner_h * 0.91
    south_collector = collector_h * 1.03
    north_collector = collector_h * 0.80
    y_levels = (
        -south_outer,
        -south_inner,
        -south_collector,
        126.0,
        north_collector,
        north_inner,
        north_outer,
    )
    bridge_rows = (-south_inner, -south_collector, north_collector, north_inner)
    downtown_anchor = (-west_bank * 0.55, north_collector * 0.42)

    subcenter_specs = (
        (0.17, 0.97, 1.02, -west_bank * 0.35, north_collector * 0.30),
        (0.31, 1.03, 0.96, east_bank * 0.18, north_collector * 0.18),
        (0.58, 1.08, 0.92, -west_bank * 0.18, -north_collector * 0.12),
        (0.79, 0.88, 1.06, east_bank * 0.34, -north_collector * 0.08),
        (1.06, 1.10, 0.84, east_bank * 0.42, north_collector * 0.06),
        (1.34, 0.92, 1.00, -west_bank * 0.46, north_collector * 0.10),
    )
    subcenter_points = tuple(
        (
            round(inner_w * x_scale * sin(tau * (angle + 0.25)) + x_bias, 3),
            round(inner_h * y_scale * sin(tau * angle) + y_bias, 3),
        )
        for angle, x_scale, y_scale, x_bias, y_bias in subcenter_specs
    )

    barrier_polyline = tuple(
        (
            round(((west_bank + east_bank) * 0.19) * sin((idx / 8.0) * tau + (seed % 17) * 0.03), 3),
            round(-south_outer * 1.08 + idx * (((south_outer + north_outer) * 2.04) / 8.0), 3),
        )
        for idx in range(9)
    )

    return {
        "style_id": style_id,
        "seed": int(seed),
        "bounds": {"width": int(width), "height": int(height)},
        "downtown_anchor": downtown_anchor,
        "subcenter_points": subcenter_points,
        "outer_ring_bounds": (-half_w, half_w, -half_h, half_h),
        "inner_ring_bounds": (-inner_w, inner_w, -inner_h, inner_h),
        "collector_ring_bounds": (-collector_w, collector_w, -collector_h, collector_h),
        "x_levels": x_levels,
        "y_levels": y_levels,
        "bridge_rows": bridge_rows,
        "river_bank_x": (-west_bank, east_bank),
        "barrier_polylines": (barrier_polyline,),
        "outer_frame_gap_segments": (
            ("h", 0, 0),
            ("h", 0, len(x_levels) - 2),
            ("h", len(y_levels) - 1, 0),
            ("h", len(y_levels) - 1, len(x_levels) - 2),
            ("v", 0, 0),
            ("v", len(x_levels) - 1, 0),
            ("v", 0, len(y_levels) - 2),
            ("v", len(x_levels) - 1, len(y_levels) - 2),
        ),
        "interior_gap_segments": (),
        "frame_cut_in_pairs": (
            ((-half_w, -inner_h), (-inner_w, -half_h)),
            ((-half_w, inner_h), (-inner_w, half_h)),
            ((half_w, -inner_h), (inner_w, -half_h)),
            ((half_w, inner_h), (inner_w, half_h)),
            ((-inner_w, -half_h), (-collector_w, -inner_h)),
            ((inner_w, -half_h), (collector_w, -inner_h)),
            ((-inner_w, half_h), (-collector_w, inner_h)),
            ((inner_w, half_h), (collector_w, inner_h)),
        ),
        "diagonal_spines": (
            ((-west_inner, -south_collector), (-west_collector, 126.0)),
            ((-west_collector, 126.0), (-west_inner, north_collector)),
            ((east_inner, -south_collector), (east_collector, 126.0)),
            ((east_collector, 126.0), (east_inner, north_inner)),
            ((-west_inner, -south_inner), (-west_bank * 0.25, -south_collector)),
            ((east_bank * 0.42, north_collector), (east_inner, north_inner)),
        ),
        "edge_fracture_spurs": (
            ((-west_outer, -south_collector), (-west_inner * 0.84, -south_inner * 0.64)),
            ((-west_outer, north_collector), (-west_inner * 0.88, north_inner * 0.58)),
            ((east_outer, -south_collector), (east_inner * 0.92, -south_inner * 0.52)),
            ((east_outer, north_collector), (east_inner * 0.76, north_inner * 0.72)),
            ((-west_inner * 0.92, -south_outer), (-west_collector * 0.78, -south_inner * 0.72)),
            ((east_inner * 0.72, north_outer), (east_collector * 0.64, north_inner * 0.74)),
            ((-west_outer * 0.94, 126.0), (-west_bank * 0.42, north_collector * 0.42)),
            ((east_outer * 0.92, 126.0), (east_bank * 0.54, -south_collector * 0.34)),
        ),
        "fringe_spillover_spurs": (
            ((-west_outer * 0.96, north_outer * 0.86), (-half_w * 1.12, half_h * 0.98)),
            ((east_outer * 0.94, north_outer * 0.84), (half_w * 1.04, half_h * 1.02)),
            ((-west_outer * 0.96, -south_outer * 0.88), (-half_w * 1.10, -half_h * 1.04)),
            ((east_outer * 0.92, -south_outer * 0.86), (half_w * 1.02, -half_h * 1.02)),
            ((-west_inner * 0.82, north_outer * 0.92), (-half_w * 0.98, half_h * 1.08)),
            ((east_inner * 0.78, -south_outer * 0.92), (half_w * 0.94, -half_h * 1.08)),
        ),
        "shell_fragment_pairs": (
            ((-west_outer, north_inner), (-west_collector * 1.02, north_outer * 1.02)),
            ((east_outer, north_collector), (east_collector * 1.08, north_outer * 1.04)),
            ((-west_outer, -south_collector), (-west_collector * 0.96, -south_outer * 1.04)),
            ((east_outer, -south_inner), (east_collector * 1.04, -south_outer * 1.02)),
            ((-west_outer * 0.56, north_outer), (-west_inner * 0.16, north_outer * 0.86)),
            ((east_outer * 0.52, north_outer), (east_inner * 0.14, north_outer * 0.84)),
            ((-west_outer * 0.54, -south_outer), (-west_inner * 0.14, -south_outer * 0.84)),
            ((east_outer * 0.50, -south_outer), (east_inner * 0.12, -south_outer * 0.82)),
        ),
        "terrain_drift_pairs": (
            ((-west_outer * 0.78, north_collector * 0.92), (-west_bank * 0.18, north_outer * 1.04)),
            ((east_bank * 0.22, north_inner * 0.88), (east_outer * 0.82, north_outer * 1.06)),
            ((-west_outer * 0.74, -south_inner * 0.82), (-west_bank * 0.16, -south_outer * 1.04)),
            ((east_bank * 0.18, -south_collector * 0.86), (east_outer * 0.84, -south_outer * 1.02)),
        ),
        "tapered_corridor_spurs": (),
    }


def _build_polycentric_mesh(*, seed: int, width: int, height: int) -> dict[str, object]:
    half_w = float(width) * 0.36
    half_h = float(height) * 0.36
    span_x = half_w * 0.55
    span_y = half_h * 0.55
    subcenter_points = (
        (-span_x, -span_y),
        (span_x, -span_y),
        (-span_x, span_y),
        (span_x, span_y),
        (0.0, -half_h * 0.88),
        (0.0, half_h * 0.88),
    )
    return {
        "style_id": "polycentric_tod",
        "seed": int(seed),
        "bounds": {"width": int(width), "height": int(height)},
        "downtown_anchor": (0.0, 0.0),
        "subcenter_points": subcenter_points,
        "outer_ring_bounds": (-half_w, half_w, -half_h, half_h),
        "inner_ring_bounds": (-span_x * 1.08, span_x * 1.08, -span_y * 1.08, span_y * 1.08),
        "collector_ring_bounds": (-span_x * 0.7, span_x * 0.7, -span_y * 0.7, span_y * 0.7),
        "x_levels": (-half_w, -span_x, -span_x * 0.45, 0.0, span_x * 0.45, span_x, half_w),
        "y_levels": (-half_h, -span_y, -span_y * 0.45, 0.0, span_y * 0.45, span_y, half_h),
        "bridge_rows": (),
        "river_bank_x": (),
        "barrier_polylines": (),
        "outer_frame_gap_segments": (
            ("h", 0, 0),
            ("h", 0, 5),
            ("h", 6, 0),
            ("h", 6, 5),
            ("h", 6, 3),
            ("v", 6, 3),
        ),
        "interior_gap_segments": (),
        "frame_cut_in_pairs": (
            ((-half_w, -span_y), (-span_x, -half_h)),
            ((half_w, -span_y), (span_x, -half_h)),
            ((-half_w, span_y), (-span_x, half_h)),
            ((half_w, span_y), (span_x, half_h)),
        ),
        "diagonal_spines": (
            ((-span_x, -span_y), (-span_x * 0.08, -span_y * 0.10)),
            ((-span_x, span_y), (-span_x * 0.05, span_y * 0.18)),
            ((span_x, span_y), (span_x * 0.18, span_y * 0.12)),
            ((0.0, half_h * 0.88), (span_x * 0.08, span_y * 0.18)),
        ),
        "edge_fracture_spurs": (),
        "fringe_spillover_spurs": (
            ((-half_w * 0.92, span_y * 0.88), (-half_w * 1.10, half_h * 0.96)),
            ((half_w * 0.92, span_y * 0.88), (half_w * 1.10, half_h * 0.96)),
            ((-half_w * 0.92, -span_y * 0.84), (-half_w * 1.08, -half_h * 0.98)),
            ((half_w * 0.92, -span_y * 0.82), (half_w * 1.08, -half_h * 0.98)),
            ((0.0, half_h * 0.88), (span_x * 0.14, half_h * 1.12)),
            ((0.0, -half_h * 0.88), (-span_x * 0.12, -half_h * 1.10)),
        ),
        "shell_fragment_pairs": (
            ((-half_w, 0.0), (-span_x * 0.92, span_y * 0.16)),
            ((half_w, 0.0), (span_x * 0.92, -span_y * 0.12)),
            ((0.0, half_h), (span_x * 0.22, span_y * 0.76)),
            ((0.0, -half_h), (-span_x * 0.22, -span_y * 0.74)),
            ((-span_x * 0.58, half_h), (-span_x * 0.10, span_y * 0.72)),
            ((span_x * 0.54, half_h), (span_x * 0.08, span_y * 0.70)),
            ((-span_x * 0.56, -half_h), (-span_x * 0.12, -span_y * 0.70)),
            ((span_x * 0.52, -half_h), (span_x * 0.10, -span_y * 0.72)),
        ),
        "terrain_drift_pairs": (
            ((-half_w * 0.84, -span_y * 0.18), (-span_x * 0.34, -half_h * 0.86)),
            ((half_w * 0.82, -span_y * 0.12), (span_x * 0.28, -half_h * 0.84)),
            ((-half_w * 0.86, span_y * 0.22), (-span_x * 0.36, half_h * 0.82)),
            ((half_w * 0.84, span_y * 0.18), (span_x * 0.24, half_h * 0.84)),
        ),
        "tapered_corridor_spurs": (
            ((-half_w, -span_y * 0.65), (-span_x * 0.78, -span_y * 0.18)),
            ((half_w, -span_y * 0.42), (span_x * 0.74, -span_y * 0.08)),
            ((-half_w * 0.92, span_y * 0.56), (-span_x * 0.66, span_y * 0.12)),
            ((half_w * 0.88, span_y * 0.82), (span_x * 0.54, span_y * 0.28)),
        ),
    }
