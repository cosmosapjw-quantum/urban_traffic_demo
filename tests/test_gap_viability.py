"""Model-level contracts, not an empirical road-safety certification."""
from dataclasses import replace
import math
import pytest
from metroflow.stopping_envelope import motion,maximum_closure,hold_brake
from metroflow.gap_transport import PairBin,PairState,LeaderReport,control,step,ViabilityError
from metroflow.foundation_kinetics import VehicleClass


def test_transient_closure_is_not_final_stop_difference():
    peak,t=maximum_closure(20.,15.,-8.,.5,8.,2.)
    assert peak==pytest.approx(25/12) and t==pytest.approx(5/6)
    assert hold_brake(20.,-8.,.5,8.,100.)[0]-motion(15.,-2.,100.)[0]<0


def test_delayed_reaction_and_stopped_leader_match_map_envelope():
    peak,_=maximum_closure(10.,0.,2.,2.,4.,6.)
    assert peak==pytest.approx(48.5)


def test_motion_stops_continuously_without_reverse_travel():
    assert motion(10.,-5.,3.)==pytest.approx((10.,0.))
    assert motion(10.,-5.,1.)==pytest.approx((7.5,5.))


def test_gap_changes_by_relative_displacement_and_preserves_weight():
    c=VehicleClass()
    b=PairBin(c,100.,100.,10.,5.)
    s=PairState(0.,(b,));n,proof=step(s,(LeaderReport(0.,5.),),(0.,),.5,20.,6.)
    old=b;new=n.bins[0]
    assert new.h==pytest.approx(old.h+5*.5-(new.x-old.x))
    assert new.h<old.h and new.mass==old.mass
    assert s.bins[0].h==100.


def test_filter_prevents_crossing_under_immediate_leader_braking():
    c=VehicleClass(brake_mps2=5.)
    s=PairState(0.,(PairBin(c,1.,45.,20.,15.),))
    for _ in range(60):
        report=LeaderReport(s.time_s,s.bins[0].w)
        s,proof=step(s,(report,),(-6.,),.2,25.,6.)
        assert proof[0]['min_gap_m']>=c.min_gap_m-1e-8
        assert 0<=s.bins[0].v
    assert s.bins[0].v<1e-6


def test_empty_robust_certificate_preserves_checkpoint_not_teleport():
    s=PairState(0.,(PairBin(VehicleClass(),5.,3.,20.,0.),))
    with pytest.raises(ViabilityError) as caught:
        step(s,(LeaderReport(0.,0.),),(0.,),.5,20.,6.)
    assert caught.value.checkpoint==s
    assert s.bins[0].x==0 and s.bins[0].h==3


def test_control_cannot_read_hidden_leader_truth():
    c=VehicleClass();report=LeaderReport(0.,12.)
    a=PairBin(c,1.,40.,10.,9.);b=replace(a,w=20.)
    assert control(a,report,1.,.5,20.,6.)==control(b,report,1.,.5,20.,6.)


def test_leader_velocity_bound_uses_age_and_response_is_nonanticipative():
    b=PairBin(VehicleClass(),1.,40.,15.,15.)
    report=LeaderReport(0.,15.)
    fresh=control(b,report,0.,.5,20.,6.)
    stale=control(b,report,1.,.5,20.,6.)
    assert stale<=fresh


def test_mass_scaling_does_not_create_more_phase_nodes():
    bins=(PairBin(VehicleClass(),.5,50.,10.,8.),PairBin(VehicleClass('truck',15.,4.,.7,2.,3.,1.5,12.),.5,100.,10.,8.))
    a=PairState(0.,bins);b=PairState(0.,tuple(replace(x,mass=x.mass*100000) for x in bins))
    for _ in range(20):
        reports=tuple(LeaderReport(a.time_s,x.w) for x in a.bins)
        a,_=step(a,reports,(0.,0.),.25,20.,6.)
        b,_=step(b,reports,(0.,0.),.25,20.,6.)
    assert len(a.bins)==len(b.bins)==2
    assert sum(x.mass for x in b.bins)==100000
    assert [(x.h,x.v,x.w,x.x) for x in a.bins]==[(x.h,x.v,x.w,x.x) for x in b.bins]


def test_delayed_report_history_and_emergency_recovery():
    from metroflow.gap_transport import lower_speed
    c=VehicleClass(brake_mps2=5.)
    s=PairState(0.,(PairBin(c,100.,65.,20.,15.),))
    history=[LeaderReport(0.,15.)]
    for k in range(120):
        available=[r for r in history if r.stamp_s<=s.time_s-1.]
        r=available[-1] if available else history[0]
        aL=-6. if 3.<=s.time_s<6. else 1. if 8.<=s.time_s<13. else 0.
        s,proof=step(s,(r,),(aL,),.25,20.,6.)
        assert proof[0]['min_gap_m']>=2.-1e-8
        history.append(LeaderReport(s.time_s,s.bins[0].w))
    assert s.bins[0].w==pytest.approx(5.)
    assert s.bins[0].x>0 and sum(b.mass for b in s.bins)==100.


def test_invalid_observation_and_disturbance_are_not_silently_accepted():
    from metroflow.gap_transport import lower_speed
    s=PairState(0.,(PairBin(VehicleClass(),1.,50.,10.,5.),))
    with pytest.raises(ValueError,match='future'):
        control(s.bins[0],LeaderReport(1.,5.),0.,.2,20.,6.)
    with pytest.raises(ValueError,match='contradicts'):
        step(s,(LeaderReport(0.,15.),),(0.,),.2,20.,6.)
    with pytest.raises(ValueError,match='lower acceleration'):
        step(s,(LeaderReport(0.,5.),),(-7.,),.2,20.,6.)
    assert lower_speed(None,0.,6.)==0.


def test_unrestricted_envelope_matches_dense_independent_evaluation():
    import random
    rng=random.Random(513)
    def advance(v,a,t):
        if a<0 and t>=v/(-a):return v*v/(-2*a)
        return v*t+.5*a*t*t
    for _ in range(60):
        v,w=rng.uniform(0.,30.),rng.uniform(0.,30.)
        b,B=rng.uniform(1.,8.),rng.uniform(1.,8.)
        a,dt=rng.uniform(-b,3.),rng.uniform(0.,3.)
        end=max(w/B,dt+max(0.,v+a*dt)/b)
        exact,_=maximum_closure(v,w,a,dt,b,B)
        values=[]
        for k in range(1001):
            t=end*k/1000
            xf=advance(v,a,min(t,dt))
            if t>dt:xf+=advance(max(0.,v+a*dt),-b,t-dt)
            values.append(xf-advance(w,-B,t))
        sampled=max(values)
        assert exact>=sampled-1e-9
        assert exact-sampled<=(v+max(0.,a)*dt+w)*end/1000+1e-9


def test_no_hidden_per_mass_loops_and_class_specific_moments():
    from metroflow.gap_transport import moments
    c=VehicleClass()
    a=PairState(0.,(PairBin(c,1.,30.,10.,10.),PairBin(c,1.,70.,10.,10.)))
    b=PairState(0.,(PairBin(c,2.,50.,10.,10.),))
    assert moments(a)==moments(b)
    # Change headway target to place one bin below and one above the speed cap.
    a=replace(a,bins=tuple(replace(p,h=p.h-20.) for p in a.bins))
    b=replace(b,bins=(replace(b.bins[0],h=30.),))
    a,_=step(a,(LeaderReport(0.,10.),)*2,(0.,0.),.2,20.,6.)
    b,_=step(b,(LeaderReport(0.,10.),),(0.,),.2,20.,6.)
    assert moments(a)['mean_v']!=pytest.approx(moments(b)['mean_v'])
    assert moments(a)['variance_v']>0


def test_first_passage_is_from_same_continuous_applied_trajectory():
    # No new tick-delay is allowed when measuring a segment inside a held step.
    from metroflow.stopping_envelope import passage_in_interval
    assert passage_in_interval(10.,0.,3.,2.)==pytest.approx(.3)
    assert passage_in_interval(0.,2.,1.,2.)==pytest.approx(1.)
    assert passage_in_interval(10.,-5.,10.,3.)==pytest.approx(2.,abs=1e-7)
    assert passage_in_interval(10.,-5.,11.,3.) is None
