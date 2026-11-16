"""Native road physics is compared with the existing independent Python oracle."""
from dataclasses import asdict, replace
import math

import pytest

from metroflow.active_suffix.common import BudgetExceeded, Signal
from metroflow.foundation_kinetics import VehicleClass
from metroflow.ordered_lane import Lane
from metroflow.ordered_network import Group, Route
from metroflow.packet_network import PacketNetwork
from metroflow.v1.kinetics import ClassMass
from metroflow.v1.native_road import NativeRoadNetwork
from metroflow.v1.transport import FiniteResponseMotion


def road(*, budget=10000, windows=True, signals=True, intervals=True):
    car = VehicleClass('car', preferred_mps=10)
    bus = VehicleClass('bus', preferred_mps=8, response_s=3, length_m=12)
    freight = VehicleClass('freight', preferred_mps=7, length_m=9)
    groups = (
        Group('a', 'home', 'j', Lane(length_m=12, speed_mps=9, entry_rate=2, exit_rate=1.1),
              signal=Signal(10, 6) if signals else None),
        Group('b', 'j', 'sink', Lane(length_m=15, speed_mps=9, entry_rate=1, exit_rate=.8)),
        Group('c', 'j', 'alt', Lane(length_m=7, speed_mps=9, entry_rate=1.5, exit_rate=1)),
        Group('d', 'other', 'j', Lane(length_m=8, speed_mps=9, entry_rate=2, exit_rate=.7),
              priority=2),
    )
    routes = (Route('z', ('a', 'b')), Route('alias', ('a', 'b')),
              Route('a', ('a', 'c')), Route('merge', ('d', 'b')))
    classes = {'z': car, 'alias': car, 'a': bus, 'merge': freight}
    templates = tuple(ClassMass(c, 1, latent=p, gap_scale_m=4)
                      for c, p in ((car, .8), (bus, .6), (freight, .9)))
    motion = FiniteResponseMotion(templates, (('car', 8.), ('bus', 3.), ('freight', 5.)))
    return PacketNetwork(groups, routes, dt_s=1, windows=(('b', 10, 15, 0.),) if windows else (),
                         record_budget=budget, vehicle_classes=classes,
                         space_capacities_m={g.id: 200. for g in groups}, standing_gap_m=2.,
                         motion=motion, preserve_entry_intervals=intervals)


def close(actual, expected, path='state'):
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys(), path
        for key in expected:
            close(actual[key], expected[key], path + '.' + key)
    elif isinstance(expected, (tuple, list)):
        assert len(actual) == len(expected), path
        for i, (a, e) in enumerate(zip(actual, expected)):
            close(a, e, f'{path}[{i}]')
    elif isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=2e-11, abs=2e-10), path
    else:
        assert actual == expected, path


@pytest.mark.parametrize('intervals', [False, True])
def test_multiclass_fifo_merge_signals_closure_and_every_tick_parity(intervals, monkeypatch):
    ref = road(intervals=intervals)
    native = NativeRoadNetwork(ref)
    assert native.native.registry_sizes() == (4, 3, 4)  # equal paths shared, labels preserved
    state = ref.initial()
    expected = []
    offers_by_step = {0: (('z', 5., 0.), ('a', 3., 0.), ('merge', 4., 0.), ('alias', 1., 0.)),
                      3: (('z', 1.25, 2.5), ('a', .5, .5)),
                      21: (('merge', 2., 20.),)}
    for i in range(100):
        state, events = ref.advance_interval(state, 1, offers_by_step.get(i, ()))
        expected.append((state, events))

    def forbidden_callback(*args, **kwargs):
        raise AssertionError('Python physical tick was called')

    monkeypatch.setattr(FiniteResponseMotion, 'advance', forbidden_callback)
    state = native.initial()
    for i, (oracle, oracle_events) in enumerate(expected):
        state, events = native.advance_interval(state, 1, offers_by_step.get(i, ()))
        close(asdict(state), asdict(oracle))
        close(tuple(asdict(e) for e in events), tuple(asdict(e) for e in oracle_events), 'events')
        native.check(state)
    assert state.completed == pytest.approx(16.75)


def test_native_snapshot_restore_and_callbacks_free_batch():
    ref = road(windows=False, signals=False)
    native = NativeRoadNetwork(ref)
    steps = [(1., [('z', 3., 0.), ('a', 1., 0.)])] + [(1., [])] * 24
    sequential = ref.initial()
    events = []
    for dt, offers in steps:
        sequential, e = ref.advance_interval(sequential, dt, offers)
        events.append(e)
    actual, batch_events = native.advance_batch(native.initial(), steps)
    close(asdict(actual), asdict(sequential))
    close([[asdict(e) for e in es] for es in batch_events],
          [[asdict(e) for e in es] for es in events])
    raw = native.native.snapshot()
    restored = NativeRoadNetwork(ref)
    restored.native.restore(raw)
    close(asdict(restored.snapshot()), asdict(actual))
    a, _ = restored.advance_interval(restored.snapshot(), 1)
    b, _ = ref.advance_interval(sequential, 1)
    close(asdict(a), asdict(b))
    with pytest.raises((ValueError, ArithmeticError)):
        restored.restore(replace(a, released=a.released + 1))
    close(asdict(restored.snapshot()), asdict(a))
    forged = list(restored.native.snapshot())
    forged[0] = 'different-road-model'
    with pytest.raises(ValueError, match='binding'):
        restored.native.restore(tuple(forged))
    close(asdict(restored.snapshot()), asdict(a))


def test_native_resource_failure_retains_exact_previous_state():
    ref = road(budget=1, windows=False, signals=False)
    native = NativeRoadNetwork(ref)
    before = native.initial()
    with pytest.raises(BudgetExceeded) as error:
        native.advance_interval(before, 1, [('z', 1., 0.), ('a', 1., 0.)])
    assert error.value.checkpoint == before
    assert native.snapshot() == before
    with pytest.raises(ValueError):
        native.advance_interval(before, 1, [('z', math.nan, 0.)])
    assert native.snapshot() == before


def test_closed_cap_brakes_continuously_and_control_boundary_is_enforced():
    ref = road(windows=False, signals=False)
    ref = PacketNetwork(ref.groups, [Route(k, v) for k, v in ref.routes.items()], dt_s=1,
                        windows=(('a', 1, 3, 0.),), vehicle_classes=ref.vehicle_classes,
                        space_capacities_m=ref.space_capacities_m,
                        standing_gap_m=ref.standing_gap_m, motion=ref.motion,
                        preserve_entry_intervals=True)
    native = NativeRoadNetwork(ref)
    s, _ = native.advance_interval(native.initial(), 1, [('z', 1., 0.)])
    assert s.cells[ref.index['a']].speed_mps == 8.
    before = s
    with pytest.raises(ValueError, match='closure boundary'):
        native.advance_interval(s, 3)
    assert native.snapshot() == before
    s, _ = native.advance_interval(s, 1)
    # Zero road cap changes the acceleration target, not instantaneous speed.
    assert 0 < s.cells[ref.index['a']].speed_mps < 8
    oracle, _ = ref.advance_interval(ref.initial(), 1, [('z', 1., 0.)])
    oracle, _ = ref.advance_interval(oracle, 1)
    close(asdict(s), asdict(oracle))


def test_reject_unsupported_legacy_motion_instead_of_falling_back():
    with pytest.raises(ValueError, match='finite-response'):
        NativeRoadNetwork(PacketNetwork((Group('g', 'a', 'b', Lane()),), (Route('r', ('g',)),)))


def test_batch_failure_exposes_last_valid_native_interval():
    native = NativeRoadNetwork(road(windows=False, signals=False))
    initial = native.initial()
    with pytest.raises(ValueError) as failure:
        native.advance_batch(initial, [(1, [('z', 1., 0.)]),
                                       (1, []), (1, [('z', -1., 0.)])])
    checkpoint = failure.value.checkpoint
    assert checkpoint.time_s == 2
    assert checkpoint.released == 1
    assert native.snapshot() == checkpoint
    native.check(checkpoint)
