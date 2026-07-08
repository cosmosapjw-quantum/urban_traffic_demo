from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GateThresholds:
    """Canonical blocker thresholds derived from spec SC-001/SC-006/SC-011."""

    hard_fail_rate_max: float = 0.02
    ring_radial_connectivity_min: float = 0.95
    incident_seed_pass_rate_min: float = 0.95
    incident_connectivity_min: float = 0.95
    incident_accessibility_min: float = 0.85
    incident_repair_iteration_limit: int = 3


@dataclass(frozen=True)
class GateVersions:
    oracle_version: str = "v1"
    corpus_version: str = "v1"
    budget_version: str = "v1"
    generator_version: str = "v2"


@dataclass
class GateDecision:
    metrics: dict[str, float] = field(default_factory=dict)
    thresholds: GateThresholds = field(default_factory=GateThresholds)
    versions: GateVersions = field(default_factory=GateVersions)
    hard_fail_reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        hard_fail_rate = float(self.metrics.get("hard_fail_rate", 0.0))
        ring_rate = float(self.metrics.get("ring_radial_connectivity_pass_rate", 1.0))
        incident_rate = float(self.metrics.get("incident_seed_pass_rate", 1.0))
        return (
            hard_fail_rate <= self.thresholds.hard_fail_rate_max
            and ring_rate >= self.thresholds.ring_radial_connectivity_min
            and incident_rate >= self.thresholds.incident_seed_pass_rate_min
            and not self.hard_fail_reasons
        )
