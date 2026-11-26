"""Explicit opt-in boundary; no simulation or benchmark is performed here."""
import pytest


def test_legacy_python_scientific_entrypoints_refuse_without_opt_in(monkeypatch):
    from metroflow.oracle_policy import require_python_oracle
    from metroflow.v1.information import InformationModel
    from metroflow.v1.routing import RoutingModel
    from metroflow.v1.accessibility import compile_accessibility
    from metroflow.v1.development import GrowthModel
    from metroflow.terrain_city.network import generate
    from metroflow.restored_city import generate as restored_generate

    monkeypatch.delenv("METROFLOW_ENABLE_PYTHON_ORACLE", raising=False)
    for call in (
        require_python_oracle,
        lambda: InformationModel((), ()),
        lambda: RoutingModel((), (), topology_version="test"),
        lambda: compile_accessibility("city", (), 0),
        lambda: GrowthModel(None, (), budget_m=0),
        generate,
        restored_generate,
    ):
        with pytest.raises(RuntimeError, match="opt-in test oracle"):
            call()
    monkeypatch.setenv("METROFLOW_ENABLE_PYTHON_ORACLE", "1")
    require_python_oracle()
