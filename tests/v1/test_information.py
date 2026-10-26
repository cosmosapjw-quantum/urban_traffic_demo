"""R01 observable nonanticipation and same-physics completed costs."""

from dataclasses import replace
import math
import pickle
import pytest
from metroflow.active_suffix.common import BudgetExceeded
from metroflow.v1.city import CityContractError
from metroflow.v1.information import Channel, PriorCost, Report, InformationModel
from metroflow.v1.observations import (
    CostKey, CostObservation, completed_route_observations, conditional_eta_error,
)
from metroflow.v1.timing_oracles import timing_fixture

KEY = CostKey('route', 'trip', 'car')
MEASURE = 'completed conditional birth-to-exit mean; includes all recorded holds'


def observation(seconds=90, stamp=10, xy=(0., 0.)):
    return CostObservation(KEY, seconds, stamp, 0, stamp, 1, xy, 'sensor', 'physical-v1', 'fixture-sample')


def channel(kind='direct', radius=100, latency=0, propagation=10, age=100):
    return Channel(kind, kind, (KEY,), radius, latency, propagation, age)


def model(*channels, budget=100):
    return InformationModel((PriorCost(KEY, 21, 'baseline-v1', MEASURE),),
                            channels or (channel(),), record_budget=budget)


def value(m, s, xy=(0, 0), decision='origin'):
    return m.observe(s, xy, decision=decision).costs[0]


def test_paired_worlds_remote_incident_and_refresh_clock_do_not_leak():
    m = model(channel(radius=20))
    a = m.advance(m.initial(), 15, (Report('direct', observation(90, xy=(100., 0.))),))
    b = m.advance(m.initial(), 15, (Report('direct', observation(900, xy=(100., 0.))),))
    assert value(m, a) == value(m, b)
    assert value(m, a).status == 'DECLARED_PRIOR'
    # Decisions are caller fixed boundaries; no incident-triggered refresh method.
    assert m.observe(a, (0, 0)).time_s == m.observe(b, (0, 0)).time_s == 15


def test_direct_local_and_enroute_location_have_explicit_support():
    m = model(channel(radius=20))
    s = m.advance(m.initial(), 12, (Report('direct', observation(xy=(10., 0.))),))
    assert value(m, s).seconds == 90
    assert value(m, s, (100, 0), 'en_route').seconds == 21
    assert value(m, s).age_s == 2
    assert m.observe(s, (0, 0)).coverage_fraction == 1


def test_remote_server_propagation_and_latency_exact_boundary():
    m = model(channel('server', math.inf, 2, 100))
    r = Report('server', observation(xy=(1000., 0.)))
    s = m.advance(m.initial(), 21.999, (r,))
    assert value(m, s).seconds == 21
    s = m.advance(s, 22)
    assert value(m, s).seconds == 90
    assert value(m, s).delivered_s == 22


def test_newer_undelivered_report_does_not_hide_delivered_predecessor():
    m = model(channel('v2v', 100, 5))
    s = m.advance(m.initial(), 20, (
        Report('v2v', observation(50, 10)), Report('v2v', observation(500, 19))))
    assert value(m, s).seconds == 50
    assert value(m, m.advance(s, 24)).seconds == 500


def test_expiry_is_deterministic_and_prior_is_never_present_truth():
    m = model(channel(age=5))
    s = m.advance(m.initial(), 10, (Report('direct', observation()),))
    assert value(m, s).seconds == 90
    assert value(m, m.advance(s, 15)).seconds == 90
    expired = m.advance(s, 15.001)
    assert expired.reports == ()
    assert value(m, expired).source == 'DECLARED_PRIOR'


def test_history_channel_is_explicit_and_channel_precedence_declared():
    m = model(channel('history', math.inf), channel())
    s = m.advance(m.initial(), 11, (
        Report('direct', observation(70)), Report('history', observation(40))))
    assert value(m, s).seconds == 40
    assert value(m, s).source.startswith('history:')


def test_future_unfinished_and_unlike_estimands_rejected():
    m = model()
    with pytest.raises(CityContractError, match='future'):
        m.advance(m.initial(), 9, (Report('direct', observation()),))
    with pytest.raises(CityContractError):
        replace(observation(), end_s=11)
    with pytest.raises(CityContractError, match='estimands'):
        m.advance(m.initial(), 10, (Report('direct', replace(observation(), measure='moving only')),))


def test_coverage_class_isolation_and_no_truth_fallback():
    m = model()
    with pytest.raises(CityContractError, match='coverage'):
        m.advance(m.initial(), 10, (Report('direct', replace(observation(), key=replace(KEY, vehicle_class='bus'))),))
    assert value(m, m.advance(m.initial(), 1000)).seconds == 21


def test_budget_failure_checkpoint_resume_without_averaging_marks():
    m = model(budget=1)
    s = m.advance(m.initial(), 10, (Report('direct', observation()),))
    with pytest.raises(BudgetExceeded) as caught:
        m.advance(s, 11, (Report('direct', observation(100, 11)),))
    assert caught.value.checkpoint is s
    assert s == pickle.loads(pickle.dumps(s))
    # Pruning old history permits a new report; no mass or time mark coarsening.
    later = m.advance(s, 111, (Report('direct', observation(100, 111)),))
    assert value(m, later).seconds == 100


def test_duplicate_delivery_is_idempotent_and_split_resume_identical():
    m = model()
    r = Report('direct', observation())
    a = m.advance(m.initial(), 12, (r, r))
    b = m.advance(m.advance(m.initial(), 10, (r,)), 12, (r,))
    assert a == b
    assert len(a.reports) == 1
    other = model(channel(latency=1))
    with pytest.raises(CityContractError, match='another contract'):
        other.observe(a, (0, 0))


def test_completed_route_adapter_same_physics_no_double_signal_or_queue():
    physical = timing_fixture(.1, window=0, mass=1)
    initial = physical.initial()
    partial = physical.advance(initial, 10)
    assert completed_route_observations(physical, partial, since_s=0,
                                        sensor_xy={'trip': (0., 0.)}, version='T04') == ()
    final = physical.advance(partial, 30)
    before = pickle.dumps(final)
    obs, = completed_route_observations(physical, final, since_s=0,
                                        sensor_xy={'trip': (0., 0.)}, version='T04')
    assert obs.seconds == pytest.approx(physical.report(final)['whole_population_mean_s'])
    m = InformationModel((PriorCost(obs.key, 21, 'static', obs.measure),),
                         (replace(channel(), coverage=(obs.key,)),))
    s = m.advance(m.initial(), 30, (Report('direct', obs),))
    assert value(m, s).seconds == obs.seconds
    assert pickle.dumps(final) == before
    assert physical.advance(partial, 30) == final
    assert completed_route_observations(physical, final, since_s=30,
                                        sensor_xy={'trip': (0., 0.)}, version='T04') == ()


def test_error_requires_matching_population_and_handles_unavailable():
    o = observation()
    assert conditional_eta_error(replace(o, seconds=95), o) == 5
    assert conditional_eta_error(replace(o, seconds=math.inf), o) is None
    with pytest.raises(CityContractError):
        conditional_eta_error(replace(o, measure='other population'), o)


@pytest.mark.parametrize('kind,radius', [('direct', math.inf), ('v2v', math.inf), ('unknown', 1)])
def test_invalid_channels_reject(kind, radius):
    with pytest.raises(CityContractError):
        channel(kind, radius)


def test_ambiguous_same_timestamp_reports_rejected_without_id_based_cost_choice():
    m = model()
    with pytest.raises(CityContractError, match='conflicting'):
        m.advance(m.initial(), 10, (Report('direct', observation(40)),
                                    Report('direct', observation(90))))


def test_eta_error_cannot_reconstruct_cross_population_correlation():
    with pytest.raises(CityContractError):
        conditional_eta_error(observation(), replace(observation(), population='other'))
