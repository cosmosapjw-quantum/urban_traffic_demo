"""Bounded opt-in Rust entry projection: conservation, identity and rollback.

Kernel support-switch/atom/high-clock tests also live beside the Rust kernel.
These tests require the rebuilt extension; import/constructor failure is not RED.
"""
import math
import struct

import pytest
from _metroflow_rust import NativeWholeEngine, V1Road

from test_native_engine import make_native, small_fixture


def native_road(width=0.0, *, explicit=True, intervals=True):
    args = (
        "entry-projection-test", 1.,
        [[.1, 20., 10., 1., 1000., 1.]]
        + [[100., 20., 10., 10., 1000., 1.] for _ in range(4)],
        [None] * 5,
        [([0, 1, 2, 3], 0), ([0, 1, 2, 4], 0), ([0, 1, 4], 0)],
        [[20., 1., 2., 3., 2., 1., 4., .5, .2, .3, 4., 10., 6.]],
        [[0], [1], [2], [3], [4]], [], 20000, None, intervals,
    )
    return V1Road(*args, entry_projection_width_s=width) if explicit else V1Road(*args)


def suffix(width):
    return ":entry_projection_support_v1:" + struct.pack(">d", width).hex()


@pytest.mark.parametrize("width", [-1., math.inf, -math.inf, math.nan])
def test_invalid_projection_width_rejected(width):
    with pytest.raises(ValueError, match="projection.*finite|projection.*nonnegative"):
        native_road(width)


def test_projection_requires_interval_law():
    with pytest.raises(ValueError, match="preserved entry intervals"):
        native_road(.5, intervals=False)


def test_zero_width_default_and_explicit_replay_are_identical():
    default, zero = native_road(explicit=False), native_road(0.)
    assert default.snapshot() == zero.snapshot()
    offers = [(0, .3, 0., None, None), (1, .2, 0., None, None)]
    for i in range(12):
        rows = offers if i == 0 else []
        assert default.step(1., rows) == zero.step(1., rows)
        assert default.snapshot() == zero.snapshot()
    assert zero.projection_diagnostics()["policy"] == "exact_intervals"
    assert zero.snapshot()[0] == "entry-projection-test"


def test_transfer_projection_preserves_tag_mass_birth_and_entry_first_moment():
    native = native_road(.1)
    native.step(1., [(0, .3, 0., None, None), (1, .2, 0., None, None)])
    events = native.step(1., [])
    entering = [row for row in events if row[2] == 1]
    assert entering
    packets = native.snapshot()[2][1][1]
    projected = [part for _, parts in packets for part in parts]
    assert all(p[4] == p[5] for p in projected)
    for tag in (0, 1):
        original = [e for e in entering if e[0] == tag]
        result = [p for p in projected if p[0] == tag]
        assert math.fsum(p[2] for p in result) == pytest.approx(math.fsum(e[3] for e in original), abs=1e-14)
        assert math.fsum(p[3] for p in result) == pytest.approx(math.fsum(e[6] for e in original), abs=1e-14)
        assert math.fsum(p[2] * p[4] for p in result) == pytest.approx(
            math.fsum(e[3] * (e[4] + (e[5]-e[4])/2) for e in original), abs=1e-13)
        assert all(p[1] == 1 for p in result)  # route offset remains explicit
    stats = native.projection_diagnostics()
    assert stats["input_parts"] == len(entering)
    assert stats["output_parts"] == len(projected)
    assert stats["cohorts"] == len(packets)
    assert 0 < stats["local_w1_bound_veh_s"] <= .1 * math.fsum(e[3] for e in entering) / 2 + 1e-14
    assert stats["checkpointed"] is False
    assert "not network" in stats["scope"]


def test_projection_byte_failure_preserves_state_and_last_valid_diagnostics():
    native = native_road(2e-5)
    native.configure_storage_budget(1024**2)
    native.step(1., [(0, .3, 0., None, None)])
    before = native.snapshot()
    diagnostics = native.projection_diagnostics()
    with pytest.raises(MemoryError, match="storage budget"):
        native.step(1., [])
    assert native.snapshot() == before
    assert native.projection_diagnostics() == diagnostics


def test_road_identity_width_mismatch_and_same_width_replay():
    native = native_road(.1)
    assert native.snapshot()[0] == "entry-projection-test" + suffix(.1)
    native.step(1., [(0, .3, 0., None, None)])
    native.step(1., [])
    middle = native.snapshot()
    for width in (0., .2):
        other = native_road(width)
        before = other.snapshot()
        with pytest.raises(ValueError, match="binding"):
            other.restore(middle)
        assert other.snapshot() == before
    fresh = native_road(.1)
    fresh.restore(middle)
    assert fresh.step(1., []) == native.step(1., [])
    assert fresh.snapshot() == native.snapshot()


@pytest.mark.parametrize("storage_policy", ["legacy_records", "bounded_bytes_v1"])
def test_whole_engine_projection_binding_checkpoint_replay_and_config(tmp_path, storage_policy):
    city, legs, corridors = small_fixture()
    _, calendar, payload = make_native(city, legs, corridors)
    def engine(width):
        return NativeWholeEngine(calendar, payload, 256 * 1024**2,
                                 storage_policy=storage_policy,
                                 entry_projection_width_s=width)
    native = engine(.25)
    assert native.identity.endswith(suffix(.25))
    assert native.identity.count(":entry_projection_support_v1:") == 1
    assert native.execution_config()["entry_projection_width_s"] == .25
    assert native.entry_projection_width_s == .25
    middle = native.advance(native.initial(), 30.)
    path = tmp_path / "projection.bin"
    native.save(str(path), middle)
    fresh = engine(.25)
    restored = fresh.load(str(path))
    a, b = native.advance(middle, 60.), fresh.advance(restored, 60.)
    assert native.report(a) == fresh.report(b)
    left, right = tmp_path / "left.bin", tmp_path / "right.bin"
    native.save(str(left), a)
    fresh.save(str(right), b)
    assert left.read_bytes() == right.read_bytes()
    for width in (0., .5):
        with pytest.raises(ValueError, match="binding"):
            engine(width).load(str(path))
    assert native.projection_diagnostics()["width_s"] == .25


@pytest.mark.parametrize("width", [.25, 1.])
def test_projected_native_every_tick_matches_independent_python_oracle(width):
    from dataclasses import asdict
    from metroflow.packet_network import PacketNetwork
    from metroflow.ordered_network import Route
    from metroflow.v1.native_road import NativeRoadNetwork
    from test_native_road import road, close

    base = road()
    reference = PacketNetwork(
        base.groups, [Route(tag, path) for tag, path in base.routes.items()],
        dt_s=base.dt, windows=base.windows, record_budget=base.record_budget,
        vehicle_classes=base.vehicle_classes, space_capacities_m=base.space_capacities_m,
        standing_gap_m=base.standing_gap_m, motion=base.motion,
        preserve_entry_intervals=True, entry_projection_width_s=width,
    )
    native = NativeRoadNetwork(reference)
    expected, actual = reference.initial(), native.initial()
    offers = {0: [('z', 5., 0.), ('a', 3., 0.), ('merge', 4., 0.), ('alias', 1., 0.)],
              3: [('z', 1.25, 2.5), ('a', .5, .5)], 21: [('merge', 2., 20.)]}
    projected_continuous = False
    for tick in range(100):
        expected, oracle_events = reference.advance_interval(expected, 1., offers.get(tick, ()))
        actual, events = native.advance_interval(actual, 1., offers.get(tick, ()))
        close(asdict(actual), asdict(expected))
        close([asdict(e) for e in events], [asdict(e) for e in oracle_events])
        for key in ("input_parts", "output_parts", "cohorts", "protected_support_boundaries"):
            assert native.native.projection_diagnostics()[key] == reference.projection_diagnostics()[key]
        assert native.native.projection_diagnostics()["local_w1_bound_veh_s"] == pytest.approx(
            reference.projection_diagnostics()["local_w1_bound_veh_s"], rel=2e-12, abs=1e-14)
        projected_continuous |= native.native.projection_diagnostics()["local_w1_bound_veh_s"] > 0
    assert projected_continuous
    assert actual.completed == pytest.approx(16.75)
