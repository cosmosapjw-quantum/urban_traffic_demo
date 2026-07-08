from __future__ import annotations


def test_static_city_map_artifact_renders_generated_topology_layers(tmp_path) -> None:
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.init import build_initial_simulation_state
    from metroflow.ui.static_map import build_static_city_map_artifact, write_static_city_map_html

    bundle = build_initial_simulation_state(
        config=SimulationConfig(population_target=100_000, active_agent_capacity=64),
        scenario_seed=44,
        eager_trip_generation=False,
    )

    artifact = build_static_city_map_artifact(bundle.state)
    focused_artifact = build_static_city_map_artifact(
        bundle.state,
        focus_largest_component=True,
    )
    payload = artifact.to_dict()
    html = artifact.to_html()
    out_path = write_static_city_map_html(artifact, tmp_path / "city-map.html")
    repair_links = [link for link in payload["links"] if link["connectivity_repair"]]

    assert payload["scenario_id"] == "synthetic-44"
    assert payload["node_count"] == len(bundle.city_topology.nodes)
    assert payload["link_count"] == len(bundle.city_topology.links)
    assert payload["zone_count"] == len(bundle.zoning.zones)
    assert payload["poi_count"] == len(bundle.zoning.pois)
    assert payload["bounds"]["width"] > 0.0
    assert payload["bounds"]["height"] > 0.0
    assert payload["road_class_counts"]
    assert payload["zone_type_counts"]
    assert payload["metadata"]["connectivity_repair_link_count"] == 6
    assert focused_artifact.metadata["map_focus"] == "largest_component"
    assert len(repair_links) == 6
    assert {link["component_id"] for link in payload["links"]} == {0}
    assert any(link["bridge_group_id"] is not None for link in payload["links"])
    assert "<!doctype html>" in html
    assert "<svg" in html
    assert "data-static-city-map" in html
    assert "metroflow-static-city-map" in html
    assert "road-class" in html
    assert "zone-layer" in html
    assert "poi-layer" in html
    assert "repair-link" in html
    assert "data-bridge-group-id" in html
    assert ">ramp<" in html
    assert "SMOKE REVIEW ARTIFACT" in html
    assert out_path.read_text(encoding="utf-8") == html


def test_static_city_map_artifact_fails_closed_without_city_topology() -> None:
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.state import SimulationDynamicRefs, SimulationState, SimulationStaticRefs
    from metroflow.ui.static_map import build_static_city_map_artifact

    state = SimulationState(
        config=SimulationConfig(population_target=1),
        static=SimulationStaticRefs(scenario_id="missing-city"),
        dynamic=SimulationDynamicRefs(),
    )

    try:
        build_static_city_map_artifact(state)
    except ValueError as exc:
        assert "city_topology" in str(exc)
    else:
        raise AssertionError("missing city_topology should fail closed")


def test_static_city_map_artifact_fails_closed_for_missing_link_endpoint() -> None:
    from metroflow.city.generator_v2 import PreviewCityTopology
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.state import SimulationDynamicRefs, SimulationState, SimulationStaticRefs
    from metroflow.ui.static_map import build_static_city_map_artifact

    topology = PreviewCityTopology(
        nodes=(Node(1, x=0.0, y=0.0),),
        links=(RoadLink(9, 1, 2, RoadClass.LOCAL, 100.0, 10.0, 4.0),),
    )
    state = SimulationState(
        config=SimulationConfig(population_target=1),
        static=SimulationStaticRefs(scenario_id="broken-city", city_topology=topology),
        dynamic=SimulationDynamicRefs(),
    )

    try:
        build_static_city_map_artifact(state)
    except ValueError as exc:
        assert "link 9" in str(exc)
        assert "missing node" in str(exc)
    else:
        raise AssertionError("missing link endpoint should fail closed")
