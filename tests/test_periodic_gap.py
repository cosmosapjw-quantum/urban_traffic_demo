import math
from dataclasses import replace
import pytest
from metroflow.foundation_kinetics import VehicleClass
from metroflow.periodic_gap import RingCell,make_ring,advance_ring,observe_ring
from metroflow.gap_transport import ViabilityError


def cells():
    c=VehicleClass()
    return tuple(RingCell(c,h,v) for h,v in ((45.,12.),(55.,8.),(40.,10.),(60.,6.)))


def test_simultaneous_leader_controls_change_motion_and_preserve_ring_length():
    s=make_ring(cells(),10);old=s
    for _ in range(120):
        s,evidence=advance_ring(s,.25,20.)
        o=observe_ring(s)
        assert o['length_residual_m']==pytest.approx(0.,abs=1e-9)
        assert o['pair_marginal_l1']==0.
        assert min(x['min_gap_m'] for x in evidence)>=2.-1e-9
    assert s.time_s==30. and s.cells[0].travelled_m>0
    assert s.cells!=old.cells and old.time_s==0.


def test_repeated_population_matches_explicit_small_expansion():
    small=make_ring(cells(),7);expanded=make_ring(cells()*7,1)
    for _ in range(80):
        small,_=advance_ring(small,.25,20.);expanded,_=advance_ring(expanded,.25,20.)
        for i,c in enumerate(expanded.cells):
            a=small.cells[i%4]
            assert (c.gap_m,c.speed_mps,c.travelled_m)==pytest.approx((a.gap_m,a.speed_mps,a.travelled_m),abs=1e-11)
    assert small.lane_length_m==expanded.lane_length_m
    assert observe_ring(small)['vehicles']==observe_ring(expanded)['vehicles']==28


def test_weight_growth_requires_proportionally_longer_real_lane():
    a=make_ring(cells(),1);b=make_ring(cells(),25000)
    assert len(a.cells)==len(b.cells)==4
    assert b.lane_length_m==25000*a.lane_length_m
    a,_=advance_ring(a,.25,20.);b,_=advance_ring(b,.25,20.)
    assert a.cells==b.cells
    assert observe_ring(b)['vehicles']==100000
    assert observe_ring(b)['density_veh_m']==pytest.approx(observe_ring(a)['density_veh_m'])


def test_mixed_classes_keep_their_own_response_and_braking():
    c=VehicleClass();truck=VehicleClass('truck',15.,4.,.7,2.,3.,1.5,12.)
    s=make_ring((RingCell(c,80.,4.),RingCell(truck,80.,4.)),10)
    new,_=advance_ring(s,1.,15.)
    assert new.cells[0].speed_mps>new.cells[1].speed_mps
    assert observe_ring(new)['pair_marginal_l1']==0.
    assert new.lane_length_m==s.lane_length_m


def test_infeasible_state_preserved_without_forced_spacing():
    s=make_ring((RingCell(VehicleClass(),0.,20.),RingCell(VehicleClass(),50.,0.)),1)
    with pytest.raises(ViabilityError) as exc:advance_ring(s,.25,20.)
    assert exc.value.checkpoint==s and s.cells[0].gap_m==0.


def test_realizability_requires_integer_repetition_and_fixed_geometry():
    for bad in (0,-1,1.5,True):
        with pytest.raises(ValueError):make_ring(cells(),bad)
    s=make_ring(cells(),2)
    with pytest.raises(ValueError):advance_ring(replace(s,lane_length_m=s.lane_length_m-1.),.25,20.)
    with pytest.raises(ValueError):advance_ring(s,0.,20.)


@pytest.mark.parametrize('dt',(.5,.25,.1))
def test_inactive_safety_filter_preserves_predicted_growing_mode(dt):
    # Independent linearized held-control matrix, not a stability requirement.
    import cmath
    k=32;wave=2*math.pi/k;z=cmath.exp(1j*wave)-1
    rate=-math.expm1(-dt/2)/dt
    a=1+.5*rate*dt*dt*z;b=z*(dt-.5*rate*dt*dt);c=rate*dt;d=1-rate*dt
    trace=a+d;det=a*d-b*c
    eigen=max(((trace+cmath.sqrt(trace*trace-4*det))/2,
               (trace-cmath.sqrt(trace*trace-4*det))/2),key=abs)
    ratio=(eigen-a)/b
    cells=tuple(RingCell(VehicleClass(),14+1e-4*cmath.exp(1j*wave*i).real,
                 12+1e-4*(ratio*cmath.exp(1j*wave*i)).real) for i in range(k))
    state=make_ring(cells)
    mode=lambda s:2/k*sum((c.gap_m-14)*cmath.exp(-1j*wave*i) for i,c in enumerate(s.cells))
    initial=mode(state)
    for step in range(round(10/dt)):
        old=state;state,proof=advance_ring(state,dt,30.)
        for cell,p in zip(old.cells,proof):
            assert p['acceleration_mps2']==pytest.approx(rate*(cell.gap_m-2-cell.speed_mps),abs=1e-10)
    assert abs(eigen)>1 and mode(state)==pytest.approx(initial*eigen**round(10/dt),abs=2e-12)
