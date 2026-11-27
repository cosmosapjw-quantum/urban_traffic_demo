from fractions import Fraction as F
from random import Random
import struct,json,time
rng=Random(20261128);n=0;restrictions=0;bits=0
t0=time.monotonic()
for case in range(512):
 rows=[(rng.randrange(7),F(rng.randrange(1,32),32),F(rng.randrange(0,16),4)) for _ in range(rng.randrange(2,40))]
 # Each triple is key,mass,birth clock; moment=mass*clock
 a=F(rng.randrange(17),16);b=a+(1-a)*F(rng.randrange(17),16)
 for k,m,t in rows:
  M=m;B=m*t
  q=[F(0),a,b,F(1)]
  assert sum(((v-u)*M for u,v in zip(q,q[1:])),F(0))==M
  assert sum(((v-u)*B for u,v in zip(q,q[1:])),F(0))==B
  restrictions+=1
 wire=[struct.pack('<dd',float(m),float(m*t)) for _,m,t in rows]+[struct.pack('<dd',0.125,-0.0),struct.pack('<dd',0.125,0.0)]
 d=list(dict.fromkeys(wire));codes=[d.index(x) for x in wire]
 assert [d[c] for c in codes]==wire
 bits+=len(wire);n+=1
# A fixed binary64 counterexample to collapsing two multiplication factors.
x,a,b=0.1,0.1,0.3
assert struct.pack('<d',(x*a)*b)!=struct.pack('<d',x*(a*b))
print(json.dumps(dict(status='PASS_EXACT_FINITE_ASSERTIONS',seed=20261128,trajectories=n,rank_partition_checks=restrictions,ordered_bit_pairs=bits,nonassociativity_counterexample=[x,a,b,(x*a)*b,x*(a*b)],scope='finite rational uniform head rank restriction and exact Python bit dictionary; not network-wide numerical equivalence',elapsed_s=time.monotonic()-t0),indent=2))
