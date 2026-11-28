"""Exact-rational verification of a local adaptive rank-bin error bound.
This is an independent theory oracle, not a physical solver or acceptance test.
"""
from fractions import Fraction as F
from itertools import product
import json,random

def verify(widths,densities):
    h=sum(widths);mass=sum(w*r for w,r in zip(widths,densities))
    mean=mass/h;span=max(densities)-min(densities)
    t=e=F(0);maxerr=F(0)
    for w,r in zip(widths,densities):
        t+=w;e+=(r-mean)*w
        maxerr=max(maxerr,abs(e))
        assert abs(e)<=h*span/4
        assert abs(e)<=mass
    assert e==0
    return maxerr,h*span/4

count=0;checks=0
for r in product(map(F,range(5)),repeat=5):
    verify([F(1,5)]*5,r);count+=1;checks+=5
rng=random.Random(20261128)
for _ in range(4096):
    n=rng.randrange(2,24)
    widths=[F(rng.randrange(1,15),16) for _ in range(n)]
    density=[F(rng.randrange(0,50),16) for _ in range(n)]
    verify(widths,density);count+=1;checks+=n
err,bound=verify([F(1,2),F(1,2)],[F(0),F(2)])
assert err==bound==F(1,2)
# Adaptive bins: accept a block only when the certified local
# mass-prefix error is within a prescribed veh tolerance.
widths=[F(1,8)]*64
density=[F(1)]*24+[F(3,2)]*16+[F(2)]*24
threshold=F(1,64)
def partition(l,r):
    err,b=verify(widths[l:r],density[l:r])
    if b<=threshold or r-l==1:return [(l,r,b,err)]
    mid=(l+r)//2
    return partition(l,mid)+partition(mid,r)
bins=partition(0,len(widths))
assert all(b<=threshold and err<=b for _,_,b,err in bins)
assert sum(sum(w*r for w,r in zip(widths[l:h],density[l:h])) for l,h,_,_ in bins)==sum(w*r for w,r in zip(widths,density))
print(json.dumps(dict(status='PASS',seed=20261128,exact_fraction_cases=count,prefix_endpoint_checks=checks,sharp_example=dict(error=str(err),bound=str(bound)),adaptive_example=dict(raw_cells=len(widths),retained_bins=len(bins),local_prefix_tolerance_veh=str(threshold),max_certified_error_veh=str(max(b for _,_,b,_ in bins))),scope='nonnegative piecewise constant density local rank/admission bins; integral conservation and prefix error; no global junction or binary64 equivalence claim'),indent=2))
