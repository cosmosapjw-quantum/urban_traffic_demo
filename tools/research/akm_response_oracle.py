#!/usr/bin/env python3
"""Independent driven two-rate PDMP mean response check at small amplitude."""
import json, math, cmath
alpha,nu0,beta,tau,U,phi,eps=.2,0.,.6,2.,10.,.6,1e-4
k=alpha+nu0+beta*phi**2
p0=alpha/k
out=[]
for omega in [.1,.5,2.]:
    T=2*math.pi/omega
    n=2048
    h=T/n
    p,u=p0,p0
    def deriv(t,p,u):
        f=phi+eps*math.cos(omega*t)
        return alpha-(alpha+nu0+beta*f*f)*p,(p-u)/tau
    z=0j
    for i in range(12*n):
        t=i*h
        if i>=10*n:z+=(U*u-U*p0)*cmath.exp(-1j*omega*t)
        a,b=deriv(t,p,u)
        c,d=deriv(t+h/2,p+h*a/2,u+h*b/2)
        e,f=deriv(t+h/2,p+h*c/2,u+h*d/2)
        g,j=deriv(t+h,p+h*e,u+h*f)
        p+=h*(a+2*c+2*e+g)/6
        u+=h*(b+2*d+2*f+j)/6
        assert 0<=p<=1 and 0<=u<=1
    measured=z/(n*eps)
    expected=-U*p0*2*beta*phi/((k+1j*omega)*(1+1j*omega*tau))
    err=abs(measured-expected)/abs(expected)
    assert err<1e-4, (omega,err)
    out.append({'omega_rad_s':omega,'expected':[expected.real,expected.imag],'measured':[measured.real,measured.imag],'relative_error':err})
print(json.dumps({'scope':'periodic small occupancy perturbation, frozen parameters except nu(phi); not full network stability','phi':phi,'eps':eps,'results':out},indent=2))
