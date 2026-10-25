"""One origin-to-destination clock: access -> selected public solver -> egress.

The existing PacketNetwork is reused. No new road-flow or route-choice law is
introduced. Access is a declared, static conditional delay distribution. It is
NOT a capacity-constrained driveway, a safety proof, or a walking assignment.
Public entry uses the next grid boundary; that holding time is reported apart
from physical access. Terminal egress shifts actual continuous outlet intervals.
"""
from dataclasses import dataclass, replace, asdict
from collections import defaultdict
import hashlib
import json
import math
from ..packet_network import PacketNetwork, State as TrafficState
from ..active_suffix.common import BudgetExceeded


@dataclass(frozen=True, slots=True)
class DelayLaw:
    atoms: tuple[tuple[float, float], ...]  # delay [s], probability [1]

    def __post_init__(self):
        if not self.atoms or any(not all(map(math.isfinite, x)) or x[0] < 0 or x[1] <= 0 for x in self.atoms):
            raise ValueError('finite nonnegative delays and positive probabilities required')
        if abs(math.fsum(w for _, w in self.atoms)-1.) > 1e-10:
            raise ValueError('conditional delay probability must sum to one')

    @property
    def mean_s(self):
        return math.fsum(t*w for t, w in self.atoms)


@dataclass(frozen=True, slots=True)
class JourneyBoundary:
    tag: str
    origin: DelayLaw
    destination: DelayLaw


@dataclass(frozen=True, slots=True)
class AccessEntry:
    tag: str
    mass: float
    born_s: float
    delay_s: float

    @property
    def ready_s(self):
        return self.born_s+self.delay_s


@dataclass(frozen=True, slots=True)
class FinishSpan:
    tag: str
    mass: float
    start_s: float
    end_s: float
    birth_moment: float


@dataclass(frozen=True, slots=True)
class JourneyState:
    model_id: str
    traffic: TrafficState
    entering: tuple[AccessEntry, ...] = ()
    finishing: tuple[FinishSpan, ...] = ()
    released: float = 0.
    completed: float = 0.
    birth_moment: float = 0.
    exit_moment: float = 0.
    finished_origin_seconds: float = 0.
    finished_entry_hold_seconds: float = 0.

    @property
    def time_s(self):
        return self.traffic.time_s

    @property
    def system_vehicle_seconds(self):
        return (self.released-self.completed)*self.time_s-self.birth_moment+self.exit_moment


def _merge_entries(entries):
    groups = defaultdict(list)
    for entry in entries:
        groups[(entry.tag, entry.born_s, entry.delay_s)].append(entry.mass)
    return tuple(AccessEntry(tag, math.fsum(masses), born, delay)
                 for (tag, born, delay), masses in sorted(groups.items()))


def _merge_spans(spans):
    groups = defaultdict(list)
    for span in spans:
        groups[(span.tag, span.start_s, span.end_s)].append(span)
    return tuple(FinishSpan(tag, math.fsum(s.mass for s in values), a, b,
                            math.fsum(s.birth_moment for s in values))
                 for (tag, a, b), values in sorted(groups.items()))


class JourneyModel:
    """Homogeneous conditional paths with real origin and destination clocks.

    Route boundaries must cover exactly the network's route tags. Each tag is
    already conditioned on its chosen gates. Traffic mass must be apportioned
    by gate probability BEFORE calling step. Origin and destination laws are
    independent conditional marginals in this version. Correlation needs a
    joint law and cannot be recovered from these marginals alone.
    """
    def __init__(self, network: PacketNetwork, boundaries, record_budget=20000):
        self.network = network
        boundaries = tuple(boundaries)
        self.boundaries = {b.tag: b for b in boundaries}
        if len(self.boundaries) != len(boundaries):
            raise ValueError('duplicate journey boundary tag')
        if set(self.boundaries) != set(network.routes):
            raise ValueError('one access/egress boundary per public route required')
        if any(key.startswith('private:') for key in network.index):
            raise ValueError('remove replaced private connectors; access must not be counted twice')
        if isinstance(record_budget, bool) or not isinstance(record_budget, int) or record_budget < 1:
            raise ValueError('positive journey record budget required')
        self.record_budget = record_budget
        payload = (network.identity, [asdict(self.boundaries[t]) for t in sorted(self.boundaries)], record_budget)
        self.identity = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()

    def initial(self, start_s=0.):
        return JourneyState(self.identity, self.network.initial(start_s))

    def residence(self, state):
        t = state.time_s
        origin = state.finished_origin_seconds + math.fsum(
            e.mass*min(t-e.born_s, e.delay_s) for e in state.entering)
        hold = state.finished_entry_hold_seconds + math.fsum(
            e.mass*max(0., t-e.ready_s) for e in state.entering)
        public = state.traffic.system_vehicle_seconds-state.traffic.pre_entry_seconds
        egress = ((state.traffic.completed-state.completed)*t
                  -state.traffic.exit_moment+state.exit_moment)
        return dict(origin_access=origin, entry_grid_hold=hold, public_network=public,
                    destination_egress=egress, total=state.system_vehicle_seconds)

    def check(self, state):
        if state.model_id != self.identity:
            raise ValueError('journey-state identity mismatch')
        self.network.check(state.traffic)
        numbers = (state.released, state.completed, state.birth_moment, state.exit_moment,
                   state.finished_origin_seconds, state.finished_entry_hold_seconds)
        if any(not math.isfinite(v) or v < 0 for v in numbers):
            raise ValueError('invalid journey ledger')
        for e in state.entering:
            if (e.tag not in self.boundaries or not all(map(math.isfinite, (e.mass,e.born_s,e.delay_s)))
                    or e.mass <= 0 or not 0 <= e.born_s <= state.time_s or e.delay_s < 0):
                raise ValueError('invalid entering measure')
        for e in state.finishing:
            if (e.tag not in self.boundaries or not all(map(math.isfinite, (e.mass,e.start_s,e.end_s,e.birth_moment)))
                    or e.mass <= 0 or e.start_s < state.time_s-1e-9 or e.end_s <= e.start_s
                    or e.birth_moment < 0):
                raise ValueError('invalid finishing measure')
        tol = 1e-9*max(1., state.released)
        origin_mass = math.fsum(e.mass for e in state.entering)
        finish_mass = math.fsum(e.mass for e in state.finishing)
        public_mass = state.traffic.released-state.traffic.completed
        if abs(state.released-state.completed-origin_mass-finish_mass-public_mass) > tol:
            raise ArithmeticError('whole journey mass balance')
        if abs(finish_mass-(state.traffic.completed-state.completed)) > tol:
            raise ArithmeticError('destination egress balance')
        prior = state.finished_origin_seconds+state.finished_entry_hold_seconds
        if abs(prior-state.traffic.pre_entry_seconds) > 1e-8*max(1.,prior):
            raise ArithmeticError('origin age boundary balance')
        parts = self.residence(state)
        if abs(sum(v for k,v in parts.items() if k != 'total')-parts['total']) > 1e-8*max(1.,abs(parts['total'])):
            raise ArithmeticError('whole journey residence balance')

    def step(self, state, offers=()):
        try:
            return self._step(state, tuple(offers))
        except BudgetExceeded as exc:
            exc.checkpoint = state
            raise

    def _step(self, state, offers):
        self.check(state)
        t = state.time_s
        entering = list(state.entering)
        released = 0.
        for tag, mass in offers:
            if tag not in self.boundaries or not math.isfinite(mass) or mass < 0:
                raise ValueError('invalid journey departure')
            released += mass
            if mass:
                entering.extend(AccessEntry(tag, mass*w, t, delay)
                                for delay,w in self.boundaries[tag].origin.atoms)
        entering = _merge_entries(entering)
        waiting, road_offers = [], []
        origin_done = state.finished_origin_seconds
        hold_done = state.finished_entry_hold_seconds
        for e in entering:
            if e.ready_s <= t:
                road_offers.append((e.tag, e.mass, e.mass*e.born_s))
                origin_done += e.mass*e.delay_s
                hold_done += e.mass*(t-e.ready_s)
            else:
                waiting.append(e)
        traffic, outlets = self.network.step_measures(state.traffic, road_offers)
        end = traffic.time_s
        spans = list(state.finishing)
        for e in outlets:
            if e.destination is not None:
                continue
            for delay, weight in self.boundaries[e.tag].destination.atoms:
                spans.append(FinishSpan(e.tag, e.mass*weight, e.start_s+delay, e.end_s+delay,
                                        e.birth_moment*weight))
        unfinished, completions = [], []
        complete = state.completed
        exit_moment = state.exit_moment
        for e in _merge_spans(spans):
            if end <= e.start_s:
                unfinished.append(e)
                continue
            stop = min(end, e.end_s)
            fraction = (stop-e.start_s)/(e.end_s-e.start_s)
            amount = e.mass*fraction
            moment = amount*(e.start_s+stop)/2
            complete += amount
            exit_moment += moment
            completions.append(FinishSpan(e.tag, amount, e.start_s, stop, e.birth_moment*fraction))
            if fraction < 1:
                unfinished.append(FinishSpan(e.tag, e.mass-amount, stop, e.end_s,
                                             e.birth_moment*(1-fraction)))
        out = JourneyState(self.identity, traffic, tuple(waiting), tuple(unfinished),
                           state.released+released, complete, state.birth_moment+released*t,
                           exit_moment, origin_done, hold_done)
        count = len(out.entering)+len(out.finishing)+self.network.counts(traffic)['parts']
        if count > self.record_budget:
            raise BudgetExceeded('journey access/egress record budget')
        self.check(out)
        return out, tuple(completions)

    def report(self, state):
        self.check(state)
        pending = state.released-state.completed
        cleared = pending <= 1e-9*max(1.,state.released)
        residence = self.residence(state)
        return dict(time_s=state.time_s, released=state.released, completed=state.completed,
                    remaining=max(0.,pending), mean_journey_s=state.system_vehicle_seconds/state.completed
                    if cleared and state.completed > 0 else None,
                    residence_vehicle_seconds=residence,
                    road_source_wait_seconds=state.traffic.source_wait_seconds,
                    road_transfer_hold_seconds=state.traffic.transfer_hold_seconds,
                    origin_records=len(state.entering), destination_records=len(state.finishing),
                    traffic_records=self.network.counts(state.traffic), per_car_records=0,
                    status='CLEARED_SCOPED' if cleared else 'HORIZON_REACHED')
