"""Authoritative terrain-to-runtime realistic synthetic city pipeline."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Protocol

from metroflow.map.node_compiler import compile_node_interfaces
from metroflow.map.road_geometry import (
    build_endpoint_geometry_catalog,
    count_interior_centerline_intersections,
    validate_geometry_endpoint_anchors,
)
from metroflow.map.section_compiler import compile_road_sections

from .block_land_use import (
    BlockLandUse,
    BlockLandUseType,
    build_block_land_use_catalog,
)
from .blueprint import CityBlueprint, GeneratedCityMap, RealisticCityQualityResult
from .connectivity import analyze_directed_reachability, analyze_weak_connectivity
from .generated_map import PreviewCityTopology
from .graph import BridgeCrossing, TurnType
from .hierarchical_streets import build_hierarchical_street_skeleton
from .map_validation import require_valid_city_map_contract
from .planar_blocks import compile_planar_city_blocks
from .realistic_local_fabric import build_continuous_local_fabric
from .terrain_field import build_terrain_field
from .turn_compiler import compile_turn_authority
from .urban_form import build_urban_form_field
from .zones import POI, Zone, ZoningPlacementResult, zoning_placement_fingerprint

__all__ = ["generate_city_map"]


class _CityGenerationConfigLike(Protocol):
    topology_mode: str
    morphology_style_id: str
    zone_poi_coupling_mode: str


def generate_city_map(
    config: _CityGenerationConfigLike,
    scenario_id: str,
    seed: int,
) -> GeneratedCityMap:
    """Generate one fail-closed realistic city and compile runtime authorities."""

    scenario_id = str(scenario_id).strip()
    seed = int(seed)
    if not scenario_id:
        raise ValueError("scenario_id must not be empty")
    if str(config.topology_mode) != "realistic_synthetic_v1":
        raise ValueError("generate_city_map requires realistic_synthetic_v1")
    if str(config.zone_poi_coupling_mode) != "block_based_v1":
        raise ValueError("realistic city generation requires block_based_v1")
    style_id = _resolve_style_id(
        requested=str(config.morphology_style_id),
        scenario_id=scenario_id,
    )
    width_m, height_m = _dimensions_for_scenario(scenario_id)
    terrain = build_terrain_field(
        width=width_m,
        height=height_m,
        seed=seed,
        style_id=style_id,
        max_grid_size=128,
    )
    urban_form = build_urban_form_field(
        terrain=terrain,
        style_id=style_id,
        seed=seed,
    )
    skeleton = build_hierarchical_street_skeleton(
        terrain=terrain,
        urban_form=urban_form,
    )
    street_network = build_continuous_local_fabric(
        terrain=terrain,
        urban_form=urban_form,
        skeleton=skeleton,
    )
    blocks = compile_planar_city_blocks(street_network)
    land_use = build_block_land_use_catalog(
        terrain=terrain,
        urban_form=urban_form,
        street_network=street_network,
        block_catalog=blocks,
    )
    blueprint = CityBlueprint(
        schema_version="realistic_synthetic_city_v1",
        scenario_id=scenario_id,
        seed=seed,
        style_id=style_id,
        width_m=width_m,
        height_m=height_m,
        terrain=terrain,
        urban_form=urban_form,
        street_skeleton=skeleton,
        street_network=street_network,
        blocks=blocks,
        land_use=land_use,
    )
    topology = _compile_topology(blueprint)
    zoning = _compile_zoning(blueprint=blueprint, topology=topology)
    topology.metadata.update(
        {
            "zoning_placement_fingerprint": zoning.metadata[
                "zoning_placement_fingerprint"
            ],
            "land_use_catalog_fingerprint": land_use.fingerprint,
            "zone_poi_coupling_requested_mode": "block_based_v1",
            "zone_poi_coupling_resolved_mode": "block_based_v1",
            "zone_poi_coupling_fallback_reason": "",
            "zone_poi_coupling_gate_version": "block_land_use_v1",
            "zone_poi_coupling_gate_digest": land_use.fingerprint,
            "zone_poi_coupling_anchor_digest": blocks.fingerprint,
        }
    )
    road_csr = topology.build_csr(
        validate=True,
        require_weak_connectivity=True,
    )
    quality = _evaluate_quality(
        blueprint=blueprint,
        topology=topology,
        zoning=zoning,
    )
    generated = GeneratedCityMap(
        blueprint=blueprint,
        topology=topology,
        road_csr=road_csr,
        zoning=zoning,
        quality=quality,
    )
    topology.metadata["generated_city_map_fingerprint"] = generated.fingerprint
    return generated


def _compile_topology(blueprint: CityBlueprint) -> PreviewCityTopology:
    nodes = blueprint.blocks.nodes
    links = blueprint.blocks.links
    connectivity = analyze_weak_connectivity(nodes=nodes, links=links)
    if connectivity.component_count != 1:
        raise ValueError(
            "realistic city topology must be connected without repair: "
            f"components={connectivity.component_sizes}"
        )
    geometry = build_endpoint_geometry_catalog(nodes=nodes, links=links)
    validate_geometry_endpoint_anchors(catalog=geometry, nodes=nodes, links=links)
    intersection_count = count_interior_centerline_intersections(geometry)
    if intersection_count:
        raise ValueError(
            "realistic city topology retained same-layer proper intersections: "
            f"{intersection_count}"
        )
    sections = compile_road_sections(links=links, road_geometry=geometry)
    node_interfaces = compile_node_interfaces(
        nodes=nodes,
        links=links,
        road_geometry=geometry,
    )
    turn_authority = compile_turn_authority(
        links=links,
        road_geometry=geometry,
        node_interfaces=node_interfaces,
    )
    bridge_crossings = _bridge_crossings(links)
    metadata = {
        "engine": "realistic_synthetic_v1",
        "topology_mode": "realistic_synthetic_v1",
        "scenario_id": blueprint.scenario_id,
        "seed": blueprint.seed,
        "style_id": blueprint.style_id,
        "city_blueprint_fingerprint": blueprint.fingerprint,
        "terrain_fingerprint": blueprint.terrain.fingerprint,
        "urban_form_fingerprint": blueprint.urban_form.fingerprint,
        "street_network_fingerprint": blueprint.street_network.fingerprint,
        "city_block_catalog_fingerprint": blueprint.blocks.fingerprint,
        "land_use_catalog_fingerprint": blueprint.land_use.fingerprint,
        "weak_component_count_before_repair": 1,
        "weak_component_sizes_before_repair": connectivity.component_sizes,
        "connectivity_repair_link_count": 0,
        "connectivity_repair_link_ids": (),
        "weak_component_count_after_repair": 1,
        "weak_component_sizes_after_repair": connectivity.component_sizes,
        "planarization_status": "passed_without_runtime_repair",
        "proper_intersection_count_before_planarization": (
            blueprint.blocks.proper_intersection_count_before
        ),
        "proper_intersection_count_after_planarization": 0,
        "road_geometry_fingerprint": geometry.fingerprint,
        "physical_centerline_count": len(geometry.centerlines),
        "geometry_assignment_count": len(geometry.assignments),
        "unmodeled_centerline_intersection_count": 0,
        "centerline_intersection_audit_status": "validation_gate_passed",
        "road_section_fingerprint": sections.fingerprint,
        "road_section_profile_count": len(sections.profiles),
        "node_interface_fingerprint": node_interfaces.fingerprint,
        "node_interface_count": len(node_interfaces.interfaces),
        "turn_authority_fingerprint": turn_authority.fingerprint,
        "turn_authority_pair_count": len(turn_authority.movements),
        "permitted_turn_movement_count": sum(
            movement.turn_type is not TurnType.U_TURN_FORBIDDEN
            for movement in turn_authority.movements
        ),
        "forbidden_u_turn_count": sum(
            movement.turn_type is TurnType.U_TURN_FORBIDDEN
            for movement in turn_authority.movements
        ),
        "turn_authority_policy": (
            "all_adjacent_pairs_explicit_immediate_return_forbidden_v1"
        ),
        "capacity_reference_tick_seconds": 1.0,
        "capacity_source_unit": "vehicles_per_second",
    }
    topology = PreviewCityTopology(
        nodes=nodes,
        links=links,
        turns=turn_authority.movements,
        bridge_crossings=bridge_crossings,
        road_geometry=geometry,
        road_sections=sections,
        node_interfaces=node_interfaces,
        metadata=metadata,
    )
    report = topology.validate(require_weak_connectivity=True)
    if not report.ok:
        raise ValueError(
            f"realistic city topology validation failed: {report.summary()}"
        )
    return topology


def _compile_zoning(
    *,
    blueprint: CityBlueprint,
    topology: PreviewCityTopology,
) -> ZoningPlacementResult:
    developed = tuple(item for item in blueprint.land_use.blocks if item.is_developed)
    zone_id_by_block_id = {item.block_id: item.block_id + 1 for item in developed}
    zones = tuple(
        Zone(
            zone_id=zone_id_by_block_id[item.block_id],
            zone_type=_legacy_zone_type(item.land_use_type),
            centroid_x=item.centroid_m[0],
            centroid_y=item.centroid_m[1],
            population_capacity=item.population_capacity,
            job_capacity=item.job_capacity,
            leisure_capacity=item.leisure_capacity,
        )
        for item in developed
    )
    pois = tuple(
        POI(
            poi_id=item.poi_id + 1,
            zone_id=zone_id_by_block_id[item.block_id],
            poi_type=item.poi_type,
            node_id=item.access_node_id,
            capacity_hint=item.capacity_hint,
        )
        for item in blueprint.land_use.pois
    )
    node_zone_by_id = _node_zone_assignments(
        nodes=topology.nodes,
        developed=developed,
        zone_id_by_block_id=zone_id_by_block_id,
    )
    zone_node_lists: dict[int, list[int]] = {zone.zone_id: [] for zone in zones}
    for node_id, zone_id in node_zone_by_id.items():
        zone_node_lists[zone_id].append(node_id)
    metadata = {
        "seed": blueprint.seed,
        "zone_count": len(zones),
        "poi_count": len(pois),
        "population_target": sum(zone.population_capacity for zone in zones),
        "zoning_policy": "block_authoritative_v1",
        "poi_placement_policy": "block_centroid_frontage_access_v1",
        "zone_poi_coupling_requested_mode": "block_based_v1",
        "zone_poi_coupling_resolved_mode": "block_based_v1",
        "zone_poi_coupling_fallback_reason": "",
        "zone_poi_coupling_gate_version": "block_land_use_v1",
        "zone_poi_coupling_gate_digest": blueprint.land_use.fingerprint,
        "zone_poi_coupling_anchor_digest": blueprint.blocks.fingerprint,
        "land_use_catalog_fingerprint": blueprint.land_use.fingerprint,
        "city_blueprint_fingerprint": blueprint.fingerprint,
    }
    zoning = ZoningPlacementResult(
        zones=zones,
        pois=pois,
        node_zone_by_id=node_zone_by_id,
        zone_node_ids={
            zone_id: tuple(sorted(node_ids))
            for zone_id, node_ids in zone_node_lists.items()
        },
        metadata=metadata,
    )
    zoning.metadata["zoning_placement_fingerprint"] = zoning_placement_fingerprint(
        zoning
    )
    issues = zoning.validate(topology=topology)
    if issues:
        raise ValueError("realistic block zoning failed: " + "; ".join(issues))
    return zoning


def _evaluate_quality(
    *,
    blueprint: CityBlueprint,
    topology: PreviewCityTopology,
    zoning: ZoningPlacementResult,
) -> RealisticCityQualityResult:
    map_report = require_valid_city_map_contract(
        topology,
        od_sample_count=512,
        seed=blueprint.seed,
    )
    interfaces = topology.node_interfaces.interfaces
    expected_turn_pairs = sum(
        len(interface.incoming_link_ids) * len(interface.outgoing_link_ids)
        for interface in interfaces
    )
    representative_nodes = tuple(
        sorted({poi.node_id for poi in zoning.pois})
    )
    if len(representative_nodes) < 2:
        raise ValueError("realistic zoning requires two distinct POI access nodes")
    representative_report = analyze_directed_reachability(
        nodes=topology.nodes,
        links=topology.links,
        pairs=((representative_nodes[0], representative_nodes[-1]),),
    )
    physical_lengths: dict[int, float] = {}
    for link in topology.links:
        if link.physical_road_id is None:
            raise ValueError("realistic topology link lacks physical_road_id")
        physical_lengths.setdefault(link.physical_road_id, link.length_m)
    metrics: dict[str, int | float | str] = {
        **dict(map_report.metrics),
        "connectivity_repair_link_count": 0,
        "geometry_coverage": len(topology.road_geometry.assignments) / len(topology.links),
        "section_coverage": len(topology.road_sections.assignments) / len(topology.links),
        "node_interface_coverage": len(interfaces) / len(topology.nodes),
        "turn_pair_coverage": len(topology.turns) / max(expected_turn_pairs, 1),
        "representative_zone_pair_count": representative_report.pair_count,
        "representative_zone_pair_reachable_count": (
            representative_report.reachable_pair_count
        ),
        "connectivity_repair_policy": "forbidden_fail_closed",
        "maximum_developed_access_distance_m": (
            blueprint.street_network.max_developed_access_distance_m
        ),
        "physical_segment_median_m": float(
            statistics.median(physical_lengths.values())
        ),
        "physical_segment_under_10m_share": blueprint.blocks.short_segment_share,
        "bounded_block_median_area_m2": blueprint.blocks.median_block_area_m2,
        "bounded_block_p95_area_m2": blueprint.blocks.p95_block_area_m2,
        "developed_block_frontage_coverage": 1.0,
        "industrial_residential_shared_edge_count": (
            blueprint.land_use.industrial_residential_shared_edge_count
        ),
        "essential_access_ratio": blueprint.land_use.essential_access_ratio,
    }
    failures: list[str] = []
    required_one = (
        "geometry_coverage",
        "section_coverage",
        "node_interface_coverage",
        "turn_pair_coverage",
        "developed_block_frontage_coverage",
        "essential_access_ratio",
    )
    if any(not math.isclose(float(metrics[key]), 1.0) for key in required_one):
        failures.append("compiler_or_land_use_coverage")
    if representative_report.reachable_pair_count != representative_report.pair_count:
        failures.append("representative_zone_reachability")
    if int(metrics["weak_component_count"]) != 1:
        failures.append("weak_connectivity")
    if int(metrics["proper_intersection_count"]) != 0:
        failures.append("proper_intersections")
    if int(metrics["industrial_residential_shared_edge_count"]) != 0:
        failures.append("industrial_buffer")
    return RealisticCityQualityResult(
        passed=not failures,
        failure_codes=tuple(failures),
        metrics=metrics,
    )


def _node_zone_assignments(
    *,
    nodes,
    developed: tuple[BlockLandUse, ...],
    zone_id_by_block_id: dict[int, int],
) -> dict[int, int]:
    developed_by_block_id = {block.block_id: block for block in developed}
    block_ids_by_point: dict[tuple[float, float], list[int]] = defaultdict(list)
    for block in developed:
        for point in block.polygon_m[:-1]:
            block_ids_by_point[point].append(block.block_id)
    assignments: dict[int, int] = {}
    for node in nodes:
        candidate_block_ids = block_ids_by_point.get((node.x, node.y), ())
        if candidate_block_ids:
            block_id = min(candidate_block_ids)
        else:
            block_id = min(
                (block.block_id for block in developed),
                key=lambda candidate: (
                    math.dist(
                        (node.x, node.y),
                        developed_by_block_id[candidate].centroid_m,
                    ),
                    candidate,
                ),
            )
        assignments[node.node_id] = zone_id_by_block_id[block_id]
    return assignments


def _bridge_crossings(links) -> tuple[BridgeCrossing, ...]:
    link_ids_by_group: dict[int, list[int]] = defaultdict(list)
    for link in links:
        if link.bridge_group_id is not None:
            link_ids_by_group[link.bridge_group_id].append(link.link_id)
    return tuple(
        BridgeCrossing(
            bridge_group_id=group_id,
            link_ids=tuple(sorted(link_ids)),
            barrier_id=group_id,
            crossing_name=f"synthetic_bridge_{group_id}",
            bottleneck_rank_hint=rank,
        )
        for rank, (group_id, link_ids) in enumerate(
            sorted(link_ids_by_group.items()),
            start=1,
        )
    )


def _legacy_zone_type(land_use_type: BlockLandUseType) -> str:
    return {
        BlockLandUseType.RESIDENTIAL: "residential",
        BlockLandUseType.COMMERCIAL: "cbd_commercial",
        BlockLandUseType.INDUSTRIAL: "industrial",
        BlockLandUseType.MIXED_USE: "mixed_use",
    }[land_use_type]


def _resolve_style_id(*, requested: str, scenario_id: str) -> str:
    if requested != "auto":
        return requested
    return "ring_radial" if scenario_id == "synthetic_100k" else "polycentric_tod"


def _dimensions_for_scenario(scenario_id: str) -> tuple[float, float]:
    if scenario_id == "synthetic_100k":
        return 5_400.0, 4_600.0
    return 4_400.0, 4_000.0
