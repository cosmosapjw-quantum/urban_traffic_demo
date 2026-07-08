from dataclasses import dataclass, replace

from metroflow.core.contracts import TickSchedule, validate_state_contract
from metroflow.core.state import WorldState
from metroflow.demand.accessibility import compute_accessibility_snapshot, update_accessibility_cache
from metroflow.landuse.evolution import (
    apply_landuse_delta,
    apply_lagged_landuse_feedback,
    reduce_zonal_costs_to_lagged_accessibility,
)
from metroflow.sim.scheduler import scheduler_decision
from metroflow.traffic.meso import EdgeEvolutionBackend, evolve_edges_fast_tick
from metroflow.traffic.routing import (
    CandidatePath,
    GeneralizedCostWeights,
    ODRouteChoiceResult,
    ODRouteEvaluationRequest,
    evaluate_od_route_set,
    validate_od_route_request,
)


@dataclass(frozen=True)
class RuntimeRoutingInput:
    origin_id: str | None = None
    destination_id: str | None = None
    candidates: tuple[CandidatePath, ...] | None = None
    k: int | None = None
    weights: GeneralizedCostWeights | None = None


@dataclass(frozen=True)
class FastTickInput:
    edge_inflow_veh_per_tick: tuple[float, ...] | None = None
    edge_outflow_veh_per_tick: tuple[float, ...] | None = None
    edge_free_flow_time_ticks: tuple[float, ...] | None = None
    edge_capacity_veh_per_tick: tuple[float, ...] | None = None
    edge_backend: EdgeEvolutionBackend = "baseline"


@dataclass(frozen=True)
class MediumTickInput:
    zonal_travel_times: tuple[tuple[float, ...], ...] | None = None
    zone_opportunities: tuple[float, ...] | None = None


@dataclass(frozen=True)
class RuntimeRoutingStepResult:
    world: WorldState
    routing_result: ODRouteChoiceResult | None


def _validate_medium_inputs(
    world: WorldState,
    zonal_travel_times: tuple[tuple[float, ...], ...] | None,
    zone_opportunities: tuple[float, ...] | None,
) -> None:
    if zonal_travel_times is None or zone_opportunities is None:
        raise ValueError("zonal_travel_times and zone_opportunities are required for medium cadence.")

    zone_count = len(world.landuse.zone_labels)
    if len(zone_opportunities) != zone_count:
        raise ValueError("zone_opportunities length must match landuse.zone_labels length.")
    if len(zonal_travel_times) != zone_count:
        raise ValueError("zonal_travel_times dimension must match landuse.zone_labels length.")
    if any(len(row) != zone_count for row in zonal_travel_times):
        raise ValueError("zonal_travel_times rows must match landuse.zone_labels length.")


def _validate_slow_snapshot(world: WorldState) -> None:
    zone_count = len(world.landuse.zone_labels)
    if not world.accessibility.zonal_costs:
        raise ValueError("A pre-call lagged accessibility snapshot is required for slow cadence.")
    if len(world.accessibility.zonal_costs) != zone_count:
        raise ValueError("Lagged accessibility payload dimension must match landuse.zone_labels length.")
    if any(len(row) != zone_count for row in world.accessibility.zonal_costs):
        raise ValueError("Lagged accessibility rows must match landuse.zone_labels length.")
    if world.accessibility.lagged_snapshot_step >= world.traffic.step:
        raise ValueError("Lagged accessibility snapshot must predate the current traffic.step.")
    if world.accessibility.graph_version != world.graph.version:
        raise ValueError("Lagged accessibility graph_version must match the pre-call world.")
    if world.accessibility.landuse_version != world.landuse.version:
        raise ValueError("Lagged accessibility landuse_version must match the pre-call world.")


def _validate_runtime_routing_input(
    world: WorldState,
    runtime_routing: RuntimeRoutingInput | None,
) -> None:
    if runtime_routing is None:
        return

    required_fields = (
        runtime_routing.origin_id,
        runtime_routing.destination_id,
        runtime_routing.candidates,
        runtime_routing.k,
    )
    if any(field is None for field in required_fields):
        raise ValueError("Runtime routing input must be complete when provided.")

    request = ODRouteEvaluationRequest(
        origin_id=runtime_routing.origin_id,
        destination_id=runtime_routing.destination_id,
        candidates=runtime_routing.candidates,
        k=runtime_routing.k,
        world=world,
        weights=GeneralizedCostWeights() if runtime_routing.weights is None else runtime_routing.weights,
    )
    validate_od_route_request(request)


def step_world_from_inputs(
    world: WorldState,
    *,
    schedule: TickSchedule | None = None,
    fast_tick: FastTickInput | None = None,
    medium_tick: MediumTickInput | None = None,
) -> WorldState:
    fast = fast_tick or FastTickInput()
    medium = medium_tick or MediumTickInput()
    return step_world(
        world,
        schedule=schedule,
        edge_inflow_veh_per_tick=fast.edge_inflow_veh_per_tick,
        edge_outflow_veh_per_tick=fast.edge_outflow_veh_per_tick,
        edge_free_flow_time_ticks=fast.edge_free_flow_time_ticks,
        edge_capacity_veh_per_tick=fast.edge_capacity_veh_per_tick,
        edge_backend=fast.edge_backend,
        zonal_travel_times=medium.zonal_travel_times,
        zone_opportunities=medium.zone_opportunities,
    )


def step_world(
    world: WorldState,
    schedule: TickSchedule | None = None,
    edge_inflow_veh_per_tick: tuple[float, ...] | None = None,
    edge_outflow_veh_per_tick: tuple[float, ...] | None = None,
    edge_free_flow_time_ticks: tuple[float, ...] | None = None,
    edge_capacity_veh_per_tick: tuple[float, ...] | None = None,
    edge_backend: EdgeEvolutionBackend = "baseline",
    zonal_travel_times: tuple[tuple[float, ...], ...] | None = None,
    zone_opportunities: tuple[float, ...] | None = None,
) -> WorldState:
    if schedule is None:
        schedule = TickSchedule()

    validate_state_contract(world)
    decision = scheduler_decision(world.traffic.step, schedule)
    if decision.run_medium and not decision.run_fast:
        raise ValueError("Illegal schedule: medium cadence requires fast cadence.")
    if decision.run_medium and decision.run_slow:
        raise ValueError("Illegal same-step medium and slow overlap is forbidden.")
    if decision.run_medium:
        _validate_medium_inputs(world, zonal_travel_times, zone_opportunities)
    if decision.run_slow:
        _validate_slow_snapshot(world)

    if not (decision.run_fast or decision.run_medium or decision.run_slow):
        return world

    next_world = world
    pre_call_accessibility = world.accessibility
    if decision.run_medium:
        snapshot = compute_accessibility_snapshot(
            step_idx=world.traffic.step,
            graph_version=world.graph.version,
            landuse_version=world.landuse.version,
            zonal_travel_times=zonal_travel_times,
            zone_opportunities=zone_opportunities,
        )
        next_world = update_accessibility_cache(next_world, snapshot)
    if decision.run_fast:
        # This boundary advances exactly one fast tick using per-fast-tick inputs.
        next_world = evolve_edges_fast_tick(
            next_world,
            edge_inflow_veh_per_tick=edge_inflow_veh_per_tick,
            edge_outflow_veh_per_tick=edge_outflow_veh_per_tick,
            edge_free_flow_time_ticks=edge_free_flow_time_ticks,
            edge_capacity_veh_per_tick=edge_capacity_veh_per_tick,
            edge_backend=edge_backend,
        )
    if decision.run_slow:
        lagged_accessibility = reduce_zonal_costs_to_lagged_accessibility(pre_call_accessibility.zonal_costs)
        delta = apply_lagged_landuse_feedback(
            lagged_accessibility,
            next_world.landuse.housing_capacity,
            next_world.landuse.jobs_capacity,
        )
        next_housing, next_jobs = apply_landuse_delta(
            next_world.landuse.housing_capacity,
            next_world.landuse.jobs_capacity,
            delta,
        )
        next_world = replace(
            next_world,
            landuse=replace(
                next_world.landuse,
                version=next_world.landuse.version + 1,
                housing_capacity=next_housing,
                jobs_capacity=next_jobs,
            ),
            accessibility=replace(
                next_world.accessibility,
                version=next_world.accessibility.version + 1,
                lagged_snapshot_step=-1,
                graph_version=pre_call_accessibility.graph_version,
                landuse_version=pre_call_accessibility.landuse_version,
                zonal_costs=tuple(),
            ),
        )
    validate_state_contract(next_world)
    return next_world


def step_world_with_routing(
    world: WorldState,
    schedule: TickSchedule | None = None,
    edge_inflow_veh_per_tick: tuple[float, ...] | None = None,
    edge_outflow_veh_per_tick: tuple[float, ...] | None = None,
    edge_free_flow_time_ticks: tuple[float, ...] | None = None,
    edge_capacity_veh_per_tick: tuple[float, ...] | None = None,
    edge_backend: EdgeEvolutionBackend = "baseline",
    zonal_travel_times: tuple[tuple[float, ...], ...] | None = None,
    zone_opportunities: tuple[float, ...] | None = None,
    runtime_routing: RuntimeRoutingInput | None = None,
) -> RuntimeRoutingStepResult:
    if schedule is None:
        schedule = TickSchedule()

    validate_state_contract(world)
    decision = scheduler_decision(world.traffic.step, schedule)
    _validate_runtime_routing_input(world, runtime_routing)

    next_world = step_world(
        world,
        schedule=schedule,
        edge_inflow_veh_per_tick=edge_inflow_veh_per_tick,
        edge_outflow_veh_per_tick=edge_outflow_veh_per_tick,
        edge_free_flow_time_ticks=edge_free_flow_time_ticks,
        edge_capacity_veh_per_tick=edge_capacity_veh_per_tick,
        edge_backend=edge_backend,
        zonal_travel_times=zonal_travel_times,
        zone_opportunities=zone_opportunities,
    )

    if runtime_routing is None or not decision.run_fast:
        return RuntimeRoutingStepResult(world=next_world, routing_result=None)

    routing_result = evaluate_od_route_set(
        next_world,
        origin_id=runtime_routing.origin_id,
        destination_id=runtime_routing.destination_id,
        candidates=runtime_routing.candidates,
        k=runtime_routing.k,
        weights=runtime_routing.weights,
    )
    return RuntimeRoutingStepResult(world=next_world, routing_result=routing_result)
