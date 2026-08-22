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

from metroflow.map.road_geometry import (
    RoadGeometryCatalog,
    count_interior_centerline_intersections,
    count_unregistered_centerline_touches,
)

from .morphology_metrics import MeasurementSpec, compute_street_network_morphometrics
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
    "source_topology_fingerprint",
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

# v2: scores are measured under an explicitly named MeasurementSpec rather than
# a boolean, the default statistic is BOEING_2019_HO with OSMnx parity checked
# rather than asserted, and `envelope_diagnostics` emits null with a status field
# instead of bare NaN/Infinity. The measured values differ from v1 even where the
# verdicts do not, so the version is bumped rather than the payload reinterpreted.
# v3: every new score carries the exact fingerprint of the topology inputs from
# which its metrics were measured. Historical scores reconstructed without that
# field retain their historical payload and fingerprint rather than being
# silently reinterpreted under the stronger contract.
# v4: the measurement specification joins the score payload and fingerprint,
# and current-schema tables reject scores missing either identity field.
CONTROL_TABLE_SCHEMA_VERSION = "morphology_control_table_v4"
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
    # Geometry-vs-topology consistency. None means "not measured", which is what
    # a score reconstructed from a stored artifact carries. Deliberately kept out
    # of `as_dict`: the fingerprint hashes that payload, and a diagnostic must
    # never invalidate a pinned artifact.
    proper_crossing_count: int | None = None
    unregistered_touch_count: int | None = None
    measurement_spec: str | None = None
    source_topology_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not str(self.arm).strip():
            raise ValueError("arm must be a non-empty label")
        missing = set(EMPIRICAL_MORPHOLOGY_METRICS) - set(self.metrics)
        if missing:
            raise ValueError(f"score is missing metrics: {sorted(missing)}")
        source_fingerprint = self.source_topology_fingerprint
        if source_fingerprint is not None and (
            type(source_fingerprint) is not str
            or len(source_fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in source_fingerprint)
        ):
            raise ValueError("source_topology_fingerprint must be a lowercase SHA-256 digest")
        if self.measurement_spec is not None and self.measurement_spec not in {
            item.value for item in MeasurementSpec
        }:
            raise ValueError("measurement_spec must name a supported MeasurementSpec")
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))

    @property
    def passed(self) -> bool:
        return not self.failed_metrics

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "arm": self.arm,
            "case": self.case,
            "metrics": {key: float(self.metrics[key]) for key in EMPIRICAL_MORPHOLOGY_METRICS},
            "failed_metrics": list(self.failed_metrics),
            "passed": self.passed,
            "simplified": self.simplified,
            "node_count": self.node_count,
            "physical_segment_count": self.physical_segment_count,
        }
        if self.source_topology_fingerprint is not None:
            payload["source_topology_fingerprint"] = self.source_topology_fingerprint
        if self.measurement_spec is not None:
            payload["measurement_spec"] = self.measurement_spec
        return payload

    def topology_diagnostics(self) -> dict[str, int | None]:
        """How far the drawn network is from the graph it compiles to.

        The seven envelope metrics cannot see this: a street that begins on
        another street's interior leaves both of them measurable and neither of
        them connected. Reported, never gated — the post-PR-B values are not
        known yet, and freezing a threshold before the measurement exists is the
        mistake this project already made once.
        """

        return {
            "measurement_spec": self.measurement_spec,
            "proper_crossing_count": self.proper_crossing_count,
            "unregistered_touch_count": self.unregistered_touch_count,
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
        score_keys = tuple((score.arm, score.case) for score in self.scores)
        if len(score_keys) != len(set(score_keys)):
            raise ValueError("control table score keys must be unique by (arm, case)")
        if self.schema_version == CONTROL_TABLE_SCHEMA_VERSION:
            if any(score.measurement_spec is None for score in self.scores):
                raise ValueError("current control table requires measurement_spec")
            if any(score.source_topology_fingerprint is None for score in self.scores):
                raise ValueError(
                    "current control table requires source_topology_fingerprint"
                )
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
            "topology_diagnostics": {
                f"{item.arm}:{item.case}": item.topology_diagnostics()
                for item in self.scores
            },
            "vacuous_metrics": list(self.vacuous_metrics),
            "summaries": [item.as_dict() for item in self.summaries],
            "scores": [item.as_dict() for item in self.scores],
            "claim_boundary": (
                "Diagnostic street-morphology comparison against a pinned "
                "reference corpus. Not empirical traffic, demand, route-choice "
                "or named-city validation; does not score scalable_synthetic_v2."
            ),
            "fingerprint": self.fingerprint,
        }


def score_street_morphology(
    topology: _TopologyLike,
    *,
    arm: str,
    case: str = "",
    spec: MeasurementSpec = MeasurementSpec.BOEING_2019_HO,
    envelopes: Mapping[str, EmpiricalMetricEnvelope] | None = None,
) -> MorphologyScore:
    """Measure one topology against the pinned empirical envelope.

    Defaults to `BOEING_2019_HO` because that is the statistic the pinned corpus
    reports, and it is the only spec checked against a pinned OSMnx.
    """

    spec = MeasurementSpec(spec)
    resolved = build_empirical_metric_envelopes() if envelopes is None else envelopes
    street = compute_street_network_morphometrics(topology, spec=spec)
    metrics = {name: float(getattr(street, name)) for name in EMPIRICAL_MORPHOLOGY_METRICS}
    failed = tuple(
        name
        for name in EMPIRICAL_MORPHOLOGY_METRICS
        if not resolved[name].contains(metrics[name])
    )
    geometry = topology.road_geometry
    return MorphologyScore(
        arm=str(arm),
        case=str(case),
        metrics=metrics,
        failed_metrics=failed,
        # Kept as a bool so the pinned v1 artifact payload stays byte-comparable.
        # Current-schema scores also bind the explicit spec name below.
        simplified=spec is MeasurementSpec.BOEING_2019_HO,
        measurement_spec=spec.value,
        node_count=len(topology.nodes),
        physical_segment_count=street.physical_segment_count,
        proper_crossing_count=count_interior_centerline_intersections(geometry),
        unregistered_touch_count=count_unregistered_centerline_touches(geometry),
        source_topology_fingerprint=source_topology_fingerprint(topology),
    )


def source_topology_fingerprint(topology: _TopologyLike) -> str:
    """Bind every input used by the morphology measurement to one digest.

    The measurement consumes node coordinates, directed-link incidence, and the
    physical centerline catalog. Runtime-only speed/capacity fields are omitted:
    changing them cannot change a street-morphology metric and should not make a
    historical measurement look stale.
    """

    geometry = topology.road_geometry
    if not isinstance(geometry, RoadGeometryCatalog):
        raise ValueError("road_geometry is required for source topology fingerprinting")
    nodes = tuple(
        sorted(
            (int(node.node_id), float(node.x), float(node.y))
            for node in topology.nodes
        )
    )
    links = tuple(
        sorted(
            (
                int(link.link_id),
                int(link.src_node_id),
                int(link.dst_node_id),
            )
            for link in topology.links
        )
    )
    payload = {
        "schema_version": "morphology_source_topology_v1",
        "nodes": nodes,
        "links": links,
        "road_geometry_fingerprint": geometry.fingerprint,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


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
