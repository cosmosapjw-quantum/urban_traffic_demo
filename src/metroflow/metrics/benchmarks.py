from dataclasses import dataclass, field
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
    route_candidate_refresh_seconds_total: float = 0.0
    dynamic_potential_recompute_seconds_total: float = 0.0
    routing_compile_seconds_estimate_total: float = 0.0
    reroute_decisions_total: int = 0
    persistence_decisions_total: int = 0
    active_agent_sink_wait_total: int = 0
    active_agent_sink_wait_this_tick: int = 0
    active_agent_update_wall_ns: int = 0
    active_agent_rerouted_this_tick: int = 0
    active_agent_reroute_cooldown_this_tick: int = 0


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
        route_candidate_refresh_seconds_total=float(
            metrics_state.get("route_candidate_refresh_seconds_total", 0.0)
        ),
        dynamic_potential_recompute_seconds_total=float(
            metrics_state.get("dynamic_potential_recompute_seconds_total", 0.0)
        ),
        routing_compile_seconds_estimate_total=float(
            metrics_state.get("routing_compile_seconds_estimate_total", 0.0)
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
