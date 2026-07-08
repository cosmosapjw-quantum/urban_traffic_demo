from __future__ import annotations


def build_district_mesh_from_cells(*, district_cells: dict[str, object]) -> dict[str, object]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for cell in tuple(district_cells.get("district_cells", ()) or ()):
        grouped.setdefault(str(cell["district_id"]), []).append(dict(cell))

    districts: list[dict[str, object]] = []
    district_centers: list[tuple[float, float]] = []
    for district_id, cells in grouped.items():
        xs = [float(cell["center"][0]) for cell in cells]
        ys = [float(cell["center"][1]) for cell in cells]
        center = (sum(xs) / max(len(xs), 1), sum(ys) / max(len(ys), 1))
        district_centers.append((round(center[0], 3), round(center[1], 3)))
        districts.append(
            {
                "district_id": district_id,
                "kind": "sidecar_cell_partition",
                "center": (round(center[0], 3), round(center[1], 3)),
                "cell_count": len(cells),
                "regimes": tuple(sorted({str(cell["regime"]) for cell in cells})),
            }
        )

    return {
        "districts": tuple(districts),
        "district_centers": tuple(district_centers),
        "district_cell_count": len(tuple(district_cells.get("district_cells", ()) or ())),
        "district_regime_count": len(tuple(district_cells.get("district_regimes", ()) or ())),
    }


def build_district_mesh(
    *,
    seed: int,
    width: int,
    height: int,
    backbone: dict[str, object] | None = None,
) -> dict[str, object]:
    if backbone is None:
        center_x = width // 2
        center_y = height // 2
        grid_xs = _district_grid_axis(center_x, 220.0)
        grid_ys = _district_grid_axis(center_y, 220.0)
        return {
            "seed": int(seed),
            "downtown_core": {"x": center_x, "y": center_y, "density_ratio": 2.0},
            "uptown_subcenters": [
                {"x": max(1, center_x - width // 4), "y": max(1, center_y - height // 4), "density_ratio": 1.4}
            ],
            "districts": (
                {
                    "district_id": "downtown",
                    "kind": "downtown",
                    "center": (center_x, center_y),
                    "radius": 220.0,
                    "block_grid_xs": grid_xs,
                    "block_grid_ys": grid_ys,
                    "block_count": _block_count(grid_xs, grid_ys),
                    "envelope_erosion_bias": 0.58,
                    "barrier_continuity_bias": 0.72,
                    "parcel_irregularity_tier": "moderate",
                    "connector_bias": 0.74,
                    "mid_annulus_fill_bias": 0.78,
                    "district_blend_bias": 0.70,
                    "connector_thickness_bias": 0.78,
                    "overlap_stitch_bias": 0.72,
                    "secondary_fabric_bias": 0.76,
                    "corridor_continuity_bias": 0.78,
                    "precinct_edge_bleed_bias": 0.74,
                    "overlap_mesh_fill_bias": 0.76,
                    "corridor_braiding_bias": 0.76,
                    "interior_quilt_bias": 0.78,
                    "downtown_deemphasis_bias": 0.74,
                    "corridor_precinct_blend_bias": 0.78,
                    "midfield_stitch_bias": 0.76,
                    "shell_deboxing_bias": 0.74,
                    "shell_fragment_v2_bias": 0.78,
                    "interior_dissolve_bias": 0.80,
                    "precinct_seam_erosion_bias": 0.76,
                    "outer_shell_collapse_bias": 0.82,
                    "interior_saturation_bias": 0.84,
                    "central_mesh_thickening_bias": 0.80,
                    "perimeter_rail_breakup_bias": 0.82,
                    "precinct_bridge_saturation_bias": 0.80,
                    "interior_web_thickening_bias": 0.82,
                    "precinct_mass_breakup_bias": 0.84,
                    "sub_block_stitch_bias": 0.82,
                    "interior_field_equalization_bias": 0.84,
                    "precinct_cluster_smoothing_bias": 0.84,
                    "continuous_local_fill_bias": 0.82,
                    "core_ring_fabric_consolidation_bias": 0.84,
                    "small_map_core_dering_bias": 0.82,
                    "midfield_local_web_saturation_bias": 0.84,
                    "scaffold_rail_attenuation_bias": 0.80,
                    "smoke_precinct_declustering_bias": 0.82,
                    "large_map_scaffold_dissolution_bias": 0.76,
                    "inner_annulus_mesh_equalization_bias": 0.80,
                    "outer_rail_attenuation_v2_bias": 0.82,
                    "interior_fabric_densification_bias": 0.84,
                    "precinct_shell_dissolution_bias": 0.80,
                    "diagonal_shell_breakup_bias": 0.84,
                    "continuous_inner_weave_bias": 0.86,
                    "precinct_mass_deemphasis_bias": 0.82,
                    "quadrant_rail_dissolution_bias": 0.84,
                    "precinct_starburst_attenuation_bias": 0.86,
                    "annulus_core_threading_bias": 0.88,
                    "quadrant_interior_knitting_bias": 0.86,
                    "precinct_knot_flattening_bias": 0.84,
                    "distributed_local_texture_bias": 0.88,
                    "quadrant_local_mesh_stitch_bias": 0.86,
                    "precinct_core_destarburst_bias": 0.84,
                    "distributed_secondary_street_fill_bias": 0.88,
                    "outer_shell_rail_thinning_bias": 0.86,
                    "precinct_shell_mesh_blend_bias": 0.84,
                    "distributed_tertiary_street_fill_bias": 0.88,
                    "shell_silhouette_collapse_bias": 0.90,
                    "precinct_boundary_dissolution_bias": 0.88,
                    "fine_grain_street_texture_bias": 0.92,
                    "shell_silhouette_deemphasis_bias": 0.94,
                    "precinct_knot_diffusion_bias": 0.92,
                    "distributed_fine_grain_weave_bias": 0.96,
                    "shell_arc_softening_bias": 0.96,
                    "precinct_knot_diffusion_v2_bias": 0.94,
                    "interior_weave_continuity_bias": 0.98,
                    "shell_arc_fading_bias": 0.98,
                    "precinct_knot_bleed_bias": 0.96,
                    "weave_corridor_threading_bias": 1.00,
                },
            ),
        }

    downtown_anchor = tuple(backbone.get("downtown_anchor", (0.0, 0.0)))
    subcenter_points = tuple(backbone.get("subcenter_points", ()))
    districts: list[dict[str, object]] = [
        {
            "district_id": "downtown_core",
            "kind": "downtown",
            "center": downtown_anchor,
            "radius": 248.0,
            "density_ratio": 2.0,
            "massing_scale": 1.16,
            "density_retention": "dense_core",
            "small_map_contrast_tier": "baseline",
            "landmark_role": "civic_core",
            "void_template": "offset_plaza",
            "taper_priority": 1.0,
            "texture_profile": "civic_fabric",
            "edge_blend_bias": 0.92,
            "envelope_erosion_bias": 0.64,
            "barrier_continuity_bias": 0.78,
            "parcel_irregularity_tier": "moderate",
            "connector_bias": 0.82,
            "mid_annulus_fill_bias": 0.80,
            "district_blend_bias": 0.76,
            "connector_thickness_bias": 0.84,
            "overlap_stitch_bias": 0.76,
            "secondary_fabric_bias": 0.80,
            "corridor_continuity_bias": 0.82,
            "precinct_edge_bleed_bias": 0.78,
            "overlap_mesh_fill_bias": 0.80,
            "corridor_braiding_bias": 0.80,
            "interior_quilt_bias": 0.78,
            "downtown_deemphasis_bias": 0.84,
            "corridor_precinct_blend_bias": 0.78,
            "midfield_stitch_bias": 0.80,
            "shell_deboxing_bias": 0.70,
            "shell_fragment_v2_bias": 0.76,
            "interior_dissolve_bias": 0.84,
            "precinct_seam_erosion_bias": 0.78,
            "outer_shell_collapse_bias": 0.84,
            "interior_saturation_bias": 0.88,
            "central_mesh_thickening_bias": 0.84,
            "perimeter_rail_breakup_bias": 0.86,
            "precinct_bridge_saturation_bias": 0.84,
            "interior_web_thickening_bias": 0.86,
            "precinct_mass_breakup_bias": 0.88,
            "sub_block_stitch_bias": 0.86,
            "interior_field_equalization_bias": 0.88,
            "precinct_cluster_smoothing_bias": 0.88,
            "continuous_local_fill_bias": 0.86,
            "core_ring_fabric_consolidation_bias": 0.88,
            "small_map_core_dering_bias": 0.82,
            "midfield_local_web_saturation_bias": 0.80,
            "scaffold_rail_attenuation_bias": 0.78,
            "smoke_precinct_declustering_bias": 0.74,
            "large_map_scaffold_dissolution_bias": 0.84,
            "inner_annulus_mesh_equalization_bias": 0.84,
            "outer_rail_attenuation_v2_bias": 0.82,
            "interior_fabric_densification_bias": 0.88,
            "precinct_shell_dissolution_bias": 0.84,
            "diagonal_shell_breakup_bias": 0.82,
            "continuous_inner_weave_bias": 0.90,
            "precinct_mass_deemphasis_bias": 0.88,
            "quadrant_rail_dissolution_bias": 0.84,
            "precinct_starburst_attenuation_bias": 0.90,
            "annulus_core_threading_bias": 0.92,
            "quadrant_interior_knitting_bias": 0.88,
            "precinct_knot_flattening_bias": 0.86,
            "distributed_local_texture_bias": 0.90,
            "quadrant_local_mesh_stitch_bias": 0.88,
            "precinct_core_destarburst_bias": 0.86,
            "distributed_secondary_street_fill_bias": 0.90,
            "outer_shell_rail_thinning_bias": 0.88,
            "precinct_shell_mesh_blend_bias": 0.86,
            "distributed_tertiary_street_fill_bias": 0.90,
            "shell_silhouette_collapse_bias": 0.92,
            "precinct_boundary_dissolution_bias": 0.90,
            "fine_grain_street_texture_bias": 0.94,
            "shell_silhouette_deemphasis_bias": 0.96,
            "precinct_knot_diffusion_bias": 0.94,
            "distributed_fine_grain_weave_bias": 0.98,
            "shell_arc_softening_bias": 0.98,
            "precinct_knot_diffusion_v2_bias": 0.96,
            "interior_weave_continuity_bias": 1.00,
            "shell_arc_fading_bias": 1.00,
            "precinct_knot_bleed_bias": 0.98,
            "weave_corridor_threading_bias": 1.02,
            "block_grid_xs": _district_grid_axis(float(downtown_anchor[0]), 248.0, skew=0.18, axis="x"),
            "block_grid_ys": _district_grid_axis(float(downtown_anchor[1]), 248.0, skew=-0.08, axis="y"),
            "hub_offsets": ((-86.0, -34.0), (58.0, -18.0), (32.0, 96.0)),
            "connector_angles": (-2.58, -1.18, -0.22, 0.86, 1.94),
            "curvature_bias": 0.22,
            "curvature_signature": "downtown_tri_arc",
        }
    ]
    districts[0]["block_count"] = _block_count(
        tuple(districts[0]["block_grid_xs"]),
        tuple(districts[0]["block_grid_ys"]),
    )
    uptown_subcenters: list[dict[str, object]] = []

    for idx, point in enumerate(subcenter_points):
        x_val = float(point[0])
        y_val = float(point[1])
        radius = 220.0 if idx < 4 else 200.0
        river_side = -1.0 if x_val < 0.0 else 1.0
        x_skew = river_side * (0.08 + 0.03 * (idx % 3))
        y_skew = ((idx % 4) - 1.5) * 0.05
        x_count = 6 if river_side < 0 else 5
        y_count = 5 if (idx % 2) == 0 else 6
        grid_xs = _district_grid_axis(x_val, radius, skew=x_skew, axis="x", count=x_count)
        grid_ys = _district_grid_axis(y_val, radius, skew=y_skew, axis="y", count=y_count)
        district = {
            "district_id": f"district_{idx + 1}",
            "kind": "subcenter" if abs(y_val) > 1.0 else "mixed_use",
            "center": (x_val, y_val),
            "radius": radius,
            "density_ratio": 1.55 if idx < 4 else 1.35,
            "massing_scale": _district_massing_scale(idx=idx, river_side=river_side),
            "density_retention": _district_density_retention(idx=idx, river_side=river_side),
            "small_map_contrast_tier": _small_map_contrast_tier(idx=idx),
            "landmark_role": _district_landmark_role(idx=idx, river_side=river_side),
            "void_template": _district_void_template(idx=idx, river_side=river_side),
            "taper_priority": _district_taper_priority(idx=idx, river_side=river_side),
            "texture_profile": _district_texture_profile(idx=idx, river_side=river_side),
            "edge_blend_bias": _district_edge_blend_bias(idx=idx, river_side=river_side),
            "envelope_erosion_bias": _district_envelope_erosion_bias(idx=idx, river_side=river_side),
            "barrier_continuity_bias": _district_barrier_continuity_bias(idx=idx, river_side=river_side),
            "parcel_irregularity_tier": _district_parcel_irregularity_tier(idx=idx, river_side=river_side),
            "connector_bias": _district_connector_bias(idx=idx, river_side=river_side),
            "mid_annulus_fill_bias": _district_mid_annulus_fill_bias(idx=idx, river_side=river_side),
            "district_blend_bias": _district_blend_bias(idx=idx, river_side=river_side),
            "connector_thickness_bias": _district_connector_thickness_bias(idx=idx, river_side=river_side),
            "overlap_stitch_bias": _district_overlap_stitch_bias(idx=idx, river_side=river_side),
            "secondary_fabric_bias": _district_secondary_fabric_bias(idx=idx, river_side=river_side),
            "corridor_continuity_bias": _district_corridor_continuity_bias(idx=idx, river_side=river_side),
            "precinct_edge_bleed_bias": _district_precinct_edge_bleed_bias(idx=idx, river_side=river_side),
            "overlap_mesh_fill_bias": _district_overlap_mesh_fill_bias(idx=idx, river_side=river_side),
            "corridor_braiding_bias": _district_corridor_braiding_bias(idx=idx, river_side=river_side),
            "interior_quilt_bias": _district_interior_quilt_bias(idx=idx, river_side=river_side),
            "downtown_deemphasis_bias": _district_downtown_deemphasis_bias(idx=idx, river_side=river_side),
            "corridor_precinct_blend_bias": _district_corridor_precinct_blend_bias(idx=idx, river_side=river_side),
            "midfield_stitch_bias": _district_midfield_stitch_bias(idx=idx, river_side=river_side),
            "shell_deboxing_bias": _district_shell_deboxing_bias(idx=idx, river_side=river_side),
            "shell_fragment_v2_bias": _district_shell_fragment_v2_bias(idx=idx, river_side=river_side),
            "interior_dissolve_bias": _district_interior_dissolve_bias(idx=idx, river_side=river_side),
            "precinct_seam_erosion_bias": _district_precinct_seam_erosion_bias(idx=idx, river_side=river_side),
            "outer_shell_collapse_bias": _district_outer_shell_collapse_bias(idx=idx, river_side=river_side),
            "interior_saturation_bias": _district_interior_saturation_bias(idx=idx, river_side=river_side),
            "central_mesh_thickening_bias": _district_central_mesh_thickening_bias(idx=idx, river_side=river_side),
            "perimeter_rail_breakup_bias": _district_perimeter_rail_breakup_bias(idx=idx, river_side=river_side),
            "precinct_bridge_saturation_bias": _district_precinct_bridge_saturation_bias(idx=idx, river_side=river_side),
            "interior_web_thickening_bias": _district_interior_web_thickening_bias(idx=idx, river_side=river_side),
            "precinct_mass_breakup_bias": _district_precinct_mass_breakup_bias(idx=idx, river_side=river_side),
            "sub_block_stitch_bias": _district_sub_block_stitch_bias(idx=idx, river_side=river_side),
            "interior_field_equalization_bias": _district_interior_field_equalization_bias(idx=idx, river_side=river_side),
            "precinct_cluster_smoothing_bias": _district_precinct_cluster_smoothing_bias(idx=idx, river_side=river_side),
            "continuous_local_fill_bias": _district_continuous_local_fill_bias(idx=idx, river_side=river_side),
            "core_ring_fabric_consolidation_bias": _district_core_ring_fabric_consolidation_bias(idx=idx, river_side=river_side),
            "small_map_core_dering_bias": _district_small_map_core_dering_bias(idx=idx, river_side=river_side),
            "midfield_local_web_saturation_bias": _district_midfield_local_web_saturation_bias(idx=idx, river_side=river_side),
            "scaffold_rail_attenuation_bias": _district_scaffold_rail_attenuation_bias(idx=idx, river_side=river_side),
            "smoke_precinct_declustering_bias": _district_smoke_precinct_declustering_bias(idx=idx, river_side=river_side),
            "large_map_scaffold_dissolution_bias": _district_large_map_scaffold_dissolution_bias(idx=idx, river_side=river_side),
            "inner_annulus_mesh_equalization_bias": _district_inner_annulus_mesh_equalization_bias(idx=idx, river_side=river_side),
            "outer_rail_attenuation_v2_bias": _district_outer_rail_attenuation_v2_bias(idx=idx, river_side=river_side),
            "interior_fabric_densification_bias": _district_interior_fabric_densification_bias(idx=idx, river_side=river_side),
            "precinct_shell_dissolution_bias": _district_precinct_shell_dissolution_bias(idx=idx, river_side=river_side),
            "diagonal_shell_breakup_bias": _district_diagonal_shell_breakup_bias(idx=idx, river_side=river_side),
            "continuous_inner_weave_bias": _district_continuous_inner_weave_bias(idx=idx, river_side=river_side),
            "precinct_mass_deemphasis_bias": _district_precinct_mass_deemphasis_bias(idx=idx, river_side=river_side),
            "quadrant_rail_dissolution_bias": _district_quadrant_rail_dissolution_bias(idx=idx, river_side=river_side),
            "precinct_starburst_attenuation_bias": _district_precinct_starburst_attenuation_bias(idx=idx, river_side=river_side),
            "annulus_core_threading_bias": _district_annulus_core_threading_bias(idx=idx, river_side=river_side),
            "quadrant_interior_knitting_bias": _district_quadrant_interior_knitting_bias(idx=idx, river_side=river_side),
            "precinct_knot_flattening_bias": _district_precinct_knot_flattening_bias(idx=idx, river_side=river_side),
            "distributed_local_texture_bias": _district_distributed_local_texture_bias(idx=idx, river_side=river_side),
            "quadrant_local_mesh_stitch_bias": _district_quadrant_local_mesh_stitch_bias(idx=idx, river_side=river_side),
            "precinct_core_destarburst_bias": _district_precinct_core_destarburst_bias(idx=idx, river_side=river_side),
            "distributed_secondary_street_fill_bias": _district_distributed_secondary_street_fill_bias(idx=idx, river_side=river_side),
            "outer_shell_rail_thinning_bias": _district_outer_shell_rail_thinning_bias(idx=idx, river_side=river_side),
            "precinct_shell_mesh_blend_bias": _district_precinct_shell_mesh_blend_bias(idx=idx, river_side=river_side),
            "distributed_tertiary_street_fill_bias": _district_distributed_tertiary_street_fill_bias(idx=idx, river_side=river_side),
            "shell_silhouette_collapse_bias": _district_shell_silhouette_collapse_bias(idx=idx, river_side=river_side),
            "precinct_boundary_dissolution_bias": _district_precinct_boundary_dissolution_bias(idx=idx, river_side=river_side),
            "fine_grain_street_texture_bias": _district_fine_grain_street_texture_bias(idx=idx, river_side=river_side),
            "shell_silhouette_deemphasis_bias": _district_shell_silhouette_deemphasis_bias(idx=idx, river_side=river_side),
            "precinct_knot_diffusion_bias": _district_precinct_knot_diffusion_bias(idx=idx, river_side=river_side),
            "distributed_fine_grain_weave_bias": _district_distributed_fine_grain_weave_bias(idx=idx, river_side=river_side),
            "shell_arc_softening_bias": _district_shell_arc_softening_bias(idx=idx, river_side=river_side),
            "precinct_knot_diffusion_v2_bias": _district_precinct_knot_diffusion_v2_bias(idx=idx, river_side=river_side),
            "interior_weave_continuity_bias": _district_interior_weave_continuity_bias(idx=idx, river_side=river_side),
            "shell_arc_fading_bias": _district_shell_arc_fading_bias(idx=idx, river_side=river_side),
            "precinct_knot_bleed_bias": _district_precinct_knot_bleed_bias(idx=idx, river_side=river_side),
            "weave_corridor_threading_bias": _district_weave_corridor_threading_bias(idx=idx, river_side=river_side),
            "block_grid_xs": grid_xs,
            "block_grid_ys": grid_ys,
            "block_count": _block_count(grid_xs, grid_ys),
            "signature": _district_signature(grid_xs, grid_ys),
            "river_side": "west" if river_side < 0 else "east",
            "hub_offsets": _district_hub_offsets(idx=idx, river_side=river_side),
            "connector_angles": _district_connector_angles(idx=idx, river_side=river_side),
            "curvature_bias": _district_curvature_bias(idx=idx, river_side=river_side),
            "curvature_signature": _district_curvature_signature(idx=idx, river_side=river_side),
        }
        districts.append(district)
        if y_val > 0.0:
            uptown_subcenters.append({"x": x_val, "y": y_val, "density_ratio": district["density_ratio"]})

    if str(backbone.get("style_id", "")) == "polycentric_tod":
        contrast_overrides = (
            {"massing_scale": 0.60, "density_retention": "void_band", "small_map_contrast_tier": "void"},
            {"massing_scale": 0.54, "density_retention": "void_band", "small_map_contrast_tier": "void"},
            {"massing_scale": 0.98, "density_retention": "hub_pockets", "small_map_contrast_tier": "transition"},
            {"massing_scale": 1.52, "density_retention": "landmark_cluster", "small_map_contrast_tier": "landmark"},
            {"massing_scale": 0.58, "density_retention": "void_band", "small_map_contrast_tier": "void"},
            {"massing_scale": 1.34, "density_retention": "landmark_cluster", "small_map_contrast_tier": "landmark"},
        )
        for district, override in zip(districts[1:], contrast_overrides):
            district.update(override)

    return {
        "seed": int(seed),
        "downtown_core": {
            "x": float(downtown_anchor[0]),
            "y": float(downtown_anchor[1]),
            "density_ratio": 2.2,
        },
        "uptown_subcenters": uptown_subcenters,
        "districts": tuple(districts),
        "district_centers": tuple(district["center"] for district in districts),
        "district_block_count": sum(int(district["block_count"]) for district in districts),
        "district_signatures": tuple(str(district.get("signature", "")) for district in districts),
        "district_curvature_signatures": tuple(str(district.get("curvature_signature", "")) for district in districts),
        "district_massing_scales": tuple(float(district.get("massing_scale", 1.0)) for district in districts),
        "small_map_contrast_tiers": tuple(str(district.get("small_map_contrast_tier", "")) for district in districts),
        "landmark_roles": tuple(str(district.get("landmark_role", "")) for district in districts),
        "void_templates": tuple(str(district.get("void_template", "")) for district in districts),
        "texture_profiles": tuple(str(district.get("texture_profile", "")) for district in districts),
        "envelope_erosion_biases": tuple(float(district.get("envelope_erosion_bias", 0.0)) for district in districts),
        "barrier_continuity_biases": tuple(float(district.get("barrier_continuity_bias", 0.0)) for district in districts),
        "parcel_irregularity_tiers": tuple(str(district.get("parcel_irregularity_tier", "")) for district in districts),
        "connector_biases": tuple(float(district.get("connector_bias", 0.0)) for district in districts),
        "mid_annulus_fill_biases": tuple(float(district.get("mid_annulus_fill_bias", 0.0)) for district in districts),
        "district_blend_biases": tuple(float(district.get("district_blend_bias", 0.0)) for district in districts),
        "connector_thickness_biases": tuple(float(district.get("connector_thickness_bias", 0.0)) for district in districts),
        "overlap_stitch_biases": tuple(float(district.get("overlap_stitch_bias", 0.0)) for district in districts),
        "secondary_fabric_biases": tuple(float(district.get("secondary_fabric_bias", 0.0)) for district in districts),
        "corridor_continuity_biases": tuple(float(district.get("corridor_continuity_bias", 0.0)) for district in districts),
        "precinct_edge_bleed_biases": tuple(float(district.get("precinct_edge_bleed_bias", 0.0)) for district in districts),
        "overlap_mesh_fill_biases": tuple(float(district.get("overlap_mesh_fill_bias", 0.0)) for district in districts),
        "corridor_braiding_biases": tuple(float(district.get("corridor_braiding_bias", 0.0)) for district in districts),
        "interior_quilt_biases": tuple(float(district.get("interior_quilt_bias", 0.0)) for district in districts),
        "downtown_deemphasis_biases": tuple(float(district.get("downtown_deemphasis_bias", 0.0)) for district in districts),
        "corridor_precinct_blend_biases": tuple(float(district.get("corridor_precinct_blend_bias", 0.0)) for district in districts),
        "midfield_stitch_biases": tuple(float(district.get("midfield_stitch_bias", 0.0)) for district in districts),
        "shell_deboxing_biases": tuple(float(district.get("shell_deboxing_bias", 0.0)) for district in districts),
        "shell_fragment_v2_biases": tuple(float(district.get("shell_fragment_v2_bias", 0.0)) for district in districts),
        "interior_dissolve_biases": tuple(float(district.get("interior_dissolve_bias", 0.0)) for district in districts),
        "precinct_seam_erosion_biases": tuple(float(district.get("precinct_seam_erosion_bias", 0.0)) for district in districts),
        "outer_shell_collapse_biases": tuple(float(district.get("outer_shell_collapse_bias", 0.0)) for district in districts),
        "interior_saturation_biases": tuple(float(district.get("interior_saturation_bias", 0.0)) for district in districts),
        "central_mesh_thickening_biases": tuple(float(district.get("central_mesh_thickening_bias", 0.0)) for district in districts),
        "perimeter_rail_breakup_biases": tuple(float(district.get("perimeter_rail_breakup_bias", 0.0)) for district in districts),
        "precinct_bridge_saturation_biases": tuple(float(district.get("precinct_bridge_saturation_bias", 0.0)) for district in districts),
        "interior_web_thickening_biases": tuple(float(district.get("interior_web_thickening_bias", 0.0)) for district in districts),
        "precinct_mass_breakup_biases": tuple(float(district.get("precinct_mass_breakup_bias", 0.0)) for district in districts),
        "sub_block_stitch_biases": tuple(float(district.get("sub_block_stitch_bias", 0.0)) for district in districts),
        "interior_field_equalization_biases": tuple(float(district.get("interior_field_equalization_bias", 0.0)) for district in districts),
        "precinct_cluster_smoothing_biases": tuple(float(district.get("precinct_cluster_smoothing_bias", 0.0)) for district in districts),
        "continuous_local_fill_biases": tuple(float(district.get("continuous_local_fill_bias", 0.0)) for district in districts),
        "core_ring_fabric_consolidation_biases": tuple(float(district.get("core_ring_fabric_consolidation_bias", 0.0)) for district in districts),
        "small_map_core_dering_biases": tuple(float(district.get("small_map_core_dering_bias", 0.0)) for district in districts),
        "midfield_local_web_saturation_biases": tuple(float(district.get("midfield_local_web_saturation_bias", 0.0)) for district in districts),
        "scaffold_rail_attenuation_biases": tuple(float(district.get("scaffold_rail_attenuation_bias", 0.0)) for district in districts),
        "smoke_precinct_declustering_biases": tuple(float(district.get("smoke_precinct_declustering_bias", 0.0)) for district in districts),
        "large_map_scaffold_dissolution_biases": tuple(float(district.get("large_map_scaffold_dissolution_bias", 0.0)) for district in districts),
        "inner_annulus_mesh_equalization_biases": tuple(float(district.get("inner_annulus_mesh_equalization_bias", 0.0)) for district in districts),
        "outer_rail_attenuation_v2_biases": tuple(float(district.get("outer_rail_attenuation_v2_bias", 0.0)) for district in districts),
        "interior_fabric_densification_biases": tuple(float(district.get("interior_fabric_densification_bias", 0.0)) for district in districts),
        "precinct_shell_dissolution_biases": tuple(float(district.get("precinct_shell_dissolution_bias", 0.0)) for district in districts),
        "diagonal_shell_breakup_biases": tuple(float(district.get("diagonal_shell_breakup_bias", 0.0)) for district in districts),
        "continuous_inner_weave_biases": tuple(float(district.get("continuous_inner_weave_bias", 0.0)) for district in districts),
        "precinct_mass_deemphasis_biases": tuple(float(district.get("precinct_mass_deemphasis_bias", 0.0)) for district in districts),
        "quadrant_rail_dissolution_biases": tuple(float(district.get("quadrant_rail_dissolution_bias", 0.0)) for district in districts),
        "precinct_starburst_attenuation_biases": tuple(float(district.get("precinct_starburst_attenuation_bias", 0.0)) for district in districts),
        "annulus_core_threading_biases": tuple(float(district.get("annulus_core_threading_bias", 0.0)) for district in districts),
        "quadrant_interior_knitting_biases": tuple(float(district.get("quadrant_interior_knitting_bias", 0.0)) for district in districts),
        "precinct_knot_flattening_biases": tuple(float(district.get("precinct_knot_flattening_bias", 0.0)) for district in districts),
        "distributed_local_texture_biases": tuple(float(district.get("distributed_local_texture_bias", 0.0)) for district in districts),
        "quadrant_local_mesh_stitch_biases": tuple(float(district.get("quadrant_local_mesh_stitch_bias", 0.0)) for district in districts),
        "precinct_core_destarburst_biases": tuple(float(district.get("precinct_core_destarburst_bias", 0.0)) for district in districts),
        "distributed_secondary_street_fill_biases": tuple(float(district.get("distributed_secondary_street_fill_bias", 0.0)) for district in districts),
        "outer_shell_rail_thinning_biases": tuple(float(district.get("outer_shell_rail_thinning_bias", 0.0)) for district in districts),
        "precinct_shell_mesh_blend_biases": tuple(float(district.get("precinct_shell_mesh_blend_bias", 0.0)) for district in districts),
        "distributed_tertiary_street_fill_biases": tuple(float(district.get("distributed_tertiary_street_fill_bias", 0.0)) for district in districts),
        "shell_silhouette_collapse_biases": tuple(float(district.get("shell_silhouette_collapse_bias", 0.0)) for district in districts),
        "precinct_boundary_dissolution_biases": tuple(float(district.get("precinct_boundary_dissolution_bias", 0.0)) for district in districts),
        "fine_grain_street_texture_biases": tuple(float(district.get("fine_grain_street_texture_bias", 0.0)) for district in districts),
        "shell_silhouette_deemphasis_biases": tuple(float(district.get("shell_silhouette_deemphasis_bias", 0.0)) for district in districts),
        "precinct_knot_diffusion_biases": tuple(float(district.get("precinct_knot_diffusion_bias", 0.0)) for district in districts),
        "distributed_fine_grain_weave_biases": tuple(float(district.get("distributed_fine_grain_weave_bias", 0.0)) for district in districts),
        "shell_arc_softening_biases": tuple(float(district.get("shell_arc_softening_bias", 0.0)) for district in districts),
        "precinct_knot_diffusion_v2_biases": tuple(float(district.get("precinct_knot_diffusion_v2_bias", 0.0)) for district in districts),
        "interior_weave_continuity_biases": tuple(float(district.get("interior_weave_continuity_bias", 0.0)) for district in districts),
        "shell_arc_fading_biases": tuple(float(district.get("shell_arc_fading_bias", 0.0)) for district in districts),
        "precinct_knot_bleed_biases": tuple(float(district.get("precinct_knot_bleed_bias", 0.0)) for district in districts),
        "weave_corridor_threading_biases": tuple(float(district.get("weave_corridor_threading_bias", 0.0)) for district in districts),
    }


def _district_grid_axis(
    center: float,
    radius: float,
    *,
    skew: float = 0.0,
    axis: str = "x",
    count: int = 5,
) -> tuple[float, ...]:
    step = float(radius) * 0.36
    if count <= 0:
        return ()
    if count == 5:
        offsets = (-2.0, -1.1, 0.0, 1.0, 2.2) if axis == "x" else (-2.1, -0.9, 0.0, 1.1, 2.0)
    elif count == 6:
        offsets = (-2.4, -1.5, -0.45, 0.55, 1.45, 2.35) if axis == "x" else (-2.5, -1.3, -0.25, 0.75, 1.7, 2.3)
    else:
        span = float(count - 1) / 2.0
        offsets = tuple(-span + idx for idx in range(count))
    warped: list[float] = []
    for idx, offset in enumerate(offsets):
        asym = (idx - ((len(offsets) - 1) / 2.0)) * float(skew) * step
        warped.append(round(float(center) + offset * step + asym, 3))
    return tuple(warped)


def _block_count(xs: tuple[float, ...], ys: tuple[float, ...]) -> int:
    return max(0, len(xs) - 1) * max(0, len(ys) - 1)


def _district_signature(xs: tuple[float, ...], ys: tuple[float, ...]) -> str:
    x_steps = tuple(round(xs[idx + 1] - xs[idx], 1) for idx in range(len(xs) - 1))
    y_steps = tuple(round(ys[idx + 1] - ys[idx], 1) for idx in range(len(ys) - 1))
    return f"x:{x_steps}|y:{y_steps}"


def _district_hub_offsets(*, idx: int, river_side: float) -> tuple[tuple[float, float], ...]:
    if river_side < 0:
        options = (
            ((-48.0, -22.0), (34.0, 18.0)),
            ((-54.0, 12.0), (18.0, 54.0)),
            ((-36.0, -46.0), (42.0, 8.0)),
        )
    else:
        options = (
            ((44.0, -18.0), (-28.0, 16.0)),
            ((38.0, 26.0), (-16.0, 48.0)),
            ((52.0, -34.0), (-22.0, -12.0)),
        )
    return options[idx % len(options)]


def _district_connector_angles(*, idx: int, river_side: float) -> tuple[float, ...]:
    if river_side < 0:
        variants = (
            (-2.72, -1.54, -0.52, 0.66, 1.82),
            (-2.38, -1.08, 0.14, 1.08, 2.22),
            (-2.86, -1.92, -0.34, 0.72, 1.56),
        )
    else:
        variants = (
            (-2.18, -0.88, 0.08, 1.18, 2.42),
            (-2.54, -1.22, -0.14, 0.94, 2.08),
            (-2.02, -0.62, 0.48, 1.42, 2.62),
        )
    return variants[idx % len(variants)]


def _district_curvature_bias(*, idx: int, river_side: float) -> float:
    base = (0.16, 0.21, 0.27)[idx % 3]
    if river_side < 0:
        return base + 0.03
    return base - 0.01


def _district_curvature_signature(*, idx: int, river_side: float) -> str:
    side = "west" if river_side < 0 else "east"
    pattern = ("fan", "arc", "bend")[idx % 3]
    return f"{side}:{pattern}:{idx % 2}"


def _district_massing_scale(*, idx: int, river_side: float) -> float:
    west = (1.18, 0.92, 1.08)
    east = (0.88, 1.14, 0.98)
    return (west if river_side < 0 else east)[idx % 3]


def _district_density_retention(*, idx: int, river_side: float) -> str:
    if river_side < 0:
        variants = ("dense_wedge", "split_band", "hub_pockets")
    else:
        variants = ("hub_pockets", "dense_wedge", "split_band")
    return variants[idx % 3]


def _small_map_contrast_tier(*, idx: int) -> str:
    return ("dense", "transition", "void")[idx % 3]


def _district_landmark_role(*, idx: int, river_side: float) -> str:
    if river_side < 0:
        roles = ("market_spine", "waterfront_anchor", "garden_crescent")
    else:
        roles = ("transit_square", "hill_anchor", "university_mall")
    return roles[idx % 3]


def _district_void_template(*, idx: int, river_side: float) -> str:
    if river_side < 0:
        templates = ("crescent_gap", "offset_court", "river_plaza")
    else:
        templates = ("terrace_void", "offset_court", "ridge_green")
    return templates[idx % 3]


def _district_taper_priority(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.86, 0.72, 0.58)
    else:
        values = (0.90, 0.68, 0.62)
    return values[idx % 3]


def _district_texture_profile(*, idx: int, river_side: float) -> str:
    if river_side < 0:
        variants = ("market_grain", "river_walk", "garden_patch")
    else:
        variants = ("transit_mix", "campus_walk", "terrace_patch")
    return variants[idx % 3]


def _district_edge_blend_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.92, 0.74, 0.61)
    else:
        values = (0.88, 0.71, 0.64)
    return values[idx % 3]


def _district_envelope_erosion_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.84, 0.66, 0.58)
    else:
        values = (0.78, 0.62, 0.54)
    return values[idx % 3]


def _district_barrier_continuity_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.88, 0.76, 0.70)
    else:
        values = (0.86, 0.72, 0.68)
    return values[idx % 3]


def _district_parcel_irregularity_tier(*, idx: int, river_side: float) -> str:
    if river_side < 0:
        tiers = ("high", "medium", "high")
    else:
        tiers = ("medium", "high", "medium")
    return tiers[idx % 3]


def _district_connector_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.86, 0.74, 0.68)
    else:
        values = (0.82, 0.72, 0.66)
    return values[idx % 3]


def _district_mid_annulus_fill_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.84, 0.76, 0.70)
    else:
        values = (0.80, 0.74, 0.68)
    return values[idx % 3]


def _district_blend_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.80, 0.70, 0.64)
    else:
        values = (0.78, 0.68, 0.62)
    return values[idx % 3]


def _district_connector_thickness_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.88, 0.76, 0.72)
    else:
        values = (0.84, 0.74, 0.70)
    return values[idx % 3]


def _district_overlap_stitch_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.78, 0.70, 0.64)
    else:
        values = (0.76, 0.68, 0.62)
    return values[idx % 3]


def _district_secondary_fabric_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.84, 0.74, 0.68)
    else:
        values = (0.80, 0.72, 0.66)
    return values[idx % 3]


def _district_corridor_continuity_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.86, 0.78, 0.72)
    else:
        values = (0.82, 0.74, 0.70)
    return values[idx % 3]


def _district_precinct_edge_bleed_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.82, 0.74, 0.68)
    else:
        values = (0.80, 0.72, 0.66)
    return values[idx % 3]


def _district_overlap_mesh_fill_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.80, 0.72, 0.68)
    else:
        values = (0.78, 0.70, 0.66)
    return values[idx % 3]


def _district_corridor_braiding_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.82, 0.74, 0.70)
    else:
        values = (0.80, 0.72, 0.68)
    return values[idx % 3]


def _district_interior_quilt_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.84, 0.76, 0.70)
    else:
        values = (0.82, 0.74, 0.68)
    return values[idx % 3]


def _district_downtown_deemphasis_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.80, 0.72, 0.68)
    else:
        values = (0.82, 0.74, 0.70)
    return values[idx % 3]


def _district_corridor_precinct_blend_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.84, 0.76, 0.70)
    else:
        values = (0.82, 0.74, 0.68)
    return values[idx % 3]


def _district_midfield_stitch_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.82, 0.74, 0.70)
    else:
        values = (0.80, 0.72, 0.68)
    return values[idx % 3]


def _district_shell_deboxing_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.80, 0.72, 0.66)
    else:
        values = (0.78, 0.70, 0.64)
    return values[idx % 3]


def _district_shell_fragment_v2_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.84, 0.76, 0.70)
    else:
        values = (0.80, 0.74, 0.68)
    return values[idx % 3]


def _district_interior_dissolve_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.86, 0.78, 0.72)
    else:
        values = (0.84, 0.76, 0.70)
    return values[idx % 3]


def _district_precinct_seam_erosion_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.82, 0.74, 0.68)
    else:
        values = (0.80, 0.72, 0.66)
    return values[idx % 3]


def _district_outer_shell_collapse_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.88, 0.80, 0.74)
    else:
        values = (0.84, 0.78, 0.72)
    return values[idx % 3]


def _district_interior_saturation_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.90, 0.82, 0.76)
    else:
        values = (0.88, 0.80, 0.74)
    return values[idx % 3]


def _district_central_mesh_thickening_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.84, 0.76, 0.70)
    else:
        values = (0.82, 0.74, 0.68)
    return values[idx % 3]


def _district_perimeter_rail_breakup_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.88, 0.82, 0.76)
    else:
        values = (0.86, 0.80, 0.74)
    return values[idx % 3]


def _district_precinct_bridge_saturation_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.86, 0.80, 0.74)
    else:
        values = (0.84, 0.78, 0.72)
    return values[idx % 3]


def _district_interior_web_thickening_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.88, 0.82, 0.76)
    else:
        values = (0.86, 0.80, 0.74)
    return values[idx % 3]


def _district_precinct_mass_breakup_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.90, 0.84, 0.78)
    else:
        values = (0.88, 0.82, 0.76)
    return values[idx % 3]


def _district_sub_block_stitch_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.88, 0.82, 0.76)
    else:
        values = (0.86, 0.80, 0.74)
    return values[idx % 3]


def _district_interior_field_equalization_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.90, 0.84, 0.78)
    else:
        values = (0.88, 0.82, 0.76)
    return values[idx % 3]


def _district_precinct_cluster_smoothing_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.90, 0.84, 0.78)
    else:
        values = (0.88, 0.82, 0.76)
    return values[idx % 3]


def _district_continuous_local_fill_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.88, 0.82, 0.76)
    else:
        values = (0.86, 0.80, 0.74)
    return values[idx % 3]


def _district_core_ring_fabric_consolidation_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.90, 0.84, 0.78)
    else:
        values = (0.88, 0.82, 0.76)
    return values[idx % 3]


def _district_small_map_core_dering_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.86, 0.80, 0.74)
    else:
        values = (0.84, 0.78, 0.72)
    return values[idx % 3]


def _district_midfield_local_web_saturation_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.90, 0.84, 0.78)
    else:
        values = (0.88, 0.82, 0.76)
    return values[idx % 3]


def _district_scaffold_rail_attenuation_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.84, 0.78, 0.72)
    else:
        values = (0.82, 0.76, 0.70)
    return values[idx % 3]


def _district_smoke_precinct_declustering_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.88, 0.82, 0.76)
    else:
        values = (0.86, 0.80, 0.74)
    return values[idx % 3]


def _district_large_map_scaffold_dissolution_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.82, 0.76, 0.70)
    else:
        values = (0.84, 0.78, 0.72)
    return values[idx % 3]


def _district_inner_annulus_mesh_equalization_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.88, 0.82, 0.76)
    else:
        values = (0.86, 0.80, 0.74)
    return values[idx % 3]


def _district_outer_rail_attenuation_v2_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.90, 0.84, 0.78)
    else:
        values = (0.88, 0.82, 0.76)
    return values[idx % 3]


def _district_interior_fabric_densification_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.92, 0.86, 0.80)
    else:
        values = (0.90, 0.84, 0.78)
    return values[idx % 3]


def _district_precinct_shell_dissolution_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.88, 0.82, 0.76)
    else:
        values = (0.90, 0.84, 0.78)
    return values[idx % 3]


def _district_diagonal_shell_breakup_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.92, 0.86, 0.80)
    else:
        values = (0.90, 0.84, 0.78)
    return values[idx % 3]


def _district_continuous_inner_weave_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.94, 0.88, 0.82)
    else:
        values = (0.92, 0.86, 0.80)
    return values[idx % 3]


def _district_precinct_mass_deemphasis_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.90, 0.84, 0.78)
    else:
        values = (0.88, 0.82, 0.76)
    return values[idx % 3]


def _district_quadrant_rail_dissolution_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.92, 0.86, 0.80)
    else:
        values = (0.90, 0.84, 0.78)
    return values[idx % 3]


def _district_precinct_starburst_attenuation_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.94, 0.88, 0.82)
    else:
        values = (0.92, 0.86, 0.80)
    return values[idx % 3]


def _district_annulus_core_threading_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.96, 0.90, 0.84)
    else:
        values = (0.94, 0.88, 0.82)
    return values[idx % 3]


def _district_quadrant_interior_knitting_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.94, 0.88, 0.82)
    else:
        values = (0.92, 0.86, 0.80)
    return values[idx % 3]


def _district_precinct_knot_flattening_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.92, 0.86, 0.80)
    else:
        values = (0.90, 0.84, 0.78)
    return values[idx % 3]


def _district_distributed_local_texture_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.96, 0.90, 0.84)
    else:
        values = (0.94, 0.88, 0.82)
    return values[idx % 3]


def _district_quadrant_local_mesh_stitch_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.94, 0.88, 0.82)
    else:
        values = (0.92, 0.86, 0.80)
    return values[idx % 3]


def _district_precinct_core_destarburst_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.92, 0.86, 0.80)
    else:
        values = (0.90, 0.84, 0.78)
    return values[idx % 3]


def _district_distributed_secondary_street_fill_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.96, 0.90, 0.84)
    else:
        values = (0.94, 0.88, 0.82)
    return values[idx % 3]


def _district_outer_shell_rail_thinning_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.94, 0.88, 0.82)
    else:
        values = (0.92, 0.86, 0.80)
    return values[idx % 3]


def _district_precinct_shell_mesh_blend_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.92, 0.86, 0.80)
    else:
        values = (0.90, 0.84, 0.78)
    return values[idx % 3]


def _district_distributed_tertiary_street_fill_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.96, 0.90, 0.84)
    else:
        values = (0.94, 0.88, 0.82)
    return values[idx % 3]


def _district_shell_silhouette_collapse_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.98, 0.92, 0.86)
    else:
        values = (0.96, 0.90, 0.84)
    return values[idx % 3]


def _district_precinct_boundary_dissolution_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (0.96, 0.90, 0.84)
    else:
        values = (0.94, 0.88, 0.82)
    return values[idx % 3]


def _district_fine_grain_street_texture_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (1.00, 0.94, 0.88)
    else:
        values = (0.98, 0.92, 0.86)
    return values[idx % 3]


def _district_shell_silhouette_deemphasis_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (1.02, 0.96, 0.90)
    else:
        values = (1.00, 0.94, 0.88)
    return values[idx % 3]


def _district_precinct_knot_diffusion_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (1.00, 0.94, 0.88)
    else:
        values = (0.98, 0.92, 0.86)
    return values[idx % 3]


def _district_distributed_fine_grain_weave_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (1.04, 0.98, 0.92)
    else:
        values = (1.02, 0.96, 0.90)
    return values[idx % 3]


def _district_shell_arc_softening_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (1.04, 0.98, 0.92)
    else:
        values = (1.02, 0.96, 0.90)
    return values[idx % 3]


def _district_precinct_knot_diffusion_v2_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (1.02, 0.96, 0.90)
    else:
        values = (1.00, 0.94, 0.88)
    return values[idx % 3]


def _district_interior_weave_continuity_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (1.06, 1.00, 0.94)
    else:
        values = (1.04, 0.98, 0.92)
    return values[idx % 3]


def _district_shell_arc_fading_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (1.06, 1.00, 0.94)
    else:
        values = (1.04, 0.98, 0.92)
    return values[idx % 3]


def _district_precinct_knot_bleed_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (1.04, 0.98, 0.92)
    else:
        values = (1.02, 0.96, 0.90)
    return values[idx % 3]


def _district_weave_corridor_threading_bias(*, idx: int, river_side: float) -> float:
    if river_side < 0:
        values = (1.08, 1.02, 0.96)
    else:
        values = (1.06, 1.00, 0.94)
    return values[idx % 3]
