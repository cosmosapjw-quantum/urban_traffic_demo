"""Atomic all-calendar preactivation around one occupied joint road state.

The current transport registry is immutable. Calendar pages therefore compile
before traffic starts; they are never separately simulated. This conservative
implementation rejects oversized calendars before enumerating any OD leg.
It does not claim dynamic route insertion into an occupied network.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import itertools
import math
from pathlib import Path
import tempfile

from ..active_suffix.common import BudgetExceeded
from .city import reject
from .joint_release_runtime import JointReleaseRuntime
from .release_plan import PlanCursor


@dataclass(frozen=True, slots=True)
class PreparationCheckpoint:
    city_identity: str
    cursor: PlanCursor
    calendar: tuple

    def report(self):
        return dict(status='BLOCKED_RESOURCE', city_identity=self.city_identity,
                    cursor=asdict(self.cursor), calendar=dict(self.calendar),
                    remaining_legs=dict(self.calendar)['legs'],
                    remaining_amounts={unit: dict(self.calendar)[unit]
                                       for unit in ('persons','vehicles','cargo_kg')},
                    units='calendar amounts count outward and return legs separately', simulated_s=0,
                    scope='no calendar leg enumerated and no road state created')


@dataclass(frozen=True, slots=True)
class DriverState:
    driver_identity: str
    cursor: PlanCursor
    runtime_state: object

    @property
    def time_s(self):
        return self.runtime_state.time_s


class ReleaseDriver:
    """One exact full-calendar registry and one JointReleaseRuntime instance.

    ``service_factory(city, legs, step_s=...)`` supplies an explicit fleet/depot
    plan over exactly those legs. Missing service assignments remain pending in
    the joint runtime; complete activation is not complete trip service.
    """
    def __init__(self, plan, service_factory, *, max_legs=20000, page_size=256,
                 step_s=1.0, record_budget=20000):
        for value in (max_legs, page_size):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                reject('positive calendar materialization/page budget required')
        totals = plan.totals()
        start = plan.cursor()
        if totals['legs'] > max_legs:
            exc = BudgetExceeded('whole calendar exceeds preactivation leg budget; no demand omitted')
            exc.status = 'BLOCKED_RESOURCE'
            exc.checkpoint = PreparationCheckpoint(plan.city.identity, start, tuple(totals.items()))
            raise exc
        # Only the joint runtime consumes physical routes/access laws. Calling
        # plan.take here resolved them once only to discard that work, and each
        # page replayed the preceding calendar prefix. Traverse exactly once.
        iterator = iter(plan.schedule.iter_legs())
        cursor, legs = start, []
        units = ('persons', 'vehicles', 'cargo_kg')
        amounts = [0.0, 0.0, 0.0]
        while len(legs) < totals['legs']:
            page = tuple(itertools.islice(iterator, min(page_size, totals['legs']-len(legs))))
            if not page:
                reject('calendar ended before declared exact leg total', 'IMPLEMENTATION_ERROR')
            legs.extend(page)
            # Preserve the existing page-wise summation/cursor representation.
            for i, unit in enumerate(units):
                amounts[i] += math.fsum(getattr(leg.amounts, unit) for leg in page)
        if next(iterator, None) is not None:
            reject('calendar exceeds declared exact leg total', 'IMPLEMENTATION_ERROR')
        cursor = PlanCursor(plan.schedule.identity, len(legs), *amounts)
        plan.summary(cursor)
        self.plan, self.cursor = plan, cursor
        services = service_factory(plan.city, tuple(legs), step_s=step_s)
        self.runtime = JointReleaseRuntime(plan.city, tuple(legs), services,
                        step_s=step_s, max_legs=max_legs, record_budget=record_budget)
        self.identity = hashlib.sha256(json.dumps((plan.city.identity, plan.schedule.identity,
                    self.runtime.identity, asdict(cursor)), sort_keys=True).encode()).hexdigest()

    def initial(self):
        return DriverState(self.identity, self.cursor, self.runtime.initial())

    def check(self, state):
        if state.driver_identity != self.identity or state.cursor != self.cursor:
            reject('driver checkpoint calendar/runtime binding differs')
        self.plan.summary(state.cursor)
        self.runtime.check(state.runtime_state)

    def advance(self, state, end_s):
        self.check(state)
        try:
            updated = self.runtime.advance(state.runtime_state, end_s)
        except BudgetExceeded as exc:
            # Runtime may have made valid immutable progress before its failure.
            valid = getattr(exc, 'checkpoint', state.runtime_state)
            self.runtime.check(valid)
            exc.checkpoint = DriverState(self.identity, state.cursor, valid)
            raise
        return DriverState(self.identity, state.cursor, updated)

    def report(self, state):
        self.check(state)
        return dict(status='WHOLE_CALENDAR_ACTIVATED',
                    activation='complete preactivation; no occupied-state insertion',
                    calendar=self.plan.summary(state.cursor),
                    execution=self.runtime.report(state.runtime_state),
                    full_local_acceptance='NOT_RUN')

    def save(self, path, state):
        self.check(state)
        path = Path(path)
        # Reuse the explicit service/road schema, then place cursor and runtime
        # in a single atomic file. There is no separate publishable sidecar.
        with tempfile.TemporaryDirectory(dir=path.parent) as directory:
            raw = Path(directory)/'runtime.json'
            self.runtime.save(raw, state.runtime_state)
            envelope = dict(schema='metroflow_release_driver_v1', driver_identity=self.identity,
                            cursor=asdict(state.cursor), runtime=json.loads(raw.read_text()))
            staged = Path(directory)/'checkpoint.json'
            staged.write_text(json.dumps(envelope, allow_nan=False))
            staged.replace(path)

    def load(self, path):
        path = Path(path)
        envelope = json.loads(path.read_text())
        if (set(envelope) != {'schema','driver_identity','cursor','runtime'}
                or envelope['schema'] != 'metroflow_release_driver_v1'
                or envelope['driver_identity'] != self.identity):
            reject('driver checkpoint envelope differs')
        cursor = PlanCursor(**envelope['cursor'])
        if cursor != self.cursor:
            reject('driver checkpoint calendar/runtime binding differs')
        with tempfile.TemporaryDirectory(dir=path.parent) as directory:
            raw = Path(directory)/'runtime.json'
            raw.write_text(json.dumps(envelope['runtime'], allow_nan=False))
            runtime_state = self.runtime.load(raw)
        state = DriverState(self.identity, cursor, runtime_state)
        self.check(state)
        return state
