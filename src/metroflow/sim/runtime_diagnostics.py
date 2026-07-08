"""Runtime-spine diagnostic report and static HTML review rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from metroflow.sim.control import SimulationControl
from metroflow.sim.rng import PRNGKeyArray
from metroflow.sim.routing_runtime import coerce_simulation_route_cache_state
from metroflow.sim.state import SimulationState
from metroflow.sim.step import simulation_step
from metroflow.ui.snapshots import build_ui_snapshot_source

__all__ = [
    "RuntimeDiagnosticFrame",
    "RuntimeDiagnosticReport",
    "run_runtime_diagnostic_rollout",
    "render_runtime_diagnostic_html",
    "write_runtime_diagnostic_html",
]


@dataclass(slots=True)
class RuntimeDiagnosticFrame:
    """One tick of runtime-spine diagnostic state."""

    tick_index: int
    active_agent_count: int
    queue_vehicles_total: float
    outflow_vehicles_total: float
    trip_completed_total: int
    trip_failed_total: int
    active_agent_moved_this_tick: int
    active_agent_rerouted_this_tick: int
    active_agent_reroute_cooldown_this_tick: int
    route_candidate_refresh_total: int
    route_candidate_reuse_total: int
    dynamic_potential_recompute_total: int
    dynamic_potential_cache_hits_total: int
    active_agent_sink_wait_this_tick: int = 0
    sampled_link_congestion: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    candidate_paths_by_od: dict[str, tuple[tuple[int, ...], ...]] = field(default_factory=dict)
    candidate_metadata_by_od: dict[str, dict[str, Any]] = field(default_factory=dict)
    selected_candidate_slots: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self.tick_index = int(self.tick_index)
        self.active_agent_count = int(self.active_agent_count)
        self.queue_vehicles_total = float(self.queue_vehicles_total)
        self.outflow_vehicles_total = float(self.outflow_vehicles_total)
        self.trip_completed_total = int(self.trip_completed_total)
        self.trip_failed_total = int(self.trip_failed_total)
        self.active_agent_moved_this_tick = int(self.active_agent_moved_this_tick)
        self.active_agent_sink_wait_this_tick = int(self.active_agent_sink_wait_this_tick)
        self.active_agent_rerouted_this_tick = int(self.active_agent_rerouted_this_tick)
        self.active_agent_reroute_cooldown_this_tick = int(
            self.active_agent_reroute_cooldown_this_tick
        )
        self.route_candidate_refresh_total = int(self.route_candidate_refresh_total)
        self.route_candidate_reuse_total = int(self.route_candidate_reuse_total)
        self.dynamic_potential_recompute_total = int(self.dynamic_potential_recompute_total)
        self.dynamic_potential_cache_hits_total = int(self.dynamic_potential_cache_hits_total)
        self.sampled_link_congestion = tuple(dict(item) for item in self.sampled_link_congestion)
        self.candidate_paths_by_od = {
            str(key): tuple(tuple(int(link_id) for link_id in path) for path in value)
            for key, value in dict(self.candidate_paths_by_od).items()
        }
        self.candidate_metadata_by_od = {
            str(key): _normalize_candidate_metadata(value)
            for key, value in dict(self.candidate_metadata_by_od).items()
        }
        self.selected_candidate_slots = tuple(
            _normalize_selected_candidate_slot(item) for item in self.selected_candidate_slots
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize this frame into JSON-safe diagnostic data."""

        return {
            "tick_index": self.tick_index,
            "active_agent_count": self.active_agent_count,
            "queue_vehicles_total": self.queue_vehicles_total,
            "outflow_vehicles_total": self.outflow_vehicles_total,
            "trip_completed_total": self.trip_completed_total,
            "trip_failed_total": self.trip_failed_total,
            "active_agent_moved_this_tick": self.active_agent_moved_this_tick,
            "active_agent_sink_wait_this_tick": self.active_agent_sink_wait_this_tick,
            "active_agent_rerouted_this_tick": self.active_agent_rerouted_this_tick,
            "active_agent_reroute_cooldown_this_tick": self.active_agent_reroute_cooldown_this_tick,
            "route_candidate_refresh_total": self.route_candidate_refresh_total,
            "route_candidate_reuse_total": self.route_candidate_reuse_total,
            "dynamic_potential_recompute_total": self.dynamic_potential_recompute_total,
            "dynamic_potential_cache_hits_total": self.dynamic_potential_cache_hits_total,
            "sampled_link_congestion": tuple(dict(item) for item in self.sampled_link_congestion),
            "candidate_paths_by_od": {
                key: tuple(tuple(path) for path in paths)
                for key, paths in self.candidate_paths_by_od.items()
            },
            "candidate_metadata_by_od": {
                key: dict(value) for key, value in self.candidate_metadata_by_od.items()
            },
            "selected_candidate_slots": tuple(
                dict(item) for item in self.selected_candidate_slots
            ),
        }


@dataclass(slots=True)
class RuntimeDiagnosticReport:
    """Review-oriented deterministic report for one runtime-spine rollout."""

    scenario_id: str
    label: str
    frames: tuple[RuntimeDiagnosticFrame, ...]
    summary: dict[str, Any]

    def __post_init__(self) -> None:
        self.scenario_id = str(self.scenario_id)
        self.label = str(self.label)
        self.frames = tuple(self.frames)
        self.summary = _with_frame_derived_summary(dict(self.summary), self.frames)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report into JSON-safe diagnostic data."""

        return {
            "scenario_id": self.scenario_id,
            "label": self.label,
            "summary": dict(self.summary),
            "frames": tuple(frame.to_dict() for frame in self.frames),
        }

    def to_json(self) -> str:
        """Serialize the report as stable JSON for review artifacts."""

        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)


def run_runtime_diagnostic_rollout(
    initial_state: SimulationState,
    rng_key: PRNGKeyArray,
    *,
    controls: Sequence[SimulationControl],
    max_link_samples: int = 12,
    label: str = "SMOKE DIAGNOSTIC",
) -> RuntimeDiagnosticReport:
    """Run `simulation_step` repeatedly and capture review-friendly frames."""

    state = initial_state
    key = rng_key
    frames: list[RuntimeDiagnosticFrame] = []
    for control in tuple(controls):
        state, _telemetry, _snapshot, key = simulation_step(state, control, key)
        frames.append(_build_diagnostic_frame(state, max_link_samples=max_link_samples))
    return RuntimeDiagnosticReport(
        scenario_id=str(state.static.scenario_id),
        label=label,
        frames=tuple(frames),
        summary=_build_report_summary(state, frames),
    )


def render_runtime_diagnostic_html(report: RuntimeDiagnosticReport) -> str:
    """Render a static, server-free HTML review artifact with inline SVG."""

    data_json = escape(report.to_json())
    frame_rows = "\n".join(_render_frame_row(frame) for frame in report.frames)
    candidate_rows = "\n".join(_render_candidate_row(frame) for frame in report.frames)
    selected_rows = "\n".join(_render_selected_candidate_row(frame) for frame in report.frames)
    svg = _render_svg_timeline(report.frames)
    summary = report.summary
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Runtime Spine Diagnostic</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: #f6f7f9; color: #18202a; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 28px; }}
    h1 {{ font-size: 26px; margin: 0 0 6px; letter-spacing: 0; }}
    h2 {{ font-size: 16px; margin: 28px 0 10px; letter-spacing: 0; }}
    .meta {{ color: #596574; margin-bottom: 20px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }}
    .metric {{ background: #ffffff; border: 1px solid #d7dce2; border-radius: 8px; padding: 12px; }}
    .metric strong {{ display: block; font-size: 22px; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; background: #ffffff; border: 1px solid #d7dce2; }}
    th, td {{ border-bottom: 1px solid #e1e5ea; padding: 9px 10px; text-align: left; font-size: 13px; }}
    th {{ background: #edf1f5; font-weight: 650; }}
    .chart {{ background: #ffffff; border: 1px solid #d7dce2; border-radius: 8px; padding: 12px; overflow-x: auto; }}
    .note {{ color: #596574; font-size: 13px; line-height: 1.45; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }}
  </style>
</head>
<body>
<main data-runtime-diagnostic="{data_json}">
  <h1>Runtime Spine Diagnostic</h1>
  <div class="meta">{escape(report.label)} · scenario <code>{escape(report.scenario_id)}</code></div>
  <section class="grid">
    <div class="metric">final tick<strong>{int(summary.get("final_tick", 0))}</strong></div>
    <div class="metric">completed trips<strong>{int(summary.get("final_completed_trips_total", 0))}</strong></div>
    <div class="metric">rerouted total<strong>{int(summary.get("active_agent_rerouted_total", 0))}</strong></div>
    <div class="metric">sink wait total<strong>{int(summary.get("active_agent_sink_wait_total", 0))}</strong></div>
    <div class="metric">cache hits<strong>{int(summary.get("dynamic_potential_cache_hits_total", 0))}</strong></div>
  </section>
  <h2>Tick Timeline</h2>
  <div class="chart">{svg}</div>
  <h2>Frame Metrics</h2>
  <table>
    <thead><tr><th>tick</th><th>active</th><th>moved</th><th>sink wait</th><th>rerouted</th><th>cooldown</th><th>queue</th><th>outflow</th><th>completed</th><th>failed</th><th>route refresh</th><th>cache hits</th></tr></thead>
    <tbody>{frame_rows}</tbody>
  </table>
  <h2>Candidate Paths</h2>
  <table>
    <thead><tr><th>tick</th><th>OD</th><th>paths</th><th>costs</th><th>path size</th></tr></thead>
    <tbody>{candidate_rows}</tbody>
  </table>
  <h2>Selected Candidates</h2>
  <table>
    <thead><tr><th>tick</th><th>slot</th><th>candidate</th><th>cost</th><th>path size</th><th>utility</th></tr></thead>
    <tbody>{selected_rows}</tbody>
  </table>
  <p class="note">This is a SMOKE diagnostic for runtime-spine review. It is not a validation claim or performance benchmark.</p>
</main>
</body>
</html>
"""


def write_runtime_diagnostic_html(
    report: RuntimeDiagnosticReport,
    output_path: str | Path,
) -> Path:
    """Write a static runtime diagnostic HTML artifact."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_runtime_diagnostic_html(report), encoding="utf-8")
    return path


def _build_diagnostic_frame(
    state: SimulationState,
    *,
    max_link_samples: int,
) -> RuntimeDiagnosticFrame:
    metrics = state.dynamic.metrics_state if isinstance(state.dynamic.metrics_state, Mapping) else {}
    snapshot = build_ui_snapshot_source(
        state=state,
        invariant_report=state.dynamic.invariant_state,
        max_link_samples=max_link_samples,
    )
    route_state = coerce_simulation_route_cache_state(state.dynamic.route_candidate_state)
    return RuntimeDiagnosticFrame(
        tick_index=state.tick_index,
        active_agent_count=int(metrics.get("active_agents", 0)),
        queue_vehicles_total=float(metrics.get("queue_vehicles_total", 0.0)),
        outflow_vehicles_total=float(metrics.get("outflow_vehicles_total", 0.0)),
        trip_completed_total=int(metrics.get("completed_trips_total", 0)),
        trip_failed_total=int(metrics.get("failed_trips_total", 0)),
        active_agent_moved_this_tick=int(metrics.get("active_agent_moved_this_tick", 0)),
        active_agent_sink_wait_this_tick=int(
            metrics.get("active_agent_sink_wait_this_tick", 0)
        ),
        active_agent_rerouted_this_tick=int(
            metrics.get("active_agent_rerouted_this_tick", 0)
        ),
        active_agent_reroute_cooldown_this_tick=int(
            metrics.get("active_agent_reroute_cooldown_this_tick", 0)
        ),
        route_candidate_refresh_total=int(metrics.get("route_candidate_refresh_total", 0)),
        route_candidate_reuse_total=int(metrics.get("route_candidate_reuse_total", 0)),
        dynamic_potential_recompute_total=int(metrics.get("dynamic_potential_recompute_total", 0)),
        dynamic_potential_cache_hits_total=int(metrics.get("dynamic_potential_cache_hits_total", 0)),
        sampled_link_congestion=tuple(snapshot.get("sampled_link_congestion", ()) or ()),
        candidate_paths_by_od=_candidate_paths_by_od(route_state.candidate_sets),
        candidate_metadata_by_od=_candidate_metadata_by_od(route_state.candidate_sets),
        selected_candidate_slots=_selected_candidate_slots(state.dynamic.active_agent_pool),
    )


def _build_report_summary(
    state: SimulationState,
    frames: list[RuntimeDiagnosticFrame],
) -> dict[str, Any]:
    metrics = state.dynamic.metrics_state if isinstance(state.dynamic.metrics_state, Mapping) else {}
    return {
        "final_tick": int(state.tick_index),
        "frame_count": len(frames),
        "final_completed_trips_total": int(metrics.get("completed_trips_total", 0)),
        "final_failed_trips_total": int(metrics.get("failed_trips_total", 0)),
        "final_active_agents": int(metrics.get("active_agents", 0)),
        "route_candidate_refresh_total": int(metrics.get("route_candidate_refresh_total", 0)),
        "route_candidate_reuse_total": int(metrics.get("route_candidate_reuse_total", 0)),
        "dynamic_potential_recompute_total": int(metrics.get("dynamic_potential_recompute_total", 0)),
        "dynamic_potential_cache_hits_total": int(metrics.get("dynamic_potential_cache_hits_total", 0)),
        "active_agent_rerouted_this_tick": int(
            metrics.get("active_agent_rerouted_this_tick", 0)
        ),
        "active_agent_sink_wait_this_tick": int(
            metrics.get("active_agent_sink_wait_this_tick", 0)
        ),
        "active_agent_reroute_cooldown_this_tick": int(
            metrics.get("active_agent_reroute_cooldown_this_tick", 0)
        ),
        "max_queue_vehicles_total": max((frame.queue_vehicles_total for frame in frames), default=0.0),
    }


def _with_frame_derived_summary(
    summary: dict[str, Any],
    frames: tuple[RuntimeDiagnosticFrame, ...],
) -> dict[str, Any]:
    summary.setdefault(
        "active_agent_rerouted_total",
        sum(int(frame.active_agent_rerouted_this_tick) for frame in frames),
    )
    summary.setdefault(
        "active_agent_reroute_cooldown_total",
        sum(int(frame.active_agent_reroute_cooldown_this_tick) for frame in frames),
    )
    summary.setdefault(
        "active_agent_sink_wait_total",
        sum(int(frame.active_agent_sink_wait_this_tick) for frame in frames),
    )
    return summary


def _candidate_paths_by_od(candidate_sets: Mapping[Any, Any]) -> dict[str, tuple[tuple[int, ...], ...]]:
    out: dict[str, tuple[tuple[int, ...], ...]] = {}
    for od_key, candidate_set in sorted(dict(candidate_sets).items(), key=lambda item: str(item[0])):
        try:
            origin, destination = tuple(od_key)
        except ValueError:
            continue
        key = f"{int(origin)}->{int(destination)}"
        out[key] = tuple(tuple(int(link_id) for link_id in path) for path in candidate_set.candidate_paths)
    return out


def _candidate_metadata_by_od(candidate_sets: Mapping[Any, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for od_key, candidate_set in sorted(dict(candidate_sets).items(), key=lambda item: str(item[0])):
        try:
            origin, destination = tuple(od_key)
        except ValueError:
            continue
        key = f"{int(origin)}->{int(destination)}"
        metadata = getattr(candidate_set, "metadata", {})
        if not isinstance(metadata, Mapping):
            metadata = {}
        out[key] = _normalize_candidate_metadata(
            {
                "candidate_count": len(getattr(candidate_set, "candidate_paths", ()) or ()),
                "candidate_ids": tuple(getattr(candidate_set, "candidate_ids", ()) or ()),
                "candidate_path_costs": metadata.get("candidate_path_costs", ()),
                "candidate_path_size_factors": metadata.get("candidate_path_size_factors", ()),
            }
        )
    return out


def _normalize_candidate_metadata(value: Any) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, Mapping) else {}
    return {
        "candidate_count": int(raw.get("candidate_count", 0)),
        "candidate_ids": tuple(int(item) for item in tuple(raw.get("candidate_ids", ()) or ())),
        "candidate_path_costs": tuple(
            float(item) for item in tuple(raw.get("candidate_path_costs", ()) or ())
        ),
        "candidate_path_size_factors": tuple(
            float(item)
            for item in tuple(raw.get("candidate_path_size_factors", ()) or ())
        ),
    }


def _selected_candidate_slots(active_agent_pool: Any) -> tuple[dict[str, Any], ...]:
    plugin_memory = getattr(active_agent_pool, "plugin_memory", {})
    if not isinstance(plugin_memory, Mapping):
        return ()
    slots: list[dict[str, Any]] = []
    for slot_id, memory in sorted(dict(plugin_memory).items(), key=lambda item: int(item[0])):
        if not isinstance(memory, Mapping):
            continue
        if "selected_candidate_id" not in memory:
            continue
        slots.append(
            _normalize_selected_candidate_slot(
                {
                    "slot_id": slot_id,
                    "candidate_id": memory.get("selected_candidate_id", 0),
                    "candidate_index": memory.get("selected_candidate_index", 0),
                    "candidate_count": memory.get("selected_candidate_count", 0),
                    "path_cost": memory.get("selected_candidate_path_cost", 0.0),
                    "path_size_factor": memory.get(
                        "selected_candidate_path_size_factor",
                        1.0,
                    ),
                    "utility": memory.get("selected_candidate_utility", 0.0),
                }
            )
        )
    return tuple(slots)


def _normalize_selected_candidate_slot(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "slot_id": int(value.get("slot_id", 0)),
        "candidate_id": int(value.get("candidate_id", 0)),
        "candidate_index": int(value.get("candidate_index", 0)),
        "candidate_count": int(value.get("candidate_count", 0)),
        "path_cost": float(value.get("path_cost", 0.0)),
        "path_size_factor": float(value.get("path_size_factor", 1.0)),
        "utility": float(value.get("utility", 0.0)),
    }


def _render_frame_row(frame: RuntimeDiagnosticFrame) -> str:
    return (
        "<tr>"
        f"<td>tick {frame.tick_index}</td>"
        f"<td>{frame.active_agent_count}</td>"
        f"<td>{frame.active_agent_moved_this_tick}</td>"
        f"<td>{frame.active_agent_sink_wait_this_tick}</td>"
        f"<td>{frame.active_agent_rerouted_this_tick}</td>"
        f"<td>{frame.active_agent_reroute_cooldown_this_tick}</td>"
        f"<td>{frame.queue_vehicles_total:.3f}</td>"
        f"<td>{frame.outflow_vehicles_total:.3f}</td>"
        f"<td>{frame.trip_completed_total}</td>"
        f"<td>{frame.trip_failed_total}</td>"
        f"<td>{frame.route_candidate_refresh_total}</td>"
        f"<td>{frame.dynamic_potential_cache_hits_total}</td>"
        "</tr>"
    )


def _render_candidate_row(frame: RuntimeDiagnosticFrame) -> str:
    if not frame.candidate_paths_by_od:
        return f"<tr><td>tick {frame.tick_index}</td><td>none</td><td>()</td><td>()</td><td>()</td></tr>"
    rows = []
    for od_key, paths in sorted(frame.candidate_paths_by_od.items()):
        metadata = frame.candidate_metadata_by_od.get(od_key, {})
        costs = tuple(round(float(item), 3) for item in metadata.get("candidate_path_costs", ()))
        path_sizes = tuple(
            round(float(item), 3) for item in metadata.get("candidate_path_size_factors", ())
        )
        rows.append(
            "<tr>"
            f"<td>tick {frame.tick_index}</td>"
            f"<td>{escape(od_key)}</td>"
            f"<td><code>{escape(str(paths))}</code></td>"
            f"<td><code>{escape(str(costs))}</code></td>"
            f"<td><code>{escape(str(path_sizes))}</code></td>"
            "</tr>"
        )
    return "\n".join(rows)


def _render_selected_candidate_row(frame: RuntimeDiagnosticFrame) -> str:
    if not frame.selected_candidate_slots:
        return f"<tr><td>tick {frame.tick_index}</td><td>none</td><td>()</td><td>()</td><td>()</td><td>()</td></tr>"
    rows = []
    for item in frame.selected_candidate_slots:
        rows.append(
            "<tr>"
            f"<td>tick {frame.tick_index}</td>"
            f"<td>{int(item['slot_id'])}</td>"
            f"<td>{int(item['candidate_id'])} / {int(item['candidate_index'])}</td>"
            f"<td>{float(item['path_cost']):.3f}</td>"
            f"<td>{float(item['path_size_factor']):.3f}</td>"
            f"<td>{float(item['utility']):.3f}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _render_svg_timeline(frames: tuple[RuntimeDiagnosticFrame, ...]) -> str:
    width = max(520, 110 * max(1, len(frames)))
    height = 210
    left = 42
    bottom = 170
    usable_w = width - 80
    max_queue = max((frame.queue_vehicles_total for frame in frames), default=1.0)
    max_queue = max(max_queue, 1.0)
    max_completed = max((frame.trip_completed_total for frame in frames), default=1)
    max_completed = max(max_completed, 1)
    queue_points = []
    completed_points = []
    for i, frame in enumerate(frames):
        x = left + (usable_w * i / max(1, len(frames) - 1))
        queue_y = bottom - (120.0 * frame.queue_vehicles_total / max_queue)
        completed_y = bottom - (120.0 * frame.trip_completed_total / max_completed)
        queue_points.append(f"{x:.1f},{queue_y:.1f}")
        completed_points.append(f"{x:.1f},{completed_y:.1f}")
    tick_labels = "\n".join(
        f'<text x="{left + (usable_w * i / max(1, len(frames) - 1)):.1f}" y="195" text-anchor="middle" font-size="11">tick {frame.tick_index}</text>'
        for i, frame in enumerate(frames)
    )
    return f"""<svg role="img" aria-label="runtime diagnostic queue and completion timeline" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />
  <line x1="{left}" y1="38" x2="{left}" y2="{bottom}" stroke="#8a96a3" />
  <line x1="{left}" y1="{bottom}" x2="{width - 28}" y2="{bottom}" stroke="#8a96a3" />
  <polyline fill="none" stroke="#1f6f8b" stroke-width="3" points="{' '.join(queue_points)}" />
  <polyline fill="none" stroke="#b24a3b" stroke-width="3" points="{' '.join(completed_points)}" />
  <text x="{left}" y="20" font-size="12" fill="#1f6f8b">queue vehicles</text>
  <text x="170" y="20" font-size="12" fill="#b24a3b">completed trips</text>
  {tick_labels}
</svg>"""
