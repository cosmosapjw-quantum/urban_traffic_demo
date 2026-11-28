from fractions import Fraction as F
import cmath,math,json,random
rng=random.Random(20261128)
count=0
for i in range(1,21):
 l=F(i,20)
 for j in range(81):
  g=F(j,10);b=l*g
  # exclude exact unit-circle boundary from numerical classification
  z=(float(1-l)+cmath.sqrt(float((1-l)**2-4*b)))/2
  w=(float(1-l)-cmath.sqrt(float((1-l)**2-4*b)))/2
  if b!=1:assert (max(abs(z),abs(w))<1)==(b<1)
  count+=1
def prob(c,s,t):
 v=[math.log(x)-y/t for x,y in zip(s,c)];m=max(v);v=[math.exp(x-m) for x in v];z=sum(v);return [x/z for x in v]
for _ in range(2048):
 k=rng.randrange(2,9);c=[rng.uniform(0,120) for _ in range(k)];s=[rng.uniform(.1,1) for _ in range(k)]
 t=rng.uniform(3,50);e=rng.uniform(0,30);d=[rng.uniform(-e,e) for _ in c]
 p,q=prob(c,s,t),prob([x+y for x,y in zip(c,d)],s,t)
 assert .5*sum(abs(x-y) for x,y in zip(p,q))<=min(1,e/(2*t))+1e-12
print(json.dumps(dict(status='PASS',linear_cases=count,logit_cases=2048,scope='fixed candidate set local response, no network stability theorem'),indent=2))
