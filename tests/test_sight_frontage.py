from dataclasses import replace
import math
import pytest
from metroflow.environment.terrain import Terrain
from metroflow.restored_city import RoadMap, Junction, Section
from metroflow.restored_geometry import ground_profile
from metroflow.frontage_growth import grow_access, Site
from metroflow.sight_frontage import SightRule,SightClass


def fixture(ridge=8.):
    heights=tuple(z for _ in range(5) for z in (0.,0.,ridge,0.,0.))
    t=Terrain(4,100.,heights)
    pts,length,grade=ground_profile(t,((0.,200.),(400.,200.)))
    r=Section('street','a','b',pts,'collector','surface',1,1,length,grade)
    city=RoadMap('fixture',t,(Junction('a',pts[0]),Junction('b',pts[-1])),(r,))
    from metroflow.frontage_growth import _projection
    proj=_projection((230.,240.),r.points)
    return city,r,proj


def test_crest_rejects_sight_hidden_frontage_but_flat_control_accepts():
    c,r,p=fixture()
    assert SightRule()(c,Site('x',(230.,240.)),r,p)=='sight_obstructed'
    c,r,p=fixture(0.)
    assert SightRule()(c,Site('x',(230.,240.)),r,p) is None


def test_unknown_approach_extent_is_not_treated_as_infinite_visibility():
    c,r,_=fixture(0.)
    from metroflow.frontage_growth import _projection
    p=_projection((10.,250.),r.points)
    assert SightRule()(c,Site('x',(10.,250.)),r,p)=='sight_extent_unknown'


def test_frontage_generator_honors_optional_gate_without_editing_old_city():
    c,_,_=fixture(0.)
    sites=(Site('x',(230.,240.)),)
    legacy=grow_access(c,sites,budget_m=100.)
    assert len(legacy.admitted)==1
    denied=grow_access(c,sites,budget_m=100.,admission_rule=lambda *args:'declared_test_gate')
    assert not denied.admitted
    assert denied.rejected==( ('x','declared_test_gate'), )
    assert denied.city==c
    assert grow_access(c,sites,budget_m=100.,admission_rule=None)==legacy


def test_class_braking_and_downhill_change_required_distance():
    from metroflow.sight_frontage import stopping_distance
    assert stopping_distance(10.,1.,5.,0.,0.)==pytest.approx(20.)
    assert stopping_distance(10.,1.,5.,.1,0.)>20.
    c,r,p=fixture(0.)
    car=SightRule((SightClass('car',1.,4.,1.2),))
    truck=SightRule((SightClass('truck',1.5,2.,2.5),))
    assert truck.assess(c,r,p)[0].required_m>car.assess(c,r,p)[0].required_m
    assert math.isinf(stopping_distance(10.,1.,.2,.1))
    with pytest.raises(ValueError):SightClass(brake_mps2=0.)
    with pytest.raises(ValueError):SightRule(classes=())
