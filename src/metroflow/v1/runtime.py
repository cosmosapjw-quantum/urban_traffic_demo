"""C01 immutable phase runner on the sole T04 transport lineage.

Medium decisions are proposals; no occupied packet is rewritten. Slow consumers
see the previous accessibility snapshot. City/demand identities bind frozen input
owners; full daily scenario composition remains C02.
"""
from dataclasses import dataclass, replace, asdict
import hashlib
import json
import math
from .city import reject
from .observations import completed_route_observations
from .routing import DecisionBoundary


@dataclass(frozen=True, slots=True)
class AccessibilitySnapshot:
    stamp_s: float
    completed_veh: float


@dataclass(frozen=True, slots=True)
class PhaseEvent:
    time_s: float
    phase: str
    input_stamp_s: float


@dataclass(frozen=True, slots=True)
class WorldState:
    model_id: str
    city_identity: str
    demand_identity: str
    traffic: object
    information: object
    routing: object
    accessibility: AccessibilitySnapshot
    slow_input: AccessibilitySnapshot
    journal: tuple[PhaseEvent, ...] = ()
    completed_costs: tuple = ()
    decisions: tuple = ()
    city_snapshot_json: str | None = None
    trip_schedule: object = None
    next_medium_s: float = 5.0
    next_slow_s: float = 10.0
    observation_cursor_s: float = 0.0


class Runtime:
    def __init__(self, transport, information, routing, preference, *, city_identity,
                 demand_identity, origin, destination, medium_s=5.0, slow_s=10.0,
                 record_budget=10000, city_snapshot=None, trip_schedule=None):
        if (any(not math.isfinite(x) or x <= 0 for x in (medium_s, slow_s))
                or not city_identity or not demand_identity or not origin or not destination
                or isinstance(record_budget, bool) or not isinstance(record_budget, int)
                or record_budget < 1):
            reject('invalid runtime identities, clocks or record budget', 'CONTRACT_ERROR')
        if city_snapshot is not None and city_snapshot.identity != city_identity:
            reject('CitySnapshot identity differs', 'CONTRACT_ERROR')
        if trip_schedule is not None and (trip_schedule.identity != demand_identity
                or trip_schedule.city_identity != city_identity):
            reject('TripSchedule identity differs', 'CONTRACT_ERROR')
        self.city_json = json.dumps(city_snapshot.to_dict(), sort_keys=True) if city_snapshot else None
        self.trip_schedule = trip_schedule
        self.transport, self.information, self.routing = transport, information, routing
        self.preference = preference
        self.city_identity, self.demand_identity = city_identity, demand_identity
        self.origin, self.destination = origin, destination
        self.medium_s, self.slow_s, self.record_budget = medium_s, slow_s, record_budget
        self.identity = hashlib.sha256(json.dumps(dict(
            policy='C01_atomic_phases_v1', transport=transport.identity,
            information=information.identity, routing=routing.identity,
            preference=asdict(preference), city=city_identity, demand=demand_identity,
            origin=origin, destination=destination, medium=medium_s, slow=slow_s,
            budget=record_budget, city_snapshot=self.city_json,
            trip_schedule=asdict(trip_schedule) if trip_schedule is not None else None), sort_keys=True).encode()).hexdigest()

    def initial(self):
        snapshot = AccessibilitySnapshot(0.0, 0.0)
        return WorldState(self.identity, self.city_identity, self.demand_identity,
                          self.transport.initial(), self.information.initial(), self.routing.initial(),
                          snapshot, snapshot, city_snapshot_json=self.city_json, trip_schedule=self.trip_schedule,
                          next_medium_s=self.medium_s, next_slow_s=self.slow_s)

    def check(self, state):
        if (state.model_id != self.identity or state.city_identity != self.city_identity
                or state.demand_identity != self.demand_identity
                or state.routing.model_id != self.routing.identity
                or state.city_snapshot_json != self.city_json or state.trip_schedule != self.trip_schedule):
            reject('world input/configuration identity mismatch', 'CONTRACT_ERROR')
        self.transport.check(state.traffic)
        self.information.check(state.information)
        now = state.traffic.road.time_s
        if (state.information.time_s > now or state.next_medium_s <= now
                or state.next_slow_s <= now or state.observation_cursor_s > now
                or state.accessibility.stamp_s > now or state.slow_input.stamp_s > now):
            reject('invalid world phase checkpoint', 'CONTRACT_ERROR')

    def advance(self, state, until_s, *, reports=()):
        """Atomic per call: any failure attaches the complete input world checkpoint.

        Reports have already completed at their stamps; R01 applies latency and
        coverage. New reports are published only at the first eligible medium tick.
        """
        from ..active_suffix.common import BudgetExceeded
        self.check(state)
        if not math.isfinite(until_s) or until_s < state.traffic.road.time_s:
            reject('monotone finite runtime horizon required', 'CONTRACT_ERROR')
        pending = tuple(reports)
        if any(r.observation.stamp_s > until_s for r in pending):
            reject('future reports outside transaction horizon', 'CONTRACT_ERROR')
        current = state
        try:
            while current.traffic.road.time_s < until_s:
                tick = min(until_s, current.next_medium_s, current.next_slow_s,
                           current.traffic.road.time_s + 900.0)
                traffic = self.transport.advance(current.traffic, tick)
                updated = replace(current, traffic=traffic)
                # Frozen old snapshot is selected before any same-tick publication.
                previous = current.accessibility
                if tick == current.next_medium_s:
                    delivered = tuple(r for r in pending if r.observation.stamp_s <= tick)
                    pending = tuple(r for r in pending if r.observation.stamp_s > tick)
                    information = self.information.advance(current.information, tick, delivered)
                    observation = self.information.observe(information, (0.0, 0.0))
                    routing, decision = self.routing.decide(current.routing, observation,
                        DecisionBoundary(tick, self.origin), self.preference, self.destination)
                    costs = completed_route_observations(self.transport, traffic,
                        since_s=current.observation_cursor_s,
                        sensor_xy={tag:(0.0, 0.0) for tag in self.transport.network.routes},
                        version=self.transport.identity)
                    updated = replace(updated, information=information, routing=routing,
                        accessibility=AccessibilitySnapshot(tick, traffic.road.completed),
                        completed_costs=current.completed_costs + costs,
                        decisions=current.decisions + (decision,), observation_cursor_s=tick,
                        next_medium_s=current.next_medium_s + self.medium_s,
                        journal=updated.journal + (PhaseEvent(tick, 'medium', previous.stamp_s),))
                if tick == current.next_slow_s:
                    updated = replace(updated, slow_input=previous,
                        next_slow_s=current.next_slow_s + self.slow_s,
                        journal=updated.journal + (PhaseEvent(tick, 'slow', previous.stamp_s),))
                if len(updated.journal) + len(updated.completed_costs) + len(updated.decisions) > self.record_budget:
                    raise BudgetExceeded('C01 world observation/journal budget')
                current = updated
            if pending:
                reject('reports require an eligible medium boundary within this transaction', 'CONTRACT_ERROR')
            self.check(current)
            return current
        except Exception as exc:
            exc.checkpoint = state
            raise

    def run(self, state, until_s, checkpoint_path):
        from .checkpoint import save_checkpoint
        self.check(state)
        current = state
        while current.traffic.road.time_s < until_s:
            current = self.advance(current, min(until_s, current.traffic.road.time_s + 900.0))
            save_checkpoint(checkpoint_path, self, current)
        return current

    def graph_edit(self, state, removed_links):
        """Validate deletion request without mutating graph or discarding occupancy.

        A drained request returns a reviewable transaction descriptor. Building a
        replacement CitySnapshot/TransportModel is the subsequent explicit step.
        """
        self.check(state)
        removed = frozenset(removed_links)
        if not removed <= set(self.transport.network.index):
            reject('graph edit references unknown link', 'CONTRACT_ERROR')
        active = any(state.traffic.road.cells[self.transport.network.index[e]].occupancy > 0
                     for e in removed)
        scheduled = any(e in removed for f in self.transport.fluxes
                        if f.end_s > state.traffic.road.time_s
                        for e in self.transport.network.routes[f.tag])
        pending = state.traffic.road.released > state.traffic.road.completed
        return dict(status='DRAIN_REQUIRED' if active or scheduled or pending else 'READY_TRANSACTION',
                    removed_links=tuple(sorted(removed)), checkpoint=state,
                    requires_new_city_and_transport_identity=True)


def toy_runtime():
    from .timing_oracles import timing_fixture
    from .routing import RoutingLink, RoutingModel, Preference
    from .information import InformationModel, PriorCost
    from .observations import CostKey
    transport = timing_fixture(.1, mass=2, window=2, entry_rate=.5)
    links = tuple(RoutingLink(g.id, g.tail, g.head, g.physics.length_m)
                  for g in transport.network.groups)
    routing = RoutingModel(links, (('0', '1'),), topology_version='toy_city')
    information = InformationModel(tuple(PriorCost(CostKey('link', e.id, 'car'),
        e.length_m/10, 'toy_static', 'conditional link mean including link holds') for e in links), ())
    return Runtime(transport, information, routing, Preference('car', 'work'),
                   city_identity='toy_city', demand_identity=transport.identity,
                   origin='0', destination='2')
