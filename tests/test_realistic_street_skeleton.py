from __future__ import annotations

import subprocess
import sys
from dataclasses import replace

import pytest


def _build(style_id: str, seed: int = 17):
    from metroflow.city.hierarchical_streets import (
        build_hierarchical_street_skeleton,
    )
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
    plan = build_hierarchical_street_skeleton(
        terrain=terrain,
        urban_form=urban_form,
    )
    return terrain, urban_form, plan


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
def test_hierarchical_skeleton_is_deterministic_and_connects_anchors(
    style_id: str,
) -> None:
    terrain, _, first = _build(style_id)
    _, _, second = _build(style_id)

    assert first.fingerprint == second.fingerprint
    assert first.tree_edge_count == len(first.anchor_points_m) - 1
    assert first.redundancy_edge_count >= 1
    assert len({street.street_id for street in first.streets}) == len(first.streets)
    adjacency = {index: set() for index in range(len(first.anchor_points_m))}
    for street in first.streets:
        left, right = street.source_anchor_ids
        adjacency[left].add(right)
        adjacency[right].add(left)
        assert street.length_m > 0.0
        assert street.capacity_veh_per_second > 0.0
        assert all(
            -terrain.width_m * 0.5 <= x <= terrain.width_m * 0.5
            and -terrain.height_m * 0.5 <= y <= terrain.height_m * 0.5
            for x, y in street.points_m
        )
    reached = {0}
    frontier = [0]
    while frontier:
        current = frontier.pop()
        for neighbor in adjacency[current] - reached:
            reached.add(neighbor)
            frontier.append(neighbor)
    assert reached == set(adjacency)


def test_river_skeleton_splits_water_crossing_into_bridge_runs() -> None:
    from metroflow.city.graph import RoadClass

    _, _, plan = _build("river_constrained", seed=29)
    bridges = tuple(
        street for street in plan.streets if street.road_class is RoadClass.BRIDGE
    )

    assert bridges
    assert all(street.bridge_group_id is not None for street in bridges)
    assert len({street.bridge_group_id for street in bridges}) == len(bridges)
    assert any(
        street.road_class is not RoadClass.BRIDGE for street in plan.streets
    )


def test_skeleton_rejects_mismatched_terrain_and_urban_form() -> None:
    from metroflow.city.hierarchical_streets import (
        build_hierarchical_street_skeleton,
    )

    terrain, urban_form, _ = _build("grid_core")
    stale = replace(urban_form, terrain_fingerprint="stale")

    with pytest.raises(ValueError, match="provided terrain"):
        build_hierarchical_street_skeleton(terrain=terrain, urban_form=stale)


def test_street_plan_rejects_out_of_range_anchor_provenance() -> None:
    _, _, plan = _build("grid_core")
    bad_street = replace(plan.streets[0], source_anchor_ids=(0, 999))

    with pytest.raises(ValueError, match="outside anchor range"):
        replace(plan, streets=(bad_street, *plan.streets[1:]))


def test_street_skeleton_import_does_not_load_optional_accelerators() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import metroflow.city.hierarchical_streets; "
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
