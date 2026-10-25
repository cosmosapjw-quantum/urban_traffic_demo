"""Bounded experiments separating symmetry, representation and measured outputs."""
from pathlib import Path
import sys,json,math,time,argparse,hashlib
from dataclasses import asdict,replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))


def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,sort_keys=True,allow_nan=False)+'\n')


def maps(out):
    from metroflow.terrain_city.area_access import AreaAccess,Portal
    from metroflow.terrain_city.landscape import Polygon,polygon_clear
    rows=[]
    for case in ('polycentric_river','valley_city','coastal_port'):
        path=Path(f'artifacts/terrain_atlas_20261025/final/{case}.json')
        atlas=json.loads(path.read_text())
        grown=json.loads(Path(f'artifacts/block_flux_20261025/map_{case}.json').read_text())
        changes={b['id']:n-b['residents'] for b,n in zip(atlas['blocks'],grown['history'][-1]['residents'])}
        key=max(changes,key=changes.get);block=next(b for b in atlas['blocks'] if b['id']==key)
        nodes={n['id']:tuple(n['xyz'][:2]) for n in atlas['roadmap']['nodes']}
        boundary=tuple(nodes[k] for k in block['boundary'])
        mask=tuple(Polygon(p['name'],tuple(tuple(v) for v in p['points'])) for p in
                   atlas['landscape']['water']+atlas['landscape']['protected'])
        assert polygon_clear(boundary,mask)
        baseline=next(a for a in grown['access'] if a['block']==key)
        gate=Portal(baseline['road_node'],nodes[baseline['road_node']])
        model=AreaAccess(boundary);t0=time.perf_counter()
        profile=model.evaluate((gate,),speed_mps=5.,depth=3,keep_samples=True)
        coarse=model.evaluate((gate,),speed_mps=5.,depth=2)
        surface={node for s in atlas['roadmap']['sections'] if s['facility']=='surface' for node in (s['start'],s['end'])}
        proposals=tuple(Portal(k,nodes[k]) for k in block['boundary'] if k in surface and k!=gate.id)
        ranked=model.candidate_additions((gate,),proposals,speed_mps=5.,depth=2)
        # This selected scenario is the numerical minimum, not a certified unique
        # optimum when the reported error intervals overlap. IDs do not rank it.
        best=min(ranked['candidates'],key=lambda r:r['mean_s'])
        added=next(p for p in proposals if p.id==best['portal'])
        two=model.evaluate((gate,added),speed_mps=5.,depth=3,keep_samples=True)
        result=dict(case=case,block=key,input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            new_residents_in_parent=changes[key],boundary=boundary,old_anchor=block['xy'],
            original_length_m=baseline['length_m'],first_gate=asdict(gate),proposed_second_gate=asdict(added),
            one_portal=profile,two_portal=two,coarse_mean_s=coarse['mean_s'],
            coarse_error_s=coarse['error_bound_s'],portal_candidates=ranked,
            euclidean_rms_to_first_gate_m=math.sqrt(model.squared_distance_mean(gate.xy)),
            elapsed_s=time.perf_counter()-t0,
            scope='uniform planar internal access proxy; no new public road or calibrated building occupancy; gates are existing surface nodes')
        write(out/f'area_{case}.json',result)
        rows.append({k:result[k] for k in ('case','block','original_length_m','new_residents_in_parent','euclidean_rms_to_first_gate_m') }|
                    dict(mean_internal_distance_m=5*profile['mean_s'],error_distance_m=5*profile['error_bound_s'],
                         p95_quadrature_distance_m=5*profile['p95_quadrature_s'],
                         two_portal_mean_m=5*two['mean_s'],two_portal_error_m=5*two['error_bound_s'],
                         quadrature_samples=profile['samples']))
    write(out/'MAP_RESULTS.json',rows);return rows


def traffic(out):
    from metroflow.ordered_lane import Lane
    from metroflow.ordered_network import Network,Group,Route
    from metroflow.packet_network import PacketNetwork
    def trial(cls,names=('a','b'),fragment=1,weights=(1.,1.)):
        a,b=names
        groups=(Group(a,'A','M',Lane(1,10,1,1,20,interaction_rate=0),weights[0]),
                Group(b,'B','M',Lane(1,10,1,1,20,interaction_rate=0),weights[1]),
                Group('c','M','D',Lane(1,10,2,.25,20,interaction_rate=0)))
        model=cls(groups,(Route('F',(a,'c')),Route('G',(b,'c'))));s=model.initial()
        done={'F':0.,'G':0.};moment=dict(done);peak=0;trace=[]
        for k in range(25):
            offers=tuple((tag,1./fragment) for tag in ('F','G') for _ in range(fragment)) if k==0 else ()
            s,events=model.step(s,offers)
            for e in events:
                if e.destination is None:
                    done[e.tag]+=e.mass;moment[e.tag]+=e.mass*(e.start_s+e.end_s)/2
            if cls is PacketNetwork:peak=max(peak,model.counts(s)['parts'])
            else:peak=max(peak,len(s.pending)+sum(len(x.inside) for x in s.lanes))
            trace.append(dict(t=s.time_s,completed=dict(done)))
        return dict(mean_s={k:moment[k]/done[k] for k in done},completed=done,peak_parts=peak,
                    system_residence=s.system_vehicle_seconds,trace=trace)
    result=dict(parent=trial(Network),parent_renamed=trial(Network,('b','a')),
        packet=trial(PacketNetwork),packet_renamed=trial(PacketNetwork,('b','a')),
        fragmented_packet=trial(PacketNetwork,fragment=100),fragmented_parent=trial(Network,fragment=100))
    write(out/'TRAFFIC_RESULTS.json',result);return {k:{j:v for j,v in r.items() if j!='trace'} for k,r in result.items()}


def city(out,seconds=120.):
    if not math.isfinite(seconds) or seconds<=0 or seconds!=round(seconds):
        raise ValueError('observation must be a positive integer number of 1-second steps')
    from metroflow.ordered_lane import Lane
    from metroflow.ordered_network import Group,Route,Network
    from metroflow.packet_network import PacketNetwork
    from metroflow.active_suffix.common import Signal
    path=Path('artifacts/block_flux_20261025/plan_polycentric_river_dt1.json')
    data=json.loads(path.read_text())
    groups=tuple(Group(g['id'],g['tail'],g['head'],Lane(**g['physics']),g['priority'],
                       Signal(**g['signal']) if g['signal'] else None) for g in data['groups'])
    routes=tuple(Route(r['tag'],tuple(r['groups'])) for r in data['routes']);amounts=data['amounts']
    reports=[]
    for cls in (Network,PacketNetwork):
        model=cls(groups,routes,record_budget=20000);s=model.initial();peak=0;masserr=0.;stor=0.;t0=time.perf_counter()
        for k in range(round(seconds)):
            s,e=model.step(s,tuple((tag,mass/60) for tag,mass in amounts) if k<60 else ())
            if cls is PacketNetwork:
                active=math.fsum(c.occupancy for c in s.cells);pending=math.fsum(p.mass for q in s.pending for p in q)
                peak=max(peak,model.counts(s)['parts']);cells=s.cells
            else:
                active=math.fsum(c.occupancy for c in s.lanes);pending=math.fsum(p.mass for p in s.pending)
                peak=max(peak,len(s.pending)+sum(len(c.inside) for c in s.lanes));cells=s.lanes
            masserr=max(masserr,abs(s.released-s.completed-active-pending))
            stor=max(stor,max(c.occupancy/g.physics.storage for c,g in zip(cells,model.groups)))
        reports.append(dict(model=cls.__name__,time_s=s.time_s,released=s.released,completed=s.completed,
                    active=active,pending=pending,max_mass_error=masserr,max_storage_ratio=stor,
                    peak_parts=peak,elapsed_s=time.perf_counter()-t0,system_residence=s.system_vehicle_seconds,
                    status='HORIZON_REACHED',mean_journey_s=None))
        write(out/f'city_{cls.__name__}_checkpoint.json',asdict(s))
    result=dict(input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),groups=len(groups),routes=len(routes),
                scenario='150 vehicle-equivalent visits from 1500 new occupants; no 100k background traffic',cases=reports)
    write(out/'CITY_RESULTS.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--part',choices=('map','traffic','city'),required=True)
    p.add_argument('--out',type=Path,default=Path('artifacts/symmetry_observables_20261025'))
    p.add_argument('--seconds',type=float,default=120.)
    a=p.parse_args();result=maps(a.out) if a.part=='map' else traffic(a.out) if a.part=='traffic' else city(a.out,a.seconds)
    print(json.dumps(result,indent=2,allow_nan=False))
