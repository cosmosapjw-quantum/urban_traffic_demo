from __future__ import annotations

import pytest


def test_simulation_state_clock_updates_are_immutable_and_validated() -> None:
    from metroflow.sim.config import DayType, TimeBand
    from metroflow.sim.state import SimulationState

    state = SimulationState()
    updated = state.with_clock(tick_index=3, day_type="weekend", time_band="evening")

    assert state.tick_index == 0
    assert state.day_type is DayType.WEEKDAY
    assert updated.tick_index == 3
    assert updated.day_type is DayType.WEEKEND
    assert updated.time_band is TimeBand.EVENING

    with pytest.raises(KeyError, match="unknown dynamic fields"):
        updated.with_dynamic_updates(unknown_field=object())


def test_ui_control_command_parser_maps_packets_to_simulation_control() -> None:
    from metroflow.ui.control_adapter import parse_ui_control_command
    from metroflow.ui.packets import UIPacketType, build_ui_packet_envelope

    packet = build_ui_packet_envelope(
        packet_type=UIPacketType.CONTROL_COMMAND,
        run_id="run-1",
        tick=5,
        day_type="weekday",
        time_band="morning",
        payload={
            "command_id": "cmd-1",
            "action": "set_time_band",
            "arguments": {"time_band": "night"},
        },
    )

    parsed = parse_ui_control_command(packet)

    assert parsed.accepted is True
    assert parsed.command_id == "cmd-1"
    assert parsed.control.set_time_band.value == "night"
    assert parsed.ack_payload(applied_tick=6) == {
        "command_id": "cmd-1",
        "accepted": True,
        "applied_tick": 6,
    }


def test_invariant_report_counts_capacity_and_conservation_violations() -> None:
    from metroflow.sim.invariants import (
        ConservationSnapshot,
        check_capacity_violation_flags,
        check_conservation_hook,
    )

    conservation = check_conservation_hook(
        ConservationSnapshot(
            generated_total=10,
            pending_trip_requests=3,
            active_agents=2,
            completed_trips_total=4,
            failed_trips_total=0,
        )
    )
    capacity = check_capacity_violation_flags(
        outflow_values=[2.0, 5.0],
        effective_capacity_values=[2.0, 3.0],
        flagged_count=0,
    )

    assert conservation[0].code == "conservation_mismatch"
    assert conservation[0].details["delta"] == 1
    assert capacity[0].code == "capacity_flag_count_mismatch"
    assert capacity[0].details["observed_exceed_count"] == 1


def test_ui_snapshot_source_samples_link_congestion_and_summary_metrics() -> None:
    import numpy as np

    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr
    from metroflow.flow.state import LinkState
    from metroflow.sim.active_agents import create_active_agent_pool
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.invariants import InvariantReport
    from metroflow.sim.state import SimulationDynamicRefs, SimulationState, SimulationStaticRefs
    from metroflow.ui.snapshots import build_ui_snapshot_source

    road_csr = build_road_network_csr(
        nodes=(Node(1), Node(2), Node(3)),
        links=(
            RoadLink(1, 1, 2, RoadClass.LOCAL, 100.0, 10.0, 4.0),
            RoadLink(2, 2, 3, RoadClass.ARTERIAL, 150.0, 15.0, 6.0),
        ),
        turns=(),
    )
    link_state = LinkState(
        queue_vehicles=np.asarray([2.0, 3.0], dtype=np.float32),
        inflow_vehicles=np.asarray([0.0, 0.0], dtype=np.float32),
        outflow_vehicles=np.asarray([1.0, 2.0], dtype=np.float32),
        travel_time_cost=np.asarray([12.0, 20.0], dtype=np.float32),
        capacity_veh_per_tick=np.asarray([4.0, 6.0], dtype=np.float32),
        incident_capacity_multiplier=np.asarray([1.0, 1.0], dtype=np.float32),
        capacity_violation_flags=np.asarray([False, True], dtype=np.bool_),
        metadata={"free_flow_travel_time_cost": np.asarray([10.0, 10.0], dtype=np.float32)},
    )
    state = SimulationState(
        config=SimulationConfig(),
        static=SimulationStaticRefs(
            routing_static={"road_csr": road_csr},
            ui_network_geometry_version="geom-1",
        ),
        dynamic=SimulationDynamicRefs(
            active_agent_pool=create_active_agent_pool(4),
            flow_link_state=link_state,
            event_state={"active_events": ("event-1",)},
            metrics_state={
                "queued_trip_requests": 7,
                "completed_trips_total": 2,
                "failed_trips_total": 1,
                "capacity_violation_count": 1,
                "flow_backend": "baseline",
                "routing_backend": "baseline",
                "route_candidate_refresh_total": 3,
                "route_candidate_reuse_total": 4,
                "dynamic_potential_recompute_total": 5,
                "dynamic_potential_cache_hits_total": 6,
                "active_agent_moved_this_tick": 8,
                "active_agent_sink_wait_this_tick": 3,
                "active_agent_sink_wait_total": 11,
                "active_agent_rerouted_this_tick": 2,
                "active_agent_reroute_cooldown_this_tick": 1,
                "us2_reroute_decisions_total": 9,
                "us2_persistence_decisions_total": 10,
            },
        ),
    )

    snapshot = build_ui_snapshot_source(
        state=state,
        invariant_report=InvariantReport(tick_index=state.tick_index),
        max_link_samples=2,
    )

    assert snapshot["network_geometry_version"] == "geom-1"
    assert len(snapshot["sampled_link_congestion"]) == 2
    assert snapshot["sampled_link_congestion"][1]["capacity_flag"] is True
    assert snapshot["active_events"] == ("event-1",)
    assert snapshot["summary_metrics"]["queued_trip_requests"] == 7
    assert snapshot["summary_metrics"]["capacity_violation_count"] == 1
    assert snapshot["summary_metrics"]["routing_backend"] == "baseline"
    assert snapshot["summary_metrics"]["route_candidate_refresh_total"] == 3
    assert snapshot["summary_metrics"]["dynamic_potential_cache_hits_total"] == 6
    assert snapshot["summary_metrics"]["active_agent_moved_this_tick"] == 8
    assert snapshot["summary_metrics"]["active_agent_sink_wait_this_tick"] == 3
    assert snapshot["summary_metrics"]["active_agent_sink_wait_total"] == 11
    assert snapshot["summary_metrics"]["active_agent_rerouted_this_tick"] == 2
    assert snapshot["summary_metrics"]["active_agent_reroute_cooldown_this_tick"] == 1
    assert snapshot["summary_metrics"]["us2_reroute_decisions_total"] == 9
    assert snapshot["summary_metrics"]["us2_persistence_decisions_total"] == 10


def test_disruption_scenario_controls_build_deterministic_event_sequence() -> None:
    from metroflow.flow.events import TrafficEventStatus
    from metroflow.ui.scenario_controls import build_disruption_scenario_controls

    controls = build_disruption_scenario_controls(
        "blocked_edge_accident",
        link_id=9,
        event_id=123,
        current_tick=10,
        start_tick=2,
        duration_ticks=2,
    )

    assert len(controls) == 4
    assert controls[0].inject_event.event_id == 123
    assert controls[0].inject_event.start_tick == 12
    assert controls[0].inject_event.status is TrafficEventStatus.SCHEDULED
    assert controls[-2].clear_event_ids == (123,)
    assert controls[-1].ui_force_snapshot is True
