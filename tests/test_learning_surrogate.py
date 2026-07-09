from __future__ import annotations

import subprocess
import sys

import pytest

from metroflow.flow.state import create_link_state


def make_surrogate_label_records():
    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr
    from metroflow.learning.labels import export_route_scoring_label_records

    road_csr = build_road_network_csr(
        nodes=(Node(1), Node(2), Node(3), Node(4)),
        links=(
            RoadLink(10, 1, 2, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(11, 2, 4, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(12, 1, 3, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(13, 3, 4, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
        ),
    )
    link_state = create_link_state(
        road_csr.link_count,
        travel_time_cost=(5.0, 1.0, 2.0, 1.0),
        capacity_veh_per_tick=(5.0, 5.0, 5.0, 5.0),
    )
    return export_route_scoring_label_records(
        road_csr=road_csr,
        link_state=link_state,
        od_pairs=((1, 4),),
        max_candidates=2,
    )


def test_baseline_route_surrogate_fit_and_predict_are_deterministic():
    from metroflow.learning.surrogate import (
        RouteSurrogateExperimentConfig,
        fit_route_surrogate_experiment,
        predict_route_surrogate_scores,
    )

    records = make_surrogate_label_records()
    config = RouteSurrogateExperimentConfig(
        backend="baseline_numpy",
        model_version="route_surrogate_v0",
    )
    first = fit_route_surrogate_experiment(records, config=config)
    second = fit_route_surrogate_experiment(records, config=config)

    assert first.model_fingerprint == second.model_fingerprint
    assert first.backend_requested == "baseline_numpy"
    assert first.backend_actual == "baseline_numpy"
    assert first.backend_fallback is None
    assert first.runtime_authority == "baseline_fallback_only"
    assert first.label_count == 1
    assert first.model_version == "route_surrogate_v0"
    prediction = predict_route_surrogate_scores(first.model, records[0])
    assert prediction.backend_actual == "baseline_numpy"
    assert prediction.predicted_route_score_values == (-3.0, -6.0)
    assert prediction.selected_candidate_index == 0
    assert prediction.runtime_authority == "baseline_fallback_only"


def test_torch_optional_surrogate_falls_back_when_torch_unavailable(monkeypatch):
    from metroflow.learning import surrogate
    from metroflow.learning.surrogate import (
        RouteSurrogateExperimentConfig,
        fit_route_surrogate_experiment,
    )

    records = make_surrogate_label_records()

    def fail_import_torch():
        raise ModuleNotFoundError("No module named 'torch'")

    monkeypatch.setattr(surrogate, "_import_torch", fail_import_torch)
    result = fit_route_surrogate_experiment(
        records,
        config=RouteSurrogateExperimentConfig(backend="torch_optional"),
    )

    assert result.backend_requested == "torch_optional"
    assert result.backend_actual == "baseline_numpy"
    assert result.backend_fallback == "torch_unavailable"
    assert result.model_family == "numpy_route_score_mean"
    assert result.runtime_authority == "baseline_fallback_only"


def test_torch_optional_surrogate_probe_does_not_claim_torch_model(monkeypatch):
    from metroflow.learning import surrogate
    from metroflow.learning.surrogate import (
        RouteSurrogateExperimentConfig,
        fit_route_surrogate_experiment,
    )

    records = make_surrogate_label_records()

    monkeypatch.setattr(surrogate, "_fit_torch_route_score_summary", lambda _records: None)
    result = fit_route_surrogate_experiment(
        records,
        config=RouteSurrogateExperimentConfig(backend="torch_optional"),
    )

    assert result.backend_requested == "torch_optional"
    assert result.backend_actual == "baseline_numpy"
    assert result.backend_fallback == "torch_probe_only"
    assert result.model_family == "numpy_route_score_mean"
    assert result.metadata["torch_probe_available"] is True


def test_surrogate_rejects_runtime_backend_names():
    from metroflow.learning.surrogate import RouteSurrogateExperimentConfig
    from metroflow.sim.config import SimulationConfig

    with pytest.raises(ValueError, match="backend"):
        RouteSurrogateExperimentConfig(backend="torch_cuda")
    with pytest.raises(ValueError, match="routing_backend"):
        SimulationConfig(routing_backend="torch_cuda")


def test_surrogate_imports_do_not_load_accelerators():
    script = """
import sys
import metroflow.learning.surrogate  # noqa: F401
print('torch', 'torch' in sys.modules)
print('jax', 'jax' in sys.modules)
print('jax.numpy', 'jax.numpy' in sys.modules)
print('_metroflow_rust', '_metroflow_rust' in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == [
        "torch False",
        "jax False",
        "jax.numpy False",
        "_metroflow_rust False",
    ]


def test_learning_package_imports_do_not_load_accelerators():
    script = """
import sys
import metroflow.learning  # noqa: F401
print('torch', 'torch' in sys.modules)
print('jax', 'jax' in sys.modules)
print('jax.numpy', 'jax.numpy' in sys.modules)
print('_metroflow_rust', '_metroflow_rust' in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == [
        "torch False",
        "jax False",
        "jax.numpy False",
        "_metroflow_rust False",
    ]
