from fractions import Fraction as F
import random,cmath,json
rng=random.Random(20261128)
for _ in range(2048):
 h=rng.randrange(1,500);p=rng.randrange(h+1);q=rng.randrange(100);initial=p+q;total=0
 for k in range(3):
  i=rng.randrange(50);c=rng.randrange(50);total+=i;h+=c
  x=min(q+i,h-p) if rng.randrange(2) else 0
  p+=x;q+=i-x
  assert p+q==initial+total and 0<=p<=h and q>=0
  jobs=rng.randrange(500);n=min(p,jobs)
  assert n+(p-n)==p
for n in range(1,301):
 births=[600*i//n for i in range(n)]
 assert len(set(births))==n and min(births)==0 and max(births)<600
 done=[b+rng.randrange(1,1000) for b in births];t=rng.randrange(600,1801)
 assert sum(sum(b<=s<d for b,d in zip(births,done)) for s in range(t))==sum(min(t,d)-b for b,d in zip(births,done))
count=0
for i in range(1,20):
 a=F(i,20)
 for j in range(81):
  bc=F(j,20);x=float(1-a);w=cmath.sqrt(x*x-4*float(bc))
  if bc!=1:assert (max(abs((x+w)/2),abs((x-w)/2))<1)==(bc<1)
  count+=1
print(json.dumps(dict(status="PASS",growth_ledger_cases=2048,three_updates_per_case=True,schedule_and_exposure_cases=300,linear_cases=count,scope="arithmetic and smooth surrogate only"),indent=2))
