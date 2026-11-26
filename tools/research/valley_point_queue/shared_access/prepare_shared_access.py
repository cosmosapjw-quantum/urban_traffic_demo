"""Bind original Valley car records, finite access marginals, scheduled buses, and freight."""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib,json,math,shutil,sys,time
from pathlib import Path
from access_law import coupled,verify,canonical

def main():
    ap=argparse.ArgumentParser()
    for k in ('repo','prepared','passages','out'): ap.add_argument(k,type=Path)
    a=ap.parse_args()
    repo,prep,passages,out=(getattr(a,k).resolve() for k in ('repo','prepared','passages','out'))
    out.mkdir(parents=True,exist_ok=True)
    sys.path[:0]=[str(repo/'tools/research/valley_point_queue/onset')]
    from native_phase_boundary import original_laws
    start=time.monotonic()
    city,cal,laws,static=original_laws(repo)
    from _metroflow_rust import V1RoutingGraph
    from metroflow.foundation_kinetics import VehicleClass,passage
    sha=lambda p:hashlib.file_digest(open(p,'rb'),'sha256').hexdigest()
    meta=json.loads((prep/'input_summary.json').read_text())
    assert city==meta['city_identity'] and cal.identity==meta['schedule_identity']
    assert static['identity']==meta['source_static_identity']
    assert sha(prep/'network.txt')==meta['extracted_input_sha256']
    assert sha(passages)=='a310ee706ae3eb64ba35eef2c9275da38141dbd32eb89f86bcb6a90c89bd73c1'
    idx={k:i for i,k in enumerate(static['link_ids'])}
    arcs=static['route_arcs']
    legal=set(map(tuple,static['allowed_turns']))
    def checkpath(p):
        assert p and all((arcs[i][0],arcs[j][0]) in legal for i,j in zip(p,p[1:]))
    with (prep/'network.txt').open() as f,passages.open() as pf,(out/'groups.tmp').open('w') as g:
        L,P,G,W,dwell=map(float,next(f).split());L,P,G,W=map(int,(L,P,G,W))
        assert int(next(pf))==P and L==len(static['groups'])
        for _ in range(L): next(f)
        paths=[]; times=[]; mapping={}
        for i in range(P):
            n,*p=map(int,next(f).split());assert n==len(p);checkpath(p)
            nn,*t=next(pf).split();assert int(nn)==n and len(t)==n
            paths.append(tuple(p));times.append(t);mapping[tuple(p)]=i
        windows=[tuple(map(float,next(f).split())) for _ in range(W)]
        profmap={w:i for i,w in enumerate(windows)}
        def profile(w):
            if w not in profmap:profmap[w]=len(windows);windows.append(w)
            return profmap[w]
        cls=static['classes'][static['class_names'].index('car')]
        assert all(x[:4]==cls[:4] and x[11]==cls[11] for x in static['classes'])
        vh=VehicleClass('car',preferred_mps=cls[0],response_s=cls[1],accel_mps2=cls[2],brake_mps2=cls[3])
        def pathid(p):
            p=tuple(p);checkpath(p)
            if p in mapping:return mapping[p]
            v=cls[11];t=[]
            for e in p:
                length,speed,*_=static['groups'][e]
                dt,v=passage(vh,v,min(cls[0],speed),length)
                assert math.isfinite(dt) and dt>0
                t.append(format(dt,'.17g'))
            mapping[p]=len(paths);paths.append(p);times.append(t)
            return mapping[p]
        key=lambda measure:(measure.block_id,measure.kind)
        service={ (block,json.loads(label)['kind']):(node,tuple(atoms))
             for label,block,_,node,_,atoms,_ in static['activities'] }
        @lru_cache(maxsize=32768)
        def joint(k1,k2):
            aa,bb=laws[k1][1],laws[k2][1]
            c=coupled(aa,bb);verify(aa,bb,c)
            return [(float(t),float(s),float(w)) for t,s,w in c]
        total=Counter();excluded=Counter();expanded=Counter(); atom_counts=Counter();orig_groups=0;phase=0
        max_mass_error=0.
        for _,legs in cal.iter_records():
            if not legs:continue
            leg=legs[0]
            if leg.mode!='car':continue
            if leg.endpoint_kind!='interzonal' or leg.destination is None:continue
            k1,k2=key(leg.origin),key(leg.destination)
            n1,aa=laws[k1];n2,bb=laws[k2]
            if not n1 or not n2 or n1==n2:continue
            v=next(f).split();p,q,pr=map(int,v[:3]);mass,am,bm=map(float,v[3:])
            assert ('work','school','service')[pr]==leg.purpose and mass==leg.amounts.vehicles
            assert math.isclose(am,math.fsum(t*w for t,w in aa),rel_tol=0,abs_tol=1e-12)
            assert math.isclose(bm,math.fsum(t*w for t,w in bb),rel_tol=0,abs_tol=1e-12)
            assert (arcs[paths[p][0]][1],arcs[paths[p][-1]][2])==(n1,n2)
            assert (arcs[paths[q][0]][1],arcs[paths[q][-1]][2])==(n2,n1)
            c=joint(k1,k2);atom_counts[len(c)]+=1
            max_mass_error=max(max_mass_error,abs(math.fsum(mass*w for _,_,w in c)-mass))
            for t,s,w in c:
                print(p,q,pr,format(mass*w,'.17g'),t,s,0,phase,file=g)
            total['car']+=2*mass;expanded['car']+=len(c);orig_groups+=1;phase+=1
        assert orig_groups==G and not f.read().strip() and math.isclose(total['car'],meta['projected_vehicles'],abs_tol=1e-7)
        # The native fleet is a fixed inventory, not passenger-demand vehicle equivalents.
        routes=dict(static['corridor_routes'])
        for bid,_,_,t,_,dwell_bus in static['corridors']:
            if bid not in routes:raise ValueError('missing actual bus route')
            p=pathid([idx[x] for x in routes[bid]])
            pr=profile((t,t,0.,0.))
            print(p,-1,pr,1.,0.,0.,2,phase,file=g)
            total['scheduled_bus']+=1;expanded['scheduled_bus']+=1;phase+=1
        # Actual one-way freight, native depot and service access law; use fixed legal
        # shortest route, not the dynamic assignment. Co-located freight is excluded.
        router=V1RoutingGraph(static['route_arcs'],[x[1] for x in static['route_costs']],static['allowed_turns'],8)
        depot=static['depot_node_or_None']
        for leg in cal.iter_freight_legs():
            node,atoms=service[key(leg.destination)]
            if not node or node==depot or not atoms:
                excluded['freight_colocated_or_missing']+=leg.amounts.vehicles;continue
            found,_,_=router.search(depot,node,1,2000)
            if not found or not found[0]:
                excluded['freight_missing_route']+=leg.amounts.vehicles;continue
            p=pathid([idx[x] for x in found[0]])
            for win in leg.departures.windows:
                pr=profile((win.start_s,win.end_s,0.,0.))
                m=leg.amounts.vehicles*win.probability
                for s,w in canonical(atoms):
                    print(p,-1,pr,format(m*float(w),'.17g'),0.,float(s),1,phase,file=g)
                    expanded['freight']+=1
                total['freight']+=m;phase+=1
    net=out/'network.txt'
    with net.open('w') as f,(out/'groups.tmp').open() as g:
        print(L,len(paths),sum(expanded.values()),len(windows),dwell,file=f)
        for length,v,entry,exit,storage,_ in static['groups']:
            print(length/min(v,10.),entry,exit,storage,file=f)
        for p in paths:print(len(p),*p,file=f)
        for w in windows:print(*w,file=f)
        shutil.copyfileobj(g,f)
    (out/'groups.tmp').unlink()
    with (out/'passages.txt').open('w') as f:
        print(len(paths),file=f)
        for t in times:print(len(t),*t,file=f)
    summary=dict(city_identity=city,schedule_identity=cal.identity,static_identity=static['identity'],
        old_network_sha256=meta['extracted_input_sha256'],network_sha256=sha(net),
        passages_sha256=sha(out/'passages.txt'),links=L,original_car_groups=G,expanded_groups=dict(expanded),
        coupling_atom_counts=dict(atom_counts),expected_vehicle_trips=dict(total),excluded=dict(excluded),
        max_group_mass_roundoff=max_mass_error,footprints_m=[x[12] for x in static['classes']],
        classes=static['class_names'],profiles=len(windows),paths=len(paths),
        coupling='common quantile rank, exact normalized finite marginals, not independent product',
        wall_s=time.monotonic()-start)
    assert summary['classes']==['car','freight','scheduled_bus'] and max_mass_error<1e-12
    (out/'input_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)
if __name__=='__main__':main()
