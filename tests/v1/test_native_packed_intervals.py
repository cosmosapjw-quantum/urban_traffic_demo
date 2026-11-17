"""Compact finite interval storage preserves the public rows and wire bytes."""
import math
import struct
import sys

import pytest
from _metroflow_rust import NativeWholeEngine

from test_native_byte_budget import one_group
from test_native_engine import make_native, small_fixture


def active_row(native, a, b, time=1.):
    mass = 1e-300
    birth = mass * time
    return (native.snapshot()[0], time,
            [([0., 1., mass, 0., birth, 0., 0., 0.],
              [(0., [(0, 0, mass, birth, a, b)])], [])],
            [[]], [mass, 0., birth, 0., 0., 0., 0.],
            [[mass, 0., 0., 0., 0.]])


def option_bits(value):
    return None if value is None else struct.pack('<d', value)


@pytest.mark.parametrize('a,b,time', [
    (None, None, 1.), (-0., 0., 1.), (0., -0., 1.),
    (math.ulp(0.), math.ulp(0.), 1.),
    (sys.float_info.max, sys.float_info.max, sys.float_info.max),
])
def test_finite_endpoint_row_roundtrip_preserves_presence_and_exact_bits(a, b, time):
    native = one_group(count=1)
    native.restore(active_row(native, a, b, time))
    restored = native.snapshot()[2][0][1][0][1][0]
    assert native.packet_storage_counts() == (1, 0, 1, 0)
    assert option_bits(restored[4]) == option_bits(a)
    assert option_bits(restored[5]) == option_bits(b)
    fresh = one_group(count=1)
    fresh.restore(native.snapshot())
    copied = fresh.snapshot()[2][0][1][0][1][0]
    assert option_bits(copied[4]) == option_bits(a)
    assert option_bits(copied[5]) == option_bits(b)


def test_actual_part_layout_and_byte_derived_record_ceiling():
    native = one_group(count=1)
    # CorePart, expanded Part, Packet (including enum metadata), EventRow.
    # Packet's enum niche/layout is compiler-owned, not a checkpoint ABI.
    core, expanded, packet, event = native.storage_layout_bytes()
    assert (core, expanded, event) == (32, 48, 64)
    assert 40 <= packet <= 56
    native.configure_storage_budget(1024**2)
    assert native.storage_limits()[1] == 1024**2 // 48
    assert native.storage_limits()[2] == 1024**2 // 64


def test_packing_checks_expanded_and_compact_buffers_before_allocating():
    native = one_group(count=128)
    native.configure_storage_budget(38000)
    before = native.snapshot()
    with pytest.raises(MemoryError, match='phase=packet interval packing'):
        native.step(1., [(i, 1e-4, 0., None, None) for i in range(128)])
    assert native.snapshot() == before
    assert native.packet_storage_counts() == (0, 0, 0, 0)


@pytest.mark.parametrize('intervals', [
    ((-0., 0.), (0., 0.)),
    ((0., -0.), (0., 0.)),
    ((None, None), (0., 0.)),
    ((.125, .25), (.25, .5)),
])
def test_mixed_packet_fallback_preserves_each_endpoint_bits_and_original_order(intervals):
    native = one_group(count=1)
    row = list(active_row(native, None, None))
    parts = [(0, 0, 1e-300, 1e-300, a, b) for a, b in intervals]
    row[2] = [([0., 1., 2e-300, 0., 2e-300, 0., 0., 0.], [(0., parts)], [])]
    row[4] = [2e-300, 0., 2e-300, 0., 0., 0., 0.]
    row[5] = [[2e-300, 0., 0., 0., 0.]]
    native.restore(tuple(row))
    assert native.packet_storage_counts() == (0, 1, 0, 2)
    actual = native.snapshot()[2][0][1][0][1]
    assert [(option_bits(p[4]), option_bits(p[5])) for p in actual] == [
        (option_bits(a), option_bits(b)) for a, b in intervals]
    fresh = one_group(count=1)
    fresh.restore(native.snapshot())
    copied = fresh.snapshot()[2][0][1][0][1]
    assert [(option_bits(p[4]), option_bits(p[5])) for p in copied] == [
        (option_bits(a), option_bits(b)) for a, b in intervals]
    assert fresh.packet_storage_counts() == (0, 1, 0, 2)


@pytest.mark.parametrize('value', [math.nan, math.inf, -math.inf,
    struct.unpack('<d', struct.pack('<Q', 2**64 - 1))[0]])
def test_nonfinite_endpoint_cannot_collide_with_none_and_failure_is_atomic(value):
    native = one_group(count=1)
    before = native.snapshot()
    with pytest.raises(ValueError):
        native.restore(active_row(native, value, value))
    assert native.snapshot() == before
    with pytest.raises(ValueError):
        native.step(1., [(0, .1, 0., value, value)])
    assert native.snapshot() == before


def first_part_options(data):
    offset = 8
    for _ in range(2):
        length = struct.unpack_from('<Q', data, offset)[0]
        offset += 8 + length
    offset += 8  # road time
    cells = struct.unpack_from('<Q', data, offset)[0]
    offset += 8
    for _ in range(cells):
        offset += 8 * 8
        packets = struct.unpack_from('<Q', data, offset)[0]
        offset += 8
        for _ in range(packets):
            offset += 8  # packet target
            parts = struct.unpack_from('<Q', data, offset)[0]
            offset += 8
            assert parts > 0
            offset += 8 * 4  # tag, route offset, mass, birth
            start = offset
            for _ in range(2):
                present = struct.unpack_from('<Q', data, offset)[0]
                offset += 8 + (8 if present else 0)
            return start, offset
        latent = struct.unpack_from('<Q', data, offset)[0]
        offset += 8 + 16 * latent
    raise AssertionError('fixture has no occupied road packet')


def whole_fixture(tmp_path):
    city, legs, corridors = small_fixture()
    _, calendar, payload = make_native(city, legs, corridors)
    native = NativeWholeEngine(calendar, payload, 256 * 1024**2,
                              storage_policy='bounded_bytes_v1')
    state = native.advance(native.initial(), 17.)
    path = tmp_path / 'original.bin'
    native.save(str(path), state)
    return native, path.read_bytes()


@pytest.mark.parametrize('a,b', [(None, None), (-0., 0.), (0., -0.)])
def test_option_wire_tags_and_signed_zero_bytes_roundtrip_unchanged(tmp_path, a, b):
    native, original = whole_fixture(tmp_path)
    start, end = first_part_options(original)
    replacement = b''.join(struct.pack('<Q', int(value is not None)) +
        (struct.pack('<d', value) if value is not None else b'') for value in (a, b))
    expected = original[:start] + replacement + original[end:]
    path = tmp_path / 'modified.bin'
    path.write_bytes(expected)
    restored = native.load(str(path))
    result = tmp_path / 'roundtrip.bin'
    native.save(str(result), restored)
    assert result.read_bytes() == expected


@pytest.mark.parametrize('bits', [0x7ff0000000000000, 0xfff0000000000000,
                                 0x7ff8000000000001, 0xffffffffffffffff])
def test_nonfinite_wire_endpoint_is_rejected_before_install(tmp_path, bits):
    native, original = whole_fixture(tmp_path)
    start, end = first_part_options(original)
    replacement = struct.pack('<QQQQ', 1, bits, 1, bits)
    path = tmp_path / 'nonfinite.bin'
    path.write_bytes(original[:start] + replacement + original[end:])
    with pytest.raises(ValueError, match='nonfinite retained boundary interval'):
        native.load(str(path))
    preserved = tmp_path / 'preserved.bin'
    native.save(str(preserved), native.snapshot())
    assert preserved.read_bytes() == original
