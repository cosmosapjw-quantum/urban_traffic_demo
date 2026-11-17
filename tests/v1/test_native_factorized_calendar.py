"""Exact native Cartesian generation versus the unchanged Python leg oracle."""
from dataclasses import replace
import math

import pytest
from _metroflow_rust import NativeCalendar

from metroflow.v1.demand import ModeShare
from metroflow.v1.factorized_demand import FactorizedSchedule, compile_factorized_demand
from metroflow.v1.native_calendar import (
    compile_native_calendar, compile_native_factorized_calendar, decode_native_leg,
)
from test_factorized_demand import measures


@pytest.mark.parametrize("options", [
    dict(worker_fraction=.1, service_fraction=.4, external_service_fraction=.25,
         school_share=.3, freight_kg=1000, minimum_dwell_s=100),
    dict(worker_shortfall="unassigned_home", service_fraction=.4, freight_kg=321),
    dict(day="weekend", worker_fraction=0, service_fraction=.4,
         external_service_fraction=1, modes=(ModeShare("noncar", 1., None),)),
    dict(worker_fraction=0, service_fraction=0, freight_kg=1000),
    dict(worker_fraction=0, service_fraction=0),
])
def test_direct_native_matches_every_original_record(options):
    schedule = compile_factorized_demand(*measures(), **options)
    oracle = compile_native_calendar(schedule, page_size=3)
    native = compile_native_factorized_calendar(schedule)
    assert native.binding() == oracle.binding()
    assert len(native) == len(oracle)
    assert native.totals() == oracle.totals()
    assert native.initial_ledger_totals() == (0., 0.)
    for i in range(len(native)):
        assert decode_native_leg(native, i) == decode_native_leg(oracle, i)
    for a, b in ((0, 86400), (1000, 30000), (30000, 45000), (60000, 85000)):
        assert native.requested_totals(a, b) == oracle.requested_totals(a, b)


def test_native_generation_never_calls_python_cartesian_iterators(monkeypatch):
    schedule = compile_factorized_demand(*measures(), worker_shortfall="unassigned_home")
    expected = tuple(schedule.iter_legs())

    def forbidden(*args, **kwargs):
        raise AssertionError("Python OD or leg enumeration entered")

    monkeypatch.setattr(FactorizedSchedule, "iter_records", forbidden)
    monkeypatch.setattr(FactorizedSchedule, "iter_legs", forbidden)
    monkeypatch.setattr(FactorizedSchedule, "iter_freight_legs", forbidden)
    native = compile_native_factorized_calendar(schedule)
    assert len(native) == len(expected)
    ids = [decode_native_leg(native, i)["id"] for i in range(len(native))]
    assert ids == [leg.id for leg in expected]
    cohorts = sorted({int(leg.cohort_id[1:]) for leg in expected if leg.cohort_id})
    assert any(b - a > 1 for a, b in zip(cohorts, cohorts[1:]))  # stationary cohorts retain their IDs
    assert native.totals() == pytest.approx(tuple(
        math.fsum(getattr(leg.amounts, k) for leg in expected)
        for k in ("persons", "vehicles", "cargo_kg")), rel=1e-14, abs=1e-14)


def arguments():
    return dict(homes=[(0, 1., 1)], targets=[(0, 0, 0, 1., 1., False, [(0, 1.)])],
                modes=[(0, 0, 1., 1., False)], laws=[], freight=[],
                config=(1., 0., 0., 0., 1000.), labels=[0]*8, freight_profile=0)


def registry(budget=100000):
    r = NativeCalendar(budget)
    r.intern_label("null")
    r.intern_profile([(0., 10., 1.)])
    return r


def test_preflight_failure_never_commits_partial_calendar():
    r = registry(1000)
    before = r.storage_report()
    args = arguments()
    args["homes"] *= 100
    with pytest.raises(MemoryError, match="budget"):
        r.build_factorized(**args)
    assert r.storage_report() == before
    assert len(r) == 0 and r.totals() == (0., 0., 0.)
    args = arguments()
    args["targets"] = [(0, 0, 0, 1e308, 1., False, [(0, 1.)])]
    with pytest.raises(ValueError, match="overflow"):
        r.build_factorized(**args)
    assert r.storage_report() == before
    assert r.totals() == (0., 0., 0.)


def test_invalid_registered_handles_and_reinitialization_rejected():
    r = registry()
    args = arguments()
    args["targets"] = [(0, 99, 0, 1., 1., False, [(0, 1.)])]
    with pytest.raises(ValueError, match="profile"):
        r.build_factorized(**args)
    assert len(r) == 0
    r.build_factorized(**arguments())
    assert len(r) == 2 and r.totals() == (2., 2., 0.)
    with pytest.raises(ValueError, match="empty"):
        r.build_factorized(**arguments())
    assert len(r) == 2 and r.totals() == (2., 2., 0.)


def test_direct_frontend_requires_factorized_contract_and_matching_city():
    with pytest.raises(TypeError, match="FactorizedSchedule"):
        compile_native_factorized_calendar(object())
    schedule = compile_factorized_demand(*measures(), worker_shortfall="unassigned_home")
    with pytest.raises(ValueError, match="another city"):
        compile_native_factorized_calendar(replace(schedule, city_identity="other"))
    with pytest.raises(ValueError, match="byte_budget"):
        compile_native_factorized_calendar(schedule, byte_budget=True)
