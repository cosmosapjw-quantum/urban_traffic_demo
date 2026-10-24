import math
import pytest
from metroflow.active_suffix import Road,Demand,Config,BudgetExceeded
from metroflow.active_suffix.causal import Information,CostFrame,CausalPackedModel,perceived


def test_only_delivered_dynamic_information_changes_perceived_cost():
    info=Information(100.,10.,2.)
    history=(CostFrame(5.,(99.,88.)),)
    assert perceived((1.,2.),(50.,200.),info,history,11.)==(1.,2.)
    assert perceived((1.,2.),(50.,200.),info,history,12.)==(99.,2.)


def fixture(info,closure,frame_budget=256,rate=0.,start=100.):
    roads=(Road('oa','O','A',100.,10.,1.,30.),Road('ad','A','D',100.,10.,1.,30.),
           Road('ob','O','B',150.,10.,1.,30.),Road('bd','B','D',150.,10.,1.,30.))
    sensors={key:(50.,0.) for key in ('oa','ad','ob','bd')}
    cfg=Config(dt_s=1.,paths_per_od=2,route_refresh_s=1.,route_response_s=1.,temperature_s=0.,
               interaction_rate_s=0.)
    return CausalPackedModel(roads,(Demand('O','D',start,start+20.,rate),),
            ((0.,0.),),sensors,info,cfg,
            capacity_windows=(('ad',2.,60.,0.),) if closure else (),frame_budget=frame_budget)


def test_paired_worlds_have_identical_choices_until_report_arrives():
    a=fixture(Information(100.,10.,2.),False);b=fixture(Information(100.,10.,2.),True)
    x,y=a.initial(),b.initial()
    for _ in range(10):
        x,y=a.step(x),b.step(y)
        assert x.physical.choice==y.physical.choice
    x,y=a.step(x),b.step(y)  # completed frame t=3 arrives at t=10
    assert x.physical.choice!=y.physical.choice


def test_outside_information_radius_does_not_expose_remote_closure():
    a=fixture(Information(20.,10.,2.),False);b=fixture(Information(20.,10.,2.),True)
    x,y=a.initial(),b.initial()
    for _ in range(20):
        x,y=a.step(x),b.step(y)
        assert x.physical.choice==y.physical.choice


def test_observation_budget_failure_preserves_last_valid_state():
    m=fixture(Information(100.,1.,2.),False,frame_budget=1)
    first=m.initial();second=m.step(first)
    assert first.physical.tick==0
    with pytest.raises(BudgetExceeded) as exc:m.step(second)
    assert exc.value.checkpoint==second


def test_hidden_event_does_not_leak_via_refresh_schedule():
    from dataclasses import replace
    a=fixture(Information(20.,10.,2.),False);b=fixture(Information(20.,10.,2.),True)
    a.kernel.cfg=replace(a.kernel.cfg,route_refresh_s=4.)
    b.kernel.cfg=replace(b.kernel.cfg,route_refresh_s=4.)
    x,y=a.initial(),b.initial()
    for _ in range(20):
        x,y=a.step(x),b.step(y)
        assert x.physical.last_choice_s==y.physical.last_choice_s
        assert x.physical.choice==y.physical.choice


def test_belief_never_overrides_actual_closure_or_mass_conservation():
    m=fixture(Information(20.,10.,2.),True,rate=.2,start=0.)
    state=m.initial()
    for _ in range(200):
        old=state;state=m.step(state)
        if 2<=old.physical.tick<60:
            j=m.kernel.index['ad']
            assert state.physical.link_outflow[j]==old.physical.link_outflow[j]
        occ,_=m.occupancy(state)
        assert state.physical.released==pytest.approx(state.physical.completed+sum(state.physical.pending)+sum(occ),abs=1e-10)
        assert all(x<=r.storage_veh+1e-10 for x,r in zip(occ,m.kernel.roads))
    assert state.physical.completed==pytest.approx(4.,abs=1e-9)
    assert len(state.history)<=2


def test_replay_and_pruning_preserve_the_observed_costs():
    m=fixture(Information(100.,10.,2.),True)
    x,y=m.initial(),m.initial();full=[]
    for _ in range(40):
        x,y=m.step(x),m.step(y)
        full.append(x.history[-1])
        assert x==y and m.fingerprint(x)==m.fingerprint(y)
        now=x.physical.tick
        assert perceived(m.prior,m.distances[0],m.information[0],x.history,now)==perceived(m.prior,m.distances[0],m.information[0],tuple(full),now)
    assert len(x.history)<=9


def test_information_classes_and_validation():
    h=(CostFrame(5.,(99.,)),)
    assert perceived((1.,),(50.,),Information(100.,10.,0.),h,10.)==(99.,)
    assert perceived((1.,),(50.,),Information(100.,10.,1.),h,10.)==(1.,)
    with pytest.raises(ValueError):Information(propagation_mps=0.)
    with pytest.raises(ValueError):perceived((1.,),(50.,),Information(),h+h,10.)
