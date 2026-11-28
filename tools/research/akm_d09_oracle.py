from fractions import Fraction as F
import random,json
rng=random.Random(20261128)
for _ in range(2048):
    # distinct units stay independent; parent fraction only
    U=[];done=[]
    for i in range(16):
        f=F(rng.randrange(9),8);s=F(rng.randrange(9),8)
        p=rng.randrange(i) if i and rng.randrange(2) else None
        u=min(f,s,U[p] if p is not None else F(1))
        c=min(f,s,done[p] if p is not None else F(1))*F(rng.randrange(9),8)
        a=F(rng.randrange(1,100),8)
        assert 0<=c<=u<=f and a*(f-c)>=a*(f-u)
        U.append(u);done.append(c)
for _ in range(2048):
    k=rng.randrange(20);h=F(rng.randrange(1,11))
    rows=[(F(rng.randrange(1,17),8),(k+F(rng.randrange(1,17),16))*h,F(rng.randrange(17),16)*k*h) for _ in range(rng.randrange(1,16))]
    m=sum(x[0] for x in rows);r=sum(x[0]*x[1] for x in rows)/m;b=sum(x[0]*x[2] for x in rows)/m
    assert k*h<r<=(k+1)*h and 0<=b<=r
    for cut in [k*h,(k+1)*h]:
        assert sum(x[0] for x in rows if x[1]<=cut)==(m if r<=cut else 0)
    assert sum(x[0]*abs(x[1]-r) for x in rows)<=m*h
    assert m*r==sum(x[0]*x[1] for x in rows) and m*b==sum(x[0]*x[2] for x in rows)
print(json.dumps(dict(status="PASS",support_cases=2048,legs_per_case=16,clock_cell_cases=2048,scope="exact rational arithmetic only"),indent=2))
