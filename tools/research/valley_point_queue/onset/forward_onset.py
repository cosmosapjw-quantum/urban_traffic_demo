"""Evaluate fixed surgical-arm car-boundary predictions without access to native receipts."""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from native_phase_boundary import original_laws
from physical_onset import H,route_laws


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("repo",type=Path); p.add_argument("prepared",type=Path)
    p.add_argument("output",type=Path); p.add_argument("clocks",nargs="+",type=int)
    args=p.parse_args()
    if args.output.exists(): p.error("Use a fresh prediction file.")
    largest=max(args.clocks)
    if min(args.clocks)<25200 or largest>=28800 or any(t%H for t in args.clocks):
        p.error("This holdout targets original aligned early work clocks.")
    city,calendar,laws,static=original_laws(args.repo.resolve())
    network=args.prepared/"network.txt"
    input_sha=hashlib.sha256(network.read_bytes()).hexdigest()
    meta=json.loads((args.prepared/"input_summary.json").read_text())
    assert (city,calendar.identity,input_sha)==(meta["city_identity"],meta["schedule_identity"],meta["extracted_input_sha256"])
    values=Counter()
    with network.open() as f:
        L,P,G,K,_=next(f).split()
        for _ in range(int(L)): next(f)
        paths=[list(map(int,next(f).split()))[1:] for _ in range(int(P))]
        windows=[tuple(map(float,next(f).split())) for _ in range(int(K))]
        count=0
        for _,legs in calendar.iter_records():
            if not legs:continue
            leg=legs[0]
            if leg.mode!="car" or leg.endpoint_kind!="interzonal" or leg.destination is None:continue
            orig=leg.origin.block_id,leg.origin.kind
            n1,at=laws[orig];n2,other=laws[leg.destination.block_id,leg.destination.kind]
            if not n1 or not n2 or n1==n2:continue
            r,_,k,m,a,b=next(f).split()
            assert (float(a),float(b),float(m))==(math.fsum(d*w for d,w in at),math.fsum(d*w for d,w in other),leg.amounts.vehicles)
            assert ("work","school","service")[int(k)]==leg.purpose
            if leg.purpose=="work":values[orig,int(r)]+=float(m)
            count+=1
        assert count==int(G) and not f.read().strip()
    durations,_=route_laws(paths,static)
    route_ticks=np.rint(durations["native_link_phase"]).astype(int)
    start,end,*_=windows[0]
    @lru_cache(None)
    def source(orig,t):
        if t<start:return 0.
        _,atoms=laws[orig]
        n=(end-start)/H
        N=min(n,(t-start)/H)
        return math.fsum(w*max(0,min(N,math.floor((t+1e-10-start-a)/H+0.5)))/n for a,w in atoms)
    out={}
    for t in args.clocks:
        admitted=math.fsum(m*source(o,t-H) for (o,r),m in values.items())
        exits=math.fsum(m*source(o,t-int(route_ticks[r])) for (o,r),m in values.items())
        out[t]=dict(car_admitted_veh=admitted,car_exited_veh=exits,car_subsystem_stock_veh=admitted-exits)
    path=Path(__file__).resolve().parent
    result=dict(city=city,schedule=calendar.identity,network_sha256=input_sha,observation_step_s=H,
                code_sha256={k:hashlib.sha256((path/k).read_bytes()).hexdigest() for k in
                             ("forward_onset.py","native_phase_boundary.py","physical_onset.py")},
                predictions=out)
    args.output.write_text(json.dumps(result,indent=2)+"\n")


if __name__=="__main__": main()
