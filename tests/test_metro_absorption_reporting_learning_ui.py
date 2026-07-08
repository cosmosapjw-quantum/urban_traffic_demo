from __future__ import annotations

import sys


def test_learning_experience_batch_is_simulator_only_and_bounded() -> None:
    assert not any(path.endswith("/metro/src") for path in sys.path)

    from metroflow.flow.events import TrafficEvent, TrafficEventSchedulerState, TrafficEventStatus
    from metroflow.learning.experience import (
        compute_trip_outcome_reward,
        extract_online_experience_batch,
    )
    from metroflow.sim.control import SimulationTelemetry
    from metroflow.sim.init import build_initial_simulation_state

    bundle = build_initial_simulation_state(scenario_seed=31, eager_trip_generation=False)
    event = TrafficEvent(
        event_id=99,
        event_type="accident",
        start_tick=0,
        end_tick=10,
        target_scope={"link_ids": (1, 2)},
        severity=0.5,
        effect_model="capacity_multiplier",
        status=TrafficEventStatus.ACTIVE,
    )
    state = bundle.state.with_dynamic_updates(
        event_state=TrafficEventSchedulerState(active_events=(event,)),
        metadata={"us2_active_event_affected_link_ids": (1, 2)},
    )
    telemetry = SimulationTelemetry(
        tick_index=state.tick_index,
        active_agent_count=3,
        trip_completed_this_tick=1,
        trip_failed_this_tick=1,
        policy_mix_lambda=0.25,
    )

    batch = extract_online_experience_batch(
        state=state,
        telemetry=telemetry,
        outcome_rows=[
            {
                "od_key": ("home-1", "work-1"),
                "trip_id": 7,
                "outcome": "completed",
                "observed_travel_time": 12.0,
                "baseline_travel_time": 6.0,
                "chosen_arm_index": 2,
            },
            {
                "od_key": ("home-2", "work-2"),
                "trip_id": 8,
                "outcome": "failed",
                "observed_travel_time": 20.0,
                "baseline_travel_time": 10.0,
            },
            {"od_key": ("bad", "row"), "trip_id": 9, "outcome": "ignored"},
        ],
    )

    assert len(batch) == 2
    assert batch[0].reward == compute_trip_outcome_reward(
        outcome="completed",
        observed_travel_time=12.0,
        baseline_travel_time=6.0,
    )
    assert 0.0 <= batch[0].reward <= 1.0
    assert -1.0 <= batch[1].reward <= 0.0
    assert batch[0].policy_mix_lambda == 0.25
    assert batch[0].context_summary["active_agent_count"] == 3
    assert batch[0].event_context["active_event_ids"] == (99,)
    assert batch[0].event_context["affected_link_ids"] == (1, 2)


def test_baseline_run_summary_and_comparison_are_donor_independent() -> None:
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.init import build_initial_simulation_state
    from metroflow.sim.run_summary import (
        build_baseline_run_summary,
        build_run_summary_comparison,
        format_run_summary_comparison_markdown,
    )
    from metroflow.sim.step import simulation_step

    bundle = build_initial_simulation_state(
        scenario_seed=32,
        config=SimulationConfig(route_path_size_gamma=1.5),
        eager_trip_generation=True,
    )
    state, _telemetry, _snapshot, _key = simulation_step(
        bundle.state,
        SimulationControl(ui_force_snapshot=True),
        bundle.rng_key,
    )
    summary = build_baseline_run_summary(state, ui_packet_counts={"ui.metrics_summary": 1})

    assert summary.scenario_id == "synthetic-32"
    assert summary.seed == 32
    assert summary.tick_index == 1
    assert summary.trip_generation_total == len(bundle.trip_requests.trip_requests)
    assert summary.ui_packets_emitted == 1
    assert summary.hotspot_links_top_k
    assert summary.map_foundation_profile == "sc020_sc042_map_foundation"
    assert summary.route_path_size_gamma == 1.5

    adaptive = build_baseline_run_summary(
        state.with_dynamic_updates(
            metrics_state={
                **state.dynamic.metrics_state,
                "completed_trips_total": summary.trip_completed_total + 2,
                "failed_trips_total": summary.trip_failed_total,
                "us2_reroute_decisions_total": 4,
                "us2_persistence_decisions_total": 6,
            }
        ),
        ui_packet_counts={"ui.metrics_summary": 1},
    )
    comparison = build_run_summary_comparison(summary, adaptive)
    markdown = format_run_summary_comparison_markdown(comparison)

    assert comparison.trip_completed_total_delta == 2
    assert comparison.reroute_share_delta > 0.0
    assert "Completed trips delta" in markdown


def test_navigator_ui_stream_server_packetizes_step_output_and_control_ack() -> None:
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.init import build_initial_simulation_state
    from metroflow.sim.step import simulation_step
    from metroflow.ui.packets import UIPacketType, build_ui_packet_envelope
    from metroflow.ui.stream_server import NavigatorUIStreamServer

    bundle = build_initial_simulation_state(
        scenario_seed=33,
        config=None,
        eager_trip_generation=True,
    )
    state, telemetry, snapshot, key = simulation_step(
        bundle.state,
        SimulationControl(ui_force_snapshot=True),
        bundle.rng_key,
    )
    assert key.tolist() != bundle.rng_key.tolist()
    metrics_state = dict(state.dynamic.metrics_state)
    metrics_state.update(
        {
            "routing_backend": "baseline",
            "flow_backend": "baseline",
            "route_candidate_refresh_total": 3,
            "dynamic_potential_recompute_total": 2,
            "dynamic_potential_cache_hits_total": 1,
            "active_agent_moved_this_tick": 4,
            "active_agent_sink_wait_this_tick": 3,
            "active_agent_sink_wait_total": 11,
            "active_agent_rerouted_this_tick": 2,
            "active_agent_reroute_cooldown_this_tick": 1,
            "us2_reroute_decisions_total": 7,
            "us2_persistence_decisions_total": 5,
        }
    )
    state = state.with_dynamic_updates(metrics_state=metrics_state)

    server = NavigatorUIStreamServer(metrics_emit_interval_ticks=1)
    packets = server.ingest_step_output(
        state=state,
        telemetry=telemetry,
        ui_snapshot_source=snapshot,
        force_snapshot_emit=True,
    )
    packet_types = tuple(packet.type for packet in packets)

    assert UIPacketType.TOPOLOGY_SNAPSHOT in packet_types
    assert UIPacketType.CONGESTION_FRAME in packet_types
    assert UIPacketType.METRICS_SUMMARY in packet_types
    assert packets[0].run_id == "synthetic-33"
    metrics_payload = next(
        packet.payload for packet in packets if packet.type is UIPacketType.METRICS_SUMMARY
    )
    assert metrics_payload["routing_backend"] == "baseline"
    assert metrics_payload["flow_backend"] == "baseline"
    assert metrics_payload["route_candidate_refresh_total"] == 3
    assert metrics_payload["dynamic_potential_recompute_total"] == 2
    assert metrics_payload["dynamic_potential_cache_hits_total"] == 1
    assert metrics_payload["active_agent_moved_this_tick"] == 4
    assert metrics_payload["active_agent_sink_wait_this_tick"] == 3
    assert metrics_payload["active_agent_sink_wait_total"] == 11
    assert metrics_payload["active_agent_rerouted_this_tick"] == 2
    assert metrics_payload["active_agent_reroute_cooldown_this_tick"] == 1
    assert metrics_payload["us2_reroute_decisions_total"] == 7
    assert metrics_payload["us2_persistence_decisions_total"] == 5

    command = build_ui_packet_envelope(
        packet_type=UIPacketType.CONTROL_COMMAND,
        run_id="synthetic-33",
        tick=state.tick_index,
        day_type=state.day_type,
        time_band=state.time_band,
        payload={
            "command_id": "cmd-snapshot",
            "action": "request_snapshot",
            "arguments": {"force": True},
        },
    )
    control, ack = server.handle_ui_control_packet(command, state=state, applied_tick=state.tick_index)

    assert control.ui_force_snapshot is True
    assert ack.type is UIPacketType.CONTROL_ACK
    assert ack.payload["accepted"] is True
    assert ack.payload["command_id"] == "cmd-snapshot"
