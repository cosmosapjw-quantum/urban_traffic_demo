#!/usr/bin/env python3
"""KCMB proof-of-concept: kinetic mean + conservative triangular Godunov flux.

Research-only one-class, one-dimensional corridor.  No route FIFO theorem,
traffic-network node implementation, calibration, or V03 acceptance claim.
State dimension is fixed: three real numbers per spatial cell.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True, slots=True)
class KineticCell:
    mass: float                 # veh
    latent_mass: float          # veh (E[sigma] * mass)
    velocity_moment: float      # veh*m/s (E[v] * mass)


@dataclass(frozen=True, slots=True)
class Corridor:
    dx_m: float
    dt_s: float
    cap_veh_per_s: float
    wave_m_per_s: float
    jam_veh_per_m: float
    free_max_m_per_s: float
    restart_per_s: float
    hazard_per_s: float
    response_s: float

    def __post_init__(self):
        if not all(math.isfinite(v) and v > 0 for v in (
            self.dx_m,self.dt_s,self.cap_veh_per_s,self.wave_m_per_s,
            self.jam_veh_per_m,self.free_max_m_per_s,self.response_s)):
            raise ValueError("all corridor scales must be finite and positive")
        if self.restart_per_s < 0 or self.hazard_per_s < 0:
            raise ValueError("nonnegative transition rates required")
        if max(self.free_max_m_per_s,self.wave_m_per_s)*self.dt_s > self.dx_m:
            raise ValueError("discrete CFL condition violated")

    @property
    def jam_storage(self):
        return self.jam_veh_per_m*self.dx_m


def evolved_local(cell: KineticCell, config: Corridor) -> KineticCell:
    """Exact frozen Markov mean semigroup; no acceleration clipping."""
    m = cell.mass
    if not m:
        return cell
    p = cell.latent_mass/m
    v0 = cell.velocity_moment/m
    alpha,nu = config.restart_per_s,config.hazard_per_s
    lam=alpha+nu
    gamma=1/config.response_s
    eq=alpha/lam if lam else p
    t=config.dt_s
    p1=eq+(p-eq)*math.exp(-lam*t)
    d=gamma-lam
    if abs(d*t)<1e-6:
        # analytic equal-rate limit; second-order in d*t near resonance
        mixed=t*math.exp(-(gamma+lam)*t/2) * (1+(d*t)**2/24)
    else:
        mixed=(math.exp(-lam*t)-math.exp(-gamma*t))/d
    v1=config.free_max_m_per_s*eq+(v0-config.free_max_m_per_s*eq)*math.exp(-gamma*t)
    v1+=config.free_max_m_per_s*gamma*(p-eq)*mixed
    if not (-1e-11 <= p1 <= 1+1e-11 and -1e-11 <= v1 <= config.free_max_m_per_s+1e-11):
        raise ArithmeticError("kinetic physical domain")
    return KineticCell(m,m*p1,m*v1)


def step(states: Sequence[KineticCell], config: Corridor, *, inject_veh=0.,
         exit_gate=1., source_p=1., source_speed=None):
    """Kinetic collide, then simultaneous conservative finite volume transport."""
    n=len(states)
    if n<1 or not all(0<=s.mass<=config.jam_storage+1e-10 and
                      0<=s.latent_mass<=s.mass+1e-10 and
                      0<=s.velocity_moment<=s.mass*config.free_max_m_per_s+1e-10
                      for s in states):
        raise ValueError("invalid kinetic cell moments")
    if inject_veh<0 or not 0<=exit_gate<=1:
        raise ValueError("invalid source/exit")
    source_speed=config.free_max_m_per_s if source_speed is None else source_speed
    if not (0 <= source_p <= 1 and 0 <= source_speed <= config.free_max_m_per_s):
        raise ValueError("source kinetic moments outside physical bounds")
    kinetic=[evolved_local(s,config) for s in states]
    send=[min(s.mass, config.cap_veh_per_s*config.dt_s,
              config.dt_s/config.dx_m*s.velocity_moment) for s in kinetic]
    receive=[min(max(0.,config.jam_storage-s.mass),
                 config.cap_veh_per_s*config.dt_s,
                 config.wave_m_per_s*config.dt_s/config.dx_m *
                 max(0.,config.jam_storage-s.mass)) for s in kinetic]
    transfers=[min(send[i],receive[i+1]) for i in range(n-1)]
    source=min(inject_veh,receive[0])
    sink=send[-1]*exit_gate
    flux=[source]+transfers+[sink]
    new=[]
    for i,s in enumerate(kinetic):
        old_fraction=flux[i+1]/s.mass if s.mass>0 else 0.
        inflow=flux[i]
        if i==0:
            ip,in_m=inflow*source_p,inflow*source_speed
        else:
            upstream=kinetic[i-1]
            input_fraction=inflow/upstream.mass if upstream.mass>0 else 0.
            ip, in_m=input_fraction*upstream.latent_mass,input_fraction*upstream.velocity_moment
        new.append(KineticCell(s.mass+inflow-flux[i+1],
                               s.latent_mass*(1-old_fraction)+ip,
                               s.velocity_moment*(1-old_fraction)+in_m))
    mass0=math.fsum(s.mass for s in states)
    mass1=math.fsum(s.mass for s in new)
    residual=mass1-(mass0+source-sink)
    if abs(residual)>3e-10*max(1,mass0+source):
        raise ArithmeticError("conservation residual")
    return tuple(new),dict(inject_veh=source,exit_veh=sink,
                           mass_residual_veh=residual,
                           state_scalar_capacity=3*n)


def godunov_step(densities: Sequence[float], dx:float, dt:float,
                 vf:float,w:float,kj:float,cap:float,
                 left:float,right:float):
    """Independent equilibrium constant-parameter scalar finite-volume check."""
    assert max(vf,w)*dt/dx<=1+1e-13
    def flux(kleft,kright):
        demand=min(vf*kleft,cap)
        supply=min(w*(kj-kright),cap)
        return min(demand,supply)
    aug=[left,*densities,right]
    interface=[flux(aug[i],aug[i+1]) for i in range(len(aug)-1)]
    return [k+(dt/dx)*(interface[i]-interface[i+1])
            for i,k in enumerate(densities)]


def run_shock_oracle(nx=800,dx=5.,dt=.25,tend=100.):
    vf,w,kj=15.,5.,.15
    cap=vf*w*kj/(vf+w)
    left,right=.02,.10
    state=[left if i < nx//2 else right for i in range(nx)]
    initial_mass=math.fsum(state)*dx
    for _ in range(round(tend/dt)):
        state=godunov_step(state,dx,dt,vf,w,kj,cap,left,right)
    # numerical mass change = imposed difference of boundary Riemann fluxes.
    # The shock has speed -0.625m/s, so mass gain = (kR-kL)*62.5m.
    excess=(math.fsum(state)*dx-initial_mass)
    shock_shift=-excess/(right-left)
    analytic=(w*(kj-right)-vf*left)/(right-left)*tend
    # The mass-derived position above is a conservation identity and CANNOT
    # establish that the density shock actually travels at that speed.
    # The spatial L1 metric independently observes the *shape* and location.
    l1=0.
    crossing=None
    for i,rho in enumerate(state):
        xlo=(i-nx/2)*dx
        xhi=xlo+dx
        left_width=max(0.,min(dx,analytic-xlo))
        l1+=abs(rho-left)*left_width + abs(rho-right)*(dx-left_width)
        if crossing is None and rho >= (left+right)/2:
            crossing=xlo+dx/2
    return dict(ncells=nx,dx_m=dx,dt_s=dt,
                predicted_shift_m=analytic,reconstructed_shift_m=shock_shift,
                conservation_only_shift_residual_m=shock_shift-analytic,
                density_half_height_crossing_m=crossing,
                crossing_error_m=(crossing-analytic if crossing is not None else None),
                spatial_L1_error_veh=l1)


def run_signal_spillback():
    cfg=Corridor(dx_m=10.,dt_s=.5,cap_veh_per_s=.6,wave_m_per_s=5.,
                 jam_veh_per_m=.15,free_max_m_per_s=10.,
                 restart_per_s=.2,hazard_per_s=.0,response_s=2.)
    s=tuple(KineticCell(0.,0.,0.) for _ in range(20))
    pending=0.
    released=completed=0.
    maxfill=0.
    for tick in range(600):
        # one 150s red period and 150s green period; constant arrivals.
        births=.8*cfg.dt_s
        pending+=births
        green=0. if tick<300 else 1.
        s,receipt=step(s,cfg,inject_veh=pending,exit_gate=green)
        pending-=receipt['inject_veh']
        released+=births
        completed+=receipt['exit_veh']
        maxfill=max(maxfill,max(x.mass for x in s))
        assert all(-1e-11<=x.mass<=cfg.jam_storage+1e-11 for x in s)
        assert abs(released-(pending+completed+math.fsum(x.mass for x in s)))<1e-7
        if tick<300:
            assert completed==0.
    return dict(cells=len(s),fixed_state_scalars=3*len(s),
                released_veh=released,completed_veh=completed,pending_veh=pending,
                active_veh=math.fsum(x.mass for x in s),
                max_occupancy_veh=maxfill,
                jam_capacity_veh=cfg.jam_storage,
                conservative=True)


def main(path: str):
    s=run_shock_oracle()
    t=run_signal_spillback()
    assert abs(s["crossing_error_m"]) < 2*s["dx_m"] and s["spatial_L1_error_veh"] < 3., (s,t)
    result=dict(model="research-only kinetic Markov + conservative Godunov bridge",
                shock=s,signal_spillback=t,
                scope="1D one-class, frozen parameters; no full FIFO, mixed bus freight, full city or empirical validation")
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps(result))


if __name__=="__main__":
    import sys
    if len(sys.argv)!=2: raise SystemExit("usage: kc_bridge_reference.py output.json")
    main(sys.argv[1])
