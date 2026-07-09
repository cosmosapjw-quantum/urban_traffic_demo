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


def test_runtime_benchmark_suite_report_dict_preserves_machine_readable_gate_metadata() -> None:
    from metroflow.benchmarks.reporting import runtime_benchmark_suite_to_dict
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
            workload_name="runtime-suite-json",
            wall_clock_ns=1000 + seed,
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
                RuntimeStageTiming("flow_update", 450, 0.45, True),
            ),
            gpu_candidate_stage_names=("flow_update",),
        )
        for seed in (1, 2, 3)
    )
    gate_report = summarize_runtime_gpu_candidate_gate(per_seed_results)
    suite_result = MeasuredRuntimeBenchmarkSuiteResult(
        name="measured_runtime_spine_suite",
        workload_name="runtime-suite-json",
        seed_count=3,
        seeds=(1, 2, 3),
        num_steps=2,
        wall_clock_ns_total=3006,
        per_seed_results=per_seed_results,
        gpu_candidate_gate_report=gate_report,
        gpu_candidate_gate_markdown=format_runtime_gpu_candidate_gate_markdown(gate_report),
    )

    payload = runtime_benchmark_suite_to_dict(suite_result)

    assert payload["name"] == "measured_runtime_spine_suite"
    assert payload["workload_name"] == "runtime-suite-json"
    assert payload["seeds"] == [1, 2, 3]
    assert payload["per_seed_results"][0]["runtime_stage_timings"][0] == {
        "stage_name": "flow_update",
        "wall_clock_ns": 450,
        "wall_time_share": 0.45,
        "gpu_candidate": True,
    }
    assert payload["gpu_candidate_gate_report"]["gpu_review_eligible_stage_names"] == [
        "flow_update",
    ]


def test_runtime_benchmark_suite_html_renders_stage_gate_metadata() -> None:
    from metroflow.benchmarks.reporting import render_runtime_benchmark_suite_html

    html = render_runtime_benchmark_suite_html(
        {
            "name": "measured_runtime_spine_suite",
            "workload_name": "runtime-suite-html",
            "seeds": [1, 2, 3],
            "seed_count": 3,
            "num_steps": 2,
            "wall_clock_ns_total": 3000,
            "per_seed_results": [
                {
                    "seed": 1,
                    "flow_backend": "baseline",
                    "routing_backend": "baseline",
                    "agent_backend": "baseline",
                    "wall_clock_ns": 1000,
                }
            ],
            "gpu_candidate_gate_report": {
                "gpu_review_eligible_stage_names": ["flow_update"],
                "stage_summaries": [
                    {
                        "stage_name": "flow_update",
                        "candidate_run_count": 3,
                        "deterministic_run_count": 3,
                        "mean_wall_time_share": 0.45,
                        "min_wall_time_share": 0.44,
                        "max_wall_time_share": 0.46,
                        "max_wall_clock_ns": 900,
                        "gpu_review_eligible": True,
                    }
                ],
            },
        }
    )

    assert "<main data-runtime-benchmark-suite=" in html
    assert "Runtime Benchmark Suite" in html
    assert "runtime-suite-html" in html
    assert "<td>flow_update</td>" in html
    assert "<td>yes</td>" in html
    assert "baseline / baseline / baseline" in html


def test_runtime_acceleration_candidate_report_flags_gpu_nn_fit_and_overlap() -> None:
    from metroflow.benchmarks.reporting import runtime_acceleration_candidate_report

    payload = {
        "workload_name": "eager-gpu-nn-review",
        "eager_trip_generation": True,
        "gpu_candidate_gate_report": {
            "gpu_review_eligible_stage_names": [
                "route_candidate_refresh",
                "active_agent_update",
            ],
            "stage_summaries": [
                {
                    "stage_name": "route_candidate_refresh",
                    "candidate_run_count": 3,
                    "deterministic_run_count": 3,
                    "mean_wall_time_share": 0.50,
                    "min_wall_time_share": 0.49,
                    "max_wall_time_share": 0.51,
                    "max_wall_clock_ns": 900,
                    "gpu_review_eligible": True,
                },
                {
                    "stage_name": "dynamic_potential_recompute",
                    "candidate_run_count": 0,
                    "deterministic_run_count": 3,
                    "mean_wall_time_share": 0.20,
                    "min_wall_time_share": 0.19,
                    "max_wall_time_share": 0.21,
                    "max_wall_clock_ns": 500,
                    "gpu_review_eligible": False,
                },
                {
                    "stage_name": "active_agent_update",
                    "candidate_run_count": 3,
                    "deterministic_run_count": 3,
                    "mean_wall_time_share": 0.42,
                    "min_wall_time_share": 0.40,
                    "max_wall_time_share": 0.43,
                    "max_wall_clock_ns": 700,
                    "gpu_review_eligible": True,
                },
            ],
        },
    }

    report = runtime_acceleration_candidate_report(payload)
    candidates = {
        candidate["stage_name"]: candidate
        for candidate in report["stage_candidates"]
    }

    assert report["report_type"] == "runtime_acceleration_candidate_report_v1"
    assert report["eager_trip_generation"] is True
    assert report["timing_overlap_warning"] is True
    assert candidates["route_candidate_refresh"]["nn_surrogate_fit"] == "high"
    assert candidates["route_candidate_refresh"]["jax_gpu_fit"] == "medium"
    assert candidates["active_agent_update"]["rust_cpu_fit"] == "high"
    assert candidates["active_agent_update"]["nn_surrogate_fit"] == "medium"
    assert candidates["dynamic_potential_recompute"]["nn_surrogate_fit"] == "high"


def test_runtime_acceleration_candidate_report_profiles_nested_stage_fits() -> None:
    from metroflow.benchmarks.reporting import runtime_acceleration_candidate_report

    report = runtime_acceleration_candidate_report(
        {
            "workload_name": "nested-gpu-nn-review",
            "gpu_candidate_gate_report": {
                "gpu_review_eligible_stage_names": [
                    "route_candidate_path_build",
                    "active_agent_movement",
                ],
                "stage_summaries": [
                    {
                        "stage_name": "route_candidate_potential",
                        "mean_wall_time_share": 0.20,
                        "max_wall_time_share": 0.21,
                        "max_wall_clock_ns": 200,
                    },
                    {
                        "stage_name": "route_candidate_path_build",
                        "mean_wall_time_share": 0.36,
                        "max_wall_time_share": 0.38,
                        "max_wall_clock_ns": 360,
                        "gpu_review_eligible": True,
                    },
                    {
                        "stage_name": "route_candidate_metadata",
                        "mean_wall_time_share": 0.05,
                        "max_wall_time_share": 0.06,
                        "max_wall_clock_ns": 50,
                    },
                    {
                        "stage_name": "active_agent_allocation",
                        "mean_wall_time_share": 0.08,
                        "max_wall_time_share": 0.09,
                        "max_wall_clock_ns": 80,
                    },
                    {
                        "stage_name": "active_agent_candidate_selection",
                        "mean_wall_time_share": 0.33,
                        "max_wall_time_share": 0.34,
                        "max_wall_clock_ns": 330,
                        "gpu_review_eligible": True,
                    },
                    {
                        "stage_name": "active_agent_pool_write",
                        "mean_wall_time_share": 0.04,
                        "max_wall_time_share": 0.05,
                        "max_wall_clock_ns": 40,
                    },
                    {
                        "stage_name": "active_agent_pool_array_write",
                        "mean_wall_time_share": 0.07,
                        "max_wall_time_share": 0.08,
                        "max_wall_clock_ns": 80,
                    },
                    {
                        "stage_name": "active_agent_plugin_memory_write",
                        "mean_wall_time_share": 0.31,
                        "max_wall_time_share": 0.32,
                        "max_wall_clock_ns": 320,
                        "gpu_review_eligible": True,
                    },
                    {
                        "stage_name": "active_agent_movement",
                        "mean_wall_time_share": 0.34,
                        "max_wall_time_share": 0.35,
                        "max_wall_clock_ns": 340,
                        "gpu_review_eligible": True,
                    },
                ],
            },
        }
    )
    candidates = {
        candidate["stage_name"]: candidate
        for candidate in report["stage_candidates"]
    }

    assert candidates["route_candidate_potential"]["nn_surrogate_fit"] == "high"
    assert candidates["route_candidate_path_build"]["rust_cpu_fit"] == "high"
    assert candidates["route_candidate_path_build"]["nn_surrogate_fit"] == "medium"
    assert candidates["route_candidate_metadata"]["jax_gpu_fit"] == "medium"
    assert candidates["active_agent_allocation"]["nn_surrogate_fit"] == "medium"
    assert candidates["active_agent_candidate_selection"]["nn_surrogate_fit"] == "high"
    assert candidates["active_agent_candidate_selection"]["jax_gpu_fit"] == "medium"
    assert candidates["active_agent_pool_write"]["rust_cpu_fit"] == "high"
    assert candidates["active_agent_pool_write"]["nn_surrogate_fit"] == "low"
    assert candidates["active_agent_pool_array_write"]["rust_cpu_fit"] == "high"
    assert candidates["active_agent_pool_array_write"]["jax_gpu_fit"] == "low"
    assert candidates["active_agent_plugin_memory_write"]["rust_cpu_fit"] == "medium"
    assert candidates["active_agent_plugin_memory_write"]["nn_surrogate_fit"] == "low"
    assert candidates["active_agent_movement"]["rust_cpu_fit"] == "high"
    assert candidates["active_agent_movement"]["jax_gpu_fit"] == "low"


def test_runtime_benchmark_suite_html_renders_acceleration_candidate_report() -> None:
    from metroflow.benchmarks.reporting import render_runtime_benchmark_suite_html

    html = render_runtime_benchmark_suite_html(
        {
            "name": "measured_runtime_spine_suite",
            "workload_name": "runtime-suite-acceleration",
            "eager_trip_generation": True,
            "seeds": [1, 2, 3],
            "seed_count": 3,
            "num_steps": 2,
            "wall_clock_ns_total": 3000,
            "per_seed_results": [],
            "gpu_candidate_gate_report": {
                "gpu_review_eligible_stage_names": ["route_candidate_refresh"],
                "stage_summaries": [
                    {
                        "stage_name": "route_candidate_refresh",
                        "candidate_run_count": 3,
                        "deterministic_run_count": 3,
                        "mean_wall_time_share": 0.50,
                        "min_wall_time_share": 0.49,
                        "max_wall_time_share": 0.51,
                        "max_wall_clock_ns": 900,
                        "gpu_review_eligible": True,
                    }
                ],
            },
        }
    )

    assert "Acceleration Candidate Review" in html
    assert "<td>route_candidate_refresh</td>" in html
    assert "<td>medium</td>" in html
    assert "<td>high</td>" in html


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
        eager_trip_generation=True,
    )

    assert captured_config == [
        MeasuredRuntimeBenchmarkSuiteConfig(
            workload_name="runner-suite",
            seeds=(11, 12, 13),
            num_steps=5,
            eager_trip_generation=True,
        )
    ]
    assert result["suite_result"].workload_name == "runner-suite"
    assert result["report_data"]["workload_name"] == "runner-suite"
    assert result["report_data"]["seeds"] == [11, 12, 13]
    assert result["report_data"]["eager_trip_generation"] is True
    assert result["report_data"]["acceleration_candidate_report"]["eager_trip_generation"] is True
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
            "eager_trip_generation": False,
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


def test_benchmark_cli_runtime_suite_writes_json_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import json

    from metroflow.benchmarks import run as benchmark_run_module

    json_path = tmp_path / "runtime-suite.json"

    def fake_runtime_suite(**kwargs: object) -> dict[str, object]:
        return {
            "suite_result": object(),
            "gpu_candidate_gate_report": object(),
            "report": "- Runtime benchmark suite:\n- Workload: json-suite",
            "report_data": {
                "name": "measured_runtime_spine_suite",
                "workload_name": "json-suite",
                "seeds": [8, 9, 10],
            },
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
            "json-suite",
            "--runtime-suite-json-path",
            str(json_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(json_path.read_text(encoding="utf-8")) == {
        "name": "measured_runtime_spine_suite",
        "seeds": [8, 9, 10],
        "workload_name": "json-suite",
    }


def test_benchmark_cli_runtime_suite_writes_html_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from metroflow.benchmarks import run as benchmark_run_module

    html_path = tmp_path / "runtime-suite.html"

    def fake_runtime_suite(**kwargs: object) -> dict[str, object]:
        return {
            "suite_result": object(),
            "gpu_candidate_gate_report": object(),
            "report": "- Runtime benchmark suite:\n- Workload: html-suite",
            "report_data": {
                "name": "measured_runtime_spine_suite",
                "workload_name": "html-suite",
                "seeds": [8, 9, 10],
                "seed_count": 3,
                "num_steps": 1,
                "wall_clock_ns_total": 3000,
                "per_seed_results": [
                    {
                        "seed": 8,
                        "flow_backend": "baseline",
                        "routing_backend": "baseline",
                        "agent_backend": "baseline",
                        "wall_clock_ns": 1000,
                    }
                ],
                "gpu_candidate_gate_report": {
                    "gpu_review_eligible_stage_names": [],
                    "stage_summaries": [],
                },
            },
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
            "html-suite",
            "--runtime-suite-html-path",
            str(html_path),
        ]
    )

    html = html_path.read_text(encoding="utf-8")

    assert exit_code == 0
    assert "<main data-runtime-benchmark-suite=" in html
    assert "html-suite" in html
    assert "baseline / baseline / baseline" in html


def test_runtime_benchmark_suite_artifact_bundle_writes_manifest(tmp_path) -> None:
    import json

    from metroflow.benchmarks.run import write_runtime_benchmark_suite_artifact_bundle

    prefix = tmp_path / "runtime-suite"
    paths = write_runtime_benchmark_suite_artifact_bundle(
        {
            "report": "- Runtime benchmark suite:\n- Workload: bundle-suite",
            "report_data": {
                "name": "measured_runtime_spine_suite",
                "workload_name": "bundle-suite",
                "seeds": [1, 2, 3],
                "seed_count": 3,
                "num_steps": 2,
                "eager_trip_generation": True,
                "wall_clock_ns_total": 3000,
                "per_seed_results": [
                    {
                        "seed": 1,
                        "flow_backend": "baseline",
                        "routing_backend": "baseline",
                        "agent_backend": "baseline",
                        "wall_clock_ns": 1000,
                    }
                ],
                "gpu_candidate_gate_report": {
                    "gpu_review_eligible_stage_names": [
                        "route_candidate_refresh",
                        "active_agent_update",
                    ],
                    "stage_summaries": [
                        {
                            "stage_name": "route_candidate_refresh",
                            "candidate_run_count": 3,
                            "deterministic_run_count": 3,
                            "mean_wall_time_share": 0.50,
                            "min_wall_time_share": 0.49,
                            "max_wall_time_share": 0.51,
                            "max_wall_clock_ns": 900,
                            "gpu_review_eligible": True,
                        },
                        {
                            "stage_name": "dynamic_potential_recompute",
                            "candidate_run_count": 0,
                            "deterministic_run_count": 3,
                            "mean_wall_time_share": 0.20,
                            "min_wall_time_share": 0.19,
                            "max_wall_time_share": 0.21,
                            "max_wall_clock_ns": 500,
                            "gpu_review_eligible": False,
                        },
                        {
                            "stage_name": "active_agent_update",
                            "candidate_run_count": 3,
                            "deterministic_run_count": 3,
                            "mean_wall_time_share": 0.42,
                            "min_wall_time_share": 0.40,
                            "max_wall_time_share": 0.43,
                            "max_wall_clock_ns": 700,
                            "gpu_review_eligible": True,
                        },
                    ],
                },
            },
        },
        output_prefix=prefix,
    )

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))

    assert paths["markdown"] == tmp_path / "runtime-suite.md"
    assert paths["json"] == tmp_path / "runtime-suite.json"
    assert paths["html"] == tmp_path / "runtime-suite.html"
    assert paths["manifest"] == tmp_path / "runtime-suite.manifest.json"
    assert paths["markdown"].read_text(encoding="utf-8") == (
        "- Runtime benchmark suite:\n- Workload: bundle-suite\n"
    )
    assert json.loads(paths["json"].read_text(encoding="utf-8"))["seeds"] == [1, 2, 3]
    assert "<main data-runtime-benchmark-suite=" in paths["html"].read_text(encoding="utf-8")
    assert manifest["artifact_format_version"] == "runtime_suite_bundle_v1"
    assert manifest["workload_name"] == "bundle-suite"
    assert manifest["eager_trip_generation"] is True
    assert manifest["gpu_review_eligible_stage_names"] == [
        "route_candidate_refresh",
        "active_agent_update",
    ]
    assert manifest["timing_overlap_warning"] is True
    assert manifest["jax_gpu_candidate_stage_names"] == ["route_candidate_refresh"]
    assert manifest["nn_surrogate_candidate_stage_names"] == [
        "route_candidate_refresh",
        "dynamic_potential_recompute",
        "active_agent_update",
    ]
    assert manifest["rust_cpu_candidate_stage_names"] == [
        "route_candidate_refresh",
        "dynamic_potential_recompute",
        "active_agent_update",
    ]
    assert manifest["jax_gpu_review_ready_stage_names"] == ["route_candidate_refresh"]
    assert manifest["nn_surrogate_review_ready_stage_names"] == [
        "route_candidate_refresh",
        "active_agent_update",
    ]
    assert manifest["rust_cpu_review_ready_stage_names"] == [
        "route_candidate_refresh",
        "active_agent_update",
    ]


def test_benchmark_cli_runtime_suite_writes_artifact_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import json

    from metroflow.benchmarks import run as benchmark_run_module

    prefix = tmp_path / "runtime-suite"

    def fake_runtime_suite(**kwargs: object) -> dict[str, object]:
        return {
            "suite_result": object(),
            "gpu_candidate_gate_report": object(),
            "report": "- Runtime benchmark suite:\n- Workload: cli-bundle",
            "report_data": {
                "name": "measured_runtime_spine_suite",
                "workload_name": "cli-bundle",
                "seeds": [4, 5, 6],
                "seed_count": 3,
                "num_steps": 1,
                "wall_clock_ns_total": 3000,
                "per_seed_results": [],
                "gpu_candidate_gate_report": {
                    "gpu_review_eligible_stage_names": [],
                    "stage_summaries": [],
                },
            },
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
            "cli-bundle",
            "--runtime-suite-artifact-prefix",
            str(prefix),
        ]
    )

    manifest_path = tmp_path / "runtime-suite.manifest.json"

    assert exit_code == 0
    assert (tmp_path / "runtime-suite.md").exists()
    assert (tmp_path / "runtime-suite.json").exists()
    assert (tmp_path / "runtime-suite.html").exists()
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["artifact_paths"] == {
        "html": str(tmp_path / "runtime-suite.html"),
        "json": str(tmp_path / "runtime-suite.json"),
        "manifest": str(manifest_path),
        "markdown": str(tmp_path / "runtime-suite.md"),
    }


def test_benchmark_cli_runtime_suite_passes_eager_trip_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.benchmarks import run as benchmark_run_module

    captured_calls: list[dict[str, object]] = []

    def fake_runtime_suite(**kwargs: object) -> dict[str, object]:
        captured_calls.append(dict(kwargs))
        return {
            "suite_result": object(),
            "gpu_candidate_gate_report": object(),
            "report": "- Runtime benchmark suite:\n- Workload: eager-suite",
            "report_data": {
                "name": "measured_runtime_spine_suite",
                "workload_name": "eager-suite",
                "seeds": [1, 2, 3],
                "seed_count": 3,
                "num_steps": 1,
                "wall_clock_ns_total": 3000,
                "per_seed_results": [],
                "gpu_candidate_gate_report": {
                    "gpu_review_eligible_stage_names": [],
                    "stage_summaries": [],
                },
            },
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
            "eager-suite",
            "--runtime-suite-eager-trip-generation",
        ]
    )

    assert exit_code == 0
    assert captured_calls[0]["eager_trip_generation"] is True


def test_benchmark_cli_runtime_suite_passes_routing_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.benchmarks import run as benchmark_run_module

    captured_calls: list[dict[str, object]] = []

    def fake_runtime_suite(**kwargs: object) -> dict[str, object]:
        captured_calls.append(dict(kwargs))
        return {
            "suite_result": object(),
            "gpu_candidate_gate_report": object(),
            "report": "- Runtime benchmark suite:\n- Workload: rust-routing-suite",
            "report_data": {
                "name": "measured_runtime_spine_suite",
                "workload_name": "rust-routing-suite",
                "seeds": [1, 2, 3],
                "seed_count": 3,
                "num_steps": 1,
                "wall_clock_ns_total": 3000,
                "per_seed_results": [],
                "gpu_candidate_gate_report": {
                    "gpu_review_eligible_stage_names": [],
                    "stage_summaries": [],
                },
            },
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
            "rust-routing-suite",
            "--runtime-suite-routing-backend",
            "rust_cpu",
        ]
    )

    assert exit_code == 0
    assert captured_calls[0]["routing_backend"] == "rust_cpu"


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
