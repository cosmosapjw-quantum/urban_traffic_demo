"""Benchmark report utility skeletons for MetroFlow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from html import escape
import json
from typing import Any, Mapping

__all__ = [
    "BenchmarkReport",
    "benchmark_report_from_run_summary",
    "format_benchmark_report_markdown",
    "format_runtime_benchmark_suite_markdown",
    "render_runtime_benchmark_suite_html",
    "runtime_benchmark_suite_to_dict",
]


@dataclass(slots=True)
class BenchmarkReport:
    """PR/review friendly benchmark summary payload.

    This mirrors the planned benchmark reporting template while staying usable
    before the full benchmark runner and summary aggregation land.
    """

    scenario_id: str
    seed: int
    population_target: int | None = None
    active_agent_median: float | None = None
    active_agent_p95: float | None = None
    duration_ticks: int | None = None
    duration_seconds: float | None = None
    tick_rate_median_hz: float | None = None
    tick_rate_p10_hz: float | None = None
    invariant_violations: dict[str, int] = field(default_factory=dict)
    route_candidate_refresh_total: int | None = None
    route_candidate_reuse_total: int | None = None
    dynamic_potential_recompute_total: int | None = None
    dynamic_potential_cache_hits_total: int | None = None
    route_path_size_gamma: float | None = None
    route_candidate_refresh_seconds_total: float | None = None
    dynamic_potential_recompute_seconds_total: float | None = None
    routing_compile_seconds_estimate_total: float | None = None
    event_mix: str | None = None
    ui_mode: str | None = None
    environment: str | None = None
    map_foundation_profile: str | None = None
    map_foundation_overall_pass: bool | None = None
    map_foundation_failed_checks: tuple[str, ...] = field(default_factory=tuple)
    radical_gate_profile: str | None = None
    radical_gate_overall_pass: bool | None = None
    radical_gate_failed_checks: tuple[str, ...] = field(default_factory=tuple)
    radical_active_bbox_aspect_ratio: float | None = None
    radical_axis_aligned_link_share: float | None = None
    radical_district_anisotropy_score: float | None = None
    radical_one_tick_runtime_seconds_median: float | None = None
    radical_fr002a_non_regression_pass: bool | None = None
    radical_fr005b_non_regression_pass: bool | None = None
    radical_fr006a_non_regression_pass: bool | None = None
    radical_fr006b_non_regression_pass: bool | None = None


def benchmark_report_from_run_summary(
    run_summary: Mapping[str, Any],
    *,
    population_target: int | None = None,
    active_agent_median: float | None = None,
    active_agent_p95: float | None = None,
    duration_ticks: int | None = None,
    duration_seconds: float | None = None,
    event_mix: str | None = None,
    ui_mode: str | None = None,
    environment: str | None = None,
) -> BenchmarkReport:
    """Build a `BenchmarkReport` from a RunSummary-like mapping.

    The RunSummary fields are specified in the phase-1 data model. Extra
    benchmark-only values remain optional until benchmark aggregation is added.
    """

    invariant_counts = run_summary.get("invariant_violation_counts", {})
    if not isinstance(invariant_counts, Mapping):
        invariant_counts = {}

    return BenchmarkReport(
        scenario_id=str(run_summary.get("scenario_id", "unknown")),
        seed=int(run_summary.get("seed", 0)),
        population_target=population_target,
        active_agent_median=active_agent_median,
        active_agent_p95=active_agent_p95,
        duration_ticks=duration_ticks,
        duration_seconds=duration_seconds,
        tick_rate_median_hz=_as_optional_float(run_summary.get("tick_rate_median")),
        tick_rate_p10_hz=_as_optional_float(run_summary.get("tick_rate_p10")),
        invariant_violations={str(k): int(v) for k, v in invariant_counts.items()},
        route_candidate_refresh_total=_as_optional_int(run_summary.get("route_candidate_refresh_total")),
        route_candidate_reuse_total=_as_optional_int(run_summary.get("route_candidate_reuse_total")),
        dynamic_potential_recompute_total=_as_optional_int(run_summary.get("dynamic_potential_recompute_total")),
        dynamic_potential_cache_hits_total=_as_optional_int(run_summary.get("dynamic_potential_cache_hits_total")),
        route_path_size_gamma=_as_optional_float(run_summary.get("route_path_size_gamma")),
        route_candidate_refresh_seconds_total=_as_optional_float(
            run_summary.get("route_candidate_refresh_seconds_total")
        ),
        dynamic_potential_recompute_seconds_total=_as_optional_float(
            run_summary.get("dynamic_potential_recompute_seconds_total")
        ),
        routing_compile_seconds_estimate_total=_as_optional_float(
            run_summary.get("routing_compile_seconds_estimate_total")
        ),
        event_mix=event_mix,
        ui_mode=ui_mode,
        environment=environment,
        map_foundation_profile=(
            str(run_summary["map_foundation_profile"])
            if "map_foundation_profile" in run_summary
            else None
        ),
        map_foundation_overall_pass=(
            bool(run_summary["map_foundation_overall_pass"])
            if "map_foundation_overall_pass" in run_summary
            else None
        ),
        map_foundation_failed_checks=tuple(
            str(item) for item in (run_summary.get("map_foundation_failed_checks") or ())
        ),
        radical_gate_profile=(
            str(run_summary["radical_gate_profile"])
            if "radical_gate_profile" in run_summary
            else None
        ),
        radical_gate_overall_pass=(
            bool(run_summary["radical_gate_overall_pass"])
            if "radical_gate_overall_pass" in run_summary
            else None
        ),
        radical_gate_failed_checks=tuple(
            str(item) for item in (run_summary.get("radical_gate_failed_checks") or ())
        ),
        radical_active_bbox_aspect_ratio=_as_optional_float(
            run_summary.get("radical_active_bbox_aspect_ratio")
        ),
        radical_axis_aligned_link_share=_as_optional_float(
            run_summary.get("radical_axis_aligned_link_share")
        ),
        radical_district_anisotropy_score=_as_optional_float(
            run_summary.get("radical_district_anisotropy_score")
        ),
        radical_one_tick_runtime_seconds_median=_as_optional_float(
            run_summary.get("radical_one_tick_runtime_seconds_median")
        ),
        radical_fr002a_non_regression_pass=(
            bool(run_summary["radical_fr002a_non_regression_pass"])
            if "radical_fr002a_non_regression_pass" in run_summary
            else None
        ),
        radical_fr005b_non_regression_pass=(
            bool(run_summary["radical_fr005b_non_regression_pass"])
            if "radical_fr005b_non_regression_pass" in run_summary
            else None
        ),
        radical_fr006a_non_regression_pass=(
            bool(run_summary["radical_fr006a_non_regression_pass"])
            if "radical_fr006a_non_regression_pass" in run_summary
            else None
        ),
        radical_fr006b_non_regression_pass=(
            bool(run_summary["radical_fr006b_non_regression_pass"])
            if "radical_fr006b_non_regression_pass" in run_summary
            else None
        ),
    )


def format_benchmark_report_markdown(report: BenchmarkReport) -> str:
    """Render the planned benchmark review template as markdown bullets."""

    return "\n".join(
        [
            f"- Scenario ID: {report.scenario_id}",
            f"- Seed: {report.seed}",
            f"- Population target: {_fmt(report.population_target)}",
            (
                "- Active agent median/p95: "
                f"{_fmt(report.active_agent_median)} / {_fmt(report.active_agent_p95)}"
            ),
            (
                "- Duration (ticks / real time): "
                f"{_fmt(report.duration_ticks)} / {_fmt(report.duration_seconds)}"
            ),
            f"- Median tick rate (Hz): {_fmt(report.tick_rate_median_hz)}",
            f"- p10 tick rate (Hz): {_fmt(report.tick_rate_p10_hz)}",
            f"- Invariant violations (counts): {_fmt_mapping(report.invariant_violations)}",
            (
                "- Routing perf (candidate refresh/reuse, dyn-potential recompute/cache-hit): "
                f"{_fmt(report.route_candidate_refresh_total)} / "
                f"{_fmt(report.route_candidate_reuse_total)} / "
                f"{_fmt(report.dynamic_potential_recompute_total)} / "
                f"{_fmt(report.dynamic_potential_cache_hits_total)}"
            ),
            f"- Route path-size gamma: {_fmt(report.route_path_size_gamma)}",
            (
                "- Routing perf seconds (candidate refresh / dyn-potential / compile-estimate): "
                f"{_fmt(report.route_candidate_refresh_seconds_total)} / "
                f"{_fmt(report.dynamic_potential_recompute_seconds_total)} / "
                f"{_fmt(report.routing_compile_seconds_estimate_total)}"
            ),
            f"- Event mix (if any): {_fmt(report.event_mix)}",
            f"- UI mode (off / stream): {_fmt(report.ui_mode)}",
            f"- Environment (ROCm container image + GPU/CPU): {_fmt(report.environment)}",
            f"- Map foundation profile: {_fmt(report.map_foundation_profile)}",
            f"- Map foundation gate pass: {_fmt(report.map_foundation_overall_pass)}",
            (
                "- Map foundation failed checks: "
                f"{_fmt_mapping({key: 1 for key in report.map_foundation_failed_checks})}"
            ),
            f"- Radical gate profile: {_fmt(report.radical_gate_profile)}",
            f"- Radical gate pass: {_fmt(report.radical_gate_overall_pass)}",
            (
                "- Radical gate failed checks: "
                f"{_fmt_mapping({key: 1 for key in report.radical_gate_failed_checks})}"
            ),
            (
                "- Radical metrics (active bbox/as-aligned/anisotropy/runtime): "
                f"{_fmt(report.radical_active_bbox_aspect_ratio)} / "
                f"{_fmt(report.radical_axis_aligned_link_share)} / "
                f"{_fmt(report.radical_district_anisotropy_score)} / "
                f"{_fmt(report.radical_one_tick_runtime_seconds_median)}"
            ),
            (
                "- Radical non-regression (FR-002a/FR-005b/FR-006a/FR-006b): "
                f"{_fmt(report.radical_fr002a_non_regression_pass)} / "
                f"{_fmt(report.radical_fr005b_non_regression_pass)} / "
                f"{_fmt(report.radical_fr006a_non_regression_pass)} / "
                f"{_fmt(report.radical_fr006b_non_regression_pass)}"
            ),
        ]
    )


def format_runtime_benchmark_suite_markdown(result: Any) -> str:
    """Render a measured runtime benchmark suite result for review."""

    seeds = tuple(int(seed) for seed in getattr(result, "seeds", ()) or ())
    seed_text = ", ".join(str(seed) for seed in seeds) or "N/A"
    gate_markdown = str(getattr(result, "gpu_candidate_gate_markdown", "") or "")
    per_seed_count = len(tuple(getattr(result, "per_seed_results", ()) or ()))
    lines = [
        "- Runtime benchmark suite:",
        f"- Workload: {_fmt(getattr(result, 'workload_name', None))}",
        f"- Seeds: {seed_text}",
        f"- Seed count: {_fmt(getattr(result, 'seed_count', None))}",
        f"- Steps per seed: {_fmt(getattr(result, 'num_steps', None))}",
        f"- Wall-clock ns total: {_fmt(getattr(result, 'wall_clock_ns_total', None))}",
        f"- Per-seed results: {per_seed_count}",
    ]
    if gate_markdown:
        lines.append(gate_markdown)
    return "\n".join(lines)


def runtime_benchmark_suite_to_dict(result: Any) -> dict[str, Any]:
    """Return a JSON-safe runtime benchmark suite payload."""

    payload = _json_ready(result)
    if not isinstance(payload, dict):
        raise TypeError("runtime benchmark suite result must serialize to a mapping")
    return payload


def render_runtime_benchmark_suite_html(result: Any) -> str:
    """Render a standalone HTML review artifact for a runtime benchmark suite."""

    payload = runtime_benchmark_suite_to_dict(result)
    data_json = escape(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    stage_rows = "\n".join(
        _render_runtime_suite_stage_row(item)
        for item in _as_sequence(
            _as_mapping(payload.get("gpu_candidate_gate_report")).get("stage_summaries")
        )
    )
    seed_rows = "\n".join(
        _render_runtime_suite_seed_row(item)
        for item in _as_sequence(payload.get("per_seed_results"))
    )
    eligible = ", ".join(
        str(item)
        for item in _as_sequence(
            _as_mapping(payload.get("gpu_candidate_gate_report")).get(
                "gpu_review_eligible_stage_names"
            )
        )
    ) or "none"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Runtime Benchmark Suite</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: #f5f7fa; color: #1b2430; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 28px; }}
    h1 {{ font-size: 26px; margin: 0 0 6px; letter-spacing: 0; }}
    h2 {{ font-size: 16px; margin: 24px 0 10px; letter-spacing: 0; }}
    .meta {{ color: #5c6878; margin-bottom: 18px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }}
    .metric {{ background: #ffffff; border: 1px solid #d8dee7; border-radius: 8px; padding: 12px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 20px; }}
    table {{ width: 100%; border-collapse: collapse; background: #ffffff; border: 1px solid #d8dee7; }}
    th, td {{ border-bottom: 1px solid #e4e8ee; padding: 9px 10px; text-align: left; font-size: 13px; }}
    th {{ background: #edf1f5; font-weight: 650; }}
    .note {{ color: #5c6878; font-size: 13px; line-height: 1.45; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }}
  </style>
</head>
<body>
<main data-runtime-benchmark-suite="{data_json}">
  <h1>Runtime Benchmark Suite</h1>
  <div class="meta">workload <code>{escape(str(payload.get("workload_name", "unknown")))}</code></div>
  <section class="grid">
    <div class="metric">seeds<strong>{escape(_fmt(payload.get("seed_count")))}</strong></div>
    <div class="metric">steps per seed<strong>{escape(_fmt(payload.get("num_steps")))}</strong></div>
    <div class="metric">wall-clock ns<strong>{escape(_fmt(payload.get("wall_clock_ns_total")))}</strong></div>
    <div class="metric">eligible stages<strong>{escape(eligible)}</strong></div>
  </section>
  <h2>GPU/C++ Candidate Gate</h2>
  <table>
    <thead><tr><th>stage</th><th>candidate runs</th><th>runs</th><th>mean share</th><th>min share</th><th>max share</th><th>max ns</th><th>eligible</th></tr></thead>
    <tbody>{stage_rows}</tbody>
  </table>
  <h2>Per-Seed Runs</h2>
  <table>
    <thead><tr><th>seed</th><th>wall-clock ns</th><th>flow / routing / agent backend</th></tr></thead>
    <tbody>{seed_rows}</tbody>
  </table>
  <p class="note">This static HTML is a review artifact for backend migration planning. It is not a validation claim or GPU/C++ implementation authorization.</p>
</main>
</body>
</html>
"""


def _json_ready(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            str(key): _json_ready(item)
            for key, item in asdict(value).items()
        }
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_ready(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _render_runtime_suite_stage_row(item: Any) -> str:
    stage = _as_mapping(item)
    eligible = "yes" if bool(stage.get("gpu_review_eligible", False)) else "no"
    return (
        "<tr>"
        f"<td>{escape(str(stage.get('stage_name', 'unknown')))}</td>"
        f"<td>{escape(_fmt(stage.get('candidate_run_count')))}</td>"
        f"<td>{escape(_fmt(stage.get('deterministic_run_count')))}</td>"
        f"<td>{escape(_fmt(stage.get('mean_wall_time_share')))}</td>"
        f"<td>{escape(_fmt(stage.get('min_wall_time_share')))}</td>"
        f"<td>{escape(_fmt(stage.get('max_wall_time_share')))}</td>"
        f"<td>{escape(_fmt(stage.get('max_wall_clock_ns')))}</td>"
        f"<td>{eligible}</td>"
        "</tr>"
    )


def _render_runtime_suite_seed_row(item: Any) -> str:
    run = _as_mapping(item)
    backends = (
        f"{run.get('flow_backend', 'unknown')} / "
        f"{run.get('routing_backend', 'unknown')} / "
        f"{run.get('agent_backend', 'unknown')}"
    )
    return (
        "<tr>"
        f"<td>{escape(_fmt(run.get('seed')))}</td>"
        f"<td>{escape(_fmt(run.get('wall_clock_ns')))}</td>"
        f"<td>{escape(backends)}</td>"
        "</tr>"
    )


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple | list):
        return tuple(value)
    return ()


def _as_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: Any) -> str:
    return "N/A" if value is None else str(value)


def _fmt_mapping(values: Mapping[str, int]) -> str:
    if not values:
        return "N/A"
    return ", ".join(f"{key}={value}" for key, value in sorted(values.items()))
