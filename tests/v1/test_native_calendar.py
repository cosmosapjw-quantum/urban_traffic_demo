"""Native tests deliberately fail import if the required Rust build is absent."""
from dataclasses import asdict
import math
from types import SimpleNamespace

import pytest
from _metroflow_rust import NativeCalendar

from metroflow.v1.demand import Amounts, TripLeg
from metroflow.v1.native_calendar import compile_native_calendar, decode_native_leg
from metroflow.v1.schedules import DepartureProfile, DepartureWindow


def sample():
    p = DepartureProfile((DepartureWindow(100, 200, .6), DepartureWindow(300, 400, .4)))
    a = Amounts(2.5, 2, 4)
    legs = [TripLeg("c0:out", "c0", None, None, "work", "car", "car", a, p),
            TripLeg("c0:home", "c0", None, None, "return_home", "car", "car", a, p,
                    "c0:out", 20),
            TripLeg("freight:custom", None, None, None, "delivery", "freight", "freight",
                    Amounts(0, .5, 10), p)]
    return SimpleNamespace(city_identity="fixture", identity="schedule", iter_legs=lambda: iter(legs)), legs


def test_streamed_lossless_identity_and_quantities():
    schedule, legs = sample()
    r = compile_native_calendar(schedule, page_size=1)
    assert len(r) == 3
    assert r.binding() == ("fixture", "schedule")
    assert r.storage_report()[1] == 1
    assert r.totals() == (5, 4.5, 18)
    assert r.initial_ledger_totals() == (0, 0)
    for i, leg in enumerate(legs):
        d = decode_native_leg(r, i)
        for key in ("id", "cohort_id", "depends_on", "purpose", "mode", "vehicle_class", "minimum_dwell_s"):
            assert d[key] == getattr(leg, key)
        assert d["amounts"] == asdict(leg.amounts)
        assert d["departures"] == [(w.start_s, w.end_s, w.probability) for w in leg.departures.windows]
    for lo, hi in ((0, 86400), (150, 350), (250, 290), (400, 500), (-10, 120)):
        expected = tuple(math.fsum(getattr(x.requested(lo, hi), k) for x in legs)
                         for k in ("persons", "vehicles", "cargo_kg"))
        assert r.requested_totals(lo, hi) == pytest.approx(expected, rel=1e-14, abs=1e-14)


def empty_registry(budget=100000):
    r=NativeCalendar(budget)
    r.intern_label("null")
    r.intern_profile([(0, 10, 1)])
    return r


def row(key, parent=None, cohort="c0", amounts=(1., 1., 0.)):
    return (key, cohort, parent, [0]*8, amounts, 0.)


def test_page_failure_is_atomic_for_duplicate_parent_and_amounts():
    r=empty_registry()
    r.append([row("c0:out")])
    for rows in ([row("next"), row("c0:out")], [row("next"), row("bad", "absent")],
                 [row("next"), row("bad", "c0:out", amounts=(2., 1., 0.))]):
        before=r.storage_report()
        with pytest.raises(ValueError):r.append(rows)
        assert r.storage_report()==before
        assert len(r)==1
    r.append([row("c0:home", "c0:out")])
    assert len(r)==2


def test_budget_rejection_preserves_prior_page():
    r=empty_registry(1500)
    r.append([row("c0:out")])
    with pytest.raises(MemoryError):
        r.append([row(f"c{i}:out", cohort=f"c{i}") for i in range(1, 20)])
    assert len(r)==1 and r.leg(0)[0]=="c0:out"


def test_profile_and_nonfinite_validation():
    r=empty_registry()
    for p in ([], [(0, 10, .5)], [(0, 10, 1), (5, 15, 1)], [(0, float('inf'), 1)],
              [(0, 1, 1e308), (1, 2, 1e308)]):
        with pytest.raises(ValueError):r.intern_profile(p)
    with pytest.raises(ValueError):r.append([row("bad", amounts=(float('nan'), 0, 0))])
    with pytest.raises(ValueError):r.requested_totals(2, 1)


def test_amount_sum_overflow_rejects_whole_page():
    r=empty_registry()
    r.append([row("c0:out", amounts=(1e308, 0., 0.))])
    with pytest.raises(ValueError, match="overflow"):
        r.append([row("c1:out", cohort="c1", amounts=(1e308, 0., 0.))])
    assert len(r)==1 and r.totals()==(1e308, 0., 0.)


def test_noncanonical_ids_are_not_normalized_or_collided():
    r=empty_registry()
    ids=("c01:out", "c1:out", "c4611686018427387904:out", "plain", "c1:home")
    r.append([row(i) for i in ids])
    assert tuple(r.leg(i)[0] for i in range(len(ids)))==ids
