"""Exact Hausdorff moment bound and independent extremal reconstruction."""
from fractions import Fraction as F
import random,json
rng=random.Random(20261128)
checked=0
max_width=F(0)
for _ in range(4096):
    atoms=[(F(rng.randrange(1,17),16),F(rng.randrange(17),16)) for _ in range(rng.randrange(1,9))]
    M,J,Z,W=[sum((m*u**k for m,u in atoms),F(0)) for k in range(4)]
    if J==0:
        assert Z==W==0
        continue
    if J==M:
        assert Z==W==M
        continue
    lo=Z*Z/J
    hi=Z-(J-Z)**2/(M-J)
    a=(J-Z)/(M-J)
    b=(M-J)/(1-a)
    extremal=[(b,a),(M-b,F(1))]
    assert all(m>=0 and 0<=u<=1 for m,u in extremal)
    assert [sum(m*u**k for m,u in extremal) for k in range(4)]==[M,J,Z,hi]
    assert lo<=W<=hi
    assert hi-lo==(J-Z)*(M*Z-J*J)/(J*(M-J))
    assert hi-lo<=M/16
    max_width=max(max_width,(hi-lo)/M)
    checked+=1
M,J,Z=F(1),F(1,2),F(3,8)
assert Z-(J-Z)**2/(M-J)-Z*Z/J==M/16
print(json.dumps({"status":"PASS","generated":4096,"nondegenerate_cases":checked,"max_sample_width_per_mass":float(max_width),"scope":"sharp third moment bounds; not global transport error or FIFO theorem"},indent=2))
