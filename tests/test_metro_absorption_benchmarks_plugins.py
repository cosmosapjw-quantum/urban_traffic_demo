from __future__ import annotations

import pytest


def test_benchmark_smoke_runner_returns_report_without_donor_specs() -> None:
    from metroflow.benchmarks import run_benchmark_scenario

    result = run_benchmark_scenario(
        scenario_id="synthetic_smoke",
        seed=41,
        duration_ticks=2,
        smoke=True,
        ui_mode="off",
    )

    assert result["run_summary"]["scenario_id"] == "synthetic_smoke"
    assert result["run_summary"]["duration_ticks"] == 4
    assert result["map_foundation_gate"]["profile"] == "sc020_sc042_map_foundation"
    assert result["version_summary"]["budget_version"] == "v1"
    assert "MetroFlow" not in result["report"]
    assert "Scenario ID" in result["report"]


def test_benchmark_summary_metrics_host_handles_empty_and_positive_durations() -> None:
    import numpy as np

    from metroflow.benchmarks.run import compute_benchmark_summary_metrics_host

    empty = compute_benchmark_summary_metrics_host(
        tick_durations=np.asarray([], dtype=np.float64),
        active_agent_counts=np.asarray([], dtype=np.float64),
    )
    nonempty = compute_benchmark_summary_metrics_host(
        tick_durations=np.asarray([0.5, 1.0, 2.0], dtype=np.float64),
        active_agent_counts=np.asarray([10.0, 20.0, 30.0], dtype=np.float64),
    )

    assert empty == {
        "tick_rate_median": 0.0,
        "tick_rate_p10": 0.0,
        "active_agent_median": 0.0,
        "active_agent_p95": 0.0,
    }
    assert nonempty["tick_rate_median"] == 1.0
    assert nonempty["active_agent_median"] == 20.0
    assert nonempty["active_agent_p95"] == pytest.approx(29.0)


def test_benchmark_report_preserves_route_choice_policy_metadata() -> None:
    from metroflow.benchmarks.reporting import (
        benchmark_report_from_run_summary,
        format_benchmark_report_markdown,
    )

    report = benchmark_report_from_run_summary(
        {
            "scenario_id": "policy-summary",
            "seed": 7,
            "route_path_size_gamma": 1.5,
        }
    )
    markdown = format_benchmark_report_markdown(report)

    assert report.route_path_size_gamma == 1.5
    assert "Route path-size gamma: 1.5" in markdown


def test_runtime_benchmark_suite_report_renders_gpu_gate_metadata() -> None:
    from metroflow.benchmarks.reporting import format_runtime_benchmark_suite_markdown
    from metroflow.metrics.benchmarks import (
        MeasuredRuntimeBenchmarkResult,
        MeasuredRuntimeBenchmarkSuiteResult,
        RuntimeStageTiming,
        format_runtime_gpu_candidate_gate_markdown,
        summarize_runtime_gpu_candidate_gate,
    )

    per_seed_results = tuple(
        MeasuredRuntimeBenchmarkResult(
            name="measured_runtime_spine",
            workload_name="runtime-suite-report",
            wall_clock_ns=1000,
            num_steps=2,
            initial_tick=0,
            final_tick=2,
            active_agent_count=0,
            flow_backend="baseline",
            routing_backend="baseline",
            agent_backend="baseline",
            route_path_size_gamma=0.0,
            routing_copy_boundary_note="numpy baseline",
            agent_copy_boundary_note="python baseline",
            route_candidate_refresh_total=0,
            route_candidate_reuse_total=0,
            dynamic_potential_recompute_total=0,
            dynamic_potential_cache_hits_total=0,
            seed=seed,
            runtime_stage_timings=(
                RuntimeStageTiming("flow_update", 400, 0.4, True),
            ),
            gpu_candidate_stage_names=("flow_update",),
        )
        for seed in (1, 2, 3)
    )
    gate_report = summarize_runtime_gpu_candidate_gate(per_seed_results)
    suite_result = MeasuredRuntimeBenchmarkSuiteResult(
        name="measured_runtime_spine_suite",
        workload_name="runtime-suite-report",
        seed_count=3,
        seeds=(1, 2, 3),
        num_steps=2,
        wall_clock_ns_total=3000,
        per_seed_results=per_seed_results,
        gpu_candidate_gate_report=gate_report,
        gpu_candidate_gate_markdown=format_runtime_gpu_candidate_gate_markdown(gate_report),
    )

    markdown = format_runtime_benchmark_suite_markdown(suite_result)

    assert "Runtime benchmark suite" in markdown
    assert "Workload: runtime-suite-report" in markdown
    assert "Seeds: 1, 2, 3" in markdown
    assert "Per-seed results: 3" in markdown
    assert "Eligible stages: flow_update" in markdown


def test_runtime_benchmark_suite_runner_returns_review_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    from metroflow.benchmarks import run_runtime_benchmark_suite
    from metroflow.benchmarks import run as benchmark_run_module
    from metroflow.metrics.benchmarks import (
        MeasuredRuntimeBenchmarkResult,
        MeasuredRuntimeBenchmarkSuiteConfig,
        MeasuredRuntimeBenchmarkSuiteResult,
        RuntimeStageTiming,
        format_runtime_gpu_candidate_gate_markdown,
        summarize_runtime_gpu_candidate_gate,
    )

    captured_config: list[MeasuredRuntimeBenchmarkSuiteConfig] = []

    def fake_suite_runner(
        config: MeasuredRuntimeBenchmarkSuiteConfig,
    ) -> MeasuredRuntimeBenchmarkSuiteResult:
        captured_config.append(config)
        per_seed_results = tuple(
            MeasuredRuntimeBenchmarkResult(
                name="measured_runtime_spine",
                workload_name=config.workload_name,
                wall_clock_ns=1000,
                num_steps=config.num_steps,
                initial_tick=0,
                final_tick=config.num_steps,
                active_agent_count=0,
                flow_backend="baseline",
                routing_backend="baseline",
                agent_backend="baseline",
                route_path_size_gamma=0.0,
                routing_copy_boundary_note="numpy baseline",
                agent_copy_boundary_note="python baseline",
                route_candidate_refresh_total=0,
                route_candidate_reuse_total=0,
                dynamic_potential_recompute_total=0,
                dynamic_potential_cache_hits_total=0,
                seed=seed,
                runtime_stage_timings=(
                    RuntimeStageTiming("active_agent_update", 350, 0.35, True),
                ),
                gpu_candidate_stage_names=("active_agent_update",),
            )
            for seed in config.seeds
        )
        gate_report = summarize_runtime_gpu_candidate_gate(per_seed_results)
        return MeasuredRuntimeBenchmarkSuiteResult(
            name="measured_runtime_spine_suite",
            workload_name=config.workload_name,
            seed_count=len(config.seeds),
            seeds=config.seeds,
            num_steps=config.num_steps,
            wall_clock_ns_total=sum(result.wall_clock_ns for result in per_seed_results),
            per_seed_results=per_seed_results,
            gpu_candidate_gate_report=gate_report,
            gpu_candidate_gate_markdown=format_runtime_gpu_candidate_gate_markdown(gate_report),
        )

    monkeypatch.setattr(
        benchmark_run_module,
        "run_measured_runtime_spine_benchmark_suite",
        fake_suite_runner,
    )

    result = run_runtime_benchmark_suite(
        workload_name="runner-suite",
        seeds=(11, 12, 13),
        num_steps=5,
    )

    assert captured_config == [
        MeasuredRuntimeBenchmarkSuiteConfig(
            workload_name="runner-suite",
            seeds=(11, 12, 13),
            num_steps=5,
        )
    ]
    assert result["suite_result"].workload_name == "runner-suite"
    assert result["gpu_candidate_gate_report"].gpu_review_eligible_stage_names == (
        "active_agent_update",
    )
    assert "Runtime benchmark suite" in result["report"]
    assert "Eligible stages: active_agent_update" in result["report"]


def test_benchmark_cli_runtime_suite_prints_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from metroflow.benchmarks import run as benchmark_run_module

    captured_calls: list[dict[str, object]] = []

    def fake_runtime_suite(**kwargs: object) -> dict[str, object]:
        captured_calls.append(dict(kwargs))
        return {
            "suite_result": object(),
            "gpu_candidate_gate_report": object(),
            "report": "- Runtime benchmark suite:\n- Eligible stages: flow_update",
        }

    monkeypatch.setattr(
        benchmark_run_module,
        "run_runtime_benchmark_suite",
        fake_runtime_suite,
    )

    exit_code = benchmark_run_module.main(
        [
            "--runtime-suite",
            "--runtime-suite-workload",
            "cli-suite",
            "--runtime-suite-seeds",
            "5,6,7",
            "--runtime-suite-steps",
            "3",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured_calls == [
        {
            "workload_name": "cli-suite",
            "seeds": (5, 6, 7),
            "num_steps": 3,
        }
    ]
    assert "MetroFlow runtime benchmark suite complete." in output
    assert "workload=cli-suite" in output
    assert "seeds=5,6,7" in output
    assert "Eligible stages: flow_update" in output


def test_benchmark_cli_runtime_suite_writes_report_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from metroflow.benchmarks import run as benchmark_run_module

    report_path = tmp_path / "runtime-suite.md"

    def fake_runtime_suite(**kwargs: object) -> dict[str, object]:
        return {
            "suite_result": object(),
            "gpu_candidate_gate_report": object(),
            "report": "- Runtime benchmark suite:\n- Workload: file-suite",
        }

    monkeypatch.setattr(
        benchmark_run_module,
        "run_runtime_benchmark_suite",
        fake_runtime_suite,
    )

    exit_code = benchmark_run_module.main(
        [
            "--runtime-suite",
            "--runtime-suite-workload",
            "file-suite",
            "--runtime-suite-report-path",
            str(report_path),
        ]
    )

    assert exit_code == 0
    assert report_path.read_text(encoding="utf-8") == (
        "- Runtime benchmark suite:\n- Workload: file-suite\n"
    )


def test_benchmark_cli_runtime_suite_rejects_empty_seed_list() -> None:
    from metroflow.benchmarks import run as benchmark_run_module

    with pytest.raises(SystemExit) as exc_info:
        benchmark_run_module.main(
            [
                "--runtime-suite",
                "--runtime-suite-seeds",
                ",",
            ]
        )

    assert exc_info.value.code == 2


def test_policy_plugin_registry_validates_identity_and_duplicate_names() -> None:
    from metroflow.learning.plugins import create_policy_plugin, register_policy_plugin

    class DemoPlugin:
        plugin_name = "demo"
        plugin_version = "v1"
        supports_online_update = True
        supports_batch_context = False

        def init(self, config, seed):
            return {"seed": int(seed)}

        def score_actions(self, plugin_state, routing_context_batch, rng_key):
            return ()

        def update_online(self, plugin_state, experience_batch, rng_key):
            return plugin_state

    registered = register_policy_plugin(DemoPlugin)
    instance = create_policy_plugin("demo")

    assert registered is DemoPlugin
    assert instance.plugin_name == "demo"

    with pytest.raises(ValueError, match="already registered"):
        register_policy_plugin(DemoPlugin)


def test_scenario_presets_expose_map_foundation_and_radical_gate_contracts() -> None:
    from metroflow.sim.scenario_presets import (
        MAP_FOUNDATION_GATE_PRESETS,
        RADICAL_BACKBONE_GATE_PRESET,
        REALISM_VALIDATION_SEEDS,
    )

    assert "map_foundation_weekday_morning" in MAP_FOUNDATION_GATE_PRESETS
    assert MAP_FOUNDATION_GATE_PRESETS["map_foundation_weekday_morning"]["scenario_id"] == (
        "synthetic_100k"
    )
    assert "active_bbox_aspect_ratio" in RADICAL_BACKBONE_GATE_PRESET["required_metrics"]
    assert REALISM_VALIDATION_SEEDS["radical_backbone_gate"] == RADICAL_BACKBONE_GATE_PRESET["seed"]
