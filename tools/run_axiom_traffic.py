"""Small conditional physics and information experiments; stdlib solver only."""
from pathlib import Path
import sys,json,math,time,argparse,hashlib
from dataclasses import asdict
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metroflow.foundation_kinetics import VehicleClass,PhaseBin,evolve,moments,mean_passage
from metroflow.active_suffix import Road,Demand,Signal,Config
from metroflow.active_suffix.packed import PackedModel
from metroflow.active_suffix.causal import Information,CausalPackedModel


def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,sort_keys=True,allow_nan=False)+'\n')


def local(out):
    car=VehicleClass();truck=VehicleClass('freight',15.,4.,.7,2.,3.,1.5,12.)
    distributions={'equal_gaps':(PhaseBin(100.,20.,2.),),
                   'dispersed_gaps':(PhaseBin(50.,5.,2.),PhaseBin(50.,35.,2.))}
    series=[]
    for tick in range(21):
        row=dict(time_s=tick)
        for name,bins in distributions.items():row[name]=moments(evolve(car,bins,tick,20.))
        row['freight']=moments(evolve(truck,distributions['dispersed_gaps'],tick,20.))
        series.append(row)
    result=dict(scope='frozen conditional headway and class; no joint gap dynamics',series=series,
                first_passage_s=mean_passage(car,(PhaseBin(.5,7.,5.),PhaseBin(.5,17.,15.)),20.,100.),
                inverse_mean_s=10.,per_car_records=0)
    write(out/'LOCAL_KINETIC.json',result)
    return result


def pair(out):
    roads=(Road('oa','O','A',100.,10.,1.,30.),Road('ad','A','D',100.,10.,1.,30.),
           Road('ob','O','B',150.,10.,1.,30.),Road('bd','B','D',150.,10.,1.,30.))
    cfg=Config(paths_per_od=2,route_refresh_s=1.,route_response_s=1.,temperature_s=0.,interaction_rate_s=0.)
    demand=(Demand('O','D',100.,120.,0.),) # isolate information, not legitimate physical feedback
    models={}
    for closed in (False,True):
        windows=(('ad',2.,60.,0.),) if closed else ()
        for name,info in (('within',Information(100.,10.,2.)),('outside',Information(20.,10.,2.))):
            models[(name,closed)]=CausalPackedModel(roads,demand,((0.,0.),),
                {r.id:(50.,0.) for r in roads},info,cfg,capacity_windows=windows)
        models[('global',closed)]=PackedModel(roads,demand,cfg,capacity_windows=windows)
    states={k:m.initial() for k,m in models.items()};rows=[];first={}
    for tick in range(30):
        values={}
        for key,m in models.items():
            states[key]=m.step(states[key]);s=states[key].physical if key[0]!='global' else states[key]
            values[str(key)]=s.choice[0][0]
        for name in ('global','within','outside'):
            if values[str((name,False))]!=values[str((name,True))] and name not in first:first[name]=tick
        rows.append(dict(decision_time_s=tick,short_route_share=values))
    assert first=={'global':2,'within':10}
    result=dict(scope='paired worlds with zero demand, a pure nonanticipation intervention',
                incident_time_s=2.,first_completed_report_s=3.,sensor_distance_m=50.,
                propagation_mps=10.,latency_s=2.,first_changed_decision_s=first,series=rows)
    write(out/'PAIRED_INFORMATION.json',result);return result


def city(out,input_path,horizon=120.):
    raw=Path(input_path).read_bytes();data=json.loads(raw)
    roads=tuple(Road(**(r|{'signal':Signal(**r['signal']) if r['signal'] else None})) for r in data['compiled']['roads'])
    demands=tuple(Demand(**d) for d in data['plan']['demands'])
    turns=frozenset(tuple(x) for x in data['compiled']['turns'])
    nodes={n['id']:tuple(n['xyz'][:2]) for n in data['map']['nodes']}
    sensors={r.id:tuple((a+b)/2 for a,b in zip(nodes[r.tail],nodes[r.head])) for r in roads}
    observers=tuple(nodes[d.origin] for d in demands)
    cfg=Config(dt_s=2.,route_refresh_s=30.,paths_per_od=2,adaptive_routes=True,max_routes_per_od=4,
               max_live_suffixes=12000,event_budget=24000)
    reports=[]
    for label,model in (
        ('global_cost',PackedModel(roads,demands,cfg,allowed_turns=turns)),
        ('causal_source',CausalPackedModel(roads,demands,observers,sensors,Information(1200.,60.,2.),cfg,
                         allowed_turns=turns,frame_budget=32))):
        t0=time.perf_counter();state=model.initial();max_mass=0.;max_occ=0.;frames=0;arrivals=0;trace=[]
        for _ in range(round(horizon/cfg.dt_s)):
            state=model.step(state)
            s=state.physical if label=='causal_source' else state
            occupied,_=model.occupancy(state)
            max_mass=max(max_mass,abs(s.released-s.completed-math.fsum(s.pending)-math.fsum(occupied)))
            rr=model.kernel.roads if label=='causal_source' else model.roads
            max_occ=max(max_occ,max(n/r.storage_veh for n,r in zip(occupied,rr)))
            if label=='causal_source':frames=max(frames,len(state.history))
            arrivals=max(arrivals,len(s.transit))
            if s.tick%15==0:trace.append(dict(time_s=s.tick*cfg.dt_s,completed=s.completed,active=math.fsum(occupied),pending=math.fsum(s.pending)))
        row=dict(model=label,horizon_s=horizon,released=s.released,completed=s.completed,
                 active=math.fsum(occupied),pending=math.fsum(s.pending),max_mass_error=max_mass,
                 max_occupancy_ratio=max_occ,peak_cost_frames=frames,peak_cost_scalars=frames*len(roads),
                 peak_arrival_records=arrivals,route_solves=s.route_solves,source_route_repairs=s.routing_repairs,
                 seconds=time.perf_counter()-t0,fingerprint=model.fingerprint(state),trace=trace,
                 mean_journey_s=None,status='HORIZON_REACHED')
        assert max_mass<1e-8 and max_occ<=1.+1e-10
        reports.append(row)
    result=dict(input_sha256=hashlib.sha256(raw).hexdigest(),directed_roads=len(roads),
                demand_schedules=len(demands),resident_stock=100000,
                scope='short matched observation; legacy physical activity retained; not a speed/accuracy benchmark',cases=reports)
    write(out/'CITY_INFORMATION.json',result);return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('artifacts/axiom_gap_20261024/traffic'))
    p.add_argument('--city-input',type=Path);p.add_argument('--horizon',type=float,default=120.)
    a=p.parse_args();local(a.out);pair(a.out)
    if a.city_input:city(a.out,a.city_input,a.horizon)
    print(json.dumps({'output':str(a.out),'local_and_information':'executed','city':bool(a.city_input)}))

if __name__=='__main__':main()
