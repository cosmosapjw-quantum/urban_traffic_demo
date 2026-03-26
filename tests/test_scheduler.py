from dataclasses import replace

from metroflow.core.contracts import TickSchedule
from metroflow.core.state import GraphState, TrafficState, make_empty_world_state
from metroflow.sim.orchestrator import step_world
from metroflow.sim.scheduler import scheduler_decision


def test_scheduler_decision_cadence():
    schedule = TickSchedule(fast_every=1, medium_every=5, slow_every=20)
    d0 = scheduler_decision(0, schedule)
    d1 = scheduler_decision(1, schedule)
    d5 = scheduler_decision(5, schedule)
    assert d0.run_fast and d0.run_medium and d0.run_slow
    assert d1.run_fast and (not d1.run_medium) and (not d1.run_slow)
    assert d5.run_medium


def test_step_world_advances_on_fast_tick_schedule():
    schedule = TickSchedule(fast_every=2, medium_every=5, slow_every=20)
    world = replace(
        make_empty_world_state(),
        graph=GraphState(num_edges=1),
        traffic=TrafficState(
            step=0,
            edge_queue=(0.0,),
            edge_stock=(1.0,),
            edge_travel_time=(0.0,),
        ),
    )

    world2 = step_world(world, schedule=schedule)
    world3 = step_world(world2, schedule=schedule)

    assert world2.traffic.step == 1
    assert world2.traffic.edge_travel_time == (1.0,)
    assert world3 == world2
    assert world3 is world2
