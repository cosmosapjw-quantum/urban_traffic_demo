from metroflow.core.contracts import TickSchedule, validate_state_contract
from metroflow.core.state import WorldState
from metroflow.sim.scheduler import scheduler_decision
from metroflow.traffic.meso import evolve_edges_fast_tick


def step_world(
    world: WorldState,
    schedule: TickSchedule | None = None,
    edge_inflow_veh_per_tick: tuple[float, ...] | None = None,
    edge_outflow_veh_per_tick: tuple[float, ...] | None = None,
    edge_free_flow_time_ticks: tuple[float, ...] | None = None,
    edge_capacity_veh_per_tick: tuple[float, ...] | None = None,
) -> WorldState:
    if schedule is None:
        schedule = TickSchedule()

    validate_state_contract(world)
    decision = scheduler_decision(world.traffic.step, schedule)
    if decision.run_fast:
        # This boundary advances exactly one fast tick using per-fast-tick inputs.
        next_world = evolve_edges_fast_tick(
            world,
            edge_inflow_veh_per_tick=edge_inflow_veh_per_tick,
            edge_outflow_veh_per_tick=edge_outflow_veh_per_tick,
            edge_free_flow_time_ticks=edge_free_flow_time_ticks,
            edge_capacity_veh_per_tick=edge_capacity_veh_per_tick,
        )
        validate_state_contract(next_world)
        return next_world
    return world
