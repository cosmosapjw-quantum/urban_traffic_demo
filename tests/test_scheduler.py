from metroflow.core.contracts import TickSchedule
from metroflow.sim.scheduler import scheduler_decision


def test_scheduler_decision_cadence():
    schedule = TickSchedule(fast_every=1, medium_every=5, slow_every=20)
    d0 = scheduler_decision(0, schedule)
    d1 = scheduler_decision(1, schedule)
    d5 = scheduler_decision(5, schedule)
    assert d0.run_fast and d0.run_medium and d0.run_slow
    assert d1.run_fast and (not d1.run_medium) and (not d1.run_slow)
    assert d5.run_medium
