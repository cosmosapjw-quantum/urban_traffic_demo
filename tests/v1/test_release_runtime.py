"""Actual gate routing, conservative pending modes and checkpoint continuation."""
from dataclasses import replace

import pytest

from metroflow.v1.activity import compile_activity, ActivityPatch
from metroflow.v1.city import CityContractError
from metroflow.v1.demand import TripLeg, Amounts
from metroflow.v1.release_runtime import ReleaseRuntime
from metroflow.v1.scenarios import scenario_city
from metroflow.v1.schedules import DepartureProfile, DepartureWindow


def fixture():
    city = scenario_city(1000)
    nodes = {n.id:n for n in city.roadmap.nodes}
    measures = []
    for block, kind in [('block','residential'),('work','job')]:
        door = next(p for p in city.portals if p.block_id == block)
        xy = nodes[door.node_id].xyz[:2]
        measures.append(compile_activity(city, block, kind, patches=(ActivityPatch(1000,(xy,)),)))
    leg = TripLeg('out', 'cohort', *measures, 'work', 'car', 'car', Amounts(1.25,1),
                  DepartureProfile((DepartureWindow(0,2),)))
    return city, leg


def test_real_portals_legal_route_birth_and_unexecuted_modes(tmp_path):
    city, leg = fixture()
    bus = replace(leg,id='bus',mode='bus',amounts=Amounts(25,1))
    model = ReleaseRuntime(city,(leg,bus),step_s=1)
    state = model.advance(model.initial(),10)
    assert state.journey.birth_moment == pytest.approx(1)
    assert model.route_links['out']
    assert all(pair in city.transport_graph.allowed_turns
               for pair in zip(model.route_links['out'],model.route_links['out'][1:]))
    report = model.report(state)
    assert report['ledger']['persons']['requested'] == pytest.approx(26.25)
    assert report['ledger']['persons']['pending'] == pytest.approx(25)
    path = tmp_path/'checkpoint.json'
    model.save(path,state)
    restored = model.load(path)
    assert restored == state
    assert model.advance(restored,60) == model.advance(state,60)
    end = model.advance(state,120)
    assert end.journey.completed == pytest.approx(1)
    assert model.report(end)['ledger']['persons']['completed'] == pytest.approx(1.25)


def test_budget_is_before_eager_materialization_and_identity_rejected(tmp_path):
    city, leg = fixture()
    with pytest.raises(CityContractError,match='bound'):
        ReleaseRuntime(city,(replace(leg,id=str(i)) for i in range(10)),max_legs=1)
    model = ReleaseRuntime(city,(leg,))
    with pytest.raises(CityContractError,match='identity'):
        model.check(replace(model.initial(),model_id='different'))


def test_committed_routes_share_the_same_physical_network():
    city, leg = fixture()
    other = replace(leg, id='other')
    model = ReleaseRuntime(city, (leg, other))
    assert model.route_links['out'] == model.route_links['other']
    # The road registry appears once even when both OD labels use every link.
    assert len(model.model.network.groups) == len(city.transport_graph.roads)
    state = model.advance(model.initial(), 120)
    report = model.report(state)
    assert report['ledger']['vehicles']['released'] == pytest.approx(2)
    assert report['ledger']['vehicles']['completed'] == pytest.approx(2)


def test_corrupt_checkpoint_cannot_diverge_from_physical_or_unsupported_ledgers():
    city, leg = fixture()
    bus = replace(leg, id='bus', mode='bus', amounts=Amounts(25,1))
    model = ReleaseRuntime(city, (leg,bus))
    state = model.advance(model.initial(), 10)
    with pytest.raises(CityContractError, match='physical road ledgers'):
        model.check(replace(state, released=(0.0,0.0)))
    # Preserve the grand total while maliciously moving car release to a bus.
    with pytest.raises(CityContractError, match='unsupported leg'):
        model.check(replace(state, released=(0.0, state.released[0])))
