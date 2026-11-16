"""A representation guard may change; the physical solution and replay may not."""
from dataclasses import replace

import pytest
from _metroflow_rust import NativeWholeEngine

from metroflow.v1.journey import DelayLaw
from test_native_engine import make_native, small_fixture


def fixture():
    city, legs, _ = small_fixture()
    # Deliberately unsorted atoms: a cursor over declaration order is invalid.
    internal = replace(legs[0], destination=legs[0].origin,
        intrazonal=DelayLaw(((8., .25), (0., .5), (3., .25))))
    return city, (internal,)


def physical_report(engine, state):
    report = engine.report(state)
    return {key: value for key, value in report.items() if key != "construction"}


def test_explicit_byte_policy_preserves_solution_beyond_legacy_row_guard(tmp_path):
    city, legs = fixture()
    limited, calendar, payload = make_native(city, legs, record_budget=1)
    reference, _, _ = make_native(city, legs, record_budget=20000)
    with pytest.raises(MemoryError, match="record budget"):
        limited.advance(limited.initial(), 120.)
    native = NativeWholeEngine(calendar, payload, 256 * 1024**2,
        storage_policy="bounded_bytes_v1")
    initial = native.initial()
    middle = native.advance(initial, 17.)
    checkpoint = tmp_path / "middle.bin"
    native.save(str(checkpoint), middle)
    before = checkpoint.read_bytes()
    actual = native.advance(middle, 120.)
    expected = reference.advance(reference.initial(), 120.)
    assert physical_report(native, actual) == physical_report(reference, expected)
    assert native.sample_legs(actual, [0]) == reference.sample_legs(expected, [0])
    assert initial.time_s == 0.
    native.save(str(checkpoint), middle)
    assert checkpoint.read_bytes() == before
    assert native.identity != limited.identity

    final = tmp_path / "final.bin"
    native.save(str(final), actual)
    fresh = NativeWholeEngine(calendar, payload, 256 * 1024**2,
        native_threads=4, storage_policy="bounded_bytes_v1")
    restarted = fresh.advance(fresh.load(str(checkpoint)), 120.)
    replay = tmp_path / "replay.bin"
    fresh.save(str(replay), restarted)
    assert replay.read_bytes() == final.read_bytes()


def test_storage_policy_binding_prevents_silent_checkpoint_reinterpretation(tmp_path):
    city, legs = fixture()
    legacy, calendar, payload = make_native(city, legs)
    path = tmp_path / "legacy.bin"
    legacy.save(str(path), legacy.initial())
    native = NativeWholeEngine(calendar, payload, 256 * 1024**2,
        storage_policy="bounded_bytes_v1")
    with pytest.raises(ValueError, match="binding"):
        native.load(str(path))
    assert native.snapshot().time_s == 0.


def test_unknown_storage_policy_is_rejected():
    city, legs = fixture()
    _, calendar, payload = make_native(city, legs)
    with pytest.raises(ValueError, match="storage_policy"):
        NativeWholeEngine(calendar, payload, 256 * 1024**2,
            storage_policy="ignore_resources")
