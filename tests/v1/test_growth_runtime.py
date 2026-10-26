"""M04 explicit frozen spatial input survives actual C01 checkpoint resume."""
from dataclasses import replace
import pytest
from metroflow.v1.runtime import toy_runtime, Runtime
from metroflow.v1.access_audit import fixture_city
from metroflow.v1.activity import compile_activity
from metroflow.v1.development import GrowthModel, DevelopmentSite, compile_entry
from metroflow.v1.accessibility import CompletedAccessibility
from metroflow.v1.checkpoint import save_checkpoint, load_checkpoint
from metroflow.v1.city import CityContractError


def fixture():
    city = fixture_city()
    entry = compile_entry(city, compile_activity(city,'block'), 'east', capacity_veh_s=1,
                          corridor=((300.,20.),(310.,10.)))
    growth = GrowthModel(city, (DevelopmentSite('block',entry,20),), budget_m=100,
                         slow_epoch_s=10, max_access_s=50)
    base = toy_runtime()
    runtime = Runtime(base.transport, base.information, base.routing, base.preference,
                      city_identity=city.identity, demand_identity=base.demand_identity,
                      origin=base.origin, destination=base.destination, growth_model=growth)
    snapshot = CompletedAccessibility(city.identity,0.,(('block',20.),),'completed_fixture')
    return runtime, snapshot


def test_nonempty_growth_world_checkpoint_and_once_only_request(tmp_path):
    model, snapshot = fixture()
    state = model.publish_growth_input(model.initial(), snapshot, requested_increment=10)
    path = tmp_path/'growth.json'
    save_checkpoint(path, model, state)
    loaded = load_checkpoint(path, model)
    assert loaded == state
    final = model.advance(loaded,10)
    assert final == model.advance(state,10)
    assert sum(dict(final.growth_state.allocations).values()) == 1010
    assert final.growth_increment == 0
    save_checkpoint(path,model,final)
    assert load_checkpoint(path,model) == final
    second = model.publish_growth_input(final,replace(snapshot,city_identity=model.growth_model.materialize_city(final.growth_state).identity,stamp_s=10.,source_version='next'))
    second = model.advance(second,20)
    assert second.growth_state.requested_increment == 10


def test_absent_or_stale_growth_input_is_atomic_failure():
    model,snapshot = fixture()
    initial = model.initial()
    with pytest.raises(CityContractError) as exc:
        model.advance(initial,10)
    assert exc.value.checkpoint is initial
    state = model.advance(model.publish_growth_input(initial,snapshot),10)
    with pytest.raises(CityContractError) as exc:
        model.advance(state,20)
    assert exc.value.checkpoint is state


def test_growth_publication_cannot_overwrite_unconsumed_increment():
    model,snapshot = fixture()
    state = model.publish_growth_input(model.initial(),snapshot,requested_increment=10)
    with pytest.raises(CityContractError):
        model.publish_growth_input(state,snapshot,requested_increment=5)
    with pytest.raises(CityContractError):
        model.publish_growth_input(model.initial(),replace(snapshot,stamp_s=1.))
