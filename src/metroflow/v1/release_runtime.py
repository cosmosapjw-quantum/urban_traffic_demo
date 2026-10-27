"""Bounded real-map car transport composition with explicit unexecuted demand.

All committed routes share one T04 network. Independent batch simulations must
not be summed into a city congestion run. Fixed bus fleet, freight endpoint assignment and global streaming route
activation remain explicit pending obligations; they are never zero-time completions.
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
    internal: tuple = ()
    receipts: tuple = ()  # per-leg (completion time, normalized fraction)
    road_intent_hold: float = 0.0

    @property
    def time_s(self):
        return self.journey.time_s


class ReleaseRuntime:
    """Execute a finite registered set of actual-map car legs and internal trips.

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
        for leg in self.legs:
            if leg.depends_on in {x.id for x in self.legs}:
                parent = next(x for x in self.legs if x.id == leg.depends_on)
                if (parent.id == leg.id or parent.depends_on is not None
                        or parent.cohort_id != leg.cohort_id or parent.amounts != leg.amounts):
                    reject('dependent return must match one outward cohort and amounts')
        self.step_s = step_s
        contract = compile_lanegroups(city, dt_s=step_s)
        nodes = {n.id: n for n in city.roadmap.nodes}
        gates = {}
        for p in city.portals:
            gates.setdefault(p.block_id, []).append(p)
        arcs = tuple(Arc(g.id, g.tail, g.head) for g in contract.groups)
        costs = {g.id: g.physics.length_m / g.physics.speed_mps for g in contract.groups}
        routes, boundaries, self.unsupported = [], [], {}
        self.internal_laws = {}
        self.record_budget = record_budget
        self.route_links = {}
        self.indices = {leg.id: i for i, leg in enumerate(self.legs)}
        for leg in self.legs:
            if any(m is not None and m.city_identity != city.identity
                   for m in (leg.origin, leg.destination)):
                reject('release activity belongs to another city')
            reason = None
            if leg.depends_on and leg.depends_on not in self.indices:
                reason = 'return parent absent from committed set'
            elif leg.endpoint_kind == 'intrazonal' and leg.mode in ('car', 'noncar'):
                self.internal_laws[leg.id] = leg.intrazonal
                continue
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
            if origin.node_id == dest.node_id:
                endpoint_laws = []
                for measure, gate in ((leg.origin,origin),(leg.destination,dest)):
                    law,_ = activity_access(measure,(Portal(gate.id,nodes[gate.node_id].xyz[:2]),),depth=0)
                    endpoint_laws.append(law.condition(gate.id)[1])
                atoms = {}
                for a,wa in endpoint_laws[0]:
                    for b,wb in endpoint_laws[1]:
                        atoms[a+b] = atoms.get(a+b,0.0)+wa*wb
                if len(atoms) > record_budget:
                    reject('co-located access law exceeds budget','BLOCKED_RESOURCE')
                self.internal_laws[leg.id] = DelayLaw(tuple(sorted(atoms.items())))
                continue
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
        if not routes and not self.internal_laws:
            reject('no supported route or internal delay in bounded set', 'BLOCKED_IMPLEMENTATION_DEPENDENCY')
        # PacketNetwork requires a registered route even for an internal-only
        # calendar. This inert clock route is never injected or counted as demand.
        if not routes:
            tag = '__release_clock__'
            if tag in self.indices:
                reject('reserved clock route label')
            routes.append(Route(tag,(contract.groups[0].id,)))
            boundaries.append(JourneyBoundary(tag,DelayLaw(((0.0,1.0),)),DelayLaw(((0.0,1.0),))))
        car = VehicleClass('car', preferred_mps=10.0)
        physical = TransportModel(contract, routes, {r.tag: car for r in routes}, (),
                                  max_step_s=step_s, templates=(ClassMass(car, 1.0, 1.0, 0.0, 0.0),) if routes else (),
                                  entry_speeds={'car': 10.0} if routes else {}, record_budget=record_budget)
        self.model = JourneyModel(physical.network, boundaries, record_budget=record_budget)
        self.identity = hashlib.sha256(json.dumps(dict(city=city.identity, model=self.model.identity,
            legs=[(leg.id, leg.purpose, leg.mode, leg.depends_on, leg.minimum_dwell_s,
                   leg.amounts.persons, leg.amounts.vehicles, leg.amounts.cargo_kg,
                   [(w.start_s,w.end_s,w.probability) for w in leg.departures.windows]) for leg in self.legs],
            unsupported=self.unsupported, internal_laws={k:v.atoms for k,v in self.internal_laws.items()}), sort_keys=True).encode()).hexdigest()

    def initial(self):
        return ReleaseState(self.identity, self.model.initial(), (0.0,)*len(self.legs), (0.0,)*len(self.legs), (), tuple(() for _ in self.legs))

    def check(self, state):
        if state.model_id != self.identity or len(state.released) != len(self.legs) or len(state.completed) != len(self.legs):
            reject('release checkpoint identity/schema differs')
        self.model.check(state.journey)
        for leg, released, completed in zip(self.legs,state.released,state.completed):
            if leg.id in self.unsupported and (released != 0 or completed != 0):
                reject('unsupported leg has physical release/completion', 'IMPLEMENTATION_ERROR')
        tolerance = 1e-9 * max(1.0, state.journey.released, state.journey.completed)
        if (abs(math.fsum(state.released[self.indices[k]] for k in self.route_links)-state.journey.released) > tolerance
                or abs(math.fsum(state.completed[self.indices[k]] for k in self.route_links)-state.journey.completed) > tolerance):
            reject('release and physical road ledgers differ', 'IMPLEMENTATION_ERROR')
        for leg, released, completed in zip(self.legs, state.released, state.completed):
            if leg.id in self.unsupported and (released != 0 or completed != 0):
                reject('unsupported leg has physical release/completion', 'IMPLEMENTATION_ERROR')
            carrier = self.carrier(leg)
            requested = carrier * leg.departures.fraction(0, state.time_s)
            if not 0 <= completed <= released + 1e-8 or released > requested + 1e-8:
                reject('release requested/completed ledger differs', 'IMPLEMENTATION_ERROR')
        if (not math.isfinite(state.road_intent_hold) or state.road_intent_hold < 0
                or state.road_intent_hold > self.model.residence(state.journey)['origin_access']+tolerance):
            reject('intent holding ledger differs','IMPLEMENTATION_ERROR')
        if any(e.tag not in self.internal_laws or not math.isfinite(e.mass) or e.mass <= 0
               or not math.isfinite(e.born_s) or not 0 <= e.born_s <= state.time_s
               or not math.isfinite(e.delay_s) or e.delay_s < 0 for e in state.internal):
            reject('internal activity checkpoint differs','IMPLEMENTATION_ERROR')
        if len(state.receipts) != len(self.legs):
            reject('completion receipt schema differs')
        for i, leg in enumerate(self.legs):
            carrier = self.carrier(leg)
            if any(not math.isfinite(when) or not math.isfinite(f) or not 0 <= when <= state.time_s
                   or f <= 0 for when,f in state.receipts[i]):
                reject('invalid completion receipt')
            total = math.fsum(f for _, f in state.receipts[i])*carrier
            if abs(total-state.completed[i]) > tolerance:
                reject('completion receipt ledger differs', 'IMPLEMENTATION_ERROR')
            if leg.depends_on and leg.depends_on in self.indices:
                eligible = math.fsum(f for when,f in state.receipts[self.indices[leg.depends_on]]
                                     if when+leg.minimum_dwell_s <= state.time_s)
                if state.released[i] > carrier*eligible+tolerance:
                    reject('return released before completion and dwell', 'IMPLEMENTATION_ERROR')
            if leg.id in self.internal_laws:
                active = math.fsum(e.mass for e in state.internal if e.tag == leg.id)
                if abs(active-(state.released[i]-state.completed[i])) > tolerance:
                    reject('internal activity ledger differs', 'IMPLEMENTATION_ERROR')

    @staticmethod
    def carrier(leg):
        return leg.amounts.vehicles or leg.amounts.persons

    @staticmethod
    def birth_between(profile, lo, hi):
        # Exact first moment on a quantile band of disjoint uniform windows.
        total = moment = 0.0
        for w in sorted(profile.windows, key=lambda w:w.start_s):
            a, b = max(lo,total), min(hi,total+w.probability)
            if b > a:
                x = w.start_s+(a-total)*(w.end_s-w.start_s)/w.probability
                y = w.start_s+(b-total)*(w.end_s-w.start_s)/w.probability
                moment += (b-a)*(x+y)/2
            total += w.probability
        return moment/(hi-lo)

    def advance(self, state, end_s):
        self.check(state)
        steps = (end_s-state.time_s)/self.step_s
        if not math.isfinite(steps) or steps < 0 or abs(steps-round(steps)) > 1e-8:
            reject('advance requires ordered aligned horizon')
        for _ in range(round(steps)):
            previous = state
            t = state.time_s
            entering = list(state.journey.entering)
            internal = list(state.internal)
            released = list(state.released)
            added_mass = added_birth = 0.0
            intent_hold = state.road_intent_hold
            for i, leg in enumerate(self.legs):
                if leg.id in self.unsupported:
                    continue
                carrier = self.carrier(leg)
                if not carrier:
                    continue
                requested = leg.departures.fraction(0,t)
                eligible = 1.0
                if leg.depends_on:
                    parent = self.indices[leg.depends_on]
                    eligible = math.fsum(f for when,f in state.receipts[parent]
                                         if when+leg.minimum_dwell_s <= t)
                old = released[i]/carrier
                ready = min(requested, eligible)
                fraction = max(0.0,ready-old)
                if not fraction:
                    continue
                mass = carrier*fraction
                birth = self.birth_between(leg.departures, old, ready)
                released[i] += mass
                hold = max(0.0,t-birth) if leg.depends_on else 0.0
                if leg.id in self.internal_laws:
                    # Internal access law is the entire intrazonal journey.
                    internal.extend(AccessEntry(leg.id,mass*w,birth,delay+hold)
                                    for delay,w in self.internal_laws[leg.id].atoms)
                else:
                    added_mass += mass
                    added_birth += mass*birth
                    intent_hold += mass*hold
                    entering.extend(AccessEntry(leg.id,mass*w,birth,delay+hold)
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
            receipts = [list(x) for x in state.receipts]
            for event in completions:
                i = self.indices[event.tag]
                completed[i] += event.mass
                receipts[i].append((event.end_s,event.mass/self.carrier(self.legs[i])))
            pending_internal = []
            for event in internal:
                if event.ready_s <= journey.time_s:
                    i = self.indices[event.tag]
                    completed[i] += event.mass
                    receipts[i].append((max(t,event.ready_s),event.mass/self.carrier(self.legs[i])))
                else:
                    pending_internal.append(event)
            if len(pending_internal)+sum(map(len,receipts)) > self.record_budget:
                exc = BudgetExceeded('release internal/completion record budget')
                exc.checkpoint = previous
                raise exc
            state = ReleaseState(self.identity, journey, tuple(released), tuple(completed),
                                 tuple(pending_internal),tuple(tuple(x) for x in receipts),intent_hold)
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
                carrier = self.carrier(leg)
                ratio = amount/carrier if carrier else 0.0
                released += ratio*state.released[i]
                completed += ratio*state.completed[i]
            quantities[unit] = dict(requested=requested, released=released, completed=completed,
                                    pending=requested-released, active=released-completed)
        journey_report = self.model.report(state.journey)
        residence = journey_report['residence_vehicle_seconds']
        residence['origin_access'] -= state.road_intent_hold
        residence['return_intent_hold'] = state.road_intent_hold
        return dict(status='SCOPED_SHARED_MAP_EXECUTION', time_s=state.time_s,
                    ledger=quantities, unsupported=self.unsupported, journey=journey_report,
                    full_release_campaign='NOT_RUN', scope='one shared network for this bounded route set')

    def save(self, path, state):
        self.check(state)
        Path(path).write_text(json.dumps(encode((state.model_id,state.journey,state.released,state.completed,state.internal,state.receipts,state.road_intent_hold)), allow_nan=False))

    def load(self, path):
        values = decode(json.loads(Path(path).read_text()))
        state = ReleaseState(*values)
        self.check(state)
        return state
