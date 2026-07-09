"""Baseline run summary aggregation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from metroflow.flow.state import LinkState
from metroflow.sim.state import SimulationState

__all__ = [
    "BaselineRunSummary",
    "RunSummaryComparison",
    "build_baseline_run_summary",
    "build_run_summary_comparison",
    "format_run_summary_comparison_markdown",
    "run_summary_comparison_deltas_core",
]


@dataclass(slots=True)
class BaselineRunSummary:
    """Compact host-side run summary for demo/reporting output."""

    scenario_id: str
    seed: int | None
    tick_index: int
    day_type: str
    time_band: str
    trip_generation_total: int
    trip_completed_total: int
    trip_failed_total: int
    active_agents: int
    queued_trip_requests: int
    pending_trip_requests: int
    capacity_violation_count: int
    negative_queue_detected: bool
    ui_packets_emitted: int
    route_candidate_refresh_total: int = 0
    route_candidate_reuse_total: int = 0
    dynamic_potential_recompute_total: int = 0
    dynamic_potential_cache_hits_total: int = 0
    flow_backend: str = "baseline"
    routing_backend: str = "baseline"
    agent_backend: str = "baseline"
    route_path_size_gamma: float = 0.0
    route_candidate_refresh_seconds_total: float = 0.0
    dynamic_potential_recompute_seconds_total: float = 0.0
    routing_compile_seconds_estimate_total: float = 0.0
    flow_update_wall_ns_total: int = 0
    active_agent_update_wall_ns: int = 0
    active_agent_update_wall_ns_total: int = 0
    reroute_decision_wall_ns: int = 0
    reroute_decision_wall_ns_total: int = 0
    hotspot_links_top_k: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    ui_packet_counts: dict[str, int] = field(default_factory=dict)
    disruption_active_event_count: int = 0
    disruption_affected_link_count: int = 0
    active_agent_sink_wait_total: int = 0
    reroute_decisions_total: int = 0
    persistence_decisions_total: int = 0
    reroute_share: float = 0.0
    persistence_share: float = 0.0
    corridor_shift_count: int = 0
    corridor_shift_share: float = 0.0
    disruption_response_metrics_available: bool = False
    map_foundation_profile: str = "sc020_sc042_map_foundation"
    map_foundation_overall_pass: bool = False
    map_foundation_failed_checks: tuple[str, ...] = field(default_factory=tuple)
    map_foundation_check_count: int = 0
    map_foundation_passed_check_count: int = 0
    map_realism_collector_link_share: float = 0.0
    map_realism_zone_count: int = 0
    map_realism_poi_count: int = 0

    def __post_init__(self) -> None:
        self.scenario_id = str(self.scenario_id)
        self.seed = None if self.seed is None else int(self.seed)
        self.tick_index = int(self.tick_index)
        self.day_type = str(self.day_type)
        self.time_band = str(self.time_band)
        self.trip_generation_total = int(self.trip_generation_total)
        self.trip_completed_total = int(self.trip_completed_total)
        self.trip_failed_total = int(self.trip_failed_total)
        self.active_agents = int(self.active_agents)
        self.queued_trip_requests = int(self.queued_trip_requests)
        self.pending_trip_requests = int(self.pending_trip_requests)
        self.capacity_violation_count = int(self.capacity_violation_count)
        self.negative_queue_detected = bool(self.negative_queue_detected)
        self.ui_packets_emitted = int(self.ui_packets_emitted)
        self.route_candidate_refresh_total = int(self.route_candidate_refresh_total)
        self.route_candidate_reuse_total = int(self.route_candidate_reuse_total)
        self.dynamic_potential_recompute_total = int(self.dynamic_potential_recompute_total)
        self.dynamic_potential_cache_hits_total = int(self.dynamic_potential_cache_hits_total)
        self.flow_backend = str(self.flow_backend)
        self.routing_backend = str(self.routing_backend)
        self.agent_backend = str(self.agent_backend)
        self.route_path_size_gamma = float(self.route_path_size_gamma)
        self.route_candidate_refresh_seconds_total = float(self.route_candidate_refresh_seconds_total)
        self.dynamic_potential_recompute_seconds_total = float(
            self.dynamic_potential_recompute_seconds_total
        )
        self.routing_compile_seconds_estimate_total = float(
            self.routing_compile_seconds_estimate_total
        )
        self.flow_update_wall_ns_total = int(self.flow_update_wall_ns_total)
        self.active_agent_update_wall_ns = int(self.active_agent_update_wall_ns)
        self.active_agent_update_wall_ns_total = int(
            self.active_agent_update_wall_ns_total
        )
        self.reroute_decision_wall_ns = int(self.reroute_decision_wall_ns)
        self.reroute_decision_wall_ns_total = int(self.reroute_decision_wall_ns_total)
        self.hotspot_links_top_k = tuple(dict(item) for item in self.hotspot_links_top_k)
        self.ui_packet_counts = {str(k): int(v) for k, v in dict(self.ui_packet_counts).items()}
        self.disruption_active_event_count = int(self.disruption_active_event_count)
        self.disruption_affected_link_count = int(self.disruption_affected_link_count)
        self.active_agent_sink_wait_total = int(self.active_agent_sink_wait_total)
        self.reroute_decisions_total = int(self.reroute_decisions_total)
        self.persistence_decisions_total = int(self.persistence_decisions_total)
        self.reroute_share = float(self.reroute_share)
        self.persistence_share = float(self.persistence_share)
        self.corridor_shift_count = int(self.corridor_shift_count)
        self.corridor_shift_share = float(self.corridor_shift_share)
        self.disruption_response_metrics_available = bool(
            self.disruption_response_metrics_available
        )
        self.map_foundation_profile = str(self.map_foundation_profile)
        self.map_foundation_overall_pass = bool(self.map_foundation_overall_pass)
        self.map_foundation_failed_checks = tuple(
            str(item) for item in self.map_foundation_failed_checks
        )
        self.map_foundation_check_count = int(self.map_foundation_check_count)
        self.map_foundation_passed_check_count = int(self.map_foundation_passed_check_count)
        self.map_realism_collector_link_share = float(self.map_realism_collector_link_share)
        self.map_realism_zone_count = int(self.map_realism_zone_count)
        self.map_realism_poi_count = int(self.map_realism_poi_count)

    @property
    def completed_trips_total(self) -> int:
        return int(self.trip_completed_total)

    @property
    def failed_trips_total(self) -> int:
        return int(self.trip_failed_total)

    @property
    def trip_completion_rate(self) -> float:
        generated = max(0, int(self.trip_generation_total))
        return float(self.trip_completed_total / generated) if generated > 0 else 0.0

    @property
    def trip_failure_rate(self) -> float:
        generated = max(0, int(self.trip_generation_total))
        return float(self.trip_failed_total / generated) if generated > 0 else 0.0


@dataclass(slots=True)
class RunSummaryComparison:
    """Baseline vs adaptive experiment comparison payload."""

    scenario_id: str
    seed: int | None
    baseline_summary: BaselineRunSummary
    adaptive_summary: BaselineRunSummary
    trip_completed_total_delta: int
    trip_failed_total_delta: int
    trip_completion_rate_delta: float
    trip_failure_rate_delta: float
    active_agents_delta: int
    queued_trip_requests_delta: int
    pending_trip_requests_delta: int
    capacity_violation_count_delta: int
    reroute_share_delta: float
    persistence_share_delta: float
    corridor_shift_share_delta: float

    def __post_init__(self) -> None:
        self.scenario_id = str(self.scenario_id)
        self.seed = None if self.seed is None else int(self.seed)
        self.trip_completed_total_delta = int(self.trip_completed_total_delta)
        self.trip_failed_total_delta = int(self.trip_failed_total_delta)
        self.trip_completion_rate_delta = float(self.trip_completion_rate_delta)
        self.trip_failure_rate_delta = float(self.trip_failure_rate_delta)
        self.active_agents_delta = int(self.active_agents_delta)
        self.queued_trip_requests_delta = int(self.queued_trip_requests_delta)
        self.pending_trip_requests_delta = int(self.pending_trip_requests_delta)
        self.capacity_violation_count_delta = int(self.capacity_violation_count_delta)
        self.reroute_share_delta = float(self.reroute_share_delta)
        self.persistence_share_delta = float(self.persistence_share_delta)
        self.corridor_shift_share_delta = float(self.corridor_shift_share_delta)


def build_baseline_run_summary(
    state: SimulationState,
    *,
    ui_packet_counts: Mapping[str, int] | None = None,
    hotspot_top_k: int = 5,
) -> BaselineRunSummary:
    """Aggregate a baseline run summary from the current simulation state."""

    normalized_ui_packet_counts = (
        {} if ui_packet_counts is None else {str(k): int(v) for k, v in dict(ui_packet_counts).items()}
    )
    metrics_state = state.dynamic.metrics_state if isinstance(state.dynamic.metrics_state, Mapping) else {}
    dynamic_metadata = state.dynamic.metadata if isinstance(state.dynamic.metadata, Mapping) else {}
    generated_total = int(metrics_state.get("generated_trip_total", 0))
    completed_total = int(metrics_state.get("completed_trips_total", 0))
    failed_total = int(metrics_state.get("failed_trips_total", 0))
    queued = int(metrics_state.get("queued_trip_requests", 0))
    pending = int(metrics_state.get("pending_trip_requests", queued))
    active_agents = int(metrics_state.get("active_agents", _alive_count_fallback(state)))
    ui_packets_emitted = (
        int(sum(normalized_ui_packet_counts.values()))
        if normalized_ui_packet_counts
        else int(metrics_state.get("ui_packets_emitted", 0))
    )
    reroute_total = int(
        metrics_state.get("us2_reroute_decisions_total", dynamic_metadata.get("us2_reroute_decisions_total", 0))
    )
    persistence_total = int(
        metrics_state.get(
            "us2_persistence_decisions_total",
            dynamic_metadata.get("us2_persistence_decisions_total", 0),
        )
    )
    corridor_shift_count = int(
        metrics_state.get(
            "us2_corridor_shift_count_total",
            dynamic_metadata.get("us2_corridor_shift_count_total", 0),
        )
    )
    behavior_total = max(0, reroute_total + persistence_total)
    reroute_share = float(reroute_total / behavior_total) if behavior_total > 0 else 0.0
    persistence_share = float(persistence_total / behavior_total) if behavior_total > 0 else 0.0
    corridor_shift_share = float(corridor_shift_count / reroute_total) if reroute_total > 0 else 0.0
    map_gate = _map_foundation_gate_summary(state)
    return BaselineRunSummary(
        scenario_id=str(getattr(state.static, "scenario_id", "") or "unknown"),
        seed=_extract_seed(state),
        tick_index=int(state.tick_index),
        day_type=str(state.day_type.value),
        time_band=str(state.time_band.value),
        trip_generation_total=generated_total,
        trip_completed_total=completed_total,
        trip_failed_total=failed_total,
        active_agents=active_agents,
        queued_trip_requests=queued,
        pending_trip_requests=pending,
        capacity_violation_count=int(
            metrics_state.get("capacity_violation_count", _capacity_violation_count_fallback(state))
        ),
        negative_queue_detected=bool(
            metrics_state.get("negative_queue_detected", _negative_queue_detected_fallback(state))
        ),
        ui_packets_emitted=ui_packets_emitted,
        route_candidate_refresh_total=int(metrics_state.get("route_candidate_refresh_total", 0)),
        route_candidate_reuse_total=int(metrics_state.get("route_candidate_reuse_total", 0)),
        dynamic_potential_recompute_total=int(metrics_state.get("dynamic_potential_recompute_total", 0)),
        dynamic_potential_cache_hits_total=int(metrics_state.get("dynamic_potential_cache_hits_total", 0)),
        flow_backend=str(metrics_state.get("flow_backend", state.config.flow_backend)),
        routing_backend=str(metrics_state.get("routing_backend", state.config.routing_backend)),
        agent_backend=str(metrics_state.get("agent_backend", state.config.agent_backend)),
        route_path_size_gamma=float(state.config.route_path_size_gamma),
        route_candidate_refresh_seconds_total=float(metrics_state.get("route_candidate_refresh_seconds_total", 0.0)),
        dynamic_potential_recompute_seconds_total=float(
            metrics_state.get("dynamic_potential_recompute_seconds_total", 0.0)
        ),
        routing_compile_seconds_estimate_total=float(metrics_state.get("routing_compile_seconds_estimate_total", 0.0)),
        flow_update_wall_ns_total=int(metrics_state.get("flow_update_wall_ns_total", 0)),
        active_agent_update_wall_ns=int(metrics_state.get("active_agent_update_wall_ns", 0)),
        active_agent_update_wall_ns_total=int(
            metrics_state.get("active_agent_update_wall_ns_total", 0)
        ),
        reroute_decision_wall_ns=int(metrics_state.get("reroute_decision_wall_ns", 0)),
        reroute_decision_wall_ns_total=int(
            metrics_state.get("reroute_decision_wall_ns_total", 0)
        ),
        hotspot_links_top_k=_hotspot_links_top_k(state, k=hotspot_top_k),
        ui_packet_counts=normalized_ui_packet_counts,
        disruption_active_event_count=_active_event_count_fallback(state),
        disruption_affected_link_count=_affected_link_count_fallback(state),
        active_agent_sink_wait_total=int(metrics_state.get("active_agent_sink_wait_total", 0)),
        reroute_decisions_total=reroute_total,
        persistence_decisions_total=persistence_total,
        reroute_share=reroute_share,
        persistence_share=persistence_share,
        corridor_shift_count=corridor_shift_count,
        corridor_shift_share=corridor_shift_share,
        disruption_response_metrics_available=behavior_total > 0 or corridor_shift_count > 0,
        map_foundation_profile=map_gate["profile"],
        map_foundation_overall_pass=map_gate["overall_pass"],
        map_foundation_failed_checks=map_gate["failed_checks"],
        map_foundation_check_count=map_gate["check_count"],
        map_foundation_passed_check_count=map_gate["passed_check_count"],
        map_realism_collector_link_share=map_gate["collector_link_share"],
        map_realism_zone_count=map_gate["zone_count"],
        map_realism_poi_count=map_gate["poi_count"],
    )


def build_run_summary_comparison(
    baseline_summary: BaselineRunSummary | Mapping[str, Any],
    adaptive_summary: BaselineRunSummary | Mapping[str, Any],
) -> RunSummaryComparison:
    """Build a host-side baseline-vs-adaptive comparison payload."""

    baseline = _coerce_baseline_run_summary(baseline_summary)
    adaptive = _coerce_baseline_run_summary(adaptive_summary)
    _validate_comparable_run_summaries(baseline, adaptive)
    deltas = run_summary_comparison_deltas_core(
        baseline_trip_generation_total=baseline.trip_generation_total,
        adaptive_trip_generation_total=adaptive.trip_generation_total,
        baseline_trip_completed_total=baseline.trip_completed_total,
        adaptive_trip_completed_total=adaptive.trip_completed_total,
        baseline_trip_failed_total=baseline.trip_failed_total,
        adaptive_trip_failed_total=adaptive.trip_failed_total,
        baseline_active_agents=baseline.active_agents,
        adaptive_active_agents=adaptive.active_agents,
        baseline_queued_trip_requests=baseline.queued_trip_requests,
        adaptive_queued_trip_requests=adaptive.queued_trip_requests,
        baseline_pending_trip_requests=baseline.pending_trip_requests,
        adaptive_pending_trip_requests=adaptive.pending_trip_requests,
        baseline_capacity_violation_count=baseline.capacity_violation_count,
        adaptive_capacity_violation_count=adaptive.capacity_violation_count,
        baseline_reroute_share=baseline.reroute_share,
        adaptive_reroute_share=adaptive.reroute_share,
        baseline_persistence_share=baseline.persistence_share,
        adaptive_persistence_share=adaptive.persistence_share,
        baseline_corridor_shift_share=baseline.corridor_shift_share,
        adaptive_corridor_shift_share=adaptive.corridor_shift_share,
    )
    return RunSummaryComparison(
        scenario_id=baseline.scenario_id,
        seed=baseline.seed,
        baseline_summary=baseline,
        adaptive_summary=adaptive,
        trip_completed_total_delta=int(deltas[0]),
        trip_failed_total_delta=int(deltas[1]),
        trip_completion_rate_delta=float(deltas[2]),
        trip_failure_rate_delta=float(deltas[3]),
        active_agents_delta=int(deltas[4]),
        queued_trip_requests_delta=int(deltas[5]),
        pending_trip_requests_delta=int(deltas[6]),
        capacity_violation_count_delta=int(deltas[7]),
        reroute_share_delta=float(deltas[8]),
        persistence_share_delta=float(deltas[9]),
        corridor_shift_share_delta=float(deltas[10]),
    )


def format_run_summary_comparison_markdown(comparison: RunSummaryComparison) -> str:
    """Render a short markdown comparison for baseline vs adaptive experiments."""

    return "\n".join(
        [
            f"- Scenario ID: {comparison.scenario_id}",
            f"- Seed: {_fmt_value(comparison.seed)}",
            f"- Completed trips delta (adaptive - baseline): {comparison.trip_completed_total_delta:+d}",
            f"- Failed trips delta (adaptive - baseline): {comparison.trip_failed_total_delta:+d}",
            f"- Completion rate delta (adaptive - baseline): {comparison.trip_completion_rate_delta:+.6f}",
            f"- Failure rate delta (adaptive - baseline): {comparison.trip_failure_rate_delta:+.6f}",
            f"- Active agents delta (adaptive - baseline): {comparison.active_agents_delta:+d}",
            f"- Queued trips delta (adaptive - baseline): {comparison.queued_trip_requests_delta:+d}",
            f"- Pending trips delta (adaptive - baseline): {comparison.pending_trip_requests_delta:+d}",
            f"- Capacity violation delta (adaptive - baseline): {comparison.capacity_violation_count_delta:+d}",
            f"- Reroute share delta (adaptive - baseline): {comparison.reroute_share_delta:+.6f}",
            f"- Persistence share delta (adaptive - baseline): {comparison.persistence_share_delta:+.6f}",
            f"- Corridor shift share delta (adaptive - baseline): {comparison.corridor_shift_share_delta:+.6f}",
        ]
    )


def run_summary_comparison_deltas_core(
    *,
    baseline_trip_generation_total: Any,
    adaptive_trip_generation_total: Any,
    baseline_trip_completed_total: Any,
    adaptive_trip_completed_total: Any,
    baseline_trip_failed_total: Any,
    adaptive_trip_failed_total: Any,
    baseline_active_agents: Any,
    adaptive_active_agents: Any,
    baseline_queued_trip_requests: Any,
    adaptive_queued_trip_requests: Any,
    baseline_pending_trip_requests: Any,
    adaptive_pending_trip_requests: Any,
    baseline_capacity_violation_count: Any,
    adaptive_capacity_violation_count: Any,
    baseline_reroute_share: Any,
    adaptive_reroute_share: Any,
    baseline_persistence_share: Any,
    adaptive_persistence_share: Any,
    baseline_corridor_shift_share: Any,
    adaptive_corridor_shift_share: Any,
) -> tuple[Any, ...]:
    """Return comparison deltas while keeping scalar-array inputs accepted."""

    baseline_generated = max(0.0, float(baseline_trip_generation_total))
    adaptive_generated = max(0.0, float(adaptive_trip_generation_total))
    baseline_completed = float(baseline_trip_completed_total)
    adaptive_completed = float(adaptive_trip_completed_total)
    baseline_failed = float(baseline_trip_failed_total)
    adaptive_failed = float(adaptive_trip_failed_total)
    baseline_completion_rate = baseline_completed / baseline_generated if baseline_generated else 0.0
    adaptive_completion_rate = adaptive_completed / adaptive_generated if adaptive_generated else 0.0
    baseline_failure_rate = baseline_failed / baseline_generated if baseline_generated else 0.0
    adaptive_failure_rate = adaptive_failed / adaptive_generated if adaptive_generated else 0.0
    return (
        adaptive_trip_completed_total - baseline_trip_completed_total,
        adaptive_trip_failed_total - baseline_trip_failed_total,
        adaptive_completion_rate - baseline_completion_rate,
        adaptive_failure_rate - baseline_failure_rate,
        adaptive_active_agents - baseline_active_agents,
        adaptive_queued_trip_requests - baseline_queued_trip_requests,
        adaptive_pending_trip_requests - baseline_pending_trip_requests,
        adaptive_capacity_violation_count - baseline_capacity_violation_count,
        adaptive_reroute_share - baseline_reroute_share,
        adaptive_persistence_share - baseline_persistence_share,
        adaptive_corridor_shift_share - baseline_corridor_shift_share,
    )


def _extract_seed(state: SimulationState) -> int | None:
    for container in (state.metadata, state.static.metadata, state.dynamic.metadata):
        if isinstance(container, Mapping) and "scenario_seed" in container:
            try:
                return int(container["scenario_seed"])
            except Exception:
                continue
    return None


def _coerce_baseline_run_summary(value: BaselineRunSummary | Mapping[str, Any]) -> BaselineRunSummary:
    if isinstance(value, BaselineRunSummary):
        return value
    return BaselineRunSummary(**dict(value))


def _validate_comparable_run_summaries(
    baseline: BaselineRunSummary,
    adaptive: BaselineRunSummary,
) -> None:
    mismatches: list[str] = []
    if baseline.scenario_id != adaptive.scenario_id:
        mismatches.append("scenario_id")
    if baseline.seed != adaptive.seed:
        mismatches.append("seed")
    if baseline.day_type != adaptive.day_type:
        mismatches.append("day_type")
    if baseline.time_band != adaptive.time_band:
        mismatches.append("time_band")
    if baseline.trip_generation_total != adaptive.trip_generation_total:
        mismatches.append("trip_generation_total")
    if mismatches:
        raise ValueError(
            "baseline/adaptive run summaries are not comparable: " + ", ".join(mismatches)
        )


def _alive_count_fallback(state: SimulationState) -> int:
    pool = state.dynamic.active_agent_pool
    return int(getattr(pool, "alive_count", 0) or 0)


def _capacity_violation_count_fallback(state: SimulationState) -> int:
    link_state = state.dynamic.flow_link_state
    if isinstance(link_state, LinkState):
        return int(link_state.capacity_violation_count)
    return 0


def _negative_queue_detected_fallback(state: SimulationState) -> bool:
    invariant_state = state.dynamic.invariant_state
    counters = getattr(invariant_state, "counters", None)
    return int(getattr(counters, "negative_queue_violations", 0) or 0) > 0


def _active_event_count_fallback(state: SimulationState) -> int:
    event_state = state.dynamic.event_state
    active_events = event_state.get("active_events") if isinstance(event_state, Mapping) else getattr(event_state, "active_events", None)
    return _safe_len(active_events)


def _affected_link_count_fallback(state: SimulationState) -> int:
    metadata = state.dynamic.metadata if isinstance(state.dynamic.metadata, Mapping) else {}
    return _safe_len(metadata.get("us2_active_event_affected_link_ids", ()))


def _map_foundation_gate_summary(state: SimulationState) -> dict[str, Any]:
    static_metadata = state.static.metadata if isinstance(state.static.metadata, Mapping) else {}
    raw_gate = static_metadata.get("map_foundation_gate", {})
    if isinstance(raw_gate, Mapping):
        failed_checks = tuple(str(item) for item in raw_gate.get("failed_checks", ()) or ())
        return {
            "profile": str(raw_gate.get("profile", "sc020_sc042_map_foundation")),
            "overall_pass": bool(raw_gate.get("overall_pass", False)),
            "failed_checks": failed_checks,
            "check_count": int(raw_gate.get("check_count", len(failed_checks))),
            "passed_check_count": int(raw_gate.get("passed_check_count", 0)),
            "collector_link_share": _collector_link_share(state),
            "zone_count": _safe_len(state.static.zones),
            "poi_count": _safe_len(state.static.pois),
        }
    zones = _safe_len(state.static.zones)
    pois = _safe_len(state.static.pois)
    return {
        "profile": "sc020_sc042_map_foundation",
        "overall_pass": zones >= 4 and pois >= 8,
        "failed_checks": () if zones >= 4 and pois >= 8 else ("SC-024", "SC-025"),
        "check_count": 2,
        "passed_check_count": int(zones >= 4) + int(pois >= 8),
        "collector_link_share": _collector_link_share(state),
        "zone_count": zones,
        "poi_count": pois,
    }


def _collector_link_share(state: SimulationState) -> float:
    routing_static = state.static.routing_static if isinstance(state.static.routing_static, Mapping) else {}
    road_csr = routing_static.get("road_csr")
    links = tuple(getattr(road_csr, "links", ()) or ())
    if not links:
        return 0.0
    collector_count = sum(
        1 for link in links if str(getattr(link.road_class, "value", link.road_class)) == "collector"
    )
    return float(collector_count / len(links))


def _hotspot_links_top_k(state: SimulationState, *, k: int) -> tuple[dict[str, Any], ...]:
    k = max(0, int(k))
    if k == 0:
        return ()
    link_state = state.dynamic.flow_link_state
    routing_static = state.static.routing_static if isinstance(state.static.routing_static, Mapping) else {}
    road_csr = routing_static.get("road_csr")
    if not isinstance(link_state, LinkState) or road_csr is None:
        return ()
    links = tuple(getattr(road_csr, "links", ()) or ())
    if len(links) != int(link_state.link_count) or not links:
        return ()
    queue = np.asarray(link_state.queue_vehicles, dtype=np.float32)
    cap = np.asarray(link_state.effective_capacity_vehicles, dtype=np.float32)
    congestion = queue / np.maximum(cap, 1e-6)
    order = np.argsort(-congestion, kind="stable")[: min(k, len(links))]
    cost = np.asarray(link_state.travel_time_cost, dtype=np.float32)
    free_cost_src = link_state.metadata.get("free_flow_travel_time_cost", link_state.travel_time_cost)
    free_cost = np.asarray(free_cost_src, dtype=np.float32)
    out: list[dict[str, Any]] = []
    for idx in order.tolist():
        link = links[int(idx)]
        slowdown = cost[int(idx)] / max(float(free_cost[int(idx)]), 1e-6)
        out.append(
            {
                "link_id": int(link.link_id),
                "road_class": str(getattr(link.road_class, "value", link.road_class)),
                "queue_vehicles": float(queue[int(idx)]),
                "congestion_ratio": float(congestion[int(idx)]),
                "travel_time_ratio": float(slowdown),
            }
        )
    return tuple(out)


def _safe_len(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(len(value))
    except Exception:
        return sum(1 for _ in value)


def _fmt_value(value: Any) -> str:
    return "N/A" if value is None else str(value)
