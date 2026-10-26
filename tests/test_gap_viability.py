"""Model-level contracts, not an empirical road-safety certification."""

from dataclasses import replace
import pytest
from metroflow.stopping_envelope import motion, maximum_closure, hold_brake
from metroflow.gap_transport import PairBin, PairState, LeaderReport, control, step, ViabilityError
from metroflow.foundation_kinetics import VehicleClass


def test_transient_closure_is_not_final_stop_difference():
    peak, t = maximum_closure(20.0, 15.0, -8.0, 0.5, 8.0, 2.0)
    assert peak == pytest.approx(25 / 12) and t == pytest.approx(5 / 6)
    assert hold_brake(20.0, -8.0, 0.5, 8.0, 100.0)[0] - motion(15.0, -2.0, 100.0)[0] < 0


def test_delayed_reaction_and_stopped_leader_match_map_envelope():
    peak, _ = maximum_closure(10.0, 0.0, 2.0, 2.0, 4.0, 6.0)
    assert peak == pytest.approx(48.5)


def test_motion_stops_continuously_without_reverse_travel():
    assert motion(10.0, -5.0, 3.0) == pytest.approx((10.0, 0.0))
    assert motion(10.0, -5.0, 1.0) == pytest.approx((7.5, 5.0))


def test_gap_changes_by_relative_displacement_and_preserves_weight():
    c = VehicleClass()
    b = PairBin(c, 100.0, 100.0, 10.0, 5.0)
    s = PairState(0.0, (b,))
    n, proof = step(s, (LeaderReport(0.0, 5.0),), (0.0,), 0.5, 20.0, 6.0)
    old = b
    new = n.bins[0]
    assert new.h == pytest.approx(old.h + 5 * 0.5 - (new.x - old.x))
    assert new.h < old.h and new.mass == old.mass
    assert s.bins[0].h == 100.0


def test_filter_prevents_crossing_under_immediate_leader_braking():
    c = VehicleClass(brake_mps2=5.0)
    s = PairState(0.0, (PairBin(c, 1.0, 45.0, 20.0, 15.0),))
    for _ in range(60):
        report = LeaderReport(s.time_s, s.bins[0].w)
        s, proof = step(s, (report,), (-6.0,), 0.2, 25.0, 6.0)
        assert proof[0]["min_gap_m"] >= c.min_gap_m - 1e-8
        assert 0 <= s.bins[0].v
    assert s.bins[0].v < 1e-6


def test_empty_robust_certificate_preserves_checkpoint_not_teleport():
    s = PairState(0.0, (PairBin(VehicleClass(), 5.0, 3.0, 20.0, 0.0),))
    with pytest.raises(ViabilityError) as caught:
        step(s, (LeaderReport(0.0, 0.0),), (0.0,), 0.5, 20.0, 6.0)
    assert caught.value.checkpoint == s
    assert s.bins[0].x == 0 and s.bins[0].h == 3


def test_control_cannot_read_hidden_leader_truth():
    c = VehicleClass()
    report = LeaderReport(0.0, 12.0)
    a = PairBin(c, 1.0, 40.0, 10.0, 9.0)
    b = replace(a, w=20.0)
    assert control(a, report, 1.0, 0.5, 20.0, 6.0) == control(b, report, 1.0, 0.5, 20.0, 6.0)


def test_leader_velocity_bound_uses_age_and_response_is_nonanticipative():
    b = PairBin(VehicleClass(), 1.0, 40.0, 15.0, 15.0)
    report = LeaderReport(0.0, 15.0)
    fresh = control(b, report, 0.0, 0.5, 20.0, 6.0)
    stale = control(b, report, 1.0, 0.5, 20.0, 6.0)
    assert stale <= fresh


def test_mass_scaling_does_not_create_more_phase_nodes():
    bins = (
        PairBin(VehicleClass(), 0.5, 50.0, 10.0, 8.0),
        PairBin(VehicleClass("truck", 15.0, 4.0, 0.7, 2.0, 3.0, 1.5, 12.0), 0.5, 100.0, 10.0, 8.0),
    )
    a = PairState(0.0, bins)
    b = PairState(0.0, tuple(replace(x, mass=x.mass * 100000) for x in bins))
    for _ in range(20):
        reports = tuple(LeaderReport(a.time_s, x.w) for x in a.bins)
        a, _ = step(a, reports, (0.0, 0.0), 0.25, 20.0, 6.0)
        b, _ = step(b, reports, (0.0, 0.0), 0.25, 20.0, 6.0)
    assert len(a.bins) == len(b.bins) == 2
    assert sum(x.mass for x in b.bins) == 100000
    assert [(x.h, x.v, x.w, x.x) for x in a.bins] == [(x.h, x.v, x.w, x.x) for x in b.bins]


def test_delayed_report_history_and_emergency_recovery():

    c = VehicleClass(brake_mps2=5.0)
    s = PairState(0.0, (PairBin(c, 100.0, 65.0, 20.0, 15.0),))
    history = [LeaderReport(0.0, 15.0)]
    for k in range(120):
        available = [r for r in history if r.stamp_s <= s.time_s - 1.0]
        r = available[-1] if available else history[0]
        aL = -6.0 if 3.0 <= s.time_s < 6.0 else 1.0 if 8.0 <= s.time_s < 13.0 else 0.0
        s, proof = step(s, (r,), (aL,), 0.25, 20.0, 6.0)
        assert proof[0]["min_gap_m"] >= 2.0 - 1e-8
        history.append(LeaderReport(s.time_s, s.bins[0].w))
    assert s.bins[0].w == pytest.approx(5.0)
    assert s.bins[0].x > 0 and sum(b.mass for b in s.bins) == 100.0


def test_invalid_observation_and_disturbance_are_not_silently_accepted():
    from metroflow.gap_transport import lower_speed

    s = PairState(0.0, (PairBin(VehicleClass(), 1.0, 50.0, 10.0, 5.0),))
    with pytest.raises(ValueError, match="future"):
        control(s.bins[0], LeaderReport(1.0, 5.0), 0.0, 0.2, 20.0, 6.0)
    with pytest.raises(ValueError, match="contradicts"):
        step(s, (LeaderReport(0.0, 15.0),), (0.0,), 0.2, 20.0, 6.0)
    with pytest.raises(ValueError, match="lower acceleration"):
        step(s, (LeaderReport(0.0, 5.0),), (-7.0,), 0.2, 20.0, 6.0)
    assert lower_speed(None, 0.0, 6.0) == 0.0


def test_unrestricted_envelope_matches_dense_independent_evaluation():
    import random

    rng = random.Random(513)

    def advance(v, a, t):
        if a < 0 and t >= v / (-a):
            return v * v / (-2 * a)
        return v * t + 0.5 * a * t * t

    for _ in range(60):
        v, w = rng.uniform(0.0, 30.0), rng.uniform(0.0, 30.0)
        b, B = rng.uniform(1.0, 8.0), rng.uniform(1.0, 8.0)
        a, dt = rng.uniform(-b, 3.0), rng.uniform(0.0, 3.0)
        end = max(w / B, dt + max(0.0, v + a * dt) / b)
        exact, _ = maximum_closure(v, w, a, dt, b, B)
        values = []
        for k in range(1001):
            t = end * k / 1000
            xf = advance(v, a, min(t, dt))
            if t > dt:
                xf += advance(max(0.0, v + a * dt), -b, t - dt)
            values.append(xf - advance(w, -B, t))
        sampled = max(values)
        assert exact >= sampled - 1e-9
        assert exact - sampled <= (v + max(0.0, a) * dt + w) * end / 1000 + 1e-9


def test_no_hidden_per_mass_loops_and_class_specific_moments():
    from metroflow.gap_transport import moments

    c = VehicleClass()
    a = PairState(0.0, (PairBin(c, 1.0, 30.0, 10.0, 10.0), PairBin(c, 1.0, 70.0, 10.0, 10.0)))
    b = PairState(0.0, (PairBin(c, 2.0, 50.0, 10.0, 10.0),))
    assert moments(a) == moments(b)
    # Change headway target to place one bin below and one above the speed cap.
    a = replace(a, bins=tuple(replace(p, h=p.h - 20.0) for p in a.bins))
    b = replace(b, bins=(replace(b.bins[0], h=30.0),))
    a, _ = step(a, (LeaderReport(0.0, 10.0),) * 2, (0.0, 0.0), 0.2, 20.0, 6.0)
    b, _ = step(b, (LeaderReport(0.0, 10.0),), (0.0,), 0.2, 20.0, 6.0)
    assert moments(a)["mean_v"] != pytest.approx(moments(b)["mean_v"])
    assert moments(a)["variance_v"] > 0


def test_first_passage_is_from_same_continuous_applied_trajectory():
    # No new tick-delay is allowed when measuring a segment inside a held step.
    from metroflow.stopping_envelope import passage_in_interval

    assert passage_in_interval(10.0, 0.0, 3.0, 2.0) == pytest.approx(0.3)
    assert passage_in_interval(0.0, 2.0, 1.0, 2.0) == pytest.approx(1.0)
    assert passage_in_interval(10.0, -5.0, 10.0, 3.0) == pytest.approx(2.0, abs=1e-7)
    assert passage_in_interval(10.0, -5.0, 11.0, 3.0) is None
