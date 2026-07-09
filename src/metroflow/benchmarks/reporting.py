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
    "runtime_acceleration_candidate_report",
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
    acceleration_report = _as_mapping(
        payload.get("acceleration_candidate_report")
    ) or runtime_acceleration_candidate_report(payload)
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
    acceleration_rows = "\n".join(
        _render_runtime_acceleration_row(item)
        for item in _as_sequence(acceleration_report.get("stage_candidates"))
    )
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
  <h2>Acceleration Candidate Review</h2>
  <table>
    <thead><tr><th>stage</th><th>mean share</th><th>JAX/GPU</th><th>NN surrogate</th><th>Rust CPU</th><th>next probe</th></tr></thead>
    <tbody>{acceleration_rows}</tbody>
  </table>
  <p class="note">This static HTML is a review artifact for backend migration planning. It is not a validation claim or GPU/C++ implementation authorization.</p>
</main>
</body>
</html>
"""


def runtime_acceleration_candidate_report(result: Any) -> dict[str, Any]:
    """Summarize runtime stages as Rust/GPU/NN acceleration candidates."""

    payload = runtime_benchmark_suite_to_dict(result)
    gate_report = _as_mapping(payload.get("gpu_candidate_gate_report"))
    stage_summaries = tuple(_as_mapping(item) for item in _as_sequence(gate_report.get("stage_summaries")))
    mean_share_total = sum(_as_float(stage.get("mean_wall_time_share")) for stage in stage_summaries)
    stage_candidates = tuple(_acceleration_candidate_for_stage(stage) for stage in stage_summaries)
    return {
        "report_type": "runtime_acceleration_candidate_report_v1",
        "workload_name": str(payload.get("workload_name", "unknown")),
        "eager_trip_generation": bool(payload.get("eager_trip_generation", False)),
        "stage_mean_wall_time_share_total": round(mean_share_total, 6),
        "timing_overlap_warning": mean_share_total > 1.0,
        "stage_candidates": list(stage_candidates),
        "notes": [
            (
                "Stage shares can overlap when a coarse stage contains a nested measured stage; "
                "do not sum them as exclusive wall-clock partitions."
            )
        ] if mean_share_total > 1.0 else [],
    }


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


def _acceleration_candidate_for_stage(stage: Mapping[str, Any]) -> dict[str, Any]:
    stage_name = str(stage.get("stage_name", "unknown"))
    profile = _stage_acceleration_profile(stage_name)
    return {
        "stage_name": stage_name,
        "mean_wall_time_share": _as_float(stage.get("mean_wall_time_share")),
        "max_wall_time_share": _as_float(stage.get("max_wall_time_share")),
        "max_wall_clock_ns": int(stage.get("max_wall_clock_ns", 0) or 0),
        "gpu_review_eligible": bool(stage.get("gpu_review_eligible", False)),
        "jax_gpu_fit": profile["jax_gpu_fit"],
        "nn_surrogate_fit": profile["nn_surrogate_fit"],
        "rust_cpu_fit": profile["rust_cpu_fit"],
        "custom_cuda_fit": profile["custom_cuda_fit"],
        "recommended_next_probe": profile["recommended_next_probe"],
        "rationale": profile["rationale"],
    }


def _stage_acceleration_profile(stage_name: str) -> dict[str, str]:
    profiles = {
        "route_candidate_refresh": {
            "jax_gpu_fit": "medium",
            "nn_surrogate_fit": "high",
            "rust_cpu_fit": "medium",
            "custom_cuda_fit": "low",
            "recommended_next_probe": "split OD batching, cache lookup, candidate scoring, and path construction timings",
            "rationale": "mixed graph/orchestration workload; NN route scorer or batched JAX scoring may help after baseline labels exist",
        },
        "dynamic_potential_recompute": {
            "jax_gpu_fit": "low",
            "nn_surrogate_fit": "high",
            "rust_cpu_fit": "high",
            "custom_cuda_fit": "low",
            "recommended_next_probe": "keep Dijkstra authoritative and collect labels for learned cost-to-go surrogate experiments",
            "rationale": "reverse graph search is irregular for GPU kernels, but it can supervise NN cost-to-go approximators",
        },
        "route_candidate_potential": {
            "jax_gpu_fit": "low",
            "nn_surrogate_fit": "high",
            "rust_cpu_fit": "high",
            "custom_cuda_fit": "low",
            "recommended_next_probe": "compare cache-hit time, baseline Dijkstra, Rust Dijkstra, and learned cost-to-go labels separately",
            "rationale": "potential computation is graph-search dominated but can produce supervised labels for NN cost-to-go surrogates",
        },
        "route_candidate_path_build": {
            "jax_gpu_fit": "low",
            "nn_surrogate_fit": "medium",
            "rust_cpu_fit": "high",
            "custom_cuda_fit": "low",
            "recommended_next_probe": "split greedy next-link scoring from ranked-K heap expansion before choosing Rust or NN scorer work",
            "rationale": "path construction is branchy graph control flow; NN may help scoring, while Rust is the likely execution backend",
        },
        "route_candidate_metadata": {
            "jax_gpu_fit": "medium",
            "nn_surrogate_fit": "low",
            "rust_cpu_fit": "medium",
            "custom_cuda_fit": "low",
            "recommended_next_probe": "profile path-cost and path-size batches at larger K before opening a tensor backend",
            "rationale": "metadata scoring is more array-like than graph search but must remain baseline-checkable",
        },
        "active_agent_update": {
            "jax_gpu_fit": "low",
            "nn_surrogate_fit": "medium",
            "rust_cpu_fit": "high",
            "custom_cuda_fit": "low",
            "recommended_next_probe": "separate Python pack, Rust action core, and immutable pool apply timings",
            "rationale": "deterministic slot-order budget mutation is CPU/control-flow heavy; NN/GPU belongs in policy scoring, not state apply",
        },
        "active_agent_allocation": {
            "jax_gpu_fit": "low",
            "nn_surrogate_fit": "medium",
            "rust_cpu_fit": "medium",
            "custom_cuda_fit": "low",
            "recommended_next_probe": "split candidate selection from pool slot allocation before adding policy inference",
            "rationale": "allocation includes route choice policy scoring and Python-owned immutable state writes",
        },
        "active_agent_candidate_selection": {
            "jax_gpu_fit": "medium",
            "nn_surrogate_fit": "high",
            "rust_cpu_fit": "medium",
            "custom_cuda_fit": "low",
            "recommended_next_probe": "batch route-choice scoring and collect baseline-selected labels before adding a neural scorer",
            "rationale": "candidate selection is policy/scoring shaped and is the most plausible active-agent NN surface",
        },
        "active_agent_pool_write": {
            "jax_gpu_fit": "low",
            "nn_surrogate_fit": "low",
            "rust_cpu_fit": "high",
            "custom_cuda_fit": "low",
            "recommended_next_probe": "measure immutable pool replacement and plugin-memory writes separately if this grows",
            "rationale": "pool writes are deterministic state mutation and should stay CPU/Rust-oriented",
        },
        "active_agent_pool_array_write": {
            "jax_gpu_fit": "low",
            "nn_surrogate_fit": "low",
            "rust_cpu_fit": "high",
            "custom_cuda_fit": "low",
            "recommended_next_probe": "compare Python immutable array replacement with a Rust action/apply plan before changing ownership",
            "rationale": "typed active-agent pool arrays are deterministic state mutation and fit Rust CPU better than NN/GPU",
        },
        "active_agent_plugin_memory_write": {
            "jax_gpu_fit": "low",
            "nn_surrogate_fit": "low",
            "rust_cpu_fit": "medium",
            "custom_cuda_fit": "low",
            "recommended_next_probe": "reduce dict-heavy selected-candidate metadata writes or move hot metadata into typed arrays",
            "rationale": "plugin-memory writes are Python mapping churn; optimize data layout before adding accelerator backends",
        },
        "active_agent_movement": {
            "jax_gpu_fit": "low",
            "nn_surrogate_fit": "low",
            "rust_cpu_fit": "high",
            "custom_cuda_fit": "low",
            "recommended_next_probe": "separate budget lookup, Rust action plan, and pool replacement timings",
            "rationale": "movement is deterministic slot-order state mutation and is a CPU backend target, not an NN surrogate target",
        },
        "flow_update": {
            "jax_gpu_fit": "high",
            "nn_surrogate_fit": "low",
            "rust_cpu_fit": "medium",
            "custom_cuda_fit": "high",
            "recommended_next_probe": "profile larger dense flow batches before opening custom CUDA",
            "rationale": "array-style numeric update is tensor friendly when it becomes a sustained wall-time share",
        },
        "reroute_decision": {
            "jax_gpu_fit": "medium",
            "nn_surrogate_fit": "high",
            "rust_cpu_fit": "medium",
            "custom_cuda_fit": "low",
            "recommended_next_probe": "collect simulator labels for policy/choice NN and keep deterministic fallback",
            "rationale": "decision scoring can become batched tensor inference, while route legality remains baseline-checked",
        },
    }
    return profiles.get(
        stage_name,
        {
            "jax_gpu_fit": "low",
            "nn_surrogate_fit": "low",
            "rust_cpu_fit": "medium",
            "custom_cuda_fit": "low",
            "recommended_next_probe": "add a stage-specific timing probe before selecting a backend",
            "rationale": "stage has no established acceleration profile yet",
        },
    )


def _render_runtime_acceleration_row(item: Any) -> str:
    candidate = _as_mapping(item)
    return (
        "<tr>"
        f"<td>{escape(str(candidate.get('stage_name', 'unknown')))}</td>"
        f"<td>{escape(_fmt(candidate.get('mean_wall_time_share')))}</td>"
        f"<td>{escape(str(candidate.get('jax_gpu_fit', 'low')))}</td>"
        f"<td>{escape(str(candidate.get('nn_surrogate_fit', 'low')))}</td>"
        f"<td>{escape(str(candidate.get('rust_cpu_fit', 'medium')))}</td>"
        f"<td>{escape(str(candidate.get('recommended_next_probe', 'N/A')))}</td>"
        "</tr>"
    )


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


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
