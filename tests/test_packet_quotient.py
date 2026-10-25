from dataclasses import replace
import math
import pytest
from metroflow.ordered_lane import Lane
from metroflow.ordered_network import Group,Route
from metroflow.packet_network import PacketNetwork


def merge_trial(a,b,fragment=False):
    groups=(Group(a,'A','M',Lane(1,10,1,1,20,interaction_rate=0)),
            Group(b,'B','M',Lane(1,10,1,1,20,interaction_rate=0)),
            Group('c','M','D',Lane(1,10,2,.25,20,interaction_rate=0)))
    model=PacketNetwork(groups,(Route('F',(a,'c')),Route('G',(b,'c'))))
    state=model.initial();done={'F':0.,'G':0.};moment=dict(done)
    offers=(('F',1.),('G',1.)) if not fragment else (('F',.25),('G',.5),('F',.75),('G',.5))
    for i in range(25):
        state,events=model.step(state,offers if i==0 else ())
        for e in events:
            if e.destination is None:
                done[e.tag]+=e.mass;moment[e.tag]+=e.mass*(e.start_s+e.end_s)/2
    return {k:moment[k]/done[k] for k in done}


def test_lane_id_relabel_does_not_set_physical_merge_order():
    a=merge_trial('a','b');b=merge_trial('b','a')
    assert a==pytest.approx(b,abs=1e-11)


def test_physical_exchange_symmetry_of_simultaneous_equal_inflows():
    a=merge_trial('a','b')
    assert a['F']==pytest.approx(a['G'],abs=1e-11)


def run(model,steps,offers=(),start=0.):
    s=model.initial(start_s=start);events=[]
    for k in range(steps):
        s,ev=model.step(s,offers if k==0 else ());events.extend(ev)
    return s,events


def test_fragment_and_offer_list_representations_are_equivalent():
    assert merge_trial('a','b')==pytest.approx(merge_trial('a','b',fragment=True),abs=1e-11)
    groups=(Group('g','O','D',Lane(100,10,20,1,100,interaction_rate=0)),)
    m=PacketNetwork(groups,(Route('R',('g',)),));a,b=m.initial(),m.initial()
    for k in range(40):
        a,_=m.step(a,(('R',10.),) if k==0 else ())
        b,_=m.step(b,(('R',.01),)*1000 if k==0 else ())
        assert a.completed==pytest.approx(b.completed,abs=1e-10)
        assert a.system_vehicle_seconds==pytest.approx(b.system_vehicle_seconds,abs=1e-9)
        assert m.counts(a)==m.counts(b)
    assert a.completed==pytest.approx(10.)


def test_clock_origin_is_a_gauge_and_time_units_are_not_speed_changes():
    m=PacketNetwork((Group('g','O','D',Lane(100,10,2,1,30)),),(Route('R',('g',)),))
    a=m.initial()
    for k in range(4):a,_=m.step(a,(('R',1.),))
    b=m.rebase_clock(a,(-3500.,))
    assert b.cells[0].progress_m!=a.cells[0].progress_m
    for _ in range(40):
        a,ea=m.step(a);b,eb=m.step(b)
        assert a.completed==pytest.approx(b.completed,abs=1e-10)
        assert a.system_vehicle_seconds==pytest.approx(b.system_vehicle_seconds,abs=1e-8)
    assert a.completed==pytest.approx(4.)


def test_physical_priority_breaks_exchange_symmetry_without_using_names():
    def trial(priority):
        groups=(Group('a','A','M',Lane(1,10,10,10,30,interaction_rate=0),priority),
                Group('b','B','M',Lane(1,10,10,10,30,interaction_rate=0)),
                Group('c','M','D',Lane(1,10,1,1,30,interaction_rate=0)))
        m=PacketNetwork(groups,(Route('F',('a','c')),Route('G',('b','c'))))
        s,ev=run(m,3,(('F',10.),('G',10.)))
        return {k:math.fsum(e.mass for e in ev if e.source==k and e.start_s==1.1) for k in ('a','b')}
    equal=trial(1.);unequal=trial(3.)
    assert equal['a']==pytest.approx(equal['b'])
    assert unequal['a']==pytest.approx(3*unequal['b'])


def test_shared_mixed_packet_blocks_as_a_unit_but_independent_lane_moves():
    from metroflow.active_suffix.common import Signal
    gs=(Group('a','O','M',Lane(1,10,10,10,30,interaction_rate=0)),
        Group('z','Z','M',Lane(1,10,10,10,30,interaction_rate=0)),
        Group('b','M','B',Lane(1,10,10,10,30,interaction_rate=0)),
        Group('c','M','C',Lane(1,10,10,10,30,interaction_rate=0)))
    m=PacketNetwork(gs,(Route('X',('a','b')),Route('Y',('a','c')),Route('free',('z','c'))),windows=(('b',0.,10.,0.),))
    s,events=run(m,9,(('X',1.),('Y',1.),('free',1.)))
    assert not any(e.tag in ('X','Y') for e in events)
    assert any(e.tag=='free' and e.destination is None for e in events)
    for _ in range(20):s,_=m.step(s)
    assert s.completed==pytest.approx(3.)


def test_different_entry_times_are_physical_order_not_representation():
    m=PacketNetwork((Group('g','O','D',Lane(100,10,1,1,30,interaction_rate=0)),),
                    (Route('first',('g',)),Route('later',('g',))))
    s=m.initial();s=replace(s,cells=(replace(s.cells[0],activity=.1),));events=[]
    for k in range(70):
        s,e=m.step(s,(('first',.1),) if k==0 else (('later',.1),) if k==10 else ())
        events.extend(e)
    assert max(e.end_s for e in events if e.tag=='first')<=min(e.start_s for e in events if e.tag=='later')


def test_mass_storage_and_residence_across_closure_and_reopening():
    from metroflow.active_suffix.common import Signal
    gs=(Group('a','O','M',Lane(10,10,1,1,1),signal=Signal(4,2)),Group('b','M','D',Lane(10,10,1,1,1)))
    m=PacketNetwork(gs,(Route('R',('a','b')),),windows=(('b',4.,8.,0.),))
    s=m.initial()
    for k in range(100):
        s,e=m.step(s,(('R',5.),) if k==0 else ())
        m.check(s)
        assert all(c.occupancy<=g.physics.storage+1e-10 for c,g in zip(s.cells,m.groups))
    assert s.completed==pytest.approx(5.)
    assert s.system_vehicle_seconds==pytest.approx(sum(c.residence(s.time_s) for c in s.cells)+s.source_wait_seconds+s.transfer_hold_seconds)


def test_time_origin_shift_requires_shifting_signal_and_incident_not_frozen_clock():
    from metroflow.active_suffix.common import Signal
    g=Group('a','O','D',Lane(10,10,1,1,10),signal=Signal(6,4,0))
    a=PacketNetwork((g,),(Route('R',('a',)),),windows=(('a',2.,8.,0.),))
    b=PacketNetwork((replace(g,signal=Signal(6,4,20)),),(Route('R',('a',)),),windows=(('a',22.,28.,0.),))
    x,ex=run(a,60,(('R',3.),));y,ey=run(b,60,(('R',3.),),start=20.)
    assert x.completed==pytest.approx(y.completed)
    assert x.system_vehicle_seconds==pytest.approx(y.system_vehicle_seconds,abs=1e-9)
    assert [e.end_s for e in ex]==pytest.approx([e.end_s-20 for e in ey])


def test_record_budget_is_atomic_and_invalid_state_is_rejected():
    from metroflow.active_suffix.common import BudgetExceeded
    m=PacketNetwork((Group('g','O','D',Lane()),),(Route('x',('g',)),Route('y',('g',))),record_budget=1)
    s=m.initial()
    with pytest.raises(BudgetExceeded) as exc:m.step(s,(('x',.5),('y',.5)))
    assert exc.value.checkpoint==s and s.released==0
    with pytest.raises(ValueError):m.step(replace(s,birth_moment=float('nan')))


def test_empty_and_corrupted_packet_is_not_a_valid_quotient_state():
    from metroflow.packet_network import Packet
    m=PacketNetwork((Group('g','O','D',Lane()),),(Route('x',('g',)),))
    s=m.initial()
    with pytest.raises(ValueError):m.check(replace(s,cells=(replace(s.cells[0],packets=(Packet(1.,()),)),)))
