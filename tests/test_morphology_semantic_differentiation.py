"""Structural semantic differentiation tests for the 6 urban morphology archetypes.

These tests measure actual topological and spatial properties rather than
fingerprint/hash uniqueness, establishing explicit RED targets (via xfail)
for the upcoming morphology grammar rebuild.
"""

from __future__ import annotations

import pytest

from metroflow.city.scale import CityScaleSpec
from metroflow.city.scalable_topology import (
    FacilityKind,
    build_scalable_street_network,
)


def test_river_constrained_has_bridge_structures() -> None:
    """river_constrained must contain physical bridge roads and failure groups."""
    scale = CityScaleSpec(100_000, 25.0)
    net = build_scalable_street_network(scale, "river_constrained", seed=17)
    bridge_roads = [
        r for r in net.roads if r.facility == FacilityKind.BRIDGE or "bridge" in r.semantic_id
    ]
    assert len(bridge_roads) >= 3, "must have at least 3 river crossing bridges"


@pytest.mark.xfail(
    reason="morphology grammar rebuild required: ring_radial lacks genuine concentric rings in S2",
    strict=False,
)
def test_ring_radial_has_concentric_ring_hierarchy() -> None:
    """ring_radial should have distinct circular/concentric road alignments compared to grid_core."""
    scale = CityScaleSpec(100_000, 25.0)
    radial_net = build_scalable_street_network(scale, "ring_radial", seed=17)
    grid_net = build_scalable_street_network(scale, "grid_core", seed=17)

    # In a genuine ring-radial, node degree distribution or curved road segments differ fundamentally
    radial_road_classes = {r.hierarchy for r in radial_net.roads}
    grid_road_classes = {r.hierarchy for r in grid_net.roads}
    # Structural assertion that will fail on current rectilinear lattice
    assert radial_road_classes != grid_road_classes


@pytest.mark.xfail(
    reason="polycentric centers currently share 1D y-coordinate (y=0)",
    strict=False,
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
    strict=False,
)
def test_superblock_has_hierarchical_block_area_variation() -> None:
    """superblock_mixed should have distinct superblock cells enclosed by continuous arterial boundaries."""
    from metroflow.city.scalable_blocks import build_scalable_block_authority

    scale = CityScaleSpec(100_000, 25.0)
    sb_net = build_scalable_street_network(scale, "superblock_mixed", seed=17)
    sb_blocks = build_scalable_block_authority(sb_net)

    grid_net = build_scalable_street_network(scale, "grid_core", seed=17)
    grid_blocks = build_scalable_block_authority(grid_net)

    # Superblock face area distribution should have bimodal distribution (large superblock cells vs fine interior)
    sb_areas = [f.area_m2 for f in sb_blocks.faces if f.area_m2 > 0]
    grid_areas = [f.area_m2 for f in grid_blocks.faces if f.area_m2 > 0]

    # In a genuine superblock, the max face area ratio to median face area is significantly larger than orthogonal grid
    import statistics
    sb_ratio = max(sb_areas) / (statistics.median(sb_areas) or 1.0)
    grid_ratio = max(grid_areas) / (statistics.median(grid_areas) or 1.0)
    assert sb_ratio > 2.0 * grid_ratio

