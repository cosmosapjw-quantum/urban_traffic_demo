"""Native routing integrated into the shared car/bus/freight runtime.

The physical/service owner is still the reference implementation in this
migration slice. These tests certify identical routes and downstream execution,
not a Rust-owned physical time integrator.
"""
import pytest

from metroflow.v1.joint_release_runtime import JointReleaseRuntime
from metroflow.v1.native_routing import NativeRoutingGraph
from test_joint_release_runtime import fixture


def test_native_shared_runtime_state_and_cross_backend_checkpoint_parity(monkeypatch, tmp_path):
    monkeypatch.setenv("METROFLOW_V1_ROUTING_BACKEND", "python_oracle")
    oracle_city, oracle_legs, oracle_plan = fixture()
    oracle = JointReleaseRuntime(oracle_city, oracle_legs, oracle_plan)

    calls = []
    actual_search = NativeRoutingGraph.search

    def counted_native_search(self, *args, **kwargs):
        result = actual_search(self, *args, **kwargs)
        calls.append((args, result))
        return result

    monkeypatch.setattr(NativeRoutingGraph, "search", counted_native_search)
    monkeypatch.setenv("METROFLOW_V1_ROUTING_BACKEND", "rust")
    native_city, native_legs, native_plan = fixture()
    service_searches = len(calls)
    assert service_searches > 0  # Service construction really entered Rust.
    native = JointReleaseRuntime(native_city, native_legs, native_plan)
    assert len(calls) > service_searches  # Car/helper construction did so too.

    assert native_city.identity == oracle_city.identity
    assert native_legs == oracle_legs
    for name in ("source_legs", "buses", "passengers", "freight", "pending", "metadata"):
        assert getattr(native_plan, name) == getattr(oracle_plan, name)
    assert native_plan.assignment_report() == oracle_plan.assignment_report()
    assert native.routes == oracle.routes
    assert native.helper.route_links == oracle.helper.route_links
    assert native.identity == oracle.identity
    assert native.service.identity == oracle.service.identity
    assert native.initial() == oracle.initial()

    oracle_120 = oracle.advance(oracle.initial(), 120)
    native_120 = native.advance(native.initial(), 120)
    assert native_120 == oracle_120
    assert native.report(native_120) == oracle.report(oracle_120)
    # Preserve the existing physical counterexample: a bus return scheduled
    # before outward completion+dwell remains pending, rather than teleporting.
    assert native_120.released[3] == 0
    assert native.report(native_120)["ledger"]["persons"]["pending"] == pytest.approx(25)
    assert native.report(native_120)["ledger"]["cargo_kg"]["completed"] == pytest.approx(100)

    oracle_path, native_path = tmp_path / "oracle.json", tmp_path / "native.json"
    oracle.save(oracle_path, oracle_120)
    native.save(native_path, native_120)
    assert native.load(native_path) == native_120
    assert native.load(oracle_path) == oracle_120
    assert oracle.load(native_path) == native_120
    continuous_125 = oracle.advance(oracle.initial(), 125)
    assert native.advance(native.load(native_path), 125) == continuous_125
    assert native.advance(native.load(oracle_path), 125) == continuous_125


def test_explicit_native_service_failure_is_not_silently_fallback(monkeypatch):
    monkeypatch.setenv("METROFLOW_V1_ROUTING_BACKEND", "rust")

    def broken_native_search(self, *args, **kwargs):
        raise RuntimeError("injected native service search failure")

    monkeypatch.setattr(NativeRoutingGraph, "search", broken_native_search)
    with pytest.raises(RuntimeError, match="injected native service search failure"):
        fixture()
