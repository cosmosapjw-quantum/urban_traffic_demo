from dataclasses import replace

import pytest

from metroflow.core.contracts import TickSchedule
from metroflow.core.state import (
    AccessibilityState,
    GraphState,
    LandUseState,
    TrafficState,
    make_empty_world_state,
)
from metroflow.sim.orchestrator import step_world


def make_materialized_graph(num_edges: int) -> GraphState:
    return GraphState(
        num_nodes=max(num_edges + 1, 0),
        num_edges=num_edges,
        edge_src=tuple(range(num_edges)),
        edge_dst=tuple(range(1, num_edges + 1)),
        edge_class=("road",) * num_edges,
    )


def make_world(step: int = 0, zone_labels: tuple[str, ...] = ("core", "ring")):
    num_edges = 2
    return replace(
        make_empty_world_state(seed=17),
        graph=make_materialized_graph(num_edges),
        traffic=TrafficState(
            step=step,
            edge_queue=(0.0, 0.0),
            edge_stock=(1.0, 1.0),
            edge_travel_time=(1.0, 1.0),
        ),
        landuse=LandUseState(
            version=3,
            zone_labels=zone_labels,
            housing_capacity=tuple(100.0 + idx for idx, _ in enumerate(zone_labels)),
            jobs_capacity=tuple(120.0 + idx for idx, _ in enumerate(zone_labels)),
        ),
    )


def fast_kwargs():
    return {
        "edge_inflow_veh_per_tick": (0.5, 0.25),
        "edge_outflow_veh_per_tick": (0.25, 0.0),
        "edge_free_flow_time_ticks": (2.0, 3.0),
        "edge_capacity_veh_per_tick": (1.0, 1.0),
    }


def medium_kwargs():
    return {
        "zonal_travel_times": ((2.0, 4.0), (6.0, 8.0)),
        "zone_opportunities": (2.0, 4.0),
    }


def test_fast_only_step_keeps_accessibility_and_landuse_unchanged():
    world = replace(
        make_world(step=1),
        accessibility=AccessibilityState(
            version=4,
            lagged_snapshot_step=0,
            graph_version=0,
            landuse_version=3,
            zonal_costs=((1.0, 2.0), (2.0, 1.0)),
        ),
    )
    schedule = TickSchedule(fast_every=1, medium_every=3, slow_every=5)

    world2 = step_world(world, schedule=schedule, **fast_kwargs())

    assert world2.traffic.step == 2
    assert world2.accessibility == world.accessibility
    assert world2.landuse == world.landuse
    assert world2.graph.version == world.graph.version


def test_legal_fast_and_medium_step_produces_accessibility_snapshot():
    world = make_world(step=2)
    schedule = TickSchedule(fast_every=1, medium_every=2, slow_every=5)

    world2 = step_world(
        world,
        schedule=schedule,
        zonal_travel_times=((2.0, 4.0), (6.0, 8.0)),
        zone_opportunities=(2.0, 4.0),
        **fast_kwargs(),
    )

    assert world2.traffic.step == 3
    assert world2.accessibility.lagged_snapshot_step == 2
    assert world2.accessibility.graph_version == world.graph.version
    assert world2.accessibility.landuse_version == world.landuse.version
    assert world2.accessibility.zonal_costs == ((1.0, 1.0), (3.0, 2.0))


def test_slow_step_consumes_only_preexisting_lagged_accessibility():
    world = replace(
        make_world(step=6),
        accessibility=AccessibilityState(
            version=7,
            lagged_snapshot_step=5,
            graph_version=0,
            landuse_version=3,
            zonal_costs=((2.0, 4.0), (3.0, 9.0)),
        ),
    )
    schedule = TickSchedule(fast_every=1, medium_every=4, slow_every=6)

    world2 = step_world(world, schedule=schedule)

    assert world2.traffic.step == world.traffic.step + 1
    assert world2.landuse.version == world.landuse.version + 1
    assert world2.landuse.housing_capacity == (100.00333333333333, 101.00166666666667)
    assert world2.landuse.jobs_capacity == (120.00333333333333, 121.00166666666667)
    assert world2.accessibility.zonal_costs == ()
    assert world2.accessibility.lagged_snapshot_step == -1
    assert world2.accessibility.graph_version == world.accessibility.graph_version
    assert world2.accessibility.landuse_version == world.accessibility.landuse_version


def test_same_tick_medium_and_slow_overlap_is_rejected_before_mutation():
    world = make_world(step=0)
    schedule = TickSchedule(fast_every=1, medium_every=2, slow_every=2)

    with pytest.raises(ValueError, match="same-step medium and slow overlap"):
        step_world(
            world,
            schedule=schedule,
            zonal_travel_times=((1.0, 1.0), (1.0, 1.0)),
            zone_opportunities=(1.0, 1.0),
            **fast_kwargs(),
        )


def test_medium_snapshot_from_prior_call_is_consumed_on_later_slow_call():
    initial = make_world(step=2)
    schedule = TickSchedule(fast_every=1, medium_every=3, slow_every=5)

    after_fast_only = step_world(initial, schedule=schedule, **medium_kwargs(), **fast_kwargs())
    after_medium = step_world(after_fast_only, schedule=schedule, **medium_kwargs(), **fast_kwargs())
    produced_snapshot = after_medium.accessibility
    after_carry = step_world(after_medium, schedule=schedule, **medium_kwargs(), **fast_kwargs())
    after_slow = step_world(after_carry, schedule=schedule, **medium_kwargs(), **fast_kwargs())

    assert after_fast_only.traffic.step == 3
    assert after_fast_only.accessibility == initial.accessibility
    assert after_medium.traffic.step == 4
    assert after_medium.accessibility.lagged_snapshot_step == 3
    assert after_medium.accessibility.zonal_costs == ((1.0, 1.0), (3.0, 2.0))
    assert after_carry.traffic.step == 5
    assert after_carry.accessibility == produced_snapshot
    assert after_slow.traffic.step == 6
    assert after_slow.landuse.housing_capacity == (100.01, 101.004)
    assert after_slow.landuse.jobs_capacity == (120.01, 121.004)
    assert after_slow.accessibility.zonal_costs == ()
    assert after_slow.accessibility.lagged_snapshot_step == -1
    assert after_slow.accessibility.graph_version == produced_snapshot.graph_version
    assert after_slow.accessibility.landuse_version == produced_snapshot.landuse_version


def test_multistep_sequence_is_deterministic():
    initial = make_world(step=2)
    schedule = TickSchedule(fast_every=1, medium_every=3, slow_every=5)

    def run_trajectory():
        current = initial
        trajectory = []
        for _ in range(4):
            current = step_world(current, schedule=schedule, **medium_kwargs(), **fast_kwargs())
            trajectory.append(current)
        return trajectory

    run1 = run_trajectory()
    run2 = run_trajectory()

    assert run1 == run2
    assert [world.traffic.step for world in run1] == [3, 4, 5, 6]
    assert run1[1].accessibility.lagged_snapshot_step == 3
    assert run1[2].accessibility == run1[1].accessibility
    assert run1[3].accessibility.zonal_costs == ()
