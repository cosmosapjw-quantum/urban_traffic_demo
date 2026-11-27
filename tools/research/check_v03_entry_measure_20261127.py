"""Independent exact-rational observer and finite FIFO oracle; not Rust."""
from fractions import Fraction as F
from collections import defaultdict,deque
from itertools import combinations_with_replacement,product
import json,time
DT=F(2)
def tick(r):
    q=r/DT
    return -(-q.numerator//q.denominator)
def projected(raw):
    # Absolute consumption tick key; exact centroid in both marks.
    groups=defaultdict(lambda:[F(0),F(0),F(0)])
    for l,m,b,r in raw:
        v=groups[l,tick(r)];v[0]+=m;v[1]+=m*b;v[2]+=m*r
    return [(l,m,b/m,r/m) for (l,k),(m,b,r) in sorted(groups.items())]
def direct_boundary(raw,k):
    # Independent selection by actual clock predicate, not tick formula.
    lower=(k-1)*DT if k else F(-1)
    upper=k*DT
    result=defaultdict(lambda:[F(0),F(0)])
    for l,m,b,r in raw:
        if lower<r<=upper:
            result[l][0]+=m;result[l][1]+=m*b
    return dict(result)
def fifo(raw,caps):
    # Canonical per-tick homogeneous source packet; later packets never
    # bypass earlier ones. Within a packet serve a common mass fraction.
    queue=deque();out=[]
    for k,capacity in enumerate(caps):
        packet=direct_boundary(raw,k)
        if packet:queue.append(packet)
        served=defaultdict(lambda:[F(0),F(0)])
        while capacity and queue:
            head=queue[0];M=sum(v[0] for v in head.values())
            ratio=min(F(1),capacity/M)
            for l,(m,b) in head.items():
                served[l][0]+=ratio*m;served[l][1]+=ratio*b
                head[l]=[(1-ratio)*m,(1-ratio)*b]
            capacity-=ratio*M
            if ratio==1:queue.popleft()
        out.append((dict(served),[dict(p) for p in queue]))
    return out
atoms=[(l,F(b,2),F(r,2)) for l in (0,1) for b,r in [(0,0),(0,1),(0,3),(1,3),(1,4),(2,5),(2,8),(3,9)]]
start=time.monotonic();n=0;queries=0;fifo_cases=0
for inds in combinations_with_replacement(range(len(atoms)),3):
    for masses in product((F(1,4),F(3,4)),repeat=3):
        raw=[(atoms[i][0],m,atoms[i][1],atoms[i][2]) for i,m in zip(inds,masses)]
        reduced=projected(raw)
        assert all(b<=r and m>0 for _,m,b,r in reduced)
        for k in range(5):
            assert direct_boundary(raw,k)==direct_boundary(reduced,k)
            queries+=1
        assert fifo(raw,(F(0),F(1,2),F(1,4),F(0),F(1),F(3)))==fifo(reduced,(F(0),F(1,2),F(1,4),F(0),F(1),F(3)))
        fifo_cases+=1;n+=1
# Same tag, different readiness tick cannot be merged: first boundary changes.
raw=[(0,F(1),F(0),F(1)),(0,F(1),F(0),F(3))]
wrong=[(0,F(2),F(0),F(2))]
assert direct_boundary(raw,1)!=direct_boundary(wrong,1)
print(json.dumps(dict(status='PASS_EXACT_FINITE_ASSERTIONS',atom_types=len(atoms),three_atom_cases=n,boundary_checks=queries,fifo_cases=fifo_cases,scope='fixed dt=2, eps=0, canonical source packet and proportional FIFO service; not full MetroFlow proof or binary64 test',elapsed_s=time.monotonic()-start),indent=2))
