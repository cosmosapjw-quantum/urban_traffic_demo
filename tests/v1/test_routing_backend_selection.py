"""Explicit migration backend selection never silently changes the closure."""
import pytest
from metroflow.v1.scenarios import scenario_city
from metroflow.v1.release_services import compile_service_plan


def test_invalid_backend_rejected_before_preparation(monkeypatch):
    monkeypatch.setenv('METROFLOW_V1_ROUTING_BACKEND', 'typo')
    with pytest.raises(ValueError, match='routing backend'):
        compile_service_plan(scenario_city(1000), ())
