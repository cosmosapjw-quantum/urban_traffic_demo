#!/usr/bin/env python3
"""Bounded node-locality benchmark, not original V03 traffic runtime.

Timed kernels have identical group inputs and state semantics. Source/route
identity and resource constraints are matched before comparing timings.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import platform
import resource
import statistics
from time import perf_counter

from metroflow.v1.kcmb import KCMBClass
from metroflow.v1.kcmb_network import (
    KCMBLink, KCMBRoute, KCMBNetworkConfig, KCMBBoundedNetwork,
    progressive_junction,
)
from _metroflow_rust import allocate_kcmb_nodes


def node_allocation(n:int,repeats:int):
    groups=tuple(((i,i,0.25,5.),) for i in range(n))
    receiving={i:1. for i in range(n)}
    vacant={i:10. for i in range(n)}
    weights=(1.,)*n
    def py_global():
        return progressive_junction(groups,receive_count=receiving,
            receive_metres=vacant,weights=weights)
    def py_local():
        out={}
        for g in range(n):
            row=progressive_junction((groups[g],),
                receive_count={g:1.},receive_metres={g:10.},weights=(1.,))
            out[g,0]=row[0,0]
        return out
    def rust_global():
        x=allocate_kcmb_nodes(
            [[(i,i,.25,5.)] for i in range(n)],[1.]*n,[10.]*n,[1.]*n,[1.]*n)
        return {(g,z):v for g,z,v in x}
    def rust_local():
        out={}
        for g in range(n):
            result=allocate_kcmb_nodes([[(g,0,.25,5.)]],[1.],[10.],[1.],[1.])
            out[g,0]=result[0][2]
        return out
    fns={"python_global":py_global,"python_node_local":py_local,
         "rust_global":rust_global,"rust_node_local":rust_local}
    timings={}
    digest={}
    for k,fn in fns.items():
        samples=[]
        result=None
        for _ in range(repeats):
            t0=perf_counter()
            result=fn()
            samples.append(perf_counter()-t0)
        assert result is not None and len(result)==n
        assert all(abs(value-.25)<1e-12 for value in result.values())
        timings[k]={"seconds":samples,"median_seconds":statistics.median(samples)}
        digest[k]=round(math.fsum(result.values()),12)
    assert len(set(digest.values()))==1
    return {"groups":n,"receiver_resources":n,"repeats":repeats,
            "timings":timings,"output_total_veh":digest["python_node_local"],
            "outcome":"all allocation outputs are identical",
            "interpretation":"independent-junction resource matrix; no full traffic model in this sub-benchmark"}


def network(n:int,backend:str,steps:int):
    links=tuple(KCMBLink(f"road{i}",f"node{i}",f"node{i+1}",20.,1,2.,5.)
                for i in range(n))
    c=KCMBClass("car",10.,5.,.2,.3,2.,
                source_p=1.,source_speed_fraction=1.)
    route=KCMBRoute("single_route",c,tuple(l.name for l in links))
    model=KCMBBoundedNetwork(KCMBNetworkConfig(
        links=links,routes=(route,),dt_s=.5),backend=backend)
    state=model.initial_profile({f"road{i}":(.1,) for i in range(n)})
    times=[]
    for t in range(steps):
        start=perf_counter()
        state,r=model.step(state,(.3 if t%5 else 0.,),
                           gates={(f"road{n-1}",None):float(t%17>=5)})
        times.append(perf_counter()-start)
    active=math.fsum(model.cell_class_mass(state,f"road{i}",0) for i in range(n))
    assert abs(state.released[0]-state.pending[0]-state.completed[0]-active)<1e-7
    return {"links":n,"backend":backend,"steps":steps,
            "timed_step_total_seconds":sum(times),
            "median_step_seconds":statistics.median(times),
            "state_scalars":model.state_scalars,
            "released_veh":state.released[0],"completed_veh":state.completed[0],
            "pending_veh":state.pending[0],"active_veh":active,
            "peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "scope":"opt-in one-route synthetic chain, not city/campaign"}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--target",choices=("node","network"),required=True)
    parser.add_argument("--links",type=int,default=400)
    parser.add_argument("--repeats",type=int,default=3)
    parser.add_argument("--backend",choices=("python","rust"),default="python")
    parser.add_argument("--steps",type=int,default=20)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    if args.links<1 or args.repeats<1 or args.steps<1:
        parser.error("positive bounded simulation size required")
    result=node_allocation(args.links,args.repeats) if args.target=="node" else network(
        args.links,args.backend,args.steps)
    result["python"]=platform.python_version()
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({k:result[k] for k in result if k in (
        "links","groups","repeats","backend","steps","timed_step_total_seconds",
        "median_step_seconds","outcome","state_scalars")}))


if __name__=="__main__":
    main()
