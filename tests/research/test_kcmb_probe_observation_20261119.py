"""New exact moment-to-probe map: independent microscopic and generator checks."""
from __future__ import annotations

import math
import random
import pytest

from metroflow.v1.kcmb_probe_observation import (
    AffineProbeWeights,
    selected_probe_mean_speed,
    pooled_probe_mean_speed,
    stationary_six_moments,
)


def direct_particles(particles, weights, U):
    num=0.
    den=0.
    for sigma,u,mass in particles:
        if sigma==0:
            w=weights.a0+weights.b0*u
        else:
            w=weights.a1+weights.b1*u
        assert w>=0
        num+=mass*w*u
        den+=mass*w
    return U*num/den


def particle_moments(particles):
    out=[0.]*6
    for sigma,u,mass in particles:
        out[sigma]+=mass
        out[2+sigma]+=mass*u
        out[4+sigma]+=mass*u*u
    return tuple(out)


@pytest.mark.parametrize("weights",[
    AffineProbeWeights(),
    AffineProbeWeights(1.,1.,.5,.5),
    AffineProbeWeights(0.,1.,1.,-.8),
    AffineProbeWeights(3.,-2.,2.,1.),
])
def test_exact_affine_map_matches_independently_enumerated_microscopic_particles(weights):
    particles=[(0,0.25,2.),(0,.75,1.),(1,.1,3.),(1,.6,5.),(1,1.,2.)]
    y=particle_moments(particles)
    actual=selected_probe_mean_speed(y,20.,weights)
    expected=direct_particles(particles,weights,20.)
    assert actual==pytest.approx(expected,rel=2e-14,abs=1e-13)
    assert 0<=actual<=20.


def test_unweighted_and_positive_negative_speed_selection_bias_identity():
    # Positive distribution with strictly nonzero speed variance.
    particles=[(0,.1,2.),(0,.3,1.),(1,.6,2.),(1,.9,3.)]
    x=particle_moments(particles)
    M=x[0]+x[1]
    mean=(x[2]+x[3])/M
    variance=(x[4]+x[5])/M-mean*mean
    assert variance>0
    reference=selected_probe_mean_speed(x,15.,AffineProbeWeights())
    assert reference==pytest.approx(15*mean)
    for eta in (1.,-.8):
        w=AffineProbeWeights(1.,eta,1.,eta)
        observed=selected_probe_mean_speed(x,15.,w)
        correction=15*eta*variance/(1+eta*mean)
        assert observed-reference==pytest.approx(correction,abs=1e-12)
        assert (observed>reference)==(eta>0)


def test_weight_scaling_is_unobservable_and_zero_support_fails_closed():
    particles=[(0,.2,2.),(1,.6,3.)]
    y=particle_moments(particles)
    a=AffineProbeWeights(1.,.5,2.,-.25)
    b=AffineProbeWeights(5.,2.5,10.,-1.25)
    assert selected_probe_mean_speed(y,15.,a)==pytest.approx(
        selected_probe_mean_speed(y,15.,b),abs=1e-12)
    with pytest.raises(ValueError,match="support|probe"):
        selected_probe_mean_speed(y,15.,AffineProbeWeights(0.,0.,0.,0.))
    with pytest.raises(ValueError,match="support|probe"):
        selected_probe_mean_speed((0.,1.,0.,1.,0.,1.),15.,
                                  AffineProbeWeights(1.,-1.,1.,-1.))


@pytest.mark.parametrize("bad", [
    (-.1,0.,1.,0.),
    (1.,-1.01,1.,0.),
    (1.,0.,-1.,0.),
    (1.,0.,0.5,-.50001),
    (math.nan,0.,1.,0.),
    (1.,0.,math.inf,0.),
])
def test_invalid_physical_probe_weights_are_rejected(bad):
    with pytest.raises(ValueError,match="weight|finite|nonnegative"):
        AffineProbeWeights(*bad)


def test_nonphysical_kinetic_moments_or_speed_cannot_create_fake_measurement():
    with pytest.raises(ValueError):
        selected_probe_mean_speed((-1.,1.,0.,0.,0.,0.),10.,AffineProbeWeights())
    with pytest.raises(ValueError):
        selected_probe_mean_speed((1.,1.,1.4,0.,0.,0.),10.,AffineProbeWeights())
    with pytest.raises(ValueError):
        selected_probe_mean_speed((1.,1.,0.,0.,0.,0.),-1.,AffineProbeWeights())
    with pytest.raises(ValueError,match="support|probe"):
        selected_probe_mean_speed((0.,)*6,10.,AffineProbeWeights())


def test_pooled_observation_uses_support_weights_not_average_of_cell_speeds():
    a=particle_moments([(0,.1,100.)])
    b=particle_moments([(1,.9,1.)])
    obs=pooled_probe_mean_speed(((a,10.,AffineProbeWeights()),
                                (b,10.,AffineProbeWeights())))
    assert obs==pytest.approx(10*(10+.9)/101)
    assert obs!=pytest.approx(5.,abs=.01)
    mixed=pooled_probe_mean_speed(((a,10.,AffineProbeWeights()),
                                  (b,20.,AffineProbeWeights())))
    assert mixed==pytest.approx((100*.1*10+1*.9*20)/101)


@pytest.mark.parametrize("p,k,tau",[
    (.1,.5,3.),(.6,.5,3.),(.98,.01,.02),(.5,12.,9.),(0.,.5,4.),(1.,.5,2.)
])
def test_analytic_stationary_six_moments_satisfy_independent_generator(p,k,tau):
    y=stationary_six_moments(p,k,tau,mass=3.)
    m0,m1,j0,j1,z0,z1=y
    assert m0+m1==pytest.approx(3.)
    assert j0+j1==pytest.approx(3*p,abs=4e-14)
    variance=(z0+z1)/3-p*p
    assert variance==pytest.approx(p*(1-p)/(1+k*tau),abs=4e-13)
    alpha=k*p
    nu=k*(1-p)
    g=1/tau
    rhs=(
        -alpha*m0+nu*m1,
        alpha*m0-nu*m1,
        -(g+alpha)*j0+nu*j1,
        g*m1+alpha*j0-(g+nu)*j1,
        -(2*g+alpha)*z0+nu*z1,
        2*g*j1+alpha*z0-(2*g+nu)*z1,
    )
    assert max(abs(x) for x in rhs)<1e-9


def test_non_affine_probe_weight_third_moment_not_determined_by_six_moments():
    nodes=(0.,1/3,2/3,1.)
    baseline=(1/8,3/8,3/8,1/8)
    h=(-1,3,-3,1)
    plus=[(0,u,b+v/32) for u,b,v in zip(nodes,baseline,h)]
    minus=[(0,u,b-v/32) for u,b,v in zip(nodes,baseline,h)]
    ym=particle_moments(plus)
    yn=particle_moments(minus)
    assert ym==pytest.approx(yn,abs=1e-13)
    def nonlinear(arr):
        return sum(m*u**3 for s,u,m in arr)/sum(m*u*u for s,u,m in arr)
    assert abs(nonlinear(plus)-nonlinear(minus))>1e-3
