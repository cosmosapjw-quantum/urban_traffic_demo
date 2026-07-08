from dataclasses import replace

import pytest

import metroflow.metrics.benchmarks as benchmark_module
from metroflow.core.contracts import TickSchedule
from metroflow.flow.engine import BaselineFlowUpdateResult
from metroflow.core.state import TrafficState, make_empty_world_state
from metroflow.flow.state import create_link_state, create_node_state
from metroflow.metrics.benchmarks import (
    BenchmarkResult,
    MeasuredFlowBenchmarkConfig,
    MeasuredFlowBenchmarkResult,
    MeasuredBenchmarkConfig,
    MeasuredBenchmarkResult,
    MeasuredRoutingBenchmarkConfig,
    MeasuredRoutingBenchmarkResult,
    MeasuredRuntimeBenchmarkConfig,
    MeasuredRuntimeBenchmarkResult,
    run_city_smoke_benchmark,
    run_measured_flow_update_benchmark,
    run_measured_routing_candidate_benchmark,
    run_measured_runtime_spine_benchmark,
    run_measured_step_world_benchmark,
)


def make_measured_world(step: int = 1):
    return replace(
        make_empty_world_state(seed=17),
        traffic=TrafficState(step=step),
    )


def make_measured_config() -> MeasuredBenchmarkConfig:
    return MeasuredBenchmarkConfig(
        workload_name="baseline-fast",
        num_steps=3,
        schedule=TickSchedule(fast_every=1, medium_every=10, slow_every=100),
        edge_backend="baseline",
    )


def make_measured_routing_fixture():
    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr

    road_csr = build_road_network_csr(
        nodes=(Node(1), Node(2), Node(3), Node(4)),
        links=(
            RoadLink(10, 1, 2, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(11, 2, 4, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(12, 1, 3, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(13, 3, 4, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
        ),
    )
    link_state = create_link_state(
        road_csr.link_count,
        travel_time_cost=(50.0, 1.0, 1.0, 1.0),
        capacity_veh_per_tick=(5.0, 5.0, 5.0, 5.0),
    )
    return road_csr, link_state


def test_measured_benchmark_smoke_execution_returns_measured_record():
    result = run_measured_step_world_benchmark(make_measured_world(), make_measured_config())

    assert isinstance(result, MeasuredBenchmarkResult)
    assert result.name == "measured_step_world"
    assert result.workload_name == "baseline-fast"
    assert result.wall_clock_ns >= 0


def test_measured_and_proxy_benchmark_paths_remain_distinct():
    measured = run_measured_step_world_benchmark(make_measured_world(), make_measured_config())
    proxy = run_city_smoke_benchmark(population=100_000, edge_count=12_500, zone_count=64)

    assert isinstance(measured, MeasuredBenchmarkResult)
    assert isinstance(proxy, BenchmarkResult)
    assert measured.name != proxy.name
    assert measured.name.startswith("measured_")
    assert not proxy.name.startswith("measured_")
    assert hasattr(measured, "wall_clock_ns")
    assert not hasattr(measured, "step_proxy_score")
    assert hasattr(proxy, "step_proxy_score")
    assert not hasattr(proxy, "wall_clock_ns")


def test_empty_world_measured_benchmark_remains_contract_valid():
    result = run_measured_step_world_benchmark(
        make_measured_world(),
        MeasuredBenchmarkConfig(
            workload_name="empty-baseline-fast",
            num_steps=1,
            schedule=TickSchedule(fast_every=1, medium_every=10, slow_every=100),
        ),
    )

    assert result.name == "measured_step_world"
    assert result.edge_count == 0
    assert result.zone_count == 0
    assert result.wall_clock_ns >= 0


def test_identical_workload_shape_produces_valid_measured_result_records():
    config = make_measured_config()
    result_a = run_measured_step_world_benchmark(make_measured_world(), config)
    result_b = run_measured_step_world_benchmark(make_measured_world(), config)

    assert result_a.workload_name == result_b.workload_name
    assert result_a.num_steps == result_b.num_steps
    assert result_a.initial_traffic_step == result_b.initial_traffic_step
    assert result_a.final_traffic_step == result_b.final_traffic_step
    assert result_a.schedule == result_b.schedule
    assert result_a.seed == result_b.seed
    assert result_a.edge_count == result_b.edge_count
    assert result_a.zone_count == result_b.zone_count
    assert result_a.wall_clock_ns >= 0
    assert result_b.wall_clock_ns >= 0


def test_measured_benchmark_metadata_fields_are_populated_and_typed():
    config = MeasuredBenchmarkConfig(
        workload_name="jax-fast",
        num_steps=3,
        schedule=TickSchedule(fast_every=1, medium_every=10, slow_every=100),
        edge_backend="jax",
    )
    result = run_measured_step_world_benchmark(make_measured_world(), config)

    assert isinstance(result.name, str)
    assert isinstance(result.workload_name, str)
    assert isinstance(result.wall_clock_ns, int)
    assert isinstance(result.seed, int)
    assert isinstance(result.num_steps, int)
    assert isinstance(result.initial_traffic_step, int)
    assert isinstance(result.final_traffic_step, int)
    assert isinstance(result.schedule, TickSchedule)
    assert isinstance(result.edge_count, int)
    assert isinstance(result.zone_count, int)
    assert result.edge_backend == "jax"
    assert result.initial_traffic_step == 1
    assert result.final_traffic_step == 4


def test_measured_benchmark_preserves_rust_cpu_edge_backend_metadata():
    config = MeasuredBenchmarkConfig(
        workload_name="rust-cpu-fast",
        num_steps=3,
        schedule=TickSchedule(fast_every=1, medium_every=10, slow_every=100),
        edge_backend="rust_cpu",
    )
    result = run_measured_step_world_benchmark(make_measured_world(), config)

    assert result.edge_backend == "rust_cpu"
    assert result.initial_traffic_step == 1
    assert result.final_traffic_step == 4


def test_measured_benchmark_rejects_invalid_configuration():
    with pytest.raises(ValueError, match="workload_name must be non-empty"):
        run_measured_step_world_benchmark(
            make_measured_world(),
            MeasuredBenchmarkConfig(workload_name="", num_steps=1),
        )

    with pytest.raises(ValueError, match="num_steps must be positive"):
        run_measured_step_world_benchmark(
            make_measured_world(),
            MeasuredBenchmarkConfig(workload_name="baseline-fast", num_steps=0),
        )


def test_measured_benchmark_times_execution_loop_only(monkeypatch):
    events: list[object] = []
    timestamps = iter((100, 160))

    def fake_perf_counter_ns() -> int:
        events.append("timer")
        return next(timestamps)

    def fake_step_world(world, **kwargs):
        events.append(("step", world.traffic.step, kwargs["schedule"]))
        assert kwargs["edge_backend"] == "jax"
        return replace(world, traffic=replace(world.traffic, step=world.traffic.step + 1))

    monkeypatch.setattr(benchmark_module, "perf_counter_ns", fake_perf_counter_ns)
    monkeypatch.setattr(benchmark_module, "step_world", fake_step_world)

    config = MeasuredBenchmarkConfig(
        workload_name="jax-fast",
        num_steps=3,
        schedule=TickSchedule(fast_every=1, medium_every=10, slow_every=100),
        edge_backend="jax",
    )
    result = run_measured_step_world_benchmark(make_measured_world(), config)

    assert result.wall_clock_ns == 60
    assert events == [
        "timer",
        ("step", 1, config.schedule),
        ("step", 2, config.schedule),
        ("step", 3, config.schedule),
        "timer",
    ]


def test_measured_benchmark_surfaces_invalid_underlying_workload_inputs():
    with pytest.raises(
        ValueError,
        match="zonal_travel_times and zone_opportunities are required for medium cadence",
    ):
        run_measured_step_world_benchmark(
            make_measured_world(step=10),
            MeasuredBenchmarkConfig(
                workload_name="baseline-medium-invalid",
                num_steps=1,
                schedule=TickSchedule(fast_every=1, medium_every=10, slow_every=100),
            ),
        )


def test_measured_benchmark_continues_to_target_step_world_not_runtime_routing_wrapper(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[int] = []

    def fake_step_world(world, **kwargs):
        calls.append(world.traffic.step)
        return replace(world, traffic=replace(world.traffic, step=world.traffic.step + 1))

    def fail_if_wrapper_called(*args, **kwargs):
        raise AssertionError("measured benchmark must not call step_world_with_routing")

    monkeypatch.setattr(benchmark_module, "step_world", fake_step_world)
    monkeypatch.setattr(benchmark_module, "step_world_with_routing", fail_if_wrapper_called, raising=False)

    result = run_measured_step_world_benchmark(make_measured_world(), make_measured_config())

    assert calls == [1, 2, 3]
    assert result.final_traffic_step == 4


def test_measured_flow_update_benchmark_preserves_rust_cpu_backend_metadata(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[str] = []
    link_state = create_link_state(2, travel_time_cost=(5.0, 6.0), capacity_veh_per_tick=(1.0, 2.0))
    node_state = create_node_state((0,), (1,), node_count=2)

    def fake_update(link_state_arg, node_state_arg, **kwargs):
        calls.append(kwargs["flow_backend"])
        return BaselineFlowUpdateResult(
            link_state=link_state_arg,
            node_state=node_state_arg,
        )

    monkeypatch.setattr(benchmark_module, "update_link_node_flow", fake_update)

    config = MeasuredFlowBenchmarkConfig(
        workload_name="rust-flow-core",
        num_steps=2,
        flow_backend="rust_cpu",
    )
    result = run_measured_flow_update_benchmark(link_state, node_state, config)

    assert isinstance(result, MeasuredFlowBenchmarkResult)
    assert result.name == "measured_flow_update"
    assert result.flow_backend == "rust_cpu"
    assert result.link_count == 2
    assert result.turn_count == 1
    assert result.copy_boundary_note == "rust_cpu Vec copy boundary"
    assert calls == ["rust_cpu", "rust_cpu"]


def test_measured_routing_candidate_benchmark_records_baseline_path_metadata():
    road_csr, link_state = make_measured_routing_fixture()

    result = run_measured_routing_candidate_benchmark(
        road_csr,
        link_state,
        MeasuredRoutingBenchmarkConfig(
            workload_name="baseline-routing-candidate",
            num_steps=2,
            origin_node_id=1,
            destination_node_id=4,
            routing_backend="baseline",
            max_candidates=2,
        ),
    )

    assert isinstance(result, MeasuredRoutingBenchmarkResult)
    assert result.name == "measured_routing_candidate"
    assert result.routing_backend == "baseline"
    assert result.routing_copy_boundary_note == "numpy baseline"
    assert result.link_count == 4
    assert result.turn_count == 0
    assert result.origin_node_id == 1
    assert result.destination_node_id == 4
    assert result.candidate_path == (12, 13)
    assert result.candidate_path_length == 2
    assert result.candidate_paths == ((12, 13), (10, 11))
    assert result.candidate_count == 2
    assert result.candidate_path_costs == (2.0, 51.0)
    assert result.candidate_path_size_factors == (1.0, 1.0)
    assert result.candidate_generation_mode == "baseline_ranked_k"
    assert result.candidate_enumeration_backend == "python_host_ranked_k"
    assert result.routing_backend_requested == "baseline"
    assert result.routing_backend_actual == "baseline"
    assert result.routing_backend_fallback is None
    assert result.dynamic_potential_recompute_total == 2
    assert result.dynamic_potential_cache_hits_total == 0
    assert result.route_candidate_refresh_seconds_total >= 0.0
    assert result.dynamic_potential_recompute_seconds_total >= 0.0


def test_measured_routing_candidate_benchmark_records_single_candidate_metadata():
    road_csr, link_state = make_measured_routing_fixture()

    result = run_measured_routing_candidate_benchmark(
        road_csr,
        link_state,
        MeasuredRoutingBenchmarkConfig(
            workload_name="baseline-single-routing-candidate",
            num_steps=1,
            origin_node_id=1,
            destination_node_id=4,
            routing_backend="baseline",
        ),
    )

    assert result.candidate_path == (12, 13)
    assert result.candidate_paths == ((12, 13),)
    assert result.candidate_count == 1
    assert result.candidate_path_costs == (2.0,)
    assert result.candidate_path_size_factors == (1.0,)
    assert result.candidate_generation_mode == "baseline_greedy_single"
    assert result.candidate_enumeration_backend == "backend_greedy_route_candidate"
    assert result.routing_backend_requested == "baseline"
    assert result.routing_backend_actual == "baseline"
    assert result.routing_backend_fallback is None


def test_measured_routing_candidate_benchmark_preserves_rust_backend_metadata(
    monkeypatch: pytest.MonkeyPatch,
):
    from metroflow.routing.candidates import RouteCandidateSet

    road_csr, link_state = make_measured_routing_fixture()
    calls: list[str] = []

    def fake_create_route_candidate_set(**kwargs):
        calls.append(kwargs["routing_backend"])
        stats = kwargs.get("stats")
        if stats is not None:
            stats["dynamic_potential_recompute_total"] = int(
                stats.get("dynamic_potential_recompute_total", 0)
            ) + 1
        return RouteCandidateSet(
            od_key=(1, 4),
            candidate_ids=(0,),
            candidate_paths=((12, 13),),
            last_refresh_tick=0,
            metadata={
                "candidate_path_costs": (2.0,),
                "candidate_path_size_factors": (1.0,),
                "candidate_generation_mode": "baseline_greedy_single",
                "candidate_enumeration_backend": "backend_greedy_route_candidate",
                "routing_backend": "rust_cpu",
                "routing_backend_requested": "rust_cpu",
            },
        )

    monkeypatch.setattr(
        benchmark_module,
        "create_route_candidate_set",
        fake_create_route_candidate_set,
    )

    result = run_measured_routing_candidate_benchmark(
        road_csr,
        link_state,
        MeasuredRoutingBenchmarkConfig(
            workload_name="rust-routing-candidate",
            num_steps=2,
            origin_node_id=1,
            destination_node_id=4,
            routing_backend="rust_cpu",
        ),
    )

    assert result.routing_backend == "rust_cpu"
    assert (
        result.routing_copy_boundary_note
        == "rust_cpu Vec copy boundary for dynamic-potential, next-link scoring, greedy path, and ranked-K candidates"
    )
    assert result.candidate_path == (12, 13)
    assert result.candidate_path_costs == (2.0,)
    assert result.candidate_path_size_factors == (1.0,)
    assert result.dynamic_potential_recompute_total == 2
    assert calls == ["rust_cpu", "rust_cpu"]


def test_measured_runtime_benchmark_preserves_rust_routing_copy_boundary_note(
    monkeypatch: pytest.MonkeyPatch,
):
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.init import build_initial_simulation_state

    bundle = build_initial_simulation_state(
        config=SimulationConfig(
            routing_backend="rust_cpu",
            active_agent_capacity=4,
            route_path_size_gamma=2.0,
        ),
        scenario_seed=2,
        eager_trip_generation=False,
    )

    def fake_simulation_step(state, _control, key):
        return state.with_clock(tick_index=state.tick_index + 1), None, None, key

    monkeypatch.setattr(benchmark_module, "simulation_step", fake_simulation_step)

    result = run_measured_runtime_spine_benchmark(
        bundle.state,
        bundle.rng_key,
        MeasuredRuntimeBenchmarkConfig(workload_name="rust-routing-runtime", num_steps=2),
    )

    assert isinstance(result, MeasuredRuntimeBenchmarkResult)
    assert result.routing_backend == "rust_cpu"
    assert result.route_path_size_gamma == 2.0
    assert (
        result.routing_copy_boundary_note
        == "rust_cpu Vec copy boundary for dynamic-potential, next-link scoring, greedy path, and ranked-K candidates"
    )
    assert result.initial_tick == 0
    assert result.final_tick == 2


def test_measured_runtime_benchmark_preserves_reroute_counter_metadata(
    monkeypatch: pytest.MonkeyPatch,
):
    from metroflow.sim.init import build_initial_simulation_state

    bundle = build_initial_simulation_state(scenario_seed=4, eager_trip_generation=False)

    def fake_simulation_step(state, _control, key):
        metrics = dict(state.dynamic.metrics_state)
        metrics["us2_reroute_decisions_total"] = int(
            metrics.get("us2_reroute_decisions_total", 0)
        ) + 2
        metrics["us2_persistence_decisions_total"] = int(
            metrics.get("us2_persistence_decisions_total", 0)
        ) + 1
        metrics["active_agent_sink_wait_total"] = int(
            metrics.get("active_agent_sink_wait_total", 0)
        ) + 3
        metrics["active_agent_sink_wait_this_tick"] = 3
        metrics["route_candidate_refresh_seconds_total"] = 0.125
        metrics["dynamic_potential_recompute_seconds_total"] = 0.25
        metrics["routing_compile_seconds_estimate_total"] = 0.5
        metrics["active_agent_rerouted_this_tick"] = 2
        metrics["active_agent_reroute_cooldown_this_tick"] = 1
        return (
            state.with_clock(tick_index=state.tick_index + 1).with_dynamic_updates(
                metrics_state=metrics
            ),
            None,
            None,
            key,
        )

    monkeypatch.setattr(benchmark_module, "simulation_step", fake_simulation_step)

    result = run_measured_runtime_spine_benchmark(
        bundle.state,
        bundle.rng_key,
        MeasuredRuntimeBenchmarkConfig(workload_name="runtime-reroute", num_steps=2),
    )

    assert result.reroute_decisions_total == 4
    assert result.persistence_decisions_total == 2
    assert result.active_agent_sink_wait_total == 6
    assert result.active_agent_sink_wait_this_tick == 3
    assert result.route_candidate_refresh_seconds_total == 0.125
    assert result.dynamic_potential_recompute_seconds_total == 0.25
    assert result.routing_compile_seconds_estimate_total == 0.5
    assert result.active_agent_rerouted_this_tick == 2
    assert result.active_agent_reroute_cooldown_this_tick == 1
