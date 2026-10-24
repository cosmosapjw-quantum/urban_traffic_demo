"""Scientific audits through explicit observation and realization contracts."""
import math
import pytest
from metroflow.audit_observables import speed_measure, ring_requirements, ovm_modes, edie_observables


def test_space_and_entry_measures_must_not_be_identified():
    spatial=speed_measure((5.,15.),(.5,.5),100.,measure='space')
    entering=speed_measure((5.,15.),(.5,.5),100.,measure='entry')
    assert spatial['entry_weights']==pytest.approx((.25,.75))
    assert spatial['mean_entry_trip_s']==pytest.approx(10.)
    assert entering['space_weights']==pytest.approx((.75,.25))
    assert entering['space_mean_mps']==pytest.approx(7.5)
    assert entering['mean_entry_trip_s']==pytest.approx(40/3)


def test_stationary_measure_conversion_rejects_stopped_atoms():
    with pytest.raises(ValueError,match='positive'):
        speed_measure((0.,10.),(.5,.5),100.,measure='space')


def test_pair_mass_scaling_needs_corresponding_lane_length():
    result=ring_requirements((100000.,),(20.,),(10.,),(10.,),5.,1000.)
    assert result['required_lane_length_m']==2500000.
    assert not result['length_consistent']
    assert result['velocity_marginal_l1']==0.
    assert not result['necessary_conditions_pass']


def test_leader_follower_marginals_are_an_independent_necessary_gate():
    result=ring_requirements((1.,1.),(20.,20.),(5.,15.),(5.,5.),5.,50.)
    assert result['length_consistent']
    assert result['velocity_marginal_l1']==pytest.approx(1.)
    assert not result['necessary_conditions_pass']
    ok=ring_requirements((1.,1.),(20.,20.),(5.,15.),(15.,5.),5.,50.)
    assert ok['necessary_conditions_pass']
    assert ok['sufficient_realizability_proved'] is False


def test_nominal_ovm_growth_and_damping_are_different_from_safety():
    k=2*math.pi/100
    unstable=ovm_modes(1.,2.,k)
    damped=ovm_modes(1.,2.,k,relative_speed_gain_s=1.)
    assert unstable['largest_real_part_per_s']>0
    assert damped['largest_real_part_per_s']<0
    assert unstable['longwave_real_k2_coefficient_per_s']==pytest.approx(1.5)
    assert damped['longwave_real_k2_coefficient_per_s']==pytest.approx(-.5)


def test_space_time_observables_have_explicit_geometry_and_clock():
    values=edie_observables(6000.,60000.,1000.,60.)
    assert values['density_veh_m']==pytest.approx(.1)
    assert values['flow_veh_s']==pytest.approx(1.)
    assert values['space_time_mean_mps']==pytest.approx(10.)
