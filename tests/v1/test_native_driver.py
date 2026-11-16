"""Explicit native engine selection at the production driver boundary."""
from dataclasses import fields, is_dataclass
import math
import json
from types import SimpleNamespace

import pytest

from metroflow.v1.release_driver import ReleaseDriver
from test_release_driver import fixture, services


def assert_equivalent(actual, expected):
    if is_dataclass(expected):
        assert type(actual) is type(expected)
        for field in fields(expected):
            assert_equivalent(getattr(actual, field.name), getattr(expected, field.name))
    elif isinstance(expected, (list, tuple)):
        assert len(actual) == len(expected)
        for a, e in zip(actual, expected):
            assert_equivalent(a, e)
    elif isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            assert_equivalent(actual[key], expected[key])
    elif isinstance(expected, float):
        assert math.isclose(actual, expected, rel_tol=2e-10, abs_tol=2e-9), (actual, expected)
    else:
        assert actual == expected


def test_unknown_native_engine_rejected_before_enumeration(monkeypatch):
    monkeypatch.setenv('METROFLOW_V1_ENGINE_BACKEND', 'typo')
    with pytest.raises(ValueError, match='engine backend'):
        ReleaseDriver(fixture(), services, max_legs=2, step_s=3600)


def test_native_driver_executes_and_resumes_same_complete_calendar(monkeypatch, tmp_path):
    monkeypatch.setenv('METROFLOW_V1_ENGINE_BACKEND', 'python_oracle')
    oracle = ReleaseDriver(fixture(), services, max_legs=2, step_s=3600)
    monkeypatch.setenv('METROFLOW_V1_ENGINE_BACKEND', 'rust')
    native = ReleaseDriver(fixture(), services, max_legs=2, step_s=3600)
    assert type(native.runtime).__name__ == 'NativeJointReleaseRuntime'
    assert native.cursor == oracle.cursor
    assert native.identity == oracle.identity
    a, e = native.advance(native.initial(), 9*3600), oracle.advance(oracle.initial(), 9*3600)
    assert_equivalent(a, e)
    path = tmp_path/'native-driver.json'
    native.save(path, a)
    restored = native.load(path)
    assert restored == a
    assert_equivalent(oracle.load(path), a)
    a = native.advance(restored, 86400)
    e = oracle.advance(e, 86400)
    assert_equivalent(a, e)
    assert_equivalent(native.report(a), oracle.report(e))


def test_missing_native_engine_is_explicit_failure(monkeypatch):
    monkeypatch.setenv('METROFLOW_V1_ENGINE_BACKEND', 'rust')
    from metroflow.v1 import native_journey
    def broken(*args, **kwargs):
        raise RuntimeError('native engine unavailable')
    monkeypatch.setattr(native_journey, 'NativeJointReleaseRuntime', broken)
    with pytest.raises(RuntimeError, match='native engine unavailable'):
        ReleaseDriver(fixture(), services, max_legs=2, step_s=3600)


def test_campaign_uses_native_hourly_chunks_with_internal_tick_measurements(monkeypatch, tmp_path):
    import tools.run_v1_local_acceptance as cli

    monkeypatch.setenv('METROFLOW_V1_ENGINE_BACKEND', 'rust')
    driver = ReleaseDriver(fixture(), services, max_legs=2, step_s=600)
    calls = []
    advance = driver.advance
    def counted(state, end):
        calls.append((state.time_s, end))
        return advance(state, end)
    monkeypatch.setattr(driver, 'advance', counted)
    monkeypatch.setattr(cli, 'prepare', lambda *args: (driver,
        dict(source_sha256='fixture', patch_sha256='fixture')))
    matrix = tmp_path/'matrix.json'
    matrix.write_text('{}')
    args = SimpleNamespace(step_s=600, horizon_s=86400, matrix=matrix, out=tmp_path,
                           label='native.fixture', prepare_only=False, resume=True)
    assert cli.worker(args, {'limits': {'peak_rss_bytes': 2**40}}, {'id': 'fixture'}) == 0
    result = json.loads((tmp_path/'native.fixture.json').read_text())
    assert len(calls) == 24
    assert all(b-a == 3600 for a, b in calls)
    assert result['simulated_s'] == 86400
    assert result['tick_p50_s'] >= 0
    assert result['tick_p95_s'] >= result['tick_p50_s']
    assert result['peak_tracked_records'] > 0
    assert result['native_frontend_boundary_s'] >= 0
    assert result['tick_measurement_scope'].startswith('native complete tick')
    assert (tmp_path/'native.fixture.middle.json').exists()
