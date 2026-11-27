"""Independent exact-rational oracle, not the production Rust backend."""
from fractions import Fraction as F
from itertools import product, combinations_with_replacement
from collections import defaultdict
import json
import time
T, DT = F(2), F(2)
# (birth, ready): includes clamp region, current interval, future intervals,
# exact grid boundaries and half-step positions.
ATOMS = [(F(b,2),F(r,2)) for b,r in [
    (0,0),(0,1),(1,2),(2,2),(0,3),(1,4),(3,4),(4,4),
    (0,5),(1,7),(2,8),(3,9),(4,11),(4,12)]]
W=(F(1,4),F(3,4))
def key(r):
    if r<=0: return 0
    if r<=T: return 1
    q=(r-T)/DT
    return 1+(-(-q.numerator//q.denominator))
def clock(r): return max(F(0),r) if key(r)<=1 else r
def project(raw):
    cells=defaultdict(lambda:[F(0),F(0),F(0)])
    for b,r,m in raw:
        c=cells[key(r)];c[0]+=m;c[1]+=m*b;c[2]+=m*r
    return [(b/m,r/m,m) for m,b,r in cells.values()]
def moments(raw):
    cells=defaultdict(lambda:[F(0),F(0),F(0)])
    for b,r,m in raw:
        c=cells[key(r)];c[0]+=m;c[1]+=m*b;c[2]+=m*clock(r)
    return dict(cells)
def releases(raw,dwell,start):
    x=F(0);out=[]
    for u in range(0,17,2):
        profile=min(F(1),max(F(0),(F(u)-start)/4))
        eligible=sum((m for _,r,m in raw if clock(r)+dwell<=u),F(0))
        x=max(x,min(profile,eligible))
        out.append(x)
    return out
begin=time.monotonic()
tests=0;queries=0;lipschitz=0;stream=0
for inds in combinations_with_replacement(range(len(ATOMS)),3):
    for ww in product(W,repeat=3):
        raw=[(*ATOMS[i],w) for i,w in zip(inds,ww)]
        reduced=project(raw)
        assert moments(raw)==moments(reduced)
        tests+=1
        rmax=max(r for _,r,_ in raw)
        for dwell,offset in [(F(0),F(0)),(F(1),F(1)),(F(5,2),F(0))]:
            start=max(T,rmax)+dwell+offset
            assert releases(raw,dwell,start)==releases(reduced,dwell,start)
            queries+=1
        # Exact recursive sufficient statistic versus batch measure.
        M=B=F(0)
        for _,r,m in raw:
            M+=m;B+=m*clock(r)
        assert M==sum(m for _,_,m in reduced)
        assert B==sum(m*clock(r) for _,r,m in reduced)
        stream+=1
        for k in set(key(r) for _,r,_ in raw):
            cell=[(clock(r),m) for _,r,m in raw if key(r)==k]
            mass=sum(m for r,m in cell)
            avg=sum(r*m for r,m in cell)/mass
            width=max(r for r,m in cell)-min(r for r,m in cell)
            assert sum(m*abs(r-avg) for r,m in cell)<=mass*width/2
            lipschitz+=1
# Explicit failed inference when an unprotected query distinguishes members
# of the same retirement cell. Both events retire at t=2; dwell=1, u=2.
raw=[(F(0),F(1,2),F(1,2)),(F(0),F(3,2),F(1,2))]
rep=project(raw)
q=lambda rows:sum(m for _,r,m in rows if clock(r)+1<=2)
assert q(raw)==F(1,2) and q(rep)==1
print(json.dumps(dict(status="PASS_EXACT_FINITE_ASSERTIONS",positive_atoms=len(ATOMS),three_atom_mass_cases=tests,hidden_release_sequence_cases=queries,streaming_moment_cases=stream,lipschitz_cells=lipschitz,unprotected_query_counterexample={"raw":"1/2","centroid":"1"},seconds=time.monotonic()-begin,scope="rational finite test with dt=2, eps=0; proof in research note, not binary64 or full-city proof"),indent=2))
