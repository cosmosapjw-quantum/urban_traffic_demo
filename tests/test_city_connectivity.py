from __future__ import annotations


def test_weak_connectivity_report_finds_disconnected_components() -> None:
    from metroflow.city.connectivity import analyze_weak_connectivity
    from metroflow.city.graph import Node, RoadClass, RoadLink

    nodes = (
        Node(1, x=0.0, y=0.0),
        Node(2, x=10.0, y=0.0),
        Node(3, x=100.0, y=0.0),
    )
    links = (RoadLink(7, 1, 2, RoadClass.LOCAL, 10.0, 10.0, 4.0),)

    report = analyze_weak_connectivity(nodes=nodes, links=links)

    assert report.component_count == 2
    assert report.component_sizes == (2, 1)
    assert report.node_component_id_by_node_id == {1: 0, 2: 0, 3: 1}


def test_topology_validator_can_fail_closed_on_disconnected_graph() -> None:
    from metroflow.city.graph import Node, RoadClass, RoadLink, validate_road_network_topology

    nodes = (
        Node(1, x=0.0, y=0.0),
        Node(2, x=10.0, y=0.0),
        Node(3, x=100.0, y=0.0),
    )
    links = (RoadLink(7, 1, 2, RoadClass.LOCAL, 10.0, 10.0, 4.0),)

    permissive = validate_road_network_topology(nodes=nodes, links=links)
    strict = validate_road_network_topology(
        nodes=nodes,
        links=links,
        require_weak_connectivity=True,
    )

    assert permissive.ok
    assert not strict.ok
    assert strict.issues[0].code == "weak_connectivity_missing"
    assert strict.issues[0].details["component_sizes"] == (2, 1)


def test_repair_weak_connectivity_adds_deterministic_collector_stitches() -> None:
    from metroflow.city.connectivity import repair_weak_connectivity
    from metroflow.city.graph import Node, RoadClass, RoadLink

    nodes = (
        Node(10, x=0.0, y=0.0),
        Node(11, x=10.0, y=0.0),
        Node(12, x=100.0, y=0.0),
        Node(13, x=-50.0, y=0.0),
    )
    links = (RoadLink(20, 10, 11, RoadClass.LOCAL, 10.0, 10.0, 4.0),)

    result = repair_weak_connectivity(nodes=nodes, links=links)

    assert result.before.component_sizes == (2, 1, 1)
    assert result.after.component_sizes == (4,)
    assert result.repair_link_ids == (21, 22, 23, 24)
    assert [link.link_id for link in result.links[-4:]] == [21, 22, 23, 24]
    assert {link.road_class for link in result.links[-4:]} == {RoadClass.COLLECTOR}
    assert result.metadata == {
        "weak_component_count_before_repair": 3,
        "weak_component_sizes_before_repair": (2, 1, 1),
        "connectivity_repair_link_count": 4,
        "connectivity_repair_link_ids": (21, 22, 23, 24),
        "weak_component_count_after_repair": 1,
        "weak_component_sizes_after_repair": (4,),
    }


def test_seed_44_generated_topology_is_repaired_before_runtime_acceptance() -> None:
    from metroflow.city.connectivity import analyze_weak_connectivity
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.init import build_initial_simulation_state

    bundle = build_initial_simulation_state(
        config=SimulationConfig(population_target=100_000),
        scenario_seed=44,
        eager_trip_generation=False,
    )

    report = analyze_weak_connectivity(
        nodes=bundle.city_topology.nodes,
        links=bundle.city_topology.links,
    )

    assert report.component_sizes == (1128,)
    assert bundle.city_topology.metadata["weak_component_sizes_before_repair"] == (
        1121,
        3,
        3,
        1,
    )
    assert bundle.city_topology.metadata["weak_component_count_after_repair"] == 1
    assert bundle.city_topology.metadata["connectivity_repair_link_count"] == 6
