"""Explicit fixed-fleet/depot plans on actual registered city doors.

A plan builds one B01 ServiceModel containing bus, freight and external car
routes. It must not be advanced alongside a JourneyModel on the same road.
Passenger arrival and freight arrival below are road-stop arrivals; access
metadata remains available to a whole-journey consumer.
"""
from dataclasses import dataclass
import hashlib
import json
import math

from ..active_suffix.routing import Arc, candidate_paths
from ..foundation_kinetics import VehicleClass
from ..terrain_city.area_access import Portal
from .access import activity_access
from .city import reject
from .lanegroups import compile_lanegroups
from .demand import Amounts
from .services import BusRun, PassengerCohort, FreightRun, ServiceModel


class EligibilityServiceModel(ServiceModel):
    """Dependent passenger arrivals need the joint runtime's physical ledger."""
    def __init__(self, *args, return_dependencies=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.return_dependencies = tuple(return_dependencies)
        self.identity = hashlib.sha256(json.dumps((self.identity, self.return_dependencies),
                                                  sort_keys=True).encode()).hexdigest()

    def step(self, s, offers=(), eligible_passengers=None):
        if self.return_dependencies and eligible_passengers is None:
            reject('dependent bus passengers require explicit completion/dwell eligibility')
        return super().step(s, offers, eligible_passengers)


@dataclass(frozen=True, slots=True)
class BusCorridor:
    id: str
    origin_block: str
    destination_block: str
    departure_s: float
    capacity_persons: float
    dwell_s: float = 5.0

    def __post_init__(self):
        if (not self.id or not math.isfinite(self.departure_s) or self.departure_s < 0
                or not math.isfinite(self.capacity_persons) or self.capacity_persons <= 0
                or not math.isfinite(self.dwell_s) or self.dwell_s < 0):
            reject('explicit finite fleet schedule/capacity required')


@dataclass(frozen=True, slots=True)
class PendingService:
    leg_id: str
    fraction: float
    reason: str
    amounts: Amounts
    window: int | None = None


@dataclass(frozen=True, slots=True)
class ReleaseServicePlan:
    city_identity: str
    contract: object
    time_step_s: float
    source_legs: tuple
    buses: tuple
    passengers: tuple
    freight: tuple
    pending: tuple
    metadata: tuple

    def assignment_report(self):
        """Trip demand units; bus vehicle equivalents are not physical fleet."""
        units = {}
        for unit in ('persons', 'vehicles', 'cargo_kg'):
            requested = math.fsum(getattr(t.amounts, unit) for t in self.source_legs)
            unassigned = math.fsum(getattr(p.amounts, unit) for p in self.pending)
            units[unit] = dict(requested=requested, assigned=requested-unassigned,
                               unassigned=unassigned)
        return dict(units=units, fixed_fleet_vehicles=len(self.buses),
                    scope='assignment, not trip completion; bus demand vehicles are occupancy equivalents')

    def model(self, *, step_s=None, traffic_routes=(), traffic_classes=None, record_budget=20000):
        """Cars and services enter one network; caller owns any journey stages."""
        step_s = self.time_step_s if step_s is None else step_s
        if step_s != self.time_step_s:
            reject('service step must match compiled lane contract')
        return EligibilityServiceModel(self.contract, self.buses, self.passengers, self.freight,
                            bus_class=VehicleClass('scheduled_bus', preferred_mps=10, length_m=12),
                            freight_class=VehicleClass('freight', preferred_mps=10, length_m=10),
                            step_s=step_s, return_dependencies=tuple(
                                (t.id,t.depends_on,t.minimum_dwell_s) for t in self.source_legs
                                if t.mode == 'bus' and t.depends_on),
                            traffic_routes=traffic_routes,
                            traffic_classes=traffic_classes, record_budget=record_budget)


def compile_service_plan(city, legs, corridors=(), *, depot_block_id=None,
                         step_s=1.0, max_legs=256, max_runs=20000):
    """Compile declared fleet and cargo endpoints; never infer a fleet from OD.

    All passengers in a departure window become stop-available at window end
    plus the maximum delay of the declared depth0 discrete access law. This
    conservative finite-window closure relative to that numerical law preserves the original window birth moment in metadata.
    A full bus leaves residual waiting passengers in the B01 person ledger.
    Dependent returns require explicit completion/dwell eligibility at execution.
    """
    if (isinstance(max_legs, bool) or not isinstance(max_legs, int) or max_legs < 1
            or isinstance(max_runs, bool) or not isinstance(max_runs, int) or max_runs < 1):
        reject('positive finite service record budgets required')
    bounded = []
    for leg in legs:
        if len(bounded) >= max_legs:
            reject('service leg budget exceeded; no demand omitted', 'BLOCKED_RESOURCE')
        bounded.append(leg)
    legs = tuple(bounded)
    if len({leg.id for leg in legs}) != len(legs):
        reject('unique service leg IDs required')
    bounded_corridors = []
    for corridor in corridors:
        if len(bounded_corridors) >= max_runs:
            reject('fixed fleet run budget exceeded', 'BLOCKED_RESOURCE')
        bounded_corridors.append(corridor)
    corridors = tuple(bounded_corridors)
    if len({b.id for b in corridors}) != len(corridors):
        reject('unique fixed fleet IDs required')
    contract = compile_lanegroups(city, dt_s=step_s)
    nodes = {n.id: n for n in city.roadmap.nodes}
    gates = {}
    for p in city.portals:
        gates.setdefault(p.block_id, []).append(p)
    # Construction registry ordering has no traffic allocation priority.
    doors = {b: min(ps, key=lambda p: nodes[p.node_id].xyz) for b, ps in gates.items()}
    arcs = tuple(Arc(g.id, g.tail, g.head) for g in contract.groups)
    costs = {g.id: g.physics.length_m/g.physics.speed_mps for g in contract.groups}
    allowed = frozenset(costs)
    cache = {}

    def path(a, b):
        if a not in doors or b not in doors or a == b:
            return ()
        key = (a, b)
        if key not in cache:
            found = candidate_paths(arcs, costs, doors[a].node_id, doors[b].node_id,
                                    1, allowed_turns=contract.allowed_turns).paths
            cache[key] = found[0] if found else ()
        return cache[key]

    def access(measure):
        door = doors.get(measure.block_id)
        if door is None:
            return None
        law, _ = activity_access(measure, (Portal(door.id, nodes[door.node_id].xyz[:2]),), depth=0)
        return law

    buses, metadata, pending = [], [], []

    def reserve():
        if len(passengers)+len(freight)+len(buses) >= max_runs:
            reject('service record budget exceeded; no demand omitted', 'BLOCKED_RESOURCE')

    for b in corridors:
        route = path(b.origin_block, b.destination_block)
        if not route:
            reject('fixed bus corridor lacks a nonempty legal registered route', 'PHYSICAL_INFEASIBLE')
        buses.append(BusRun(b.id, (route,), (b.departure_s,), b.capacity_persons, b.dwell_s, allowed))
    passengers, freight = [], []

    def unassigned(leg, reason, fraction=1.0, window=None):
        pending.append(PendingService(leg.id, fraction, reason,
                                      leg.amounts.scaled(fraction), window))

    for leg in legs:
        if any(m is not None and m.city_identity != city.identity for m in (leg.origin, leg.destination)):
            reject('service demand belongs to a different city')
        if leg.depends_on and leg.mode != 'bus':
            unassigned(leg, 'dependent return eligibility required')
            continue
        if leg.mode == 'bus' and leg.origin is not None and leg.destination is not None:
            origin, destination = access(leg.origin), access(leg.destination)
            if origin is None or destination is None:
                unassigned(leg, 'missing registered stop door')
                continue
            maximum_delay = max(a.maximum_s for a in origin.atoms)
            for i, w in enumerate(leg.departures.windows):
                ready = w.end_s + maximum_delay
                eligible = [b for b in corridors if (b.origin_block, b.destination_block) ==
                            (leg.origin.block_id, leg.destination.block_id) and b.departure_s >= ready]
                if not eligible:
                    unassigned(leg, 'no fixed bus after stop availability', w.probability, i)
                    continue
                departure = min(b.departure_s for b in eligible)
                tied = tuple(b for b in eligible if b.departure_s == departure)
                persons = leg.amounts.persons*w.probability/len(tied)
                for bus in tied:
                    reserve()
                    passenger_id = leg.id+':'+str(i)+':'+bus.id
                    passengers.append(PassengerCohort(passenger_id,
                                                      bus.id,0,1,ready,persons))
                    metadata.append(dict(leg_id=leg.id, window=i, run_id=bus.id,
                                         passenger_id=passenger_id, depends_on=leg.depends_on,
                                         minimum_dwell_s=leg.minimum_dwell_s,
                                         persons=persons, birth_person_s=leg.amounts.persons *
                                         leg.departures.first_moment_s(w.start_s,w.end_s)/len(tied),
                                         origin_access=tuple((a.delay_s,a.weight) for a in origin.atoms),
                                         destination_access=tuple((a.delay_s,a.weight) for a in destination.atoms),
                                         closure='window-end plus maximum ingress delay; road-stop arrival'))
        elif leg.mode == 'freight' and leg.destination is not None:
            if depot_block_id is None:
                unassigned(leg, 'explicit freight depot required')
                continue
            route = path(depot_block_id, leg.destination.block_id)
            if not route:
                unassigned(leg, 'depot route absent or intrazonal')
                continue
            destination = access(leg.destination)
            for i, w in enumerate(leg.departures.windows):
                vehicles = leg.amounts.vehicles*w.probability
                cargo = leg.amounts.cargo_kg*w.probability
                if not vehicles:
                    if cargo:
                        reject('cargo requires positive freight vehicle amount')
                    continue
                reserve()
                freight.append(FreightRun(leg.id+':'+str(i),route,w.end_s,vehicles,cargo,
                                          2000.0,5000.0,allowed))
                metadata.append(dict(leg_id=leg.id,window=i,freight_run_id=leg.id+':'+str(i),
                                     cargo_kg=cargo,
                                     birth_vehicle_s=leg.amounts.vehicles *
                                     leg.departures.first_moment_s(w.start_s,w.end_s),
                                     destination_access=tuple((a.delay_s,a.weight) for a in destination.atoms),
                                     closure='explicit road-node depot; window-end dispatch; road arrival'))
        else:
            unassigned(leg, 'not an assignable internal bus or depot freight request')
        if len(passengers)+len(freight)+len(buses) > max_runs:
            reject('service record budget exceeded; no demand omitted','BLOCKED_RESOURCE')
    return ReleaseServicePlan(city.identity, contract, step_s, legs, tuple(buses), tuple(passengers),
                              tuple(freight), tuple(pending), tuple(metadata))
