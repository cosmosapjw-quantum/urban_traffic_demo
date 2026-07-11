from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest


def _metric(model_kind: str, seed: int, normalized_mae: float, *, parameter_count: int):
    from metroflow.benchmarks.jax_graph_cost_to_go_bakeoff import ModelFitMetric

    return ModelFitMetric(
        model_kind=model_kind,
        model_seed=seed,
        validation_normalized_mae=normalized_mae,
        validation_normalized_rmse=normalized_mae * 1.2,
        validation_raw_mae=normalized_mae * 10.0,
        validation_raw_rmse=normalized_mae * 12.0,
        final_train_loss=0.1,
        parameter_count=parameter_count,
        parameter_fingerprint=("a" if model_kind == "row_local" else "b") * 64,
        first_train_step_wall_ns=10,
        steady_train_step_median_wall_ns=5,
        first_inference_wall_ns=8,
        steady_inference_median_wall_ns=3,
        device_platform="gpu",
        device_kind="NVIDIA GeForce RTX 3080 Ti",
        jax_version="0.10.2",
        optax_version="0.2.8",
    )


def _run(seed: int, *, ratio: float):
    from metroflow.benchmarks.jax_graph_cost_to_go_bakeoff import (
        GraphBakeoffSeedRun,
    )

    row = _metric("row_local", seed, 1.0, parameter_count=3_873)
    graph = _metric("graph_aware", seed, ratio, parameter_count=4_257)
    return GraphBakeoffSeedRun(model_seed=seed, row_local=row, graph_aware=graph)


def _repeat(*, passed: bool = True):
    from metroflow.benchmarks.jax_graph_cost_to_go_bakeoff import (
        RepeatDeterminismAudit,
    )

    return RepeatDeterminismAudit(
        model_seed=41,
        maximum_normalized_prediction_difference=(0.0 if passed else 1.0e-2),
        normalized_mae_difference=(0.0 if passed else 1.0e-3),
        passed=passed,
    )


def _validation_slices(runs):
    from metroflow.benchmarks.jax_graph_cost_to_go_bakeoff import (
        ValidationSliceMetric,
    )

    slices = []
    for run in runs:
        for model_kind, metric in (
            ("row_local", run.row_local),
            ("graph_aware", run.graph_aware),
        ):
            for style_id in ("grid_core", "polycentric_tod", "organic"):
                for dynamic_state in ("free_flow", "stressed_closure"):
                    for distance_bin in (
                        "0.00-0.25",
                        "0.25-0.50",
                        "0.50-0.75",
                        "0.75-1.00",
                    ):
                        slices.append(
                            ValidationSliceMetric(
                                model_kind=model_kind,
                                model_seed=run.model_seed,
                                style_id=style_id,
                                scenario_seed=29,
                                dynamic_state=dynamic_state,
                                distance_bin=distance_bin,
                                valid_target_count=1,
                                normalized_mae=metric.validation_normalized_mae,
                                normalized_rmse=metric.validation_normalized_rmse,
                                raw_mae=metric.validation_raw_mae,
                                raw_rmse=metric.validation_raw_rmse,
                            )
                        )
    return tuple(slices)

def test_graph_bakeoff_config_freezes_canonical_workload() -> None:
    from metroflow.benchmarks.jax_graph_cost_to_go_bakeoff import (
        JaxGraphCostToGoBakeoffConfig,
    )

    config = JaxGraphCostToGoBakeoffConfig()
    assert config.canonical_profile is True
    assert config.style_ids == ("grid_core", "polycentric_tod", "organic")
    assert config.scenario_seeds == (17, 29, 41)
    assert config.model_seeds == (41, 42, 43)
    assert config.held_out_scenario_seed == 29
    assert config.message_passing_steps == 16
    assert config.epochs == 30
    assert config.graph_batch_size == 4
    assert config.required_mean_mae_ratio == 0.90
    assert config.required_seed_pass_count == 2
    with pytest.raises(ValueError, match="three unique model seeds"):
        JaxGraphCostToGoBakeoffConfig(model_seeds=(41, 42, 42))
    with pytest.raises(ValueError, match="repeat_model_seed"):
        JaxGraphCostToGoBakeoffConfig(repeat_model_seed=99)
    with pytest.raises(ValueError, match="graph_batch_size"):
        JaxGraphCostToGoBakeoffConfig(graph_batch_size=0)


def test_graph_bakeoff_gate_distinguishes_support_miss_and_inconclusive() -> None:
    from metroflow.benchmarks.jax_graph_cost_to_go_bakeoff import (
        JaxGraphCostToGoBakeoffConfig,
        evaluate_graph_bakeoff_decision,
    )

    config = JaxGraphCostToGoBakeoffConfig()
    supported = evaluate_graph_bakeoff_decision(
        config,
        tuple(_run(seed, ratio=0.80) for seed in config.model_seeds),
        _repeat(),
        corpus_provenance_valid=True,
    )
    assert supported.decision_state == "graph_signal_supported"
    assert supported.graph_signal_supported is True
    assert supported.runtime_nn_backend_authorized is False
    assert supported.mean_normalized_mae_ratio == pytest.approx(0.80)
    assert supported.seed_pass_count == 3

    missed = evaluate_graph_bakeoff_decision(
        config,
        tuple(_run(seed, ratio=0.95) for seed in config.model_seeds),
        _repeat(),
        corpus_provenance_valid=True,
    )
    assert missed.decision_state == "graph_signal_not_supported"
    assert missed.graph_signal_supported is False
    assert missed.inconclusive_reasons == ()

    nondeterministic = evaluate_graph_bakeoff_decision(
        config,
        tuple(_run(seed, ratio=0.80) for seed in config.model_seeds),
        _repeat(passed=False),
        corpus_provenance_valid=True,
    )
    assert nondeterministic.decision_state == "inconclusive"
    assert "repeat_determinism_failed" in nondeterministic.inconclusive_reasons

    cpu_run = replace(
        _run(41, ratio=0.80),
        graph_aware=replace(
            _metric("graph_aware", 41, 0.80, parameter_count=4_257),
            device_platform="cpu",
        ),
    )
    wrong_device = evaluate_graph_bakeoff_decision(
        config,
        (cpu_run, _run(42, ratio=0.80), _run(43, ratio=0.80)),
        _repeat(),
        corpus_provenance_valid=True,
    )
    assert wrong_device.decision_state == "inconclusive"
    assert "gpu_requirement_failed" in wrong_device.inconclusive_reasons


def test_graph_bakeoff_gate_fails_closed_on_seed_or_parameter_mismatch() -> None:
    from metroflow.benchmarks.jax_graph_cost_to_go_bakeoff import (
        JaxGraphCostToGoBakeoffConfig,
        evaluate_graph_bakeoff_decision,
    )

    config = JaxGraphCostToGoBakeoffConfig()
    with pytest.raises(ValueError, match="exactly one run per model seed"):
        evaluate_graph_bakeoff_decision(
            config,
            (_run(41, ratio=0.8), _run(42, ratio=0.8)),
            _repeat(),
            corpus_provenance_valid=True,
        )
    unfair = _run(41, ratio=0.8)
    unfair = replace(
        unfair,
        graph_aware=replace(unfair.graph_aware, parameter_count=8_000),
    )
    decision = evaluate_graph_bakeoff_decision(
        config,
        (unfair, _run(42, ratio=0.8), _run(43, ratio=0.8)),
        _repeat(),
        corpus_provenance_valid=True,
    )
    assert decision.decision_state == "inconclusive"
    assert "parameter_count_fairness_failed" in decision.inconclusive_reasons


def test_pr49_holdout_loader_preserves_canonical_provenance() -> None:
    from metroflow.benchmarks.jax_graph_cost_to_go_bakeoff import (
        load_pr49_holdout_contract,
    )

    artifact_path = (
        Path(__file__).resolve().parents[1]
        / "artifacts"
        / "cost_to_go_feature_audit_20260711"
        / "cost-to-go-feature-audit.json"
    )
    holdout = load_pr49_holdout_contract(artifact_path)
    assert holdout.held_out_seed == 29
    assert holdout.split_seed == 49
    assert len(holdout.train_static_network_fingerprints) == 6
    assert len(holdout.validation_static_network_fingerprints) == 3
    assert holdout.split_fingerprint == (
        "ff6d63ba13a465c032dea2c20b4920bd77ee04c8180e409602a772051d80e18a"
    )
    forged_path = artifact_path.parent / "forged.json"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload["map_holdout"]["split_fingerprint"] = "f" * 64
    with pytest.raises(ValueError, match="map holdout fingerprint"):
        load_pr49_holdout_contract(forged_path, payload=payload)


def test_graph_bakeoff_artifact_is_diagnostic_and_deterministic(tmp_path) -> None:
    from metroflow.benchmarks.jax_graph_cost_to_go_bakeoff import (
        GraphBakeoffResult,
        JaxGraphCostToGoBakeoffConfig,
        evaluate_graph_bakeoff_decision,
        write_graph_bakeoff_artifacts,
    )
    from metroflow.learning.cost_to_go_graph_tensors import (
        COST_TO_GO_GRAPH_CONTRACT_FINGERPRINT,
    )

    config = JaxGraphCostToGoBakeoffConfig()
    runs = tuple(_run(seed, ratio=0.8) for seed in config.model_seeds)
    decision = evaluate_graph_bakeoff_decision(
        config,
        runs,
        _repeat(),
        corpus_provenance_valid=True,
    )
    result = GraphBakeoffResult(
        config=config,
        runs=runs,
        repeat_determinism=_repeat(),
        decision=decision,
        corpus_fingerprint="c" * 64,
        graph_contract_fingerprint=COST_TO_GO_GRAPH_CONTRACT_FINGERPRINT,
        graph_split_fingerprint="d" * 64,
        map_holdout_split_fingerprint="e" * 64,
        normalization_fingerprint="f" * 64,
        model_config_fingerprint="1" * 64,
        graph_sample_count=72,
        train_graph_count=48,
        validation_graph_count=24,
        validation_slice_metrics=_validation_slices(runs),
        jax_runtime_warmup_wall_ns=100,
        xla_python_client_mem_fraction="0.70",
    )
    first = write_graph_bakeoff_artifacts(result, tmp_path / "first")
    second = write_graph_bakeoff_artifacts(result, tmp_path / "second")
    payload = json.loads(first["json"].read_text(encoding="utf-8"))
    manifest = json.loads(first["manifest"].read_text(encoding="utf-8"))
    assert payload["evidence_status"] == "diagnostic_not_runtime_validation"
    assert payload["decision"]["decision_state"] == "graph_signal_supported"
    assert payload["runtime_nn_backend_authorized"] is False
    assert payload["route_legality_changed"] is False
    assert payload["raw_predictions_persisted"] is False
    assert manifest["runtime_nn_backend_authorized"] is False
    assert manifest["graph_split_fingerprint"] == "d" * 64
    with pytest.raises(ValueError, match="evidence_status"):
        replace(result, evidence_status="validated")
    with pytest.raises(ValueError, match="decision does not match"):
        replace(
            result,
            decision=replace(
                decision,
                mean_normalized_mae_ratio=0.79,
            ),
        )
    with pytest.raises(ValueError, match="configured model seeds"):
        replace(result, runs=(runs[0], runs[0], runs[2]))
    with pytest.raises(ValueError, match="positive and complete"):
        replace(result, validation_graph_count=25)
    with pytest.raises(ValueError, match="validation slices must cover"):
        replace(result, validation_slice_metrics=result.validation_slice_metrics[:-1])
    with pytest.raises(ValueError, match="reconstruct top-level"):
        first_slice = result.validation_slice_metrics[0]
        replace(
            result,
            validation_slice_metrics=(
                replace(first_slice, normalized_mae=0.0),
                *result.validation_slice_metrics[1:],
            ),
        )
    for key in ("json", "markdown", "manifest"):
        assert first[key].read_bytes() == second[key].read_bytes()
    with pytest.raises(ValueError, match="output_dir must be empty"):
        write_graph_bakeoff_artifacts(result, tmp_path / "first")


def test_graph_bakeoff_import_is_accelerator_lazy() -> None:
    script = """
import sys
import metroflow.benchmarks.jax_graph_cost_to_go_bakeoff  # noqa: F401
print('jax', 'jax' in sys.modules)
print('optax', 'optax' in sys.modules)
print('torch', 'torch' in sys.modules)
print('_metroflow_rust', '_metroflow_rust' in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.splitlines() == [
        "jax False",
        "optax False",
        "torch False",
        "_metroflow_rust False",
    ]


def test_graph_message_kernel_propagates_reverse_and_respects_masks() -> None:
    jax = pytest.importorskip("jax")
    jnp = pytest.importorskip("jax.numpy")
    from metroflow.benchmarks.jax_graph_cost_to_go_bakeoff import (
        _predict_graph_aware,
    )

    params = {
        "encoder": {
            "weight": jnp.asarray([[1.0]], dtype=jnp.float32),
            "bias": jnp.zeros((1,), dtype=jnp.float32),
        },
        "message": {
            "weight": jnp.asarray([[1.0], [1.0]], dtype=jnp.float32),
            "bias": jnp.zeros((1,), dtype=jnp.float32),
        },
        "update": {
            "weight": jnp.asarray([[0.0], [1.0]], dtype=jnp.float32),
            "bias": jnp.zeros((1,), dtype=jnp.float32),
        },
        "output": {
            "weight": jnp.asarray([[1.0]], dtype=jnp.float32),
            "bias": jnp.zeros((1,), dtype=jnp.float32),
        },
    }
    data = {
        "node_features": jnp.asarray([[[0.0], [0.0], [1.0]]]),
        "edge_features": jnp.asarray([[[0.0], [0.0], [10.0]]]),
        "edge_index": jnp.asarray([[[0, 1, 2], [1, 2, 0]]], dtype=jnp.int32),
        "blocked_link_mask": jnp.zeros((1, 3), dtype=jnp.bool_),
        "node_mask": jnp.ones((1, 3), dtype=jnp.bool_),
        "edge_mask": jnp.asarray([[True, True, False]], dtype=jnp.bool_),
    }
    connected = np.asarray(
        _predict_graph_aware(
            params,
            data,
            message_passing_steps=2,
            jax=jax,
            jnp=jnp,
        )
    )
    blocked = np.asarray(
        _predict_graph_aware(
            params,
            {**data, "blocked_link_mask": jnp.ones((1, 3), dtype=jnp.bool_)},
            message_passing_steps=2,
            jax=jax,
            jnp=jnp,
        )
    )
    assert connected[0, 0] > blocked[0, 0]
    assert connected.shape == (1, 3)
    padding_as_real = np.asarray(
        _predict_graph_aware(
            params,
            {**data, "edge_mask": jnp.ones((1, 3), dtype=jnp.bool_)},
            message_passing_steps=2,
            jax=jax,
            jnp=jnp,
        )
    )
    assert not np.array_equal(connected, padding_as_real)


def test_edge_sort_keeps_features_and_blocked_mask_aligned() -> None:
    from metroflow.benchmarks.jax_graph_cost_to_go_bakeoff import (
        _stable_sort_edges_by_source_in_place,
    )

    edge_index = np.asarray(
        [[[1, 0, 1, 99], [2, 1, 0, 99]]],
        dtype=np.int32,
    )
    edge_features = np.asarray([[[10.0], [20.0], [30.0], [999.0]]])
    blocked = np.asarray([[True, False, False, True]])
    _stable_sort_edges_by_source_in_place(
        edge_index,
        edge_features,
        blocked,
        (3,),
    )
    np.testing.assert_array_equal(edge_index[0, :, :3], [[0, 1, 1], [1, 2, 0]])
    np.testing.assert_array_equal(
        edge_features[0, :, 0],
        [20.0, 10.0, 30.0, 999.0],
    )
    np.testing.assert_array_equal(blocked[0], [False, True, False, True])


def test_short_jax_training_smoke_is_repeatable() -> None:
    jax = pytest.importorskip("jax")
    jnp = pytest.importorskip("jax.numpy")
    optax = pytest.importorskip("optax")
    from metroflow.benchmarks.jax_graph_cost_to_go_bakeoff import (
        JaxGraphCostToGoBakeoffConfig,
        _fit_jax_model,
    )

    node_features = np.asarray(
        [
            [[0.0, 1.0], [0.5, 0.5], [1.0, 0.0]],
            [[0.0, 1.0], [0.4, 0.6], [1.0, 0.0]],
            [[0.0, 1.0], [0.6, 0.4], [1.0, 0.0]],
            [[0.0, 1.0], [0.7, 0.3], [1.0, 0.0]],
        ],
        dtype=np.float32,
    )
    target_normalized = np.asarray(
        [[2.0, 1.0, 0.0]] * 4,
        dtype=np.float32,
    )
    host_data = {
        "blocked_link_mask": np.zeros((4, 2), dtype=np.bool_),
        "distance_fraction": node_features[:, :, 0],
        "edge_features": np.zeros((4, 2, 1), dtype=np.float32),
        "edge_index": np.asarray([[[0, 1], [1, 2]]] * 4, dtype=np.int32),
        "edge_mask": np.ones((4, 2), dtype=np.bool_),
        "node_features": node_features,
        "node_mask": np.ones((4, 3), dtype=np.bool_),
        "target_log": np.log1p(target_normalized).astype(np.float32),
        "target_mask": np.ones((4, 3), dtype=np.bool_),
        "target_normalized": target_normalized,
        "target_raw": target_normalized * 10.0,
        "target_scale": np.full((4, 3), 10.0, dtype=np.float32),
    }
    device = jax.devices()[0]
    device_data = {name: jax.device_put(value) for name, value in host_data.items()}
    config = JaxGraphCostToGoBakeoffConfig(
        hidden_width=4,
        message_passing_steps=2,
        epochs=2,
        graph_batch_size=2,
        require_gpu=False,
    )
    arguments = {
        "model_kind": "graph_aware",
        "model_seed": 41,
        "config": config,
        "jax": jax,
        "jnp": jnp,
        "optax": optax,
        "device_data": device_data,
        "train_indices": np.asarray([0, 1], dtype=np.int32),
        "validation_indices": np.asarray([2, 3], dtype=np.int32),
        "device": device,
    }
    first = _fit_jax_model(**arguments)
    second = _fit_jax_model(**arguments)
    assert first.metric.parameter_count > 0
    assert np.isfinite(first.metric.validation_normalized_mae)
    assert np.max(
        np.abs(
            first.validation_normalized_predictions
            - second.validation_normalized_predictions
        )
    ) <= 1.0e-4


def test_canonical_graph_bakeoff_artifact_fails_accuracy_and_determinism_gates() -> None:
    artifact_path = (
        Path(__file__).resolve().parents[1]
        / "artifacts"
        / "jax_graph_cost_to_go_bakeoff_20260711"
        / "jax-graph-cost-to-go-bakeoff.json"
    )
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert payload["config"]["canonical_profile"] is True
    assert payload["graph_sample_count"] == 72
    assert payload["train_graph_count"] == 48
    assert payload["validation_graph_count"] == 24
    assert payload["decision"]["decision_state"] == "inconclusive"
    assert payload["decision"]["graph_signal_supported"] is False
    assert payload["decision"]["accuracy_gate_passed"] is False
    assert payload["decision"]["seed_pass_count"] == 0
    assert payload["decision"]["mean_normalized_mae_ratio"] > 0.90
    assert payload["repeat_determinism"]["passed"] is False
    assert "repeat_determinism_failed" in payload["decision"][
        "inconclusive_reasons"
    ]
    assert payload["runtime_nn_backend_authorized"] is False
    assert payload["route_legality_changed"] is False
    assert payload["raw_predictions_persisted"] is False
    assert payload["graph_split_fingerprint"]
    assert len(payload["validation_slice_metrics"]) == 144
    assert all(
        metric["valid_target_count"] > 0
        for metric in payload["validation_slice_metrics"]
    )
    assert {metric["distance_bin"] for metric in payload["validation_slice_metrics"]} == {
        "0.00-0.25",
        "0.25-0.50",
        "0.50-0.75",
        "0.75-1.00",
    }
