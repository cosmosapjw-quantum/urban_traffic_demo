from dataclasses import replace
import json
import sys

import pytest

import metroflow.metrics.benchmarks as benchmark_module
from metroflow.core.contracts import TickSchedule
from metroflow.flow.engine import BaselineFlowUpdateResult
from metroflow.core.state import TrafficState, make_empty_world_state
from metroflow.flow.state import create_link_state, create_node_state
from metroflow.metrics.benchmarks import (
    BenchmarkResult,
    MeasuredDynamicPotentialBenchmarkConfig,
    MeasuredDynamicPotentialBenchmarkResult,
    MeasuredFlowBenchmarkConfig,
    MeasuredFlowBenchmarkResult,
    MeasuredBenchmarkConfig,
    MeasuredBenchmarkResult,
    MeasuredRoutingBenchmarkConfig,
    MeasuredRoutingBenchmarkResult,
    MeasuredRuntimeBenchmarkConfig,
    MeasuredRuntimeBenchmarkSuiteConfig,
    MeasuredRuntimeBenchmarkResult,
    MeasuredRuntimeBenchmarkSuiteResult,
    RuntimeStageTiming,
    run_city_smoke_benchmark,
    run_measured_dynamic_potential_benchmark,
    run_measured_flow_update_benchmark,
    run_measured_routing_candidate_benchmark,
    run_measured_runtime_spine_benchmark_suite,
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


def make_runtime_stage_result(
    *,
    seed: int,
    flow_share: float,
    active_agent_share: float,
) -> MeasuredRuntimeBenchmarkResult:
    wall_clock_ns = 1_000
    return MeasuredRuntimeBenchmarkResult(
        name="measured_runtime_spine",
        workload_name="runtime-stage-gate",
        wall_clock_ns=wall_clock_ns,
        num_steps=1,
        initial_tick=0,
        final_tick=1,
        active_agent_count=0,
        flow_backend="baseline",
        routing_backend="baseline",
        agent_backend="baseline",
        route_path_size_gamma=0.0,
        routing_copy_boundary_note="numpy baseline",
        agent_copy_boundary_note="python baseline",
        route_candidate_refresh_total=0,
        route_candidate_reuse_total=0,
        dynamic_potential_recompute_total=0,
        dynamic_potential_cache_hits_total=0,
        seed=seed,
        runtime_stage_timings=(
            RuntimeStageTiming(
                "flow_update",
                int(round(wall_clock_ns * flow_share)),
                flow_share,
                flow_share >= 0.30,
            ),
            RuntimeStageTiming(
                "active_agent_update",
                int(round(wall_clock_ns * active_agent_share)),
                active_agent_share,
                active_agent_share >= 0.30,
            ),
            RuntimeStageTiming(
                "dynamic_potential_recompute",
                600,
                0.60,
                False,
            ),
        ),
        gpu_candidate_stage_names=tuple(
            name
            for name, share in (
                ("flow_update", flow_share),
                ("active_agent_update", active_agent_share),
            )
            if share >= 0.30
        ),
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


def test_measured_dynamic_potential_benchmark_is_potential_only(
    monkeypatch: pytest.MonkeyPatch,
):
    road_csr, link_state = make_measured_routing_fixture()

    def fail_candidate_generation(**_kwargs):
        raise AssertionError("potential-only benchmark must not build route candidates")

    monkeypatch.setattr(
        benchmark_module,
        "create_route_candidate_set",
        fail_candidate_generation,
    )

    result = run_measured_dynamic_potential_benchmark(
        road_csr,
        link_state,
        MeasuredDynamicPotentialBenchmarkConfig(
            workload_name="baseline-potential-only",
            num_steps=2,
            destination_node_id=4,
            routing_backend="baseline",
        ),
    )

    assert isinstance(result, MeasuredDynamicPotentialBenchmarkResult)
    assert result.name == "measured_dynamic_potential"
    assert result.routing_backend == "baseline"
    assert result.routing_backend_requested == "baseline"
    assert result.routing_backend_actual == "baseline"
    assert result.routing_backend_fallback is None
    assert result.routing_copy_boundary_note == "numpy baseline dynamic-potential only"
    assert result.node_count == 4
    assert result.link_count == 4
    assert result.destination_node_id == 4
    assert result.dynamic_potential_recompute_total == 2
    assert result.dynamic_potential_cache_hits_total == 0
    assert result.reachable_node_count == 4
    assert result.node_cost_fingerprint


def test_measured_dynamic_potential_benchmark_auto_fallback_records_metadata(
    monkeypatch: pytest.MonkeyPatch,
):
    from metroflow.routing import dynamic_potential

    road_csr, link_state = make_measured_routing_fixture()
    monkeypatch.setattr(dynamic_potential, "rust_routing_backend_available", lambda: False)

    result = run_measured_dynamic_potential_benchmark(
        road_csr,
        link_state,
        MeasuredDynamicPotentialBenchmarkConfig(
            workload_name="auto-potential-only",
            num_steps=1,
            destination_node_id=4,
            routing_backend="auto",
        ),
    )

    assert result.routing_backend == "auto"
    assert result.routing_backend_requested == "auto"
    assert result.routing_backend_actual == "baseline"
    assert result.routing_backend_fallback == "rust_cpu_unavailable"
    assert result.routing_copy_boundary_note == (
        "auto rust_cpu Vec copy boundary for dynamic-potential only when available"
    )


def test_measured_dynamic_potential_benchmark_explicit_rust_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
):
    from metroflow.routing import dynamic_potential

    road_csr, link_state = make_measured_routing_fixture()
    monkeypatch.setattr(dynamic_potential, "rust_routing_backend_available", lambda: True)

    def fail_rust(**_kwargs):
        raise RuntimeError("Rust CPU routing backend unavailable")

    monkeypatch.setattr(
        dynamic_potential,
        "compute_dynamic_potential_node_costs_rust",
        fail_rust,
    )

    with pytest.raises(RuntimeError, match="Rust CPU routing backend unavailable"):
        run_measured_dynamic_potential_benchmark(
            road_csr,
            link_state,
            MeasuredDynamicPotentialBenchmarkConfig(
                workload_name="rust-potential-only",
                num_steps=1,
                destination_node_id=4,
                routing_backend="rust_cpu",
            ),
        )


def test_measured_dynamic_potential_benchmark_rust_matches_baseline_when_available():
    from metroflow.backends.rust_cpu import rust_routing_backend_available

    if not rust_routing_backend_available():
        pytest.skip("_metroflow_rust extension is not importable")

    road_csr, link_state = make_measured_routing_fixture()
    baseline = run_measured_dynamic_potential_benchmark(
        road_csr,
        link_state,
        MeasuredDynamicPotentialBenchmarkConfig(
            workload_name="baseline-potential-only",
            num_steps=1,
            destination_node_id=4,
            routing_backend="baseline",
        ),
    )
    accelerated = run_measured_dynamic_potential_benchmark(
        road_csr,
        link_state,
        MeasuredDynamicPotentialBenchmarkConfig(
            workload_name="rust-potential-only",
            num_steps=1,
            destination_node_id=4,
            routing_backend="rust_cpu",
        ),
    )

    assert accelerated.routing_backend_actual == "rust_cpu"
    assert accelerated.node_cost_fingerprint == baseline.node_cost_fingerprint
    assert accelerated.reachable_node_count == baseline.reachable_node_count


def test_measured_dynamic_potential_benchmark_generated_od_rust_parity_when_available():
    from metroflow.backends.rust_cpu import rust_routing_backend_available
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.init import build_initial_simulation_state

    if not rust_routing_backend_available():
        pytest.skip("_metroflow_rust extension is not importable")

    bundle = build_initial_simulation_state(
        config=SimulationConfig(population_target=512),
        scenario_seed=44,
        eager_trip_generation=True,
    )
    state = bundle.state
    road_csr = state.static.routing_static["road_csr"]
    link_state = state.dynamic.flow_link_state
    trip = state.dynamic.demand_state["trip_requests"][0]
    pois_by_id = {int(poi.poi_id): poi for poi in state.static.pois}
    destination_node_id = int(pois_by_id[int(trip.dest_poi_id)].node_id)
    baseline = run_measured_dynamic_potential_benchmark(
        road_csr,
        link_state,
        MeasuredDynamicPotentialBenchmarkConfig(
            workload_name="generated-od-baseline-potential-only",
            num_steps=1,
            destination_node_id=destination_node_id,
            routing_backend="baseline",
        ),
    )
    accelerated = run_measured_dynamic_potential_benchmark(
        road_csr,
        link_state,
        MeasuredDynamicPotentialBenchmarkConfig(
            workload_name="generated-od-rust-potential-only",
            num_steps=1,
            destination_node_id=destination_node_id,
            routing_backend="rust_cpu",
        ),
    )

    assert accelerated.routing_backend_actual == "rust_cpu"
    assert accelerated.node_count == baseline.node_count
    assert accelerated.link_count == baseline.link_count
    assert accelerated.destination_node_id == baseline.destination_node_id
    assert accelerated.node_cost_fingerprint == baseline.node_cost_fingerprint


def test_route_candidate_set_records_internal_refresh_timing_breakdown():
    from metroflow.routing.candidates import create_route_candidate_set

    road_csr, link_state = make_measured_routing_fixture()
    stats: dict[str, object] = {}

    candidate_set = create_route_candidate_set(
        road_csr=road_csr,
        link_state=link_state,
        od_key=(1, 4),
        origin_node_id=1,
        destination_node_id=4,
        current_tick=0,
        max_candidates=2,
        max_hops=4,
        routing_backend="baseline",
        potential_cache={},
        stats=stats,
    )

    assert candidate_set.candidate_paths
    assert stats["route_candidate_refresh_total"] == 1
    assert float(stats["route_candidate_potential_seconds_total"]) >= 0.0
    assert float(stats["route_candidate_path_build_seconds_total"]) >= 0.0
    assert float(stats["route_candidate_metadata_seconds_total"]) >= 0.0


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
    expected_note = (
        "rust_cpu Vec copy boundary for dynamic-potential, next-link scoring, "
        "greedy path, ranked-K candidates, candidate metadata, candidate selection, "
        "and reroute decision"
    )
    assert result.routing_copy_boundary_note == expected_note
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
            agent_backend="rust_cpu",
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
    assert result.agent_backend == "rust_cpu"
    assert result.route_path_size_gamma == 2.0
    expected_note = (
        "rust_cpu Vec copy boundary for dynamic-potential, next-link scoring, "
        "greedy path, ranked-K candidates, candidate metadata, candidate selection, "
        "and reroute decision"
    )
    assert result.routing_copy_boundary_note == expected_note
    assert result.agent_copy_boundary_note == "rust_cpu Vec copy boundary for active-agent action planning"
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
        metrics["active_agent_update_wall_ns"] = 33
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
    assert result.active_agent_update_wall_ns == 33


def test_measured_runtime_benchmark_reports_stage_shares_and_gpu_candidates(
    monkeypatch: pytest.MonkeyPatch,
):
    from metroflow.sim.init import build_initial_simulation_state

    bundle = build_initial_simulation_state(scenario_seed=5, eager_trip_generation=False)
    timestamps = iter((1_000, 2_000))

    def fake_perf_counter_ns() -> int:
        return next(timestamps)

    def fake_simulation_step(state, _control, key):
        metrics = dict(state.dynamic.metrics_state)
        metrics.update(
            {
                "flow_update_wall_ns_total": 400,
                "route_candidate_refresh_seconds_total": 0.00000035,
                "dynamic_potential_recompute_seconds_total": 0.0000002,
                "routing_compile_seconds_estimate_total": 0.00000005,
                "reroute_decision_wall_ns_total": 299,
                "active_agent_update_wall_ns_total": 100,
            }
        )
        return (
            state.with_clock(tick_index=state.tick_index + 1).with_dynamic_updates(
                metrics_state=metrics
            ),
            None,
            None,
            key,
        )

    monkeypatch.setattr(benchmark_module, "perf_counter_ns", fake_perf_counter_ns)
    monkeypatch.setattr(benchmark_module, "simulation_step", fake_simulation_step)

    result = run_measured_runtime_spine_benchmark(
        bundle.state,
        bundle.rng_key,
        MeasuredRuntimeBenchmarkConfig(workload_name="runtime-stage-shares", num_steps=1),
    )

    assert result.wall_clock_ns == 1000
    assert result.gpu_candidate_threshold == 0.30
    assert result.gpu_candidate_min_seed_count == 3
    assert result.gpu_candidate_stage_names == (
        "flow_update",
        "route_candidate_refresh",
    )
    runtime_stage_timing = benchmark_module.RuntimeStageTiming
    assert result.runtime_stage_timings[:2] == (
        runtime_stage_timing(
            stage_name="flow_update",
            wall_clock_ns=400,
            wall_time_share=0.4,
            gpu_candidate=True,
        ),
        runtime_stage_timing(
            stage_name="route_candidate_refresh",
            wall_clock_ns=350,
            wall_time_share=0.35,
            gpu_candidate=True,
        ),
    )
    assert result.runtime_stage_timings[4].stage_name == "reroute_decision"
    assert result.runtime_stage_timings[4].wall_clock_ns == 299
    assert result.runtime_stage_timings[4].gpu_candidate is False


def test_measured_runtime_benchmark_reports_nested_route_and_agent_stage_shares(
    monkeypatch: pytest.MonkeyPatch,
):
    from metroflow.sim.init import build_initial_simulation_state

    bundle = build_initial_simulation_state(scenario_seed=6, eager_trip_generation=False)
    timestamps = iter((10_000, 11_000))

    def fake_perf_counter_ns() -> int:
        return next(timestamps)

    def fake_simulation_step(state, _control, key):
        metrics = dict(state.dynamic.metrics_state)
        metrics.update(
            {
                "route_candidate_refresh_seconds_total": 0.00000055,
                "route_candidate_potential_seconds_total": 0.00000035,
                "route_candidate_path_build_seconds_total": 0.00000031,
                "route_candidate_metadata_seconds_total": 0.00000008,
                "dynamic_potential_recompute_seconds_total": 0.00000030,
                "active_agent_update_wall_ns_total": 450,
                "active_agent_allocation_wall_ns_total": 80,
                "active_agent_candidate_selection_wall_ns_total": 310,
                "active_agent_pool_write_wall_ns_total": 90,
                "active_agent_pool_array_write_wall_ns_total": 70,
                "active_agent_plugin_memory_write_wall_ns_total": 320,
                "active_agent_movement_wall_ns_total": 330,
            }
        )
        return (
            state.with_clock(tick_index=state.tick_index + 1).with_dynamic_updates(
                metrics_state=metrics
            ),
            None,
            None,
            key,
        )

    monkeypatch.setattr(benchmark_module, "perf_counter_ns", fake_perf_counter_ns)
    monkeypatch.setattr(benchmark_module, "simulation_step", fake_simulation_step)

    result = run_measured_runtime_spine_benchmark(
        bundle.state,
        bundle.rng_key,
        MeasuredRuntimeBenchmarkConfig(
            workload_name="runtime-nested-stage-shares",
            num_steps=1,
        ),
    )
    timings = {item.stage_name: item for item in result.runtime_stage_timings}

    assert result.route_candidate_potential_seconds_total == 0.00000035
    assert result.route_candidate_path_build_seconds_total == 0.00000031
    assert result.route_candidate_metadata_seconds_total == 0.00000008
    assert result.active_agent_allocation_wall_ns_total == 80
    assert result.active_agent_candidate_selection_wall_ns_total == 310
    assert result.active_agent_pool_write_wall_ns_total == 90
    assert result.active_agent_pool_array_write_wall_ns_total == 70
    assert result.active_agent_plugin_memory_write_wall_ns_total == 320
    assert result.active_agent_movement_wall_ns_total == 330
    assert timings["route_candidate_potential"].wall_clock_ns == 350
    assert timings["route_candidate_path_build"].gpu_candidate is True
    assert timings["active_agent_candidate_selection"].gpu_candidate is True
    assert timings["active_agent_pool_write"].wall_clock_ns == 90
    assert timings["active_agent_pool_array_write"].wall_clock_ns == 70
    assert timings["active_agent_plugin_memory_write"].wall_clock_ns == 320
    assert timings["active_agent_plugin_memory_write"].gpu_candidate is True
    assert timings["active_agent_movement"].wall_clock_ns == 330
    assert "route_candidate_path_build" in result.gpu_candidate_stage_names
    assert "active_agent_candidate_selection" in result.gpu_candidate_stage_names
    assert "active_agent_plugin_memory_write" in result.gpu_candidate_stage_names
    assert "active_agent_movement" in result.gpu_candidate_stage_names


def test_runtime_stage_timing_markdown_reports_gpu_candidate_gate() -> None:
    runtime_stage_timing = benchmark_module.RuntimeStageTiming
    result = MeasuredRuntimeBenchmarkResult(
        name="measured_runtime_spine",
        workload_name="runtime-stage-shares",
        wall_clock_ns=1000,
        num_steps=1,
        initial_tick=0,
        final_tick=1,
        active_agent_count=0,
        flow_backend="baseline",
        routing_backend="baseline",
        agent_backend="baseline",
        route_path_size_gamma=0.0,
        routing_copy_boundary_note="numpy baseline",
        agent_copy_boundary_note="python baseline",
        route_candidate_refresh_total=0,
        route_candidate_reuse_total=0,
        dynamic_potential_recompute_total=0,
        dynamic_potential_cache_hits_total=0,
        runtime_stage_timings=(
            runtime_stage_timing("flow_update", 400, 0.4, True),
            runtime_stage_timing("active_agent_update", 100, 0.1, False),
        ),
        gpu_candidate_stage_names=("flow_update",),
    )

    markdown = benchmark_module.format_runtime_stage_timing_markdown(result)

    assert "GPU candidate stages: flow_update" in markdown
    assert "threshold: 0.3" in markdown
    assert "minimum deterministic seeds: 3" in markdown
    assert "flow_update: 400 ns (share 0.4)" in markdown


def test_runtime_gpu_candidate_gate_requires_stage_candidate_in_all_seed_runs() -> None:
    report = benchmark_module.summarize_runtime_gpu_candidate_gate(
        (
            make_runtime_stage_result(seed=11, flow_share=0.35, active_agent_share=0.40),
            make_runtime_stage_result(seed=12, flow_share=0.31, active_agent_share=0.20),
            make_runtime_stage_result(seed=13, flow_share=0.45, active_agent_share=0.50),
        )
    )

    assert report.workload_name == "runtime-stage-gate"
    assert report.deterministic_run_count == 3
    assert report.unique_seed_count == 3
    assert report.seeds == (11, 12, 13)
    assert report.gpu_review_eligible_stage_names == ("flow_update",)

    summaries = {item.stage_name: item for item in report.stage_summaries}
    assert summaries["flow_update"].candidate_run_count == 3
    assert summaries["flow_update"].gpu_review_eligible is True
    assert summaries["flow_update"].min_wall_time_share == 0.31
    assert summaries["active_agent_update"].candidate_run_count == 2
    assert summaries["active_agent_update"].gpu_review_eligible is False
    assert summaries["dynamic_potential_recompute"].candidate_run_count == 0
    assert summaries["dynamic_potential_recompute"].gpu_review_eligible is False


def test_runtime_gpu_candidate_gate_requires_minimum_seed_count() -> None:
    report = benchmark_module.summarize_runtime_gpu_candidate_gate(
        (
            make_runtime_stage_result(seed=21, flow_share=0.40, active_agent_share=0.40),
            make_runtime_stage_result(seed=22, flow_share=0.50, active_agent_share=0.45),
        )
    )

    assert report.deterministic_run_count == 2
    assert report.unique_seed_count == 2
    assert report.gpu_review_eligible_stage_names == ()
    assert all(not item.gpu_review_eligible for item in report.stage_summaries)


def test_runtime_gpu_candidate_gate_requires_unique_seed_count() -> None:
    report = benchmark_module.summarize_runtime_gpu_candidate_gate(
        (
            make_runtime_stage_result(seed=44, flow_share=0.40, active_agent_share=0.40),
            make_runtime_stage_result(seed=44, flow_share=0.50, active_agent_share=0.45),
            make_runtime_stage_result(seed=44, flow_share=0.60, active_agent_share=0.50),
        )
    )

    assert report.deterministic_run_count == 3
    assert report.unique_seed_count == 1
    assert report.gpu_review_eligible_stage_names == ()
    assert all(not item.gpu_review_eligible for item in report.stage_summaries)


def test_runtime_gpu_candidate_gate_markdown_reports_eligible_stage_names() -> None:
    report = benchmark_module.summarize_runtime_gpu_candidate_gate(
        (
            make_runtime_stage_result(seed=31, flow_share=0.35, active_agent_share=0.40),
            make_runtime_stage_result(seed=32, flow_share=0.31, active_agent_share=0.20),
            make_runtime_stage_result(seed=33, flow_share=0.45, active_agent_share=0.50),
        )
    )

    markdown = benchmark_module.format_runtime_gpu_candidate_gate_markdown(report)

    assert "Runtime GPU candidate gate" in markdown
    assert "Deterministic runs: 3" in markdown
    assert "Unique seeds: 3" in markdown
    assert "Eligible stages: flow_update" in markdown
    assert "active_agent_update: candidate runs 2/3" in markdown


def test_measured_runtime_benchmark_suite_runs_unique_seeds_and_reports_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.sim.init import SimulationInitBundle
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.state import SimulationState

    built_seeds: list[int] = []
    run_seeds: list[int] = []

    def fake_build_initial_simulation_state(*, scenario_seed: int, **_kwargs):
        seed = int(scenario_seed)
        built_seeds.append(seed)
        state = SimulationState(metadata={"scenario_seed": seed})
        return SimulationInitBundle(
            state=state,
            rng_key=key_from_seed(seed),
            city_topology=None,
            zoning=None,
            population=None,
            trip_requests=None,
        )

    def fake_runtime_benchmark(state, _rng_key, config):
        seed = int(state.metadata["scenario_seed"])
        run_seeds.append(seed)
        return make_runtime_stage_result(
            seed=seed,
            flow_share=0.35,
            active_agent_share=0.10,
        )

    monkeypatch.setattr(
        benchmark_module,
        "build_initial_simulation_state",
        fake_build_initial_simulation_state,
    )
    monkeypatch.setattr(
        benchmark_module,
        "run_measured_runtime_spine_benchmark",
        fake_runtime_benchmark,
    )

    result = run_measured_runtime_spine_benchmark_suite(
        MeasuredRuntimeBenchmarkSuiteConfig(
            workload_name="runtime-suite",
            seeds=(101, 102, 103),
            num_steps=2,
        )
    )

    assert isinstance(result, MeasuredRuntimeBenchmarkSuiteResult)
    assert built_seeds == [101, 102, 103]
    assert run_seeds == [101, 102, 103]
    assert result.name == "measured_runtime_spine_suite"
    assert result.workload_name == "runtime-suite"
    assert result.seed_count == 3
    assert result.seeds == (101, 102, 103)
    assert len(result.per_seed_results) == 3
    assert result.gpu_candidate_gate_report.gpu_review_eligible_stage_names == (
        "flow_update",
    )
    assert "Eligible stages: flow_update" in result.gpu_candidate_gate_markdown


def test_measured_runtime_benchmark_suite_rejects_duplicate_seeds() -> None:
    with pytest.raises(ValueError, match="seeds must be unique"):
        run_measured_runtime_spine_benchmark_suite(
            MeasuredRuntimeBenchmarkSuiteConfig(
                workload_name="runtime-suite",
                seeds=(101, 101, 102),
                num_steps=1,
            )
        )


def test_default_workload_matrix_covers_required_review_classes() -> None:
    from metroflow.metrics.benchmarks import default_runtime_workload_matrix

    matrix = default_runtime_workload_matrix(
        num_steps=2,
        eager_trip_generation=True,
    )
    entries = {entry.workload_class: entry for entry in matrix}

    assert tuple(entries) == (
        "eager_runtime_1_step",
        "eager_runtime_2_step",
        "generated_od_routing",
        "dense_flow_turn_batch",
        "route_candidate_k_gt_1_scoring",
        "active_agent_dense_pool",
    )
    assert entries["eager_runtime_1_step"].enabled is True
    assert entries["eager_runtime_2_step"].enabled is True
    assert entries["generated_od_routing"].stage_group == "route_candidate_refresh"
    assert entries["dense_flow_turn_batch"].hardware_lanes == (
        "numpy_simd",
        "rust_cpu",
        "jax_gpu_optional",
    )
    assert entries["route_candidate_k_gt_1_scoring"].parameters["max_candidates_min"] == 2
    assert entries["active_agent_dense_pool"].stage_group == "active_agent_update"


def test_workload_matrix_separates_measured_coverage_from_required_probes() -> None:
    from metroflow.metrics.benchmarks import default_runtime_workload_matrix

    matrix = default_runtime_workload_matrix(
        num_steps=2,
        eager_trip_generation=False,
    )
    entries = {entry.workload_class: entry for entry in matrix}

    assert entries["eager_runtime_1_step"].enabled is True
    assert entries["eager_runtime_1_step"].coverage_state == "measured_in_suite"
    assert entries["eager_runtime_2_step"].coverage_state == "measured_in_suite"
    assert entries["generated_od_routing"].enabled is False
    assert entries["generated_od_routing"].coverage_state == "requires_eager_runtime_suite"
    assert entries["dense_flow_turn_batch"].enabled is False
    assert entries["dense_flow_turn_batch"].coverage_state == "requires_dedicated_probe"
    assert entries["route_candidate_k_gt_1_scoring"].enabled is False
    assert entries["route_candidate_k_gt_1_scoring"].coverage_state == (
        "requires_dedicated_probe"
    )
    assert entries["active_agent_dense_pool"].enabled is False
    assert entries["active_agent_dense_pool"].coverage_state == "requires_dedicated_probe"


def test_workload_matrix_builder_does_not_import_accelerator_modules() -> None:
    accelerator_prefixes = ("jax", "torch", "_metroflow_rust")
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in accelerator_prefixes)
    }
    for module_name in tuple(saved_modules):
        sys.modules.pop(module_name, None)
    try:
        from metroflow.metrics.benchmarks import default_runtime_workload_matrix

        default_runtime_workload_matrix(num_steps=1, eager_trip_generation=False)

        assert "jax" not in sys.modules
        assert "torch" not in sys.modules
        assert "_metroflow_rust" not in sys.modules
    finally:
        for module_name in tuple(sys.modules):
            if any(
                module_name == prefix or module_name.startswith(f"{prefix}.")
                for prefix in accelerator_prefixes
            ):
                sys.modules.pop(module_name, None)
        sys.modules.update(saved_modules)


def test_runtime_suite_result_serializes_workload_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.benchmarks.reporting import runtime_benchmark_suite_to_dict
    from metroflow.sim.init import SimulationInitBundle
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.state import SimulationState

    def fake_build_initial_simulation_state(*, scenario_seed: int, **_kwargs):
        seed = int(scenario_seed)
        state = SimulationState(metadata={"scenario_seed": seed})
        return SimulationInitBundle(
            state=state,
            rng_key=key_from_seed(seed),
            city_topology=None,
            zoning=None,
            population=None,
            trip_requests=None,
        )

    def fake_runtime_benchmark(state, _rng_key, config):
        return make_runtime_stage_result(
            seed=int(state.metadata["scenario_seed"]),
            flow_share=0.10,
            active_agent_share=0.10,
        )

    monkeypatch.setattr(
        benchmark_module,
        "build_initial_simulation_state",
        fake_build_initial_simulation_state,
    )
    monkeypatch.setattr(
        benchmark_module,
        "run_measured_runtime_spine_benchmark",
        fake_runtime_benchmark,
    )

    result = run_measured_runtime_spine_benchmark_suite(
        MeasuredRuntimeBenchmarkSuiteConfig(
            workload_name="matrix-suite",
            seeds=(201, 202, 203),
            num_steps=2,
            eager_trip_generation=True,
        )
    )
    payload = runtime_benchmark_suite_to_dict(result)

    assert result.workload_matrix[0].workload_class == "eager_runtime_1_step"
    assert payload["workload_matrix"][0]["workload_class"] == "eager_runtime_1_step"
    assert payload["workload_matrix"][1]["enabled"] is True
    assert payload["workload_matrix"][2]["enabled"] is False
    assert payload["workload_matrix"][2]["coverage_state"] == "configured_not_observed"
    assert payload["workload_matrix"][4]["parameters"]["max_candidates_min"] == 2


def test_runtime_suite_marks_generated_od_routing_measured_only_when_observed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.benchmarks.reporting import runtime_benchmark_suite_to_dict
    from metroflow.sim.init import SimulationInitBundle
    from metroflow.sim.rng import key_from_seed
    from metroflow.sim.state import SimulationState

    def fake_build_initial_simulation_state(*, scenario_seed: int, **_kwargs):
        seed = int(scenario_seed)
        state = SimulationState(metadata={"scenario_seed": seed})
        return SimulationInitBundle(
            state=state,
            rng_key=key_from_seed(seed),
            city_topology=None,
            zoning=None,
            population=None,
            trip_requests=None,
        )

    def fake_runtime_benchmark(state, _rng_key, config):
        seed = int(state.metadata["scenario_seed"])
        return replace(
            make_runtime_stage_result(
                seed=seed,
                flow_share=0.10,
                active_agent_share=0.10,
            ),
            route_candidate_refresh_total=1 if seed == 301 else 0,
        )

    monkeypatch.setattr(
        benchmark_module,
        "build_initial_simulation_state",
        fake_build_initial_simulation_state,
    )
    monkeypatch.setattr(
        benchmark_module,
        "run_measured_runtime_spine_benchmark",
        fake_runtime_benchmark,
    )

    result = run_measured_runtime_spine_benchmark_suite(
        MeasuredRuntimeBenchmarkSuiteConfig(
            workload_name="observed-matrix-suite",
            seeds=(301, 302, 303),
            num_steps=2,
            eager_trip_generation=True,
        )
    )
    payload = runtime_benchmark_suite_to_dict(result)
    generated_od_entry = payload["workload_matrix"][2]

    assert generated_od_entry["workload_class"] == "generated_od_routing"
    assert generated_od_entry["enabled"] is True
    assert generated_od_entry["coverage_state"] == "measured_in_suite"
    assert generated_od_entry["parameters"]["observed_run_count"] == 1
    assert generated_od_entry["parameters"]["route_candidate_refresh_total"] == 1


def test_runtime_suite_artifact_manifest_preserves_workload_matrix(tmp_path) -> None:
    from metroflow.benchmarks.run import write_runtime_benchmark_suite_artifact_bundle

    workload_matrix = [
        {
            "workload_class": "route_candidate_k_gt_1_scoring",
            "label": "Route candidate K>1 scoring",
            "stage_group": "route_candidate_metadata",
            "hardware_lanes": ["numpy_simd", "jax_gpu_optional", "nn_surrogate"],
            "enabled": True,
            "coverage_state": "measured_in_probe",
            "parameters": {"max_candidates_min": 2},
            "decision_state": "diagnostic",
        }
    ]
    paths = write_runtime_benchmark_suite_artifact_bundle(
        {
            "report": "- Runtime benchmark suite:\n- Workload: matrix-bundle",
            "report_data": {
                "name": "measured_runtime_spine_suite",
                "workload_name": "matrix-bundle",
                "seeds": [1, 2, 3],
                "seed_count": 3,
                "num_steps": 2,
                "wall_clock_ns_total": 3000,
                "per_seed_results": [],
                "gpu_candidate_gate_report": {
                    "gpu_review_eligible_stage_names": [],
                    "stage_summaries": [],
                },
                "workload_matrix": workload_matrix,
            },
        },
        output_prefix=tmp_path / "matrix-bundle",
    )

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))

    assert manifest["workload_classes"] == ["route_candidate_k_gt_1_scoring"]
    assert manifest["workload_matrix"] == workload_matrix
