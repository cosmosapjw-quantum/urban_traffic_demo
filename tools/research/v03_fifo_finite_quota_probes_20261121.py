#!/usr/bin/env python3
"""Exact finite quota-probe non-identifiability for ideal chronological FIFO."""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import subprocess
from tools.research.v03_fifo_priority_quantile_exact_20261121 import curve,w1_mass

ROOT=Path(__file__).resolve().parents[2]

def finite_probe_witness(knots:list[F]):
    assert len(knots)>=2 and knots[0]==0 and all(
        knots[i]<knots[i+1] for i in range(len(knots)-1)
    )
    # Any finite probe grid has a positive open mass gap. Place an exact
    # zero-mean signed priority perturbation inside that gap.
    target=max(range(len(knots)-1), key=lambda i:knots[i+1]-knots[i])
    left,right=knots[target:target+2]
    length=right-left
    baseline=[]
    perturbed=[]
    for i,(a,b) in enumerate(zip(knots,knots[1:])):
        m=b-a
        if i<target:
            baseline.append((F(0),m,"a"))
            perturbed.append((F(0),m,"a"))
        elif i==target:
            baseline.append((F(2),m,"a"))
            perturbed.extend([(F(1),m/2,"a"),(F(3),m/2,"a")])
        else:
            baseline.append((F(4),m,"a"))
            perturbed.append((F(4),m,"a"))
    assert all(curve(baseline,q)==curve(perturbed,q) for q in knots)
    interior=left+length/4
    deviation=abs(curve(baseline,interior)[0]-curve(perturbed,interior)[0])
    assert deviation==length/4 and deviation>0
    w1=w1_mass(baseline,perturbed)
    assert w1==length and deviation<=w1
    assert sum(x[1] for x in baseline)==sum(x[1] for x in perturbed)==knots[-1]
    return {
      "probe_quota_knots":[str(q) for q in knots],
      "ambiguous_gap":[str(left),str(right)],
      "baseline":[[str(t),str(m),label] for t,m,label in baseline],
      "counterexample":[[str(t),str(m),label] for t,m,label in perturbed],
      "all_sampled_A_and_F_identical":True,
      "interior_quota":str(interior),
      "strict_interior_A_difference":str(deviation),
      "W1_exact":str(w1),
      "no_probed_quantity_replaced_by_approximation":True,
    }

def main():
    probes=[
       [F(0),F(1)],
       [F(0),F(1,3),F(2,3),F(1)],
       [F(0),F(2),F(5),F(8)],
       [F(0),F(1,5),F(7,5),F(13,5),F(3)],
       [F(0),F(1,7),F(2,7),F(3,7),F(4,7),F(5,7),F(6,7),F(1)],
    ]
    evidence=[finite_probe_witness(k) for k in probes]
    road=ROOT/"crates/metroflow-rust/src/v1_road.rs"
    result={
      "schema":"METROFLOW_FIFO_QUOTA_FINITE_SAMPLING_OBSTRUCTION_20261121_V1",
      "status":"CONSTRUCTIVE_PROOF_WITH_EXACT_FINITE_WITNESSES",
      "claim":"Any finite set of service quotas, even with full sampled next-cell F_j values, cannot identify arbitrary nonnegative chronological FIFO priority-cohort distributions; all-q A is complete",
      "domain":"finite strictly increasing mass quota samples 0=q0<...<qL=M, exact FIFO; no upper bound on number of cohorts",
      "constructive_proof":"Change one open quota gap: constant priority tau=2 versus equal masses at tau=1 and tau=3; choose priority 0 before and 4 after. Integral unchanged on every sampled boundary, different on interior.",
      "fraction_cases":evidence,
      "source_road_sha256":hashlib.sha256(road.read_bytes()).hexdigest(),
      "source_git_HEAD":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
      "arithmetic":"exact rational Fraction",
      "nonclaims":["not a proof that infinite-memory numerical implementation is required",
                   "not a world-first result in inverse distribution theory",
                   "not equivalent to original native network-wide FIFO without sector assumptions",
                   "not a simulation of one whole original 100k city day"],
    }
    out=ROOT/"artifacts/v03_quantile_capture_20261121/R8_THEORY_FINITE_QUOTA_PROBES.json"
    out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":result["status"],
       "cases":len(evidence),
       "first":evidence[0],
       "last":evidence[-1],
       "road_sha256":result["source_road_sha256"]},sort_keys=True))
if __name__=="__main__":main()
