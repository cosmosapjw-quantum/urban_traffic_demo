"""Independent exact-rational pushforward and conditional-mean checks.
Python is explicitly an independent scientific oracle, not a backend."""
from fractions import Fraction as F
import random, math, json
rng=random.Random(20261128)
def moments(rows):
    return tuple(sum((m*u**k for m,s,u in rows if s==sigma),F()) for k in range(3) for sigma in (0,1))
def mat_switch(y,p01,p10):
    return tuple(v for k in range(0,6,2) for v in ((1-p01)*y[k]+p10*y[k+1],p01*y[k]+(1-p10)*y[k+1]))
def atom_switch(rows,p01,p10):
    return [(m*f,s2,u) for m,s,u in rows for s2,f in ((s,1-(p01 if s==0 else p10)),(1-s,p01 if s==0 else p10))]
def mat_drift(y,a,target):
    b=(1-a)*target
    return y[:2]+(a*y[2],a*y[3]+b*y[1],a*a*y[4],a*a*y[5]+2*a*b*y[3]+b*b*y[1])
checks=0;flux_checks=0
for _ in range(1024):
    rows=[(F(rng.randrange(1,20),16),rng.randrange(2),F(rng.randrange(17),16)) for i in range(rng.randrange(1,10))]
    p01,p10,a,target=[F(rng.randrange(17),16) for i in range(4)]
    y=moments(rows);sw=atom_switch(rows,p01,p10)
    drift=[(m,s,a*u+(1-a)*target*s) for m,s,u in sw]
    out=atom_switch(drift,p01,p10)
    result=mat_switch(mat_drift(mat_switch(y,p01,p10),a,target),p01,p10)
    assert result==moments(out)
    assert sum(result[:2])==sum(y[:2])
    for s in (0,1):
        m,j,z=result[s],result[s+2],result[s+4];assert 0<=z<=j<=m and j*j<=m*z
    f=F(rng.randrange(17),16)
    assert tuple(x*f+(1-f)*x for x in result)==result
    checks+=1
    # arbitrary small receiver count/metre demand; donor common scaling
    n=5;d=[F(rng.randrange(20),8) for _ in range(n)]
    widths=[F(rng.choice([5,10,12])) for _ in d]
    cap,space=F(rng.randrange(20),4),F(rng.randrange(100),4)
    s=min(F(1),cap/sum(d) if sum(d) else F(1),space/sum(x*b for x,b in zip(d,widths)) if any(d) else F(1))
    accepted=[s*x for x in d];assert sum(accepted)<=cap and sum(x*b for x,b in zip(accepted,widths))<=space
    flux_checks+=1
# independent integration of two-pole means via RK4; compare closed expression.
def exact(p,u,al,nu,tau,target,h):
    k=al+nu;l=1/tau;pe=al/k
    if abs(k-l)<1e-12:cv=l*h*math.exp(-l*h)
    else:cv=l*(math.exp(-k*h)-math.exp(-l*h))/(l-k)
    return pe+(p-pe)*math.exp(-k*h),target*pe+(u-target*pe)*math.exp(-l*h)+target*(p-pe)*cv
def integrate(p,u,al,nu,tau,target,T,n=4000):
    h=T/n
    def f(p,u):return al-(al+nu)*p,(target*p-u)/tau
    for _ in range(n):
        a,b=f(p,u);c,d=f(p+a*h/2,u+b*h/2);e,g=f(p+c*h/2,u+d*h/2);i,j=f(p+e*h,u+g*h)
        p+=h*(a+2*c+2*e+i)/6;u+=h*(b+2*d+2*g+j)/6
    return p,u
maxerr=0
for i in range(96):
    al=.1+rng.random();nu=rng.random();tau=.5+rng.random()*3
    if i==0:al,nu,tau=.2,.3,2.
    p,u,target=[rng.random() for _ in range(3)]
    t=0.1+rng.random()*5
    x=exact(p,u,al,nu,tau,target,t);y=integrate(p,u,al,nu,tau,target,t)
    maxerr=max(maxerr,max(abs(a-b) for a,b in zip(x,y)));assert all(-1e-12<=z<=1+1e-12 for z in x)
assert maxerr<1e-10
# static derivative and complex transfer function evaluated independently.
a=.2;b=.6;n0=0.;U=10.;rhoj=.2
def nu(rho):return n0+b*(rho/rhoj)**2
def flow(rho):return U*rho*a/(a+nu(rho))
derr=0
for i in range(1,100):
    r=rhoj*i/100;h=1e-7
    nd=2*b*r/rhoj**2;k=a+nu(r)
    deriv=U*a*(k-r*nd)/k**2
    derr=max(derr,abs((flow(r+h)-flow(r-h))/(2*h)-deriv))
assert derr<1e-7
print(json.dumps(dict(status='PASS',seed=20261128,rational_pushforwards=checks,rational_quota_cases=flux_checks,rk4_mean_cases=96,max_mean_absolute_error=maxerr,finite_difference_cases=99,max_flux_derivative_error=derr,scope='independent exact atom pushforward and conditional mean checks; not full nonlinear traffic proof'),indent=2))
