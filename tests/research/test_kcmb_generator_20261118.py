"""Independent moment-generator / numerical realizability audit of KCMB.

RHS is written directly from the conditional microscopic generator, separate
from the uniformization matrix implementation.
"""
from __future__ import annotations
import math
import random

import pytest
from metroflow.v1.kcmb import KCMBClass, KCMBConfig, KCMBCorridor, _kinetic_transition


def rhs(state, a, nu, tau):
    m0,m1,j0,j1,z0,z1=state
    g=1/tau
    return (-a*m0+nu*m1,
            a*m0-nu*m1,
            -(g+a)*j0+nu*j1,
            g*m1+a*j0-(g+nu)*j1,
            -(2*g+a)*z0+nu*z1,
            2*g*j1+a*z0-(2*g+nu)*z1)


def rk4(initial, a, nu, tau, duration, n):
    x=list(initial)
    h=duration/n
    for _ in range(n):
        k1=rhs(x,a,nu,tau)
        k2=rhs([v+h*w/2 for v,w in zip(x,k1)],a,nu,tau)
        k3=rhs([v+h*w/2 for v,w in zip(x,k2)],a,nu,tau)
        k4=rhs([v+h*w for v,w in zip(x,k3)],a,nu,tau)
        x=[v+h*(p+2*q+2*r+s)/6 for v,p,q,r,s in zip(x,k1,k2,k3,k4)]
    return x


def direct(matrix,values):
    return tuple(math.fsum(matrix[6*i+j]*values[j] for j in range(6)) for i in range(6))


def test_independent_rk4_matches_uniformization_for_deterministic_micro_measures():
    rng=random.Random(20261118)
    for i in range(48):
        a=(0.,.01,.1,2.)[i%4]
        nu=(0.,.02,.4,1.)[(i//4)%4]
        tau=(.1,2.,4.)[(i//16)%3]
        dt=.3 if i%2 else 1.
        kind=KCMBClass(f"mode{i}",10.,5.,a,nu,tau)
        u=rng.random()
        p=rng.random()
        initial=((1-p),p,(1-p)*u,p*u,(1-p)*u*u,p*u*u)
        mat=_kinetic_transition(kind,dt)
        got=direct(mat,initial)
        ref=rk4(initial,a,nu,tau,dt,max(100,int(200*dt*max(a+nu,1/tau))))
        for v,w in zip(got,ref):
            assert v==pytest.approx(w,abs=2e-10,rel=2e-10),(i,got,ref)
        assert got[0]+got[1]==pytest.approx(1.,abs=1e-12)
        for mass,j,z in ((got[0],got[2],got[4]),(got[1],got[3],got[5])):
            assert mass>=-2e-13 and j>=-2e-13 and z>=-2e-13
            assert j*j<=mass*z+2e-12
            assert z<=j+2e-12 and j<=mass+2e-12


def test_frozen_semigroup_composition_for_far_from_equilibrium():
    cl=KCMBClass("c",20.,5.,.3,.8,2.)
    initial=(.7,.3,.13,.20,.04,.15)
    # This test checks the propagator identity for an arbitrary vector,
    # not moment realizability of this particular input.
    half=_kinetic_transition(cl,.25)
    full=_kinetic_transition(cl,.50)
    once=direct(full,initial)
    twice=direct(half,direct(half,initial))
    for a,b in zip(once,twice):
        assert a==pytest.approx(b,abs=2e-13,rel=1e-12)


def test_stationary_variance_is_not_binary_velocity_variance():
    a,nu,tau=.2,.3,3.
    c=KCMBClass("c",20.,6.,a,nu,tau)
    model=KCMBCorridor(KCMBConfig(
        cells=1,cell_length_m=100.,lanes=1,dt_s=.1,
        capacity_veh_per_s=.5,backward_wave_mps=5.,classes=(c,)))
    state=model.initial_profile(((1.,),),latent=(.8,),speed_fraction=(.2,))
    for _ in range(2500):
        state,_=model.step(state,(0.,),green=0.)
    m,p,V,H,Z=model.moment_observables(state)[0][0]
    pstar=a/(a+nu)
    theory=c.vmax_mps**2*pstar*(1-pstar)/(1+(a+nu)*tau)
    assert Z/m-(V/m)**2==pytest.approx(theory,abs=1e-9)


def test_rejects_density_overfill_and_nonrealizable_speed_distribution():
    c=KCMBClass("c",10.,8.,.2,.2,1.)
    model=KCMBCorridor(KCMBConfig(
        cells=1,cell_length_m=10.,lanes=1,dt_s=.5,
        capacity_veh_per_s=.2,backward_wave_mps=5.,classes=(c,)))
    with pytest.raises(ValueError,match="storage"):
        model.initial_profile(((2.,),))
    s=model.initial_profile(((1.,),))
    from dataclasses import replace
    with pytest.raises(ValueError,match="nonrealizable"):
        model.step(replace(s,moments=(.5,.5,.9,.9,.9,.9)),(0.,))


def test_large_mass_is_always_pending_rather_than_silently_discarded():
    c=KCMBClass("c",10.,8.,.2,.2,1.)
    obj=KCMBCorridor(KCMBConfig(
        cells=1,cell_length_m=10.,lanes=1,dt_s=.5,
        capacity_veh_per_s=.2,backward_wave_mps=5.,classes=(c,)))
    s,receipt=obj.step(obj.initial(),(1e6,),green=0.)
    assert s.released[0]==1e6
    assert receipt["accepted_by_class"][0] <=.1+1e-12
    assert s.released[0] == pytest.approx(s.pending[0]+obj.cell_class_mass(s,0,0),abs=1e-8)


def test_direct_microscopic_markov_trajectories_match_kinetic_moments():
    # Event-driven independent microscopic process, NOT the matrix generator
    # or its RK4 discretization. This is a stochastic sanity check only.
    rng=random.Random(20261119)
    alpha,nu,tau,T=.2,.4,2.1,3.
    p0,u0=.74,.31
    c=KCMBClass("microscopic",20.,5.,alpha,nu,tau)
    initial=(1-p0,p0,(1-p0)*u0,p0*u0,(1-p0)*u0*u0,p0*u0*u0)
    target=direct(_kinetic_transition(c,T),initial)
    samples=30000
    pmean=umean=zmean=0.
    for _ in range(samples):
        sigma=1 if rng.random()<p0 else 0
        u=u0
        t=0.
        while t<T:
            rate=alpha if sigma==0 else nu
            hold=rng.expovariate(rate) if rate>0 else float("inf")
            dt=min(hold,T-t)
            u=sigma+(u-sigma)*math.exp(-dt/tau)
            t+=dt
            if t<T:
                sigma=1-sigma
        pmean+=sigma
        umean+=u
        zmean+=u*u
    pmean/=samples
    umean/=samples
    zmean/=samples
    assert abs(pmean-target[1])<.02
    assert abs(umean-target[2]-target[3])<.02
    assert abs(zmean-target[4]-target[5])<.02
