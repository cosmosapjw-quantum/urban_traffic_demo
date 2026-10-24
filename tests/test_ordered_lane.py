import math
from dataclasses import replace
import pytest
from metroflow.ordered_lane import Lane,ClockState,advance,quote_admission,clock_time
from metroflow.active_suffix.common import BudgetExceeded


def test_same_clock_prevents_the_frozen_entry_delay_reversal():
    lane=Lane(interaction_rate=0.)
    state=ClockState(activity=.1);events=[]
    for k in range(60):
        offers=(('early',.1),) if k==0 else (('late',.1),) if k==10 else ()
        state,flow=advance(lane,state,1.,offers);events.extend(flow)
    early=[f for f in events if f.tag=='early'];late=[f for f in events if f.tag=='late']
    assert early and late and early[-1].end_s<=late[0].start_s
    assert state.completed==pytest.approx(.2)
    expected=clock_time(100.,.1,10.,.2,0.)
    assert early[0].start_s==pytest.approx(expected,abs=1e-9)


def test_positive_travel_clock_and_queue_cost_use_the_same_trajectory():
    lane=Lane(length_m=103.,speed_mps=10.,entry_rate=2.,exit_rate=1.,interaction_rate=0.)
    s=ClockState();quote=quote_admission(lane,s,'d',2.)
    assert quote==pytest.approx((10.3,12.3,11.3))
    flows=[]
    for k in range(20):
        s,events=advance(lane,s,1.,(('d',2.),) if k==0 else ());flows.extend(events)
    assert sum(f.mass*(f.start_s+f.end_s)/2 for f in flows)/2==pytest.approx(quote[2])
    assert s.network_vehicle_seconds==pytest.approx(22.6)
    assert s.vehicle_metres==pytest.approx(206.)
    assert s.system_vehicle_seconds==pytest.approx(s.network_vehicle_seconds)


def test_shared_lane_blocked_head_does_not_pass_but_independent_lane_can():
    lane=Lane(length_m=1.,speed_mps=1.,entry_rate=10.,exit_rate=10.,interaction_rate=0.)
    s=ClockState()
    s,_=advance(lane,s,1.,(('blocked',1.),('open',1.)),{'blocked':0.,'open':10.})
    s,events=advance(lane,s,2.,(),{'blocked':0.,'open':10.})
    assert s.completed==0 and not events
    s,events=advance(lane,s,1.,(),{'blocked':10.,'open':10.})
    assert [f.tag for f in events]==['blocked','open']
    independent=ClockState()
    independent,_=advance(lane,independent,1.,(('open',1.),),{'open':10.})
    independent,_=advance(lane,independent,1.,(),{'open':10.})
    assert independent.completed==1.


def test_storage_source_waiting_and_mass_ledgers_are_separate():
    lane=Lane(length_m=10.,speed_mps=10.,storage=2.,entry_rate=10.,exit_rate=1.,interaction_rate=0.)
    s=ClockState()
    for k in range(15):
        s,_=advance(lane,s,1.,(('d',5.),) if k==0 else (),{'d':0. if k<3 else 1.})
        assert s.occupancy<=2.+1e-12
        assert s.released==pytest.approx(s.completed+s.occupancy+s.pending_mass)
    assert s.completed==pytest.approx(5.)
    assert s.system_vehicle_seconds>s.network_vehicle_seconds


def test_fixed_rate_clock_refinement_has_no_extra_administrative_ticks():
    values=[]
    lane=Lane(length_m=103.,speed_mps=10.,base_stop_rate=.1,interaction_rate=0.)
    for dt in (2.,1.,.5,.25):
        s=ClockState(activity=.4);first=None
        for k in range(round(50/dt)):
            s,events=advance(lane,s,dt,(('d',.1),) if k==0 else ())
            if events and first is None:first=events[0].start_s
        values.append(first)
    assert values==pytest.approx([clock_time(103.,.4,10.,.2,.1)]*4,abs=1e-8)


def test_aggregate_mass_does_not_create_individual_records():
    lane=Lane(length_m=100.,entry_rate=1e6,exit_rate=1e6,storage=1e6,interaction_rate=0.)
    for mass in (1.,1000.,100000.):
        s,events=advance(lane,ClockState(),1.,(('one_group',mass),))
        assert len(s.inside)==1 and s.inside[0].mass==mass
        assert s.occupancy==mass
    # This amplitude check scales storage explicitly; not 100k cars in a fixed real lane.


def test_atomic_budget_failure_and_bad_inputs():
    lane=Lane(length_m=1000.,entry_rate=10.)
    s=ClockState()
    with pytest.raises(BudgetExceeded) as exc:
        advance(lane,s,1.,(('a',1.),('b',1.)),record_budget=1)
    assert exc.value.checkpoint==s
    for bad in (-1.,math.nan):
        with pytest.raises(ValueError):advance(lane,s,1.,(('a',bad),))
    with pytest.raises(ValueError):advance(lane,s,0.)
    with pytest.raises(ValueError):advance(lane,s,1.,(('a',1.),),{'b':1.})


def test_rest_start_clock_resolves_tiny_positive_motion_without_cancellation():
    from metroflow.ordered_lane import distance_clock
    dt=1e-16
    distance,p=distance_clock(dt,0.,10.,.2,0.)
    assert distance==pytest.approx(1e-32,rel=1e-14,abs=0.)
    assert distance>0 and p>0


def test_nonfinite_cumulative_ledger_is_rejected_before_step():
    from dataclasses import replace
    for field in ('released','admitted','completed','birth_moment','entry_moment','exit_moment','vehicle_metres'):
        with pytest.raises(ValueError):
            advance(Lane(),replace(ClockState(),**{field:float('nan')}),1.)
