"""Selected-theory R7 checks: research prototype only; no V1 production mutation."""
from __future__ import annotations

import cmath
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import math
import random
import sys

DIR=Path(__file__).resolve().parents[2]/"tools/research"


def load(name, file):
    spec=spec_from_file_location(name,DIR/file)
    obj=module_from_spec(spec)
    sys.modules[spec.name]=obj
    spec.loader.exec_module(obj)
    return obj


bridge=load("kcmb_ref_theory","kc_bridge_reference.py")
frozen=load("frozen_mean_oracle_theory","frozen_relaxation_oracle.py")


def test_frozen_micro_generator_matches_markov_expected_speed():
    cfg=bridge.Corridor(dx_m=10.,dt_s=.5,cap_veh_per_s=.5,
        wave_m_per_s=5.,jam_veh_per_m=.2,free_max_m_per_s=10.,
        restart_per_s=.2,hazard_per_s=.3,response_s=2.)
    c=bridge.KineticCell(mass=1.25,latent_mass=1.25*.8,
                         velocity_moment=1.25*5.)
    actual=bridge.evolved_local(c,cfg)
    micro=frozen.exact_frozen(cfg.dt_s,10.,5.,
              (frozen.Species(1.,2.,.8,.2,.3),))
    pstar=.2/.5
    p1=pstar+(.8-pstar)*math.exp(-.5*.5)
    assert math.isclose(actual.latent_mass,1.25*p1,abs_tol=2e-13)
    assert math.isclose(actual.velocity_moment,1.25*micro[0],abs_tol=2e-13)


def test_finite_state_conservation_under_adversarial_flows_and_gates():
    cfg=bridge.Corridor(dx_m=10.,dt_s=.5,cap_veh_per_s=.5,
        wave_m_per_s=5.,jam_veh_per_m=.15,free_max_m_per_s=10.,
        restart_per_s=.3,hazard_per_s=.1,response_s=3.)
    rng=random.Random(1107)
    s=tuple(bridge.KineticCell(0.,0.,0.) for _ in range(12))
    offered=pending=completed=0.
    for j in range(700):
        birth=rng.random()*2.
        offered+=birth
        pending+=birth
        green=0. if j%19<8 else 1.
        s,rec=bridge.step(s,cfg,inject_veh=pending,exit_gate=green,source_p=.7,source_speed=5.)
        pending-=rec["inject_veh"]
        completed+=rec["exit_veh"]
        assert rec["state_scalar_capacity"] ==36
        assert math.isclose(offered,pending+completed+math.fsum(c.mass for c in s),
                            rel_tol=5e-13,abs_tol=1e-10)
        assert all(0 <=c.mass <=cfg.jam_storage+1e-10 and
                   0<=c.latent_mass<=c.mass+1e-10 and
                   0<=c.velocity_moment<=c.mass*cfg.free_max_m_per_s+1e-10 for c in s)
        if green==0.:
            assert rec["exit_veh"]==0.


def test_gate_and_cfl_reject_physically_inconsistent_inputs():
    base=dict(dx_m=10.,dt_s=.5,cap_veh_per_s=.6,wave_m_per_s=5.,
              jam_veh_per_m=.15,free_max_m_per_s=10.,
              restart_per_s=.2,hazard_per_s=.3,response_s=2.)
    import pytest
    with pytest.raises(ValueError,match="CFL"):
        bridge.Corridor(**{**base,"dt_s":2.})
    cfg=bridge.Corridor(**base)
    blank=[bridge.KineticCell(0.,0.,0.)]
    with pytest.raises(ValueError,match="source"):
        bridge.step(blank,cfg,inject_veh=.1,source_speed=12.)
    with pytest.raises(ValueError,match="source"):
        bridge.step(blank,cfg,inject_veh=.1,source_p=1.01)


def test_actual_density_shock_shape_converges_not_just_mass_position():
    cases=[]
    for dx in (20.,10.,5.,2.5):
        result=bridge.run_shock_oracle(nx=round(4000/dx),dx=dx,dt=dx/20)
        cases.append(result)
        assert abs(result["crossing_error_m"])<dx
        assert result["spatial_L1_error_veh"]>0.
    errors=[a["spatial_L1_error_veh"] for a in cases]
    assert all(b<a for a,b in zip(errors,errors[1:])),errors
    assert errors[-1]<.02


def test_dense_to_spillback_signal_case_is_mass_and_storage_consistent():
    result=bridge.run_signal_spillback()
    assert result["fixed_state_scalars"]==60
    assert result["max_occupancy_veh"]<=result["jam_capacity_veh"]+1e-12
    assert result["pending_veh"]>0 and result["completed_veh"]>0
    assert math.isclose(result["released_veh"],result["completed_veh"]+
                        result["pending_veh"]+result["active_veh"],abs_tol=5e-10)


def test_ovm_instability_threshold_is_conditional_not_an_independent_solver_claim():
    # Exact linearized OVM ring mode: tau λ^2+λ=a(exp(i k)-1).
    # k=2pi/256 is small, chosen to expose the long-wave instability.
    k=2*math.pi/256
    a=1.  # s^-1, the derivative V'(h*)
    def growth(tau):
        lam=(-1+cmath.sqrt(1+4*tau*a*(cmath.exp(1j*k)-1)))/(2*tau)
        return lam.real
    assert growth(.25)<0
    assert growth(2.)>0
    assert growth(2.)<.003
