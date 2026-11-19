#!/usr/bin/env python3
"""Matched-input physics sensitivity to explicitly declared turning-lane geometry.

Two physics variants deliberately have different road storage/spatial topology.
Only Python/Rust comparisons *within* a variant are same-physics performance
claims. Observed driver/lane data are NOT used in this research-only harness.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import resource
import statistics
from time import perf_counter_ns

from metroflow.v1.kcmb import KCMBClass
from metroflow.v1.kcmb_network import KCMBLink, KCMBRoute, KCMBNetworkConfig
from metroflow.v1.kcmb_adaptive_fifo import CertifiedAdaptiveFIFO
from metroflow.v1.kcmb_turn_pockets import (
    PocketGroup, TurnPocketLayout, compile_turn_pockets,
)


def setup(geometry: str, backend: str):
    c=KCMBClass("test_driver",vmax_mps=10.,footprint_m=5.,
                alpha_per_s=.2,nu_per_s=0.,tau_s=1.,
                source_p=1.,source_speed_fraction=1.)
    original=KCMBNetworkConfig(
        (KCMBLink("approach","O","J",100.,1,2.,5.),
         KCMBLink("left","J","L",100.,1,2.,5.),
         KCMBLink("right","J","R",100.,1,2.,5.)),
        (KCMBRoute("A",c,("approach","left")),
         KCMBRoute("B",c,("approach","right"))),dt_s=.5)
    if geometry=="coarse_one_lane":
        graph=original
        left="approach"
        right="approach"
        ledger={"total_physical_lane_metres":100.,
                "approach_lane_metres":100.,
                "extra_widened_lane_metres":0.}
    else:
        if geometry=="mixed_one_pocket":
            groups=(PocketGroup("mixed",("A","B"),1,1.),)
        elif geometry=="split_two_pockets":
            groups=(PocketGroup("A_pocket",("A",),1,1.),
                    PocketGroup("B_pocket",("B",),1,1.))
        else:
            raise ValueError("unknown geometry")
        compiled=compile_turn_pockets(original,TurnPocketLayout(
            "approach",30.,groups))
        graph=compiled.config
        lookup=dict(compiled.pocket_link_by_group)
        left=lookup["mixed"] if geometry=="mixed_one_pocket" else lookup["A_pocket"]
        right=lookup["mixed"] if geometry=="mixed_one_pocket" else lookup["B_pocket"]
        ledger={
           "approach_lane_metres_before":compiled.geometry.original_lane_metres,
           "approach_lane_metres_after":compiled.geometry.compiled_lane_metres,
           "extra_widened_lane_metres":compiled.geometry.added_lane_metres,
           "pocket_region_lanes":compiled.geometry.pocket_region_lanes}
    return (CertifiedAdaptiveFIFO(graph,backend=backend,max_runs=1400),
            left,right,ledger)


def run(geometry:str,backend:str,steps:int):
    model,left,right,ledger=setup(geometry,backend)
    state=model.initial()
    times=[]
    max_runs=0
    max_error=0.
    checkpoints=[]
    # Same offered vehicle-equivalent mass and signal history in all variants.
    for tick in range(steps):
        demand=(.25,.25) if tick<110 else (0.,0.)
        signals={(left,"left"):float(tick>=110),
                 (right,"right"):1.}
        before=perf_counter_ns()
        state,receipt=model.step(state,demand,gates=signals)
        times.append(perf_counter_ns()-before)
        max_runs=max(max_runs,receipt["run_count"])
        max_error=max(max_error,receipt["mass_error_max_veh"])
        if tick in (49,99,109,140,steps-1):
            checkpoints.append({
                "tick":state.tick,
                "completed_by_route":state.completed,
                "pending_by_route":state.pending,
                "active_by_route":[sum(model.cell_class_mass(state,l.name,k)
                          for l in model.config.links) for k in range(2)],
                "run_count":receipt["run_count"]
            })
    checkpoint=model.to_bytes(state)
    return {
        "model_id":model.model_id,"geometry":geometry,"backend":backend,
        "links":len(model.config.links),"routes":len(model.config.routes),
        "steps":steps,"dt_s":model.config.dt_s,
        "physical_lane_geometry":ledger,
        "max_abs_class_mass_error_veh":max_error,
        "max_runs":max_runs,
        "max_physical_state_scalars":model.state_scalars,
        "completion_by_route":state.completed,
        "pending_by_route":state.pending,
        "released_by_route":state.released,
        "observation_checkpoints":checkpoints,
        "total_timed_s":sum(times)/1e9,
        "median_step_us":statistics.median(times)/1e3,
        "p95_step_us":sorted(times)[int(.95*(len(times)-1))]/1e3,
        "checkpoint_bytes":len(checkpoint),
        "checkpoint_sha256":hashlib.sha256(checkpoint).hexdigest(),
        "process_peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "scope":"synthetic KCMB physical-model comparison, not true traffic measurement",
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--geometry",required=True,choices=(
        "coarse_one_lane","mixed_one_pocket","split_two_pockets"))
    parser.add_argument("--backend",required=True,choices=("python","rust"))
    parser.add_argument("--steps",type=int,default=180)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    if not 150<=args.steps<=1000:
        parser.error("bounded duration 150..1000 steps")
    result=run(args.geometry,args.backend,args.steps)
    result["python"]=platform.python_version()
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({k:result[k] for k in (
        "geometry","backend","total_timed_s","max_runs",
        "max_abs_class_mass_error_veh","completion_by_route",
        "pending_by_route")}))


if __name__=="__main__":
    main()
