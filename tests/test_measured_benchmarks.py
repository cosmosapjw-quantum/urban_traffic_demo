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
    MeasuredRuntimeBenchmarkConfig,
    MeasuredRuntimeBenchmarkResult,
    run_city_smoke_benchmark,
    run_measured_flow_update_benchmark,
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


def test_measured_runtime_benchmark_preserves_rust_routing_copy_boundary_note(
    monkeypatch: pytest.MonkeyPatch,
):
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.init import build_initial_simulation_state

    bundle = build_initial_simulation_state(
        config=SimulationConfig(routing_backend="rust_cpu", active_agent_capacity=4),
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
    assert result.routing_copy_boundary_note == "rust_cpu Vec copy boundary"
    assert result.initial_tick == 0
    assert result.final_tick == 2
