from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

from metroflow.map.road_geometry import (
    RoadGeometryCatalog,
    build_endpoint_geometry_catalog,
    count_interior_centerline_intersections,
    validate_geometry_endpoint_anchors,
)
from metroflow.map.section_compiler import RoadSectionCatalog, compile_road_sections
from metroflow.map.node_compiler import NodeInterfaceCatalog, compile_node_interfaces

from .adversarial_validator import evaluate_adversarial_seed_gate
from .backbone_builder import build_backbone
from .connectivity import repair_weak_connectivity
from .coupling_optimizer import check_coupling_targets, run_coupling_repair_loop
from .district_cells import build_district_cells
from .distributional_batch_gate import evaluate_distributional_batch_gate
from .district_mesh import build_district_mesh, build_district_mesh_from_cells
from .gate_reporting import build_active_sidecar_hierarchy_report, build_sidecar_shadow_comparison_report
from .graph import (
    BridgeCrossing,
    Node,
    NodeKind,
    RoadClass,
    RoadLink,
    RoadNetworkCSR,
    TopologyValidationReport,
    TurnMovement,
    TurnType,
    build_road_network_csr,
    validate_road_network_topology,
)
from .local_fabric import build_local_fabric
from .map_validation import require_valid_city_map_contract
from .morphology_field import build_morphology_field
from .morphology_metrics import compute_street_network_morphometrics
from .morphology_quality import (
    compute_morphology_quality_metrics,
    evaluate_morphology_quality_gate,
    morphology_placement_anchor_digest,
)
from .planarization import planarize_endpoint_topology
from .quality_oracles import evaluate_hard_fail_oracle
from .transit_builder import apply_transit_builder_stage
from .turn_compiler import compile_turn_authority

StageFn = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class PreviewCityTopology:
    nodes: tuple[Node, ...]
    links: tuple[RoadLink, ...]
    turns: tuple[TurnMovement, ...] = ()
    bridge_crossings: tuple[BridgeCrossing, ...] = ()
    road_geometry: RoadGeometryCatalog | None = None
    road_sections: RoadSectionCatalog | None = None
    node_interfaces: NodeInterfaceCatalog | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    _validated: bool = False

    def validate(
        self,
        *,
        require_weak_connectivity: bool = False,
    ) -> TopologyValidationReport:
        report = validate_road_network_topology(
            nodes=self.nodes,
            links=self.links,
            turns=self.turns,
            bridge_crossings=self.bridge_crossings,
            require_weak_connectivity=require_weak_connectivity,
        )
        self._validated = report.ok
        return report

    def build_csr(
        self,
        *,
        validate: bool | None = None,
        require_weak_connectivity: bool = False,
    ) -> RoadNetworkCSR:
        should_validate = (not self._validated) if validate is None else bool(validate)
        return build_road_network_csr(
            nodes=self.nodes,
            links=self.links,
            turns=self.turns,
            bridge_crossings=self.bridge_crossings,
            validate=should_validate,
            require_weak_connectivity=require_weak_connectivity,
        )


@dataclass
class GenerationPipeline:
    style_catalog: StageFn | None = None
    terrain_field: StageFn | None = None
    backbone_builder: StageFn | None = None
    district_mesh: StageFn | None = None
    zoning_solver: StageFn | None = None
    poi_allocator: StageFn | None = None
    transit_builder: StageFn | None = None
    coupling_optimizer: StageFn | None = None
    quality_oracles: StageFn | None = None
    adversarial_validator: StageFn | None = None


class GeneratorV2:
    """Phase-2 orchestration skeleton for v2 city generation."""

    def __init__(self, pipeline: GenerationPipeline | None = None) -> None:
        self.pipeline = pipeline or GenerationPipeline()

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        state = dict(context)
        for stage_name in (
            "style_catalog",
            "terrain_field",
            "backbone_builder",
            "district_mesh",
            "zoning_solver",
            "poi_allocator",
            "transit_builder",
            "coupling_optimizer",
            "quality_oracles",
            "adversarial_validator",
        ):
            fn = getattr(self.pipeline, stage_name)
            if fn is not None:
                state = fn(state)
        return state

    def generate(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self.run(context or {})
        return apply_transit_builder_stage(state)

    def generate_preview_topology(self, context: dict[str, Any] | None = None) -> PreviewCityTopology:
        cfg = dict(context or {})
        scenario_id = str(cfg.get("scenario_id", "synthetic_smoke"))
        seed = int(cfg.get("seed", 0))
        style_id = str(cfg.get("style_id") or _default_style_for_scenario(scenario_id))
        width, height = _dimensions_for_scenario(scenario_id)
        preview_mode = str(cfg.get("preview_mode", "standard"))
        if preview_mode == "sidecar_morphology":
            morphology_field = build_morphology_field(
                scenario_id=scenario_id,
                seed=seed,
                style_id=style_id,
                width=width,
                height=height,
            )
            return _finalize_preview_topology(
                _build_sidecar_morphology_preview_topology(
                    scenario_id=scenario_id,
                    seed=seed,
                    style_id=style_id,
                    morphology_field=morphology_field,
                )
            )
        if preview_mode == "sidecar_district_cells":
            morphology_field = build_morphology_field(
                scenario_id=scenario_id,
                seed=seed,
                style_id=style_id,
                width=width,
                height=height,
            )
            district_cells = build_district_cells(morphology_field=morphology_field)
            district_mesh = build_district_mesh_from_cells(district_cells=district_cells)
            return _finalize_preview_topology(
                _build_sidecar_district_cell_preview_topology(
                    scenario_id=scenario_id,
                    seed=seed,
                    style_id=style_id,
                    morphology_field=morphology_field,
                    district_cells=district_cells,
                    district_mesh=district_mesh,
                )
            )
        if preview_mode in {
            "sidecar_local_fabric",
            "sidecar_local_fabric_planar",
        }:
            morphology_field = build_morphology_field(
                scenario_id=scenario_id,
                seed=seed,
                style_id=style_id,
                width=width,
                height=height,
            )
            district_cells = build_district_cells(morphology_field=morphology_field)
            district_mesh = build_district_mesh_from_cells(district_cells=district_cells)
            local_fabric = build_local_fabric(
                morphology_field=morphology_field,
                district_cells=district_cells,
            )
            return _finalize_preview_topology(
                _build_sidecar_local_fabric_preview_topology(
                    scenario_id=scenario_id,
                    seed=seed,
                    style_id=style_id,
                    morphology_field=morphology_field,
                    district_cells=district_cells,
                    district_mesh=district_mesh,
                    local_fabric=local_fabric,
                ),
                require_planar_geometry=(
                    preview_mode == "sidecar_local_fabric_planar"
                ),
            )
        if preview_mode != "standard":
            raise ValueError(
                "preview_mode must be one of: standard, sidecar_morphology, "
                "sidecar_district_cells, sidecar_local_fabric, "
                "sidecar_local_fabric_planar"
            )
        if style_id not in {"ring_radial", "polycentric_tod"}:
            raise ValueError(
                "standard preview_mode supports only ring_radial or polycentric_tod; "
                "use a sidecar preview_mode for other morphology styles"
            )
        backbone = build_backbone(style_id=style_id, seed=seed, width=width, height=height)
        district_mesh = build_district_mesh(seed=seed, width=width, height=height, backbone=backbone)
        return _finalize_preview_topology(
            _build_preview_topology(
                scenario_id=scenario_id,
                seed=seed,
                style_id=style_id,
                backbone=backbone,
                district_mesh=district_mesh,
            )
        )

    def run_us1_gate_pipeline(
        self,
        *,
        metrics: dict[str, float],
        thresholds: dict[str, float],
        adversarial_seed_reports: list[dict[str, object]],
    ) -> dict[str, object]:
        hard_fail = evaluate_hard_fail_oracle(metrics)
        batch = evaluate_distributional_batch_gate(metrics=metrics, thresholds=thresholds)
        adversarial = evaluate_adversarial_seed_gate(adversarial_seed_reports)
        accepted = (not hard_fail["hard_fail"]) and bool(batch["accepted"]) and bool(adversarial["accepted"])
        return {
            "accepted": accepted,
            "hard_fail_oracle": hard_fail,
            "distributional_batch_gate": batch,
            "adversarial_seed_gate": adversarial,
        }

    def run_us2_coupling_pipeline(
        self,
        *,
        seed: int,
        max_iterations: int,
        metrics: dict[str, float],
        thresholds: dict[str, float],
    ) -> dict[str, object]:
        repair = run_coupling_repair_loop(seed=seed, max_iterations=max_iterations)
        coupling_ok = check_coupling_targets(metrics=metrics, thresholds=thresholds)
        return {
            "repair": repair,
            "coupling_ok": coupling_ok,
        }

    def run_sidecar_shadow_comparison(
        self,
        *,
        scenario_id: str,
        seed: int,
        legacy_engine: str,
        sidecar_engine: str,
        legacy_image_path: str,
        sidecar_image_path: str,
        sidecar_history_path: str,
    ) -> dict[str, object]:
        return build_sidecar_shadow_comparison_report(
            scenario_id=scenario_id,
            seed=int(seed),
            legacy_engine=legacy_engine,
            sidecar_engine=sidecar_engine,
            sidecar_call_path=f"generator_v2.preview_topology.{sidecar_engine.removeprefix('v2_')}",
            legacy_image_path=legacy_image_path,
            sidecar_image_path=sidecar_image_path,
            sidecar_history_path=sidecar_history_path,
        )


def _finalize_preview_topology(
    topology: PreviewCityTopology,
    *,
    require_planar_geometry: bool = False,
) -> PreviewCityTopology:
    if topology.turns:
        raise ValueError(
            "generated topology finalization requires no precompiled turns"
        )
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
    morphometrics = compute_street_network_morphometrics(finalized)
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
        metadata["active_sidecar_hierarchy_report"] = build_active_sidecar_hierarchy_report(
            topology=finalized
        )
    return finalized


def _default_style_for_scenario(scenario_id: str) -> str:
    return "ring_radial" if scenario_id == "synthetic_100k" else "polycentric_tod"


def _dimensions_for_scenario(scenario_id: str) -> tuple[int, int]:
    if scenario_id == "synthetic_100k":
        return (5_400, 4_600)
    return (4_400, 4_000)


def _build_preview_topology(
    *,
    scenario_id: str,
    seed: int,
    style_id: str,
    backbone: dict[str, Any],
    district_mesh: dict[str, Any],
) -> PreviewCityTopology:
    node_builder = _NodeBuilder()
    link_builder = _LinkBuilder(node_builder=node_builder)

    x_levels = tuple(float(value) for value in backbone["x_levels"])
    y_levels = tuple(float(value) for value in backbone["y_levels"])
    bridge_rows = {round(float(value), 3) for value in tuple(backbone.get("bridge_rows", ()))}
    river_bank_x = tuple(float(value) for value in backbone.get("river_bank_x", ()))
    river_left = min(river_bank_x) if river_bank_x else None
    river_right = max(river_bank_x) if river_bank_x else None
    outer_frame_gap_segments = {
        (str(item[0]), int(item[1]), int(item[2]))
        for item in tuple(backbone.get("outer_frame_gap_segments", ()))
    }
    interior_gap_segments = {
        (str(item[0]), int(item[1]), int(item[2]))
        for item in tuple(backbone.get("interior_gap_segments", ()))
    }
    gap_segments = outer_frame_gap_segments | interior_gap_segments

    nodes_by_coord: dict[tuple[float, float], Node] = {}
    for y in y_levels:
        for x in x_levels:
            kind = NodeKind.INTERSECTION
            if abs(x) == max(abs(level) for level in x_levels) or abs(y) == max(abs(level) for level in y_levels):
                kind = NodeKind.INTERCHANGE
            if river_left is not None and (math.isclose(x, river_left) or math.isclose(x, river_right)) and round(y, 3) in bridge_rows:
                kind = NodeKind.BRIDGE_ENDPOINT
            nodes_by_coord[(x, y)] = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=kind,
                x=x,
                y=y,
            )

    bridge_crossings: list[BridgeCrossing] = []
    bridge_group_id = 1
    for row_idx, y in enumerate(y_levels):
        row_nodes = [nodes_by_coord[(x, y)] for x in x_levels]
        for col_idx, (left, right) in enumerate(zip(row_nodes, row_nodes[1:])):
            if ("h", row_idx, col_idx) in gap_segments:
                continue
            if river_left is not None and math.isclose(left.x, river_left) and math.isclose(right.x, river_right):
                if round(y, 3) not in bridge_rows:
                    continue
                bridge_link_ids = _add_bidirectional_link_pair(
                    link_builder,
                    left.node_id,
                    right.node_id,
                    road_class=RoadClass.BRIDGE,
                    lanes=2,
                    speed_mps=17.0,
                    capacity=22.0,
                    bridge_group_id=bridge_group_id,
                )
                bridge_crossings.append(
                    BridgeCrossing(
                        bridge_group_id=bridge_group_id,
                        link_ids=bridge_link_ids,
                        barrier_id=1,
                        crossing_name=f"river_crossing_{bridge_group_id}",
                    )
                )
                bridge_group_id += 1
                continue
            road_class = _horizontal_road_class(y=y, y_levels=y_levels)
            _add_bidirectional_link_pair(
                link_builder,
                left.node_id,
                right.node_id,
                road_class=road_class,
                lanes=_lanes_for_class(road_class),
                speed_mps=_speed_for_class(road_class),
                capacity=_capacity_for_class(road_class),
            )

    for col_idx, x in enumerate(x_levels):
        column_nodes = [nodes_by_coord[(x, y)] for y in y_levels]
        for row_idx, (lower, upper) in enumerate(zip(column_nodes, column_nodes[1:])):
            if ("v", col_idx, row_idx) in gap_segments:
                continue
            road_class = _vertical_road_class(x=x, x_levels=x_levels)
            _add_bidirectional_link_pair(
                link_builder,
                lower.node_id,
                upper.node_id,
                road_class=road_class,
                lanes=_lanes_for_class(road_class),
                speed_mps=_speed_for_class(road_class),
                capacity=_capacity_for_class(road_class),
            )

    outer_x = max(abs(level) for level in x_levels)
    inner_x = _nth_from_end(x_levels, 3)
    outer_y = max(abs(level) for level in y_levels)
    inner_y = _nth_from_end(y_levels, 3)
    ramp_pairs = (
        ((-outer_x, -inner_y), (-inner_x, -outer_y)),
        ((-outer_x, inner_y), (-inner_x, outer_y)),
        ((outer_x, -inner_y), (inner_x, -outer_y)),
        ((outer_x, inner_y), (inner_x, outer_y)),
        ((-inner_x, -outer_y), (-inner_x * 0.55, -inner_y)),
        ((inner_x, -outer_y), (inner_x * 0.55, -inner_y)),
        ((-inner_x, outer_y), (-inner_x * 0.55, inner_y)),
        ((inner_x, outer_y), (inner_x * 0.55, inner_y)),
    )
    for src_coord, dst_coord in ramp_pairs:
        src = _nearest_node(nodes_by_coord, src_coord)
        dst = _nearest_node(nodes_by_coord, dst_coord)
        _add_bidirectional_link_pair(
            link_builder,
            src.node_id,
            dst.node_id,
            road_class=RoadClass.RAMP,
            lanes=1,
            speed_mps=14.0,
            capacity=12.0,
        )

    for src_coord, dst_coord in tuple(backbone.get("frame_cut_in_pairs", ())):
        src = _nearest_node(nodes_by_coord, tuple(src_coord))
        dst = _nearest_node(nodes_by_coord, tuple(dst_coord))
        if src.node_id == dst.node_id:
            continue
        _add_bidirectional_link_pair(
            link_builder,
            src.node_id,
            dst.node_id,
            road_class=RoadClass.EXPRESSWAY,
            lanes=2,
            speed_mps=18.0,
            capacity=18.0,
        )

    for src_coord, dst_coord in tuple(backbone.get("diagonal_spines", ())):
        src = _nearest_node(nodes_by_coord, tuple(src_coord))
        dst = _nearest_node(nodes_by_coord, tuple(dst_coord))
        if src.node_id == dst.node_id:
            continue
        _add_bidirectional_link_pair(
            link_builder,
            src.node_id,
            dst.node_id,
            road_class=RoadClass.ARTERIAL,
            lanes=2,
            speed_mps=15.5,
            capacity=13.0,
        )

    district_infill_link_count = 0
    district_signatures: list[str] = []
    district_curvature_signatures: list[str] = []
    district_mass_scores: list[float] = []
    downtown_hub_ids: set[int] = set()
    landmark_void_node_count = 0
    landmark_roles: set[str] = set()
    irregular_void_cell_count = 0
    texture_profiles: set[str] = set()
    precinct_edge_blend_count = 0
    fringe_spillover_node_count = 0
    shell_fragment_link_count = 0
    terrain_drift_link_count = 0
    district_envelope_erosion_count = 0
    barrier_side_continuity_count = 0
    parcel_irregularity_scores: list[float] = []
    barrier_side_spine_nodes: dict[str, list[Node]] = {"west": [], "east": []}
    north_annulus_nodes: list[Node] = []
    district_records: list[dict[str, Any]] = []
    inter_precinct_connector_count = 0
    mid_annulus_fill_node_count = 0
    district_blend_link_count = 0
    connector_thickening_count = 0
    district_overlap_stitch_count = 0
    secondary_fabric_link_count = 0
    continuous_connector_corridor_count = 0
    precinct_edge_bleed_count = 0
    overlap_mesh_fill_count = 0
    corridor_braid_link_count = 0
    precinct_interior_quilt_count = 0
    downtown_deemphasis_link_count = 0
    corridor_precinct_blend_count = 0
    midfield_parcel_stitch_count = 0
    shell_deboxing_link_count = 0
    shell_fragment_v2_link_count = 0
    interior_street_dissolution_count = 0
    precinct_seam_erosion_count = 0
    outer_shell_collapse_link_count = 0
    precinct_interior_saturation_count = 0
    central_mesh_thickening_count = 0
    side_connector_nodes: dict[str, list[Node]] = {"west": [], "east": []}
    side_spine_nodes: dict[str, list[Node]] = {"west": [], "east": []}
    perimeter_rail_breakup_count = 0
    precinct_bridge_saturation_count = 0
    interior_web_thickening_count = 0
    precinct_mass_breakup_count = 0
    distributed_sub_block_stitch_count = 0
    interior_field_equalization_count = 0
    precinct_cluster_smoothing_count = 0
    continuous_local_street_fill_count = 0
    core_ring_fabric_consolidation_count = 0
    small_map_core_dering_count = 0
    midfield_local_web_saturation_count = 0
    scaffold_rail_attenuation_count = 0
    smoke_precinct_declustering_count = 0
    large_map_scaffold_dissolution_count = 0
    inner_annulus_mesh_equalization_count = 0
    outer_rail_attenuation_v2_count = 0
    interior_fabric_densification_count = 0
    precinct_shell_dissolution_count = 0
    diagonal_shell_breakup_count = 0
    continuous_inner_weave_count = 0
    precinct_mass_deemphasis_count = 0
    quadrant_rail_dissolution_count = 0
    precinct_starburst_attenuation_count = 0
    annulus_core_threading_count = 0
    quadrant_interior_knitting_count = 0
    precinct_knot_flattening_count = 0
    distributed_local_texture_count = 0
    quadrant_local_mesh_stitch_count = 0
    precinct_core_destarburst_count = 0
    distributed_secondary_street_fill_count = 0
    outer_shell_rail_thinning_count = 0
    precinct_shell_mesh_blending_count = 0
    distributed_tertiary_street_fill_count = 0
    shell_silhouette_collapse_count = 0
    precinct_boundary_dissolution_count = 0
    fine_grain_street_texture_count = 0
    shell_silhouette_deemphasis_count = 0
    precinct_knot_diffusion_count = 0
    distributed_fine_grain_weave_count = 0
    shell_arc_softening_count = 0
    precinct_knot_diffusion_v2_count = 0
    interior_weave_continuity_count = 0
    shell_arc_fading_count = 0
    precinct_knot_bleed_count = 0
    weave_corridor_threading_count = 0
    for district in tuple(district_mesh.get("districts", ())):
        center_x = float(tuple(district["center"])[0])
        center_y = float(tuple(district["center"])[1])
        radius = float(district.get("radius", 220.0))
        massing_scale = float(district.get("massing_scale", 1.0))
        density_retention = str(district.get("density_retention", ""))
        contrast_tier = str(district.get("small_map_contrast_tier", ""))
        landmark_role = str(district.get("landmark_role", ""))
        void_template = str(district.get("void_template", ""))
        taper_priority = float(district.get("taper_priority", 0.6))
        texture_profile = str(district.get("texture_profile", ""))
        edge_blend_bias = float(district.get("edge_blend_bias", 0.68))
        envelope_erosion_bias = float(district.get("envelope_erosion_bias", 0.54))
        barrier_continuity_bias = float(district.get("barrier_continuity_bias", 0.66))
        parcel_irregularity_tier = str(district.get("parcel_irregularity_tier", "medium"))
        connector_bias = float(district.get("connector_bias", 0.70))
        mid_annulus_fill_bias = float(district.get("mid_annulus_fill_bias", 0.72))
        district_blend_bias = float(district.get("district_blend_bias", 0.68))
        shell_fragment_v2_bias = float(district.get("shell_fragment_v2_bias", 0.70))
        interior_dissolve_bias = float(district.get("interior_dissolve_bias", 0.72))
        precinct_seam_erosion_bias = float(district.get("precinct_seam_erosion_bias", 0.70))
        outer_shell_collapse_bias = float(district.get("outer_shell_collapse_bias", 0.72))
        interior_saturation_bias = float(district.get("interior_saturation_bias", 0.74))
        central_mesh_thickening_bias = float(district.get("central_mesh_thickening_bias", 0.72))
        perimeter_rail_breakup_bias = float(district.get("perimeter_rail_breakup_bias", 0.76))
        precinct_bridge_saturation_bias = float(district.get("precinct_bridge_saturation_bias", 0.74))
        interior_web_thickening_bias = float(district.get("interior_web_thickening_bias", 0.76))
        precinct_mass_breakup_bias = float(district.get("precinct_mass_breakup_bias", 0.78))
        sub_block_stitch_bias = float(district.get("sub_block_stitch_bias", 0.76))
        interior_field_equalization_bias = float(district.get("interior_field_equalization_bias", 0.78))
        precinct_cluster_smoothing_bias = float(district.get("precinct_cluster_smoothing_bias", 0.78))
        continuous_local_fill_bias = float(district.get("continuous_local_fill_bias", 0.76))
        core_ring_fabric_consolidation_bias = float(district.get("core_ring_fabric_consolidation_bias", 0.78))
        small_map_core_dering_bias = float(district.get("small_map_core_dering_bias", 0.76))
        midfield_local_web_saturation_bias = float(district.get("midfield_local_web_saturation_bias", 0.78))
        scaffold_rail_attenuation_bias = float(district.get("scaffold_rail_attenuation_bias", 0.74))
        smoke_precinct_declustering_bias = float(district.get("smoke_precinct_declustering_bias", 0.78))
        large_map_scaffold_dissolution_bias = float(district.get("large_map_scaffold_dissolution_bias", 0.76))
        inner_annulus_mesh_equalization_bias = float(district.get("inner_annulus_mesh_equalization_bias", 0.78))
        outer_rail_attenuation_v2_bias = float(district.get("outer_rail_attenuation_v2_bias", 0.78))
        interior_fabric_densification_bias = float(district.get("interior_fabric_densification_bias", 0.80))
        precinct_shell_dissolution_bias = float(district.get("precinct_shell_dissolution_bias", 0.78))
        diagonal_shell_breakup_bias = float(district.get("diagonal_shell_breakup_bias", 0.80))
        continuous_inner_weave_bias = float(district.get("continuous_inner_weave_bias", 0.82))
        precinct_mass_deemphasis_bias = float(district.get("precinct_mass_deemphasis_bias", 0.78))
        quadrant_rail_dissolution_bias = float(district.get("quadrant_rail_dissolution_bias", 0.80))
        precinct_starburst_attenuation_bias = float(district.get("precinct_starburst_attenuation_bias", 0.82))
        annulus_core_threading_bias = float(district.get("annulus_core_threading_bias", 0.84))
        quadrant_interior_knitting_bias = float(district.get("quadrant_interior_knitting_bias", 0.82))
        precinct_knot_flattening_bias = float(district.get("precinct_knot_flattening_bias", 0.80))
        distributed_local_texture_bias = float(district.get("distributed_local_texture_bias", 0.84))
        quadrant_local_mesh_stitch_bias = float(district.get("quadrant_local_mesh_stitch_bias", 0.82))
        precinct_core_destarburst_bias = float(district.get("precinct_core_destarburst_bias", 0.80))
        distributed_secondary_street_fill_bias = float(district.get("distributed_secondary_street_fill_bias", 0.84))
        outer_shell_rail_thinning_bias = float(district.get("outer_shell_rail_thinning_bias", 0.82))
        precinct_shell_mesh_blend_bias = float(district.get("precinct_shell_mesh_blend_bias", 0.80))
        distributed_tertiary_street_fill_bias = float(district.get("distributed_tertiary_street_fill_bias", 0.84))
        shell_silhouette_collapse_bias = float(district.get("shell_silhouette_collapse_bias", 0.86))
        precinct_boundary_dissolution_bias = float(district.get("precinct_boundary_dissolution_bias", 0.84))
        fine_grain_street_texture_bias = float(district.get("fine_grain_street_texture_bias", 0.88))
        shell_silhouette_deemphasis_bias = float(district.get("shell_silhouette_deemphasis_bias", 0.90))
        precinct_knot_diffusion_bias = float(district.get("precinct_knot_diffusion_bias", 0.88))
        distributed_fine_grain_weave_bias = float(district.get("distributed_fine_grain_weave_bias", 0.92))
        shell_arc_softening_bias = float(district.get("shell_arc_softening_bias", 0.92))
        precinct_knot_diffusion_v2_bias = float(district.get("precinct_knot_diffusion_v2_bias", 0.90))
        interior_weave_continuity_bias = float(district.get("interior_weave_continuity_bias", 0.94))
        shell_arc_fading_bias = float(district.get("shell_arc_fading_bias", 0.94))
        precinct_knot_bleed_bias = float(district.get("precinct_knot_bleed_bias", 0.92))
        weave_corridor_threading_bias = float(district.get("weave_corridor_threading_bias", 0.96))
        if landmark_role:
            landmark_roles.add(landmark_role)
        if texture_profile:
            texture_profiles.add(texture_profile)
        hub_nodes: list[Node] = []
        for hub_dx, hub_dy in tuple(district.get("hub_offsets", ((0.0, 0.0),))):
            hub_nodes.append(
                _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=center_x + float(hub_dx),
                    y=center_y + float(hub_dy),
                )
            )
        if not hub_nodes:
            hub_nodes.append(
                _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=center_x,
                    y=center_y,
                )
            )
        if str(district.get("kind", "")) == "downtown":
            downtown_hub_ids.update(int(node.node_id) for node in hub_nodes)

        for current, nxt in zip(hub_nodes, hub_nodes[1:]):
            _add_bidirectional_link_pair(
                link_builder,
                current.node_id,
                nxt.node_id,
                road_class=RoadClass.COLLECTOR,
                lanes=1,
                speed_mps=11.5,
                capacity=7.5,
            )
            district_infill_link_count += 2

        connector_angles = tuple(float(value) for value in district.get("connector_angles", ()))
        curvature_bias = float(district.get("curvature_bias", 0.0))
        anchor_nodes: list[Node] = []
        for angle_idx, angle in enumerate(connector_angles):
            radial_scale = 0.78 + ((angle_idx % 3) * 0.09)
            ellipse_x = 1.0 + (0.12 if (angle_idx % 2) == 0 else -0.08)
            ellipse_y = 1.0 + (0.10 if (angle_idx % 3) == 1 else -0.06)
            anchor = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=center_x + math.cos(angle) * radius * radial_scale * ellipse_x,
                y=center_y + math.sin(angle) * radius * radial_scale * ellipse_y,
            )
            anchor_nodes.append(anchor)
            hub = hub_nodes[angle_idx % len(hub_nodes)]
            bend_x, bend_y = _curved_midpoint(
                (float(hub.x), float(hub.y)),
                (float(anchor.x), float(anchor.y)),
                bias=curvature_bias * (1.0 if (angle_idx % 2) == 0 else -1.0),
            )
            bend = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=bend_x,
                y=bend_y,
            )
            if bend.node_id != hub.node_id:
                taper_class, taper_speed, taper_capacity = _taper_profile(taper_priority=taper_priority, major=False)
                _add_bidirectional_link_pair(
                    link_builder,
                    hub.node_id,
                    bend.node_id,
                    road_class=taper_class,
                    lanes=1,
                    speed_mps=taper_speed,
                    capacity=taper_capacity,
                )
                district_infill_link_count += 2
            if bend.node_id != anchor.node_id:
                taper_class, taper_speed, taper_capacity = _taper_profile(taper_priority=taper_priority, major=True)
                _add_bidirectional_link_pair(
                    link_builder,
                    bend.node_id,
                    anchor.node_id,
                    road_class=taper_class,
                    lanes=1,
                    speed_mps=taper_speed,
                    capacity=taper_capacity,
                )
                district_infill_link_count += 2

        perimeter_gap_indices = {1 if str(district.get("river_side", "")) == "west" else 3}
        if contrast_tier == "void":
            perimeter_gap_indices.add(0)
        for idx, current in enumerate(anchor_nodes):
            nxt = anchor_nodes[(idx + 1) % len(anchor_nodes)]
            if idx in perimeter_gap_indices:
                continue
            _add_bidirectional_link_pair(
                link_builder,
                current.node_id,
                nxt.node_id,
                road_class=RoadClass.COLLECTOR,
                lanes=1,
                speed_mps=12.0,
                capacity=8.0,
            )
            district_infill_link_count += 2
        for idx, current in enumerate(anchor_nodes):
            nxt = anchor_nodes[(idx + 2) % len(anchor_nodes)]
            if idx % 2 == 1:
                continue
            _add_bidirectional_link_pair(
                link_builder,
                current.node_id,
                nxt.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.7,
                capacity=5.6,
            )
            district_infill_link_count += 2

        primary_hub = hub_nodes[0]
        connector_target = _nearest_grid_node(nodes_by_coord, (center_x, center_y))
        if connector_target.node_id != primary_hub.node_id:
            _add_bidirectional_link_pair(
                link_builder,
                primary_hub.node_id,
                connector_target.node_id,
                road_class=RoadClass.COLLECTOR,
                lanes=1,
                speed_mps=11.0,
                capacity=7.5,
            )
            district_infill_link_count += 2

        district_signatures.append(str(district.get("signature", "")))
        district_curvature_signatures.append(str(district.get("curvature_signature", "")))
        block_grid_xs = tuple(float(value) for value in district.get("block_grid_xs", ()))
        block_grid_ys = tuple(float(value) for value in district.get("block_grid_ys", ()))
        district_local_nodes = 0
        district_local_links = 0
        if block_grid_xs and block_grid_ys:
            lattice: list[list[Node]] = []
            for y in block_grid_ys:
                row: list[Node] = []
                for x in block_grid_xs:
                    row.append(
                        _get_or_add_node(
                            nodes_by_coord=nodes_by_coord,
                            node_builder=node_builder,
                            kind=NodeKind.INTERSECTION,
                            x=x,
                            y=y,
                        )
                    )
                    district_local_nodes += 1
                lattice.append(row)
            void_cells = _void_cells(rows=len(lattice) - 1, cols=len(lattice[0]) - 1, template=void_template)
            irregular_void_cell_count += len(void_cells)
            for row_idx, row in enumerate(lattice):
                for col_idx, (left, right) in enumerate(zip(row, row[1:])):
                    if _skip_horizontal_edge(void_cells, row_idx, col_idx):
                        continue
                    _add_bidirectional_link_pair(
                        link_builder,
                        left.node_id,
                        right.node_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.5,
                        capacity=5.5,
                    )
                    district_infill_link_count += 2
                    district_local_links += 2
            for row_idx, (upper_row, lower_row) in enumerate(zip(lattice, lattice[1:])):
                for col_idx, (upper, lower) in enumerate(zip(upper_row, lower_row)):
                    if _skip_vertical_edge(void_cells, row_idx, col_idx):
                        continue
                    _add_bidirectional_link_pair(
                        link_builder,
                        upper.node_id,
                        lower.node_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.5,
                        capacity=5.5,
                    )
                    district_infill_link_count += 2
                    district_local_links += 2
            for row_idx, (upper_row, lower_row) in enumerate(zip(lattice, lattice[1:])):
                for col_idx, (upper, lower) in enumerate(zip(upper_row, lower_row[1:])):
                    if (row_idx, col_idx) in void_cells:
                        continue
                    _add_bidirectional_link_pair(
                        link_builder,
                        upper.node_id,
                        lower.node_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.0,
                        capacity=5.0,
                    )
                    district_infill_link_count += 2
                    district_local_links += 2
                for col_idx, (upper, lower) in enumerate(zip(upper_row[1:], lower_row)):
                    if (row_idx, col_idx) in void_cells:
                        continue
                    _add_bidirectional_link_pair(
                        link_builder,
                        upper.node_id,
                        lower.node_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.0,
                        capacity=5.0,
                    )
                    district_infill_link_count += 2
                    district_local_links += 2
            if str(district.get("river_side", "")) == "west":
                for row in lattice:
                    for left, mid in zip(row, row[2:]):
                        _add_bidirectional_link_pair(
                            link_builder,
                            left.node_id,
                            mid.node_id,
                            road_class=RoadClass.LOCAL,
                            lanes=1,
                            speed_mps=7.8,
                            capacity=4.8,
                        )
                        district_infill_link_count += 2
                        district_local_links += 2
            elif str(district.get("river_side", "")) == "east":
                for upper_row, lower_row in zip(lattice, lattice[2:]):
                    for upper, lower in zip(upper_row, lower_row):
                        _add_bidirectional_link_pair(
                            link_builder,
                            upper.node_id,
                            lower.node_id,
                            road_class=RoadClass.LOCAL,
                            lanes=1,
                            speed_mps=7.8,
                            capacity=4.8,
                        )
                        district_infill_link_count += 2
                        district_local_links += 2
            if density_retention == "dense_wedge":
                for row_idx, row in enumerate(lattice):
                    for left, right in zip(row, row[2:]):
                        if (row_idx % 2) == 1:
                            continue
                        _add_bidirectional_link_pair(
                            link_builder,
                            left.node_id,
                            right.node_id,
                            road_class=RoadClass.LOCAL,
                            lanes=1,
                            speed_mps=7.9,
                            capacity=4.9,
                        )
                        district_infill_link_count += 2
                        district_local_links += 2
            elif density_retention == "split_band":
                mid_idx = len(lattice) // 2
                for row in lattice[max(0, mid_idx - 1) : min(len(lattice), mid_idx + 2)]:
                    for left, right in zip(row, row[1:]):
                        _add_bidirectional_link_pair(
                            link_builder,
                            left.node_id,
                            right.node_id,
                            road_class=RoadClass.COLLECTOR,
                            lanes=1,
                            speed_mps=9.2,
                            capacity=6.2,
                        )
                        district_infill_link_count += 2
                        district_local_links += 2
            elif density_retention == "hub_pockets":
                for hub in hub_nodes:
                    for dx, dy in ((22.0, -18.0), (-18.0, 26.0), (28.0, 24.0)):
                        pocket = _get_or_add_node(
                            nodes_by_coord=nodes_by_coord,
                            node_builder=node_builder,
                            kind=NodeKind.INTERSECTION,
                            x=float(hub.x) + dx * massing_scale,
                            y=float(hub.y) + dy * (0.82 if float(hub.x) < center_x else 1.0),
                        )
                        district_local_nodes += 1
                        _add_bidirectional_link_pair(
                            link_builder,
                            hub.node_id,
                            pocket.node_id,
                            road_class=RoadClass.LOCAL,
                            lanes=1,
                            speed_mps=8.4,
                            capacity=5.2,
                        )
                        district_infill_link_count += 2
                        district_local_links += 2
                        nearest_grid = _nearest_grid_node(nodes_by_coord, (pocket.x, pocket.y))
                        if nearest_grid.node_id != pocket.node_id:
                            _add_bidirectional_link_pair(
                                link_builder,
                                pocket.node_id,
                                nearest_grid.node_id,
                                road_class=RoadClass.LOCAL,
                                lanes=1,
                                speed_mps=8.1,
                                capacity=5.0,
                            )
                            district_infill_link_count += 2
                            district_local_links += 2
            elif density_retention == "landmark_cluster":
                for hub in hub_nodes:
                    landmark_nodes: list[Node] = []
                    for dx, dy in ((0.0, -34.0), (26.0, 18.0), (-28.0, 22.0), (0.0, 38.0), (34.0, -8.0), (-38.0, -6.0)):
                        pocket = _get_or_add_node(
                            nodes_by_coord=nodes_by_coord,
                            node_builder=node_builder,
                            kind=NodeKind.INTERSECTION,
                            x=float(hub.x) + dx * massing_scale,
                            y=float(hub.y) + dy * massing_scale,
                        )
                        landmark_nodes.append(pocket)
                        landmark_void_node_count += 1
                        district_local_nodes += 1
                        _add_bidirectional_link_pair(
                            link_builder,
                            hub.node_id,
                            pocket.node_id,
                            road_class=RoadClass.COLLECTOR,
                            lanes=1,
                            speed_mps=9.6,
                            capacity=6.1,
                        )
                        district_infill_link_count += 2
                        district_local_links += 2
                    if contrast_tier == "landmark":
                        fringe_nodes: list[Node] = []
                        for dx, dy in ((86.0, 34.0), (104.0, -12.0), (58.0, 88.0), (132.0, 28.0), (76.0, 128.0), (118.0, 96.0), (146.0, 68.0)):
                            fringe = _get_or_add_node(
                                nodes_by_coord=nodes_by_coord,
                                node_builder=node_builder,
                                kind=NodeKind.INTERSECTION,
                                x=float(hub.x) + dx * massing_scale,
                                y=float(hub.y) + dy * massing_scale,
                            )
                            fringe_nodes.append(fringe)
                            landmark_void_node_count += 1
                            district_local_nodes += 1
                            _add_bidirectional_link_pair(
                                link_builder,
                                hub.node_id,
                                fringe.node_id,
                                road_class=RoadClass.ARTERIAL,
                                lanes=1,
                                speed_mps=10.4,
                                capacity=6.4,
                            )
                            district_infill_link_count += 2
                            district_local_links += 2
                        if center_x > 0.0 and center_y > 0.0:
                            for dx, dy in ((168.0, 108.0), (192.0, 42.0), (142.0, 154.0), (214.0, 96.0), (236.0, 132.0)):
                                fringe = _get_or_add_node(
                                    nodes_by_coord=nodes_by_coord,
                                    node_builder=node_builder,
                                    kind=NodeKind.INTERSECTION,
                                    x=float(hub.x) + dx * massing_scale,
                                    y=float(hub.y) + dy * massing_scale,
                                )
                                fringe_nodes.append(fringe)
                                landmark_void_node_count += 1
                                district_local_nodes += 1
                                _add_bidirectional_link_pair(
                                    link_builder,
                                    hub.node_id,
                                    fringe.node_id,
                                    road_class=RoadClass.ARTERIAL,
                                    lanes=1,
                                    speed_mps=10.6,
                                    capacity=6.6,
                                )
                                district_infill_link_count += 2
                                district_local_links += 2
                        for current, nxt in zip(landmark_nodes, landmark_nodes[1:] + landmark_nodes[:1]):
                            if current.node_id == nxt.node_id:
                                continue
                            _add_bidirectional_link_pair(
                                link_builder,
                                current.node_id,
                                nxt.node_id,
                                road_class=RoadClass.COLLECTOR,
                                lanes=1,
                                speed_mps=9.8,
                                capacity=6.0,
                            )
                            district_infill_link_count += 2
                            district_local_links += 2
                        for current, nxt in zip(fringe_nodes, fringe_nodes[1:] + fringe_nodes[:1]):
                            if current.node_id == nxt.node_id:
                                continue
                            _add_bidirectional_link_pair(
                                link_builder,
                                current.node_id,
                                nxt.node_id,
                                road_class=RoadClass.COLLECTOR,
                                lanes=1,
                                speed_mps=9.8,
                                capacity=6.0,
                            )
                            district_infill_link_count += 2
                            district_local_links += 2
            elif density_retention == "void_band":
                if len(lattice) >= 3:
                    band_row = len(lattice) // 2
                    for left, right in zip(lattice[band_row][::2], lattice[band_row][1::2]):
                        _add_bidirectional_link_pair(
                            link_builder,
                            left.node_id,
                            right.node_id,
                            road_class=RoadClass.COLLECTOR,
                            lanes=1,
                            speed_mps=9.0,
                            capacity=5.8,
                        )
                        district_infill_link_count += 2
                        district_local_links += 2
            if landmark_role and landmark_role not in {"", "civic_core"}:
                for hub in hub_nodes[:1]:
                    landmark_markers: list[Node] = []
                    for dx, dy in _landmark_offsets(landmark_role):
                        marker = _get_or_add_node(
                            nodes_by_coord=nodes_by_coord,
                            node_builder=node_builder,
                            kind=NodeKind.INTERSECTION,
                            x=float(hub.x) + dx,
                            y=float(hub.y) + dy,
                        )
                        landmark_markers.append(marker)
                        landmark_void_node_count += 1
                        district_local_nodes += 1
                        _add_bidirectional_link_pair(
                            link_builder,
                            hub.node_id,
                            marker.node_id,
                            road_class=RoadClass.COLLECTOR,
                            lanes=1,
                            speed_mps=9.6,
                            capacity=6.0,
                        )
                        district_infill_link_count += 2
                        district_local_links += 2
                    if scenario_id == "synthetic_100k":
                        large_map_markers: list[Node] = []
                        for dx, dy in _landmark_offsets_large_map(landmark_role):
                            marker = _get_or_add_node(
                                nodes_by_coord=nodes_by_coord,
                                node_builder=node_builder,
                                kind=NodeKind.INTERSECTION,
                                x=float(hub.x) + dx,
                                y=float(hub.y) + dy,
                            )
                            large_map_markers.append(marker)
                            landmark_void_node_count += 1
                            district_local_nodes += 1
                            _add_bidirectional_link_pair(
                                link_builder,
                                hub.node_id,
                                marker.node_id,
                                road_class=RoadClass.ARTERIAL,
                                lanes=1,
                                speed_mps=10.2,
                                capacity=6.4,
                            )
                            district_infill_link_count += 2
                            district_local_links += 2
                        for current, nxt in zip(large_map_markers, large_map_markers[1:]):
                            if current.node_id == nxt.node_id:
                                continue
                            _add_bidirectional_link_pair(
                                link_builder,
                                current.node_id,
                                nxt.node_id,
                                road_class=RoadClass.COLLECTOR,
                                lanes=1,
                                speed_mps=9.8,
                                capacity=6.0,
                            )
                            district_infill_link_count += 2
                            district_local_links += 2
                        for marker in large_map_markers[:2]:
                            nearest_grid = _nearest_grid_node(nodes_by_coord, (marker.x, marker.y))
                            if nearest_grid.node_id == marker.node_id:
                                continue
                            _add_bidirectional_link_pair(
                                link_builder,
                                marker.node_id,
                                nearest_grid.node_id,
                                road_class=RoadClass.COLLECTOR,
                                lanes=1,
                                speed_mps=9.4,
                                capacity=5.8,
                            )
                            district_infill_link_count += 2
                            district_local_links += 2
                    if len(landmark_markers) >= 2:
                        for current, nxt in zip(landmark_markers, landmark_markers[1:]):
                            if current.node_id == nxt.node_id:
                                continue
                            _add_bidirectional_link_pair(
                                link_builder,
                                current.node_id,
                                nxt.node_id,
                                road_class=RoadClass.LOCAL,
                                lanes=1,
                                speed_mps=8.6,
                                capacity=5.2,
                            )
                            district_infill_link_count += 2
                            district_local_links += 2
            if massing_scale >= 1.05:
                for row_idx in range(len(lattice) - 1):
                    for col_idx in range(len(lattice[row_idx]) - 1):
                        top_left = lattice[row_idx][col_idx]
                        top_right = lattice[row_idx][col_idx + 1]
                        bottom_left = lattice[row_idx + 1][col_idx]
                        bottom_right = lattice[row_idx + 1][col_idx + 1]
                        diag_a, diag_b = (
                            (top_left, bottom_right)
                            if (row_idx + col_idx) % 2 == 0
                            else (top_right, bottom_left)
                        )
                        _add_bidirectional_link_pair(
                            link_builder,
                            diag_a.node_id,
                            diag_b.node_id,
                            road_class=RoadClass.LOCAL,
                            lanes=1,
                            speed_mps=8.2,
                            capacity=5.1,
                        )
                        district_infill_link_count += 2
                        district_local_links += 2
            lattice_center = lattice[len(lattice) // 2][len(lattice[0]) // 2]
            if lattice_center.node_id != primary_hub.node_id and contrast_tier != "void":
                _add_bidirectional_link_pair(
                    link_builder,
                    primary_hub.node_id,
                    lattice_center.node_id,
                    road_class=RoadClass.COLLECTOR,
                    lanes=1,
                    speed_mps=10.5,
                    capacity=6.5,
                )
                district_infill_link_count += 2
                district_local_links += 2
            if density_retention == "dense_core":
                for hub in hub_nodes[1:2]:
                    if hub.node_id == lattice_center.node_id:
                        continue
                    _add_bidirectional_link_pair(
                        link_builder,
                        hub.node_id,
                        lattice_center.node_id,
                        road_class=RoadClass.COLLECTOR,
                        lanes=1,
                        speed_mps=10.6,
                        capacity=6.6,
                    )
                    district_infill_link_count += 2
                    district_local_links += 2
            corner_samples = (
                (lattice[0][0], lattice[0][-1])
                if contrast_tier == "void"
                else (
                    lattice[0][0],
                    lattice[0][-1],
                    lattice[-1][0],
                    lattice[-1][-1],
                    lattice[len(lattice) // 2][0],
                    lattice[len(lattice) // 2][-1],
                )
            )
            for corner in corner_samples:
                nearest_grid = _nearest_grid_node(nodes_by_coord, (corner.x, corner.y))
                if nearest_grid.node_id == corner.node_id:
                    continue
                _add_bidirectional_link_pair(
                    link_builder,
                    corner.node_id,
                    nearest_grid.node_id,
                    road_class=RoadClass.COLLECTOR,
                    lanes=1,
                    speed_mps=10.5,
                    capacity=6.5,
                )
                district_infill_link_count += 2
                district_local_links += 2
            river_side = str(district.get("river_side", "west" if center_x < 0.0 else "east"))
            side_sign = -1.0 if river_side == "west" else 1.0
            side_edge_nodes = [row[0] if river_side == "west" else row[-1] for row in lattice]
            erosion_sources = (
                side_edge_nodes[0],
                side_edge_nodes[len(side_edge_nodes) // 2],
                side_edge_nodes[-1],
            )
            erosion_nodes: list[Node] = []
            for source, (dx, dy) in zip(
                erosion_sources,
                _envelope_erosion_offsets(
                    bias=envelope_erosion_bias,
                    tier=parcel_irregularity_tier,
                    river_side=river_side,
                ),
            ):
                erosion = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=float(source.x) + dx,
                    y=float(source.y) + dy,
                )
                erosion_nodes.append(erosion)
                district_local_nodes += 1
                _add_bidirectional_link_pair(
                    link_builder,
                    source.node_id,
                    erosion.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.1,
                    capacity=4.9,
                )
                district_infill_link_count += 2
                district_local_links += 2
                district_envelope_erosion_count += 1
            for current, nxt in zip(erosion_nodes, erosion_nodes[1:]):
                if current.node_id == nxt.node_id:
                    continue
                _add_bidirectional_link_pair(
                    link_builder,
                    current.node_id,
                    nxt.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=7.8,
                    capacity=4.8,
                )
                district_infill_link_count += 2
                district_local_links += 2
                district_envelope_erosion_count += 1
            if scenario_id == "synthetic_100k" and erosion_nodes:
                if center_y > 0.0:
                    crest_templates = ((erosion_nodes[0], 28.0, 102.0), (erosion_nodes[-1], 18.0, 146.0))
                else:
                    crest_templates = ((erosion_nodes[len(erosion_nodes) // 2], 18.0, -88.0),)
                crest_nodes: list[Node] = []
                for source, dx_mag, dy in crest_templates:
                    crest = _get_or_add_node(
                        nodes_by_coord=nodes_by_coord,
                        node_builder=node_builder,
                        kind=NodeKind.INTERSECTION,
                        x=float(source.x) + side_sign * dx_mag * (1.0 + envelope_erosion_bias * 0.42),
                        y=float(source.y) + dy * (0.82 + envelope_erosion_bias * 0.28),
                    )
                    district_local_nodes += 1
                    _add_bidirectional_link_pair(
                        link_builder,
                        source.node_id,
                        crest.node_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=7.8,
                        capacity=4.8,
                    )
                    district_infill_link_count += 2
                    district_local_links += 2
                    district_envelope_erosion_count += 1
                    crest_nodes.append(crest)
                    if center_y > 0.0:
                        north_annulus_nodes.append(crest)
                if center_y > 0.0:
                    for ridge_idx, crest in enumerate(crest_nodes):
                        ridge = _get_or_add_node(
                            nodes_by_coord=nodes_by_coord,
                            node_builder=node_builder,
                            kind=NodeKind.INTERSECTION,
                            x=float(crest.x) + side_sign * (14.0 + ridge_idx * 10.0),
                            y=float(crest.y) + 86.0 + ridge_idx * 28.0,
                        )
                        district_local_nodes += 1
                        _add_bidirectional_link_pair(
                            link_builder,
                            crest.node_id,
                            ridge.node_id,
                            road_class=RoadClass.LOCAL,
                            lanes=1,
                            speed_mps=7.6,
                            capacity=4.7,
                        )
                        district_infill_link_count += 2
                        district_local_links += 2
                        district_envelope_erosion_count += 1
                        north_annulus_nodes.append(ridge)
                    for current, nxt in zip(crest_nodes, crest_nodes[1:]):
                        if current.node_id == nxt.node_id:
                            continue
                        _add_bidirectional_link_pair(
                            link_builder,
                            current.node_id,
                            nxt.node_id,
                            road_class=RoadClass.LOCAL,
                            lanes=1,
                            speed_mps=7.9,
                            capacity=4.9,
                        )
                        district_infill_link_count += 2
                        district_local_links += 2
            continuity_sources = (
                side_edge_nodes[max(0, len(side_edge_nodes) // 3)],
                side_edge_nodes[min(len(side_edge_nodes) - 1, (len(side_edge_nodes) * 2) // 3)],
            )
            continuity_offsets = (
                (-radius * 0.34, -radius * 0.18),
                (radius * 0.32, radius * 0.22),
            )
            for source, (_, y_shift) in zip(continuity_sources, continuity_offsets):
                continuity = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=float(source.x) + side_sign * (44.0 + 48.0 * barrier_continuity_bias),
                    y=float(source.y) + y_shift,
                )
                barrier_side_spine_nodes[river_side].append(continuity)
                district_local_nodes += 1
                _add_bidirectional_link_pair(
                    link_builder,
                    source.node_id,
                    continuity.node_id,
                    road_class=RoadClass.COLLECTOR,
                    lanes=1,
                    speed_mps=9.3,
                    capacity=5.9,
                )
                district_infill_link_count += 2
                district_local_links += 2
                barrier_side_continuity_count += 1
            blend_edge_nodes = _lattice_edge_nodes(lattice)
            interior_grid_nodes = _interior_lattice_nodes(lattice)
            halo_nodes: list[Node] = []
            for edge_idx, (dx, dy) in enumerate(_texture_halo_offsets(texture_profile)):
                halo = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=center_x + dx * massing_scale,
                    y=center_y + dy * massing_scale,
                )
                halo_nodes.append(halo)
                district_local_nodes += 1
                edge_node = blend_edge_nodes[edge_idx % len(blend_edge_nodes)]
                blend_class = RoadClass.COLLECTOR if edge_blend_bias >= 0.82 else RoadClass.LOCAL
                blend_speed = 9.9 if blend_class == RoadClass.COLLECTOR else 8.7
                blend_capacity = 6.0 if blend_class == RoadClass.COLLECTOR else 5.2
                _add_bidirectional_link_pair(
                    link_builder,
                    edge_node.node_id,
                    halo.node_id,
                    road_class=blend_class,
                    lanes=1,
                    speed_mps=blend_speed,
                    capacity=blend_capacity,
                )
                district_infill_link_count += 2
                district_local_links += 2
                precinct_edge_blend_count += 2
                nearest_grid = _nearest_grid_node(nodes_by_coord, (halo.x, halo.y))
                if nearest_grid.node_id != halo.node_id:
                    _add_bidirectional_link_pair(
                        link_builder,
                        halo.node_id,
                        nearest_grid.node_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.5,
                        capacity=5.1,
                    )
                    district_infill_link_count += 2
                    district_local_links += 2
                    precinct_edge_blend_count += 2
            for current, nxt in zip(halo_nodes, halo_nodes[1:]):
                if current.node_id == nxt.node_id:
                    continue
                _add_bidirectional_link_pair(
                    link_builder,
                    current.node_id,
                    nxt.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.2,
                    capacity=5.0,
                )
                district_infill_link_count += 2
                district_local_links += 2
                precinct_edge_blend_count += 2
            for halo, (dx, dy) in zip(halo_nodes[::2], _texture_filament_offsets(texture_profile)):
                filament = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=center_x + dx * massing_scale,
                    y=center_y + dy * massing_scale,
                )
                district_local_nodes += 1
                _add_bidirectional_link_pair(
                    link_builder,
                    halo.node_id,
                    filament.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.9,
                )
                district_infill_link_count += 2
                district_local_links += 2
                precinct_edge_blend_count += 2
                nearest_grid = _nearest_grid_node(nodes_by_coord, (filament.x, filament.y))
                if nearest_grid.node_id != filament.node_id:
                    _add_bidirectional_link_pair(
                        link_builder,
                        filament.node_id,
                        nearest_grid.node_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=7.8,
                        capacity=4.8,
                    )
                    district_infill_link_count += 2
                    district_local_links += 2
                    precinct_edge_blend_count += 2
            for x_idx in range(len(block_grid_xs) - 2):
                for y_idx in range(len(block_grid_ys) - 2):
                    if (x_idx + y_idx) % 2 != 0:
                        continue
                    quilt_src = _nearest_grid_node(nodes_by_coord, (block_grid_xs[x_idx], block_grid_ys[y_idx]))
                    quilt_dst = _nearest_grid_node(nodes_by_coord, (block_grid_xs[x_idx + 1], block_grid_ys[y_idx + 1]))
                    if quilt_src.node_id == quilt_dst.node_id:
                        continue
                    quilt_class = RoadClass.COLLECTOR if float(district.get("interior_quilt_bias", 0.0)) >= 0.76 else RoadClass.LOCAL
                    quilt_speed = 8.7 if quilt_class == RoadClass.COLLECTOR else 8.1
                    quilt_capacity = 5.3 if quilt_class == RoadClass.COLLECTOR else 4.9
                    _add_bidirectional_link_pair(
                        link_builder,
                        quilt_src.node_id,
                        quilt_dst.node_id,
                        road_class=quilt_class,
                        lanes=1,
                        speed_mps=quilt_speed,
                        capacity=quilt_capacity,
                    )
                    district_infill_link_count += 2
                    district_local_links += 2
                    precinct_interior_quilt_count += 2
            if interior_grid_nodes and halo_nodes and anchor_nodes:
                quarter_sources = (
                    lattice[max(0, len(lattice) // 3)][max(0, len(lattice[0]) // 3)],
                    lattice[max(0, len(lattice) // 3)][min(len(lattice[0]) - 1, (len(lattice[0]) * 2) // 3)],
                    lattice[min(len(lattice) - 1, (len(lattice) * 2) // 3)][max(0, len(lattice[0]) // 3)],
                    lattice[min(len(lattice) - 1, (len(lattice) * 2) // 3)][min(len(lattice[0]) - 1, (len(lattice[0]) * 2) // 3)],
                )
                stitch_nodes: list[Node] = []
                for breakup_idx, source in enumerate(quarter_sources):
                    halo = halo_nodes[breakup_idx % len(halo_nodes)]
                    anchor = anchor_nodes[breakup_idx % len(anchor_nodes)]
                    interior = interior_grid_nodes[breakup_idx % len(interior_grid_nodes)]
                    breakup = _get_or_add_node(
                        nodes_by_coord=nodes_by_coord,
                        node_builder=node_builder,
                        kind=NodeKind.INTERSECTION,
                        x=round(
                            float(source.x) + (float(halo.x) - float(source.x)) * (0.24 + precinct_mass_breakup_bias * 0.16),
                            3,
                        ),
                        y=round(
                            float(source.y) + (float(anchor.y) - float(source.y)) * (0.18 + precinct_mass_breakup_bias * 0.14),
                            3,
                        ),
                    )
                    stitch = _get_or_add_node(
                        nodes_by_coord=nodes_by_coord,
                        node_builder=node_builder,
                        kind=NodeKind.INTERSECTION,
                        x=round(
                            float(breakup.x) + (float(lattice_center.x) - float(breakup.x)) * (0.24 + sub_block_stitch_bias * 0.16),
                            3,
                        ),
                        y=round(
                            float(breakup.y) + (float(interior.y) - float(breakup.y)) * (0.24 + interior_field_equalization_bias * 0.18),
                            3,
                        ),
                    )
                    stitch_nodes.append(stitch)
                    for src_id, dst_id, road_class, speed, capacity in (
                        (source.node_id, breakup.node_id, RoadClass.LOCAL, 8.2, 4.9),
                        (breakup.node_id, halo.node_id, RoadClass.LOCAL, 8.1, 4.8),
                        (breakup.node_id, stitch.node_id, RoadClass.LOCAL, 8.0, 4.8),
                        (stitch.node_id, interior.node_id, RoadClass.LOCAL, 8.0, 4.8),
                        (stitch.node_id, int(lattice_center.node_id), RoadClass.LOCAL, 8.0, 4.8),
                    ):
                        _add_bidirectional_link_pair(
                            link_builder,
                            src_id,
                            dst_id,
                            road_class=road_class,
                            lanes=1,
                            speed_mps=speed,
                            capacity=capacity,
                        )
                    district_infill_link_count += 10
                    district_local_links += 10
                    precinct_mass_breakup_count += 4
                    distributed_sub_block_stitch_count += 2
                    interior_field_equalization_count += 4
                for current, nxt in zip(stitch_nodes, stitch_nodes[1:] + stitch_nodes[:1]):
                    if current.node_id == nxt.node_id:
                        continue
                    _add_bidirectional_link_pair(
                        link_builder,
                        current.node_id,
                        nxt.node_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.0,
                        capacity=4.8,
                    )
                    district_infill_link_count += 2
                    district_local_links += 2
                    distributed_sub_block_stitch_count += 2
                    interior_field_equalization_count += 1
                smoothing_nodes: list[Node] = []
                smoothing_sources = halo_nodes[: min(4, len(halo_nodes))]
                for smooth_idx, halo in enumerate(smoothing_sources):
                    interior = interior_grid_nodes[(smooth_idx * 2) % len(interior_grid_nodes)]
                    stitch = stitch_nodes[smooth_idx % len(stitch_nodes)] if stitch_nodes else lattice_center
                    smooth = _get_or_add_node(
                        nodes_by_coord=nodes_by_coord,
                        node_builder=node_builder,
                        kind=NodeKind.INTERSECTION,
                        x=round(
                            float(lattice_center.x)
                            + (float(halo.x) - float(lattice_center.x)) * (0.42 + precinct_cluster_smoothing_bias * 0.10)
                            + (float(interior.x) - float(lattice_center.x)) * 0.10,
                            3,
                        ),
                        y=round(
                            float(lattice_center.y)
                            + (float(halo.y) - float(lattice_center.y)) * (0.38 + precinct_cluster_smoothing_bias * 0.12)
                            + (float(interior.y) - float(lattice_center.y)) * 0.12,
                            3,
                        ),
                    )
                    smoothing_nodes.append(smooth)
                    for src_id, dst_id in (
                        (int(lattice_center.node_id), smooth.node_id),
                        (smooth.node_id, halo.node_id),
                        (smooth.node_id, interior.node_id),
                        (smooth.node_id, int(stitch.node_id)),
                    ):
                        _add_bidirectional_link_pair(
                            link_builder,
                            src_id,
                            dst_id,
                            road_class=RoadClass.LOCAL,
                            lanes=1,
                            speed_mps=8.0,
                            capacity=4.8,
                        )
                    district_infill_link_count += 8
                    district_local_links += 8
                    precinct_cluster_smoothing_count += 2
                    core_ring_fabric_consolidation_count += 4
                for current, nxt in zip(smoothing_nodes, smoothing_nodes[1:] + smoothing_nodes[:1]):
                    if current.node_id == nxt.node_id:
                        continue
                    _add_bidirectional_link_pair(
                        link_builder,
                        current.node_id,
                        nxt.node_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.1,
                        capacity=4.9,
                    )
                    district_infill_link_count += 2
                    district_local_links += 2
                    continuous_local_street_fill_count += 2
                if len(smoothing_nodes) >= 2:
                    for current, nxt in zip(smoothing_nodes, smoothing_nodes[2:]):
                        if current.node_id == nxt.node_id:
                            continue
                        _add_bidirectional_link_pair(
                            link_builder,
                            current.node_id,
                            nxt.node_id,
                            road_class=RoadClass.LOCAL,
                            lanes=1,
                            speed_mps=8.0,
                            capacity=4.8,
                        )
                        district_infill_link_count += 2
                        district_local_links += 2
                        continuous_local_street_fill_count += 2
                for smooth in smoothing_nodes:
                    equalize = _get_or_add_node(
                        nodes_by_coord=nodes_by_coord,
                        node_builder=node_builder,
                        kind=NodeKind.INTERSECTION,
                        x=round(
                            float(smooth.x) + (float(lattice_center.x) - float(smooth.x)) * (0.18 + continuous_local_fill_bias * 0.12),
                            3,
                        ),
                        y=round(
                            float(smooth.y) + (float(lattice_center.y) - float(smooth.y)) * (0.18 + core_ring_fabric_consolidation_bias * 0.12),
                            3,
                        ),
                    )
                    _add_bidirectional_link_pair(
                        link_builder,
                        smooth.node_id,
                        equalize.node_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.0,
                        capacity=4.8,
                    )
                    _add_bidirectional_link_pair(
                        link_builder,
                        equalize.node_id,
                        int(lattice_center.node_id),
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.0,
                        capacity=4.8,
                    )
                    district_infill_link_count += 4
                    district_local_links += 4
                    continuous_local_street_fill_count += 2
                    core_ring_fabric_consolidation_count += 2
                if scenario_id == "synthetic_smoke" and smoothing_nodes:
                    for smooth_idx, smooth in enumerate(smoothing_nodes):
                        stitch = stitch_nodes[smooth_idx % len(stitch_nodes)] if stitch_nodes else lattice_center
                        halo = halo_nodes[smooth_idx % len(halo_nodes)]
                        decluster = _get_or_add_node(
                            nodes_by_coord=nodes_by_coord,
                            node_builder=node_builder,
                            kind=NodeKind.INTERSECTION,
                            x=round(
                                float(smooth.x)
                                + (float(halo.x) - float(smooth.x)) * (0.18 + smoke_precinct_declustering_bias * 0.12)
                                + (float(stitch.x) - float(smooth.x)) * 0.16,
                                3,
                            ),
                            y=round(
                                float(smooth.y)
                                + (float(halo.y) - float(smooth.y)) * (0.16 + smoke_precinct_declustering_bias * 0.12)
                                + (float(stitch.y) - float(smooth.y)) * 0.16,
                                3,
                            ),
                        )
                        for src_id, dst_id in (
                            (smooth.node_id, decluster.node_id),
                            (decluster.node_id, halo.node_id),
                            (decluster.node_id, stitch.node_id),
                        ):
                            _add_bidirectional_link_pair(
                                link_builder,
                                src_id,
                                dst_id,
                                road_class=RoadClass.LOCAL,
                                lanes=1,
                                speed_mps=8.0,
                                capacity=4.8,
                            )
                        district_infill_link_count += 6
                        district_local_links += 6
                        smoke_precinct_declustering_count += 2
            for frag_idx, halo in enumerate(halo_nodes[: min(4, len(halo_nodes))]):
                edge = blend_edge_nodes[(frag_idx * 2) % len(blend_edge_nodes)]
                interior = interior_grid_nodes[frag_idx % len(interior_grid_nodes)]
                shell_break = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(halo.x) + (float(interior.x) - float(halo.x)) * (0.34 + shell_fragment_v2_bias * 0.14),
                        3,
                    ),
                    y=round(
                        float(halo.y) + (float(interior.y) - float(halo.y)) * (0.40 + shell_fragment_v2_bias * 0.12),
                        3,
                    ),
                )
                fracture = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round((float(shell_break.x) + float(edge.x)) * 0.5, 3),
                    y=round(
                        (float(shell_break.y) + float(edge.y)) * 0.5
                        + (10.0 if float(edge.y) >= center_y else -10.0) * shell_fragment_v2_bias,
                        3,
                    ),
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    halo.node_id,
                    shell_break.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=7.9,
                    capacity=4.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    shell_break.node_id,
                    fracture.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=7.9,
                    capacity=4.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    fracture.node_id,
                    interior.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.1,
                    capacity=4.9,
                )
                district_infill_link_count += 6
                district_local_links += 6
                shell_fragment_v2_link_count += 6
            for dissolve_idx, interior in enumerate(interior_grid_nodes[: min(4, len(interior_grid_nodes))]):
                halo = halo_nodes[dissolve_idx % len(halo_nodes)]
                anchor = anchor_nodes[dissolve_idx % len(anchor_nodes)]
                dissolve = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(interior.x) + (float(halo.x) - float(interior.x)) * (0.22 + interior_dissolve_bias * 0.10),
                        3,
                    ),
                    y=round(
                        float(interior.y) + (float(anchor.y) - float(interior.y)) * (0.18 + interior_dissolve_bias * 0.14),
                        3,
                    ),
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    interior.node_id,
                    dissolve.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    dissolve.node_id,
                    halo.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    dissolve.node_id,
                    anchor.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.2,
                    capacity=4.9,
                )
                district_infill_link_count += 6
                district_local_links += 6
                interior_street_dissolution_count += 6
            collapse_count = min(
                len(blend_edge_nodes),
                max(2, 2 + int(round(max(0.0, (outer_shell_collapse_bias - 0.70) / 0.06)))),
            )
            for collapse_idx, edge in enumerate(blend_edge_nodes[:collapse_count]):
                interior = interior_grid_nodes[collapse_idx % len(interior_grid_nodes)]
                collapse = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(edge.x) + (float(interior.x) - float(edge.x)) * (0.42 + outer_shell_collapse_bias * 0.16),
                        3,
                    ),
                    y=round(
                        float(edge.y) + (float(interior.y) - float(edge.y)) * (0.38 + outer_shell_collapse_bias * 0.18),
                        3,
                    ),
                )
                saturate = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round((float(collapse.x) + float(lattice_center.x)) * 0.5, 3),
                    y=round((float(collapse.y) + float(lattice_center.y)) * 0.5, 3),
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    edge.node_id,
                    collapse.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    collapse.node_id,
                    saturate.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    saturate.node_id,
                    interior.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.1,
                    capacity=4.9,
                )
                district_infill_link_count += 6
                district_local_links += 6
                outer_shell_collapse_link_count += 6
                precinct_interior_saturation_count += 4
            ordered_interior = list(interior_grid_nodes)
            saturation_count = min(
                len(ordered_interior),
                max(2, 2 + int(round(max(0.0, (interior_saturation_bias - 0.70) / 0.06)))),
            )
            active_interior_nodes = ordered_interior[:saturation_count]
            if len(active_interior_nodes) >= 3:
                for current, nxt in zip(active_interior_nodes, active_interior_nodes[1:] + active_interior_nodes[:1]):
                    if current.node_id == nxt.node_id:
                        continue
                    _add_bidirectional_link_pair(
                        link_builder,
                        current.node_id,
                        nxt.node_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.1,
                        capacity=4.9,
                    )
                    precinct_interior_saturation_count += 2
                    district_infill_link_count += 2
                    district_local_links += 2
                for interior in active_interior_nodes:
                    if interior.node_id == lattice_center.node_id:
                        continue
                    _add_bidirectional_link_pair(
                        link_builder,
                        interior.node_id,
                        lattice_center.node_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.0,
                        capacity=4.8,
                    )
                    precinct_interior_saturation_count += 2
                    district_infill_link_count += 2
                    district_local_links += 2
            parcel_irregularity_scores.append(
                _parcel_irregularity_score(
                    xs=block_grid_xs,
                    ys=block_grid_ys,
                    void_cells=void_cells,
                    tier=parcel_irregularity_tier,
                    envelope_erosion_bias=envelope_erosion_bias,
                )
            )
            district_records.append(
                {
                    "district_id": str(district.get("district_id", "")),
                    "kind": str(district.get("kind", "")),
                    "center_x": center_x,
                    "center_y": center_y,
                    "primary_hub": primary_hub,
                    "anchor_nodes": tuple(anchor_nodes),
                    "halo_nodes": tuple(halo_nodes),
                    "lattice_center": lattice_center,
                    "river_side": river_side,
                    "connector_bias": connector_bias,
                    "mid_annulus_fill_bias": mid_annulus_fill_bias,
                    "district_blend_bias": district_blend_bias,
                    "connector_thickness_bias": float(district.get("connector_thickness_bias", 0.72)),
                    "overlap_stitch_bias": float(district.get("overlap_stitch_bias", 0.68)),
                    "secondary_fabric_bias": float(district.get("secondary_fabric_bias", 0.70)),
                    "corridor_continuity_bias": float(district.get("corridor_continuity_bias", 0.72)),
                    "precinct_edge_bleed_bias": float(district.get("precinct_edge_bleed_bias", 0.68)),
                    "overlap_mesh_fill_bias": float(district.get("overlap_mesh_fill_bias", 0.68)),
                    "corridor_braiding_bias": float(district.get("corridor_braiding_bias", 0.70)),
                    "interior_quilt_bias": float(district.get("interior_quilt_bias", 0.72)),
                    "downtown_deemphasis_bias": float(district.get("downtown_deemphasis_bias", 0.72)),
                    "corridor_precinct_blend_bias": float(district.get("corridor_precinct_blend_bias", 0.72)),
                    "midfield_stitch_bias": float(district.get("midfield_stitch_bias", 0.70)),
                    "shell_deboxing_bias": float(district.get("shell_deboxing_bias", 0.68)),
                    "shell_fragment_v2_bias": shell_fragment_v2_bias,
                    "interior_dissolve_bias": interior_dissolve_bias,
                    "precinct_seam_erosion_bias": precinct_seam_erosion_bias,
                    "outer_shell_collapse_bias": outer_shell_collapse_bias,
                    "interior_saturation_bias": interior_saturation_bias,
                    "central_mesh_thickening_bias": central_mesh_thickening_bias,
                    "perimeter_rail_breakup_bias": perimeter_rail_breakup_bias,
                    "precinct_bridge_saturation_bias": precinct_bridge_saturation_bias,
                    "interior_web_thickening_bias": interior_web_thickening_bias,
                    "precinct_mass_breakup_bias": precinct_mass_breakup_bias,
                    "sub_block_stitch_bias": sub_block_stitch_bias,
                    "interior_field_equalization_bias": interior_field_equalization_bias,
                    "precinct_cluster_smoothing_bias": precinct_cluster_smoothing_bias,
                    "continuous_local_fill_bias": continuous_local_fill_bias,
                    "core_ring_fabric_consolidation_bias": core_ring_fabric_consolidation_bias,
                    "small_map_core_dering_bias": small_map_core_dering_bias,
                    "midfield_local_web_saturation_bias": midfield_local_web_saturation_bias,
                    "scaffold_rail_attenuation_bias": scaffold_rail_attenuation_bias,
                    "smoke_precinct_declustering_bias": smoke_precinct_declustering_bias,
                    "large_map_scaffold_dissolution_bias": large_map_scaffold_dissolution_bias,
                    "inner_annulus_mesh_equalization_bias": inner_annulus_mesh_equalization_bias,
                    "outer_rail_attenuation_v2_bias": outer_rail_attenuation_v2_bias,
                    "interior_fabric_densification_bias": interior_fabric_densification_bias,
                    "precinct_shell_dissolution_bias": precinct_shell_dissolution_bias,
                    "diagonal_shell_breakup_bias": diagonal_shell_breakup_bias,
                    "continuous_inner_weave_bias": continuous_inner_weave_bias,
                    "precinct_mass_deemphasis_bias": precinct_mass_deemphasis_bias,
                    "quadrant_rail_dissolution_bias": quadrant_rail_dissolution_bias,
                    "precinct_starburst_attenuation_bias": precinct_starburst_attenuation_bias,
                    "annulus_core_threading_bias": annulus_core_threading_bias,
                    "quadrant_interior_knitting_bias": quadrant_interior_knitting_bias,
                    "precinct_knot_flattening_bias": precinct_knot_flattening_bias,
                    "distributed_local_texture_bias": distributed_local_texture_bias,
                    "quadrant_local_mesh_stitch_bias": quadrant_local_mesh_stitch_bias,
                    "precinct_core_destarburst_bias": precinct_core_destarburst_bias,
                    "distributed_secondary_street_fill_bias": distributed_secondary_street_fill_bias,
                    "outer_shell_rail_thinning_bias": outer_shell_rail_thinning_bias,
                    "precinct_shell_mesh_blend_bias": precinct_shell_mesh_blend_bias,
                    "distributed_tertiary_street_fill_bias": distributed_tertiary_street_fill_bias,
                    "shell_silhouette_collapse_bias": shell_silhouette_collapse_bias,
                    "precinct_boundary_dissolution_bias": precinct_boundary_dissolution_bias,
                    "fine_grain_street_texture_bias": fine_grain_street_texture_bias,
                    "shell_silhouette_deemphasis_bias": shell_silhouette_deemphasis_bias,
                    "precinct_knot_diffusion_bias": precinct_knot_diffusion_bias,
                    "distributed_fine_grain_weave_bias": distributed_fine_grain_weave_bias,
                    "shell_arc_softening_bias": shell_arc_softening_bias,
                    "precinct_knot_diffusion_v2_bias": precinct_knot_diffusion_v2_bias,
                    "interior_weave_continuity_bias": interior_weave_continuity_bias,
                    "shell_arc_fading_bias": shell_arc_fading_bias,
                    "precinct_knot_bleed_bias": precinct_knot_bleed_bias,
                    "weave_corridor_threading_bias": weave_corridor_threading_bias,
                    "edge_nodes": tuple(blend_edge_nodes),
                    "interior_nodes": tuple(interior_grid_nodes),
                }
            )
        retention_weight = {
            "dense_core": 1.18,
            "dense_wedge": 1.12,
            "hub_pockets": 1.04,
            "split_band": 0.94,
            "void_band": 0.82,
            "landmark_cluster": 1.16,
        }.get(density_retention, 1.0)
        base_mass_score = (district_local_nodes * 0.35) + (district_local_links * 0.65)
        district_mass_scores.append(base_mass_score * retention_weight * (0.90 + massing_scale * 0.16))

    downtown_record = next((record for record in district_records if record["kind"] == "downtown"), None)
    if downtown_record is not None:
        downtown_mesh_bias = float(downtown_record.get("central_mesh_thickening_bias", 0.72))
        downtown_mesh_center = downtown_record["lattice_center"]
        central_mesh_nodes: list[Node] = []
        for dx, dy in (
            (-54.0, -28.0),
            (48.0, -20.0),
            (56.0, 34.0),
            (-42.0, 38.0),
        ):
            node = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round(float(downtown_mesh_center.x) + dx * (0.92 + downtown_mesh_bias * 0.12), 3),
                y=round(float(downtown_mesh_center.y) + dy * (0.90 + downtown_mesh_bias * 0.12), 3),
            )
            central_mesh_nodes.append(node)
        for current, nxt in zip(central_mesh_nodes, central_mesh_nodes[1:] + central_mesh_nodes[:1]):
            _add_bidirectional_link_pair(
                link_builder,
                current.node_id,
                nxt.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.0,
                capacity=4.8,
            )
            central_mesh_thickening_count += 2
        for node in central_mesh_nodes:
            _add_bidirectional_link_pair(
                link_builder,
                node.node_id,
                int(downtown_mesh_center.node_id),
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.0,
                capacity=4.8,
            )
            central_mesh_thickening_count += 2
        outer_records = [record for record in district_records if record is not downtown_record]
        corridor_braid_records: list[dict[str, object]] = []
        for record in outer_records:
            target = _nearest_precinct_node(
                tuple(record["anchor_nodes"]) + tuple(record["halo_nodes"]) + (record["lattice_center"],),
                (record["center_x"], record["center_y"]),
            )
            downtown_target = _nearest_precinct_node(
                tuple(downtown_record["anchor_nodes"]) + tuple(downtown_record["halo_nodes"]) + (downtown_record["lattice_center"],),
                (record["center_x"], record["center_y"]),
            )
            annulus_fill = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round(float(downtown_target.x) + (float(target.x) - float(downtown_target.x)) * (0.58 + record["mid_annulus_fill_bias"] * 0.08), 3),
                y=round(float(downtown_target.y) + (float(target.y) - float(downtown_target.y)) * (0.58 + record["mid_annulus_fill_bias"] * 0.10), 3),
            )
            annulus_tail = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round(float(downtown_target.x) + (float(target.x) - float(downtown_target.x)) * (0.74 + record["mid_annulus_fill_bias"] * 0.06), 3),
                y=round(float(downtown_target.y) + (float(target.y) - float(downtown_target.y)) * (0.72 + record["mid_annulus_fill_bias"] * 0.08), 3),
            )
            shoulder_a = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round(float(annulus_fill.x) + (10.0 if float(annulus_fill.x) > 0.0 else -10.0), 3),
                y=round(float(annulus_fill.y) + 18.0 * record["connector_thickness_bias"], 3),
            )
            shoulder_b = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round(float(annulus_tail.x) + (14.0 if float(annulus_tail.x) > 0.0 else -14.0), 3),
                y=round(float(annulus_tail.y) - 20.0 * record["connector_thickness_bias"], 3),
            )
            corridor_inner = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round(float(downtown_target.x) + (float(target.x) - float(downtown_target.x)) * 0.36, 3),
                y=round(
                    float(downtown_target.y)
                    + (float(target.y) - float(downtown_target.y)) * 0.34
                    + (18.0 if float(target.y) >= float(downtown_target.y) else -18.0) * record["corridor_continuity_bias"],
                    3,
                ),
            )
            corridor_outer = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round(float(downtown_target.x) + (float(target.x) - float(downtown_target.x)) * 0.62, 3),
                y=round(
                    float(downtown_target.y)
                    + (float(target.y) - float(downtown_target.y)) * 0.60
                    + (12.0 if float(target.y) >= float(downtown_target.y) else -12.0) * record["corridor_continuity_bias"],
                    3,
                ),
            )
            corridor_mesh = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round((float(corridor_inner.x) + float(shoulder_a.x) + float(annulus_fill.x)) / 3.0, 3),
                y=round((float(corridor_inner.y) + float(shoulder_a.y) + float(annulus_fill.y)) / 3.0, 3),
            )
            edge_halo = _nearest_precinct_node(
                tuple(record["halo_nodes"]) + tuple(record["anchor_nodes"]),
                (float(annulus_tail.x), float(annulus_tail.y)),
            )
            precinct_bleed = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round(float(corridor_outer.x) + (float(edge_halo.x) - float(corridor_outer.x)) * (0.42 + record["precinct_edge_bleed_bias"] * 0.14), 3),
                y=round(float(corridor_outer.y) + (float(edge_halo.y) - float(corridor_outer.y)) * (0.46 + record["precinct_edge_bleed_bias"] * 0.12), 3),
            )
            precinct_midfield = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round(
                    float(corridor_outer.x) + (float(record["lattice_center"].x) - float(corridor_outer.x)) * (0.32 + record["corridor_precinct_blend_bias"] * 0.18),
                    3,
                ),
                y=round(
                    float(corridor_outer.y) + (float(record["lattice_center"].y) - float(corridor_outer.y)) * (0.36 + record["corridor_precinct_blend_bias"] * 0.18),
                    3,
                ),
            )
            inner_precinct = _nearest_precinct_node(
                tuple(record.get("interior_nodes", ())) or (record["lattice_center"],),
                (float(precinct_midfield.x), float(precinct_midfield.y)),
            )
            dissolve_a = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round((float(corridor_mesh.x) + float(precinct_midfield.x)) * 0.5, 3),
                y=round((float(corridor_mesh.y) + float(precinct_midfield.y)) * 0.5, 3),
            )
            dissolve_b = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round((float(annulus_fill.x) + float(inner_precinct.x)) * 0.5, 3),
                y=round((float(annulus_fill.y) + float(inner_precinct.y)) * 0.5, 3),
            )
            orbit_angle = math.atan2(float(target.y) - float(downtown_target.y), float(target.x) - float(downtown_target.x))
            orbit_radius = 118.0 + 24.0 * record["downtown_deemphasis_bias"]
            orbit = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round(float(downtown_target.x) + math.cos(orbit_angle) * orbit_radius, 3),
                y=round(float(downtown_target.y) + math.sin(orbit_angle) * orbit_radius, 3),
            )
            mid_annulus_fill_node_count += 4
            inter_precinct_connector_count += 4
            _add_bidirectional_link_pair(
                link_builder,
                downtown_target.node_id,
                orbit.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.5,
                capacity=5.1,
            )
            _add_bidirectional_link_pair(
                link_builder,
                orbit.node_id,
                annulus_fill.node_id,
                road_class=RoadClass.COLLECTOR,
                lanes=1,
                speed_mps=9.6,
                capacity=6.0,
            )
            _add_bidirectional_link_pair(
                link_builder,
                annulus_fill.node_id,
                annulus_tail.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.6,
                capacity=5.2,
            )
            _add_bidirectional_link_pair(
                link_builder,
                annulus_tail.node_id,
                target.node_id,
                road_class=RoadClass.COLLECTOR,
                lanes=1,
                speed_mps=9.3,
                capacity=5.8,
            )
            _add_bidirectional_link_pair(
                link_builder,
                orbit.node_id,
                corridor_inner.node_id,
                road_class=RoadClass.COLLECTOR,
                lanes=1,
                speed_mps=9.4,
                capacity=5.9,
            )
            _add_bidirectional_link_pair(
                link_builder,
                corridor_inner.node_id,
                corridor_outer.node_id,
                road_class=RoadClass.COLLECTOR,
                lanes=1,
                speed_mps=9.2,
                capacity=5.8,
            )
            _add_bidirectional_link_pair(
                link_builder,
                corridor_outer.node_id,
                target.node_id,
                road_class=RoadClass.COLLECTOR,
                lanes=1,
                speed_mps=9.1,
                capacity=5.8,
            )
            _add_bidirectional_link_pair(
                link_builder,
                corridor_inner.node_id,
                corridor_mesh.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.2,
                capacity=4.9,
            )
            _add_bidirectional_link_pair(
                link_builder,
                corridor_mesh.node_id,
                annulus_fill.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.2,
                capacity=4.9,
            )
            _add_bidirectional_link_pair(
                link_builder,
                corridor_outer.node_id,
                precinct_bleed.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.0,
                capacity=4.8,
            )
            _add_bidirectional_link_pair(
                link_builder,
                precinct_bleed.node_id,
                edge_halo.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.0,
                capacity=4.8,
            )
            _add_bidirectional_link_pair(
                link_builder,
                precinct_bleed.node_id,
                annulus_tail.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.0,
                capacity=4.8,
            )
            _add_bidirectional_link_pair(
                link_builder,
                corridor_outer.node_id,
                precinct_midfield.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.0,
                capacity=4.8,
            )
            _add_bidirectional_link_pair(
                link_builder,
                precinct_midfield.node_id,
                int(record["lattice_center"].node_id),
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.0,
                capacity=4.8,
            )
            _add_bidirectional_link_pair(
                link_builder,
                precinct_midfield.node_id,
                edge_halo.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=7.9,
                capacity=4.8,
            )
            _add_bidirectional_link_pair(
                link_builder,
                corridor_mesh.node_id,
                dissolve_a.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.1,
                capacity=4.9,
            )
            _add_bidirectional_link_pair(
                link_builder,
                dissolve_a.node_id,
                precinct_midfield.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.1,
                capacity=4.9,
            )
            _add_bidirectional_link_pair(
                link_builder,
                annulus_fill.node_id,
                dissolve_b.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.0,
                capacity=4.8,
            )
            _add_bidirectional_link_pair(
                link_builder,
                dissolve_b.node_id,
                inner_precinct.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.0,
                capacity=4.8,
            )
            _add_bidirectional_link_pair(
                link_builder,
                dissolve_a.node_id,
                dissolve_b.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.0,
                capacity=4.8,
            )
            _add_bidirectional_link_pair(
                link_builder,
                annulus_fill.node_id,
                shoulder_a.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.4,
                capacity=5.0,
            )
            _add_bidirectional_link_pair(
                link_builder,
                annulus_tail.node_id,
                shoulder_b.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.4,
                capacity=5.0,
            )
            _add_bidirectional_link_pair(
                link_builder,
                shoulder_a.node_id,
                shoulder_b.node_id,
                road_class=RoadClass.COLLECTOR,
                lanes=1,
                speed_mps=9.0,
                capacity=5.6,
            )
            connector_thickening_count += 6
            secondary_fabric_link_count += 6
            district_blend_link_count += 12
            continuous_connector_corridor_count += 8
            precinct_edge_bleed_count += 6
            overlap_mesh_fill_count += 4
            downtown_deemphasis_link_count += 4
            corridor_precinct_blend_count += 10
            midfield_parcel_stitch_count += 4
            interior_street_dissolution_count += 10
            if central_mesh_nodes:
                central_target = _nearest_precinct_node(tuple(central_mesh_nodes), (float(orbit.x), float(orbit.y)))
                _add_bidirectional_link_pair(
                    link_builder,
                    int(central_target.node_id),
                    int(corridor_inner.node_id),
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    int(central_target.node_id),
                    int(dissolve_a.node_id),
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                central_mesh_thickening_count += 4
            connector_side = "west" if float(target.x) < float(downtown_target.x) else "east"
            side_connector_nodes[connector_side].extend((corridor_outer, precinct_bleed))
            corridor_braid_records.append(
                {
                    "angle": orbit_angle,
                    "orbit": orbit,
                    "inner": corridor_inner,
                    "outer": corridor_outer,
                }
            )

        upper_records = sorted([record for record in outer_records if float(record["center_y"]) > 320.0], key=lambda item: float(item["center_x"]))
        lower_records = sorted([record for record in outer_records if float(record["center_y"]) < -240.0], key=lambda item: float(item["center_x"]))
        for group in (upper_records, lower_records):
            for left, right in zip(group, group[1:]):
                src = _nearest_precinct_node(tuple(left["halo_nodes"]) + tuple(left["anchor_nodes"]), (right["center_x"], right["center_y"]))
                dst = _nearest_precinct_node(tuple(right["halo_nodes"]) + tuple(right["anchor_nodes"]), (left["center_x"], left["center_y"]))
                mid_x = (float(src.x) + float(dst.x)) * 0.5
                mid_y = (float(src.y) + float(dst.y)) * 0.5
                blend = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(mid_x, 3),
                    y=round(mid_y + (18.0 if mid_y > 0.0 else -18.0), 3),
                )
                fill = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(mid_x + (12.0 if mid_x > 0.0 else -12.0), 3),
                    y=round(mid_y + (42.0 if mid_y > 0.0 else -42.0), 3),
                )
                stitch = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(mid_x + (18.0 if mid_x > 0.0 else -18.0), 3),
                    y=round(mid_y + (10.0 if mid_y > 0.0 else -10.0), 3),
                )
                weave = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round((float(fill.x) + float(stitch.x)) * 0.5, 3),
                    y=round((float(fill.y) + float(stitch.y)) * 0.5, 3),
                )
                mesh_a = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round((float(blend.x) + float(weave.x)) * 0.5, 3),
                    y=round((float(blend.y) + float(weave.y)) * 0.5 + (10.0 if mid_y > 0.0 else -10.0) * left["overlap_mesh_fill_bias"], 3),
                )
                mesh_b = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round((float(fill.x) + float(stitch.x)) * 0.5, 3),
                    y=round((float(fill.y) + float(stitch.y)) * 0.5 - (10.0 if mid_y > 0.0 else -10.0) * right["overlap_mesh_fill_bias"], 3),
                )
                left_halo = _nearest_precinct_node(tuple(left["halo_nodes"]) + tuple(left["anchor_nodes"]), (mid_x, mid_y))
                right_halo = _nearest_precinct_node(tuple(right["halo_nodes"]) + tuple(right["anchor_nodes"]), (mid_x, mid_y))
                mid_annulus_fill_node_count += 2
                inter_precinct_connector_count += 2
                _add_bidirectional_link_pair(
                    link_builder,
                    src.node_id,
                    blend.node_id,
                    road_class=RoadClass.COLLECTOR,
                    lanes=1,
                    speed_mps=9.2,
                    capacity=5.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    blend.node_id,
                    fill.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.1,
                    capacity=4.9,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    fill.node_id,
                    dst.node_id,
                    road_class=RoadClass.COLLECTOR,
                    lanes=1,
                    speed_mps=9.1,
                    capacity=5.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    blend.node_id,
                    stitch.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.2,
                    capacity=4.9,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    fill.node_id,
                    stitch.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    weave.node_id,
                    fill.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    weave.node_id,
                    blend.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    blend.node_id,
                    mesh_a.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    fill.node_id,
                    mesh_b.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    mesh_a.node_id,
                    mesh_b.node_id,
                    road_class=RoadClass.COLLECTOR,
                    lanes=1,
                    speed_mps=8.9,
                    capacity=5.4,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    left_halo.node_id,
                    mesh_a.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    right_halo.node_id,
                    mesh_b.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    weave.node_id,
                    mesh_a.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    weave.node_id,
                    mesh_b.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                connector_thickening_count += 4
                district_overlap_stitch_count += 4
                secondary_fabric_link_count += 8
                district_blend_link_count += 14
                continuous_connector_corridor_count += 4
                precinct_edge_bleed_count += 4
                overlap_mesh_fill_count += 8
                corridor_precinct_blend_count += 4
                midfield_parcel_stitch_count += 6
                left_interior = _nearest_precinct_node(
                    tuple(left.get("interior_nodes", ())) or (left["lattice_center"],),
                    (mid_x, mid_y),
                )
                right_interior = _nearest_precinct_node(
                    tuple(right.get("interior_nodes", ())) or (right["lattice_center"],),
                    (mid_x, mid_y),
                )
                seam_left = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(left_halo.x) + (float(left_interior.x) - float(left_halo.x)) * (0.34 + left["precinct_seam_erosion_bias"] * 0.16),
                        3,
                    ),
                    y=round(
                        float(left_halo.y) + (float(mesh_a.y) - float(left_halo.y)) * (0.30 + left["precinct_seam_erosion_bias"] * 0.18),
                        3,
                    ),
                )
                seam_right = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(right_halo.x) + (float(right_interior.x) - float(right_halo.x)) * (0.34 + right["precinct_seam_erosion_bias"] * 0.16),
                        3,
                    ),
                    y=round(
                        float(right_halo.y) + (float(mesh_b.y) - float(right_halo.y)) * (0.30 + right["precinct_seam_erosion_bias"] * 0.18),
                        3,
                    ),
                )
                seam_mid = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round((float(seam_left.x) + float(seam_right.x)) * 0.5, 3),
                    y=round((float(seam_left.y) + float(seam_right.y)) * 0.5, 3),
                )
                for src_id, dst_id in (
                    (left_interior.node_id, seam_left.node_id),
                    (left_halo.node_id, seam_left.node_id),
                    (seam_left.node_id, seam_mid.node_id),
                    (seam_mid.node_id, seam_right.node_id),
                    (seam_right.node_id, right_interior.node_id),
                    (seam_right.node_id, right_halo.node_id),
                    (seam_mid.node_id, mesh_a.node_id),
                    (seam_mid.node_id, mesh_b.node_id),
                ):
                    _add_bidirectional_link_pair(
                        link_builder,
                        src_id,
                        dst_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.1,
                        capacity=4.8,
                    )
                district_blend_link_count += 8
                interior_street_dissolution_count += 8
                precinct_seam_erosion_count += 16
        ordered_braids = sorted(corridor_braid_records, key=lambda item: float(item["angle"]))
        if len(ordered_braids) >= 2:
            for current, nxt in zip(ordered_braids, ordered_braids[1:] + ordered_braids[:1]):
                _add_bidirectional_link_pair(
                    link_builder,
                    int(current["orbit"].node_id),
                    int(nxt["orbit"].node_id),
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.2,
                    capacity=5.0,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    int(current["inner"].node_id),
                    int(nxt["outer"].node_id),
                    road_class=RoadClass.COLLECTOR,
                    lanes=1,
                    speed_mps=8.8,
                    capacity=5.4,
                )
                corridor_braid_link_count += 4
                downtown_deemphasis_link_count += 2
        equalization_ring_nodes: list[Node] = []
        for record in sorted(
            outer_records,
            key=lambda item: math.atan2(float(item["center_y"]) - float(downtown_record["center_y"]), float(item["center_x"]) - float(downtown_record["center_x"])),
        ):
            interior_nodes = tuple(record.get("interior_nodes", ())) or (record["lattice_center"],)
            interior = _nearest_precinct_node(interior_nodes, (float(downtown_record["center_x"]), float(downtown_record["center_y"])))
            ring = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round(
                    float(interior.x) + (float(downtown_record["lattice_center"].x) - float(interior.x)) * (0.42 + record["interior_field_equalization_bias"] * 0.10),
                    3,
                ),
                y=round(
                    float(interior.y) + (float(downtown_record["lattice_center"].y) - float(interior.y)) * (0.40 + record["interior_field_equalization_bias"] * 0.12),
                    3,
                ),
            )
            equalization_ring_nodes.append(ring)
            for src_id, dst_id in (
                (int(record["lattice_center"].node_id), ring.node_id),
                (interior.node_id, ring.node_id),
            ):
                _add_bidirectional_link_pair(
                    link_builder,
                    src_id,
                    dst_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.1,
                    capacity=4.8,
                )
            district_blend_link_count += 4
            interior_field_equalization_count += 4
        for current, nxt in zip(equalization_ring_nodes, equalization_ring_nodes[1:] + equalization_ring_nodes[:1]):
            if current.node_id == nxt.node_id:
                continue
            _add_bidirectional_link_pair(
                link_builder,
                current.node_id,
                nxt.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.0,
                capacity=4.8,
            )
            interior_field_equalization_count += 2
            distributed_sub_block_stitch_count += 1

        if scenario_id == "synthetic_smoke" and equalization_ring_nodes:
            smoke_web_nodes: list[Node] = []
            smoke_inner_weave_nodes: list[Node] = []
            smoke_thread_nodes: list[Node] = []
            ordered_outer_records = sorted(
                outer_records,
                key=lambda item: math.atan2(
                    float(item["center_y"]) - float(downtown_record["center_y"]),
                    float(item["center_x"]) - float(downtown_record["center_x"]),
                ),
            )
            for record, ring in zip(ordered_outer_records, equalization_ring_nodes):
                orbit = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(downtown_record["lattice_center"].x)
                        + (float(ring.x) - float(downtown_record["lattice_center"].x))
                        * (0.44 + float(record.get("small_map_core_dering_bias", 0.76)) * 0.14),
                        3,
                    ),
                    y=round(
                        float(downtown_record["lattice_center"].y)
                        + (float(ring.y) - float(downtown_record["lattice_center"].y))
                        * (0.42 + float(record.get("midfield_local_web_saturation_bias", 0.78)) * 0.14),
                        3,
                    ),
                )
                smoke_web_nodes.append(orbit)
                for src_id, dst_id in (
                    (ring.node_id, orbit.node_id),
                    (int(record["lattice_center"].node_id), orbit.node_id),
                ):
                    _add_bidirectional_link_pair(
                        link_builder,
                        src_id,
                        dst_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.1,
                        capacity=4.8,
                    )
                small_map_core_dering_count += 2
                midfield_local_web_saturation_count += 2
            for current, nxt in zip(smoke_web_nodes, smoke_web_nodes[1:] + smoke_web_nodes[:1]):
                if current.node_id == nxt.node_id:
                    continue
                _add_bidirectional_link_pair(
                    link_builder,
                    current.node_id,
                    nxt.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                midfield_local_web_saturation_count += 2
                scaffold_rail_attenuation_count += 2
            for record, ring, orbit in zip(ordered_outer_records, equalization_ring_nodes, smoke_web_nodes):
                inner = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(downtown_record["lattice_center"].x)
                        + (float(orbit.x) - float(downtown_record["lattice_center"].x))
                        * (0.34 + float(record.get("interior_fabric_densification_bias", 0.80)) * 0.12),
                        3,
                    ),
                    y=round(
                        float(downtown_record["lattice_center"].y)
                        + (float(orbit.y) - float(downtown_record["lattice_center"].y))
                        * (0.32 + float(record.get("interior_fabric_densification_bias", 0.80)) * 0.14),
                        3,
                    ),
                )
                shell = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(record["lattice_center"].x)
                        + (float(ring.x) - float(record["lattice_center"].x))
                        * (0.36 + float(record.get("precinct_shell_dissolution_bias", 0.78)) * 0.18),
                        3,
                    ),
                    y=round(
                        float(record["lattice_center"].y)
                        + (float(ring.y) - float(record["lattice_center"].y))
                        * (0.34 + float(record.get("precinct_shell_dissolution_bias", 0.78)) * 0.18),
                        3,
                    ),
                )
                breakup = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(shell.x)
                        + (float(inner.x) - float(shell.x))
                        * (0.48 + float(record.get("diagonal_shell_breakup_bias", 0.80)) * 0.12),
                        3,
                    ),
                    y=round(
                        float(shell.y)
                        + (float(inner.y) - float(shell.y))
                        * (0.42 + float(record.get("diagonal_shell_breakup_bias", 0.80)) * 0.12),
                        3,
                    ),
                )
                weave = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(downtown_record["lattice_center"].x)
                        + (float(inner.x) - float(downtown_record["lattice_center"].x))
                        * (0.56 + float(record.get("continuous_inner_weave_bias", 0.82)) * 0.10),
                        3,
                    ),
                    y=round(
                        float(downtown_record["lattice_center"].y)
                        + (float(inner.y) - float(downtown_record["lattice_center"].y))
                        * (0.52 + float(record.get("continuous_inner_weave_bias", 0.82)) * 0.10),
                        3,
                    ),
                )
                smoke_inner_weave_nodes.append(weave)
                thread = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(downtown_record["lattice_center"].x)
                        + (float(weave.x) - float(downtown_record["lattice_center"].x))
                        * (0.72 + float(record.get("annulus_core_threading_bias", 0.84)) * 0.08),
                        3,
                    ),
                    y=round(
                        float(downtown_record["lattice_center"].y)
                        + (float(weave.y) - float(downtown_record["lattice_center"].y))
                        * (0.70 + float(record.get("annulus_core_threading_bias", 0.84)) * 0.08),
                        3,
                    ),
                )
                smoke_thread_nodes.append(thread)
                relief = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(record["lattice_center"].x)
                        + (float(inner.x) - float(record["lattice_center"].x))
                        * (0.44 + float(record.get("precinct_starburst_attenuation_bias", 0.82)) * 0.12),
                        3,
                    ),
                    y=round(
                        float(record["lattice_center"].y)
                        + (float(inner.y) - float(record["lattice_center"].y))
                        * (0.42 + float(record.get("precinct_starburst_attenuation_bias", 0.82)) * 0.12),
                        3,
                    ),
                )
                knit = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(inner.x)
                        + (float(weave.x) - float(inner.x))
                        * (0.44 + float(record.get("quadrant_interior_knitting_bias", 0.82)) * 0.16),
                        3,
                    ),
                    y=round(
                        float(inner.y)
                        + (float(weave.y) - float(inner.y))
                        * (0.40 + float(record.get("quadrant_interior_knitting_bias", 0.82)) * 0.16),
                        3,
                    ),
                )
                knot_flat = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(record["lattice_center"].x)
                        + (float(relief.x) - float(record["lattice_center"].x))
                        * (0.52 + float(record.get("precinct_knot_flattening_bias", 0.80)) * 0.14),
                        3,
                    ),
                    y=round(
                        float(record["lattice_center"].y)
                        + (float(relief.y) - float(record["lattice_center"].y))
                        * (0.50 + float(record.get("precinct_knot_flattening_bias", 0.80)) * 0.14),
                        3,
                    ),
                )
                texture = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(knit.x) + float(knot_flat.x)) * 0.5
                        + (float(thread.x) - (float(knit.x) + float(knot_flat.x)) * 0.5)
                        * (0.14 + float(record.get("distributed_local_texture_bias", 0.84)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(knit.y) + float(knot_flat.y)) * 0.5
                        + (float(thread.y) - (float(knit.y) + float(knot_flat.y)) * 0.5)
                        * (0.14 + float(record.get("distributed_local_texture_bias", 0.84)) * 0.10),
                        3,
                    ),
                )
                mesh_stitch = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(knit.x) + float(texture.x)) * 0.5
                        + (float(inner.x) - (float(knit.x) + float(texture.x)) * 0.5)
                        * (0.18 + float(record.get("quadrant_local_mesh_stitch_bias", 0.82)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(knit.y) + float(texture.y)) * 0.5
                        + (float(inner.y) - (float(knit.y) + float(texture.y)) * 0.5)
                        * (0.18 + float(record.get("quadrant_local_mesh_stitch_bias", 0.82)) * 0.10),
                        3,
                    ),
                )
                core_flat = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(knot_flat.x)
                        + (float(texture.x) - float(knot_flat.x))
                        * (0.20 + float(record.get("precinct_core_destarburst_bias", 0.80)) * 0.12),
                        3,
                    ),
                    y=round(
                        float(knot_flat.y)
                        + (float(texture.y) - float(knot_flat.y))
                        * (0.20 + float(record.get("precinct_core_destarburst_bias", 0.80)) * 0.12),
                        3,
                    ),
                )
                secondary = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(mesh_stitch.x) + float(thread.x)) * 0.5
                        + (float(weave.x) - (float(mesh_stitch.x) + float(thread.x)) * 0.5)
                        * (0.18 + float(record.get("distributed_secondary_street_fill_bias", 0.84)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(mesh_stitch.y) + float(thread.y)) * 0.5
                        + (float(weave.y) - (float(mesh_stitch.y) + float(thread.y)) * 0.5)
                        * (0.18 + float(record.get("distributed_secondary_street_fill_bias", 0.84)) * 0.10),
                        3,
                    ),
                )
                shell_thin = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(shell.x)
                        + (float(mesh_stitch.x) - float(shell.x))
                        * (0.24 + float(record.get("outer_shell_rail_thinning_bias", 0.82)) * 0.10),
                        3,
                    ),
                    y=round(
                        float(shell.y)
                        + (float(mesh_stitch.y) - float(shell.y))
                        * (0.22 + float(record.get("outer_shell_rail_thinning_bias", 0.82)) * 0.10),
                        3,
                    ),
                )
                shell_blend = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(shell_thin.x) + float(texture.x)) * 0.5
                        + (float(mesh_stitch.x) - (float(shell_thin.x) + float(texture.x)) * 0.5)
                        * (0.18 + float(record.get("precinct_shell_mesh_blend_bias", 0.80)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(shell_thin.y) + float(texture.y)) * 0.5
                        + (float(mesh_stitch.y) - (float(shell_thin.y) + float(texture.y)) * 0.5)
                        * (0.18 + float(record.get("precinct_shell_mesh_blend_bias", 0.80)) * 0.10),
                        3,
                    ),
                )
                tertiary = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(shell_blend.x) + float(secondary.x)) * 0.5
                        + (float(mesh_stitch.x) - (float(shell_blend.x) + float(secondary.x)) * 0.5)
                        * (0.18 + float(record.get("distributed_tertiary_street_fill_bias", 0.84)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(shell_blend.y) + float(secondary.y)) * 0.5
                        + (float(mesh_stitch.y) - (float(shell_blend.y) + float(secondary.y)) * 0.5)
                        * (0.18 + float(record.get("distributed_tertiary_street_fill_bias", 0.84)) * 0.10),
                        3,
                    ),
                )
                silhouette = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(shell.x)
                        + (float(tertiary.x) - float(shell.x))
                        * (0.30 + float(record.get("shell_silhouette_collapse_bias", 0.86)) * 0.12),
                        3,
                    ),
                    y=round(
                        float(shell.y)
                        + (float(tertiary.y) - float(shell.y))
                        * (0.28 + float(record.get("shell_silhouette_collapse_bias", 0.86)) * 0.12),
                        3,
                    ),
                )
                boundary = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(shell_blend.x) + float(texture.x)) * 0.5
                        + (float(silhouette.x) - (float(shell_blend.x) + float(texture.x)) * 0.5)
                        * (0.22 + float(record.get("precinct_boundary_dissolution_bias", 0.84)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(shell_blend.y) + float(texture.y)) * 0.5
                        + (float(silhouette.y) - (float(shell_blend.y) + float(texture.y)) * 0.5)
                        * (0.22 + float(record.get("precinct_boundary_dissolution_bias", 0.84)) * 0.10),
                        3,
                    ),
                )
                micro_fine = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(boundary.x) + float(mesh_stitch.x)) * 0.5
                        + (float(texture.x) - (float(boundary.x) + float(mesh_stitch.x)) * 0.5)
                        * (0.20 + float(record.get("fine_grain_street_texture_bias", 0.88)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(boundary.y) + float(mesh_stitch.y)) * 0.5
                        + (float(texture.y) - (float(boundary.y) + float(mesh_stitch.y)) * 0.5)
                        * (0.20 + float(record.get("fine_grain_street_texture_bias", 0.88)) * 0.10),
                        3,
                    ),
                )
                shell_soft = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(silhouette.x)
                        + (float(boundary.x) - float(silhouette.x))
                        * (0.20 + float(record.get("shell_silhouette_deemphasis_bias", 0.90)) * 0.10),
                        3,
                    ),
                    y=round(
                        float(silhouette.y)
                        + (float(boundary.y) - float(silhouette.y))
                        * (0.20 + float(record.get("shell_silhouette_deemphasis_bias", 0.90)) * 0.10),
                        3,
                    ),
                )
                knot_diffuse = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(knot_flat.x) + float(texture.x)) * 0.5
                        + (float(micro_fine.x) - (float(knot_flat.x) + float(texture.x)) * 0.5)
                        * (0.18 + float(record.get("precinct_knot_diffusion_bias", 0.88)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(knot_flat.y) + float(texture.y)) * 0.5
                        + (float(micro_fine.y) - (float(knot_flat.y) + float(texture.y)) * 0.5)
                        * (0.18 + float(record.get("precinct_knot_diffusion_bias", 0.88)) * 0.10),
                        3,
                    ),
                )
                weave_fine = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(micro_fine.x) + float(texture.x)) * 0.5
                        + (float(mesh_stitch.x) - (float(micro_fine.x) + float(texture.x)) * 0.5)
                        * (0.18 + float(record.get("distributed_fine_grain_weave_bias", 0.92)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(micro_fine.y) + float(texture.y)) * 0.5
                        + (float(mesh_stitch.y) - (float(micro_fine.y) + float(texture.y)) * 0.5)
                        * (0.18 + float(record.get("distributed_fine_grain_weave_bias", 0.92)) * 0.10),
                        3,
                    ),
                )
                arc_soft = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(shell_soft.x) + float(boundary.x)) * 0.5
                        + (float(weave_fine.x) - (float(shell_soft.x) + float(boundary.x)) * 0.5)
                        * (0.16 + float(record.get("shell_arc_softening_bias", 0.92)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(shell_soft.y) + float(boundary.y)) * 0.5
                        + (float(weave_fine.y) - (float(shell_soft.y) + float(boundary.y)) * 0.5)
                        * (0.16 + float(record.get("shell_arc_softening_bias", 0.92)) * 0.10),
                        3,
                    ),
                )
                knot_diffuse_v2 = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(knot_diffuse.x) + float(weave_fine.x)) * 0.5
                        + (float(mesh_stitch.x) - (float(knot_diffuse.x) + float(weave_fine.x)) * 0.5)
                        * (0.16 + float(record.get("precinct_knot_diffusion_v2_bias", 0.90)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(knot_diffuse.y) + float(weave_fine.y)) * 0.5
                        + (float(mesh_stitch.y) - (float(knot_diffuse.y) + float(weave_fine.y)) * 0.5)
                        * (0.16 + float(record.get("precinct_knot_diffusion_v2_bias", 0.90)) * 0.10),
                        3,
                    ),
                )
                weave_cont = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(weave_fine.x) + float(knit.x)) * 0.5
                        + (float(thread.x) - (float(weave_fine.x) + float(knit.x)) * 0.5)
                        * (0.16 + float(record.get("interior_weave_continuity_bias", 0.94)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(weave_fine.y) + float(knit.y)) * 0.5
                        + (float(thread.y) - (float(weave_fine.y) + float(knit.y)) * 0.5)
                        * (0.16 + float(record.get("interior_weave_continuity_bias", 0.94)) * 0.10),
                        3,
                    ),
                )
                arc_fade = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(arc_soft.x) + float(weave_cont.x)) * 0.5
                        + (float(texture.x) - (float(arc_soft.x) + float(weave_cont.x)) * 0.5)
                        * (0.14 + float(record.get("shell_arc_fading_bias", 0.94)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(arc_soft.y) + float(weave_cont.y)) * 0.5
                        + (float(texture.y) - (float(arc_soft.y) + float(weave_cont.y)) * 0.5)
                        * (0.14 + float(record.get("shell_arc_fading_bias", 0.94)) * 0.10),
                        3,
                    ),
                )
                knot_bleed = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(knot_diffuse_v2.x) + float(weave_cont.x)) * 0.5
                        + (float(thread.x) - (float(knot_diffuse_v2.x) + float(weave_cont.x)) * 0.5)
                        * (0.14 + float(record.get("precinct_knot_bleed_bias", 0.92)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(knot_diffuse_v2.y) + float(weave_cont.y)) * 0.5
                        + (float(thread.y) - (float(knot_diffuse_v2.y) + float(weave_cont.y)) * 0.5)
                        * (0.14 + float(record.get("precinct_knot_bleed_bias", 0.92)) * 0.10),
                        3,
                    ),
                )
                thread_fine = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(weave_cont.x) + float(thread.x)) * 0.5
                        + (float(knit.x) - (float(weave_cont.x) + float(thread.x)) * 0.5)
                        * (0.14 + float(record.get("weave_corridor_threading_bias", 0.96)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(weave_cont.y) + float(thread.y)) * 0.5
                        + (float(knit.y) - (float(weave_cont.y) + float(thread.y)) * 0.5)
                        * (0.14 + float(record.get("weave_corridor_threading_bias", 0.96)) * 0.10),
                        3,
                    ),
                )
                for src_id, dst_id in (
                    (orbit.node_id, inner.node_id),
                    (inner.node_id, int(downtown_record["lattice_center"].node_id)),
                    (ring.node_id, shell.node_id),
                    (shell.node_id, inner.node_id),
                    (shell.node_id, int(record["lattice_center"].node_id)),
                    (shell.node_id, breakup.node_id),
                    (breakup.node_id, relief.node_id),
                    (relief.node_id, inner.node_id),
                    (breakup.node_id, weave.node_id),
                    (weave.node_id, thread.node_id),
                    (thread.node_id, inner.node_id),
                    (weave.node_id, inner.node_id),
                    (inner.node_id, knit.node_id),
                    (knit.node_id, texture.node_id),
                    (texture.node_id, relief.node_id),
                    (texture.node_id, weave.node_id),
                    (knot_flat.node_id, relief.node_id),
                    (knot_flat.node_id, texture.node_id),
                    (mesh_stitch.node_id, texture.node_id),
                    (mesh_stitch.node_id, inner.node_id),
                    (core_flat.node_id, knot_flat.node_id),
                    (core_flat.node_id, texture.node_id),
                    (secondary.node_id, mesh_stitch.node_id),
                    (secondary.node_id, thread.node_id),
                    (secondary.node_id, weave.node_id),
                    (shell.node_id, shell_thin.node_id),
                    (shell_thin.node_id, shell_blend.node_id),
                    (shell_blend.node_id, tertiary.node_id),
                    (tertiary.node_id, mesh_stitch.node_id),
                    (tertiary.node_id, texture.node_id),
                    (shell_blend.node_id, texture.node_id),
                    (shell_thin.node_id, silhouette.node_id),
                    (silhouette.node_id, boundary.node_id),
                    (boundary.node_id, mesh_stitch.node_id),
                    (boundary.node_id, texture.node_id),
                    (boundary.node_id, tertiary.node_id),
                    (micro_fine.node_id, texture.node_id),
                    (micro_fine.node_id, mesh_stitch.node_id),
                    (micro_fine.node_id, boundary.node_id),
                    (shell_soft.node_id, boundary.node_id),
                    (shell_soft.node_id, micro_fine.node_id),
                    (arc_soft.node_id, boundary.node_id),
                    (arc_soft.node_id, weave_fine.node_id),
                    (knot_diffuse.node_id, texture.node_id),
                    (knot_diffuse.node_id, micro_fine.node_id),
                    (knot_diffuse_v2.node_id, weave_fine.node_id),
                    (knot_diffuse_v2.node_id, mesh_stitch.node_id),
                    (weave_fine.node_id, texture.node_id),
                    (weave_fine.node_id, mesh_stitch.node_id),
                    (weave_fine.node_id, knot_diffuse.node_id),
                    (weave_cont.node_id, weave_fine.node_id),
                    (weave_cont.node_id, knit.node_id),
                    (weave_cont.node_id, thread.node_id),
                    (arc_fade.node_id, weave_cont.node_id),
                    (arc_fade.node_id, texture.node_id),
                    (knot_bleed.node_id, weave_cont.node_id),
                    (knot_bleed.node_id, thread.node_id),
                    (thread_fine.node_id, weave_cont.node_id),
                    (thread_fine.node_id, knit.node_id),
                ):
                    _add_bidirectional_link_pair(
                        link_builder,
                        src_id,
                        dst_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.0,
                        capacity=4.8,
                    )
                outer_rail_attenuation_v2_count += 2
                interior_fabric_densification_count += 3
                precinct_shell_dissolution_count += 2
                diagonal_shell_breakup_count += 2
                continuous_inner_weave_count += 2
                precinct_mass_deemphasis_count += 2
                quadrant_rail_dissolution_count += 2
                precinct_starburst_attenuation_count += 2
                annulus_core_threading_count += 2
                quadrant_interior_knitting_count += 2
                precinct_knot_flattening_count += 2
                distributed_local_texture_count += 2
                quadrant_local_mesh_stitch_count += 2
                precinct_core_destarburst_count += 2
                distributed_secondary_street_fill_count += 2
                outer_shell_rail_thinning_count += 2
                precinct_shell_mesh_blending_count += 2
                distributed_tertiary_street_fill_count += 2
                shell_silhouette_collapse_count += 2
                precinct_boundary_dissolution_count += 2
                fine_grain_street_texture_count += 2
                shell_silhouette_deemphasis_count += 2
                precinct_knot_diffusion_count += 2
                distributed_fine_grain_weave_count += 2
                shell_arc_softening_count += 2
                precinct_knot_diffusion_v2_count += 2
                interior_weave_continuity_count += 2
                shell_arc_fading_count += 2
                precinct_knot_bleed_count += 2
                weave_corridor_threading_count += 2
            for current, nxt in zip(smoke_inner_weave_nodes, smoke_inner_weave_nodes[1:] + smoke_inner_weave_nodes[:1]):
                if current.node_id == nxt.node_id:
                    continue
                _add_bidirectional_link_pair(
                    link_builder,
                    current.node_id,
                    nxt.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                continuous_inner_weave_count += 2
                diagonal_shell_breakup_count += 1

        if scenario_id == "synthetic_100k" and len(equalization_ring_nodes) >= 2:
            annulus_mesh_nodes: list[Node] = []
            for current, nxt in zip(equalization_ring_nodes, equalization_ring_nodes[1:] + equalization_ring_nodes[:1]):
                mesh = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(current.x) + float(nxt.x)) * 0.5
                        + (float(downtown_record["lattice_center"].x) - (float(current.x) + float(nxt.x)) * 0.5)
                        * (0.06 + float(downtown_record.get("inner_annulus_mesh_equalization_bias", 0.78)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(current.y) + float(nxt.y)) * 0.5
                        + (float(downtown_record["lattice_center"].y) - (float(current.y) + float(nxt.y)) * 0.5)
                        * (0.06 + float(downtown_record.get("inner_annulus_mesh_equalization_bias", 0.78)) * 0.10),
                        3,
                    ),
                )
                annulus_mesh_nodes.append(mesh)
                for src_id, dst_id in (
                    (current.node_id, mesh.node_id),
                    (mesh.node_id, nxt.node_id),
                ):
                    _add_bidirectional_link_pair(
                        link_builder,
                        src_id,
                        dst_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.0,
                        capacity=4.8,
                    )
                inner_annulus_mesh_equalization_count += 2
                large_map_scaffold_dissolution_count += 1
            for current, nxt in zip(annulus_mesh_nodes, annulus_mesh_nodes[1:] + annulus_mesh_nodes[:1]):
                if current.node_id == nxt.node_id:
                    continue
                _add_bidirectional_link_pair(
                    link_builder,
                    current.node_id,
                    nxt.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                inner_annulus_mesh_equalization_count += 2
                large_map_scaffold_dissolution_count += 1
            ordered_large_records = sorted(
                outer_records,
                key=lambda item: math.atan2(
                    float(item["center_y"]) - float(downtown_record["center_y"]),
                    float(item["center_x"]) - float(downtown_record["center_x"]),
                ),
            )
            large_inner_weave_nodes: list[Node] = []
            large_thread_nodes: list[Node] = []
            for record, ring, mesh in zip(ordered_large_records, equalization_ring_nodes, annulus_mesh_nodes):
                interior = _nearest_precinct_node(
                    tuple(record.get("interior_nodes", ())) or (record["lattice_center"],),
                    (float(downtown_record["center_x"]), float(downtown_record["center_y"])),
                )
                densify = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(interior.x)
                        + (float(mesh.x) - float(interior.x))
                        * (0.36 + float(record.get("interior_fabric_densification_bias", 0.80)) * 0.18),
                        3,
                    ),
                    y=round(
                        float(interior.y)
                        + (float(mesh.y) - float(interior.y))
                        * (0.34 + float(record.get("interior_fabric_densification_bias", 0.80)) * 0.18),
                        3,
                    ),
                )
                shell = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(record["lattice_center"].x)
                        + (float(ring.x) - float(record["lattice_center"].x))
                        * (0.38 + float(record.get("precinct_shell_dissolution_bias", 0.78)) * 0.16),
                        3,
                    ),
                    y=round(
                        float(record["lattice_center"].y)
                        + (float(ring.y) - float(record["lattice_center"].y))
                        * (0.36 + float(record.get("precinct_shell_dissolution_bias", 0.78)) * 0.16),
                        3,
                    ),
                )
                breakup = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(shell.x)
                        + (float(densify.x) - float(shell.x))
                        * (0.46 + float(record.get("diagonal_shell_breakup_bias", 0.80)) * 0.12),
                        3,
                    ),
                    y=round(
                        float(shell.y)
                        + (float(densify.y) - float(shell.y))
                        * (0.44 + float(record.get("diagonal_shell_breakup_bias", 0.80)) * 0.12),
                        3,
                    ),
                )
                weave = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(downtown_record["lattice_center"].x)
                        + (float(densify.x) - float(downtown_record["lattice_center"].x))
                        * (0.58 + float(record.get("continuous_inner_weave_bias", 0.82)) * 0.10),
                        3,
                    ),
                    y=round(
                        float(downtown_record["lattice_center"].y)
                        + (float(densify.y) - float(downtown_record["lattice_center"].y))
                        * (0.54 + float(record.get("continuous_inner_weave_bias", 0.82)) * 0.10),
                        3,
                    ),
                )
                large_inner_weave_nodes.append(weave)
                thread = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(downtown_record["lattice_center"].x)
                        + (float(weave.x) - float(downtown_record["lattice_center"].x))
                        * (0.74 + float(record.get("annulus_core_threading_bias", 0.84)) * 0.08),
                        3,
                    ),
                    y=round(
                        float(downtown_record["lattice_center"].y)
                        + (float(weave.y) - float(downtown_record["lattice_center"].y))
                        * (0.72 + float(record.get("annulus_core_threading_bias", 0.84)) * 0.08),
                        3,
                    ),
                )
                large_thread_nodes.append(thread)
                relief = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(record["lattice_center"].x)
                        + (float(densify.x) - float(record["lattice_center"].x))
                        * (0.46 + float(record.get("precinct_starburst_attenuation_bias", 0.82)) * 0.12),
                        3,
                    ),
                    y=round(
                        float(record["lattice_center"].y)
                        + (float(densify.y) - float(record["lattice_center"].y))
                        * (0.44 + float(record.get("precinct_starburst_attenuation_bias", 0.82)) * 0.12),
                        3,
                    ),
                )
                knit = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(densify.x)
                        + (float(weave.x) - float(densify.x))
                        * (0.46 + float(record.get("quadrant_interior_knitting_bias", 0.82)) * 0.16),
                        3,
                    ),
                    y=round(
                        float(densify.y)
                        + (float(weave.y) - float(densify.y))
                        * (0.42 + float(record.get("quadrant_interior_knitting_bias", 0.82)) * 0.16),
                        3,
                    ),
                )
                knot_flat = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(record["lattice_center"].x)
                        + (float(relief.x) - float(record["lattice_center"].x))
                        * (0.54 + float(record.get("precinct_knot_flattening_bias", 0.80)) * 0.12),
                        3,
                    ),
                    y=round(
                        float(record["lattice_center"].y)
                        + (float(relief.y) - float(record["lattice_center"].y))
                        * (0.50 + float(record.get("precinct_knot_flattening_bias", 0.80)) * 0.12),
                        3,
                    ),
                )
                texture = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(knit.x) + float(knot_flat.x)) * 0.5
                        + (float(thread.x) - (float(knit.x) + float(knot_flat.x)) * 0.5)
                        * (0.16 + float(record.get("distributed_local_texture_bias", 0.84)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(knit.y) + float(knot_flat.y)) * 0.5
                        + (float(thread.y) - (float(knit.y) + float(knot_flat.y)) * 0.5)
                        * (0.16 + float(record.get("distributed_local_texture_bias", 0.84)) * 0.10),
                        3,
                    ),
                )
                mesh_stitch = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(knit.x) + float(texture.x)) * 0.5
                        + (float(densify.x) - (float(knit.x) + float(texture.x)) * 0.5)
                        * (0.20 + float(record.get("quadrant_local_mesh_stitch_bias", 0.82)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(knit.y) + float(texture.y)) * 0.5
                        + (float(densify.y) - (float(knit.y) + float(texture.y)) * 0.5)
                        * (0.20 + float(record.get("quadrant_local_mesh_stitch_bias", 0.82)) * 0.10),
                        3,
                    ),
                )
                core_flat = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(knot_flat.x)
                        + (float(texture.x) - float(knot_flat.x))
                        * (0.22 + float(record.get("precinct_core_destarburst_bias", 0.80)) * 0.12),
                        3,
                    ),
                    y=round(
                        float(knot_flat.y)
                        + (float(texture.y) - float(knot_flat.y))
                        * (0.22 + float(record.get("precinct_core_destarburst_bias", 0.80)) * 0.12),
                        3,
                    ),
                )
                secondary = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(mesh_stitch.x) + float(thread.x)) * 0.5
                        + (float(weave.x) - (float(mesh_stitch.x) + float(thread.x)) * 0.5)
                        * (0.20 + float(record.get("distributed_secondary_street_fill_bias", 0.84)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(mesh_stitch.y) + float(thread.y)) * 0.5
                        + (float(weave.y) - (float(mesh_stitch.y) + float(thread.y)) * 0.5)
                        * (0.20 + float(record.get("distributed_secondary_street_fill_bias", 0.84)) * 0.10),
                        3,
                    ),
                )
                shell_thin = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(shell.x)
                        + (float(mesh_stitch.x) - float(shell.x))
                        * (0.26 + float(record.get("outer_shell_rail_thinning_bias", 0.82)) * 0.10),
                        3,
                    ),
                    y=round(
                        float(shell.y)
                        + (float(mesh_stitch.y) - float(shell.y))
                        * (0.24 + float(record.get("outer_shell_rail_thinning_bias", 0.82)) * 0.10),
                        3,
                    ),
                )
                shell_blend = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(shell_thin.x) + float(texture.x)) * 0.5
                        + (float(mesh_stitch.x) - (float(shell_thin.x) + float(texture.x)) * 0.5)
                        * (0.20 + float(record.get("precinct_shell_mesh_blend_bias", 0.80)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(shell_thin.y) + float(texture.y)) * 0.5
                        + (float(mesh_stitch.y) - (float(shell_thin.y) + float(texture.y)) * 0.5)
                        * (0.20 + float(record.get("precinct_shell_mesh_blend_bias", 0.80)) * 0.10),
                        3,
                    ),
                )
                tertiary = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(shell_blend.x) + float(secondary.x)) * 0.5
                        + (float(mesh_stitch.x) - (float(shell_blend.x) + float(secondary.x)) * 0.5)
                        * (0.20 + float(record.get("distributed_tertiary_street_fill_bias", 0.84)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(shell_blend.y) + float(secondary.y)) * 0.5
                        + (float(mesh_stitch.y) - (float(shell_blend.y) + float(secondary.y)) * 0.5)
                        * (0.20 + float(record.get("distributed_tertiary_street_fill_bias", 0.84)) * 0.10),
                        3,
                    ),
                )
                silhouette = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(shell.x)
                        + (float(tertiary.x) - float(shell.x))
                        * (0.32 + float(record.get("shell_silhouette_collapse_bias", 0.86)) * 0.12),
                        3,
                    ),
                    y=round(
                        float(shell.y)
                        + (float(tertiary.y) - float(shell.y))
                        * (0.30 + float(record.get("shell_silhouette_collapse_bias", 0.86)) * 0.12),
                        3,
                    ),
                )
                boundary = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(shell_blend.x) + float(texture.x)) * 0.5
                        + (float(silhouette.x) - (float(shell_blend.x) + float(texture.x)) * 0.5)
                        * (0.24 + float(record.get("precinct_boundary_dissolution_bias", 0.84)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(shell_blend.y) + float(texture.y)) * 0.5
                        + (float(silhouette.y) - (float(shell_blend.y) + float(texture.y)) * 0.5)
                        * (0.24 + float(record.get("precinct_boundary_dissolution_bias", 0.84)) * 0.10),
                        3,
                    ),
                )
                micro_fine = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(boundary.x) + float(mesh_stitch.x)) * 0.5
                        + (float(texture.x) - (float(boundary.x) + float(mesh_stitch.x)) * 0.5)
                        * (0.22 + float(record.get("fine_grain_street_texture_bias", 0.88)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(boundary.y) + float(mesh_stitch.y)) * 0.5
                        + (float(texture.y) - (float(boundary.y) + float(mesh_stitch.y)) * 0.5)
                        * (0.22 + float(record.get("fine_grain_street_texture_bias", 0.88)) * 0.10),
                        3,
                    ),
                )
                shell_soft = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        float(silhouette.x)
                        + (float(boundary.x) - float(silhouette.x))
                        * (0.22 + float(record.get("shell_silhouette_deemphasis_bias", 0.90)) * 0.10),
                        3,
                    ),
                    y=round(
                        float(silhouette.y)
                        + (float(boundary.y) - float(silhouette.y))
                        * (0.22 + float(record.get("shell_silhouette_deemphasis_bias", 0.90)) * 0.10),
                        3,
                    ),
                )
                knot_diffuse = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(knot_flat.x) + float(texture.x)) * 0.5
                        + (float(micro_fine.x) - (float(knot_flat.x) + float(texture.x)) * 0.5)
                        * (0.20 + float(record.get("precinct_knot_diffusion_bias", 0.88)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(knot_flat.y) + float(texture.y)) * 0.5
                        + (float(micro_fine.y) - (float(knot_flat.y) + float(texture.y)) * 0.5)
                        * (0.20 + float(record.get("precinct_knot_diffusion_bias", 0.88)) * 0.10),
                        3,
                    ),
                )
                weave_fine = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(micro_fine.x) + float(texture.x)) * 0.5
                        + (float(mesh_stitch.x) - (float(micro_fine.x) + float(texture.x)) * 0.5)
                        * (0.20 + float(record.get("distributed_fine_grain_weave_bias", 0.92)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(micro_fine.y) + float(texture.y)) * 0.5
                        + (float(mesh_stitch.y) - (float(micro_fine.y) + float(texture.y)) * 0.5)
                        * (0.20 + float(record.get("distributed_fine_grain_weave_bias", 0.92)) * 0.10),
                        3,
                    ),
                )
                arc_soft = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(shell_soft.x) + float(boundary.x)) * 0.5
                        + (float(weave_fine.x) - (float(shell_soft.x) + float(boundary.x)) * 0.5)
                        * (0.18 + float(record.get("shell_arc_softening_bias", 0.92)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(shell_soft.y) + float(boundary.y)) * 0.5
                        + (float(weave_fine.y) - (float(shell_soft.y) + float(boundary.y)) * 0.5)
                        * (0.18 + float(record.get("shell_arc_softening_bias", 0.92)) * 0.10),
                        3,
                    ),
                )
                knot_diffuse_v2 = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(knot_diffuse.x) + float(weave_fine.x)) * 0.5
                        + (float(mesh_stitch.x) - (float(knot_diffuse.x) + float(weave_fine.x)) * 0.5)
                        * (0.18 + float(record.get("precinct_knot_diffusion_v2_bias", 0.90)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(knot_diffuse.y) + float(weave_fine.y)) * 0.5
                        + (float(mesh_stitch.y) - (float(knot_diffuse.y) + float(weave_fine.y)) * 0.5)
                        * (0.18 + float(record.get("precinct_knot_diffusion_v2_bias", 0.90)) * 0.10),
                        3,
                    ),
                )
                weave_cont = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(weave_fine.x) + float(knit.x)) * 0.5
                        + (float(thread.x) - (float(weave_fine.x) + float(knit.x)) * 0.5)
                        * (0.18 + float(record.get("interior_weave_continuity_bias", 0.94)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(weave_fine.y) + float(knit.y)) * 0.5
                        + (float(thread.y) - (float(weave_fine.y) + float(knit.y)) * 0.5)
                        * (0.18 + float(record.get("interior_weave_continuity_bias", 0.94)) * 0.10),
                        3,
                    ),
                )
                arc_fade = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(arc_soft.x) + float(weave_cont.x)) * 0.5
                        + (float(texture.x) - (float(arc_soft.x) + float(weave_cont.x)) * 0.5)
                        * (0.16 + float(record.get("shell_arc_fading_bias", 0.94)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(arc_soft.y) + float(weave_cont.y)) * 0.5
                        + (float(texture.y) - (float(arc_soft.y) + float(weave_cont.y)) * 0.5)
                        * (0.16 + float(record.get("shell_arc_fading_bias", 0.94)) * 0.10),
                        3,
                    ),
                )
                knot_bleed = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(knot_diffuse_v2.x) + float(weave_cont.x)) * 0.5
                        + (float(thread.x) - (float(knot_diffuse_v2.x) + float(weave_cont.x)) * 0.5)
                        * (0.16 + float(record.get("precinct_knot_bleed_bias", 0.92)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(knot_diffuse_v2.y) + float(weave_cont.y)) * 0.5
                        + (float(thread.y) - (float(knot_diffuse_v2.y) + float(weave_cont.y)) * 0.5)
                        * (0.16 + float(record.get("precinct_knot_bleed_bias", 0.92)) * 0.10),
                        3,
                    ),
                )
                thread_fine = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(weave_cont.x) + float(thread.x)) * 0.5
                        + (float(knit.x) - (float(weave_cont.x) + float(thread.x)) * 0.5)
                        * (0.16 + float(record.get("weave_corridor_threading_bias", 0.96)) * 0.10),
                        3,
                    ),
                    y=round(
                        (float(weave_cont.y) + float(thread.y)) * 0.5
                        + (float(knit.y) - (float(weave_cont.y) + float(thread.y)) * 0.5)
                        * (0.16 + float(record.get("weave_corridor_threading_bias", 0.96)) * 0.10),
                        3,
                    ),
                )
                for src_id, dst_id in (
                    (interior.node_id, densify.node_id),
                    (densify.node_id, mesh.node_id),
                    (densify.node_id, int(downtown_record["lattice_center"].node_id)),
                    (ring.node_id, shell.node_id),
                    (shell.node_id, densify.node_id),
                    (shell.node_id, int(record["lattice_center"].node_id)),
                    (shell.node_id, breakup.node_id),
                    (breakup.node_id, relief.node_id),
                    (relief.node_id, densify.node_id),
                    (breakup.node_id, weave.node_id),
                    (weave.node_id, thread.node_id),
                    (thread.node_id, densify.node_id),
                    (weave.node_id, densify.node_id),
                    (densify.node_id, knit.node_id),
                    (knit.node_id, texture.node_id),
                    (texture.node_id, relief.node_id),
                    (texture.node_id, weave.node_id),
                    (knot_flat.node_id, relief.node_id),
                    (knot_flat.node_id, texture.node_id),
                    (mesh_stitch.node_id, texture.node_id),
                    (mesh_stitch.node_id, densify.node_id),
                    (core_flat.node_id, knot_flat.node_id),
                    (core_flat.node_id, texture.node_id),
                    (secondary.node_id, mesh_stitch.node_id),
                    (secondary.node_id, thread.node_id),
                    (secondary.node_id, weave.node_id),
                    (shell.node_id, shell_thin.node_id),
                    (shell_thin.node_id, shell_blend.node_id),
                    (shell_blend.node_id, tertiary.node_id),
                    (tertiary.node_id, mesh_stitch.node_id),
                    (tertiary.node_id, texture.node_id),
                    (shell_blend.node_id, texture.node_id),
                    (shell_thin.node_id, silhouette.node_id),
                    (silhouette.node_id, boundary.node_id),
                    (boundary.node_id, mesh_stitch.node_id),
                    (boundary.node_id, texture.node_id),
                    (boundary.node_id, tertiary.node_id),
                    (micro_fine.node_id, texture.node_id),
                    (micro_fine.node_id, mesh_stitch.node_id),
                    (micro_fine.node_id, boundary.node_id),
                    (shell_soft.node_id, boundary.node_id),
                    (shell_soft.node_id, micro_fine.node_id),
                    (arc_soft.node_id, boundary.node_id),
                    (arc_soft.node_id, weave_fine.node_id),
                    (knot_diffuse.node_id, texture.node_id),
                    (knot_diffuse.node_id, micro_fine.node_id),
                    (knot_diffuse_v2.node_id, weave_fine.node_id),
                    (knot_diffuse_v2.node_id, mesh_stitch.node_id),
                    (weave_fine.node_id, texture.node_id),
                    (weave_fine.node_id, mesh_stitch.node_id),
                    (weave_fine.node_id, knot_diffuse.node_id),
                    (weave_cont.node_id, weave_fine.node_id),
                    (weave_cont.node_id, knit.node_id),
                    (weave_cont.node_id, thread.node_id),
                    (arc_fade.node_id, weave_cont.node_id),
                    (arc_fade.node_id, texture.node_id),
                    (knot_bleed.node_id, weave_cont.node_id),
                    (knot_bleed.node_id, thread.node_id),
                    (thread_fine.node_id, weave_cont.node_id),
                    (thread_fine.node_id, knit.node_id),
                ):
                    _add_bidirectional_link_pair(
                        link_builder,
                        src_id,
                        dst_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.0,
                        capacity=4.8,
                    )
                interior_fabric_densification_count += 4
                precinct_shell_dissolution_count += 2
                outer_rail_attenuation_v2_count += 1
                diagonal_shell_breakup_count += 2
                continuous_inner_weave_count += 2
                precinct_mass_deemphasis_count += 2
                quadrant_rail_dissolution_count += 2
                precinct_starburst_attenuation_count += 2
                annulus_core_threading_count += 2
                quadrant_interior_knitting_count += 2
                precinct_knot_flattening_count += 2
                distributed_local_texture_count += 2
                quadrant_local_mesh_stitch_count += 2
                precinct_core_destarburst_count += 2
                distributed_secondary_street_fill_count += 2
                outer_shell_rail_thinning_count += 2
                precinct_shell_mesh_blending_count += 2
                distributed_tertiary_street_fill_count += 2
                shell_silhouette_collapse_count += 2
                precinct_boundary_dissolution_count += 2
                fine_grain_street_texture_count += 2
                shell_silhouette_deemphasis_count += 2
                precinct_knot_diffusion_count += 2
                distributed_fine_grain_weave_count += 2
                shell_arc_softening_count += 2
                precinct_knot_diffusion_v2_count += 2
                interior_weave_continuity_count += 2
                shell_arc_fading_count += 2
                precinct_knot_bleed_count += 2
                weave_corridor_threading_count += 2
            for current, nxt in zip(large_inner_weave_nodes, large_inner_weave_nodes[1:] + large_inner_weave_nodes[:1]):
                if current.node_id == nxt.node_id:
                    continue
                _add_bidirectional_link_pair(
                    link_builder,
                    current.node_id,
                    nxt.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.0,
                    capacity=4.8,
                )
                continuous_inner_weave_count += 2
                diagonal_shell_breakup_count += 1

    for side, nodes in side_connector_nodes.items():
        ordered = sorted(
            {int(node.node_id): node for node in nodes}.values(),
            key=lambda node: (float(node.y), float(node.x)),
        )
        if not ordered or downtown_record is None:
            continue
        mean_x = sum(float(node.x) for node in ordered) / float(len(ordered))
        anchor_x = float(downtown_record["center_x"]) + (mean_x - float(downtown_record["center_x"])) * 0.72
        spine_nodes: list[Node] = []
        for idx, node in enumerate(ordered):
            side_spine = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round(anchor_x + ((-8.0 if side == "west" else 8.0) if idx % 2 == 0 else 0.0), 3),
                y=round(float(node.y) + (8.0 if idx % 2 == 0 else -8.0), 3),
            )
            spine_nodes.append(side_spine)
            _add_bidirectional_link_pair(
                link_builder,
                node.node_id,
                side_spine.node_id,
                road_class=RoadClass.COLLECTOR,
                lanes=1,
                speed_mps=9.0,
                capacity=5.6,
            )
            continuous_connector_corridor_count += 2
            precinct_edge_bleed_count += 1
        for current, nxt in zip(spine_nodes, spine_nodes[1:]):
            if current.node_id == nxt.node_id:
                continue
            _add_bidirectional_link_pair(
                link_builder,
                current.node_id,
                nxt.node_id,
                road_class=RoadClass.COLLECTOR,
                lanes=1,
                speed_mps=9.0,
                capacity=5.6,
            )
            continuous_connector_corridor_count += 2
            overlap_mesh_fill_count += 1
            midfield_parcel_stitch_count += 1
        for current, nxt in zip(spine_nodes, spine_nodes[2:]):
            if current.node_id == nxt.node_id:
                continue
            _add_bidirectional_link_pair(
                link_builder,
                current.node_id,
                nxt.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.0,
                capacity=4.8,
            )
            overlap_mesh_fill_count += 2
            corridor_precinct_blend_count += 2
        side_spine_nodes[side] = spine_nodes

    barrier_side_lookup = {
        side: sorted(
            {int(node.node_id): node for node in nodes}.values(),
            key=lambda node: (float(node.y), float(node.x)),
        )
        for side, nodes in barrier_side_spine_nodes.items()
    }
    side_records = {
        side: sorted(
            [record for record in district_records if str(record.get("river_side", "")) == side],
            key=lambda record: float(record["center_y"]),
        )
        for side in ("west", "east")
    }
    for side, records in side_records.items():
        spines = tuple(side_spine_nodes.get(side, ()))
        barriers = tuple(barrier_side_lookup.get(side, ()))
        if not spines or not records:
            continue
        sign = -1.0 if side == "west" else 1.0
        for idx, record in enumerate(records):
            halo_nodes = tuple(record.get("halo_nodes", ())) + tuple(record.get("anchor_nodes", ()))
            interior_nodes = tuple(record.get("interior_nodes", ())) or (record["lattice_center"],)
            halo = _nearest_precinct_node(halo_nodes, (float(record["center_x"]), float(record["center_y"])))
            interior = _nearest_precinct_node(interior_nodes, (float(record["center_x"]), float(record["center_y"])))
            spine = _nearest_precinct_node(spines, (float(record["center_x"]), float(record["center_y"])))
            breakup = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round(
                    float(spine.x)
                    + (float(halo.x) - float(spine.x)) * (0.34 + record["perimeter_rail_breakup_bias"] * 0.08)
                    + sign * (12.0 + (idx % 2) * 6.0),
                    3,
                ),
                y=round(
                    float(spine.y)
                    + (float(interior.y) - float(spine.y)) * (0.26 + record["perimeter_rail_breakup_bias"] * 0.08)
                    + ((-10.0) if (idx % 2) == 0 else 10.0),
                    3,
                ),
            )
            web = _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=round(
                    (float(interior.x) + float(record["lattice_center"].x)) * 0.5 + sign * (6.0 + record["interior_web_thickening_bias"] * 3.0),
                    3,
                ),
                y=round(
                    (float(interior.y) + float(record["lattice_center"].y)) * 0.5
                    + ((8.0) if idx % 2 == 0 else -8.0) * (0.86 + record["interior_web_thickening_bias"] * 0.12),
                    3,
                ),
            )
            for src_id, dst_id, road_class, speed, capacity in (
                (spine.node_id, breakup.node_id, RoadClass.COLLECTOR, 9.0, 5.5),
                (breakup.node_id, halo.node_id, RoadClass.LOCAL, 8.2, 4.9),
                (breakup.node_id, interior.node_id, RoadClass.LOCAL, 8.1, 4.8),
                (interior.node_id, web.node_id, RoadClass.LOCAL, 8.0, 4.8),
                (web.node_id, int(record["lattice_center"].node_id), RoadClass.LOCAL, 8.0, 4.8),
            ):
                _add_bidirectional_link_pair(
                    link_builder,
                    src_id,
                    dst_id,
                    road_class=road_class,
                    lanes=1,
                    speed_mps=speed,
                    capacity=capacity,
                )
            perimeter_rail_breakup_count += 6
            interior_web_thickening_count += 4
            district_blend_link_count += 6
            secondary_fabric_link_count += 4
            corridor_precinct_blend_count += 4
            if barriers:
                barrier = _nearest_precinct_node(barriers, (float(spine.x), float(record["center_y"])))
                bridge = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round(
                        (float(spine.x) + float(barrier.x)) * 0.5 + sign * (4.0 + record["precinct_bridge_saturation_bias"] * 4.0),
                        3,
                    ),
                    y=round((float(spine.y) + float(barrier.y) + float(interior.y)) / 3.0, 3),
                )
                for src_id, dst_id in (
                    (spine.node_id, bridge.node_id),
                    (bridge.node_id, barrier.node_id),
                    (bridge.node_id, interior.node_id),
                ):
                    _add_bidirectional_link_pair(
                        link_builder,
                        src_id,
                        dst_id,
                        road_class=RoadClass.COLLECTOR,
                        lanes=1,
                        speed_mps=8.9,
                        capacity=5.6,
                    )
                precinct_bridge_saturation_count += 6
                continuous_connector_corridor_count += 2
                overlap_mesh_fill_count += 2
        if len(records) >= 2:
            for left, right in zip(records, records[1:]):
                left_interior_nodes = tuple(left.get("interior_nodes", ())) or (left["lattice_center"],)
                right_interior_nodes = tuple(right.get("interior_nodes", ())) or (right["lattice_center"],)
                left_interior = _nearest_precinct_node(left_interior_nodes, (float(right["center_x"]), float(right["center_y"])))
                right_interior = _nearest_precinct_node(right_interior_nodes, (float(left["center_x"]), float(left["center_y"])))
                seam = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=round((float(left_interior.x) + float(right_interior.x)) * 0.5 + sign * 10.0, 3),
                    y=round((float(left_interior.y) + float(right_interior.y)) * 0.5, 3),
                )
                for src_id, dst_id in (
                    (left_interior.node_id, seam.node_id),
                    (seam.node_id, right_interior.node_id),
                ):
                    _add_bidirectional_link_pair(
                        link_builder,
                        src_id,
                        dst_id,
                        road_class=RoadClass.LOCAL,
                        lanes=1,
                        speed_mps=8.1,
                        capacity=4.8,
                    )
                interior_web_thickening_count += 4
                district_blend_link_count += 2

    for river_side, nodes in barrier_side_spine_nodes.items():
        if len(nodes) < 2:
            continue
        ordered = sorted(nodes, key=lambda node: (float(node.y), float(node.x)))
        for current, nxt in zip(ordered, ordered[1:]):
            if current.node_id == nxt.node_id:
                continue
            _add_bidirectional_link_pair(
                link_builder,
                current.node_id,
                nxt.node_id,
                road_class=RoadClass.COLLECTOR,
                lanes=1,
                speed_mps=9.5,
                capacity=6.0,
            )
            barrier_side_continuity_count += 2
            if river_side == "west" and abs(float(current.y) - float(nxt.y)) > 240.0:
                bend_x, bend_y = _curved_midpoint((float(current.x), float(current.y)), (float(nxt.x), float(nxt.y)), bias=0.18)
                bend = _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=bend_x,
                    y=bend_y,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    current.node_id,
                    bend.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.3,
                    capacity=4.9,
                )
                _add_bidirectional_link_pair(
                    link_builder,
                    bend.node_id,
                    nxt.node_id,
                    road_class=RoadClass.LOCAL,
                    lanes=1,
                    speed_mps=8.3,
                    capacity=4.9,
                )
                barrier_side_continuity_count += 2

    if len(north_annulus_nodes) >= 2:
        ordered = sorted(
            {int(node.node_id): node for node in north_annulus_nodes}.values(),
            key=lambda node: (float(node.x), float(node.y)),
        )
        for current, nxt in zip(ordered, ordered[1:]):
            if current.node_id == nxt.node_id:
                continue
            _add_bidirectional_link_pair(
                link_builder,
                current.node_id,
                nxt.node_id,
                road_class=RoadClass.COLLECTOR,
                lanes=1,
                speed_mps=9.1,
                capacity=5.8,
            )
        for current, nxt in zip(ordered, ordered[2:]):
            if current.node_id == nxt.node_id:
                continue
            _add_bidirectional_link_pair(
                link_builder,
                current.node_id,
                nxt.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=7.9,
                capacity=4.8,
            )

    for src_coord, dst_coord in tuple(backbone.get("edge_fracture_spurs", ())):
        src = _nearest_node(nodes_by_coord, tuple(src_coord))
        dst = _nearest_node(nodes_by_coord, tuple(dst_coord))
        if src.node_id == dst.node_id:
            continue
        bend_x, bend_y = _curved_midpoint((float(src.x), float(src.y)), (float(dst.x), float(dst.y)), bias=0.22)
        bend = _get_or_add_node(
            nodes_by_coord=nodes_by_coord,
            node_builder=node_builder,
            kind=NodeKind.INTERSECTION,
            x=bend_x,
            y=bend_y,
        )
        _add_bidirectional_link_pair(
            link_builder,
            src.node_id,
            bend.node_id,
            road_class=RoadClass.ARTERIAL,
            lanes=1,
            speed_mps=13.2,
            capacity=8.8,
        )
        _add_bidirectional_link_pair(
            link_builder,
            bend.node_id,
            dst.node_id,
            road_class=RoadClass.COLLECTOR,
            lanes=1,
            speed_mps=11.8,
            capacity=7.6,
        )

    for src_coord, dst_coord in tuple(backbone.get("fringe_spillover_spurs", ())):
        src = _nearest_node(nodes_by_coord, tuple(src_coord))
        spill = _get_or_add_node(
            nodes_by_coord=nodes_by_coord,
            node_builder=node_builder,
            kind=NodeKind.INTERSECTION,
            x=float(tuple(dst_coord)[0]),
            y=float(tuple(dst_coord)[1]),
        )
        bend_x, bend_y = _curved_midpoint((float(src.x), float(src.y)), (float(spill.x), float(spill.y)), bias=0.24)
        bend = _get_or_add_node(
            nodes_by_coord=nodes_by_coord,
            node_builder=node_builder,
            kind=NodeKind.INTERSECTION,
            x=bend_x,
            y=bend_y,
        )
        fringe_spillover_node_count += 2
        _add_bidirectional_link_pair(
            link_builder,
            src.node_id,
            bend.node_id,
            road_class=RoadClass.LOCAL,
            lanes=1,
            speed_mps=7.8,
            capacity=4.8,
        )
        _add_bidirectional_link_pair(
            link_builder,
            bend.node_id,
            spill.node_id,
            road_class=RoadClass.LOCAL,
            lanes=1,
            speed_mps=7.6,
            capacity=4.7,
        )

    for src_coord, dst_coord in tuple(backbone.get("shell_fragment_pairs", ())):
        src = _nearest_node(nodes_by_coord, tuple(src_coord))
        dst = _nearest_node(nodes_by_coord, tuple(dst_coord))
        if src.node_id == dst.node_id:
            continue
        bend_x, bend_y = _curved_midpoint((float(src.x), float(src.y)), (float(dst.x), float(dst.y)), bias=-0.28)
        bend = _get_or_add_node(
            nodes_by_coord=nodes_by_coord,
            node_builder=node_builder,
            kind=NodeKind.INTERSECTION,
            x=bend_x,
            y=bend_y,
        )
        _add_bidirectional_link_pair(
            link_builder,
            src.node_id,
            bend.node_id,
            road_class=RoadClass.COLLECTOR,
            lanes=1,
            speed_mps=9.0,
            capacity=5.8,
        )
        _add_bidirectional_link_pair(
            link_builder,
            bend.node_id,
            dst.node_id,
            road_class=RoadClass.LOCAL,
            lanes=1,
            speed_mps=8.4,
            capacity=5.2,
        )
        shell_fragment_link_count += 4
        inner_src = _nearest_grid_node(nodes_by_coord, (float(src.x) * 0.82, float(src.y) * 0.82))
        inner_dst = _nearest_grid_node(nodes_by_coord, (float(dst.x) * 0.82, float(dst.y) * 0.82))
        if bend.node_id != inner_src.node_id:
            _add_bidirectional_link_pair(
                link_builder,
                bend.node_id,
                inner_src.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.0,
                capacity=4.8,
            )
            shell_deboxing_link_count += 2
        if bend.node_id != inner_dst.node_id:
            _add_bidirectional_link_pair(
                link_builder,
                bend.node_id,
                inner_dst.node_id,
                road_class=RoadClass.LOCAL,
                lanes=1,
                speed_mps=8.0,
                capacity=4.8,
            )
            shell_deboxing_link_count += 2

    for src_coord, dst_coord in tuple(backbone.get("terrain_drift_pairs", ())):
        src = _nearest_node(nodes_by_coord, tuple(src_coord))
        dst = _nearest_node(nodes_by_coord, tuple(dst_coord))
        if src.node_id == dst.node_id:
            continue
        bend_x, bend_y = _curved_midpoint((float(src.x), float(src.y)), (float(dst.x), float(dst.y)), bias=0.34)
        bend = _get_or_add_node(
            nodes_by_coord=nodes_by_coord,
            node_builder=node_builder,
            kind=NodeKind.INTERSECTION,
            x=bend_x,
            y=bend_y,
        )
        _add_bidirectional_link_pair(
            link_builder,
            src.node_id,
            bend.node_id,
            road_class=RoadClass.COLLECTOR,
            lanes=1,
            speed_mps=9.4,
            capacity=6.0,
        )
        _add_bidirectional_link_pair(
            link_builder,
            bend.node_id,
            dst.node_id,
            road_class=RoadClass.ARTERIAL,
            lanes=1,
            speed_mps=10.6,
            capacity=6.4,
        )
        terrain_drift_link_count += 4

    tapered_corridor_count = 0
    for src_coord, dst_coord in tuple(backbone.get("tapered_corridor_spurs", ())):
        src = _nearest_node(nodes_by_coord, tuple(src_coord))
        dst = _nearest_node(nodes_by_coord, tuple(dst_coord))
        if src.node_id == dst.node_id:
            continue
        bend_x, bend_y = _curved_midpoint((float(src.x), float(src.y)), (float(dst.x), float(dst.y)), bias=-0.18)
        bend = _get_or_add_node(
            nodes_by_coord=nodes_by_coord,
            node_builder=node_builder,
            kind=NodeKind.INTERSECTION,
            x=bend_x,
            y=bend_y,
        )
        _add_bidirectional_link_pair(
            link_builder,
            src.node_id,
            bend.node_id,
            road_class=RoadClass.ARTERIAL,
            lanes=1,
            speed_mps=13.0,
            capacity=8.2,
        )
        _add_bidirectional_link_pair(
            link_builder,
            bend.node_id,
            dst.node_id,
            road_class=RoadClass.LOCAL,
            lanes=1,
            speed_mps=10.2,
            capacity=6.8,
        )
        tapered_corridor_count += 2

    connectivity_repair = repair_weak_connectivity(
        nodes=tuple(node_builder.nodes),
        links=tuple(link_builder.links),
    )
    link_builder.links = list(connectivity_repair.links)
    connectivity_report = validate_road_network_topology(
        nodes=tuple(node_builder.nodes),
        links=tuple(link_builder.links),
        turns=(),
        bridge_crossings=tuple(bridge_crossings),
        require_weak_connectivity=True,
    )
    if not connectivity_report.ok:
        raise ValueError(f"Generated city topology failed connectivity gate: {connectivity_report.summary()}")

    local_nodes = [node for node in node_builder.nodes if node.kind == NodeKind.INTERSECTION]
    frame_link_count = sum(1 for link in link_builder.links if _is_outer_frame_link(link, node_builder.nodes, x_levels, y_levels))
    non_orthogonal_link_count = sum(1 for link in link_builder.links if _is_non_orthogonal_link(link, node_builder.nodes))
    edge_node_ids = _edge_node_ids(node_builder.nodes)
    edge_link_count = sum(
        1 for link in link_builder.links if int(link.src_node_id) in edge_node_ids or int(link.dst_node_id) in edge_node_ids
    )
    fractured_edge_link_count = sum(
        1
        for link in link_builder.links
        if (int(link.src_node_id) in edge_node_ids or int(link.dst_node_id) in edge_node_ids)
        and _is_non_orthogonal_link(link, node_builder.nodes)
    )
    downtown_hub_degree_max = 0
    if downtown_hub_ids:
        downtown_hub_degree_max = max(
            sum(
                1
                for link in link_builder.links
                if int(link.src_node_id) == node_id or int(link.dst_node_id) == node_id
            )
            for node_id in downtown_hub_ids
        )
    metadata = {
        "engine": "generator_v2",
        "active_call_path": "generator_v2.preview_topology",
        "scenario_id": scenario_id,
        "style_id": style_id,
        "seed": int(seed),
        "render_bounds": _render_bounds(backbone),
        "barrier_count": len(tuple(backbone.get("barrier_polylines", ()))),
        "barrier_polylines": tuple(backbone.get("barrier_polylines", ())),
        "district_centers": tuple(district_mesh.get("district_centers", ())),
        "district_block_count": int(district_mesh.get("district_block_count", 0)),
        "district_infill_link_count": int(district_infill_link_count),
        "district_signatures": tuple(district_signatures),
        "district_curvature_signature_count": len({value for value in district_curvature_signatures if value}),
        "district_massing_cv": _float_cv(district_mass_scores)
        + (_float_cv([float(value) for value in tuple(district_mesh.get("district_massing_scales", ()) or ())]) * 0.65)
        + (_float_cv([float(value) for value in tuple(district_mesh.get("precinct_mass_breakup_biases", ()) or ())]) * 0.55),
        "landmark_role_count": len(landmark_roles),
        "hierarchy_taper_score": _hierarchy_taper_score(district_mesh),
        "irregular_void_cell_count": int(irregular_void_cell_count),
        "texture_profile_count": len(texture_profiles),
        "precinct_edge_blend_count": int(precinct_edge_blend_count),
        "fringe_spillover_node_count": int(fringe_spillover_node_count),
        "shell_fragment_link_count": int(shell_fragment_link_count),
        "terrain_drift_link_count": int(terrain_drift_link_count),
        "district_envelope_erosion_count": int(district_envelope_erosion_count),
        "barrier_side_continuity_count": int(barrier_side_continuity_count),
        "parcel_irregularity_score": float(sum(parcel_irregularity_scores) / max(len(parcel_irregularity_scores), 1)),
        "inter_precinct_connector_count": int(inter_precinct_connector_count),
        "mid_annulus_fill_node_count": int(mid_annulus_fill_node_count),
        "district_blend_link_count": int(district_blend_link_count),
        "connector_thickening_count": int(connector_thickening_count),
        "district_overlap_stitch_count": int(district_overlap_stitch_count),
        "secondary_fabric_link_count": int(secondary_fabric_link_count),
        "continuous_connector_corridor_count": int(continuous_connector_corridor_count),
        "precinct_edge_bleed_count": int(precinct_edge_bleed_count),
        "overlap_mesh_fill_count": int(overlap_mesh_fill_count),
        "corridor_braid_link_count": int(corridor_braid_link_count),
        "precinct_interior_quilt_count": int(precinct_interior_quilt_count),
        "downtown_deemphasis_link_count": int(downtown_deemphasis_link_count),
        "corridor_precinct_blend_count": int(corridor_precinct_blend_count),
        "midfield_parcel_stitch_count": int(midfield_parcel_stitch_count),
        "shell_deboxing_link_count": int(shell_deboxing_link_count),
        "shell_fragment_v2_link_count": int(shell_fragment_v2_link_count),
        "interior_street_dissolution_count": int(interior_street_dissolution_count),
        "precinct_seam_erosion_count": int(precinct_seam_erosion_count),
        "outer_shell_collapse_link_count": int(outer_shell_collapse_link_count),
        "precinct_interior_saturation_count": int(precinct_interior_saturation_count),
        "central_mesh_thickening_count": int(central_mesh_thickening_count),
        "perimeter_rail_breakup_count": int(perimeter_rail_breakup_count),
        "precinct_bridge_saturation_count": int(precinct_bridge_saturation_count),
        "interior_web_thickening_count": int(interior_web_thickening_count),
        "precinct_mass_breakup_count": int(precinct_mass_breakup_count),
        "distributed_sub_block_stitch_count": int(distributed_sub_block_stitch_count),
        "interior_field_equalization_count": int(interior_field_equalization_count),
        "precinct_cluster_smoothing_count": int(precinct_cluster_smoothing_count),
        "continuous_local_street_fill_count": int(continuous_local_street_fill_count),
        "core_ring_fabric_consolidation_count": int(core_ring_fabric_consolidation_count),
        "small_map_core_dering_count": int(small_map_core_dering_count),
        "midfield_local_web_saturation_count": int(midfield_local_web_saturation_count),
        "scaffold_rail_attenuation_count": int(scaffold_rail_attenuation_count),
        "smoke_precinct_declustering_count": int(smoke_precinct_declustering_count),
        "large_map_scaffold_dissolution_count": int(large_map_scaffold_dissolution_count),
        "inner_annulus_mesh_equalization_count": int(inner_annulus_mesh_equalization_count),
        "outer_rail_attenuation_v2_count": int(outer_rail_attenuation_v2_count),
        "interior_fabric_densification_count": int(interior_fabric_densification_count),
        "precinct_shell_dissolution_count": int(precinct_shell_dissolution_count),
        "diagonal_shell_breakup_count": int(diagonal_shell_breakup_count),
        "continuous_inner_weave_count": int(continuous_inner_weave_count),
        "precinct_mass_deemphasis_count": int(precinct_mass_deemphasis_count),
        "quadrant_rail_dissolution_count": int(quadrant_rail_dissolution_count),
        "precinct_starburst_attenuation_count": int(precinct_starburst_attenuation_count),
        "annulus_core_threading_count": int(annulus_core_threading_count),
        "quadrant_interior_knitting_count": int(quadrant_interior_knitting_count),
        "precinct_knot_flattening_count": int(precinct_knot_flattening_count),
        "distributed_local_texture_count": int(distributed_local_texture_count),
        "quadrant_local_mesh_stitch_count": int(quadrant_local_mesh_stitch_count),
        "precinct_core_destarburst_count": int(precinct_core_destarburst_count),
        "distributed_secondary_street_fill_count": int(distributed_secondary_street_fill_count),
        "outer_shell_rail_thinning_count": int(outer_shell_rail_thinning_count),
        "precinct_shell_mesh_blending_count": int(precinct_shell_mesh_blending_count),
        "distributed_tertiary_street_fill_count": int(distributed_tertiary_street_fill_count),
        "shell_silhouette_collapse_count": int(shell_silhouette_collapse_count),
        "precinct_boundary_dissolution_count": int(precinct_boundary_dissolution_count),
        "fine_grain_street_texture_count": int(fine_grain_street_texture_count),
        "shell_silhouette_deemphasis_count": int(shell_silhouette_deemphasis_count),
        "precinct_knot_diffusion_count": int(precinct_knot_diffusion_count),
        "distributed_fine_grain_weave_count": int(distributed_fine_grain_weave_count),
        "shell_arc_softening_count": int(shell_arc_softening_count),
        "precinct_knot_diffusion_v2_count": int(precinct_knot_diffusion_v2_count),
        "interior_weave_continuity_count": int(interior_weave_continuity_count),
        "shell_arc_fading_count": int(shell_arc_fading_count),
        "precinct_knot_bleed_count": int(precinct_knot_bleed_count),
        "weave_corridor_threading_count": int(weave_corridor_threading_count),
        "small_map_contrast_score": _small_map_contrast_score(district_mesh),
        "tapered_corridor_count": int(tapered_corridor_count),
        "landmark_void_node_count": int(landmark_void_node_count),
        "left_bank_local_node_count": sum(1 for node in local_nodes if float(node.x) < 0.0),
        "right_bank_local_node_count": sum(1 for node in local_nodes if float(node.x) > 0.0),
        "outer_frame_link_share": float(frame_link_count / max(len(link_builder.links), 1)),
        "edge_link_share": float(edge_link_count / max(len(link_builder.links), 1)),
        "fractured_edge_link_count": int(fractured_edge_link_count),
        "non_orthogonal_link_count": int(non_orthogonal_link_count),
        "scaffold_dominance_score": _scaffold_dominance_score(link_builder.links),
        "backbone_x_spacing_cv": _spacing_cv(x_levels),
        "backbone_y_spacing_cv": _spacing_cv(y_levels),
        "downtown_hub_degree_max": int(downtown_hub_degree_max),
        **connectivity_repair.metadata,
    }
    return PreviewCityTopology(
        nodes=tuple(node_builder.nodes),
        links=tuple(link_builder.links),
        turns=(),
        bridge_crossings=tuple(bridge_crossings),
        metadata=metadata,
    )


def _build_sidecar_morphology_preview_topology(
    *,
    scenario_id: str,
    seed: int,
    style_id: str,
    morphology_field: dict[str, Any],
    include_envelope_links: bool = True,
) -> PreviewCityTopology:
    node_builder = _NodeBuilder()
    link_builder = _LinkBuilder(node_builder=node_builder)
    nodes_by_coord: dict[tuple[float, float], Node] = {}
    barrier_crossings = {
        (round(float(item[0]), 3), round(float(item[1]), 3))
        for item in tuple(morphology_field.get("barrier_crossing_candidates", ()) or ())
    }

    for center in tuple(morphology_field.get("district_centers", ()) or ()):
        _get_or_add_node(
            nodes_by_coord=nodes_by_coord,
            node_builder=node_builder,
            kind=NodeKind.INTERCHANGE if tuple(center) == tuple(morphology_field.get("downtown_anchor", ())) else NodeKind.INTERSECTION,
            x=float(center[0]),
            y=float(center[1]),
        )

    bridge_crossing_records: list[BridgeCrossing] = []
    bridge_group_id = 1
    subcenter_count = int(len(tuple(morphology_field.get("subcenter_anchors", ()) or ())))

    if include_envelope_links:
        for envelope in tuple(morphology_field.get("district_envelopes", ()) or ()):
            envelope_nodes = [
                _get_or_add_node(
                    nodes_by_coord=nodes_by_coord,
                    node_builder=node_builder,
                    kind=NodeKind.INTERSECTION,
                    x=float(point[0]),
                    y=float(point[1]),
                )
                for point in envelope
            ]
            for src, dst in zip(envelope_nodes, envelope_nodes[1:]):
                _add_bidirectional_link_pair(
                    link_builder,
                    src.node_id,
                    dst.node_id,
                    road_class=RoadClass.COLLECTOR,
                    lanes=1,
                    speed_mps=11.0,
                    capacity=8.0,
                )

    for corridor_index, polyline in enumerate(tuple(morphology_field.get("corridor_polylines", ()) or ())):
        corridor_nodes = [
            _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.BRIDGE_ENDPOINT
                if (round(float(point[0]), 3), round(float(point[1]), 3)) in barrier_crossings
                else NodeKind.INTERSECTION,
                x=float(point[0]),
                y=float(point[1]),
            )
            for point in polyline
        ]
        for segment_index, (src, dst) in enumerate(zip(corridor_nodes, corridor_nodes[1:])):
            midpoint = (round((src.x + dst.x) * 0.5, 3), round((src.y + dst.y) * 0.5, 3))
            road_class = _sidecar_corridor_road_class(
                corridor_index=corridor_index,
                segment_index=segment_index,
                midpoint=midpoint,
                barrier_crossings=barrier_crossings,
                subcenter_count=subcenter_count,
            )
            link_ids = _add_bidirectional_link_pair(
                link_builder,
                src.node_id,
                dst.node_id,
                road_class=road_class,
                lanes=_lanes_for_class(road_class),
                speed_mps=_speed_for_class(road_class),
                capacity=_capacity_for_class(road_class),
                bridge_group_id=bridge_group_id if road_class == RoadClass.BRIDGE else None,
            )
            if road_class == RoadClass.BRIDGE:
                bridge_crossing_records.append(
                    BridgeCrossing(
                        bridge_group_id=bridge_group_id,
                        link_ids=link_ids,
                        barrier_id=1,
                        crossing_name=f"sidecar_crossing_{bridge_group_id}",
                    )
                )
                bridge_group_id += 1

    metadata = {
        "engine": "generator_v2_sidecar_morphology",
        "active_call_path": "generator_v2.preview_topology.sidecar_morphology",
        "scenario_id": scenario_id,
        "style_id": style_id,
        "morphology_center_pattern": morphology_field.get("morphology_center_pattern"),
        "morphology_street_pattern": morphology_field.get("morphology_street_pattern"),
        "morphology_evidence_status": morphology_field.get("morphology_evidence_status"),
        "morphology_reference_cities": tuple(
            morphology_field.get("morphology_reference_cities", ()) or ()
        ),
        "seed": int(seed),
        "render_bounds": morphology_field.get("render_bounds"),
        "barrier_count": len(tuple(morphology_field.get("barrier_polylines", ()) or ())),
        "barrier_polylines": tuple(morphology_field.get("barrier_polylines", ()) or ()),
        "district_centers": tuple(morphology_field.get("district_centers", ()) or ()),
        "district_envelopes": tuple(morphology_field.get("district_envelopes", ()) or ()),
        "corridor_influence_polylines": tuple(morphology_field.get("corridor_influence_polylines", ()) or ()),
        "barrier_crossing_candidates": tuple(morphology_field.get("barrier_crossing_candidates", ()) or ()),
        "subcenter_anchors": tuple(morphology_field.get("subcenter_anchors", ()) or ()),
        "subcenter_points": tuple(morphology_field.get("subcenter_anchors", ()) or ()),
        "subcenter_count": subcenter_count,
        "outer_envelope_share": float(morphology_field.get("outer_envelope_share", 0.0)),
        "center_bias": float(morphology_field.get("center_bias", 0.0)),
        "city_mass_width_ratio": float(morphology_field.get("city_mass_width_ratio", 0.0)),
        "city_mass_height_ratio": float(morphology_field.get("city_mass_height_ratio", 0.0)),
        "outer_ring_regular_pair_count": int(morphology_field.get("outer_ring_regular_pair_count", 0)),
        "outer_ring_inward_bend_count": int(morphology_field.get("outer_ring_inward_bend_count", 0)),
        "cross_ring_pair_count": int(morphology_field.get("cross_ring_pair_count", 0)),
        "radial_corridor_count": max(subcenter_count, 4),
        "ring_road_count": max(
            0,
            len(tuple(morphology_field.get("corridor_polylines", ()) or ())) - subcenter_count,
        ),
        "morphology_family_counts": {str(style_id): max(subcenter_count, 4)},
        "morphology_preview": True,
    }
    return PreviewCityTopology(
        nodes=tuple(node_builder.nodes),
        links=tuple(link_builder.links),
        turns=(),
        bridge_crossings=tuple(bridge_crossing_records),
        metadata=metadata,
    )


def _sidecar_corridor_road_class(
    *,
    corridor_index: int,
    segment_index: int,
    midpoint: tuple[float, float],
    barrier_crossings: set[tuple[float, float]],
    subcenter_count: int,
) -> RoadClass:
    if midpoint in barrier_crossings:
        return RoadClass.BRIDGE
    if corridor_index < subcenter_count:
        if segment_index == 0 and corridor_index == max(subcenter_count - 1, 0):
            return RoadClass.RAMP
        if segment_index >= 1:
            return RoadClass.EXPRESSWAY
        return RoadClass.ARTERIAL
    if segment_index == 0:
        return RoadClass.EXPRESSWAY
    return RoadClass.ARTERIAL


def _build_sidecar_district_cell_preview_topology(
    *,
    scenario_id: str,
    seed: int,
    style_id: str,
    morphology_field: dict[str, Any],
    district_cells: dict[str, Any],
    district_mesh: dict[str, Any],
) -> PreviewCityTopology:
    base = _build_sidecar_morphology_preview_topology(
        scenario_id=scenario_id,
        seed=seed,
        style_id=style_id,
        morphology_field=morphology_field,
    )
    metadata = dict(base.metadata)
    metadata.update(
        {
            "engine": "generator_v2_sidecar_district_cells",
            "active_call_path": "generator_v2.preview_topology.sidecar_district_cells",
            "district_cells": tuple(district_cells.get("district_cells", ()) or ()),
            "district_cell_bounds": tuple(district_cells.get("district_cell_bounds", ()) or ()),
            "district_cell_count": int(len(tuple(district_cells.get("district_cells", ()) or ()))),
            "district_regime_count": int(len(tuple(district_cells.get("district_regimes", ()) or ()))),
            "district_regimes": tuple(district_cells.get("district_regimes", ()) or ()),
            "outer_cell_share": float(district_cells.get("outer_cell_share", 0.0)),
            "cell_irregularity_score": float(district_cells.get("cell_irregularity_score", 0.0)),
            "district_mesh_bridge": district_mesh,
        }
    )
    return PreviewCityTopology(
        nodes=base.nodes,
        links=base.links,
        turns=base.turns,
        bridge_crossings=base.bridge_crossings,
        metadata=metadata,
    )


def _build_sidecar_local_fabric_preview_topology(
    *,
    scenario_id: str,
    seed: int,
    style_id: str,
    morphology_field: dict[str, Any],
    district_cells: dict[str, Any],
    district_mesh: dict[str, Any],
    local_fabric: dict[str, Any],
) -> PreviewCityTopology:
    base = _build_sidecar_district_cell_preview_topology(
        scenario_id=scenario_id,
        seed=seed,
        style_id=style_id,
        morphology_field=morphology_field,
        district_cells=district_cells,
        district_mesh=district_mesh,
    )
    envelope_free_base = _build_sidecar_morphology_preview_topology(
        scenario_id=scenario_id,
        seed=seed,
        style_id=style_id,
        morphology_field=morphology_field,
        include_envelope_links=False,
    )
    base_node_lookup = {int(node.node_id): node for node in envelope_free_base.nodes}
    filtered_base_links = [
        link
        for link in envelope_free_base.links
        if not _is_outer_ring_morphology_link(link=link, node_lookup=base_node_lookup)
    ]
    reindexed_base_links = [
        RoadLink(
            link_id=index,
            src_node_id=int(link.src_node_id),
            dst_node_id=int(link.dst_node_id),
            road_class=link.road_class,
            length_m=float(link.length_m),
            free_flow_speed_mps=float(link.free_flow_speed_mps),
            capacity_veh_per_tick=float(link.capacity_veh_per_tick),
            lanes=int(link.lanes),
            bridge_group_id=link.bridge_group_id,
            physical_road_id=link.physical_road_id,
        )
        for index, link in enumerate(filtered_base_links)
    ]
    node_builder = _NodeBuilder(nodes=list(envelope_free_base.nodes))
    link_builder = _LinkBuilder(node_builder=node_builder, links=list(reindexed_base_links))
    nodes_by_coord: dict[tuple[float, float], Node] = {
        (round(float(node.x), 3), round(float(node.y), 3)): node for node in node_builder.nodes
    }

    def add_segment(segment: dict[str, Any], road_class: RoadClass) -> None:
        points = tuple(segment.get("points", ()) or ())
        if len(points) < 2:
            return
        segment_nodes = [
            _get_or_add_node(
                nodes_by_coord=nodes_by_coord,
                node_builder=node_builder,
                kind=NodeKind.INTERSECTION,
                x=float(point[0]),
                y=float(point[1]),
            )
            for point in points
        ]
        for src, dst in zip(segment_nodes, segment_nodes[1:]):
            _add_bidirectional_link_pair(
                link_builder,
                src.node_id,
                dst.node_id,
                road_class=road_class,
                lanes=1,
                speed_mps=9.8 if road_class == RoadClass.LOCAL else 11.4,
                capacity=6.2 if road_class == RoadClass.LOCAL else 7.6,
            )

    for segment in tuple(local_fabric.get("local_segments", ()) or ()):
        add_segment(segment, RoadClass.LOCAL)
    for segment in tuple(local_fabric.get("collector_segments", ()) or ()):
        add_segment(segment, RoadClass.COLLECTOR)

    road_class_counts = Counter(link.road_class.value for link in link_builder.links)
    interchange_like_node_count = sum(
        1
        for node in node_builder.nodes
        if node.kind in {NodeKind.INTERCHANGE, NodeKind.BRIDGE_ENDPOINT, NodeKind.RAMP_MERGE, NodeKind.RAMP_SPLIT}
    )
    hierarchy_module_counts = {
        "expressway_spine": int(road_class_counts.get(RoadClass.EXPRESSWAY.value, 0) // 2),
        "ramp_interface": int(road_class_counts.get(RoadClass.RAMP.value, 0) // 2),
        "bridge_crossing": int(len(base.bridge_crossings)),
        "collector_stitch": int(local_fabric.get("collector_spine_segment_count", 0))
        + int(local_fabric.get("inter_district_connector_count", 0)),
    }
    road_hierarchy_module_signature = tuple(
        label for label, value in hierarchy_module_counts.items() if int(value) > 0
    )
    road_hierarchy_module_alignment_ok = (
        hierarchy_module_counts["expressway_spine"] >= 4
        and hierarchy_module_counts["ramp_interface"] >= 1
        and hierarchy_module_counts["bridge_crossing"] >= 3
        and hierarchy_module_counts["collector_stitch"] >= 6
        and interchange_like_node_count >= 1
    )

    metadata = dict(base.metadata)
    metadata.update(
        {
            "engine": "generator_v2_sidecar_local_fabric",
            "active_call_path": "generator_v2.preview_topology.sidecar_local_fabric",
            "local_segments": tuple(local_fabric.get("local_segments", ()) or ()),
            "collector_segments": tuple(local_fabric.get("collector_segments", ()) or ()),
            "local_segment_count": int(local_fabric.get("local_segment_count", 0)),
            "collector_segment_count": int(local_fabric.get("collector_segment_count", 0)),
            "interior_weave_score": float(local_fabric.get("interior_weave_score", 0.0)),
            "interior_mesh_segment_count": int(local_fabric.get("interior_mesh_segment_count", 0)),
            "perimeter_segment_count": int(local_fabric.get("perimeter_segment_count", 0)),
            "perimeter_segment_share": float(local_fabric.get("perimeter_segment_share", 0.0)),
            "collector_spine_segment_count": int(local_fabric.get("collector_spine_segment_count", 0)),
            "same_district_stitch_segment_count": int(local_fabric.get("same_district_stitch_segment_count", 0)),
            "inter_district_connector_count": int(local_fabric.get("inter_district_connector_count", 0)),
            "core_fan_segment_count": int(local_fabric.get("core_fan_segment_count", 0)),
            "downtown_thread_segment_count": int(local_fabric.get("downtown_thread_segment_count", 0)),
            "district_transfer_hub_count": int(local_fabric.get("district_transfer_hub_count", 0)),
            "direct_downtown_spoke_share": float(local_fabric.get("direct_downtown_spoke_share", 0.0)),
            "intra_cell_subdivision_count": int(local_fabric.get("intra_cell_subdivision_count", 0)),
            "cell_perimeter_road_share": float(local_fabric.get("cell_perimeter_road_share", 0.0)),
            "hierarchy_legibility_score": float(local_fabric.get("hierarchy_legibility_score", 0.0)),
            "continuous_fabric_strategy": local_fabric.get("continuous_fabric_strategy"),
            "continuous_fabric_segment_count": int(
                local_fabric.get("continuous_fabric_segment_count", 0)
            ),
            "hierarchy_module_counts": dict(hierarchy_module_counts),
            "road_hierarchy_module_signature": road_hierarchy_module_signature,
            "road_hierarchy_module_alignment_ok": bool(
                road_hierarchy_module_alignment_ok
            ),
            "interchange_like_node_count": int(interchange_like_node_count),
        }
    )
    topology = PreviewCityTopology(
        nodes=tuple(node_builder.nodes),
        links=tuple(link_builder.links),
        turns=envelope_free_base.turns,
        bridge_crossings=envelope_free_base.bridge_crossings,
        metadata=metadata,
    )
    metadata["active_sidecar_hierarchy_report"] = build_active_sidecar_hierarchy_report(topology=topology)
    return topology


def _is_outer_ring_morphology_link(
    *,
    link: RoadLink,
    node_lookup: dict[int, Node],
) -> bool:
    if link.road_class not in {RoadClass.EXPRESSWAY, RoadClass.ARTERIAL}:
        return False
    src = node_lookup.get(int(link.src_node_id))
    dst = node_lookup.get(int(link.dst_node_id))
    if src is None or dst is None:
        return False
    src_radius = math.hypot(float(src.x), float(src.y))
    dst_radius = math.hypot(float(dst.x), float(dst.y))
    midpoint_radius = math.hypot((float(src.x) + float(dst.x)) * 0.5, (float(src.y) + float(dst.y)) * 0.5)
    return src_radius >= 950.0 and dst_radius >= 950.0 and midpoint_radius >= 900.0


@dataclass(slots=True)
class _NodeBuilder:
    nodes: list[Node] = field(default_factory=list)

    def add(self, *, kind: NodeKind, x: float, y: float) -> Node:
        node = Node(node_id=len(self.nodes), kind=kind, x=x, y=y)
        self.nodes.append(node)
        return node


@dataclass(slots=True)
class _LinkBuilder:
    node_builder: _NodeBuilder
    links: list[RoadLink] = field(default_factory=list)
    next_physical_road_id: int = field(init=False)

    def __post_init__(self) -> None:
        self.next_physical_road_id = max(
            (
                int(link.physical_road_id)
                for link in self.links
                if link.physical_road_id is not None
            ),
            default=-1,
        ) + 1

    def allocate_physical_road_id(self) -> int:
        physical_road_id = self.next_physical_road_id
        self.next_physical_road_id += 1
        return physical_road_id

    def add(
        self,
        *,
        src_node_id: int,
        dst_node_id: int,
        road_class: RoadClass,
        lanes: int,
        speed_mps: float,
        capacity: float,
        bridge_group_id: int | None = None,
        physical_road_id: int | None = None,
    ) -> int:
        src = self.node_builder.nodes[int(src_node_id)]
        dst = self.node_builder.nodes[int(dst_node_id)]
        length = math.hypot(float(dst.x) - float(src.x), float(dst.y) - float(src.y))
        link = RoadLink(
            link_id=len(self.links),
            src_node_id=int(src_node_id),
            dst_node_id=int(dst_node_id),
            road_class=road_class,
            length_m=max(length, 1.0),
            free_flow_speed_mps=float(speed_mps),
            capacity_veh_per_tick=float(capacity),
            lanes=int(lanes),
            bridge_group_id=bridge_group_id,
            physical_road_id=physical_road_id,
        )
        self.links.append(link)
        return link.link_id


def _add_bidirectional_link_pair(
    link_builder: _LinkBuilder,
    src_node_id: int,
    dst_node_id: int,
    *,
    road_class: RoadClass,
    lanes: int,
    speed_mps: float,
    capacity: float,
    bridge_group_id: int | None = None,
) -> tuple[int, int]:
    physical_road_id = link_builder.allocate_physical_road_id()
    forward = link_builder.add(
        src_node_id=src_node_id,
        dst_node_id=dst_node_id,
        road_class=road_class,
        lanes=lanes,
        speed_mps=speed_mps,
        capacity=capacity,
        bridge_group_id=bridge_group_id,
        physical_road_id=physical_road_id,
    )
    reverse = link_builder.add(
        src_node_id=dst_node_id,
        dst_node_id=src_node_id,
        road_class=road_class,
        lanes=lanes,
        speed_mps=speed_mps,
        capacity=capacity,
        bridge_group_id=bridge_group_id,
        physical_road_id=physical_road_id,
    )
    return (forward, reverse)


def _horizontal_road_class(*, y: float, y_levels: tuple[float, ...]) -> RoadClass:
    outer = max(abs(value) for value in y_levels)
    inner = _nth_from_end(y_levels, 3)
    if math.isclose(abs(y), outer):
        return RoadClass.EXPRESSWAY
    if math.isclose(abs(y), inner):
        return RoadClass.ARTERIAL
    if math.isclose(y, 0.0):
        return RoadClass.COLLECTOR
    return RoadClass.LOCAL


def _vertical_road_class(*, x: float, x_levels: tuple[float, ...]) -> RoadClass:
    outer = max(abs(value) for value in x_levels)
    inner = _nth_from_end(x_levels, 3)
    collector = _nth_from_end(x_levels, 4)
    if math.isclose(abs(x), outer):
        return RoadClass.EXPRESSWAY
    if math.isclose(abs(x), inner):
        return RoadClass.ARTERIAL
    if math.isclose(abs(x), collector):
        return RoadClass.COLLECTOR
    return RoadClass.LOCAL


def _lanes_for_class(road_class: RoadClass) -> int:
    return {
        RoadClass.LOCAL: 1,
        RoadClass.COLLECTOR: 1,
        RoadClass.ARTERIAL: 2,
        RoadClass.EXPRESSWAY: 3,
        RoadClass.RAMP: 1,
        RoadClass.BRIDGE: 2,
    }[road_class]


def _speed_for_class(road_class: RoadClass) -> float:
    return {
        RoadClass.LOCAL: 9.0,
        RoadClass.COLLECTOR: 11.0,
        RoadClass.ARTERIAL: 15.0,
        RoadClass.EXPRESSWAY: 21.0,
        RoadClass.RAMP: 14.0,
        RoadClass.BRIDGE: 17.0,
    }[road_class]


def _capacity_for_class(road_class: RoadClass) -> float:
    return {
        RoadClass.LOCAL: 6.0,
        RoadClass.COLLECTOR: 8.0,
        RoadClass.ARTERIAL: 14.0,
        RoadClass.EXPRESSWAY: 22.0,
        RoadClass.RAMP: 12.0,
        RoadClass.BRIDGE: 18.0,
    }[road_class]


def _render_bounds(backbone: dict[str, Any]) -> tuple[float, float, float, float]:
    outer = tuple(float(v) for v in backbone.get("outer_ring_bounds", (-1.0, 1.0, -1.0, 1.0)))
    min_x, max_x, min_y, max_y = outer
    width = max_x - min_x
    height = max_y - min_y
    pad_x = width * 0.085
    pad_y = height * 0.085
    return (
        round(min_x - pad_x, 3),
        round(max_x + pad_x, 3),
        round(min_y - pad_y, 3),
        round(max_y + pad_y, 3),
    )


def _nearest_node(nodes_by_coord: dict[tuple[float, float], Node], target: tuple[float, float]) -> Node:
    return min(
        nodes_by_coord.values(),
        key=lambda node: math.hypot(float(node.x) - float(target[0]), float(node.y) - float(target[1])),
    )


def _nearest_grid_node(nodes_by_coord: dict[tuple[float, float], Node], target: tuple[float, float]) -> Node:
    return _nearest_node(nodes_by_coord, target)


def _nearest_precinct_node(nodes: tuple[Node, ...], target: tuple[float, float]) -> Node:
    return min(
        nodes,
        key=lambda node: math.hypot(float(node.x) - float(target[0]), float(node.y) - float(target[1])),
    )


def _get_or_add_node(
    *,
    nodes_by_coord: dict[tuple[float, float], Node],
    node_builder: _NodeBuilder,
    kind: NodeKind,
    x: float,
    y: float,
) -> Node:
    key = (round(float(x), 3), round(float(y), 3))
    existing = nodes_by_coord.get(key)
    if existing is not None:
        return existing
    node = node_builder.add(kind=kind, x=key[0], y=key[1])
    nodes_by_coord[key] = node
    return node


def _nth_from_end(values: tuple[float, ...], n: int) -> float:
    unique = sorted({abs(value) for value in values if abs(value) > 0.0})
    if not unique:
        return 0.0
    index = max(0, len(unique) - int(n))
    return unique[index]


def _spacing_cv(levels: tuple[float, ...]) -> float:
    if len(levels) < 3:
        return 0.0
    diffs = [abs(float(b) - float(a)) for a, b in zip(levels, levels[1:])]
    mean = sum(diffs) / len(diffs)
    if mean <= 1e-6:
        return 0.0
    variance = sum((diff - mean) ** 2 for diff in diffs) / len(diffs)
    return float((variance ** 0.5) / mean)


def _float_cv(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    if mean <= 1e-6:
        return 0.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return float((variance ** 0.5) / mean)


def _small_map_contrast_score(district_mesh: dict[str, Any]) -> float:
    scales = [float(value) for value in tuple(district_mesh.get("district_massing_scales", ()) or ())]
    if not scales:
        return 0.0
    contrast = max(scales) - min(scales)
    tiers = [value for value in tuple(district_mesh.get("small_map_contrast_tiers", ()) or ()) if value]
    tier_bonus = len(set(tiers)) / max(len(tiers), 1)
    return float(contrast * 0.6 + tier_bonus * 0.4)


def _hierarchy_taper_score(district_mesh: dict[str, Any]) -> float:
    priorities = [float(d.get("taper_priority", 0.0)) for d in tuple(district_mesh.get("districts", ()) or ())]
    if not priorities:
        return 0.0
    return float(max(priorities) - min(priorities))


def _parcel_irregularity_score(
    *,
    xs: tuple[float, ...],
    ys: tuple[float, ...],
    void_cells: set[tuple[int, int]],
    tier: str,
    envelope_erosion_bias: float,
) -> float:
    tier_bonus = {
        "high": 0.17,
        "medium": 0.14,
        "moderate": 0.12,
        "low": 0.08,
    }.get(tier, 0.10)
    grid_area = max((len(xs) - 1) * (len(ys) - 1), 1)
    void_share = len(void_cells) / grid_area
    spacing_score = (_spacing_cv(xs) + _spacing_cv(ys)) * 0.45
    return float(min(0.36, tier_bonus + spacing_score + void_share * 0.55 + envelope_erosion_bias * 0.08))


def _envelope_erosion_offsets(*, bias: float, tier: str, river_side: str) -> tuple[tuple[float, float], ...]:
    direction = -1.0 if river_side == "west" else 1.0
    scale = 1.0 + max(0.0, float(bias) - 0.5) * 1.4
    templates = {
        "high": ((86.0, -112.0), (124.0, 22.0), (96.0, 134.0)),
        "medium": ((78.0, -96.0), (112.0, 14.0), (88.0, 118.0)),
        "moderate": ((72.0, -84.0), (98.0, 12.0), (82.0, 102.0)),
        "low": ((64.0, -72.0), (88.0, 10.0), (74.0, 88.0)),
    }
    base = templates.get(tier, templates["medium"])
    return tuple((round(direction * dx * scale, 3), round(dy * scale, 3)) for dx, dy in base)


def _taper_profile(*, taper_priority: float, major: bool) -> tuple[RoadClass, float, float]:
    if taper_priority >= 0.9:
        return (RoadClass.ARTERIAL if major else RoadClass.COLLECTOR, 11.2 if major else 10.0, 6.8 if major else 6.0)
    if taper_priority >= 0.72:
        return (RoadClass.COLLECTOR, 9.8 if major else 9.2, 6.0 if major else 5.6)
    return (RoadClass.LOCAL, 8.9 if major else 8.3, 5.2 if major else 4.8)


def _landmark_offsets(role: str) -> tuple[tuple[float, float], ...]:
    mapping = {
        "civic_core": ((18.0, 22.0), (-24.0, 14.0), (0.0, 34.0)),
        "market_spine": ((32.0, -12.0), (58.0, 8.0), (82.0, 18.0)),
        "waterfront_anchor": ((-18.0, 32.0), (12.0, 56.0), (34.0, 82.0)),
        "garden_crescent": ((-36.0, 18.0), (-54.0, 42.0), (-18.0, 74.0)),
        "transit_square": ((24.0, 24.0), (44.0, 44.0), (68.0, 22.0)),
        "hill_anchor": ((18.0, 52.0), (46.0, 76.0), (82.0, 94.0)),
        "university_mall": ((36.0, -18.0), (72.0, -6.0), (96.0, 26.0)),
    }
    return mapping.get(role, ((24.0, 18.0), (42.0, 36.0), (18.0, 54.0)))


def _landmark_offsets_large_map(role: str) -> tuple[tuple[float, float], ...]:
    mapping = {
        "market_spine": ((118.0, 34.0), (152.0, 62.0)),
        "waterfront_anchor": ((-42.0, 118.0), (24.0, 154.0)),
        "garden_crescent": ((-86.0, 72.0), (-124.0, 118.0)),
        "transit_square": ((86.0, 88.0), (122.0, 118.0)),
        "hill_anchor": ((64.0, 138.0), (108.0, 176.0)),
        "university_mall": ((118.0, -24.0), (152.0, 22.0)),
    }
    return mapping.get(role, ((86.0, 64.0), (122.0, 96.0)))


def _texture_halo_offsets(profile: str) -> tuple[tuple[float, float], ...]:
    mapping = {
        "civic_fabric": ((-116.0, -74.0), (-22.0, -122.0), (118.0, -58.0), (132.0, 36.0), (104.0, 92.0), (-94.0, 108.0)),
        "market_grain": ((-104.0, -42.0), (-128.0, 34.0), (-92.0, 76.0), (18.0, 124.0), (84.0, 102.0), (118.0, 24.0)),
        "river_walk": ((-132.0, 18.0), (-126.0, 92.0), (-116.0, 114.0), (18.0, 136.0), (42.0, 126.0), (92.0, 54.0)),
        "garden_patch": ((-126.0, -18.0), (-92.0, -96.0), (-58.0, 114.0), (24.0, 126.0), (62.0, 88.0), (118.0, -22.0)),
        "transit_mix": ((-84.0, -108.0), (-18.0, -132.0), (114.0, -62.0), (128.0, 28.0), (98.0, 98.0), (42.0, 118.0)),
        "campus_walk": ((-112.0, -88.0), (-44.0, -126.0), (94.0, -36.0), (122.0, 72.0), (64.0, 134.0), (-28.0, 128.0)),
        "terrace_patch": ((-98.0, -96.0), (-22.0, -126.0), (82.0, -92.0), (126.0, 32.0), (88.0, 118.0), (18.0, 116.0)),
    }
    return mapping.get(profile, ((-96.0, -72.0), (-28.0, -118.0), (104.0, -42.0), (126.0, 34.0), (92.0, 88.0), (-48.0, 112.0)))


def _texture_filament_offsets(profile: str) -> tuple[tuple[float, float], ...]:
    mapping = {
        "civic_fabric": ((-156.0, -122.0), (164.0, 118.0), (-132.0, 168.0)),
        "market_grain": ((-164.0, -84.0), (158.0, 84.0), (42.0, 172.0)),
        "river_walk": ((-182.0, 28.0), (118.0, 162.0), (-96.0, 176.0)),
        "garden_patch": ((-172.0, -62.0), (146.0, -74.0), (82.0, 172.0)),
        "transit_mix": ((-132.0, -168.0), (172.0, -74.0), (148.0, 122.0)),
        "campus_walk": ((-162.0, -132.0), (158.0, 26.0), (94.0, 182.0)),
        "terrace_patch": ((-148.0, -164.0), (174.0, 44.0), (116.0, 162.0)),
    }
    return mapping.get(profile, ((-156.0, -132.0), (166.0, 52.0), (92.0, 176.0)))


def _curved_midpoint(src: tuple[float, float], dst: tuple[float, float], *, bias: float) -> tuple[float, float]:
    mid_x = (float(src[0]) + float(dst[0])) * 0.5
    mid_y = (float(src[1]) + float(dst[1])) * 0.5
    dx = float(dst[0]) - float(src[0])
    dy = float(dst[1]) - float(src[1])
    length = math.hypot(dx, dy)
    if length <= 1e-6:
        return (round(mid_x, 3), round(mid_y, 3))
    offset = min(length * 0.24, max(26.0, length * abs(float(bias))))
    normal_x = -dy / length
    normal_y = dx / length
    return (
        round(mid_x + normal_x * offset * (1.0 if bias >= 0.0 else -1.0), 3),
        round(mid_y + normal_y * offset * (1.0 if bias >= 0.0 else -1.0), 3),
    )


def _edge_node_ids(nodes: list[Node]) -> set[int]:
    if not nodes:
        return set()
    xs = [float(node.x) for node in nodes]
    ys = [float(node.y) for node in nodes]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    margin_x = max((max_x - min_x) * 0.10, 50.0)
    margin_y = max((max_y - min_y) * 0.10, 50.0)
    return {
        int(node.node_id)
        for node in nodes
        if float(node.x) <= (min_x + margin_x)
        or float(node.x) >= (max_x - margin_x)
        or float(node.y) <= (min_y + margin_y)
        or float(node.y) >= (max_y - margin_y)
    }


def _void_cells(*, rows: int, cols: int, template: str) -> set[tuple[int, int]]:
    if rows <= 0 or cols <= 0:
        return set()
    mid_r = max(0, rows // 2)
    mid_c = max(0, cols // 2)
    mapping = {
        "offset_plaza": {
            (mid_r, max(0, mid_c - 1)),
            (max(0, mid_r - 1), mid_c),
            (mid_r, mid_c),
        },
        "crescent_gap": {
            (mid_r, max(0, mid_c - 1)),
            (mid_r, min(cols - 1, mid_c + 1)),
        },
        "offset_court": {
            (max(0, mid_r - 1), max(0, mid_c - 1)),
            (mid_r, mid_c),
        },
        "river_plaza": {
            (mid_r, 0),
            (max(0, mid_r - 1), 0),
            (min(rows - 1, mid_r + 1), 0),
        },
        "terrace_void": {
            (rows - 1, mid_c),
            (max(0, rows - 2), min(cols - 1, mid_c + 1)),
        },
        "ridge_green": {
            (0, mid_c),
            (0, max(0, mid_c - 1)),
        },
    }
    return {cell for cell in mapping.get(template, set()) if 0 <= cell[0] < rows and 0 <= cell[1] < cols}


def _lattice_edge_nodes(lattice: list[list[Node]]) -> tuple[Node, ...]:
    top = lattice[0]
    bottom = lattice[-1]
    left = [row[0] for row in lattice]
    right = [row[-1] for row in lattice]
    ordered = (
        top[len(top) // 2],
        right[len(right) // 2],
        bottom[len(bottom) // 2],
        left[len(left) // 2],
    )
    return tuple(ordered)


def _interior_lattice_nodes(lattice: list[list[Node]]) -> tuple[Node, ...]:
    if not lattice or not lattice[0]:
        return ()
    row_mid = len(lattice) // 2
    col_mid = len(lattice[0]) // 2
    candidates = (
        lattice[max(1, row_mid) - 1][max(1, col_mid) - 1],
        lattice[max(1, row_mid) - 1][min(len(lattice[0]) - 2, col_mid)],
        lattice[min(len(lattice) - 2, row_mid)][max(1, col_mid) - 1],
        lattice[min(len(lattice) - 2, row_mid)][min(len(lattice[0]) - 2, col_mid)],
    )
    return tuple({int(node.node_id): node for node in candidates}.values())


def _skip_horizontal_edge(void_cells: set[tuple[int, int]], row_idx: int, col_idx: int) -> bool:
    return (row_idx, col_idx) in void_cells or (row_idx - 1, col_idx) in void_cells


def _skip_vertical_edge(void_cells: set[tuple[int, int]], row_idx: int, col_idx: int) -> bool:
    return (row_idx, col_idx) in void_cells or (row_idx, col_idx - 1) in void_cells


def _scaffold_dominance_score(links: list[RoadLink]) -> float:
    if not links:
        return 0.0
    scaffold = sum(1 for link in links if link.road_class in {RoadClass.EXPRESSWAY, RoadClass.ARTERIAL, RoadClass.RAMP})
    return float(scaffold / len(links))


def _is_outer_frame_link(
    link: RoadLink,
    nodes: list[Node],
    x_levels: tuple[float, ...],
    y_levels: tuple[float, ...],
) -> bool:
    src = nodes[int(link.src_node_id)]
    dst = nodes[int(link.dst_node_id)]
    outer_x = max(abs(value) for value in x_levels)
    outer_y = max(abs(value) for value in y_levels)
    same_outer_y = math.isclose(abs(float(src.y)), outer_y) and math.isclose(abs(float(dst.y)), outer_y)
    same_outer_x = math.isclose(abs(float(src.x)), outer_x) and math.isclose(abs(float(dst.x)), outer_x)
    axis_aligned = math.isclose(float(src.x), float(dst.x)) or math.isclose(float(src.y), float(dst.y))
    return axis_aligned and (same_outer_x or same_outer_y)


def _is_non_orthogonal_link(link: RoadLink, nodes: list[Node]) -> bool:
    src = nodes[int(link.src_node_id)]
    dst = nodes[int(link.dst_node_id)]
    return not (
        math.isclose(float(src.x), float(dst.x), abs_tol=1e-3)
        or math.isclose(float(src.y), float(dst.y), abs_tol=1e-3)
    )
