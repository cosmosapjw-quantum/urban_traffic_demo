from __future__ import annotations

import subprocess
import sys

import pytest


def _build(style_id: str, *, seed: int = 17):
    from metroflow.city.hierarchical_streets import (
        build_hierarchical_street_skeleton,
    )
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
    return terrain, form, skeleton, network


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
def test_local_fabric_is_deterministic_connected_and_accessible(style_id: str) -> None:
    _, _, skeleton, first = _build(style_id, seed=29)
    _, _, _, second = _build(style_id, seed=29)

    assert first.fingerprint == second.fingerprint
    assert first.skeleton_fingerprint == skeleton.fingerprint
    assert first.skeleton_street_count == len(skeleton.streets)
    assert first.local_street_count > 0
    assert first.local_component_count_before_connectors >= 1
    assert (
        first.collector_street_count
        + first.local_component_direct_attachment_count
        == first.local_component_count_before_connectors
    )
    assert first.max_developed_access_distance_m <= 400.0
    assert tuple(street.street_id for street in first.streets) == tuple(
        range(len(first.streets))
    )


def test_local_and_collector_streets_do_not_cross_water_cells() -> None:
    from metroflow.city.graph import RoadClass

    terrain, _, _, network = _build("river_constrained", seed=29)
    for street in network.streets[network.skeleton_street_count :]:
        assert street.road_class in {RoadClass.LOCAL, RoadClass.COLLECTOR}
        for x, y in street.points_m:
            column = int(abs(terrain.x_coordinates_m - x).argmin())
            row = int(abs(terrain.y_coordinates_m - y).argmin())
            assert not bool(terrain.water_mask[row, column])


def test_style_profiles_do_not_collapse_to_one_local_edge_pattern() -> None:
    style_ids = (
        "ring_radial",
        "grid_core",
        "polycentric_tod",
        "river_constrained",
        "superblock_mixed",
        "organic",
    )
    signatures = set()
    for style_id in style_ids:
        _, _, _, network = _build(style_id, seed=41)
        local_start = network.skeleton_street_count
        local_end = local_start + network.local_street_count
        signatures.add(
            tuple(street.points_m for street in network.streets[local_start:local_end])
        )

    assert len(signatures) == len(style_ids)


@pytest.mark.parametrize("spacing", (79.0, 221.0))
def test_local_fabric_rejects_out_of_contract_spacing(spacing: float) -> None:
    from metroflow.city.realistic_local_fabric import build_continuous_local_fabric

    terrain, form, skeleton, _ = _build("grid_core")
    with pytest.raises(ValueError, match="block_spacing_m"):
        build_continuous_local_fabric(
            terrain=terrain,
            urban_form=form,
            skeleton=skeleton,
            block_spacing_m=spacing,
        )


def test_local_fabric_import_does_not_load_optional_accelerators() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import metroflow.city.realistic_local_fabric; "
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
