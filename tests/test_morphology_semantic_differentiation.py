"""Structural semantic differentiation tests for the 6 urban morphology archetypes.

These tests measure actual topological and spatial properties rather than
fingerprint/hash uniqueness, establishing explicit RED targets (via xfail(strict=True))
for the upcoming morphology grammar rebuild.
"""

from __future__ import annotations

import math
import statistics

import pytest

from metroflow.city.scale import CityScaleSpec
from metroflow.city.scalable_blocks import build_scalable_block_authority
from metroflow.city.scalable_topology import (
    FacilityKind,
    build_scalable_street_network,
)


def _compute_non_orthogonal_segment_ratio(roads: tuple) -> float:
    """Compute the fraction of road segments whose heading deviates from orthogonal axes."""
    non_orthogonal = 0
    total = 0
    for road in roads:
        coords = road.centerline
        for (x1, y1), (x2, y2) in zip(coords, coords[1:], strict=False):
            dx = x2 - x1
            dy = y2 - y1
            if dx == 0 and dy == 0:
                continue
            total += 1
            # Heading in degrees [0, 360)
            angle_deg = math.degrees(math.atan2(dy, dx)) % 360.0
            # Deviation from nearest 90-degree axis
            nearest_90 = round(angle_deg / 90.0) * 90.0
            diff = abs(angle_deg - nearest_90)
            if diff > 3.0:
                non_orthogonal += 1
    return (non_orthogonal / total) if total > 0 else 0.0


def test_river_constrained_has_bridge_structures() -> None:
    """river_constrained must contain physical bridge roads and failure groups."""
    scale = CityScaleSpec(100_000, 25.0)
    net = build_scalable_street_network(scale, "river_constrained", seed=17)
    bridge_roads = [
        r for r in net.roads if r.facility == FacilityKind.BRIDGE or "bridge" in r.semantic_id
    ]
    assert len(bridge_roads) >= 3, "must have at least 3 river crossing bridges"


@pytest.mark.xfail(
    reason="concentric ring geometry not yet differentiated in S2 generator",
    strict=True,
)
def test_ring_radial_has_concentric_ring_hierarchy() -> None:
    """ring_radial should have non-orthogonal curved/orbital segments forming concentric rings."""
    scale = CityScaleSpec(100_000, 25.0)
    radial_net = build_scalable_street_network(scale, "ring_radial", seed=17)

    non_ortho_ratio = _compute_non_orthogonal_segment_ratio(radial_net.roads)
    # A true ring-radial has circular rings with continuous angles (>20% non-orthogonal)
    assert non_ortho_ratio > 0.20, f"ring_radial non-orthogonal ratio is only {non_ortho_ratio:.4f}"


@pytest.mark.xfail(
    reason="polycentric centers currently share 1D y-coordinate (y=0)",
    strict=True,
)
def test_polycentric_centers_distributed_in_2d() -> None:
    """polycentric_tod must place centers across 2D space, not all on the same y coordinate."""
    scale = CityScaleSpec(100_000, 50.0)
    net = build_scalable_street_network(scale, "polycentric_tod", seed=17)
    assert len(net.centers) >= 3
    y_coords = {c[1] for c in net.centers}
    assert len(y_coords) > 1, f"centers {net.centers} are all on a 1D horizontal line"


@pytest.mark.xfail(
    reason="superblock hierarchy differentiation required: interior local fabric currently crosses arterial boundaries freely",
    strict=True,
)
def test_superblock_has_hierarchical_block_area_variation() -> None:
    """superblock_mixed should have distinct superblock cells enclosed by continuous arterial boundaries."""
    scale = CityScaleSpec(100_000, 25.0)
    sb_net = build_scalable_street_network(scale, "superblock_mixed", seed=17)
    sb_blocks = build_scalable_block_authority(sb_net)

    grid_net = build_scalable_street_network(scale, "grid_core", seed=17)
    grid_blocks = build_scalable_block_authority(grid_net)

    # Superblock face area distribution should have bimodal distribution (large superblock cells vs fine interior)
    sb_areas = [float(b.net_area_mm2) / 1e6 for b in sb_blocks.blocks]
    grid_areas = [float(b.net_area_mm2) / 1e6 for b in grid_blocks.blocks]

    assert len(sb_areas) > 0 and len(grid_areas) > 0
    sb_ratio = max(sb_areas) / (statistics.median(sb_areas) or 1.0)
    grid_ratio = max(grid_areas) / (statistics.median(grid_areas) or 1.0)
    assert sb_ratio > 2.0 * grid_ratio


@pytest.mark.xfail(
    reason="organic morphology currently rectilinear lattice with minor jitter",
    strict=True,
)
def test_organic_has_non_orthogonal_orientation_entropy() -> None:
    """organic morphology must feature non-orthogonal, organic road alignments (>20%)."""
    scale = CityScaleSpec(100_000, 25.0)
    net = build_scalable_street_network(scale, "organic", seed=17)

    non_ortho_ratio = _compute_non_orthogonal_segment_ratio(net.roads)
    assert non_ortho_ratio > 0.20, f"organic non-orthogonal ratio is only {non_ortho_ratio:.4f}"
