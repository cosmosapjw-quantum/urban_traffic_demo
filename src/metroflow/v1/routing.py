"""R02 bounded legal-link routing from R01 delivered beliefs only.

Aggregate path-size logit is a declared behavioral closure, not a system optimum.
Route geometry and cache never own vehicle mass. Proposals preserve the occupied
link; the runtime may apply a suffix only at the explicitly supplied exit boundary.
"""

from collections import defaultdict
from dataclasses import dataclass, asdict
import hashlib
import heapq
import json
import math
from types import MappingProxyType

from ..active_suffix.routing import Arc, destination_potential
from .city import reject, CityContractError


def checked_sum(values):
    try:
        result = math.fsum(values)
    except OverflowError:
        reject('route sum overflow', 'NUMERICAL_ERROR')
    if not math.isfinite(result):
        reject('route sum is nonfinite', 'NUMERICAL_ERROR')
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class RoutingLink:
    id: str
    tail: str
    head: str
    length_m: float
    toll_units: float = 0.0

    def __post_init__(self):
        if (not self.id or not self.tail or not self.head or self.tail == self.head
                or not math.isfinite(self.length_m) or self.length_m <= 0
                or not math.isfinite(self.toll_units) or self.toll_units < 0):
            reject('routing links require positive SI length and nonnegative explicit toll')


@dataclass(frozen=True, slots=True)
class Preference:
    vehicle_class: str
    purpose: str
    time_weight: float = 1.0
    distance_s_per_m: float = 0.0
    money_s_per_unit: float = 0.0
    logit_scale_s: float = 30.0
    path_size_beta: float = 1.0

    def __post_init__(self):
        if (not self.vehicle_class or not self.purpose
                or any(not math.isfinite(x) or x < 0 for x in (
                    self.time_weight, self.distance_s_per_m, self.money_s_per_unit,
                    self.logit_scale_s, self.path_size_beta))
                or self.time_weight <= 0 or self.logit_scale_s <= 0):
            reject('explicit finite preference weights and positive time/logit scale required')


@dataclass(frozen=True, slots=True)
class DecisionBoundary:
    time_s: float
    node_id: str
    kind: str = 'origin'
    incoming_link: str | None = None

    def __post_init__(self):
        if (not math.isfinite(self.time_s) or self.time_s < 0 or not self.node_id
                or self.kind not in ('origin', 'link_exit')
                or (self.kind == 'origin') != (self.incoming_link is None)):
            reject('explicit origin or actual link-exit decision boundary required')


@dataclass(frozen=True, slots=True)
class RouteCommitment:
    graph_id: str
    links: tuple[str, ...]
    position: int = 0  # occupied link, retained during an exit-boundary proposal

    def __post_init__(self):
        if (not isinstance(self.links, tuple) or not self.links
                or isinstance(self.position, bool) or not isinstance(self.position, int)
                or not 0 <= self.position < len(self.links)):
            reject('immutable nonempty commitment and valid occupied position required')


@dataclass(frozen=True, slots=True)
class RouteGeometry:
    links: tuple[str, ...]
    length_m: float


@dataclass(frozen=True, slots=True)
class RouteAlternative:
    geometry: RouteGeometry
    suffix: tuple[str, ...]
    travel_time_s: float  # remaining reported link means; excludes sunk occupied prefix
    generalized_cost_s: float
    path_size: float
    probability: float
    commitment: RouteCommitment | None


@dataclass(frozen=True, slots=True)
class PotentialEntry:
    key: str
    values: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class RoutingState:
    model_id: str
    cache: tuple[PotentialEntry, ...] = ()
    cache_hits: int = 0
    cache_misses: int = 0


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    status: str
    reason: str
    time_s: float
    alternatives: tuple[RouteAlternative, ...]
    fallback: RouteCommitment | None
    cache_hit: bool
    expanded: int
    conditional_regret_s: float | None
    cost_epoch: str


def path_size_probabilities(paths, lengths, costs, preference):
    """PS_r=Σ_e (length_e/length_r)/number_of_candidates_using_e.

    P_r ∝ exp(-C_r/scale) PS_r**beta, using log-sum-exp for stability.
    Duplicate geometry is rejected rather than treated as extra demand support.
    """
    if not paths or len(set(paths)) != len(paths) or len(costs) != len(paths):
        reject('distinct nonempty route candidates and one finite cost each required')
    if any(not p or len(set(p)) != len(p) for p in paths):
        reject('path-size probabilities require nonempty loopless candidates')
    if any(not math.isfinite(lengths[e]) or lengths[e] <= 0 for p in paths for e in p):
        reject('positive finite path-size lengths required')
    if any(not math.isfinite(c) or c < 0 for c in costs):
        reject('finite nonnegative candidate costs required')
    counts = {e: sum(e in p for p in paths) for p in paths for e in p}
    sizes = tuple(checked_sum(lengths[e] / counts[e] for e in p)
                  / checked_sum(lengths[e] for e in p) for p in paths)
    minimum = min(costs)
    logs = tuple(-(c - minimum) / preference.logit_scale_s
                 + preference.path_size_beta * math.log(ps) for c, ps in zip(costs, sizes))
    peak = max(logs)
    weights = tuple(math.exp(x - peak) for x in logs)
    total = checked_sum(weights)
    return sizes, tuple(w / total for w in weights)


class RoutingModel:
    def __init__(self, links, allowed_turns, *, topology_version, k=3,
                 expansion_budget=2000, frontier_budget=10000, graph_budget=10000,
                 cache_budget=32):
        self.links = tuple(links)
        self.turns = frozenset(allowed_turns)
        budgets = (k, expansion_budget, frontier_budget, graph_budget, cache_budget)
        if (any(isinstance(x, bool) or not isinstance(x, int) for x in budgets)
                or not 1 <= k <= 3 or expansion_budget < 0
                or min(frontier_budget, graph_budget, cache_budget) < 1 or not topology_version):
            reject('K<=3 and explicit nonnegative work/positive storage budgets required')
        if len(self.links) + len(self.turns) > graph_budget:
            reject('routing graph budget exceeded', 'BLOCKED_RESOURCE')
        self.ids = MappingProxyType({e.id: e for e in self.links})
        if len(self.ids) != len(self.links):
            reject('duplicate routing link')
        for a, b in self.turns:
            if a not in self.ids or b not in self.ids or self.ids[a].head != self.ids[b].tail:
                reject('turn permission requires adjacent registered directed links')
        self.arcs = tuple(Arc(e.id, e.tail, e.head) for e in self.links)
        successors = defaultdict(list)
        for a, b in self.turns:
            successors[a].append(b)
        self.succ = MappingProxyType({e.id: tuple(sorted(successors[e.id])) for e in self.links})
        self.k, self.expansion_budget = k, expansion_budget
        self.frontier_budget, self.cache_budget = frontier_budget, cache_budget
        self.graph_id = digest(dict(version=topology_version,
                                    links=sorted((asdict(e) for e in self.links), key=lambda e: e['id']),
                                    turns=sorted(self.turns)))
        self.identity = digest((self.graph_id, budgets, 'R02_path_size_logit_v1'))

    @classmethod
    def from_lanegroups(cls, contract, **kwargs):
        return cls(tuple(RoutingLink(g.id, g.tail, g.head, g.physics.length_m)
                         for g in contract.groups), contract.allowed_turns,
                   topology_version=contract.city_identity, **kwargs)

    def initial(self):
        return RoutingState(self.identity)

    def _legal(self, path, origin, destination, incoming=None, banned=()):
        if not path:
            return origin == destination
        if (any(e not in self.ids for e in path) or self.ids[path[0]].tail != origin
                or self.ids[path[-1]].head != destination
                or any((a, b) not in self.turns for a, b in zip(path, path[1:]))
                or (incoming is not None and (incoming, path[0]) not in self.turns)):
            return False
        nodes = (origin,) + tuple(self.ids[e].head for e in path)
        return len(set(nodes)) == len(nodes) and not set(nodes).intersection(banned)

    def _costs(self, observation, preference, boundary):
        if (observation.time_s != boundary.time_s
                or observation.decision != ('origin' if boundary.kind == 'origin' else 'en_route')):
            reject('cost observation must match this decision boundary and time')
        rows = [c for c in observation.costs if c.key.vehicle_class == preference.vehicle_class]
        if (any(c.key.kind != 'link' for c in rows)
                or len({c.key.id for c in rows}) != len(rows)
                or {c.key.id for c in rows} != set(self.ids)):
            reject('one delivered/prior link cost per graph link and selected class required; route totals cannot be decomposed')
        for c in rows:
            if (math.isnan(c.seconds) or c.seconds < 0 or not c.measure or not c.version
                    or c.status not in ('DELIVERED', 'DECLARED_PRIOR')
                    or (c.status == 'DELIVERED' and (
                        c.stamp_s is None or c.delivered_s is None or c.age_s is None
                        or c.stamp_s < 0 or c.stamp_s > boundary.time_s
                        or c.delivered_s < c.stamp_s or c.delivered_s > boundary.time_s
                        or not math.isclose(c.age_s, boundary.time_s - c.stamp_s)))):
                reject('invalid, future or undelivered routing observation')
        physical = {c.key.id: c.seconds for c in rows}
        generalized = {e.id: preference.time_weight * physical[e.id]
                       + preference.distance_s_per_m * e.length_m
                       + preference.money_s_per_unit * e.toll_units for e in self.links}
        if any(math.isfinite(physical[e]) and not math.isfinite(generalized[e]) for e in physical):
            reject('generalized cost overflow', 'NUMERICAL_ERROR')
        epoch = digest(sorted((asdict(c) for c in rows), key=lambda c: c['key']['id']))
        return physical, generalized, epoch

    def _search(self, costs, V, origin, destination, incoming, banned):
        if origin == destination:
            return ((),), 0, None
        heap = []
        for e in self.links:
            if (e.tail == origin and math.isfinite(V[e.id]) and e.head not in banned
                    and e.head != origin and (incoming is None or (incoming, e.id) in self.turns)):
                heapq.heappush(heap, (V[e.id], costs[e.id], (e.id,), (origin, e.head)))
        found, expanded = [], 0
        if len(heap) > self.frontier_budget:
            return (), 0, 'frontier budget'
        while heap:
            if len(found) >= self.k:
                cutoff = checked_sum(costs[e] for e in found[-1])
                if heap[0][0] > cutoff and not math.isclose(heap[0][0], cutoff, rel_tol=1e-12, abs_tol=1e-12):
                    break
            if expanded >= self.expansion_budget:
                return (), expanded, 'expansion budget before complete candidate/tie boundary'
            _, cost, path, visited = heapq.heappop(heap)
            expanded += 1
            if self.ids[path[-1]].head == destination:
                found.append(path)
                if len(found) > self.k:
                    return (), expanded, 'cost tie exceeds K; ID-biased truncation refused'
                continue
            for j in self.succ[path[-1]]:
                head = self.ids[j].head
                if head in visited or head in banned or not math.isfinite(V[j]):
                    continue
                if len(heap) >= self.frontier_budget:
                    return (), expanded, 'frontier budget'
                heapq.heappush(heap, (checked_sum((cost, V[j])), checked_sum((cost, costs[j])),
                                      path + (j,), visited + (head,)))
        return tuple(found), expanded, None

    def _potential(self, costs, destination):
        maximum = max((c for c in costs.values() if math.isfinite(c)), default=1.0)
        scale = maximum if maximum > 1e250 else 1.0
        values = destination_potential(self.arcs, {k:v / scale for k,v in costs.items()},
                                       destination, self.turns)
        result = {}
        for key, value in values.items():
            result[key] = value * scale
            if math.isfinite(value) and not math.isfinite(result[key]):
                reject('destination potential overflow', 'NUMERICAL_ERROR')
        return result

    def decide(self, state, observation, boundary, preference, destination,
               *, current=None, baseline=()):
        try:
            return self._decide(state, observation, boundary, preference, destination,
                                current=current, baseline=baseline)
        except CityContractError as exc:
            exc.checkpoint = state
            raise

    def _decide(self, state, observation, boundary, preference, destination,
               *, current=None, baseline=()):
        if state.model_id != self.identity or len(state.cache) > self.cache_budget:
            reject('routing state belongs to another graph/configuration')
        prefix, banned = (), ()
        if boundary.kind == 'link_exit':
            if (current is None or current.graph_id != self.graph_id
                    or any(e not in self.ids for e in current.links)
                    or not self._legal(current.links, self.ids[current.links[0]].tail,
                                       self.ids[current.links[-1]].head)
                    or current.links[current.position] != boundary.incoming_link
                    or self.ids[boundary.incoming_link].head != boundary.node_id):
                reject('link-exit boundary must match actual occupied committed link')
            prefix = current.links[:current.position + 1]
            banned = (self.ids[prefix[0]].tail,) + tuple(self.ids[e].head for e in prefix[:-1])
            baseline = current.links[current.position + 1:]
        elif current is not None:
            reject('occupied route cannot be changed at an origin boundary')
        baseline = tuple(baseline)
        physical, costs, epoch = self._costs(observation, preference, boundary)
        fallback = None
        if (self._legal(baseline, boundary.node_id, destination, boundary.incoming_link, banned)
                and all(math.isfinite(costs[e]) for e in baseline) and (prefix or baseline)):
            fallback = current if current is not None else RouteCommitment(self.graph_id, baseline)
        key = digest((self.graph_id, destination, asdict(preference), epoch))
        entry = next((e for e in state.cache if e.key == key), None)
        hit = entry is not None
        V = dict(entry.values) if hit else self._potential(costs, destination)
        paths, expanded, failure = self._search(costs, V, boundary.node_id, destination,
                                                boundary.incoming_link, banned)
        if failure:
            return state, RoutingDecision('BLOCKED_RESOURCE', failure, boundary.time_s, (),
                                          fallback, hit, expanded, None, epoch)
        cache = tuple(e for e in state.cache if e.key != key) + (PotentialEntry(key, tuple(sorted(V.items()))),)
        new_state = RoutingState(self.identity, cache[-self.cache_budget:],
                                 state.cache_hits + int(hit), state.cache_misses + int(not hit))
        if not paths:
            topological = destination_potential(self.arcs, dict.fromkeys(self.ids, 1.0), destination, self.turns)
            # This topological test is an upper reachability bound with loop avoidance.
            # A graph route can exist while the observer has no finite supported path.
            starts = [e.id for e in self.links if e.tail == boundary.node_id and
                      (boundary.incoming_link is None or (boundary.incoming_link, e.id) in self.turns)]
            connected = any(math.isfinite(topological[e]) for e in starts)
            status = 'NO_PERCEIVED_PATH' if connected else 'PHYSICAL_UNREACHABLE'
            return new_state, RoutingDecision(status, 'external wait; no teleport or mass deletion',
                                              boundary.time_s, (), None, hit, expanded, None, epoch)
        if paths == ((),):
            status = 'ARRIVED_AT_NODE' if current is not None else 'LOCAL_ACTIVITY_REQUIRED'
            return new_state, RoutingDecision(status, 'same node is not automatic trip completion',
                                              boundary.time_s, (), current, hit, expanded, None, epoch)
        generalized = tuple(checked_sum(costs[e] for e in p) for p in paths)
        lengths = {e.id: e.length_m for e in self.links}
        sizes, probabilities = path_size_probabilities(paths, lengths, generalized, preference)
        choices = []
        for path, cost, ps, probability in zip(paths, generalized, sizes, probabilities):
            full = prefix + path
            commitment = RouteCommitment(self.graph_id, full, current.position if current else 0)
            choices.append(RouteAlternative(RouteGeometry(full, checked_sum(lengths[e] for e in full)),
                                            path, checked_sum(physical[e] for e in path), cost,
                                            ps, probability, commitment))
        regret = (checked_sum(costs[e] for e in baseline) - min(generalized)) if fallback else None
        changed = current is not None and any(prefix + p != current.links for p in paths)
        reason = ('legal suffix alternatives after occupied link; delivered cost epoch ' + epoch
                  if changed else 'origin/unchanged suffix candidates from delivered cost epoch ' + epoch)
        return new_state, RoutingDecision('PROPOSED_SUFFIX' if changed else 'CANDIDATES', reason,
                                          boundary.time_s, tuple(choices), fallback, hit, expanded,
                                          regret, epoch)
