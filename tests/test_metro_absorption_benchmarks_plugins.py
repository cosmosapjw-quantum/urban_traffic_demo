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
