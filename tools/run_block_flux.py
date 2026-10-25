"""Frozen atlas -> slow growth -> bounded transport experiments."""
from pathlib import Path
from dataclasses import asdict
import argparse,hashlib,json,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metroflow.environment.terrain import Terrain,Rect
from metroflow.terrain_city.landscape import Landscape,Polygon
from metroflow.terrain_city.network import Atlas,Block
from metroflow.restored_city import RoadMap,Junction,Section
from metroflow.terrain_city.block_access import Growth,build_access


def read_atlas(path):
    data=json.loads(Path(path).read_text());ld=data['landscape']
    def terrain(t):
        return Terrain(t['n'],t['spacing_m'],tuple(t['heights_m']),tuple(Rect(**r) for r in t.get('water',())),
                       tuple(Rect(**r) for r in t.get('protected',())),tuple(t.get('bridge_rows',())))
    land=Landscape(ld['kind'],ld['seed'],terrain(ld['terrain']),
          tuple(Polygon(p['name'],tuple(tuple(x) for x in p['points'])) for p in ld['water']),
          tuple(Polygon(p['name'],tuple(tuple(x) for x in p['points'])) for p in ld['protected']))
    r=data['roadmap'];nodes=tuple(Junction(n['id'],tuple(n['xyz']),n['layer']) for n in r['nodes'])
    sections=tuple(Section(**(s|{'points':tuple(tuple(x) for x in s['points'])})) for s in r['sections'])
    road=RoadMap(r['style'],terrain(r['terrain']),nodes,sections,tuple(tuple(x) for x in r['rejected']))
    blocks=tuple(Block(**(b|{'boundary':tuple(b['boundary']),'xy':tuple(b['xy'])})) for b in data['blocks'])
    return Atlas(land,road,tuple(data['centers']),tuple(tuple(x) for x in data['phases']),blocks,data['summary'])


def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,sort_keys=True,allow_nan=False)+'\n')


def map_run(path,out):
    start=time.perf_counter();a=read_atlas(path);access,rejected=build_access(a)
    valid={x.block for x in access}
    jobs=tuple(b.id for b in sorted(a.blocks,key=lambda b:(-b.jobs,b.id)) if b.jobs>0 and b.id in valid)[:3]
    model=Growth(a,jobs);state=model.initial();history=[asdict(state)];receipts=[]
    for _ in range(3):
        state,r=model.step(state,500,budget_m=500.,max_new_access=4);receipts.append(r);history.append(asdict(state))
    result=dict(case=Path(path).stem,input_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                atlas_id=model.identity,blocks=len(a.blocks),admitted_access=len(access),rejected_access=rejected,
                incumbent_residents=sum(b.residents for b in a.blocks),
                inherited_unplaced=a.summary.get('unplaced_residents'),new_offered=state.offered,
                new_placed=sum(state.residents)-sum(b.residents for b in a.blocks),pending=state.pending,
                growth_access_m=state.built_m,attractors=jobs,epochs=receipts,
                history=history,access=[asdict(x) for x in access],seconds=time.perf_counter()-start,
                scope='private access and incremental occupancy; fixed public streets, block footprints and job opportunities')
    write(Path(out)/f'map_{Path(path).stem}.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('history','access','epochs')},indent=2))
    return model,state,result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--out',default='artifacts/block_flux_20261025')
    p.add_argument('--traffic',action='store_true');p.add_argument('--dt',type=float,default=1.)
    p.add_argument('--horizon',type=float,default=2400.)
    args=p.parse_args();model,state,result=map_run(args.input,args.out)
    if args.traffic:
        from metroflow.terrain_city.block_trips import plan_visits,simulate_visits
        plan=plan_visits(model,model.initial(),state)
        started=time.perf_counter()
        report,checkpoint=simulate_visits(plan,horizon_s=args.horizon,dt_s=args.dt)
        report['seconds']=time.perf_counter()-started
        stem=Path(args.input).stem+f'_dt{args.dt:g}'
        write(Path(args.out)/f'plan_{stem}.json',asdict(plan))
        write(Path(args.out)/f'traffic_{stem}.json',report)
        write(Path(args.out)/f'checkpoint_{stem}.json',asdict(checkpoint))
        print(json.dumps({k:v for k,v in report.items() if k not in ('trace','completed_events')},indent=2))
