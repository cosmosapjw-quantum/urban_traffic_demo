from __future__ import annotations

import pytest


def test_generated_topology_has_complete_geometry_catalog() -> None:
    from metroflow.city.generator_v2 import GeneratorV2

    topology = GeneratorV2().generate_preview_topology(
        {"scenario_id": "synthetic_smoke", "seed": 7}
    )

    assert topology.road_geometry is not None
    assert len(topology.road_geometry.assignments) == len(topology.links)
    assert topology.metadata["road_geometry_fingerprint"] == (
        topology.road_geometry.fingerprint
    )
    assert topology.metadata["physical_centerline_count"] == len(
        topology.road_geometry.centerlines
    )
    assert topology.metadata["centerline_intersection_audit_status"] == (
        "diagnostic_not_validation"
    )
    assert topology.metadata["unmodeled_centerline_intersection_count"] >= 0
    assert topology.validate(require_weak_connectivity=True).ok


def test_generated_physical_road_ids_disambiguate_parallel_links() -> None:
    from metroflow.city.generator_v2 import GeneratorV2

    topology = GeneratorV2().generate_preview_topology(
        {"scenario_id": "synthetic_100k", "seed": 44}
    )
    road_ids = [link.physical_road_id for link in topology.links]

    assert all(road_id is not None for road_id in road_ids)
    for road_id in set(road_ids):
        link_ids = [
            link.link_id for link in topology.links if link.physical_road_id == road_id
        ]
        assert len(link_ids) == 2
        geometry_ids = {
            topology.road_geometry.assignment_for_link(link_id).geometry_id
            for link_id in link_ids
        }
        assert len(geometry_ids) == 1


def test_sidecar_local_fabric_mode_is_explicit_and_connected() -> None:
    from metroflow.city.generator_v2 import GeneratorV2
    from metroflow.sim.config import CityGenerationConfig

    config = CityGenerationConfig(topology_mode="sidecar_local_fabric")
    topology = GeneratorV2().generate_preview_topology(
        {
            "scenario_id": "synthetic_100k",
            "seed": 44,
            "preview_mode": config.topology_mode,
        }
    )

    assert topology.metadata["engine"] == "generator_v2_sidecar_local_fabric"
    assert topology.metadata["weak_component_count_after_repair"] == 1
    assert topology.metadata["connectivity_repair_link_count"] > 0
    assert topology.road_geometry is not None
    assert topology.validate(require_weak_connectivity=True).ok


def test_city_generation_config_rejects_unknown_topology_mode() -> None:
    from metroflow.sim.config import CityGenerationConfig

    with pytest.raises(ValueError, match="topology_mode"):
        CityGenerationConfig(topology_mode="external_magic")


def test_initial_state_propagates_geometry_fingerprint_and_mode() -> None:
    from metroflow.sim.config import CityGenerationConfig, SimulationConfig
    from metroflow.sim.init import build_initial_simulation_state

    bundle = build_initial_simulation_state(
        config=SimulationConfig(population_target=100),
        city_config=CityGenerationConfig(topology_mode="sidecar_local_fabric"),
        scenario_seed=3,
    )
    fingerprint = bundle.city_topology.road_geometry.fingerprint

    assert fingerprint in bundle.state.static.ui_network_geometry_version
    assert bundle.state.metadata["city_topology_mode"] == "sidecar_local_fabric"
    assert bundle.state.metadata["road_geometry_fingerprint"] == fingerprint


def test_project_owned_hierarchy_metadata_replaces_legacy_names() -> None:
    from metroflow.city.gate_reporting import build_active_sidecar_hierarchy_report
    from metroflow.city.generator_v2 import GeneratorV2

    topology = GeneratorV2().generate_preview_topology(
        {
            "scenario_id": "synthetic_smoke",
            "seed": 5,
            "preview_mode": "sidecar_local_fabric",
        }
    )
    report = build_active_sidecar_hierarchy_report(topology=topology)

    assert "road_hierarchy_module_signature" in topology.metadata
    assert "road_hierarchy_module_alignment_ok" in topology.metadata
    assert "road_hierarchy_module_signature" in report
    assert "road_hierarchy_module_alignment_ok" in report
    assert not any(key.startswith("csur_module_") for key in topology.metadata)
    assert not any(key.startswith("csur_module_") for key in report)


@pytest.mark.parametrize(
    ("scenario_id", "mode", "seed"),
    (
        ("synthetic_smoke", "standard", 7),
        ("synthetic_100k", "sidecar_local_fabric", 44),
    ),
)
def test_finalized_topology_is_deterministic(scenario_id, mode, seed) -> None:
    from metroflow.city.generator_v2 import GeneratorV2

    context = {"scenario_id": scenario_id, "seed": seed, "preview_mode": mode}
    first = GeneratorV2().generate_preview_topology(context)
    second = GeneratorV2().generate_preview_topology(context)

    assert first.nodes == second.nodes
    assert first.links == second.links
    assert first.metadata["connectivity_repair_link_ids"] == second.metadata[
        "connectivity_repair_link_ids"
    ]
    assert first.road_geometry.fingerprint == second.road_geometry.fingerprint


def test_connectivity_repair_allocates_independent_physical_road_ids() -> None:
    from metroflow.city.connectivity import repair_weak_connectivity
    from metroflow.city.graph import Node, RoadClass, RoadLink

    nodes = (Node(1, x=0.0), Node(2, x=10.0), Node(3, x=20.0))
    links = (
        RoadLink(
            0,
            1,
            2,
            RoadClass.LOCAL,
            10.0,
            9.0,
            4.0,
            physical_road_id=50,
        ),
        RoadLink(
            1,
            2,
            1,
            RoadClass.LOCAL,
            10.0,
            9.0,
            4.0,
            physical_road_id=50,
        ),
    )

    repaired = repair_weak_connectivity(nodes=nodes, links=links)
    repair_ids = set(repaired.repair_link_ids)
    repair_physical_ids = {
        link.physical_road_id for link in repaired.links if link.link_id in repair_ids
    }

    assert repair_physical_ids == {51}
