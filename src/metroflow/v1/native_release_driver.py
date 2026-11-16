"""Whole FactorizedSchedule activation with native static and dynamic ownership.

The Python frontend binds the immutable city/calendar/fleet, supplies compact
marginal declarations, and stores opaque native checkpoints. It never enumerates
the OD calendar or converts physical state/history to Python containers.
"""
from dataclasses import asdict
import hashlib
import json

from ..active_suffix.common import BudgetExceeded
from .city import reject
from .native_engine import NativeWholeRuntime
from .release_driver import DriverState
from .release_plan import PlanCursor


class NativeReleaseDriver:
    engine_backend = 'rust_whole'

    def __init__(self, plan, inventory, *, step_s=10.0,
                 byte_budget=2 * 1024**3, record_budget=20000, event_budget=20000):
        totals = plan.totals()
        self.plan = plan
        self.runtime = NativeWholeRuntime(plan.city, plan.schedule, inventory,
            step_s=step_s, byte_budget=byte_budget, record_budget=record_budget,
            event_budget=event_budget)
        self.cursor = PlanCursor(plan.schedule.identity, totals['legs'],
            totals['persons'], totals['vehicles'], totals['cargo_kg'])
        plan.summary(self.cursor)
        self.identity = hashlib.sha256(json.dumps((plan.city.identity,
            plan.schedule.identity, self.runtime.identity, asdict(self.cursor)),
            sort_keys=True).encode()).hexdigest()

    def initial(self):
        return DriverState(self.identity, self.cursor, self.runtime.initial())

    def check(self, state):
        if state.driver_identity != self.identity or state.cursor != self.cursor:
            reject('native driver checkpoint calendar/runtime binding differs')
        self.plan.summary(state.cursor)
        self.runtime.check(state.runtime_state)

    def advance(self, state, end_s):
        self.check(state)
        try:
            updated = self.runtime.advance(state.runtime_state, end_s)
        except BudgetExceeded as exc:
            valid = getattr(exc, 'checkpoint', state.runtime_state)
            self.runtime.check(valid)
            exc.checkpoint = DriverState(self.identity, self.cursor, valid)
            raise
        return DriverState(self.identity, self.cursor, updated)

    def report(self, state):
        self.check(state)
        return dict(status='WHOLE_CALENDAR_ACTIVATED',
            activation='complete native preactivation; one shared occupied road',
            calendar=self.plan.summary(state.cursor),
            execution=self.runtime.report(state.runtime_state),
            full_local_acceptance='NOT_RUN')

    def save(self, path, state):
        self.check(state)
        # The native runtime binds city, schedule, fleet, step and budgets in
        # its binary checkpoint. No second Python state envelope is needed.
        self.runtime.save(path, state.runtime_state)

    def load(self, path):
        state = DriverState(self.identity, self.cursor, self.runtime.load(path))
        self.check(state)
        return state
