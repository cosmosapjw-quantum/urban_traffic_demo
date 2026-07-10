from dataclasses import dataclass, field, replace
import hashlib
from time import perf_counter_ns
from typing import Literal, Mapping

import numpy as np

from metroflow.backends.jax_flow import JaxFlowUnavailableError, run_dense_flow_jax
from metroflow.benchmarks.dense_flow_workload import (
    build_dense_flow_jax_inputs,
    build_dense_flow_scale_state as _build_dense_flow_scale_state,
    fingerprint_flow_output as _fingerprint_flow_output,
    flow_output_arrays as _flow_output_arrays,
    max_abs_flow_output_diff as _max_abs_flow_output_diff,
    run_flow_update_steps as _run_flow_update_steps,
)
from metroflow.core.contracts import TickSchedule
from metroflow.core.state import WorldState
from metroflow.flow.engine import FlowUpdateBackend, update_link_node_flow
from metroflow.flow.state import LinkState, NodeState
from metroflow.city.graph import RoadNetworkCSR
from metroflow.routing.dynamic_potential import RoutingBackend, compute_dynamic_potential_state
from metroflow.routing.candidates import create_route_candidate_set
from metroflow.routing.reroute_policy import (
    compute_reroute_decision_core,
    rust_reroute_backend_available,
)
from metroflow.traffic.meso import EdgeEvolutionBackend
from metroflow.sim.control import SimulationControl
from metroflow.sim.config import SimulationConfig
from metroflow.sim.init import build_initial_simulation_state
from metroflow.sim.rng import PRNGKeyArray
from metroflow.sim.replay import ReplayInputSignatureRecord
from metroflow.sim.orchestrator import step_world
from metroflow.sim.routing_runtime import _select_candidate_route
from metroflow.sim.state import SimulationState
from metroflow.sim.step import simulation_step

DenseFlowScaleProbeBackend = Literal["baseline", "rust_cpu", "jax_optional"]
RouteScoreProbeBackend = Literal["baseline", "jax_optional"]


@dataclass(frozen=True)
class BenchmarkResult:
    name: str
    step_proxy_score: float
    state_proxy_score: float
    note: str = ""
    signature: str = ""


@dataclass(frozen=True)
class MeasuredBenchmarkConfig:
    workload_name: str
    num_steps: int
    schedule: TickSchedule = TickSchedule()
    edge_backend: EdgeEvolutionBackend = "baseline"
    edge_inflow_veh_per_tick: tuple[float, ...] | None = None
    edge_outflow_veh_per_tick: tuple[float, ...] | None = None
    edge_free_flow_time_ticks: tuple[float, ...] | None = None
    edge_capacity_veh_per_tick: tuple[float, ...] | None = None
    zonal_travel_times: tuple[tuple[float, ...], ...] | None = None
    zone_opportunities: tuple[float, ...] | None = None


@dataclass(frozen=True)
class MeasuredFlowBenchmarkConfig:
    workload_name: str
    num_steps: int
    flow_backend: FlowUpdateBackend = "baseline"
    validate: bool = False


@dataclass(frozen=True)
class MeasuredDenseFlowScaleBenchmarkConfig:
    workload_name: str
    num_steps: int
    link_count: int
    turns_per_link: int
    probe_backend: DenseFlowScaleProbeBackend = "baseline"
    seed: int = 0


@dataclass(frozen=True)
class MeasuredRoutingBenchmarkConfig:
    workload_name: str
    num_steps: int
    origin_node_id: int
    destination_node_id: int
    routing_backend: RoutingBackend = "baseline"
    incoming_link_id: int | None = None
    max_hops: int = 64
    max_candidates: int = 1


@dataclass(frozen=True)
class MeasuredRouteScoringBatchBenchmarkConfig:
    workload_name: str
    num_steps: int
    origin_node_id: int
    destination_node_id: int
    max_candidates: int = 2
    max_hops: int = 64
    path_size_gamma: float = 0.0
    routing_backend: RoutingBackend = "baseline"
    reroute_backend: RoutingBackend = "baseline"
    reroute_batch_size: int = 32
    score_probe_backend: RouteScoreProbeBackend = "baseline"


@dataclass(frozen=True)
class MeasuredDynamicPotentialBenchmarkConfig:
    workload_name: str
    num_steps: int
    destination_node_id: int
    routing_backend: RoutingBackend = "baseline"


@dataclass(frozen=True)
class MeasuredRuntimeBenchmarkConfig:
    workload_name: str
    num_steps: int
    control: SimulationControl = field(default_factory=SimulationControl)


@dataclass(frozen=True)
class BenchmarkWorkloadMatrixEntry:
    workload_class: str
    label: str
    stage_group: str
    hardware_lanes: tuple[str, ...]
    enabled: bool
    coverage_state: str = "diagnostic_metadata"
    parameters: dict[str, object] = field(default_factory=dict)
    decision_state: str = "diagnostic"

    def __post_init__(self) -> None:
        workload_class = str(self.workload_class).strip()
        if not workload_class:
            raise ValueError("workload_class must be non-empty.")
        label = str(self.label).strip()
        if not label:
            raise ValueError("label must be non-empty.")
        stage_group = str(self.stage_group).strip()
        if not stage_group:
            raise ValueError("stage_group must be non-empty.")
        object.__setattr__(self, "workload_class", workload_class)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "stage_group", stage_group)
        object.__setattr__(
            self,
            "hardware_lanes",
            tuple(str(lane) for lane in self.hardware_lanes),
        )
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "coverage_state", str(self.coverage_state))
        object.__setattr__(
            self,
            "parameters",
            {str(key): value for key, value in dict(self.parameters).items()},
        )
        object.__setattr__(self, "decision_state", str(self.decision_state))


@dataclass(frozen=True)
class MeasuredRuntimeBenchmarkSuiteConfig:
    workload_name: str
    seeds: tuple[int, ...]
    num_steps: int
    control: SimulationControl = field(default_factory=SimulationControl)
    simulation_config: SimulationConfig | None = None
    eager_trip_generation: bool = False
    workload_matrix: tuple[BenchmarkWorkloadMatrixEntry, ...] | None = None


@dataclass(frozen=True)
class MeasuredBenchmarkResult:
    name: str
    workload_name: str
    wall_clock_ns: int
    seed: int
    num_steps: int
    initial_traffic_step: int
    final_traffic_step: int
    schedule: TickSchedule
    edge_count: int
    zone_count: int
    edge_backend: EdgeEvolutionBackend


@dataclass(frozen=True)
class MeasuredFlowBenchmarkResult:
    name: str
    workload_name: str
    wall_clock_ns: int
    num_steps: int
    link_count: int
    turn_count: int
    flow_backend: FlowUpdateBackend
    copy_boundary_note: str


@dataclass(frozen=True)
class MeasuredDenseFlowScaleBenchmarkResult:
    name: str
    workload_name: str
    wall_clock_ns: int
    baseline_wall_clock_ns: int
    probe_wall_clock_ns: int
    jax_first_call_wall_ns: int
    jax_steady_state_wall_ns: int
    jax_input_copy_wall_ns: int
    jax_output_copy_wall_ns: int
    num_steps: int
    link_count: int
    turn_count: int
    turns_per_link: int
    probe_backend: str
    probe_backend_actual: str
    probe_backend_fallback: str | None
    copy_boundary_note: str
    jax_available: bool
    baseline_output_fingerprint: str
    probe_output_fingerprint: str
    output_max_abs_diff_vs_baseline: float


@dataclass(frozen=True)
class MeasuredRoutingBenchmarkResult:
    name: str
    workload_name: str
    wall_clock_ns: int
    num_steps: int
    link_count: int
    turn_count: int
    origin_node_id: int
    destination_node_id: int
    candidate_path: tuple[int, ...]
    candidate_path_length: int
    candidate_paths: tuple[tuple[int, ...], ...]
    candidate_count: int
    candidate_path_costs: tuple[float, ...]
    candidate_path_size_factors: tuple[float, ...]
    candidate_generation_mode: str
    candidate_enumeration_backend: str
    routing_backend: RoutingBackend
    routing_backend_requested: str
    routing_backend_actual: str
    routing_backend_fallback: str | None
    routing_copy_boundary_note: str
    dynamic_potential_recompute_total: int
    dynamic_potential_cache_hits_total: int
    dynamic_potential_cache_pruned_total: int = 0
    dynamic_potential_cache_entry_count: int = 0
    route_candidate_refresh_seconds_total: float = 0.0
    dynamic_potential_recompute_seconds_total: float = 0.0


@dataclass(frozen=True)
class MeasuredRouteScoringBatchBenchmarkResult:
    name: str
    workload_name: str
    wall_clock_ns: int
    num_steps: int
    link_count: int
    turn_count: int
    origin_node_id: int
    destination_node_id: int
    max_candidates: int
    path_size_gamma: float
    candidate_paths: tuple[tuple[int, ...], ...]
    candidate_count: int
    candidate_path_costs: tuple[float, ...]
    candidate_path_size_factors: tuple[float, ...]
    selected_candidate_index: int
    selected_candidate_id: int
    selected_candidate_utility: float
    selection_backend: str
    candidate_generation_mode: str
    candidate_enumeration_backend: str
    candidate_metadata_backend: str
    routing_backend: RoutingBackend
    routing_backend_requested: str
    routing_backend_actual: str
    routing_backend_fallback: str | None
    reroute_backend: RoutingBackend
    reroute_backend_actual: str
    reroute_backend_fallback: str | None
    score_probe_backend: str
    score_probe_backend_actual: str
    score_probe_backend_fallback: str | None
    routing_copy_boundary_note: str
    route_score_batch_shape: tuple[int, ...]
    reroute_score_batch_shape: tuple[int, ...]
    route_score_fingerprint: str
    score_probe_fingerprint: str
    score_probe_max_abs_diff_vs_baseline: float
    reroute_score_fingerprint: str
    reroute_decision_count: int
    route_candidate_refresh_seconds_total: float
    route_candidate_path_build_seconds_total: float
    route_candidate_metadata_seconds_total: float
    dynamic_potential_recompute_seconds_total: float
    route_score_wall_ns_total: int
    reroute_score_wall_ns_total: int
    score_probe_wall_ns_total: int
    jax_score_available: bool
    jax_score_first_call_wall_ns: int
    jax_score_steady_state_wall_ns: int


@dataclass(frozen=True)
class MeasuredDynamicPotentialBenchmarkResult:
    name: str
    workload_name: str
    wall_clock_ns: int
    num_steps: int
    node_count: int
    link_count: int
    destination_node_id: int
    destination_node_index: int
    routing_backend: RoutingBackend
    routing_backend_requested: str
    routing_backend_actual: str
    routing_backend_fallback: str | None
    routing_copy_boundary_note: str
    dynamic_potential_recompute_total: int
    dynamic_potential_cache_hits_total: int
    dynamic_potential_recompute_seconds_total: float
    node_cost_fingerprint: str
    reachable_node_count: int


@dataclass(frozen=True)
class RuntimeStageTiming:
    stage_name: str
    wall_clock_ns: int
    wall_time_share: float
    gpu_candidate: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage_name", str(self.stage_name))
        object.__setattr__(self, "wall_clock_ns", int(self.wall_clock_ns))
        object.__setattr__(self, "wall_time_share", float(self.wall_time_share))
        object.__setattr__(self, "gpu_candidate", bool(self.gpu_candidate))


@dataclass(frozen=True)
class MeasuredRuntimeBenchmarkResult:
    name: str
    workload_name: str
    wall_clock_ns: int
    num_steps: int
    initial_tick: int
    final_tick: int
    active_agent_count: int
    flow_backend: str
    routing_backend: str
    agent_backend: str
    route_path_size_gamma: float
    routing_copy_boundary_note: str
    agent_copy_boundary_note: str
    route_candidate_refresh_total: int
    route_candidate_reuse_total: int
    dynamic_potential_recompute_total: int
    dynamic_potential_cache_hits_total: int
    dynamic_potential_cache_pruned_total: int = 0
    dynamic_potential_cache_entry_count: int = 0
    seed: int | None = None
    route_candidate_refresh_seconds_total: float = 0.0
    route_candidate_potential_seconds_total: float = 0.0
    route_candidate_path_build_seconds_total: float = 0.0
    route_candidate_metadata_seconds_total: float = 0.0
    dynamic_potential_recompute_seconds_total: float = 0.0
    routing_compile_seconds_estimate_total: float = 0.0
    flow_update_wall_ns_total: int = 0
    active_agent_update_wall_ns_total: int = 0
    reroute_decision_wall_ns_total: int = 0
    active_agent_allocation_wall_ns_total: int = 0
    active_agent_candidate_selection_wall_ns_total: int = 0
    active_agent_pool_write_wall_ns_total: int = 0
    active_agent_pool_array_write_wall_ns_total: int = 0
    active_agent_plugin_memory_write_wall_ns_total: int = 0
    active_agent_movement_wall_ns_total: int = 0
    runtime_stage_timings: tuple[RuntimeStageTiming, ...] = ()
    gpu_candidate_stage_names: tuple[str, ...] = ()
    gpu_candidate_threshold: float = 0.30
    gpu_candidate_min_seed_count: int = 3
    reroute_decisions_total: int = 0
    persistence_decisions_total: int = 0
    active_agent_sink_wait_total: int = 0
    active_agent_sink_wait_this_tick: int = 0
    active_agent_update_wall_ns: int = 0
    active_agent_rerouted_this_tick: int = 0
    active_agent_reroute_cooldown_this_tick: int = 0


@dataclass(frozen=True)
class MeasuredRuntimeBenchmarkSuiteResult:
    name: str
    workload_name: str
    seed_count: int
    seeds: tuple[int, ...]
    num_steps: int
    wall_clock_ns_total: int
    per_seed_results: tuple[MeasuredRuntimeBenchmarkResult, ...]
    gpu_candidate_gate_report: "RuntimeGpuCandidateGateReport"
    gpu_candidate_gate_markdown: str
    workload_matrix: tuple[BenchmarkWorkloadMatrixEntry, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "workload_name", str(self.workload_name))
        object.__setattr__(self, "seed_count", int(self.seed_count))
        object.__setattr__(self, "seeds", tuple(int(seed) for seed in self.seeds))
        object.__setattr__(self, "num_steps", int(self.num_steps))
        object.__setattr__(self, "wall_clock_ns_total", int(self.wall_clock_ns_total))
        object.__setattr__(self, "per_seed_results", tuple(self.per_seed_results))
        object.__setattr__(
            self,
            "gpu_candidate_gate_markdown",
            str(self.gpu_candidate_gate_markdown),
        )
        object.__setattr__(
            self,
            "workload_matrix",
            tuple(_normalize_workload_matrix_entry(item) for item in self.workload_matrix),
        )


@dataclass(frozen=True)
class RuntimeStageGateSummary:
    stage_name: str
    deterministic_run_count: int
    candidate_run_count: int
    min_wall_time_share: float
    mean_wall_time_share: float
    max_wall_time_share: float
    max_wall_clock_ns: int
    gpu_review_eligible: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage_name", str(self.stage_name))
        object.__setattr__(
            self,
            "deterministic_run_count",
            int(self.deterministic_run_count),
        )
        object.__setattr__(self, "candidate_run_count", int(self.candidate_run_count))
        object.__setattr__(self, "min_wall_time_share", float(self.min_wall_time_share))
        object.__setattr__(self, "mean_wall_time_share", float(self.mean_wall_time_share))
        object.__setattr__(self, "max_wall_time_share", float(self.max_wall_time_share))
        object.__setattr__(self, "max_wall_clock_ns", int(self.max_wall_clock_ns))
        object.__setattr__(self, "gpu_review_eligible", bool(self.gpu_review_eligible))


@dataclass(frozen=True)
class RuntimeGpuCandidateGateReport:
    workload_name: str
    deterministic_run_count: int
    unique_seed_count: int
    seeds: tuple[int, ...]
    gpu_candidate_threshold: float
    gpu_candidate_min_seed_count: int
    gpu_review_eligible_stage_names: tuple[str, ...]
    stage_summaries: tuple[RuntimeStageGateSummary, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "workload_name", str(self.workload_name))
        object.__setattr__(
            self,
            "deterministic_run_count",
            int(self.deterministic_run_count),
        )
        object.__setattr__(self, "unique_seed_count", int(self.unique_seed_count))
        object.__setattr__(self, "seeds", tuple(int(seed) for seed in self.seeds))
        object.__setattr__(
            self,
            "gpu_candidate_threshold",
            float(self.gpu_candidate_threshold),
        )
        object.__setattr__(
            self,
            "gpu_candidate_min_seed_count",
            int(self.gpu_candidate_min_seed_count),
        )
        object.__setattr__(
            self,
            "gpu_review_eligible_stage_names",
            tuple(str(name) for name in self.gpu_review_eligible_stage_names),
        )
        object.__setattr__(self, "stage_summaries", tuple(self.stage_summaries))


def record_input_signature_smoke_benchmark(
    record: ReplayInputSignatureRecord,
    *,
    step_proxy_score: float,
    state_proxy_score: float,
) -> BenchmarkResult:
    return BenchmarkResult(
        name="input-signature-smoke",
        step_proxy_score=step_proxy_score,
        state_proxy_score=state_proxy_score,
        note=f"seed={record.seed} steps={record.num_steps}",
        signature=record.input_fingerprint,
    )


def run_city_smoke_benchmark(*, population: int, edge_count: int, zone_count: int) -> BenchmarkResult:
    if population <= 0 or edge_count <= 0 or zone_count <= 0:
        raise ValueError("population, edge_count, and zone_count must be positive.")
    step_proxy_score = round((population / 10_000.0) + (edge_count / 5_000.0), 3)
    state_proxy_score = round((population / 2_000.0) + (zone_count / 10.0), 3)
    return BenchmarkResult(
        name="city100k-smoke",
        step_proxy_score=step_proxy_score,
        state_proxy_score=state_proxy_score,
        note=f"population={population} edges={edge_count} zones={zone_count}",
        signature=f"{population}:{edge_count}:{zone_count}",
    )


def default_runtime_workload_matrix(
    *,
    num_steps: int,
    eager_trip_generation: bool,
) -> tuple[BenchmarkWorkloadMatrixEntry, ...]:
    """Return diagnostic workload-class coverage for runtime acceleration review."""

    steps = max(0, int(num_steps))
    eager = bool(eager_trip_generation)
    return (
        BenchmarkWorkloadMatrixEntry(
            workload_class="eager_runtime_1_step",
            label="Eager runtime 1-step",
            stage_group="runtime_spine",
            hardware_lanes=("python_orchestration", "numpy_authority"),
            enabled=steps >= 1,
            coverage_state="measured_in_suite" if steps >= 1 else "not_measured",
            parameters={
                "steps": min(steps, 1),
                "eager_trip_generation": eager,
            },
        ),
        BenchmarkWorkloadMatrixEntry(
            workload_class="eager_runtime_2_step",
            label="Eager runtime 2-step",
            stage_group="runtime_spine",
            hardware_lanes=("python_orchestration", "numpy_authority"),
            enabled=steps >= 2,
            coverage_state="measured_in_suite" if steps >= 2 else "not_measured",
            parameters={
                "steps": min(steps, 2),
                "eager_trip_generation": eager,
            },
        ),
        BenchmarkWorkloadMatrixEntry(
            workload_class="generated_od_routing",
            label="Generated OD routing",
            stage_group="route_candidate_refresh",
            hardware_lanes=("python_orchestration", "rust_cpu", "nn_surrogate"),
            enabled=False,
            coverage_state=(
                "configured_not_observed" if eager else "requires_eager_runtime_suite"
            ),
            parameters={
                "generated_city": True,
                "routing_backend_default": "baseline",
                "eager_trip_generation": eager,
            },
        ),
        BenchmarkWorkloadMatrixEntry(
            workload_class="dense_flow_turn_batch",
            label="Dense flow/turn batch",
            stage_group="flow_update",
            hardware_lanes=("numpy_simd", "rust_cpu", "jax_gpu_optional"),
            enabled=False,
            coverage_state="requires_dedicated_probe",
            parameters={
                "requires_dedicated_probe": True,
            },
        ),
        BenchmarkWorkloadMatrixEntry(
            workload_class="route_candidate_k_gt_1_scoring",
            label="Route candidate K>1 scoring",
            stage_group="route_candidate_metadata",
            hardware_lanes=("numpy_simd", "jax_gpu_optional", "nn_surrogate"),
            enabled=False,
            coverage_state="requires_dedicated_probe",
            parameters={
                "max_candidates_min": 2,
                "requires_dedicated_probe": True,
            },
        ),
        BenchmarkWorkloadMatrixEntry(
            workload_class="active_agent_dense_pool",
            label="Active-agent dense pool",
            stage_group="active_agent_update",
            hardware_lanes=("python_orchestration", "rust_cpu"),
            enabled=False,
            coverage_state="requires_dedicated_probe",
            parameters={
                "eager_trip_generation": eager,
                "requires_dense_pool_probe": True,
            },
        ),
    )


def run_measured_flow_update_benchmark(
    link_state: LinkState,
    node_state: NodeState,
    config: MeasuredFlowBenchmarkConfig,
) -> MeasuredFlowBenchmarkResult:
    workload_name = config.workload_name.strip()
    if not workload_name:
        raise ValueError("workload_name must be non-empty.")
    if config.num_steps <= 0:
        raise ValueError("num_steps must be positive.")

    current_link_state = link_state
    current_node_state = node_state
    start_ns = perf_counter_ns()
    for _ in range(config.num_steps):
        update_result = update_link_node_flow(
            current_link_state,
            current_node_state,
            validate=config.validate,
            flow_backend=config.flow_backend,
        )
        current_link_state = update_result.link_state
        current_node_state = update_result.node_state
    elapsed_ns = perf_counter_ns() - start_ns

    return MeasuredFlowBenchmarkResult(
        name="measured_flow_update",
        workload_name=workload_name,
        wall_clock_ns=max(elapsed_ns, 0),
        num_steps=config.num_steps,
        link_count=link_state.link_count,
        turn_count=node_state.turn_count,
        flow_backend=config.flow_backend,
        copy_boundary_note=_flow_copy_boundary_note(config.flow_backend),
    )


def run_measured_dense_flow_scale_benchmark(
    config: MeasuredDenseFlowScaleBenchmarkConfig,
) -> MeasuredDenseFlowScaleBenchmarkResult:
    workload_name = config.workload_name.strip()
    if not workload_name:
        raise ValueError("workload_name must be non-empty.")
    if config.num_steps <= 0:
        raise ValueError("num_steps must be positive.")
    if config.link_count < 2:
        raise ValueError("link_count must be >= 2.")
    if config.turns_per_link < 1:
        raise ValueError("turns_per_link must be >= 1.")
    if config.probe_backend not in {"baseline", "rust_cpu", "jax_optional"}:
        raise ValueError("probe_backend must be one of: baseline, rust_cpu, jax_optional.")
    if config.probe_backend == "jax_optional" and config.num_steps < 2:
        raise ValueError("jax_optional requires num_steps >= 2.")

    link_state, node_state = _build_dense_flow_scale_state(
        link_count=int(config.link_count),
        turns_per_link=int(config.turns_per_link),
        seed=int(config.seed),
    )
    baseline_link, baseline_node, baseline_ns = _run_flow_update_steps(
        link_state,
        node_state,
        num_steps=int(config.num_steps),
        flow_backend="baseline",
    )
    baseline_output = _flow_output_arrays(baseline_link, baseline_node)
    baseline_fingerprint = _fingerprint_flow_output(baseline_output)

    probe_backend_actual = str(config.probe_backend)
    probe_backend_fallback: str | None = None
    probe_ns = baseline_ns
    jax_first_call_ns = 0
    jax_steady_state_ns = 0
    jax_input_copy_ns = 0
    jax_output_copy_ns = 0
    jax_available = False
    if config.probe_backend == "baseline":
        probe_output = baseline_output
        probe_backend_actual = "baseline"
    elif config.probe_backend == "rust_cpu":
        probe_link, probe_node, probe_ns = _run_flow_update_steps(
            link_state,
            node_state,
            num_steps=int(config.num_steps),
            flow_backend="rust_cpu",
        )
        probe_output = _flow_output_arrays(probe_link, probe_node)
    else:
        (
            probe_output,
            probe_ns,
            jax_first_call_ns,
            jax_steady_state_ns,
            jax_input_copy_ns,
            jax_output_copy_ns,
            jax_available,
            probe_backend_actual,
            probe_backend_fallback,
        ) = _run_dense_flow_jax_optional_probe(
            link_state,
            node_state,
            num_steps=int(config.num_steps),
            fallback_output=baseline_output,
        )

    return MeasuredDenseFlowScaleBenchmarkResult(
        name="measured_dense_flow_scale",
        workload_name=workload_name,
        wall_clock_ns=int(probe_ns),
        baseline_wall_clock_ns=int(baseline_ns),
        probe_wall_clock_ns=int(probe_ns),
        jax_first_call_wall_ns=int(jax_first_call_ns),
        jax_steady_state_wall_ns=int(jax_steady_state_ns),
        jax_input_copy_wall_ns=int(jax_input_copy_ns),
        jax_output_copy_wall_ns=int(jax_output_copy_ns),
        num_steps=int(config.num_steps),
        link_count=int(config.link_count),
        turn_count=int(config.link_count) * int(config.turns_per_link),
        turns_per_link=int(config.turns_per_link),
        probe_backend=str(config.probe_backend),
        probe_backend_actual=probe_backend_actual,
        probe_backend_fallback=probe_backend_fallback,
        copy_boundary_note=_dense_flow_probe_copy_boundary_note(config.probe_backend),
        jax_available=bool(jax_available),
        baseline_output_fingerprint=baseline_fingerprint,
        probe_output_fingerprint=_fingerprint_flow_output(probe_output),
        output_max_abs_diff_vs_baseline=_max_abs_flow_output_diff(
            baseline_output,
            probe_output,
        ),
    )


def run_measured_dynamic_potential_benchmark(
    road_csr: RoadNetworkCSR,
    link_state: LinkState,
    config: MeasuredDynamicPotentialBenchmarkConfig,
) -> MeasuredDynamicPotentialBenchmarkResult:
    workload_name = config.workload_name.strip()
    if not workload_name:
        raise ValueError("workload_name must be non-empty.")
    if config.num_steps <= 0:
        raise ValueError("num_steps must be positive.")
    if link_state.link_count != road_csr.link_count:
        raise ValueError("link_state.link_count must match road_csr.link_count.")

    potential_state = None
    routing_backend_requested = str(config.routing_backend)
    routing_backend_actual = str(config.routing_backend)
    routing_backend_fallback: str | None = None
    stats: dict[str, object] = {}
    start_ns = perf_counter_ns()
    for _ in range(config.num_steps):
        potential_state = compute_dynamic_potential_state(
            road_csr,
            destination_node_id=int(config.destination_node_id),
            link_state=link_state,
            routing_backend=config.routing_backend,
            stats=stats,
        )
        metadata = potential_state.metadata
        routing_backend_requested = str(
            metadata.get("routing_backend_requested", config.routing_backend)
        )
        routing_backend_actual = str(metadata.get("routing_backend", config.routing_backend))
        fallback = metadata.get("routing_backend_fallback")
        routing_backend_fallback = None if fallback is None else str(fallback)
    elapsed_ns = perf_counter_ns() - start_ns
    if potential_state is None:
        raise RuntimeError("dynamic potential benchmark did not execute")

    node_cost = np.ascontiguousarray(potential_state.node_cost_to_go, dtype=np.float32)
    return MeasuredDynamicPotentialBenchmarkResult(
        name="measured_dynamic_potential",
        workload_name=workload_name,
        wall_clock_ns=max(elapsed_ns, 0),
        num_steps=config.num_steps,
        node_count=road_csr.node_count,
        link_count=road_csr.link_count,
        destination_node_id=int(config.destination_node_id),
        destination_node_index=int(potential_state.destination_node_index),
        routing_backend=config.routing_backend,
        routing_backend_requested=routing_backend_requested,
        routing_backend_actual=routing_backend_actual,
        routing_backend_fallback=routing_backend_fallback,
        routing_copy_boundary_note=_dynamic_potential_copy_boundary_note(
            config.routing_backend
        ),
        dynamic_potential_recompute_total=int(
            stats.get("dynamic_potential_recompute_total", 0)
        ),
        dynamic_potential_cache_hits_total=int(
            stats.get("dynamic_potential_cache_hits_total", 0)
        ),
        dynamic_potential_recompute_seconds_total=float(
            stats.get("dynamic_potential_recompute_seconds_total", 0.0)
        ),
        node_cost_fingerprint=hashlib.sha256(node_cost.tobytes()).hexdigest(),
        reachable_node_count=int(np.count_nonzero(node_cost < 1e12)),
    )


def run_measured_routing_candidate_benchmark(
    road_csr: RoadNetworkCSR,
    link_state: LinkState,
    config: MeasuredRoutingBenchmarkConfig,
) -> MeasuredRoutingBenchmarkResult:
    workload_name = config.workload_name.strip()
    if not workload_name:
        raise ValueError("workload_name must be non-empty.")
    if config.num_steps <= 0:
        raise ValueError("num_steps must be positive.")
    if config.max_hops < 1:
        raise ValueError("max_hops must be >= 1.")
    if config.max_candidates < 1:
        raise ValueError("max_candidates must be >= 1.")
    if link_state.link_count != road_csr.link_count:
        raise ValueError("link_state.link_count must match road_csr.link_count.")

    candidate_path: tuple[int, ...] = ()
    candidate_paths: tuple[tuple[int, ...], ...] = ()
    candidate_path_costs: tuple[float, ...] = ()
    candidate_path_size_factors: tuple[float, ...] = ()
    candidate_generation_mode = "baseline_greedy_single"
    candidate_enumeration_backend = "backend_greedy_route_candidate"
    routing_backend_requested = str(config.routing_backend)
    routing_backend_actual = str(config.routing_backend)
    routing_backend_fallback: str | None = None
    stats: dict[str, object] = {}
    start_ns = perf_counter_ns()
    for _ in range(config.num_steps):
        candidate_set = create_route_candidate_set(
            road_csr=road_csr,
            link_state=link_state,
            od_key=(int(config.origin_node_id), int(config.destination_node_id)),
            origin_node_id=config.origin_node_id,
            destination_node_id=config.destination_node_id,
            current_tick=0,
            incoming_link_id=config.incoming_link_id,
            max_candidates=config.max_candidates,
            max_hops=config.max_hops,
            routing_backend=config.routing_backend,
            stats=stats,
        )
        candidate_paths = candidate_set.candidate_paths
        candidate_path = candidate_paths[0] if candidate_paths else ()
        metadata = candidate_set.metadata
        candidate_path_costs = tuple(
            float(item) for item in tuple(metadata.get("candidate_path_costs", ()) or ())
        )
        candidate_path_size_factors = tuple(
            float(item) for item in tuple(metadata.get("candidate_path_size_factors", ()) or ())
        )
        candidate_generation_mode = str(
            metadata.get("candidate_generation_mode", candidate_generation_mode)
        )
        candidate_enumeration_backend = str(
            metadata.get("candidate_enumeration_backend", candidate_enumeration_backend)
        )
        routing_backend_requested = str(
            metadata.get("routing_backend_requested", config.routing_backend)
        )
        routing_backend_actual = str(metadata.get("routing_backend", config.routing_backend))
        fallback = metadata.get("routing_backend_fallback")
        routing_backend_fallback = None if fallback is None else str(fallback)
    elapsed_ns = perf_counter_ns() - start_ns

    return MeasuredRoutingBenchmarkResult(
        name="measured_routing_candidate",
        workload_name=workload_name,
        wall_clock_ns=max(elapsed_ns, 0),
        num_steps=config.num_steps,
        link_count=road_csr.link_count,
        turn_count=road_csr.turn_count,
        origin_node_id=int(config.origin_node_id),
        destination_node_id=int(config.destination_node_id),
        candidate_path=tuple(int(link_id) for link_id in candidate_path),
        candidate_path_length=len(candidate_path),
        candidate_paths=tuple(tuple(int(link_id) for link_id in path) for path in candidate_paths),
        candidate_count=len(candidate_paths),
        candidate_path_costs=candidate_path_costs,
        candidate_path_size_factors=candidate_path_size_factors,
        candidate_generation_mode=candidate_generation_mode,
        candidate_enumeration_backend=candidate_enumeration_backend,
        routing_backend=config.routing_backend,
        routing_backend_requested=routing_backend_requested,
        routing_backend_actual=routing_backend_actual,
        routing_backend_fallback=routing_backend_fallback,
        routing_copy_boundary_note=_routing_copy_boundary_note(config.routing_backend),
        dynamic_potential_recompute_total=int(
            stats.get("dynamic_potential_recompute_total", 0)
        ),
        dynamic_potential_cache_hits_total=int(
            stats.get("dynamic_potential_cache_hits_total", 0)
        ),
        dynamic_potential_cache_pruned_total=int(
            stats.get("dynamic_potential_cache_pruned_total", 0)
        ),
        dynamic_potential_cache_entry_count=int(
            stats.get("dynamic_potential_cache_entry_count", 0)
        ),
        route_candidate_refresh_seconds_total=float(
            stats.get("route_candidate_refresh_seconds_total", 0.0)
        ),
        dynamic_potential_recompute_seconds_total=float(
            stats.get("dynamic_potential_recompute_seconds_total", 0.0)
        ),
    )


def run_measured_route_scoring_batch_benchmark(
    road_csr: RoadNetworkCSR,
    link_state: LinkState,
    config: MeasuredRouteScoringBatchBenchmarkConfig,
) -> MeasuredRouteScoringBatchBenchmarkResult:
    workload_name = config.workload_name.strip()
    if not workload_name:
        raise ValueError("workload_name must be non-empty.")
    if config.num_steps <= 0:
        raise ValueError("num_steps must be positive.")
    if config.max_candidates < 2:
        raise ValueError("max_candidates must be >= 2.")
    if config.max_hops < 1:
        raise ValueError("max_hops must be >= 1.")
    if config.reroute_batch_size < 1:
        raise ValueError("reroute_batch_size must be >= 1.")
    if config.score_probe_backend not in {"baseline", "jax_optional"}:
        raise ValueError("score_probe_backend must be one of: baseline, jax_optional.")
    if config.score_probe_backend == "jax_optional" and config.num_steps < 2:
        raise ValueError("jax_optional requires num_steps >= 2.")
    if link_state.link_count != road_csr.link_count:
        raise ValueError("link_state.link_count must match road_csr.link_count.")

    candidate_paths: tuple[tuple[int, ...], ...] = ()
    candidate_path_costs: tuple[float, ...] = ()
    candidate_path_size_factors: tuple[float, ...] = ()
    selected_candidate_index = -1
    selected_candidate_id = -1
    selected_candidate_utility = 0.0
    selection_backend = "none"
    candidate_generation_mode = "baseline_ranked_k"
    candidate_enumeration_backend = "python_host_ranked_k"
    candidate_metadata_backend = "python_host_candidate_metadata"
    routing_backend_requested = str(config.routing_backend)
    routing_backend_actual = str(config.routing_backend)
    routing_backend_fallback: str | None = None
    route_score_values = np.zeros((0,), dtype=np.float32)
    reroute_score_values = np.zeros((0,), dtype=np.float32)
    reroute_should = np.zeros((0,), dtype=np.bool_)
    reroute_backend_actual = str(config.reroute_backend)
    reroute_backend_fallback: str | None = None
    route_score_wall_ns_total = 0
    reroute_score_wall_ns_total = 0
    stats: dict[str, object] = {}
    reroute_inputs = _build_reroute_scoring_inputs(int(config.reroute_batch_size))
    start_ns = perf_counter_ns()
    for _ in range(int(config.num_steps)):
        candidate_set = create_route_candidate_set(
            road_csr=road_csr,
            link_state=link_state,
            od_key=(int(config.origin_node_id), int(config.destination_node_id)),
            origin_node_id=int(config.origin_node_id),
            destination_node_id=int(config.destination_node_id),
            current_tick=0,
            max_candidates=int(config.max_candidates),
            max_hops=int(config.max_hops),
            routing_backend=config.routing_backend,
            stats=stats,
        )
        candidate_paths = candidate_set.candidate_paths
        metadata = candidate_set.metadata
        candidate_path_costs = tuple(
            float(item) for item in tuple(metadata.get("candidate_path_costs", ()) or ())
        )
        candidate_path_size_factors = tuple(
            float(item) for item in tuple(metadata.get("candidate_path_size_factors", ()) or ())
        )
        candidate_generation_mode = str(
            metadata.get("candidate_generation_mode", candidate_generation_mode)
        )
        candidate_enumeration_backend = str(
            metadata.get("candidate_enumeration_backend", candidate_enumeration_backend)
        )
        candidate_metadata_backend = str(
            metadata.get("candidate_metadata_backend", candidate_metadata_backend)
        )
        routing_backend_requested = str(
            metadata.get("routing_backend_requested", config.routing_backend)
        )
        routing_backend_actual = str(metadata.get("routing_backend", config.routing_backend))
        fallback = metadata.get("routing_backend_fallback")
        routing_backend_fallback = None if fallback is None else str(fallback)

        route_score_start_ns = perf_counter_ns()
        route_score_values = _route_score_values(
            candidate_path_costs,
            candidate_path_size_factors,
            path_size_gamma=float(config.path_size_gamma),
        )
        selected = _select_candidate_route(
            candidate_set,
            path_size_gamma=float(config.path_size_gamma),
            routing_backend=config.routing_backend,
        )
        route_score_wall_ns_total += max(0, perf_counter_ns() - route_score_start_ns)
        if selected is None:
            selected_candidate_index = -1
            selected_candidate_id = -1
            selected_candidate_utility = 0.0
            selection_backend = "none"
        else:
            selected_candidate_index = int(selected.candidate_index)
            selected_candidate_id = int(selected.candidate_id)
            selected_candidate_utility = float(selected.utility)
            selection_backend = str(selected.selection_backend)

        (
            reroute_should,
            reroute_score_values,
            reroute_backend_actual,
            reroute_backend_fallback,
            reroute_ns,
        ) = _run_reroute_scoring_probe(
            reroute_inputs,
            routing_backend=config.reroute_backend,
        )
        reroute_score_wall_ns_total += int(reroute_ns)
    elapsed_ns = perf_counter_ns() - start_ns

    (
        score_probe_values,
        score_probe_ns,
        jax_first_ns,
        jax_steady_ns,
        jax_available,
        score_probe_backend_actual,
        score_probe_backend_fallback,
    ) = _run_route_score_probe_backend(
        route_score_values,
        candidate_path_costs,
        candidate_path_size_factors,
        path_size_gamma=float(config.path_size_gamma),
        num_steps=int(config.num_steps),
        score_probe_backend=config.score_probe_backend,
    )

    return MeasuredRouteScoringBatchBenchmarkResult(
        name="measured_route_scoring_batch",
        workload_name=workload_name,
        wall_clock_ns=max(elapsed_ns, 0) + int(score_probe_ns),
        num_steps=int(config.num_steps),
        link_count=road_csr.link_count,
        turn_count=road_csr.turn_count,
        origin_node_id=int(config.origin_node_id),
        destination_node_id=int(config.destination_node_id),
        max_candidates=int(config.max_candidates),
        path_size_gamma=float(config.path_size_gamma),
        candidate_paths=tuple(tuple(int(link_id) for link_id in path) for path in candidate_paths),
        candidate_count=len(candidate_paths),
        candidate_path_costs=candidate_path_costs,
        candidate_path_size_factors=candidate_path_size_factors,
        selected_candidate_index=selected_candidate_index,
        selected_candidate_id=selected_candidate_id,
        selected_candidate_utility=selected_candidate_utility,
        selection_backend=selection_backend,
        candidate_generation_mode=candidate_generation_mode,
        candidate_enumeration_backend=candidate_enumeration_backend,
        candidate_metadata_backend=candidate_metadata_backend,
        routing_backend=config.routing_backend,
        routing_backend_requested=routing_backend_requested,
        routing_backend_actual=routing_backend_actual,
        routing_backend_fallback=routing_backend_fallback,
        reroute_backend=config.reroute_backend,
        reroute_backend_actual=reroute_backend_actual,
        reroute_backend_fallback=reroute_backend_fallback,
        score_probe_backend=str(config.score_probe_backend),
        score_probe_backend_actual=score_probe_backend_actual,
        score_probe_backend_fallback=score_probe_backend_fallback,
        routing_copy_boundary_note=_routing_copy_boundary_note(config.routing_backend),
        route_score_batch_shape=tuple(int(x) for x in route_score_values.shape),
        reroute_score_batch_shape=tuple(int(x) for x in reroute_score_values.shape),
        route_score_fingerprint=_fingerprint_numeric_arrays(
            {"route_score_values": route_score_values}
        ),
        score_probe_fingerprint=_fingerprint_numeric_arrays(
            {"route_score_values": score_probe_values}
        ),
        score_probe_max_abs_diff_vs_baseline=_max_abs_float32_array_diff(
            route_score_values,
            score_probe_values,
        ),
        reroute_score_fingerprint=_fingerprint_numeric_arrays(
            {
                "reroute_should": reroute_should,
                "reroute_score_values": reroute_score_values,
            }
        ),
        reroute_decision_count=int(np.count_nonzero(reroute_should)),
        route_candidate_refresh_seconds_total=float(
            stats.get("route_candidate_refresh_seconds_total", 0.0)
        ),
        route_candidate_path_build_seconds_total=float(
            stats.get("route_candidate_path_build_seconds_total", 0.0)
        ),
        route_candidate_metadata_seconds_total=float(
            stats.get("route_candidate_metadata_seconds_total", 0.0)
        ),
        dynamic_potential_recompute_seconds_total=float(
            stats.get("dynamic_potential_recompute_seconds_total", 0.0)
        ),
        route_score_wall_ns_total=int(route_score_wall_ns_total),
        reroute_score_wall_ns_total=int(reroute_score_wall_ns_total),
        score_probe_wall_ns_total=int(score_probe_ns),
        jax_score_available=bool(jax_available),
        jax_score_first_call_wall_ns=int(jax_first_ns),
        jax_score_steady_state_wall_ns=int(jax_steady_ns),
    )


def run_measured_runtime_spine_benchmark(
    state: SimulationState,
    rng_key: PRNGKeyArray,
    config: MeasuredRuntimeBenchmarkConfig,
) -> MeasuredRuntimeBenchmarkResult:
    workload_name = config.workload_name.strip()
    if not workload_name:
        raise ValueError("workload_name must be non-empty.")
    if config.num_steps <= 0:
        raise ValueError("num_steps must be positive.")

    current_state = state
    current_key = rng_key
    start_ns = perf_counter_ns()
    for _ in range(config.num_steps):
        current_state, _telemetry, _snapshot, current_key = simulation_step(
            current_state,
            config.control,
            current_key,
        )
    elapsed_ns = perf_counter_ns() - start_ns

    metrics_state = (
        current_state.dynamic.metrics_state
        if isinstance(current_state.dynamic.metrics_state, dict)
        else {}
    )
    flow_update_wall_ns_total = _stage_ns_metric(
        metrics_state,
        total_key="flow_update_wall_ns_total",
        tick_key="flow_update_wall_ns",
    )
    active_agent_update_wall_ns_total = _stage_ns_metric(
        metrics_state,
        total_key="active_agent_update_wall_ns_total",
        tick_key="active_agent_update_wall_ns",
    )
    reroute_decision_wall_ns_total = _stage_ns_metric(
        metrics_state,
        total_key="reroute_decision_wall_ns_total",
        tick_key="reroute_decision_wall_ns",
    )
    active_agent_allocation_wall_ns_total = _stage_ns_metric(
        metrics_state,
        total_key="active_agent_allocation_wall_ns_total",
        tick_key="active_agent_allocation_wall_ns",
    )
    active_agent_candidate_selection_wall_ns_total = _stage_ns_metric(
        metrics_state,
        total_key="active_agent_candidate_selection_wall_ns_total",
        tick_key="active_agent_candidate_selection_wall_ns",
    )
    active_agent_pool_write_wall_ns_total = _stage_ns_metric(
        metrics_state,
        total_key="active_agent_pool_write_wall_ns_total",
        tick_key="active_agent_pool_write_wall_ns",
    )
    active_agent_pool_array_write_wall_ns_total = _stage_ns_metric(
        metrics_state,
        total_key="active_agent_pool_array_write_wall_ns_total",
        tick_key="active_agent_pool_array_write_wall_ns",
    )
    active_agent_plugin_memory_write_wall_ns_total = _stage_ns_metric(
        metrics_state,
        total_key="active_agent_plugin_memory_write_wall_ns_total",
        tick_key="active_agent_plugin_memory_write_wall_ns",
    )
    active_agent_movement_wall_ns_total = _stage_ns_metric(
        metrics_state,
        total_key="active_agent_movement_wall_ns_total",
        tick_key="active_agent_movement_wall_ns",
    )
    stage_timings = _runtime_stage_timing_breakdown(
        wall_clock_ns=max(elapsed_ns, 0),
        flow_update_wall_ns=flow_update_wall_ns_total,
        route_candidate_refresh_ns=_seconds_to_ns(
            metrics_state.get("route_candidate_refresh_seconds_total", 0.0)
        ),
        route_candidate_potential_ns=_seconds_to_ns(
            metrics_state.get("route_candidate_potential_seconds_total", 0.0)
        ),
        route_candidate_path_build_ns=_seconds_to_ns(
            metrics_state.get("route_candidate_path_build_seconds_total", 0.0)
        ),
        route_candidate_metadata_ns=_seconds_to_ns(
            metrics_state.get("route_candidate_metadata_seconds_total", 0.0)
        ),
        dynamic_potential_recompute_ns=_seconds_to_ns(
            metrics_state.get("dynamic_potential_recompute_seconds_total", 0.0)
        ),
        routing_compile_estimate_ns=_seconds_to_ns(
            metrics_state.get("routing_compile_seconds_estimate_total", 0.0)
        ),
        reroute_decision_wall_ns=reroute_decision_wall_ns_total,
        active_agent_update_wall_ns=active_agent_update_wall_ns_total,
        active_agent_allocation_wall_ns=active_agent_allocation_wall_ns_total,
        active_agent_candidate_selection_wall_ns=(
            active_agent_candidate_selection_wall_ns_total
        ),
        active_agent_pool_write_wall_ns=active_agent_pool_write_wall_ns_total,
        active_agent_pool_array_write_wall_ns=(
            active_agent_pool_array_write_wall_ns_total
        ),
        active_agent_plugin_memory_write_wall_ns=(
            active_agent_plugin_memory_write_wall_ns_total
        ),
        active_agent_movement_wall_ns=active_agent_movement_wall_ns_total,
    )
    return MeasuredRuntimeBenchmarkResult(
        name="measured_runtime_spine",
        workload_name=workload_name,
        wall_clock_ns=max(elapsed_ns, 0),
        num_steps=config.num_steps,
        initial_tick=state.tick_index,
        final_tick=current_state.tick_index,
        active_agent_count=int(getattr(current_state.dynamic.active_agent_pool, "alive_count", 0) or 0),
        flow_backend=current_state.config.flow_backend,
        routing_backend=current_state.config.routing_backend,
        agent_backend=current_state.config.agent_backend,
        route_path_size_gamma=float(current_state.config.route_path_size_gamma),
        routing_copy_boundary_note=_routing_copy_boundary_note(current_state.config.routing_backend),
        agent_copy_boundary_note=_agent_copy_boundary_note(current_state.config.agent_backend),
        route_candidate_refresh_total=int(metrics_state.get("route_candidate_refresh_total", 0)),
        route_candidate_reuse_total=int(metrics_state.get("route_candidate_reuse_total", 0)),
        dynamic_potential_recompute_total=int(
            metrics_state.get("dynamic_potential_recompute_total", 0)
        ),
        dynamic_potential_cache_hits_total=int(
            metrics_state.get("dynamic_potential_cache_hits_total", 0)
        ),
        dynamic_potential_cache_pruned_total=int(
            metrics_state.get("dynamic_potential_cache_pruned_total", 0)
        ),
        dynamic_potential_cache_entry_count=int(
            metrics_state.get("dynamic_potential_cache_entry_count", 0)
        ),
        seed=_runtime_state_seed(current_state),
        route_candidate_refresh_seconds_total=float(
            metrics_state.get("route_candidate_refresh_seconds_total", 0.0)
        ),
        route_candidate_potential_seconds_total=float(
            metrics_state.get("route_candidate_potential_seconds_total", 0.0)
        ),
        route_candidate_path_build_seconds_total=float(
            metrics_state.get("route_candidate_path_build_seconds_total", 0.0)
        ),
        route_candidate_metadata_seconds_total=float(
            metrics_state.get("route_candidate_metadata_seconds_total", 0.0)
        ),
        dynamic_potential_recompute_seconds_total=float(
            metrics_state.get("dynamic_potential_recompute_seconds_total", 0.0)
        ),
        routing_compile_seconds_estimate_total=float(
            metrics_state.get("routing_compile_seconds_estimate_total", 0.0)
        ),
        flow_update_wall_ns_total=flow_update_wall_ns_total,
        active_agent_update_wall_ns_total=active_agent_update_wall_ns_total,
        reroute_decision_wall_ns_total=reroute_decision_wall_ns_total,
        active_agent_allocation_wall_ns_total=active_agent_allocation_wall_ns_total,
        active_agent_candidate_selection_wall_ns_total=(
            active_agent_candidate_selection_wall_ns_total
        ),
        active_agent_pool_write_wall_ns_total=active_agent_pool_write_wall_ns_total,
        active_agent_pool_array_write_wall_ns_total=(
            active_agent_pool_array_write_wall_ns_total
        ),
        active_agent_plugin_memory_write_wall_ns_total=(
            active_agent_plugin_memory_write_wall_ns_total
        ),
        active_agent_movement_wall_ns_total=active_agent_movement_wall_ns_total,
        runtime_stage_timings=stage_timings,
        gpu_candidate_stage_names=tuple(
            item.stage_name for item in stage_timings if item.gpu_candidate
        ),
        reroute_decisions_total=int(metrics_state.get("us2_reroute_decisions_total", 0)),
        persistence_decisions_total=int(
            metrics_state.get("us2_persistence_decisions_total", 0)
        ),
        active_agent_sink_wait_total=int(
            metrics_state.get("active_agent_sink_wait_total", 0)
        ),
        active_agent_sink_wait_this_tick=int(
            metrics_state.get("active_agent_sink_wait_this_tick", 0)
        ),
        active_agent_update_wall_ns=int(
            metrics_state.get("active_agent_update_wall_ns", 0)
        ),
        active_agent_rerouted_this_tick=int(
            metrics_state.get("active_agent_rerouted_this_tick", 0)
        ),
        active_agent_reroute_cooldown_this_tick=int(
            metrics_state.get("active_agent_reroute_cooldown_this_tick", 0)
        ),
    )


def summarize_runtime_gpu_candidate_gate(
    results: tuple[MeasuredRuntimeBenchmarkResult, ...],
    *,
    gpu_candidate_threshold: float | None = None,
    gpu_candidate_min_seed_count: int | None = None,
) -> RuntimeGpuCandidateGateReport:
    result_tuple = tuple(results)
    if not result_tuple:
        raise ValueError("results must contain at least one runtime benchmark result.")
    workload_name = result_tuple[0].workload_name
    if any(result.workload_name != workload_name for result in result_tuple):
        raise ValueError("all runtime benchmark results must use the same workload_name.")

    threshold = (
        float(result_tuple[0].gpu_candidate_threshold)
        if gpu_candidate_threshold is None
        else float(gpu_candidate_threshold)
    )
    min_seed_count = (
        int(result_tuple[0].gpu_candidate_min_seed_count)
        if gpu_candidate_min_seed_count is None
        else int(gpu_candidate_min_seed_count)
    )
    if min_seed_count <= 0:
        raise ValueError("gpu_candidate_min_seed_count must be positive.")

    seeds = _unique_runtime_result_seeds(result_tuple)
    stage_order: list[str] = []
    timings_by_result: list[dict[str, RuntimeStageTiming]] = []
    for result in result_tuple:
        timing_map: dict[str, RuntimeStageTiming] = {}
        for item in result.runtime_stage_timings:
            timing_map[item.stage_name] = item
            if item.stage_name not in stage_order:
                stage_order.append(item.stage_name)
        timings_by_result.append(timing_map)

    run_count = len(result_tuple)
    stage_summaries: list[RuntimeStageGateSummary] = []
    for stage_name in stage_order:
        shares: list[float] = []
        wall_clock_ns: list[int] = []
        candidate_run_count = 0
        for timing_map in timings_by_result:
            timing = timing_map.get(stage_name)
            if timing is None:
                shares.append(0.0)
                wall_clock_ns.append(0)
                continue
            shares.append(max(0.0, float(timing.wall_time_share)))
            wall_clock_ns.append(max(0, int(timing.wall_clock_ns)))
            if timing.gpu_candidate:
                candidate_run_count += 1
        min_share = round(min(shares) if shares else 0.0, 6)
        mean_share = round((sum(shares) / run_count) if run_count else 0.0, 6)
        max_share = round(max(shares) if shares else 0.0, 6)
        eligible = (
            run_count >= min_seed_count
            and len(seeds) >= min_seed_count
            and candidate_run_count == run_count
            and min_share >= threshold
        )
        stage_summaries.append(
            RuntimeStageGateSummary(
                stage_name=stage_name,
                deterministic_run_count=run_count,
                candidate_run_count=candidate_run_count,
                min_wall_time_share=min_share,
                mean_wall_time_share=mean_share,
                max_wall_time_share=max_share,
                max_wall_clock_ns=max(wall_clock_ns) if wall_clock_ns else 0,
                gpu_review_eligible=eligible,
            )
        )

    return RuntimeGpuCandidateGateReport(
        workload_name=workload_name,
        deterministic_run_count=run_count,
        unique_seed_count=len(seeds),
        seeds=seeds,
        gpu_candidate_threshold=threshold,
        gpu_candidate_min_seed_count=min_seed_count,
        gpu_review_eligible_stage_names=tuple(
            item.stage_name for item in stage_summaries if item.gpu_review_eligible
        ),
        stage_summaries=tuple(stage_summaries),
    )


def run_measured_runtime_spine_benchmark_suite(
    config: MeasuredRuntimeBenchmarkSuiteConfig,
) -> MeasuredRuntimeBenchmarkSuiteResult:
    workload_name = config.workload_name.strip()
    if not workload_name:
        raise ValueError("workload_name must be non-empty.")
    if config.num_steps <= 0:
        raise ValueError("num_steps must be positive.")
    seeds = tuple(int(seed) for seed in config.seeds)
    if not seeds:
        raise ValueError("seeds must contain at least one seed.")
    if len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be unique for runtime benchmark suites.")
    workload_matrix = _resolve_runtime_workload_matrix(config)

    per_seed_results: list[MeasuredRuntimeBenchmarkResult] = []
    for seed in seeds:
        bundle = build_initial_simulation_state(
            config=config.simulation_config,
            scenario_seed=seed,
            eager_trip_generation=config.eager_trip_generation,
        )
        result = run_measured_runtime_spine_benchmark(
            bundle.state,
            bundle.rng_key,
            MeasuredRuntimeBenchmarkConfig(
                workload_name=workload_name,
                num_steps=config.num_steps,
                control=config.control,
            ),
        )
        per_seed_results.append(
            replace(
                result,
                workload_name=workload_name,
                seed=seed,
            )
        )

    result_tuple = tuple(per_seed_results)
    workload_matrix = _apply_runtime_workload_observations(workload_matrix, result_tuple)
    gate_report = summarize_runtime_gpu_candidate_gate(result_tuple)
    return MeasuredRuntimeBenchmarkSuiteResult(
        name="measured_runtime_spine_suite",
        workload_name=workload_name,
        seed_count=len(seeds),
        seeds=seeds,
        num_steps=int(config.num_steps),
        wall_clock_ns_total=sum(result.wall_clock_ns for result in result_tuple),
        per_seed_results=result_tuple,
        gpu_candidate_gate_report=gate_report,
        gpu_candidate_gate_markdown=format_runtime_gpu_candidate_gate_markdown(gate_report),
        workload_matrix=workload_matrix,
    )


def _resolve_runtime_workload_matrix(
    config: MeasuredRuntimeBenchmarkSuiteConfig,
) -> tuple[BenchmarkWorkloadMatrixEntry, ...]:
    if config.workload_matrix is None:
        return default_runtime_workload_matrix(
            num_steps=config.num_steps,
            eager_trip_generation=config.eager_trip_generation,
        )
    matrix = tuple(_normalize_workload_matrix_entry(item) for item in config.workload_matrix)
    if not matrix:
        raise ValueError("workload_matrix must contain at least one entry when provided.")
    return matrix


def _apply_runtime_workload_observations(
    matrix: tuple[BenchmarkWorkloadMatrixEntry, ...],
    results: tuple[MeasuredRuntimeBenchmarkResult, ...],
) -> tuple[BenchmarkWorkloadMatrixEntry, ...]:
    route_refresh_total = sum(
        max(0, int(result.route_candidate_refresh_total)) for result in results
    )
    route_observed_count = sum(
        1 for result in results if int(result.route_candidate_refresh_total) > 0
    )
    out: list[BenchmarkWorkloadMatrixEntry] = []
    for entry in matrix:
        if entry.workload_class != "generated_od_routing":
            out.append(entry)
            continue
        parameters = dict(entry.parameters)
        parameters["observed_run_count"] = int(route_observed_count)
        parameters["route_candidate_refresh_total"] = int(route_refresh_total)
        observed = route_refresh_total > 0
        configured = bool(parameters.get("eager_trip_generation", False))
        out.append(
            BenchmarkWorkloadMatrixEntry(
                workload_class=entry.workload_class,
                label=entry.label,
                stage_group=entry.stage_group,
                hardware_lanes=entry.hardware_lanes,
                enabled=observed,
                coverage_state=(
                    "measured_in_suite"
                    if observed
                    else (
                        "configured_not_observed"
                        if configured
                        else "requires_eager_runtime_suite"
                    )
                ),
                parameters=parameters,
                decision_state=entry.decision_state,
            )
        )
    return tuple(out)


def _normalize_workload_matrix_entry(
    entry: object,
) -> BenchmarkWorkloadMatrixEntry:
    if isinstance(entry, BenchmarkWorkloadMatrixEntry):
        return entry
    if isinstance(entry, dict):
        return BenchmarkWorkloadMatrixEntry(
            workload_class=str(entry.get("workload_class", "")),
            label=str(entry.get("label", "")),
            stage_group=str(entry.get("stage_group", "")),
            hardware_lanes=tuple(str(item) for item in entry.get("hardware_lanes", ()) or ()),
            enabled=bool(entry.get("enabled", False)),
            coverage_state=str(entry.get("coverage_state", "diagnostic_metadata")),
            parameters=dict(entry.get("parameters", {}) or {}),
            decision_state=str(entry.get("decision_state", "diagnostic")),
        )
    raise TypeError("workload matrix entries must be BenchmarkWorkloadMatrixEntry values.")


def _route_score_values(
    candidate_path_costs: tuple[float, ...],
    candidate_path_size_factors: tuple[float, ...],
    *,
    path_size_gamma: float,
) -> np.ndarray:
    costs = np.asarray(candidate_path_costs, dtype=np.float32)
    if costs.ndim != 1:
        raise ValueError("candidate_path_costs must be 1-D")
    if int(costs.shape[0]) == 0:
        return costs
    path_sizes = np.ones_like(costs, dtype=np.float32)
    raw_path_sizes = np.asarray(candidate_path_size_factors, dtype=np.float32)
    if raw_path_sizes.ndim == 1 and int(raw_path_sizes.shape[0]) >= int(costs.shape[0]):
        path_sizes = raw_path_sizes[: int(costs.shape[0])]
    safe_path_sizes = np.where(
        np.logical_and(np.isfinite(path_sizes), path_sizes > 0.0),
        path_sizes,
        np.asarray(1.0e-12, dtype=np.float32),
    )
    gamma = max(0.0, float(path_size_gamma))
    return np.asarray(-costs + gamma * np.log(safe_path_sizes), dtype=np.float32)


def _build_reroute_scoring_inputs(batch_size: int) -> dict[str, np.ndarray]:
    count = int(batch_size)
    if count < 1:
        raise ValueError("batch_size must be >= 1")
    x = np.linspace(0.0, 1.0, num=count, dtype=np.float32)
    return {
        "reroute_willingness": np.clip(0.15 + 0.80 * x, 0.0, 1.0),
        "delay_sensitivity": np.asarray(0.25 + 2.50 * x, dtype=np.float32),
        "exploration_bias": np.clip(0.05 + 0.40 * (1.0 - x), 0.0, 1.0),
        "persistence_bias": np.asarray(-0.25 + 0.75 * x, dtype=np.float32),
        "improvement_ratio": np.asarray(0.01 + 0.40 * x, dtype=np.float32),
    }


def _run_reroute_scoring_probe(
    inputs: Mapping[str, np.ndarray],
    *,
    routing_backend: RoutingBackend,
) -> tuple[np.ndarray, np.ndarray, str, str | None, int]:
    backend = str(routing_backend)
    fallback: str | None = None
    actual_backend = backend
    effective_backend = backend
    if backend == "auto":
        if rust_reroute_backend_available():
            effective_backend = "rust_cpu"
            actual_backend = "rust_cpu"
        else:
            effective_backend = "baseline"
            actual_backend = "baseline"
            fallback = "rust_cpu_unavailable"

    start_ns = perf_counter_ns()
    try:
        should, score = compute_reroute_decision_core(
            reroute_willingness=inputs["reroute_willingness"],
            delay_sensitivity=inputs["delay_sensitivity"],
            exploration_bias=inputs["exploration_bias"],
            persistence_bias=inputs["persistence_bias"],
            improvement_ratio=inputs["improvement_ratio"],
            routing_backend=effective_backend,
        )
    except RuntimeError:
        if backend != "auto":
            raise
        fallback = "rust_cpu_failed"
        actual_backend = "baseline"
        should, score = compute_reroute_decision_core(
            reroute_willingness=inputs["reroute_willingness"],
            delay_sensitivity=inputs["delay_sensitivity"],
            exploration_bias=inputs["exploration_bias"],
            persistence_bias=inputs["persistence_bias"],
            improvement_ratio=inputs["improvement_ratio"],
            routing_backend="baseline",
        )
    elapsed_ns = max(0, perf_counter_ns() - start_ns)
    return (
        np.asarray(should, dtype=np.bool_),
        np.asarray(score, dtype=np.float32),
        actual_backend,
        fallback,
        elapsed_ns,
    )


def _run_route_score_probe_backend(
    baseline_scores: np.ndarray,
    candidate_path_costs: tuple[float, ...],
    candidate_path_size_factors: tuple[float, ...],
    *,
    path_size_gamma: float,
    num_steps: int,
    score_probe_backend: str,
) -> tuple[np.ndarray, int, int, int, bool, str, str | None]:
    baseline = np.asarray(baseline_scores, dtype=np.float32)
    if score_probe_backend == "baseline":
        return baseline.copy(), 0, 0, 0, False, "baseline", None
    if score_probe_backend != "jax_optional":
        raise ValueError("score_probe_backend must be one of: baseline, jax_optional.")
    try:
        import jax
        import jax.numpy as jnp
    except ImportError:
        return baseline.copy(), 0, 0, 0, False, "unavailable", "jax_unavailable"

    try:
        costs = np.asarray(candidate_path_costs, dtype=np.float32)
        path_sizes = np.ones_like(costs, dtype=np.float32)
        raw_path_sizes = np.asarray(candidate_path_size_factors, dtype=np.float32)
        if raw_path_sizes.ndim == 1 and int(raw_path_sizes.shape[0]) >= int(costs.shape[0]):
            path_sizes = raw_path_sizes[: int(costs.shape[0])]
        costs_jax = jnp.asarray(costs, dtype=jnp.float32)
        path_sizes_jax = jnp.asarray(path_sizes, dtype=jnp.float32)
        gamma_jax = jnp.asarray(max(0.0, float(path_size_gamma)), dtype=jnp.float32)

        @jax.jit
        def score(costs_now, path_sizes_now, gamma_now):
            safe_path_sizes = jnp.where(
                jnp.logical_and(jnp.isfinite(path_sizes_now), path_sizes_now > 0.0),
                path_sizes_now,
                jnp.asarray(1.0e-12, dtype=jnp.float32),
            )
            return -costs_now + gamma_now * jnp.log(safe_path_sizes)

        first_start_ns = perf_counter_ns()
        result = score(costs_jax, path_sizes_jax, gamma_jax)
        jax.block_until_ready(result)
        first_ns = max(0, perf_counter_ns() - first_start_ns)
        steady_start_ns = perf_counter_ns()
        for _ in range(int(num_steps) - 1):
            result = score(costs_jax, path_sizes_jax, gamma_jax)
        jax.block_until_ready(result)
        steady_ns = max(0, perf_counter_ns() - steady_start_ns)
        return (
            np.asarray(result, dtype=np.float32),
            first_ns + steady_ns,
            first_ns,
            steady_ns,
            True,
            "jax",
            None,
        )
    except Exception:
        return baseline.copy(), 0, 0, 0, False, "unavailable", "jax_failed"


def _fingerprint_numeric_arrays(arrays: Mapping[str, np.ndarray]) -> str:
    digest = hashlib.sha256()
    for key in sorted(arrays):
        array = np.ascontiguousarray(arrays[key])
        digest.update(str(key).encode("utf-8"))
        digest.update(str(array.dtype).encode("utf-8"))
        digest.update(np.asarray(array.shape, dtype=np.int64).tobytes())
        digest.update(array.tobytes())
    return digest.hexdigest()


def _max_abs_float32_array_diff(baseline: np.ndarray, probe: np.ndarray) -> float:
    baseline_arr = np.asarray(baseline, dtype=np.float32)
    probe_arr = np.asarray(probe, dtype=np.float32)
    if baseline_arr.shape != probe_arr.shape:
        return float("inf")
    if baseline_arr.size == 0:
        return 0.0
    return float(np.max(np.abs(baseline_arr - probe_arr)))


def _run_dense_flow_jax_optional_probe(
    link_state: LinkState,
    node_state: NodeState,
    *,
    num_steps: int,
    fallback_output: Mapping[str, np.ndarray],
) -> tuple[dict[str, np.ndarray], int, int, int, int, int, bool, str, str | None]:
    try:
        result = run_dense_flow_jax(
            **build_dense_flow_jax_inputs(link_state, node_state),
            num_steps=int(num_steps),
            execution_mode="host_step_loop",
            require_gpu=False,
        )
        probe_ns = (
            result.input_copy_wall_ns
            + result.first_call_wall_ns
            + result.steady_state_wall_ns
            + result.output_copy_wall_ns
        )
        return (
            dict(result.output),
            probe_ns,
            result.first_call_wall_ns,
            result.steady_state_wall_ns,
            result.input_copy_wall_ns,
            result.output_copy_wall_ns,
            True,
            "jax",
            None,
        )
    except (JaxFlowUnavailableError, RuntimeError) as exc:
        fallback_reason = (
            "jax_unavailable" if isinstance(exc, JaxFlowUnavailableError) else "jax_failed"
        )
        return (
            {key: np.asarray(value).copy() for key, value in fallback_output.items()},
            0,
            0,
            0,
            0,
            0,
            False,
            "unavailable",
            fallback_reason,
        )


def _flow_copy_boundary_note(flow_backend: FlowUpdateBackend) -> str:
    if flow_backend == "rust_cpu":
        return "rust_cpu Vec copy boundary"
    if flow_backend == "auto":
        return "auto rust_cpu Vec copy boundary when available"
    return "numpy baseline"


def _routing_copy_boundary_note(routing_backend: str) -> str:
    if routing_backend == "rust_cpu":
        return (
            "rust_cpu Vec copy boundary for dynamic-potential, next-link scoring, "
            "greedy path, ranked-K candidates, candidate metadata, candidate selection, "
            "and reroute decision"
        )
    if routing_backend == "auto":
        return (
            "auto rust_cpu Vec copy boundary for dynamic-potential, next-link scoring, "
            "greedy path, ranked-K candidates, candidate metadata, candidate selection, "
            "and reroute decision when available"
        )
    return "numpy baseline"


def _dense_flow_probe_copy_boundary_note(probe_backend: str) -> str:
    if probe_backend == "rust_cpu":
        return "rust_cpu Vec copy boundary dense flow"
    if probe_backend == "jax_optional":
        return "optional JAX dense flow compile/steady-state probe"
    return "numpy baseline dense flow"


def _dynamic_potential_copy_boundary_note(routing_backend: str) -> str:
    if routing_backend == "rust_cpu":
        return "rust_cpu Vec copy boundary for dynamic-potential only"
    if routing_backend == "auto":
        return "auto rust_cpu Vec copy boundary for dynamic-potential only when available"
    return "numpy baseline dynamic-potential only"


def _agent_copy_boundary_note(agent_backend: str) -> str:
    if agent_backend == "rust_cpu":
        return "rust_cpu Vec copy boundary for active-agent action planning"
    if agent_backend == "auto":
        return "auto rust_cpu Vec copy boundary for active-agent action planning when available"
    return "python baseline"


def _runtime_state_seed(state: SimulationState) -> int | None:
    for container in (state.metadata, state.static.metadata):
        if isinstance(container, dict) and "scenario_seed" in container:
            try:
                return int(container["scenario_seed"])
            except (TypeError, ValueError):
                return None
    try:
        return int(state.config.random_seed)
    except (TypeError, ValueError):
        return None


def _unique_runtime_result_seeds(
    results: tuple[MeasuredRuntimeBenchmarkResult, ...],
) -> tuple[int, ...]:
    seen: set[int] = set()
    out: list[int] = []
    for result in results:
        if result.seed is None:
            continue
        seed = int(result.seed)
        if seed in seen:
            continue
        seen.add(seed)
        out.append(seed)
    return tuple(out)


def _stage_ns_metric(
    metrics_state: dict[str, object],
    *,
    total_key: str,
    tick_key: str,
) -> int:
    return max(0, int(metrics_state.get(total_key, metrics_state.get(tick_key, 0)) or 0))


def _seconds_to_ns(value: object) -> int:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return 0
    return max(0, int(round(seconds * 1_000_000_000.0)))


def _runtime_stage_timing_breakdown(
    *,
    wall_clock_ns: int,
    flow_update_wall_ns: int = 0,
    route_candidate_refresh_ns: int = 0,
    route_candidate_potential_ns: int = 0,
    route_candidate_path_build_ns: int = 0,
    route_candidate_metadata_ns: int = 0,
    dynamic_potential_recompute_ns: int = 0,
    routing_compile_estimate_ns: int = 0,
    reroute_decision_wall_ns: int = 0,
    active_agent_update_wall_ns: int = 0,
    active_agent_allocation_wall_ns: int = 0,
    active_agent_candidate_selection_wall_ns: int = 0,
    active_agent_pool_write_wall_ns: int = 0,
    active_agent_pool_array_write_wall_ns: int = 0,
    active_agent_plugin_memory_write_wall_ns: int = 0,
    active_agent_movement_wall_ns: int = 0,
    gpu_candidate_threshold: float = 0.30,
) -> tuple[RuntimeStageTiming, ...]:
    denominator = max(1, int(wall_clock_ns))
    gpu_candidate_stage_names = {
        "flow_update",
        "route_candidate_refresh",
        "route_candidate_potential",
        "route_candidate_path_build",
        "route_candidate_metadata",
        "reroute_decision",
        "active_agent_update",
        "active_agent_allocation",
        "active_agent_candidate_selection",
        "active_agent_pool_write",
        "active_agent_pool_array_write",
        "active_agent_plugin_memory_write",
        "active_agent_movement",
    }
    raw = (
        ("flow_update", flow_update_wall_ns),
        ("route_candidate_refresh", route_candidate_refresh_ns),
        ("dynamic_potential_recompute", dynamic_potential_recompute_ns),
        ("routing_compile_estimate", routing_compile_estimate_ns),
        ("reroute_decision", reroute_decision_wall_ns),
        ("active_agent_update", active_agent_update_wall_ns),
        ("route_candidate_potential", route_candidate_potential_ns),
        ("route_candidate_path_build", route_candidate_path_build_ns),
        ("route_candidate_metadata", route_candidate_metadata_ns),
        ("active_agent_allocation", active_agent_allocation_wall_ns),
        (
            "active_agent_candidate_selection",
            active_agent_candidate_selection_wall_ns,
        ),
        ("active_agent_pool_write", active_agent_pool_write_wall_ns),
        ("active_agent_pool_array_write", active_agent_pool_array_write_wall_ns),
        (
            "active_agent_plugin_memory_write",
            active_agent_plugin_memory_write_wall_ns,
        ),
        ("active_agent_movement", active_agent_movement_wall_ns),
    )
    out: list[RuntimeStageTiming] = []
    for stage_name, wall_ns in raw:
        wall_ns = max(0, int(wall_ns))
        share = round(float(wall_ns / denominator), 6)
        out.append(
            RuntimeStageTiming(
                stage_name=stage_name,
                wall_clock_ns=wall_ns,
                wall_time_share=share,
                gpu_candidate=(
                    stage_name in gpu_candidate_stage_names
                    and share >= float(gpu_candidate_threshold)
                ),
            )
        )
    return tuple(out)


def format_runtime_stage_timing_markdown(
    result: MeasuredRuntimeBenchmarkResult,
) -> str:
    """Render runtime stage timing and future GPU gate metadata."""

    candidate_names = ", ".join(result.gpu_candidate_stage_names) or "none"
    lines = [
        "- Runtime stage timing:",
        f"- GPU candidate stages: {candidate_names}",
        f"- GPU candidate threshold: {result.gpu_candidate_threshold}",
        f"- GPU candidate minimum deterministic seeds: {result.gpu_candidate_min_seed_count}",
    ]
    lines.extend(
        f"- {item.stage_name}: {item.wall_clock_ns} ns (share {item.wall_time_share})"
        for item in result.runtime_stage_timings
    )
    return "\n".join(lines)


def format_runtime_gpu_candidate_gate_markdown(
    report: RuntimeGpuCandidateGateReport,
) -> str:
    """Render the multi-run gate used before opening GPU backend work."""

    eligible_names = ", ".join(report.gpu_review_eligible_stage_names) or "none"
    seed_names = ", ".join(str(seed) for seed in report.seeds) or "unknown"
    lines = [
        "- Runtime GPU candidate gate:",
        f"- Workload: {report.workload_name}",
        f"- Deterministic runs: {report.deterministic_run_count}",
        f"- Unique seeds: {report.unique_seed_count}",
        f"- Seeds: {seed_names}",
        f"- Threshold: {report.gpu_candidate_threshold}",
        f"- Minimum deterministic seeds: {report.gpu_candidate_min_seed_count}",
        f"- Eligible stages: {eligible_names}",
    ]
    lines.extend(
        (
            f"- {item.stage_name}: candidate runs "
            f"{item.candidate_run_count}/{item.deterministic_run_count}, "
            f"mean share {item.mean_wall_time_share}, "
            f"min share {item.min_wall_time_share}, "
            f"max share {item.max_wall_time_share}, "
            f"eligible {'yes' if item.gpu_review_eligible else 'no'}"
        )
        for item in report.stage_summaries
    )
    return "\n".join(lines)


def run_measured_step_world_benchmark(
    world: WorldState,
    config: MeasuredBenchmarkConfig,
) -> MeasuredBenchmarkResult:
    workload_name = config.workload_name.strip()
    if not workload_name:
        raise ValueError("workload_name must be non-empty.")
    if config.num_steps <= 0:
        raise ValueError("num_steps must be positive.")

    current_world = world
    start_ns = perf_counter_ns()
    for _ in range(config.num_steps):
        current_world = step_world(
            current_world,
            schedule=config.schedule,
            edge_inflow_veh_per_tick=config.edge_inflow_veh_per_tick,
            edge_outflow_veh_per_tick=config.edge_outflow_veh_per_tick,
            edge_free_flow_time_ticks=config.edge_free_flow_time_ticks,
            edge_capacity_veh_per_tick=config.edge_capacity_veh_per_tick,
            edge_backend=config.edge_backend,
            zonal_travel_times=config.zonal_travel_times,
            zone_opportunities=config.zone_opportunities,
        )
    elapsed_ns = perf_counter_ns() - start_ns

    return MeasuredBenchmarkResult(
        name="measured_step_world",
        workload_name=workload_name,
        wall_clock_ns=max(elapsed_ns, 0),
        seed=world.replay.seed,
        num_steps=config.num_steps,
        initial_traffic_step=world.traffic.step,
        final_traffic_step=current_world.traffic.step,
        schedule=config.schedule,
        edge_count=world.graph.num_edges,
        zone_count=len(world.landuse.zone_labels),
        edge_backend=config.edge_backend,
    )
