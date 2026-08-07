"""Evidence-bounded plausibility audit for realistic synthetic city maps."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import statistics
from types import MappingProxyType
from typing import Any, Iterable, Mapping

import numpy as np

from .blueprint import GeneratedCityMap
from .graph import RoadClass
from .morphology_metrics import compute_street_network_morphometrics
from .morphology_reference import (
    MORPHOLOGY_ARCHETYPES,
    empirical_street_network_references,
    get_morphology_archetype,
)
from .realistic_city import generate_city_map

__all__ = [
    "REALISTIC_CITY_AUDIT_SEEDS",
    "REALISTIC_CITY_AUDIT_STYLES",
    "EmpiricalMetricEnvelope",
    "RealisticCityAuditRecord",
    "RealisticCityPlausibilityAudit",
    "build_empirical_metric_envelopes",
    "load_realistic_city_plausibility_audit",
    "run_realistic_city_plausibility_audit",
    "write_realistic_city_plausibility_artifacts",
]

REALISTIC_CITY_AUDIT_STYLES = MORPHOLOGY_ARCHETYPES
REALISTIC_CITY_AUDIT_SEEDS = (17, 29, 41, 44, 53)
_AUDIT_SCHEMA_VERSION = "realistic_city_plausibility_audit_v1"
_EMPIRICAL_EXPANSION_FRACTION = 0.20
_SHARE_METRICS = frozenset(
    {"orientation_order", "dead_end_share", "four_way_share"}
)
# The range each metric can take by construction. A derived bound outside this
# range is inert: no map can violate it, so the gate stops discriminating on
# that metric. Clamping to these values can only ever make a bound stricter.
_ORIENTATION_BIN_COUNT = 36
_THEORETICAL_RANGES: Mapping[str, tuple[float, float]] = MappingProxyType(
    {
        "orientation_order": (0.0, 1.0),
        "orientation_entropy": (0.0, math.log(float(_ORIENTATION_BIN_COUNT))),
        "median_segment_length_m": (0.0, math.inf),
        "circuity": (1.0, math.inf),
        "mean_node_degree": (0.0, math.inf),
        "dead_end_share": (0.0, 1.0),
        "four_way_share": (0.0, 1.0),
    }
)
# A finite-range envelope covering at least this fraction of its own range
# cannot meaningfully fail.
_VACUOUS_COVERAGE_FRACTION = 0.95
_EMPIRICAL_METRICS = (
    "orientation_order",
    "orientation_entropy",
    "median_segment_length_m",
    "circuity",
    "mean_node_degree",
    "dead_end_share",
    "four_way_share",
)
_ROAD_CLASSES = tuple(item.value for item in RoadClass)
_LAND_USE_TYPES = (
    "residential",
    "commercial",
    "mixed_use",
    "industrial",
    "open_space",
)


@dataclass(frozen=True, slots=True)
class EmpiricalMetricEnvelope:
    metric: str
    reference_min: float
    reference_max: float
    lower: float
    upper: float
    expansion_fraction: float
    source_url: str
    source_cities: tuple[str, ...]
    # Derived from the metric name so every construction path - including the
    # artifact loader, which replays stored bounds - reports the same range.
    theoretical_min: float = field(init=False)
    theoretical_max: float = field(init=False)

    def __post_init__(self) -> None:
        theoretical_min, theoretical_max = _THEORETICAL_RANGES.get(
            str(self.metric), (-math.inf, math.inf)
        )
        object.__setattr__(self, "theoretical_min", float(theoretical_min))
        object.__setattr__(self, "theoretical_max", float(theoretical_max))
        values = (
            float(self.reference_min),
            float(self.reference_max),
            float(self.lower),
            float(self.upper),
            float(self.expansion_fraction),
        )
        if not str(self.metric).strip() or not str(self.source_url).strip():
            raise ValueError("envelope metric and source_url must be non-empty")
        if not all(math.isfinite(value) for value in values):
            raise ValueError("envelope values must be finite")
        if values[0] > values[1] or values[2] > values[3]:
            raise ValueError("envelope minima must not exceed maxima")
        if values[4] < 0.0:
            raise ValueError("envelope expansion_fraction must be >= 0")
        if not self.source_cities:
            raise ValueError("envelope source_cities must not be empty")

    def contains(self, value: float, *, tolerance: float = 1e-9) -> bool:
        value = float(value)
        return math.isfinite(value) and (
            self.lower - tolerance <= value <= self.upper + tolerance
        )

    @property
    def lower_bound_is_inert(self) -> bool:
        """No attainable value can fall below this bound."""

        return float(self.lower) <= float(self.theoretical_min)

    @property
    def upper_bound_is_inert(self) -> bool:
        """No attainable value can rise above this bound."""

        return float(self.upper) >= float(self.theoretical_max)

    @property
    def theoretical_coverage(self) -> float:
        """Fraction of the metric's attainable range the envelope admits."""

        span = float(self.theoretical_max) - float(self.theoretical_min)
        if not math.isfinite(span) or span <= 0.0:
            return math.nan
        return (float(self.upper) - float(self.lower)) / span

    @property
    def is_vacuous(self) -> bool:
        """The envelope admits so much of the range that it cannot fail."""

        if self.lower_bound_is_inert and self.upper_bound_is_inert:
            return True
        coverage = self.theoretical_coverage
        return math.isfinite(coverage) and coverage >= _VACUOUS_COVERAGE_FRACTION

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "reference_min": self.reference_min,
            "reference_max": self.reference_max,
            "lower": self.lower,
            "upper": self.upper,
            "expansion_fraction": self.expansion_fraction,
            "source_url": self.source_url,
            "source_cities": list(self.source_cities),
        }

    def diagnostics(self) -> dict[str, Any]:
        """Discriminative-power diagnostics, deliberately outside the fingerprint.

        These are fully derived from the bounds, so hashing them would add no
        information while breaking round-trips of previously written artifacts.
        """

        return {
            "metric": self.metric,
            "theoretical_min": self.theoretical_min,
            "theoretical_max": self.theoretical_max,
            "theoretical_coverage": self.theoretical_coverage,
            "lower_bound_is_inert": self.lower_bound_is_inert,
            "upper_bound_is_inert": self.upper_bound_is_inert,
            "is_vacuous": self.is_vacuous,
        }


@dataclass(frozen=True, slots=True)
class RealisticCityAuditRecord:
    style_id: str
    seed: int
    map_fingerprint: str
    metrics: Mapping[str, int | float]
    empirical_failures: tuple[str, ...]
    structural_failures: tuple[str, ...]
    passed: bool
    preview: Mapping[str, Any] | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        style_id = get_morphology_archetype(self.style_id).style_id
        metrics = {
            str(key): value
            for key, value in dict(self.metrics).items()
        }
        if not metrics:
            raise ValueError("audit record metrics must not be empty")
        for key, value in metrics.items():
            if not isinstance(value, (int, float, np.integer, np.floating)):
                raise ValueError(f"audit metric {key} must be numeric")
            if not math.isfinite(float(value)):
                raise ValueError(f"audit metric {key} must be finite")
        empirical = tuple(sorted({str(value) for value in self.empirical_failures}))
        structural = tuple(sorted({str(value) for value in self.structural_failures}))
        if bool(self.passed) != (not bool(empirical or structural)):
            raise ValueError("audit record pass flag and failures are inconsistent")
        preview = None
        if self.preview is not None:
            preview = MappingProxyType(dict(self.preview))
        object.__setattr__(self, "style_id", style_id)
        object.__setattr__(self, "seed", int(self.seed))
        object.__setattr__(self, "map_fingerprint", str(self.map_fingerprint))
        object.__setattr__(self, "metrics", MappingProxyType(metrics))
        object.__setattr__(self, "empirical_failures", empirical)
        object.__setattr__(self, "structural_failures", structural)
        object.__setattr__(self, "passed", bool(self.passed))
        object.__setattr__(self, "preview", preview)

    def as_dict(self, *, include_preview: bool = True) -> dict[str, Any]:
        payload = {
            "style_id": self.style_id,
            "seed": self.seed,
            "map_fingerprint": self.map_fingerprint,
            "passed": self.passed,
            "empirical_failures": list(self.empirical_failures),
            "structural_failures": list(self.structural_failures),
            "metrics": dict(self.metrics),
        }
        if include_preview:
            payload["preview"] = _json_safe(self.preview)
        return payload


@dataclass(frozen=True, slots=True)
class RealisticCityPlausibilityAudit:
    scenario_id: str
    style_ids: tuple[str, ...]
    seeds: tuple[int, ...]
    envelopes: tuple[EmpiricalMetricEnvelope, ...]
    records: tuple[RealisticCityAuditRecord, ...]
    reference_corpus_fingerprint: str
    style_summaries: Mapping[str, Mapping[str, int | float]]
    overall_pass: bool
    schema_version: str = _AUDIT_SCHEMA_VERSION
    evidence_status: str = "diagnostic_plausibility_audit"
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        scenario_id = str(self.scenario_id).strip()
        styles = tuple(get_morphology_archetype(value).style_id for value in self.style_ids)
        seeds = tuple(int(value) for value in self.seeds)
        records = tuple(self.records)
        if not scenario_id or not styles or not seeds:
            raise ValueError("audit scenario, styles, and seeds must be non-empty")
        if len(set(styles)) != len(styles) or len(set(seeds)) != len(seeds):
            raise ValueError("audit matrix axes must be unique")
        expected_pairs = tuple((style, seed) for style in styles for seed in seeds)
        actual_pairs = tuple((record.style_id, record.seed) for record in records)
        if actual_pairs != expected_pairs:
            raise ValueError("audit records must exactly cover style-major matrix order")
        expected_pass = all(record.passed for record in records)
        if bool(self.overall_pass) != expected_pass:
            raise ValueError("audit overall_pass does not match records")
        summaries = {
            str(style): MappingProxyType(dict(values))
            for style, values in dict(self.style_summaries).items()
        }
        if set(summaries) != set(styles):
            raise ValueError("audit style_summaries must cover every style")
        object.__setattr__(self, "scenario_id", scenario_id)
        object.__setattr__(self, "style_ids", styles)
        object.__setattr__(self, "seeds", seeds)
        object.__setattr__(self, "envelopes", tuple(self.envelopes))
        object.__setattr__(self, "records", records)
        object.__setattr__(self, "style_summaries", MappingProxyType(summaries))
        object.__setattr__(self, "overall_pass", expected_pass)
        object.__setattr__(self, "fingerprint", _report_fingerprint(self))

    @property
    def map_count(self) -> int:
        return len(self.records)

    @property
    def passed_map_count(self) -> int:
        return sum(record.passed for record in self.records)

    def as_dict(self, *, include_previews: bool = True) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_status": self.evidence_status,
            "scenario_id": self.scenario_id,
            "style_ids": list(self.style_ids),
            "seeds": list(self.seeds),
            "map_count": self.map_count,
            "passed_map_count": self.passed_map_count,
            "overall_pass": self.overall_pass,
            "reference_corpus_fingerprint": self.reference_corpus_fingerprint,
            "empirical_envelope_policy": "corpus_min_max_expanded_20_percent",
            "raw_osm_data_included": False,
            "external_data_learning_used": False,
            "runtime_network_access_used": False,
            "claim_boundary": (
                "broad synthetic plausibility diagnostic; not named-city, traffic, "
                "demand, route-choice, or land-use-evolution validation"
            ),
            "metric_definition_notes": {
                "street_graph": (
                    "undirected physical centerlines after planar compilation"
                ),
                "circuity": (
                    "compiled straight-fragment length divided by endpoint distance; "
                    "a lower-resolution diagnostic, not simplified OSM-edge circuity"
                ),
                "maximum_branch_free_corridor_m": (
                    "sum of contiguous degree-two physical edges whose source streets "
                    "front developed blocks"
                ),
                "motif_metrics": (
                    "diagnostic only; not used as admission thresholds"
                ),
            },
            "envelopes": [item.as_dict() for item in self.envelopes],
            "style_summaries": {
                style: dict(values)
                for style, values in self.style_summaries.items()
            },
            "records": [
                record.as_dict(include_preview=include_previews)
                for record in self.records
            ],
            "compact_ccot": {
                "question": (
                    "Do all fixed style/seed maps satisfy both pinned empirical "
                    "envelopes and frozen structural gates?"
                ),
                "evidence": (
                    "per-map street, block, hierarchy, land-use, terrain, and "
                    "compiled-runtime metrics"
                ),
                "inference": (
                    "overall pass requires every record; aggregate means cannot hide a failure"
                ),
                "counterevidence_checked": (
                    "motif concentration, hierarchy imbalance, block repetition, "
                    "single-seed success, and visual overclaim"
                ),
                "decision": "pass" if self.overall_pass else "fail_closed",
                "falsifier": "any empirical or structural failure in the fixed matrix",
                "next_action": (
                    "PR63 scale gate" if self.overall_pass else "generator revision before promotion"
                ),
            },
            "fingerprint": self.fingerprint,
        }


def build_empirical_metric_envelopes() -> Mapping[str, EmpiricalMetricEnvelope]:
    """Derive fixed 20-percent envelopes from the pinned reference corpus."""

    references = empirical_street_network_references()
    if not references:
        raise RuntimeError("empirical street-network reference corpus is empty")
    source_urls = {item.source_url for item in references}
    if len(source_urls) != 1:
        raise RuntimeError("reference corpus must use one pinned source version")
    source_url = next(iter(source_urls))
    cities = tuple(item.city for item in references)
    out: dict[str, EmpiricalMetricEnvelope] = {}
    for metric in _EMPIRICAL_METRICS:
        values = tuple(float(getattr(item, metric)) for item in references)
        reference_min = min(values)
        reference_max = max(values)
        lower = reference_min * (1.0 - _EMPIRICAL_EXPANSION_FRACTION)
        upper = reference_max * (1.0 + _EMPIRICAL_EXPANSION_FRACTION)
        theoretical_min, theoretical_max = _THEORETICAL_RANGES[metric]
        # Clamp into the attainable range. This only ever tightens a bound, so
        # it cannot turn a failing map into a passing one.
        lower = max(lower, theoretical_min)
        upper = min(upper, theoretical_max)
        out[metric] = EmpiricalMetricEnvelope(
            metric=metric,
            reference_min=reference_min,
            reference_max=reference_max,
            lower=lower,
            upper=upper,
            expansion_fraction=_EMPIRICAL_EXPANSION_FRACTION,
            source_url=source_url,
            source_cities=cities,
        )
    return MappingProxyType(out)


def run_realistic_city_plausibility_audit(
    *,
    style_ids: Iterable[str] = REALISTIC_CITY_AUDIT_STYLES,
    seeds: Iterable[int] = REALISTIC_CITY_AUDIT_SEEDS,
    scenario_id: str = "synthetic_smoke",
    include_previews: bool = True,
) -> RealisticCityPlausibilityAudit:
    """Generate and audit a deterministic style-by-seed map matrix."""

    styles = tuple(str(value) for value in style_ids)
    seed_values = tuple(int(value) for value in seeds)
    if not styles:
        raise ValueError("style_ids must not be empty")
    if len(set(styles)) != len(styles):
        raise ValueError("style_ids must be unique")
    if not seed_values:
        raise ValueError("seeds must not be empty")
    if len(set(seed_values)) != len(seed_values):
        raise ValueError("seeds must be unique")
    styles = tuple(get_morphology_archetype(value).style_id for value in styles)
    envelopes = build_empirical_metric_envelopes()
    records: list[RealisticCityAuditRecord] = []
    for style_id in styles:
        for seed in seed_values:
            generated = generate_city_map(
                _realistic_city_config(style_id),
                scenario_id=scenario_id,
                seed=seed,
            )
            records.append(
                _audit_generated_city_map(
                    generated,
                    envelopes=envelopes,
                    include_preview=bool(include_previews and seed == seed_values[0]),
                )
            )
    record_tuple = tuple(records)
    return RealisticCityPlausibilityAudit(
        scenario_id=scenario_id,
        style_ids=styles,
        seeds=seed_values,
        envelopes=tuple(envelopes.values()),
        records=record_tuple,
        reference_corpus_fingerprint=_reference_corpus_fingerprint(),
        style_summaries=_style_summaries(styles, record_tuple),
        overall_pass=all(record.passed for record in record_tuple),
    )


def load_realistic_city_plausibility_audit(
    path: str | Path,
) -> RealisticCityPlausibilityAudit:
    """Load and validate a previously written deterministic audit JSON."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    envelopes = tuple(
        EmpiricalMetricEnvelope(
            metric=item["metric"],
            reference_min=item["reference_min"],
            reference_max=item["reference_max"],
            lower=item["lower"],
            upper=item["upper"],
            expansion_fraction=item["expansion_fraction"],
            source_url=item["source_url"],
            source_cities=tuple(item["source_cities"]),
        )
        for item in payload["envelopes"]
    )
    records = tuple(
        RealisticCityAuditRecord(
            style_id=item["style_id"],
            seed=item["seed"],
            map_fingerprint=item["map_fingerprint"],
            metrics=item["metrics"],
            empirical_failures=tuple(item["empirical_failures"]),
            structural_failures=tuple(item["structural_failures"]),
            passed=item["passed"],
            preview=item.get("preview"),
        )
        for item in payload["records"]
    )
    styles = tuple(payload["style_ids"])
    report = RealisticCityPlausibilityAudit(
        scenario_id=payload["scenario_id"],
        style_ids=styles,
        seeds=tuple(payload["seeds"]),
        envelopes=envelopes,
        records=records,
        reference_corpus_fingerprint=payload["reference_corpus_fingerprint"],
        style_summaries=_style_summaries(styles, records),
        overall_pass=payload["overall_pass"],
        schema_version=payload["schema_version"],
        evidence_status=payload["evidence_status"],
    )
    if report.fingerprint != str(payload["fingerprint"]):
        raise ValueError("audit JSON fingerprint does not match reconstructed authority")
    return report


def write_realistic_city_plausibility_artifacts(
    artifact_prefix: str | Path,
    *,
    report: RealisticCityPlausibilityAudit | None = None,
    style_ids: Iterable[str] = REALISTIC_CITY_AUDIT_STYLES,
    seeds: Iterable[int] = REALISTIC_CITY_AUDIT_SEEDS,
    scenario_id: str = "synthetic_smoke",
) -> dict[str, Path]:
    """Write deterministic JSON, Markdown, HTML, and manifest review artifacts."""

    from .plausibility_reporting import write_plausibility_artifacts

    resolved = report or run_realistic_city_plausibility_audit(
        style_ids=style_ids,
        seeds=seeds,
        scenario_id=scenario_id,
        include_previews=True,
    )
    return write_plausibility_artifacts(artifact_prefix, report=resolved)


def _realistic_city_config(style_id: str) -> Any:
    from metroflow.sim.config import CityGenerationConfig

    return CityGenerationConfig(
        topology_mode="realistic_synthetic_v1",
        morphology_style_id=style_id,
        zone_poi_coupling_mode="block_based_v1",
    )


def _audit_generated_city_map(
    generated: GeneratedCityMap,
    *,
    envelopes: Mapping[str, EmpiricalMetricEnvelope],
    include_preview: bool,
) -> RealisticCityAuditRecord:
    metrics = _map_metrics(generated)
    empirical_failures = tuple(
        f"{metric}_outside_empirical_envelope"
        for metric, envelope in envelopes.items()
        if not envelope.contains(float(metrics[metric]))
    )
    structural_failures = _structural_failures(metrics, generated)
    failures = empirical_failures + structural_failures
    return RealisticCityAuditRecord(
        style_id=generated.blueprint.style_id,
        seed=generated.blueprint.seed,
        map_fingerprint=generated.fingerprint,
        metrics=metrics,
        empirical_failures=empirical_failures,
        structural_failures=structural_failures,
        passed=not failures,
        preview=_preview_payload(generated) if include_preview else None,
    )


def _map_metrics(generated: GeneratedCityMap) -> dict[str, int | float]:
    street = compute_street_network_morphometrics(generated.topology)
    quality = generated.quality.metrics
    blocks = generated.blueprint.blocks.blocks
    land_use_blocks = generated.blueprint.land_use.blocks
    terrain = generated.blueprint.terrain
    hierarchy = _hierarchy_length_shares(generated)
    orientation = _orientation_concentration(generated)
    lengths = tuple(
        float(item.length_m) for item in generated.topology.road_geometry.centerlines
    )
    block_areas = tuple(float(item.area_m2) for item in blocks)
    land_use_counts = Counter(item.land_use_type.value for item in land_use_blocks)
    block_count = max(len(land_use_blocks), 1)
    sampled_od_count = int(quality["sampled_od_count"])
    reachable_od_count = int(quality["reachable_od_count"])
    metrics: dict[str, int | float] = {
        "orientation_order": street.orientation_order,
        "orientation_entropy": street.orientation_entropy,
        "median_segment_length_m": street.median_segment_length_m,
        "circuity": street.circuity,
        "mean_node_degree": street.mean_node_degree,
        "dead_end_share": street.dead_end_share,
        "four_way_share": street.four_way_share,
        "physical_segment_count": street.physical_segment_count,
        "node_count": len(generated.topology.nodes),
        "directed_link_count": len(generated.topology.links),
        "turn_count": len(generated.topology.turns),
        "weak_component_count": int(quality["weak_component_count"]),
        "connectivity_repair_link_count": int(
            quality["connectivity_repair_link_count"]
        ),
        "proper_intersection_count": int(quality["proper_intersection_count"]),
        "geometry_coverage": float(quality["geometry_coverage"]),
        "section_coverage": float(quality["section_coverage"]),
        "node_interface_coverage": float(quality["node_interface_coverage"]),
        "turn_pair_coverage": float(quality["turn_pair_coverage"]),
        "sampled_od_count": sampled_od_count,
        "reachable_od_count": reachable_od_count,
        "sampled_od_reachability_share": (
            reachable_od_count / max(sampled_od_count, 1)
        ),
        "maximum_developed_access_distance_m": float(
            quality["maximum_developed_access_distance_m"]
        ),
        "maximum_branch_free_corridor_m": _maximum_branch_free_corridor_m(
            generated
        ),
        "physical_segment_median_m": float(quality["physical_segment_median_m"]),
        "physical_segment_under_10m_share": float(
            quality["physical_segment_under_10m_share"]
        ),
        "bounded_block_count": len(blocks),
        "bounded_block_median_area_m2": float(
            quality["bounded_block_median_area_m2"]
        ),
        "bounded_block_p95_area_m2": float(
            quality["bounded_block_p95_area_m2"]
        ),
        "developed_block_frontage_coverage": float(
            quality["developed_block_frontage_coverage"]
        ),
        "developed_block_share": (
            generated.blueprint.land_use.developed_block_count / block_count
        ),
        "essential_access_ratio": float(quality["essential_access_ratio"]),
        "industrial_residential_shared_edge_count": int(
            quality["industrial_residential_shared_edge_count"]
        ),
        "water_cell_share": float(np.mean(terrain.water_mask)),
        "buildable_cell_share": float(np.mean(terrain.buildable_mask)),
        "center_count": len(generated.blueprint.urban_form.centers),
        "skeleton_street_count": generated.blueprint.street_network.skeleton_street_count,
        "local_street_count": generated.blueprint.street_network.local_street_count,
        "collector_street_count": generated.blueprint.street_network.collector_street_count,
        "dominant_orientation_bin_share": orientation[0],
        "top_two_orientation_bin_share": orientation[1],
        "dominant_length_bin_share": _dominant_binned_share(lengths, width=10.0),
        "dominant_block_area_bin_share": _dominant_binned_share(
            block_areas,
            width=2_500.0,
        ),
        "block_area_coefficient_of_variation": _coefficient_of_variation(
            block_areas
        ),
    }
    metrics.update(hierarchy)
    metrics.update(
        {
            f"land_use_{land_use_type}_share": (
                land_use_counts.get(land_use_type, 0) / block_count
            )
            for land_use_type in _LAND_USE_TYPES
        }
    )
    return metrics


def _structural_failures(
    metrics: Mapping[str, int | float],
    generated: GeneratedCityMap,
) -> tuple[str, ...]:
    failures: list[str] = []
    if not generated.quality.passed:
        failures.extend(f"quality_{code}" for code in generated.quality.failure_codes)
    exact_values = {
        "weak_component_count": 1,
        "connectivity_repair_link_count": 0,
        "proper_intersection_count": 0,
        "industrial_residential_shared_edge_count": 0,
    }
    for name, expected in exact_values.items():
        if int(metrics[name]) != expected:
            failures.append(f"{name}_must_equal_{expected}")
    for name in (
        "geometry_coverage",
        "section_coverage",
        "node_interface_coverage",
        "turn_pair_coverage",
        "sampled_od_reachability_share",
        "developed_block_frontage_coverage",
        "essential_access_ratio",
    ):
        if not math.isclose(float(metrics[name]), 1.0, abs_tol=1e-9):
            failures.append(f"{name}_must_equal_1")
    bounded_checks = (
        ("maximum_developed_access_distance_m", None, 400.0),
        ("maximum_branch_free_corridor_m", None, 800.0),
        ("physical_segment_median_m", 40.0, 180.0),
        ("physical_segment_under_10m_share", None, 0.02),
        ("bounded_block_median_area_m2", 3_000.0, 30_000.0),
        ("bounded_block_p95_area_m2", None, 120_000.0),
    )
    for name, lower, upper in bounded_checks:
        value = float(metrics[name])
        if lower is not None and value < lower - 1e-9:
            failures.append(f"{name}_below_{lower:g}")
        if upper is not None and value > upper + 1e-9:
            failures.append(f"{name}_above_{upper:g}")
    return tuple(sorted(set(failures)))


def _hierarchy_length_shares(
    generated: GeneratedCityMap,
) -> dict[str, float]:
    length_by_class = Counter()
    for street in generated.blueprint.street_network.streets:
        length_by_class[street.road_class.value] += float(street.length_m)
    total = max(sum(length_by_class.values()), 1e-12)
    return {
        f"road_class_{road_class}_length_share": (
            float(length_by_class.get(road_class, 0.0)) / total
        )
        for road_class in _ROAD_CLASSES
    }


def _orientation_concentration(
    generated: GeneratedCityMap,
) -> tuple[float, float]:
    counts = [0] * 36
    for centerline in generated.topology.road_geometry.centerlines:
        left = centerline.points_m[0]
        right = centerline.points_m[-1]
        dx = float(right[0]) - float(left[0])
        dy = float(right[1]) - float(left[1])
        if math.hypot(dx, dy) <= 0.0:
            continue
        bearing = math.degrees(math.atan2(dx, dy)) % 360.0
        for value in (bearing, (bearing + 180.0) % 360.0):
            counts[int(((value + 5.0) % 360.0) // 10.0)] += 1
    total = sum(counts)
    if total == 0:
        return (0.0, 0.0)
    ordered = sorted(counts, reverse=True)
    return (ordered[0] / total, sum(ordered[:2]) / total)


def _dominant_binned_share(values: tuple[float, ...], *, width: float) -> float:
    if not values:
        return 0.0
    counts = Counter(int(math.floor(float(value) / width)) for value in values)
    return max(counts.values()) / len(values)


def _coefficient_of_variation(values: tuple[float, ...]) -> float:
    if not values:
        return 0.0
    mean = statistics.fmean(values)
    if mean <= 0.0 or len(values) < 2:
        return 0.0
    return statistics.pstdev(values) / mean


def _maximum_branch_free_corridor_m(generated: GeneratedCityMap) -> float:
    developed_street_ids = {
        int(street_id)
        for block in generated.blueprint.land_use.blocks
        if block.is_developed
        for street_id in block.frontage_street_ids
    }
    source_street_by_link_id = dict(
        generated.blueprint.blocks.new_link_to_street_id
    )
    edge_by_id: dict[int, tuple[int, int, float]] = {}
    for link in generated.topology.links:
        physical_id = int(link.physical_road_id)
        source_street_id = source_street_by_link_id.get(int(link.link_id))
        if source_street_id not in developed_street_ids:
            continue
        edge_by_id.setdefault(
            physical_id,
            (int(link.src_node_id), int(link.dst_node_id), float(link.length_m)),
        )
    return _maximum_branch_free_corridor_from_edges(edge_by_id)


def _maximum_branch_free_corridor_from_edges(
    edge_by_id: Mapping[int, tuple[int, int, float]],
) -> float:
    if not edge_by_id:
        return 0.0
    adjacency: dict[int, list[int]] = defaultdict(list)
    for edge_id, (left, right, _length) in edge_by_id.items():
        adjacency[left].append(edge_id)
        adjacency[right].append(edge_id)
    visited: set[int] = set()
    maximum = 0.0

    def traverse(start_node: int, first_edge: int) -> float:
        total = 0.0
        node = int(start_node)
        edge_id = int(first_edge)
        while edge_id not in visited:
            visited.add(edge_id)
            left, right, length = edge_by_id[edge_id]
            total += length
            node = right if node == left else left
            candidates = [value for value in adjacency[node] if value != edge_id]
            if len(adjacency[node]) != 2 or not candidates:
                break
            edge_id = candidates[0]
        return total

    for node, edge_ids in sorted(adjacency.items()):
        if len(edge_ids) == 2:
            continue
        for edge_id in sorted(edge_ids):
            if edge_id not in visited:
                maximum = max(maximum, traverse(node, edge_id))
    for edge_id in sorted(edge_by_id):
        if edge_id not in visited:
            maximum = max(maximum, traverse(edge_by_id[edge_id][0], edge_id))
    return float(maximum)


def _preview_payload(generated: GeneratedCityMap) -> Mapping[str, Any]:
    terrain = generated.blueprint.terrain
    stride_y = max(1, terrain.shape[0] // 24)
    stride_x = max(1, terrain.shape[1] // 24)
    terrain_cells = []
    for row in range(0, terrain.shape[0], stride_y):
        for col in range(0, terrain.shape[1], stride_x):
            terrain_cells.append(
                {
                    "x": float(terrain.x_coordinates_m[col]),
                    "y": float(terrain.y_coordinates_m[row]),
                    "width": terrain.cell_size_x_m * stride_x,
                    "height": terrain.cell_size_y_m * stride_y,
                    "elevation": float(terrain.elevation_m[row, col]),
                    "water": bool(terrain.water_mask[row, col]),
                    "buildable": bool(terrain.buildable_mask[row, col]),
                }
            )
    roads = tuple(
        {
            "road_class": street.road_class.value,
            "points": street.points_m,
        }
        for street in generated.blueprint.street_network.streets
    )
    blocks = tuple(
        {"block_id": block.block_id, "polygon": block.polygon_m}
        for block in generated.blueprint.blocks.blocks
    )
    land_use = tuple(
        {
            "block_id": block.block_id,
            "land_use_type": block.land_use_type.value,
            "polygon": block.polygon_m,
        }
        for block in generated.blueprint.land_use.blocks
    )
    runtime_roads = tuple(
        {
            "geometry_id": centerline.geometry_id,
            "points": centerline.points_m,
        }
        for centerline in generated.topology.road_geometry.centerlines
    )
    runtime_nodes = tuple(
        (float(node.x), float(node.y)) for node in generated.topology.nodes
    )
    return MappingProxyType(
        {
            "width_m": generated.blueprint.width_m,
            "height_m": generated.blueprint.height_m,
            "layers": MappingProxyType(
                {
                    "terrain": {"cells": tuple(terrain_cells)},
                    "roads": {"roads": roads},
                    "blocks": {"blocks": blocks},
                    "land_use": {"blocks": land_use},
                    "runtime": {
                        "roads": runtime_roads,
                        "nodes": runtime_nodes,
                    },
                }
            ),
        }
    )


def _style_summaries(
    styles: tuple[str, ...],
    records: tuple[RealisticCityAuditRecord, ...],
) -> Mapping[str, Mapping[str, int | float]]:
    summaries: dict[str, Mapping[str, int | float]] = {}
    for style in styles:
        selected = tuple(record for record in records if record.style_id == style)
        summary: dict[str, int | float] = {
            "map_count": len(selected),
            "passed_map_count": sum(record.passed for record in selected),
            "empirical_failure_count": sum(
                len(record.empirical_failures) for record in selected
            ),
            "structural_failure_count": sum(
                len(record.structural_failures) for record in selected
            ),
        }
        for metric in (
            *_EMPIRICAL_METRICS,
            "dominant_orientation_bin_share",
            "dominant_length_bin_share",
            "dominant_block_area_bin_share",
            "block_area_coefficient_of_variation",
            "road_class_local_length_share",
            "road_class_collector_length_share",
            "maximum_branch_free_corridor_m",
        ):
            values = tuple(float(record.metrics[metric]) for record in selected)
            summary[f"{metric}_min"] = min(values)
            summary[f"{metric}_median"] = statistics.median(values)
            summary[f"{metric}_max"] = max(values)
        summaries[style] = MappingProxyType(summary)
    return MappingProxyType(summaries)


def _reference_corpus_fingerprint() -> str:
    return _sha256(
        [
            {
                "city": item.city,
                **{metric: getattr(item, metric) for metric in _EMPIRICAL_METRICS},
                "source_url": item.source_url,
                "evidence_status": item.evidence_status,
            }
            for item in empirical_street_network_references()
        ]
    )


def _report_fingerprint(report: RealisticCityPlausibilityAudit) -> str:
    return _sha256(
        {
            "schema_version": report.schema_version,
            "scenario_id": report.scenario_id,
            "style_ids": report.style_ids,
            "seeds": report.seeds,
            "reference_corpus_fingerprint": report.reference_corpus_fingerprint,
            "envelopes": [item.as_dict() for item in report.envelopes],
            "records": [
                {
                    "style_id": item.style_id,
                    "seed": item.seed,
                    "map_fingerprint": item.map_fingerprint,
                    "metrics": dict(item.metrics),
                    "empirical_failures": item.empirical_failures,
                    "structural_failures": item.structural_failures,
                    "passed": item.passed,
                }
                for item in report.records
            ],
            "overall_pass": report.overall_pass,
        }
    )


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    raise TypeError(f"unsupported audit JSON value: {type(value).__name__}")


def _sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _json_safe(payload),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()
