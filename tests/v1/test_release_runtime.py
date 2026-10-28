"""Actual gate routing, conservative pending modes and checkpoint continuation."""
from dataclasses import replace
import math

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


def test_delayed_return_retains_calendar_birth_and_enforces_outward_completion_and_dwell(tmp_path):
    city, outward = fixture()
    returning = replace(outward, id='return', origin=outward.destination,
                        destination=outward.origin, purpose='return_home', depends_on='out',
                        minimum_dwell_s=100,
                        departures=DepartureProfile((DepartureWindow(0,2),)))
    model = ReleaseRuntime(city,(outward,returning))
    before = model.advance(model.initial(),20)
    assert before.released[1] == 0
    midway = model.advance(before,60)
    assert midway.released[1] == 0
    path = tmp_path/'return.json'
    model.save(path,midway)
    assert model.load(path) == midway
    final = model.advance(midway,350)
    assert final.completed == pytest.approx((1,1))
    # Both intent windows have mean t=1, including the held return.
    assert final.journey.birth_moment == pytest.approx(2)
    assert final.road_intent_hold > 100
    report = model.report(final)
    r = report['journey']['residence_vehicle_seconds']
    assert r['return_intent_hold'] == final.road_intent_hold
    assert r['origin_access'] == pytest.approx(0,abs=1e-8)
    assert math.fsum(v for k,v in r.items() if k != 'total') == pytest.approx(r['total'])


def test_intrazonal_noncar_uses_actual_delay_and_conserves_persons(tmp_path):
    from metroflow.v1.journey import DelayLaw
    city, outward = fixture()
    internal = replace(outward, id='internal', origin=outward.origin,destination=outward.origin,
                       mode='noncar',vehicle_class=None,amounts=Amounts(persons=3),
                       intrazonal=DelayLaw(((10,1),)))
    model = ReleaseRuntime(city,(internal,))
    early = model.advance(model.initial(),5)
    assert early.completed == (0,)
    assert model.report(early)['ledger']['persons']['active'] == 3
    final = model.advance(early,20)
    assert model.report(final)['ledger']['persons']['completed'] == 3
    assert final.journey.released == 0
    path=tmp_path/'internal.json'
    model.save(path,early)
    assert model.advance(model.load(path),20) == final


def test_return_parent_contract_and_intent_hold_checkpoint_are_checked():
    city, outward = fixture()
    invalid = replace(outward,id='return',depends_on='out',amounts=Amounts(2.5,2))
    with pytest.raises(CityContractError,match='cohort and amounts'):
        ReleaseRuntime(city,(outward,invalid))
    model = ReleaseRuntime(city,(outward,))
    with pytest.raises(CityContractError,match='intent holding'):
        model.check(replace(model.initial(),road_intent_hold=1))
