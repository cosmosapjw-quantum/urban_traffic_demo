import math
from dataclasses import replace
import pytest
from metroflow.active_suffix import Road,Demand,Config,Signal,BudgetExceeded
from metroflow.active_suffix.interval import IntervalModel


def now(model,state):
    return state.time_s if hasattr(state,'time_s') else state.tick*model.cfg.dt_s


def evolve(model,horizon=200.):
    s=model.initial();peak=0;steps=0
    while now(model,s)<horizon-1e-9:
        s=model.step(s);steps+=1;peak=max(peak,len(s.transit))
        occ,_=model.occupancy(s)
        assert s.released==pytest.approx(s.completed+sum(s.pending)+sum(occ),abs=1e-8)
        assert all(-1e-10<=v<=r.storage_veh+1e-8 for v,r in zip(occ,model.roads))
        assert steps<20000,'event clock stopped progressing'
    return s,peak

@pytest.mark.parametrize('dt',(4.,2.,1.,.5))
def test_ten_second_free_flow_is_not_twelve_seconds(dt):
    m=IntervalModel((Road('r','O','D',100.,10.,1.,100.),),
        (Demand('O','D',0.,4.,.01),),Config(dt_s=dt,paths_per_od=1,interaction_rate_s=0.))
    s,_=evolve(m)
    assert s.completed==pytest.approx(.04)
    assert s.vehicle_seconds/s.completed==pytest.approx(10.,abs=1e-9)


def test_multilink_fractional_clock_and_partial_source_interval():
    roads=(Road('a','O','M',70.,10.,1.,100.),Road('b','M','D',130.,10.,1.,100.))
    m=IntervalModel(roads,(Demand('O','D',.7,3.3,.01),),
        Config(dt_s=3.,paths_per_od=1,interaction_rate_s=0.))
    s,_=evolve(m)
    assert s.released==pytest.approx(.026)
    assert s.completed==pytest.approx(.026)
    assert s.vehicle_seconds/s.completed==pytest.approx(20.,abs=1e-9)


def test_constant_stream_calendar_does_not_scale_with_dt():
    peaks=[]
    for dt in (2.,1.,.5):
        m=IntervalModel((Road('r','O','D',100.,10.,1.,100.),),
            (Demand('O','D',0.,80.,.125),),Config(dt_s=dt,paths_per_od=1,interaction_rate_s=0.))
        s,peak=evolve(m,120.);peaks.append(peak)
        assert s.completed==pytest.approx(10.)
    assert max(peaks)<=2,peaks


def test_red_and_closure_boundaries_conserve_mass_without_illegal_service():
    r=Road('r','O','D',10.,10.,1.,5.,signal=Signal(10.,5.))
    m=IntervalModel((r,),(Demand('O','D',0.,20.,2.),),
        Config(dt_s=2.,paths_per_od=1,interaction_rate_s=.2),capacity_windows=(('r',3.2,9.7,0.),))
    s=m.initial()
    while now(m,s)<40.-1e-9:
        before=s;s=m.step(s);t=now(m,before);end=now(m,s)
        if (5<=t and end<=10) or (3.2<=t and end<=9.7):
            assert s.completed==before.completed
        occ,_=m.occupancy(s)
        assert s.released==pytest.approx(s.completed+sum(s.pending)+sum(occ),abs=1e-8)
        assert occ[0]<=5.+1e-9
    assert sum(s.pending)>0  # cannot conjure physical capacity


def test_complete_delay_not_rounded_and_same_tick_teleport_forbidden():
    m=IntervalModel((Road('r','O','D',100.,10.,1.,100.),),
        (Demand('O','D',0.,1.,.1),),Config(dt_s=4.,paths_per_od=1,interaction_rate_s=0.))
    s=m.initial()
    while now(m,s)<10.-1e-9:
        s=m.step(s)
        if now(m,s)<=10.+1e-9:assert s.completed==0.
    s,_=evolve(m,100.)
    assert s.vehicle_seconds==pytest.approx(1.)

def test_small_signal_queue_drains_at_capacity_not_over_an_arbitrary_step():
    # Arrival [1,6) at .1/s; [5,6) accumulates .1 veh in red. At t=10,
    # service 1/s clears at10.1. Extra waiting area .1*(10.05-5.5)=.455 veh*s.
    m=IntervalModel((Road('r','O','D',10.,10.,1.,100.,signal=Signal(10.,5.)),),
        (Demand('O','D',0.,5.,.1),),Config(dt_s=4.,paths_per_od=1,interaction_rate_s=0.))
    s,_=evolve(m,100.)
    assert s.completed==pytest.approx(.5)
    assert s.vehicle_seconds/s.completed==pytest.approx(1.91,abs=1e-9)


def test_source_backlog_clears_at_its_physical_service_time():
    # In .5/s over2.7s, admit .3/s over4.5s, delay1.3s.
    # Mean journey=1.3+4.5/2-2.7/2=2.2s.
    m=IntervalModel((Road('r','O','D',13.,10.,.3,100.),),
        (Demand('O','D',0.,2.7,.5),),Config(dt_s=2.,paths_per_od=1,interaction_rate_s=0.))
    s,_=evolve(m,100.)
    assert s.completed==pytest.approx(1.35)
    assert s.vehicle_seconds/s.completed==pytest.approx(2.2,abs=1e-9)

def test_activity_updates_do_not_fragment_constant_source_at_every_arrival_event():
    # Transport-event resolution is distinct from the fixed bulk-activity cadence.
    m=IntervalModel((Road('r','O','D',1000.,10.,1.,500.),),
        (Demand('O','D',0.,120.,.125),),Config(dt_s=5.,paths_per_od=1,interaction_rate_s=.2,event_budget=1000))
    s,peak=evolve(m,140.)
    assert peak<=30,peak
    assert s.activity[0]<1. and s.completed>0

def test_urban_first_minute_fits_the_unchanged_24000_interval_budget():
    from metroflow.restored_city import generate
    from metroflow.restored_zoning import attach_zones
    from metroflow.restored_traffic import compile_traffic
    from metroflow.environment.demand import plan_commute
    city=generate('grid_core');stock,_=attach_zones(city);network=compile_traffic(city)
    plan=plan_commute(stock,network.roads,divisions=3,profile=((0.,3600.,1.),),allowed_turns=network.allowed_turns)
    cfg=Config(dt_s=5.,paths_per_od=2,adaptive_routes=True,max_routes_per_od=4,
               route_refresh_s=30.,max_live_suffixes=12000,event_budget=24000)
    m=IntervalModel(network.roads,plan.demands,cfg,allowed_turns=network.allowed_turns,conflicts=network.conflicts)
    s,peak=evolve(m,60.)
    assert s.released>90. and peak<24000

def test_calendar_compression_preserves_mass_and_reports_its_small_approximation():
    from metroflow.active_suffix.interval import RateInterval,canonical_intervals
    events=(RateInterval(0.,2.,.125,0),RateInterval(2.,4.,.125+1e-15,0),
            RateInterval(1.,3.,.25,1),RateInterval(2.,4.,.25,1))
    out,error,moment=canonical_intervals(events,with_error=True)
    assert sum(x.mass for x in out)==pytest.approx(sum(x.mass for x in events),abs=1e-14)
    assert len([x for x in out if x.suffix==0])==1
    def cum(es,sid,t):return sum(x.rate_veh_s*max(0.,min(t,x.end_s)-x.start_s) for x in es if x.suffix==sid)
    for sid in (0,1):
        for k in range(41):assert abs(cum(events,sid,k/10)-cum(out,sid,k/10))<=error+1e-14
    assert 0<error<1e-12 and 0<=moment<1e-12


def test_closed_bridge_remains_committed_and_new_departures_can_detour():
    roads=(Road('oa','O','A',100.,10.,.8,30.),Road('ad','A','D',100.,10.,.8,30.),
           Road('ob','O','B',200.,10.,.8,30.),Road('bd','B','D',200.,10.,.8,30.))
    cfg=Config(dt_s=2.,paths_per_od=1,max_routes_per_od=1,adaptive_routes=True,
               route_regret_budget_s=0.,interaction_rate_s=0.,route_refresh_s=5.)
    m=IntervalModel(roads,(Demand('O','D',0.,60.,.1),),cfg,capacity_windows=(('ad',15.,65.,0.),))
    s=m.initial()
    while s.time_s<180.-1e-9:
        old=s;s=m.step(s)
        if 15.<=old.time_s and s.time_s<=65.:assert s.link_outflow[m.index['ad']]==old.link_outflow[m.index['ad']]
    assert s.completed==pytest.approx(6.,abs=1e-9)
    assert s.link_outflow[m.index['ad']]>0 and s.link_outflow[m.index['bd']]>0
    assert s.routing_repairs>=1 and s.cache_evictions>=1


def test_lane_and_mass_scaling_keep_activity_and_service_clock():
    r=Road('r','O','D',100.,10.,.1,10.,signal=Signal(10.,6.))
    cfg=Config(dt_s=2.,paths_per_od=1)
    a=IntervalModel((r,),(Demand('O','D',0.,20.,.1),),cfg)
    b=IntervalModel((replace(r,capacity_veh_s=.2,storage_veh=20.),),(Demand('O','D',0.,20.,.2),),cfg)
    x,y=a.initial(),b.initial()
    for _ in range(60):
        x,y=a.step(x),b.step(y)
        assert x.time_s==pytest.approx(y.time_s,abs=1e-9)
        assert y.completed==pytest.approx(2*x.completed,abs=1e-10)
        assert x.activity==pytest.approx(y.activity,abs=1e-12)
        assert y.vehicle_seconds==pytest.approx(2*x.vehicle_seconds,abs=1e-9)


def test_calendar_budget_returns_unmodified_last_valid_state():
    m=IntervalModel((Road('r','O','D',100.,10.,1.,100.),),
        (Demand('O','D',0.,20.,.1),Demand('O','D',3.,8.,.03)),
        Config(dt_s=1.,paths_per_od=1,event_budget=1,interaction_rate_s=0.))
    s=m.initial()
    with pytest.raises(BudgetExceeded) as caught:
        for _ in range(20):s=m.step(s)
    assert caught.value.checkpoint is s
    assert s.released==pytest.approx(s.completed+sum(s.pending)+sum(m.occupancy(s)[0]))


def test_deterministic_replay_and_resuming_at_fractional_time():
    r=Road('r','O','D',37.,10.,1.,50.)
    cfg=Config(dt_s=4.,paths_per_od=1,interaction_rate_s=0.)
    m=IntervalModel((r,),(Demand('O','D',.3,5.7,.2),),cfg)
    a,_=evolve(m,80.);b,_=evolve(m,80.)
    assert a==b and m.fingerprint(a)==m.fingerprint(b)
    assert a.vehicle_seconds/a.completed==pytest.approx(3.7,abs=1e-9)
