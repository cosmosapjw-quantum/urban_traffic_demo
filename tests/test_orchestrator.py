from dataclasses import replace

import pytest

from metroflow.core.contracts import TickSchedule
from metroflow.core.state import (
    AccessibilityState,
    GraphState,
    LandUseState,
    PolicyState,
    ReplayState,
    TrafficState,
    make_empty_world_state,
)
from metroflow.sim.orchestrator import RuntimeRoutingInput, RuntimeRoutingStepResult, step_world, step_world_with_routing
from metroflow.sim import orchestrator as orchestrator_module
from metroflow.traffic.routing import CandidatePath, ODRouteChoiceResult


def make_materialized_graph(num_edges: int) -> GraphState:
    return GraphState(
        num_nodes=max(num_edges + 1, 0),
        num_edges=num_edges,
        edge_src=tuple(range(num_edges)),
        edge_dst=tuple(range(1, num_edges + 1)),
        edge_class=("road",) * num_edges,
    )


def make_world(num_edges: int = 2, step: int = 0) -> object:
    return replace(
        make_empty_world_state(seed=17),
        graph=make_materialized_graph(num_edges),
        traffic=TrafficState(
            step=step,
            edge_queue=(0.0,) * num_edges,
            edge_stock=(1.0,) * num_edges,
            edge_travel_time=(1.0,) * num_edges,
        ),
    )


def make_runtime_routing_input() -> RuntimeRoutingInput:
    return RuntimeRoutingInput(
        origin_id="origin-a",
        destination_id="destination-b",
        candidates=(
            CandidatePath(path_id=2, edge_ids=(2,), path_size=1.0),
            CandidatePath(path_id=1, edge_ids=(0, 1), path_size=1.0),
        ),
        k=2,
    )


def test_step_world_executes_fast_tick_edge_evolution_with_overrides():
    world = make_world(step=1)
    schedule = TickSchedule(fast_every=1, medium_every=5, slow_every=20)

    world2 = step_world(
        world,
        schedule=schedule,
        edge_inflow_veh_per_tick=(2.0, 0.5),
        edge_outflow_veh_per_tick=(1.0, 0.25),
        edge_free_flow_time_ticks=(5.0, 6.0),
        edge_capacity_veh_per_tick=(2.0, 4.0),
    )

    assert world2.traffic.step == 2
    assert world2.traffic.edge_queue == (1.0, 0.25)
    assert world2.traffic.edge_stock == (2.0, 1.25)
    assert world2.traffic.edge_travel_time == (5.5, 6.0625)


def test_step_world_from_inputs_accepts_structured_fast_tick_input():
    world = make_world(step=1)
    schedule = TickSchedule(fast_every=1, medium_every=5, slow_every=20)

    world2 = orchestrator_module.step_world_from_inputs(
        world,
        schedule=schedule,
        fast_tick=orchestrator_module.FastTickInput(
            edge_inflow_veh_per_tick=(2.0, 0.5),
            edge_outflow_veh_per_tick=(1.0, 0.25),
            edge_free_flow_time_ticks=(5.0, 6.0),
            edge_capacity_veh_per_tick=(2.0, 4.0),
        ),
    )

    assert world2.traffic.step == 2
    assert world2.traffic.edge_queue == (1.0, 0.25)
    assert world2.traffic.edge_stock == (2.0, 1.25)
    assert world2.traffic.edge_travel_time == (5.5, 6.0625)


def test_step_world_passes_optional_edge_inputs_to_helper(monkeypatch: pytest.MonkeyPatch):
    world = make_world(step=1)
    schedule = TickSchedule()
    captured: dict[str, object] = {}

    def fake_evolve(current_world, **kwargs):
        captured["world"] = current_world
        captured["kwargs"] = kwargs
        return current_world

    monkeypatch.setattr("metroflow.sim.orchestrator.evolve_edges_fast_tick", fake_evolve)

    result = step_world(
        world,
        schedule=schedule,
        edge_inflow_veh_per_tick=(1.0, 2.0),
        edge_outflow_veh_per_tick=(0.5, 0.25),
        edge_free_flow_time_ticks=(3.0, 4.0),
        edge_capacity_veh_per_tick=(5.0, 6.0),
        edge_backend="jax",
    )

    assert result is world
    assert captured["world"] is world
    assert captured["kwargs"] == {
        "edge_inflow_veh_per_tick": (1.0, 2.0),
        "edge_outflow_veh_per_tick": (0.5, 0.25),
        "edge_free_flow_time_ticks": (3.0, 4.0),
        "edge_capacity_veh_per_tick": (5.0, 6.0),
        "edge_backend": "jax",
    }


def test_step_world_rejects_override_length_mismatch():
    world = make_world(step=1)

    with pytest.raises(ValueError, match="edge_inflow_veh_per_tick length must match graph.num_edges."):
        step_world(
            world,
            schedule=TickSchedule(),
            edge_inflow_veh_per_tick=(1.0,),
        )


def test_step_world_is_deterministic_for_equivalent_inputs():
    world = make_world(step=2)
    schedule = TickSchedule(fast_every=1, medium_every=5, slow_every=20)
    kwargs = {
        "edge_inflow_veh_per_tick": (1.0, 0.25),
        "edge_outflow_veh_per_tick": (0.5, 0.25),
        "edge_free_flow_time_ticks": (7.0, 8.0),
        "edge_capacity_veh_per_tick": (2.0, 3.0),
    }

    world2 = step_world(world, schedule=schedule, **kwargs)
    world3 = step_world(world, schedule=schedule, **kwargs)

    assert world2 == world3


def test_step_world_rejects_invalid_incoming_world_before_fast_tick():
    world = replace(
        make_world(num_edges=1, step=1),
        traffic=TrafficState(
            step=1,
            edge_queue=(-1.0,),
            edge_stock=(1.0,),
            edge_travel_time=(1.0,),
        ),
    )

    with pytest.raises(ValueError, match="Edge queue values must be non-negative."):
        step_world(world, schedule=TickSchedule())


def test_step_world_rejects_invalid_produced_world(monkeypatch: pytest.MonkeyPatch):
    world = make_world(num_edges=1, step=1)

    def fake_evolve(current_world, **kwargs):
        return replace(
            current_world,
            traffic=replace(
                current_world.traffic,
                step=current_world.traffic.step + 1,
                edge_queue=(2.0,),
                edge_stock=(1.0,),
                edge_travel_time=(1.0,),
            ),
        )

    monkeypatch.setattr("metroflow.sim.orchestrator.evolve_edges_fast_tick", fake_evolve)

    with pytest.raises(ValueError, match="Edge queue must not exceed edge stock."):
        step_world(world, schedule=TickSchedule())


def test_step_world_fast_only_cadence_keeps_lagged_state_unchanged():
    world = replace(
        make_world(step=1),
        accessibility=AccessibilityState(
            version=3,
            lagged_snapshot_step=0,
            graph_version=0,
            landuse_version=4,
            zonal_costs=((1.0,),),
        ),
        landuse=LandUseState(
            version=4,
            zone_labels=("core",),
            housing_capacity=(100.0,),
            jobs_capacity=(120.0,),
        ),
        policy=PolicyState(version=5, last_learning_step=11),
        replay=ReplayState(seed=17, journal_length=9),
    )
    schedule = TickSchedule(fast_every=1, medium_every=3, slow_every=5)

    world2 = step_world(
        world,
        schedule=schedule,
        edge_inflow_veh_per_tick=(0.5, 0.0),
        edge_outflow_veh_per_tick=(0.25, 0.0),
        edge_free_flow_time_ticks=(2.0, 3.0),
        edge_capacity_veh_per_tick=(1.0, 1.0),
    )

    assert world2.accessibility == world.accessibility
    assert world2.landuse == world.landuse
    assert world2.policy == world.policy
    assert world2.replay == world.replay


def test_step_world_rejects_missing_medium_inputs():
    world = replace(
        make_world(step=2),
        landuse=LandUseState(
            version=2,
            zone_labels=("A", "B"),
            housing_capacity=(100.0, 120.0),
            jobs_capacity=(130.0, 140.0),
        ),
    )
    schedule = TickSchedule(fast_every=1, medium_every=2, slow_every=5)

    with pytest.raises(ValueError, match="zonal_travel_times and zone_opportunities are required"):
        step_world(world, schedule=schedule)


def test_step_world_allows_medium_cadence_on_empty_zone_world():
    world = make_world(step=2)
    schedule = TickSchedule(fast_every=1, medium_every=2, slow_every=5)

    world2 = step_world(
        world,
        schedule=schedule,
        zonal_travel_times=(),
        zone_opportunities=(),
    )

    assert world2.traffic.step == 3
    assert world2.accessibility.zonal_costs == ()
    assert world2.accessibility.lagged_snapshot_step == -1


def test_step_world_rejects_medium_only_cadence_before_mutation():
    world = replace(
        make_world(step=6),
        landuse=LandUseState(
            version=2,
            zone_labels=("A", "B"),
            housing_capacity=(100.0, 120.0),
            jobs_capacity=(130.0, 140.0),
        ),
    )
    schedule = TickSchedule(fast_every=4, medium_every=6, slow_every=12)

    with pytest.raises(ValueError, match="medium cadence requires fast cadence"):
        step_world(
            world,
            schedule=schedule,
            zonal_travel_times=((1.0, 2.0), (2.0, 1.0)),
            zone_opportunities=(1.0, 1.0),
        )


def test_step_world_rejects_same_tick_medium_and_slow_overlap_before_mutation():
    world = replace(
        make_world(step=0),
        landuse=LandUseState(
            version=2,
            zone_labels=("A", "B"),
            housing_capacity=(100.0, 120.0),
            jobs_capacity=(130.0, 140.0),
        ),
    )
    schedule = TickSchedule(fast_every=1, medium_every=2, slow_every=2)

    with pytest.raises(ValueError, match="same-step medium and slow overlap"):
        step_world(
            world,
            schedule=schedule,
            zonal_travel_times=((1.0, 2.0), (2.0, 1.0)),
            zone_opportunities=(1.0, 1.0),
        )


@pytest.mark.parametrize(
    ("accessibility", "message"),
    (
        (
            AccessibilityState(
                version=3,
                lagged_snapshot_step=5,
                graph_version=99,
                landuse_version=2,
                zonal_costs=((1.0, 2.0), (2.0, 1.0)),
            ),
            "graph_version must match the pre-call world",
        ),
        (
            AccessibilityState(
                version=3,
                lagged_snapshot_step=5,
                graph_version=0,
                landuse_version=99,
                zonal_costs=((1.0, 2.0), (2.0, 1.0)),
            ),
            "landuse_version must match the pre-call world",
        ),
    ),
)
def test_step_world_rejects_slow_snapshot_provenance_mismatch(accessibility: AccessibilityState, message: str):
    world = replace(
        make_world(step=6),
        landuse=LandUseState(
            version=2,
            zone_labels=("A", "B"),
            housing_capacity=(100.0, 120.0),
            jobs_capacity=(130.0, 140.0),
        ),
        accessibility=accessibility,
    )
    schedule = TickSchedule(fast_every=1, medium_every=4, slow_every=6)

    with pytest.raises(ValueError, match=message):
        step_world(world, schedule=schedule)


def test_step_world_rejects_same_tick_overlap_before_helpers_run(monkeypatch: pytest.MonkeyPatch):
    world = replace(
        make_world(step=0),
        landuse=LandUseState(
            version=2,
            zone_labels=("A", "B"),
            housing_capacity=(100.0, 120.0),
            jobs_capacity=(130.0, 140.0),
        ),
    )
    schedule = TickSchedule(fast_every=1, medium_every=2, slow_every=2)
    calls: list[str] = []

    def fake_compute(*args, **kwargs):
        calls.append("medium")
        raise AssertionError("compute_accessibility_snapshot should not run on illegal overlap")

    def fake_evolve(*args, **kwargs):
        calls.append("fast")
        raise AssertionError("evolve_edges_fast_tick should not run on illegal overlap")

    monkeypatch.setattr("metroflow.sim.orchestrator.compute_accessibility_snapshot", fake_compute)
    monkeypatch.setattr("metroflow.sim.orchestrator.evolve_edges_fast_tick", fake_evolve)

    with pytest.raises(ValueError, match="same-step medium and slow overlap"):
        step_world(
            world,
            schedule=schedule,
            zonal_travel_times=((1.0, 2.0), (2.0, 1.0)),
            zone_opportunities=(1.0, 1.0),
        )

    assert calls == []


def test_step_world_with_routing_invokes_od_evaluator_when_fast_due(monkeypatch: pytest.MonkeyPatch):
    world = make_world(num_edges=3, step=1)
    captured: dict[str, object] = {}

    def fake_evaluate(current_world, **kwargs):
        captured["world"] = current_world
        captured["kwargs"] = kwargs
        return ODRouteChoiceResult(
            name="od_route_choice",
            origin_id=kwargs["origin_id"],
            destination_id=kwargs["destination_id"],
            path_id=2,
            observed_cost=4.0,
            utility=-4.0,
            rerouted=False,
        )

    monkeypatch.setattr("metroflow.sim.orchestrator.evaluate_od_route_set", fake_evaluate)

    result = step_world_with_routing(
        world,
        schedule=TickSchedule(fast_every=1, medium_every=5, slow_every=20),
        edge_free_flow_time_ticks=(3.0, 3.0, 4.0),
        runtime_routing=make_runtime_routing_input(),
    )

    assert isinstance(result, RuntimeRoutingStepResult)
    assert result.world.traffic.step == 2
    assert result.routing_result == ODRouteChoiceResult(
        name="od_route_choice",
        origin_id="origin-a",
        destination_id="destination-b",
        path_id=2,
        observed_cost=4.0,
        utility=-4.0,
        rerouted=False,
    )
    assert captured["world"] == result.world
    assert captured["kwargs"] == {
        "origin_id": "origin-a",
        "destination_id": "destination-b",
        "candidates": (
            CandidatePath(path_id=2, edge_ids=(2,), path_size=1.0),
            CandidatePath(path_id=1, edge_ids=(0, 1), path_size=1.0),
        ),
        "k": 2,
        "weights": None,
    }


def test_step_world_with_routing_rejects_partial_runtime_routing_input():
    world = make_world(num_edges=3, step=1)

    with pytest.raises(ValueError, match="complete when provided"):
        step_world_with_routing(
            world,
            schedule=TickSchedule(fast_every=1, medium_every=5, slow_every=20),
            runtime_routing=RuntimeRoutingInput(origin_id="origin-a"),
        )


def test_step_world_with_routing_changes_choice_when_network_costs_change():
    world = make_world(num_edges=3, step=1)
    schedule = TickSchedule(fast_every=1, medium_every=5, slow_every=20)
    routing_input = make_runtime_routing_input()

    first = step_world_with_routing(
        world,
        schedule=schedule,
        edge_inflow_veh_per_tick=(0.0, 0.0, 0.0),
        edge_outflow_veh_per_tick=(0.0, 0.0, 0.0),
        edge_free_flow_time_ticks=(3.0, 3.0, 10.0),
        edge_capacity_veh_per_tick=(1.0, 1.0, 1.0),
        runtime_routing=routing_input,
    )
    second = step_world_with_routing(
        world,
        schedule=schedule,
        edge_inflow_veh_per_tick=(0.0, 0.0, 0.0),
        edge_outflow_veh_per_tick=(0.0, 0.0, 0.0),
        edge_free_flow_time_ticks=(8.0, 1.0, 6.0),
        edge_capacity_veh_per_tick=(1.0, 1.0, 1.0),
        runtime_routing=routing_input,
    )

    assert first.routing_result is not None
    assert second.routing_result is not None
    assert first.routing_result.path_id == 1
    assert second.routing_result.path_id == 2


def test_step_world_with_routing_falls_back_when_runtime_routing_is_absent():
    world = make_world(num_edges=3, step=1)
    schedule = TickSchedule(fast_every=1, medium_every=5, slow_every=20)
    kwargs = {
        "edge_inflow_veh_per_tick": (0.5, 0.0, 0.0),
        "edge_outflow_veh_per_tick": (0.25, 0.0, 0.0),
        "edge_free_flow_time_ticks": (2.0, 3.0, 4.0),
        "edge_capacity_veh_per_tick": (1.0, 1.0, 1.0),
    }

    routed = step_world_with_routing(world, schedule=schedule, **kwargs)
    baseline = step_world(world, schedule=schedule, **kwargs)

    assert routed.routing_result is None
    assert routed.world == baseline


def test_step_world_with_routing_falls_back_when_fast_is_not_due():
    world = make_world(num_edges=3, step=1)
    schedule = TickSchedule(fast_every=4, medium_every=5, slow_every=20)

    routed = step_world_with_routing(
        world,
        schedule=schedule,
        runtime_routing=make_runtime_routing_input(),
    )

    assert routed.routing_result is None
    assert routed.world == world


def test_step_world_with_routing_is_deterministic_and_keeps_unsorted_candidates_safe():
    world = make_world(num_edges=3, step=1)
    schedule = TickSchedule(fast_every=1, medium_every=5, slow_every=20)
    kwargs = {
        "edge_inflow_veh_per_tick": (0.0, 0.0, 0.0),
        "edge_outflow_veh_per_tick": (0.0, 0.0, 0.0),
        "edge_free_flow_time_ticks": (8.0, 1.0, 6.0),
        "edge_capacity_veh_per_tick": (1.0, 1.0, 1.0),
        "runtime_routing": make_runtime_routing_input(),
    }

    first = step_world_with_routing(world, schedule=schedule, **kwargs)
    second = step_world_with_routing(world, schedule=schedule, **kwargs)
    baseline = step_world(world, schedule=schedule, **{k: v for k, v in kwargs.items() if k != "runtime_routing"})

    assert first == second
    assert first.routing_result is not None
    assert first.routing_result.path_id == 2
    assert first.world == baseline
