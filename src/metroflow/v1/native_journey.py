"""Native service scheduling and journey transitions, with reference-compatible IO.

Python still constructs the static validated calendar/service graph and converts
snapshots for diagnostics/checkpoint. The default advance call executes the
coupled road/service/journey time loop in Rust without Python tick callbacks.
An explicit python_oracle road bridge isolates scheduling parity in tests.
"""
from dataclasses import astuple, replace
import math

from ..active_suffix.common import BudgetExceeded
from .city import reject
from .joint_release_runtime import JointReleaseRuntime, JointReleaseState
from .journey import AccessEntry
from .release_runtime import ReleaseRuntime
from .services import ServiceState, RunState, PassengerState

NATIVE_TIMING_SCOPE = ("native complete tick including rollback checkpoint copying; "
                       "excludes frontend boundary validation/serialization")


def _people(values):
    return [astuple(p) for p in values]


def _sinks(events):
    return [(e.tag, e.mass, e.end_s) for e in events if e.destination is None]


class NativeServiceModel:
    """Persistent native service owner around exactly one road owner.

    Failed road steps leave service state uncommitted. Existing immutable
    ServiceState snapshots remain valid for branching and checkpoint rewind.
    """
    def __init__(self, reference, *, road_backend="rust"):
        from _metroflow_rust import NativeServiceCore

        self.reference = reference
        self.network = reference.network
        if road_backend == "rust":
            from .native_road import NativeRoadNetwork
            self.network = NativeRoadNetwork(reference.network)
        elif road_backend != "python_oracle":
            raise ValueError("road_backend must be rust or python_oracle")
        self.road_backend = road_backend
        buses = [(b.id, list(b.departures_s), b.capacity_persons, b.dwell_s)
                 for b in reference.buses]
        run = {b.id: i for i, b in enumerate(reference.buses)}
        people = [(run[p.run_id], p.origin_stop, p.destination_stop, p.available_s, p.persons)
                  for p in reference.passengers]
        freight = [(f.id, f.departure_s, f.vehicles) for f in reference.freight]
        cars = [(c.id, c.departure_s, c.vehicles) for c in reference.cars]
        self.native = NativeServiceCore(buses, people, freight, cars)
        self._current = None

    def __getattr__(self, name):
        return getattr(self.reference, name)

    def initial(self):
        value = replace(self.reference.initial(), road=self.network.initial())
        self._restore(value)
        self._current = value
        return value

    def _restore(self, state):
        phase = {"STOP": 0, "ROAD": 1, "DONE": 2}
        self.native.restore(([(r.leg, phase[r.phase], r.ready_s, r.completed_leg_veh, r.delay_s)
                              for r in state.buses], _people(state.passengers),
                             list(state.freight_released), list(state.freight_completed),
                             list(state.cars_released)))

    def check(self, state):
        self.reference.check(state)

    def snapshot(self, road, events=()):
        runs, people, released, completed, cars = self.native.snapshot()
        phases = ("STOP", "ROAD", "DONE")
        result = ServiceState(self.identity, road,
            tuple(RunState(r[0], phases[r[1]], *r[2:]) for r in runs),
            tuple(PassengerState(*p) for p in people), tuple(released), tuple(completed),
            tuple(cars), tuple(events))
        self._current = result
        return result

    def step(self, state, offers=(), eligible_passengers=None):
        try:
            self.check(state)
            offers = list(offers)
            if any(not offer or offer[0] not in self.traffic_tags for offer in offers):
                reject("external offer tag must have dedicated traffic route")
            if eligible_passengers is None:
                allowed = [True] * len(self.passengers)
            else:
                eligible_passengers = frozenset(eligible_passengers)
                if not eligible_passengers <= {p.id for p in self.passengers}:
                    reject("unknown eligible passenger cohort")
                allowed = [p.id in eligible_passengers for p in self.passengers]
            if self._current is not state:
                self._restore(state)
            offers.extend(self.native.prepare(state.road.time_s, allowed))
            road, events = self.network.advance_interval(state.road, self.step_s, offers)
            self.native.finish(road.time_s, _sinks(events))
            result = self.snapshot(road, events)
            self.check(result)
            self._current = result
            return result
        except Exception as exc:
            self.native.abort()
            self._current = None
            exc.checkpoint = state
            raise

    def advance(self, state, end_s):
        count = (end_s - state.road.time_s) / self.step_s
        if not math.isfinite(count) or count < 0 or abs(count - round(count)) > 1e-8:
            reject("service horizon must align with fixed step")
        for _ in range(round(count)):
            state = self.step(state)
        return state


class NativeJointReleaseRuntime(JointReleaseRuntime):
    """Reference-compatible runtime with native journey, service and road owners.

    The constructor still materializes the Python static leg/service graph. This
    adapter therefore does not by itself remove whole-calendar activation caps.
    Once constructed, a coarse advance keeps all three numerical owners in Rust.
    """
    def __init__(self, city, legs, service_plan, *, step_s=1.0, max_legs=256,
                 record_budget=20000, road_backend="rust", release_timing="legacy"):
        from _metroflow_rust import NativeJourneyCore

        super().__init__(city, legs, service_plan, step_s=step_s, max_legs=max_legs,
                         record_budget=record_budget, release_timing=release_timing)
        self.service = NativeServiceModel(self.service, road_backend=road_backend)
        records = []
        for leg in self.legs:
            kind = 2 if leg.id in self.internal_laws else 1 if leg.id in self.routes else 0
            origin = destination = ()
            if kind == 2:
                origin = self.internal_laws[leg.id].atoms
                destination = ((0.0, 1.0),)
            elif kind == 1:
                boundary = self.helper.model.boundaries[leg.id]
                origin, destination = boundary.origin.atoms, boundary.destination.atoms
            parent = (None if not leg.depends_on else
                      self.indices.get(leg.depends_on, len(self.legs)))
            records.append((leg.id, ReleaseRuntime.carrier(leg), parent, leg.minimum_dwell_s,
                            [(w.start_s, w.end_s, w.probability) for w in leg.departures.windows],
                            kind, list(origin), list(destination)))
        bus = []
        for k, p in enumerate(self.service.passengers):
            i = self.bus_leg[k]
            leg = self.legs[i]
            meta = self.bus_meta[p.id]
            required = leg.departures.fraction(0, leg.departures.windows[meta["window"]].end_s)
            bus.append((i, leg.amounts.persons, p.persons, meta["birth_person_s"], required,
                        list(meta["destination_access"])))
        freight = [(self.freight_leg[k], f.vehicles, self.freight_meta[f.id]["birth_vehicle_s"],
                    list(self.freight_meta[f.id]["destination_access"]))
                   for k, f in enumerate(self.service.freight)]
        self.native_journey = NativeJourneyCore(records, bus, freight, record_budget,
                                                release_timing=release_timing)
        self.last_advance_metrics = dict(tick_times_s=[], peak_records=0, scope=NATIVE_TIMING_SCOPE)

    def _restore_journey(self, state):
        def stages(values):
            return [(self.indices[e.tag], e.mass, e.born_s, e.delay_s) for e in values]
        self.native_journey.restore((state.time_s, stages(state.entering), stages(state.egress),
            stages(state.internal), list(state.released), list(state.completed),
            [list(r) for r in state.receipts], list(state.birth_carrier_s)))

    def _snapshot(self, service):
        t, entering, egress, internal, released, completed, receipts, birth = self.native_journey.snapshot()
        if t != service.road.time_s:
            reject("native journey and road clocks differ", "IMPLEMENTATION_ERROR")
        def stages(values):
            return tuple(AccessEntry(self.legs[e[0]].id, *e[1:]) for e in values)
        return JointReleaseState(self.identity, service, stages(entering), stages(egress),
            stages(internal), tuple(released), tuple(completed),
            tuple(tuple(r) for r in receipts), tuple(birth))

    def advance(self, state, end_s):
        self.check(state)
        count = (end_s - state.time_s) / self.step_s
        if not math.isfinite(count) or count < 0 or abs(count - round(count)) > 1e-8:
            reject("joint horizon must align with fixed step")
        self._restore_journey(state)
        if self.service.road_backend == "rust":
            return self._advance_native(state, round(count))
        self.last_advance_metrics = dict(tick_times_s=[], peak_records=0,
                                        scope="python_oracle bridge; native tick metrics not collected")
        service = state.service
        for _ in range(round(count)):
            previous = service
            try:
                if self.release_interval:
                    offers, allow, arrivals = self.native_journey.prepare_interval(self.step_s)
                    offers = [offer + (arrival,) for offer, arrival in zip(offers, arrivals)]
                else:
                    offers, allow = self.native_journey.prepare()
                eligible = [p.id for p, permitted in zip(self.service.passengers, allow) if permitted]
                service = self.service.step(previous, offers, eligible_passengers=eligible)
                self.native_journey.finish(service.road.time_s, _sinks(service.last_events),
                    _people(previous.passengers), _people(service.passengers),
                    list(previous.freight_released), list(service.freight_released),
                    list(previous.freight_completed), list(service.freight_completed))
            except Exception as exc:
                self.native_journey.abort()
                checkpoint = self._snapshot(previous)
                if isinstance(exc, MemoryError):
                    wrapped = BudgetExceeded(str(exc))
                    wrapped.checkpoint = checkpoint
                    raise wrapped from exc
                exc.checkpoint = checkpoint
                raise
        result = self._snapshot(service)
        self.check(result)
        return result

    def _advance_native(self, state, count):
        from _metroflow_rust import advance_native_joint

        network = self.service.network
        network.restore(state.service.road)
        self.service._restore(state.service)

        def snapshot():
            times, peak = self.native_journey.advance_metrics()
            self.last_advance_metrics = dict(tick_times_s=times, peak_records=peak,
                                            scope=NATIVE_TIMING_SCOPE)
            road = network.snapshot()
            events = (state.service.last_events if road.time_s == state.time_s else
                      network._events(self.service.native.road_events()))
            return self._snapshot(self.service.snapshot(road, events))

        try:
            advance_native_joint(network.native, self.service.native, self.native_journey,
                                 list(network.tags), count, self.step_s)
        except Exception as exc:
            checkpoint = snapshot()
            self.check(checkpoint)
            if isinstance(exc, MemoryError):
                wrapped = BudgetExceeded(str(exc))
                wrapped.checkpoint = checkpoint
                raise wrapped from exc
            exc.checkpoint = checkpoint
            raise
        result = snapshot()
        try:
            self.check(result)
        except Exception as exc:
            # An independent boundary-check failure cannot certify the new
            # snapshot; retain the previously validated caller checkpoint.
            self._restore_journey(state)
            self.service._restore(state.service)
            network.restore(state.service.road)
            exc.checkpoint = state
            raise
        return result
