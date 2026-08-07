from __future__ import annotations

from dataclasses import replace
import math
import subprocess
import sys

import pytest

from metroflow.city.planar_blocks import CityBlock


def _build(style_id: str, seed: int = 17):
    from metroflow.city.hierarchical_streets import (
        build_hierarchical_street_skeleton,
    )
    from metroflow.city.planar_blocks import compile_planar_city_blocks
    from metroflow.city.realistic_local_fabric import build_continuous_local_fabric
    from metroflow.city.terrain_field import build_terrain_field
    from metroflow.city.urban_form import build_urban_form_field

    terrain = build_terrain_field(
        width=4_400,
        height=4_000,
        seed=seed,
        style_id=style_id,
        max_grid_size=64,
    )
    form = build_urban_form_field(terrain=terrain, style_id=style_id, seed=seed)
    skeleton = build_hierarchical_street_skeleton(
        terrain=terrain,
        urban_form=form,
    )
    network = build_continuous_local_fabric(
        terrain=terrain,
        urban_form=form,
        skeleton=skeleton,
    )
    return network, compile_planar_city_blocks(network)


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
@pytest.mark.parametrize("seed", (17, 29, 41, 44))
def test_planar_blocks_pass_frozen_geometry_and_area_gates(
    style_id: str,
    seed: int,
) -> None:
    network, catalog = _build(style_id, seed=seed)

    assert catalog.street_network_fingerprint == network.fingerprint
    assert catalog.blocks
    assert catalog.proper_intersection_count_after == 0
    assert catalog.short_segment_share <= 0.02
    assert 3_000.0 <= catalog.median_block_area_m2 <= 30_000.0
    assert catalog.p95_block_area_m2 <= 120_000.0
    assert all(block.frontage_street_ids for block in catalog.blocks)
    assert all(
        len(set(block.polygon_m[:-1])) == len(block.polygon_m) - 1
        for block in catalog.blocks
    )
    assert set(catalog.new_link_to_street_id) == {
        link.link_id for link in catalog.links
    }


def test_planar_block_catalog_is_deterministic() -> None:
    _, first = _build("grid_core", seed=41)
    _, second = _build("grid_core", seed=41)

    assert first.fingerprint == second.fingerprint
    assert tuple(block.polygon_m for block in first.blocks) == tuple(
        block.polygon_m for block in second.blocks
    )


def test_city_block_uses_area_weighted_polygon_centroid() -> None:
    block = CityBlock(
        block_id=0,
        polygon_m=((0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4), (0, 0)),
        area_m2=7.0,
        perimeter_m=16.0,
        frontage_street_ids=(3,),
    )

    assert block.centroid_m == pytest.approx((9.5 / 7.0, 9.5 / 7.0))


def test_city_block_rejects_non_simple_or_inconsistent_geometry() -> None:
    with pytest.raises(ValueError, match="must not repeat"):
        CityBlock(
            block_id=0,
            polygon_m=((0, 0), (4, 0), (4, 4), (4, 0), (0, 4), (0, 0)),
            area_m2=8.0,
            perimeter_m=math.inf,
            frontage_street_ids=(0,),
        )

    with pytest.raises(ValueError, match="area_m2 does not match"):
        CityBlock(
            block_id=0,
            polygon_m=((0, 0), (4, 0), (4, 4), (0, 4), (0, 0)),
            area_m2=15.0,
            perimeter_m=16.0,
            frontage_street_ids=(0,),
        )


def test_city_block_catalog_recomputes_aggregate_metrics() -> None:
    _, catalog = _build("grid_core", seed=17)

    with pytest.raises(ValueError, match="median_block_area_m2 does not match"):
        replace(
            catalog,
            median_block_area_m2=catalog.median_block_area_m2 + 1.0,
        )


def test_planar_block_import_does_not_load_optional_accelerators() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import metroflow.city.planar_blocks; "
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
