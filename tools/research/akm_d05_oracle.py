from fractions import Fraction as F
import math,json,random
rng=random.Random(20261128)
def solve(p,s,C,S,E,R):
    # p = (donor,receiver,amount,footprint) receiver=-1 outlet
    def ratios(rows,src,c,b):
        d=[F(0)]*R;w=d.copy()
        for e,j,m,l in rows:
            if j>=0:d[j]+=m;w[j]+=m*l
        for j,m,l in src:d[j]+=m;w[j]+=m*l
        return [min(F(1),c[j]/d[j] if d[j] else F(1),b[j]/w[j] if w[j] else F(1)) for j in range(R)]
    def donors(rows,r,enabled):
        f=[F(1) if en else F(0) for en in enabled]
        for e,j,m,l in rows:
            if j>=0 and m>0:f[e]=min(f[e],r[j])
        return f
    def usage(rows,src,f,g):
        c=[F(0)]*R;b=c.copy()
        for e,j,m,l in rows:
            if j>=0:c[j]+=m*f[e];b[j]+=m*f[e]*l
        for j,m,l in src:c[j]+=m*g[j];b[j]+=m*g[j]*l
        return c,b
    g=ratios(p,s,C,S);f=donors(p,g,[True]*E)
    c,b=usage(p,s,f,g);rc=[x-y for x,y in zip(C,c)];rs=[x-y for x,y in zip(S,b)]
    assert min(rc+rs)>=0
    rem=[(e,j,m*(1-f[e]),l) for e,j,m,l in p]
    src=[(j,m*(1-g[j]),l) for j,m,l in s]
    en=[True]*E
    for e,j,m,l in rem:
        if j>=0 and m>0 and (rc[j]==0 or rs[j]==0):en[e]=False
    rem=[(e,j,m if en[e] else F(0),l) for e,j,m,l in rem]
    r=ratios(rem,src,rc,rs);df=donors(rem,r,en)
    ff=[x+(1-x)*y for x,y in zip(f,df)];gg=[x+(1-x)*y for x,y in zip(g,r)]
    c2,b2=usage(p,s,ff,gg)
    assert all(x<=y<=z for x,y,z in zip(c,c2,C)) and all(x<=y<=z for x,y,z in zip(b,b2,S))
    assert all(x<=y<=1 for x,y in zip(f,ff)) and all(x<=y<=1 for x,y in zip(g,gg))
    return f,ff,g,gg
improved=0
for _ in range(2048):
    E,R=3,4
    p=[(e,rng.randrange(-1,R),F(rng.randrange(9),4),F(rng.randrange(1,6))) for e in range(E) for _ in range(3)]
    s=[(j,F(rng.randrange(9),4),F(rng.randrange(1,6))) for j in range(R)]
    C=[F(rng.randrange(9),4) for _ in range(R)];S=[F(rng.randrange(17),2) for _ in range(R)]
    f,ff,g,gg=solve(p,s,C,S,E,R);improved+=int(f!=ff or g!=gg)
p=[(0,0,F(1),F(5)),(0,1,F(1),F(5)),(1,1,F(1),F(5))]
f,ff,_,_=solve(p,[],[F(0),F(1)],[F(0),F(5)],2,2)
assert f==[0,F(1,2)] and ff==[0,1]
# Independent integration with midpoint sums for frozen affine drift;
# all variables normalized except distance U*h [m].
err=0.
for _ in range(128):
    u,q,p=[rng.random() for _ in range(3)]
    h=0.1+10*rng.random();tau=0.2+5*rng.random()
    A=-tau*math.expm1(-h/tau);D=u*A+q*p*(h-A)
    ref=sum((u*math.exp(-(i+.5)*h/4096/tau)+q*p*(-math.expm1(-(i+.5)*h/4096/tau))) for i in range(4096))*h/4096
    assert 0<=D<=h
    err=max(err,abs(ref-D))
assert err<1e-6
print(json.dumps(dict(status='PASS',rational_allocation_cases=2048,improved_cases=improved,blocked_donor_control=[str(x) for x in ff],distance_cases=128,max_midpoint_error_s=err),indent=2))
