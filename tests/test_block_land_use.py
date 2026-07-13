from __future__ import annotations

from dataclasses import replace
import subprocess
import sys

import pytest


def _build(style_id: str, seed: int = 17):
    from metroflow.city.block_land_use import build_block_land_use_catalog
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
    return terrain, urban_form, street_network, blocks, land_use


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
def test_block_land_use_passes_functional_city_gates(
    style_id: str,
    seed: int,
) -> None:
    terrain, urban_form, street_network, blocks, catalog = _build(style_id, seed)

    assert catalog.terrain_fingerprint == terrain.fingerprint
    assert catalog.urban_form_fingerprint == urban_form.fingerprint
    assert catalog.street_network_fingerprint == street_network.fingerprint
    assert catalog.block_catalog_fingerprint == blocks.fingerprint
    assert tuple(item.block_id for item in catalog.blocks) == tuple(
        block.block_id for block in blocks.blocks
    )
    assert catalog.developed_block_count > 0
    assert catalog.industrial_residential_shared_edge_count == 0
    assert catalog.essential_access_ratio == 1.0
    assert {poi.poi_type.value for poi in catalog.pois} == {
        "home",
        "workplace",
        "leisure",
    }
    assert all(
        item.access_node_id is not None
        for item in catalog.blocks
        if item.is_developed
    )
    assert all(
        item.population_capacity == 0
        and item.job_capacity == 0
        and item.leisure_capacity == 0
        for item in catalog.blocks
        if not item.is_developed
    )


def test_block_land_use_is_deterministic() -> None:
    *_, first = _build("polycentric_tod", seed=41)
    *_, second = _build("polycentric_tod", seed=41)

    assert first.fingerprint == second.fingerprint
    assert first.blocks == second.blocks
    assert first.pois == second.pois


def test_block_land_use_records_reject_false_geometry_capacity_and_poi_data() -> None:
    *_, catalog = _build("grid_core", seed=17)
    developed = next(item for item in catalog.blocks if item.is_developed)

    with pytest.raises(ValueError, match="centroid does not match"):
        replace(
            developed,
            centroid_m=(developed.centroid_m[0] + 1.0, developed.centroid_m[1]),
        )
    with pytest.raises(ValueError, match="capacities do not match"):
        replace(
            developed,
            population_capacity=developed.population_capacity + 1,
        )
    first_poi = catalog.pois[0]
    with pytest.raises(ValueError, match="coordinates do not match"):
        replace(
            catalog,
            pois=(
                replace(first_poi, x_m=first_poi.x_m + 1.0),
                *catalog.pois[1:],
            ),
        )


def test_block_land_use_import_does_not_load_optional_accelerators() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import metroflow.city.block_land_use; "
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
