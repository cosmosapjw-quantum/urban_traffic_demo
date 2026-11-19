#!/usr/bin/env python3
"""Explicit order-information and bounded-resource KCMB FIFO research probes.

All inputs are synthetic; the original MetroFlow V1 physical model differs.
No field-data or full 24h vehicle-runtime claims are supported.
"""
from __future__ import annotations

from argparse import ArgumentParser
from hashlib import sha256
import json
import platform
import resource
import statistics
from pathlib import Path
from time import perf_counter_ns

from metroflow.v1.kcmb import KCMBClass
from metroflow.v1.kcmb_network import KCMBLink, KCMBRoute, KCMBNetworkConfig, KCMBBoundedNetwork
from metroflow.v1.kcmb_ordered_fifo import OrderedKCMBBoundedNetwork


def test_model(length=20.,dt=.5,capacity=2.,backend="python",max_runs=1500):
    c=KCMBClass("car",10.,5.,.2,0.,1.,
                source_p=1.,source_speed_fraction=1.)
    links=(
        KCMBLink("in","O","J",length,1,capacity,5.),
        KCMBLink("Aroad","J","Aend",length,1,capacity,5.),
        KCMBLink("Broad","J","Bend",length,1,capacity,5.),
    )
    routes=(KCMBRoute("A",c,("in","Aroad")),
            KCMBRoute("B",c,("in","Broad")))
    cfg=KCMBNetworkConfig(links,routes,dt)
    return OrderedKCMBBoundedNetwork(cfg,backend=backend,max_runs=max_runs)


def case_counterexample():
    gate={("in","Aroad"):0.,("in","Broad"):1.}
    orderings=(("A","B"),("B","A"))
    ordered=test_model()
    def outcome(seq):
        state=ordered.initial_profile({"in":(1.,1.)},
            order_by_link={"in":tuple((n,1.) for n in seq)})
        after,event=ordered.step(state,(0.,0.),gates=gate)
        return {
            "initial_six_moment_digest":sha256(repr(state.moments).encode()).hexdigest(),
            "B_departed_veh":event["turn_flows"].get(("in","Broad","B"),0.),
            "A_departed_veh":event["turn_flows"].get(("in","Aroad","A"),0.),
            "run_count":event["run_count"],
            "mass_error_veh":event["mass_error_max_veh"],
        }
    values={"_".join(seq):outcome(seq) for seq in orderings}
    # Compare two existing fixed-moment choices at SAME total inventory.
    bulk={}
    for policy in ("shared_head","independent_turn"):
        obj=KCMBBoundedNetwork(KCMBNetworkConfig(ordered.config.links,
            ordered.config.routes,ordered.config.dt_s,lane_policy=policy))
        state=obj.initial_profile({"in":(1.,1.)})
        _,event=obj.step(state,(0.,0.),gates=gate)
        bulk[policy]=event["turn_flows"].get(("in","Broad","B"),0.)
    values["bulk_models_B_departed_veh"]=bulk
    assert values["A_B"]["B_departed_veh"]==0.
    assert values["B_A"]["B_departed_veh"]>0.
    assert values["A_B"]["initial_six_moment_digest"]==values["B_A"]["initial_six_moment_digest"]
    return values


def case_runs(n,backend,steps):
    if n>2000:
        raise ValueError("experiment max runs")
    model=test_model(length=100.,dt=1.,capacity=20.,backend=backend,max_runs=2100)
    # All 500 packets in the heterogeneous experiment carry the same numeric
    # total; the sequence alternates every 0.02 vehicles, with identical v.
    if n==1:
        order=(("A",10.),)
        totals=(10.,0.)
    else:
        assert n%2==0
        order=tuple(("A" if i%2==0 else "B",10./n) for i in range(n))
        totals=(5.,5.)
    initial=model.initial_profile({"in":totals},order_by_link={"in":order})
    state=initial
    durations=[]
    receipts=[]
    for _ in range(steps):
        start=perf_counter_ns()
        state,rc=model.step(state,(0.,0.))
        durations.append(perf_counter_ns()-start)
        receipts.append(rc)
    assert state.released==initial.released
    assert all(abs(x)<1e-8 for x in [rc["mass_error_max_veh"] for rc in receipts])
    return {
        "initial_runs":len(initial.runs[0]),
        "final_runs":sum(len(q) for q in state.runs),
        "backend":backend,"number_initial_fragments":n,"steps":steps,
        "first_step_turn_mass_veh":sum(receipts[0]["turn_flows"].values()),
        "per_step_numerical_roundoff_charge_veh":[r["numerical_completion_charge_veh"]
                                                   for r in receipts],
        "per_step_run_count":[r["run_count"] for r in receipts],
        "state_scalar_capacity":model.state_scalars,
        "max_run_state_scalars":3*model.max_runs,
        "step_us": [v/1000 for v in durations],
        "median_step_us": statistics.median(v/1000 for v in durations),
        "max_mass_residual_veh":max(r["mass_error_max_veh"] for r in receipts),
        "process_peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }


def main():
    parser=ArgumentParser()
    parser.add_argument("--output",required=True)
    parser.add_argument("--backend",choices=("python","rust"),default="python")
    parser.add_argument("--steps",type=int,default=4)
    args=parser.parse_args()
    if not 1<=args.steps<=40:
        parser.error("bounded steps 1..40")
    result={
        "source":"synthetic KCMB route FIFO; not observational or original V03 run",
        "python":platform.python_version(),
        "backend":args.backend,
        "fifo_ambiguity":case_counterexample(),
        "scaling": [case_runs(n,args.backend,args.steps) for n in (1,100,500)],
        "admission_scope":"route head order, not within-tick arrivals or full microscopic FIFO",
    }
    dest=Path(args.output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
        "backend":args.backend,
        "ambiguity": {k:v["B_departed_veh"] for k,v in result["fifo_ambiguity"].items()
                      if isinstance(v,dict) and "B_departed_veh" in v},
        "cases":[(s["number_initial_fragments"],s["final_runs"],
                  round(s["median_step_us"],2))
                 for s in result["scaling"]]
    }))


if __name__=="__main__":
    main()
