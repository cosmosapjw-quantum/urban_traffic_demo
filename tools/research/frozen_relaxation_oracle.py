#!/usr/bin/env python3
"""Research-only frozen-environment exact response, not a runtime replacement.

For each class c: p'_c = r_c - lambda_c p_c.
Unclipped common speed: v' = -gamma v + U sum_c (w_c/tau_c) p_c.
All parameters are frozen on [0, T]; no link/node/queue effects.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys


@dataclass(frozen=True)
class Species:
    weight: float
    tau_s: float
    p0: float
    restart_per_s: float
    hazard_per_s: float

    def params(self):
        assert self.weight > 0 and self.tau_s > 0
        assert 0 <= self.p0 <= 1 and self.restart_per_s >= 0 and self.hazard_per_s >= 0
        lam = self.restart_per_s + self.hazard_per_s
        equilibrium = self.restart_per_s / lam if lam else self.p0
        return lam, equilibrium, self.p0 - equilibrium


def exp_integral(rate: float, duration: float):
    return -math.expm1(-rate * duration) / rate if rate else duration


def resonance_integral(rate: float, duration: float):
    z = rate * duration
    if abs(z) < 1e-4:
        return duration ** 2 * (0.5 - z / 3 + z ** 2 / 8 - z ** 3 / 30)
    return (-math.expm1(-z) - z * math.exp(-z)) / rate ** 2


def mixed_exponential_integral(gamma: float, lam: float, t: float):
    diff = gamma - lam
    if abs(diff * t) < 1e-6:
        # Midpoint difference-quotient limit, error O((diff*t)^2).
        return resonance_integral((gamma + lam) * 0.5, t)
    return (exp_integral(lam, t) - exp_integral(gamma, t)) / diff


def mixed_exponential(gamma: float, lam: float, t: float):
    diff = gamma - lam
    z = diff * t
    if abs(z) < 1e-5:
        ratio = 1 + z/2 + z*z/6 + z**3/24 + z**4/120
        return t * math.exp(-gamma*t) * ratio
    # Avoid large expm1 overflow for extreme positive z.
    if z > 500:
        return (math.exp(-lam*t) - math.exp(-gamma*t)) / diff
    return t * math.exp(-gamma*t) * math.expm1(z) / z


def exact_frozen(t: float, U: float, v0: float, species: tuple[Species, ...]):
    assert t >= 0 and U >= 0 and v0 >= 0
    assert abs(math.fsum(s.weight for s in species)-1) < 1e-12
    gamma = math.fsum(s.weight / s.tau_s for s in species)
    weights = [s.weight / s.tau_s for s in species]
    parms = [s.params() for s in species]
    vstar = U * math.fsum(a * eq for a, (_, eq, _) in zip(weights, parms)) / gamma
    velocity = vstar + (v0 - vstar) * math.exp(-gamma*t)
    distance = vstar*t + (v0-vstar)*exp_integral(gamma,t)
    for a, (lam, _, delta) in zip(weights, parms):
        coefficient = U * a * delta
        velocity += coefficient * mixed_exponential(gamma,lam,t)
        distance += coefficient * mixed_exponential_integral(gamma,lam,t)
    return velocity, distance


def rk4(t: float, U: float, v0: float, species: tuple[Species,...], n: int):
    h=t/n
    p=[s.p0 for s in species]
    v=v0
    x=0.0
    gamma=math.fsum(s.weight/s.tau_s for s in species)
    a=[s.weight/s.tau_s for s in species]
    def deriv(ys):
        pp=ys[:-2]
        vv=ys[-2]
        return ([s.restart_per_s - (s.restart_per_s+s.hazard_per_s)*pc
                 for s,pc in zip(species,pp)]
                + [-gamma*vv + U*math.fsum(ac*pc for ac,pc in zip(a,pp)),vv])
    ys=p+[v,x]
    for _ in range(n):
        k1=deriv(ys)
        k2=deriv([y+h*k/2 for y,k in zip(ys,k1)])
        k3=deriv([y+h*k/2 for y,k in zip(ys,k2)])
        k4=deriv([y+h*k for y,k in zip(ys,k3)])
        ys=[y+h*(u+2*w+2*z+k)/6 for y,u,w,z,k in zip(ys,k1,k2,k3,k4)]
    return ys[-2],ys[-1]


def strang_frozen(t:float,U:float,v0:float,species:tuple[Species,...],steps:int):
    h=t/steps
    gamma=math.fsum(s.weight/s.tau_s for s in species)
    a=[s.weight/s.tau_s for s in species]
    parms=[s.params() for s in species]
    p=[s.p0 for s in species]
    v=v0
    x=0.0
    for _ in range(steps):
        mid=[eq+(pc-eq)*math.exp(-lam*h/2)
             for pc,(lam,eq,_) in zip(p,parms)]
        target=U * math.fsum(ac*pc for ac,pc in zip(a,mid)) / gamma
        x += target*h+(v-target)*exp_integral(gamma,h)
        v = target+(v-target)*math.exp(-gamma*h)
        p=[eq+(pc-eq)*math.exp(-lam*h)
           for pc,(lam,eq,_) in zip(p,parms)]
    return v,x


def main(out):
    classes=(Species(2/3,2.,0.9,0.2,0.3),Species(1/3,3.,0.2,0.1,0.05))
    t,U,v0=5.,12.,5.
    exact=exact_frozen(t,U,v0,classes)
    approximate=rk4(t,U,v0,classes,5000)
    errs=[max(abs(a-b) for a,b in zip(strang_frozen(t,U,v0,classes,n),exact))
          for n in (5,10,20,40)]
    assert max(abs(a-b) for a,b in zip(exact,approximate)) < 3e-9
    assert all(right < left*0.3 for left,right in zip(errs,errs[1:])), errs
    # Resonant analytical solution has a linear-in-t exponential.
    resonant=(Species(1.0,2.0,0.8,0.2,0.3),)
    vv,xx=exact_frozen(2.,10.,7.,resonant)
    ex=math.exp(-1.)
    expected_v=4.+(7.-4.)*ex+2.*2.*ex
    expected_x=4.*2+(7.-4.)*exp_integral(.5,2.)+2.*resonance_integral(.5,2.)
    assert abs(vv-expected_v)<1e-12 and abs(xx-expected_x)<1e-12
    result={"model":"frozen multi-class latent relaxation, no clipping",
            "sample":{"T_s":t,"U_m_per_s":U,"v0_m_per_s":v0},
            "exact":{"velocity_m_per_s":exact[0],"distance_m":exact[1]},
            "rk4_5000":{"velocity_m_per_s":approximate[0],"distance_m":approximate[1]},
            "maximum_absolute_error_strang_step_counts":[[n,e] for n,e in zip((5,10,20,40),errs)],
            "resonance_checked":True,
            "status":"DERIVED + NUMERICALLY_CHECKED_REFERENCE_ONLY",
            "caveats":["no acceleration/braking clip","frozen U/hazard/composition/length","not network runtime or 24h performance",
                       "distance near gamma=lambda uses controlled midpoint limit"]}
    Path(out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"exact":exact,"rk4":approximate,"strang_errors":errs}))


if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("usage: frozen_relaxation_oracle.py OUTPUT.json")
    main(sys.argv[1])
