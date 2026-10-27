"""Exact coupling equivalence and explicit worker shortfall conservation."""
from dataclasses import replace
import math

import pytest

from metroflow.v1.access_audit import fixture_city
from metroflow.v1.activity import compile_activity
from metroflow.v1.city import CityContractError
from metroflow.v1.demand import compile_daily_demand
from metroflow.v1.factorized_demand import compile_factorized_demand


def measures():
    city = fixture_city()
    home = compile_activity(city,'block')
    jobs = compile_activity(city,'block','job')
    services = compile_activity(city,'block','service',service_stock=300)
    homes = (replace(home,patches=tuple(replace(p,mass=p.mass*.4) for p in home.patches)),
             replace(home,block_id='second',patches=tuple(replace(p,mass=p.mass*.6) for p in home.patches)))
    return homes,(jobs,),(services,)


def test_lazy_exact_dense_equivalence_including_birth_profiles_and_freight():
    homes,jobs,services = measures()
    options = dict(worker_fraction=.1,service_fraction=.4,external_service_fraction=.25,
                   school_share=.3,freight_kg=1000,minimum_dwell_s=100)
    dense = compile_daily_demand(homes,jobs,services,**options)
    lazy = compile_factorized_demand(homes,jobs,services,**options)
    records = tuple(lazy.iter_records())
    assert tuple(c for c,_ in records) == dense.cohorts
    assert tuple(lazy.iter_legs()) == dense.legs
    chunks = tuple(lazy.iter_chunks(3))
    assert all(len(chunk) <= 3 for chunk in chunks)
    assert tuple(r for chunk in chunks for r in chunk) == records
    for a,b in zip(lazy.iter_legs(),dense.legs):
        assert a.departures.first_moment_s(0,86400) == b.departures.first_moment_s(0,86400)
    assert math.fsum(c.persons for c,_ in records) == pytest.approx(1000)


def test_worker_shortfall_strict_default_and_explicit_home_ledger():
    homes,jobs,services = measures()
    with pytest.raises(CityContractError,match='workers exceed'):
        compile_factorized_demand(homes,jobs,services)
    schedule = compile_factorized_demand(homes,jobs,services,worker_shortfall='unassigned_home')
    assert schedule.requested_workers == 500
    assert schedule.allocated_workers == 200
    assert schedule.unassigned_workers == 300
    records = tuple(schedule.iter_records())
    assert math.fsum(c.persons for c,_ in records) == pytest.approx(1000)
    unassigned = [c for c,_ in records if c.purpose == 'unassigned_work']
    assert math.fsum(c.persons for c in unassigned) == 300
    assert all(c.outbound_id is None and c.return_id is None for c in unassigned)
    assert math.fsum(c.persons for c,_ in records if c.purpose=='work') == pytest.approx(200)


def test_factor_budget_counts_marginals_not_cartesian_support():
    homes,jobs,services = measures()
    homes = tuple(replace(homes[0],block_id=f'h{i}') for i in range(150))
    jobs = tuple(replace(jobs[0],block_id=f'j{i}') for i in range(150))
    schedule = compile_factorized_demand(homes,jobs,(),service_fraction=0,max_factors=303)
    assert len(next(schedule.iter_chunks(2))) == 2
    with pytest.raises(CityContractError,match='factor budget'):
        compile_factorized_demand(homes,jobs,(),service_fraction=0,max_factors=302)
    with pytest.raises(CityContractError,match='chunk'):
        next(schedule.iter_chunks(0))
