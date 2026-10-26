"""Small R02 causal/commitment probes; classical Braess remains a static oracle."""

from .routing import RoutingLink, RoutingModel, Preference, DecisionBoundary, RouteCommitment
from .information import InformationModel, PriorCost
from .observations import CostKey
from ..active_suffix.routing import braess_reference


def routing_oracles():
    before = braess_reference()
    after = braess_reference(shortcut=True)
    rows = [dict(case='static_braess_minutes', status='PASS' if
                 abs(before['mean_cost_min'] - 65) < .05 and abs(after['mean_cost_min'] - 80) < .05
                 else 'NOT_ACCEPTED', before=before, after=after,
                 scope='classical static nonatomic oracle; not dynamic T04 validation')]
    links = (RoutingLink('oa', 'O', 'A', 100), RoutingLink('ad', 'A', 'D', 100),
             RoutingLink('ab', 'A', 'B', 100), RoutingLink('bd', 'B', 'D', 100))
    turns = (('oa', 'ad'), ('oa', 'ab'), ('ab', 'bd'))
    model = RoutingModel(links, turns, topology_version='R02_oracle')
    costs = dict(oa=10, ad=100, ab=1, bd=12)
    im = InformationModel(tuple(PriorCost(CostKey('link', e.id, 'car'), costs[e.id], 'prior',
                                        'conditional link means, all link holds once') for e in links), ())
    observation = im.observe(im.advance(im.initial(), 10), (0, 0), decision='en_route')
    current = RouteCommitment(model.graph_id, ('oa', 'ad'))
    state, result = model.decide(model.initial(), observation,
                                DecisionBoundary(10, 'A', 'link_exit', 'oa'),
                                Preference('car', 'work'), 'D', current=current)
    first = result.alternatives[0]
    rows.append(dict(case='finite_belief_exit_suffix', status='PASS' if
                     first.commitment.links == ('oa', 'ab', 'bd') and first.commitment.position == 0
                     and result.conditional_regret_s == 87 else 'NOT_ACCEPTED',
                     old_path=current.links, proposed_path=first.commitment.links,
                     occupied_link_preserved='oa', time_s=result.time_s,
                     conditional_regret_s=result.conditional_regret_s,
                     probabilities=[a.probability for a in result.alternatives],
                     cache_entries=len(state.cache)))
    limited = RoutingModel(links, turns, topology_version='R02_oracle', expansion_budget=0)
    baseline = RouteCommitment(limited.graph_id, ('oa', 'ad'))
    checkpoint = limited.initial()
    resumed, failure = limited.decide(checkpoint, observation,
                                     DecisionBoundary(10, 'A', 'link_exit', 'oa'),
                                     Preference('car', 'work'), 'D', current=baseline)
    rows.append(dict(case='budget_fallback', status='PASS' if resumed is checkpoint
                     and failure.fallback is baseline and failure.status == 'BLOCKED_RESOURCE'
                     else 'NOT_ACCEPTED', outcome=failure.status,
                     retained_path=failure.fallback.links, checkpoint_unchanged=resumed is checkpoint))
    return rows
