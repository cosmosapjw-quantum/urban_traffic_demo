from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from metroflow.benchmarks.realistic_city_scale import (
    REALISTIC_CITY_SCALE_POPULATIONS,
    REALISTIC_CITY_SCALE_SEEDS,
    CityScaleRunResult,
    CityScaleWorkerSpec,
    build_realistic_city_scale_report,
    load_realistic_city_scale_report,
    run_realistic_city_scale_audit,
    run_realistic_city_scale_subprocess,
    write_realistic_city_scale_artifacts,
)


def _run(
    *,
    mode: str,
    seed: int,
    operation: str = "fixed_steps",
    city_ns: int = 100,
    runtime_ns: int = 100,
    rss_kib: int = 100,
    ticks: int = 20,
    budget_ns: int = 0,
    stages: tuple[tuple[str, int], ...] = (),
    citizen_count: int | None = None,
) -> CityScaleRunResult:
    return CityScaleRunResult(
        topology_mode=mode,
        population_target=100_000,
        seed=seed,
        scenario_id="synthetic_100k",
        morphology_style_id=("ring_radial" if mode == "realistic_synthetic_v1" else ""),
        operation=operation,
        eager_trip_generation=True,
        requested_steps=20 if operation == "fixed_steps" else 0,
        tick_budget_ns=budget_ns,
        ticks_completed=ticks,
        worker_pid=seed + (1000 if mode == "standard" else 2000),
        city_authority_wall_ns=city_ns,
        initialization_wall_ns=city_ns + 20,
        runtime_wall_ns=runtime_ns,
        peak_rss_kib=rss_kib,
        process_peak_rss_kib=rss_kib,
        node_count=100,
        link_count=300,
        turn_count=500,
        block_count=50 if mode == "realistic_synthetic_v1" else 0,
        zone_count=4,
        citizen_count=(
            citizen_count
            if citizen_count is not None
            else (100_000 if operation in {"fixed_steps", "time_budget"} else 0)
        ),
        trip_request_count=10,
        active_agent_capacity=20_000,
        city_stage_wall_ns=stages,
        runtime_stage_wall_ns=(),
        city_fingerprint=f"{mode}-{seed}",
    )


def _passing_matrix() -> tuple[
    tuple[CityScaleRunResult, ...],
    tuple[CityScaleRunResult, ...],
    tuple[CityScaleRunResult, ...],
    tuple[CityScaleRunResult, ...],
]:
    generation: list[CityScaleRunResult] = []
    fixed: list[CityScaleRunResult] = []
    budget: list[CityScaleRunResult] = []
    stages: list[CityScaleRunResult] = []
    for seed in (17, 29, 41):
        fixed.append(_run(mode="standard", seed=seed))
        fixed.append(
            _run(
                mode="realistic_synthetic_v1",
                seed=seed,
                runtime_ns=120,
            )
        )
        generation.append(
            _run(
                mode="standard",
                seed=seed,
                operation="city_authority",
            )
        )
        generation.append(
            _run(
                mode="realistic_synthetic_v1",
                seed=seed,
                operation="city_authority",
                city_ns=180,
                rss_kib=140,
            )
        )
        stages.append(
            _run(
                mode="realistic_synthetic_v1",
                seed=seed,
                operation="city_stage_profile",
                city_ns=180,
                stages=(
                    ("hierarchical_street_skeleton", 60),
                    ("continuous_local_fabric", 20),
                    ("planar_blocks", 10),
                ),
            )
        )
        budget.append(
            _run(
                mode="standard",
                seed=seed,
                operation="time_budget",
                ticks=30,
                budget_ns=250,
            )
        )
        budget.append(
            _run(
                mode="realistic_synthetic_v1",
                seed=seed,
                operation="time_budget",
                ticks=31,
                budget_ns=250,
            )
        )
    return tuple(generation), tuple(fixed), tuple(budget), tuple(stages)


def test_scale_contract_fixes_canonical_matrix() -> None:
    assert REALISTIC_CITY_SCALE_POPULATIONS == (1_000, 10_000, 100_000)
    assert REALISTIC_CITY_SCALE_SEEDS == (17, 29, 41)


def test_scale_report_applies_per_seed_gates_and_rust_admission() -> None:
    generation, fixed, budget, stages = _passing_matrix()
    report = build_realistic_city_scale_report(
        generation_runs=generation,
        fixed_runs=fixed,
        budget_runs=budget,
        stage_profile_runs=stages,
        population_targets=(100_000,),
        seeds=(17, 29, 41),
        num_steps=20,
        prior_plausibility_gate_status="failed_pr62",
    )

    assert report.performance_gate_pass is True
    assert report.default_promotion_eligible is False
    assert report.rust_generation_probe_admitted is True
    assert report.rust_candidate_stage == "hierarchical_street_skeleton"
    assert report.prior_plausibility_gate_status == "failed_pr62"
    assert len(report.performance_pairs) == 3
    assert all(pair.generation_ratio == pytest.approx(1.8) for pair in report.performance_pairs)


def test_scale_report_requires_complete_unique_and_paired_matrix() -> None:
    generation, fixed, budget, stages = _passing_matrix()
    with pytest.raises(ValueError, match="fixed-step matrix"):
        build_realistic_city_scale_report(
            generation_runs=generation,
            fixed_runs=fixed[:-1],
            budget_runs=budget,
            stage_profile_runs=stages,
            population_targets=(100_000,),
            seeds=(17, 29, 41),
            num_steps=20,
        )
    with pytest.raises(ValueError, match="duplicate"):
        build_realistic_city_scale_report(
            generation_runs=generation,
            fixed_runs=(*fixed, fixed[0]),
            budget_runs=budget,
            stage_profile_runs=stages,
            population_targets=(100_000,),
            seeds=(17, 29, 41),
            num_steps=20,
        )
    mismatched_budget = tuple(
        _run(
            mode=item.topology_mode,
            seed=item.seed,
            operation="time_budget",
            ticks=item.ticks_completed,
            budget_ns=(251 if item.seed == 17 and item.topology_mode == "realistic_synthetic_v1" else 250),
        )
        for item in budget
    )
    with pytest.raises(ValueError, match="paired wall budget"):
        build_realistic_city_scale_report(
            generation_runs=generation,
            fixed_runs=fixed,
            budget_runs=mismatched_budget,
            stage_profile_runs=stages,
            population_targets=(100_000,),
            seeds=(17, 29, 41),
            num_steps=20,
        )


def test_rust_admission_requires_threshold_on_every_seed() -> None:
    generation, fixed, budget, stages = _passing_matrix()
    revised = tuple(
        _run(
            mode="realistic_synthetic_v1",
            seed=item.seed,
            operation="city_stage_profile",
            city_ns=item.city_authority_wall_ns,
            rss_kib=item.peak_rss_kib,
            stages=(
                (
                    "hierarchical_street_skeleton",
                    20 if item.seed == 41 else 60,
                ),
            ),
        )
        for item in stages
    )
    report = build_realistic_city_scale_report(
        generation_runs=generation,
        fixed_runs=fixed,
        budget_runs=budget,
        stage_profile_runs=revised,
        population_targets=(100_000,),
        seeds=(17, 29, 41),
        num_steps=20,
    )
    assert report.rust_generation_probe_admitted is False
    assert report.rust_candidate_stage is None


def test_scale_report_rejects_vacuous_zero_tick_budget_progress() -> None:
    generation, fixed, budget, stages = _passing_matrix()
    zero_budget_progress = tuple(
        _run(
            mode=item.topology_mode,
            seed=item.seed,
            operation="time_budget",
            ticks=0,
            budget_ns=item.tick_budget_ns,
        )
        for item in budget
    )
    report = build_realistic_city_scale_report(
        generation_runs=generation,
        fixed_runs=fixed,
        budget_runs=zero_budget_progress,
        stage_profile_runs=stages,
        population_targets=(100_000,),
        seeds=(17, 29, 41),
        num_steps=20,
    )
    assert report.performance_gate_pass is False
    assert all(not item.tick_progress_gate_pass for item in report.performance_pairs)


def test_scale_report_fails_when_requested_100k_population_is_not_realized() -> None:
    generation, fixed, budget, stages = _passing_matrix()
    underfilled = tuple(
        _run(
            mode=item.topology_mode,
            seed=item.seed,
            city_ns=item.city_authority_wall_ns,
            runtime_ns=item.runtime_wall_ns,
            rss_kib=item.peak_rss_kib,
            citizen_count=62_500,
        )
        for item in fixed
    )
    report = build_realistic_city_scale_report(
        generation_runs=generation,
        fixed_runs=underfilled,
        budget_runs=budget,
        stage_profile_runs=stages,
        population_targets=(100_000,),
        seeds=(17, 29, 41),
        num_steps=20,
    )
    assert report.performance_gate_pass is False
    assert all(not item.population_gate_pass for item in report.performance_pairs)


def test_scale_artifacts_round_trip_without_preview_payload(tmp_path: Path) -> None:
    generation, fixed, budget, stages = _passing_matrix()
    report = build_realistic_city_scale_report(
        generation_runs=generation,
        fixed_runs=fixed,
        budget_runs=budget,
        stage_profile_runs=stages,
        population_targets=(100_000,),
        seeds=(17, 29, 41),
        num_steps=20,
        prior_plausibility_gate_status="failed_pr62",
    )
    paths = write_realistic_city_scale_artifacts(tmp_path / "scale", report)

    assert set(paths) == {"json", "markdown", "html", "manifest"}
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert payload["fingerprint"] == report.fingerprint
    assert payload["claim_status"] == "diagnostic_scale_gate"
    assert payload["default_promotion_eligible"] is False
    assert "preview" not in paths["json"].read_text(encoding="utf-8").lower()
    assert manifest["report_fingerprint"] == report.fingerprint
    assert report.fingerprint in paths["markdown"].read_text(encoding="utf-8")
    assert "PR62" in paths["html"].read_text(encoding="utf-8")
    assert load_realistic_city_scale_report(paths["json"]) == report

    tampered = json.loads(paths["json"].read_text(encoding="utf-8"))
    tampered["performance_gate_pass"] = not tampered["performance_gate_pass"]
    paths["json"].write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        load_realistic_city_scale_report(paths["json"])


def test_scale_worker_runs_in_fresh_process() -> None:
    result = run_realistic_city_scale_subprocess(
        CityScaleWorkerSpec(
            topology_mode="standard",
            population_target=16,
            seed=17,
            operation="fixed_steps",
            requested_steps=1,
            eager_trip_generation=False,
        ),
        timeout_seconds=120.0,
    )
    assert result.worker_pid != os.getpid()
    assert result.operation == "fixed_steps"
    assert result.ticks_completed == 1
    assert result.initialization_wall_ns >= result.city_authority_wall_ns > 0
    assert result.peak_rss_kib > 0


def test_scale_audit_orchestrates_separate_phases_and_paired_budget() -> None:
    seen: list[CityScaleWorkerSpec] = []

    def fake_worker(spec: CityScaleWorkerSpec) -> CityScaleRunResult:
        seen.append(spec)
        stages = (
            (("hierarchical_street_skeleton", 60),)
            if spec.operation == "city_stage_profile"
            else ()
        )
        return _run(
            mode=spec.topology_mode,
            seed=spec.seed,
            operation=spec.operation,
            city_ns=(180 if spec.topology_mode == "realistic_synthetic_v1" else 100),
            runtime_ns=(120 if spec.topology_mode == "realistic_synthetic_v1" else 100),
            rss_kib=(140 if spec.topology_mode == "realistic_synthetic_v1" else 100),
            ticks=(31 if spec.topology_mode == "realistic_synthetic_v1" else 30),
            budget_ns=spec.tick_budget_ns,
            stages=stages,
        )

    report = run_realistic_city_scale_audit(
        population_targets=(100_000,),
        seeds=(17,),
        num_steps=20,
        minimum_tick_budget_ns=250,
        worker_runner=fake_worker,
    )

    assert [item.operation for item in seen].count("city_authority") == 2
    assert [item.operation for item in seen].count("fixed_steps") == 2
    assert [item.operation for item in seen].count("city_stage_profile") == 1
    assert [item.operation for item in seen].count("time_budget") == 2
    assert {item.tick_budget_ns for item in seen if item.operation == "time_budget"} == {250}
    assert report.performance_gate_pass is True


def test_scale_import_does_not_eagerly_load_accelerators() -> None:
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, sys; "
                "import metroflow.benchmarks.realistic_city_scale; "
                "print(json.dumps(sorted(name for name in sys.modules "
                "if name == 'jax' or name.startswith('jax.') or "
                "name == 'torch' or name.startswith('torch.') or "
                "name == '_metroflow_rust')))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(probe.stdout) == []
