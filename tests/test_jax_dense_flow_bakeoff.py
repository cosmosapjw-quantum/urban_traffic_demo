from __future__ import annotations

import importlib.util
from dataclasses import replace
import subprocess
import sys

import numpy as np
import pytest


def test_jax_flow_backend_import_is_lazy() -> None:
    code = """
import sys
import metroflow.backends.jax_flow
assert 'jax' not in sys.modules
assert 'jax.numpy' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_device_chunk_matches_numpy_when_jax_is_available() -> None:
    if importlib.util.find_spec("jax") is None:
        pytest.skip("metroflow[jax] is not installed")

    from metroflow.backends.jax_flow import run_dense_flow_jax
    from metroflow.benchmarks.dense_flow_workload import (
        build_dense_flow_jax_inputs,
        build_dense_flow_scale_state,
        flow_output_arrays,
        max_abs_flow_output_diff,
        run_flow_update_steps,
    )

    link_state, node_state = build_dense_flow_scale_state(
        link_count=16,
        turns_per_link=2,
        seed=11,
    )
    expected_link, expected_node, _ = run_flow_update_steps(
        link_state,
        node_state,
        num_steps=3,
        flow_backend="baseline",
    )
    result = run_dense_flow_jax(
        **build_dense_flow_jax_inputs(link_state, node_state),
        num_steps=3,
        execution_mode="device_chunk",
        require_gpu=False,
    )

    assert result.execution_mode == "device_chunk"
    assert result.num_steps == 3
    assert result.first_call_wall_ns > 0
    assert result.steady_state_wall_ns > 0
    assert max_abs_flow_output_diff(
        flow_output_arrays(expected_link, expected_node),
        result.output,
    ) <= 1e-4


def test_device_chunk_matches_zero_capacity_and_zero_base_cost_semantics() -> None:
    if importlib.util.find_spec("jax") is None:
        pytest.skip("metroflow[jax] is not installed")

    from metroflow.backends.jax_flow import run_dense_flow_jax
    from metroflow.benchmarks.dense_flow_workload import (
        build_dense_flow_jax_inputs,
        build_dense_flow_scale_state,
        flow_output_arrays,
        max_abs_flow_output_diff,
        run_flow_update_steps,
    )

    link_state, node_state = build_dense_flow_scale_state(
        link_count=4,
        turns_per_link=1,
        seed=3,
    )
    queue = link_state.queue_vehicles.copy()
    capacity = link_state.capacity_veh_per_tick.copy()
    base_cost = np.asarray(
        link_state.metadata["free_flow_travel_time_cost"],
        dtype=np.float32,
    ).copy()
    queue[0] = 1.0
    capacity[0] = 0.0
    base_cost[0] = 0.0
    link_state = replace(
        link_state,
        queue_vehicles=queue,
        capacity_veh_per_tick=capacity,
        metadata={"free_flow_travel_time_cost": base_cost},
    )
    expected_link, expected_node, _ = run_flow_update_steps(
        link_state,
        node_state,
        num_steps=2,
        flow_backend="baseline",
    )
    result = run_dense_flow_jax(
        **build_dense_flow_jax_inputs(link_state, node_state),
        num_steps=2,
        execution_mode="device_chunk",
        require_gpu=False,
    )
    assert max_abs_flow_output_diff(
        flow_output_arrays(expected_link, expected_node),
        result.output,
    ) <= 1e-4


def test_dense_flow_diff_fails_closed_for_nonfinite_or_integer_drift() -> None:
    from metroflow.benchmarks.dense_flow_workload import max_abs_flow_output_diff

    assert np.isinf(
        max_abs_flow_output_diff(
            {"value": np.asarray([0.0], dtype=np.float32)},
            {"value": np.asarray([np.nan], dtype=np.float32)},
        )
    )
    assert np.isinf(
        max_abs_flow_output_diff(
            {"value": np.asarray([1], dtype=np.int32)},
            {"value": np.asarray([2], dtype=np.int32)},
        )
    )


def test_gpu_bakeoff_admission_requires_warm_first_call_copy_parity_and_three_seeds() -> None:
    from metroflow.benchmarks.gpu_flow_bakeoff import (
        DenseFlowGpuBakeoffConfig,
        DenseFlowGpuBakeoffRun,
        summarize_dense_flow_gpu_bakeoff,
    )

    config = DenseFlowGpuBakeoffConfig(
        workload_name="fixture",
        link_counts=(16_384,),
        seeds=(41, 42, 43),
        num_steps=512,
        turns_per_link=3,
    )
    runs = tuple(
        DenseFlowGpuBakeoffRun(
            link_count=16_384,
            turn_count=49_152,
            seed=seed,
            num_steps=512,
            baseline_wall_ns=500_000_000,
            input_copy_wall_ns=2_000_000,
            first_call_wall_ns=300_000_000,
            steady_state_wall_ns=40_000_000,
            output_copy_wall_ns=2_000_000,
            max_abs_diff=0.0005,
            device_platform="gpu",
            device_kind="fixture-gpu",
            jax_version="fixture",
        )
        for seed in config.seeds
    )
    result = summarize_dense_flow_gpu_bakeoff(config, runs)

    assert result.runtime_flow_backend_authorized is False
    assert result.persistent_device_chunk_review_ready_link_counts == (16_384,)
    assert (
        result.size_summaries[0].minimum_warm_first_call_plus_copy_estimate_speedup
        > 1.0
    )
    assert result.size_summaries[0].maximum_abs_diff <= 1e-3

    rejected = summarize_dense_flow_gpu_bakeoff(
        config,
        runs[:-1]
        + (replace(runs[-1], max_abs_diff=0.01),),
    )
    assert rejected.persistent_device_chunk_review_ready_link_counts == ()
    with pytest.raises(ValueError, match="num_steps"):
        summarize_dense_flow_gpu_bakeoff(
            config,
            (replace(runs[0], num_steps=511),) + runs[1:],
        )


def test_gpu_bakeoff_artifact_keeps_runtime_backend_unauthorized(tmp_path) -> None:
    from metroflow.benchmarks.gpu_flow_bakeoff import (
        DenseFlowGpuBakeoffConfig,
        DenseFlowGpuBakeoffRun,
        summarize_dense_flow_gpu_bakeoff,
        write_dense_flow_gpu_bakeoff_artifacts,
    )

    config = DenseFlowGpuBakeoffConfig(
        workload_name="artifact-fixture",
        link_counts=(16,),
        seeds=(1, 2, 3),
        num_steps=4,
        turns_per_link=2,
    )
    runs = tuple(
        DenseFlowGpuBakeoffRun(
            link_count=16,
            turn_count=32,
            seed=seed,
            num_steps=4,
            baseline_wall_ns=100,
            input_copy_wall_ns=5,
            first_call_wall_ns=50,
            steady_state_wall_ns=20,
            output_copy_wall_ns=5,
            max_abs_diff=1e-5,
            device_platform="gpu",
            device_kind="fixture",
            jax_version="fixture",
        )
        for seed in config.seeds
    )
    result = summarize_dense_flow_gpu_bakeoff(config, runs)
    paths = write_dense_flow_gpu_bakeoff_artifacts(result, tmp_path)

    json_text = paths["json"].read_text(encoding="utf-8")
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert '"runtime_flow_backend_authorized": false' in json_text
    assert "does not authorize a runtime JAX flow backend" in markdown
    assert "Diagnostic" in markdown


def test_gpu_bakeoff_config_rejects_insufficient_or_duplicate_matrix() -> None:
    from metroflow.benchmarks.gpu_flow_bakeoff import DenseFlowGpuBakeoffConfig

    with pytest.raises(ValueError, match="at least three"):
        DenseFlowGpuBakeoffConfig("bad", (16,), (1, 2), 4, 2)
    with pytest.raises(ValueError, match="unique"):
        DenseFlowGpuBakeoffConfig("bad", (16,), (1, 1, 2), 4, 2)
    with pytest.raises(ValueError, match="link_counts"):
        DenseFlowGpuBakeoffConfig("bad", (16, 16), (1, 2, 3), 4, 2)
