from __future__ import annotations


def _build_bundle(seed: int = 44):
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.init import build_initial_simulation_state

    return build_initial_simulation_state(
        config=SimulationConfig(population_target=100_000, active_agent_capacity=64),
        scenario_seed=seed,
        eager_trip_generation=False,
    )


def test_static_map_builds_one_width_aware_road_per_physical_centerline() -> None:
    from metroflow.ui.static_map import build_static_city_map_artifact

    bundle = _build_bundle()
    artifact = build_static_city_map_artifact(bundle.state)

    assert len(artifact.roads) == len(bundle.city_topology.road_geometry.centerlines)
    assert len({road["geometry_id"] for road in artifact.roads}) == len(artifact.roads)
    assert all(len(road["polyline"]) >= 2 for road in artifact.roads)
    assert all(road["section_width_m"] > 0.0 for road in artifact.roads)
    assert all(road["render_width_px"] > 0.0 for road in artifact.roads)
    assert any(road["has_median"] for road in artifact.roads)
    assert any(road["has_shoulder"] for road in artifact.roads)
    assert any(road["ramp"] for road in artifact.roads)
    assert any(road["connectivity_repair"] for road in artifact.roads)
    assert artifact.metadata["road_geometry_fingerprint"]
    assert artifact.metadata["road_section_fingerprint"]


def test_static_map_svg_uses_curved_physical_paths_without_directed_duplicates() -> None:
    from metroflow.map.road_geometry import RoadCenterline, RoadGeometryCatalog
    from metroflow.ui.static_map import build_static_city_map_artifact

    bundle = _build_bundle(seed=12)
    city = bundle.city_topology
    first = city.road_geometry.centerlines[0]
    start = first.points_m[0]
    end = first.points_m[-1]
    midpoint = ((start[0] + end[0]) * 0.5 + 23.0, (start[1] + end[1]) * 0.5 + 31.0)
    curved = RoadCenterline(
        geometry_id=first.geometry_id,
        points_m=(start, midpoint, end),
        source=first.source,
        source_ref=first.source_ref,
        layer=first.layer,
        corridor_id=first.corridor_id,
    )
    city.road_geometry = RoadGeometryCatalog(
        centerlines=(curved, *city.road_geometry.centerlines[1:]),
        assignments=city.road_geometry.assignments,
    )
    city.metadata["road_geometry_fingerprint"] = city.road_geometry.fingerprint

    artifact = build_static_city_map_artifact(bundle.state)
    html = artifact.to_html()
    curved_payload = next(
        road for road in artifact.roads if road["geometry_id"] == first.geometry_id
    )

    assert len(curved_payload["polyline"]) == 3
    assert artifact.bounds["scale_px_per_m"] > 0.0
    assert all(
        40.0 <= coordinate <= limit
        for point in curved_payload["polyline"]
        for coordinate, limit in zip(point, (1040.0, 720.0), strict=True)
    )
    assert html.count('class="road-ribbon ') == len(artifact.roads)
    assert f'data-geometry-id="{first.geometry_id}"' in html
    assert ' d="M ' in html
    assert 'stroke-width="' in html


def test_static_map_visible_layers_are_explicit_and_fail_closed() -> None:
    import pytest

    from metroflow.ui.static_map import build_static_city_map_artifact

    bundle = _build_bundle(seed=9)
    roads_only = build_static_city_map_artifact(
        bundle.state,
        visible_layers=("roads",),
    )
    html = roads_only.to_html()

    assert roads_only.visible_layers == ("roads",)
    assert 'data-visible-layers="roads"' in html
    assert 'class="road-ribbon ' in html
    assert 'class="zone ' not in html
    assert 'class="poi ' not in html
    assert 'data-layer-toggle="zones" aria-pressed="false" disabled' in html

    with pytest.raises(ValueError, match="unknown static map layer"):
        build_static_city_map_artifact(bundle.state, visible_layers=("traffic",))


def test_static_map_preserves_selected_backend_metadata() -> None:
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.init import build_initial_simulation_state
    from metroflow.ui.static_map import build_static_city_map_artifact

    bundle = build_initial_simulation_state(
        config=SimulationConfig(
            population_target=1,
            edge_backend="baseline",
            flow_backend="auto",
            routing_backend="baseline",
            agent_backend="auto",
        ),
        scenario_seed=5,
        eager_trip_generation=False,
    )
    metadata = build_static_city_map_artifact(bundle.state).metadata

    assert metadata["edge_backend"] == "baseline"
    assert metadata["flow_backend"] == "auto"
    assert metadata["routing_backend"] == "baseline"
    assert metadata["agent_backend"] == "auto"


def test_static_map_fails_on_stale_geometry_fingerprint() -> None:
    import pytest

    from metroflow.ui.static_map import build_static_city_map_artifact

    bundle = _build_bundle(seed=8)
    bundle.city_topology.metadata["road_geometry_fingerprint"] = "stale"

    with pytest.raises(ValueError, match="does not match"):
        build_static_city_map_artifact(bundle.state)


def test_static_map_derives_fingerprints_for_legacy_topology_adapter() -> None:
    from metroflow.city.generator_v2 import PreviewCityTopology
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.state import (
        SimulationDynamicRefs,
        SimulationState,
        SimulationStaticRefs,
    )
    from metroflow.ui.static_map import build_static_city_map_artifact

    topology = PreviewCityTopology(
        nodes=(Node(1, x=0.0, y=0.0), Node(2, x=20.0, y=0.0)),
        links=(
            RoadLink(1, 1, 2, RoadClass.LOCAL, 20.0, 5.0, 4.0),
            RoadLink(2, 2, 1, RoadClass.LOCAL, 20.0, 5.0, 4.0),
        ),
    )
    state = SimulationState(
        config=SimulationConfig(population_target=1),
        static=SimulationStaticRefs(
            scenario_id="legacy-adapter",
            city_topology=topology,
        ),
        dynamic=SimulationDynamicRefs(),
    )

    artifact = build_static_city_map_artifact(state)

    assert len(artifact.roads) == 1
    assert artifact.metadata["road_geometry_fingerprint"]
    assert artifact.metadata["road_section_fingerprint"]


def test_direct_artifact_construction_synthesizes_legacy_road_payload() -> None:
    from metroflow.ui.static_map import StaticCityMapArtifact

    link = {
        "link_id": 1,
        "src_node_id": 1,
        "dst_node_id": 2,
        "road_class": "local",
        "lanes": 1,
        "polyline": ((40.0, 40.0), (100.0, 40.0)),
    }
    artifact = StaticCityMapArtifact(
        "legacy",
        "v1",
        {"min_x": 0.0, "min_y": 0.0, "width": 100.0, "height": 100.0},
        (),
        (link,),
    )

    assert len(artifact.roads) == 1
    assert artifact.roads[0]["source"] == "legacy_link_fallback"
    assert 'class="road-ribbon ' in artifact.to_html()


def test_largest_component_focus_excludes_distant_centerline_bounds() -> None:
    from metroflow.city.generator_v2 import PreviewCityTopology
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.state import (
        SimulationDynamicRefs,
        SimulationState,
        SimulationStaticRefs,
    )
    from metroflow.ui.static_map import build_static_city_map_artifact

    topology = PreviewCityTopology(
        nodes=(
            Node(1, x=0.0, y=0.0),
            Node(2, x=20.0, y=0.0),
            Node(3, x=1000.0, y=0.0),
            Node(4, x=1020.0, y=0.0),
        ),
        links=(
            RoadLink(1, 1, 2, RoadClass.LOCAL, 20.0, 5.0, 4.0),
            RoadLink(2, 2, 1, RoadClass.LOCAL, 20.0, 5.0, 4.0),
            RoadLink(3, 3, 4, RoadClass.LOCAL, 20.0, 5.0, 4.0),
            RoadLink(4, 4, 3, RoadClass.LOCAL, 20.0, 5.0, 4.0),
        ),
    )
    state = SimulationState(
        config=SimulationConfig(population_target=1),
        static=SimulationStaticRefs(
            scenario_id="disconnected",
            city_topology=topology,
        ),
        dynamic=SimulationDynamicRefs(),
    )

    full = build_static_city_map_artifact(state)
    focused = build_static_city_map_artifact(
        state,
        focus_largest_component=True,
    )

    assert focused.bounds["width"] < full.bounds["width"]
    assert focused.metadata["map_focus"] == "largest_component"
