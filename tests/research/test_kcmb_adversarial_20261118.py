"""One bounded adversarial readback of opt-in KCMB Python/Rust semantics."""
from __future__ import annotations
import math
import random

import pytest
from metroflow.v1.kcmb import KCMBClass, KCMBConfig, KCMBCorridor


@pytest.mark.parametrize("seed",(1,17,41,103,500))
def test_randomized_multi_class_python_rust_equality_mass_and_kinetic_cone(seed):
    rng=random.Random(seed)
    classes=tuple(
        KCMBClass(f"type{i}",vmax_mps=7.+2*i,footprint_m=4.+2*i,
            alpha_per_s=rng.random()*.8,nu_per_s=rng.random()*.5,
            tau_s=1.+rng.random()*4.,source_p=rng.random(),
            source_speed_fraction=rng.random())
        for i in range(3))
    spec=KCMBConfig(cells=11,cell_length_m=15.,lanes=2,dt_s=.25,
        capacity_veh_per_s=.6,backward_wave_mps=4.,classes=classes)
    py,rs=KCMBCorridor(spec,backend="python"),KCMBCorridor(spec,backend="rust")
    profile=tuple(tuple(rng.random()*.04 for _ in classes) for i in range(spec.cells))
    a=py.initial_profile(profile)
    b=rs.initial_profile(profile)
    assert a.model_id==b.model_id
    for tick in range(90):
        offered=tuple(rng.random()*.15 for _ in classes)
        green=0. if tick%30<12 else 1.
        a,x=py.step(a,offered,green=green)
        b,y=rs.step(b,offered,green=green)
        assert a.tick==b.tick
        assert x["mass_error_max_veh"]<1e-9
        assert y["mass_error_max_veh"]<1e-9
        for u,v in zip(a.moments,b.moments):
            assert u==pytest.approx(v,abs=4e-11,rel=4e-11)
        for i in range(spec.cells):
            assert py.cell_occupied_metres(a,i)<=spec.lanes*spec.cell_length_m+1e-8
        for i in range(len(classes)):
            active=sum(py.cell_class_mass(a,j,i) for j in range(spec.cells))
            assert a.released[i]==pytest.approx(a.pending[i]+a.completed[i]+active,
                                                  abs=1e-9)


def test_large_rate_and_zero_rate_limits_no_unbounded_work():
    c=KCMBClass("stiff",vmax_mps=20.,footprint_m=6.,
                 alpha_per_s=1000.,nu_per_s=1000.,tau_s=.001)
    cfg=KCMBConfig(cells=1,cell_length_m=100.,lanes=1,dt_s=.1,
        capacity_veh_per_s=.2,backward_wave_mps=5.,classes=(c,))
    py=KCMBCorridor(cfg,backend="python")
    st=py.initial_profile(((2.,),),latent=(1.,),speed_fraction=(1.,))
    for i in range(2):
        st,_=py.step(st,(0.,),green=0.)
    mass,p,mean,h,z=py.moment_observables(st)[0][0]
    assert p/mass==pytest.approx(.5,abs=2e-9)
    assert mean/mass==pytest.approx(10.,abs=2e-8)
    with pytest.raises(ValueError,match="budget"):
        KCMBCorridor(KCMBConfig(cells=1,cell_length_m=10.,lanes=1,dt_s=.5,
            capacity_veh_per_s=.5,backward_wave_mps=5.,
            classes=(KCMBClass("too-fast",10.,2.,1e8,1e8,1e-9),)))


def test_bad_checkpoint_and_failed_rust_step_does_not_change_input():
    cl=KCMBClass("one",10.,6.,.2,.4,2.)
    m=KCMBCorridor(KCMBConfig(cells=3,cell_length_m=10.,lanes=1,
        dt_s=.5,capacity_veh_per_s=.5,backward_wave_mps=5.,classes=(cl,)),
        backend="rust")
    s=m.initial()
    frozen=m.to_bytes(s)
    with pytest.raises(ValueError):
        m.step(s,(float("inf"),))
    with pytest.raises(ValueError):
        m.step(s,(-1.,))
    import json
    wire=json.loads(frozen)
    wire['moments'][0]=float("nan")
    with pytest.raises(ValueError):
        m.from_bytes(json.dumps(wire).encode())
    assert m.to_bytes(s)==frozen


def test_memory_state_bound_is_independent_of_input_mass_not_of_spatial_resolution():
    cl=KCMBClass("one",10.,6.,.2,.3,2.)
    sizes=[]
    for n in (8,16,32):
        spec=KCMBConfig(cells=n,cell_length_m=10.,lanes=1,dt_s=.5,
            capacity_veh_per_s=.5,backward_wave_mps=5.,classes=(cl,))
        m=KCMBCorridor(spec,backend="rust")
        state=m.initial()
        state,_=m.step(state,(1e8,),green=0.)
        sizes.append((n,m.state_scalars,len(state.moments),state.pending[0]))
    assert [v[1] for v in sizes] == [6*n+3 for n in (8,16,32)]
    assert all(v[3]>1e8-1 for v in sizes)
