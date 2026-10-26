"""D01 synthetic 24h demand-generation audit; no simulated traffic completions."""

from dataclasses import replace
import math

from .access_audit import fixture_city
from .activity import compile_activity
from .city import compile_city, reject
from .demand import (
    compile_daily_demand,
    initial_ledger,
    advance_requests,
    demand_report,
    iter_departures,
)
from .schedules import DAY_S


def audit_inputs(population):
    if isinstance(population, bool) or not isinstance(population, int) or population < 1:
        reject("positive integer audit resident population required")
    base = fixture_city()
    jobs = math.ceil(0.6 * population)
    block = replace(
        base.face_graph.blocks[0],
        residents=population,
        housing_capacity=population,
        jobs=jobs,
        job_capacity=jobs,
    )
    city = compile_city(base.roadmap, blocks=(block,), portals=base.portals)
    return (
        (compile_activity(city, "block"),),
        (compile_activity(city, "block", "job"),),
        (compile_activity(city, "block", "service", service_stock=0.4 * population),),
    )


def audit_demand(population=100000, day="weekday"):
    homes, jobs, services = audit_inputs(population)
    schedule = compile_daily_demand(homes, jobs, services, day=day, freight_kg=population * 0.1)
    ledger = advance_requests(schedule, initial_ledger(schedule), DAY_S)
    report = demand_report(schedule, ledger)
    report["scope"] = "24h calendar generated; no road/queue simulation; zero implicit completions"
    report["departure_integration"] = []
    for step in (900, 300, 60):
        batches = tuple(iter_departures(schedule, step))
        amounts = {
            unit: math.fsum(getattr(b.amounts, unit) for b in batches)
            for unit in ("persons", "vehicles", "cargo_kg")
        }
        expected = report["trip_amounts"]["requested"]
        residuals = {unit: amounts[unit] - expected[unit] for unit in amounts}
        passed = all(abs(residuals[u]) <= 1e-9 * max(1.0, expected[u]) for u in amounts)
        report["departure_integration"].append(
            dict(
                step_s=step,
                amounts=amounts,
                residuals=residuals,
                status="PASS" if passed else "NUMERICAL_ERROR",
            )
        )
    if any(r["status"] != "PASS" for r in report["departure_integration"]):
        report["status"] = "NUMERICAL_ERROR"
    report["morning_persons"] = math.fsum(
        t.requested(6 * 3600, 10 * 3600).persons for t in schedule.legs
    )
    report["evening_persons"] = math.fsum(
        t.requested(16 * 3600, 20 * 3600).persons for t in schedule.legs
    )
    return report
