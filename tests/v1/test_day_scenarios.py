"""C02 actual day execution; fluid trip and stock populations stay distinct."""

import json
import os
from pathlib import Path
import pytest
from metroflow.v1.scenarios import compile_scenario, run_scenario, SCENARIOS
from metroflow.v1.city import CityContractError


@pytest.fixture(scope="module")
def days(tmp_path_factory):
    folder = Path(os.environ.get("C02_EVIDENCE_DIR", tmp_path_factory.mktemp("c02")))
    results = {}
    for name in ("city10k_weekday", "city10k_weekend", "city1k_analytic"):
        results[name] = run_scenario(name, out=folder / name)
        print(
            json.dumps(
                dict(
                    actual_day=name,
                    wall_s=results[name]["wall_s"],
                    road_completed=results[name]["services"]["road_completed_veh"],
                )
            )
        )
    return folder, results


def test_actual_two_10k_days_and_1k_analytic_terminate(days):
    _, results = days
    for name, r in results.items():
        assert r["status"] == "PASS" and r["time_s"] == 86400
        assert r["resident_stock"] == (1000 if name == "city1k_analytic" else 10000)
        assert r["am_actual_road_vehicles"] > 0 and r["pm_actual_road_vehicles"] > 0
        assert len(r["hourly"]) == 24
        assert abs(r["demand"]["resident_residual"]) < 1e-7


def test_independent_1k_throughput_and_bus_capacity_oracle(days):
    r = days[1]["city1k_analytic"]
    # work500+service200; 60% cars at1.25persons/veh, two directions =>672.
    # Four fixed bus runs, one freight vehicle. Bus125/leg work caps at100;
    # service50/leg belowcap =>300 bus person-trips,50 unserved.
    assert r["services"]["road_completed_veh"] == pytest.approx(672 + 4 + 1, abs=1e-7)
    assert r["services"]["scheduled_bus_vehicles"] == 4
    assert r["services"]["arrived_persons"] == 300
    assert r["services"]["waiting_persons"] == 50
    assert r["completed_person_trips"] == pytest.approx(1350)
    assert r["unfinished_person_trips"] == pytest.approx(50)
    assert r["services"]["cargo_delivered_kg"] == 1000


def test_overload_person_stock_pending_and_no_omniscient_statistics(days):
    for r in days[1].values():
        amounts = r["demand"]["trip_amounts"]
        assert amounts["completed"]["persons"] + amounts["active"]["persons"] + amounts["pending"][
            "persons"
        ] == pytest.approx(r["scheduled_person_trips"])
        assert sum(r["demand"]["resident_stocks"].values()) == pytest.approx(r["resident_stock"])
        assert r["whole_person_trip_mean_s"] is None and r["p95_s"] is None
        assert r["services"]["scheduled_bus_vehicles"] == 4
        assert r["services"]["cargo_unfinished_kg"] == pytest.approx(0, abs=1e-6)


def test_actual_json_csv_svg_are_same_executed_city(days):
    folder, results = days
    for name, r in results.items():
        p = folder / name
        assert json.loads((p / "report.json").read_text())["city_identity"] == r["city_identity"]
        assert r["city_identity"] in (p / "city.json").read_text()
        assert len((p / "hourly.csv").read_text().splitlines()) == 25
        assert "<svg" in (p / "city.svg").read_text()
        assert "connector" in (p / "city.svg").read_text()


def test_controlled_interventions_preserve_calendar_and_growth_is_explicit():
    baseline = compile_scenario()
    closed = compile_scenario("city10k_bridgeclosure")
    bypass = compile_scenario("city10k_bypass")
    growth = compile_scenario("city10k_growth_weekday")
    assert (
        baseline["demand_control_identity"]
        == closed["demand_control_identity"]
        == bypass["demand_control_identity"]
    )
    assert growth["demand_control_identity"] != baseline["demand_control_identity"]
    assert growth["schedule"].resident_stock == 10100
    assert (
        growth["growth_evidence"]["slow_response_s"]
        > growth["growth_evidence"]["completed_access_stamp_s"]
    )
    assert len(bypass["city"].roadmap.sections) == len(baseline["city"].roadmap.sections) + 1
    assert closed["model"].network.windows


def test_scenario_configuration_rejects_silent_unsupported_scope():
    assert len(SCENARIOS) == 6
    for kw in (dict(days=2), dict(name="unknown"), dict(step_s=7)):
        with pytest.raises(CityContractError):
            run_scenario(**kw)
