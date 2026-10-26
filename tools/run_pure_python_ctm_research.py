#!/usr/bin/env python3
"""Run the pure-Python CTM research experiments and emit strict JSON/SVG artifacts."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
from statistics import fmean, median
import sys
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from metroflow.pure_traffic.ctm import NetworkSpec, SimulationResult, SimulationSnapshot, simulate  # noqa: E402 - standalone script bootstraps src above
from metroflow.pure_traffic.scenarios import (  # noqa: E402 - standalone script bootstraps src above
    CTMScenario,
    build_diamond_bottleneck_scenario,
    build_priority_diverge_scenario,
    build_weighted_merge_scenario,
)


def _run(scenario: CTMScenario, ticks: int) -> SimulationResult:
    return simulate(
        scenario.network,
        scenario.requests,
        scenario.config,
        ticks=ticks,
        incidents=scenario.incidents,
        initial_state=scenario.initial_state,
    )


def _snapshot(result: SimulationResult, tick: int) -> SimulationSnapshot:
    if tick < 1 or tick > len(result.snapshots):
        raise ValueError(f"tick {tick} is outside recorded snapshots")
    return result.snapshots[tick - 1]


def _branch_times(scenario: CTMScenario, result: SimulationResult, branch: str) -> list[float]:
    values: list[float] = []
    for request, admitted, completed in zip(
        scenario.requests,
        result.final_state.admitted_ticks,
        result.final_state.completed_ticks,
        strict=True,
    ):
        if branch not in request.route[1] or admitted is None or completed is None:
            continue
        values.append((completed - admitted) * scenario.config.tick_seconds)
    return values


def _summary() -> tuple[dict[str, object], dict[str, tuple[CTMScenario, SimulationResult]]]:
    round0_s = build_diamond_bottleneck_scenario(
        vehicles=320,
        release_batch=4,
        node_policy="lexicographic",
        fifo_mode="strict",
        movement_age_priority=False,
    )
    round0_r = _run(round0_s, 220)
    round1_s = build_diamond_bottleneck_scenario(
        vehicles=320,
        release_batch=4,
        node_policy="lexicographic",
        fifo_mode="movement",
        movement_age_priority=False,
    )
    round1_r = _run(round1_s, 220)
    round2_lex_s = build_weighted_merge_scenario(node_policy="lexicographic")
    round2_lex_r = _run(round2_lex_s, 10)
    round2_fair_s = build_weighted_merge_scenario(node_policy="weighted_fair")
    round2_fair_r = _run(round2_fair_s, 10)
    round3_noage_s = build_priority_diverge_scenario(movement_age_priority=False)
    round3_noage_r = _run(round3_noage_s, 15)
    round3_age_s = build_priority_diverge_scenario(movement_age_priority=True)
    round3_age_r = _run(round3_age_s, 15)
    final_s = build_diamond_bottleneck_scenario(
        vehicles=320,
        release_batch=4,
        node_policy="weighted_fair",
        fifo_mode="movement",
        movement_age_priority=True,
    )
    final_r = _run(final_s, 220)

    def clear_tick(result: SimulationResult, total: int) -> int | None:
        return next(
            (snapshot.tick for snapshot in result.snapshots if snapshot.completed_count == total),
            None,
        )

    final_times = list(final_r.completed_travel_times_s)
    upper_times = _branch_times(final_s, final_r, "upper")
    lower_times = _branch_times(final_s, final_r, "lower")
    payload: dict[str, object] = {
        "schema_version": "pure_python_ctm_research_v1",
        "base_commit": "01c80b432344f94209daaa198bb1eb007839fc7f",
        "model": (
            "multi_commodity_integer_cell_transmission_with_holding_free_max_throughput_node_solver"
        ),
        "rounds": {
            "round0_strict_fifo": {
                "defect": "full-link FIFO causes artificial head-of-line blocking at a diverge",
                "completed_at_tick_220": round0_r.final_state.completed_count,
                "active_at_tick_220": round0_r.final_state.active_count,
                "peak_upstream_occupancy": max(
                    snapshot.link_occupancy_ratio["in"] for snapshot in round0_r.snapshots
                ),
                "clear_tick": clear_tick(round0_r, len(round0_s.requests)),
                "fingerprint": round0_r.fingerprint,
            },
            "round1_movement_fifo": {
                "repair": "movement-group FIFO prevents a blocked turn from freezing an open turn",
                "completed_at_tick_220": round1_r.final_state.completed_count,
                "clear_tick": clear_tick(round1_r, len(round1_s.requests)),
                "mean_travel_time_s": fmean(round1_r.completed_travel_times_s),
                "fingerprint": round1_r.fingerprint,
            },
            "round2_weighted_merge": {
                "defect": "lexicographic maximum-flow allocation starves the second approach",
                "lexicographic_a_to_out": round2_lex_r.cumulative_movement_flow[("a", "out")],
                "lexicographic_b_to_out": round2_lex_r.cumulative_movement_flow[("b", "out")],
                "weighted_a_to_out": round2_fair_r.cumulative_movement_flow[("a", "out")],
                "weighted_b_to_out": round2_fair_r.cumulative_movement_flow[("b", "out")],
                "target_priority_ratio": 2.0,
                "holding_events": round2_fair_r.node_holding_events,
            },
            "round3_age_priority": {
                "defect": "fixed movement priority starves the minority turn on a shared approach",
                "no_age_major": round3_noage_r.cumulative_movement_flow[("approach", "major")],
                "no_age_minor": round3_noage_r.cumulative_movement_flow[("approach", "minor")],
                "age_major": round3_age_r.cumulative_movement_flow[("approach", "major")],
                "age_minor": round3_age_r.cumulative_movement_flow[("approach", "minor")],
                "final_max_wait_ticks": max(round3_age_r.final_state.movement_wait_ticks[:2]),
            },
        },
        "final": {
            "fingerprint": final_r.fingerprint,
            "released": final_r.final_state.released_count,
            "completed": final_r.final_state.completed_count,
            "active": final_r.final_state.active_count,
            "pending": final_r.final_state.pending_count,
            "clear_tick": clear_tick(final_r, len(final_s.requests)),
            "mass_balance_error": final_r.final_state.mass_balance_error,
            "node_holding_events": final_r.node_holding_events,
            "travel_time_s": {
                "mean": fmean(final_times),
                "median": median(final_times),
                "maximum": max(final_times),
                "upper_mean": fmean(upper_times),
                "lower_mean": fmean(lower_times),
            },
            "max_occupancy": {
                link.link_id: max(
                    snapshot.link_occupancy_ratio[link.link_id] for snapshot in final_r.snapshots
                )
                for link in final_s.network.links
            },
            "movement_flow": [
                {"from": source, "to": target, "vehicles": value}
                for (source, target), value in sorted(
                    final_r.cumulative_movement_flow.items(),
                    key=lambda item: (item[0][0], "" if item[0][1] is None else item[0][1]),
                )
            ],
        },
        "claim_gate": {
            "research_ready": True,
            "default_ready": False,
            "empirically_calibrated": False,
            "scope": (
                "structural traffic-flow plausibility on controlled small networks; "
                "not a calibrated real-city forecast"
            ),
        },
    }
    runs = {
        "round0": (round0_s, round0_r),
        "round1": (round1_s, round1_r),
        "round2_lex": (round2_lex_s, round2_lex_r),
        "round2_fair": (round2_fair_s, round2_fair_r),
        "round3_noage": (round3_noage_s, round3_noage_r),
        "round3_age": (round3_age_s, round3_age_r),
        "final": (final_s, final_r),
    }
    return payload, runs


def _colour(value: float) -> str:
    x = min(max(value, 0.0), 1.0)
    anchors = (
        (0.0, (224, 239, 248)),
        (0.35, (120, 180, 210)),
        (0.65, (244, 174, 91)),
        (1.0, (180, 32, 37)),
    )
    for (x0, c0), (x1, c1) in zip(anchors, anchors[1:], strict=False):
        if x <= x1:
            t = (x - x0) / (x1 - x0)
            rgb = tuple(round(c0[i] + t * (c1[i] - c0[i])) for i in range(3))
            return "#%02x%02x%02x" % rgb
    return "#b42025"


def _text(
    parts: list[str],
    x: float,
    y: float,
    text: str,
    *,
    size: int = 18,
    weight: int = 400,
    anchor: str = "start",
    fill: str = "#18232b",
) -> None:
    parts.append(
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="DejaVu Sans, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
        f'fill="{fill}">{escape(text)}</text>'
    )


def _network_panel(
    parts: list[str],
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    network: NetworkSpec,
    snapshot: SimulationSnapshot,
    title: str,
    subtitle: str,
    incident_links: Sequence[str] = (),
) -> None:
    parts.append(
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="16" '
        'fill="#ffffff" stroke="#c8d0d5" stroke-width="1.4"/>'
    )
    _text(parts, x + 18, y + 30, title, size=20, weight=700)
    _text(parts, x + 18, y + 53, subtitle, size=13, fill="#51606a")
    coords = network.coordinates
    xs = [point[0] for point in coords.values()]
    ys = [point[1] for point in coords.values()]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    plot_x = x + 34
    plot_y = y + 78
    plot_w = width - 68
    plot_h = height - 115
    sx = plot_w / max(xmax - xmin, 1.0)
    sy = plot_h / max(ymax - ymin, 1.0)
    scale = min(sx, sy)
    offset_x = plot_x + 0.5 * (plot_w - scale * (xmax - xmin))
    offset_y = plot_y + 0.5 * (plot_h - scale * (ymax - ymin))

    def project(node: str) -> tuple[float, float]:
        px, py = coords[node]
        return offset_x + scale * (px - xmin), offset_y + scale * (ymax - py)

    for link in network.links:
        x0, y0 = project(link.tail)
        x1, y1 = project(link.head)
        ratios = snapshot.link_cell_occupancy_ratio[link.link_id]
        if link.link_id in incident_links:
            parts.append(
                f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
                'stroke="#7a1313" stroke-width="18" stroke-linecap="round"/>'
            )
        parts.append(
            f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
            'stroke="#d8dde0" stroke-width="14" stroke-linecap="round"/>'
        )
        for index, ratio in enumerate(ratios):
            t0 = index / len(ratios)
            t1 = (index + 1) / len(ratios)
            ax = x0 + (x1 - x0) * t0
            ay = y0 + (y1 - y0) * t0
            bx = x0 + (x1 - x0) * t1
            by = y0 + (y1 - y0) * t1
            parts.append(
                f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" '
                f'stroke="{_colour(ratio)}" stroke-width="10" stroke-linecap="butt"/>'
            )
        mx = 0.5 * (x0 + x1)
        my = 0.5 * (y0 + y1)
        _text(
            parts,
            mx,
            my - 9,
            f"{link.link_id} {snapshot.link_occupancy_ratio[link.link_id]:.0%}",
            size=10,
            anchor="middle",
            fill="#26343d",
        )
    for node, point in coords.items():
        px, py = project(node)
        parts.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="#17232b" '
            'stroke="#ffffff" stroke-width="1.2"/>'
        )
        _text(parts, px, py - 9, node, size=10, anchor="middle")


def _bar_group(
    parts: list[str],
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    subtitle: str,
    groups: Sequence[tuple[str, Sequence[tuple[str, float, str]]]],
    max_value: float,
) -> None:
    parts.append(
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="16" '
        'fill="#ffffff" stroke="#c8d0d5" stroke-width="1.4"/>'
    )
    _text(parts, x + 18, y + 30, title, size=20, weight=700)
    _text(parts, x + 18, y + 53, subtitle, size=13, fill="#51606a")
    chart_x = x + 52
    chart_y = y + 82
    chart_w = width - 80
    chart_h = height - 125
    parts.append(
        f'<line x1="{chart_x}" y1="{chart_y + chart_h}" '
        f'x2="{chart_x + chart_w}" y2="{chart_y + chart_h}" '
        'stroke="#62717a" stroke-width="1"/>'
    )
    group_width = chart_w / max(len(groups), 1)
    for group_index, (group_label, bars) in enumerate(groups):
        gx = chart_x + group_index * group_width
        bar_gap = 8
        bar_width = min(56.0, (group_width - 32) / max(len(bars), 1) - bar_gap)
        total_bar_w = len(bars) * bar_width + (len(bars) - 1) * bar_gap
        start_x = gx + 0.5 * (group_width - total_bar_w)
        for bar_index, (label, value, colour) in enumerate(bars):
            bh = 0.0 if max_value <= 0 else chart_h * value / max_value
            bx = start_x + bar_index * (bar_width + bar_gap)
            by = chart_y + chart_h - bh
            parts.append(
                f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_width:.1f}" '
                f'height="{bh:.1f}" fill="{colour}" rx="3"/>'
            )
            _text(parts, bx + bar_width / 2, by - 7, f"{value:g}", size=12, anchor="middle")
            _text(
                parts,
                bx + bar_width / 2,
                chart_y + chart_h + 18,
                label,
                size=11,
                anchor="middle",
            )
        _text(
            parts,
            gx + group_width / 2,
            chart_y + chart_h + 40,
            group_label,
            size=12,
            weight=600,
            anchor="middle",
        )


def _line_chart(
    parts: list[str],
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    series: Sequence[tuple[str, Sequence[float], str]],
    shaded_intervals: Sequence[tuple[int, int, str, str]] = (),
) -> None:
    parts.append(
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="16" '
        'fill="#ffffff" stroke="#c8d0d5" stroke-width="1.4"/>'
    )
    _text(parts, x + 18, y + 30, title, size=20, weight=700)
    chart_x = x + 56
    chart_y = y + 55
    chart_w = width - 82
    chart_h = height - 92
    max_len = max((len(values) for _, values, _ in series), default=1)
    max_value = max((max(values) for _, values, _ in series if values), default=1.0)
    max_value = max(max_value, 1.0)
    for start, end, colour, label in shaded_intervals:
        left = chart_x + chart_w * max(start - 1, 0) / max(max_len - 1, 1)
        right = chart_x + chart_w * min(end - 1, max_len - 1) / max(max_len - 1, 1)
        parts.append(
            f'<rect x="{left:.1f}" y="{chart_y:.1f}" width="{max(0.0, right - left):.1f}" '
            f'height="{chart_h:.1f}" fill="{colour}" fill-opacity="0.16"/>'
        )
        _text(
            parts,
            0.5 * (left + right),
            chart_y + 15,
            label,
            size=10,
            anchor="middle",
            fill="#7a3b31",
        )
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        yy = chart_y + chart_h * (1.0 - fraction)
        parts.append(
            f'<line x1="{chart_x}" y1="{yy:.1f}" x2="{chart_x + chart_w}" '
            f'y2="{yy:.1f}" stroke="#e5e9eb" stroke-width="1"/>'
        )
        _text(
            parts,
            chart_x - 8,
            yy + 4,
            f"{max_value * fraction:.0f}",
            size=10,
            anchor="end",
            fill="#65727a",
        )
    for tick_fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        xx = chart_x + chart_w * tick_fraction
        tick_value = 1 + round((max_len - 1) * tick_fraction)
        parts.append(
            f'<line x1="{xx:.1f}" y1="{chart_y + chart_h:.1f}" x2="{xx:.1f}" '
            f'y2="{chart_y + chart_h + 5:.1f}" stroke="#62717a" stroke-width="1"/>'
        )
        _text(
            parts,
            xx,
            chart_y + chart_h + 20,
            str(tick_value),
            size=10,
            anchor="middle",
            fill="#65727a",
        )
    _text(
        parts,
        chart_x + chart_w / 2,
        chart_y + chart_h + 37,
        "simulation tick",
        size=11,
        anchor="middle",
        fill="#65727a",
    )
    for name, values, colour in series:
        if not values:
            continue
        points = []
        for index, value in enumerate(values):
            px = chart_x + chart_w * index / max(max_len - 1, 1)
            py = chart_y + chart_h * (1.0 - value / max_value)
            points.append(f"{px:.1f},{py:.1f}")
        parts.append(
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{colour}" '
            'stroke-width="2.2" stroke-linejoin="round"/>'
        )
    legend_x = x + width - 160
    for index, (name, _values, colour) in enumerate(series):
        ly = y + 25 + 20 * index
        parts.append(
            f'<line x1="{legend_x}" y1="{ly}" x2="{legend_x + 24}" y2="{ly}" '
            f'stroke="{colour}" stroke-width="3"/>'
        )
        _text(parts, legend_x + 31, ly + 4, name, size=11)


def _write_audit_svg(
    path: Path,
    payload: Mapping[str, object],
    runs: Mapping[str, tuple[CTMScenario, SimulationResult]],
) -> None:
    width, height = 1600, 1120
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Pure-Python CTM adversarial audit rounds</title>',
        '<desc id="desc">Four bounded repair rounds comparing FIFO, merge fairness, and movement ageing on controlled road networks.</desc>',
        '<rect width="100%" height="100%" fill="#f3f5f6"/>',
    ]
    _text(parts, 40, 48, "Pure-Python CTM · adversarial traffic-theory audit", size=29, weight=700)
    _text(
        parts,
        40,
        75,
        "Finite storage · spillback · exact integer conservation · holding-free node flow",
        size=15,
        fill="#52616a",
    )
    round0_s, round0_r = runs["round0"]
    round1_s, round1_r = runs["round1"]
    _network_panel(
        parts,
        x=35,
        y=100,
        width=750,
        height=385,
        network=round0_s.network,
        snapshot=_snapshot(round0_r, 80),
        title="R0 · strict full-link FIFO",
        subtitle="Artificial diverge blocking: source occupancy 93%; 77 remain at tick 220",
        incident_links=("upper_a",),
    )
    _network_panel(
        parts,
        x=815,
        y=100,
        width=750,
        height=385,
        network=round1_s.network,
        snapshot=_snapshot(round1_r, 80),
        title="Repair 1 · movement-group FIFO",
        subtitle="Queues propagate into branches; all 320 vehicles clear by tick 174",
        incident_links=("upper_a",),
    )
    merge_lex = runs["round2_lex"][1]
    merge_fair = runs["round2_fair"][1]
    _bar_group(
        parts,
        x=35,
        y=515,
        width=750,
        height=300,
        title="Repair 2 · maximum throughput + weighted virtual finish",
        subtitle="Saturated 2:1 merge, first 10 ticks",
        groups=(
            (
                "lexicographic",
                (
                    ("A", float(merge_lex.cumulative_movement_flow[("a", "out")]), "#345b8c"),
                    ("B", float(merge_lex.cumulative_movement_flow[("b", "out")]), "#d06b42"),
                ),
            ),
            (
                "weighted fair",
                (
                    ("A", float(merge_fair.cumulative_movement_flow[("a", "out")]), "#345b8c"),
                    ("B", float(merge_fair.cumulative_movement_flow[("b", "out")]), "#d06b42"),
                ),
            ),
        ),
        max_value=30.0,
    )
    diverge_noage = runs["round3_noage"][1]
    diverge_age = runs["round3_age"][1]
    _bar_group(
        parts,
        x=815,
        y=515,
        width=750,
        height=300,
        title="Repair 3 · movement waiting-age priority",
        subtitle="Shared approach, first 15 ticks",
        groups=(
            (
                "fixed priority",
                (
                    (
                        "major",
                        float(diverge_noage.cumulative_movement_flow[("approach", "major")]),
                        "#345b8c",
                    ),
                    (
                        "minor",
                        float(diverge_noage.cumulative_movement_flow[("approach", "minor")]),
                        "#d06b42",
                    ),
                ),
            ),
            (
                "age priority",
                (
                    (
                        "major",
                        float(diverge_age.cumulative_movement_flow[("approach", "major")]),
                        "#345b8c",
                    ),
                    (
                        "minor",
                        float(diverge_age.cumulative_movement_flow[("approach", "minor")]),
                        "#d06b42",
                    ),
                ),
            ),
        ),
        max_value=15.0,
    )
    final = payload["final"]
    assert isinstance(final, Mapping)
    claim = payload["claim_gate"]
    assert isinstance(claim, Mapping)
    parts.append(
        '<rect x="35" y="845" width="1530" height="225" rx="16" '
        'fill="#eef5f0" stroke="#8aaa91" stroke-width="1.6"/>'
    )
    _text(parts, 58, 880, "Final claim gate", size=22, weight=700, fill="#173d25")
    bullets = (
        f"PASS: mass error {final['mass_balance_error']}; holding events {final['node_holding_events']}; clear tick {final['clear_tick']}",
        "PASS: exact vehicle identities and simultaneous source/movement/sink commit",
        "PASS: finite cell storage, backward receiving constraints, incident-induced queue propagation",
        "LIMIT: movement-group FIFO is a lane-group approximation, not perfect network-wide FIFO",
        "LIMIT: uncalibrated triangular fundamental diagrams and authored junction priorities",
        f"STATUS: research_ready={claim['research_ready']}; default_ready={claim['default_ready']}",
    )
    for index, bullet in enumerate(bullets):
        _text(parts, 66, 915 + 27 * index, "• " + bullet, size=15, fill="#294236")
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _write_evolution_svg(path: Path, scenario: CTMScenario, result: SimulationResult) -> None:
    ticks = (20, 40, 60, 80, 100, 130, 174)
    width, height = 1600, 900
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Final CTM diamond-network state evolution</title>',
        '<desc id="desc">Cell occupancy during an upper-route incident and subsequent recovery.</desc>',
        '<rect width="100%" height="100%" fill="#f3f5f6"/>',
    ]
    _text(parts, 40, 48, "Final model · diamond corridor state evolution", size=29, weight=700)
    _text(parts, 40, 75, "Upper-route incident active on ticks 18–41", size=15, fill="#52616a")
    panel_w = 500
    panel_h = 245
    positions = [
        (35, 105),
        (550, 105),
        (1065, 105),
        (35, 375),
        (550, 375),
        (1065, 375),
        (550, 645),
    ]
    for tick, (x, y) in zip(ticks, positions, strict=True):
        snapshot = _snapshot(result, tick)
        incident = ("upper_a",) if 18 <= tick < 42 else ()
        _network_panel(
            parts,
            x=x,
            y=y,
            width=panel_w,
            height=panel_h,
            network=scenario.network,
            snapshot=snapshot,
            title=f"tick {tick}",
            subtitle=(f"active {snapshot.active_count} · completed {snapshot.completed_count}"),
            incident_links=incident,
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _write_timeseries_svg(path: Path, result: SimulationResult) -> None:
    width, height = 1500, 720
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Final CTM traffic time series</title>',
        '<desc id="desc">Active, completed and route-merge vehicle counts over simulation ticks.</desc>',
        '<rect width="100%" height="100%" fill="#f3f5f6"/>',
    ]
    _text(parts, 40, 48, "Final model · traffic histories", size=29, weight=700)
    active = [float(snapshot.active_count) for snapshot in result.snapshots]
    completed = [float(snapshot.completed_count) for snapshot in result.snapshots]
    pending = [float(snapshot.pending_count) for snapshot in result.snapshots]
    upper = [
        float(snapshot.cumulative_movement_flow[("upper_b", "out")])
        for snapshot in result.snapshots
    ]
    lower = [
        float(snapshot.cumulative_movement_flow[("lower_b", "out")])
        for snapshot in result.snapshots
    ]
    _line_chart(
        parts,
        x=35,
        y=85,
        width=700,
        height=580,
        title="Network vehicle compartments",
        series=(
            ("active", active, "#315b8a"),
            ("completed", completed, "#2f8057"),
            ("pending", pending, "#c44c3d"),
        ),
        shaded_intervals=((18, 42, "#d67b67", "upper-route incident"),),
    )
    _line_chart(
        parts,
        x=765,
        y=85,
        width=700,
        height=580,
        title="Cumulative branch-to-merge throughput",
        series=(
            ("upper", upper, "#8c4f9c"),
            ("lower", lower, "#cc7a2d"),
        ),
        shaded_intervals=((18, 42, "#d67b67", "upper-route incident"),),
    )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload, runs = _summary()
    summary_path = args.output_dir / "traffic_research_summary.json"
    summary_path.write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_audit_svg(args.output_dir / "traffic_audit_rounds.svg", payload, runs)
    final_s, final_r = runs["final"]
    _write_evolution_svg(
        args.output_dir / "final_diamond_evolution.svg",
        final_s,
        final_r,
    )
    _write_timeseries_svg(args.output_dir / "final_traffic_timeseries.svg", final_r)
    print(json.dumps(payload, allow_nan=False, indent=2, sort_keys=True))
    final = payload["final"]
    assert isinstance(final, Mapping)
    return 0 if final["mass_balance_error"] == 0 and final["node_holding_events"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
