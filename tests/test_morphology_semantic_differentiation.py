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


def _compute_orientation_entropy(roads: tuple, num_bins: int = 36) -> float:
    """Compute directional entropy of street orientations (OSMnx / Boeing standard)."""
    bin_counts = [0.0] * num_bins
    total_len = 0.0
    for road in roads:
        coords = [(x / 1000.0, y / 1000.0) for x, y in road.points_mm]
        for (x1, y1), (x2, y2) in zip(coords, coords[1:], strict=False):
            dx = x2 - x1
            dy = y2 - y1
            seg_len = math.hypot(dx, dy)
            if seg_len < 1e-3:
                continue
            total_len += seg_len
            angle_deg = math.degrees(math.atan2(dy, dx)) % 360.0
            bin_idx = int(angle_deg / (360.0 / num_bins)) % num_bins
            bin_counts[bin_idx] += seg_len
    if total_len == 0.0:
        return 0.0
    entropy = 0.0
    for count in bin_counts:
        p = count / total_len
        if p > 0.0:
            entropy -= p * math.log(p)
    return entropy


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
    raises=AssertionError,
)
def test_ring_radial_has_concentric_ring_hierarchy() -> None:
    """ring_radial should have non-orthogonal curved/orbital segments forming concentric rings."""
    scale = CityScaleSpec(100_000, 25.0)
    radial_net = build_scalable_street_network(scale, "ring_radial", seed=17)

    entropy = _compute_orientation_entropy(radial_net.roads)
    # A true ring-radial has circular rings with continuous angles (entropy > 2.80 vs ~2.16 on grid)
    assert entropy > 2.80, f"ring_radial orientation entropy is only {entropy:.4f}"


@pytest.mark.xfail(
    reason="polycentric centers currently share 1D y-coordinate (y=0)",
    strict=True,
    raises=AssertionError,
)
def test_polycentric_centers_distributed_in_2d() -> None:
    """polycentric_tod must place centers across 2D space, not all on the same y coordinate."""
    scale = CityScaleSpec(100_000, 25.0)
    net = build_scalable_street_network(scale, "polycentric_tod", seed=17)
    assert len(net.centers) >= 3
    y_coords = {c[1] for c in net.centers}
    assert len(y_coords) > 1, f"centers {net.centers} are all on a 1D horizontal line"


@pytest.mark.xfail(
    reason="superblock hierarchy differentiation required: interior local fabric currently crosses arterial boundaries freely",
    strict=True,
    raises=AssertionError,
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
    raises=AssertionError,
)
def test_organic_has_non_orthogonal_orientation_entropy() -> None:
    """organic morphology must feature non-orthogonal, organic road alignments (entropy > 2.80)."""
    scale = CityScaleSpec(100_000, 25.0)
    net = build_scalable_street_network(scale, "organic", seed=17)

    entropy = _compute_orientation_entropy(net.roads)
    assert entropy > 2.80, f"organic orientation entropy is only {entropy:.4f}"
