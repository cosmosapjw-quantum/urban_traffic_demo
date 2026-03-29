from dataclasses import replace

import pytest

from metroflow.core.cache import invalidate_on_graph_edit
from metroflow.core.state import GraphState, LandUseState, make_empty_world_state
from metroflow.demand.accessibility import (
    compute_accessibility_placeholder,
    compute_accessibility_snapshot,
    snapshot_is_stale,
    update_accessibility_cache,
)


def test_accessibility_placeholder():
    snap = compute_accessibility_placeholder()
    assert snap.computed_at_step == 0


def test_accessibility_cache_updates_and_invalidates_on_graph_edit():
    world = replace(
        make_empty_world_state(),
        graph=GraphState(version=1),
        landuse=LandUseState(
            version=2,
            zone_labels=("A", "B"),
            housing_capacity=(10.0, 20.0),
            jobs_capacity=(12.0, 18.0),
        ),
    )
    snapshot = compute_accessibility_snapshot(
        step_idx=world.traffic.step - 1,
        graph_version=world.graph.version,
        landuse_version=world.landuse.version,
        zonal_travel_times=((1.0, 2.0), (2.0, 1.0)),
        zone_opportunities=(10.0, 20.0),
    )
    updated_world = update_accessibility_cache(world, snapshot)

    assert updated_world.accessibility.graph_version == 1
    assert updated_world.accessibility.landuse_version == 2
    assert updated_world.accessibility.lagged_snapshot_step == world.traffic.step - 1
    assert updated_world.accessibility.zonal_costs == ((0.1, 0.1), (0.2, 0.05))
    assert snapshot_is_stale(snapshot, invalidate_on_graph_edit(updated_world)) is True


def test_compute_accessibility_snapshot_rejects_negative_travel_time_or_opportunity():
    with pytest.raises(ValueError, match="zonal_travel_times must be non-negative."):
        compute_accessibility_snapshot(
            step_idx=0,
            graph_version=1,
            landuse_version=2,
            zonal_travel_times=((-1.0,),),
            zone_opportunities=(1.0,),
        )

    with pytest.raises(ValueError, match="zone_opportunities must be non-negative."):
        compute_accessibility_snapshot(
            step_idx=0,
            graph_version=1,
            landuse_version=2,
            zonal_travel_times=((1.0,),),
            zone_opportunities=(-1.0,),
        )


def test_update_accessibility_cache_preserves_cleared_state_for_zero_zone_snapshot():
    world = make_empty_world_state()
    snapshot = compute_accessibility_snapshot(
        step_idx=world.traffic.step,
        graph_version=world.graph.version,
        landuse_version=world.landuse.version,
        zonal_travel_times=(),
        zone_opportunities=(),
    )

    updated_world = update_accessibility_cache(world, snapshot)

    assert updated_world.accessibility.zonal_costs == ()
    assert updated_world.accessibility.lagged_snapshot_step == -1
