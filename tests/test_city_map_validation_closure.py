from __future__ import annotations

import numpy as np
import pytest


def test_explicit_planar_sidecar_passes_without_runtime_default_promotion() -> None:
    from metroflow.map.road_geometry import count_interior_centerline_intersections
    from metroflow.sim.config import CityGenerationConfig, SimulationConfig
    from metroflow.sim.init import build_initial_simulation_state

    assert CityGenerationConfig().topology_mode == "standard"
    bundle = build_initial_simulation_state(
        config=SimulationConfig(population_target=100_000, active_agent_capacity=32),
        city_config=CityGenerationConfig(
            topology_mode="sidecar_local_fabric_planar"
        ),
        scenario_seed=44,
        eager_trip_generation=False,
    )
    topology = bundle.city_topology

    assert topology.metadata["engine"] == "generator_v2_sidecar_local_fabric"
    assert topology.metadata["planarization_status"] == "passed"
    assert topology.metadata["planarization_admission_status"] == (
        "explicit_only_runtime_default_not_promoted"
    )
    assert topology.metadata["proper_intersection_count_before_planarization"] > 0
    assert topology.metadata["proper_intersection_count_after_planarization"] == 0
    assert topology.metadata["city_map_validation_status"] == "passed"
    assert count_interior_centerline_intersections(topology.road_geometry) == 0
    valid_link_ids = {link.link_id for link in topology.links}
    assert set(topology.metadata["connectivity_repair_link_ids"]) <= valid_link_ids
    assert all(
        set(crossing.link_ids) <= valid_link_ids
        for crossing in topology.bridge_crossings
    )


@pytest.mark.parametrize("seed", (41, 42, 43))
def test_runtime_city_validation_passes_deterministic_seed_matrix(seed: int) -> None:
    from metroflow.city.map_validation import validate_city_map_contract
    from metroflow.sim.config import CityGenerationConfig, SimulationConfig
    from metroflow.sim.init import build_initial_simulation_state

    bundle = build_initial_simulation_state(
        config=SimulationConfig(population_target=500, active_agent_capacity=16),
        city_config=CityGenerationConfig(
            topology_mode="sidecar_local_fabric_planar"
        ),
        scenario_seed=seed,
        eager_trip_generation=False,
    )
    report = validate_city_map_contract(
        bundle.city_topology,
        od_sample_count=32,
        seed=seed,
    )

    assert report.ok
    assert report.metrics["weak_component_count"] == 1
    assert report.metrics["proper_intersection_count"] == 0
    assert report.metrics["reachable_od_count"] == 32
    assert report.metrics["sampled_od_count"] == 32
    assert report.metrics["geometry_assignment_count"] == len(bundle.city_topology.links)
    assert report.metrics["section_assignment_count"] == len(bundle.city_topology.links)
    repeated = build_initial_simulation_state(
        config=SimulationConfig(population_target=500, active_agent_capacity=16),
        city_config=CityGenerationConfig(
            topology_mode="sidecar_local_fabric_planar"
        ),
        scenario_seed=seed,
        eager_trip_generation=False,
    ).city_topology
    repeated_report = validate_city_map_contract(
        repeated,
        od_sample_count=32,
        seed=seed,
    )
    assert dict(report.metrics) == dict(repeated_report.metrics)
    assert bundle.city_topology.road_geometry.fingerprint == (
        repeated.road_geometry.fingerprint
    )


def test_legacy_standard_mode_remains_explicit_and_fails_planar_acceptance() -> None:
    from metroflow.city.generator_v2 import GeneratorV2
    from metroflow.city.map_validation import validate_city_map_contract

    topology = GeneratorV2().generate_preview_topology(
        {
            "scenario_id": "synthetic_smoke",
            "seed": 7,
            "preview_mode": "standard",
        }
    )
    report = validate_city_map_contract(topology, od_sample_count=8, seed=7)

    assert not report.ok
    assert "proper_centerline_intersections" in report.failure_codes
    assert topology.metadata["centerline_intersection_audit_status"] == (
        "diagnostic_not_validation"
    )


def test_planarization_preserves_link_and_section_authority() -> None:
    from metroflow.sim.config import CityGenerationConfig, SimulationConfig
    from metroflow.sim.init import build_initial_simulation_state

    bundle = build_initial_simulation_state(
        config=SimulationConfig(population_target=500, active_agent_capacity=16),
        city_config=CityGenerationConfig(
            topology_mode="sidecar_local_fabric_planar"
        ),
        scenario_seed=19,
        eager_trip_generation=False,
    )
    topology = bundle.city_topology

    assert len(topology.road_geometry.assignments) == len(topology.links)
    assert len(topology.road_sections.assignments) == len(topology.links)
    for link in topology.links:
        assignment = topology.road_sections.assignment_for_link(link.link_id)
        assert assignment.lane_count == link.lanes
        assert assignment.capacity_veh_per_tick == link.capacity_veh_per_tick
    assert topology.metadata["road_geometry_fingerprint"] == (
        topology.road_geometry.fingerprint
    )
    assert topology.metadata["road_section_fingerprint"] == (
        topology.road_sections.fingerprint
    )


def test_planar_city_initialization_remains_replay_deterministic() -> None:
    from metroflow.sim.config import CityGenerationConfig, SimulationConfig
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.init import build_initial_simulation_state
    from metroflow.sim.replay import (
        RuntimeReplayRequest,
        make_runtime_replay_boundary,
        replay_simulation_sequence,
    )
    from metroflow.sim.rng import key_from_seed

    config = SimulationConfig(population_target=500, active_agent_capacity=32)
    city_config = CityGenerationConfig(
        topology_mode="sidecar_local_fabric_planar"
    )
    first = build_initial_simulation_state(
        config=config,
        city_config=city_config,
        scenario_seed=23,
        eager_trip_generation=True,
    ).state
    second = build_initial_simulation_state(
        config=SimulationConfig(population_target=500, active_agent_capacity=32),
        city_config=CityGenerationConfig(
            topology_mode="sidecar_local_fabric_planar"
        ),
        scenario_seed=23,
        eager_trip_generation=True,
    ).state
    controls = (SimulationControl(), SimulationControl())
    first_result = replay_simulation_sequence(
        RuntimeReplayRequest(
            name="replay_planar_city_first",
            initial_state=first,
            declared_boundary=make_runtime_replay_boundary(first),
            controls=controls,
            rng_key=key_from_seed(23),
            num_steps=2,
        )
    )
    second_result = replay_simulation_sequence(
        RuntimeReplayRequest(
            name="replay_planar_city_second",
            initial_state=second,
            declared_boundary=make_runtime_replay_boundary(second),
            controls=controls,
            rng_key=key_from_seed(23),
            num_steps=2,
        )
    )

    assert first_result.initial_boundary == second_result.initial_boundary
    assert first_result.cache_fingerprint == second_result.cache_fingerprint
    assert tuple(item.as_replay_dict() for item in first_result.telemetry_log) == tuple(
        item.as_replay_dict() for item in second_result.telemetry_log
    )
    assert np.array_equal(first_result.final_rng_key, second_result.final_rng_key)
    first_link_state = first_result.final_state.dynamic.flow_link_state
    second_link_state = second_result.final_state.dynamic.flow_link_state
    for field_name in (
        "queue_vehicles",
        "inflow_vehicles",
        "outflow_vehicles",
        "travel_time_cost",
        "capacity_veh_per_tick",
        "incident_capacity_multiplier",
        "capacity_violation_flags",
    ):
        assert np.array_equal(
            getattr(first_link_state, field_name),
            getattr(second_link_state, field_name),
        )
    first_node_state = first_result.final_state.dynamic.flow_node_state
    second_node_state = second_result.final_state.dynamic.flow_node_state
    for field_name in (
        "turn_from_link_index",
        "turn_to_link_index",
        "turn_demand",
        "turn_supply",
        "turn_flow",
        "signal_phase_index",
        "signal_phase_timer",
    ):
        assert np.array_equal(
            getattr(first_node_state, field_name),
            getattr(second_node_state, field_name),
        )


def test_replay_cache_fingerprint_excludes_only_timing_diagnostics() -> None:
    from metroflow.sim.routing_runtime import runtime_route_cache_fingerprint

    first = runtime_route_cache_fingerprint(
        stats={"route_candidate_refresh_total": 3, "route_candidate_refresh_seconds_total": 1.0}
    )
    second = runtime_route_cache_fingerprint(
        stats={"route_candidate_refresh_total": 3, "route_candidate_refresh_seconds_total": 9.0}
    )
    changed = runtime_route_cache_fingerprint(
        stats={"route_candidate_refresh_total": 4, "route_candidate_refresh_seconds_total": 1.0}
    )

    assert first == second
    assert first != changed


def test_city_validation_rejects_semantically_swapped_section_profiles() -> None:
    from dataclasses import replace

    from metroflow.city.generator_v2 import PreviewCityTopology
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.city.map_validation import validate_city_map_contract
    from metroflow.map.node_compiler import compile_node_interfaces
    from metroflow.map.road_geometry import build_endpoint_geometry_catalog
    from metroflow.map.section_compiler import RoadSectionCatalog, compile_road_sections

    nodes = (
        Node(0, x=0.0, y=0.0),
        Node(1, x=10.0, y=0.0),
        Node(2, x=20.0, y=0.0),
    )
    links = (
        RoadLink(0, 0, 1, RoadClass.LOCAL, 10.0, 9.0, 4.0, physical_road_id=0),
        RoadLink(1, 1, 0, RoadClass.LOCAL, 10.0, 9.0, 4.0, physical_road_id=0),
        RoadLink(2, 1, 2, RoadClass.ARTERIAL, 10.0, 15.0, 4.0, physical_road_id=1),
        RoadLink(3, 2, 1, RoadClass.ARTERIAL, 10.0, 15.0, 4.0, physical_road_id=1),
    )
    geometry = build_endpoint_geometry_catalog(nodes=nodes, links=links)
    sections = compile_road_sections(links=links, road_geometry=geometry)
    local_profile = sections.assignment_for_link(0).profile_id
    arterial_profile = sections.assignment_for_link(2).profile_id
    corrupted = RoadSectionCatalog(
        profiles=sections.profiles,
        assignments=tuple(
            replace(
                assignment,
                profile_id=(
                    arterial_profile
                    if assignment.profile_id == local_profile
                    else local_profile
                ),
            )
            for assignment in sections.assignments
        ),
    )
    interfaces = compile_node_interfaces(
        nodes=nodes,
        links=links,
        road_geometry=geometry,
    )
    topology = PreviewCityTopology(
        nodes=nodes,
        links=links,
        road_geometry=geometry,
        road_sections=corrupted,
        node_interfaces=interfaces,
        metadata={
            "road_geometry_fingerprint": geometry.fingerprint,
            "road_section_fingerprint": corrupted.fingerprint,
            "node_interface_fingerprint": interfaces.fingerprint,
        },
    )

    report = validate_city_map_contract(topology, od_sample_count=8, seed=3)

    assert not report.ok
    assert "section_semantic_catalog" in report.failure_codes
