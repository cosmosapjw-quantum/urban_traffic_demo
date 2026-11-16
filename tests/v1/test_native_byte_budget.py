"""Explicit native road byte policy and unchanged ordered packet arithmetic."""
from dataclasses import asdict
import math
import struct

import pytest
from _metroflow_rust import NativeWholeEngine, V1Road

from metroflow.v1.native_road import NativeRoadNetwork
from test_native_road import road, close
from test_native_engine import make_native, small_fixture


def one_group(count=128, record_budget=20000, event_budget=None):
    return V1Road(
        "road-byte-test", 1., [[100., 20., 100., 100., 1000., 1.]], [None],
        [([0], 0) for _ in range(count)],
        [[20., 1., 2., 3., 2., 1., 4., .5, .2, .3, 4., 10., 6.]],
        [[0]], [], record_budget, event_budget, True,
    )


def test_legacy_20k_guard_remains_default_and_explicit_bytes_cover_state_and_events():
    count = 20001
    offers = [(i, 1e-6, 0., None, None) for i in range(count)]
    legacy = one_group(count)
    initial = legacy.snapshot()
    assert legacy.storage_limits() == (None, 20000, 20000, None)
    with pytest.raises(MemoryError, match="record budget|state budget"):
        legacy.step(1., offers)
    assert legacy.snapshot() == initial

    native = one_group(count)
    native.configure_storage_budget(64 * 1024**2)
    byte_limit, state_limit, event_limit, junction_limit = native.storage_limits()
    assert byte_limit == 64 * 1024**2
    assert count < state_limit < 2**63 and count < event_limit < 2**63
    assert junction_limit is None
    native.step(1., offers)
    assert sum(len(parts) for _, packets, _ in native.snapshot()[2]
               for _, parts in packets) == count
    events = native.step(20., [])
    assert len(events) == count  # transfer rows have their own byte-derived ceiling
    assert native.snapshot()[4][1] == pytest.approx(count * 1e-6)


def test_byte_preflight_rejects_before_candidate_and_keeps_current_state_exact():
    native = one_group()
    native.configure_storage_budget(8192)
    before = native.snapshot()
    with pytest.raises(MemoryError, match="phase=tick preflight.*required_bytes=.*budget_bytes=8192"):
        native.step(1., [(i, 1e-4, 0., None, None) for i in range(128)])
    assert native.snapshot() == before
    assert native.storage_limits()[0] == 8192


def test_byte_policy_configuration_failure_is_atomic_and_preserves_junction_guard():
    native = one_group(event_budget=17)
    native.step(1., [(0, .1, 0., None, None)])
    before, limits = native.snapshot(), native.storage_limits()
    with pytest.raises(MemoryError, match="storage budget"):
        native.configure_storage_budget(64)
    assert native.snapshot() == before and native.storage_limits() == limits
    with pytest.raises(ValueError):
        native.configure_storage_budget(0)
    assert native.storage_limits() == limits
    native.configure_storage_budget(1024**2)
    assert native.storage_limits()[3] == 17


@pytest.mark.parametrize("intervals", [False, True])
def test_noncontiguous_same_keys_and_mixed_intervals_match_python_grouping(intervals):
    reference = road(windows=False, signals=False, intervals=intervals)
    native = NativeRoadNetwork(reference)
    native.native.configure_storage_budget(64 * 1024**2)
    expected, actual = reference.initial(), native.initial()
    expected, _ = reference.advance_interval(expected, 1.)
    actual, _ = native.advance_interval(actual, 1.)
    # Equal keys are separated by other tags and interval keys. The varied
    # exponents require exact per-group summation in original encounter order.
    offers = [
        ('z', 1., .25, 0., .5),
        ('a', .5, .125, .25, .75),
        ('z', 2.**-53, 2.**-55, 0., .5),
        ('merge', .7, .35, .5, 1.),
        ('z', 2.**-106, 2.**-108, 0., .5),
        ('alias', .3, .15, .5, 1.),
        ('z', .25, .125, .5, 1.),
        ('a', 2.**-54, 2.**-56, .25, .75),
    ]
    for tick in range(80):
        batch = offers if tick == 0 else ()
        expected, expected_events = reference.advance_interval(expected, 1., batch)
        actual, actual_events = native.advance_interval(actual, 1., batch)
        close(asdict(actual), asdict(expected))
        close(tuple(asdict(e) for e in actual_events), tuple(asdict(e) for e in expected_events))
    assert actual.completed == pytest.approx(math.fsum(v[1] for v in offers))


@pytest.mark.parametrize("mass", [math.nan, math.inf, -1.])
def test_byte_mode_does_not_accept_invalid_physical_parts(mass):
    native = one_group()
    native.configure_storage_budget(1024**2)
    before = native.snapshot()
    with pytest.raises(ValueError):
        native.step(1., [(0, mass, 0., None, None)])
    assert native.snapshot() == before


@pytest.mark.parametrize("allocation", ["packet_registry", "packet_parts"])
def test_checkpoint_decode_rejects_oversized_reserve_before_reading_payload(tmp_path, allocation):
    city, legs, corridors = small_fixture()
    _, calendar, payload = make_native(city, legs, corridors)
    native = NativeWholeEngine(calendar, payload, 256 * 1024**2,
                              storage_policy="bounded_bytes_v1")
    valid = tmp_path / "valid.bin"
    native.save(str(valid), native.initial())
    original = valid.read_bytes()
    allowance = native.storage_config()["road_dynamic_allowance_bytes"]
    probe = one_group(count=1)
    probe.configure_storage_budget(allowance)
    record_ceiling = probe.storage_limits()[1]

    # Walk the fixed whole-engine / road identity frames, then the first cell's
    # eight scalar fields. Payload counts remain within the raw row ceiling but
    # exceed the simultaneous-owner byte envelope. A truncated body proves that
    # the guard runs before the allocation/read, not after complete decoding.
    offset = 8
    for _ in range(2):
        length = struct.unpack_from("<Q", original, offset)[0]
        offset += 8 + length
    offset += 8 + 8 + 8 * 8  # road time, cell count, first cell scalar fields
    if allocation == "packet_registry":
        tail = struct.pack("<Q", record_ceiling)
    else:
        tail = struct.pack("<QdQ", 1, 0., record_ceiling)
    corrupt = tmp_path / "oversized.bin"
    corrupt.write_bytes(original[:offset] + tail)
    with pytest.raises(MemoryError, match="phase=checkpoint decode preflight"):
        native.load(str(corrupt))
    after = tmp_path / "after.bin"
    native.save(str(after), native.snapshot())
    assert after.read_bytes() == original
