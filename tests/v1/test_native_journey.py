"""Native scheduling/journey contracts against the existing scientific oracle.

These tests explicitly use the Python road to isolate the new scheduling layer.
The native driver suite separately combines it with the Rust physical owner.
"""
from dataclasses import asdict, is_dataclass, replace
import math

import pytest
from _metroflow_rust import NativeJourneyCore, NativeServiceCore

from metroflow.active_suffix.common import BudgetExceeded
from metroflow.v1.activity import compile_activity
from metroflow.v1.joint_release_runtime import JointReleaseRuntime
from metroflow.v1.native_journey import NativeJointReleaseRuntime
from metroflow.v1.release_services import BusCorridor, compile_service_plan
from metroflow.v1.schedules import DepartureProfile, DepartureWindow
from test_joint_release_runtime import fixture


def assert_same(actual, expected):
    if is_dataclass(actual):
        return assert_same(asdict(actual), asdict(expected))
    if isinstance(actual, dict):
        assert actual.keys() == expected.keys()
        for key in actual:
            assert_same(actual[key], expected[key])
    elif isinstance(actual, (tuple, list)):
        assert len(actual) == len(expected)
        for x, y in zip(actual, expected):
            assert_same(x, y)
    elif isinstance(actual, float):
        assert math.isclose(actual, expected, rel_tol=2e-12, abs_tol=2e-10), (actual, expected)
    else:
        assert actual == expected


def compare(city, legs, plan, end):
    oracle = JointReleaseRuntime(city, legs, plan)
    native = NativeJointReleaseRuntime(city, legs, plan, road_backend="python_oracle")
    expected = oracle.advance(oracle.initial(), end)
    actual = native.advance(native.initial(), end)
    assert_same(actual, expected)
    assert_same(native.report(actual), oracle.report(expected))
    return native, actual, oracle, expected


def test_native_shared_service_journey_checkpoint_and_rewind(tmp_path):
    native, actual, oracle, expected = compare(*fixture(), 120)
    assert actual.released[3] == 0  # Dependent bus left before return eligibility.
    assert actual.completed[4] == pytest.approx(1)
    a, b = tmp_path / "native.json", tmp_path / "oracle.json"
    native.save(a, actual)
    oracle.save(b, expected)
    assert_same(native.load(b), expected)
    assert_same(oracle.load(a), actual)
    assert_same(native.advance(native.load(b), 125), oracle.advance(expected, 125))
    # Reuse the same native owner after rewinding to zero; no residual service state.
    assert_same(native.advance(native.initial(), 120), expected)


def test_native_egress_preserves_whole_journey_delay():
    city, legs, _ = fixture()
    target = compile_activity(city, "work", "job")
    legs = tuple(replace(legs[i], destination=target) for i in (0, 2, 4))
    plan = compile_service_plan(city, legs, (BusCorridor("out", "block", "work", 3, 50),),
                                depot_block_id="block")
    _, state, _, _ = compare(city, legs, plan, 30)
    assert state.egress and state.completed[0] < 1


def test_native_multiwindow_bus_uses_calendar_to_window_person_ratio():
    city, legs, _ = fixture()
    bus = replace(legs[2], departures=DepartureProfile((DepartureWindow(0, 2, .25),
                                                       DepartureWindow(3, 4, .75))))
    plan = compile_service_plan(city, (bus,),
        (BusCorridor("early", "block", "work", 3, 50),
         BusCorridor("late", "block", "work", 5, 50)), depot_block_id="block")
    _, state, _, _ = compare(city, (bus,), plan, 120)
    assert state.completed[0] == pytest.approx(1)
    assert state.birth_carrier_s[0] == pytest.approx(.25*1+.75*3.5)


def test_native_internal_and_unassigned_activity_stays_pending():
    from metroflow.v1.journey import DelayLaw
    city, legs, _ = fixture()
    internal = replace(legs[0], destination=legs[0].origin, intrazonal=DelayLaw(((2., .3), (5., .7))))
    unsupported = replace(legs[0], id="walk", mode="noncar", vehicle_class=None)
    plan = compile_service_plan(city, (internal, unsupported))
    _, state, _, _ = compare(city, (internal, unsupported), plan, 10)
    assert state.completed == pytest.approx((1, 0))
    assert state.service.road.released == 0


def test_native_service_proportional_boarding_partial_sink_and_dwell():
    core = NativeServiceCore([("b", [0., 5.], 10., 3.)],
        [(0, 0, 1, 0., 8.), (0, 0, 2, 0., 12.)], [("f", 2., .5)], [])
    initial = core.snapshot()
    assert core.prepare(0., [True, True]) == [("bus:b:0", 1., 0.)]
    assert core.snapshot() == initial  # Prepared boarding is not committed yet.
    core.finish(1., [("bus:b:0", .4, .7)])
    runs, people, released, completed, _ = core.snapshot()
    assert people[0][:3] == (4., 4., 0.)
    assert people[1][:3] == (6., 6., 0.)
    assert runs[0][1] == 1 and runs[0][3] == .4
    assert core.prepare(1., [True, True]) == []
    core.finish(2., [("bus:b:0", .6, 1.9)])
    assert core.snapshot()[0][0][:3] == (1, 0, 5.)
    assert core.snapshot()[1][0][:3] == (4., 0., 4.)
    assert core.prepare(2., [True, True]) == [("freight:f", .5, 1.)]
    core.abort()
    assert core.snapshot()[2] == [False]
    core.restore(initial)
    assert core.snapshot() == initial


def test_native_service_bad_finish_preserves_committed_state():
    core = NativeServiceCore([], [], [("f", 0., 1.)], [])
    before = core.snapshot()
    core.prepare(0., [])
    with pytest.raises(ValueError):
        core.finish(1., [("freight:f", 2., 1.)])
    assert core.snapshot() == before
    core.abort()
    assert core.prepare(0., []) == [("freight:f", 1., 0.)]


def test_native_service_finite_cohorts_cannot_hide_aggregate_overflow():
    core = NativeServiceCore([("b", [0.], 10., 0.)],
        [(0, 0, 1, 0., 1e308), (0, 0, 1, 0., 1e308)], [], [])
    before = core.snapshot()
    with pytest.raises(ValueError, match="overflow"):
        core.prepare(0., [True, True])
    assert core.snapshot() == before


def test_native_boarding_boundary_preserves_reference_clock_tolerance():
    core = NativeServiceCore([("b", [0.], 1., 0.)], [(0, 0, 1, 5e-11, 1.)], [], [])
    assert core.prepare(0., [True]) == [("bus:b:0", 1., 0.)]
    core.finish(1., [])
    assert core.snapshot()[1][0][3] == -5e-11


@pytest.mark.parametrize("road_backend", ["python_oracle", "rust"])
def test_native_journey_over_budget_preserves_valid_checkpoint(road_backend):
    from metroflow.v1.journey import DelayLaw
    city, legs, _ = fixture()
    leg = replace(legs[0], destination=legs[0].origin, intrazonal=DelayLaw(((0., .5), (1., .5))))
    plan = compile_service_plan(city, (leg,))
    native = NativeJointReleaseRuntime(city, (leg,), plan, record_budget=1,
                                      road_backend=road_backend)
    with pytest.raises(BudgetExceeded) as failure:
        native.advance(native.initial(), 5)
    checkpoint = failure.value.checkpoint
    native.check(checkpoint)
    assert checkpoint.time_s == 1
    assert checkpoint.released == (0.,)


def test_native_journey_rejects_nan_profile_and_missing_phase():
    leg = ("x", 1., None, 0., [(0., 1., float("nan"))], 0, [], [])
    with pytest.raises(ValueError):
        NativeJourneyCore([leg], [], [], 10)
    core = NativeJourneyCore([], [], [], 10)
    with pytest.raises(ValueError, match="without prepare"):
        core.finish(1., [], [], [], [], [], [], [])


def test_unknown_road_backend_is_rejected():
    with pytest.raises(ValueError, match="road_backend"):
        NativeJointReleaseRuntime(*fixture(), road_backend="typo")


def test_coupled_native_loop_never_calls_python_tick_methods(monkeypatch):
    city, legs, plan = fixture()
    oracle = JointReleaseRuntime(city, legs, plan)
    native = NativeJointReleaseRuntime(city, legs, plan)

    def forbidden(*args, **kwargs):
        raise AssertionError("Python per-tick method called")

    monkeypatch.setattr(native.service, "step", forbidden)
    monkeypatch.setattr(native.service.network, "advance_interval", forbidden)
    actual = native.advance(native.initial(), 120)
    expected = oracle.advance(oracle.initial(), 120)
    assert_same(actual, expected)
    # Coarse calls retain their final physical events and can resume or rewind.
    assert_same(native.advance(actual, 125), oracle.advance(expected, 125))
    assert_same(native.advance(native.initial(), 120), expected)


def test_coupled_native_metrics_count_and_peak_match_observed_complete_ticks():
    city, legs, plan = fixture()
    oracle = JointReleaseRuntime(city, legs, plan)
    native = NativeJointReleaseRuntime(city, legs, plan)
    state = oracle.initial()
    peak = 0
    for t in range(1, 121):
        state = oracle.advance(state, t)
        road = state.service.road
        records = sum(len(q.parts) for c in road.cells for q in c.packets)
        records += sum(len(q.parts) for queue in road.pending for q in queue)
        records += len(state.entering)+len(state.egress)+len(state.internal)+sum(map(len, state.receipts))
        peak = max(peak, records)
    actual = native.advance(native.initial(), 120)
    assert_same(actual, state)
    metrics = native.last_advance_metrics
    assert len(metrics["tick_times_s"]) == 120
    assert all(math.isfinite(t) and t >= 0 for t in metrics["tick_times_s"])
    assert metrics["peak_records"] == peak
    assert "excludes frontend" in metrics["scope"]
    native.advance(actual, 125)
    assert len(native.last_advance_metrics["tick_times_s"]) == 5  # Per call, not cumulative.
