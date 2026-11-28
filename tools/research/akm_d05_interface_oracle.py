from fractions import Fraction as F
import random,json
rng=random.Random(20261128)
maxsteps=0;strict=0;compete=0
for _ in range(1024):
 m=F(rng.randrange(1,5),2);ell=F(rng.randrange(4,16));L=F(100);w=F(5);c=F(rng.randrange(1,9),4);h=F(rng.randrange(1,9),4)
 free=ell*m+F(rng.randrange(1,81));r=min(c,w*(free-ell*m)/(L*ell));a=F(0);n=0
 while a<m:
  q=min(m-a,c*h,w*h*(free-ell*a)/(L*ell));assert q>0
  assert q<=c*h and q*ell<=w*h*(free-ell*a)/L
  upstream=m-a;down=a;a+=q
  assert (upstream-q)+(down+q)==m and ell*a<=free
  n+=1;assert n*h<=m/r+h
 maxsteps=max(maxsteps,n);strict+=1
# fixed positive supply, deterministic priority with two classes and one receiver
for _ in range(1024):
 cap=F(rng.randrange(17),8);space=F(rng.randrange(65),4)
 demands=[F(rng.randrange(1,13),8) for _ in range(3)];lengths=[F(12),F(5),F(10)]
 initial_cap,initial_space=cap,space;used=F(0);metres=F(0)
 for m,ell in zip(demands,lengths):
  z=min(m,cap,space/ell);assert 0<=z<=m
  cap-=z;space-=z*ell;used+=z;metres+=z*ell
 assert 0<=cap and 0<=space and used+cap==initial_cap and metres+space==initial_space
 compete+=1
m=F(1);a=F(0);h=F(1,2);w=F(5);L=F(100);r=h*w/L
for n in range(1,129):
 a+=r*(m-a)
 assert a==m*(1-(1-r)**n)<m
print(json.dumps(dict(status='PASS',strict_slack_cases=strict,max_steps=maxsteps,competing_quota_cases=compete,exact_slack_steps=128,exact_slack_remaining=float(1-a)),indent=2))
