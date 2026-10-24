"""Small ordered-lane and realizable periodic-ring controls; stdlib only."""
from pathlib import Path
import argparse,cmath,json,math,sys
from dataclasses import asdict,replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metroflow.ordered_lane import Lane,ClockState,advance,quote_admission,clock_time
from metroflow.periodic_gap import RingCell,make_ring,advance_ring,observe_ring
from metroflow.foundation_kinetics import VehicleClass
from metroflow.audit_observables import edie_observables
from metroflow.active_suffix.common import BudgetExceeded
from metroflow.active_suffix.routing import braess_reference
from run_literature_audit import overtaking


def lane_run(lane,dt,horizon,offers=(),initial=None,supply=None):
    state=initial or ClockState();trace=[];events=[];peak=0;max_error=0.
    schedule=dict(offers)
    for step in range(round(horizon/dt)):
        incoming=schedule.get(round(state.time_s,8),())
        receiving=supply(state.time_s) if supply else None
        state,out=advance(lane,state,dt,incoming,receiving)
        events.extend(asdict(x) for x in out)
        peak=max(peak,len(state.waiting)+len(state.inside))
        error=state.released-state.completed-state.occupancy-state.pending_mass
        max_error=max(max_error,abs(error))
        assert abs(error)<1e-8 and state.occupancy<=lane.storage+1e-9
        trace.append(dict(time_s=state.time_s,completed=state.completed,inside=state.occupancy,
                          pending=state.pending_mass,progress_m=state.progress_m,activity=state.activity))
    return dict(state=asdict(state),trace=trace,departures=events,peak_records=peak,
                mass_error=max_error,network_vehicle_seconds=state.network_vehicle_seconds,
                system_vehicle_seconds=state.system_vehicle_seconds,
                mean_system_time_s=(state.exit_moment-state.birth_moment)/state.completed
                    if state.completed and state.pending_mass+state.occupancy<1e-10 else None)


def modes(dt,K=32):
    z=cmath.exp(2j*math.pi/K)-1;rate=-math.expm1(-dt/2)/dt
    a=1+.5*rate*dt*dt*z;b=z*(dt-.5*rate*dt*dt);c=rate*dt;d=1-rate*dt
    tr=a+d;det=a*d-b*c
    eigen=max(((tr+cmath.sqrt(tr*tr-4*det))/2,(tr-cmath.sqrt(tr*tr-4*det))/2),key=abs)
    ratio=(eigen-a)/b
    return eigen,tuple(RingCell(VehicleClass(),14+1e-4*cmath.exp(2j*math.pi*i/K).real,
                  12+1e-4*(ratio*cmath.exp(2j*math.pi*i/K)).real) for i in range(K))


def main(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    fifo=lane_run(Lane(interaction_rate=0.),1.,60.,
          ((0.,(('early',.1),)),(10.,(('late',.1),))),ClockState(activity=.1))
    assert fifo['departures'][0]['tag']=='early' and fifo['departures'][-1]['tag']=='late'
    free_lane=Lane(length_m=103.,entry_rate=4.,exit_rate=1.,interaction_rate=0.)
    quote=quote_admission(free_lane,ClockState(),'batch',2.)
    free=lane_run(free_lane,1.,40.,((0.,(('batch',2.),)),))
    assert abs(free['mean_system_time_s']-quote[2])<1e-10
    observation=edie_observables(free['network_vehicle_seconds'],free['state']['vehicle_metres'],103.,40.)
    blocked=lane_run(Lane(length_m=10.,interaction_rate=0.),1.,20.,
             ((0.,(('blocked',.2),('open',.2))),),supply=lambda t:{'blocked':0. if t<10 else 1.,'open':1.})
    assert not any(d['start_s']<10 for d in blocked['departures'])
    assert blocked['state']['completed']==.4
    density=[]
    for dt in (1.,.5,.25,.125):
        r=lane_run(Lane(length_m=103.,entry_rate=10.,exit_rate=.5,storage=4.,interaction_rate=1.),
                   dt,100.,((0.,(('a',1.),)),(4.,(('b',1.),))))
        density.append(dict(dt_s=dt,mean_s=r['mean_system_time_s'],mass_error=r['mass_error']))
    scaling=[]
    for mass in (1.,1000.,100000.):
        # Explicitly rescale capacity/storage, not 100k vehicles on a 30-vehicle link.
        r=lane_run(Lane(length_m=100.,entry_rate=2*mass,exit_rate=mass,storage=2*mass,interaction_rate=0.),
                   1.,20.,((0.,(('same_class',mass),)),))
        scaling.append(dict(mass=mass,peak_records=r['peak_records'],completed=r['state']['completed'],
                            storage=2*mass,mean_s=r['mean_system_time_s']))
    c=VehicleClass();motif=tuple(RingCell(c,h,v) for h,v in ((45.,12.),(55.,8.),(40.,10.),(60.,6.)))
    small=make_ring(motif,7);full=make_ring(motif*7);hist=[];error=0.;min_gap=math.inf
    for _ in range(240):
        small,proof=advance_ring(small,.25,25.);full,_=advance_ring(full,.25,25.)
        for i,cell in enumerate(full.cells):
            ref=small.cells[i%4]
            error=max(error,abs(cell.gap_m-ref.gap_m),abs(cell.speed_mps-ref.speed_mps),abs(cell.travelled_m-ref.travelled_m))
        min_gap=min(min_gap,min(p['min_gap_m'] for p in proof));obs=observe_ring(small)
        assert obs['pair_marginal_l1']==0. and abs(obs['length_residual_m'])<1e-8
        hist.append(dict(time_s=small.time_s,**obs))
    scale=observe_ring(make_ring(motif,25000))
    growth=[]
    for dt in (.5,.25,.1):
        eigen,cells=modes(dt);state=make_ring(cells)
        measure=lambda st:sum((c.gap_m-14)*cmath.exp(-2j*math.pi*i/32) for i,c in enumerate(st.cells))*2/32
        initial=measure(state);err=0.;trace=[];changed=0
        for i in range(round(10/dt)):
            old=state;state,proof=advance_ring(state,dt,30.)
            rate=-math.expm1(-dt/2)/dt
            changed+=sum(abs(p['acceleration_mps2']-rate*(c.gap_m-2-c.speed_mps))>1e-10 for c,p in zip(old.cells,proof))
            err=max(err,abs(measure(state)-initial*eigen**(i+1)))
            trace.append(dict(time_s=state.time_s,mode_amplitude=abs(measure(state))))
        growth.append(dict(dt_s=dt,predicted_per_s=math.log(abs(eigen))/dt,
            observed_per_s=math.log(abs(measure(state)/initial))/state.time_s,
            max_complex_mode_error_m=err,filter_interventions=changed,trace=trace))
        assert err<2e-12 and changed==0
    integration=None
    mapfile=out/'map_organic.json'
    if mapfile.exists():
        data=json.loads(mapfile.read_text());last=data['history'][-1]['city']
        road=next(s for s in last['sections'] if s['id'].startswith('access:'))
        U=8.33/(1+3*road['max_grade'])
        lane=Lane(length_m=road['length_m'],speed_mps=U,entry_rate=1.,exit_rate=1.,storage=.12*road['length_m'],interaction_rate=0.)
        r=lane_run(lane,1.,120.,((0.,(('new_site',1.),)),))
        integration=dict(section=road['id'],length_m=road['length_m'],speed_mps=U,
                         expected_mean_s=road['length_m']/U+.5,observed_mean_s=r['mean_system_time_s'],
                         completed=r['state']['completed'],source='actual constructed access; one homogeneous direction, no city OD rerun')
        assert abs(integration['expected_mean_s']-integration['observed_mean_s'])<1e-10
    result=dict(scope='separate homogeneous FIFO-lane and periodic-ring references, not replacement of city physics',
        old_packed_counterexample=overtaking(),ordered=fifo,free=dict(quote_s=quote,result=free,observation=observation),
        blocked_head=blocked,density_refinement=density,amplitude_scaling=scaling,
        ring=dict(reduced_representatives=4,explicit_representatives=28,steps=240,max_state_difference=error,
                  min_gap_m=min_gap,final=observe_ring(small),trace=hist,large_symmetric_ensemble=scale),
        growing_modes=growth,map_traffic_segment=integration,
        static_braess_minutes=[braess_reference()['mean_cost_min'],braess_reference(shortcut=True)['mean_cost_min']])
    (out/'TRAFFIC_RESULTS.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps(dict(ordered_departures=fifo['departures'],free_quote=quote,density_refinement=density,
         ring_max_difference=error,ring_final=observe_ring(small),large_symmetric=scale,
         growing_modes=[{k:v for k,v in x.items() if k!='trace'} for x in growth],integration=integration),indent=2))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=Path('artifacts/access_fifo_20261025'))
    main(parser.parse_args().out)
