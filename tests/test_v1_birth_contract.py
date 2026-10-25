"""Observe the old clock reset, then reuse the identical seam after the repair."""
from dataclasses import replace
import pytest
from metroflow.packet_network import PacketNetwork
from metroflow.ordered_network import Group, Route
from metroflow.ordered_lane import Lane


def model():
    return PacketNetwork((Group('road','O','D',Lane(100.,10.,10.,10.,100.,interaction_rate=0.)),),
                         (Route('trip',('road',)),))


def offer_with_original_birth(m,s,tag,mass,birth):
    if hasattr(m,'step_measures'):
        return m.step_measures(s,((tag,mass,birth),))
    # Actual parent behavior: resetting time at the road boundary loses access.
    return m.step(s,((tag,mass),))


def test_original_birth_survives_entry_after_ten_seconds_access():
    m=model();s=m.initial(start_s=10.)
    s,_=offer_with_original_birth(m,s,'trip',1.,0.)
    assert s.birth_moment==0., 'Road entry reset the original journey clock'
    while s.completed<1.-1e-12:s,_=m.step(s)
    assert s.system_vehicle_seconds==pytest.approx(21.05)
    assert s.pre_entry_seconds==pytest.approx(10.)


def test_invalid_future_birth_fails_atomically():
    m=model();s=m.initial(start_s=10.)
    with pytest.raises(ValueError):offer_with_original_birth(m,s,'trip',1.,11.)
    assert s.released==0.
