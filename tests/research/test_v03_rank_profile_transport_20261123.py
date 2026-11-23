"""Scoped exact-rational behavior checks for rank-profile transport."""
from collections import deque
from dataclasses import FrozenInstanceError
from fractions import Fraction as F

import pytest

from metroflow.v1.rank_profile_transport import (
    MarkedMass, RankSegment, RankProfile, ServiceWindow, TimedView,
    concat_adjacent, merge_streams, representation_stats, serve_windows,
    transport_moments,
)


def source():
    return RankProfile((
        RankSegment((MarkedMass("r", 2, 0), MarkedMass("b", 1, 0)), 10, (0, 0)),
        RankSegment((MarkedMass("r", 1, F(1, 2)), MarkedMass("b", 3, 1)), 10, (1, 1)),
        RankSegment((MarkedMass("r", 2, 2), MarkedMass("b", 1, F(3, 2))), 10, (2, 2)),
    ))


def oracle(profile, schedule):
    """Independent mutable proportional-head splitting, no profile/view calls."""
    queue = deque([
        [[p.mark, p.mass, p.birth_moment] for p in s.parts]
        for s in profile.segments
    ])
    totals = {}
    for window in schedule:
        remaining = window.rate * (window.end - window.start)
        clock = window.start
        while remaining:
            rows = queue[0]
            total = sum(p[1] for p in rows)
            take = min(remaining, total)
            fraction = take / total
            duration = take / window.rate
            for mark, m, b in rows:
                old = totals.setdefault(mark, [F(0), F(0), F(0)])
                old[0] += m * fraction
                old[1] += b * fraction
                old[2] += m * fraction * (clock + duration / 2)
            if take == total:
                queue.popleft()
            else:
                queue[0] = [[mark, m * (1 - fraction), b * (1 - fraction)]
                            for mark, m, b in rows]
            remaining -= take
            clock += duration
    return {mark: tuple(values) for mark, values in totals.items()}


def test_exact_service_matches_materialized_oracle_with_stop_windows():
    profile = source()
    rates = tuple(map(F, (0, "1/2", "3/2", 2, 0, "1/3", "5/3", 1, 2, 1)))
    schedule = tuple(ServiceWindow(F(3 + i), F(4 + i), q) for i, q in enumerate(rates))
    slices = serve_windows(profile.view(), schedule, require_complete=True)
    result = transport_moments(slices, displacement=lambda t: F(10))
    expected = oracle(profile, schedule)
    for mark, item in result.as_dict().items():
        assert (item.mass, item.birth_moment, item.exit_moment) == expected[mark]
    assert result.as_dict()["r"].exit_moment == F(701, 16)
    assert result.as_dict()["b"].exit_moment == F(2129, 48)
    assert result.readiness_checked and result.boundary_checked
    assert len(slices) == 8


def test_heterogeneous_adjacent_views_preserve_knots_and_do_not_average():
    p = source()
    a, b = p.view(0, 4), p.view(4, 10)
    joined = concat_adjacent((a, b))
    assert joined.profile is p
    assert len(tuple(joined.iter_pieces())) == 3
    assert joined.subview(0, 1).moments()["r"][0] == F(2, 3)
    assert joined.moments()["r"][0] / joined.mass == F(1, 2)
    assert representation_stats((a, b)) == {
        "profile_owners": 1, "segment_owners": 3, "mark_owners": 6,
        "view_count": 2, "stored_profile_segments": 3,
        "essential_profile_segments": 3, "profile_dag_depth": 1,
        "view_profile_depth": 2,
    }
    with pytest.raises(ValueError):
        concat_adjacent((a, p.view(5, 10)))
    with pytest.raises(ValueError):
        concat_adjacent((a, source().view(4, 10)))
    with pytest.raises(FrozenInstanceError):
        a.start = F(1)


def test_subview_semigroup_and_affine_boundary_clipping():
    p = RankProfile((RankSegment((MarkedMass("r", 3, 3),), 5, (2, 8)),))
    view = p.view(1, 2)
    piece, = tuple(view.iter_pieces())
    assert piece.boundary == (F(4), F(6))
    assert view.moments() == {"r": (F(1), F(1))}
    assert p.view().subview(1).subview(0, 1) == view
    assert p.view(3, 3).moments() == {}
    assert tuple(p.view(0, 0).iter_pieces()) == ()


def test_ready_frontier_and_boundary_checks_fail_closed():
    p = source()
    assert p.ready_prefix(9) == 0
    assert p.ready_prefix(10) == 10
    slices = serve_windows(p.view(), (ServiceWindow(3, 13, 1),))
    with pytest.raises(ValueError, match="precedes readiness"):
        transport_moments(slices, displacement=lambda t: F(9))
    unknown = RankProfile((RankSegment((MarkedMass("r", 1, 0),)),))
    with pytest.raises(ValueError, match="unknown"):
        unknown.ready_prefix(10)
    us = serve_windows(unknown.view(), (ServiceWindow(0, 1, 1),))
    with pytest.raises(ValueError, match="boundary metadata unknown"):
        transport_moments(us)
    with pytest.raises(ValueError, match="readiness metadata unknown"):
        transport_moments(us, check_boundary=False, displacement=lambda t: F(10))
    unchecked = transport_moments(us, check_boundary=False)
    assert not unchecked.readiness_checked and not unchecked.boundary_checked
    late = RankProfile((RankSegment((MarkedMass("r", 1, 0),), 0, (2, 2)),))
    with pytest.raises(ValueError, match="precedes declared boundary"):
        transport_moments(serve_windows(late.view(), (ServiceWindow(1, 2, 1),)))


def merge_inputs(refined=False):
    u = RankProfile((
        RankSegment((MarkedMass("U:r", 1, 1),), 0, (0, 0)),
        RankSegment((MarkedMass("U:b", 2, 4),), 0, (0, 0)),
    ))
    v = RankProfile((RankSegment((
        MarkedMass("V:r", F(1, 2), 0),
        MarkedMass("V:b", F(3, 2), F(9, 2)),
    ), 0, (0, 0)),))
    edges = tuple(map(F, (4, "17/4", "19/4", 5, "41/8", "11/2", 6))) if refined else (F(4), F(5), F(6))
    su = tuple(ServiceWindow(a, b, 1 if a < 5 else 2) for a, b in zip(edges, edges[1:]))
    sv = tuple(ServiceWindow(a, b, 1) for a, b in zip(edges, edges[1:]))
    return (serve_windows(u.view(), su, require_complete=True),
            serve_windows(v.view(), sv, require_complete=True))


def test_multi_input_merge_preserves_marks_births_and_partition_covariance():
    coarse = merge_streams(merge_inputs(), target_at_end=lambda t: F(10))
    fine = merge_streams(merge_inputs(True), target_at_end=lambda t: F(10))
    assert len(coarse.segments) == len(fine.segments) == 2
    assert coarse == fine
    for i in range(51):
        z = F(i, 10)
        assert coarse.view(0, z).moments() == fine.view(0, z).moments()
        t = 4 + z / 2 if z <= 2 else 5 + (z - 2) / 3
        before, after = min(F(1), t - 4), max(F(0), t - 5)
        expected = {
            "U:r": (before, before),
            "U:b": (2 * after, 4 * after),
            "V:r": ((t - 4) / 4, F(0)),
            "V:b": (3 * (t - 4) / 4, 9 * (t - 4) / 4),
        }
        actual = coarse.view(0, z).moments()
        for mark, pair in expected.items():
            assert actual.get(mark, (F(0), F(0))) == pair
    one = coarse.view(0, 1).moments()
    assert one["U:r"][0] + one["V:r"][0] == F(5, 8)
    assert coarse.view().moments()["U:b"][1] == 4  # original birth, not node entry
    assert coarse.segments[0].boundary == (F(4), F(5))
    assert coarse.segments[1].boundary == (F(5), F(6))


def test_end_admission_target_is_explicit_and_not_partition_invariant_by_default():
    coarse = merge_streams(merge_inputs(), target_at_end=lambda t: t)
    fine = merge_streams(merge_inputs(True), target_at_end=lambda t: t)
    assert coarse.ready_prefix(F(19, 4)) == 0
    assert fine.ready_prefix(F(19, 4)) > 0
    assert coarse.view().moments() == fine.view().moments()
    unknown = merge_streams(merge_inputs())
    with pytest.raises(ValueError, match="unknown"):
        unknown.ready_prefix(20)


def test_repeated_phase_shifted_merge_retains_real_knot_growth():
    p = RankProfile((
        RankSegment((MarkedMass("r", 1, 0),), 0, (0, 0)),
        RankSegment((MarkedMass("b", 1, 0),), 0, (0, 0)),
    ))
    counts = []
    for level in range(1, 5):
        base, delay = F(2 * level), F(1, 2 * level + 3)
        a = serve_windows(p.view(), (ServiceWindow(base, base + 1, p.mass),))
        b = serve_windows(p.view(), (ServiceWindow(base + delay, base + 1 + delay, p.mass),))
        old = p.view().moments()
        p = merge_streams((a, b), target_at_end=lambda t: F(0))
        counts.append(p.essential_segments)
        assert p.view().moments() == {
            mark: (2 * values[0], 2 * values[1]) for mark, values in old.items()
        }
    assert all(b > a for a, b in zip((2, *counts[:-1]), counts))
    assert p.essential_segments == len(p.segments)
    # No claim that flat profiles stay bounded under repeated interleaving.


def test_last_five_veh_can_compose_with_an_external_ready_clock():
    p = source()
    tail = p.view(p.mass - 5)
    slices = serve_windows(tail, (ServiceWindow(10, 15, 1),), require_complete=True)
    result = transport_moments(slices, displacement=lambda t: F(10)).as_dict()
    assert sum(item.mass for item in result.values()) == 5
    expected = tail.moments()
    for mark, item in result.items():
        assert (item.mass, item.birth_moment) == expected[mark]


def test_invalid_exact_domain_schedule_and_order_fail_closed():
    with pytest.raises(TypeError):
        MarkedMass("r", 0.5, 0)
    with pytest.raises(ValueError):
        MarkedMass("r", 0, 1)
    with pytest.raises(ValueError):
        RankSegment((MarkedMass("r", 0, 0),))
    with pytest.raises(ValueError):
        RankProfile((
            RankSegment((MarkedMass("r", 1, 0),), 2),
            RankSegment((MarkedMass("r", 1, 0),), 1),
        ))
    p = source()
    with pytest.raises(ValueError):
        p.view(-1, 1)
    with pytest.raises(ValueError, match="exceeds"):
        serve_windows(p.view(), (ServiceWindow(0, 11, 1),))
    with pytest.raises(ValueError, match="incomplete"):
        serve_windows(p.view(), (ServiceWindow(0, 1, 1),), require_complete=True)
    with pytest.raises(ValueError, match="overlapping"):
        serve_windows(p.view(), (ServiceWindow(0, 1, 1), ServiceWindow(F(1, 2), 2, 1)))
    with pytest.raises(ValueError, match="causal contiguous"):
        merge_streams(((TimedView(p.view(0, 1), 3, 4), TimedView(p.view(2, 3), 4, 5)),))
