"""R02 legal decisions, aggregate path probabilities and immutable commitments."""

from dataclasses import replace
import math
import pickle
import pytest

from metroflow.active_suffix.routing import braess_reference
from metroflow.v1.city import CityContractError
from metroflow.v1.information import PriorCost, InformationModel, Channel, Report
from metroflow.v1.observations import CostKey, CostObservation
from metroflow.v1.routing import (
    RoutingLink, RoutingModel, Preference, DecisionBoundary, RouteCommitment,
    path_size_probabilities,
)

LINKS = (RoutingLink('oa', 'O', 'A', 100), RoutingLink('ad', 'A', 'D', 100),
         RoutingLink('ob', 'O', 'B', 100), RoutingLink('bd', 'B', 'D', 100),
         RoutingLink('ab', 'A', 'B', 100))
TURNS = (('oa', 'ad'), ('oa', 'ab'), ('ab', 'bd'), ('ob', 'bd'))
PREF = Preference('car', 'work')
MEASURE = 'completed conditional link entry-to-exit mean; all link holds once'


def model(**kw):
    return RoutingModel(LINKS, TURNS, topology_version='fixture-v1', **kw)


def info(costs=None, now=0, enroute=False, links=LINKS, vehicle_class='car'):
    costs = costs or dict(oa=10, ad=10, ob=12, bd=12, ab=20)
    priors = tuple(PriorCost(CostKey('link', e.id, vehicle_class), costs[e.id], 'prior-v1', MEASURE)
                   for e in links)
    m = InformationModel(priors, ())
    return m.observe(m.advance(m.initial(), now), (0, 0), decision='en_route' if enroute else 'origin')


def decide(m, costs=None, **kw):
    return m.decide(m.initial(), info(costs), DecisionBoundary(0, 'O'), PREF, 'D', **kw)


def test_candidates_legal_and_probabilities_conserve_unit_mass():
    m = model()
    _, d = decide(m)
    assert d.status == 'CANDIDATES'
    assert {a.suffix for a in d.alternatives} == {('oa', 'ad'), ('ob', 'bd'), ('oa', 'ab', 'bd')}
    assert math.fsum(a.probability for a in d.alternatives) == pytest.approx(1)
    assert all(a.probability > 0 for a in d.alternatives)
    assert d.alternatives[0].travel_time_s == 20
    assert all(a.commitment.graph_id == m.graph_id for a in d.alternatives)


def test_path_size_correction_is_independently_computed():
    paths = (('a', 'b'), ('a', 'c'), ('d',))
    sizes, probabilities = path_size_probabilities(paths, dict.fromkeys('abcd', 1), (20, 20, 20), PREF)
    assert sizes == pytest.approx((.75, .75, 1))
    assert probabilities == pytest.approx((.3, .3, .4))
    with pytest.raises(CityContractError):
        path_size_probabilities((paths[0], paths[0]), dict.fromkeys('abcd', 1), (20, 20), PREF)


def test_candidate_id_relabeling_has_no_physical_share_bias():
    m = model()
    costs = dict.fromkeys((e.id for e in LINKS), 10)
    _, a = decide(m, costs)
    rename = dict(oa='z', ad='y', ob='x', bd='w', ab='v')
    reverse = {v: k for k, v in rename.items()}
    links = tuple(replace(e, id=rename[e.id]) for e in reversed(LINKS))
    n = RoutingModel(links, tuple((rename[a], rename[b]) for a, b in TURNS), topology_version='renamed')
    _, b = n.decide(n.initial(), info({rename[k]: v for k, v in costs.items()}, links=links),
                    DecisionBoundary(0, 'O'), PREF, 'D')
    shares = {a.suffix: a.probability for a in a.alternatives}
    assert {tuple(reverse[e] for e in a.suffix): a.probability for a in b.alternatives} == pytest.approx(shares)


def test_equal_cost_k_cut_is_explicit_budget_failure_not_id_selection():
    m = model(k=1)
    costs = dict(oa=10, ad=10, ob=10, bd=10, ab=100)
    s, d = decide(m, costs, baseline=('ob', 'bd'))
    assert s == m.initial()
    assert d.status == 'BLOCKED_RESOURCE' and 'tie' in d.reason
    assert d.fallback.links == ('ob', 'bd')
    assert not d.alternatives


def test_more_than_three_equal_paths_wait_instead_of_truncating_by_id():
    links = tuple(RoutingLink(str(i), 'O', 'D', 10) for i in range(4))
    m = RoutingModel(links, (), topology_version='four')
    _, d = m.decide(m.initial(), info(dict.fromkeys((e.id for e in links), 1), links=links),
                    DecisionBoundary(0, 'O'), PREF, 'D')
    assert d.status == 'BLOCKED_RESOURCE' and d.fallback is None


def test_preference_units_tolls_and_time_are_distinct():
    links = tuple(replace(e, toll_units=100 if e.id == 'oa' else 0) for e in LINKS)
    m = RoutingModel(links, TURNS, topology_version='tolls')
    _, d = m.decide(m.initial(), info(), DecisionBoundary(0, 'O'),
                    replace(PREF, money_s_per_unit=2, distance_s_per_m=.1), 'D')
    a = next(a for a in d.alternatives if a.suffix == ('oa', 'ad'))
    assert a.travel_time_s == 20
    assert a.generalized_cost_s == 240
    assert d.alternatives[0].suffix == ('ob', 'bd')


def test_closure_reopen_and_new_edge_comparison():
    m = model()
    costs = dict(oa=10, ad=10, ob=12, bd=12, ab=1)
    _, before = decide(m, costs)
    assert before.alternatives[0].suffix == ('oa', 'ad')
    closed = dict(costs, ad=math.inf)
    _, during = decide(m, closed)
    assert all('ad' not in a.suffix for a in during.alternatives)
    assert decide(m, costs)[1] == before
    oldlinks = LINKS[:-1]
    old = RoutingModel(oldlinks, (('oa', 'ad'), ('ob', 'bd')), topology_version='old')
    oldcosts = {k:v for k,v in costs.items() if k != 'ab'}
    _, d = old.decide(old.initial(), info(oldcosts, links=oldlinks), DecisionBoundary(0, 'O'), PREF, 'D')
    assert len(d.alternatives) == 2 and len(before.alternatives) == 3


def test_enroute_reroute_only_at_exit_and_occupied_prefix_retained():
    m = model()
    current = RouteCommitment(m.graph_id, ('oa', 'ad'))
    original = pickle.dumps(current)
    costs = dict(oa=10, ad=100, ob=12, bd=12, ab=1)
    _, d = m.decide(m.initial(), info(costs, now=10, enroute=True),
                    DecisionBoundary(10, 'A', 'link_exit', 'oa'), PREF, 'D', current=current)
    assert d.status == 'PROPOSED_SUFFIX' and d.time_s == 10
    assert d.alternatives[0].suffix == ('ab', 'bd')
    assert d.alternatives[0].commitment.links == ('oa', 'ab', 'bd')
    assert d.alternatives[0].commitment.position == 0
    assert d.conditional_regret_s == 87
    assert pickle.dumps(current) == original
    with pytest.raises(CityContractError, match='occupied route'):
        m.decide(m.initial(), info(costs, now=10), DecisionBoundary(10, 'O'), PREF, 'D', current=current)
    with pytest.raises(CityContractError, match='actual occupied'):
        m.decide(m.initial(), info(costs, now=10, enroute=True),
                 DecisionBoundary(10, 'B', 'link_exit', 'ob'), PREF, 'D', current=current)


def test_turn_permissions_enforced_even_if_forbidden_route_is_cheaper():
    m = RoutingModel(LINKS, (('oa', 'ad'), ('ob', 'bd')), topology_version='no_shortcut_turn')
    _, d = decide(m, dict(oa=1, ad=100, ob=10, bd=10, ab=0))
    assert d.alternatives[0].suffix == ('ob', 'bd')
    assert all('ab' not in a.suffix for a in d.alternatives)


def test_no_perceived_path_is_not_proof_of_physical_unreachability():
    _, d = decide(model(), dict.fromkeys((e.id for e in LINKS), math.inf))
    assert d.status == 'NO_PERCEIVED_PATH' and not d.alternatives
    m = RoutingModel(LINKS, (), topology_version='no_turns')
    _, d = decide(m)
    assert d.status == 'PHYSICAL_UNREACHABLE'


@pytest.mark.parametrize('kw', [{'expansion_budget': 0}, {'frontier_budget': 1}])
def test_budget_preserves_valid_baseline_or_external_wait(kw):
    m = model(**kw)
    state = m.initial()
    after, d = decide(m, baseline=('oa', 'ad'))
    assert after == state and d.status == 'BLOCKED_RESOURCE'
    assert d.fallback.links == ('oa', 'ad')
    assert decide(m)[1].fallback is None


def test_budget_enroute_keeps_original_commitment():
    m = model(expansion_budget=0)
    current = RouteCommitment(m.graph_id, ('oa', 'ad'))
    after, d = m.decide(m.initial(), info(now=10, enroute=True),
                        DecisionBoundary(10, 'A', 'link_exit', 'oa'), PREF, 'D', current=current)
    assert d.fallback is current and after == m.initial()


def test_destination_potential_shared_across_origins_and_cache_eviction_safe():
    m = model(cache_budget=1)
    obs = info()
    state, d = m.decide(m.initial(), obs, DecisionBoundary(0, 'O'), PREF, 'D')
    commitment = d.alternatives[0].commitment
    before = pickle.dumps(commitment)
    state, d = m.decide(state, obs, DecisionBoundary(0, 'B'), PREF, 'D')
    assert d.cache_hit and state.cache_hits == 1
    state, d = m.decide(state, obs, DecisionBoundary(0, 'O'), replace(PREF, purpose='service'), 'D')
    assert not d.cache_hit and len(state.cache) == 1
    assert pickle.dumps(commitment) == before
    assert not any(hasattr(entry, 'mass') for entry in state.cache)


def test_cache_invalidation_class_cost_version_graph_and_restart():
    m = model()
    obs = info()
    state, _ = m.decide(m.initial(), obs, DecisionBoundary(0, 'O'), PREF, 'D')
    a = m.decide(state, obs, DecisionBoundary(0, 'O'), PREF, 'D')
    b = m.decide(pickle.loads(pickle.dumps(state)), obs, DecisionBoundary(0, 'O'), PREF, 'D')
    assert a == b and a[1].cache_hit
    changed = replace(obs, costs=tuple(replace(c, version='new') for c in obs.costs))
    assert not m.decide(state, changed, DecisionBoundary(0, 'O'), PREF, 'D')[1].cache_hit
    bus = info(vehicle_class='bus')
    assert not m.decide(state, bus, DecisionBoundary(0, 'O'), replace(PREF, vehicle_class='bus'), 'D')[1].cache_hit
    other = RoutingModel(LINKS, TURNS, topology_version='changed')
    with pytest.raises(CityContractError, match='another graph'):
        other.decide(state, obs, DecisionBoundary(0, 'O'), PREF, 'D')


def test_route_totals_cannot_be_silently_decomposed_into_link_costs():
    m = model()
    o = info()
    with pytest.raises(CityContractError, match='decomposed'):
        m.decide(m.initial(), replace(o, costs=tuple(replace(c, key=replace(c.key, kind='route'))
                                                    for c in o.costs)), DecisionBoundary(0, 'O'), PREF, 'D')
    with pytest.raises(CityContractError, match='boundary'):
        m.decide(m.initial(), o, DecisionBoundary(1, 'O'), PREF, 'D')


def test_paired_world_routing_from_R01_hidden_remote_incident_is_identical():
    priors = tuple(PriorCost(CostKey('link', e.id, 'car'), 10, 'static', MEASURE) for e in LINKS)
    channel = Channel('local', 'direct', tuple(p.key for p in priors), 10, 0, 10, 100)
    im = InformationModel(priors, (channel,))
    m = model()
    worlds = []
    for value in (1, 1000):
        report = CostObservation(CostKey('link', 'ad', 'car'), value, 10, 0, 10, 1,
                                 (1000., 0.), 'sensor', 'v1', 'same-sample', MEASURE)
        s = im.advance(im.initial(), 20, (Report('local', report),))
        worlds.append(m.decide(m.initial(), im.observe(s, (0, 0)), DecisionBoundary(20, 'O'), PREF, 'D'))
    assert worlds[0] == worlds[1]


def test_stable_softmax_extreme_costs_and_duplicate_geometry_rejected():
    _, p = path_size_probabilities((('a',), ('b',)), {'a':1,'b':1}, (1e200, 1e200), PREF)
    assert p == (.5, .5)
    _, p = path_size_probabilities((('a',), ('b',)), {'a':1,'b':1}, (0, 1e200), PREF)
    assert p == (1, 0)


def test_static_braess_65_to_80_minutes_not_dynamic_validation():
    before, after = braess_reference(), braess_reference(shortcut=True)
    assert before['mean_cost_min'] == pytest.approx(65, abs=.05)
    assert after['mean_cost_min'] == pytest.approx(80, abs=.05)
    assert after['relative_wardrop_gap'] < .002


def test_real_T03_adapter_and_routing_do_not_modify_T04_physics():
    from metroflow.v1.timing_oracles import timing_fixture
    from metroflow.v1.lanegroups import LaneGroupContract
    p = timing_fixture(.1)
    n = p.network
    contract = LaneGroupContract('fixture', n.groups, frozenset({('0', '1')}), (), (), (), ())
    m = RoutingModel.from_lanegroups(contract)
    state = p.advance(p.initial(), 1)
    before = pickle.dumps(state)
    links = m.links
    costs = {e.id:e.length_m/10 for e in links}
    _, d = m.decide(m.initial(), info(costs, now=1, links=links),
                    DecisionBoundary(1, links[0].tail), PREF, links[-1].head)
    assert d.alternatives
    assert pickle.dumps(state) == before


@pytest.mark.parametrize('kw', [{'k':4}, {'k':True}, {'cache_budget':0}, {'graph_budget':1}])
def test_invalid_configuration_is_explicit(kw):
    with pytest.raises(CityContractError):
        model(**kw)


def test_same_origin_destination_requires_local_activity_not_zero_time_completion():
    m = model()
    _, d = m.decide(m.initial(), info(), DecisionBoundary(0, 'O'), PREF, 'O')
    assert d.status == 'LOCAL_ACTIVITY_REQUIRED' and not d.alternatives


def test_arrival_boundary_is_distinct_from_new_origin_and_keeps_occupied_link():
    m = model()
    current = RouteCommitment(m.graph_id, ('oa', 'ad'), 1)
    _, d = m.decide(m.initial(), info(now=50, enroute=True),
                    DecisionBoundary(50, 'D', 'link_exit', 'ad'), PREF, 'D', current=current)
    assert d.status == 'ARRIVED_AT_NODE' and d.fallback is current


def test_numerical_cost_overflow_is_not_physical_unreachability_and_keeps_checkpoint():
    m = model()
    state = m.initial()
    with pytest.raises(CityContractError) as error:
        m.decide(state, info(dict.fromkeys((e.id for e in LINKS), 1e308)),
                 DecisionBoundary(0, 'O'), PREF, 'D')
    assert error.value.status == 'NUMERICAL_ERROR'
    assert error.value.checkpoint is state
