from dataclasses import dataclass, field, replace
from time import perf_counter_ns

from metroflow.core.contracts import TickSchedule
from metroflow.core.state import WorldState
from metroflow.flow.engine import FlowUpdateBackend, update_link_node_flow
from metroflow.flow.state import LinkState, NodeState
from metroflow.city.graph import RoadNetworkCSR
from metroflow.routing.dynamic_potential import RoutingBackend
from metroflow.routing.candidates import create_route_candidate_set
from metroflow.traffic.meso import EdgeEvolutionBackend
from metroflow.sim.control import SimulationControl
from metroflow.sim.config import SimulationConfig
from metroflow.sim.init import build_initial_simulation_state
from metroflow.sim.rng import PRNGKeyArray
from metroflow.sim.replay import ReplayInputSignatureRecord
from metroflow.sim.orchestrator import step_world
from metroflow.sim.state import SimulationState
from metroflow.sim.step import simulation_step


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
class MeasuredRuntimeBenchmarkConfig:
    workload_name: str
    num_steps: int
    control: SimulationControl = field(default_factory=SimulationControl)


@dataclass(frozen=True)
class MeasuredRuntimeBenchmarkSuiteConfig:
    workload_name: str
    seeds: tuple[int, ...]
    num_steps: int
    control: SimulationControl = field(default_factory=SimulationControl)
    simulation_config: SimulationConfig | None = None
    eager_trip_generation: bool = False


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
    route_candidate_refresh_seconds_total: float = 0.0
    dynamic_potential_recompute_seconds_total: float = 0.0


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
        route_candidate_refresh_seconds_total=float(
            stats.get("route_candidate_refresh_seconds_total", 0.0)
        ),
        dynamic_potential_recompute_seconds_total=float(
            stats.get("dynamic_potential_recompute_seconds_total", 0.0)
        ),
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
