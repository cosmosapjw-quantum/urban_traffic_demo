import pytest
from metroflow.active_suffix import Road, Demand, Config, BudgetExceeded
from metroflow.active_suffix.causal import Information, CostFrame, CausalPackedModel, perceived


def test_only_delivered_dynamic_information_changes_perceived_cost():
    info = Information(100.0, 10.0, 2.0)
    history = (CostFrame(5.0, (99.0, 88.0)),)
    assert perceived((1.0, 2.0), (50.0, 200.0), info, history, 11.0) == (1.0, 2.0)
    assert perceived((1.0, 2.0), (50.0, 200.0), info, history, 12.0) == (99.0, 2.0)


def fixture(info, closure, frame_budget=256, rate=0.0, start=100.0):
    roads = (
        Road("oa", "O", "A", 100.0, 10.0, 1.0, 30.0),
        Road("ad", "A", "D", 100.0, 10.0, 1.0, 30.0),
        Road("ob", "O", "B", 150.0, 10.0, 1.0, 30.0),
        Road("bd", "B", "D", 150.0, 10.0, 1.0, 30.0),
    )
    sensors = {key: (50.0, 0.0) for key in ("oa", "ad", "ob", "bd")}
    cfg = Config(
        dt_s=1.0,
        paths_per_od=2,
        route_refresh_s=1.0,
        route_response_s=1.0,
        temperature_s=0.0,
        interaction_rate_s=0.0,
    )
    return CausalPackedModel(
        roads,
        (Demand("O", "D", start, start + 20.0, rate),),
        ((0.0, 0.0),),
        sensors,
        info,
        cfg,
        capacity_windows=(("ad", 2.0, 60.0, 0.0),) if closure else (),
        frame_budget=frame_budget,
    )


def test_paired_worlds_have_identical_choices_until_report_arrives():
    a = fixture(Information(100.0, 10.0, 2.0), False)
    b = fixture(Information(100.0, 10.0, 2.0), True)
    x, y = a.initial(), b.initial()
    for _ in range(10):
        x, y = a.step(x), b.step(y)
        assert x.physical.choice == y.physical.choice
    x, y = a.step(x), b.step(y)  # completed frame t=3 arrives at t=10
    assert x.physical.choice != y.physical.choice


def test_outside_information_radius_does_not_expose_remote_closure():
    a = fixture(Information(20.0, 10.0, 2.0), False)
    b = fixture(Information(20.0, 10.0, 2.0), True)
    x, y = a.initial(), b.initial()
    for _ in range(20):
        x, y = a.step(x), b.step(y)
        assert x.physical.choice == y.physical.choice


def test_observation_budget_failure_preserves_last_valid_state():
    m = fixture(Information(100.0, 1.0, 2.0), False, frame_budget=1)
    first = m.initial()
    second = m.step(first)
    assert first.physical.tick == 0
    with pytest.raises(BudgetExceeded) as exc:
        m.step(second)
    assert exc.value.checkpoint == second


def test_hidden_event_does_not_leak_via_refresh_schedule():
    from dataclasses import replace

    a = fixture(Information(20.0, 10.0, 2.0), False)
    b = fixture(Information(20.0, 10.0, 2.0), True)
    a.kernel.cfg = replace(a.kernel.cfg, route_refresh_s=4.0)
    b.kernel.cfg = replace(b.kernel.cfg, route_refresh_s=4.0)
    x, y = a.initial(), b.initial()
    for _ in range(20):
        x, y = a.step(x), b.step(y)
        assert x.physical.last_choice_s == y.physical.last_choice_s
        assert x.physical.choice == y.physical.choice


def test_belief_never_overrides_actual_closure_or_mass_conservation():
    m = fixture(Information(20.0, 10.0, 2.0), True, rate=0.2, start=0.0)
    state = m.initial()
    for _ in range(200):
        old = state
        state = m.step(state)
        if 2 <= old.physical.tick < 60:
            j = m.kernel.index["ad"]
            assert state.physical.link_outflow[j] == old.physical.link_outflow[j]
        occ, _ = m.occupancy(state)
        assert state.physical.released == pytest.approx(
            state.physical.completed + sum(state.physical.pending) + sum(occ), abs=1e-10
        )
        assert all(x <= r.storage_veh + 1e-10 for x, r in zip(occ, m.kernel.roads))
    assert state.physical.completed == pytest.approx(4.0, abs=1e-9)
    assert len(state.history) <= 2


def test_replay_and_pruning_preserve_the_observed_costs():
    m = fixture(Information(100.0, 10.0, 2.0), True)
    x, y = m.initial(), m.initial()
    full = []
    for _ in range(40):
        x, y = m.step(x), m.step(y)
        full.append(x.history[-1])
        assert x == y and m.fingerprint(x) == m.fingerprint(y)
        now = x.physical.tick
        assert perceived(m.prior, m.distances[0], m.information[0], x.history, now) == perceived(
            m.prior, m.distances[0], m.information[0], tuple(full), now
        )
    assert len(x.history) <= 9


def test_information_classes_and_validation():
    h = (CostFrame(5.0, (99.0,)),)
    assert perceived((1.0,), (50.0,), Information(100.0, 10.0, 0.0), h, 10.0) == (99.0,)
    assert perceived((1.0,), (50.0,), Information(100.0, 10.0, 1.0), h, 10.0) == (1.0,)
    with pytest.raises(ValueError):
        Information(propagation_mps=0.0)
    with pytest.raises(ValueError):
        perceived((1.0,), (50.0,), Information(), h + h, 10.0)
