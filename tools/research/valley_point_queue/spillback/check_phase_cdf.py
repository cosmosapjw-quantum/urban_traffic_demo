"""Exact rational checks for the antithetic stratum and one-server cumulative bound."""
from fractions import Fraction as F
from itertools import product

def ranks(n,u):
    return [(F(j)+u)/n if j<n-1-j else
            (1-(F(n-1-j)+u)/n if j>n-1-j else F(1,2))
            for j in range(n)]

def cdf(r,x):
    return F(sum(q<=x for q in r),len(r))

checks=0
for n in range(1,33):
    for u in [F(1,19),F(7,19),F(1,2),F(18,19)]:
        r=ranks(n,u)
        assert sum(r)==F(n,2)
        assert all(F(j,n)<q<F(j+1,n) for j,q in enumerate(r))
        for x in sorted(set([F(i,73) for i in range(74)]+r)):
            assert abs(cdf(r,x)-x)<=F(1,n)
            checks+=1
# discrete cumulative analogue of min-plus constant service, arbitrary arrival steps.
def dep(A,c):
    return [min(A[j]+c*(i-j) for j in range(i+1)) for i in range(len(A))]
pairs=0
for a,b in product(product(range(3),repeat=4),repeat=2):
    A=[0]; B=[0]
    for x,y in zip(a,b): A.append(A[-1]+x);B.append(B[-1]+y)
    delta=max(abs(x-y) for x,y in zip(A,B))
    da,db=dep(A,F(3,2)),dep(B,F(3,2))
    assert max(abs(x-y) for x,y in zip(da,db))<=delta
    assert max(abs(x-d-y+e) for x,d,y,e in zip(A,da,B,db))<=2*delta
    pairs+=1
print(f"exact rational CDF evaluations={checks}; min-plus pairs={pairs}; passed")
