"""Optional experiment harness for route-score surrogate work.

This module is deliberately outside runtime authority. It consumes simulator
labels and records fallback metadata for experiments; route legality remains
owned by baseline/Rust routing code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Literal, Sequence

import numpy as np

from metroflow.learning.labels import SimulatorLabelRecord

__all__ = [
    "RouteSurrogateExperimentConfig",
    "RouteSurrogateModel",
    "RouteSurrogateFitResult",
    "RouteSurrogatePrediction",
    "fit_route_surrogate_experiment",
    "predict_route_surrogate_scores",
]

SurrogateBackend = Literal["baseline_numpy", "torch_optional"]
RUNTIME_AUTHORITY = "baseline_fallback_only"


@dataclass(frozen=True)
class RouteSurrogateExperimentConfig:
    """Configuration for experiment-only route surrogate fitting."""

    backend: SurrogateBackend = "baseline_numpy"
    model_version: str = "route_surrogate_v0"
    fallback_to_baseline: bool = True

    def __post_init__(self) -> None:
        if self.backend not in {"baseline_numpy", "torch_optional"}:
            raise ValueError("backend must be one of: baseline_numpy, torch_optional")
        model_version = str(self.model_version).strip()
        if not model_version:
            raise ValueError("model_version must be non-empty")
        object.__setattr__(self, "model_version", model_version)
        object.__setattr__(self, "fallback_to_baseline", bool(self.fallback_to_baseline))


@dataclass(frozen=True)
class RouteSurrogateModel:
    """Small deterministic route-score summary model."""

    model_family: str
    model_version: str
    backend_actual: str
    mean_route_score_by_rank: tuple[float, ...]
    selected_candidate_prior: tuple[float, ...]
    label_fingerprints: tuple[str, ...]
    runtime_authority: str = RUNTIME_AUTHORITY
    metadata: dict[str, Any] = field(default_factory=dict)
    model_fingerprint: str = ""

    def __post_init__(self) -> None:
        scores = tuple(float(value) for value in self.mean_route_score_by_rank)
        priors = tuple(float(value) for value in self.selected_candidate_prior)
        if not scores:
            raise ValueError("mean_route_score_by_rank must be non-empty")
        if len(priors) != len(scores):
            raise ValueError("selected_candidate_prior must match score length")
        if any(not np.isfinite(value) for value in (*scores, *priors)):
            raise ValueError("surrogate model numeric values must be finite")
        label_fingerprints = tuple(str(item) for item in self.label_fingerprints)
        metadata = dict(self.metadata)
        object.__setattr__(self, "model_family", str(self.model_family))
        object.__setattr__(self, "model_version", str(self.model_version))
        object.__setattr__(self, "backend_actual", str(self.backend_actual))
        object.__setattr__(self, "mean_route_score_by_rank", scores)
        object.__setattr__(self, "selected_candidate_prior", priors)
        object.__setattr__(self, "label_fingerprints", label_fingerprints)
        object.__setattr__(self, "runtime_authority", str(self.runtime_authority))
        object.__setattr__(self, "metadata", metadata)
        fingerprint = str(self.model_fingerprint).strip()
        if not fingerprint:
            fingerprint = _fingerprint_json(
                {
                    "model_family": self.model_family,
                    "model_version": self.model_version,
                    "backend_actual": self.backend_actual,
                    "mean_route_score_by_rank": scores,
                    "selected_candidate_prior": priors,
                    "label_fingerprints": label_fingerprints,
                    "runtime_authority": self.runtime_authority,
                    "metadata": metadata,
                }
            )
        object.__setattr__(self, "model_fingerprint", fingerprint)


@dataclass(frozen=True)
class RouteSurrogateFitResult:
    """Fit result plus provenance/fallback metadata."""

    model: RouteSurrogateModel
    backend_requested: str
    backend_actual: str
    backend_fallback: str | None
    model_family: str
    model_version: str
    label_count: int
    feature_count: int
    model_fingerprint: str
    label_fingerprint: str
    runtime_authority: str = RUNTIME_AUTHORITY
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RouteSurrogatePrediction:
    """Experiment-only route score prediction payload."""

    predicted_route_score_values: tuple[float, ...]
    selected_candidate_index: int
    backend_actual: str
    model_fingerprint: str
    runtime_authority: str = RUNTIME_AUTHORITY
    metadata: dict[str, Any] = field(default_factory=dict)


def fit_route_surrogate_experiment(
    records: Sequence[SimulatorLabelRecord],
    *,
    config: RouteSurrogateExperimentConfig | None = None,
) -> RouteSurrogateFitResult:
    """Fit an experiment-only route score surrogate from simulator labels."""

    cfg = config or RouteSurrogateExperimentConfig()
    route_records = _route_scoring_records(records)
    label_fingerprints = tuple(record.fingerprint for record in route_records)
    backend_actual = "baseline_numpy"
    fallback: str | None = None
    torch_probe_available = False
    model_family = "numpy_route_score_mean"
    if cfg.backend == "torch_optional":
        try:
            _fit_torch_route_score_summary(route_records)
            fallback = "torch_probe_only"
            torch_probe_available = True
        except ModuleNotFoundError:
            if not cfg.fallback_to_baseline:
                raise
            fallback = "torch_unavailable"
        except Exception:
            if not cfg.fallback_to_baseline:
                raise
            fallback = "torch_failed"

    scores, priors = _fit_numpy_route_score_summary(route_records)
    model = RouteSurrogateModel(
        model_family=model_family,
        model_version=cfg.model_version,
        backend_actual=backend_actual,
        mean_route_score_by_rank=scores,
        selected_candidate_prior=priors,
        label_fingerprints=label_fingerprints,
        metadata={
            "label_kind": "route_scoring",
            "runtime_authority": RUNTIME_AUTHORITY,
        },
    )
    return RouteSurrogateFitResult(
        model=model,
        backend_requested=cfg.backend,
        backend_actual=backend_actual,
        backend_fallback=fallback,
        model_family=model.model_family,
        model_version=model.model_version,
        label_count=len(route_records),
        feature_count=len(model.mean_route_score_by_rank),
        model_fingerprint=model.model_fingerprint,
        label_fingerprint=_fingerprint_json(label_fingerprints),
        runtime_authority=RUNTIME_AUTHORITY,
        metadata={
            "fallback_to_baseline": bool(cfg.fallback_to_baseline),
            "route_legality_authority": "baseline_routing",
            "torch_probe_available": bool(torch_probe_available),
        },
    )


def predict_route_surrogate_scores(
    model: RouteSurrogateModel,
    record: SimulatorLabelRecord,
) -> RouteSurrogatePrediction:
    """Predict route scores for a route-scoring label record."""

    if record.label_kind != "route_scoring":
        raise ValueError("record must be a route_scoring label")
    candidate_count = len(tuple(record.features.get("candidate_paths", ()) or ()))
    if candidate_count < 1:
        raise ValueError("record must contain at least one candidate path")
    scores = tuple(model.mean_route_score_by_rank[:candidate_count])
    if len(scores) < candidate_count:
        pad_value = scores[-1] if scores else 0.0
        scores = scores + (pad_value,) * (candidate_count - len(scores))
    selected_index = int(np.argmax(np.asarray(scores, dtype=np.float32)))
    return RouteSurrogatePrediction(
        predicted_route_score_values=tuple(float(value) for value in scores),
        selected_candidate_index=selected_index,
        backend_actual=model.backend_actual,
        model_fingerprint=model.model_fingerprint,
        runtime_authority=RUNTIME_AUTHORITY,
        metadata={"route_legality_authority": "baseline_routing"},
    )


def _route_scoring_records(
    records: Sequence[SimulatorLabelRecord],
) -> tuple[SimulatorLabelRecord, ...]:
    route_records = tuple(record for record in records if record.label_kind == "route_scoring")
    if not route_records:
        raise ValueError("records must contain at least one route_scoring label")
    return route_records


def _fit_numpy_route_score_summary(
    records: tuple[SimulatorLabelRecord, ...],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    max_len = max(len(tuple(record.labels.get("route_score_values", ()) or ())) for record in records)
    if max_len < 1:
        raise ValueError("route_scoring labels must contain route_score_values")
    score_sums = np.zeros((max_len,), dtype=np.float64)
    score_counts = np.zeros((max_len,), dtype=np.float64)
    selected_counts = np.zeros((max_len,), dtype=np.float64)
    for record in records:
        scores = tuple(float(value) for value in tuple(record.labels["route_score_values"]))
        selected = int(record.labels["selected_candidate_index"])
        for idx, value in enumerate(scores):
            score_sums[idx] += float(value)
            score_counts[idx] += 1.0
        if 0 <= selected < max_len:
            selected_counts[selected] += 1.0
    means = np.divide(
        score_sums,
        np.maximum(score_counts, 1.0),
        out=np.zeros_like(score_sums),
    )
    priors = selected_counts / max(float(len(records)), 1.0)
    return (
        tuple(float(value) for value in means.astype(np.float32)),
        tuple(float(value) for value in priors.astype(np.float32)),
    )


def _fit_torch_route_score_summary(records: tuple[SimulatorLabelRecord, ...]) -> None:
    torch = _import_torch()
    rows = [
        [float(value) for value in tuple(record.labels["route_score_values"])]
        for record in records
    ]
    max_len = max(len(row) for row in rows)
    padded = [row + [row[-1]] * (max_len - len(row)) for row in rows]
    tensor = torch.as_tensor(padded, dtype=torch.float32, device="cpu")
    _ = torch.mean(tensor, dim=0)


def _import_torch():
    import torch

    return torch


def _fingerprint_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    ).hexdigest()
