#!/usr/bin/env python3
"""Exact finite FIFO birth-moment closure obstruction; not a full road benchmark."""
from fractions import Fraction as Q
from math import comb
from pathlib import Path
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[2]

def moment(rows,r):
    return sum((w*(t**r if r else 1) for t,w in rows),Q(0))

def fifo_departure(rows,q):
    remaining=Q(q)
    out=[]
    for t,m in rows:
        served=min(m,remaining)
        if served>0:
            out.append((t,served))
            remaining-=served
        if remaining==0:
            break
    assert remaining==0
    return out

def exact_witness(p):
    plus=[(Q(i),Q((2+(-1)**i)*comb(p+1,i))) for i in range(p+2)]
    minus=[(Q(i),Q((2-(-1)**i)*comb(p+1,i))) for i in range(p+2)]
    equal=[moment(plus,r)==moment(minus,r) for r in range(p+1)]
    assert all(equal)
    assert all(w>0 for _,w in plus+minus)
    sp=fifo_departure(plus,Q(2))
    sm=fifo_departure(minus,Q(2))
    assert moment(sp,0)==moment(sm,0)==Q(2)
    assert moment(sp,1)==Q(0) and moment(sm,1)==Q(1)
    return {
        "p":p, "cohorts":p+2,
        "plus_masses":[str(w) for _,w in plus],
        "minus_masses":[str(w) for _,w in minus],
        "first_p_moments_exactly_equal":equal,
        "total_mass":str(moment(plus,0)),
        "fifo_served_mass":str(moment(sp,0)),
        "fifo_served_birth_moment_plus":str(moment(sp,1)),
        "fifo_served_birth_moment_minus":str(moment(sm,1)),
    }

def rank(matrix):
    a=[[Q(x) for x in row] for row in matrix]
    rows=len(a);cols=len(a[0]);r=0
    for j in range(cols):
        i=next((i for i in range(r,rows) if a[i][j]),None)
        if i is None:continue
        a[r],a[i]=a[i],a[r]
        pivot=a[r][j]
        a[r]=[x/pivot for x in a[r]]
        for k in range(rows):
            if k!=r:
                factor=a[k][j]
                a[k]=[x-factor*y for x,y in zip(a[k],a[r])]
        r+=1
        if r==rows:break
    return r

def main():
    cases=[exact_witness(p) for p in range(0,11)]
    ranks=[]
    for j in range(2,8):
        # Independent coordinates e_k-e_0 span fixed-total H_0.
        basis=[[int(k==i)-int(k==0) for i in range(j)] for k in range(1,j)]
        outgoing=list(map(list,zip(*basis)))
        assert rank(outgoing)==j-1
        assert rank([[1]*j])==1
        ranks.append({"destinations":j,"rank_destination_flux_on_fixed_mass":j-1,
                      "rank_total_only":1})
    source=ROOT/"crates/metroflow-rust/src/v1_road.rs"
    result={
        "schema":"METROFLOW_FIFO_MOMENT_NONCLOSURE_EXACT_20261121_V1",
        "domain":"ideal chronological FIFO, nonnegative finite cohorts, first p polynomial moments",
        "arithmetic":"Python Fraction exact rational; no random sampling or floating tolerance",
        "source_road_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "moment_witnesses":cases,
        "rank_lower_bounds":ranks,
        "theorem_status":"PROVED_BY_FINITE_DIFFERENCES_UNIFORMLY_IN_ALL_P",
        "finite_assertion_status":"CHECKED_P_0_TO_10_AND_J_2_TO_7",
        "nonclaims":["not proof of globally novel mathematical result","not full original V03 100k physical acceptance",
                     "not proof against every nonlinear state encoding","not statement that existing native drops FIFO history"],
    }
    target=ROOT/"artifacts/v03_fifo_closure_20261121/THEORY_EXACT_WITNESSES.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"witnesses":len(cases),"ranks":ranks,
      "p1":cases[1],"source_sha256":result["source_road_sha256"]},sort_keys=True))
if __name__=="__main__":main()
