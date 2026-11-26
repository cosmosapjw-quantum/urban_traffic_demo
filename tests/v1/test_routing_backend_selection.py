"""Explicit migration backend selection never silently changes the closure."""
import pytest
from metroflow.v1.scenarios import scenario_city
from metroflow.v1.release_services import compile_service_plan


def test_invalid_backend_rejected_before_preparation(monkeypatch):
    monkeypatch.setenv('METROFLOW_V1_ROUTING_BACKEND', 'typo')
    with pytest.raises(ValueError, match='routing backend'):
        compile_service_plan(scenario_city(1000), ())


def test_default_rust_and_opt_in_oracle_boundary(monkeypatch):
    from metroflow.v1 import routing_backend, native_routing

    monkeypatch.delenv("METROFLOW_V1_ROUTING_BACKEND", raising=False)
    monkeypatch.delenv("METROFLOW_ENABLE_PYTHON_ORACLE", raising=False)
    class FakeNative:
        def __init__(self, *args):
            pass
        def search(self, *args):
            return "rust"
    monkeypatch.setattr(native_routing, "NativeRoutingGraph", FakeNative)
    assert routing_backend.routing_search((), {}, ())("a", "b") == "rust"
    monkeypatch.setenv("METROFLOW_V1_ROUTING_BACKEND", "python_oracle")
    with pytest.raises(RuntimeError, match="opt-in"):
        routing_backend.routing_search((), {}, ())
    monkeypatch.setenv("METROFLOW_ENABLE_PYTHON_ORACLE", "1")
    monkeypatch.setattr(routing_backend, "candidate_paths", lambda *args: "oracle")
    assert routing_backend.routing_search((), {}, ())("a", "b") == "oracle"
