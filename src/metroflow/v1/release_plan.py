"""Bounded, exact traversal of release demand and static legal-turn routes.

Pages are compilation units, never separate traffic simulations. Every activated
route must enter the same live runtime. Caches share immutable geometry/cost
work only; purpose, class, history and birth measures remain attached to each leg.
"""
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
import heapq
import itertools
import math
from types import MappingProxyType

from ..active_suffix.routing import Arc
from ..terrain_city.area_access import Portal
from .access import activity_access
from .city import reject
from .journey import DelayLaw
from .lanegroups import compile_lanegroups


def _positive_budget(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        reject(f'positive integer {name} required', 'CONTRACT_ERROR')


class LegalRouteCache:
    """LRU source trees on directed *link* states with frozen SI second costs.

    A shortest route can revisit a physical node when legal turn restrictions
    require it. No transition outside allowed_turns is added. Eviction only
    recomputes a tree; it does not approximate the selected route or demand.
    Storage: O(max_sources * links + links + legal_turns).
    """
    def __init__(self, arcs, costs, allowed_turns, *, max_sources=8):
        _positive_budget(max_sources, 'source-tree budget')
        arcs = tuple(arcs)
        self.arcs = {a.id: a for a in arcs}
        if len(self.arcs) != len(arcs):
            reject('duplicate route links')
        if not self.arcs:
            reject('route cache requires directed links')
        self.costs = dict(costs)
        if set(self.costs) != set(self.arcs) or any(
                not math.isfinite(x) or x <= 0 for x in self.costs.values()):
            reject('strictly positive finite route costs in seconds required')
        self.outgoing = defaultdict(list)
        self.successors = {key: [] for key in self.arcs}
        self.nodes = set()
        for a in self.arcs.values():
            self.outgoing[a.tail].append(a.id)
            self.nodes.update((a.tail, a.head))
        for a, b in allowed_turns:
            if a not in self.arcs or b not in self.arcs or self.arcs[a].head != self.arcs[b].tail:
                reject('route cache legal turn lacks physical link contact')
            self.successors[a].append(b)
        for values in (*self.outgoing.values(), *self.successors.values()):
            values.sort()
        self.arcs = MappingProxyType(self.arcs)
        self.costs = MappingProxyType(self.costs)
        self.outgoing = MappingProxyType({k: tuple(v) for k,v in self.outgoing.items()})
        self.successors = MappingProxyType({k: tuple(v) for k,v in self.successors.items()})
        self.max_sources = max_sources
        self._trees = OrderedDict()
        self.tree_builds = 0

    @property
    def cached_sources(self):
        return tuple(self._trees)

    def _tree(self, origin):
        if origin in self._trees:
            self._trees.move_to_end(origin)
            return self._trees[origin]
        distance, parent, heap = {}, {}, []
        for key in self.outgoing.get(origin, ()):
            distance[key], parent[key] = self.costs[key], None
            heapq.heappush(heap, (distance[key], key))
        while heap:
            value, key = heapq.heappop(heap)
            if value != distance[key]:
                continue
            for nxt in self.successors[key]:
                candidate = value + self.costs[nxt]
                if candidate < distance.get(nxt, math.inf):
                    distance[nxt], parent[nxt] = candidate, key
                    heapq.heappush(heap, (candidate, nxt))
        targets = {}
        for key, value in distance.items():
            node = self.arcs[key].head
            if (value, key) < targets.get(node, (math.inf, '')):
                targets[node] = (value, key)
        tree = (parent, targets)
        self._trees[origin] = tree
        self.tree_builds += 1
        if len(self._trees) > self.max_sources:
            self._trees.popitem(last=False)
        return tree

    def resolve(self, origin, destination):
        if origin not in self.nodes or destination not in self.nodes:
            reject('unknown route endpoint')
        if origin == destination:
            return ()
        parent, targets = self._tree(origin)
        if destination not in targets:
            return None
        key = targets[destination][1]
        path = []
        while key is not None:
            path.append(key)
            key = parent[key]
        return tuple(reversed(path))


@dataclass(frozen=True, slots=True)
class PlanCursor:
    schedule_identity: str
    offset: int = 0
    materialized_persons: float = 0.0
    materialized_vehicles: float = 0.0
    materialized_cargo_kg: float = 0.0


@dataclass(frozen=True, slots=True)
class PlannedLeg:
    leg: object
    links: tuple | None
    origin_law: DelayLaw | None
    destination_law: DelayLaw | None
    status: str


class ReleasePlan:
    """Exact demand iterator with bounded static route and access-law caches.

    This object does not pretend to bound the number of simultaneous physical
    records. Runtime resource failure must retain its last valid checkpoint and
    this calendar cursor. A page is not evidence of whole-city execution.
    """
    def __init__(self, city, schedule, *, max_sources=8, max_access_laws=128, step_s=1.0):
        if city.identity != schedule.city_identity:
            reject('release plan city and schedule identities differ')
        _positive_budget(max_access_laws, 'access-law cache budget')
        self.city, self.schedule = city, schedule
        self.contract = compile_lanegroups(city, dt_s=step_s)
        arcs = tuple(Arc(g.id, g.tail, g.head) for g in self.contract.groups)
        costs = {g.id: g.physics.length_m / g.physics.speed_mps for g in self.contract.groups}
        self.routes = LegalRouteCache(arcs, costs, self.contract.allowed_turns, max_sources=max_sources)
        self.nodes = {n.id: n for n in city.roadmap.nodes}
        self.gates = defaultdict(list)
        for p in city.portals:
            self.gates[p.block_id].append(p)
        self.max_access_laws = max_access_laws
        self._access = OrderedDict()

    def totals(self):
        """Closed-form full-calendar leg totals, including outward AND return.

        At-home unassigned activity is a separate resident/intent ledger, not a
        trip. These are calendar amounts, not physical releases/completions.
        """
        s = self.schedule
        internal_service = (s.resident_stock * s.service_fraction *
                            (1-s.external_service_fraction) - s.unassigned_service_persons)
        external_service = s.resident_stock*s.service_fraction*s.external_service_fraction
        targets_per_home = ((len(s.jobs) if s.allocated_workers else 0)
            + len(s.services)*(int(internal_service*s.school_share > 0)
                               + int(internal_service*(1-s.school_share) > 0))
            + int(external_service > 0))
        legs = 2*len(s.homes)*len(s.modes)*targets_per_home
        if s.freight_kg:
            legs += len(s.services)
        persons = 2*(s.allocated_workers+internal_service+external_service)
        occupancy = math.fsum(m.share/m.occupancy_persons_veh for m in s.modes
                              if m.occupancy_persons_veh is not None)
        return dict(legs=legs, persons=persons,
                    vehicles=persons*occupancy+s.freight_kg/s.freight_kg_per_vehicle,
                    cargo_kg=s.freight_kg, resident_stock=s.resident_stock,
                    requested_workers=s.requested_workers,
                    allocated_workers=s.allocated_workers, unassigned_workers=s.unassigned_workers)

    def summary(self, cursor):
        self._check_cursor(cursor)
        totals = self.totals()
        return dict(calendar=totals, materialized_legs=cursor.offset,
                    remaining_legs=totals['legs']-cursor.offset,
                    remaining_amounts={unit: totals[unit]-getattr(cursor, 'materialized_'+unit)
                                       for unit in ('persons', 'vehicles', 'cargo_kg')},
                    execution='NOT_RUN',
                    scope='exact compilation coverage; pages must enter one shared live runtime')

    def _check_cursor(self, cursor):
        totals = self.totals()
        if (cursor.schedule_identity != self.schedule.identity or isinstance(cursor.offset, bool)
                or not isinstance(cursor.offset, int) or not 0 <= cursor.offset <= totals['legs']):
            reject('release plan cursor differs from schedule')
        units = ('persons', 'vehicles', 'cargo_kg')
        amounts = tuple(getattr(cursor, 'materialized_'+unit) for unit in units)
        if any(not math.isfinite(x) or x < 0 or x > totals[unit]+1e-9*max(1,totals[unit])
               for unit,x in zip(units,amounts)):
            reject('release plan cursor amount exceeds calendar')
        # A restored cursor must agree with the exact immutable calendar prefix.
        # This costs prefix traversal (no route search or OD array storage).
        if cursor.offset == 0:
            expected = (0.0, 0.0, 0.0)
        elif cursor.offset == totals['legs']:
            expected = tuple(totals[unit] for unit in units)
        else:
            expected = [0.0, 0.0, 0.0]
            for leg in itertools.islice(self.schedule.iter_legs(), cursor.offset):
                for i,unit in enumerate(units):
                    expected[i] += getattr(leg.amounts,unit)
        if any(abs(actual-wanted)>1e-9*max(1,totals[unit])
               for unit,actual,wanted in zip(units,amounts,expected)):
            reject('release plan cursor amount differs from calendar prefix')

    def cursor(self):
        return PlanCursor(self.schedule.identity)

    def _law(self, measure, gate):
        key = (measure, gate)
        if key in self._access:
            self._access.move_to_end(key)
            return self._access[key]
        law, _ = activity_access(measure, (Portal(gate.id, self.nodes[gate.node_id].xyz[:2]),), depth=0)
        result = DelayLaw(law.condition(gate.id)[1])
        self._access[key] = result
        if len(self._access) > self.max_access_laws:
            self._access.popitem(last=False)
        return result

    def resolve(self, leg):
        if any(m is not None and m.city_identity != self.city.identity for m in (leg.origin, leg.destination)):
            reject('planned leg activity belongs to another city')
        if leg.origin is None or leg.destination is None:
            return PlannedLeg(leg, None, None, None, 'PENDING_EXTERNAL_ENDPOINT')
        if leg.intrazonal is not None:
            return PlannedLeg(leg, (), None, leg.intrazonal, 'INTRAZONAL')
        gates = (self.gates[leg.origin.block_id], self.gates[leg.destination.block_id])
        if any(len(g) != 1 for g in gates):
            return PlannedLeg(leg, None, None, None, 'PENDING_PORTAL_POLICY')
        a, b = (g[0] for g in gates)
        links = self.routes.resolve(a.node_id, b.node_id)
        if not links:
            return PlannedLeg(leg, links, None, None, 'PENDING_ROAD_ROUTE')
        return PlannedLeg(leg, links, self._law(leg.origin, a), self._law(leg.destination, b), 'ROUTED')

    def take(self, cursor, count=256):
        _positive_budget(count, 'plan-page size')
        self._check_cursor(cursor)
        # Replaying a cursor costs traversal, but never stores the preceding OD
        # product. Its sequence and leg identities are exactly reproducible.
        legs = itertools.islice(self.schedule.iter_legs(), cursor.offset, cursor.offset + count)
        page = tuple(self.resolve(leg) for leg in legs)
        totals = tuple(getattr(cursor, 'materialized_'+unit) +
                       math.fsum(getattr(p.leg.amounts, unit) for p in page)
                       for unit in ('persons', 'vehicles', 'cargo_kg'))
        return PlanCursor(cursor.schedule_identity, cursor.offset + len(page), *totals), page
