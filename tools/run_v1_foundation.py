"""Reproduce M01/T01 on pinned atlas inputs and one actual public-city route."""
from pathlib import Path
from dataclasses import asdict
import argparse,json,math,hashlib,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metroflow.terrain_city.area_access import AreaAccess,Portal
from metroflow.v1.access import compile_access
from metroflow.v1.journey import JourneyModel,JourneyBoundary,DelayLaw
from metroflow.packet_network import PacketNetwork
from metroflow.ordered_network import Group,Route
from metroflow.ordered_lane import Lane
from metroflow.active_suffix.common import Signal


def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,sort_keys=True,allow_nan=False)+'\n')


def main(out):
    out=Path(out);root=Path(__file__).resolve().parents[1]
    atlas_path=root/'artifacts/terrain_atlas_20261025/final/polycentric_river.json'
    growth_path=root/'artifacts/block_flux_20261025/map_polycentric_river.json'
    plan_path=root/'artifacts/block_flux_20261025/plan_polycentric_river_dt1.json'
    atlas=json.loads(atlas_path.read_text());growth=json.loads(growth_path.read_text());plan=json.loads(plan_path.read_text())
    nodes={n['id']:n for n in atlas['roadmap']['nodes']}
    blocks={b['id']:b for b in atlas['blocks']};access={a['block']:a for a in growth['access']}
    tag='0:3:109>59'
    route=next(r for r in plan['routes'] if r['tag']==tag)
    original=tuple(route['groups'])
    assert original[0]=='private:109:out' and original[-1]=='private:59:in'
    public=original[1:-1]
    kernels={};reports={}
    for key in ('109','59'):
        points=tuple(tuple(nodes[n]['xyz'][:2]) for n in blocks[key]['boundary'])
        portal=access[key]['road_node']
        profile=AreaAccess(points).evaluate((Portal(portal,tuple(nodes[portal]['xyz'][:2])),),
                                           speed_mps=5.,depth=3,keep_samples=True)
        law=compile_access(profile,bin_s=2.,max_atoms=256)
        probability,delays=law.condition(portal)
        assert abs(probability-1.)<1e-10
        kernels[key]=DelayLaw(delays)
        reports[key]=asdict(law)|dict(old_point_length_m=access[key]['length_m'],block=key,portal=portal)
    allgroups={g['id']:g for g in plan['groups']}
    groups=tuple(Group(k,allgroups[k]['tail'],allgroups[k]['head'],Lane(**allgroups[k]['physics']),
        allgroups[k]['priority'],Signal(**allgroups[k]['signal']) if allgroups[k]['signal'] else None)
        for k in public)
    # Old private links are REPLACED, not retained alongside the access kernels.
    net=PacketNetwork(groups,(Route(tag,public),),dt_s=1.,record_budget=20000)
    results=[]
    for kind in ('zero_access_control','area_access'):
        origin=kernels['109'] if kind=='area_access' else DelayLaw(((0.,1.),))
        destination=kernels['59'] if kind=='area_access' else DelayLaw(((0.,1.),))
        model=JourneyModel(net,(JourneyBoundary(tag,origin,destination),))
        state=model.initial();trace=[];peak=0;max_balance=0.;start=time.perf_counter()
        for i in range(1800):
            state,events=model.step(state,((tag,2.),) if i==0 else ())
            model.check(state)
            r=model.report(state)
            parts=r['residence_vehicle_seconds']
            max_balance=max(max_balance,abs(parts['total']-sum(v for k,v in parts.items() if k!='total')))
            peak=max(peak,r['origin_records']+r['destination_records']+r['traffic_records']['parts'])
            if i%30==0:trace.append(dict(time_s=state.time_s,completed=state.completed,
                          road_completed=state.traffic.completed,mean_journey_s=r['mean_journey_s']))
            if state.completed>=2.-1e-9:break
        r=model.report(state)
        results.append(r|dict(case=kind,trace=trace,peak_records=peak,
                              max_residence_residual=max_balance,wall_s=time.perf_counter()-start,
                              origin_mean_s=origin.mean_s,destination_mean_s=destination.mean_s))
        write(out/f'checkpoint_{kind}.json',asdict(state))
    report=dict(base='0a7c980d3934146a978280fe76045443ad12640e',
        inputs={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (atlas_path,growth_path,plan_path)},
        background_residents=100000,simulated_vehicle_equivalents=2.,route=tag,
        removed_private_links=[original[0],original[-1]],public_groups=len(groups),map_kernels=reports,cases=results,
        scope='One inherited city route; frozen signal plans and fixed route; no full-city traffic or performance claim',
        empirical_calibration='NOT_RUN',continuous_pair_physics='NOT_INTEGRATED')
    write(out/'EXPERIMENTS.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('inputs','map_kernels','cases')},indent=2))
    for key,r in reports.items():print(key,'samples',r['input_samples'],'atoms',len(r['atoms']),'mean',r['mean_s'],'compression_W1_bound',r['mean_absolute_compression_s'])
    for r in results:print({k:v for k,v in r.items() if k not in ('trace',)})
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',default='artifacts/v1_foundation_20261025')
    args=p.parse_args();main(args.out)
