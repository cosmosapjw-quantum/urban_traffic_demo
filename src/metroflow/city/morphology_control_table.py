"""Score street morphology for any topology, so control arms are comparable.

`plausibility_audit.run_realistic_city_plausibility_audit` generates its own maps
with `topology_mode="realistic_synthetic_v1"`, so it can only score the generator
under test. This module applies the same pinned envelope to any
`PreviewCityTopology`, which is what makes a positive control (an offline OSM
extract) and the incumbent/sidecar arms measurable on one instrument.

Scope is deliberately the seven empirical street-morphology metrics only. The
structural, block, land-use and reachability gates stay in `plausibility_audit`
because they require a full `GeneratedCityMap`, which most arms do not produce.

This is diagnostic instrumentation, not empirical city or traffic validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol

from metroflow.map.road_geometry import RoadGeometryCatalog

from .morphology_metrics import compute_street_network_morphometrics
from .plausibility_audit import (
    EmpiricalMetricEnvelope,
    build_empirical_metric_envelopes,
)

__all__ = [
    "MorphologyScore",
    "ArmSummary",
    "MorphologyControlTable",
    "score_street_morphology",
    "build_morphology_control_table",
    "EMPIRICAL_MORPHOLOGY_METRICS",
]

EMPIRICAL_MORPHOLOGY_METRICS = (
    "orientation_order",
    "orientation_entropy",
    "median_segment_length_m",
    "circuity",
    "mean_node_degree",
    "dead_end_share",
    "four_way_share",
)

CONTROL_TABLE_SCHEMA_VERSION = "morphology_control_table_v1"
EVIDENCE_STATUS = "diagnostic_not_empirical_validation"


class _TopologyLike(Protocol):
    nodes: tuple[Any, ...]
    links: tuple[Any, ...]
    road_geometry: RoadGeometryCatalog | None


@dataclass(frozen=True, slots=True)
class MorphologyScore:
    """One topology measured against the pinned empirical envelope."""

    arm: str
    case: str
    metrics: Mapping[str, float]
    failed_metrics: tuple[str, ...]
    simplified: bool
    node_count: int
    physical_segment_count: int

    def __post_init__(self) -> None:
        if not str(self.arm).strip():
            raise ValueError("arm must be a non-empty label")
        missing = set(EMPIRICAL_MORPHOLOGY_METRICS) - set(self.metrics)
        if missing:
            raise ValueError(f"score is missing metrics: {sorted(missing)}")
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))

    @property
    def passed(self) -> bool:
        return not self.failed_metrics

    def as_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "case": self.case,
            "metrics": {key: float(self.metrics[key]) for key in EMPIRICAL_MORPHOLOGY_METRICS},
            "failed_metrics": list(self.failed_metrics),
            "passed": self.passed,
            "simplified": self.simplified,
            "node_count": self.node_count,
            "physical_segment_count": self.physical_segment_count,
        }


@dataclass(frozen=True, slots=True)
class ArmSummary:
    """How one arm scored across all of its cases."""

    arm: str
    case_count: int
    passed_case_count: int
    metric_pass_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "metric_pass_counts", MappingProxyType(dict(self.metric_pass_counts))
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "case_count": self.case_count,
            "passed_case_count": self.passed_case_count,
            "metric_pass_counts": {
                key: int(self.metric_pass_counts[key])
                for key in EMPIRICAL_MORPHOLOGY_METRICS
            },
        }


@dataclass(frozen=True, slots=True)
class MorphologyControlTable:
    """Every arm scored on one instrument, with the instrument's own limits."""

    scores: tuple[MorphologyScore, ...]
    envelopes: tuple[EmpiricalMetricEnvelope, ...]
    summaries: tuple[ArmSummary, ...] = field(init=False)
    vacuous_metrics: tuple[str, ...] = field(init=False)
    fingerprint: str = field(init=False)
    schema_version: str = CONTROL_TABLE_SCHEMA_VERSION
    evidence_status: str = EVIDENCE_STATUS

    def __post_init__(self) -> None:
        if not self.scores:
            raise ValueError("control table requires at least one score")
        if not self.envelopes:
            raise ValueError("control table requires the pinned envelopes")
        object.__setattr__(self, "summaries", _summarize(self.scores))
        object.__setattr__(
            self,
            "vacuous_metrics",
            tuple(item.metric for item in self.envelopes if item.is_vacuous),
        )
        object.__setattr__(self, "fingerprint", _fingerprint(self))

    def summary_for(self, arm: str) -> ArmSummary:
        for item in self.summaries:
            if item.arm == arm:
                return item
        raise KeyError(f"unknown arm {arm!r}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_status": self.evidence_status,
            "envelopes": [item.as_dict() for item in self.envelopes],
            "envelope_diagnostics": {
                item.metric: item.diagnostics() for item in self.envelopes
            },
            "vacuous_metrics": list(self.vacuous_metrics),
            "summaries": [item.as_dict() for item in self.summaries],
            "scores": [item.as_dict() for item in self.scores],
            "claim_boundary": (
                "Diagnostic street-morphology comparison against a pinned "
                "reference corpus. Not empirical traffic, demand, route-choice "
                "or named-city validation."
            ),
            "fingerprint": self.fingerprint,
        }


def score_street_morphology(
    topology: _TopologyLike,
    *,
    arm: str,
    case: str = "",
    simplify_interstitial_nodes: bool = True,
    envelopes: Mapping[str, EmpiricalMetricEnvelope] | None = None,
) -> MorphologyScore:
    """Measure one topology against the pinned empirical envelope.

    Defaults to the simplified graph because the pinned corpus reports OSMnx
    values measured after `simplify_graph` contracts degree-2 nodes.
    """

    resolved = build_empirical_metric_envelopes() if envelopes is None else envelopes
    street = compute_street_network_morphometrics(
        topology,
        simplify_interstitial_nodes=simplify_interstitial_nodes,
    )
    metrics = {name: float(getattr(street, name)) for name in EMPIRICAL_MORPHOLOGY_METRICS}
    failed = tuple(
        name
        for name in EMPIRICAL_MORPHOLOGY_METRICS
        if not resolved[name].contains(metrics[name])
    )
    return MorphologyScore(
        arm=str(arm),
        case=str(case),
        metrics=metrics,
        failed_metrics=failed,
        simplified=bool(simplify_interstitial_nodes),
        node_count=len(topology.nodes),
        physical_segment_count=street.physical_segment_count,
    )


def build_morphology_control_table(
    scores: Iterable[MorphologyScore],
    *,
    envelopes: Mapping[str, EmpiricalMetricEnvelope] | None = None,
) -> MorphologyControlTable:
    resolved = build_empirical_metric_envelopes() if envelopes is None else envelopes
    return MorphologyControlTable(
        scores=tuple(scores),
        envelopes=tuple(resolved[name] for name in EMPIRICAL_MORPHOLOGY_METRICS),
    )


def _summarize(scores: tuple[MorphologyScore, ...]) -> tuple[ArmSummary, ...]:
    ordered_arms: list[str] = []
    by_arm: dict[str, list[MorphologyScore]] = {}
    for score in scores:
        if score.arm not in by_arm:
            by_arm[score.arm] = []
            ordered_arms.append(score.arm)
        by_arm[score.arm].append(score)
    return tuple(
        ArmSummary(
            arm=arm,
            case_count=len(by_arm[arm]),
            passed_case_count=sum(item.passed for item in by_arm[arm]),
            metric_pass_counts={
                metric: sum(metric not in item.failed_metrics for item in by_arm[arm])
                for metric in EMPIRICAL_MORPHOLOGY_METRICS
            },
        )
        for arm in ordered_arms
    )


def _fingerprint(table: MorphologyControlTable) -> str:
    payload = {
        "schema_version": table.schema_version,
        "envelopes": [item.as_dict() for item in table.envelopes],
        "scores": [item.as_dict() for item in table.scores],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()
