"""Whole native construction against a small, independent Python joint oracle.

Small explicit legs here are test declarations only. Production construction is
also checked with every Python Cartesian iterator disabled.
"""

from dataclasses import asdict, replace
import hashlib
import json
import math
from types import SimpleNamespace

import pytest
from _metroflow_rust import NativeWholeEngine

from metroflow.v1.demand import Amounts
from metroflow.v1.factorized_demand import FactorizedSchedule, compile_factorized_demand
from metroflow.v1.joint_release_runtime import JointReleaseRuntime
from metroflow.v1.journey import DelayLaw
from metroflow.v1.native_calendar import compile_native_calendar, compile_native_factorized_calendar
from metroflow.v1.native_static import prepare_native_static
from metroflow.v1.release_inventory import InventoryPolicy, ReleaseInventory
from metroflow.v1.release_runtime import ReleaseRuntime
from metroflow.v1.release_services import BusCorridor, compile_service_plan
from metroflow.v1.schedules import DepartureProfile, DepartureWindow
from test_joint_release_runtime import fixture


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def small_fixture():
    city, legs, _ = fixture()
    corridors = (BusCorridor("out", "block", "work", 3, 50),
                 BusCorridor("back", "work", "block", 5, 50))
    return city, legs, corridors


def make_native(city, legs, corridors=(), depot="block", record_budget=20000):
    """Use the real marginal frontend with an explicit test calendar binding."""
    legs = tuple(legs)
    measures = tuple(dict.fromkeys(m for leg in legs for m in (leg.origin, leg.destination)
                                  if m is not None))
    home = next(m for m in measures if m.kind == "residential")
    jobs = tuple(m for m in measures if m.kind == "job")
    services = tuple(m for m in measures if m.kind == "service")
    schedule = compile_factorized_demand((home,), jobs, services,
                                         worker_fraction=0, service_fraction=0)
    inventory = ReleaseInventory(city.identity, InventoryPolicy(), (), tuple(corridors),
                                 depot, _digest([asdict(c) for c in corridors]))
    payload = prepare_native_static(city, schedule, inventory, step_s=1,
                                    record_budget=record_budget)
    binding = _digest([asdict(leg) for leg in legs])
    source = SimpleNamespace(city_identity=city.identity, identity=binding,
                             iter_legs=lambda: iter(legs))
    calendar = compile_native_calendar(source)
    payload["schedule_identity"] = binding
    payload["intrazonal_laws"] = list({
        json.dumps(asdict(leg.intrazonal), sort_keys=True, allow_nan=False): leg.intrazonal.atoms
        for leg in legs if leg.intrazonal is not None
    }.items())
    payload.pop("identity")
    payload["identity"] = _digest(payload)
    return NativeWholeEngine(calendar, payload, 256 * 1024**2), calendar, payload


def assert_numeric(actual, expected):
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            assert_numeric(actual[key], expected[key])
    elif isinstance(expected, (tuple, list)):
        assert len(actual) == len(expected)
        for a, b in zip(actual, expected):
            assert_numeric(a, b)
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        assert math.isclose(actual, expected, rel_tol=2e-10, abs_tol=2e-9), (actual, expected)
    else:
        assert actual == expected


def assert_oracle(native, actual, oracle, expected):
    report, reference = native.report(actual), oracle.report(expected)
    for key in ("time_s", "ledger", "released_intent_first_moments", "service", "assignment"):
        assert_numeric(report[key], reference[key])
    assert_numeric(native.sample_legs(actual, list(range(len(oracle.legs)))), [
        (leg.id, expected.released[i], expected.completed[i], expected.birth_carrier_s[i])
        for i, leg in enumerate(oracle.legs)
    ])
    assert report["construction"]["unsupported_legs"] == len(oracle.unsupported)
    assert report["construction"]["road_legs"] == len(oracle.routes)
    assert report["construction"]["internal_legs"] == len(oracle.internal_laws)
    assert report["construction"]["road_owners"] == 1
    assert report["construction"]["python_calendar_leg_objects"] == 0


def oracle_for(city, legs, corridors=(), depot="block"):
    plan = compile_service_plan(city, legs, corridors, depot_block_id=depot, step_s=1)
    return JointReleaseRuntime(city, legs, plan)


def test_native_whole_mixed_initial_progress_branch_and_restart(tmp_path):
    city, legs, corridors = small_fixture()
    oracle = oracle_for(city, legs, corridors)
    native, _, _ = make_native(city, legs, corridors)
    initial = native.initial()
    assert_oracle(native, initial, oracle, oracle.initial())
    at_30 = native.advance(initial, 30)
    early_report = native.report(at_30)
    expected = oracle.advance(oracle.initial(), 120)
    actual = native.advance(at_30, 120)
    assert_oracle(native, actual, oracle, expected)
    # A later advance/report cannot invalidate an earlier immutable snapshot.
    assert native.report(at_30) == early_report
    assert initial.time_s == 0 and at_30.time_s == 30 and actual.time_s == 120
    branch = native.advance(initial, 120)
    assert native.report(branch) == native.report(actual)
    samples = native.sample_legs(actual, list(range(5)))
    assert samples[3][1] == 0  # Return bus left before parent completion + dwell.
    assert [r[2] for r in samples] == pytest.approx((1, 1, 1, 0, 1))
    report = native.report(actual)
    assert report["ledger"]["persons"]["pending"] == pytest.approx(25)
    assert report["ledger"]["cargo_kg"]["completed"] == pytest.approx(100)
    # The assignment report belongs to the service compiler: cars remain
    # service-unassigned even though the shared journey owner executes them.
    assert report["assignment"]["units"]["persons"]["unassigned"] == pytest.approx(2.5)
    path = tmp_path / "whole.bin"
    native.save(str(path), at_30)
    restored = native.load(str(path))
    assert native.report(restored) == early_report
    assert native.report(native.advance(restored, 120)) == report


def test_native_whole_tied_buses_partial_assignment_and_freight_birth():
    city, legs, _ = small_fixture()
    profile = DepartureProfile((DepartureWindow(0, 2, .25), DepartureWindow(3, 4, .75)))
    bus = replace(legs[2], departures=profile)
    freight = replace(legs[4], departures=profile)
    corridors = (BusCorridor("tie-first", "block", "work", 2, 4),
                 BusCorridor("tie-second", "block", "work", 2, 4))
    custom = (bus, freight)
    oracle = oracle_for(city, custom, corridors)
    native, _, _ = make_native(city, custom, corridors)
    actual = native.advance(native.initial(), 120)
    expected = oracle.advance(oracle.initial(), 120)
    assert_oracle(native, actual, oracle, expected)
    report = native.report(actual)
    assert report["assignment"]["units"]["persons"]["assigned"] == pytest.approx(6.25)
    assert report["assignment"]["units"]["persons"]["unassigned"] == pytest.approx(18.75)
    samples = native.sample_legs(actual, [0, 1])
    assert samples[0][1:] == pytest.approx((.25, .25, .25))
    assert samples[1][1:] == pytest.approx((1., 1., .25 * 1. + .75 * 3.5))


def test_native_whole_internal_noncar_and_ordinary_noncar_pending():
    city, legs, _ = small_fixture()
    internal = replace(legs[0], mode="noncar", vehicle_class=None,
                       amounts=Amounts(persons=1.25), destination=legs[0].origin,
                       intrazonal=DelayLaw(((2., .3), (5., .7))))
    pending = replace(legs[0], id="walk", mode="noncar", vehicle_class=None,
                      amounts=Amounts(persons=2.))
    custom = (internal, pending)
    oracle = oracle_for(city, custom)
    native, _, _ = make_native(city, custom)
    actual = native.advance(native.initial(), 10)
    assert_oracle(native, actual, oracle, oracle.advance(oracle.initial(), 10))
    assert native.sample_legs(actual, [0, 1])[0][2] == pytest.approx(1.25)
    assert native.report(actual)["service"]["road_released_veh"] == 0


def test_native_whole_assignment_preserves_fsum_at_large_dynamic_range():
    city, legs, _ = small_fixture()
    custom = tuple(replace(legs[2], id=f"bus-{i}", cohort_id=f"b-{i}",
                           amounts=Amounts(persons=persons, vehicles=persons / 25))
                   for i, persons in enumerate((1e16, 1., 1.)))
    oracle = oracle_for(city, custom)
    native, _, _ = make_native(city, custom)
    # Exact comparison: ordinary left-fold addition loses both small cohorts.
    assert native.report(native.initial())["assignment"] == oracle.plan.assignment_report()


def test_native_whole_factorized_constructor_never_enters_python_od_graph(monkeypatch):
    from test_native_static import fixture as static_fixture

    city, schedule, inventory = static_fixture()

    def forbidden(*args, **kwargs):
        raise AssertionError("whole native construction entered the Python OD graph")

    for name in ("iter_records", "iter_legs", "iter_freight_legs"):
        monkeypatch.setattr(FactorizedSchedule, name, forbidden)
    monkeypatch.setattr(JointReleaseRuntime, "__init__", forbidden)
    monkeypatch.setattr(ReleaseRuntime, "__init__", forbidden)
    calendar = compile_native_factorized_calendar(schedule)
    payload = prepare_native_static(city, schedule, inventory)
    native = NativeWholeEngine(calendar, payload, 256 * 1024**2)
    report = native.report(native.initial())
    assert report["construction"]["legs"] == len(calendar)
    assert tuple(report["assignment"]["units"][name]["requested"]
                 for name in ("persons", "vehicles", "cargo_kg")) == pytest.approx(calendar.totals())
    assert report["construction"]["python_calendar_leg_objects"] == 0
