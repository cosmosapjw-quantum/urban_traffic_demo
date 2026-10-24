"""Bounded interval-flow benchmarks. Every stopped probe keeps its last state."""
from pathlib import Path
import sys,json,time,argparse,math
from dataclasses import asdict
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metroflow.active_suffix import Road,Signal,Demand,Config,Model,BudgetExceeded
from metroflow.active_suffix.interval import IntervalModel


def run(model,horizon,max_steps=20000,wall_limit_s=15.):
    s=model.initial();start=time.perf_counter();peaks=0;steps=0;err=0.;storage=0.;trace=[];reason=None
    while (s.time_s if hasattr(s,'time_s') else s.tick*model.cfg.dt_s)<horizon-1e-9:
        if steps>=max_steps or time.perf_counter()-start>wall_limit_s:
            reason='probe_step_or_wall_budget';break
        try:
            s=model.step(s,stop_s=horizon) if isinstance(model,IntervalModel) else model.step(s)
        except BudgetExceeded as exc:
            reason=str(exc);s=exc.checkpoint;break
        steps+=1;peaks=max(peaks,len(s.transit));occ,_=model.occupancy(s)
        err=max(err,abs(s.released-s.completed-sum(s.pending)-sum(occ)))
        storage=max(storage,max(x/r.storage_veh for x,r in zip(occ,model.roads)))
        if steps%25==0:trace.append([getattr(s,'time_s',s.tick*model.cfg.dt_s),s.completed,len(s.transit)])
    occ,_=model.occupancy(s);t=getattr(s,'time_s',s.tick*model.cfg.dt_s)
    cleared=t>=max(d.end_s for d in model.demands) and sum(occ)+sum(s.pending)<1e-8*max(1.,s.released)
    report=dict(status='BLOCKED_RESOURCE' if reason else 'CLEARED_SCOPED' if cleared else 'HORIZON_REACHED',
        blocker=reason,time_s=t,steps=steps,released=s.released,completed=s.completed,active=sum(occ),
        pending=sum(s.pending),mean_s=s.vehicle_seconds/s.completed if cleared and s.completed else None,
        residence_vehicle_seconds=s.vehicle_seconds,peak_records=peaks,max_mass_error=err,
        max_storage_ratio=storage,wall_s=time.perf_counter()-start,
        calendar_cdf_error_veh=getattr(s,'calendar_cdf_error_veh',0.),
        calendar_moment_error_veh_s=getattr(s,'calendar_moment_error_veh_s',0.),
        merges=getattr(s,'interval_merges',0),peak_suffix_final=len(s.suffixes),per_car_records=0,
        fingerprint=model.fingerprint(s),trace=trace)
    return report,s


def main():
    p=argparse.ArgumentParser();p.add_argument('--part',choices=('oracles','city'),required=True)
    p.add_argument('--input',type=Path);p.add_argument('--legacy',action='store_true');
    p.add_argument('--max-steps',type=int,default=20000);p.add_argument('--wall-limit',type=float,default=12.);
    p.add_argument('--horizon',type=float,default=150.)
    p.add_argument('--out',type=Path,default=Path('artifacts/frontage_interval_20261024/traffic'))
    args=p.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
    if args.part=='oracles':
        rows=[]
        for dt in (4.,2.,1.,.5):
            for cls in (Model,IntervalModel):
                model=cls((Road('r','O','D',100.,10.,1.,100.),),(Demand('O','D',0.,80.,.125),),
                          Config(dt_s=dt,paths_per_od=1,interaction_rate_s=0.))
                r,_=run(model,120.);r.update(model=cls.__name__,dt_s=dt);rows.append(r)
                if cls is IntervalModel:
                    assert abs(r['mean_s']-10.)<1e-9 and r['peak_records']<=2
        (out/'oracles.json').write_text(json.dumps(rows,indent=2,allow_nan=False))
        print(json.dumps([{k:r[k] for k in ('model','dt_s','mean_s','peak_records','steps')} for r in rows],indent=2))
    else:
        if args.input is None:raise ValueError('--input must be a saved restored-road input')
        d=json.loads(args.input.read_text())
        roads=tuple(Road(**(r|{'signal':Signal(**r['signal']) if r['signal'] else None})) for r in d['compiled']['roads'])
        demands=tuple(Demand(**x) for x in d['plan']['demands']);cfg=Config(**d['config'])
        turns=frozenset(tuple(x) for x in d['compiled']['turns'])
        model=(Model if args.legacy else IntervalModel)(roads,demands,cfg,allowed_turns=turns)
        report,state=run(model,args.horizon,max_steps=args.max_steps,wall_limit_s=args.wall_limit)
        (out/'city_probe.json').write_text(json.dumps(report,indent=2,allow_nan=False))
        (out/'city_checkpoint.json').write_text(json.dumps(asdict(state),allow_nan=False))
        print(json.dumps({k:v for k,v in report.items() if k!='trace'},indent=2))

if __name__=='__main__':main()
