"""Whole-calendar activation never duplicates occupied road capacity by page."""
from dataclasses import replace
import json

import pytest

from metroflow.active_suffix.common import BudgetExceeded
from metroflow.v1.activity import compile_activity
from metroflow.v1.city import CityContractError
from metroflow.v1.demand import ModeShare
from metroflow.v1.factorized_demand import compile_factorized_demand
from metroflow.v1.release_driver import ReleaseDriver, DriverState, PreparationCheckpoint
from metroflow.v1.release_plan import ReleasePlan
from metroflow.v1.release_services import compile_service_plan
from metroflow.v1.scenarios import scenario_city


def fixture():
    city = scenario_city(1000)
    homes = (compile_activity(city,'block'),)
    jobs = (compile_activity(city,'work','job'),)
    schedule = compile_factorized_demand(homes,jobs,service_fraction=0,
                                         modes=(ModeShare('car',1,1.25),))
    return ReleasePlan(city,schedule,step_s=3600)


def services(city, legs, *, step_s):
    return compile_service_plan(city,legs,step_s=step_s)


def test_complete_activation_one_road_owner_checkpoint_and_continuation(tmp_path,monkeypatch):
    plan = fixture()
    driver = ReleaseDriver(plan,services,max_legs=2,page_size=1,step_s=3600)
    state = driver.initial()
    assert state.cursor.offset == plan.totals()['legs'] == 2
    calls = []
    step = driver.runtime.service.step
    def counted(*args,**kwargs):
        calls.append(1)
        return step(*args,**kwargs)
    monkeypatch.setattr(driver.runtime.service,'step',counted)
    state = driver.advance(state,9*3600)
    assert len(calls) == 9
    assert sum(state.runtime_state.released) > 0
    path = tmp_path/'driver.json'
    driver.save(path,state)
    assert driver.load(path) == state
    continued = driver.advance(driver.load(path),86400)
    assert driver.advance(state,86400) == continued
    report = driver.report(continued)
    assert report['calendar']['remaining_legs'] == 0
    assert report['full_local_acceptance'] == 'NOT_RUN'
    raw = json.loads(path.read_text())
    raw['cursor']['offset'] = 1
    path.write_text(json.dumps(raw))
    with pytest.raises(CityContractError,match='binding'):
        driver.load(path)


def test_oversized_calendar_is_rejected_before_enumeration_or_runtime(monkeypatch):
    plan = fixture()
    def forbidden(*args,**kwargs):
        raise AssertionError('calendar enumerated or service created before budget check')
    monkeypatch.setattr(type(plan.schedule),'iter_legs',forbidden)
    with pytest.raises(BudgetExceeded) as caught:
        ReleaseDriver(plan,forbidden,max_legs=1)
    checkpoint = caught.value.checkpoint
    assert isinstance(checkpoint,PreparationCheckpoint)
    assert checkpoint.cursor.offset == 0
    report = checkpoint.report()
    assert report['remaining_legs'] == 2
    assert report['calendar']['persons'] == 1000
    assert report['simulated_s'] == 0


def test_runtime_resource_failure_preserves_driver_binding_and_last_valid_state(monkeypatch):
    driver = ReleaseDriver(fixture(),services,max_legs=2,step_s=3600)
    initial = driver.initial()
    valid = driver.advance(initial,3600)
    def failure(*args,**kwargs):
        exc = BudgetExceeded('physical record budget')
        exc.checkpoint = valid.runtime_state
        raise exc
    monkeypatch.setattr(driver.runtime,'advance',failure)
    with pytest.raises(BudgetExceeded) as caught:
        driver.advance(initial,7200)
    assert caught.value.checkpoint == valid
    assert isinstance(caught.value.checkpoint,DriverState)
    with pytest.raises(CityContractError,match='binding'):
        driver.check(replace(valid,cursor=replace(valid.cursor,materialized_vehicles=0)))
