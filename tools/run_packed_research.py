"""Compare opt-in packed tick transport with legacy and interval references."""
from pathlib import Path
import sys,json,math,time,argparse
from dataclasses import asdict,replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metroflow.active_suffix import Road,Signal,Demand,Config,Model,BudgetExceeded
from metroflow.active_suffix.packed import PackedModel
from metroflow.active_suffix.interval import IntervalModel
from run_interval_research import run


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path)
    p.add_argument('--out',type=Path,default=Path('artifacts/frontage_interval_20261024/packed'))
    p.add_argument('--horizon',type=float,default=300.);p.add_argument('--dt',type=float,default=2.)
    args=p.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for dt in (4.,2.,1.,.5):
        for cls in (Model,PackedModel,IntervalModel):
            m=cls((Road('r','O','D',100.,10.,1.,100.),),(Demand('O','D',0.,80.,.125),),
                  Config(dt_s=dt,paths_per_od=1,interaction_rate_s=0.))
            r,s=run(m,120.);r.update(model=cls.__name__,dt_s=dt);rows.append(r)
            if cls is PackedModel:assert abs(r['mean_s']-math.ceil(10/dt)*dt)<1e-9 and r['peak_records']==1
    (out/'oracles.json').write_text(json.dumps(rows,indent=2,allow_nan=False))
    if args.input:
        data=json.loads(args.input.read_text())
        roads=tuple(Road(**(r|{'signal':Signal(**r['signal']) if r['signal'] else None})) for r in data['compiled']['roads'])
        demands=tuple(Demand(**d) for d in data['plan']['demands'])
        turns=frozenset(tuple(t) for t in data['compiled']['turns'])
        cfg=replace(Config(**data['config']),dt_s=args.dt)
        for cls in (Model,PackedModel):
            for closure in (False,True):
                windows=tuple((r.id,60.,180.,0.) for r in roads if r.id.startswith('bridge:6|')) if closure else ()
                m=cls(roads,demands,cfg,allowed_turns=turns,capacity_windows=windows)
                report,state=run(m,args.horizon,wall_limit_s=20.)
                report.update(model=cls.__name__,dt_s=args.dt,closure=closure)
                key=cls.__name__+('_closure' if closure else '_baseline')
                (out/f'{key}.json').write_text(json.dumps(report,indent=2,allow_nan=False))
                (out/f'{key}_checkpoint.json').write_text(json.dumps(asdict(state),allow_nan=False))
                assert report['status']=='HORIZON_REACHED',report
                assert report['max_mass_error']<1e-8 and report['max_storage_ratio']<=1+1e-10
                print(json.dumps({k:v for k,v in report.items() if k!='trace'},indent=2))
        (out/'matched_input.json').write_text(json.dumps(dict(config=asdict(cfg),roads=[asdict(r) for r in roads],
             demands=[asdict(d) for d in demands],turns=sorted(turns)),allow_nan=False))
    else:print(json.dumps([{k:r[k] for k in ('model','dt_s','mean_s','peak_records')} for r in rows],indent=2))

if __name__=='__main__':main()
