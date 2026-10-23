"""Public service-rate regressions: conservation alone is insufficient."""
from dataclasses import replace
import pytest
from metroflow.pure_traffic.ctm import (
    CTMConfig, LinkSpec, MovementSpec, NetworkSpec, VehicleRequest,
    initialize_state, simulate,
)


def saturated_fixture(dt=1.0, green=(), two_links=False):
    links = [LinkSpec('a','o','m',1000.,1,15.,5.,150.,1800.)]
    moves = [MovementSpec('a',None,1800.,green_cycle=green)]
    route = ('a',)
    if two_links:
        links.append(LinkSpec('b','m','d',1000.,1,15.,5.,150.,1800.))
        moves = [MovementSpec('a','b',1800.,green_cycle=green),MovementSpec('b',None,1800.)]
        route = ('a','b')
    net=NetworkSpec(tuple(links),tuple(moves))
    requests=tuple(VehicleRequest(i,0,route) for i in range(100))
    cfg=CTMConfig(tick_seconds=dt,forced_cell_count_by_link={link.link_id:1 for link in links})
    state=initialize_state(net,requests,cfg)
    cells=((tuple(range(100)),),)+(((),),)*(len(links)-1)
    state=replace(state,cells=cells,admitted_ticks=(0,)*100,
                  released_count=100,cumulative_source_admissions=(100,)+(0,)*(len(links)-1))
    return net,requests,cfg,state


@pytest.mark.parametrize('dt',[0.5,1.,2.,5.,10.])
def test_saturated_service_is_independent_of_subvehicle_tick(dt):
    net,requests,cfg,state=saturated_fixture(dt)
    result=simulate(net,requests,cfg,ticks=round(100/dt),initial_state=state)
    assert result.final_state.completed_count == 50
    assert result.final_state.mass_balance_error == 0


def test_fractional_green_pulses_accumulate_but_red_never_discharges():
    net,requests,cfg,state=saturated_fixture(green=(True,False))
    result=simulate(net,requests,cfg,ticks=100,initial_state=state)
    assert result.final_state.completed_count == 25
    counts={s.tick:s.completed_count for s in result.snapshots}
    for tick in range(1,100,2):
        assert counts[tick+1] == counts[tick]


def test_out_of_phase_sending_receiving_ledgers_do_not_deadlock():
    net,requests,cfg,state=saturated_fixture(two_links=True)
    state=replace(state,entry_residuals=(0.,0.5))
    result=simulate(net,requests,cfg,ticks=100,initial_state=state)
    assert result.cumulative_movement_flow[('a','b')] == 50
    assert result.final_state.mass_balance_error == 0


def test_refinement_must_not_invent_vehicle_storage():
    net=NetworkSpec((LinkSpec('a','o','d',100.,1,10.,5.,150.,1800.),),
                    (MovementSpec('a',None,1800.),))
    cfg=CTMConfig(tick_seconds=.1,forced_cell_count_by_link={'a':100})
    with pytest.raises(ValueError,match='storage|vehicle'):
        initialize_state(net,(),cfg)


def test_full_retained_credit_cannot_release_through_a_red_gate():
    net,requests,cfg,state=saturated_fixture(green=(False,))
    state=replace(state,movement_residuals=(1.,),exit_residuals=(1.,))
    result=simulate(net,requests,cfg,ticks=20,initial_state=state)
    assert result.final_state.completed_count == 0
    assert result.final_state.movement_residuals == (1.,)


def test_zero_incident_capacity_is_a_hard_gate_even_with_full_credits():
    from metroflow.pure_traffic.ctm import Incident
    net,requests,cfg,state=saturated_fixture()
    state=replace(state,movement_residuals=(1.,),exit_residuals=(1.,))
    result=simulate(net,requests,cfg,ticks=20,initial_state=state,
                    incidents=(Incident('a',0,20,capacity_multiplier=0.),))
    assert result.final_state.completed_count == 0


def test_credit_restart_is_identical_to_uninterrupted_simulation():
    net,requests,cfg,state=saturated_fixture(green=(True,False,True))
    full=simulate(net,requests,cfg,ticks=100,initial_state=state)
    first=simulate(net,requests,cfg,ticks=37,initial_state=state)
    rest=simulate(net,requests,cfg,ticks=63,initial_state=first.final_state)
    assert rest.final_state == full.final_state
    assert state.completed_count == 0
    assert all(0<=c<=1 for group in (rest.final_state.exit_residuals,
               rest.final_state.entry_residuals,rest.final_state.movement_residuals) for c in group)


def test_legacy_mode_remains_an_explicit_counterexample_not_the_default():
    net,requests,cfg,state=saturated_fixture()
    legacy=simulate(net,requests,replace(cfg,node_token_mode='legacy'),ticks=100,initial_state=state)
    new=simulate(net,requests,cfg,ticks=100,initial_state=state)
    assert legacy.final_state.completed_count == 25
    assert new.final_state.completed_count == 50
    assert legacy.fingerprint != new.fingerprint
