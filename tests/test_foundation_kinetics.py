import math
from dataclasses import replace
import pytest
from metroflow.foundation_kinetics import VehicleClass,PhaseBin,characteristic,evolve,moments,passage,mean_passage


def test_actual_speed_is_continuous_and_acceleration_is_bounded():
    c=VehicleClass()
    x,v=characteristic(c,0.,10.,1.)
    assert v==pytest.approx(2.) and x==pytest.approx(1.)
    for t in (0.,.1,1.,5.):
        x,v=characteristic(c,0.,10.,t)
        assert 0<=v<=min(10.,2*t)+1e-12


def test_unsaturated_solution_is_exact_characteristic_not_instant_target():
    c=VehicleClass(response_s=5.)
    x,v=characteristic(c,2.,8.,2.)
    assert v==pytest.approx(8.-6.*math.exp(-.4))
    assert x==pytest.approx(16.-30.*(1-math.exp(-.4)))
    t,vend=passage(c,2.,8.,100.)
    assert characteristic(c,2.,8.,t)[0]==pytest.approx(100.,abs=1e-9)


def test_same_mean_gap_different_correlations_remain_distinguishable():
    c=VehicleClass()
    a=(PhaseBin(100.,20.,2.),)
    b=(PhaseBin(50.,5.,2.),PhaseBin(50.,35.,2.))
    ma=moments(evolve(c,a,1.,20.));mb=moments(evolve(c,b,1.,20.))
    assert ma[0]==mb[0]==100.
    assert ma[1]!=pytest.approx(mb[1]) and mb[2]>0
    scaled=tuple(replace(x,mass=x.mass*1000) for x in b)
    out=evolve(c,scaled,1.,20.)
    assert len(out)==2 and moments(out)[0]==100000.
    assert moments(out)[1:]==pytest.approx(mb[1:])


def test_mean_first_passage_not_inverse_mean_speed():
    c=VehicleClass()
    bins=(PhaseBin(.5,7.,5.),PhaseBin(.5,17.,15.))
    assert mean_passage(c,bins,20.,100.)==pytest.approx(40/3)
    assert 100/moments(bins)[1]==10.


def test_stopping_target_has_finite_coast_distance_not_teleport_stop():
    c=VehicleClass(response_s=2.,brake_mps2=3.)
    assert math.isfinite(passage(c,10.,0.,10.)[0])
    assert math.isinf(passage(c,10.,0.,23.)[0])
    assert passage(c,0.,0.,0.)==(0.,0.)


def test_characteristic_semigroup_and_type_specific_response():
    car=VehicleClass();truck=VehicleClass('truck',15.,4.,.7,2.,3.,1.5,12.)
    for v0,u,t,s in ((0.,20.,3.,7.),(20.,0.,2.,8.),(5.,7.,.3,4.)):
        x,v=characteristic(car,v0,u,t)
        y,w=characteristic(car,v,u,s)
        total,end=characteristic(car,v0,u,t+s)
        assert (x+y,w)==pytest.approx((total,end),abs=1e-10)
    assert characteristic(car,0.,10.,1.)[1]>characteristic(truck,0.,10.,1.)[1]


def test_invalid_inputs_and_explicit_vacuum_convention():
    with pytest.raises(ValueError):VehicleClass(response_s=0.)
    with pytest.raises(ValueError):PhaseBin(-1.,3.,1.)
    with pytest.raises(ValueError):characteristic(VehicleClass(),1.,2.,math.nan)
    assert moments(())==(0.,0.,0.)
    with pytest.raises(ValueError):mean_passage(VehicleClass(),(),10.,10.)
