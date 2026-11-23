"""Property/exact-oracle plan for a new adapter; no legacy RED claim."""
from dataclasses import FrozenInstanceError
from fractions import Fraction as F
import itertools
import math
import unittest

_CASE = unittest.TestCase()

from metroflow.v1.fifo_rank import (CompositionRoot, RankDomainError, RankPrecisionError,
                       RankSpan, SourceRow, prefix_envelope, prefix_error_bound)


def fixture(exact=True):
    c = F if exact else float
    return (SourceRow(7, 2, c(2), c(6), -0.0, 8.0),
            SourceRow(3, 5, c(3), c(21), -0.0, 8.0),
            SourceRow(7, 2, c(1), c(2), -0.0, 8.0))


def test_hand_calculated_prefix_and_birth_oracle():
    head = RankSpan.from_rows(fixture())
    split = head.take_mass(F(3, 2), eligible_rank=F(2))
    # Independent 1/4-of-source oracle, with duplicate source tag preserved.
    actual = list(split.served.iter_rows())
    assert [(r.mass, r.birth) for r in actual] == [(F(1, 2), F(3, 2)),
                                                 (F(3, 4), F(21, 4)),
                                                 (F(1, 4), F(1, 2))]
    assert split.remainder.mass == F(9, 2)
    assert split.served.moments_by_key() == {(7, 2): (F(3, 4), F(2)),
                                           (3, 5): (F(3, 4), F(21, 4))}
    assert split.roundoff_mass == 0


def test_immutable_source_shared_without_remainder_row_copy():
    head = RankSpan.from_rows(fixture())
    split = head.take_mass(2, 6)
    split2 = split.remainder.take_mass(1, 6)
    for view in (split.served, split.remainder, split2.served, split2.remainder):
        assert view.root is head.root
        assert view.root.rows is head.root.rows
    assert head.lo == 0 and head.hi == 6
    with _CASE.assertRaises(FrozenInstanceError):
        head.lo = 1
    with _CASE.assertRaises(FrozenInstanceError):
        head.root.rows[0].mass = 99


def test_metadata_order_and_signed_zero_survive():
    head = RankSpan.from_rows(fixture())
    rows = list(head.take_mass(1, 6).remainder.iter_rows())
    assert [(r.tag, r.offset) for r in rows] == [(7, 2), (3, 5), (7, 2)]
    assert all(math.copysign(1, r.a) == -1 and r.b == 8.0 for r in rows)


def test_exact_rational_subdivision_equals_one_service():
    head = RankSpan.from_rows(fixture())
    emitted = [F(0)] * 3
    emitted_birth = [F(0)] * 3
    for amount in (F(1, 7), F(2, 9), F(13, 17), F(1, 23)):
        split = head.take_mass(amount, 6)
        for j, row in enumerate(split.served.iter_rows()):
            emitted[j] += row.mass
            emitted_birth[j] += row.birth
        head = split.remainder
    q = F(1, 7) + F(2, 9) + F(13, 17) + F(1, 23)
    # Manual proportional mixture rule, independently expressed by total q.
    assert emitted == [q / 3, q / 2, q / 6]
    assert emitted_birth == [q, F(7, 2) * q, q / 3]
    assert head.mass == 6 - q


def test_fraction_adapter_matches_original_repeated_fraction_rationally():
    head = RankSpan.from_rows(fixture())
    masses = [F(2), F(3), F(1)]
    births = [F(6), F(21), F(2)]
    for fraction in (F(2, 7), F(3, 11), F(1, 3), F(1)):
        split = head.take_fraction(fraction, 6)
        actual = list(split.served.iter_rows())
        for j in range(3):
            assert actual[j].mass == masses[j] * fraction
            assert actual[j].birth == births[j] * fraction
            masses[j] *= 1 - fraction
            births[j] *= 1 - fraction
        head = split.remainder
    assert head.mass == 0


def test_fifo_stopped_and_incrementing_eligibility():
    head = RankSpan.from_rows(fixture())
    head = head.take_mass(2, 2).remainder
    with _CASE.assertRaises(RankDomainError):
        head.take_mass(F(1, 100), 2)
    head = head.take_mass(1, 3).remainder
    assert head.lo == 3
    assert head.take_mass(3, 6).remainder.mass == 0


def test_float_conservation_at_explicit_adapter_tolerances():
    head = RankSpan.from_rows(fixture(False))
    served = [[] for _ in range(3)]
    served_birth = [[] for _ in range(3)]
    for k in range(10000):
        split = head.take_fraction(1.0 / (20000 - k), 6.0)
        for j, row in enumerate(split.served.iter_rows()):
            served[j].append(row.mass)
            served_birth[j].append(row.birth)
        head = split.remainder
    remaining = list(head.iter_rows())
    for j, source in enumerate(fixture(False)):
        assert abs(math.fsum(served[j]) + remaining[j].mass - source.mass) <= 1e-9 * max(1, source.mass)
        assert abs(math.fsum(served_birth[j]) + remaining[j].birth - source.birth) <= 1e-8 * max(1, source.birth)
        assert abs(remaining[j].mass - source.mass / 2) <= 1e-9 * max(1, source.mass)


def test_subulp_positive_service_is_not_silently_lost():
    span = RankSpan(CompositionRoot.from_rows([SourceRow(0, 0, 1e16, 0.0)]),
                    1e16 - 2, 1e16)
    with _CASE.assertRaises(RankPrecisionError):
        span.take_mass(0.1, 1e16)
    tiny = RankSpan.from_rows([SourceRow(0, 0, 5e-324, 0.0)])
    with _CASE.assertRaises(RankPrecisionError):
        tiny.take_fraction(0.5, tiny.hi)
    heterogeneous = RankSpan.from_rows([SourceRow(0, 0, 5e-324, 0.0),
                                       SourceRow(1, 0, 1.0, 1.0)])
    with _CASE.assertRaises(RankPrecisionError):
        list(heterogeneous.take_mass(0.5, 1.0).served.iter_rows())


def test_zero_service_empty_span_and_zero_source_rows():
    head = RankSpan.from_rows([SourceRow(0, 0, F(0), F(0)), SourceRow(1, 0, F(1), F(2))])
    split = head.take_mass(0, 0)
    assert split.served.mass == 0 and split.remainder.mass == 1
    assert len(list(split.served.iter_rows())) == 2
    empty = head.take_mass(1, 1).remainder
    assert empty.take_mass(0, 1).served.mass == 0
    with _CASE.assertRaises(RankDomainError):
        empty.take_mass(F(1, 100), 1)
    with _CASE.assertRaises(RankDomainError):
        RankSpan.from_rows([])
    with _CASE.assertRaises(RankDomainError):
        RankSpan.from_rows([SourceRow(0, 0, 0, 0)])


def test_invalid_source_mass():
    for bad in [-1, math.nan, math.inf, -math.inf, True, "1"]:
        with _CASE.assertRaises(RankDomainError):
            SourceRow(0, 0, bad, 0)


def test_invalid_fractions():
    for fraction in [-0.01, 1.01, math.nan, math.inf]:
        with _CASE.assertRaises(RankDomainError):
            RankSpan.from_rows(fixture(False)).take_fraction(fraction, 6.0)


def test_source_and_span_domain_edges():
    for args in [(0, 0, 1, -1), (0, 0, 0, 1), (-1, 0, 1, 0), (0, 0, 1, 0, 2, 1),
                 (0, 0, 1, 0, 1, None)]:
        with _CASE.assertRaises(RankDomainError):
            SourceRow(*args)
    head = RankSpan.from_rows(fixture())
    for lo, hi in [(-1, 1), (4, 3), (0, 7)]:
        with _CASE.assertRaises(RankDomainError):
            RankSpan(head.root, lo, hi)
    with _CASE.assertRaises(RankDomainError):
        head.take_fraction(0.5, 6)
    with _CASE.assertRaises(RankDomainError):
        head.take_mass(1, 7)


def test_sharp_prefix_envelope_and_all_binary_profiles_through_eight():
    for n in range(1, 9):
        for labels in itertools.product((0, 1), repeat=n):
            for k in range(n + 1):
                lo, hi, approx, bound = prefix_envelope(n, sum(labels), k)
                truth = sum(labels[:k])
                assert lo <= truth <= hi
                assert abs(truth - approx) <= bound <= F(n, 4)
    lo, hi, approx, bound = prefix_envelope(2, 1, 1)
    assert (lo, hi, approx, bound) == (0, 1, F(1, 2), F(1, 2))
    assert prefix_envelope(0, 0, 0) == (0, 0, 0, 0)
    with _CASE.assertRaises(RankDomainError):
        prefix_error_bound(-1, F(1, 2))


def test_fixed_block_prefix_errors_do_not_accumulate_over_service_calls():
    # Four whole blocks cancel; only the final half A/B block can disagree.
    blocks = [(0, 1), (1, 1), (0, 0), (1, 0), (1, 0)]
    truth_prefix = 0
    approx_prefix = F(0)
    for block in blocks:
        for j in range(1, 3):
            truth = truth_prefix + sum(block[:j])
            approx = approx_prefix + F(sum(block), 2) * j
            assert abs(truth - approx) <= F(1, 2)  # delta/4, delta=2
        truth_prefix += sum(block)
        approx_prefix += sum(block)


if __name__ == "__main__":
    suite = unittest.TestSuite(unittest.FunctionTestCase(fn)
                               for name, fn in globals().copy().items()
                               if name.startswith("test_") and callable(fn))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
