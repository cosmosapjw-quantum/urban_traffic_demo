"""Fail-closed compilation shared by generated-city topology builders."""

from __future__ import annotations

from metroflow.map.node_compiler import compile_node_interfaces
from metroflow.map.road_geometry import (
    build_endpoint_geometry_catalog,
    count_interior_centerline_intersections,
    validate_geometry_endpoint_anchors,
)
from metroflow.map.section_compiler import compile_road_sections

from .connectivity import repair_weak_connectivity
from .gate_reporting import build_active_sidecar_hierarchy_report
from .generated_map import PreviewCityTopology
from .graph import BridgeCrossing, TurnType
from .map_validation import require_valid_city_map_contract
from .morphology_metrics import MeasurementSpec, compute_street_network_morphometrics
from .morphology_quality import (
    compute_morphology_quality_metrics,
    evaluate_morphology_quality_gate,
    morphology_placement_anchor_digest,
)
from .planarization import planarize_endpoint_topology
from .turn_compiler import compile_turn_authority

__all__ = ["finalize_preview_topology"]


def finalize_preview_topology(
    topology: PreviewCityTopology,
    *,
    require_planar_geometry: bool = False,
) -> PreviewCityTopology:
    """Compile geometry, sections, turns, and validation without hidden fallback."""

    if topology.turns:
        raise ValueError("generated topology finalization requires no precompiled turns")
    repair = repair_weak_connectivity(nodes=topology.nodes, links=topology.links)
    metadata = dict(topology.metadata)
    if repair.repair_link_ids or "weak_component_count_after_repair" not in metadata:
        metadata.update(repair.metadata)
    finalized_nodes = repair.nodes
    finalized_links = repair.links
    finalized_bridge_crossings = topology.bridge_crossings
    if require_planar_geometry:
        preliminary_geometry = build_endpoint_geometry_catalog(
            nodes=finalized_nodes,
            links=finalized_links,
        )
        planarized = planarize_endpoint_topology(
            nodes=finalized_nodes,
            links=finalized_links,
            road_geometry=preliminary_geometry,
        )
        finalized_nodes = planarized.nodes
        finalized_links = planarized.links
        finalized_bridge_crossings = tuple(
            BridgeCrossing(
                bridge_group_id=crossing.bridge_group_id,
                link_ids=tuple(
                    new_link_id
                    for old_link_id in crossing.link_ids
                    for new_link_id in planarized.old_link_to_new_link_ids[old_link_id]
                ),
                barrier_id=crossing.barrier_id,
                crossing_name=crossing.crossing_name,
                bottleneck_rank_hint=crossing.bottleneck_rank_hint,
            )
            for crossing in topology.bridge_crossings
        )
        mapped_repair_ids = tuple(
            new_link_id
            for old_link_id in repair.repair_link_ids
            for new_link_id in planarized.old_link_to_new_link_ids[old_link_id]
        )
        metadata.update(
            {
                "planarization_status": "passed",
                "proper_intersection_count_before_planarization": (
                    planarized.proper_intersection_count_before
                ),
                "proper_intersection_count_after_planarization": (
                    planarized.proper_intersection_count_after
                ),
                "planarization_added_node_count": (
                    planarized.added_intersection_node_count
                ),
                "planarization_admission_status": (
                    "explicit_only_runtime_default_not_promoted"
                ),
                "connectivity_repair_original_link_ids": repair.repair_link_ids,
                "connectivity_repair_link_ids": mapped_repair_ids,
                "connectivity_repair_link_count": len(mapped_repair_ids),
            }
        )
    geometry = build_endpoint_geometry_catalog(
        nodes=finalized_nodes,
        links=finalized_links,
    )
    validate_geometry_endpoint_anchors(
        catalog=geometry,
        nodes=finalized_nodes,
        links=finalized_links,
    )
    road_sections = compile_road_sections(
        links=finalized_links,
        road_geometry=geometry,
    )
    node_interfaces = compile_node_interfaces(
        nodes=finalized_nodes,
        links=finalized_links,
        road_geometry=geometry,
    )
    turn_authority = compile_turn_authority(
        links=finalized_links,
        road_geometry=geometry,
        node_interfaces=node_interfaces,
    )
    intersection_count = count_interior_centerline_intersections(geometry)
    metadata.update(
        {
            "road_geometry_fingerprint": geometry.fingerprint,
            "physical_centerline_count": len(geometry.centerlines),
            "geometry_assignment_count": len(geometry.assignments),
            "unmodeled_centerline_intersection_count": intersection_count,
            "centerline_intersection_audit_status": (
                "validation_gate_passed"
                if require_planar_geometry
                else "diagnostic_not_validation"
            ),
            "road_section_fingerprint": road_sections.fingerprint,
            "road_section_profile_count": len(road_sections.profiles),
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
        }
    )
    finalized = PreviewCityTopology(
        nodes=finalized_nodes,
        links=finalized_links,
        turns=turn_authority.movements,
        bridge_crossings=finalized_bridge_crossings,
        road_geometry=geometry,
        road_sections=road_sections,
        node_interfaces=node_interfaces,
        metadata=metadata,
    )
    report = finalized.validate(require_weak_connectivity=True)
    if not report.ok:
        raise ValueError(f"generated topology finalization failed: {report.summary()}")
    if require_planar_geometry:
        map_report = require_valid_city_map_contract(
            finalized,
            od_sample_count=32,
            seed=int(metadata.get("seed", 0)),
        )
        metadata.update(
            {
                "city_map_validation_status": "passed",
                "city_map_validation_metrics": dict(map_report.metrics),
            }
        )
    # Runtime metadata reports what the compiled topology actually is, not a
    # Boeing-comparable statistic. Named explicitly so nobody reads these numbers
    # against the reference corpus.
    morphometrics = compute_street_network_morphometrics(
        finalized, spec=MeasurementSpec.RUNTIME_COMPILED_DIAGNOSTIC
    )
    quality_metrics = compute_morphology_quality_metrics(finalized)
    placement_anchor_digest = morphology_placement_anchor_digest(
        metadata=metadata,
        nodes=finalized.nodes,
    )
    quality_gate = evaluate_morphology_quality_gate(
        style_id=str(metadata.get("style_id", "unknown")),
        geometry_fingerprint=geometry.fingerprint,
        metrics=quality_metrics,
        placement_anchor_digest=placement_anchor_digest,
    )
    metadata.update(
        {
            "street_network_morphometrics": dict(morphometrics.as_dict()),
            "street_network_morphometrics_status": "diagnostic_not_city_replication",
            "morphology_quality_metrics": dict(quality_metrics.as_dict()),
            "morphology_quality_status": "diagnostic_not_city_replication",
            "morphology_quality_gate": dict(quality_gate.as_dict()),
        }
    )
    if require_planar_geometry and not quality_gate.accepted:
        raise ValueError(
            "generated topology morphology quality gate failed: "
            + "; ".join(quality_gate.failures)
        )
    if "active_sidecar_hierarchy_report" in metadata:
        metadata["active_sidecar_hierarchy_report"] = (
            build_active_sidecar_hierarchy_report(topology=finalized)
        )
    return finalized
