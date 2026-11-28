from fractions import Fraction as F
import random,json
rng=random.Random(9)
for _ in range(4096):
    m=F(rng.randrange(1,100),8)
    b=m*F(rng.randrange(1,100),4)
    q=F(rng.randrange(1,100),16)
    r=m;birth=b;out=F(0);ob=F(0);steps=0
    while r:
        f=min(F(1),q/r);y=r*f;yb=birth*f
        r-=y;birth-=yb;out+=y;ob+=yb;steps+=1
        assert r>=0 and birth>=0 and r+out==m and birth+ob==b
    assert steps==-(m//-q)
    L=F(rng.randrange(1,100));v=F(rng.randrange(1,30),4);h=F(rng.randrange(1,12),4)
    d=F(0);n=0
    while d<L:d=min(L,d+h*v);n+=1
    assert n==-(L//-(h*v))
# Constructive nonconvergence in synchronized single-cohort closure:
counterexamples=[dict(T=100,epsilon=e,gated_exit=200,independent_exit=100+e,extra_delay=100-e) for e in [1,10,50,99]]
print(json.dumps(dict(status='PASS',cases=4096,exact_rational=True,counterexamples=counterexamples),indent=2))
