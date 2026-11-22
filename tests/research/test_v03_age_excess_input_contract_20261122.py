"""Regression cases for source-population and threshold semantics."""
from fractions import Fraction as F
import pytest
from metroflow.v1.age_excess_transport import (
    AgeBoundary, AgeCohort, finite_age_excess_transport,
)


def test_duplicate_threshold_does_not_duplicate_completed_physical_mass():
    x = finite_age_excess_transport(
        0, 3, (AgeCohort(1, 1, 0),),
        (AgeBoundary(F(3), 1, "out", 1, 0),), (2, F(2), 2),
    )[(1, F(2))]
    assert x.output_loss == 1
    assert x.tail_stock_time == 1
    assert x.output_mass == x.route_source_mass == 1


def test_duplicate_threshold_does_not_break_unfinished_endpoint_balance():
    x = finite_age_excess_transport(
        0, 3, (AgeCohort(1, 1, 0),), (), (2, F(2), 2),
    )[(1, F(2))]
    assert x.output_loss == 0
    assert x.tail_stock_time == x.terminal_loss == 1
    assert x.censored_tail_upper_bound(1) == 1


def test_explicit_internal_transfer_preserves_unique_source_exit_law():
    exit_event = AgeBoundary(F(3), 1, "out", 1, 0)
    initial = (AgeCohort(1, 1, 0),)
    baseline = finite_age_excess_transport(0, 3, initial, (exit_event,), (2,))
    for directions in (("out", "in"), ("in", "out")):
        internal = tuple(
            AgeBoundary(F(2), 1, d, 1, 0, kind="internal")
            for d in directions
        )
        measured = finite_age_excess_transport(
            0, 3, initial, (*internal, exit_event), (2,),
        )
        assert measured == baseline
        x = measured[(1, F(2))]
        assert x.output_mass == x.route_source_mass == 1
        assert x.fixed_source_cdf == 0
        assert x.censored_tail_upper_bound(1) == 1


def test_internal_transfer_requires_same_clock_route_birth_mass_cancellation():
    for bad_pair in (
        (AgeBoundary(F(2), 1, "out", 1, 0, kind="internal"),),
        (AgeBoundary(F(2), 1, "out", 1, 0, kind="internal"),
         AgeBoundary(F(2), 2, "in", 1, 0, kind="internal")),
        (AgeBoundary(F(2), 1, "out", 1, 0, kind="internal"),
         AgeBoundary(F(2), 1, "in", F(1, 2), 0, kind="internal")),
    ):
        with pytest.raises(ValueError, match="internal"):
            finite_age_excess_transport(0, 3, (AgeCohort(1, 1, 0),),
                                       bad_pair, (2,))


def test_declared_source_includes_assigned_but_not_yet_entered_population():
    x = finite_age_excess_transport(
        0, 3, (AgeCohort(1, 1, 0),),
        (AgeBoundary(F(3), 1, "out", 1, 0),), (3,),
        assigned_source_mass={1: 2, 2: 3},
    )
    route = x[(1, F(3))]
    assert route.completed_cdf == 1
    assert route.fixed_source_cdf == F(1, 2)
    assert route.route_source_mass == 2 and route.output_mass == 1
    assert route.censored_tail_upper_bound(1) == F(1, 2)
    pending = x[(2, F(3))]
    assert pending.output_loss == pending.output_mass == 0
    assert pending.fixed_source_cdf == 0
    assert pending.censored_tail_upper_bound(1) == 1


def test_declared_source_cannot_omit_or_undercount_admitted_population():
    for declared in ({}, {1: F(1, 2)}, {1: -1}):
        with pytest.raises(ValueError, match="source"):
            finite_age_excess_transport(
                0, 3, (AgeCohort(1, 1, 0),), (), (2,),
                assigned_source_mass=declared,
            )


def test_window_source_mass_removes_shared_checkpoint_stock_once():
    initial = (AgeCohort(1, 2, 0),)
    left_events = (AgeBoundary(F(2), 1, "out", 1, 0),)
    right_events = (
        AgeBoundary(F(4), 1, "in", 3, 4),
        AgeBoundary(F(5), 1, "out", 1, 4),
    )
    full = finite_age_excess_transport(
        0, 5, initial, left_events + right_events, (2,),
    )[(1, F(2))]
    left = finite_age_excess_transport(
        0, 3, initial, left_events, (2,),
    )[(1, F(2))]
    split_stock = F(1)
    right = finite_age_excess_transport(
        3, 5, (AgeCohort(1, split_stock, 0),), right_events, (2,),
    )[(1, F(2))]
    assert (left.route_source_mass, right.route_source_mass,
            full.route_source_mass) == (2, 4, 5)
    assert (left.route_source_mass + right.route_source_mass
            - split_stock) == full.route_source_mass
    completed_le = (left.output_mass - left.strict_output_tail_mass
                    + right.output_mass - right.strict_output_tail_mass)
    assert completed_le / full.route_source_mass == full.fixed_source_cdf == F(2, 5)


def test_7875_exact_censored_tail_bounds_against_direct_exit_counts():
    from itertools import product
    from metroflow.v1.age_excess_transport import AgeBoundary, AgeCohort
    checked = 0
    for ages in product(range(1, 6), repeat=3):
        events = tuple(AgeBoundary(F(age), 1, "out", 1, 0)
                       for age in sorted(ages))
        for unfinished in range(3):
            observed = finite_age_excess_transport(
                0, max(ages), (AgeCohort(1, 3, 0),), events, range(7),
                assigned_source_mass={1: 3 + unfinished},
            )
            for u in range(7):
                for gap in (F(1, 2), F(1), F(3)):
                    direct = F(unfinished + sum(F(age) >= F(u) + gap
                                               for age in ages),
                               3 + unfinished)
                    upper = observed[(1, F(u))].censored_tail_upper_bound(gap)
                    assert 0 <= direct <= upper <= 1
                    checked += 1
    assert checked == 7875
