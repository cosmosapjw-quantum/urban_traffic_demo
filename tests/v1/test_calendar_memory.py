"""Immutable calendar sharing must preserve all scientific and checkpoint values."""
from dataclasses import FrozenInstanceError, asdict, replace

import pytest

from metroflow.v1.access_audit import fixture_city
from metroflow.v1.activity import compile_activity
from metroflow.v1.checkpoint import decode, encode
import metroflow.v1.demand as demand
import metroflow.v1.factorized_demand as factorized
from metroflow.v1.schedules import daily_profiles


def inputs(count=2):
    city=fixture_city()
    home=compile_activity(city,'block')
    job=compile_activity(city,'block','job')
    homes=tuple(replace(home,block_id=f'h{i}') for i in range(count))
    jobs=tuple(replace(job,block_id=f'j{i}') for i in range(count))
    return homes,jobs


def test_shared_profiles_preserve_dense_lazy_identity_values_and_checkpoint(monkeypatch):
    homes,jobs=inputs()
    options=dict(worker_fraction=.1,service_fraction=0)
    with monkeypatch.context() as old:
        old.setattr(demand,'calendar_profiles',daily_profiles)
        old.setattr(factorized,'calendar_profiles',daily_profiles)
        baseline=demand.compile_daily_demand(homes,jobs,**options)
        baseline_lazy=factorized.compile_factorized_demand(homes,jobs,**options)
        baseline_legs=tuple(baseline_lazy.iter_legs())
    demand.calendar_profiles.cache_clear()
    compact=demand.compile_daily_demand(homes,jobs,**options)
    lazy=factorized.compile_factorized_demand(homes,jobs,**options)
    legs=tuple(lazy.iter_legs())
    assert compact.identity==baseline.identity
    assert asdict(compact)==asdict(baseline)
    assert lazy.identity==baseline_lazy.identity
    assert legs==baseline_legs==compact.legs
    assert encode(legs)==encode(baseline_legs)
    assert decode(encode(legs))==legs
    assert len({id(leg.departures) for leg in legs})==2
    assert len({leg.id for leg in legs})==len(legs)
    assert legs[0].amounts==baseline_legs[0].amounts


def test_shared_profile_registry_is_bounded_and_deeply_immutable():
    demand.calendar_profiles.cache_clear()
    for day in ('weekday','weekend'):
        for purpose in ('work','school','service','delivery'):
            pair=demand.calendar_profiles(day,purpose)
            assert pair is demand.calendar_profiles(day,purpose)
            for profile in pair:
                if profile is None:
                    continue
                assert isinstance(profile.windows,tuple)
                with pytest.raises(FrozenInstanceError):
                    profile.windows=()
                with pytest.raises(FrozenInstanceError):
                    profile.windows[0].probability=0
    assert demand.calendar_profiles.cache_info().currsize==8
    assert demand.calendar_profiles.cache_info().maxsize==8
