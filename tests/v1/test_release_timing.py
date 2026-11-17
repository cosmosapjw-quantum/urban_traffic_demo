"""release_interval_v1: in-step release, atom-aligned access rows, in-step arrivals.

Legacy evaluates the departure fraction and the access deadline at the step
start and the road admits a tick-start source only at the step end. The opt-in
policy releases each birth inside its own step, creates one access row per atom
whose individual ready times all fall in one step, and offers it to the road
source queue at its mean ready time inside that step. These tests compare both
timings, the Python oracle and both native road backends, and the whole engine.
"""
from dataclasses import replace
import json
import math
from types import SimpleNamespace

import pytest
from _metroflow_rust import NativeJourneyCore, NativeWholeEngine

from metroflow.active_suffix.common import BudgetExceeded
from metroflow.v1.activity import compile_activity
from metroflow.v1.city import CityContractError
from metroflow.v1.joint_release_runtime import JointReleaseRuntime
from metroflow.v1.native_journey import NativeJointReleaseRuntime
from metroflow.v1.release_services import compile_service_plan
from metroflow.v1.schedules import DepartureProfile, DepartureWindow
from test_joint_release_runtime import fixture
from test_native_engine import assert_oracle, make_native
from test_native_journey import assert_same

POLICY = "release_interval_v1"
STEP = 10.0


def core(delays, interval, amount=1.0):
    legs = [(f"leg{k}", amount, None, 0., [(0., 100., 1.)], 1, [(d, 1.)], [(0., 1.)])
            for k, d in enumerate(delays)]
    return NativeJourneyCore(legs, [], [], 100000,
                             release_timing=POLICY if interval else "legacy")


def tick(journey):
    t = journey.snapshot()[0]
    if journey.release_timing == POLICY:
        offers, _, arrivals = journey.prepare_interval(STEP)
    else:
        offers, _ = journey.prepare()
        arrivals = [t] * len(offers)
    journey.finish(t + STEP, [], [], [], [], [], [], [])
    return t, offers, arrivals


def uniform(t):
    return min(1., max(0., t / 100.))


def test_legacy_release_lags_one_step_and_policy_is_exact_at_grid_times():
    legacy, interval = core([0.], False), core([0.], True)
    for k in range(1, 8):
        tick(legacy)
        tick(interval)
        grid = k * STEP
        # Counterexample to exact release: legacy holds A*F(T - dt) at T.
        assert legacy.snapshot()[4][0] == pytest.approx(uniform(grid - STEP), abs=1e-12)
        assert interval.snapshot()[4][0] == pytest.approx(uniform(grid), abs=1e-12)
    assert legacy.release_timing == "legacy" and interval.release_timing == POLICY


def test_policy_offers_exactly_the_mass_ready_by_each_step_end_and_never_earlier():
    delays = (0., 3., 14., 20., 27.5)
    legacy, interval = core(delays, False), core(delays, True)
    offered = [0.] * len(delays)
    legacy_offered = [0.] * len(delays)
    for k in range(14):
        t, offers, arrivals = tick(interval)
        _, old, _ = tick(legacy)
        end = t + STEP
        for (tag, mass, birth), arrival in zip(offers, arrivals):
            i = int(tag[3:])
            assert t <= arrival <= end
            assert birth <= mass * arrival
            # Arrival moment = birth moment + mass * access delay.
            assert mass * arrival == pytest.approx(birth + mass * delays[i], rel=1e-12, abs=1e-12)
            offered[i] += mass
        for tag, mass, _ in old:
            legacy_offered[int(tag[3:])] += mass
        for i, d in enumerate(delays):
            ready = uniform(end - d)
            assert offered[i] == pytest.approx(ready, abs=1e-12)
            assert legacy_offered[i] <= ready + 1e-12
        if k == 4:
            assert all(o - l > 0.05 for o, l in zip(offered, legacy_offered))


def test_unstaged_access_closes_released_offered_and_staged_ledger():
    delays = (0., 3., 14., 27.5)
    interval = core(delays, True, amount=3.)
    offered = [0.] * len(delays)
    for _ in range(13):
        _, offers, _ = tick(interval)
        for tag, mass, _ in offers:
            offered[int(tag[3:])] += mass
        t, entering, _, _, released, *_ = interval.snapshot()
        unstaged = interval.unstaged_access(STEP)
        for i, d in enumerate(delays):
            staged = math.fsum(row[1] for row in entering if row[0] == i)
            assert unstaged[i] == pytest.approx(3. * (uniform(t) - uniform(t - math.fmod(d, STEP))), abs=1e-12)
            assert released[i] == pytest.approx(offered[i] + staged + unstaged[i], abs=1e-12)
            assert all(row[2] + row[3] > t for row in entering if row[0] == i)
    assert core(delays, False).unstaged_access(STEP) == [0.] * len(delays)


def test_unknown_release_timing_and_wrong_entry_point_are_rejected():
    with pytest.raises(ValueError, match="release_timing"):
        core([0.], True).__class__([], [], [], 10, release_timing="release_interval")
    with pytest.raises(ValueError, match="prepare_interval"):
        core([0.], True).prepare()
    with pytest.raises(ValueError, match="release_interval_v1"):
        core([0.], False).prepare_interval(STEP)
    with pytest.raises(ValueError, match="release_timing"):
        JointReleaseRuntime(*fixture(), release_timing="early")


def delayed_fixture(step_s=5.):
    """Car journey with fractional access/egress delay atoms and its return."""
    city, legs, _ = fixture()
    home = compile_activity(city, "block")
    work = compile_activity(city, "work", "job")
    car = replace(legs[0], origin=home, destination=work,
                  departures=DepartureProfile((DepartureWindow(0, 30),)))
    back = replace(legs[1], origin=work, destination=home)
    custom = (car, back)
    plan = compile_service_plan(city, custom, (), depot_block_id="block", step_s=step_s)
    return city, custom, plan


@pytest.mark.parametrize("road_backend", ["python_oracle", "rust"])
@pytest.mark.parametrize("case", ["fixture", "delayed"])
def test_policy_native_journey_matches_python_oracle(road_backend, case):
    if case == "fixture":
        city, legs, plan = fixture()
        step, end = 1., 120.
    else:
        city, legs, plan = delayed_fixture()
        step, end = 5., 900.
    oracle = JointReleaseRuntime(city, legs, plan, step_s=step, release_timing=POLICY)
    native = NativeJointReleaseRuntime(city, legs, plan, step_s=step, road_backend=road_backend,
                                       release_timing=POLICY)
    expected = oracle.advance(oracle.initial(), end)
    actual = native.advance(native.initial(), end)
    assert_same(actual, expected)
    assert_same(native.report(actual), oracle.report(expected))
    legacy = JointReleaseRuntime(city, legs, plan, step_s=step)
    assert oracle.identity != legacy.identity
    if case == "delayed":
        old = legacy.advance(legacy.initial(), end)
        # The child return is executed; both timings complete the outward trip.
        assert expected.completed[1] > 0
        assert expected.completed[0] == pytest.approx(old.completed[0], abs=1e-12)


def test_policy_releases_top_level_births_exactly_at_grid_times():
    city, legs, plan = delayed_fixture()
    oracle = JointReleaseRuntime(city, legs, plan, step_s=5., release_timing=POLICY)
    legacy = JointReleaseRuntime(city, legs, plan, step_s=5.)
    a, b = legacy.initial(), oracle.initial()
    for k in range(1, 8):
        a, b = legacy.advance(a, 5. * k), oracle.advance(b, 5. * k)
        carrier = legs[0].amounts.vehicles
        exact = carrier * legs[0].departures.fraction(0, 5. * k)
        assert b.released[0] == pytest.approx(exact, abs=1e-12)
        assert a.released[0] == pytest.approx(carrier * legs[0].departures.fraction(0, 5. * (k - 1)), abs=1e-12)
        # Requested = released + pending holds by construction for both.
        led = oracle.report(b)["ledger"]["vehicles"]
        assert led["requested"] - led["released"] == pytest.approx(led["pending"], abs=1e-12)


def test_policy_checkpoint_save_load_resume_and_binding(tmp_path):
    city, legs, plan = delayed_fixture()
    oracle = JointReleaseRuntime(city, legs, plan, step_s=5., release_timing=POLICY)
    native = NativeJointReleaseRuntime(city, legs, plan, step_s=5., release_timing=POLICY)
    middle_o = oracle.advance(oracle.initial(), 240.)
    middle_n = native.advance(native.initial(), 240.)
    a, b = tmp_path / "oracle.json", tmp_path / "native.json"
    oracle.save(a, middle_o)
    native.save(b, middle_n)
    direct = oracle.advance(middle_o, 600.)
    assert_same(oracle.advance(oracle.load(a), 600.), direct)
    assert_same(native.advance(native.load(a), 600.), direct)
    assert_same(oracle.advance(oracle.load(b), 600.), direct)
    legacy = JointReleaseRuntime(city, legs, plan, step_s=5.)
    old = tmp_path / "legacy.json"
    legacy.save(old, legacy.advance(legacy.initial(), 240.))
    with pytest.raises(CityContractError, match="identity"):
        oracle.load(old)
    with pytest.raises(CityContractError, match="identity"):
        legacy.load(a)


@pytest.mark.parametrize("road_backend", ["python_oracle", "rust"])
def test_policy_budget_failure_keeps_last_valid_checkpoint(road_backend):
    city, legs, plan = delayed_fixture()
    native = NativeJointReleaseRuntime(city, legs, plan, step_s=5., record_budget=12,
                                       road_backend=road_backend, release_timing=POLICY)
    with pytest.raises(BudgetExceeded) as failure:
        native.advance(native.initial(), 900.)
    checkpoint = failure.value.checkpoint
    native.check(checkpoint)
    assert 0. < checkpoint.time_s < 900.
    # The oracle with the same record budget fails at the same complete tick.
    oracle = JointReleaseRuntime(city, legs, plan, step_s=5., record_budget=12,
                                 release_timing=POLICY)
    with pytest.raises(BudgetExceeded) as reference:
        oracle.advance(oracle.initial(), 900.)
    assert_same(checkpoint, reference.value.checkpoint)


def test_python_road_accepts_in_step_arrivals_and_rejects_causality_violations():
    city, legs, plan = fixture()
    oracle = JointReleaseRuntime(city, legs, plan)
    network = oracle.service.network
    state = network.initial()
    out, _ = network.advance_interval(state, 1., [("car", 2., 2. * .25, .5)])
    assert out.pre_entry_seconds == pytest.approx(2. * .5 - .5, abs=0)
    assert out.source_wait_seconds == pytest.approx(2. * 1. - 2. * .5, abs=0)
    assert out.released == 2.
    for offer in [("car", 2., .5, 1.5), ("car", 2., .5, .1), ("car", 2., .5, float("nan"))]:
        with pytest.raises(ValueError, match="source"):
            network.advance_interval(state, 1., [offer])
    with pytest.raises(ValueError, match="source"):
        network.advance_interval(state, 1., [("car", 2., .5)])  # legacy source born later


def test_python_and_native_road_agree_on_in_step_arrivals():
    from metroflow.v1.native_road import NativeRoadNetwork

    city, legs, plan = fixture()
    reference = JointReleaseRuntime(city, legs, plan).service.network
    native = NativeRoadNetwork(reference)
    offers = [("car", 2., 2. * .25, .5), ("return", 1., 0.)]
    expected, events = reference.advance_interval(reference.initial(), 1., offers)
    actual, native_events = native.advance_interval(native.initial(), 1., offers)
    assert_same(actual, expected)
    assert_same(native_events, events)
    for _ in range(3):
        t = expected.time_s
        offer = [("car", 1., 1. * (t + .5), t + .75)]
        expected, _ = reference.advance_interval(expected, 1., offer)
        actual, _ = native.advance_interval(actual, 1., offer)
    assert_same(actual, expected)
    assert expected.pre_entry_seconds > 0


def whole(city, legs, release_timing, **kwargs):
    _, calendar, payload = make_native(city, legs, **kwargs)
    return NativeWholeEngine(calendar, payload, 256 * 1024**2, release_timing=release_timing)


@pytest.mark.parametrize("case", ["fixture", "delayed"])
def test_whole_engine_policy_matches_oracle_and_binds_identity(tmp_path, case):
    if case == "fixture":
        city, legs, _ = fixture()
        legs, end, corridors = (legs[0], legs[1], legs[4]), 120., ()
    else:
        city, legs, _ = delayed_fixture(step_s=1.)
        end, corridors = 900., ()
    plan = compile_service_plan(city, legs, corridors, depot_block_id="block", step_s=1)
    oracle = JointReleaseRuntime(city, legs, plan, release_timing=POLICY)
    native = whole(city, legs, POLICY)
    legacy = whole(city, legs, "legacy")
    assert native.release_timing == POLICY and legacy.release_timing == "legacy"
    assert native.identity == legacy.identity + ":" + POLICY
    assert native.execution_config()["release_timing"] == POLICY
    middle = native.advance(native.initial(), end / 3)
    actual = native.advance(middle, end)
    expected = oracle.advance(oracle.initial(), end)
    assert_oracle(native, actual, oracle, expected)
    ledger = native.road_ledger(actual)
    assert ledger["mass_residual_rel"] <= 1e-9 and ledger["residence_residual_rel"] <= 1e-8
    assert ledger["pre_entry_veh_s"] == pytest.approx(expected.service.road.pre_entry_seconds, rel=1e-12, abs=1e-9)
    path = tmp_path / "policy.bin"
    native.save(str(path), middle)
    restored = native.load(str(path))
    assert native.report(native.advance(restored, end)) == native.report(actual)
    legacy_path = tmp_path / "legacy.bin"
    legacy.save(str(legacy_path), legacy.initial())
    with pytest.raises(ValueError, match="binding"):
        native.load(str(legacy_path))
    with pytest.raises(ValueError, match="binding"):
        legacy.load(str(path))
    with pytest.raises(ValueError, match="release_timing"):
        whole(city, legs, "interval")


def test_whole_engine_policy_budget_failure_rolls_back_to_valid_state():
    city, legs, _ = delayed_fixture(step_s=1.)
    limited = whole(city, legs, POLICY, record_budget=12)
    initial = limited.initial()
    with pytest.raises(MemoryError, match="budget"):
        limited.advance(initial, 900.)
    snapshot = limited.snapshot()
    limited.check(snapshot)
    assert 0. < snapshot.time_s < 900.
    plan = compile_service_plan(city, legs, (), depot_block_id="block", step_s=1)
    oracle = JointReleaseRuntime(city, legs, plan, release_timing=POLICY)
    expected = oracle.advance(oracle.initial(), snapshot.time_s)
    assert_oracle(limited, snapshot, oracle, expected)
    assert initial.time_s == 0.


def test_campaign_cli_forwards_release_timing(tmp_path, monkeypatch):
    import tools.run_v1_local_acceptance as cli

    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps(dict(cases=[dict(id="case")], limits=dict(wall_s=1))))
    seen = []

    def capture(cmd, **kwargs):
        seen.append(cmd)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(cli.subprocess, "run", capture)
    monkeypatch.setattr(cli.sys, "argv", ["runner", "--run-local", "--matrix", str(matrix),
                                          "--out", str(tmp_path), "--release-timing", POLICY])
    assert cli.main() == 2
    assert all(cmd[cmd.index("--release-timing") + 1] == POLICY for cmd in seen)
    monkeypatch.setattr(cli.sys, "argv", ["runner", "--run-local", "--matrix", str(matrix),
                                          "--out", str(tmp_path), "--release-timing", POLICY,
                                          "--engine-backend", "python_oracle"])
    with pytest.raises(SystemExit):
        cli.main()
