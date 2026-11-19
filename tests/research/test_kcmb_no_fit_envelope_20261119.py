"""Independent physical particle tests for no-fit sharp affine probe bounds."""
from fractions import Fraction as F
import random
import pytest
from metroflow.v1.kcmb_probe_envelope import affine_probe_speed_envelope,pooled_affine_probe_speed_envelope
from metroflow.v1.kcmb_probe_observation import AffineProbeWeights,selected_probe_mean_speed,pooled_probe_mean_speed

def particle_moments(rows):
    x=[F(0)]*6
    for s,u,m in rows:
        x[s]+=m; x[2+s]+=u*m; x[4+s]+=u*u*m
    return tuple(float(z) for z in x)

def test_exact_fraction_extrema_are_attained_with_no_fitted_parameters():
    rows=((0,F(1,4),F(3)),(0,F(3,4),F(1)),(1,F(1,3),F(2)),(1,F(1),F(1)))
    x=particle_moments(rows)
    r=affine_probe_speed_envelope(x,12.)
    assert r.min_speed_mps==pytest.approx(3.6)
    assert r.max_speed_mps==pytest.approx(8.8)
    assert r.vertex_speeds_mps==pytest.approx((3.6,6.,4.,8.8))
    assert selected_probe_mean_speed(x,12.,AffineProbeWeights(1.,-1.,0.,0.))==pytest.approx(r.min_speed_mps)
    assert selected_probe_mean_speed(x,12.,AffineProbeWeights(0.,0.,0.,1.))==pytest.approx(r.max_speed_mps)

def test_random_nonnegative_affine_probe_laws_stay_inside_sharp_bounds():
    rng=random.Random(20261119)
    rows=tuple((rng.randrange(2),F(rng.randrange(101),100),F(rng.randrange(1,10))) for _ in range(30))
    x=particle_moments(rows)
    e=affine_probe_speed_envelope(x,14.5)
    for _ in range(120):
        a,b,c,d=[rng.random()*4 for j in range(4)]
        w=AffineProbeWeights(a,b-a,c,d-c)
        mean=selected_probe_mean_speed(x,14.5,w)
        assert e.min_speed_mps-1e-11<=mean<=e.max_speed_mps+1e-11

def test_pooled_one_common_law_and_no_naive_equal_cell_average():
    x=particle_moments(((0,F(1,5),F(100)),))
    y=particle_moments(((1,F(9,10),F(1)),))
    e=pooled_affine_probe_speed_envelope(((x,10.),(y,20.)))
    for j in range(4):
        w=[0.,0.,0.,0.];w[j]=1.
        law=AffineProbeWeights(w[0],w[1]-w[0],w[2],w[3]-w[2])
        try:v=pooled_probe_mean_speed(((x,10.,law),(y,20.,law)))
        except ValueError:continue
        assert e.min_speed_mps-1e-10<=v<=e.max_speed_mps+1e-10

def test_single_speed_collapse_and_invalid_states():
    e=affine_probe_speed_envelope((0.,3.,0.,1.5,0.,.75),20.)
    assert e.min_speed_mps==pytest.approx(10.)
    assert e.max_speed_mps==pytest.approx(10.)
    with pytest.raises(ValueError):
        affine_probe_speed_envelope((0.,)*6,10.)
    with pytest.raises(ValueError):
        affine_probe_speed_envelope((-1.,2.,0.,0.,0.,0.),10.)
    with pytest.raises(ValueError):
        affine_probe_speed_envelope((1.,1.,0.,0.,0.,0.),float('nan'))
    with pytest.raises(ValueError):
        pooled_affine_probe_speed_envelope(())
