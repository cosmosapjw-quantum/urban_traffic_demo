"""Thread count is an execution choice, never a scientific-state transformation.

The 2,560-leg case crosses the native journey parallel grain threshold while
retaining actual mixed car/bus/freight occupancy, returns, and completion rows.
All comparisons below are exact checkpoint bytes, not rounded report values.
"""
from dataclasses import replace
import hashlib
import json
import math

import pytest
from _metroflow_rust import NativeWholeEngine

from metroflow.v1.journey import DelayLaw
from test_native_engine import make_native, small_fixture


def expanded_fixture(copies):
    city, base, corridors = small_fixture()
    legs = []
    for copy in range(copies):
        ids = {leg.id: f"{leg.id}:{copy}" for leg in base}
        for leg in base:
            legs.append(replace(leg, id=ids[leg.id],
                cohort_id=(None if leg.cohort_id is None else f"{leg.cohort_id}:{copy}"),
                depends_on=None if leg.depends_on is None else ids[leg.depends_on]))
    return city, tuple(legs), corridors


def checkpoint_bytes(engine, state, path):
    engine.save(str(path), state)
    return path.read_bytes()


def parallel_network_payload(payload):
    """Force the road map grain using disconnected, initially empty links.

    They exchange no mass with the original fixture. The actual mixed roads
    still execute their finite-response/FIFO logic inside the parallel map.
    """
    payload = {**payload, **{name: list(payload[name]) for name in (
        "groups", "signals", "incoming", "link_ids", "route_arcs", "route_costs")}}
    while len(payload["groups"]) < 32:
        i = len(payload["groups"])
        tag = f"isolated-{i}"
        group = list(payload["groups"][0])
        payload["groups"].append(group)
        payload["signals"].append(None)
        payload["incoming"].append([i])
        payload["link_ids"].append(tag)
        payload["route_arcs"].append((tag, f"isolated-tail-{i}", f"isolated-head-{i}"))
        payload["route_costs"].append((tag, group[0] / group[1]))
    payload.pop("identity")
    payload["identity"] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return payload


@pytest.mark.parametrize("copies", [1, 512])
@pytest.mark.parametrize("workers", [2, 4])
def test_mixed_parallel_batches_branches_and_fresh_restart_are_byte_identical(
        tmp_path, copies, workers):
    city, legs, corridors = expanded_fixture(copies)
    _, calendar, payload = make_native(city, legs, corridors, record_budget=200000)
    payload = parallel_network_payload(payload)
    serial = NativeWholeEngine(calendar, payload, 256 * 1024**2, native_threads=1)
    parallel = NativeWholeEngine(calendar, payload, 256 * 1024**2,
                                 native_threads=workers)
    assert serial.native_threads == 1
    assert parallel.native_threads == workers
    assert serial.identity == parallel.identity
    initial = parallel.initial()
    old = parallel.advance(initial, 17)
    old_bytes = checkpoint_bytes(parallel, old, tmp_path / "old.bin")
    actual = parallel.advance(old, 120)
    expected = serial.advance(serial.initial(), 120)
    expected_bytes = checkpoint_bytes(serial, expected, tmp_path / "serial.bin")
    assert checkpoint_bytes(parallel, actual, tmp_path / "parallel.bin") == expected_bytes
    assert parallel.report(actual) == serial.report(expected)

    # Rewinding is explicit and must not mutate either historical snapshot.
    branch = parallel.advance(initial, 120)
    assert checkpoint_bytes(parallel, branch, tmp_path / "branch.bin") == expected_bytes
    assert checkpoint_bytes(parallel, old, tmp_path / "old-again.bin") == old_bytes
    assert initial.time_s == 0 and old.time_s == 17

    # The same scientific binary can cross a thread-count boundary on restart.
    fresh = NativeWholeEngine(calendar, payload, 256 * 1024**2, native_threads=workers)
    restored = fresh.load(str(tmp_path / "old.bin"))
    restarted = fresh.advance(restored, 120)
    assert checkpoint_bytes(fresh, restarted, tmp_path / "restart.bin") == expected_bytes
    ledger = fresh.report(restarted)["service"]
    assert ledger["road_released_veh"] > 0
    assert ledger["road_completed_veh"] > 0
    metrics = fresh.phase_metrics()
    assert metrics['successful_ticks'] == 103 and metrics['failed_ticks'] == 0
    assert all(math.isfinite(v) and v >= 0 for v in metrics['phase_wall_s'].values())


@pytest.mark.parametrize("workers", [1, 2, 4])
def test_parallel_resource_failure_keeps_last_full_tick_and_exact_retry(tmp_path, workers):
    city, legs, _ = small_fixture()
    internal = replace(legs[0], destination=legs[0].origin,
                       intrazonal=DelayLaw(((0., .5), (1., .5))))
    serial, calendar, payload = make_native(city, (internal,), record_budget=1)
    native = NativeWholeEngine(calendar, payload, 256 * 1024**2,
                               native_threads=workers)
    with pytest.raises(MemoryError, match="record budget"):
        serial.advance(serial.initial(), 5)
    reference = checkpoint_bytes(serial, serial.snapshot(), tmp_path / "serial.bin")
    initial = native.initial()
    with pytest.raises(MemoryError, match="record budget"):
        native.advance(initial, 5)
    valid = native.snapshot()
    assert valid.time_s == 1
    assert native.phase_metrics()['failed_ticks'] == 1
    assert checkpoint_bytes(native, valid, tmp_path / "valid.bin") == reference
    assert initial.time_s == 0
    # Both immediate retry and a fresh worker-pool restart must fail atomically.
    for loaded in (valid, native.load(str(tmp_path / "valid.bin"))):
        with pytest.raises(MemoryError, match="record budget"):
            native.advance(loaded, 2)
        assert checkpoint_bytes(native, native.snapshot(), tmp_path / "retry.bin") == reference


@pytest.mark.parametrize("workers", [0, -1, 257])
def test_explicit_worker_count_rejects_invalid_bounds(workers):
    city, legs, corridors = small_fixture()
    _, calendar, payload = make_native(city, legs, corridors)
    with pytest.raises((ValueError, OverflowError)):
        NativeWholeEngine(calendar, payload, 256 * 1024**2, native_threads=workers)
