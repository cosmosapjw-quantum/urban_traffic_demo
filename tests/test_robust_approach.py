import math
import pytest
from metroflow.sight_frontage import SightClass,SightRule,stopping_distance
from metroflow.environment.terrain import Terrain
from metroflow.restored_city import Junction,Section,RoadMap
from metroflow.restored_geometry import ground_profile
from metroflow.frontage_growth import _projection,Site,grow_access


def visibility_fixture(flat=False):
    knots=((0.,0.),(200.,0.),(250.,2.2),(270.,0.),(285.,1.2),(300.,0.),(400.,0.))
    def height(x):
        if flat:return 0.
        for (a,b),(c,d) in zip(knots,knots[1:]):
            if a<=x<=c:return b+(d-b)*(x-a)/(c-a)
    t=Terrain(80,5.,tuple(height(i*5.) for j in range(81) for i in range(81)))
    pts,length,grade=ground_profile(t,((0.,200.),(400.,200.)))
    road=Section('r','a','b',pts,'collector','surface',1,1,length,grade)
    city=RoadMap('visibility',t,(Junction('a',pts[0]),Junction('b',pts[-1])),(road,))
    return city,road,_projection((300.,240.),pts)


def test_reaction_acceleration_is_part_of_required_braking_distance():
    assert stopping_distance(10.,2.,4.,margin=0.,reaction_accel=2.)==pytest.approx(48.5)
    assert stopping_distance(10.,2.,4.,margin=0.)==pytest.approx(32.5)


def test_far_point_clear_does_not_imply_clear_approach():
    c,r,p=visibility_fixture()
    assert all(q.reason is None for q in SightRule().assess(c,r,p))
    rows=SightRule(approach_step_m=2.).assess(c,r,p)
    assert any(q.reason=='sight_obstructed' for q in rows)
    assert min(q.clearance_m for q in rows if q.clearance_m is not None)<-.2


def test_scan_budget_is_unknown_not_success():
    c,r,p=visibility_fixture(flat=True)
    rows=SightRule(approach_step_m=.01,max_samples_per_direction=2).assess(c,r,p)
    assert all(q.reason=='sight_sampling_budget' for q in rows)


def test_flat_screening_and_actual_generator_gate():
    c,r,p=visibility_fixture(flat=True)
    rule=SightRule((SightClass(reaction_accel_mps2=1.),),approach_step_m=5.)
    assert all(q.reason is None for q in rule.assess(c,r,p))
    c,r,p=visibility_fixture()
    sites=(Site('target',(300.,240.)),)
    old=grow_access(c,sites,budget_m=100.,admission_rule=SightRule())
    new=grow_access(c,sites,budget_m=100.,admission_rule=SightRule(approach_step_m=2.))
    assert len(old.admitted)==1 and not new.admitted
    assert new.city==c


def test_invalid_reaction_and_scan_inputs():
    with pytest.raises(ValueError):SightClass(reaction_accel_mps2=-1.)
    with pytest.raises(ValueError):SightRule(approach_step_m=0.)
    with pytest.raises(ValueError):SightRule(max_samples_per_direction=True)
    with pytest.raises(ValueError):stopping_distance(10.,1.,4.,reaction_accel=math.nan)
