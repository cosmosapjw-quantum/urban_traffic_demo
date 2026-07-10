from __future__ import annotations

import json
import math
import subprocess
import sys
from dataclasses import replace

import pytest


def _topology_from_edges(
    edges: tuple[tuple[int, int, str], ...],
    *,
    coordinates: tuple[tuple[float, float], ...],
    district_envelopes: tuple[tuple[tuple[float, float], ...], ...] = (),
):
    from metroflow.city.generator_v2 import PreviewCityTopology
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.map.road_geometry import build_endpoint_geometry_catalog

    nodes = tuple(Node(index, x=x, y=y) for index, (x, y) in enumerate(coordinates))
    links = tuple(
        RoadLink(
            link_id=edge_index * 2 + direction,
            src_node_id=(left, right)[direction],
            dst_node_id=(right, left)[direction],
            road_class=RoadClass(road_class),
            length_m=math.dist(coordinates[left], coordinates[right]),
            free_flow_speed_mps=10.0,
            capacity_veh_per_tick=4.0,
            physical_road_id=edge_index,
        )
        for edge_index, (left, right, road_class) in enumerate(edges)
        for direction in (0, 1)
    )
    geometry = build_endpoint_geometry_catalog(nodes=nodes, links=links)
    return PreviewCityTopology(
        nodes=nodes,
        links=links,
        road_geometry=geometry,
        metadata={"district_envelopes": district_envelopes},
    )


def test_quality_metrics_distinguish_cycle_from_tree_and_deduplicate_directions() -> None:
    from metroflow.city.morphology_quality import compute_morphology_quality_metrics

    coordinates = ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0))
    cycle = _topology_from_edges(
        (
            (0, 1, "local"),
            (1, 2, "local"),
            (2, 3, "local"),
            (3, 0, "local"),
        ),
        coordinates=coordinates,
    )
    tree = _topology_from_edges(
        ((0, 1, "local"), (1, 2, "collector"), (2, 3, "local")),
        coordinates=coordinates,
    )

    cycle_metrics = compute_morphology_quality_metrics(cycle)
    tree_metrics = compute_morphology_quality_metrics(tree)

    assert cycle_metrics.physical_road_length_m == 400.0
    assert cycle_metrics.convex_hull_area_m2 == 10_000.0
    assert cycle_metrics.street_density_km_per_km2 == 40.0
    assert cycle_metrics.block_continuity == 1.0
    assert cycle_metrics.bridge_length_share == 0.0
    assert tree_metrics.block_continuity == 0.0
    assert tree_metrics.bridge_length_share == 1.0
    assert math.isclose(tree_metrics.connector_to_local_length_ratio, 0.5)


def test_quality_metrics_report_degree_mix_and_district_coverage() -> None:
    from metroflow.city.morphology_quality import compute_morphology_quality_metrics

    envelope = ((-10.0, -10.0), (110.0, -10.0), (110.0, 110.0), (-10.0, 110.0), (-10.0, -10.0))
    topology = _topology_from_edges(
        (
            (0, 1, "local"),
            (1, 2, "local"),
            (2, 3, "local"),
            (3, 0, "local"),
        ),
        coordinates=((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)),
        district_envelopes=(envelope,),
    )

    metrics = compute_morphology_quality_metrics(topology)

    assert metrics.degree_one_share == 0.0
    assert metrics.degree_two_share == 1.0
    assert metrics.degree_three_share == 0.0
    assert metrics.degree_four_share == 0.0
    assert metrics.degree_five_plus_share == 0.0
    assert metrics.district_quadrant_presence_share == 1.0
    assert metrics.weak_component_count == 1
    assert metrics.district_count == 1


def test_block_continuity_handles_long_chain_without_recursive_dfs() -> None:
    from metroflow.city.morphology_quality import compute_morphology_quality_metrics

    coordinates = tuple((float(index), float(index % 2)) for index in range(1_205))
    topology = _topology_from_edges(
        tuple((index, index + 1, "local") for index in range(len(coordinates) - 1)),
        coordinates=coordinates,
    )

    metrics = compute_morphology_quality_metrics(topology)

    assert metrics.block_continuity == 0.0
    assert metrics.bridge_length_share == 1.0


def test_global_street_cell_presence_separates_lattice_from_precinct_islands() -> None:
    from metroflow.city.morphology_quality import (
        compute_morphology_quality_metrics,
        evaluate_morphology_quality_gate,
    )

    def lattice(
        *,
        origins: tuple[tuple[float, float], ...],
        width: float,
        grid_size: int,
    ) -> tuple[tuple[tuple[float, float], ...], tuple[tuple[int, int, str], ...]]:
        coordinates: list[tuple[float, float]] = []
        edges: list[tuple[int, int, str]] = []
        for origin_x, origin_y in origins:
            first_node = len(coordinates)
            step = width / (grid_size - 1)
            coordinates.extend(
                (origin_x + x * step, origin_y + y * step)
                for y in range(grid_size)
                for x in range(grid_size)
            )
            for y in range(grid_size):
                for x in range(grid_size):
                    node_id = first_node + y * grid_size + x
                    if x + 1 < grid_size:
                        edges.append((node_id, node_id + 1, "local"))
                    if y + 1 < grid_size:
                        edges.append((node_id, node_id + grid_size, "local"))
        return tuple(coordinates), tuple(edges)

    continuous_coordinates, continuous_edges = lattice(
        origins=((0.0, 0.0),),
        width=1_000.0,
        grid_size=7,
    )
    island_coordinates, island_edges = lattice(
        origins=((0.0, 0.0), (800.0, 0.0), (0.0, 800.0), (800.0, 800.0)),
        width=200.0,
        grid_size=7,
    )
    center_id = len(island_coordinates)
    island_coordinates += ((500.0, 500.0),)
    island_edges += tuple(
        (node_id, center_id, "collector")
        for node_id in (48, 91, 104, 147)
    )

    continuous = _topology_from_edges(
        continuous_edges,
        coordinates=continuous_coordinates,
    )
    islands = _topology_from_edges(
        island_edges,
        coordinates=island_coordinates,
    )
    continuous_metrics = compute_morphology_quality_metrics(continuous)
    island_metrics = compute_morphology_quality_metrics(islands)

    assert island_metrics.physical_road_length_m >= (
        continuous_metrics.physical_road_length_m * 0.85
    )
    assert continuous_metrics.global_street_cell_presence_share >= (
        island_metrics.global_street_cell_presence_share + 0.15
    )
    assert continuous_metrics.global_local_street_cell_presence_share >= (
        island_metrics.global_local_street_cell_presence_share + 0.20
    )
    assert continuous_metrics.global_local_junction_proximity_share >= (
        island_metrics.global_local_junction_proximity_share + 0.20
    )
    assert continuous_metrics.coverage_grid_resolution == 24
    continuous_gate = evaluate_morphology_quality_gate(
        style_id="organic",
        geometry_fingerprint="continuous-fixture",
        metrics=continuous_metrics,
    )
    island_gate = evaluate_morphology_quality_gate(
        style_id="organic",
        geometry_fingerprint="island-fixture",
        metrics=island_metrics,
    )
    assert continuous_gate.accepted is True
    assert island_gate.accepted is False
    assert any(
        failure.startswith("global_local_street_cell_presence_share")
        for failure in island_gate.failures
    )
    wrong_resolution_gate = evaluate_morphology_quality_gate(
        style_id="organic",
        geometry_fingerprint="wrong-resolution",
        metrics=replace(
            continuous_metrics,
            coverage_grid_resolution=1,
            junction_grid_resolution=1,
            junction_proximity_radius_cells=99.0,
        ),
    )
    assert wrong_resolution_gate.accepted is False
    assert {
        "coverage_grid_resolution must equal 24",
        "junction_grid_resolution must equal 12",
        "junction_proximity_radius_cells must equal 0.5",
    } <= set(wrong_resolution_gate.failures)


def test_long_local_cycle_passes_presence_but_fails_junction_gate() -> None:
    from metroflow.city.morphology_quality import (
        compute_morphology_quality_metrics,
        evaluate_morphology_quality_gate,
    )

    row_count = 12
    coordinates = tuple(
        point
        for row in range(row_count)
        for point in ((0.0, row * 100.0), (1_000.0, row * 100.0))
    )
    edges: list[tuple[int, int, str]] = []
    for row in range(row_count):
        left = row * 2
        right = left + 1
        edges.append((left, right, "local"))
        if row + 1 < row_count:
            side = right if row % 2 == 0 else left
            edges.append((side, side + 2, "local"))
    edges.append(((row_count - 1) * 2, 0, "local"))
    topology = _topology_from_edges(tuple(edges), coordinates=coordinates)
    metrics = compute_morphology_quality_metrics(topology)
    gate = evaluate_morphology_quality_gate(
        style_id="organic",
        geometry_fingerprint="long-lines",
        metrics=metrics,
    )

    assert metrics.global_local_street_cell_presence_share >= 0.40
    assert metrics.global_local_junction_proximity_share == 0.0
    assert metrics.block_continuity == 1.0
    assert "global_local_junction_proximity_share must be >= 0.4" in gate.failures


def test_quality_envelope_preserves_seed_runs_and_aggregates(tmp_path) -> None:
    from metroflow.ui.morphology_quality_report import write_morphology_quality_envelope

    paths = write_morphology_quality_envelope(
        tmp_path,
        seeds=(3, 5, 7),
        style_ids=("grid_core", "organic"),
        scenario_id="synthetic_smoke",
        topology_mode="sidecar_local_fabric_planar",
    )
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    markdown = paths["markdown"].read_text(encoding="utf-8")

    assert payload["artifact_format_version"] == "city_morphology_quality_v2"
    assert payload["evidence_status"] == "diagnostic_not_city_replication"
    assert payload["seeds"] == [3, 5, 7]
    assert [entry["style_id"] for entry in payload["styles"]] == ["grid_core", "organic"]
    assert all(len(entry["runs"]) == 3 for entry in payload["styles"])
    assert all(
        set(entry["aggregate"]["block_continuity"]) == {"min", "median", "max"}
        for entry in payload["styles"]
    )
    assert "Diagnostic structural envelope" in markdown


def test_generated_topology_exposes_quality_metrics() -> None:
    from metroflow.city.generator_v2 import GeneratorV2

    topology = GeneratorV2().generate_preview_topology(
        {
            "scenario_id": "synthetic_smoke",
            "seed": 11,
            "preview_mode": "sidecar_local_fabric_planar",
            "style_id": "polycentric_tod",
        }
    )

    metrics = topology.metadata["morphology_quality_metrics"]
    assert topology.metadata["morphology_quality_status"] == (
        "diagnostic_not_city_replication"
    )
    assert 0.0 <= metrics["block_continuity"] <= 1.0
    assert metrics["street_density_km_per_km2"] > 0.0
    assert metrics["district_count"] > 0
    gate = topology.metadata["morphology_quality_gate"]
    assert gate["accepted"] is True
    assert gate["gate_version"] == "morphology_quality_v2"
    assert gate["gate_scope"] == (
        "weak_connectivity_block_density_intersection_mix_"
        "global_local_cell_presence_junction_proximity"
    )
    assert gate["style_id"] == "polycentric_tod"
    assert gate["geometry_fingerprint"] == topology.road_geometry.fingerprint
    assert len(gate["metrics_digest"]) == 64


def test_project_owned_quality_gate_rejects_sparse_disconnected_fabric() -> None:
    from metroflow.city.morphology_quality import (
        MorphologyQualityMetrics,
        evaluate_morphology_quality_gate,
    )

    metrics = MorphologyQualityMetrics(
        convex_hull_area_m2=1_000_000.0,
        physical_road_length_m=1_000.0,
        street_density_km_per_km2=1.0,
        block_continuity=0.2,
        bridge_length_share=0.8,
        connector_to_local_length_ratio=1.0,
        median_local_length_m=100.0,
        median_connector_length_m=100.0,
        degree_one_share=0.4,
        degree_two_share=0.3,
        degree_three_share=0.2,
        degree_four_share=0.1,
        degree_five_plus_share=0.0,
        district_quadrant_presence_share=0.5,
        global_street_cell_presence_share=0.5,
        global_local_street_cell_presence_share=0.4,
        coverage_grid_resolution=24,
        global_local_junction_proximity_share=0.4,
        junction_grid_resolution=12,
        junction_proximity_radius_cells=0.5,
        weak_component_count=2,
        district_count=4,
        physical_segment_count=10,
    )

    gate = evaluate_morphology_quality_gate(
        style_id="organic",
        geometry_fingerprint="fixture",
        metrics=metrics,
    )

    assert gate.accepted is False
    assert "weak_component_count must equal 1" in gate.failures


def test_quality_metrics_reject_nonfinite_values_before_gate_evaluation() -> None:
    from metroflow.city.morphology_quality import MorphologyQualityMetrics

    with pytest.raises(ValueError, match="must be finite"):
        MorphologyQualityMetrics(
            convex_hull_area_m2=1_000.0,
            physical_road_length_m=100.0,
            street_density_km_per_km2=math.nan,
            block_continuity=0.5,
            bridge_length_share=0.5,
            connector_to_local_length_ratio=1.0,
            median_local_length_m=50.0,
            median_connector_length_m=50.0,
            degree_one_share=0.2,
            degree_two_share=0.8,
            degree_three_share=0.0,
            degree_four_share=0.0,
            degree_five_plus_share=0.0,
            district_quadrant_presence_share=1.0,
            global_street_cell_presence_share=1.0,
            global_local_street_cell_presence_share=1.0,
            coverage_grid_resolution=24,
            global_local_junction_proximity_share=1.0,
            junction_grid_resolution=12,
            junction_proximity_radius_cells=0.5,
            weak_component_count=1,
            district_count=1,
            physical_segment_count=2,
        )


def test_gate_rejects_disconnected_cycles_even_with_full_block_continuity() -> None:
    from metroflow.city.morphology_quality import (
        compute_morphology_quality_metrics,
        evaluate_morphology_quality_gate,
    )

    topology = _topology_from_edges(
        (
            (0, 1, "local"),
            (1, 2, "local"),
            (2, 3, "local"),
            (3, 0, "local"),
            (4, 5, "local"),
            (5, 6, "local"),
            (6, 7, "local"),
            (7, 4, "local"),
        ),
        coordinates=(
            (0.0, 0.0),
            (100.0, 0.0),
            (100.0, 100.0),
            (0.0, 100.0),
            (300.0, 0.0),
            (400.0, 0.0),
            (400.0, 100.0),
            (300.0, 100.0),
        ),
    )
    metrics = compute_morphology_quality_metrics(topology)
    gate = evaluate_morphology_quality_gate(
        style_id="organic",
        geometry_fingerprint="disconnected-cycles",
        metrics=metrics,
    )

    assert metrics.block_continuity == 1.0
    assert metrics.weak_component_count == 2
    assert gate.accepted is False
    assert "weak_component_count must equal 1" in gate.failures


@pytest.mark.parametrize("seed", (5, 17, 29, 41))
@pytest.mark.parametrize(
    "style_id",
    (
        "ring_radial",
        "grid_core",
        "polycentric_tod",
        "river_constrained",
        "superblock_mixed",
        "organic",
    ),
)
def test_all_style_fabric_passes_versioned_project_gate_across_seeds(
    seed: int,
    style_id: str,
) -> None:
    from metroflow.city.generator_v2 import GeneratorV2

    topology = GeneratorV2().generate_preview_topology(
        {
            "scenario_id": "synthetic_smoke",
            "seed": seed,
            "preview_mode": "sidecar_local_fabric_planar",
            "style_id": style_id,
        }
    )
    assert topology.metadata["morphology_quality_gate"]["accepted"] is True
    assert topology.metadata["morphology_quality_metrics"]["weak_component_count"] == 1


def test_morphology_quality_import_does_not_load_accelerators() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import metroflow.city.morphology_quality; "
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
