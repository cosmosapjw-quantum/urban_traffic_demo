"""Bounded JAX graph-aware versus row-local cost-to-go bakeoff."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
from statistics import mean, median
from time import perf_counter_ns
from typing import Any, Mapping

import numpy as np

from metroflow.learning.cost_to_go_features import COST_TO_GO_FEATURE_NAMES
from metroflow.learning.cost_to_go_graph_tensors import (
    COST_TO_GO_GRAPH_CONTRACT_FINGERPRINT,
    CostToGoGraphBatch,
    CostToGoGraphSample,
    CostToGoGraphSplit,
    build_cost_to_go_graph_batch,
    build_cost_to_go_graph_sample,
    compute_cost_to_go_map_holdout_fingerprint,
    split_cost_to_go_graph_samples,
)

__all__ = [
    "GraphBakeoffDecision",
    "GraphBakeoffResult",
    "GraphBakeoffSeedRun",
    "JaxGraphCostToGoBakeoffConfig",
    "ModelFitMetric",
    "PR49HoldoutContract",
    "RepeatDeterminismAudit",
    "ValidationSliceMetric",
    "evaluate_graph_bakeoff_decision",
    "load_pr49_holdout_contract",
    "run_jax_graph_cost_to_go_bakeoff",
    "write_graph_bakeoff_artifacts",
]

_CANONICAL_STYLE_IDS = ("grid_core", "polycentric_tod", "organic")
_CANONICAL_SCENARIO_SEEDS = (17, 29, 41)
_CANONICAL_MODEL_SEEDS = (41, 42, 43)
_CANONICAL_HELD_OUT_SEED = 29
_CANONICAL_HOLDOUT_SELECTION_SEED = 49
_CANONICAL_DESTINATION_COUNT = 4
_CANONICAL_CLOSURE_FRACTION = 0.03
_CANONICAL_HIDDEN_WIDTH = 32
_CANONICAL_MESSAGE_STEPS = 16
_CANONICAL_EPOCHS = 30
_CANONICAL_GRAPH_BATCH_SIZE = 4
_CANONICAL_LEARNING_RATE = 1.0e-3
_CANONICAL_REQUIRED_RATIO = 0.90
_CANONICAL_REQUIRED_SEED_COUNT = 2
_CANONICAL_PARAMETER_RATIO = 1.15
_CANONICAL_REPEAT_PREDICTION_TOLERANCE = 1.0e-4
_CANONICAL_REPEAT_MAE_TOLERANCE = 1.0e-5
_THRESHOLD_PROVENANCE = (
    "author_attested_fixed_in_worktree_before_canonical_run_"
    "not_versioned_preregistered"
)
_DISTANCE_BINS = (
    ("0.00-0.25", 0.0, 0.25),
    ("0.25-0.50", 0.25, 0.50),
    ("0.50-0.75", 0.50, 0.75),
    ("0.75-1.00", 0.75, 1.000001),
)


@dataclass(frozen=True, slots=True)
class JaxGraphCostToGoBakeoffConfig:
    style_ids: tuple[str, ...] = _CANONICAL_STYLE_IDS
    scenario_seeds: tuple[int, ...] = _CANONICAL_SCENARIO_SEEDS
    model_seeds: tuple[int, ...] = _CANONICAL_MODEL_SEEDS
    held_out_scenario_seed: int = _CANONICAL_HELD_OUT_SEED
    map_holdout_selection_seed: int = _CANONICAL_HOLDOUT_SELECTION_SEED
    destination_count: int = _CANONICAL_DESTINATION_COUNT
    closure_fraction: float = _CANONICAL_CLOSURE_FRACTION
    hidden_width: int = _CANONICAL_HIDDEN_WIDTH
    message_passing_steps: int = _CANONICAL_MESSAGE_STEPS
    epochs: int = _CANONICAL_EPOCHS
    graph_batch_size: int = _CANONICAL_GRAPH_BATCH_SIZE
    learning_rate: float = _CANONICAL_LEARNING_RATE
    required_mean_mae_ratio: float = _CANONICAL_REQUIRED_RATIO
    required_seed_pass_count: int = _CANONICAL_REQUIRED_SEED_COUNT
    maximum_parameter_count_ratio: float = _CANONICAL_PARAMETER_RATIO
    repeat_model_seed: int = 41
    maximum_repeat_prediction_difference: float = (
        _CANONICAL_REPEAT_PREDICTION_TOLERANCE
    )
    maximum_repeat_mae_difference: float = _CANONICAL_REPEAT_MAE_TOLERANCE
    require_gpu: bool = True

    def __post_init__(self) -> None:
        styles = tuple(str(value).strip() for value in self.style_ids)
        scenario_seeds = tuple(int(value) for value in self.scenario_seeds)
        model_seeds = tuple(int(value) for value in self.model_seeds)
        if len(styles) != 3 or len(set(styles)) != 3 or not all(styles):
            raise ValueError("graph bakeoff requires three unique non-empty styles")
        if len(scenario_seeds) != 3 or len(set(scenario_seeds)) != 3:
            raise ValueError("graph bakeoff requires three unique scenario seeds")
        if len(model_seeds) != 3 or len(set(model_seeds)) != 3:
            raise ValueError("graph bakeoff requires three unique model seeds")
        held_out = int(self.held_out_scenario_seed)
        if held_out not in scenario_seeds:
            raise ValueError("held_out_scenario_seed must be one scenario seed")
        repeat_seed = int(self.repeat_model_seed)
        if repeat_seed not in model_seeds:
            raise ValueError("repeat_model_seed must be one model seed")
        positive_ints = {
            "destination_count": self.destination_count,
            "hidden_width": self.hidden_width,
            "message_passing_steps": self.message_passing_steps,
            "epochs": self.epochs,
            "graph_batch_size": self.graph_batch_size,
            "required_seed_pass_count": self.required_seed_pass_count,
        }
        for name, raw_value in positive_ints.items():
            if int(raw_value) < 1:
                raise ValueError(f"{name} must be >= 1")
        if int(self.required_seed_pass_count) > len(model_seeds):
            raise ValueError("required_seed_pass_count cannot exceed model seed count")
        bounded_values = {
            "closure_fraction": self.closure_fraction,
            "learning_rate": self.learning_rate,
            "required_mean_mae_ratio": self.required_mean_mae_ratio,
            "maximum_repeat_prediction_difference": (
                self.maximum_repeat_prediction_difference
            ),
            "maximum_repeat_mae_difference": self.maximum_repeat_mae_difference,
        }
        for name, raw_value in bounded_values.items():
            value = float(raw_value)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and > 0")
        parameter_ratio = float(self.maximum_parameter_count_ratio)
        if not math.isfinite(parameter_ratio) or parameter_ratio < 1.0:
            raise ValueError("maximum_parameter_count_ratio must be finite and >= 1")
        object.__setattr__(self, "style_ids", styles)
        object.__setattr__(self, "scenario_seeds", scenario_seeds)
        object.__setattr__(self, "model_seeds", model_seeds)
        object.__setattr__(self, "held_out_scenario_seed", held_out)
        object.__setattr__(self, "map_holdout_selection_seed", int(self.map_holdout_selection_seed))
        for name, raw_value in positive_ints.items():
            object.__setattr__(self, name, int(raw_value))
        for name, raw_value in bounded_values.items():
            object.__setattr__(self, name, float(raw_value))
        object.__setattr__(self, "maximum_parameter_count_ratio", parameter_ratio)
        object.__setattr__(self, "repeat_model_seed", repeat_seed)
        object.__setattr__(self, "require_gpu", bool(self.require_gpu))

    @property
    def canonical_profile(self) -> bool:
        return self.as_dict(include_canonical=False) == {
            "style_ids": list(_CANONICAL_STYLE_IDS),
            "scenario_seeds": list(_CANONICAL_SCENARIO_SEEDS),
            "model_seeds": list(_CANONICAL_MODEL_SEEDS),
            "held_out_scenario_seed": _CANONICAL_HELD_OUT_SEED,
            "map_holdout_selection_seed": _CANONICAL_HOLDOUT_SELECTION_SEED,
            "destination_count": _CANONICAL_DESTINATION_COUNT,
            "closure_fraction": _CANONICAL_CLOSURE_FRACTION,
            "hidden_width": _CANONICAL_HIDDEN_WIDTH,
            "message_passing_steps": _CANONICAL_MESSAGE_STEPS,
            "epochs": _CANONICAL_EPOCHS,
            "graph_batch_size": _CANONICAL_GRAPH_BATCH_SIZE,
            "learning_rate": _CANONICAL_LEARNING_RATE,
            "required_mean_mae_ratio": _CANONICAL_REQUIRED_RATIO,
            "required_seed_pass_count": _CANONICAL_REQUIRED_SEED_COUNT,
            "maximum_parameter_count_ratio": _CANONICAL_PARAMETER_RATIO,
            "repeat_model_seed": 41,
            "maximum_repeat_prediction_difference": (
                _CANONICAL_REPEAT_PREDICTION_TOLERANCE
            ),
            "maximum_repeat_mae_difference": _CANONICAL_REPEAT_MAE_TOLERANCE,
            "require_gpu": True,
        }

    def as_dict(self, *, include_canonical: bool = True) -> dict[str, Any]:
        output = {
            "style_ids": list(self.style_ids),
            "scenario_seeds": list(self.scenario_seeds),
            "model_seeds": list(self.model_seeds),
            "held_out_scenario_seed": self.held_out_scenario_seed,
            "map_holdout_selection_seed": self.map_holdout_selection_seed,
            "destination_count": self.destination_count,
            "closure_fraction": self.closure_fraction,
            "hidden_width": self.hidden_width,
            "message_passing_steps": self.message_passing_steps,
            "epochs": self.epochs,
            "graph_batch_size": self.graph_batch_size,
            "learning_rate": self.learning_rate,
            "required_mean_mae_ratio": self.required_mean_mae_ratio,
            "required_seed_pass_count": self.required_seed_pass_count,
            "maximum_parameter_count_ratio": self.maximum_parameter_count_ratio,
            "repeat_model_seed": self.repeat_model_seed,
            "maximum_repeat_prediction_difference": (
                self.maximum_repeat_prediction_difference
            ),
            "maximum_repeat_mae_difference": self.maximum_repeat_mae_difference,
            "require_gpu": self.require_gpu,
        }
        if include_canonical:
            output["canonical_profile"] = self.canonical_profile
        return output


@dataclass(frozen=True, slots=True)
class PR49HoldoutContract:
    split_seed: int
    held_out_seed: int
    train_static_network_fingerprints: tuple[str, ...]
    validation_static_network_fingerprints: tuple[str, ...]
    split_fingerprint: str


@dataclass(frozen=True, slots=True)
class _GraphSampleDescriptor:
    style_id: str
    scenario_seed: int
    dynamic_state: str
    destination_node_id: int
    sample_fingerprint: str
    static_network_fingerprint: str
    dynamic_state_fingerprint: str


@dataclass(frozen=True, slots=True)
class _ExperimentCorpus:
    batch: CostToGoGraphBatch
    split: CostToGoGraphSplit
    descriptors: tuple[_GraphSampleDescriptor, ...]
    node_feature_mean: np.ndarray
    node_feature_std: np.ndarray
    edge_feature_mean: np.ndarray
    edge_feature_std: np.ndarray
    corpus_fingerprint: str
    normalization_fingerprint: str


@dataclass(frozen=True, slots=True)
class _ModelTrainingOutput:
    metric: ModelFitMetric
    validation_normalized_predictions: np.ndarray
    validation_normalized_targets: np.ndarray
    validation_raw_predictions: np.ndarray
    validation_raw_targets: np.ndarray
    validation_target_mask: np.ndarray
    validation_distance_fraction: np.ndarray


@dataclass(frozen=True, slots=True)
class ModelFitMetric:
    model_kind: str
    model_seed: int
    validation_normalized_mae: float
    validation_normalized_rmse: float
    validation_raw_mae: float
    validation_raw_rmse: float
    final_train_loss: float
    parameter_count: int
    parameter_fingerprint: str
    first_train_step_wall_ns: int
    steady_train_step_median_wall_ns: int
    first_inference_wall_ns: int
    steady_inference_median_wall_ns: int
    device_platform: str
    device_kind: str
    jax_version: str
    optax_version: str

    def __post_init__(self) -> None:
        if self.model_kind not in {"row_local", "graph_aware"}:
            raise ValueError("model_kind must be row_local or graph_aware")
        metrics = (
            self.validation_normalized_mae,
            self.validation_normalized_rmse,
            self.validation_raw_mae,
            self.validation_raw_rmse,
            self.final_train_loss,
        )
        if any(not math.isfinite(float(value)) or float(value) < 0.0 for value in metrics):
            raise ValueError("model metrics must be finite and non-negative")
        positive_ints = (
            self.parameter_count,
            self.first_train_step_wall_ns,
            self.steady_train_step_median_wall_ns,
            self.first_inference_wall_ns,
            self.steady_inference_median_wall_ns,
        )
        if any(int(value) <= 0 for value in positive_ints):
            raise ValueError("parameter count and timing metrics must be positive")
        _require_sha256(self.parameter_fingerprint, name="parameter_fingerprint")
        if not all(
            str(value).strip()
            for value in (
                self.device_platform,
                self.device_kind,
                self.jax_version,
                self.optax_version,
            )
        ):
            raise ValueError("device and library metadata must be non-empty")

    def as_dict(self) -> dict[str, Any]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class GraphBakeoffSeedRun:
    model_seed: int
    row_local: ModelFitMetric
    graph_aware: ModelFitMetric

    def __post_init__(self) -> None:
        seed = int(self.model_seed)
        if self.row_local.model_kind != "row_local":
            raise ValueError("row_local metric must report model_kind='row_local'")
        if self.graph_aware.model_kind != "graph_aware":
            raise ValueError("graph_aware metric must report model_kind='graph_aware'")
        if self.row_local.model_seed != seed or self.graph_aware.model_seed != seed:
            raise ValueError("model metrics must match GraphBakeoffSeedRun seed")
        object.__setattr__(self, "model_seed", seed)

    @property
    def normalized_mae_ratio(self) -> float:
        return float(
            self.graph_aware.validation_normalized_mae
            / max(self.row_local.validation_normalized_mae, 1.0e-12)
        )

    @property
    def parameter_count_ratio(self) -> float:
        smaller = min(self.row_local.parameter_count, self.graph_aware.parameter_count)
        larger = max(self.row_local.parameter_count, self.graph_aware.parameter_count)
        return float(larger / max(smaller, 1))

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_seed": self.model_seed,
            "normalized_mae_ratio": self.normalized_mae_ratio,
            "parameter_count_ratio": self.parameter_count_ratio,
            "row_local": self.row_local.as_dict(),
            "graph_aware": self.graph_aware.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class RepeatDeterminismAudit:
    model_seed: int
    maximum_normalized_prediction_difference: float
    normalized_mae_difference: float
    passed: bool

    def __post_init__(self) -> None:
        for value in (
            self.maximum_normalized_prediction_difference,
            self.normalized_mae_difference,
        ):
            if not math.isfinite(float(value)) or float(value) < 0.0:
                raise ValueError("repeat determinism differences must be finite and >= 0")
        if type(self.passed) is not bool:
            raise ValueError("repeat determinism passed must be bool")

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_seed": self.model_seed,
            "maximum_normalized_prediction_difference": (
                self.maximum_normalized_prediction_difference
            ),
            "normalized_mae_difference": self.normalized_mae_difference,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class ValidationSliceMetric:
    model_kind: str
    model_seed: int
    style_id: str
    scenario_seed: int
    dynamic_state: str
    distance_bin: str
    valid_target_count: int
    normalized_mae: float
    normalized_rmse: float
    raw_mae: float
    raw_rmse: float

    def __post_init__(self) -> None:
        if self.model_kind not in {"row_local", "graph_aware"}:
            raise ValueError("model_kind must be row_local or graph_aware")
        if not str(self.style_id).strip() or not str(self.dynamic_state).strip():
            raise ValueError("validation slice identity must be non-empty")
        if self.distance_bin not in {
            label for label, _lower, _upper in _DISTANCE_BINS
        }:
            raise ValueError("validation slice distance_bin is not canonical")
        if int(self.valid_target_count) < 1:
            raise ValueError("validation slice must contain at least one target")
        values = (
            self.normalized_mae,
            self.normalized_rmse,
            self.raw_mae,
            self.raw_rmse,
        )
        if any(
            not math.isfinite(float(value)) or float(value) < 0.0
            for value in values
        ):
            raise ValueError("validation slice metrics must be finite and non-negative")

    def as_dict(self) -> dict[str, Any]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class GraphBakeoffDecision:
    decision_state: str
    graph_signal_supported: bool
    mean_normalized_mae_ratio: float
    seed_pass_count: int
    accuracy_gate_passed: bool
    inconclusive_reasons: tuple[str, ...]
    runtime_nn_backend_authorized: bool = False
    route_legality_changed: bool = False

    def __post_init__(self) -> None:
        if self.decision_state not in {
            "graph_signal_supported",
            "graph_signal_not_supported",
            "inconclusive",
        }:
            raise ValueError("unexpected graph bakeoff decision_state")
        if type(self.graph_signal_supported) is not bool:
            raise ValueError("graph_signal_supported must be bool")
        if type(self.accuracy_gate_passed) is not bool:
            raise ValueError("accuracy_gate_passed must be bool")
        if (
            not math.isfinite(float(self.mean_normalized_mae_ratio))
            or float(self.mean_normalized_mae_ratio) < 0.0
        ):
            raise ValueError("mean_normalized_mae_ratio must be finite and >= 0")
        if int(self.seed_pass_count) < 0:
            raise ValueError("seed_pass_count must be >= 0")
        if self.graph_signal_supported != (
            self.decision_state == "graph_signal_supported"
        ):
            raise ValueError("graph_signal_supported must match decision_state")
        if self.decision_state == "graph_signal_supported" and (
            not self.accuracy_gate_passed or self.inconclusive_reasons
        ):
            raise ValueError("supported decision requires a clean accuracy gate")
        if self.decision_state == "graph_signal_not_supported" and (
            self.accuracy_gate_passed or self.inconclusive_reasons
        ):
            raise ValueError("unsupported decision must be a conclusive accuracy miss")
        if self.decision_state == "inconclusive" and not self.inconclusive_reasons:
            raise ValueError("inconclusive decision requires at least one reason")
        if self.runtime_nn_backend_authorized or self.route_legality_changed:
            raise ValueError("graph bakeoff cannot authorize runtime or route legality")

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision_state": self.decision_state,
            "graph_signal_supported": self.graph_signal_supported,
            "mean_normalized_mae_ratio": self.mean_normalized_mae_ratio,
            "seed_pass_count": self.seed_pass_count,
            "accuracy_gate_passed": self.accuracy_gate_passed,
            "inconclusive_reasons": list(self.inconclusive_reasons),
            "runtime_nn_backend_authorized": self.runtime_nn_backend_authorized,
            "route_legality_changed": self.route_legality_changed,
        }


@dataclass(frozen=True, slots=True)
class GraphBakeoffResult:
    config: JaxGraphCostToGoBakeoffConfig
    runs: tuple[GraphBakeoffSeedRun, ...]
    repeat_determinism: RepeatDeterminismAudit
    decision: GraphBakeoffDecision
    corpus_fingerprint: str
    graph_contract_fingerprint: str
    graph_split_fingerprint: str
    map_holdout_split_fingerprint: str
    normalization_fingerprint: str
    model_config_fingerprint: str
    graph_sample_count: int
    train_graph_count: int
    validation_graph_count: int
    validation_slice_metrics: tuple[ValidationSliceMetric, ...]
    jax_runtime_warmup_wall_ns: int
    xla_python_client_mem_fraction: str
    evidence_status: str = "diagnostic_not_runtime_validation"
    runtime_nn_backend_authorized: bool = False
    route_legality_changed: bool = False
    raw_predictions_persisted: bool = False

    def __post_init__(self) -> None:
        if (
            self.runtime_nn_backend_authorized
            or self.route_legality_changed
            or self.raw_predictions_persisted
        ):
            raise ValueError("graph bakeoff result cannot authorize or persist runtime output")
        for name in (
            "corpus_fingerprint",
            "graph_contract_fingerprint",
            "graph_split_fingerprint",
            "map_holdout_split_fingerprint",
            "normalization_fingerprint",
            "model_config_fingerprint",
        ):
            _require_sha256(getattr(self, name), name=name)
        actual_seeds = tuple(run.model_seed for run in self.runs)
        if (
            len(self.runs) != len(self.config.model_seeds)
            or len(set(actual_seeds)) != len(actual_seeds)
            or set(actual_seeds) != set(self.config.model_seeds)
        ):
            raise ValueError("result runs must match configured model seeds")
        if self.repeat_determinism.model_seed != self.config.repeat_model_seed:
            raise ValueError("result repeat seed must match config")
        if (
            self.graph_sample_count < 1
            or self.train_graph_count < 1
            or self.validation_graph_count < 1
            or self.train_graph_count + self.validation_graph_count
            != self.graph_sample_count
        ):
            raise ValueError("result graph counts must be positive and complete")
        if self.graph_contract_fingerprint != COST_TO_GO_GRAPH_CONTRACT_FINGERPRINT:
            raise ValueError("result graph contract fingerprint is not canonical")
        expected_decision = evaluate_graph_bakeoff_decision(
            self.config,
            self.runs,
            self.repeat_determinism,
            corpus_provenance_valid=True,
        )
        if self.decision != expected_decision:
            raise ValueError("result decision does not match runs and repeat audit")
        if self.evidence_status != "diagnostic_not_runtime_validation":
            raise ValueError("graph bakeoff evidence_status must remain diagnostic")
        if int(self.jax_runtime_warmup_wall_ns) <= 0:
            raise ValueError("jax_runtime_warmup_wall_ns must be positive")
        _validate_result_workload_and_slices(self)

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_format_version": "jax_graph_cost_to_go_bakeoff_v1",
            "evidence_status": self.evidence_status,
            "threshold_provenance": _THRESHOLD_PROVENANCE,
            "config": self.config.as_dict(),
            "corpus_fingerprint": self.corpus_fingerprint,
            "graph_contract_fingerprint": self.graph_contract_fingerprint,
            "graph_split_fingerprint": self.graph_split_fingerprint,
            "map_holdout_split_fingerprint": self.map_holdout_split_fingerprint,
            "normalization_fingerprint": self.normalization_fingerprint,
            "model_config_fingerprint": self.model_config_fingerprint,
            "graph_sample_count": self.graph_sample_count,
            "train_graph_count": self.train_graph_count,
            "validation_graph_count": self.validation_graph_count,
            "jax_runtime_warmup_wall_ns": self.jax_runtime_warmup_wall_ns,
            "xla_python_client_mem_fraction": self.xla_python_client_mem_fraction,
            "runs": [run.as_dict() for run in self.runs],
            "repeat_determinism": self.repeat_determinism.as_dict(),
            "validation_slice_metrics": [
                item.as_dict() for item in self.validation_slice_metrics
            ],
            "decision": self.decision.as_dict(),
            "runtime_nn_backend_authorized": self.runtime_nn_backend_authorized,
            "route_legality_changed": self.route_legality_changed,
            "raw_predictions_persisted": self.raw_predictions_persisted,
        }


def load_pr49_holdout_contract(
    artifact_path: str | Path,
    *,
    payload: Mapping[str, Any] | None = None,
) -> PR49HoldoutContract:
    if payload is None:
        resolved_payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    else:
        resolved_payload = dict(payload)
    if resolved_payload.get("evidence_status") != "diagnostic_not_validation":
        raise ValueError("PR49 artifact must remain diagnostic_not_validation")
    decision = resolved_payload.get("decision")
    if not isinstance(decision, Mapping) or decision.get("decision_state") != "relation_rejected":
        raise ValueError("PR49 artifact must report relation_rejected")
    if any(
        bool(decision.get(name, True))
        for name in (
            "raw_label_rows_persisted",
            "route_legality_changed",
            "row_local_mlp_probe_authorized",
            "runtime_nn_backend_authorized",
        )
    ):
        raise ValueError("PR49 artifact must not authorize or persist runtime output")
    holdout = resolved_payload.get("map_holdout")
    if not isinstance(holdout, Mapping):
        raise ValueError("PR49 artifact must contain map_holdout")
    train = tuple(str(value) for value in holdout.get("train_static_network_fingerprints", ()))
    validation = tuple(
        str(value)
        for value in holdout.get("validation_static_network_fingerprints", ())
    )
    held_out_seed = int(holdout.get("held_out_seed", -1))
    split_seed = int(holdout.get("split_seed", -1))
    supplied_fingerprint = str(holdout.get("split_fingerprint", ""))
    expected_fingerprint = compute_cost_to_go_map_holdout_fingerprint(
        train_static_network_fingerprints=train,
        validation_static_network_fingerprints=validation,
        held_out_seed=held_out_seed,
        split_seed=split_seed,
    )
    if supplied_fingerprint != expected_fingerprint:
        raise ValueError("PR49 map holdout fingerprint does not match its payload")
    return PR49HoldoutContract(
        split_seed=split_seed,
        held_out_seed=held_out_seed,
        train_static_network_fingerprints=train,
        validation_static_network_fingerprints=validation,
        split_fingerprint=expected_fingerprint,
    )


def evaluate_graph_bakeoff_decision(
    config: JaxGraphCostToGoBakeoffConfig,
    runs: tuple[GraphBakeoffSeedRun, ...],
    repeat_determinism: RepeatDeterminismAudit,
    *,
    corpus_provenance_valid: bool,
) -> GraphBakeoffDecision:
    expected_seeds = set(config.model_seeds)
    actual_seeds = [run.model_seed for run in runs]
    if len(runs) != len(expected_seeds) or set(actual_seeds) != expected_seeds:
        raise ValueError("runs must contain exactly one run per model seed")
    if len(set(actual_seeds)) != len(actual_seeds):
        raise ValueError("runs must contain exactly one run per model seed")
    if repeat_determinism.model_seed != config.repeat_model_seed:
        raise ValueError("repeat determinism seed must match repeat_model_seed")
    reasons: list[str] = []
    if not config.canonical_profile:
        reasons.append("noncanonical_profile")
    if type(corpus_provenance_valid) is not bool or not corpus_provenance_valid:
        reasons.append("corpus_provenance_failed")
    if any(
        metric.device_platform != "gpu"
        for run in runs
        for metric in (run.row_local, run.graph_aware)
    ):
        reasons.append("gpu_requirement_failed")
    if any(
        run.parameter_count_ratio > config.maximum_parameter_count_ratio
        for run in runs
    ):
        reasons.append("parameter_count_fairness_failed")
    repeat_passed = bool(
        repeat_determinism.passed
        and repeat_determinism.maximum_normalized_prediction_difference
        <= config.maximum_repeat_prediction_difference
        and repeat_determinism.normalized_mae_difference
        <= config.maximum_repeat_mae_difference
    )
    if not repeat_passed:
        reasons.append("repeat_determinism_failed")
    ratios = tuple(run.normalized_mae_ratio for run in runs)
    mean_ratio = float(mean(ratios))
    seed_pass_count = sum(
        ratio <= config.required_mean_mae_ratio for ratio in ratios
    )
    accuracy_gate_passed = bool(
        mean_ratio <= config.required_mean_mae_ratio
        and seed_pass_count >= config.required_seed_pass_count
    )
    if reasons:
        state = "inconclusive"
        supported = False
    elif accuracy_gate_passed:
        state = "graph_signal_supported"
        supported = True
    else:
        state = "graph_signal_not_supported"
        supported = False
    return GraphBakeoffDecision(
        decision_state=state,
        graph_signal_supported=supported,
        mean_normalized_mae_ratio=mean_ratio,
        seed_pass_count=seed_pass_count,
        accuracy_gate_passed=accuracy_gate_passed,
        inconclusive_reasons=tuple(reasons),
        runtime_nn_backend_authorized=False,
        route_legality_changed=False,
    )


def _validate_result_workload_and_slices(result: GraphBakeoffResult) -> None:
    config = result.config
    expected_validation_graphs = (
        len(config.style_ids) * 2 * config.destination_count
    )
    expected_train_graphs = expected_validation_graphs * (
        len(config.scenario_seeds) - 1
    )
    if (
        result.validation_graph_count != expected_validation_graphs
        or result.train_graph_count != expected_train_graphs
    ):
        raise ValueError("result graph counts do not match the configured workload")
    expected_identities = {
        (
            model_kind,
            model_seed,
            style_id,
            config.held_out_scenario_seed,
            dynamic_state,
            distance_label,
        )
        for model_kind in ("row_local", "graph_aware")
        for model_seed in config.model_seeds
        for style_id in config.style_ids
        for dynamic_state in ("free_flow", "stressed_closure")
        for distance_label, _lower, _upper in _DISTANCE_BINS
    }
    actual_identities = [
        (
            item.model_kind,
            item.model_seed,
            item.style_id,
            item.scenario_seed,
            item.dynamic_state,
            item.distance_bin,
        )
        for item in result.validation_slice_metrics
    ]
    if (
        len(actual_identities) != len(expected_identities)
        or len(set(actual_identities)) != len(actual_identities)
        or set(actual_identities) != expected_identities
    ):
        raise ValueError(
            "validation slices must cover each model, seed, map, state, and distance bin"
        )
    reference_counts: dict[tuple[str, str, str], int] = {}
    for item in result.validation_slice_metrics:
        slice_key = (item.style_id, item.dynamic_state, item.distance_bin)
        reference = reference_counts.setdefault(slice_key, item.valid_target_count)
        if item.valid_target_count != reference:
            raise ValueError("validation slice target counts must match across models")
    run_by_seed = {run.model_seed: run for run in result.runs}
    for model_seed in config.model_seeds:
        run = run_by_seed[model_seed]
        for model_kind, top_metric in (
            ("row_local", run.row_local),
            ("graph_aware", run.graph_aware),
        ):
            slices = tuple(
                item
                for item in result.validation_slice_metrics
                if item.model_seed == model_seed and item.model_kind == model_kind
            )
            total_count = sum(item.valid_target_count for item in slices)
            aggregate_values = {
                "validation_normalized_mae": sum(
                    item.normalized_mae * item.valid_target_count for item in slices
                )
                / total_count,
                "validation_normalized_rmse": math.sqrt(
                    sum(
                        item.normalized_rmse**2 * item.valid_target_count
                        for item in slices
                    )
                    / total_count
                ),
                "validation_raw_mae": sum(
                    item.raw_mae * item.valid_target_count for item in slices
                )
                / total_count,
                "validation_raw_rmse": math.sqrt(
                    sum(
                        item.raw_rmse**2 * item.valid_target_count
                        for item in slices
                    )
                    / total_count
                ),
            }
            for metric_name, aggregate_value in aggregate_values.items():
                if not math.isclose(
                    aggregate_value,
                    float(getattr(top_metric, metric_name)),
                    rel_tol=1.0e-6,
                    abs_tol=1.0e-7,
                ):
                    raise ValueError(
                        "validation slices do not reconstruct top-level model metrics"
                    )


def write_graph_bakeoff_artifacts(
    result: GraphBakeoffResult,
    output_dir: str | Path,
) -> dict[str, Path]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise ValueError("graph bakeoff output_dir must be empty")
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "jax-graph-cost-to-go-bakeoff.json"
    markdown_path = target / "jax-graph-cost-to-go-bakeoff.md"
    manifest_path = target / "manifest.json"
    json_path.write_text(
        json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(result), encoding="utf-8")
    manifest = {
        "artifact_files": [json_path.name, markdown_path.name],
        "artifact_format_version": "jax_graph_cost_to_go_bakeoff_bundle_v1",
        "data_json": json_path.name,
        "decision_state": result.decision.decision_state,
        "evidence_status": result.evidence_status,
        "graph_signal_supported": result.decision.graph_signal_supported,
        "accuracy_gate_passed": result.decision.accuracy_gate_passed,
        "graph_split_fingerprint": result.graph_split_fingerprint,
        "raw_predictions_persisted": False,
        "review_markdown": markdown_path.name,
        "route_legality_changed": False,
        "runtime_nn_backend_authorized": False,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": markdown_path, "manifest": manifest_path}


def _render_markdown(result: GraphBakeoffResult) -> str:
    lines = [
        "# JAX Graph Cost-To-Go Bakeoff",
        "",
        "Diagnostic experiment only. It does not authorize runtime NN routing.",
        "",
        f"- Decision: `{result.decision.decision_state}`",
        f"- Mean graph/control normalized-MAE ratio: {result.decision.mean_normalized_mae_ratio:.4f}",
        f"- Passing model seeds: {result.decision.seed_pass_count}/{len(result.runs)}",
        f"- Accuracy gate passed: {str(result.decision.accuracy_gate_passed).lower()}",
        f"- Repeat deterministic: {str(result.repeat_determinism.passed).lower()}",
        f"- Runtime NN backend authorized: {str(result.runtime_nn_backend_authorized).lower()}",
        "",
        "| Seed | Row-local MAE | Graph MAE | Ratio | Row params | Graph params |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for run in sorted(result.runs, key=lambda item: item.model_seed):
        lines.append(
            f"| {run.model_seed} | {run.row_local.validation_normalized_mae:.6g} | "
            f"{run.graph_aware.validation_normalized_mae:.6g} | "
            f"{run.normalized_mae_ratio:.4f} | {run.row_local.parameter_count} | "
            f"{run.graph_aware.parameter_count} |"
        )
    lines.extend(
        [
            "",
            "## Compact CCoT",
            "",
            "Question: Does directed graph context improve held-out-map cost-to-go prediction?",
            "Evidence: Fixed three-seed row-local and graph-aware JAX models on the exact PR49 holdout.",
            "Inference: The fixed MAE ratio and determinism gates decide only whether graph signal is supported.",
            "Counterevidence checked: No runtime replay, route legality, real-city data, or checkpoint integration is measured.",
            (
                f"Decision: {result.decision.decision_state}; the fixed graph "
                "accuracy hypothesis is not supported."
                if not result.decision.accuracy_gate_passed
                else f"Decision: {result.decision.decision_state}."
            ),
            "Falsifier: The graph model misses accuracy, provenance, GPU, parameter-fairness, or repeat gates.",
            (
                "Next action: Stop graph-NN tuning and require an owner-selected "
                "acceleration lane step-back."
                if not result.decision.accuracy_gate_passed
                else "Next action: Keep baseline Dijkstra authoritative; any follow-up requires a separate spec."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def run_jax_graph_cost_to_go_bakeoff(
    config: JaxGraphCostToGoBakeoffConfig,
    *,
    pr49_artifact_path: str | Path,
) -> GraphBakeoffResult:
    """Run the canonical optional-JAX experiment.

    The training implementation is defined below the result contracts so
    importing this module remains accelerator-lazy.
    """

    return _run_canonical_experiment(config, Path(pr49_artifact_path))


def _run_canonical_experiment(
    config: JaxGraphCostToGoBakeoffConfig,
    pr49_artifact_path: Path,
) -> GraphBakeoffResult:
    corpus = _build_canonical_corpus(config, pr49_artifact_path)
    prepared = _prepare_experiment_arrays(corpus)
    warmup_started = perf_counter_ns()
    jax, jnp, optax, device = _load_jax_stack(require_gpu=config.require_gpu)
    warmup_value = jax.device_put(jnp.ones((1,), dtype=jnp.float32)) + 1.0
    jax.block_until_ready(warmup_value)
    warmup_wall_ns = max(perf_counter_ns() - warmup_started, 1)
    device_data = {
        name: jax.device_put(value)
        for name, value in prepared.items()
    }
    jax.block_until_ready(device_data)
    train_indices = np.asarray(corpus.split.train_indices, dtype=np.int32)
    validation_indices = np.asarray(corpus.split.validation_indices, dtype=np.int32)
    if train_indices.size % config.graph_batch_size != 0:
        raise ValueError("canonical train graph count must divide graph_batch_size")
    runs: list[GraphBakeoffSeedRun] = []
    outputs: dict[tuple[str, int], _ModelTrainingOutput] = {}
    validation_slices: list[ValidationSliceMetric] = []
    for model_seed in config.model_seeds:
        row_output = _fit_jax_model(
            model_kind="row_local",
            model_seed=model_seed,
            config=config,
            jax=jax,
            jnp=jnp,
            optax=optax,
            device_data=device_data,
            train_indices=train_indices,
            validation_indices=validation_indices,
            device=device,
        )
        graph_output = _fit_jax_model(
            model_kind="graph_aware",
            model_seed=model_seed,
            config=config,
            jax=jax,
            jnp=jnp,
            optax=optax,
            device_data=device_data,
            train_indices=train_indices,
            validation_indices=validation_indices,
            device=device,
        )
        outputs[("row_local", model_seed)] = row_output
        outputs[("graph_aware", model_seed)] = graph_output
        runs.append(
            GraphBakeoffSeedRun(
                model_seed=model_seed,
                row_local=row_output.metric,
                graph_aware=graph_output.metric,
            )
        )
        validation_slices.extend(
            _validation_slice_metrics(
                corpus,
                validation_indices=validation_indices,
                model_kind="row_local",
                model_seed=model_seed,
                output=row_output,
            )
        )
        validation_slices.extend(
            _validation_slice_metrics(
                corpus,
                validation_indices=validation_indices,
                model_kind="graph_aware",
                model_seed=model_seed,
                output=graph_output,
            )
        )
    repeat_seed = config.repeat_model_seed
    repeated_row = _fit_jax_model(
        model_kind="row_local",
        model_seed=repeat_seed,
        config=config,
        jax=jax,
        jnp=jnp,
        optax=optax,
        device_data=device_data,
        train_indices=train_indices,
        validation_indices=validation_indices,
        device=device,
    )
    repeated_graph = _fit_jax_model(
        model_kind="graph_aware",
        model_seed=repeat_seed,
        config=config,
        jax=jax,
        jnp=jnp,
        optax=optax,
        device_data=device_data,
        train_indices=train_indices,
        validation_indices=validation_indices,
        device=device,
    )
    original_row = outputs[("row_local", repeat_seed)]
    original_graph = outputs[("graph_aware", repeat_seed)]
    prediction_difference = max(
        _masked_max_abs_diff(
            original_row.validation_normalized_predictions,
            repeated_row.validation_normalized_predictions,
            original_row.validation_target_mask,
        ),
        _masked_max_abs_diff(
            original_graph.validation_normalized_predictions,
            repeated_graph.validation_normalized_predictions,
            original_graph.validation_target_mask,
        ),
    )
    mae_difference = max(
        abs(
            original_row.metric.validation_normalized_mae
            - repeated_row.metric.validation_normalized_mae
        ),
        abs(
            original_graph.metric.validation_normalized_mae
            - repeated_graph.metric.validation_normalized_mae
        ),
    )
    repeat_audit = RepeatDeterminismAudit(
        model_seed=repeat_seed,
        maximum_normalized_prediction_difference=prediction_difference,
        normalized_mae_difference=mae_difference,
        passed=bool(
            prediction_difference <= config.maximum_repeat_prediction_difference
            and mae_difference <= config.maximum_repeat_mae_difference
        ),
    )
    ordered_runs = tuple(sorted(runs, key=lambda run: run.model_seed))
    decision = evaluate_graph_bakeoff_decision(
        config,
        ordered_runs,
        repeat_audit,
        corpus_provenance_valid=True,
    )
    model_config_fingerprint = _fingerprint_json(
        {
            "config": config.as_dict(),
            "graph_algorithm": "shared_reverse_edge_message_passing_v1",
            "validation_distance_bins": [
                [label, lower, upper] for label, lower, upper in _DISTANCE_BINS
            ],
            "row_local_algorithm": "four_hidden_layer_mlp_v1",
            "optimizer": "optax_adam",
            "target_transform": "log1p(cost_to_go / graph_max_travel_time)",
        }
    )
    return GraphBakeoffResult(
        config=config,
        runs=ordered_runs,
        repeat_determinism=repeat_audit,
        decision=decision,
        corpus_fingerprint=corpus.corpus_fingerprint,
        graph_contract_fingerprint=COST_TO_GO_GRAPH_CONTRACT_FINGERPRINT,
        graph_split_fingerprint=corpus.split.split_fingerprint,
        map_holdout_split_fingerprint=corpus.split.map_holdout_split_fingerprint,
        normalization_fingerprint=corpus.normalization_fingerprint,
        model_config_fingerprint=model_config_fingerprint,
        graph_sample_count=corpus.batch.batch_size,
        train_graph_count=int(train_indices.size),
        validation_graph_count=int(validation_indices.size),
        validation_slice_metrics=tuple(
            sorted(
                validation_slices,
                key=lambda item: (
                    item.model_seed,
                    item.model_kind,
                    item.style_id,
                    item.scenario_seed,
                    item.dynamic_state,
                ),
            )
        ),
        jax_runtime_warmup_wall_ns=warmup_wall_ns,
        xla_python_client_mem_fraction=str(
            os.environ.get("XLA_PYTHON_CLIENT_MEM_FRACTION", "")
        ),
    )


def _build_canonical_corpus(
    config: JaxGraphCostToGoBakeoffConfig,
    pr49_artifact_path: Path,
) -> _ExperimentCorpus:
    from metroflow.city.generator_v2 import GeneratorV2
    from metroflow.learning.cost_to_go_audit import (
        build_feature_audit_link_states,
        select_spatial_destination_node_ids,
    )

    payload = json.loads(pr49_artifact_path.read_text(encoding="utf-8"))
    holdout = load_pr49_holdout_contract(pr49_artifact_path, payload=payload)
    if holdout.held_out_seed != config.held_out_scenario_seed:
        raise ValueError("PR49 held-out scenario seed does not match bakeoff config")
    if holdout.split_seed != config.map_holdout_selection_seed:
        raise ValueError("PR49 holdout selection seed does not match bakeoff config")
    pr49_runs = tuple(payload.get("runs", ()))
    expected_static_by_pair = {
        (str(run["style_id"]), int(run["seed"])): str(
            run["static_network_fingerprint"]
        )
        for run in pr49_runs
    }
    expected_pairs = {
        (style_id, seed)
        for style_id in config.style_ids
        for seed in config.scenario_seeds
    }
    if set(expected_static_by_pair) != expected_pairs:
        raise ValueError("PR49 run matrix does not match graph bakeoff config")
    expected_run_by_pair = {
        (str(run["style_id"]), int(run["seed"])): run
        for run in pr49_runs
    }
    if (
        len(pr49_runs) != len(expected_pairs)
        or len(expected_run_by_pair) != len(expected_pairs)
    ):
        raise ValueError("PR49 run matrix contains duplicate map identities")
    sample_entries: list[tuple[CostToGoGraphSample, _GraphSampleDescriptor]] = []
    for style_id in config.style_ids:
        for scenario_seed in config.scenario_seeds:
            topology = GeneratorV2().generate_preview_topology(
                {
                    "scenario_id": "synthetic_smoke",
                    "seed": scenario_seed,
                    "preview_mode": "sidecar_local_fabric_planar",
                    "style_id": style_id,
                }
            )
            network = topology.build_csr(validate=None, require_weak_connectivity=True)
            destinations = select_spatial_destination_node_ids(
                network,
                destination_count=config.destination_count,
            )
            expected_run = expected_run_by_pair[(style_id, scenario_seed)]
            if tuple(int(value) for value in destinations) != tuple(
                int(value) for value in expected_run.get("destination_node_ids", ())
            ):
                raise ValueError("generated graph destinations do not match PR49")
            states = build_feature_audit_link_states(
                network,
                seed=scenario_seed,
                closure_fraction=config.closure_fraction,
            )
            observed_dynamic_fingerprints: set[str] = set()
            for dynamic_state in ("free_flow", "stressed_closure"):
                for destination_node_id in destinations:
                    sample = build_cost_to_go_graph_sample(
                        network,
                        states[dynamic_state],
                        destination_node_id=destination_node_id,
                    )
                    if sample.static_network_fingerprint != expected_static_by_pair[
                        (style_id, scenario_seed)
                    ]:
                        raise ValueError(
                            "generated graph static fingerprint does not match PR49"
                        )
                    if not bool(np.all(sample.target_mask)):
                        raise ValueError("canonical graph sample must retain every target row")
                    observed_dynamic_fingerprints.add(
                        sample.dynamic_state_fingerprint
                    )
                    sample_entries.append(
                        (
                            sample,
                            _GraphSampleDescriptor(
                                style_id=style_id,
                                scenario_seed=scenario_seed,
                                dynamic_state=dynamic_state,
                                destination_node_id=destination_node_id,
                                sample_fingerprint=sample.sample_fingerprint,
                                static_network_fingerprint=(
                                    sample.static_network_fingerprint
                                ),
                                dynamic_state_fingerprint=(
                                    sample.dynamic_state_fingerprint
                                ),
                            ),
                        )
                    )
            expected_dynamic_fingerprints = {
                str(value)
                for value in expected_run.get("dynamic_state_fingerprints", ())
            }
            if observed_dynamic_fingerprints != expected_dynamic_fingerprints:
                raise ValueError(
                    "generated graph dynamic fingerprints do not match PR49"
                )
    expected_sample_count = (
        len(config.style_ids)
        * len(config.scenario_seeds)
        * 2
        * config.destination_count
    )
    if len(sample_entries) != expected_sample_count:
        raise ValueError("canonical graph sample count is incomplete")
    raw_samples = tuple(sample for sample, _descriptor in sample_entries)
    split = split_cost_to_go_graph_samples(
        raw_samples,
        validation_static_network_fingerprints=(
            holdout.validation_static_network_fingerprints
        ),
        map_holdout_split_fingerprint=holdout.split_fingerprint,
        map_holdout_held_out_seed=holdout.held_out_seed,
        map_holdout_selection_seed=holdout.split_seed,
    )
    sample_by_fingerprint = {
        sample.sample_fingerprint: sample for sample in raw_samples
    }
    descriptor_by_fingerprint = {
        descriptor.sample_fingerprint: descriptor
        for _sample, descriptor in sample_entries
    }
    ordered_samples = tuple(
        sample_by_fingerprint[fingerprint]
        for fingerprint in split.sample_fingerprints
    )
    descriptors = tuple(
        descriptor_by_fingerprint[fingerprint]
        for fingerprint in split.sample_fingerprints
    )
    batch = build_cost_to_go_graph_batch(ordered_samples)
    if tuple(batch.sample_fingerprints) != tuple(split.sample_fingerprints):
        raise ValueError("graph batch order must match graph split order")
    train_indices = np.asarray(split.train_indices, dtype=np.int32)
    node_mean, node_std = _masked_feature_moments(
        batch.node_features[train_indices],
        batch.node_mask[train_indices],
    )
    edge_mean, edge_std = _masked_feature_moments(
        batch.edge_features[train_indices],
        batch.edge_mask[train_indices],
    )
    normalization_fingerprint = _fingerprint_json(
        {
            "edge_feature_mean": _array_digest(edge_mean),
            "edge_feature_std": _array_digest(edge_std),
            "node_feature_mean": _array_digest(node_mean),
            "node_feature_std": _array_digest(node_std),
            "source_partition": "train_static_networks_only",
            "split_fingerprint": split.split_fingerprint,
        }
    )
    corpus_fingerprint = _fingerprint_json(
        {
            "batch_fingerprint": batch.batch_fingerprint,
            "descriptors": [
                {
                    "destination_node_id": descriptor.destination_node_id,
                    "dynamic_state": descriptor.dynamic_state,
                    "dynamic_state_fingerprint": (
                        descriptor.dynamic_state_fingerprint
                    ),
                    "sample_fingerprint": descriptor.sample_fingerprint,
                    "scenario_seed": descriptor.scenario_seed,
                    "static_network_fingerprint": (
                        descriptor.static_network_fingerprint
                    ),
                    "style_id": descriptor.style_id,
                }
                for descriptor in descriptors
            ],
            "normalization_fingerprint": normalization_fingerprint,
            "split_fingerprint": split.split_fingerprint,
        }
    )
    return _ExperimentCorpus(
        batch=batch,
        split=split,
        descriptors=descriptors,
        node_feature_mean=node_mean,
        node_feature_std=node_std,
        edge_feature_mean=edge_mean,
        edge_feature_std=edge_std,
        corpus_fingerprint=corpus_fingerprint,
        normalization_fingerprint=normalization_fingerprint,
    )


def _masked_feature_moments(
    features: np.ndarray,
    mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(features, dtype=np.float64)
    resolved_mask = np.asarray(mask, dtype=np.bool_)
    selected = values[resolved_mask]
    if selected.ndim != 2 or selected.shape[0] < 1:
        raise ValueError("train feature normalization requires valid rows")
    feature_mean = np.asarray(np.mean(selected, axis=0), dtype=np.float32)
    feature_std = np.asarray(np.std(selected, axis=0), dtype=np.float32)
    feature_std = np.where(feature_std > 1.0e-6, feature_std, 1.0).astype(
        np.float32
    )
    return feature_mean, feature_std


def _stable_sort_edges_by_source_in_place(
    edge_index: np.ndarray,
    edge_features: np.ndarray,
    blocked_link_mask: np.ndarray,
    edge_counts: tuple[int, ...],
) -> None:
    for graph_index, edge_count in enumerate(edge_counts):
        count = int(edge_count)
        order = np.argsort(edge_index[graph_index, 0, :count], kind="stable")
        edge_index[graph_index, :, :count] = edge_index[
            graph_index,
            :,
            :count,
        ][:, order]
        edge_features[graph_index, :count] = edge_features[
            graph_index,
            :count,
        ][order]
        blocked_link_mask[graph_index, :count] = blocked_link_mask[
            graph_index,
            :count,
        ][order]


def _prepare_experiment_arrays(corpus: _ExperimentCorpus) -> dict[str, np.ndarray]:
    batch = corpus.batch
    node_mask = np.asarray(batch.node_mask, dtype=np.bool_)
    edge_mask = np.asarray(batch.edge_mask, dtype=np.bool_)
    edge_index = np.asarray(batch.edge_index, dtype=np.int32).copy()
    blocked_link_mask = np.asarray(batch.blocked_link_mask, dtype=np.bool_).copy()
    node_features = np.asarray(
        (batch.node_features - corpus.node_feature_mean)
        / corpus.node_feature_std,
        dtype=np.float32,
    )
    edge_features = np.asarray(
        (batch.edge_features - corpus.edge_feature_mean)
        / corpus.edge_feature_std,
        dtype=np.float32,
    )
    _stable_sort_edges_by_source_in_place(
        edge_index,
        edge_features,
        blocked_link_mask,
        batch.edge_counts,
    )
    node_features[np.logical_not(node_mask)] = 0.0
    edge_features[np.logical_not(edge_mask)] = 0.0
    scale_index = COST_TO_GO_FEATURE_NAMES.index(
        "global_max_travel_time_by_one_tick"
    )
    target_scale = np.asarray(batch.node_features[:, :, scale_index], dtype=np.float32)
    if bool(np.any(target_scale[node_mask] <= 0.0)):
        raise ValueError("graph target scale must be > 0 on real nodes")
    safe_scale = np.where(node_mask, target_scale, 1.0).astype(np.float32)
    distance_index = COST_TO_GO_FEATURE_NAMES.index(
        "euclidean_distance_by_spatial_diagonal"
    )
    distance_fraction = np.asarray(
        batch.node_features[:, :, distance_index],
        dtype=np.float32,
    ).copy()
    distance_fraction[np.logical_not(node_mask)] = 0.0
    target_normalized = np.asarray(batch.node_targets / safe_scale, dtype=np.float32)
    target_normalized[np.logical_not(batch.target_mask)] = 0.0
    target_log = np.asarray(np.log1p(target_normalized), dtype=np.float32)
    return {
        "blocked_link_mask": blocked_link_mask,
        "edge_features": edge_features,
        "edge_index": edge_index,
        "edge_mask": edge_mask,
        "distance_fraction": distance_fraction,
        "node_features": node_features,
        "node_mask": node_mask,
        "target_log": target_log,
        "target_mask": np.asarray(batch.target_mask, dtype=np.bool_),
        "target_normalized": target_normalized,
        "target_raw": np.asarray(batch.node_targets, dtype=np.float32),
        "target_scale": safe_scale,
    }


def _load_jax_stack(*, require_gpu: bool):
    try:
        import jax
        import jax.numpy as jnp
        import optax
    except ImportError as exc:
        raise RuntimeError(
            "JAX graph bakeoff unavailable; install the optional jax extra"
        ) from exc
    devices = tuple(jax.devices())
    if not devices:
        raise RuntimeError("JAX graph bakeoff unavailable; no JAX device found")
    device = devices[0]
    if require_gpu and str(device.platform) != "gpu":
        raise RuntimeError("JAX graph bakeoff requires a GPU device")
    return jax, jnp, optax, device


def _fit_jax_model(
    *,
    model_kind: str,
    model_seed: int,
    config: JaxGraphCostToGoBakeoffConfig,
    jax: Any,
    jnp: Any,
    optax: Any,
    device_data: Mapping[str, Any],
    train_indices: np.ndarray,
    validation_indices: np.ndarray,
    device: Any,
) -> _ModelTrainingOutput:
    params = _initialize_model_parameters(
        model_kind=model_kind,
        model_seed=model_seed,
        hidden_width=config.hidden_width,
        node_feature_count=int(device_data["node_features"].shape[-1]),
        edge_feature_count=int(device_data["edge_features"].shape[-1]),
        jax=jax,
        jnp=jnp,
    )
    optimizer = optax.adam(config.learning_rate)
    optimizer_state = optimizer.init(params)
    jax.block_until_ready((params, optimizer_state))

    def predict(selected_params, selected_data):
        if model_kind == "row_local":
            return _predict_row_local(selected_params, selected_data, jax=jax, jnp=jnp)
        return _predict_graph_aware(
            selected_params,
            selected_data,
            message_passing_steps=config.message_passing_steps,
            jax=jax,
            jnp=jnp,
        )

    def select(indices):
        return {
            name: jnp.take(values, indices, axis=0)
            for name, values in device_data.items()
        }

    def loss_function(selected_params, selected_data):
        prediction = predict(selected_params, selected_data)
        mask = selected_data["target_mask"].astype(jnp.float32)
        squared_error = jnp.square(prediction - selected_data["target_log"])
        return jnp.sum(squared_error * mask) / jnp.maximum(jnp.sum(mask), 1.0)

    def train_step(selected_params, selected_state, indices):
        selected_data = select(indices)
        loss, gradients = jax.value_and_grad(loss_function)(
            selected_params,
            selected_data,
        )
        updates, next_state = optimizer.update(
            gradients,
            selected_state,
            selected_params,
        )
        next_params = optax.apply_updates(selected_params, updates)
        return next_params, next_state, loss

    train_step_jit = jax.jit(train_step)
    inference_jit = jax.jit(
        lambda selected_params, indices: predict(selected_params, select(indices))
    )
    rng = np.random.default_rng(model_seed)
    step_batches: list[np.ndarray] = []
    for _epoch in range(config.epochs):
        permutation = rng.permutation(train_indices)
        step_batches.extend(
            np.asarray(
                permutation[start : start + config.graph_batch_size],
                dtype=np.int32,
            )
            for start in range(0, permutation.size, config.graph_batch_size)
        )
    step_timings: list[int] = []
    final_loss = None
    for batch_indices in step_batches:
        started = perf_counter_ns()
        params, optimizer_state, final_loss = train_step_jit(
            params,
            optimizer_state,
            jax.device_put(batch_indices),
        )
        jax.block_until_ready((params, optimizer_state, final_loss))
        step_timings.append(max(perf_counter_ns() - started, 1))
    if final_loss is None or len(step_timings) < 2:
        raise RuntimeError("graph bakeoff training produced no steady steps")
    validation_device_indices = jax.device_put(validation_indices)
    inference_started = perf_counter_ns()
    prediction_log = inference_jit(params, validation_device_indices)
    jax.block_until_ready(prediction_log)
    first_inference_wall_ns = max(perf_counter_ns() - inference_started, 1)
    inference_timings: list[int] = []
    for _ in range(5):
        started = perf_counter_ns()
        repeated_prediction = inference_jit(params, validation_device_indices)
        jax.block_until_ready(repeated_prediction)
        inference_timings.append(max(perf_counter_ns() - started, 1))
    prediction_log_host = np.asarray(jax.device_get(prediction_log), dtype=np.float32)
    prediction_normalized = np.asarray(
        np.expm1(np.clip(prediction_log_host, 0.0, 10.0)),
        dtype=np.float32,
    )
    target_normalized = np.asarray(
        jax.device_get(device_data["target_normalized"])[validation_indices],
        dtype=np.float32,
    )
    target_raw = np.asarray(
        jax.device_get(device_data["target_raw"])[validation_indices],
        dtype=np.float32,
    )
    target_scale = np.asarray(
        jax.device_get(device_data["target_scale"])[validation_indices],
        dtype=np.float32,
    )
    target_mask = np.asarray(
        jax.device_get(device_data["target_mask"])[validation_indices],
        dtype=np.bool_,
    )
    distance_fraction = np.asarray(
        jax.device_get(device_data["distance_fraction"])[validation_indices],
        dtype=np.float32,
    )
    prediction_raw = np.asarray(prediction_normalized * target_scale, dtype=np.float32)
    normalized_mae, normalized_rmse = _masked_error_metrics(
        prediction_normalized,
        target_normalized,
        target_mask,
    )
    raw_mae, raw_rmse = _masked_error_metrics(
        prediction_raw,
        target_raw,
        target_mask,
    )
    parameter_count = sum(
        int(np.asarray(leaf).size)
        for leaf in jax.tree_util.tree_leaves(params)
    )
    metric = ModelFitMetric(
        model_kind=model_kind,
        model_seed=model_seed,
        validation_normalized_mae=normalized_mae,
        validation_normalized_rmse=normalized_rmse,
        validation_raw_mae=raw_mae,
        validation_raw_rmse=raw_rmse,
        final_train_loss=float(np.asarray(jax.device_get(final_loss))),
        parameter_count=parameter_count,
        parameter_fingerprint=_parameter_fingerprint(params, jax=jax),
        first_train_step_wall_ns=step_timings[0],
        steady_train_step_median_wall_ns=int(median(step_timings[1:])),
        first_inference_wall_ns=first_inference_wall_ns,
        steady_inference_median_wall_ns=int(median(inference_timings)),
        device_platform=str(device.platform),
        device_kind=str(device.device_kind),
        jax_version=str(jax.__version__),
        optax_version=str(optax.__version__),
    )
    return _ModelTrainingOutput(
        metric=metric,
        validation_normalized_predictions=prediction_normalized,
        validation_normalized_targets=target_normalized,
        validation_raw_predictions=prediction_raw,
        validation_raw_targets=target_raw,
        validation_target_mask=target_mask,
        validation_distance_fraction=distance_fraction,
    )


def _initialize_model_parameters(
    *,
    model_kind: str,
    model_seed: int,
    hidden_width: int,
    node_feature_count: int,
    edge_feature_count: int,
    jax: Any,
    jnp: Any,
):
    key = jax.random.PRNGKey(model_seed)

    def dense(next_key, input_width: int, output_width: int):
        limit = math.sqrt(6.0 / max(input_width + output_width, 1))
        weights = jax.random.uniform(
            next_key,
            (input_width, output_width),
            minval=-limit,
            maxval=limit,
            dtype=jnp.float32,
        )
        bias = jnp.zeros((output_width,), dtype=jnp.float32)
        return {"weight": weights, "bias": bias}

    if model_kind == "row_local":
        widths = (node_feature_count, hidden_width, hidden_width, hidden_width, hidden_width, 1)
        keys = jax.random.split(key, len(widths) - 1)
        return tuple(
            dense(keys[index], widths[index], widths[index + 1])
            for index in range(len(widths) - 1)
        )
    if model_kind != "graph_aware":
        raise ValueError("model_kind must be row_local or graph_aware")
    keys = jax.random.split(key, 4)
    return {
        "encoder": dense(keys[0], node_feature_count, hidden_width),
        "message": dense(keys[1], hidden_width + edge_feature_count, hidden_width),
        "update": dense(keys[2], hidden_width * 2, hidden_width),
        "output": dense(keys[3], hidden_width, 1),
    }


def _dense(values, layer, *, jnp: Any):
    return jnp.matmul(values, layer["weight"]) + layer["bias"]


def _predict_row_local(params, data, *, jax: Any, jnp: Any):
    hidden = data["node_features"]
    for layer in params[:-1]:
        hidden = jax.nn.relu(_dense(hidden, layer, jnp=jnp))
    output = jax.nn.softplus(_dense(hidden, params[-1], jnp=jnp)[..., 0])
    return output * data["node_mask"].astype(jnp.float32)


def _predict_graph_aware(
    params,
    data,
    *,
    message_passing_steps: int,
    jax: Any,
    jnp: Any,
):
    hidden = jax.nn.relu(_dense(data["node_features"], params["encoder"], jnp=jnp))
    hidden = hidden * data["node_mask"][..., None].astype(jnp.float32)

    def update_one_graph(
        graph_hidden,
        edge_index,
        edge_features,
        blocked,
        node_mask,
        edge_mask,
    ):
        safe_source = jnp.where(
            edge_mask,
            edge_index[0],
            graph_hidden.shape[0] - 1,
        )
        safe_destination = jnp.where(edge_mask, edge_index[1], 0)
        message_input = jnp.concatenate(
            (graph_hidden[safe_destination], edge_features),
            axis=-1,
        )
        messages = jax.nn.relu(_dense(message_input, params["message"], jnp=jnp))
        valid_edge = edge_mask & jnp.logical_not(blocked)
        messages = messages * valid_edge[:, None].astype(jnp.float32)
        aggregate = jax.ops.segment_sum(
            messages,
            safe_source,
            num_segments=graph_hidden.shape[0],
            indices_are_sorted=True,
        )
        degree = jax.ops.segment_sum(
            valid_edge.astype(jnp.float32),
            safe_source,
            num_segments=graph_hidden.shape[0],
            indices_are_sorted=True,
        )
        aggregate = aggregate / jnp.maximum(degree[:, None], 1.0)
        next_hidden = jax.nn.relu(
            _dense(
                jnp.concatenate((graph_hidden, aggregate), axis=-1),
                params["update"],
                jnp=jnp,
            )
        )
        return next_hidden * node_mask[:, None].astype(jnp.float32)

    update_batch = jax.vmap(update_one_graph)

    def body(_index, current_hidden):
        return update_batch(
            current_hidden,
            data["edge_index"],
            data["edge_features"],
            data["blocked_link_mask"],
            data["node_mask"],
            data["edge_mask"],
        )

    hidden = jax.lax.fori_loop(0, message_passing_steps, body, hidden)
    output = jax.nn.softplus(_dense(hidden, params["output"], jnp=jnp)[..., 0])
    return output * data["node_mask"].astype(jnp.float32)


def _masked_error_metrics(
    predictions: np.ndarray,
    targets: np.ndarray,
    mask: np.ndarray,
) -> tuple[float, float]:
    selected = np.asarray(predictions - targets, dtype=np.float64)[
        np.asarray(mask, dtype=np.bool_)
    ]
    if selected.size < 1 or not np.isfinite(selected).all():
        raise ValueError("validation metrics require finite masked rows")
    return (
        float(np.mean(np.abs(selected), dtype=np.float64)),
        float(np.sqrt(np.mean(np.square(selected), dtype=np.float64))),
    )


def _masked_max_abs_diff(
    left: np.ndarray,
    right: np.ndarray,
    mask: np.ndarray,
) -> float:
    selected = np.abs(np.asarray(left, dtype=np.float64) - np.asarray(right, dtype=np.float64))[
        np.asarray(mask, dtype=np.bool_)
    ]
    return float(np.max(selected, initial=0.0))


def _validation_slice_metrics(
    corpus: _ExperimentCorpus,
    *,
    validation_indices: np.ndarray,
    model_kind: str,
    model_seed: int,
    output: _ModelTrainingOutput,
) -> tuple[ValidationSliceMetric, ...]:
    groups: dict[tuple[str, int, str], list[int]] = {}
    for local_index, graph_index in enumerate(validation_indices):
        descriptor = corpus.descriptors[int(graph_index)]
        groups.setdefault(
            (
                descriptor.style_id,
                descriptor.scenario_seed,
                descriptor.dynamic_state,
            ),
            [],
        ).append(local_index)
    metrics: list[ValidationSliceMetric] = []
    for (style_id, scenario_seed, dynamic_state), local_indices in sorted(groups.items()):
        selected = np.asarray(local_indices, dtype=np.int32)
        group_target_mask = output.validation_target_mask[selected]
        group_distances = output.validation_distance_fraction[selected]
        for distance_label, lower, upper in _DISTANCE_BINS:
            selected_mask = np.asarray(
                group_target_mask
                & (group_distances >= lower)
                & (group_distances < upper),
                dtype=np.bool_,
            )
            valid_target_count = int(np.count_nonzero(selected_mask))
            if valid_target_count < 1:
                continue
            normalized_mae, normalized_rmse = _masked_error_metrics(
                output.validation_normalized_predictions[selected],
                output.validation_normalized_targets[selected],
                selected_mask,
            )
            raw_mae, raw_rmse = _masked_error_metrics(
                output.validation_raw_predictions[selected],
                output.validation_raw_targets[selected],
                selected_mask,
            )
            metrics.append(
                ValidationSliceMetric(
                    model_kind=model_kind,
                    model_seed=model_seed,
                    style_id=style_id,
                    scenario_seed=scenario_seed,
                    dynamic_state=dynamic_state,
                    distance_bin=distance_label,
                    valid_target_count=valid_target_count,
                    normalized_mae=normalized_mae,
                    normalized_rmse=normalized_rmse,
                    raw_mae=raw_mae,
                    raw_rmse=raw_rmse,
                )
            )
    return tuple(metrics)


def _parameter_fingerprint(params, *, jax: Any) -> str:
    hasher = hashlib.sha256()
    for leaf in jax.tree_util.tree_leaves(params):
        array = np.ascontiguousarray(jax.device_get(leaf))
        hasher.update(str(array.dtype).encode("ascii"))
        hasher.update(str(tuple(array.shape)).encode("ascii"))
        hasher.update(memoryview(array).cast("B"))
    return hasher.hexdigest()


def _array_digest(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    hasher = hashlib.sha256()
    hasher.update(str(array.dtype).encode("ascii"))
    hasher.update(str(tuple(array.shape)).encode("ascii"))
    hasher.update(memoryview(array).cast("B"))
    return hasher.hexdigest()


def _require_sha256(value: Any, *, name: str) -> str:
    resolved = str(value).strip().lower()
    if len(resolved) != 64 or any(character not in "0123456789abcdef" for character in resolved):
        raise ValueError(f"{name} must be a 64-character hexadecimal fingerprint")
    return resolved


def _fingerprint_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--pr49-artifact",
        default="artifacts/cost_to_go_feature_audit_20260711/cost-to-go-feature-audit.json",
    )
    args = parser.parse_args()
    result = run_jax_graph_cost_to_go_bakeoff(
        JaxGraphCostToGoBakeoffConfig(),
        pr49_artifact_path=args.pr49_artifact,
    )
    paths = write_graph_bakeoff_artifacts(result, args.output_dir)
    print(json.dumps({key: str(value) for key, value in paths.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
