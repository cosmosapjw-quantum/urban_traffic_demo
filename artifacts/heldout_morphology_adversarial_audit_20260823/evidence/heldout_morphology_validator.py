#!/usr/bin/env python3
"""Seed-held-out structural morphology validation and sample-map rendering.

This one-off validator deliberately excludes traffic-functional measurements,
fresh-OSM empirical validation, named-city similarity, and promotion claims.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any


REPOSITORY = Path(
    "/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo"
).resolve()
SOURCE_ROOT = REPOSITORY / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import numpy as np

from metroflow.city.scale import CityScaleSpec
from metroflow.city.scalable_blocks import build_scalable_block_authority
from metroflow.city.scalable_city import ScalableCityMap, build_scalable_city_map
from metroflow.city.scalable_topology import (
    FacilityKind,
    RoadHierarchy,
    build_scalable_street_network,
)
from metroflow.sim.state import SimulationState, SimulationStaticRefs
from metroflow.ui.static_map import (
    build_static_city_map_artifact,
    render_static_city_map_svg,
)


SCHEMA_VERSION = "seed_heldout_structural_morphology_v1"
MANIFEST_SCHEMA_VERSION = "seed_heldout_morphology_samples_v1"
OUTPUT_DIR = Path(
    "/tmp/urban-traffic-heldout-morphology-samples-20260822"
).resolve()
RESULTS_PATH = OUTPUT_DIR / "heldout_morphology_results.json"
MANIFEST_PATH = OUTPUT_DIR / "sample_manifest.json"
CONTACT_SHEET_PATH = OUTPUT_DIR / "heldout_morphology_seed503_contact_sheet.png"

STYLE_SPECS: tuple[tuple[str, str], ...] = (
    ("grid_core", "Grid Core (Standard Uniform Lattice)"),
    ("ring_radial", "Ring Radial (Concentric Rings & Radial Spines)"),
    (
        "river_constrained",
        "River Constrained (Bifurcated Corridor & Bridges)",
    ),
    ("polycentric_tod", "Polycentric TOD (Multi-Hub Centers)"),
    (
        "superblock_mixed",
        "Superblock Mixed (Hierarchical Macroblock Perimeters)",
    ),
    ("organic", "Curvilinear Warped Grid (organic compatibility ID)"),
)
STYLE_IDS = tuple(style_id for style_id, _label in STYLE_SPECS)
DEVELOPMENT_SEEDS = (0, 1, 2, 3, 4, 17, 29, 42, 101)
HOLDOUT_SEEDS = (503, 701, 907)
SAMPLE_SEED = 503
VALIDATION_SCALE = CityScaleSpec(
    target_population=100_000,
    urbanized_area_km2=25.0,
)

# Frozen before the held-out seeds are opened.
RING_RADIAL_CV_MAX = 0.01
RING_WINDING_ABS_TOL = 1e-9
RING_MIN_ORBITALS = 2
POLYCENTRIC_MIN_CENTERS = 3
RIVER_MIN_BRIDGES = 3
RIVER_MIN_FAILURE_GROUPS = 3
SUPERBLOCK_MIN_AXIS_MM = 700_000
SUPERBLOCK_MAX_ASPECT_RATIO = 2.5
SUPERBLOCK_MIN_COUNT = 4
ORGANIC_MIN_BENT_CONNECTOR_SHARE_EXCLUSIVE = 0.9


@dataclass(frozen=True)
class _GalleryConfig:
    topology_mode: str = "scalable_synthetic_v2"
    morphology_style_id: str = "grid_core"
    zone_poi_coupling_mode: str = "block_based_v1"
    scale_spec: CityScaleSpec | None = VALIDATION_SCALE


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _git_output(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def protocol_payload() -> dict[str, Any]:
    if len(STYLE_IDS) != len(set(STYLE_IDS)):
        raise RuntimeError("duplicate style identity in frozen protocol")
    if len(HOLDOUT_SEEDS) != len(set(HOLDOUT_SEEDS)):
        raise RuntimeError("duplicate held-out seed in frozen protocol")
    if not set(DEVELOPMENT_SEEDS).isdisjoint(HOLDOUT_SEEDS):
        raise RuntimeError("held-out seeds overlap development seeds")
    if SAMPLE_SEED not in HOLDOUT_SEEDS:
        raise RuntimeError("sample seed must be one of the held-out seeds")
    return {
        "schema_version": SCHEMA_VERSION,
        "style_ids": list(STYLE_IDS),
        "development_seeds": list(DEVELOPMENT_SEEDS),
        "heldout_seeds": list(HOLDOUT_SEEDS),
        "sample_seed": SAMPLE_SEED,
        "attempt_count_expected": len(STYLE_IDS) * len(HOLDOUT_SEEDS),
        "scale": {
            "target_population": VALIDATION_SCALE.target_population,
            "urbanized_area_km2": VALIDATION_SCALE.urbanized_area_km2,
        },
        "holdout_kind": "seed_heldout_structural_not_fresh_osm",
        "fresh_osm_holdout_status": "NOT_EVALUATED",
        "claim_level": "STRUCTURAL_MORPHOLOGY_ONLY",
        "thresholds": {
            "ring_radial_cv_max_exclusive": RING_RADIAL_CV_MAX,
            "ring_winding_abs_tolerance": RING_WINDING_ABS_TOL,
            "ring_min_orbitals": RING_MIN_ORBITALS,
            "polycentric_min_centers": POLYCENTRIC_MIN_CENTERS,
            "river_min_bridges": RIVER_MIN_BRIDGES,
            "river_min_failure_groups": RIVER_MIN_FAILURE_GROUPS,
            "superblock_min_axis_mm": SUPERBLOCK_MIN_AXIS_MM,
            "superblock_max_aspect_ratio": SUPERBLOCK_MAX_ASPECT_RATIO,
            "superblock_min_count": SUPERBLOCK_MIN_COUNT,
            "organic_min_bent_connector_share_exclusive": (
                ORGANIC_MIN_BENT_CONNECTOR_SHARE_EXCLUSIVE
            ),
        },
    }


def _validate_case_identity(style_id: str, seed: int) -> tuple[str, int]:
    if style_id not in STYLE_IDS:
        raise ValueError(f"unsupported morphology style: {style_id!r}")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be a non-bool integer")
    if seed not in HOLDOUT_SEEDS:
        raise ValueError(f"undeclared held-out seed: {seed!r}")
    return style_id, seed


def _ordered_cycle_node_ids(roads: tuple[Any, ...]) -> tuple[int, ...] | None:
    adjacency: dict[int, list[int]] = defaultdict(list)
    for road in roads:
        adjacency[int(road.start_node_id)].append(int(road.end_node_id))
        adjacency[int(road.end_node_id)].append(int(road.start_node_id))
    if not adjacency or any(len(neighbours) != 2 for neighbours in adjacency.values()):
        return None
    start = min(adjacency)
    ordered = [start]
    previous: int | None = None
    current = start
    while True:
        candidates = sorted(
            node_id for node_id in adjacency[current] if node_id != previous
        )
        if not candidates:
            return None
        following = candidates[0]
        if following == start:
            break
        if following in ordered:
            return None
        ordered.append(following)
        previous, current = current, following
    return tuple(ordered) if len(ordered) == len(roads) else None


def _ring_witnesses(network: Any) -> tuple[dict[str, Any], dict[str, bool]]:
    center_x, center_y = network.centers[0]
    nodes = {node.node_id: node for node in network.nodes}
    groups: dict[str, list[Any]] = defaultdict(list)
    for road in network.roads:
        if road.semantic_role.startswith("ring-orbital-"):
            groups[road.semantic_role].append(road)
    valid_radii: list[float] = []
    radial_cvs: list[float] = []
    winding_magnitudes: list[float] = []
    for roads in groups.values():
        ordered_ids = _ordered_cycle_node_ids(tuple(roads))
        if ordered_ids is None:
            continue
        vectors = tuple(
            (nodes[node_id].x_mm - center_x, nodes[node_id].y_mm - center_y)
            for node_id in ordered_ids
        )
        radii = tuple(math.hypot(x_value, y_value) for x_value, y_value in vectors)
        mean_radius = sum(radii) / len(radii)
        if mean_radius <= 0.0:
            continue
        radial_cv = math.sqrt(
            sum((radius - mean_radius) ** 2 for radius in radii) / len(radii)
        ) / mean_radius
        winding = sum(
            math.atan2(
                left[0] * right[1] - left[1] * right[0],
                left[0] * right[0] + left[1] * right[1],
            )
            for left, right in zip(vectors, vectors[1:] + vectors[:1])
        ) / math.tau
        radial_cvs.append(radial_cv)
        winding_magnitudes.append(abs(winding))
        if radial_cv < RING_RADIAL_CV_MAX and math.isclose(
            abs(winding),
            1.0,
            abs_tol=RING_WINDING_ABS_TOL,
        ):
            valid_radii.append(mean_radius)
    distinct_radius_count = len({round(radius) for radius in valid_radii})
    witnesses = {
        "orbital_group_count": len(groups),
        "concentric_orbital_count": len(valid_radii),
        "distinct_radius_count": distinct_radius_count,
        "max_radial_cv": max(radial_cvs, default=0.0),
        "min_winding_magnitude": min(winding_magnitudes, default=0.0),
    }
    return witnesses, {
        "closed_concentric_orbitals": len(valid_radii) >= RING_MIN_ORBITALS,
        "distinct_orbital_radii": distinct_radius_count == len(valid_radii),
    }


def _grid_witnesses(network: Any) -> tuple[dict[str, Any], dict[str, bool]]:
    horizontal = [
        road for road in network.roads if road.semantic_role == "surface-horizontal"
    ]
    vertical = [
        road for road in network.roads if road.semantic_role == "surface-vertical"
    ]
    core = horizontal + vertical
    axis_aligned = sum(
        all(
            left[0] == right[0] or left[1] == right[1]
            for left, right in zip(road.points_mm, road.points_mm[1:])
        )
        for road in core
    )
    witnesses = {
        "horizontal_carrier_count": len(horizontal),
        "vertical_carrier_count": len(vertical),
        "axis_aligned_core_count": axis_aligned,
        "core_carrier_count": len(core),
        "center_count": len(network.centers),
    }
    return witnesses, {
        "two_axis_grid_carriers": bool(horizontal and vertical),
        "axis_aligned_grid_core": bool(core) and axis_aligned == len(core),
        "single_grid_center": len(network.centers) == 1,
    }


def _high_hierarchy_path_exists(network: Any, start_id: int, end_id: int) -> bool:
    adjacency: dict[int, set[int]] = defaultdict(set)
    for road in network.roads:
        if road.facility is not FacilityKind.SURFACE or road.hierarchy not in {
            RoadHierarchy.ARTERIAL,
            RoadHierarchy.COLLECTOR,
        }:
            continue
        adjacency[road.start_node_id].add(road.end_node_id)
        adjacency[road.end_node_id].add(road.start_node_id)
    frontier = deque((start_id,))
    visited = {start_id}
    while frontier:
        current = frontier.popleft()
        if current == end_id:
            return True
        for neighbour in adjacency[current] - visited:
            visited.add(neighbour)
            frontier.append(neighbour)
    return False


def _polycentric_witnesses(network: Any) -> tuple[dict[str, Any], dict[str, bool]]:
    centers = tuple(network.centers)
    noncollinear = False
    if len(centers) >= POLYCENTRIC_MIN_CENTERS:
        first, second, third = centers[:3]
        noncollinear = (
            (second[0] - first[0]) * (third[1] - first[1])
            - (second[1] - first[1]) * (third[0] - first[0])
        ) != 0
    catchment_counts = [0] * len(centers)
    center_points = set(centers)
    for node in network.nodes:
        if node.layer != 0 or (node.x_mm, node.y_mm) in center_points or not centers:
            continue
        owner = min(
            range(len(centers)),
            key=lambda index: (
                (node.x_mm - centers[index][0]) ** 2
                + (node.y_mm - centers[index][1]) ** 2,
                index,
            ),
        )
        catchment_counts[owner] += 1
    node_by_point = {
        (node.x_mm, node.y_mm): node.node_id
        for node in network.nodes
        if node.layer == 0
    }
    center_node_ids = tuple(
        node_by_point[center] for center in centers if center in node_by_point
    )
    backbone_pair_count = sum(
        _high_hierarchy_path_exists(network, left, right)
        for offset, left in enumerate(center_node_ids)
        for right in center_node_ids[offset + 1 :]
    )
    expected_pairs = len(centers) * (len(centers) - 1) // 2
    witnesses = {
        "center_count": len(centers),
        "nonempty_catchment_count": sum(count > 0 for count in catchment_counts),
        "backbone_pair_count": backbone_pair_count,
        "expected_backbone_pair_count": expected_pairs,
    }
    return witnesses, {
        "three_or_more_centers": len(centers) >= POLYCENTRIC_MIN_CENTERS,
        "centers_noncollinear": noncollinear,
        "nonempty_center_catchments": bool(centers)
        and all(count > 0 for count in catchment_counts),
        "hierarchy_backbone_connects_centers": (
            len(center_node_ids) == len(centers)
            and backbone_pair_count == expected_pairs
        ),
    }


def _river_witnesses(network: Any) -> tuple[dict[str, Any], dict[str, bool]]:
    bridges = [
        road
        for road in network.roads
        if road.facility is FacilityKind.BRIDGE
        or road.semantic_role == "river-bridge"
    ]
    failure_groups = {road.failure_group for road in bridges if road.failure_group}
    witnesses = {
        "river_bridge_count": len(bridges),
        "bridge_failure_group_count": len(failure_groups),
        "center_count": len(network.centers),
    }
    return witnesses, {
        "three_or_more_river_bridges": len(bridges) >= RIVER_MIN_BRIDGES,
        "bridge_failure_groups_present": (
            len(failure_groups) >= RIVER_MIN_FAILURE_GROUPS
        ),
        "two_sided_centers": len(network.centers) >= 2,
    }


def _superblock_witnesses(network: Any) -> tuple[dict[str, Any], dict[str, bool]]:
    authority = build_scalable_block_authority(network)
    road_by_id = {road.road_id: road for road in network.roads}
    macroblocks = []
    aspect_ratios: list[float] = []
    min_axes_mm: list[int] = []
    for block in authority.blocks:
        x_values = [point[0] for point in block.outer_polygon_mm]
        y_values = [point[1] for point in block.outer_polygon_mm]
        width_mm = max(x_values) - min(x_values)
        height_mm = max(y_values) - min(y_values)
        if min(width_mm, height_mm) <= 0:
            continue
        aspect_ratio = max(width_mm, height_mm) / min(width_mm, height_mm)
        if (
            min(width_mm, height_mm) >= SUPERBLOCK_MIN_AXIS_MM
            and aspect_ratio <= SUPERBLOCK_MAX_ASPECT_RATIO
        ):
            macroblocks.append(block)
            aspect_ratios.append(aspect_ratio)
            min_axes_mm.append(min(width_mm, height_mm))
    perimeter_qualified = sum(
        bool(block.frontage_road_ids)
        and all(
            road_by_id[road_id].hierarchy
            in {RoadHierarchy.ARTERIAL, RoadHierarchy.COLLECTOR}
            for road_id in block.frontage_road_ids
        )
        for block in macroblocks
    )
    witnesses = {
        "macroblock_count": len(macroblocks),
        "hierarchy_perimeter_macroblock_count": perimeter_qualified,
        "bounded_block_count": len(authority.blocks),
        "largest_macroblock_aspect_ratio": max(aspect_ratios, default=0.0),
        "smallest_macroblock_min_axis_mm": min(min_axes_mm, default=0),
    }
    return witnesses, {
        "multiple_two_dimensional_macroblocks": (
            len(macroblocks) >= SUPERBLOCK_MIN_COUNT
        ),
        "hierarchy_qualified_perimeters": bool(macroblocks)
        and perimeter_qualified == len(macroblocks),
    }


def _road_has_bent_control_point(road: Any) -> bool:
    start = road.points_mm[0]
    end = road.points_mm[-1]
    return any(
        (end[0] - start[0]) * (point[1] - start[1])
        != (end[1] - start[1]) * (point[0] - start[0])
        for point in road.points_mm[1:-1]
    )


def _organic_witnesses(network: Any) -> tuple[dict[str, Any], dict[str, bool]]:
    connectors = [
        road for road in network.roads if road.semantic_role == "organic-connector"
    ]
    bent = [road for road in connectors if _road_has_bent_control_point(road)]
    bent_share = len(bent) / len(connectors) if connectors else 0.0
    witnesses = {
        "connector_count": len(connectors),
        "bent_connector_count": len(bent),
        "bent_connector_share": bent_share,
    }
    return witnesses, {
        "curvilinear_connector_majority": (
            bent_share > ORGANIC_MIN_BENT_CONNECTOR_SHARE_EXCLUSIVE
        ),
    }


def _morphology_witnesses(
    network: Any,
    style_id: str,
) -> tuple[dict[str, Any], dict[str, bool]]:
    if style_id == "ring_radial":
        return _ring_witnesses(network)
    if style_id == "grid_core":
        return _grid_witnesses(network)
    if style_id == "polycentric_tod":
        return _polycentric_witnesses(network)
    if style_id == "river_constrained":
        return _river_witnesses(network)
    if style_id == "superblock_mixed":
        return _superblock_witnesses(network)
    if style_id == "organic":
        return _organic_witnesses(network)
    raise ValueError(f"unsupported morphology style: {style_id!r}")


def collect_case(style_id: str, seed: int) -> dict[str, Any]:
    style_id, seed = _validate_case_identity(style_id, seed)
    network = build_scalable_street_network(VALIDATION_SCALE, style_id, seed=seed)
    replay = build_scalable_street_network(VALIDATION_SCALE, style_id, seed=seed)
    witnesses, style_checks = _morphology_witnesses(network, style_id)
    checks = {
        "nonempty_network": bool(network.nodes and network.roads),
        "style_identity": network.style_id == style_id,
        "deterministic_replay": network.fingerprint == replay.fingerprint,
        **style_checks,
    }
    return {
        "style_id": style_id,
        "seed": seed,
        "network_fingerprint": network.fingerprint,
        "node_count": len(network.nodes),
        "road_count": len(network.roads),
        "witnesses": witnesses,
        "checks": checks,
        "passed": all(checks.values()),
    }


def build_validation_result() -> dict[str, Any]:
    protocol = protocol_payload()
    cases = [
        collect_case(style_id, seed)
        for style_id in STYLE_IDS
        for seed in HOLDOUT_SEEDS
    ]
    actual_keys = [(case["style_id"], case["seed"]) for case in cases]
    expected_keys = [
        (style_id, seed) for style_id in STYLE_IDS for seed in HOLDOUT_SEEDS
    ]
    if len(actual_keys) != len(set(actual_keys)):
        raise RuntimeError("duplicate held-out morphology result key")
    if set(actual_keys) != set(expected_keys) or len(actual_keys) != len(expected_keys):
        raise RuntimeError("held-out morphology result partition is incomplete")
    style_summary = {}
    for style_id in STYLE_IDS:
        style_cases = [case for case in cases if case["style_id"] == style_id]
        style_summary[style_id] = {
            "passed_case_count": sum(case["passed"] for case in style_cases),
            "attempted_case_count": len(style_cases),
            "unique_network_fingerprint_count": len(
                {case["network_fingerprint"] for case in style_cases}
            ),
            "passed": all(case["passed"] for case in style_cases),
        }
    scientific_payload = {
        "protocol": protocol,
        "cases": cases,
        "style_summary": style_summary,
        "attempt_inventory": {
            "attempted": len(cases),
            "scored": len(cases),
            "skipped": 0,
            "expected": len(expected_keys),
        },
    }
    scientific_fingerprint = _sha256_bytes(
        json.dumps(
            scientific_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    )
    all_passed = all(case["passed"] for case in cases)
    return {
        "schema_version": SCHEMA_VERSION,
        "verdict": "PASS" if all_passed else "FAIL",
        "claim_level": "SEED_HELDOUT_STRUCTURAL_MORPHOLOGY_ONLY",
        "empirical_city_validation": "NOT_EVALUATED_NO_FRESH_OSM_HOLDOUT",
        "repository": {
            "commit": _git_output("rev-parse", "HEAD"),
            "tree": _git_output("rev-parse", "HEAD^{tree}"),
        },
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
        },
        "source_script_sha256": _sha256_bytes(Path(__file__).read_bytes()),
        "scientific_fingerprint": scientific_fingerprint,
        **scientific_payload,
    }


def _manifest_entry(
    *,
    style_id: str,
    label: str,
    city: ScalableCityMap,
    svg_path: Path,
    png_path: Path,
    svg_sha256: str,
    png_sha256: str,
) -> dict[str, Any]:
    return {
        "style_id": style_id,
        "display_label": label,
        "seed": SAMPLE_SEED,
        "topology_mode": "scalable_synthetic_v2",
        "target_population": VALIDATION_SCALE.target_population,
        "urbanized_area_km2": VALIDATION_SCALE.urbanized_area_km2,
        "network_schema_version": city.network.schema_version,
        "network_fingerprint": city.network.fingerprint,
        "blocks_schema_version": city.blocks.schema_version,
        "blocks_fingerprint": city.blocks.fingerprint,
        "compiled_schema_version": city.compiled.schema_version,
        "compiled_fingerprint": city.compiled.fingerprint,
        "static_authority_schema_version": city.static_authority.schema_version,
        "static_authority_fingerprint": city.static_authority.fingerprint,
        "zoning_placement_fingerprint": city.zoning.metadata.get(
            "zoning_placement_fingerprint",
            "",
        ),
        "city_map_fingerprint": city.fingerprint,
        "node_count": len(city.topology.nodes),
        "link_count": len(city.topology.links),
        "svg_file": svg_path.name,
        "svg_sha256": svg_sha256,
        "png_file": png_path.name,
        "png_sha256": png_sha256,
    }


def _derive_sample(style_id: str, label: str) -> tuple[ScalableCityMap, str]:
    config = _GalleryConfig(morphology_style_id=style_id)
    if config.topology_mode != "scalable_synthetic_v2":
        raise RuntimeError("sample must use scalable_synthetic_v2")
    scenario_id = f"heldout_{style_id}_s{SAMPLE_SEED}"
    city = build_scalable_city_map(config, scenario_id=scenario_id, seed=SAMPLE_SEED)
    static_refs = SimulationStaticRefs(
        scenario_id=scenario_id,
        city_topology=city.topology,
        zones=city.zoning.zones,
        pois=city.zoning.pois,
        metadata={"label": label, "validation_scope": "heldout_morphology_only"},
    )
    artifact = build_static_city_map_artifact(SimulationState(static=static_refs))
    return city, render_static_city_map_svg(artifact)


def render_samples() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    png_paths = []
    for style_id, label in STYLE_SPECS:
        print(f"render {style_id} seed={SAMPLE_SEED}", flush=True)
        city, svg = _derive_sample(style_id, label)
        svg_path = OUTPUT_DIR / f"map_{style_id}_s{SAMPLE_SEED}.svg"
        png_path = OUTPUT_DIR / f"map_{style_id}_s{SAMPLE_SEED}.png"
        svg_payload = svg.encode("utf-8")
        svg_path.write_bytes(svg_payload)
        png_path.unlink(missing_ok=True)
        subprocess.run(
            [
                "google-chrome",
                "--headless",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--screenshot={png_path}",
                "--window-size=1400,1050",
                svg_path.as_uri(),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not png_path.is_file() or png_path.stat().st_size == 0:
            raise RuntimeError(f"Chrome did not produce a nonempty PNG: {png_path}")
        png_payload = png_path.read_bytes()
        entries.append(
            _manifest_entry(
                style_id=style_id,
                label=label,
                city=city,
                svg_path=svg_path,
                png_path=png_path,
                svg_sha256=_sha256_bytes(svg_payload),
                png_sha256=_sha256_bytes(png_payload),
            )
        )
        png_paths.append(png_path)
    CONTACT_SHEET_PATH.unlink(missing_ok=True)
    subprocess.run(
        [
            "montage",
            *[str(path) for path in png_paths],
            "-thumbnail",
            "700x525",
            "-tile",
            "3x2",
            "-geometry",
            "+12+12",
            "-background",
            "white",
            str(CONTACT_SHEET_PATH),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not CONTACT_SHEET_PATH.is_file() or CONTACT_SHEET_PATH.stat().st_size == 0:
        raise RuntimeError("ImageMagick did not produce a nonempty contact sheet")
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "claim_level": "SEED_HELDOUT_STRUCTURAL_MORPHOLOGY_SAMPLE_ONLY",
        "sample_seed": SAMPLE_SEED,
        "repository_commit": _git_output("rev-parse", "HEAD"),
        "repository_tree": _git_output("rev-parse", "HEAD^{tree}"),
        "entries": entries,
        "contact_sheet_file": CONTACT_SHEET_PATH.name,
        "contact_sheet_sha256": _sha256_bytes(CONTACT_SHEET_PATH.read_bytes()),
    }
    MANIFEST_PATH.write_bytes(_json_bytes(manifest))
    return manifest


def generate() -> int:
    protocol_payload()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("collect 18 seed-held-out structural morphology cases", flush=True)
    result = build_validation_result()
    RESULTS_PATH.write_bytes(_json_bytes(result))
    render_samples()
    print(
        f"generated verdict={result['verdict']} cases={len(result['cases'])} "
        f"samples={len(STYLE_SPECS)} out={OUTPUT_DIR}",
        flush=True,
    )
    return 0 if result["verdict"] == "PASS" else 1


def check_validation() -> bool:
    if not RESULTS_PATH.is_file():
        raise FileNotFoundError(RESULTS_PATH)
    committed = RESULTS_PATH.read_bytes()
    rederived = _json_bytes(build_validation_result())
    if committed != rederived:
        raise RuntimeError("held-out morphology result is not byte-identical on rederivation")
    payload = json.loads(committed)
    inventory = payload["attempt_inventory"]
    if inventory != {"attempted": 18, "expected": 18, "scored": 18, "skipped": 0}:
        raise RuntimeError(f"invalid exact attempt inventory: {inventory!r}")
    if payload["verdict"] != "PASS":
        raise RuntimeError("held-out morphology result did not pass")
    if not all(case["passed"] for case in payload["cases"]):
        raise RuntimeError("one or more held-out cases did not pass")
    print(
        "validation check passed: 18/18 cases re-derived byte-identically; "
        "0 skipped",
        flush=True,
    )
    return True


def check_samples() -> bool:
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(MANIFEST_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise RuntimeError("sample manifest schema mismatch")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not all(
        isinstance(entry, dict) for entry in entries
    ):
        raise RuntimeError("sample manifest entries must be a list of objects")
    actual_ids = [entry.get("style_id") for entry in entries]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(STYLE_IDS):
        raise RuntimeError("sample manifest style partition mismatch")
    entry_by_style = {entry["style_id"]: entry for entry in entries}
    for style_id, label in STYLE_SPECS:
        committed_entry = entry_by_style[style_id]
        svg_path = OUTPUT_DIR / committed_entry["svg_file"]
        png_path = OUTPUT_DIR / committed_entry["png_file"]
        if not svg_path.is_file() or not png_path.is_file():
            raise RuntimeError(f"missing map sample for {style_id}")
        city, rederived_svg = _derive_sample(style_id, label)
        rederived_payload = rederived_svg.encode("utf-8")
        committed_svg_payload = svg_path.read_bytes()
        if rederived_payload != committed_svg_payload:
            raise RuntimeError(f"SVG authority drift for {style_id}")
        expected_entry = _manifest_entry(
            style_id=style_id,
            label=label,
            city=city,
            svg_path=svg_path,
            png_path=png_path,
            svg_sha256=_sha256_bytes(rederived_payload),
            png_sha256=_sha256_bytes(png_path.read_bytes()),
        )
        if committed_entry != expected_entry:
            raise RuntimeError(f"sample manifest provenance drift for {style_id}")
    contact_sheet = OUTPUT_DIR / manifest["contact_sheet_file"]
    if not contact_sheet.is_file():
        raise RuntimeError("missing contact sheet")
    if _sha256_bytes(contact_sheet.read_bytes()) != manifest["contact_sheet_sha256"]:
        raise RuntimeError("contact sheet digest mismatch")
    print(
        "sample check passed: 6/6 SVG authorities re-derived byte-identically; "
        "6 PNG previews and contact sheet matched recorded digests",
        flush=True,
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--protocol-check", action="store_true")
    mode.add_argument("--check-validation", action="store_true")
    mode.add_argument("--check-samples", action="store_true")
    args = parser.parse_args()
    if args.protocol_check:
        payload = protocol_payload()
        print(
            f"protocol check passed: styles={len(payload['style_ids'])} "
            f"seeds={len(payload['heldout_seeds'])} "
            f"attempts={payload['attempt_count_expected']}",
            flush=True,
        )
        return 0
    if args.generate:
        return generate()
    if args.check_validation:
        return 0 if check_validation() else 1
    return 0 if check_samples() else 1


if __name__ == "__main__":
    raise SystemExit(main())
