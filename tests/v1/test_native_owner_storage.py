"""Lossless native owner checkpoints and fail-closed restore at the file boundary."""
import struct

import pytest

from metroflow.v1.release_services import BusCorridor
from test_joint_release_runtime import fixture
from test_native_engine import make_native


def engine():
    city, legs, _ = fixture()
    native, _, _ = make_native(
        city, legs,
        (BusCorridor("out", "block", "work", 3, 50),
         BusCorridor("back", "work", "block", 5, 50)),
    )
    return native


def saved_bytes(native, state, path):
    native.save(str(path), state)
    return path.read_bytes()


def road_time_offset(raw):
    """Skip the engine binding and road binding, both length-prefixed UTF-8."""
    at = 16 + struct.unpack_from("<Q", raw, 8)[0]
    return at + 8 + struct.unpack_from("<Q", raw, at)[0]


@pytest.mark.parametrize("end", [5, 120])
def test_native_binary_roundtrip_is_byte_exact_for_active_and_receipt_states(tmp_path, end):
    native = engine()
    state = native.advance(native.initial(), end)
    before = saved_bytes(native, state, tmp_path / "before.bin")
    loaded = native.load(str(tmp_path / "before.bin"))
    after = saved_bytes(native, loaded, tmp_path / "after.bin")
    assert after == before
    assert native.report(loaded) == native.report(state)
    expected = native.advance(state, end + 5)
    actual = native.advance(loaded, end + 5)
    assert saved_bytes(native, actual, tmp_path / "actual.bin") == saved_bytes(
        native, expected, tmp_path / "expected.bin"
    )


@pytest.mark.parametrize("damage", [
    "truncated_header", "truncated_tail", "magic", "binding",
    "oversized_header", "oversized_cells", "nan_birth", "wrong_finite_birth", "trailing",
])
def test_invalid_native_checkpoint_does_not_replace_current_owner_state(tmp_path, damage):
    native = engine()
    state = native.advance(native.initial(), 120)
    original = saved_bytes(native, state, tmp_path / "valid.bin")
    raw = bytearray(original)
    if damage == "truncated_header":
        del raw[10:]
    elif damage == "truncated_tail":
        del raw[-1:]
    elif damage == "magic":
        raw[0] ^= 1
    elif damage == "binding":
        raw[16] ^= 1
    elif damage == "oversized_header":
        struct.pack_into("<Q", raw, 8, 2**64 - 1)
    elif damage == "oversized_cells":
        struct.pack_into("<Q", raw, road_time_offset(raw) + 8, 2**64 - 1)
    elif damage == "nan_birth":
        struct.pack_into("<d", raw, len(raw) - 8, float("nan"))
    elif damage == "wrong_finite_birth":
        struct.pack_into("<d", raw, len(raw) - 8, 0.0)
    else:
        raw.extend(b"uncommitted trailing bytes")
    damaged = tmp_path / "damaged.bin"
    damaged.write_bytes(raw)
    with pytest.raises((ValueError, OSError, ArithmeticError, MemoryError)):
        native.load(str(damaged))
    assert saved_bytes(native, native.snapshot(), tmp_path / "still-valid.bin") == original


def test_checkpoint_rejects_disagreeing_owner_clocks_before_install(tmp_path):
    native = engine()
    initial = native.initial()
    raw = bytearray(saved_bytes(native, initial, tmp_path / "initial.bin"))
    # At an empty road state t=1 is individually valid; journey still has t=0.
    struct.pack_into("<d", raw, road_time_offset(raw), 1.0)
    path = tmp_path / "different-clocks.bin"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="clocks differ"):
        native.load(str(path))
    assert native.snapshot().time_s == 0.0
    assert native.report(native.snapshot()) == native.report(initial)
