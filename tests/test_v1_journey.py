from dataclasses import replace
import pytest
from metroflow.ordered_lane import Lane
from metroflow.ordered_network import Group,Route
from metroflow.packet_network import PacketNetwork
from metroflow.v1.journey import DelayLaw,JourneyBoundary,JourneyModel
from metroflow.active_suffix.common import BudgetExceeded


def model(origin=((2.,.5),(4.,.5)),destination=((3.,1.),),budget=10000,step=1.):
    net=PacketNetwork((Group('public','O','D',Lane(100.,10.,10.,10.,100.,interaction_rate=0.)),),
        (Route('r',('public',)),),dt_s=step)
    return JourneyModel(net,(JourneyBoundary('r',DelayLaw(origin),DelayLaw(destination)),),record_budget=budget)


def run(m,split=False):
    s=m.initial();events=[]
    for k in range(100):
        s,e=m.step(s,tuple(('r',.1) for _ in range(10)) if split and k==0 else (('r',1.),) if k==0 else ())
        events.extend(e)
    return s,events


def test_full_journey_keeps_origin_road_and_destination_once():
    m=model();s,ev=run(m)
    r=m.report(s)
    assert s.completed==pytest.approx(1.)
    assert s.birth_moment==0.
    assert r['residence_vehicle_seconds']['origin_access']==pytest.approx(3.)
    assert r['residence_vehicle_seconds']['destination_egress']==pytest.approx(3.)
    # each half-mass arrives separately: 10 seconds drift + .025 seconds mean service,
    # 1 second source admission split, plus origin mean3 and destination3.
    assert r['mean_journey_s']==pytest.approx(17.025)
    assert sum(x.mass*(x.start_s+x.end_s)/2-x.birth_moment for x in ev)==pytest.approx(s.system_vehicle_seconds)


def test_unfinished_egress_is_not_counted_as_completed_road_trip():
    m=model(destination=((50.,1.),));s=m.initial()
    for k in range(25):s,_=m.step(s,(('r',1.),) if k==0 else ())
    assert s.traffic.completed==pytest.approx(1.) and s.completed==0
    assert m.report(s)['mean_journey_s'] is None
    assert sum(x.mass for x in s.finishing)==pytest.approx(1.)


def test_non_grid_access_wait_is_reported_not_erased():
    m=model(origin=((2.2,1.),),destination=((0.,1.),));s,_=run(m)
    d=m.residence(s)
    assert d['origin_access']==pytest.approx(2.2)
    assert d['entry_grid_hold']==pytest.approx(.8)
    assert d['total']==pytest.approx(sum(v for k,v in d.items() if k!='total'))


def test_fragmentation_and_duplicate_law_atoms_preserve_mean_and_mass():
    a=model();b=model(origin=((2.,.25),(4.,.5),(2.,.25)))
    x,_=run(a);y,_=run(b,split=True)
    assert x.completed==pytest.approx(y.completed)
    assert x.system_vehicle_seconds==pytest.approx(y.system_vehicle_seconds,abs=1e-9)


def test_zero_delay_is_parent_road_clock_not_an_added_private_link():
    m=model(origin=((0.,1.),),destination=((0.,1.),));s=m.initial();p=m.network.initial()
    for i in range(50):
        offers=(('r',1.),) if i==0 else ()
        s,_=m.step(s,offers);p,_=m.network.step(p,offers)
        assert s.completed==pytest.approx(p.completed)
        assert s.system_vehicle_seconds==pytest.approx(p.system_vehicle_seconds)


def test_no_hidden_double_connector_and_atomic_budget_failure():
    net=PacketNetwork((Group('private:r:out','O','D',Lane()),),(Route('r',('private:r:out',)),))
    with pytest.raises(ValueError,match='twice'):
        JourneyModel(net,(JourneyBoundary('r',DelayLaw(((1.,1.),)),DelayLaw(((1.,1.),))),))
    m=model(origin=((5.,.5),(7.,.5)),budget=1);s=m.initial()
    with pytest.raises(BudgetExceeded) as e:m.step(s,(('r',1.),))
    assert e.value.checkpoint==s and s.released==0
    with pytest.raises(ValueError):DelayLaw(((1.,.7),))
    with pytest.raises(ValueError):m.step(replace(s,model_id='changed'))


def test_duplicate_boundary_labels_are_not_silently_overwritten():
    network = PacketNetwork((Group('r', 'O', 'D', Lane(100.,10.,10.,10.,100.,interaction_rate=0.)),),
                            (Route('trip', ('r',)),))
    law = DelayLaw(((0.,1.),))
    with pytest.raises(ValueError, match='duplicate'):
        JourneyModel(network, (JourneyBoundary('trip', law, law), JourneyBoundary('trip', law, law)))
