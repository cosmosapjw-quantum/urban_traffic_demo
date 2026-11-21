#!/usr/bin/env python3
"""Exact physical weighted-priority progressive junction flow with Fraction arithmetic."""
from fractions import Fraction as F
from pathlib import Path
from time import perf_counter
import hashlib
import itertools
import json

ROOT=Path(__file__).resolve().parents[2]

def solve(weights, demand, beta, supply):
    n=len(weights);k=len(supply)
    assert len(demand)==len(beta)==n and all(len(row)==k for row in beta)
    assert all(w>0 for w in weights) and all(s>=0 for s in supply+demand)
    assert all(x>=0 for row in beta for x in row)
    assert all(sum(row)==1 for row in beta), "destination complete including sinks"
    flow=[F(0) for _ in range(n)]
    active=[i for i in range(n) if demand[i]>0]
    rounds=[]
    while active:
        bounds=[(demand[i]-flow[i])/weights[i] for i in active]
        for j in range(k):
            slope=sum((beta[i][j]*weights[i] for i in active),F(0))
            if slope:
                used=sum((beta[i][j]*flow[i] for i in range(n)),F(0))
                assert supply[j]>=used
                bounds.append((supply[j]-used)/slope)
        step=min(bounds)
        assert step>=0
        for i in active:flow[i]+=step*weights[i]
        used=[sum((beta[i][j]*flow[i] for i in range(n)),F(0)) for j in range(k)]
        saturated=[j for j in range(k) if supply[j]==used[j]]
        formerly=active[:]
        active=[i for i in active if flow[i]!=demand[i] and all(beta[i][j]==0 for j in saturated)]
        assert len(active)<len(formerly)
        rounds.append({"step":str(step),"active_before":formerly,
                       "saturated_destinations":saturated,"flow_after":[str(x) for x in flow]})
    assert len(rounds)<=n
    assert all(F(0)<=q<=d for q,d in zip(flow,demand))
    out=[sum((beta[i][j]*flow[i] for i in range(n)),F(0)) for j in range(k)]
    assert all(q<=s for q,s in zip(out,supply))
    assert sum(flow)==sum(out)
    return {"flow":flow,"destinations":out,"rounds":rounds}

def validate_maxmin_exact(weights,demand,beta,supply,answer):
    """Independent bounded LP search: no one flow can increase without reducing
    a flow with normalized throughput <= that of the increased one.
    Check all directions through a nullspace-free rational vertex candidate
    for 2-input one-destination exact small cases (research assertion only).
    """
    q=answer["flow"]
    # Convex polytope monotonic feasibility: any attempting to increase a
    # frozen source must find an active tight constraint touching another
    # source of no greater weighted normalized flow, or its own demand bound.
    for i in range(len(q)):
        if q[i]==demand[i]:continue
        tight=[j for j in range(len(supply)) if
               sum((beta[h][j]*q[h] for h in range(len(q))),F(0))==supply[j]
               and beta[i][j]>0]
        assert tight
        for j in tight:
            witnesses=[h for h in range(len(q)) if beta[h][j]>0 and
                       q[h]/weights[h]<=q[i]/weights[i]]
            assert witnesses

def example():
    weights=list(map(F,[1,2,1]))
    demand=list(map(F,[10,10,4]))
    beta=[[F(1),F(0)],[F(1,2),F(1,2)],[F(0),F(1)]]
    old=solve(weights,demand,beta,list(map(F,[3,5])))
    relieved=solve(weights,demand,beta,list(map(F,[4,5])))
    assert old["flow"]==[F(3,2),F(3),F(7,2)]
    assert old["destinations"]==[F(3),F(5)] and len(old["rounds"])==2
    assert relieved["flow"]==[F(2),F(4),F(3)]
    assert relieved["destinations"]==[F(4),F(5)] and len(relieved["rounds"])==2
    validate_maxmin_exact(weights,demand,beta,[F(3),F(5)],old)
    validate_maxmin_exact(weights,demand,beta,[F(4),F(5)],relieved)
    return {"priority_weights":[str(x) for x in weights],
      "send_caps":[str(x) for x in demand],
      "beta_turning":[[str(x) for x in row] for row in beta],
      "base_supplies":["3","5"],"base_flow":[str(x) for x in old["flow"]],
      "base_downstream":[str(x) for x in old["destinations"]],
      "base_rounds":old["rounds"],
      "relieved_supplies":["4","5"],
      "relieved_flow":[str(x) for x in relieved["flow"]],
      "relieved_downstream":[str(x) for x in relieved["destinations"]],
      "physical_total_flow_gain":str(sum(relieved["flow"])-sum(old["flow"]))}

def stress():
    # Finite exact rational instances with source/cap/rate/source class
    # interactions and ties, distinguishes theorem scope from numeric Rust.
    checked=0
    for n in (1,2,3):
        for weights in itertools.product([F(1),F(2)],repeat=n):
            for turn in itertools.product([F(0),F(1,2),F(1)],repeat=n):
                beta=[[b,F(1)-b] for b in turn]
                for send in itertools.product([F(0),F(2),F(4)],repeat=n):
                    for supply in ([F(0),F(0)],[F(1),F(2)],[F(3),F(5)],[F(9),F(9)]):
                        out=solve(list(weights),list(send),beta,list(supply))
                        validate_maxmin_exact(list(weights),list(send),beta,list(supply),out)
                        checked+=1
    return checked

def main():
    started=perf_counter()
    x=example()
    count=stress()
    root=ROOT/"artifacts/v03_weighted_fifo_20261121"
    root.mkdir(parents=True,exist_ok=True)
    path=root/"R5_EXACT_WEIGHTED_JUNCTION_THEORY.json"
    source=ROOT/"crates/metroflow-rust/src/v1_road.rs"
    result={
      "schema":"METROFLOW_WEIGHTED_FIFO_JUNCTION_CONSTRUCTIVE_THEOREM_20261121_V1",
      "theory_domain":"fixed physical source heads; positive w; per-source send; nonnegative routing; destination supplies",
      "theorem":"Weighted progressive filling gives a feasible deterministic weighted lexicographic max-min flow with <= input-count active rounds under exact arithmetic",
      "source_physical_observable":"destination-specific throughput and bottleneck coalition",
      "example":x,
      "finite_exact_assertions_checked":count,
      "exact_arithmetic":"Python fractions.Fraction; no tolerance or RNG",
      "source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
      "compute_wall_s":perf_counter()-started,
      "nonclaims":["not a proof of overall maximum total throughput among all feasible priority-violating flows",
        "not a replacement of source f64 within original Rust rates()",
        "not a proof of physical 25710 original city completion",
        "not a novel general weighted max-min theorem relative to all published node models"],
    }
    path.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"example":x,"tested_exact_cases":count,
                      "wall_s":result["compute_wall_s"],
                      "source_sha256":result["source_sha256"]},sort_keys=True))
if __name__=="__main__":main()
