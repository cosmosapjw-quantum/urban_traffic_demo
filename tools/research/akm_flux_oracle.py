"""Independent finite exact checks of velocity flux and mixed residence law."""
from fractions import Fraction as F
import math, json, random
rng=random.Random(20261128);count=0
for _ in range(2048):
    rows=[(F(rng.randrange(1,20),16),F(rng.randrange(17),16)) for i in range(rng.randrange(1,10))]
    m,j,z,w=[sum((a*u**k for a,u in rows),F()) for k in range(4)]
    if j:
        assert z*z<=j*w
        v=z/j;b=j*j/z;atoms=[(m-b,F(0)),(b,v)]
    else:
        atoms=[(m,F(0))]
    assert all(a>=0 and 0<=u<=1 for a,u in atoms)
    assert [sum(a*u**k for a,u in atoms) for k in range(3)]==[m,j,z]
    for c in map(F,['0','1/4','1/2','1']):
        y=[sum(a*(c*u)*u**k for a,u in atoms) for k in range(3)]
        x=[sum(a*(1-c*u)*u**k for a,u in atoms) for k in range(3)]
        assert y[0]==c*j and y[1]==c*z
        for q in (x,y):
            assert 0<=q[2]<=q[1]<=q[0] and q[1]**2<=q[0]*q[2]
        assert [a+b for a,b in zip(x,y)]==[m,j,z]
        assert y[1]-c*j*j/m==c*(z-j*j/m)
        count+=1
# independent negative-binomial distribution finite sums, truncated tail
res=[]
for k in [1,2,4,8]:
 for a in [1,.5,.25,.125]:
    dt=10*a/k
    if a==1: mean,var=10.,0.
    else:
        probs=[(n*dt,math.comb(n-1,k-1)*a**k*(1-a)**(n-k)) for n in range(k,4096)]
        assert abs(sum(p for t,p in probs)-1)<1e-12
        mean=sum(t*p for t,p in probs);var=sum((t-mean)**2*p for t,p in probs)
    assert abs(mean-10)<1e-10 and abs(var-100*(1-a)/k)<1e-9
    res.append(dict(cells=k,cfl=a,mean_s=mean,variance_s2=var))
print(json.dumps(dict(status='PASS',atom_cases=2048,flux_cases=count,residence_cases=res,scope='exact rational quadrature and finite tail-summed negative binomial; not global traffic equivalence'),indent=2))
