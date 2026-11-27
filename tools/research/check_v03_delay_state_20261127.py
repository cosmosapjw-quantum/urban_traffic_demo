"""Independent exact-rational finite delay oracle, not production Rust."""
from fractions import Fraction as F
from random import Random
from collections import defaultdict
import json,time
DT=F(2)
def k(r):
 q=r/DT
 return -(-q.numerator//q.denominator)
def mom(rows):
 a=defaultdict(lambda:[F(0),F(0),F(0)])
 for l,m,b,r in rows:
  z=a[l];z[0]+=m;z[1]+=m*b;z[2]+=m*r
 return dict(a)
def aggregate(rows,t,horizon):
 groups=defaultdict(list);raw=[]
 for l,m,b,r in rows:
  if r<=t or r>horizon[l]:raw.append((l,m,b,r))
  else:groups[l,k(r)].append((l,m,b,r))
 for (l,j),xs in groups.items():
  M,B,R=mom(xs)[l];b=B/M;r=R/M
  assert b<=r and k(r)==j and r<=horizon[l]
  raw.append((l,M,b,r))
 return raw
def consume(rows,t):
 return [a for a in rows if a[3]<=t],[a for a in rows if a[3]>t]
def release(history,leg,u,d,start,prev):
 profile=min(F(1),max(F(0),(u-start)/8))
 E=sum((m for l,m,b,r in history if l==leg and r+d<=u),F(0))
 return max(prev,min(profile,E))
rng=Random(20261127);tests=0;steps=0;query=0;peak=0;bound_checks=0;start_time=time.monotonic()
# A dynamically changing injection stream; hidden leg 0 horizon 30,
# leg 1 horizon 40, protected leg 2 kept raw. Fixed schedule.
for case in range(240):
 raw=[];projected=[];hr=[];hp=[];prev_r=[F(0)]*3;prev_p=[F(0)]*3
 horizon=[F(30),F(40),F(-1)];dwell=[F(4),F(6),F(3)];starts=[F(34),F(46),F(0)]
 for step in range(32):
  t=DT*step
  fresh=[]
  if step<22:
   for j in range(rng.randrange(1,7)):
    l=rng.randrange(3);m=F(rng.randrange(1,8),64)
    b=t-F(rng.randrange(0,min(4,2*step)+1),2)
    r=t+F(rng.randrange(1,17),2)
    fresh.append((l,m,b,r))
  raw.extend(fresh);projected=aggregate(projected+fresh,t,horizon)
  # Every live projected group has a unique absolute retirement index,
  # restricted to the maximum 8s delay horizon (raw protected excluded).
  supported=[x for x in projected if x[3]>t and x[3]<=horizon[x[0]]]
  keys=[(x[0],k(x[3])) for x in supported]
  assert len(keys)==len(set(keys))
  assert len(keys)<=2*(8//2+2);peak=max(peak,len(keys));bound_checks+=1
  a,raw=consume(raw,t);b,projected=consume(projected,t)
  assert mom(a)==mom(b) and mom(raw)==mom(projected)
  hr.extend(a);hp.extend(b);steps+=1
  for l in range(3):
   prev_r[l]=release(hr,l,t,dwell[l],starts[l],prev_r[l])
   prev_p[l]=release(hp,l,t,dwell[l],starts[l],prev_p[l])
   assert prev_r[l]==prev_p[l];query+=1
 assert not raw and not projected
 tests+=1
# A ring residue alone aliases epochs: same modulo, different consumption.
assert 3%8==11%8 and 3!=11
print(json.dumps(dict(status="PASS_EXACT_FINITE_ASSERTIONS",seed=20261127,trajectories=tests,tick_comparisons=steps,release_queries=query,live_support_bound_checks=bound_checks,maximum_supported_live_cells=peak,scope="positive rational delay measure dt=2, max delay 8; fixed profiles and protected raw fallback; not full-city or binary64 proof",elapsed_s=time.monotonic()-start_time),indent=2))
