from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from metroflow.sim.control import SimulationControl, SimulationTelemetry
from metroflow.sim.state import SimulationState
from metroflow.ui.control_adapter import build_ui_control_ack_packet, parse_ui_control_command
from metroflow.ui.packets import (
    UIPacketEnvelope,
    UIPacketType,
    build_ui_event_overlay_packet,
    build_ui_packet_envelope,
    normalize_ui_event_overlay_item as _normalize_event_overlay_item_shared,
)
from metroflow.ui.stream_buffer import UISnapshotEmission, UISnapshotStreamBuffer

__all__ = [
    "NavigatorUIStreamServer",
]


@dataclass(slots=True)
class NavigatorUIStreamServer:
    """Minimal in-memory packet stream adapter for navigator-style UI updates.

    T039 scope:
    - Convert optional `UISnapshotSource` + telemetry into packet envelopes
    - Reuse `UISnapshotStreamBuffer` for throttled/coalesced congestion emission
    - Parse UI control packets and emit `ui.control_ack`
    - Keep topology snapshot low-frequency (only when geometry version changes)
    """

    metrics_emit_interval_ticks: int = 1
    event_overlay_emit_on_empty: bool = False
    _last_topology_geometry_version: str | None = None
    _last_event_signature: tuple[str, ...] | None = None
    _last_metrics_emit_tick: int | None = None

    def __post_init__(self) -> None:
        self.metrics_emit_interval_ticks = int(self.metrics_emit_interval_ticks)
        if self.metrics_emit_interval_ticks < 1:
            raise ValueError("metrics_emit_interval_ticks must be >= 1")
        self.event_overlay_emit_on_empty = bool(self.event_overlay_emit_on_empty)

    def handle_ui_control_packet(
        self,
        packet: Mapping[str, Any] | UIPacketEnvelope,
        *,
        state: SimulationState,
        applied_tick: int | None = None,
    ) -> tuple[SimulationControl, UIPacketEnvelope]:
        """Parse a UI control packet and emit a matching ACK envelope."""

        parse_result = parse_ui_control_command(packet)
        ack = build_ui_control_ack_packet(
            run_id=_run_id_from_state(state),
            tick=state.tick_index,
            day_type=state.day_type,
            time_band=state.time_band,
            command_id=parse_result.command_id,
            accepted=parse_result.accepted,
            reason=parse_result.reason,
            applied_tick=(None if not parse_result.accepted else applied_tick),
        )
        return parse_result.control, ack

    def ingest_step_output(
        self,
        *,
        state: SimulationState,
        telemetry: SimulationTelemetry,
        ui_snapshot_source: Mapping[str, Any] | None,
        force_snapshot_emit: bool = False,
    ) -> tuple[UIPacketEnvelope, ...]:
        """Convert step outputs into zero or more UI packet envelopes."""

        packets: list[UIPacketEnvelope] = []
        if ui_snapshot_source is None:
            return ()

        snapshot = dict(ui_snapshot_source)
        packets.extend(self._maybe_topology_packet(state=state, snapshot=snapshot))

        emission = self._offer_or_emit_snapshot(
            ui_state=state.dynamic.ui_state,
            snapshot=snapshot,
            tick=state.tick_index,
            force_emit=bool(force_snapshot_emit),
        )
        if emission is not None:
            packets.append(
                _build_congestion_frame_packet(
                    state=state,
                    telemetry=telemetry,
                    emission=emission,
                )
            )

        event_packet = self._maybe_event_overlay_packet(state=state, snapshot=snapshot)
        if event_packet is not None:
            packets.append(event_packet)

        metrics_packet = self._maybe_metrics_summary_packet(
            state=state,
            telemetry=telemetry,
            snapshot=snapshot,
        )
        if metrics_packet is not None:
            packets.append(metrics_packet)

        return tuple(packets)

    def _offer_or_emit_snapshot(
        self,
        *,
        ui_state: Any,
        snapshot: Mapping[str, Any],
        tick: int,
        force_emit: bool,
    ) -> UISnapshotEmission | None:
        if isinstance(ui_state, UISnapshotStreamBuffer):
            return ui_state.offer(snapshot, tick=tick, force_emit=force_emit)
        return UISnapshotEmission(
            snapshot_source=snapshot,
            snapshot_tick=tick,
            emitted_at_tick=tick,
            frame_seq=tick,
            forced=force_emit,
        )

    def _maybe_topology_packet(
        self,
        *,
        state: SimulationState,
        snapshot: Mapping[str, Any],
    ) -> tuple[UIPacketEnvelope, ...]:
        geometry_version = str(
            snapshot.get("network_geometry_version", state.static.ui_network_geometry_version or "unknown")
        )
        if self._last_topology_geometry_version == geometry_version:
            return ()
        payload = _build_topology_snapshot_payload(state)
        self._last_topology_geometry_version = geometry_version
        return (
            build_ui_packet_envelope(
                packet_type=UIPacketType.TOPOLOGY_SNAPSHOT,
                run_id=_run_id_from_state(state),
                tick=state.tick_index,
                day_type=state.day_type,
                time_band=state.time_band,
                payload=payload,
            ),
        )

    def _maybe_event_overlay_packet(
        self,
        *,
        state: SimulationState,
        snapshot: Mapping[str, Any],
    ) -> UIPacketEnvelope | None:
        active_events = tuple(snapshot.get("active_events", ()) or ())
        signature = tuple(_event_signature(e) for e in active_events)
        if not active_events and not self.event_overlay_emit_on_empty:
            if self._last_event_signature in (None, ()):
                return None
            # Emit a one-time clear packet so the UI can remove stale overlays.
            self._last_event_signature = ()
            return build_ui_event_overlay_packet(
                run_id=_run_id_from_state(state),
                tick=state.tick_index,
                day_type=state.day_type,
                time_band=state.time_band,
                events=(),
            )
        if signature == self._last_event_signature:
            return None
        self._last_event_signature = signature
        return build_ui_event_overlay_packet(
            run_id=_run_id_from_state(state),
            tick=state.tick_index,
            day_type=state.day_type,
            time_band=state.time_band,
            events=active_events,
        )

    def _maybe_metrics_summary_packet(
        self,
        *,
        state: SimulationState,
        telemetry: SimulationTelemetry,
        snapshot: Mapping[str, Any],
    ) -> UIPacketEnvelope | None:
        tick = int(state.tick_index)
        if self._last_metrics_emit_tick is not None:
            if (tick - self._last_metrics_emit_tick) < self.metrics_emit_interval_ticks:
                return None
        self._last_metrics_emit_tick = tick
        return build_ui_packet_envelope(
            packet_type=UIPacketType.METRICS_SUMMARY,
            run_id=_run_id_from_state(state),
            tick=tick,
            day_type=state.day_type,
            time_band=state.time_band,
            payload=_build_metrics_summary_payload(
                state=state,
                telemetry=telemetry,
                snapshot=snapshot,
            ),
        )


def _run_id_from_state(state: SimulationState) -> str:
    scenario_id = getattr(state.static, "scenario_id", "")
    run_id = str(scenario_id).strip() if scenario_id is not None else ""
    return run_id or "metroflow-run"


def _build_topology_snapshot_payload(state: SimulationState) -> dict[str, Any]:
    city = state.static.city_topology
    zones = tuple(state.static.zones or ())
    if city is None:
        return {
            "network_geometry_version": str(state.static.ui_network_geometry_version or "unknown"),
            "nodes": (),
            "links": (),
            "zones": (),
            "bridges": (),
        }

    nodes = tuple(getattr(city, "nodes", ()) or ())
    links = tuple(getattr(city, "links", ()) or ())
    bridge_crossings = tuple(getattr(city, "bridge_crossings", ()) or ())
    node_xy = {int(node.node_id): (float(node.x), float(node.y)) for node in nodes}

    node_payload = tuple(
        {
            "node_id": int(node.node_id),
            "x": float(node.x),
            "y": float(node.y),
            "kind": str(getattr(node.kind, "value", node.kind)),
        }
        for node in nodes
    )
    link_payload = tuple(
        {
            "link_id": int(link.link_id),
            "class": str(getattr(link.road_class, "value", link.road_class)),
            "bridge": bool(getattr(link, "bridge_group_id", None) is not None),
            "polyline": (
                node_xy.get(int(link.src_node_id), (0.0, 0.0)),
                node_xy.get(int(link.dst_node_id), (0.0, 0.0)),
            ),
        }
        for link in links
    )
    zone_payload = tuple(
        {
            "zone_id": int(zone.zone_id),
            "zone_type": str(getattr(zone.zone_type, "value", zone.zone_type)),
            "centroid": (float(zone.centroid_x), float(zone.centroid_y)),
        }
        for zone in zones
    )
    bridge_payload = tuple(
        {
            "bridge_group_id": int(crossing.bridge_group_id),
            "name": str(crossing.crossing_name),
            "corridor": f"barrier-{int(crossing.barrier_id)}",
        }
        for crossing in bridge_crossings
    )
    return {
        "network_geometry_version": str(state.static.ui_network_geometry_version or "unknown"),
        "nodes": node_payload,
        "links": link_payload,
        "zones": zone_payload,
        "bridges": bridge_payload,
        "map_foundation_gate": _map_foundation_gate_payload(state),
    }


def _build_congestion_frame_packet(
    *,
    state: SimulationState,
    telemetry: SimulationTelemetry,
    emission: UISnapshotEmission,
) -> UIPacketEnvelope:
    snapshot = emission.snapshot_source if isinstance(emission.snapshot_source, Mapping) else {}
    sampled = tuple(snapshot.get("sampled_link_congestion", ()) or ())
    routing_static = state.static.routing_static if isinstance(state.static.routing_static, Mapping) else {}
    road_csr = routing_static.get("road_csr")
    link_count = int(getattr(road_csr, "link_count", len(sampled) if sampled else 0) or 0)
    sampling_mode = "full" if sampled and len(sampled) == link_count else "downsampled"
    if not sampled:
        sampling_mode = "downsampled"
    link_congestion = tuple(
        {
            "link_id": int(item.get("link_id", 0)),
            "congestion_level": float(item.get("congestion_ratio", 0.0)),
            "travel_time_ratio": float(item.get("slowdown_ratio", 1.0)),
        }
        for item in sampled
        if isinstance(item, Mapping)
    )
    return build_ui_packet_envelope(
        packet_type=UIPacketType.CONGESTION_FRAME,
        run_id=_run_id_from_state(state),
        tick=state.tick_index,
        day_type=state.day_type,
        time_band=state.time_band,
        payload={
            "frame_seq": int(emission.frame_seq),
            "sampling_mode": sampling_mode,
            "link_congestion": link_congestion,
            "active_agent_count": int(telemetry.active_agent_count),
            "dropped_frame_count_since_last": int(emission.dropped_since_last_emit),
        },
    )


def _build_metrics_summary_payload(
    *,
    state: SimulationState,
    telemetry: SimulationTelemetry,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    metrics_state = state.dynamic.metrics_state if isinstance(state.dynamic.metrics_state, Mapping) else {}
    summary = snapshot.get("summary_metrics", {})
    if not isinstance(summary, Mapping):
        summary = {}
    map_gate = _map_foundation_gate_payload(state)
    return {
        "trip_generated_total": int(metrics_state.get("generated_trip_total", 0)),
        "trip_completed_total": int(summary.get("completed_trips_total", metrics_state.get("completed_trips_total", 0))),
        "trip_failed_total": int(summary.get("failed_trips_total", metrics_state.get("failed_trips_total", 0))),
        "capacity_violation_count": int(summary.get("capacity_violation_count", metrics_state.get("capacity_violation_count", 0))),
        "policy_mix_lambda": float(telemetry.policy_mix_lambda),
        "adaptive_fallback_active": bool(telemetry.adaptive_fallback_triggered),
        "tick_rate_recent_hz": float(1.0 / max(float(state.config.tick_seconds), 1e-6)),
        "map_foundation_profile": map_gate["profile"],
        "map_foundation_overall_pass": map_gate["overall_pass"],
        "map_foundation_failed_checks": map_gate["failed_checks"],
        "map_foundation_passed_check_count": map_gate["passed_check_count"],
        "map_foundation_check_count": map_gate["check_count"],
        "flow_backend": str(
            _metric_value(metrics_state, summary, "flow_backend", telemetry.flow_backend)
        ),
        "routing_backend": str(
            _metric_value(metrics_state, summary, "routing_backend", telemetry.routing_backend)
        ),
        "agent_backend": str(
            _metric_value(metrics_state, summary, "agent_backend", telemetry.agent_backend)
        ),
        "flow_update_wall_ns": int(
            _metric_value(
                metrics_state,
                summary,
                "flow_update_wall_ns",
                telemetry.flow_update_wall_ns,
            )
        ),
        "flow_update_wall_ns_total": int(
            _metric_value(
                metrics_state,
                summary,
                "flow_update_wall_ns_total",
                telemetry.flow_update_wall_ns,
            )
        ),
        "active_agent_update_wall_ns": int(
            _metric_value(
                metrics_state,
                summary,
                "active_agent_update_wall_ns",
                telemetry.active_agent_update_wall_ns,
            )
        ),
        "active_agent_update_wall_ns_total": int(
            _metric_value(
                metrics_state,
                summary,
                "active_agent_update_wall_ns_total",
                telemetry.active_agent_update_wall_ns,
            )
        ),
        "reroute_decision_wall_ns": int(
            _metric_value(
                metrics_state,
                summary,
                "reroute_decision_wall_ns",
                telemetry.reroute_decision_wall_ns,
            )
        ),
        "reroute_decision_wall_ns_total": int(
            _metric_value(
                metrics_state,
                summary,
                "reroute_decision_wall_ns_total",
                telemetry.reroute_decision_wall_ns,
            )
        ),
        "queue_vehicles_total": float(
            _metric_value(
                metrics_state,
                summary,
                "queue_vehicles_total",
                telemetry.queue_vehicles_total,
            )
        ),
        "outflow_vehicles_total": float(
            _metric_value(
                metrics_state,
                summary,
                "outflow_vehicles_total",
                telemetry.outflow_vehicles_total,
            )
        ),
        "route_candidate_refresh_total": int(
            _metric_value(
                metrics_state,
                summary,
                "route_candidate_refresh_total",
                telemetry.route_candidate_refresh_total,
            )
        ),
        "route_candidate_reuse_total": int(
            _metric_value(
                metrics_state,
                summary,
                "route_candidate_reuse_total",
                telemetry.route_candidate_reuse_total,
            )
        ),
        "dynamic_potential_recompute_total": int(
            _metric_value(
                metrics_state,
                summary,
                "dynamic_potential_recompute_total",
                telemetry.dynamic_potential_recompute_total,
            )
        ),
        "dynamic_potential_cache_hits_total": int(
            _metric_value(
                metrics_state,
                summary,
                "dynamic_potential_cache_hits_total",
                telemetry.dynamic_potential_cache_hits_total,
            )
        ),
        "active_agent_moved_this_tick": int(
            _metric_value(
                metrics_state,
                summary,
                "active_agent_moved_this_tick",
                telemetry.active_agent_moved_this_tick,
            )
        ),
        "active_agent_sink_wait_this_tick": int(
            _metric_value(
                metrics_state,
                summary,
                "active_agent_sink_wait_this_tick",
                telemetry.active_agent_sink_wait_this_tick,
            )
        ),
        "active_agent_sink_wait_total": int(
            _metric_value(metrics_state, summary, "active_agent_sink_wait_total", 0)
        ),
        "active_agent_rerouted_this_tick": int(
            _metric_value(
                metrics_state,
                summary,
                "active_agent_rerouted_this_tick",
                telemetry.active_agent_rerouted_this_tick,
            )
        ),
        "active_agent_reroute_cooldown_this_tick": int(
            _metric_value(
                metrics_state,
                summary,
                "active_agent_reroute_cooldown_this_tick",
                telemetry.active_agent_reroute_cooldown_this_tick,
            )
        ),
        "us2_reroute_decisions_total": int(
            _metric_value(metrics_state, summary, "us2_reroute_decisions_total", 0)
        ),
        "us2_persistence_decisions_total": int(
            _metric_value(metrics_state, summary, "us2_persistence_decisions_total", 0)
        ),
    }


def _metric_value(
    metrics_state: Mapping[str, Any],
    summary: Mapping[str, Any],
    key: str,
    default: Any,
) -> Any:
    if key in metrics_state:
        return metrics_state[key]
    return summary.get(key, default)


def _event_signature(event: Any) -> str:
    if isinstance(event, Mapping):
        event_id = event.get("event_id", "")
        status = event.get("status", "")
        severity = event.get("severity", "")
        event_type = event.get("event_type", "")
        return f"{event_id}|{event_type}|{status}|{severity}"
    return str(event)


def _normalize_event_overlay_item(event: Any) -> dict[str, Any]:
    # Keep private helper as a compatibility alias to the shared packet normalizer.
    return _normalize_event_overlay_item_shared(event)


def _map_foundation_gate_payload(state: SimulationState) -> dict[str, Any]:
    static_metadata = state.static.metadata if isinstance(state.static.metadata, Mapping) else {}
    raw_gate = static_metadata.get("map_foundation_gate", {})
    if not isinstance(raw_gate, Mapping):
        raw_gate = {}
    failed_checks = tuple(str(item) for item in raw_gate.get("failed_checks", ()) or ())
    return {
        "profile": str(raw_gate.get("profile", "sc020_sc042_map_foundation")),
        "overall_pass": bool(raw_gate.get("overall_pass", False)),
        "failed_checks": failed_checks,
        "passed_check_count": int(raw_gate.get("passed_check_count", 0)),
        "check_count": int(raw_gate.get("check_count", 0)),
    }
