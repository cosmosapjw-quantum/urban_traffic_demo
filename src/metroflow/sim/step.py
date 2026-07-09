"""Baseline simulation step contract for the absorbed runtime foundation."""

from __future__ import annotations

from time import perf_counter_ns
from typing import Any, Mapping

import numpy as np

from metroflow.demand.trips import TripRequestStatus, activate_trip_requests
from metroflow.flow.engine import update_link_node_flow
from metroflow.flow.event_effects import apply_active_event_effects_to_link_state
from metroflow.flow.events import (
    TrafficEvent,
    TrafficEventSchedulerState,
    advance_traffic_event_scheduler,
)
from metroflow.flow.state import LinkState, NodeState
from metroflow.sim.config import SimulationConfig
from metroflow.sim.control import SimulationControl, SimulationTelemetry
from metroflow.sim.init import build_initial_simulation_state
from metroflow.sim.invariants import InvariantReport
from metroflow.sim.invariants import validate_invariants as _validate_invariants_core
from metroflow.sim.rng import PRNGKeyArray
from metroflow.sim.routing_runtime import (
    advance_runtime_active_agents,
    refresh_runtime_route_candidates,
)
from metroflow.sim.state import SimulationState
from metroflow.ui.snapshots import build_ui_snapshot_source

__all__ = [
    "UISnapshotSource",
    "init_simulation",
    "simulation_step",
    "run_rollout",
    "validate_invariants",
]

UISnapshotSource = dict[str, Any]


def init_simulation(
    config: SimulationConfig,
    scenario_seed: int,
) -> tuple[SimulationState, PRNGKeyArray]:
    """Initialize the baseline simulation state and root PRNG key."""

    bundle = build_initial_simulation_state(
        config=_coerce_config(config),
        scenario_seed=int(scenario_seed),
        eager_trip_generation=bool(getattr(config, "learning_enabled", False)),
    )
    return bundle.state, bundle.rng_key


def simulation_step(
    state: SimulationState,
    control: SimulationControl,
    rng_key: PRNGKeyArray,
) -> tuple[SimulationState, SimulationTelemetry, UISnapshotSource | None, PRNGKeyArray]:
    """Advance one deterministic baseline simulation tick."""

    cur_state = _coerce_state(state)
    cur_control = _coerce_control(control)
    next_rng_key = _advance_rng_key_host(rng_key)

    next_state = _apply_control_to_state(cur_state, cur_control)
    next_state = _advance_event_state(next_state, cur_control)
    tick_counters = _zero_tick_counters()
    if not cur_control.pause:
        next_state = _apply_event_effects_to_flow_state(next_state)
        next_state, activation_counters = _activate_due_trip_requests(next_state)
        tick_counters.update(activation_counters)
        next_state, flow_counters = _advance_flow_state(next_state)
        tick_counters.update(flow_counters)
        next_state, routing_counters = _advance_runtime_routing_state(next_state)
        tick_counters.update(routing_counters)
    invariant_report = _validate_invariants_core(next_state)

    ui_snapshot_source = _build_optional_ui_snapshot_source(
        state=next_state,
        control=cur_control,
        invariant_report=invariant_report,
    )
    ui_snapshot_emitted = ui_snapshot_source is not None
    metrics_state = _update_metrics_state(
        state=next_state,
        prior_metrics_state=next_state.dynamic.metrics_state,
        invariant_report=invariant_report,
        ui_snapshot_emitted=ui_snapshot_emitted,
        tick_counters=tick_counters,
    )
    next_state = next_state.with_dynamic_updates(
        metrics_state=metrics_state,
        invariant_state=invariant_report,
        last_ui_snapshot_source=ui_snapshot_source,
    )
    telemetry = _build_step_telemetry(
        state=next_state,
        invariant_report=invariant_report,
        ui_snapshot_emitted=ui_snapshot_emitted,
        tick_counters=tick_counters,
    )
    return next_state, telemetry, ui_snapshot_source, next_rng_key


def run_rollout(
    initial_state: SimulationState,
    controls: list[SimulationControl],
    rng_key: PRNGKeyArray,
) -> tuple[SimulationState, list[SimulationTelemetry], PRNGKeyArray]:
    """Run repeated baseline simulation steps."""

    state = _coerce_state(initial_state)
    key = rng_key
    telemetry_log: list[SimulationTelemetry] = []
    for control in controls:
        state, telemetry, _ui_snapshot, key = simulation_step(state, control, key)
        telemetry_log.append(telemetry)
    return state, telemetry_log, key


def validate_invariants(state: SimulationState) -> InvariantReport:
    """Contract wrapper around the invariant validation hook."""

    return _validate_invariants_core(_coerce_state(state))


def _advance_rng_key_host(rng_key: PRNGKeyArray) -> np.ndarray:
    key_np = np.asarray(rng_key, dtype=np.uint32)
    if key_np.shape != (2,):
        raise ValueError("rng_key must have shape (2,)")
    out = key_np.copy()
    out[1] = np.uint32((int(out[1]) + 1) & 0xFFFFFFFF)
    return out


def _coerce_config(config: SimulationConfig | Mapping[str, Any]) -> SimulationConfig:
    if isinstance(config, SimulationConfig):
        return config
    return SimulationConfig(**dict(config))


def _coerce_state(state: SimulationState | Mapping[str, Any]) -> SimulationState:
    if isinstance(state, SimulationState):
        return state
    return SimulationState(**dict(state))


def _coerce_control(control: SimulationControl | Mapping[str, Any]) -> SimulationControl:
    if isinstance(control, SimulationControl):
        return control
    return SimulationControl(**dict(control))


def _apply_control_to_state(state: SimulationState, control: SimulationControl) -> SimulationState:
    next_state = state.with_clock(
        day_type=control.set_day_type if control.set_day_type is not None else None,
        time_band=control.set_time_band if control.set_time_band is not None else None,
    )
    if not control.pause:
        next_state = next_state.with_clock(tick_index=next_state.tick_index + 1)
    return next_state


def _advance_event_state(state: SimulationState, control: SimulationControl) -> SimulationState:
    if control.inject_event is None and not control.clear_event_ids and state.dynamic.event_state is None:
        return state
    scheduler = _coerce_event_scheduler_state(state.dynamic.event_state)
    injected = _coerce_injected_events(control.inject_event)
    if injected:
        scheduler = TrafficEventSchedulerState(
            scheduled_events=scheduler.scheduled_events + injected,
            active_events=scheduler.active_events,
            cleared_events=scheduler.cleared_events,
        )
    scheduler = advance_traffic_event_scheduler(
        scheduler,
        current_tick=state.tick_index,
        clear_event_ids=control.clear_event_ids,
    )
    return state.with_dynamic_updates(event_state=scheduler)


def _coerce_event_scheduler_state(raw: Any) -> TrafficEventSchedulerState:
    if raw is None:
        return TrafficEventSchedulerState()
    if isinstance(raw, TrafficEventSchedulerState):
        return raw
    if isinstance(raw, Mapping):
        return TrafficEventSchedulerState(**dict(raw))
    return raw


def _coerce_injected_events(raw: Any) -> tuple[TrafficEvent, ...]:
    if raw is None:
        return ()
    if isinstance(raw, TrafficEvent):
        return (raw,)
    if isinstance(raw, Mapping):
        return (TrafficEvent(**dict(raw)),)
    return tuple(event if isinstance(event, TrafficEvent) else TrafficEvent(**dict(event)) for event in raw)


def _activate_due_trip_requests(state: SimulationState) -> tuple[SimulationState, dict[str, int]]:
    demand_state = state.dynamic.demand_state
    if not isinstance(demand_state, Mapping):
        return state, _zero_tick_counters()
    trip_requests = tuple(demand_state.get("trip_requests", ()))
    if not trip_requests:
        return state, _zero_tick_counters()

    before_activated = sum(1 for trip in trip_requests if trip.status is TripRequestStatus.ACTIVATED)
    next_trip_requests = activate_trip_requests(trip_requests, current_tick=state.tick_index)
    after_activated = sum(1 for trip in next_trip_requests if trip.status is TripRequestStatus.ACTIVATED)
    queued = sum(1 for trip in next_trip_requests if trip.status is TripRequestStatus.QUEUED)
    pending = queued + after_activated
    next_demand_state = dict(demand_state)
    next_demand_state.update(
        {
            "trip_requests": next_trip_requests,
            "queued_trip_requests": queued,
            "pending_trip_requests": pending,
            "activated_trip_requests": after_activated,
        }
    )
    counters = _zero_tick_counters()
    counters["trip_activated_this_tick"] = max(0, after_activated - before_activated)
    return state.with_dynamic_updates(demand_state=next_demand_state), counters


def _zero_tick_counters() -> dict[str, int]:
    return {
        "trip_generated_this_tick": 0,
        "trip_completed_this_tick": 0,
        "trip_failed_this_tick": 0,
        "trip_activated_this_tick": 0,
        "trip_allocated_this_tick": 0,
        "active_agent_moved_this_tick": 0,
        "active_agent_sink_wait_this_tick": 0,
        "route_candidate_refresh_this_tick": 0,
        "route_candidate_reuse_this_tick": 0,
        "dynamic_potential_recompute_this_tick": 0,
        "dynamic_potential_cache_hits_this_tick": 0,
        "flow_update_wall_ns": 0,
        "active_agent_update_wall_ns": 0,
        "reroute_decision_wall_ns": 0,
        "active_agent_rerouted_this_tick": 0,
        "active_agent_reroute_cooldown_this_tick": 0,
    }


def _apply_event_effects_to_flow_state(state: SimulationState) -> SimulationState:
    road_csr = _road_csr_from_state(state)
    link_state = state.dynamic.flow_link_state
    if road_csr is None or not isinstance(link_state, LinkState):
        return state
    active_events = _active_events_from_state(state)
    has_existing_incident = bool(
        np.any(np.asarray(link_state.incident_capacity_multiplier, dtype=np.float32) < 1.0)
    )
    if not active_events and not has_existing_incident:
        return state
    result = apply_active_event_effects_to_link_state(
        road_csr=road_csr,
        link_state=link_state,
        active_events=active_events,
        validate=False,
    )
    next_link_state = _with_link_metadata_increment(
        result.link_state,
        key="runtime_incident_generation",
    )
    next_metadata = dict(state.dynamic.metadata)
    next_metadata["us2_active_event_applied_event_ids"] = result.applied_event_ids
    next_metadata["us2_active_event_ignored_event_ids"] = result.ignored_event_ids
    next_metadata["us2_active_event_affected_link_ids"] = result.affected_link_ids
    return state.with_dynamic_updates(
        flow_link_state=next_link_state,
        metadata=next_metadata,
    )


def _advance_flow_state(state: SimulationState) -> tuple[SimulationState, dict[str, int]]:
    counters = {"flow_update_wall_ns": 0}
    link_state = state.dynamic.flow_link_state
    node_state = state.dynamic.flow_node_state
    if not isinstance(link_state, LinkState) or not isinstance(node_state, NodeState):
        return state, counters
    start_ns = perf_counter_ns()
    result = update_link_node_flow(
        link_state,
        node_state,
        validate=False,
        flow_backend=state.config.flow_backend,
    )
    counters["flow_update_wall_ns"] = max(0, perf_counter_ns() - start_ns)
    next_link_state = _with_link_metadata_increment(
        result.link_state,
        key="runtime_flow_generation",
    )
    return (
        state.with_dynamic_updates(
            flow_link_state=next_link_state,
            flow_node_state=result.node_state,
        ),
        counters,
    )


def _advance_runtime_routing_state(
    state: SimulationState,
) -> tuple[SimulationState, dict[str, int]]:
    route_state, route_counters = refresh_runtime_route_candidates(state)
    state = state.with_dynamic_updates(route_candidate_state=route_state)
    start_ns = perf_counter_ns()
    pool, agent_counters, demand_state, link_state = advance_runtime_active_agents(state)
    agent_counters = dict(agent_counters)
    agent_counters["active_agent_update_wall_ns"] = max(0, perf_counter_ns() - start_ns)
    updates: dict[str, Any] = {"demand_state": demand_state}
    if pool is not None:
        updates["active_agent_pool"] = pool
    if link_state is not None:
        updates["flow_link_state"] = link_state
    return state.with_dynamic_updates(**updates), {**route_counters, **agent_counters}


def _build_optional_ui_snapshot_source(
    *,
    state: SimulationState,
    control: SimulationControl,
    invariant_report: InvariantReport,
) -> UISnapshotSource | None:
    if not control.ui_force_snapshot:
        return None
    return build_ui_snapshot_source(state=state, invariant_report=invariant_report)


def _update_metrics_state(
    *,
    state: SimulationState,
    prior_metrics_state: Any,
    invariant_report: InvariantReport,
    ui_snapshot_emitted: bool,
    tick_counters: Mapping[str, int],
) -> dict[str, Any]:
    metrics = dict(prior_metrics_state) if isinstance(prior_metrics_state, Mapping) else {}
    demand_state = state.dynamic.demand_state if isinstance(state.dynamic.demand_state, Mapping) else {}
    active_agents = int(getattr(state.dynamic.active_agent_pool, "alive_count", 0) or 0)
    queued = int(demand_state.get("queued_trip_requests", metrics.get("queued_trip_requests", 0)))
    pending = int(demand_state.get("pending_trip_requests", metrics.get("pending_trip_requests", queued)))
    capacity_count = int(getattr(state.dynamic.flow_link_state, "capacity_violation_count", 0) or 0)
    prior_capacity_count = int(metrics.get("capacity_violation_count", 0))
    route_state = state.dynamic.route_candidate_state
    route_stats = getattr(route_state, "stats", {}) if route_state is not None else {}
    if not isinstance(route_stats, Mapping):
        route_stats = {}
    link_state = state.dynamic.flow_link_state
    queue_total = _sum_link_array(link_state, "queue_vehicles")
    outflow_total = _sum_link_array(link_state, "outflow_vehicles")
    rerouted_tick = int(tick_counters.get("active_agent_rerouted_this_tick", 0))
    reroute_cooldown_tick = int(
        tick_counters.get("active_agent_reroute_cooldown_this_tick", 0)
    )
    sink_wait_tick = int(tick_counters.get("active_agent_sink_wait_this_tick", 0))
    flow_update_wall_ns = int(tick_counters.get("flow_update_wall_ns", 0))
    active_agent_update_wall_ns = int(
        tick_counters.get("active_agent_update_wall_ns", 0)
    )
    reroute_decision_wall_ns = int(tick_counters.get("reroute_decision_wall_ns", 0))
    metrics.update(
        {
            "tick_index": state.tick_index,
            "active_agents": active_agents,
            "queued_trip_requests": queued,
            "pending_trip_requests": pending,
            "capacity_violation_count": capacity_count,
            "capacity_violation_count_delta": max(0, capacity_count - prior_capacity_count),
            "negative_queue_detected": invariant_report.counters.negative_queue_violations > 0,
            "ui_packets_emitted": int(metrics.get("ui_packets_emitted", 0)) + int(ui_snapshot_emitted),
            "completed_trips_total": int(metrics.get("completed_trips_total", 0))
            + int(tick_counters.get("trip_completed_this_tick", 0)),
            "failed_trips_total": int(metrics.get("failed_trips_total", 0))
            + int(tick_counters.get("trip_failed_this_tick", 0)),
            "generated_trip_total": int(metrics.get("generated_trip_total", 0))
            + int(tick_counters.get("trip_generated_this_tick", 0)),
            "flow_backend": state.config.flow_backend,
            "routing_backend": state.config.routing_backend,
            "agent_backend": state.config.agent_backend,
            "flow_update_wall_ns": flow_update_wall_ns,
            "flow_update_wall_ns_total": int(
                metrics.get("flow_update_wall_ns_total", 0)
            )
            + flow_update_wall_ns,
            "active_agent_update_wall_ns": active_agent_update_wall_ns,
            "active_agent_update_wall_ns_total": int(
                metrics.get("active_agent_update_wall_ns_total", 0)
            )
            + active_agent_update_wall_ns,
            "reroute_decision_wall_ns": reroute_decision_wall_ns,
            "reroute_decision_wall_ns_total": int(
                metrics.get("reroute_decision_wall_ns_total", 0)
            )
            + reroute_decision_wall_ns,
            "queue_vehicles_total": queue_total,
            "outflow_vehicles_total": outflow_total,
            "route_candidate_refresh_total": int(
                route_stats.get("route_candidate_refresh_total", 0)
            ),
            "route_candidate_reuse_total": int(
                route_stats.get("route_candidate_reuse_total", 0)
            ),
            "dynamic_potential_recompute_total": int(
                route_stats.get("dynamic_potential_recompute_total", 0)
            ),
            "dynamic_potential_cache_hits_total": int(
                route_stats.get("dynamic_potential_cache_hits_total", 0)
            ),
            "route_candidate_refresh_seconds_total": float(
                route_stats.get("route_candidate_refresh_seconds_total", 0.0)
            ),
            "dynamic_potential_recompute_seconds_total": float(
                route_stats.get("dynamic_potential_recompute_seconds_total", 0.0)
            ),
            "routing_compile_seconds_estimate_total": float(
                route_stats.get("routing_compile_seconds_estimate_total", 0.0)
            ),
            "active_agent_moved_this_tick": int(
                tick_counters.get("active_agent_moved_this_tick", 0)
            ),
            "active_agent_sink_wait_this_tick": sink_wait_tick,
            "active_agent_sink_wait_total": int(
                metrics.get("active_agent_sink_wait_total", 0)
            )
            + sink_wait_tick,
            "active_agent_rerouted_this_tick": rerouted_tick,
            "active_agent_reroute_cooldown_this_tick": reroute_cooldown_tick,
            "us2_reroute_decisions_total": int(
                metrics.get("us2_reroute_decisions_total", 0)
            )
            + rerouted_tick,
            "us2_persistence_decisions_total": int(
                metrics.get("us2_persistence_decisions_total", 0)
            )
            + reroute_cooldown_tick,
        }
    )
    return metrics


def _build_step_telemetry(
    *,
    state: SimulationState,
    invariant_report: InvariantReport,
    ui_snapshot_emitted: bool,
    tick_counters: Mapping[str, int],
) -> SimulationTelemetry:
    metrics_state = state.dynamic.metrics_state if isinstance(state.dynamic.metrics_state, Mapping) else {}
    return SimulationTelemetry(
        tick_index=state.tick_index,
        active_agent_count=int(metrics_state.get("active_agents", 0)),
        trip_generated_this_tick=int(tick_counters.get("trip_generated_this_tick", 0)),
        trip_completed_this_tick=int(tick_counters.get("trip_completed_this_tick", 0)),
        trip_failed_this_tick=int(tick_counters.get("trip_failed_this_tick", 0)),
        capacity_violation_count_delta=int(metrics_state.get("capacity_violation_count_delta", 0)),
        negative_queue_detected=invariant_report.counters.negative_queue_violations > 0,
        policy_mix_lambda=0.0,
        adaptive_fallback_triggered=False,
        ui_snapshot_emitted=ui_snapshot_emitted,
        flow_backend=str(metrics_state.get("flow_backend", state.config.flow_backend)),
        routing_backend=str(metrics_state.get("routing_backend", state.config.routing_backend)),
        agent_backend=str(metrics_state.get("agent_backend", state.config.agent_backend)),
        flow_update_wall_ns=int(metrics_state.get("flow_update_wall_ns", 0)),
        active_agent_update_wall_ns=int(
            metrics_state.get("active_agent_update_wall_ns", 0)
        ),
        reroute_decision_wall_ns=int(
            metrics_state.get("reroute_decision_wall_ns", 0)
        ),
        queue_vehicles_total=float(metrics_state.get("queue_vehicles_total", 0.0)),
        outflow_vehicles_total=float(metrics_state.get("outflow_vehicles_total", 0.0)),
        route_candidate_refresh_total=int(
            metrics_state.get("route_candidate_refresh_total", 0)
        ),
        route_candidate_reuse_total=int(metrics_state.get("route_candidate_reuse_total", 0)),
        dynamic_potential_recompute_total=int(
            metrics_state.get("dynamic_potential_recompute_total", 0)
        ),
        dynamic_potential_cache_hits_total=int(
            metrics_state.get("dynamic_potential_cache_hits_total", 0)
        ),
        active_agent_moved_this_tick=int(
            metrics_state.get("active_agent_moved_this_tick", 0)
        ),
        active_agent_sink_wait_this_tick=int(
            metrics_state.get("active_agent_sink_wait_this_tick", 0)
        ),
        active_agent_rerouted_this_tick=int(
            metrics_state.get("active_agent_rerouted_this_tick", 0)
        ),
        active_agent_reroute_cooldown_this_tick=int(
            metrics_state.get("active_agent_reroute_cooldown_this_tick", 0)
        ),
    )


def _road_csr_from_state(state: SimulationState) -> Any:
    routing_static = state.static.routing_static
    if isinstance(routing_static, Mapping):
        return routing_static.get("road_csr")
    return getattr(routing_static, "road_csr", None)


def _active_events_from_state(state: SimulationState) -> tuple[Any, ...]:
    event_state = state.dynamic.event_state
    if isinstance(event_state, Mapping):
        return tuple(event_state.get("active_events", ()) or ())
    return tuple(getattr(event_state, "active_events", ()) or ())


def _with_link_metadata_increment(link_state: LinkState, *, key: str) -> LinkState:
    metadata = dict(link_state.metadata)
    metadata[key] = int(metadata.get(key, 0)) + 1
    return LinkState.from_internal_arrays(
        queue_vehicles=link_state.queue_vehicles,
        inflow_vehicles=link_state.inflow_vehicles,
        outflow_vehicles=link_state.outflow_vehicles,
        travel_time_cost=link_state.travel_time_cost,
        capacity_veh_per_tick=link_state.capacity_veh_per_tick,
        incident_capacity_multiplier=link_state.incident_capacity_multiplier,
        capacity_violation_flags=link_state.capacity_violation_flags,
        metadata=metadata,
    )


def _sum_link_array(link_state: Any, attr_name: str) -> float:
    values = getattr(link_state, attr_name, None)
    if values is None:
        return 0.0
    return float(np.sum(np.asarray(values, dtype=np.float32)).item())
