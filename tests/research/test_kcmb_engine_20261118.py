"""KCMB optional kinetic/conservative corridor: public behavior tests.

A kinetic approximation is NOT the existing FIFO packet solver; in particular,
class-mixed spatial cells do not preserve exact per-vehicle/OD order.
"""
import math
import random
import pytest

from metroflow.v1.kcmb import KCMBClass, KCMBConfig, KCMBCorridor


def small(backend="python", cells=12):
    classes = (
        KCMBClass("car", vmax_mps=10., footprint_m=6.,
                  alpha_per_s=.2, nu_per_s=.3, tau_s=2.,
                  source_p=1., source_speed_fraction=0.),
        KCMBClass("bus", vmax_mps=8., footprint_m=12.,
                  alpha_per_s=.3, nu_per_s=.1, tau_s=3.,
                  source_p=.5, source_speed_fraction=.25),
    )
    return KCMBCorridor(KCMBConfig(
        cells=cells, cell_length_m=15., lanes=2, dt_s=.5,
        capacity_veh_per_s=.7, backward_wave_mps=5.,
        classes=classes,
    ), backend=backend)


def matching(x, y, rel=3e-11, abs_tol=3e-10):
    if isinstance(x, (tuple, list)):
        assert len(x) == len(y)
        for a, b in zip(x, y):
            matching(a, b, rel, abs_tol)
    elif isinstance(x, str):
        assert x == y
    else:
        assert x == pytest.approx(y, rel=rel, abs=abs_tol)


def test_new_model_is_explicit_and_fails_closed_on_invalid_initial_and_CFL():
    model = small()
    s = model.initial()
    assert s.tick == 0 and model.state_scalars == 12*2*6+3*2
    assert s.model_id == model.model_id
    assert sum(s.moments) == 0
    with pytest.raises(ValueError, match="CFL"):
        KCMBCorridor(KCMBConfig(
            cells=2, cell_length_m=10., lanes=1, dt_s=10.,
            capacity_veh_per_s=.5, backward_wave_mps=5.,
            classes=(model.config.classes[0],)))
    with pytest.raises(ValueError):
        model.step(s, (math.nan, 0.))
    with pytest.raises(ValueError):
        model.step(s, (0., 0.), green=1.01)
    assert model.initial() == s
    with pytest.raises(ValueError, match="state|shape"):
        model.initial_profile(((1.,),))


def test_frozen_markov_velocity_and_variance_match_micro_moments():
    group = KCMBClass("car", vmax_mps=20., footprint_m=5.,
        alpha_per_s=.2, nu_per_s=.3, tau_s=3.,
        source_p=.8, source_speed_fraction=.45)
    model = KCMBCorridor(KCMBConfig(
        cells=1, cell_length_m=100., lanes=1, dt_s=.5,
        capacity_veh_per_s=.7, backward_wave_mps=5.,
        classes=(group,)), backend="python")
    s = model.initial_profile(((2.,),), latent=(1.,), speed_fraction=(1.,))
    # A closed outlet is an exact local 1-cell conditional kinetic test.
    for _ in range(240):
        s, event = model.step(s, (0.,), green=0.)
    m,p,u,h,z = model.moment_observables(s)[0][0]
    eq=.2/(.2+.3)
    stationary_variance=20.**2*eq*(1-eq)/(1+(.2+.3)*3.)
    assert p/m == pytest.approx(eq, abs=2e-11)
    assert u/m == pytest.approx(20.*eq, abs=2e-10)
    assert z/m-(u/m)**2 == pytest.approx(stationary_variance, rel=2e-10)
    assert 0 <= h <= u
    assert event["completed_by_class"][0] == 0.


def test_conservative_red_spillback_and_mixed_footprint():
    model = small(cells=20)
    state = model.initial()
    offered = [0., 0.]
    for tick in range(300):
        offers=(.24, .08)
        offered=[a+b for a,b in zip(offered,offers)]
        state,receipt=model.step(state, offers, green=(0. if tick<130 else 1.))
        for ci,amount in enumerate(offered):
            active=sum(model.cell_class_mass(state, i, ci) for i in range(20))
            assert amount == pytest.approx(state.pending[ci]+state.completed[ci]+active,
                                           rel=3e-12,abs=8e-9)
        assert all(model.cell_occupied_metres(state,i)<=model.config.lanes*15.+2e-9
                   for i in range(20))
        if tick<130:
            assert sum(receipt["completed_by_class"])==0.
        assert receipt["state_scalar_capacity"] == model.state_scalars
    assert sum(state.pending)>0.
    assert sum(state.completed)>0.


def test_checkpoint_resume_and_reject_other_model():
    model=small()
    state=model.initial()
    for tick in range(60):
        state,_=model.step(state,(.2,.1),green=float(tick%15 >= 4))
    frozen=model.to_bytes(state)
    restored=model.from_bytes(frozen)
    assert restored == state
    assert model.to_bytes(restored) == frozen
    for tick in range(20):
        state,_=model.step(state,(.1,0.),green=1.)
        restored,_=model.step(restored,(.1,0.),green=1.)
    assert state==restored
    with pytest.raises(ValueError,match="identity"):
        small(cells=13).from_bytes(frozen)
    with pytest.raises(ValueError):
        model.from_bytes(frozen+b"bad")


@pytest.mark.parametrize("backend",["python","rust"])
def test_native_and_python_are_both_explicit_stable_backends(backend):
    model=small(backend=backend)
    s=model.initial()
    for tick in range(125):
        s,rec=model.step(s,((tick%3)*.08,(tick%5)*.02),green=0. if tick%14<7 else 1.)
        assert rec["mass_error_max_veh"] <= 1e-8
    assert s.tick==125
    assert model.backend == backend


def test_python_rust_multi_class_numerical_parity():
    py=small("python",cells=36)
    rust=small("rust",cells=36)
    assert py.model_id==rust.model_id
    a=py.initial()
    b=rust.initial()
    for tick in range(240):
        offers=(0.4+(tick%4)*.03,.09 if tick%13 else .25)
        green=0. if tick%33<12 else 1.
        a,ra=py.step(a,offers,green=green)
        b,rb=rust.step(b,offers,green=green)
        matching(a.moments,b.moments,rel=2e-11,abs_tol=4e-9)
        matching(a.pending,b.pending,rel=2e-11,abs_tol=4e-9)
        matching(a.completed,b.completed,rel=2e-11,abs_tol=4e-9)
        matching(ra["accepted_by_class"],rb["accepted_by_class"],abs_tol=4e-9)
    assert a.tick==b.tick


def test_traffic_jam_scales_in_mass_not_in_allocated_state():
    model=small(cells=30)
    results=[]
    for scale in (1,10,100000):
        s=model.initial()
        for tick in range(100):
            s,rec=model.step(s, (0.1*scale,0.02*scale),green=0.)
        results.append((len(s.moments),sum(s.pending),rec["state_scalar_capacity"]))
    assert len({x[0] for x in results})==1
    assert len({x[2] for x in results})==1
    assert results[-1][1]>results[0][1]*1000


def test_triangular_godunov_limit_matches_independent_scalar_density_flux():
    c=KCMBClass("uniform",vmax_mps=10.,footprint_m=1/.15,
                alpha_per_s=1.,nu_per_s=0.,tau_s=1.,
                source_p=1.,source_speed_fraction=1.)
    for dx in (20.,10.,5.):
        dt=dx/20
        cfg=KCMBConfig(cells=int(4000/dx),cell_length_m=dx,lanes=1,dt_s=dt,
            capacity_veh_per_s=.5,backward_wave_mps=5.,classes=(c,))
        model=KCMBCorridor(cfg,backend="rust")
        masses=[(.02 if i<cfg.cells//2 else .10)*dx for i in range(cfg.cells)]
        st=model.initial_profile(tuple((m,) for m in masses), latent=(1.,),
                                 speed_fraction=(1.,))
        for _ in range(round(100/dt)):
            # Fixed Riemann reservoirs: q_left=.2veh/s; q_right=.25veh/s
            st,_=model.step(st,(.2*dt,),green=.5)
        densities=[model.cell_class_mass(st,i,0)/dx for i in range(cfg.cells)]
        exact_shock=(.25-.2)/(.10-.02)*100.
        spatial_error=0.
        for i,rho in enumerate(densities):
            xlo=(i-cfg.cells/2)*dx
            left_width=max(0.,min(dx,exact_shock-xlo))
            spatial_error+=abs(rho-.02)*left_width+abs(rho-.10)*(dx-left_width)
        assert spatial_error<3.,(dx,spatial_error)


def test_checkpoint_rejects_overbudget_input_without_materializing():
    obj=small()
    state=obj.initial()
    good=obj.to_bytes(state)
    assert obj.from_bytes(good)==state
    huge=b" "*((obj.state_scalars+1)*64+4096)
    with pytest.raises(ValueError,match="budget|size"):
        obj.from_bytes(huge)
    with pytest.raises(ValueError):
        obj.from_bytes(b"\xff\xfebroken")
