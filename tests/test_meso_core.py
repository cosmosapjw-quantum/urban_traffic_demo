from dataclasses import replace

import pytest

from metroflow.core.state import GraphState, TrafficState, make_empty_world_state
from metroflow.traffic.meso import evolve_edges_fast_tick, project_feasible_movements, update_edge_state


def make_materialized_graph(num_edges: int) -> GraphState:
    return GraphState(
        num_nodes=max(num_edges + 1, 0),
        num_edges=num_edges,
        edge_src=tuple(range(num_edges)),
        edge_dst=tuple(range(1, num_edges + 1)),
        edge_class=("road",) * num_edges,
    )


def test_update_edge_state_nonnegative():
    st = update_edge_state(queue=0.0, stock=1.0, inflow=2.0, outflow=1.0, free_flow_time=10.0, capacity=2.0)
    assert st.queue >= 0.0
    assert st.stock >= 0.0
    assert st.travel_time >= 10.0


def test_update_edge_state_respects_storage_and_capacity():
    st = update_edge_state(queue=1.0, stock=2.0, inflow=3.0, outflow=10.0, free_flow_time=5.0, capacity=2.0)
    assert st.stock == 3.0
    assert st.queue <= st.stock


def test_project_feasible_movements():
    out = project_feasible_movements((3.0, 2.0), (1.0, 3.0), (2.0, 2.0))
    assert out == (1.0, 2.0)


def test_project_feasible_movements_rejects_length_mismatch():
    with pytest.raises(ValueError, match="movement arrays must have matching lengths"):
        project_feasible_movements((3.0, 2.0), (1.0,), (2.0, 2.0))


def test_evolve_edges_fast_tick_updates_all_edges():
    world = replace(
        make_empty_world_state(seed=11),
        graph=make_materialized_graph(2),
        traffic=TrafficState(
            step=3,
            edge_queue=(0.0, 1.0),
            edge_stock=(1.0, 2.0),
            edge_travel_time=(5.0, 7.0),
        ),
    )

    world2 = evolve_edges_fast_tick(
        world,
        edge_inflow_veh_per_tick=(2.0, 0.5),
        edge_outflow_veh_per_tick=(1.0, 1.5),
        edge_free_flow_time_ticks=(10.0, 12.0),
        edge_capacity_veh_per_tick=(2.0, 4.0),
    )

    assert world2.traffic.step == 4
    assert world2.traffic.edge_queue == (1.0, 1.0)
    assert world2.traffic.edge_stock == (2.0, 1.0)
    assert world2.traffic.edge_travel_time == (10.5, 12.25)
    assert world2.graph == world.graph
    assert world2.demand == world.demand
    assert world2.accessibility == world.accessibility
    assert world2.landuse == world.landuse
    assert world2.policy == world.policy
    assert world2.replay == world.replay


def test_evolve_edges_fast_tick_jax_backend_matches_baseline_output():
    pytest.importorskip("jax")
    world = replace(
        make_empty_world_state(seed=13),
        graph=make_materialized_graph(3),
        traffic=TrafficState(
            step=8,
            edge_queue=(0.0, 1.0, 2.0),
            edge_stock=(1.0, 3.0, 5.0),
            edge_travel_time=(4.0, 5.0, 6.0),
        ),
    )
    kwargs = {
        "edge_inflow_veh_per_tick": (2.0, 0.5, 1.0),
        "edge_outflow_veh_per_tick": (1.0, 1.5, 6.0),
        "edge_free_flow_time_ticks": (10.0, 12.0, 15.0),
        "edge_capacity_veh_per_tick": (2.0, 4.0, 3.0),
    }

    baseline = evolve_edges_fast_tick(world, **kwargs)
    accelerated = evolve_edges_fast_tick(world, edge_backend="jax", **kwargs)

    assert accelerated == baseline


def test_evolve_edges_fast_tick_rust_backend_matches_baseline_output():
    pytest.importorskip("_metroflow_rust")
    world = replace(
        make_empty_world_state(seed=14),
        graph=make_materialized_graph(3),
        traffic=TrafficState(
            step=8,
            edge_queue=(0.0, 1.0, 2.0),
            edge_stock=(1.0, 3.0, 5.0),
            edge_travel_time=(4.0, 5.0, 6.0),
        ),
    )
    kwargs = {
        "edge_inflow_veh_per_tick": (2.0, 0.5, 1.0),
        "edge_outflow_veh_per_tick": (1.0, 1.5, 6.0),
        "edge_free_flow_time_ticks": (10.0, 12.0, 15.0),
        "edge_capacity_veh_per_tick": (2.0, 4.0, 3.0),
    }

    baseline = evolve_edges_fast_tick(world, **kwargs)
    accelerated = evolve_edges_fast_tick(world, edge_backend="rust_cpu", **kwargs)

    assert accelerated == baseline


def test_evolve_edges_fast_tick_explicit_rust_backend_reports_unavailable(
    monkeypatch: pytest.MonkeyPatch,
):
    world = replace(
        make_empty_world_state(seed=13),
        graph=make_materialized_graph(1),
        traffic=TrafficState(
            step=0,
            edge_queue=(0.0,),
            edge_stock=(1.0,),
            edge_travel_time=(1.0,),
        ),
    )

    def fail_rust(*args, **kwargs):
        raise RuntimeError("Rust CPU edge backend unavailable")

    monkeypatch.setattr("metroflow.traffic.meso._evolve_edges_fast_tick_rust", fail_rust, raising=False)

    with pytest.raises(RuntimeError, match="Rust CPU edge backend unavailable"):
        evolve_edges_fast_tick(world, edge_backend="rust_cpu")


def test_evolve_edges_fast_tick_explicit_jax_backend_is_fail_closed(monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("jax")
    world = replace(
        make_empty_world_state(seed=13),
        graph=make_materialized_graph(1),
        traffic=TrafficState(
            step=0,
            edge_queue=(0.0,),
            edge_stock=(1.0,),
            edge_travel_time=(1.0,),
        ),
    )

    def fail_compile():
        raise RuntimeError("simulated jax compile failure")

    monkeypatch.setattr("metroflow.traffic.meso._compiled_jax_edge_kernel", fail_compile)

    with pytest.raises(RuntimeError, match="JAX edge backend failed"):
        evolve_edges_fast_tick(world, edge_backend="jax")


def test_evolve_edges_fast_tick_explicit_jax_backend_reports_unavailable(
    monkeypatch: pytest.MonkeyPatch,
):
    world = replace(
        make_empty_world_state(seed=13),
        graph=make_materialized_graph(1),
        traffic=TrafficState(
            step=0,
            edge_queue=(0.0,),
            edge_stock=(1.0,),
            edge_travel_time=(1.0,),
        ),
    )

    def fail_import():
        raise ModuleNotFoundError("No module named 'jax'")

    monkeypatch.setattr("metroflow.traffic.meso._compiled_jax_edge_kernel", fail_import)

    with pytest.raises(RuntimeError, match="JAX edge backend unavailable"):
        evolve_edges_fast_tick(world, edge_backend="jax")


def test_evolve_edges_fast_tick_auto_backend_falls_back_when_jax_fails(monkeypatch: pytest.MonkeyPatch):
    world = replace(
        make_empty_world_state(seed=13),
        graph=make_materialized_graph(1),
        traffic=TrafficState(
            step=0,
            edge_queue=(0.0,),
            edge_stock=(1.0,),
            edge_travel_time=(1.0,),
        ),
    )

    def fail_rust(*args, **kwargs):
        raise RuntimeError("simulated rust backend failure")

    def fail_compile():
        raise RuntimeError("simulated jax compile failure")

    monkeypatch.setattr("metroflow.traffic.meso._evolve_edges_fast_tick_rust", fail_rust)
    monkeypatch.setattr("metroflow.traffic.meso._compiled_jax_edge_kernel", fail_compile)

    baseline = evolve_edges_fast_tick(world, edge_backend="baseline")
    automatic = evolve_edges_fast_tick(world, edge_backend="auto")

    assert automatic == baseline


def test_evolve_edges_fast_tick_auto_backend_tries_rust_then_jax_then_baseline(
    monkeypatch: pytest.MonkeyPatch,
):
    world = replace(
        make_empty_world_state(seed=13),
        graph=make_materialized_graph(1),
        traffic=TrafficState(
            step=0,
            edge_queue=(0.0,),
            edge_stock=(1.0,),
            edge_travel_time=(1.0,),
        ),
    )
    calls: list[str] = []

    def fail_rust(*args, **kwargs):
        calls.append("rust_cpu")
        raise RuntimeError("simulated rust backend failure")

    def fail_jax(*args, **kwargs):
        calls.append("jax")
        raise RuntimeError("simulated jax backend failure")

    monkeypatch.setattr("metroflow.traffic.meso._evolve_edges_fast_tick_rust", fail_rust, raising=False)
    monkeypatch.setattr("metroflow.traffic.meso._evolve_edges_fast_tick_jax", fail_jax)

    baseline = evolve_edges_fast_tick(world, edge_backend="baseline")
    automatic = evolve_edges_fast_tick(world, edge_backend="auto")

    assert calls == ["rust_cpu", "jax"]
    assert automatic == baseline


def test_evolve_edges_fast_tick_rejects_unknown_edge_backend():
    world = replace(
        make_empty_world_state(),
        graph=make_materialized_graph(1),
        traffic=TrafficState(
            edge_queue=(0.0,),
            edge_stock=(0.0,),
            edge_travel_time=(1.0,),
        ),
    )

    with pytest.raises(ValueError, match="edge_backend must be one of"):
        evolve_edges_fast_tick(world, edge_backend="plugin")


def test_evolve_edges_fast_tick_uses_baseline_fallback():
    world = replace(
        make_empty_world_state(),
        graph=make_materialized_graph(2),
        traffic=TrafficState(
            step=0,
            edge_queue=(0.0, 0.0),
            edge_stock=(1.0, 3.0),
            edge_travel_time=(0.0, 0.0),
        ),
    )

    world2 = evolve_edges_fast_tick(world)

    assert world2.traffic.step == 1
    assert world2.traffic.edge_queue == (0.0, 0.0)
    assert world2.traffic.edge_stock == (1.0, 3.0)
    assert world2.traffic.edge_travel_time == (1.0, 1.0)


def test_evolve_edges_fast_tick_rejects_bad_tuple_lengths():
    world = replace(
        make_empty_world_state(),
        graph=make_materialized_graph(2),
        traffic=TrafficState(
            edge_queue=(0.0, 0.0),
            edge_stock=(0.0, 0.0),
            edge_travel_time=(1.0, 1.0),
        ),
    )

    with pytest.raises(ValueError, match="edge_inflow_veh_per_tick length must match graph.num_edges."):
        evolve_edges_fast_tick(world, edge_inflow_veh_per_tick=(1.0,))


def test_evolve_edges_fast_tick_is_deterministic():
    world = replace(
        make_empty_world_state(seed=5),
        graph=make_materialized_graph(2),
        traffic=TrafficState(
            step=1,
            edge_queue=(0.0, 2.0),
            edge_stock=(1.0, 3.0),
            edge_travel_time=(4.0, 6.0),
        ),
    )
    kwargs = {
        "edge_inflow_veh_per_tick": (2.0, 1.0),
        "edge_outflow_veh_per_tick": (1.0, 0.5),
        "edge_free_flow_time_ticks": (8.0, 9.0),
        "edge_capacity_veh_per_tick": (2.0, 1.5),
    }

    world2 = evolve_edges_fast_tick(world, **kwargs)
    world3 = evolve_edges_fast_tick(world, **kwargs)

    assert world2 == world3
