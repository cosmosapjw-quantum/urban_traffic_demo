"""Fresh-process scale and hardware-fit audit for realistic synthetic cities."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable, Mapping, Sequence

import numpy as np

REALISTIC_CITY_SCALE_SCHEMA_VERSION = "realistic_city_scale_v1"
REALISTIC_CITY_SCALE_POPULATIONS = (1_000, 10_000, 100_000)
REALISTIC_CITY_SCALE_SEEDS = (17, 29, 41)
REALISTIC_CITY_SCALE_MODES = ("standard", "realistic_synthetic_v1")
REALISTIC_CITY_SCALE_STEPS = 20
REALISTIC_CITY_RUST_STAGE_THRESHOLD = 0.30
REALISTIC_CITY_RUST_ELIGIBLE_STAGES = (
    "hierarchical_street_skeleton",
    "continuous_local_fabric",
    "planar_blocks",
)
_REALISTIC_STAGE_TARGETS = (
    ("terrain_field", "build_terrain_field"),
    ("urban_form_field", "build_urban_form_field"),
    ("hierarchical_street_skeleton", "build_hierarchical_street_skeleton"),
    ("continuous_local_fabric", "build_continuous_local_fabric"),
    ("planar_blocks", "compile_planar_city_blocks"),
    ("block_land_use", "build_block_land_use_catalog"),
    ("runtime_topology_compile", "_compile_topology"),
    ("runtime_zoning_compile", "_compile_zoning"),
    ("quality_evaluation", "_evaluate_quality"),
)

__all__ = [
    "REALISTIC_CITY_SCALE_POPULATIONS",
    "REALISTIC_CITY_SCALE_SEEDS",
    "CityScalePerformancePair",
    "CityScaleRunResult",
    "CityScaleStageShare",
    "CityScaleWorkerSpec",
    "RealisticCityScaleReport",
    "build_realistic_city_scale_report",
    "load_realistic_city_scale_report",
    "run_realistic_city_scale_audit",
    "run_realistic_city_scale_subprocess",
    "write_realistic_city_scale_artifacts",
]


@dataclass(frozen=True, slots=True)
class CityScaleWorkerSpec:
    topology_mode: str
    population_target: int
    seed: int
    operation: str
    requested_steps: int = REALISTIC_CITY_SCALE_STEPS
    tick_budget_ns: int = 0
    eager_trip_generation: bool = True
    morphology_style_id: str = "auto"

    def __post_init__(self) -> None:
        if self.topology_mode not in REALISTIC_CITY_SCALE_MODES:
            raise ValueError(
                "topology_mode must be standard or realistic_synthetic_v1"
            )
        if int(self.population_target) < 1:
            raise ValueError("population_target must be positive")
        if self.operation not in {
            "city_authority",
            "fixed_steps",
            "time_budget",
            "city_stage_profile",
        }:
            raise ValueError(
                "operation must be city_authority, fixed_steps, time_budget, "
                "or city_stage_profile"
            )
        if self.operation == "fixed_steps" and int(self.requested_steps) < 1:
            raise ValueError("fixed_steps operation requires requested_steps > 0")
        if self.operation == "time_budget" and int(self.tick_budget_ns) < 1:
            raise ValueError("time_budget operation requires tick_budget_ns > 0")

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> CityScaleWorkerSpec:
        return cls(
            topology_mode=str(payload["topology_mode"]),
            population_target=int(payload["population_target"]),
            seed=int(payload["seed"]),
            operation=str(payload["operation"]),
            requested_steps=int(payload.get("requested_steps", 0)),
            tick_budget_ns=int(payload.get("tick_budget_ns", 0)),
            eager_trip_generation=bool(payload.get("eager_trip_generation", True)),
            morphology_style_id=str(payload.get("morphology_style_id", "auto")),
        )


@dataclass(frozen=True, slots=True)
class CityScaleRunResult:
    topology_mode: str
    population_target: int
    seed: int
    scenario_id: str
    morphology_style_id: str
    operation: str
    eager_trip_generation: bool
    requested_steps: int
    tick_budget_ns: int
    ticks_completed: int
    worker_pid: int
    city_authority_wall_ns: int
    initialization_wall_ns: int
    runtime_wall_ns: int
    peak_rss_kib: int
    process_peak_rss_kib: int
    node_count: int
    link_count: int
    turn_count: int
    block_count: int
    zone_count: int
    citizen_count: int
    trip_request_count: int
    active_agent_capacity: int
    city_stage_wall_ns: tuple[tuple[str, int], ...]
    runtime_stage_wall_ns: tuple[tuple[str, int], ...]
    city_fingerprint: str

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["city_stage_wall_ns"] = _timing_rows(self.city_stage_wall_ns)
        payload["runtime_stage_wall_ns"] = _timing_rows(
            self.runtime_stage_wall_ns
        )
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> CityScaleRunResult:
        return cls(
            topology_mode=str(payload["topology_mode"]),
            population_target=int(payload["population_target"]),
            seed=int(payload["seed"]),
            scenario_id=str(payload["scenario_id"]),
            morphology_style_id=str(payload["morphology_style_id"]),
            operation=str(payload["operation"]),
            eager_trip_generation=bool(payload["eager_trip_generation"]),
            requested_steps=int(payload["requested_steps"]),
            tick_budget_ns=int(payload["tick_budget_ns"]),
            ticks_completed=int(payload["ticks_completed"]),
            worker_pid=int(payload["worker_pid"]),
            city_authority_wall_ns=int(payload["city_authority_wall_ns"]),
            initialization_wall_ns=int(payload["initialization_wall_ns"]),
            runtime_wall_ns=int(payload["runtime_wall_ns"]),
            peak_rss_kib=int(payload["peak_rss_kib"]),
            process_peak_rss_kib=int(payload["process_peak_rss_kib"]),
            node_count=int(payload["node_count"]),
            link_count=int(payload["link_count"]),
            turn_count=int(payload["turn_count"]),
            block_count=int(payload["block_count"]),
            zone_count=int(payload["zone_count"]),
            citizen_count=int(payload["citizen_count"]),
            trip_request_count=int(payload["trip_request_count"]),
            active_agent_capacity=int(payload["active_agent_capacity"]),
            city_stage_wall_ns=_timing_pairs(payload.get("city_stage_wall_ns", ())),
            runtime_stage_wall_ns=_timing_pairs(
                payload.get("runtime_stage_wall_ns", ())
            ),
            city_fingerprint=str(payload["city_fingerprint"]),
        )


@dataclass(frozen=True, slots=True)
class CityScalePerformancePair:
    seed: int
    generation_ratio: float
    peak_rss_ratio: float
    runtime_ratio: float
    legacy_budget_ticks: int
    realistic_budget_ticks: int
    paired_tick_budget_ns: int
    legacy_citizen_count: int
    realistic_citizen_count: int
    legacy_trip_request_count: int
    realistic_trip_request_count: int
    population_gate_pass: bool
    workload_gate_pass: bool
    generation_gate_pass: bool
    peak_rss_gate_pass: bool
    runtime_gate_pass: bool
    tick_progress_gate_pass: bool

    @property
    def all_pass(self) -> bool:
        return bool(
            self.generation_gate_pass
            and self.population_gate_pass
            and self.workload_gate_pass
            and self.peak_rss_gate_pass
            and self.runtime_gate_pass
            and self.tick_progress_gate_pass
        )


@dataclass(frozen=True, slots=True)
class CityScaleStageShare:
    stage_name: str
    seed_shares: tuple[tuple[int, float], ...]
    minimum_share: float
    mean_share: float
    maximum_share: float
    rust_probe_eligible: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "stage_name": self.stage_name,
            "seed_shares": [
                {"seed": seed, "share": share} for seed, share in self.seed_shares
            ],
            "minimum_share": self.minimum_share,
            "mean_share": self.mean_share,
            "maximum_share": self.maximum_share,
            "rust_probe_eligible": self.rust_probe_eligible,
        }


@dataclass(frozen=True, slots=True)
class RealisticCityScaleReport:
    schema_version: str
    claim_status: str
    populations: tuple[int, ...]
    seeds: tuple[int, ...]
    modes: tuple[str, ...]
    num_steps: int
    environment: tuple[tuple[str, str], ...]
    generation_runs: tuple[CityScaleRunResult, ...]
    fixed_runs: tuple[CityScaleRunResult, ...]
    budget_runs: tuple[CityScaleRunResult, ...]
    stage_profile_runs: tuple[CityScaleRunResult, ...]
    performance_pairs: tuple[CityScalePerformancePair, ...]
    stage_shares: tuple[CityScaleStageShare, ...]
    performance_gate_pass: bool
    rust_generation_probe_admitted: bool
    rust_candidate_stage: str | None
    prior_plausibility_gate_status: str
    default_promotion_eligible: bool
    fingerprint: str

    def as_dict(self, *, include_fingerprint: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "claim_status": self.claim_status,
            "populations": list(self.populations),
            "seeds": list(self.seeds),
            "modes": list(self.modes),
            "num_steps": self.num_steps,
            "environment": dict(self.environment),
            "generation_runs": [item.as_dict() for item in self.generation_runs],
            "fixed_runs": [item.as_dict() for item in self.fixed_runs],
            "budget_runs": [item.as_dict() for item in self.budget_runs],
            "stage_profile_runs": [
                item.as_dict() for item in self.stage_profile_runs
            ],
            "performance_pairs": [asdict(item) | {"all_pass": item.all_pass} for item in self.performance_pairs],
            "stage_shares": [item.as_dict() for item in self.stage_shares],
            "performance_gate_pass": self.performance_gate_pass,
            "performance_thresholds": {
                "generation_ratio_max": 2.0,
                "peak_rss_ratio_max": 1.5,
                "runtime_ratio_max": 1.25,
                "paired_budget_tick_ratio_min": 1.0,
            },
            "rust_stage_share_threshold": REALISTIC_CITY_RUST_STAGE_THRESHOLD,
            "rust_generation_probe_admitted": self.rust_generation_probe_admitted,
            "rust_candidate_stage": self.rust_candidate_stage,
            "prior_plausibility_gate_status": self.prior_plausibility_gate_status,
            "default_promotion_eligible": self.default_promotion_eligible,
            "thread_policy": "fresh_process_single_thread_numeric_env",
            "peak_rss_scope": (
                "fresh phase boundary; performance gate uses city_authority phase"
            ),
            "claim_boundary": (
                "local diagnostic only; performance cannot override PR62 plausibility"
            ),
        }
        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> RealisticCityScaleReport:
        environment_payload = payload.get("environment", {})
        if not isinstance(environment_payload, Mapping):
            raise ValueError("scale report environment must be a mapping")
        pair_payload = payload.get("performance_pairs", ())
        stage_payload = payload.get("stage_shares", ())
        if not isinstance(pair_payload, Sequence) or isinstance(
            pair_payload, (str, bytes)
        ):
            raise ValueError("scale report performance_pairs must be a sequence")
        if not isinstance(stage_payload, Sequence) or isinstance(
            stage_payload, (str, bytes)
        ):
            raise ValueError("scale report stage_shares must be a sequence")
        report = cls(
            schema_version=str(payload["schema_version"]),
            claim_status=str(payload["claim_status"]),
            populations=tuple(int(value) for value in payload["populations"]),
            seeds=tuple(int(value) for value in payload["seeds"]),
            modes=tuple(str(value) for value in payload["modes"]),
            num_steps=int(payload["num_steps"]),
            environment=tuple(
                sorted(
                    (str(key), str(value))
                    for key, value in environment_payload.items()
                )
            ),
            generation_runs=_run_results_from_payload(
                payload.get("generation_runs", ())
            ),
            fixed_runs=_run_results_from_payload(payload.get("fixed_runs", ())),
            budget_runs=_run_results_from_payload(payload.get("budget_runs", ())),
            stage_profile_runs=_run_results_from_payload(
                payload.get("stage_profile_runs", ())
            ),
            performance_pairs=tuple(
                CityScalePerformancePair(
                    **{
                        key: value
                        for key, value in dict(item).items()
                        if key != "all_pass"
                    }
                )
                for item in pair_payload
                if isinstance(item, Mapping)
            ),
            stage_shares=tuple(
                _stage_share_from_payload(item)
                for item in stage_payload
                if isinstance(item, Mapping)
            ),
            performance_gate_pass=bool(payload["performance_gate_pass"]),
            rust_generation_probe_admitted=bool(
                payload["rust_generation_probe_admitted"]
            ),
            rust_candidate_stage=(
                str(payload["rust_candidate_stage"])
                if payload.get("rust_candidate_stage") is not None
                else None
            ),
            prior_plausibility_gate_status=str(
                payload["prior_plausibility_gate_status"]
            ),
            default_promotion_eligible=bool(payload["default_promotion_eligible"]),
            fingerprint=str(payload["fingerprint"]),
        )
        expected = _fingerprint(report.as_dict(include_fingerprint=False))
        if expected != report.fingerprint:
            raise ValueError("scale report fingerprint mismatch")
        return report


def run_realistic_city_scale_worker(spec: CityScaleWorkerSpec) -> CityScaleRunResult:
    from .realistic_city_scale_worker import run_realistic_city_scale_worker as _run

    return _run(spec)


def run_realistic_city_scale_subprocess(
    spec: CityScaleWorkerSpec,
    *,
    timeout_seconds: float = 900.0,
) -> CityScaleRunResult:
    from .realistic_city_scale_worker import (
        run_realistic_city_scale_subprocess as _run,
    )

    return _run(spec, timeout_seconds=timeout_seconds)


def run_realistic_city_scale_audit(
    *,
    population_targets: Sequence[int] = REALISTIC_CITY_SCALE_POPULATIONS,
    seeds: Sequence[int] = REALISTIC_CITY_SCALE_SEEDS,
    num_steps: int = REALISTIC_CITY_SCALE_STEPS,
    eager_trip_generation: bool = True,
    minimum_tick_budget_ns: int = 250_000_000,
    timeout_seconds: float = 900.0,
    prior_plausibility_gate_status: str = "failed_pr62",
    worker_runner: Callable[[CityScaleWorkerSpec], CityScaleRunResult] | None = None,
) -> RealisticCityScaleReport:
    populations = _unique_positive_ints(population_targets, "population_targets")
    seed_values = _unique_ints(seeds, "seeds")
    if int(num_steps) < 1:
        raise ValueError("num_steps must be positive")
    if 100_000 not in populations:
        raise ValueError("population_targets must include 100000")
    if int(minimum_tick_budget_ns) < 1:
        raise ValueError("minimum_tick_budget_ns must be positive")

    if worker_runner is None:
        def execute(spec: CityScaleWorkerSpec) -> CityScaleRunResult:
            return run_realistic_city_scale_subprocess(
                spec,
                timeout_seconds=timeout_seconds,
            )
    else:
        execute = worker_runner

    generation_runs: list[CityScaleRunResult] = []
    for population_target in populations:
        for seed in seed_values:
            for mode in REALISTIC_CITY_SCALE_MODES:
                generation_runs.append(
                    execute(
                        CityScaleWorkerSpec(
                            topology_mode=mode,
                            population_target=population_target,
                            seed=seed,
                            operation="city_authority",
                            requested_steps=0,
                            eager_trip_generation=False,
                        )
                    )
                )

    fixed_runs: list[CityScaleRunResult] = []
    for population_target in populations:
        for seed in seed_values:
            for mode in REALISTIC_CITY_SCALE_MODES:
                fixed_runs.append(
                    execute(
                        CityScaleWorkerSpec(
                            topology_mode=mode,
                            population_target=population_target,
                            seed=seed,
                            operation="fixed_steps",
                            requested_steps=num_steps,
                            eager_trip_generation=eager_trip_generation,
                        )
                    )
                )

    stage_profile_runs = [
        execute(
            CityScaleWorkerSpec(
                topology_mode="realistic_synthetic_v1",
                population_target=100_000,
                seed=seed,
                operation="city_stage_profile",
                requested_steps=0,
                eager_trip_generation=False,
            )
        )
        for seed in seed_values
    ]

    fixed_index = {
        (item.topology_mode, item.population_target, item.seed): item
        for item in fixed_runs
    }
    budget_runs: list[CityScaleRunResult] = []
    for seed in seed_values:
        legacy = fixed_index[("standard", 100_000, seed)]
        paired_budget_ns = max(
            int(minimum_tick_budget_ns),
            int(legacy.runtime_wall_ns),
        )
        for mode in REALISTIC_CITY_SCALE_MODES:
            budget_runs.append(
                execute(
                    CityScaleWorkerSpec(
                        topology_mode=mode,
                        population_target=100_000,
                        seed=seed,
                        operation="time_budget",
                        requested_steps=0,
                        tick_budget_ns=paired_budget_ns,
                        eager_trip_generation=eager_trip_generation,
                    )
                )
            )

    return build_realistic_city_scale_report(
        generation_runs=generation_runs,
        fixed_runs=fixed_runs,
        budget_runs=budget_runs,
        stage_profile_runs=stage_profile_runs,
        population_targets=populations,
        seeds=seed_values,
        num_steps=num_steps,
        prior_plausibility_gate_status=prior_plausibility_gate_status,
    )


def build_realistic_city_scale_report(
    *,
    generation_runs: Sequence[CityScaleRunResult],
    fixed_runs: Sequence[CityScaleRunResult],
    budget_runs: Sequence[CityScaleRunResult],
    stage_profile_runs: Sequence[CityScaleRunResult],
    population_targets: Sequence[int],
    seeds: Sequence[int],
    num_steps: int,
    prior_plausibility_gate_status: str = "not_evaluated",
) -> RealisticCityScaleReport:
    populations = _unique_positive_ints(population_targets, "population_targets")
    seed_values = _unique_ints(seeds, "seeds")
    generation = tuple(generation_runs)
    fixed = tuple(fixed_runs)
    budget = tuple(budget_runs)
    stage_profiles = tuple(stage_profile_runs)
    generation_index = _validate_generation_matrix(
        generation,
        populations=populations,
        seeds=seed_values,
    )
    fixed_index = _validate_fixed_matrix(
        fixed,
        populations=populations,
        seeds=seed_values,
        num_steps=int(num_steps),
    )
    budget_index = _validate_budget_matrix(budget, seeds=seed_values)
    stage_profile_index = _validate_stage_profile_matrix(
        stage_profiles,
        seeds=seed_values,
    )

    pairs: list[CityScalePerformancePair] = []
    for seed in seed_values:
        legacy_generation = generation_index[("standard", 100_000, seed)]
        realistic_generation = generation_index[
            ("realistic_synthetic_v1", 100_000, seed)
        ]
        legacy = fixed_index[("standard", 100_000, seed)]
        realistic = fixed_index[("realistic_synthetic_v1", 100_000, seed)]
        legacy_budget = budget_index[("standard", seed)]
        realistic_budget = budget_index[("realistic_synthetic_v1", seed)]
        if legacy_budget.tick_budget_ns != realistic_budget.tick_budget_ns:
            raise ValueError(f"seed {seed} does not use a paired wall budget")
        generation_ratio = _positive_ratio(
            realistic_generation.city_authority_wall_ns,
            legacy_generation.city_authority_wall_ns,
            "city_authority_wall_ns",
        )
        peak_rss_ratio = _positive_ratio(
            realistic_generation.peak_rss_kib,
            legacy_generation.peak_rss_kib,
            "peak_rss_kib",
        )
        runtime_ratio = _positive_ratio(
            realistic.runtime_wall_ns,
            legacy.runtime_wall_ns,
            "runtime_wall_ns",
        )
        pairs.append(
            CityScalePerformancePair(
                seed=seed,
                generation_ratio=generation_ratio,
                peak_rss_ratio=peak_rss_ratio,
                runtime_ratio=runtime_ratio,
                legacy_budget_ticks=legacy_budget.ticks_completed,
                realistic_budget_ticks=realistic_budget.ticks_completed,
                paired_tick_budget_ns=legacy_budget.tick_budget_ns,
                legacy_citizen_count=legacy.citizen_count,
                realistic_citizen_count=realistic.citizen_count,
                legacy_trip_request_count=legacy.trip_request_count,
                realistic_trip_request_count=realistic.trip_request_count,
                population_gate_pass=(
                    legacy.citizen_count == 100_000
                    and realistic.citizen_count == 100_000
                ),
                workload_gate_pass=(
                    legacy.eager_trip_generation
                    and realistic.eager_trip_generation
                    and legacy_budget.eager_trip_generation
                    and realistic_budget.eager_trip_generation
                    and legacy.active_agent_capacity
                    == realistic.active_agent_capacity
                ),
                generation_gate_pass=generation_ratio <= 2.0,
                peak_rss_gate_pass=peak_rss_ratio <= 1.5,
                runtime_gate_pass=runtime_ratio <= 1.25,
                tick_progress_gate_pass=(
                    legacy_budget.ticks_completed > 0
                    and realistic_budget.ticks_completed
                    >= legacy_budget.ticks_completed
                ),
            )
        )

    stage_shares = _build_stage_shares(
        stage_profile_index=stage_profile_index,
        seeds=seed_values,
    )
    admitted = tuple(item for item in stage_shares if item.rust_probe_eligible)
    candidate = (
        sorted(admitted, key=lambda item: (-item.minimum_share, item.stage_name))[0]
        if admitted
        else None
    )
    performance_gate_pass = all(item.all_pass for item in pairs)
    plausibility_status = str(prior_plausibility_gate_status)
    report = RealisticCityScaleReport(
        schema_version=REALISTIC_CITY_SCALE_SCHEMA_VERSION,
        claim_status="diagnostic_scale_gate",
        populations=populations,
        seeds=seed_values,
        modes=REALISTIC_CITY_SCALE_MODES,
        num_steps=int(num_steps),
        environment=_environment_metadata(),
        generation_runs=tuple(
            sorted(
                generation,
                key=lambda item: (
                    item.population_target,
                    item.seed,
                    item.topology_mode,
                ),
            )
        ),
        fixed_runs=tuple(
            sorted(
                fixed,
                key=lambda item: (
                    item.population_target,
                    item.seed,
                    item.topology_mode,
                ),
            )
        ),
        budget_runs=tuple(
            sorted(budget, key=lambda item: (item.seed, item.topology_mode))
        ),
        stage_profile_runs=tuple(
            sorted(stage_profiles, key=lambda item: item.seed)
        ),
        performance_pairs=tuple(pairs),
        stage_shares=stage_shares,
        performance_gate_pass=performance_gate_pass,
        rust_generation_probe_admitted=candidate is not None,
        rust_candidate_stage=(candidate.stage_name if candidate is not None else None),
        prior_plausibility_gate_status=plausibility_status,
        default_promotion_eligible=(
            performance_gate_pass and plausibility_status == "passed"
        ),
        fingerprint="",
    )
    fingerprint = _fingerprint(report.as_dict(include_fingerprint=False))
    return replace(report, fingerprint=fingerprint)


def write_realistic_city_scale_artifacts(
    artifact_prefix: str | Path,
    report: RealisticCityScaleReport,
) -> dict[str, Path]:
    from metroflow.benchmarks.realistic_city_scale_reporting import (
        write_realistic_city_scale_artifacts as _write,
    )

    return _write(artifact_prefix, report)


def load_realistic_city_scale_report(path: str | Path) -> RealisticCityScaleReport:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("scale report JSON root must be a mapping")
    return RealisticCityScaleReport.from_dict(payload)


def _validate_fixed_matrix(
    runs: tuple[CityScaleRunResult, ...],
    *,
    populations: tuple[int, ...],
    seeds: tuple[int, ...],
    num_steps: int,
) -> dict[tuple[str, int, int], CityScaleRunResult]:
    expected = {
        (mode, population, seed)
        for population in populations
        for seed in seeds
        for mode in REALISTIC_CITY_SCALE_MODES
    }
    index: dict[tuple[str, int, int], CityScaleRunResult] = {}
    for item in runs:
        key = (item.topology_mode, item.population_target, item.seed)
        if key in index:
            raise ValueError(f"duplicate fixed-step matrix entry: {key}")
        if item.operation != "fixed_steps" or item.requested_steps != num_steps:
            raise ValueError(f"invalid fixed-step matrix entry: {key}")
        index[key] = item
    if set(index) != expected:
        missing = sorted(expected - set(index))
        extra = sorted(set(index) - expected)
        raise ValueError(
            f"fixed-step matrix mismatch: missing={missing}, extra={extra}"
        )
    if 100_000 not in populations:
        raise ValueError("fixed-step matrix must include population 100000")
    return index


def _validate_generation_matrix(
    runs: tuple[CityScaleRunResult, ...],
    *,
    populations: tuple[int, ...],
    seeds: tuple[int, ...],
) -> dict[tuple[str, int, int], CityScaleRunResult]:
    expected = {
        (mode, population, seed)
        for population in populations
        for seed in seeds
        for mode in REALISTIC_CITY_SCALE_MODES
    }
    index: dict[tuple[str, int, int], CityScaleRunResult] = {}
    for item in runs:
        key = (item.topology_mode, item.population_target, item.seed)
        if key in index:
            raise ValueError(f"duplicate city-authority matrix entry: {key}")
        if item.operation != "city_authority":
            raise ValueError(f"invalid city-authority matrix entry: {key}")
        index[key] = item
    if set(index) != expected:
        missing = sorted(expected - set(index))
        extra = sorted(set(index) - expected)
        raise ValueError(
            f"city-authority matrix mismatch: missing={missing}, extra={extra}"
        )
    return index


def _validate_stage_profile_matrix(
    runs: tuple[CityScaleRunResult, ...],
    *,
    seeds: tuple[int, ...],
) -> dict[int, CityScaleRunResult]:
    index: dict[int, CityScaleRunResult] = {}
    for item in runs:
        if item.seed in index:
            raise ValueError(f"duplicate city-stage profile entry: {item.seed}")
        if (
            item.operation != "city_stage_profile"
            or item.topology_mode != "realistic_synthetic_v1"
            or item.population_target != 100_000
        ):
            raise ValueError(f"invalid city-stage profile entry: {item.seed}")
        index[item.seed] = item
    if set(index) != set(seeds):
        missing = sorted(set(seeds) - set(index))
        extra = sorted(set(index) - set(seeds))
        raise ValueError(
            f"city-stage profile matrix mismatch: missing={missing}, extra={extra}"
        )
    return index


def _validate_budget_matrix(
    runs: tuple[CityScaleRunResult, ...],
    *,
    seeds: tuple[int, ...],
) -> dict[tuple[str, int], CityScaleRunResult]:
    expected = {
        (mode, seed) for seed in seeds for mode in REALISTIC_CITY_SCALE_MODES
    }
    index: dict[tuple[str, int], CityScaleRunResult] = {}
    for item in runs:
        key = (item.topology_mode, item.seed)
        if key in index:
            raise ValueError(f"duplicate time-budget matrix entry: {key}")
        if (
            item.operation != "time_budget"
            or item.population_target != 100_000
            or item.tick_budget_ns <= 0
        ):
            raise ValueError(f"invalid time-budget matrix entry: {key}")
        index[key] = item
    if set(index) != expected:
        missing = sorted(expected - set(index))
        extra = sorted(set(index) - expected)
        raise ValueError(
            f"time-budget matrix mismatch: missing={missing}, extra={extra}"
        )
    return index


def _build_stage_shares(
    *,
    stage_profile_index: Mapping[int, CityScaleRunResult],
    seeds: tuple[int, ...],
) -> tuple[CityScaleStageShare, ...]:
    stage_names = (
        *(name for name, _target in _REALISTIC_STAGE_TARGETS),
        "unattributed_pipeline_overhead",
    )
    rows: list[CityScaleStageShare] = []
    for stage_name in stage_names:
        seed_shares: list[tuple[int, float]] = []
        for seed in seeds:
            run = stage_profile_index[seed]
            measured_stages = dict(run.city_stage_wall_ns)
            if stage_name == "unattributed_pipeline_overhead":
                stage_ns = max(
                    0,
                    run.city_authority_wall_ns - sum(measured_stages.values()),
                )
            else:
                stage_ns = measured_stages.get(stage_name, 0)
            share = _positive_ratio(
                stage_ns,
                run.city_authority_wall_ns,
                f"city_authority_wall_ns seed={seed}",
                numerator_may_be_zero=True,
            )
            seed_shares.append((seed, share))
        shares = tuple(share for _seed, share in seed_shares)
        rows.append(
            CityScaleStageShare(
                stage_name=stage_name,
                seed_shares=tuple(seed_shares),
                minimum_share=min(shares),
                mean_share=sum(shares) / len(shares),
                maximum_share=max(shares),
                rust_probe_eligible=(
                    stage_name in REALISTIC_CITY_RUST_ELIGIBLE_STAGES
                    and min(shares) >= REALISTIC_CITY_RUST_STAGE_THRESHOLD
                ),
            )
        )
    return tuple(rows)


def _positive_ratio(
    numerator: int,
    denominator: int,
    label: str,
    *,
    numerator_may_be_zero: bool = False,
) -> float:
    if int(denominator) <= 0:
        raise ValueError(f"{label} denominator must be positive")
    if int(numerator) < 0 or (int(numerator) == 0 and not numerator_may_be_zero):
        raise ValueError(f"{label} numerator must be positive")
    return float(numerator) / float(denominator)


def _timing_rows(items: Sequence[tuple[str, int]]) -> list[dict[str, object]]:
    return [
        {"stage_name": str(stage_name), "wall_ns": int(wall_ns)}
        for stage_name, wall_ns in items
    ]


def _timing_pairs(payload: object) -> tuple[tuple[str, int], ...]:
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        raise ValueError("timing rows must be a sequence")
    pairs: list[tuple[str, int]] = []
    for item in payload:
        if not isinstance(item, Mapping):
            raise ValueError("timing row must be a mapping")
        pairs.append((str(item["stage_name"]), int(item["wall_ns"])))
    return tuple(pairs)


def _run_results_from_payload(payload: object) -> tuple[CityScaleRunResult, ...]:
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        raise ValueError("scale report runs must be a sequence")
    return tuple(
        CityScaleRunResult.from_dict(item)
        for item in payload
        if isinstance(item, Mapping)
    )


def _stage_share_from_payload(payload: Mapping[str, object]) -> CityScaleStageShare:
    seed_payload = payload.get("seed_shares", ())
    if not isinstance(seed_payload, Sequence) or isinstance(
        seed_payload, (str, bytes)
    ):
        raise ValueError("stage seed_shares must be a sequence")
    return CityScaleStageShare(
        stage_name=str(payload["stage_name"]),
        seed_shares=tuple(
            (int(item["seed"]), float(item["share"]))
            for item in seed_payload
            if isinstance(item, Mapping)
        ),
        minimum_share=float(payload["minimum_share"]),
        mean_share=float(payload["mean_share"]),
        maximum_share=float(payload["maximum_share"]),
        rust_probe_eligible=bool(payload["rust_probe_eligible"]),
    )


def _unique_positive_ints(values: Sequence[int], label: str) -> tuple[int, ...]:
    result = _unique_ints(values, label)
    if any(value < 1 for value in result):
        raise ValueError(f"{label} must contain positive integers")
    return result


def _unique_ints(values: Sequence[int], label: str) -> tuple[int, ...]:
    result = tuple(int(value) for value in values)
    if not result:
        raise ValueError(f"{label} must not be empty")
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must be unique")
    return result


def _fingerprint(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _environment_metadata() -> tuple[tuple[str, str], ...]:
    values = {
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": str(os.cpu_count() or ""),
        "peak_rss_unit": "KiB_linux_ru_maxrss",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }
    return tuple(sorted(values.items()))


def _parse_csv_ints(value: str) -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in value.split(",") if item.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-json", default="", help=argparse.SUPPRESS)
    parser.add_argument("--artifact-prefix")
    parser.add_argument(
        "--populations",
        default=",".join(str(value) for value in REALISTIC_CITY_SCALE_POPULATIONS),
    )
    parser.add_argument(
        "--seeds",
        default=",".join(str(value) for value in REALISTIC_CITY_SCALE_SEEDS),
    )
    parser.add_argument("--num-steps", type=int, default=REALISTIC_CITY_SCALE_STEPS)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--minimum-tick-budget-ms", type=float, default=250.0)
    parser.add_argument(
        "--prior-plausibility-gate-status",
        default="failed_pr62",
    )
    parser.add_argument(
        "--no-eager-trip-generation",
        action="store_true",
    )
    args = parser.parse_args(argv)

    if args.worker_json:
        spec = CityScaleWorkerSpec.from_dict(json.loads(args.worker_json))
        result = run_realistic_city_scale_worker(spec)
        print(json.dumps(result.as_dict(), sort_keys=True, separators=(",", ":")))
        return 0
    if not args.artifact_prefix:
        parser.error("--artifact-prefix is required")

    report = run_realistic_city_scale_audit(
        population_targets=_parse_csv_ints(args.populations),
        seeds=_parse_csv_ints(args.seeds),
        num_steps=args.num_steps,
        eager_trip_generation=not args.no_eager_trip_generation,
        minimum_tick_budget_ns=int(args.minimum_tick_budget_ms * 1_000_000.0),
        timeout_seconds=args.timeout_seconds,
        prior_plausibility_gate_status=args.prior_plausibility_gate_status,
    )
    paths = write_realistic_city_scale_artifacts(args.artifact_prefix, report)
    print(
        json.dumps(
            {
                "paths": {key: str(value) for key, value in paths.items()},
                "performance_gate_pass": report.performance_gate_pass,
                "default_promotion_eligible": report.default_promotion_eligible,
                "rust_generation_probe_admitted": (
                    report.rust_generation_probe_admitted
                ),
                "report_fingerprint": report.fingerprint,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
