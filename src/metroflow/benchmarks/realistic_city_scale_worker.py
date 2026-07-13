"""Isolated worker implementation for realistic city scale measurements."""

from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from time import perf_counter_ns
from typing import Any, Callable, Iterator
from unittest.mock import patch

from metroflow.metrics.benchmarks import (
    MeasuredRuntimeBenchmarkConfig,
    run_measured_runtime_spine_benchmark,
)
from metroflow.sim.config import CityGenerationConfig, SimulationConfig
from metroflow.sim.control import SimulationControl
from metroflow.sim.step import simulation_step

from .realistic_city_scale import (
    _REALISTIC_STAGE_TARGETS,
    CityScaleRunResult,
    CityScaleWorkerSpec,
)

__all__ = [
    "run_realistic_city_scale_subprocess",
    "run_realistic_city_scale_worker",
]


def run_realistic_city_scale_worker(spec: CityScaleWorkerSpec) -> CityScaleRunResult:
    """Execute one worker measurement in the current process."""

    import metroflow.sim.init as init_module

    sim_config = SimulationConfig(
        population_target=spec.population_target,
        random_seed=spec.seed,
        ui_stream_enabled=False,
        eager_trip_generation=spec.eager_trip_generation,
        edge_backend="baseline",
        flow_backend="baseline",
        routing_backend="baseline",
        agent_backend="baseline",
        traffic_model="point_queue_v1",
    )
    city_config = CityGenerationConfig(
        topology_mode=spec.topology_mode,
        morphology_style_id=spec.morphology_style_id,
        zone_poi_coupling_mode=(
            "block_based_v1"
            if spec.topology_mode == "realistic_synthetic_v1"
            else "legacy"
        ),
    )
    city_stage_totals: dict[str, int] = {}
    capture_substages = spec.operation == "city_stage_profile"
    with _capture_city_stage_timings(
        init_module=init_module,
        topology_mode=spec.topology_mode,
        totals=city_stage_totals,
        capture_substages=capture_substages,
    ):
        if spec.operation in {"city_authority", "city_stage_profile"}:
            city_authority = init_module._build_initial_city_authority(
                sim_config=sim_config,
                city_config=city_config,
                scenario_seed=spec.seed,
            )
            bundle = None
            initialization_wall_ns = 0
        else:
            init_start_ns = perf_counter_ns()
            bundle = init_module.build_initial_simulation_state(
                config=sim_config,
                scenario_seed=spec.seed,
                city_config=city_config,
                eager_trip_generation=spec.eager_trip_generation,
            )
            initialization_wall_ns = perf_counter_ns() - init_start_ns
            city_authority = None
        boundary_peak_rss_kib = max(
            0,
            int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        )

    runtime_stage_wall_ns: tuple[tuple[str, int], ...] = ()
    if spec.operation == "fixed_steps":
        if bundle is None:
            raise AssertionError("fixed-step worker requires initialized bundle")
        benchmark = run_measured_runtime_spine_benchmark(
            bundle.state,
            bundle.rng_key,
            MeasuredRuntimeBenchmarkConfig(
                workload_name="realistic_city_scale",
                num_steps=spec.requested_steps,
            ),
        )
        runtime_wall_ns = benchmark.wall_clock_ns
        ticks_completed = benchmark.final_tick - benchmark.initial_tick
        runtime_stage_wall_ns = tuple(
            (item.stage_name, int(item.wall_clock_ns))
            for item in benchmark.runtime_stage_timings
        )
    elif spec.operation == "time_budget":
        if bundle is None:
            raise AssertionError("time-budget worker requires initialized bundle")
        state = bundle.state
        rng_key = bundle.rng_key
        control = SimulationControl()
        ticks_completed = 0
        runtime_start_ns = perf_counter_ns()
        deadline_ns = runtime_start_ns + spec.tick_budget_ns
        while perf_counter_ns() < deadline_ns:
            state, _telemetry, _snapshot, rng_key = simulation_step(
                state,
                control,
                rng_key,
            )
            if perf_counter_ns() <= deadline_ns:
                ticks_completed += 1
        runtime_wall_ns = perf_counter_ns() - runtime_start_ns
    else:
        runtime_wall_ns = 0
        ticks_completed = 0

    if bundle is not None:
        topology = bundle.city_topology
        generated = bundle.generated_city_map
        road_csr = bundle.state.static.routing_static["road_csr"]
        zoning = bundle.zoning
        citizen_count = len(bundle.population.citizens)
        trip_request_count = len(bundle.trip_requests.trip_requests)
    else:
        if city_authority is None:
            raise AssertionError("city worker requires city authority")
        topology = city_authority.topology
        generated = city_authority.generated_city_map
        road_csr = city_authority.road_csr
        zoning = city_authority.zoning
        citizen_count = 0
        trip_request_count = 0
    city_fingerprint = (
        generated.fingerprint
        if generated is not None
        else str(
            topology.metadata.get(
                "generated_city_map_fingerprint",
                topology.metadata.get("road_geometry_fingerprint", ""),
            )
        )
    )
    if not city_fingerprint and topology.road_geometry is not None:
        city_fingerprint = topology.road_geometry.fingerprint
    scenario_id = (
        "synthetic_100k" if spec.population_target >= 100_000 else "synthetic_smoke"
    )
    return CityScaleRunResult(
        topology_mode=spec.topology_mode,
        population_target=spec.population_target,
        seed=spec.seed,
        scenario_id=scenario_id,
        morphology_style_id=str(topology.metadata.get("style_id", "")),
        operation=spec.operation,
        eager_trip_generation=spec.eager_trip_generation,
        requested_steps=spec.requested_steps if spec.operation == "fixed_steps" else 0,
        tick_budget_ns=spec.tick_budget_ns if spec.operation == "time_budget" else 0,
        ticks_completed=ticks_completed,
        worker_pid=os.getpid(),
        city_authority_wall_ns=int(city_stage_totals["city_authority"]),
        initialization_wall_ns=max(0, int(initialization_wall_ns)),
        runtime_wall_ns=max(0, int(runtime_wall_ns)),
        peak_rss_kib=boundary_peak_rss_kib,
        process_peak_rss_kib=max(
            0,
            int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        ),
        node_count=int(road_csr.node_count),
        link_count=int(road_csr.link_count),
        turn_count=len(topology.turns),
        block_count=(len(generated.blueprint.blocks.blocks) if generated is not None else 0),
        zone_count=len(zoning.zones),
        citizen_count=citizen_count,
        trip_request_count=trip_request_count,
        active_agent_capacity=sim_config.active_agent_capacity,
        city_stage_wall_ns=tuple(
            (name, int(city_stage_totals[name]))
            for name, _target in _REALISTIC_STAGE_TARGETS
            if name in city_stage_totals
        ),
        runtime_stage_wall_ns=runtime_stage_wall_ns,
        city_fingerprint=city_fingerprint,
    )


def run_realistic_city_scale_subprocess(
    spec: CityScaleWorkerSpec,
    *,
    timeout_seconds: float = 900.0,
) -> CityScaleRunResult:
    """Run one scale workload in an isolated interpreter."""

    env = dict(os.environ)
    env.update(
        {
            "PYTHONHASHSEED": str(spec.seed),
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "metroflow.benchmarks.realistic_city_scale",
            "--worker-json",
            json.dumps(spec.as_dict(), sort_keys=True, separators=(",", ":")),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=float(timeout_seconds),
        env=env,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            "realistic city scale worker failed "
            f"for mode={spec.topology_mode}, population={spec.population_target}, "
            f"seed={spec.seed}, operation={spec.operation}: {detail}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("realistic city scale worker returned invalid JSON") from exc
    return CityScaleRunResult.from_dict(payload)


@contextmanager
def _capture_city_stage_timings(
    *,
    init_module: Any,
    topology_mode: str,
    totals: dict[str, int],
    capture_substages: bool,
) -> Iterator[None]:
    original_city_authority = init_module._build_initial_city_authority

    def timed_city_authority(*args: object, **kwargs: object) -> object:
        start_ns = perf_counter_ns()
        try:
            return original_city_authority(*args, **kwargs)
        finally:
            totals["city_authority"] = totals.get("city_authority", 0) + (
                perf_counter_ns() - start_ns
            )

    with ExitStack() as stack:
        stack.enter_context(
            patch.object(
                init_module,
                "_build_initial_city_authority",
                timed_city_authority,
            )
        )
        if capture_substages and topology_mode == "realistic_synthetic_v1":
            import metroflow.city.realistic_city as realistic_module

            for stage_name, target_name in _REALISTIC_STAGE_TARGETS:
                original = getattr(realistic_module, target_name)
                stack.enter_context(
                    patch.object(
                        realistic_module,
                        target_name,
                        _timed_callable(stage_name, original, totals),
                    )
                )
        yield


def _timed_callable(
    stage_name: str,
    function: Callable[..., object],
    totals: dict[str, int],
) -> Callable[..., object]:
    def timed(*args: object, **kwargs: object) -> object:
        start_ns = perf_counter_ns()
        try:
            return function(*args, **kwargs)
        finally:
            totals[stage_name] = totals.get(stage_name, 0) + (
                perf_counter_ns() - start_ns
            )

    return timed
