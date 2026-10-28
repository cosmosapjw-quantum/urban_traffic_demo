"""Legal route-state cache, exact page coverage and bounded cache storage."""
from dataclasses import replace
import math

import pytest

from metroflow.active_suffix.routing import Arc
from metroflow.v1.activity import compile_activity
from metroflow.v1.city import CityContractError
from metroflow.v1.factorized_demand import compile_factorized_demand
from metroflow.v1.release_plan import LegalRouteCache, ReleasePlan
from metroflow.v1.scenarios import scenario_city


def test_routes_follow_link_turns_instead_of_undirected_node_contact():
    arcs = (Arc('oa','o','a'), Arc('ad','a','d'), Arc('ab','a','b'), Arc('ba','b','a'))
    # Direct a->d is forbidden after o->a: revisit a via legal link states.
    cache = LegalRouteCache(arcs, dict.fromkeys((a.id for a in arcs),1),
                            {('oa','ab'),('ab','ba'),('ba','ad')}, max_sources=1)
    assert cache.resolve('o','d') == ('oa','ab','ba','ad')
    assert cache.resolve('d','o') is None
    assert len(cache.cached_sources) == 1
    assert cache.resolve('o','d') == ('oa','ab','ba','ad')
    assert cache.tree_builds == 3
    assert cache.resolve('o','o') == ()
    with pytest.raises(CityContractError, match='unknown'):
        cache.resolve('missing','d')


def fixture():
    city = scenario_city(1000)
    homes = tuple(compile_activity(city,b.id) for b in city.face_graph.blocks if b.residents)
    jobs = tuple(compile_activity(city,b.id,'job') for b in city.face_graph.blocks if b.jobs)
    services = tuple(compile_activity(city,b.id,'service',service_stock=b.jobs)
                     for b in city.face_graph.blocks if b.jobs)
    schedule = compile_factorized_demand(homes,jobs,services,worker_shortfall='unassigned_home',
                                         external_service_fraction=.1, freight_kg=100)
    return city, schedule


def test_exact_closed_form_totals_match_full_iteration_and_pages_preserve_legs():
    city, schedule = fixture()
    plan = ReleasePlan(city,schedule,max_sources=1,max_access_laws=1)
    expected = tuple(schedule.iter_legs())
    totals = plan.totals()
    assert totals['legs'] == len(expected)
    for unit in ('persons','vehicles','cargo_kg'):
        assert totals[unit] == pytest.approx(math.fsum(getattr(t.amounts,unit) for t in expected))
    cursor, output = plan.cursor(), []
    while True:
        cursor, page = plan.take(cursor,3)
        output.extend(p.leg for p in page)
        if not page:
            break
    assert tuple(output) == expected
    summary = plan.summary(cursor)
    assert summary['remaining_legs'] == 0
    assert all(abs(x)<1e-9 for x in summary['remaining_amounts'].values())
    assert summary['execution'] == 'NOT_RUN'
    assert len(plan.routes.cached_sources) <= 1
    assert len(plan._access) <= 1
    with pytest.raises(CityContractError,match='cursor'):
        plan.take(replace(cursor,schedule_identity='stale'),3)


def test_partial_page_does_not_hide_remaining_demand_or_claim_execution():
    city, schedule = fixture()
    plan = ReleasePlan(city,schedule)
    cursor, page = plan.take(plan.cursor(),1)
    assert len(page) == 1
    report = plan.summary(cursor)
    assert report['remaining_legs'] == plan.totals()['legs']-1
    for unit in ('persons','vehicles','cargo_kg'):
        assert report['remaining_amounts'][unit] + getattr(page[0].leg.amounts,unit) == pytest.approx(plan.totals()[unit])
    assert report['calendar']['requested_workers'] == pytest.approx(
        report['calendar']['allocated_workers']+report['calendar']['unassigned_workers'])
    assert report['execution'] == 'NOT_RUN'


def test_restored_cursor_cannot_invent_materialization_or_negative_remaining():
    city, schedule = fixture()
    plan = ReleasePlan(city,schedule)
    initial = plan.cursor()
    with pytest.raises(CityContractError,match='prefix'):
        plan.summary(replace(initial,materialized_persons=1))
    with pytest.raises(CityContractError,match='exceeds'):
        plan.summary(replace(initial,materialized_persons=plan.totals()['persons']+1))
    cursor,_ = plan.take(initial,1)
    with pytest.raises(CityContractError,match='prefix'):
        plan.take(replace(cursor,materialized_persons=0),1)
