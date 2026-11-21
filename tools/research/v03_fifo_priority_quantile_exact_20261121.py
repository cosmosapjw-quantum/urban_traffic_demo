#!/usr/bin/env python3
"""Exact original-physics FIFO priority-mass quantile reconstruction certificate.

This is an ideal FIFO ordered-cohort *theorem* check, NOT the V03 city driver.
Uses exact Fraction arithmetic without truncation/tolerance/seed.
"""
from __future__ import annotations
from fractions import Fraction as F
from pathlib import Path
from time import perf_counter
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[2]

def curve(rows:list[tuple[F,F,str]],q:F)->tuple[F,dict[str,F]]:
    """rows: (priority timestamp seconds, mass, destination), source FIFO order."""
    M=sum((x[1] for x in rows),F(0))
    assert 0<=q<=M and all(m>0 for _,m,_ in rows)
    assert all(rows[i][0]<=rows[i+1][0] for i in range(len(rows)-1))
    served={}
    A=F(0)
    remaining=q
    for tau,m,dest in rows:
        x=min(m,remaining)
        if x>0:
            A+=tau*x
            served[dest]=served.get(dest,F(0))+x
            remaining-=x
        if remaining==0:break
    assert remaining==0
    return A,served

def breakpoints(rows):
    cs=[F(0)]
    for _,m,_ in rows:cs.append(cs[-1]+m)
    return cs

def quantile(rows,u):
    assert 0<u<=breakpoints(rows)[-1]
    total=F(0)
    for tau,m,_ in rows:
        total+=m
        if u<=total:return tau
    raise AssertionError("quantile input outside domain")

def w1_mass(rows1,rows2):
    M=breakpoints(rows1)[-1]
    assert M==breakpoints(rows2)[-1]
    knots=sorted(set(breakpoints(rows1)+breakpoints(rows2)))
    return sum((quantile(rows1,(a+b)/2)-quantile(rows2,(a+b)/2)).__abs__()*(b-a)
               for a,b in zip(knots,knots[1:]))

def witness():
    rows=[(F(0),F(2),"a"),(F(1),F(1),"b"),(F(3),F(3),"a")]
    knots=breakpoints(rows)
    qgrid=[F(q) for q in range(7)]
    values=[curve(rows,q)[0] for q in qgrid]
    assert values==[F(0),F(0),F(0),F(1),F(4),F(7),F(10)]
    slopes=[values[i+1]-values[i] for i in range(6)]
    assert slopes==[0,0,1,3,3,3]
    assert slopes==sorted(slopes)
    for i,(tau,m,dest) in enumerate(rows):
        a,b=knots[i:i+2]
        midpoint=(a+b)/2
        # Right derivative is finite difference with no interval crossing.
        a0,_=curve(rows,a)
        ac,_=curve(rows,midpoint)
        a1,_=curve(rows,b)
        assert (ac-a0)/(midpoint-a)==tau==(a1-ac)/(b-midpoint)
        for tag in ("a","b"):
            _,fa=curve(rows,a)
            _,fb=curve(rows,b)
            assert (fb.get(tag,F(0))-fa.get(tag,F(0)))/(b-a)==int(dest==tag)
    # Equal mass and first 1 moment source witness from predecessor study.
    old=[(F(0),F(3),"a"),(F(1),F(2),"b"),(F(2),F(3),"a")]
    alt=[(F(0),F(1),"a"),(F(1),F(6),"b"),(F(2),F(1),"a")]
    assert sum(t*m for t,m,_ in old)==sum(t*m for t,m,_ in alt)==8
    assert sum(m for _,m,_ in old)==sum(m for _,m,_ in alt)==8
    assert curve(old,F(2))[0]==0 and curve(alt,F(2))[0]==1
    wass=w1_mass(old,alt)
    knot=sorted(set(breakpoints(old)+breakpoints(alt)))
    maxdelta=max(abs(curve(old,q)[0]-curve(alt,q)[0]) for q in knot)
    assert maxdelta<=wass
    # Unit stability constant is sharp, not just sufficient.
    mass=F(7,3)
    a=[(F(0),mass,"a")]
    b=[(F(5,2),mass,"a")]
    assert w1_mass(a,b)==mass*F(5,2)
    assert abs(curve(a,mass)[0]-curve(b,mass)[0])==w1_mass(a,b)
    # A alone fails to recover destination priority, but F_j(q) distinguishes.
    sameA=[(F(1),F(1),"a"),(F(1),F(1),"b")]
    swapped=[(F(1),F(1),"b"),(F(1),F(1),"a")]
    for q in [F(0),F(1,2),F(1),F(3,2),F(2)]:
        assert curve(sameA,q)[0]==curve(swapped,q)[0]
    assert curve(sameA,F(1,2))[1]!=curve(swapped,F(1,2))[1]
    return {
        "physical_priority_cohorts":[{"tau_s":str(t),"mass":str(m),"next_cell":d}
                                     for t,m,d in rows],
        "cumulative_quota_knots":[str(x) for x in knots],
        "A_vs_quota_integer_grid":[str(x) for x in values],
        "priority_derivative_slopes":[str(x) for x in slopes],
        "finite_moment_nonclosure_pair_W1":str(wass),
        "pair_full_response_max_deviation":str(maxdelta),
        "sharp_W1_bound_example":str(w1_mass(a,b)),
        "next_cell_priority_ambiguity_from_A_alone":True,
        "route_resolved_Fj_diverges_at_half_mass":True,
    }

def main():
    started=perf_counter()
    data=witness()
    src=ROOT/"crates/metroflow-rust/src/v1_road.rs"
    result={
        "schema":"METROFLOW_ORIGINAL_FIFO_PRIORITY_QUANTILE_THEORY_EXACT_20261121_V1",
        "status":"FINITE_ASSERTIONS_EXACT_RATIONAL_CHECKED",
        "source_file_sha256":hashlib.sha256(src.read_bytes()).hexdigest(),
        "source_git_HEAD_at_execution":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "domain":"finite positive chronological FIFO cohorts, priority tau_s monotone, fixed service quota q",
        "arithmetic":"Python Fraction only; no RNG or tolerance; W1 exact 1D equal-mass formula",
        "theorem":"A(q)=integral_0^q Q_mu(u)du; A convex and its slope reconstructs priority measure; with F_j(q) next-cell label ordering reconstructed; sup|A_mu-A_nu|<=W1(mu,nu), sharp",
        "finite_assertion":data,
        "compute_wall_s":perf_counter()-started,
        "nonclaims":[
            "not a proof that native Part.birth always equals chronological FIFO priority time",
            "not proof that future traffic network demand has independent fixed service quota",
            "not globally first discovery of inverse CDF integral or Kantorovich W1",
            "not evidence for a complete original V03 86400s 100k city run",
        ],
    }
    out=ROOT/"artifacts/v03_quantile_capture_20261121/R5_THEORY_EXACT_QUANTILE.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"wall_s":result["compute_wall_s"],
                     "certificate":data,"source_sha256":result["source_file_sha256"]},sort_keys=True))
if __name__=="__main__":main()
