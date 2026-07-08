"""Baseline/adaptive policy blend controller skeleton."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

import numpy as np

from metroflow.sim.config import LearningMixBounds

__all__ = [
    "PolicyBlendFallbackReason",
    "PolicyBlendState",
    "blend_route_scores",
    "compute_policy_mix_lambda",
    "apply_policy_blend_control",
    "fallback_to_baseline",
]

Array = np.ndarray


class PolicyBlendFallbackReason(str, Enum):
    """Fallback reason enum aligned with the phase-1 data model."""

    INSTABILITY = "instability"
    NO_SIGNAL = "no_signal"
    INVALID_OUTPUT = "invalid_output"
    INCIDENT_MODE = "incident_mode"


@dataclass(slots=True)
class PolicyBlendState:
    """State for baseline/adaptive score blending and fallback tracking."""

    lambda_mix: float = 0.0
    fallback_triggered: bool = False
    fallback_reason: PolicyBlendFallbackReason | None = None
    baseline_only_mode: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.lambda_mix = float(self.lambda_mix)
        self.fallback_triggered = bool(self.fallback_triggered)
        if self.fallback_reason is not None and not isinstance(
            self.fallback_reason,
            PolicyBlendFallbackReason,
        ):
            self.fallback_reason = PolicyBlendFallbackReason(self.fallback_reason)
        self.baseline_only_mode = bool(self.baseline_only_mode)
        if not 0.0 <= self.lambda_mix <= 1.0:
            raise ValueError("lambda_mix must be in [0, 1]")
        if not isinstance(self.metadata, dict):
            self.metadata = dict(self.metadata)

    @property
    def adaptive_enabled(self) -> bool:
        return not self.baseline_only_mode and self.lambda_mix > 0.0

    def with_lambda(
        self,
        lambda_mix: float,
        *,
        bounds: LearningMixBounds | None = None,
    ) -> "PolicyBlendState":
        """Return state with a clipped mix coefficient and cleared fallback flag."""

        next_lambda = float(lambda_mix)
        if bounds is not None:
            next_lambda = compute_policy_mix_lambda(next_lambda, bounds=bounds)
        else:
            next_lambda = min(1.0, max(0.0, next_lambda))
        return replace(
            self,
            lambda_mix=next_lambda,
            baseline_only_mode=next_lambda <= 0.0,
            fallback_triggered=False,
            fallback_reason=None,
        )


def compute_policy_mix_lambda(
    target_lambda: float,
    *,
    bounds: LearningMixBounds,
    learning_enabled: bool = True,
) -> float:
    """Compute/clamp the effective blend coefficient from config bounds."""

    if not learning_enabled:
        return 0.0
    target = float(target_lambda)
    clipped = min(bounds.lambda_max, max(bounds.lambda_min, target))
    return float(min(1.0, max(0.0, clipped)))


def apply_policy_blend_control(
    state: PolicyBlendState,
    *,
    target_lambda: float | None = None,
    bounds: LearningMixBounds | None = None,
    learning_enabled: bool = True,
    incident_mode: bool = False,
    adaptive_signal_available: bool = True,
    adaptive_output_valid: bool = True,
) -> PolicyBlendState:
    """Update `PolicyBlendState` for this tick before route-score blending.

    This controller is intentionally conservative in the foundational phase:
    fallback conditions force baseline-only routing for the tick and record a
    reason that can be surfaced in telemetry.
    """

    next_state = state
    if target_lambda is not None:
        if bounds is None:
            next_state = next_state.with_lambda(float(target_lambda))
        else:
            next_state = replace(
                next_state,
                lambda_mix=compute_policy_mix_lambda(
                    float(target_lambda),
                    bounds=bounds,
                    learning_enabled=learning_enabled,
                ),
                baseline_only_mode=not learning_enabled,
                fallback_triggered=False,
                fallback_reason=None,
            )
            if next_state.lambda_mix <= 0.0:
                next_state = replace(next_state, baseline_only_mode=True)
            elif learning_enabled:
                next_state = replace(next_state, baseline_only_mode=False)

    if not learning_enabled:
        return fallback_to_baseline(next_state, PolicyBlendFallbackReason.NO_SIGNAL, lambda_mix=0.0)
    if incident_mode:
        return fallback_to_baseline(next_state, PolicyBlendFallbackReason.INCIDENT_MODE)
    if not adaptive_signal_available:
        return fallback_to_baseline(next_state, PolicyBlendFallbackReason.NO_SIGNAL)
    if not adaptive_output_valid:
        return fallback_to_baseline(next_state, PolicyBlendFallbackReason.INVALID_OUTPUT)
    return replace(next_state, fallback_triggered=False, fallback_reason=None)


def fallback_to_baseline(
    state: PolicyBlendState,
    reason: PolicyBlendFallbackReason,
    *,
    lambda_mix: float | None = None,
) -> PolicyBlendState:
    """Return a baseline-only state and record fallback reason."""

    next_lambda = state.lambda_mix if lambda_mix is None else float(lambda_mix)
    next_lambda = min(1.0, max(0.0, next_lambda))
    if lambda_mix is None:
        # Preserve the configured mix for telemetry while forcing baseline use.
        next_lambda = state.lambda_mix
    return replace(
        state,
        lambda_mix=next_lambda,
        fallback_triggered=True,
        fallback_reason=PolicyBlendFallbackReason(reason),
        baseline_only_mode=True,
    )


def blend_route_scores(
    baseline_scores: Array | Any,
    adaptive_scores: Array | Any | None,
    blend_state: PolicyBlendState,
) -> Array:
    """Blend baseline/adaptive route scores with safe baseline fallback behavior.

    If adaptive scores are unavailable or invalid for blending, baseline scores
    are returned unchanged. Callers should use `apply_policy_blend_control(...)`
    to update `blend_state` and record the fallback reason before invoking this.
    """

    baseline = np.asarray(baseline_scores, dtype=np.float32)
    if adaptive_scores is None or blend_state.baseline_only_mode or blend_state.lambda_mix <= 0.0:
        return baseline

    adaptive = np.asarray(adaptive_scores, dtype=np.float32)
    if adaptive.shape != baseline.shape:
        return baseline
    if bool(np.any(~np.isfinite(adaptive))):
        return baseline

    lam = np.asarray(blend_state.lambda_mix, dtype=np.float32)
    return (1.0 - lam) * baseline + lam * adaptive
