"""Conservative projection is a numerical closure with protected FIFO fronts."""
from dataclasses import replace
import math

import pytest

from metroflow.active_suffix.common import BudgetExceeded
from metroflow.entry_projection import project_entry_packets, projection_identity
from metroflow.packet_network import Part, interval_packets, _rates


def part(tag, a, b, mass=1.0, birth=0.0, remaining=("road", "out")):
    return Part(tag, remaining, mass, birth, a, b)


def moments(parts):
    by_tag = {}
    for p in parts:
        by_tag.setdefault((p.tag, p.remaining), []).append(p)
    return {k: (math.fsum(p.mass for p in ps),
                math.fsum(p.birth_moment for p in ps),
                math.fsum(p.mass * (p.entry_start_s +
                     (p.entry_end_s - p.entry_start_s) / 2) for p in ps))
            for k, ps in by_tag.items()}


def flat(packets):
    return tuple(p for packet in packets for p in packet.parts)


def test_repeated_descendants_do_not_create_one_packet_per_endpoint():
    rows = tuple(part("car", k / 1000, 1 - k / 1000) for k in range(40))
    exact = interval_packets(rows, 10., 10000)
    projected, stats = project_entry_packets(rows, 10., 10000, 1.)
    assert len(exact) == 79  # Real old behavior, not a mocked baseline.
    assert len(projected) == 1
    assert len(flat(projected)) == 1
    for key, expected in moments(rows).items():
        assert moments(flat(projected))[key] == pytest.approx(expected)
    assert stats["input_parts"] == 40 and stats["output_parts"] == 1


def test_each_category_mass_birth_and_entry_first_moment_survives():
    rows = (part("car", 10000.1, 10001.2, 2., 4.),
            part("car", 10000.8, 10001.7, 3., 5.),
            part("bus", 10000.2, 10001.6, .125, .02))
    packets, stats = project_entry_packets(rows, 3., 1000, .5)
    for key, expected in moments(rows).items():
        assert moments(flat(packets))[key] == pytest.approx(expected, rel=2e-15)
    assert all(p.mass > 0 and p.entry_start_s == p.entry_end_s for p in flat(packets))
    assert stats["local_w1_bound_veh_s"] <= math.fsum(p.mass for p in rows) * .5 / 2 * (1+1e-14)


def test_original_atoms_and_their_fifo_barriers_remain_exact():
    rows = (part("a", .49, .49), part("b", .51, .51), part("stream", 0., 1.))
    packets, _ = project_entry_packets(rows, 10., 1000, 1.)
    assert len(packets) == 5
    assert [(p.tag, p.entry_start_s, p.entry_end_s) for p in flat(packets)
            if p.tag in {"a", "b"}] == [("a", .49, .49), ("b", .51, .51)]
    assert [[p.tag for p in pk.parts] for pk in packets] == [
        ["stream"], ["a"], ["stream"], ["b"], ["stream"]]


def test_tiny_closed_turn_cannot_poison_an_earlier_open_only_front():
    rows = (part("open", 0., .5, remaining=("road", "open")),
            part("blocked", .5, 1., 1e-12, remaining=("road", "closed")))
    packets, stats = project_entry_packets(rows, 0., 100, 10.)
    assert len(packets) == 2
    assert stats["protected_support_boundaries"] >= 1
    first = {p.remaining[1]: p.mass / packets[0].mass for p in packets[0].parts}
    assert _rates({0: first}, {0: 1.}, {"open": 1., "closed": 0.}, {0: 1.})[0] == 1.
    # This is why mere tiny timing/amount error is not a network error bound.
    unsafe = {"open": 1/(1+1e-12), "closed": 1e-12/(1+1e-12)}
    assert _rates({0: unsafe}, {0: 1.}, {"open": 1., "closed": 0.}, {0: 1.})[0] == 0.


def test_overlapping_support_transitions_and_future_routes_are_distinct():
    rows = (part("a", 0., 1., remaining=("road", "shared", "later-a")),
            part("b", .25, .75, remaining=("road", "shared", "later-b")),
            part("c", .4, .6, remaining=("road", "other")))
    packets, _ = project_entry_packets(rows, 0., 100, 1.)
    assert len(packets) == 3  # .4 and .6 are real immediate-support changes.
    assert all(p.remaining == next(q.remaining for q in rows if q.tag == p.tag)
               for p in flat(packets))
    for key, expected in moments(rows).items():
        assert moments(flat(packets))[key] == pytest.approx(expected)


def test_width_zero_is_the_exact_oracle_and_identity_is_separate():
    rows = (part("a", 0., .7), part("b", .3, 1.))
    exact, stats = project_entry_packets(rows, 1., 100, 0.)
    assert exact == interval_packets(rows, 1., 100)
    assert stats["local_w1_bound_veh_s"] == 0.
    assert projection_identity("base", 0.) == "base"
    assert projection_identity("base", 1.) == "base:entry_projection_support_v1:3ff0000000000000"
    assert projection_identity("base", 1.) != projection_identity("base", .5)


@pytest.mark.parametrize("width", [-1., math.nan, math.inf, True])
def test_invalid_width_rejected(width):
    with pytest.raises(ValueError):
        project_entry_packets((part("a", 0., 1.),), 0., 100, width)


def test_unrepresentable_time_grid_and_record_budget_fail_explicitly():
    with pytest.raises((ValueError, ArithmeticError), match="resol|grid|width"):
        project_entry_packets((part("a", 1e10, 1e10+1.),), 0., 100, 1e-12)
    with pytest.raises(BudgetExceeded):
        project_entry_packets((part("a", 0., 1.), part("b", 0., 1.)), 0., 1, 1.)


def test_positive_mass_underflow_is_not_silent_pruning():
    rows = (part("a", 0., 2., math.ulp(0.)),)
    with pytest.raises(ArithmeticError, match="underflow"):
        project_entry_packets(rows, 0., 100, 1.)


def test_projection_bound_refines_independently_of_traffic_timestep():
    rows = (part("a", 0., 1.),)
    bounds = []
    for h in (1., .5, .25):
        packets, stats = project_entry_packets(rows, 0., 100, h)
        for key, expected in moments(rows).items():
            assert moments(flat(packets))[key] == pytest.approx(expected)
        bounds.append(stats["local_w1_bound_veh_s"])
    assert bounds == pytest.approx((.5, .25, .125))


def test_invalid_interval_or_measure_is_rejected():
    good = part("a", 0., 1.)
    for row in (replace(good, mass=-1), replace(good, entry_end_s=math.inf),
                replace(good, entry_start_s=None), replace(good, birth_moment=math.nan)):
        with pytest.raises(ValueError):
            project_entry_packets((row,), 0., 100, 1.)


def test_equal_time_atoms_keep_the_original_exchangeable_mixture():
    rows = (part("b", .5, .5), part("a", .5, .5), part("a", .5, .5, .25))
    projected, _ = project_entry_packets(rows, 2., 100, 1.)
    assert projected == interval_packets(rows, 2., 100)


def test_empty_gaps_do_not_allocate_unoccupied_time_bins():
    rows = (part("a", 0., 1.), part("b", 1e8, 1e8+1.))
    packets, _ = project_entry_packets(rows, 0., 10, 1.)
    assert len(packets) == 2


def test_network_projection_identity_prevents_cross_policy_state_reuse():
    from metroflow.ordered_lane import Lane
    from metroflow.ordered_network import Group, Route
    from metroflow.packet_network import PacketNetwork
    groups = (Group("a", "home", "middle", Lane(length_m=2)),
              Group("b", "middle", "dest", Lane(length_m=2)))
    routes = (Route("car", ("a", "b")),)
    exact = PacketNetwork(groups, routes, preserve_entry_intervals=True)
    projected = PacketNetwork(groups, routes, preserve_entry_intervals=True,
                              entry_projection_width_s=.5)
    assert exact.identity != projected.identity
    with pytest.raises(ValueError, match="identity"):
        projected.check(exact.initial())
    state = projected.initial()
    for i in range(20):
        state, _ = projected.step(state, (("car", .1),) if i < 3 else ())
        projected.check(state)
    assert state.released == pytest.approx(.3)
    assert state.completed == pytest.approx(.3)
