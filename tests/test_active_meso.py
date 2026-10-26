import math
import pytest
from metroflow.active_meso import MesoLink, DriverGroup, MesoConfig, ActiveMeso, collision_step


def link(length=150.0, cap=1.0, storage=30.0):
    return MesoLink("a", "s", "t", length, 15.0, cap, storage)


def model(**kw):
    return ActiveMeso(
        (link(),), (DriverGroup("normal", "s", "t", braking_rate=0.0),), MesoConfig(**kw)
    )


def test_collision_positive_exact_stationary_and_semigroup():
    s, m = collision_step(10.0, 0.0, 0.2, 0.3, 100.0)
    assert m == pytest.approx(4.0, abs=1e-10)
    assert s + m == pytest.approx(10.0) and min(s, m) >= 0
    a = collision_step(3.0, 7.0, 0.2, 0.3, 2.0)
    b = collision_step(*collision_step(3.0, 7.0, 0.2, 0.3, 0.7), 0.2, 0.3, 1.3)
    assert a == pytest.approx(b)


def test_pipeline_no_early_arrival_and_exact_mass():
    sim = model(dt=1.0)
    s = sim.initial_state()
    for i in range(10):
        s = sim.step(s, (1.0 if i == 0 else 0.0,))
        d = sim.diagnostics(s)
        assert d["completed"] == 0.0
        assert d["released"] == pytest.approx(d["active"] + d["pending"] + d["completed"])
    s = sim.step(s, (0.0,))
    d = sim.diagnostics(s)
    assert d["completed"] == pytest.approx(1.0)


def test_overload_retained_outside_network_without_per_vehicle_state():
    for demand in (1000.0, 100000.0):
        sim = model(dt=1.0)
        s = sim.initial_state()
        for i in range(30):
            s = sim.step(s, (demand if i == 0 else 0.0,))
        d = sim.diagnostics(s)
        assert d["released"] == demand
        assert d["active"] <= 30.0 + 1e-9 and d["pending"] > 0
        assert d["mass_error"] == pytest.approx(0.0, abs=1e-7)
        assert 0 < sim.state_values < 100


def test_closure_does_not_teleport_mass_and_reopening_clears():
    sim = model(dt=1.0)
    s = sim.initial_state()
    for i in range(60):
        s = sim.step(
            s, (10.0 if i == 0 else 0.0,), capacity_scale={"a": 0.0 if 5 <= i < 30 else 1.0}
        )
        d = sim.diagnostics(s)
        if 5 <= i < 30:
            assert d["completed"] == 0.0
        assert abs(d["mass_error"]) < 1e-9
    assert d["completed"] == pytest.approx(10.0, abs=1e-8)


def test_red_signal_discharge_zero_with_fractional_service():
    sim = ActiveMeso(
        (link(length=15.0, cap=0.05),),
        (DriverGroup("n", "s", "t", braking_rate=0.0),),
        MesoConfig(dt=1.0),
    )
    s = sim.initial_state()
    prev = 0.0
    for i in range(120):
        green = i % 20 < 10
        s = sim.step(s, (100.0 if i == 0 else 0.0,), green={"a": green})
        d = sim.diagnostics(s)
        if not green:
            assert d["completed"] == pytest.approx(prev)
        prev = d["completed"]
    assert 2.8 <= d["completed"] <= 3.0


def test_invalid_configuration_does_not_silently_run():
    with pytest.raises(ValueError):
        model(dt=0.0)


def test_reopened_route_is_not_poisoned_by_closure_infinity_memory():
    links = (
        MesoLink("a", "s", "t", 150.0, 15.0, 1.0, 30.0),
        MesoLink("b", "s", "t", 180.0, 15.0, 1.0, 30.0),
    )
    sim = ActiveMeso(links, (DriverGroup("normal", "s", "t", braking_rate=0.0),), MesoConfig())
    s = sim.initial_state()
    for i in range(300):
        s = sim.step(s, capacity_scale={"a": 0.0 if 20 <= i < 120 else 1.0})
    first = next(r for r, (_, path, _) in enumerate(sim.routes) if path == (0,))
    assert s.perceived_costs[first] < 100.0, (
        "closures are feasibility, not a billion-second observation"
    )
    assert s.shares[first] > 0.4, (
        "reopened short route should recover without fictitious multi-hour memory"
    )


def test_service_oracle_under_time_refinement_and_red_signal():
    from dataclasses import replace

    for dt in (10.0, 5.0, 2.5, 1.0):
        sim = ActiveMeso(
            (link(length=1500.0, cap=0.05, storage=225.0),),
            (DriverGroup("normal", "s", "t", braking_rate=0.0),),
            MesoConfig(dt=dt),
        )
        s = replace(sim.initial_state(), ready=(160.0,), released=(160.0,))
        for i in range(round(600 / dt)):
            green = (i * dt) % 60 < 30
            old = s.completed[0]
            s = sim.step(s, green={"a": green})
            if not green:
                assert s.completed[0] == old
        assert s.completed[0] == pytest.approx(15.0, abs=1e-10)
        assert abs(sim.diagnostics(s)["mass_error"]) < 1e-10


def test_cohort_speed_and_number_are_not_individual_car_state():
    sim = ActiveMeso(
        (link(length=150.0, cap=10.0, storage=100.0),),
        (
            DriverGroup("fast", "s", "t", 15.0, braking_rate=0.0),
            DriverGroup("slow", "s", "t", 10.0, braking_rate=0.0),
        ),
        MesoConfig(),
    )
    s = sim.initial_state()
    for i in range(11):
        s = sim.step(s, (1.0, 1.0) if i == 0 else None)
    assert s.completed == pytest.approx((1.0, 0.0))
    for _ in range(5):
        s = sim.step(s)
    assert s.completed == pytest.approx((1.0, 1.0))
    assert sim.diagnostics(s)["max_group_mass_error"] < 1e-10


def test_symmetry_replay_and_route_share_change_bound():
    links = (
        MesoLink("a", "s", "t", 150.0, 15.0, 0.2, 30.0),
        MesoLink("b", "s", "t", 150.0, 15.0, 0.2, 30.0),
    )
    sim = ActiveMeso(links, (DriverGroup("g", "s", "t"),), MesoConfig())
    s = sim.initial_state()
    repeat = sim.initial_state()
    bound = 1 - math.exp(-10 / 60)
    for i in range(150):
        prior = s.shares
        s = sim.step(s, (0.3,))
        repeat = sim.step(repeat, (0.3,))
        assert s.shares == pytest.approx((0.5, 0.5), abs=1e-12)
        assert max(abs(a - b) for a, b in zip(s.shares, prior)) <= bound + 1e-12
    assert sim.fingerprint(s) == sim.fingerprint(repeat)


def test_state_budget_is_hard_and_route_pool_miss_is_reported():
    with pytest.raises(ValueError, match="budget"):
        model(max_state_values=10)
    links = (
        MesoLink("a", "s", "t", 150.0, 15.0, 1.0, 30.0),
        MesoLink("b", "s", "t", 180.0, 15.0, 1.0, 30.0),
    )
    sim = ActiveMeso(links, (DriverGroup("g", "s", "t"),), MesoConfig(max_paths=1))
    s = sim.step(sim.initial_state(), (10.0,), capacity_scale={"a": 0.0})
    assert s.pending[0] == 10.0
    assert s.candidate_regret_s == 1e9
    assert sim.diagnostics(s)["active"] == 0.0


def test_node_reallocates_shared_supply_without_artificial_holding():
    from dataclasses import replace

    links = (
        MesoLink("i1", "s1", "j", 15.0, 15.0, 10.0, 100.0),
        MesoLink("i2", "s2", "j", 15.0, 15.0, 10.0, 100.0),
        MesoLink("o1", "j", "t1", 15.0, 15.0, 10.0, 100.0),
        MesoLink("o2", "j", "t2", 15.0, 15.0, 10.0, 100.0),
    )
    groups = (
        DriverGroup("a", "s1", "t1", braking_rate=0.0),
        DriverGroup("b", "s1", "t2", braking_rate=0.0),
        DriverGroup("c", "s2", "t1", braking_rate=0.0),
    )
    sim = ActiveMeso(links, groups, MesoConfig(max_paths=1))
    ready = [0.0] * len(sim.legs)
    for _, _, legs in sim.routes:
        ready[legs[0]] = 10.0
    s = replace(sim.initial_state(), ready=tuple(ready), released=(10.0,) * 3)
    s = sim.step(s)
    outgoing = sum(sum(s.moving[legs[-1]]) for _, _, legs in sim.routes)
    assert outgoing == pytest.approx(20.0), (
        "15 is Pareto-maximal but not holding-free maximum throughput"
    )
