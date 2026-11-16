"""Actual whole-native driver, checkpoint and hourly campaign contracts.

These are bounded synthetic tests, not the three-city V03 acceptance campaign.
The native extension is required: no skip or Python runtime fallback is used.
"""

from dataclasses import asdict, replace
import hashlib
import json
from types import SimpleNamespace

import pytest

from metroflow.active_suffix.common import BudgetExceeded
from metroflow.v1.city import CityContractError
from metroflow.v1.factorized_demand import FactorizedSchedule
from metroflow.v1.native_release_driver import NativeReleaseDriver
from metroflow.v1.release_driver import DriverState
from metroflow.v1.release_inventory import build_inventory
from metroflow.v1.release_plan import ReleasePlan
from test_native_static import fixture as marginal_fixture


BYTE_BUDGET = 256 * 1024**2


def fixture(*, step_s=600, **kwargs):
    city, schedule, inventory = marginal_fixture()
    plan = ReleasePlan(city, schedule, step_s=step_s)
    driver = NativeReleaseDriver(plan, inventory, step_s=step_s,
                                 byte_budget=BYTE_BUDGET, **kwargs)
    return driver, inventory


def test_driver_activates_complete_calendar_without_python_legs(monkeypatch):
    city, schedule, inventory = marginal_fixture()
    plan = ReleasePlan(city, schedule, step_s=600)

    def forbidden(*args, **kwargs):
        raise AssertionError("whole-native driver enumerated Python OD/leg state")

    monkeypatch.setattr(FactorizedSchedule, "iter_legs", forbidden)
    monkeypatch.setattr(FactorizedSchedule, "iter_records", forbidden)
    monkeypatch.setattr(plan, "take", forbidden)
    monkeypatch.setattr(plan, "resolve", forbidden)
    driver = NativeReleaseDriver(plan, inventory, step_s=600, byte_budget=BYTE_BUDGET)
    initial = driver.initial()
    report = driver.report(initial)
    assert driver.engine_backend == "rust_whole"
    assert initial.cursor.offset == plan.totals()["legs"]
    assert report["calendar"]["remaining_legs"] == 0
    assert all(value == 0 for value in report["calendar"]["remaining_amounts"].values())
    construction = report["execution"]["construction"]
    assert construction["legs"] == plan.totals()["legs"]
    assert construction["python_calendar_leg_objects"] == 0
    assert construction["road_owners"] == 1
    assert report["full_local_acceptance"] == "NOT_RUN"
    assert driver.advance(initial, 3600).time_s == 3600
    assert initial.time_s == 0  # snapshot ownership survives subsequent advancement


def test_driver_checkpoint_restarts_in_fresh_runtime_and_preserves_old_snapshot(tmp_path):
    driver, _ = fixture()
    initial = driver.initial()
    middle = driver.advance(initial, 32400)
    before = driver.report(middle)
    checkpoint = tmp_path / "middle.bin"
    driver.save(checkpoint, middle)
    assert checkpoint.read_bytes().startswith(b"MFWHOLE1")

    fresh, _ = fixture()
    restored = fresh.load(checkpoint)
    assert restored.cursor == middle.cursor and restored.time_s == middle.time_s
    assert fresh.report(restored) == before
    continued = fresh.advance(restored, 86400)
    uninterrupted = driver.advance(middle, 86400)
    assert fresh.report(continued) == driver.report(uninterrupted)
    assert fresh.runtime.sample_legs(continued.runtime_state, (0, 1)) == (
        driver.runtime.sample_legs(uninterrupted.runtime_state, (0, 1)))
    fresh_path, original_path = tmp_path / "fresh.bin", tmp_path / "original.bin"
    fresh.save(fresh_path, continued)
    driver.save(original_path, uninterrupted)
    assert fresh_path.read_bytes() == original_path.read_bytes()
    assert initial.time_s == 0 and middle.time_s == 32400
    assert driver.report(middle) == before

    with pytest.raises(CityContractError, match="binding"):
        driver.check(replace(middle, cursor=replace(middle.cursor, offset=0)))
    with pytest.raises(CityContractError, match="binding"):
        driver.check(replace(middle, driver_identity="different"))


@pytest.mark.parametrize("change", ("inventory", "step", "records", "bytes"))
def test_checkpoint_rejects_changed_fleet_step_or_resource_binding(tmp_path, change):
    driver, inventory = fixture()
    checkpoint = tmp_path / "bound.bin"
    driver.save(checkpoint, driver.initial())
    options = dict(step_s=600, byte_budget=BYTE_BUDGET)
    if change == "inventory":
        inventory = build_inventory(driver.plan.city,
            replace(inventory.policy, capacity_persons=inventory.policy.capacity_persons + 1))
    elif change == "step":
        options["step_s"] = 300
    elif change == "records":
        options["record_budget"] = 20001
    else:
        options["byte_budget"] += 1
    other = NativeReleaseDriver(driver.plan, inventory, **options)
    assert other.identity != driver.identity
    with pytest.raises(ValueError, match="binding"):
        other.load(checkpoint)
    with pytest.raises(ValueError, match="binding"):
        other.runtime.check(driver.initial().runtime_state)


def test_runtime_resource_checkpoint_is_rewrapped_with_driver_binding(monkeypatch):
    driver, _ = fixture()
    initial = driver.initial()
    valid = driver.advance(initial, 3600)

    def fail(*args):
        exc = BudgetExceeded("synthetic physical record limit")
        exc.checkpoint = valid.runtime_state
        raise exc

    monkeypatch.setattr(driver.runtime, "advance", fail)
    with pytest.raises(BudgetExceeded) as caught:
        driver.advance(initial, 7200)
    saved = caught.value.checkpoint
    assert isinstance(saved, DriverState)
    assert saved.driver_identity == driver.identity and saved.cursor == valid.cursor
    assert saved.runtime_state is valid.runtime_state
    driver.check(saved)


def test_cli_prepare_selects_whole_native_before_legacy_leg_budget(monkeypatch):
    import tools.run_v1_local_acceptance as cli

    city, _, inventory = marginal_fixture()
    monkeypatch.setenv("METROFLOW_V1_ENGINE_BACKEND", "rust_whole")
    row = dict(source_sha256="fixture", patch_sha256="fixture")
    monkeypatch.setattr(cli, "load_release_city", lambda case: (city, row))

    def legacy_forbidden(*args, **kwargs):
        raise AssertionError("whole-native selection constructed legacy ReleaseDriver")

    monkeypatch.setattr(cli, "ReleaseDriver", legacy_forbidden)
    matrix = dict(worker_shortfall="unassigned_home",
                  inventory_policy=asdict(inventory.policy), route_materialization_budget=1,
                  limits={"peak_rss_bytes": 8*1024**3})
    driver, returned_row = cli.prepare(dict(id="fixture", day="weekday"), matrix, 600)
    assert isinstance(driver, NativeReleaseDriver)
    assert driver.cursor.offset > matrix["route_materialization_budget"]
    assert returned_row == row


def test_cli_uses_hourly_chunks_native_tick_metrics_and_durable_restart(monkeypatch, tmp_path):
    import tools.run_v1_local_acceptance as cli

    monkeypatch.setenv("METROFLOW_V1_ENGINE_BACKEND", "rust_whole")
    driver, _ = fixture()
    calls, loads = [], []
    advance, load = driver.advance, driver.load

    def counted(state, end):
        updated = advance(state, end)
        calls.append((state.time_s, end, len(driver.runtime.last_advance_metrics["tick_times_s"])))
        return updated

    def loaded(path):
        restored = load(path)
        loads.append(restored.time_s)
        return restored

    monkeypatch.setattr(driver, "advance", counted)
    monkeypatch.setattr(driver, "load", loaded)
    monkeypatch.setattr(cli, "prepare", lambda *args: (driver,
        dict(source_sha256="fixture", patch_sha256="fixture")))
    matrix = tmp_path / "matrix.json"
    matrix.write_text("{}")
    args = SimpleNamespace(step_s=600, horizon_s=86400, matrix=matrix, out=tmp_path,
                           label="whole.fixture", prepare_only=False, resume=True)
    assert cli.worker(args, {"limits": {"peak_rss_bytes": 2**40}}, {"id": "fixture"}) == 0
    result = json.loads((tmp_path / "whole.fixture.json").read_text())
    assert len(calls) == 24 and all(b - a == 3600 and ticks == 6 for a, b, ticks in calls)
    assert loads == [43200]
    assert result["engine_backend"] == "rust_whole"
    assert result["status"] == "EXECUTED_FOR_REVIEW"
    assert result["simulated_s"] == 86400
    assert 0 <= result["tick_p50_s"] <= result["tick_p95_s"]
    assert result["native_frontend_boundary_s"] >= 0
    assert result["peak_tracked_records"] > 0
    assert result["tick_measurement_scope"].startswith("native complete tick")
    assert result["report"]["calendar"]["remaining_legs"] == 0
    final = tmp_path / "whole.fixture.final.bin"
    assert result["final_checkpoint_sha256"] == hashlib.sha256(final.read_bytes()).hexdigest()
    assert final.read_bytes() == (tmp_path / "whole.fixture.last_valid.bin").read_bytes()
    assert driver.load(tmp_path / "whole.fixture.middle.bin").time_s == 43200


def test_cli_rejects_missing_tick_samples_without_success_receipt(monkeypatch, tmp_path):
    import tools.run_v1_local_acceptance as cli

    monkeypatch.setenv("METROFLOW_V1_ENGINE_BACKEND", "rust_whole")
    driver, _ = fixture()
    advance = driver.advance

    def wrong_metrics(state, end):
        updated = advance(state, end)
        driver.runtime.last_advance_metrics = dict(tick_times_s=[], peak_records=0)
        return updated

    monkeypatch.setattr(driver, "advance", wrong_metrics)
    monkeypatch.setattr(cli, "prepare", lambda *args: (driver,
        dict(source_sha256="fixture", patch_sha256="fixture")))
    matrix = tmp_path / "matrix.json"
    matrix.write_text("{}")
    args = SimpleNamespace(step_s=600, horizon_s=3600, matrix=matrix, out=tmp_path,
                           label="bad.metrics", prepare_only=False, resume=False)
    assert cli.worker(args, {"limits": {"peak_rss_bytes": 2**40}}, {"id": "fixture"}) == 2
    result = json.loads((tmp_path / "bad.metrics.json").read_text())
    assert result["status"] == "BLOCKED"
    assert "tick timing samples differ" in result["reason"]
    assert "final_checkpoint_sha256" not in result
    assert driver.load(tmp_path / "bad.metrics.last_valid.bin").time_s == 0
