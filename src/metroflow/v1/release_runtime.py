"""Bounded real-map car transport composition with explicit unexecuted demand.

All committed routes share one T04 network. Independent batch simulations must
not be summed into a city congestion run. Return eligibility, fixed bus fleet,
freight endpoint assignment and streaming route activation remain explicit
pending obligations; they are never zero-time completions.
"""
from dataclasses import dataclass, replace
import hashlib
import json
import math
from pathlib import Path

from ..active_suffix.common import BudgetExceeded
from ..active_suffix.routing import Arc, candidate_paths
from ..foundation_kinetics import VehicleClass
from ..ordered_network import Route
from ..terrain_city.area_access import Portal
from .access import activity_access
from .checkpoint import encode, decode
from .city import reject
from .journey import JourneyModel, JourneyBoundary, AccessEntry, DelayLaw
from .kinetics import ClassMass
from .lanegroups import compile_lanegroups
from .transport import TransportModel


@dataclass(frozen=True, slots=True)
class ReleaseState:
    model_id: str
    journey: object
    released: tuple[float, ...]
    completed: tuple[float, ...]

    @property
    def time_s(self):
        return self.journey.time_s


class ReleaseRuntime:
    """Execute a finite registered set of actual-map outbound car legs.

    The max_legs bound applies before eager materialization. Missing modes or
    routes retain requested persons/vehicles/cargo in the pending ledger.
    Profile birth first moments are exact. Each interval is injected at the
    following grid boundary using its centroid birth: this preserves its first
    moment but approximates its age distribution, with <=dt source grid hold.
    """
    def __init__(self, city, legs, *, step_s=1.0, max_legs=256, record_budget=20000):
        if (not math.isfinite(step_s) or step_s <= 0 or isinstance(max_legs, bool)
                or not isinstance(max_legs, int) or max_legs < 1):
            reject('positive step and finite leg budget required')
        bounded = []
        for leg in legs:
            if len(bounded) == max_legs:
                reject('global route set exceeds bound; no demand omitted', 'BLOCKED_RESOURCE')
            bounded.append(leg)
        self.legs = tuple(bounded)
        if len({leg.id for leg in self.legs}) != len(self.legs):
            reject('unique release leg IDs required')
        self.step_s = step_s
        contract = compile_lanegroups(city, dt_s=step_s)
        nodes = {n.id: n for n in city.roadmap.nodes}
        gates = {}
        for p in city.portals:
            gates.setdefault(p.block_id, []).append(p)
        arcs = tuple(Arc(g.id, g.tail, g.head) for g in contract.groups)
        costs = {g.id: g.physics.length_m / g.physics.speed_mps for g in contract.groups}
        routes, boundaries, self.unsupported = [], [], {}
        self.route_links = {}
        self.indices = {leg.id: i for i, leg in enumerate(self.legs)}
        for leg in self.legs:
            if any(m is not None and m.city_identity != city.identity
                   for m in (leg.origin, leg.destination)):
                reject('release activity belongs to another city')
            reason = None
            if leg.depends_on:
                reason = 'return completion/dwell coupling pending'
            elif leg.mode != 'car':
                reason = 'bus fleet/noncar/freight assignment pending'
            elif leg.endpoint_kind != 'interzonal':
                reason = 'external or intrazonal composition pending'
            elif any(len(gates.get(m.block_id, ())) != 1 for m in (leg.origin, leg.destination)):
                reason = 'exactly one committed registered portal per endpoint required'
            if reason:
                self.unsupported[leg.id] = reason
                continue
            origin, dest = (gates[m.block_id][0] for m in (leg.origin, leg.destination))
            found = candidate_paths(arcs, costs, origin.node_id, dest.node_id, 1,
                                    allowed_turns=contract.allowed_turns).paths
            if not found or not found[0]:
                self.unsupported[leg.id] = 'no nonempty legal road route'
                continue
            links = found[0]
            self.route_links[leg.id] = links
            laws = []
            for measure, gate in ((leg.origin, origin), (leg.destination, dest)):
                law, _ = activity_access(measure, (Portal(gate.id, nodes[gate.node_id].xyz[:2]),), depth=0)
                laws.append(DelayLaw(law.condition(gate.id)[1]))
            routes.append(Route(leg.id, links))
            boundaries.append(JourneyBoundary(leg.id, *laws))
        if not routes:
            reject('no supported outbound car route in bounded set', 'BLOCKED_IMPLEMENTATION_DEPENDENCY')
        car = VehicleClass('car', preferred_mps=10.0)
        physical = TransportModel(contract, routes, {r.tag: car for r in routes}, (),
                                  max_step_s=step_s, templates=(ClassMass(car, 1.0, 1.0, 0.0, 0.0),),
                                  entry_speeds={'car': 10.0}, record_budget=record_budget)
        self.model = JourneyModel(physical.network, boundaries, record_budget=record_budget)
        self.identity = hashlib.sha256(json.dumps(dict(city=city.identity, model=self.model.identity,
            legs=[(leg.id, leg.purpose, leg.mode, leg.depends_on, leg.minimum_dwell_s,
                   leg.amounts.persons, leg.amounts.vehicles, leg.amounts.cargo_kg,
                   [(w.start_s,w.end_s,w.probability) for w in leg.departures.windows]) for leg in self.legs],
            unsupported=self.unsupported), sort_keys=True).encode()).hexdigest()

    def initial(self):
        return ReleaseState(self.identity, self.model.initial(), (0.0,)*len(self.legs), (0.0,)*len(self.legs))

    def check(self, state):
        if state.model_id != self.identity or len(state.released) != len(self.legs) or len(state.completed) != len(self.legs):
            reject('release checkpoint identity/schema differs')
        self.model.check(state.journey)
        tolerance = 1e-9 * max(1.0, state.journey.released, state.journey.completed)
        if (abs(math.fsum(state.released)-state.journey.released) > tolerance
                or abs(math.fsum(state.completed)-state.journey.completed) > tolerance):
            reject('release and physical road ledgers differ', 'IMPLEMENTATION_ERROR')
        for leg, released, completed in zip(self.legs, state.released, state.completed):
            if leg.id in self.unsupported and (released != 0 or completed != 0):
                reject('unsupported leg has physical release/completion', 'IMPLEMENTATION_ERROR')
            requested = leg.amounts.vehicles * leg.departures.fraction(0, state.time_s)
            if not 0 <= completed <= released + 1e-8 or released > requested + 1e-8:
                reject('release requested/completed ledger differs', 'IMPLEMENTATION_ERROR')

    def advance(self, state, end_s):
        self.check(state)
        steps = (end_s-state.time_s)/self.step_s
        if not math.isfinite(steps) or steps < 0 or abs(steps-round(steps)) > 1e-8:
            reject('advance requires ordered aligned horizon')
        for _ in range(round(steps)):
            previous = state
            t = state.time_s
            entering = list(state.journey.entering)
            released = list(state.released)
            added_mass = added_birth = 0.0
            for i, leg in enumerate(self.legs):
                if leg.id not in self.route_links:
                    continue
                fraction = leg.departures.fraction(max(0, t-self.step_s), t)
                mass = leg.amounts.vehicles * fraction
                if not mass:
                    continue
                birth = leg.departures.first_moment_s(max(0, t-self.step_s), t) / fraction
                released[i] += mass
                added_mass += mass
                added_birth += mass * birth
                entering.extend(AccessEntry(leg.id, mass*w, birth, delay)
                                for delay,w in self.model.boundaries[leg.id].origin.atoms)
            journey = replace(state.journey, entering=tuple(entering),
                              released=state.journey.released+added_mass,
                              birth_moment=state.journey.birth_moment+added_birth)
            try:
                journey, completions = self.model.step(journey)
            except BudgetExceeded as exc:
                exc.checkpoint = previous
                raise
            completed = list(state.completed)
            for event in completions:
                completed[self.indices[event.tag]] += event.mass
            state = ReleaseState(self.identity, journey, tuple(released), tuple(completed))
            self.check(state)
        return state

    def report(self, state):
        self.check(state)
        quantities = {}
        for unit in ('persons', 'vehicles', 'cargo_kg'):
            requested = released = completed = 0.0
            for i, leg in enumerate(self.legs):
                amount = getattr(leg.amounts, unit)
                requested += amount*leg.departures.fraction(0,state.time_s)
                ratio = amount/leg.amounts.vehicles if leg.amounts.vehicles else 0.0
                released += ratio*state.released[i]
                completed += ratio*state.completed[i]
            quantities[unit] = dict(requested=requested, released=released, completed=completed,
                                    pending=requested-released, active=released-completed)
        return dict(status='SCOPED_OUTBOUND_EXECUTION', time_s=state.time_s,
                    ledger=quantities, unsupported=self.unsupported, journey=self.model.report(state.journey),
                    full_release_campaign='NOT_RUN', scope='one shared network for this bounded route set')

    def save(self, path, state):
        self.check(state)
        Path(path).write_text(json.dumps(encode((state.model_id,state.journey,state.released,state.completed)), allow_nan=False))

    def load(self, path):
        values = decode(json.loads(Path(path).read_text()))
        state = ReleaseState(*values)
        self.check(state)
        return state
