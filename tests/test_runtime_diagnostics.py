from __future__ import annotations

import numpy as np


def _diagnostic_state():
    from metroflow.city.graph import (
        Node,
        RoadClass,
        RoadLink,
        TurnMovement,
        TurnType,
        build_road_network_csr,
    )
    from metroflow.city.zones import POI, POIType
    from metroflow.demand.trips import TripRequest
    from metroflow.flow.state import LinkState, NodeState
    from metroflow.sim.active_agents import create_active_agent_pool
    from metroflow.sim.config import DayType, SimulationConfig, TimeBand
    from metroflow.sim.routing_runtime import create_simulation_route_cache_state
    from metroflow.sim.state import SimulationDynamicRefs, SimulationState, SimulationStaticRefs

    road_csr = build_road_network_csr(
        nodes=(Node(1), Node(2), Node(3)),
        links=(
            RoadLink(10, 1, 2, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
            RoadLink(11, 2, 3, RoadClass.ARTERIAL, 100.0, 10.0, 2.0),
        ),
        turns=(TurnMovement(10, 11, TurnType.THROUGH),),
    )
    link_state = LinkState(
        queue_vehicles=np.asarray((3.0, 0.0), dtype=np.float32),
        inflow_vehicles=np.zeros((2,), dtype=np.float32),
        outflow_vehicles=np.zeros((2,), dtype=np.float32),
        travel_time_cost=np.ones((2,), dtype=np.float32),
        capacity_veh_per_tick=np.asarray((2.0, 10.0), dtype=np.float32),
        incident_capacity_multiplier=np.ones((2,), dtype=np.float32),
        metadata={
            "free_flow_travel_time_cost": np.ones((2,), dtype=np.float32),
            "runtime_flow_generation": 0,
            "runtime_incident_generation": 0,
        },
    )
    node_state = NodeState(
        turn_from_link_index=road_csr.turn_from_link_index,
        turn_to_link_index=road_csr.turn_to_link_index,
        turn_demand=np.asarray((2.0,), dtype=np.float32),
        turn_supply=np.zeros((1,), dtype=np.float32),
        turn_flow=np.zeros((1,), dtype=np.float32),
        signal_phase_index=np.zeros((3,), dtype=np.int32),
        signal_phase_timer=np.zeros((3,), dtype=np.int32),
        metadata={
            "turn_base_priority": np.asarray(road_csr.turn_base_priority, dtype=np.float32),
            "turn_is_forbidden": np.asarray(road_csr.turn_is_forbidden, dtype=np.bool_),
        },
    )
    trip = TripRequest(
        trip_request_id=1,
        citizen_id=101,
        origin_poi_id=1,
        dest_poi_id=2,
        planned_depart_tick=0,
        day_type=DayType.WEEKDAY,
        time_band=TimeBand.MORNING,
    )
    return SimulationState(
        config=SimulationConfig(active_agent_capacity=4),
        static=SimulationStaticRefs(
            scenario_id="diagnostic-test",
            pois=(
                POI(1, 1, POIType.HOME, node_id=1),
                POI(2, 2, POIType.WORKPLACE, node_id=3),
            ),
            routing_static={"road_csr": road_csr},
            ui_network_geometry_version="diagnostic-geom",
        ),
        dynamic=SimulationDynamicRefs(
            demand_state={
                "trip_requests": (trip,),
                "queued_trip_requests": 1,
                "pending_trip_requests": 1,
                "activated_trip_requests": 0,
            },
            active_agent_pool=create_active_agent_pool(4),
            flow_link_state=link_state,
            flow_node_state=node_state,
            route_candidate_state=create_simulation_route_cache_state(),
            metrics_state={
                "tick_index": 0,
                "queued_trip_requests": 1,
                "pending_trip_requests": 1,
                "completed_trips_total": 0,
                "failed_trips_total": 0,
                "generated_trip_total": 1,
                "capacity_violation_count": 0,
            },
        ),
    )


def test_runtime_diagnostic_rollout_captures_frames_route_cache_and_summary() -> None:
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.runtime_diagnostics import run_runtime_diagnostic_rollout

    report = run_runtime_diagnostic_rollout(
        _diagnostic_state(),
        key_from_seed(123),
        controls=(SimulationControl(), SimulationControl(), SimulationControl()),
        max_link_samples=2,
    )

    assert report.label == "SMOKE DIAGNOSTIC"
    assert len(report.frames) == 3
    assert report.frames[0].tick_index == 1
    assert report.frames[0].route_candidate_refresh_total == 1
    assert report.frames[0].candidate_paths_by_od == {"1->2": ((10, 11),)}
    assert report.frames[0].candidate_metadata_by_od["1->2"]["candidate_count"] == 1
    assert len(report.frames[0].candidate_metadata_by_od["1->2"]["candidate_path_costs"]) == 1
    assert report.frames[0].candidate_metadata_by_od["1->2"]["candidate_path_size_factors"] == (1.0,)
    assert report.frames[0].active_agent_moved_this_tick == 0
    assert report.frames[0].active_agent_rerouted_this_tick == 0
    assert report.frames[0].active_agent_reroute_cooldown_this_tick == 0
    assert report.frames[1].active_agent_count == 1
    assert report.frames[1].active_agent_moved_this_tick == 1
    assert report.frames[2].trip_completed_total == 1
    assert report.summary["final_tick"] == 3
    assert report.summary["final_completed_trips_total"] == 1
    assert report.summary["route_candidate_reuse_total"] >= 1
    assert report.to_dict()["frames"][0]["sampled_link_congestion"]


def test_runtime_diagnostic_html_renderer_is_static_and_contains_svg_review_surface() -> None:
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.runtime_diagnostics import (
        render_runtime_diagnostic_html,
        run_runtime_diagnostic_rollout,
    )

    report = run_runtime_diagnostic_rollout(
        _diagnostic_state(),
        key_from_seed(321),
        controls=(SimulationControl(), SimulationControl()),
        max_link_samples=2,
    )
    html = render_runtime_diagnostic_html(report)

    assert html.startswith("<!doctype html>")
    assert "Runtime Spine Diagnostic" in html
    assert "SMOKE DIAGNOSTIC" in html
    assert "data-runtime-diagnostic" in html
    assert "<svg" in html
    assert "tick 1" in html
    assert "route refresh" in html
    assert "moved" in html
    assert "rerouted" in html
    assert "cooldown" in html
    assert "path size" in html


def test_runtime_diagnostic_summary_accumulates_reroute_counters() -> None:
    from metroflow.sim.runtime_diagnostics import (
        RuntimeDiagnosticFrame,
        RuntimeDiagnosticReport,
        render_runtime_diagnostic_html,
    )

    report = RuntimeDiagnosticReport(
        scenario_id="reroute-summary",
        label="REROUTE SUMMARY",
        frames=(
            RuntimeDiagnosticFrame(
                tick_index=1,
                active_agent_count=1,
                queue_vehicles_total=2.0,
                outflow_vehicles_total=1.0,
                trip_completed_total=0,
                trip_failed_total=0,
                active_agent_moved_this_tick=0,
                active_agent_rerouted_this_tick=2,
                active_agent_reroute_cooldown_this_tick=1,
                route_candidate_refresh_total=1,
                route_candidate_reuse_total=0,
                dynamic_potential_recompute_total=1,
                dynamic_potential_cache_hits_total=0,
            ),
            RuntimeDiagnosticFrame(
                tick_index=2,
                active_agent_count=1,
                queue_vehicles_total=1.0,
                outflow_vehicles_total=1.0,
                trip_completed_total=0,
                trip_failed_total=0,
                active_agent_moved_this_tick=1,
                active_agent_rerouted_this_tick=0,
                active_agent_reroute_cooldown_this_tick=3,
                route_candidate_refresh_total=1,
                route_candidate_reuse_total=1,
                dynamic_potential_recompute_total=1,
                dynamic_potential_cache_hits_total=0,
            ),
        ),
        summary={},
    )
    html = render_runtime_diagnostic_html(report)

    assert report.summary["active_agent_rerouted_total"] == 2
    assert report.summary["active_agent_reroute_cooldown_total"] == 4
    assert "rerouted total" in html
    assert "<strong>2</strong>" in html
