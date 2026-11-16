"""Thin frontend for one Rust whole-calendar road/service/journey owner.

The only demand inputs crossing Python are marginal activity/profile declarations.
No TripLeg list or Python runtime/helper graph is constructed by this backend.
Opaque immutable snapshots retain native state and preserve branching/rewind.
"""
import math
from pathlib import Path
import tempfile

from ..active_suffix.common import BudgetExceeded
from .native_calendar import compile_native_factorized_calendar
from .native_static import prepare_native_static


class NativeWholeRuntime:
    def __init__(self, city, schedule, inventory, *, step_s=10.0,
                 byte_budget=2 * 1024**3, record_budget=20000, event_budget=20000):
        from _metroflow_rust import NativeWholeEngine

        if isinstance(byte_budget, bool) or not isinstance(byte_budget, int) or byte_budget <= 0:
            raise ValueError("positive integer native byte budget required")
        payload = prepare_native_static(city, schedule, inventory, step_s=step_s,
                                        record_budget=record_budget, event_budget=event_budget)
        try:
            calendar = compile_native_factorized_calendar(schedule, byte_budget=byte_budget)
            self.native = NativeWholeEngine(calendar, payload, byte_budget)
        except MemoryError as cause:
            exc = BudgetExceeded(str(cause))
            exc.status = "BLOCKED_RESOURCE"
            raise exc from cause
        self.identity = self.native.identity
        self.step_s = step_s
        self.last_advance_metrics = dict(tick_times_s=[], peak_records=0,
            scope="native complete tick including rollback copying; no Python leg snapshots")

    def initial(self):
        return self.native.initial()

    def check(self, state):
        self.native.check(state)

    def advance(self, state, end_s):
        self.check(state)
        count = (end_s - state.time_s) / self.step_s
        if not math.isfinite(count) or count < 0 or abs(count-round(count)) > 1e-8:
            raise ValueError("joint horizon must align with fixed step")
        try:
            return self.native.advance(state, end_s)
        except Exception as cause:
            exc = BudgetExceeded(str(cause)) if isinstance(cause, MemoryError) else cause
            exc.checkpoint = self.native.snapshot()
            if exc is cause:
                raise
            exc.status = "BLOCKED_RESOURCE"
            raise exc from cause
        finally:
            times, peak = self.native.advance_metrics()
            self.last_advance_metrics = dict(tick_times_s=times, peak_records=peak,
                scope="native complete tick including rollback copying; no Python leg snapshots")

    def report(self, state):
        return self.native.report(state)

    def sample_legs(self, state, indices):
        """Bounded diagnostics only; never converts the full calendar to Python."""
        return self.native.sample_legs(state, list(indices))

    def save(self, path, state):
        self.check(state)
        path = Path(path)
        with tempfile.TemporaryDirectory(dir=path.parent) as directory:
            staged = Path(directory) / "native.checkpoint"
            self.native.save(str(staged), state)
            staged.replace(path)

    def load(self, path):
        return self.native.load(str(path))
