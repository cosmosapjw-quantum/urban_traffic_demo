"""Queue lifetime and failed-candidate ownership, independent of full-city size."""
import math

import pytest
from _metroflow_rust import NativeJourneyCore, NativeServiceCore


def internal_core(*, budget=100, delays=((3., .25), (5., .75))):
    return NativeJourneyCore([
        ("internal", 8., None, 0., [(0., 8., 1.)], 2, list(delays), [(0., 1.)]),
    ], [], [], budget)


def finish(core, end):
    core.finish(end, [], [], [], [], [], [], [])


def test_delayed_stages_retire_once_and_keep_every_completion_clock():
    core = internal_core()
    expected_queue = []
    expected_receipts = []
    for start in range(17):
        before = core.snapshot()
        offers, allowed = core.prepare()
        assert offers == allowed == []
        assert core.snapshot() == before  # preparation never changes committed state
        if 1 <= start <= 8:
            born = start - .5
            expected_queue.extend([(0, .25, born, 3.), (0, .75, born, 5.)])
        retained = []
        for row in expected_queue:
            if row[2] + row[3] <= start + 1 + 1e-10:
                expected_receipts.append((max(float(start), row[2] + row[3]), row[1] / 8.))
            else:
                retained.append(row)
        expected_queue = retained
        finish(core, start + 1)
        state = core.snapshot()
        assert state[1] == state[2] == []
        assert state[3] == expected_queue
        assert state[6][0] == expected_receipts
        assert len(state[3]) + len(state[6][0]) == 2 * min(start, 8)
    state = core.snapshot()
    assert state[3] == [] and len(state[6][0]) == 16
    assert state[4] == state[5] == [8.]
    assert state[7] == [32.]
    assert math.fsum(f for _, f in state[6][0]) == 1.
    assert core.queue_storage() == ([0, 0, 0, 16], [0, 0, 0])


def test_stage_growth_without_any_history_hits_budget_and_aborts_candidate():
    core = internal_core(budget=10, delays=((1000., .25), (2000., .75)))
    # Five source intervals create ten waiting atoms; none is a receipt.
    for end in range(1, 7):
        core.prepare()
        finish(core, end)
    before = core.snapshot()
    assert before[0] == 6 and len(before[3]) == 10 and before[6] == [[]]
    for _ in range(2):
        core.prepare()
        with pytest.raises(MemoryError, match="record budget"):
            finish(core, 7)
        assert core.snapshot() == before
        # A failed candidate is consumed, not retained alongside committed
        # queues; retry starts a fresh preparation from the same exact state.
        with pytest.raises(ValueError, match="without prepare"):
            finish(core, 7)


def test_rejected_journey_clock_consumes_candidate_without_changing_state():
    core = internal_core()
    before = core.snapshot()
    core.prepare()
    with pytest.raises(ValueError, match="clock"):
        finish(core, float("nan"))
    assert core.snapshot() == before
    core.prepare()  # no stale pending transition after the rejected finish
    finish(core, 1.)
    assert core.snapshot()[0] == 1.


def test_rejected_service_finish_aborts_uncommitted_dispatch_and_can_retry():
    core = NativeServiceCore([], [], [("delivery", 0., 1.)], [])
    before = core.snapshot()
    assert core.prepare(0., []) == [("freight:delivery", 1., 0.)]
    with pytest.raises(ValueError, match="conservation"):
        core.finish(1., [("freight:delivery", 2., 1.)])
    assert core.snapshot() == before
    assert core.prepare(0., []) == [("freight:delivery", 1., 0.)]
    core.finish(1., [("freight:delivery", 1., 1.)])
    assert core.snapshot()[2:4] == ([True], [1.])


def test_missing_parent_sentinel_stays_pending_without_invalid_history_lookup():
    # The legacy frontend explicitly uses len(legs) for an absent parent.
    leg = ("orphan", 1., 1, 0., [(0., 1., 1.)], 2, [(0., 1.)], [(0., 1.)])
    core = NativeJourneyCore([leg], [], [], 100)
    for end in range(1, 4):
        assert core.prepare() == ([], [])
        finish(core, end)
    state = core.snapshot()
    assert state[4] == state[5] == state[7] == [0.]
    assert state[6] == [[]]
    with pytest.raises(ValueError, match="journey leg"):
        NativeJourneyCore([(leg[0], leg[1], 2, *leg[3:])], [], [], 100)
