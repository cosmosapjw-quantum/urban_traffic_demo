#!/usr/bin/env python3
"""Matched-physics FIFO compression benchmark. No empirical field-data claims.

The baseline and the certified adaptive scheme solve the SAME corrected
eligible-prefix node physics with different lossless ordered-run encodings.
A/B ordering alternates by tick. No original V1 packet solver is run.
"""
from __future__ import annotations
from argparse import ArgumentParser
import json
import math
from pathlib import Path
import platform
import statistics
import time

from metroflow.v1.kcmb import KCMBClass
from metroflow.v1.kcmb_network import KCMBLink,KCMBRoute,KCMBNetworkConfig
from metroflow.v1.kcmb_ordered_fifo import OrderedKCMBBoundedNetwork
from metroflow.v1.kcmb_adaptive_fifo import CertifiedAdaptiveFIFO


def fixture(kind: str,backend:str):
    car=KCMBClass("car",10.,5.,.2,0.,1.,
                  source_p=1.,source_speed_fraction=1.)
    if kind=="homogeneous":
        links=(KCMBLink("in","O","D",1000.,1,5.,5.),)
        routes=(KCMBRoute("A",car,("in",)),)
        steps=320
        budget=130
        def input_at(t):
            return ((.1 if t<240 else 0.,),
                    {("in",None):float(t>=240)})
    else:
        links=(KCMBLink("in","O","J",1000.,1,5.,5.),
               KCMBLink("left","J","L",1000.,1,5.,5.),
               KCMBLink("right","J","R",1000.,1,5.,5.))
        routes=(KCMBRoute("A",car,("in","left")),
                KCMBRoute("B",car,("in","right")))
        steps=280
        budget=300
        def input_at(t):
            offer=((.1,0.) if t%2==0 else (0.,.1)) if t<200 else (0.,0.)
            return offer,{("in","left"):float(t>=200),
                          ("in","right"):float(t>=200)}
    config=KCMBNetworkConfig(links,routes,dt_s=1.)
    return (OrderedKCMBBoundedNetwork(config,backend=backend,max_runs=5000),
            CertifiedAdaptiveFIFO(config,backend=backend,max_runs=budget),
            steps,input_at)


def compare(kind:str,backend:str):
    old,new,steps,input_at=fixture(kind,backend)
    a,b=old.initial(),new.initial()
    timing={"ordered":[],"certified_adaptive":[]}
    peak_runs={"ordered":0,"certified_adaptive":0}
    final=None
    max_difference=0.
    merged=0
    checkpoint_peak={"ordered":0,"certified_adaptive":0}
    for tick in range(steps):
        offer,signal=input_at(tick)
        if tick%2==0:
            order=[("ordered",old,a),("certified_adaptive",new,b)]
        else:
            order=[("certified_adaptive",new,b),("ordered",old,a)]
        events={}
        for name,model,state in order:
            start=time.perf_counter_ns()
            next_state,receipt=model.step(state,offer,gates=signal)
            timing[name].append(time.perf_counter_ns()-start)
            events[name]=(next_state,receipt)
        a,ra=events["ordered"]
        b,rb=events["certified_adaptive"]
        assert a.tick==b.tick==tick+1
        assert a.released==b.released
        for x,y in zip(a.moments,b.moments):
            max_difference=max(max_difference,abs(x-y))
        for f in ("pending","completed"):
            for x,y in zip(getattr(a,f),getattr(b,f)):
                max_difference=max(max_difference,abs(x-y))
        allkeys=set(ra["turn_flows"])|set(rb["turn_flows"])
        for key in allkeys:
            max_difference=max(max_difference,abs(ra["turn_flows"].get(key,0.)-
                                                  rb["turn_flows"].get(key,0.)))
        if max_difference>2e-8:
            raise AssertionError(f"physical observable mismatch: {kind} {backend} tick={tick} {max_difference}")
        for name,state,model in (("ordered",a,old),("certified_adaptive",b,new)):
            peak_runs[name]=max(peak_runs[name],sum(len(q) for q in state.runs))
            if tick in (0,80,160,240,steps-1):
                checkpoint_peak[name]=max(checkpoint_peak[name],len(model.to_bytes(state)))
        merged+=rb["runs_certifiably_merged"]
    result={
        "kind":kind,"backend":backend,"steps":steps,
        "max_abs_difference_physical":max_difference,
        "total_eligible_runs_coalesced":merged,
        "peak_runs":peak_runs,
        "final_runs":{"ordered":sum(len(q) for q in a.runs),
                      "certified_adaptive":sum(len(q) for q in b.runs)},
        "peak_sampled_checkpoint_bytes":checkpoint_peak,
        "max_accepted_adaptive_runs":new.strict_max_runs,
        "total_step_s":{key:sum(v)/1e9 for key,v in timing.items()},
        "median_step_us":{key:statistics.median(v)/1e3 for key,v in timing.items()},
        "time_ratio_ordered_over_adaptive":sum(timing["ordered"])/sum(timing["certified_adaptive"]),
        "source_vehicle_mass_by_route":a.released,
        "finished_vehicle_mass_by_route":a.completed,
        "scope":"matched corrected KCMB node physics; not original V1 or field observations",
    }
    return result


def main():
    cli=ArgumentParser()
    cli.add_argument("--backend",choices=("python","rust"),required=True)
    cli.add_argument("--output",required=True)
    args=cli.parse_args()
    data={
      "title":"Certified lossless adaptive eligible FIFO coalescence: same physics",
      "model_parent":"ordered FIFO v2 partition-invariant",
      "backend":args.backend,
      "python_version":platform.python_version(),
      "scenarios":[compare(x,args.backend) for x in ("homogeneous","alternating")],
    }
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    for row in data["scenarios"]:
        print(json.dumps({key:row[key] for key in (
            "kind","backend","steps","max_abs_difference_physical",
            "peak_runs","final_runs","total_step_s",
            "time_ratio_ordered_over_adaptive","total_eligible_runs_coalesced"
        )}))


if __name__=="__main__":
    main()
