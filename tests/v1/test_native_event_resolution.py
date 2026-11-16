"""Positive sub-ULP head events retain mass and a bounded compensated clock.

The rate integrals below use rational arithmetic, independently of either
implementation. Oracle agreement alone is not evidence of exact mass splitting.
"""
from dataclasses import asdict, replace
from fractions import Fraction
import math

import pytest

from metroflow.foundation_kinetics import VehicleClass
from metroflow.ordered_lane import Lane
from metroflow.ordered_network import Group, Route
from metroflow.packet_network import PacketNetwork, Packet, Part, _EventClock
from metroflow.v1.kinetics import ClassMass
from metroflow.v1.native_road import NativeRoadNetwork
from metroflow.v1.transport import FiniteResponseMotion
from test_native_road import close


def ready_heads(masses, competing_mass=None, rate=1.):
    names = ('a',) if competing_mass is None else ('a', 'b')
    vehicle = VehicleClass('car')
    groups = tuple(Group(name, 'origin-' + name, 'sink',
        Lane(length_m=1., speed_mps=1., entry_rate=10.,
             exit_rate=rate if name == 'a' else 1.)) for name in names)
    motion = FiniteResponseMotion((ClassMass(vehicle, 1., latent=.5, gap_scale_m=4.),),
                                  (('car', 1.),))
    model = PacketNetwork(groups, tuple(Route(name, (name,)) for name in names),
        dt_s=1., vehicle_classes={name: vehicle for name in names},
        space_capacities_m={name: 1000. for name in names},
        standing_gap_m=2., motion=motion, preserve_entry_intervals=True,
        record_budget=10000)
    initial = model.initial()
    batches = [masses] + ([] if competing_mass is None else [[competing_mass]])
    cells = tuple(replace(cell, admitted=math.fsum(batch), packets=tuple(
        Packet(0., (Part(name, (name,), mass, 0.),)) for mass in batch))
        for name, cell, batch in zip(names, initial.cells, batches))
    total = math.fsum(mass for batch in batches for mass in batch)
    state = replace(initial, cells=cells, released=total,
                    class_ledger=(replace(initial.class_ledger[0], released=total),))
    model.check(state)
    return model, state


def compare_step(model, before, duration):
    native = NativeRoadNetwork(model)
    actual, events = native.advance_interval(before, duration)
    expected, reference_events = model.advance_interval(before, duration)
    close(asdict(actual), asdict(expected))
    close(tuple(asdict(e) for e in events), tuple(asdict(e) for e in reference_events))
    model.check(actual)
    return native, actual, events


def rational_mass(events, tag):
    return sum((Fraction(e.mass) for e in events if e.tag == tag), Fraction())


def test_two_positive_heads_do_not_require_time_word_to_change():
    tiny = 2.**-54
    model, before = ready_heads([1., tiny])
    native, after, events = compare_step(model, before, 2.)
    assert [event.mass for event in events] == [1., tiny]
    assert rational_mass(events, 'a') == Fraction(1) + Fraction(tiny)
    assert after.cells[0].packets == ()
    count, processed, residual, weighted = native.native.event_resolution_diagnostics()
    assert count == 1 and processed >= tiny and residual == 0.
    assert weighted >= tiny and processed + residual <= 1e-10


@pytest.mark.parametrize('count,tiny', [(1, 2.**-54), (128, 2.**-60), (8, 2.**-108)])
def test_competing_head_rate_integral_and_mass_split_error_are_bounded(count, tiny):
    model, before = ready_heads([1.] + [tiny] * count, competing_mass=16.)
    native, after, events = compare_step(model, before, 2.)
    assert [event.mass for event in events if event.tag == 'a'] == [1.] + [tiny] * count
    assert rational_mass(events, 'a') == Fraction(1) + count * Fraction(tiny)
    hits, processed, residual, weighted = native.native.event_resolution_diagnostics()
    assert hits >= count and processed >= count * tiny
    assert processed + residual <= 1e-10
    # Exact continuous sink rate of B is 1 veh/s for exactly 2 s. Binary64
    # splitting can leave its large remainder unchanged during tiny A events.
    # This bound reports that limitation instead of asserting false exactness.
    allowance = Fraction(weighted + 32 * math.ulp(16.))
    assert abs(rational_mass(events, 'b') - Fraction(2)) <= allowance
    remaining = sum((Fraction(part.mass) for packet in after.cells[1].packets
                     for part in packet.parts), Fraction())
    assert abs(rational_mass(events, 'b') + remaining - Fraction(16)) <= allowance
    assert all(0 <= e.start_s <= e.end_s <= 2. + 1e-10 for e in events)


def test_actual_probe_values_close_endpoint_even_when_high_word_is_already_dt():
    cursor, tiny_h = 8.221431926605018, 6.538054381607992e-16
    clock = _EventClock()
    clock.hi, clock.active = cursor, True
    assert clock.advance(tiny_h, None)
    assert clock.advance(clock.remaining(10.), 10.)
    assert clock.hi == 10. and clock.lo < 0. and clock.remaining(10.) > 0.
    assert clock.advance(clock.remaining(10.), 10.)
    assert (clock.hi, clock.lo) == (10., 0.)
    model, before = ready_heads([cursor * .45, 2.9421244717235964e-16],
                               competing_mass=16., rate=.45)
    native, _, events = compare_step(model, before, 10.)
    assert native.native.event_resolution_diagnostics()[0] >= 1
    assert abs(rational_mass(events, 'b') - Fraction(10)) <= Fraction(1e-12)


def test_compensated_clock_retains_third_word_error_and_resets_idle_future():
    clock = _EventClock()
    clock.hi, clock.lo, clock.active = 1., 2.**-54, True
    assert not clock.advance(2.**-108, None)
    assert (clock.hi, clock.lo) == (1., 2.**-54)
    assert clock.clock_roundoff_bound >= 2.**-108
    assert Fraction(clock.remaining(2.)) <= Fraction(1)
    clock.jump(2.)
    assert (clock.hi, clock.lo) == (2., 0.)
    assert clock.advance(4., None)  # h > hi needs general TwoSum, not FastTwoSum
    assert (clock.hi, clock.lo) == (6., 0.)


def test_future_and_horizon_subtraction_roundoff_is_explicitly_bounded():
    clock = _EventClock()
    clock.hi, clock.lo, clock.active = .125, 1e-20, True
    assert clock.remaining(.125) == -1e-20
    clock.advance(clock.remaining(10.), 10.)
    assert clock.hi == 10. and clock.lo > 0. and clock.remaining(10.) < 0.
    assert clock.clock_roundoff_bound >= clock.lo
    assert clock.clock_roundoff_bound < 1e-10


def test_subulp_policy_preserves_refined_horizon_and_positive_mass():
    tiny = 2.**-54
    model, before = ready_heads([1., tiny], competing_mass=16.)
    coarse, coarse_state, coarse_events = compare_step(model, before, 2.)
    fine = NativeRoadNetwork(model)
    middle, first = fine.advance_interval(before, 1.)
    fine_state, second = fine.advance_interval(middle, 1.)
    fine_events = first + second
    assert rational_mass(coarse_events, 'a') == rational_mass(fine_events, 'a')
    for events in (coarse_events, fine_events):
        assert abs(rational_mass(events, 'b') - Fraction(2)) <= Fraction(1e-12)
    assert coarse_state.completed == pytest.approx(fine_state.completed, abs=1e-12)
    assert coarse_state.exit_moment == pytest.approx(fine_state.exit_moment, abs=1e-12)
    assert coarse.native.event_resolution_diagnostics()[0] > 0


def test_ordinary_path_does_not_activate_compensated_policy():
    model, before = ready_heads([.125, .25], competing_mass=16.)
    native, _, _ = compare_step(model, before, 2.)
    assert native.native.event_resolution_diagnostics() == (0, 0., 0., 0.)


def test_subulp_roundoff_budget_failure_keeps_exact_valid_native_checkpoint():
    model, before = ready_heads([1.] + [2.**-54] * 3, rate=2.**-20)
    native = NativeRoadNetwork(model)
    native.restore(before)
    encoded = native.native.snapshot()
    # The first head sets cursor=2**20. Each tiny head needs 2**-34 s;
    # two such unrepresentable durations exceed the unchanged 1e-10 s gate.
    with pytest.raises(ArithmeticError, match="compensated clock roundoff budget"):
        native.advance_interval(before, 2.**20 + 1.)
    assert native.native.snapshot() == encoded
    assert native.snapshot() == before
    assert native.native.event_resolution_diagnostics() == (0, 0., 0., 0.)
    with pytest.raises(ArithmeticError, match="compensated clock roundoff budget"):
        model.advance_interval(before, 2.**20 + 1.)


def test_zero_duration_underflow_still_refuses_and_preserves_native_checkpoint():
    model, before = ready_heads([1e-300], rate=1e100)
    native = NativeRoadNetwork(model)
    native.restore(before)
    encoded = native.native.snapshot()
    with pytest.raises(ArithmeticError, match="reason=nonpositive_duration"):
        native.advance_interval(before, 1.)
    assert native.native.snapshot() == encoded
    assert native.snapshot() == before
    assert native.native.event_resolution_diagnostics() == (0, 0., 0., 0.)
