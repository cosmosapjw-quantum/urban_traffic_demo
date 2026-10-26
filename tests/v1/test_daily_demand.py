"""D01 independent analytic totals, temporal causality and resident conservation."""

import math
from dataclasses import replace
import pytest
from metroflow.v1.schedules import DepartureProfile, DepartureWindow, daily_profiles
from metroflow.v1.demand import (
    ModeShare,
    compile_daily_demand,
    initial_ledger,
    advance_requests,
    release_trip,
    complete_trip,
    demand_report,
)
from metroflow.v1.demand_audit import audit_inputs, audit_demand
from metroflow.v1.city import CityContractError


def schedule(**kwargs):
    return compile_daily_demand(*audit_inputs(100000), **kwargs)


def test_exact_profile_integral_and_birth_moment_on_non_aligned_steps():
    p = DepartureProfile((DepartureWindow(10.0, 20.0, 0.25), DepartureWindow(30.0, 60.0, 0.75)))
    assert p.fraction(0, 86400) == 1
    assert p.fraction(15, 40) == pytest.approx(0.375)
    assert p.first_moment_s() == pytest.approx(0.25 * 15 + 0.75 * 45)
    for step in (7, 17, 900):
        assert math.fsum(p.fraction(a, a + step) for a in range(0, 86400, step)) == pytest.approx(1)
        assert math.fsum(
            p.first_moment_s(a, a + step) for a in range(0, 86400, step)
        ) == pytest.approx(37.5)
    with pytest.raises(ValueError, match="overlapping"):
        DepartureProfile((DepartureWindow(0, 10, 0.5), DepartureWindow(5, 15, 0.5)))


def test_100k_ledger_and_units_have_analytic_totals():
    s = schedule(freight_kg=10000)
    r = demand_report(s, advance_requests(s, initial_ledger(s), 86400))
    assert r["resident_stock"] == 100000
    assert r["resident_stocks"] == dict(home=100000, activity=0, external_activity=0, in_transit=0)
    # 50k workers + 20k service visitors, each with outward + return leg.
    totals = r["trip_amounts"]["requested"]
    assert totals["persons"] == pytest.approx(140000)
    assert totals["vehicles"] == pytest.approx(2 * 70000 * (0.6 / 1.25 + 0.25 / 25) + 10)
    assert totals["cargo_kg"] == 10000
    assert r["trip_amounts"]["completed"] == dict(persons=0, vehicles=0, cargo_kg=0)
    assert math.fsum(c.persons for c in s.cohorts) == 100000
    assert r["status"] == "PASS"
    assert len(s.cohorts) < 20  # No resident/vehicle enumeration.


def test_impossible_worker_support_and_disjoint_reservations_rejected():
    homes, jobs, services = audit_inputs(100000)
    with pytest.raises(CityContractError, match="job opportunity") as err:
        compile_daily_demand(homes, jobs, services, worker_fraction=0.7, service_fraction=0.1)
    assert err.value.status == "PHYSICAL_INFEASIBLE"
    with pytest.raises(CityContractError, match="disjoint"):
        schedule(worker_fraction=0.6, service_fraction=0.5)


def test_service_shortage_and_external_and_noncar_amounts_are_visible():
    homes, jobs, _ = audit_inputs(100000)
    s = compile_daily_demand(homes, jobs, (), external_service_fraction=0.5)
    assert s.unassigned_service_persons == 10000
    assert math.fsum(c.persons for c in s.cohorts if c.purpose == "unassigned_service") == 10000
    external = [t for t in s.legs if t.endpoint_kind == "external"]
    assert math.fsum(t.amounts.persons for t in external) == 20000  # two trips per 10k persons
    assert all(t.amounts.vehicles == 0 for t in s.legs if t.mode == "noncar")
    assert math.fsum(c.persons for c in s.cohorts) == 100000


def test_partial_movements_conserve_people_and_return_requires_completion_and_dwell():
    s = schedule()
    outward = next(t for t in s.legs if t.purpose == "work")
    back = next(t for t in s.legs if t.depends_on == outward.id)
    initial = initial_ledger(s)
    ledger = advance_requests(s, initial, 18 * 3600)
    with pytest.raises(CityContractError, match="return requires"):
        release_trip(s, ledger, back.id, 0.1)
    ledger = release_trip(s, ledger, outward.id, 0.5)
    r = demand_report(s, ledger)
    assert r["resident_stocks"]["in_transit"] == outward.amounts.persons * 0.5
    ledger = complete_trip(s, ledger, outward.id, 0.25)
    with pytest.raises(CityContractError, match="dwell"):
        release_trip(s, ledger, back.id, 0.1)
    ledger = advance_requests(s, ledger, 19 * 3600)
    ledger = release_trip(s, ledger, back.id, 0.25)
    with pytest.raises(CityContractError, match="return requires"):
        release_trip(s, ledger, back.id, 0.01)
    ledger = complete_trip(s, ledger, back.id, 0.25)
    r = demand_report(s, ledger)
    assert r["status"] == "PASS" and r["resident_residual"] == pytest.approx(0)
    assert r["resident_stocks"]["in_transit"] == outward.amounts.persons * 0.25
    assert initial.time_s == 0 and initial.progress[0].released == 0


def test_early_or_duplicate_release_completion_and_stale_ledger_rejected():
    s = schedule()
    t = s.legs[0]
    ledger = initial_ledger(s)
    with pytest.raises(CityContractError, match="requested"):
        release_trip(s, ledger, t.id, 0.1)
    ledger = advance_requests(s, ledger, 12 * 3600)
    with pytest.raises(CityContractError, match="released"):
        complete_trip(s, ledger, t.id, 1)
    ledger = release_trip(s, ledger, t.id, 1)
    with pytest.raises(CityContractError, match="requested"):
        release_trip(s, ledger, t.id, 1)
    with pytest.raises(CityContractError, match="identity"):
        advance_requests(schedule(day="weekend"), ledger, 13 * 3600)
    with pytest.raises(CityContractError, match="advance"):
        advance_requests(s, ledger, 1)


def test_weekday_weekend_and_am_pm_are_declared_different():
    a, b = audit_demand(), audit_demand(day="weekend")
    assert a["morning_persons"] > b["morning_persons"] > 0
    assert a["evening_persons"] > b["evening_persons"] > 0
    assert a["trip_amounts"]["requested"]["persons"] == 140000
    assert b["trip_amounts"]["requested"]["persons"] == 100000
    assert all(
        r["status"] == "PASS" for r in a["departure_integration"] + b["departure_integration"]
    )
    assert daily_profiles("weekday", "work") != daily_profiles("weekend", "work")


def test_intrazonal_endpoints_and_identity_keep_activity_geometry():
    homes, jobs, services = audit_inputs(100000)
    s = compile_daily_demand(homes, jobs, services)
    assert all(t.intrazonal.mean_s > 0 for t in s.legs)
    assert all(t.origin is homes[0] or t.destination is homes[0] for t in s.legs)
    changed = compile_daily_demand(homes, jobs, services, modes=(ModeShare("car", 1.0, 2.0),))
    assert changed.identity != s.identity
    assert all(t.amounts.vehicles == t.amounts.persons / 2 for t in changed.legs)
    with pytest.raises(CityContractError, match="identity mismatch"):
        compile_daily_demand(homes, (replace(jobs[0], city_identity="different"),), services)


def test_delivery_is_not_resident_mass_and_input_units_are_guarded():
    s = schedule(freight_kg=5000, freight_kg_per_vehicle=500)
    freight = next(t for t in s.legs if t.mode == "freight")
    assert freight.amounts.persons == 0
    assert freight.amounts.vehicles == 10
    assert freight.amounts.cargo_kg == 5000
    assert freight.cohort_id is None and freight.endpoint_kind == "external"
    with pytest.raises(CityContractError, match="occupancy"):
        ModeShare("bus", 1.0, 0)
    with pytest.raises(CityContractError, match="probabilities"):
        schedule(modes=(ModeShare("car", 0.5, 2.0),))


def test_releasing_and_completing_all_outward_legs_does_not_teleport_home():
    s = schedule()
    ledger = advance_requests(s, initial_ledger(s), 12 * 3600)
    for t in s.legs:
        if t.depends_on is None:
            ledger = release_trip(s, ledger, t.id, 1.0)
            ledger = complete_trip(s, ledger, t.id, 1.0)
    report = demand_report(s, ledger)
    assert report["resident_stocks"]["activity"] == 70000
    assert report["resident_stocks"]["home"] == 30000
    ledger = advance_requests(s, ledger, 86400)
    assert demand_report(s, ledger)["resident_stocks"] == report["resident_stocks"]
    for t in s.legs:
        if t.depends_on is not None:
            ledger = release_trip(s, ledger, t.id, 1.0)
            ledger = complete_trip(s, ledger, t.id, 1.0)
    assert demand_report(s, ledger)["resident_stocks"]["home"] == 100000


def test_opportunity_margins_and_aggregate_budget_do_not_scale_with_people():
    a = compile_daily_demand(*audit_inputs(1000))
    b = compile_daily_demand(*audit_inputs(100000))
    assert len(a.cohorts) == len(b.cohorts)
    assert len(a.legs) == len(b.legs)
    for dest in audit_inputs(100000)[1]:
        assigned = math.fsum(
            c.persons
            for c in b.cohorts
            if c.purpose == "work" and c.destination.block_id == dest.block_id
        )
        assert assigned <= dest.mass
    with pytest.raises(CityContractError, match="budget") as exc:
        schedule(max_cohorts=1)
    assert exc.value.status == "BLOCKED_RESOURCE"


def test_departure_batches_preserve_mass_and_first_birth_moment():
    from metroflow.v1.demand import iter_departures

    s = schedule(freight_kg=5000)
    for step in (900, 300, 60):
        batches = tuple(iter_departures(s, step))
        assert all(
            0 <= b.start_s < b.end_s <= 86400 and b.start_s <= b.mean_birth_s <= b.end_s
            for b in batches
        )
        for unit in ("persons", "vehicles", "cargo_kg"):
            assert math.fsum(getattr(b.amounts, unit) for b in batches) == pytest.approx(
                math.fsum(getattr(t.amounts, unit) for t in s.legs)
            )
            expected = math.fsum(
                getattr(t.amounts, unit) * t.departures.first_moment_s() for t in s.legs
            )
            actual = math.fsum(getattr(b.amounts, unit) * b.mean_birth_s for b in batches)
            assert actual == pytest.approx(expected, rel=1e-12)


def test_demand_cli_generates_real_calendar_and_rejects_invalid_population(tmp_path):
    import subprocess
    import sys
    import json

    out = tmp_path / "daily.json"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "metroflow.v1",
            "demand-audit",
            "--population",
            "100000",
            "--day",
            "weekday",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(out.read_text())
    assert data["status"] == "PASS"
    assert data["cases"][0]["trip_amounts"]["requested"]["persons"] == 140000
    assert data["cases"][0]["origin_destination"]
    r = subprocess.run(
        [sys.executable, "-m", "metroflow.v1", "demand-audit", "--population", "-1"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2
    assert json.loads(r.stdout)["status"] == "MODEL_ERROR"


def test_school_service_split_shares_the_same_finite_opportunity_margin():
    s = schedule()
    school = [c for c in s.cohorts if c.purpose == "school"]
    service = [c for c in s.cohorts if c.purpose == "service"]
    assert math.fsum(c.persons for c in school) == 5000
    assert math.fsum(c.persons for c in service) == 15000
    t = next(t for t in s.legs if t.purpose == "school")
    assert t.departures.fraction(8 * 3600, 9 * 3600) == 1
    assert all(c.purpose != "school" for c in schedule(day="weekend").cohorts)
    assert math.fsum(c.persons for c in school + service) <= audit_inputs(100000)[2][0].mass
