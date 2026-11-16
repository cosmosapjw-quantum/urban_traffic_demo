"""Persistent storage must preserve rows, ordering, clocks and allocation bounds."""
import math
import random

import pytest
from _metroflow_rust import NativeReceiptHistory, NativeStageQueue


def test_stage_fork_shares_rows_and_tail_append_is_immutable():
    rows = [(i, (i + 1) / 8192., float(i), 5000.) for i in range(1025)]
    original = NativeStageQueue(rows)
    candidate = original.fork()
    assert original.shared_rows(candidate) == len(rows)
    extra = (1025, .5, 1025., 5000.)
    limit = candidate.append_upper_bytes(1)
    candidate.append(extra)
    assert candidate.storage_shape()[3] <= limit
    assert original.snapshot() == rows
    assert candidate.snapshot() == [*rows, extra]
    assert original.shared_rows(candidate) == 1024


def test_stage_retirement_keeps_global_order_and_future_blocks_shared():
    # Unsorted readiness within a block and across blocks rules out a FIFO
    # cursor or sorting that changes source-to-road and receipt accumulation.
    rng = random.Random(572)
    rows = [(i, (i + 1) / 8192., float(i % 4), float(rng.randrange(50)))
            for i in range(777)]
    future = [(777 + i, .25, 1000., 1.) for i in range(512)]
    queue = NativeStageQueue([*rows, *future])
    old = queue.fork()
    remaining = [*rows, *future]
    for deadline in (0., 1., 10., 30., 54., 1000., 1001.):
        expected = [a for a in remaining if a[2] + a[3] <= deadline]
        assert queue.due_count(deadline) == len(expected)
        assert queue.retire_due(deadline) == expected
        remaining = [a for a in remaining if a[2] + a[3] > deadline]
        assert queue.snapshot() == remaining
        assert old.snapshot() == [*rows, *future]
        if deadline < 1001.:
            assert old.shared_rows(queue) >= 256
    assert queue.storage_shape() == (0, 0, 0, 0)


def test_stage_ready_predicate_uses_original_rounded_addition():
    born, delay, now = 1., math.ulp(1.) / 2, 1.
    assert born + delay <= now and not born <= now - delay
    row = (0, .5, born, delay)
    queue = NativeStageQueue([row])
    assert queue.due_count(math.nextafter(now, -math.inf)) == 0
    assert queue.retire_due(now) == [row]


def test_capacity_bound_covers_fragmented_registry_and_repeated_tail_growth():
    # Retain one row from each block, then extend repeatedly. Capacity is real
    # allocated storage, not merely logical_len * sizeof(row).
    rows = [(i, 1., 0., 1000. if i % 256 == 0 else 0.) for i in range(20_000)]
    queue = NativeStageQueue(rows)
    queue.retire_due(1.)
    for i in range(700):
        upper = queue.append_upper_bytes(1)
        queue.append((20_000 + i, 1., 0., 1000.))
        assert queue.storage_shape()[3] <= upper
    assert queue.retire_due(1000.) == [a for a in rows if a[3] == 1000.] + [
        (20_000 + i, 1., 0., 1000.) for i in range(700)]
    assert queue.storage_shape() == (0, 0, 0, 0)


@pytest.mark.parametrize("row", [(0, 0., 1., 1.), (0, -1., 1., 1.),
    (0, math.nan, 1., 1.), (0, 1., -1., 1.), (0, 1., 1., math.inf)])
def test_invalid_stage_append_cannot_change_shared_checkpoint(row):
    queue = NativeStageQueue([(0, 1., 0., 3.)])
    before = queue.snapshot()
    with pytest.raises(ValueError, match="stage row"):
        queue.append(row)
    assert queue.snapshot() == before


def test_history_allocation_cache_tracks_fork_growth_without_changing_receipts():
    assert NativeReceiptHistory([]).storage_bytes() == 0
    rows = [(float(i), math.ldexp(1., -10 - i % 500)) for i in range(129)]
    original = NativeReceiptHistory(rows)
    original_bytes = original.storage_bytes()
    candidate = original.fork()
    assert candidate.storage_bytes() == original_bytes
    for i in range(200):
        upper = candidate.append_upper_bytes()
        candidate.append(200. + i, 2.**-20)
        assert candidate.storage_bytes() <= upper
        assert original.storage_bytes() == original_bytes
    assert original.snapshot() == rows
    assert candidate.total() == math.fsum(f for _, f in candidate.snapshot())
