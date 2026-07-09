"""Disruption-aware reroute trigger policy (US2/T051)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

import numpy as np

from metroflow.backends.rust_cpu import (
    compute_reroute_decision_rust,
    rust_reroute_backend_available,
)
from metroflow.routing.behavior_profiles import RouteChoiceProfile

__all__ = [
    "RerouteDecisionReason",
    "RerouteDecision",
    "compute_reroute_trigger_score_core",
    "compute_reroute_decision_core",
    "compute_reroute_trigger_score",
    "decide_reroute_vs_persist",
]


class RerouteDecisionReason(str, Enum):
    """Deterministic baseline reasons for reroute/persist decisions."""

    REROUTE = "reroute"
    NO_INCIDENT = "no_incident"
    COOLDOWN = "cooldown"
    INVALID_COSTS = "invalid_costs"
    INSUFFICIENT_IMPROVEMENT = "insufficient_improvement"
    PERSISTENCE = "persistence"


@dataclass(slots=True)
class RerouteDecision:
    """Reroute-vs-persist decision payload for US2 step integration."""

    should_reroute: bool
    reason: RerouteDecisionReason
    improvement_ratio: float
    trigger_score: float
    next_reroute_cooldown_ticks: int

    def __post_init__(self) -> None:
        self.should_reroute = bool(self.should_reroute)
        self.reason = (
            self.reason if isinstance(self.reason, RerouteDecisionReason) else RerouteDecisionReason(self.reason)
        )
        self.improvement_ratio = float(self.improvement_ratio)
        self.trigger_score = float(self.trigger_score)
        self.next_reroute_cooldown_ticks = int(self.next_reroute_cooldown_ticks)
        if self.next_reroute_cooldown_ticks < 0:
            raise ValueError("next_reroute_cooldown_ticks must be >= 0")


def decide_reroute_vs_persist(
    *,
    profile: RouteChoiceProfile | Mapping[str, Any],
    current_remaining_cost: float,
    candidate_remaining_cost: float,
    incident_active: bool = True,
    reroute_cooldown_ticks: int = 0,
    min_improvement_ratio: float = 0.05,
    cooldown_after_reroute_ticks: int = 3,
    decay_cooldown_when_no_incident: bool = False,
    routing_backend: str = "baseline",
) -> RerouteDecision:
    """Decide whether an affected traveler reroutes or persists this tick.

    The policy is deterministic and profile-driven, using:
    - route-cost improvement ratio
    - reroute willingness / delay sensitivity / persistence bias
    - reroute cooldown gating
    """

    p = _coerce_profile(profile)
    cooldown = int(reroute_cooldown_ticks)
    if cooldown < 0:
        raise ValueError("reroute_cooldown_ticks must be >= 0")
    min_improvement = max(0.0, float(min_improvement_ratio))
    cooldown_after = max(0, int(cooldown_after_reroute_ticks))

    if not incident_active:
        return RerouteDecision(
            should_reroute=False,
            reason=RerouteDecisionReason.NO_INCIDENT,
            improvement_ratio=0.0,
            trigger_score=0.0,
            next_reroute_cooldown_ticks=(max(0, cooldown - 1) if decay_cooldown_when_no_incident else cooldown),
        )
    if cooldown > 0:
        return RerouteDecision(
            should_reroute=False,
            reason=RerouteDecisionReason.COOLDOWN,
            improvement_ratio=0.0,
            trigger_score=0.0,
            next_reroute_cooldown_ticks=cooldown - 1,
        )

    current_cost = float(current_remaining_cost)
    candidate_cost = float(candidate_remaining_cost)
    if (
        not math.isfinite(current_cost)
        or not math.isfinite(candidate_cost)
        or current_cost <= 0.0
        or candidate_cost <= 0.0
    ):
        return RerouteDecision(
            should_reroute=False,
            reason=RerouteDecisionReason.INVALID_COSTS,
            improvement_ratio=0.0,
            trigger_score=0.0,
            next_reroute_cooldown_ticks=0,
        )

    improvement_ratio = max(0.0, (current_cost - candidate_cost) / max(current_cost, 1e-6))
    if improvement_ratio < min_improvement:
        return RerouteDecision(
            should_reroute=False,
            reason=RerouteDecisionReason.INSUFFICIENT_IMPROVEMENT,
            improvement_ratio=improvement_ratio,
            trigger_score=0.0,
            next_reroute_cooldown_ticks=0,
        )

    resistance = _persistence_resistance(p)
    should_reroute_arr, trigger_score_arr = compute_reroute_decision_core(
        reroute_willingness=float(p.reroute_willingness),
        delay_sensitivity=float(p.delay_sensitivity),
        exploration_bias=float(p.exploration_bias),
        persistence_bias=float(p.persistence_bias),
        improvement_ratio=float(improvement_ratio),
        routing_backend=routing_backend,
    )
    trigger_score = float(trigger_score_arr)
    should_reroute = bool(
        bool(should_reroute_arr) and trigger_score >= resistance and p.reroute_willingness > 0.0
    )
    return RerouteDecision(
        should_reroute=should_reroute,
        reason=RerouteDecisionReason.REROUTE if should_reroute else RerouteDecisionReason.PERSISTENCE,
        improvement_ratio=improvement_ratio,
        trigger_score=trigger_score,
        next_reroute_cooldown_ticks=(cooldown_after if should_reroute else 0),
    )


def compute_reroute_trigger_score_core(
    *,
    reroute_willingness: Any,
    delay_sensitivity: Any,
    exploration_bias: Any,
    improvement_ratio: Any,
) -> np.ndarray:
    """Array-friendly trigger-score core for future batched evaluation."""

    reroute = np.clip(np.asarray(reroute_willingness, dtype=np.float32), 0.0, 1.0)
    delay = np.asarray(delay_sensitivity, dtype=np.float32)
    explore = np.clip(np.asarray(exploration_bias, dtype=np.float32), 0.0, 1.0)
    improvement = np.maximum(0.0, np.asarray(improvement_ratio, dtype=np.float32))
    delay_norm = np.where(delay > 0.0, delay / (1.0 + delay), 0.0)
    return (
        0.45 * reroute
        + 0.35 * np.minimum(1.0, improvement * (0.75 + 0.75 * delay_norm))
        + 0.20 * explore
    )


def compute_reroute_decision_core(
    *,
    reroute_willingness: Any,
    delay_sensitivity: Any,
    exploration_bias: Any,
    persistence_bias: Any,
    improvement_ratio: Any,
    routing_backend: str = "baseline",
) -> tuple[np.ndarray, np.ndarray]:
    """Array-core boundary used by the host wrapper (`decide_reroute_vs_persist`)."""

    if routing_backend not in {"baseline", "rust_cpu", "auto"}:
        raise ValueError("routing_backend must be one of: baseline, rust_cpu, auto")
    if routing_backend == "auto" and not rust_reroute_backend_available():
        return _compute_reroute_decision_core_baseline(
            reroute_willingness=reroute_willingness,
            delay_sensitivity=delay_sensitivity,
            exploration_bias=exploration_bias,
            persistence_bias=persistence_bias,
            improvement_ratio=improvement_ratio,
        )
    if routing_backend in {"rust_cpu", "auto"}:
        try:
            return compute_reroute_decision_rust(
                reroute_willingness=reroute_willingness,
                delay_sensitivity=delay_sensitivity,
                exploration_bias=exploration_bias,
                persistence_bias=persistence_bias,
                improvement_ratio=improvement_ratio,
            )
        except RuntimeError:
            if routing_backend == "rust_cpu":
                raise
    return _compute_reroute_decision_core_baseline(
        reroute_willingness=reroute_willingness,
        delay_sensitivity=delay_sensitivity,
        exploration_bias=exploration_bias,
        persistence_bias=persistence_bias,
        improvement_ratio=improvement_ratio,
    )


def _compute_reroute_decision_core_baseline(
    *,
    reroute_willingness: Any,
    delay_sensitivity: Any,
    exploration_bias: Any,
    persistence_bias: Any,
    improvement_ratio: Any,
) -> tuple[np.ndarray, np.ndarray]:
    score = compute_reroute_trigger_score_core(
        reroute_willingness=reroute_willingness,
        delay_sensitivity=delay_sensitivity,
        exploration_bias=exploration_bias,
        improvement_ratio=improvement_ratio,
    )
    persist = np.asarray(persistence_bias, dtype=np.float32)
    resistance = 0.40 + 0.15 * np.where(np.abs(persist) > 0.0, np.abs(persist) / (1.0 + np.abs(persist)), 0.0)
    should = np.logical_and(score >= resistance, np.asarray(reroute_willingness, dtype=np.float32) > 0.0)
    return should, score


def compute_reroute_trigger_score(
    *,
    profile: RouteChoiceProfile | Mapping[str, Any],
    improvement_ratio: float,
) -> float:
    """Compute deterministic reroute trigger score from profile + improvement."""

    p = _coerce_profile(profile)
    raw_improvement = float(improvement_ratio)
    if not math.isfinite(raw_improvement):
        raise ValueError("improvement_ratio must be finite")
    return float(
        compute_reroute_trigger_score_core(
            reroute_willingness=float(p.reroute_willingness),
            delay_sensitivity=float(p.delay_sensitivity),
            exploration_bias=float(p.exploration_bias),
            improvement_ratio=max(0.0, raw_improvement),
        )
    )


def _persistence_resistance(profile: RouteChoiceProfile) -> float:
    bias = float(profile.persistence_bias)
    if not math.isfinite(bias):
        raise ValueError("persistence_bias must be finite")
    # Bias is intentionally only weakly normalized because data-model semantics
    # don't fix a strict range yet.
    bias_component = 0.15 * _squash_positive(abs(bias))
    return float(0.40 + bias_component)


def _squash_positive(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("profile numeric fields must be finite")
    if value <= 0.0:
        return 0.0
    return float(value / (1.0 + value))


def _coerce_profile(profile: RouteChoiceProfile | Mapping[str, Any]) -> RouteChoiceProfile:
    if isinstance(profile, RouteChoiceProfile):
        out = profile
    else:
        out = RouteChoiceProfile(**dict(profile))
    _validate_profile_finite_fields(out)
    return out


def _validate_profile_finite_fields(profile: RouteChoiceProfile) -> None:
    values = (
        float(profile.delay_sensitivity),
        float(profile.reroute_willingness),
        float(profile.persistence_bias),
        float(profile.exploration_bias),
    )
    if not all(math.isfinite(v) for v in values):
        raise ValueError("profile numeric fields must be finite")
