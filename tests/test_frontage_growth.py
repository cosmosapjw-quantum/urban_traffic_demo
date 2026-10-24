import math
from dataclasses import replace
import pytest
from metroflow.environment.terrain import Terrain,Rect
from metroflow.restored_city import RoadMap,Junction,Section
from metroflow.frontage_growth import Site,grow_access
from metroflow.restored_geometry import crossing_audit,components

def straight():
    ns=(Junction('a',(0.,100.,0.)),Junction('b',(400.,100.,0.)))
    e=Section('ab','a','b',tuple(n.xyz for n in ns),'local','surface',1,1,400.,0.)
    return RoadMap('straight',Terrain(1,500.,(0.,)*4),ns,(e,))

def test_site_gets_a_physical_road_and_a_midsegment_junction():
    old=straight();r=grow_access(old,(Site('home',(200.,220.),10.),),budget_m=130.)
    assert len(r.admitted)==1, 'Site still teleports to a distant old endpoint'
    assert len(r.city.nodes)==4 and len(r.city.sections)==3
    sid,node,join,length=r.admitted[0]
    assert sid=='home' and length==pytest.approx(120.)
    by={n.id:n for n in r.city.nodes}
    assert by[join].xyz==pytest.approx((200.,100.,0.))
    assert by[node].xyz==pytest.approx((200.,220.,0.))
    assert sum(s.length_m for s in r.city.sections)==pytest.approx(520.)
    assert not crossing_audit(r.city)['illegal']
    assert len(set(components(r.city).values()))==1
    assert len(old.sections)==1  # immutable input

def test_budget_and_obstacle_are_not_relaxed():
    c=straight();s=(Site('home',(200.,220.)),)
    assert not grow_access(c,s,budget_m=100.).admitted
    t=replace(c.terrain,water=(Rect(0.,150.,500.,160.),))
    assert not grow_access(replace(c,terrain=t),s,budget_m=200.).admitted

def test_no_frontage_on_mainline_or_bridge():
    c=straight()
    for facility in ('mainline','bridge','ramp'):
        bad=replace(c,sections=(replace(c.sections[0],facility=facility),))
        assert not grow_access(bad,(Site('x',(200.,220.)),)).admitted

def test_two_sites_preserve_cycle_rank_and_budget_replay():
    c=straight();sites=(Site('x',(100.,220.),2.),Site('y',(300.,240.),1.))
    a=grow_access(c,sites,budget_m=300.);b=grow_access(c,sites,budget_m=300.)
    assert a==b and len(a.admitted)==2
    assert a.used_length_m==pytest.approx(260.)
    assert len(a.city.sections)-len(a.city.nodes)+1==0
    assert not crossing_audit(a.city)['illegal']

def test_invalid_site_contract_and_no_zero_length_insertion():
    with pytest.raises(ValueError):grow_access(straight(),(Site('x',(math.nan,1.)),))
    with pytest.raises(ValueError):grow_access(straight(),(Site('x',(1.,1.)),Site('x',(2.,2.))))
    assert not grow_access(straight(),(Site('on',(200.,100.)),)).admitted

def test_already_fronting_site_does_not_create_half_metre_road():
    r=grow_access(straight(),(Site('near',(200.,100.5)),))
    assert not r.admitted, 'Submetre road is a discretization artifact, not new frontage'
    assert r.rejected==(('near','already_fronting'),)

def test_near_endpoint_attachment_does_not_leave_two_metre_parent_fragment():
    r=grow_access(straight(),(Site('near_end',(2.,220.)),))
    assert r.admitted
    assert len(r.city.nodes)==3 and len(r.city.sections)==2
    assert r.admitted[0][2]=='a'
