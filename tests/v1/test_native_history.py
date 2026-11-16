"""Lossless native receipts: independent sums, clock edges, and rollback sharing."""
import math
import random

import pytest
from _metroflow_rust import NativeReceiptHistory


def test_native_history_preserves_every_raw_receipt_and_exact_totals():
    rng = random.Random(412)
    rows = [(rng.randrange(500) / 8, math.ldexp(rng.random(), rng.randrange(-1000, 0)))
            for _ in range(4097)]
    history = NativeReceiptHistory(rows)
    assert history.snapshot() == rows
    assert len(history) == len(rows)
    assert history.total() == math.fsum(fraction for _, fraction in rows)
    assert history.valid_at(max(t for t, _ in rows))
    assert not history.valid_at(math.nextafter(max(t for t, _ in rows), -math.inf))
    for dwell in (0., .1, 3.125, 100.):
        for now in (0., .1, 9.125, 30., 50., 62.5, 100., 200.):
            expected = math.fsum(f for t, f in rows if t + dwell <= now)
            assert history.eligible(dwell, now) == expected


def test_native_history_keeps_addition_order_at_eligibility_boundary():
    # (t+dwell<=now) and (t<=now-dwell) differ for these binary64 values.
    t, dwell, now = 1., math.ulp(1.) / 2, 1.
    assert t + dwell <= now and not t <= now - dwell
    history = NativeReceiptHistory([(t, .25)])
    assert history.eligible(dwell, now) == .25
    assert history.eligible(dwell, math.nextafter(now, -math.inf)) == 0.


def test_native_history_prefix_sums_match_fsum_across_block_boundaries():
    # Fractional sizes straddle rounding midpoints; query whole/partial blocks.
    fractions = [1., 2.**-53, 2.**-106, 2.**-500, math.ulp(0.)]
    rows = [(float(i // 3), fractions[i % len(fractions)]) for i in range(1025)]
    history = NativeReceiptHistory(rows)
    for count in (0, 1, 63, 64, 65, 127, 128, 129, 1023, 1024, 1025):
        now = count / 3
        for dwell in (0., 1., .1):
            assert history.eligible(dwell, now) == math.fsum(
                f for t, f in rows if t + dwell <= now)


def test_native_history_rollback_clones_share_prefix_and_diverge_losslessly():
    rows = [(float(i), (i + 1) / 2.**20) for i in range(4097)]
    old = NativeReceiptHistory(rows)
    pending = old.fork()
    assert old.shared_prefix_rows(pending) == len(rows)
    pending.append(5000., .25)
    assert old.snapshot() == rows
    assert pending.snapshot() == [*rows, (5000., .25)]
    assert old.shared_prefix_rows(pending) == 4096
    assert old.storage_shape() == (8, 65, 64)
    # Repeated mutable appends cannot mutate the shared rollback prefix.
    for i in range(130):
        pending.append(5001. + i, 2.**-20)
    assert old.snapshot() == rows
    assert old.shared_prefix_rows(pending) == 4096


@pytest.mark.parametrize("row", [(-1., .1), (math.nan, .1), (math.inf, .1),
                                  (1., 0.), (1., -1.), (1., math.nan), (1., math.inf)])
def test_native_history_rejects_bad_rows_without_mutation(row):
    history = NativeReceiptHistory([(0., .5)])
    with pytest.raises(ValueError):
        history.append(*row)
    assert history.snapshot() == [(0., .5)]
    with pytest.raises(ValueError):
        NativeReceiptHistory([row])


def test_native_history_overflow_does_not_modify_last_valid_rows():
    history = NativeReceiptHistory([(0., 1e308)])
    with pytest.raises(ValueError, match="overflow"):
        history.append(1., 1e308)
    assert history.snapshot() == [(0., 1e308)]


def test_native_empty_histories_allocate_no_block_and_long_chain_drops_iteratively():
    empty = NativeReceiptHistory([])
    assert empty.storage_shape() == (8, 0, 64)
    assert empty.total() == empty.eligible(0., 0.) == 0.
    # Thousands of blocks would recurse during ordinary Arc-chain destruction.
    history = NativeReceiptHistory([(float(i), 2.**-20) for i in range(160_000)])
    assert len(history) == 160_000
    assert history.total() == math.fsum([2.**-20] * 160_000)
    del history
