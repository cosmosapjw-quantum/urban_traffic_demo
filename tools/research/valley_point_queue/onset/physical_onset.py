"""Unfitted Valley car outlet comparison on three original native clock boundaries."""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
import numpy as np
from native_phase_boundary import original_laws

H=10
REFS={25700:"artifacts/v03_causal_rank_20261123/S04_original_continuation.json",
      25710:"artifacts/v03_coding_reconstruction_20261123/C7_original_continuation.json",
      25720:"artifacts/v03_measure_lift_20261123/S06_fresh0.json"}


def route_laws(paths,static):
    from metroflow.foundation_kinetics import VehicleClass,passage
    cls=static["classes"][static["class_names"].index("car")]
    pref,tau,acc,brake=cls[:4]
    v0=cls[11]
    lengths=np.array([g[0] for g in static["groups"]])
    targets=np.minimum(pref,[g[1] for g in static["groups"]])
    routes=np.full((len(paths),max(map(len,paths))),-1,dtype=int)
    for i,path in enumerate(paths):
        routes[i,:len(path)]=path
    n=len(paths)
    speed=np.full(n,v0,dtype=float)
    free=np.zeros(n); kinetic=np.zeros(n); staged=np.full(n,H,dtype=float)
    sanity=0.
    for edges in routes.T:
        active=edges>=0
        e=edges[active]
        u,V,L=speed[active],targets[e],lengths[e]
        diff=V-u
        lim=np.where(diff>=0,acc,brake)
        sat=np.maximum(0,(np.abs(diff)-lim*tau)/lim)
        a=np.where(diff>=0,lim,-lim)
        def characteristic(dt):
            part=np.minimum(sat,dt)
            w=u+a*part
            rem=dt-part
            mix=-np.expm1(-rem/tau)
            dist=u*part+0.5*a*part*part+V*rem+(w-V)*tau*mix
            return dist,w+(V-w)*mix
        lo=np.zeros(len(e)); hi=2+2*L/V+np.maximum(0,V-u)/acc+2*tau
        assert np.all(characteristic(hi)[0]>=L)
        for _ in range(42):
            mid=(hi+lo)/2
            before=characteristic(mid)[0]<L
            lo=np.where(before,mid,lo);hi=np.where(before,hi,mid)
        _,w=characteristic(hi)
        # Compare actual project scalar characteristic and passage on each route depth.
        veh=VehicleClass("car",preferred_mps=pref,response_s=tau,accel_mps2=acc,brake_mps2=brake)
        check_t,check_w=passage(veh,float(u[0]),float(V[0]),float(L[0]))
        sanity=max(sanity,abs(float(hi[0])-check_t),abs(float(w[0])-check_w))
        free[active]+=L/V
        kinetic[active]+=hi
        staged[active]+=H*np.ceil(hi/H-1e-10)
        speed[active]=w
    assert sanity<1e-8
    return dict(free_flow=free,free_kinetic=kinetic,native_link_phase=staged),dict(
        preferred_m_s=pref,entry_m_s=v0,response_s=tau,accel_m_s2=acc,brake_m_s2=brake,
        scalar_passage_max_abs_discrepancy=sanity)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo",type=Path)
    parser.add_argument("prepared",type=Path)
    parser.add_argument("solver",type=Path,help="C07 compiled point queue")
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    began=time.perf_counter()
    repo,prep=args.repo.resolve(),args.prepared.resolve()
    city,cal,laws,static=original_laws(repo)
    meta=json.loads((prep/"input_summary.json").read_text())
    assert (city,cal.identity)==(meta["city_identity"],meta["schedule_identity"])
    network=prep/"network.txt"
    assert hashlib.sha256(network.read_bytes()).hexdigest()==meta["extracted_input_sha256"]
    mass=Counter()
    with network.open() as f:
        L,P,G,K,_=next(f).split()
        for _ in range(int(L)): next(f)
        paths=[list(map(int,next(f).split()))[1:] for _ in range(int(P))]
        windows=[list(map(float,next(f).split())) for _ in range(int(K))]
        matched=0
        for _,legs in cal.iter_records():
            if not legs: continue
            leg=legs[0]
            if leg.mode!="car" or leg.endpoint_kind!="interzonal" or leg.destination is None: continue
            origin=leg.origin.block_id,leg.origin.kind
            o,atoms=laws[origin];d,other=laws[leg.destination.block_id,leg.destination.kind]
            if not o or not d or o==d: continue
            r,_,k,m,am,bm=next(f).split()
            assert (float(am),float(bm),float(m))==(math.fsum(a*p for a,p in atoms),math.fsum(a*p for a,p in other),leg.amounts.vehicles)
            assert ("work","school","service")[int(k)]==leg.purpose
            matched+=1
            if windows[int(k)][0]<=max(REFS): mass[origin,int(k),int(r)]+=float(m)
        assert matched==int(G) and not f.read().strip()
    durations,vehicle=route_laws(paths,static)
    @lru_cache(None)
    def offered(origin,k,t):
        start,end,*_=windows[k]
        if t<start:return 0.
        _,atoms=laws[origin]
        total=(end-start)/H
        eligible=min(total,(t-start)/H)
        return math.fsum(p*max(0,min(eligible,math.floor((t+1e-10-start-a)/H+0.5)))/total for a,p in atoms)
    refs={}
    for T,file in REFS.items():
        historical=repo/file
        report=json.loads(historical.read_text())["final_execution_report"]
        assert (report["city_identity"],report["schedule_identity"])==(city,cal.identity)
        service=report["service"]
        assert service["time_s"]==T and service["bus_road_vehicles"]==service["freight_completed_vehicles"]==0
        buses=service["completed_bus_vehicles"]
        native=service["road_completed_veh"]-buses
        admitted=service["road_released_veh"]-buses
        pred_admitted=math.fsum(m*offered(o,k,T-H) for (o,k,r),m in mass.items())
        assert abs(pred_admitted-admitted)<1e-8
        baseline=subprocess.check_output([args.solver.resolve(),network,"10","-1","1",str(T)],text=True)
        baseline_line=next(x for x in baseline.splitlines() if x.startswith(f"snap {T} "))
        observed={"prior_point_queue":float(baseline_line.split()[4])}
        for arm,duration in durations.items():
            cutoff=H*np.floor((T-duration)/H+1e-10)
            observed[arm]=math.fsum(m*offered(o,k,int(cutoff[r])) for (o,k,r),m in mass.items())
        refs[T]=dict(ref=file,sha256=hashlib.sha256(historical.read_bytes()).hexdigest(),native_admitted_veh=admitted,
            source_phase_admitted_veh=pred_admitted,native_exited_veh=native,
            arms={k:dict(exited_veh=v,error_veh=v-native,relative_error=v/native-1) for k,v in observed.items()})
    doc=dict(schema="original_valley_car_surgical_onset_v1",city=city,schedule=cal.identity,network_sha256=meta["extracted_input_sha256"],
             step_s=H,vehicle=vehicle,matched_car_calendar_legs=2*matched,distinct_paths=len(paths),clocks=refs,
             wall_s=time.perf_counter()-began)
    args.output.write_text(json.dumps(doc,indent=2,allow_nan=False)+"\n")


if __name__=="__main__":
    main()
