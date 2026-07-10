from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StyleProfile:
    style_id: str
    orientation_collapse_limit: float
    dominant_axis_share_limit: float
    downtown_core_density_ratio_min: float
    core_subcenter_distance_min_m: float


_STYLE_CATALOG: dict[str, StyleProfile] = {
    "grid_core": StyleProfile("grid_core", 0.55, 0.90, 1.20, 900.0),
    "ring_radial": StyleProfile("ring_radial", 0.40, 0.70, 1.50, 1500.0),
    "polycentric_tod": StyleProfile("polycentric_tod", 0.45, 0.75, 1.40, 1300.0),
    "river_constrained": StyleProfile("river_constrained", 0.50, 0.80, 1.30, 1100.0),
    "superblock_mixed": StyleProfile("superblock_mixed", 0.48, 0.78, 1.35, 1200.0),
    "organic": StyleProfile("organic", 0.60, 0.92, 1.10, 800.0),
}


def get_style_profile(style_id: str) -> StyleProfile:
    if style_id not in _STYLE_CATALOG:
        raise KeyError(f"unknown style_id: {style_id}")
    return _STYLE_CATALOG[style_id]
