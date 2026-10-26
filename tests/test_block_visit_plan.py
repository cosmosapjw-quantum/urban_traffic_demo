import pytest
from test_atlas_block_access import fixture
from metroflow.terrain_city.block_access import Growth
from metroflow.terrain_city.block_trips import plan_visits, simulate_visits


def test_new_residents_only_and_no_access_egress_teleport():
    m = Growth(fixture(), ("job",))
    a = m.initial()
    b, _ = m.step(a, 10, budget_m=100.0)
    plan = plan_visits(m, a, b)
    ledger = dict(plan.ledger)
    assert ledger["new_residents"] == 10 and ledger["vehicle_trips"] == pytest.approx(1.0)
    assert ledger["noncar_person_trips"] == pytest.approx(0.8)
    assert len(plan.routes) == 1
    path = plan.routes[0].groups
    assert path[0] == "private:home:out" and path[-1] == "private:job:in"
    r, s = simulate_visits(plan, duration_s=10.0, horizon_s=1000.0)
    assert r["status"] == "CLEARED_SCOPED" and r["completed"] == pytest.approx(1.0)
    assert r["system_vehicle_seconds"] == pytest.approx(
        r["road_vehicle_seconds"] + r["source_wait_seconds"] + r["transfer_hold_seconds"]
    )


def test_growth_not_repeated_and_invalid_scale_and_horizon_rejected():
    m = Growth(fixture(), ("job",))
    a = m.initial()
    b, _ = m.step(a, 10, budget_m=100.0)
    with pytest.raises(ValueError):
        plan_visits(m, b, a)
    with pytest.raises(ValueError):
        plan_visits(m, a, b, persons_per_car=0.5)
    p = plan_visits(m, a, b)
    with pytest.raises(ValueError):
        simulate_visits(p, horizon_s=3.0, dt_s=2.0)
    c, _ = m.step(b, 0)
    empty = plan_visits(m, b, c)
    assert dict(empty.ledger)["vehicle_trips"] == 0 and not empty.routes
