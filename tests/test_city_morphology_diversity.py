from __future__ import annotations

import math
import json
import subprocess
import sys

import pytest


def test_empirical_reference_corpus_preserves_source_and_observed_values() -> None:
    from metroflow.city.morphology_reference import (
        MORPHOLOGY_ARCHETYPES,
        empirical_street_network_references,
        get_morphology_archetype,
    )

    references = {item.city: item for item in empirical_street_network_references()}

    assert references["Chicago"].orientation_order == 0.899
    assert references["Chicago"].four_way_share == 0.507
    assert references["Hong Kong"].circuity == 1.137
    assert references["Seoul"].orientation_entropy == 3.573
    assert all(item.evidence_status == "reference_only" for item in references.values())
    assert all("10.1007/s41109-019-0189-1" in item.source_url for item in references.values())
    assert all(
        set(get_morphology_archetype(style_id).empirical_reference_cities) <= set(references)
        for style_id in MORPHOLOGY_ARCHETYPES
    )


def test_street_network_morphometrics_measure_physical_grid_without_directed_duplication() -> None:
    from metroflow.city.generator_v2 import PreviewCityTopology
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.city.morphology_metrics import compute_street_network_morphometrics
    from metroflow.map.road_geometry import build_endpoint_geometry_catalog

    nodes = (
        Node(0, x=0.0, y=0.0),
        Node(1, x=100.0, y=0.0),
        Node(2, x=100.0, y=100.0),
        Node(3, x=0.0, y=100.0),
    )
    endpoint_pairs = ((0, 1), (1, 2), (2, 3), (3, 0))
    links = tuple(
        RoadLink(
            link_id=index * 2 + direction,
            src_node_id=pair[direction],
            dst_node_id=pair[1 - direction],
            road_class=RoadClass.LOCAL,
            length_m=100.0,
            free_flow_speed_mps=10.0,
            capacity_veh_per_tick=4.0,
            physical_road_id=index,
        )
        for index, pair in enumerate(endpoint_pairs)
        for direction in (0, 1)
    )
    geometry = build_endpoint_geometry_catalog(nodes=nodes, links=links)
    topology = PreviewCityTopology(nodes=nodes, links=links, road_geometry=geometry)

    metrics = compute_street_network_morphometrics(topology)

    assert metrics.physical_segment_count == 4
    assert math.isclose(metrics.orientation_entropy, math.log(4.0))
    assert math.isclose(metrics.orientation_order, 1.0)
    assert math.isclose(metrics.circuity, 1.0)
    assert math.isclose(metrics.mean_node_degree, 2.0)
    assert metrics.dead_end_share == 0.0
    assert metrics.four_way_share == 0.0


@pytest.mark.parametrize(
    "style_id",
    (
        "grid_core",
        "polycentric_tod",
        "river_constrained",
        "superblock_mixed",
        "organic",
    ),
)
def test_explicit_morphology_styles_pass_planar_city_contract(style_id: str) -> None:
    from metroflow.city.generator_v2 import GeneratorV2

    topology = GeneratorV2().generate_preview_topology(
        {
            "scenario_id": "synthetic_smoke",
            "seed": 17,
            "preview_mode": "sidecar_local_fabric_planar",
            "style_id": style_id,
        }
    )

    assert topology.metadata["style_id"] == style_id
    assert topology.metadata["morphology_street_pattern"] != "radial_ring"
    assert topology.metadata["direct_downtown_spoke_share"] == 0.0
    assert topology.metadata["city_map_validation_status"] == "passed"
    assert topology.metadata["proper_intersection_count_after_planarization"] == 0
    assert topology.metadata["street_network_morphometrics_status"] == (
        "diagnostic_not_city_replication"
    )


def test_river_constrained_bridge_links_cross_the_barrier_transversely() -> None:
    from metroflow.city.generator_v2 import GeneratorV2
    from metroflow.city.graph import RoadClass

    topology = GeneratorV2().generate_preview_topology(
        {
            "scenario_id": "synthetic_smoke",
            "seed": 17,
            "preview_mode": "sidecar_local_fabric",
            "style_id": "river_constrained",
        }
    )
    node_by_id = {node.node_id: node for node in topology.nodes}
    bridge_links = tuple(
        link for link in topology.links if link.road_class == RoadClass.BRIDGE
    )

    assert len(topology.bridge_crossings) == 3
    assert bridge_links
    assert all(
        abs(node_by_id[link.dst_node_id].y - node_by_id[link.src_node_id].y)
        > abs(node_by_id[link.dst_node_id].x - node_by_id[link.src_node_id].x)
        for link in bridge_links
    )


def test_morphology_styles_produce_distinct_deterministic_signatures() -> None:
    from metroflow.city.generator_v2 import GeneratorV2
    from metroflow.city.morphology_reference import MORPHOLOGY_ARCHETYPES

    signatures: dict[str, tuple[float, float, float]] = {}
    fingerprints: dict[str, str] = {}
    for style_id in MORPHOLOGY_ARCHETYPES:
        topology = GeneratorV2().generate_preview_topology(
            {
                "scenario_id": "synthetic_smoke",
                "seed": 29,
                "preview_mode": "sidecar_local_fabric",
                "style_id": style_id,
            }
        )
        metrics = topology.metadata["street_network_morphometrics"]
        signatures[style_id] = (
            round(float(metrics["orientation_order"]), 3),
            round(float(metrics["mean_node_degree"]), 3),
            round(float(metrics["dead_end_share"]), 3),
        )
        fingerprints[style_id] = topology.road_geometry.fingerprint

    repeated = GeneratorV2().generate_preview_topology(
        {
            "scenario_id": "synthetic_smoke",
            "seed": 29,
            "preview_mode": "sidecar_local_fabric",
            "style_id": "superblock_mixed",
        }
    )

    assert len(set(signatures.values())) >= 5
    assert signatures["grid_core"][0] > signatures["organic"][0] + 0.50
    assert len(set(fingerprints.values())) == len(MORPHOLOGY_ARCHETYPES)
    assert repeated.road_geometry.fingerprint == fingerprints["superblock_mixed"]


def test_city_generation_config_propagates_explicit_style_and_preserves_auto_default() -> None:
    from metroflow.sim.config import CityGenerationConfig, SimulationConfig
    from metroflow.sim.init import build_initial_simulation_state

    assert CityGenerationConfig().morphology_style_id == "auto"
    explicit = build_initial_simulation_state(
        config=SimulationConfig(population_target=500, active_agent_capacity=16),
        city_config=CityGenerationConfig(
            topology_mode="sidecar_local_fabric",
            morphology_style_id="organic",
        ),
        scenario_seed=31,
    )

    assert explicit.city_topology.metadata["style_id"] == "organic"
    assert explicit.state.metadata["city_morphology_style_id"] == "organic"
    assert explicit.state.static.metadata["city_morphology_style_id"] == "organic"
    with pytest.raises(ValueError, match="morphology style_id"):
        CityGenerationConfig(morphology_style_id="imaginary_city")
    with pytest.raises(ValueError, match="requires sidecar_local_fabric"):
        CityGenerationConfig(morphology_style_id="organic")


def test_standard_generator_rejects_style_names_it_cannot_implement() -> None:
    from metroflow.city.generator_v2 import GeneratorV2

    with pytest.raises(ValueError, match="standard preview_mode supports only"):
        GeneratorV2().generate_preview_topology(
            {
                "scenario_id": "synthetic_smoke",
                "seed": 3,
                "preview_mode": "standard",
                "style_id": "organic",
            }
        )


def test_morphology_contract_import_does_not_load_accelerator_modules() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import metroflow.city.morphology_reference; "
                "import metroflow.city.morphology_metrics; "
                "assert 'jax' not in sys.modules; "
                "assert 'torch' not in sys.modules; "
                "assert '_metroflow_rust' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_morphology_atlas_writes_review_bundle_without_raw_osm(tmp_path) -> None:
    from metroflow.ui.morphology_atlas import write_city_morphology_atlas

    paths = write_city_morphology_atlas(
        tmp_path,
        seed=5,
        topology_mode="sidecar_local_fabric",
        style_ids=("grid_core", "organic"),
    )
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    index = paths["index"].read_text(encoding="utf-8")

    assert manifest["artifact_format_version"] == "city_morphology_atlas_v1"
    assert manifest["raw_osm_data_included"] is False
    assert manifest["html_retention"] == (
        "reproducible_local_output_not_required_in_version_control"
    )
    assert [item["style_id"] for item in manifest["styles"]] == ["grid_core", "organic"]
    assert "Diagnostic comparison only" in index
    assert paths["grid_core_html"].is_file()
    assert paths["organic_html"].is_file()
