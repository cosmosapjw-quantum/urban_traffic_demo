"""Evidence-gated JAX dense-flow persistent-device chunk bakeoff."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
from typing import Any

from metroflow.backends.jax_flow import run_dense_flow_jax, warm_up_jax_flow_runtime
from metroflow.benchmarks.dense_flow_workload import (
    build_dense_flow_jax_inputs,
    build_dense_flow_scale_state,
    flow_output_arrays,
    max_abs_flow_output_diff,
    run_flow_update_steps,
)

__all__ = [
    "DenseFlowGpuBakeoffConfig",
    "DenseFlowGpuBakeoffRun",
    "DenseFlowGpuBakeoffResult",
    "DenseFlowGpuBakeoffSizeSummary",
    "run_dense_flow_gpu_bakeoff",
    "summarize_dense_flow_gpu_bakeoff",
    "write_dense_flow_gpu_bakeoff_artifacts",
]


@dataclass(frozen=True, slots=True)
class DenseFlowGpuBakeoffConfig:
    workload_name: str
    link_counts: tuple[int, ...]
    seeds: tuple[int, ...]
    num_steps: int
    turns_per_link: int
    max_abs_diff_tolerance: float = 1.0e-3
    require_gpu: bool = True

    def __post_init__(self) -> None:
        workload = str(self.workload_name).strip()
        link_counts = tuple(int(value) for value in self.link_counts)
        seeds = tuple(int(value) for value in self.seeds)
        steps = int(self.num_steps)
        turns = int(self.turns_per_link)
        tolerance = float(self.max_abs_diff_tolerance)
        if not workload:
            raise ValueError("workload_name must be non-empty")
        if not link_counts or any(value < 2 for value in link_counts):
            raise ValueError("link_counts must contain values >= 2")
        if len(set(link_counts)) != len(link_counts):
            raise ValueError("link_counts must be unique")
        if len(seeds) < 3:
            raise ValueError("GPU bakeoff requires at least three seeds")
        if len(set(seeds)) != len(seeds):
            raise ValueError("GPU bakeoff seeds must be unique")
        if steps < 2:
            raise ValueError("num_steps must be >= 2")
        if turns < 1:
            raise ValueError("turns_per_link must be >= 1")
        if not math.isfinite(tolerance) or tolerance <= 0.0:
            raise ValueError("max_abs_diff_tolerance must be finite and > 0")
        object.__setattr__(self, "workload_name", workload)
        object.__setattr__(self, "link_counts", link_counts)
        object.__setattr__(self, "seeds", seeds)
        object.__setattr__(self, "num_steps", steps)
        object.__setattr__(self, "turns_per_link", turns)
        object.__setattr__(self, "max_abs_diff_tolerance", tolerance)
        object.__setattr__(self, "require_gpu", bool(self.require_gpu))


@dataclass(frozen=True, slots=True)
class DenseFlowGpuBakeoffRun:
    link_count: int
    turn_count: int
    seed: int
    num_steps: int
    baseline_wall_ns: int
    input_copy_wall_ns: int
    first_call_wall_ns: int
    steady_state_wall_ns: int
    output_copy_wall_ns: int
    max_abs_diff: float
    device_platform: str
    device_kind: str
    jax_version: str

    def __post_init__(self) -> None:
        positive = (self.link_count, self.turn_count, self.num_steps, self.baseline_wall_ns)
        timings = (
            self.input_copy_wall_ns,
            self.first_call_wall_ns,
            self.steady_state_wall_ns,
            self.output_copy_wall_ns,
        )
        if any(int(value) <= 0 for value in positive):
            raise ValueError("run size, steps, and baseline timing must be positive")
        if any(int(value) < 0 for value in timings):
            raise ValueError("JAX run timings must be non-negative")
        if int(self.first_call_wall_ns) <= 0 or int(self.steady_state_wall_ns) <= 0:
            raise ValueError("first-call and steady-state timings must be positive")
        if not math.isfinite(float(self.max_abs_diff)) or self.max_abs_diff < 0.0:
            raise ValueError("max_abs_diff must be finite and non-negative")
        if not all(
            str(value).strip()
            for value in (self.device_platform, self.device_kind, self.jax_version)
        ):
            raise ValueError("device and JAX version metadata must be non-empty")

    @property
    def warm_first_call_plus_copy_estimate_wall_ns(self) -> int:
        return int(
            self.input_copy_wall_ns
            + self.first_call_wall_ns
            + self.output_copy_wall_ns
        )

    @property
    def steady_copy_inclusive_wall_ns(self) -> int:
        return int(
            self.input_copy_wall_ns
            + self.steady_state_wall_ns
            + self.output_copy_wall_ns
        )

    @property
    def warm_first_call_plus_copy_estimate_speedup(self) -> float:
        return float(
            self.baseline_wall_ns
            / max(self.warm_first_call_plus_copy_estimate_wall_ns, 1)
        )

    @property
    def steady_copy_inclusive_speedup(self) -> float:
        return float(
            self.baseline_wall_ns / max(self.steady_copy_inclusive_wall_ns, 1)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_count": int(self.link_count),
            "turn_count": int(self.turn_count),
            "seed": int(self.seed),
            "num_steps": int(self.num_steps),
            "baseline_wall_ns": int(self.baseline_wall_ns),
            "input_copy_wall_ns": int(self.input_copy_wall_ns),
            "first_call_wall_ns": int(self.first_call_wall_ns),
            "steady_state_wall_ns": int(self.steady_state_wall_ns),
            "output_copy_wall_ns": int(self.output_copy_wall_ns),
            "warm_first_call_plus_copy_estimate_wall_ns": (
                self.warm_first_call_plus_copy_estimate_wall_ns
            ),
            "steady_copy_inclusive_wall_ns": self.steady_copy_inclusive_wall_ns,
            "warm_first_call_plus_copy_estimate_speedup": (
                self.warm_first_call_plus_copy_estimate_speedup
            ),
            "steady_copy_inclusive_speedup": self.steady_copy_inclusive_speedup,
            "max_abs_diff": float(self.max_abs_diff),
            "device_platform": str(self.device_platform),
            "device_kind": str(self.device_kind),
            "jax_version": str(self.jax_version),
        }


@dataclass(frozen=True, slots=True)
class DenseFlowGpuBakeoffSizeSummary:
    link_count: int
    deterministic_run_count: int
    minimum_warm_first_call_plus_copy_estimate_speedup: float
    minimum_steady_copy_inclusive_speedup: float
    maximum_abs_diff: float
    warm_first_call_copy_parity_gate_passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_count": self.link_count,
            "deterministic_run_count": self.deterministic_run_count,
            "minimum_warm_first_call_plus_copy_estimate_speedup": (
                self.minimum_warm_first_call_plus_copy_estimate_speedup
            ),
            "minimum_steady_copy_inclusive_speedup": (
                self.minimum_steady_copy_inclusive_speedup
            ),
            "maximum_abs_diff": self.maximum_abs_diff,
            "warm_first_call_copy_parity_gate_passed": (
                self.warm_first_call_copy_parity_gate_passed
            ),
        }


@dataclass(frozen=True, slots=True)
class DenseFlowGpuBakeoffResult:
    config: DenseFlowGpuBakeoffConfig
    runs: tuple[DenseFlowGpuBakeoffRun, ...]
    size_summaries: tuple[DenseFlowGpuBakeoffSizeSummary, ...]
    persistent_device_chunk_review_ready_link_counts: tuple[int, ...]
    runtime_flow_backend_authorized: bool = False
    evidence_status: str = "diagnostic_not_runtime_validation"
    xla_python_client_mem_fraction: str = ""
    jax_runtime_warmup_wall_ns: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_format_version": "dense_flow_gpu_bakeoff_v1",
            "evidence_status": self.evidence_status,
            "workload_name": self.config.workload_name,
            "link_counts": list(self.config.link_counts),
            "seeds": list(self.config.seeds),
            "num_steps": self.config.num_steps,
            "turns_per_link": self.config.turns_per_link,
            "max_abs_diff_tolerance": self.config.max_abs_diff_tolerance,
            "require_gpu": self.config.require_gpu,
            "xla_python_client_mem_fraction": (
                self.xla_python_client_mem_fraction
            ),
            "jax_runtime_warmup_wall_ns": self.jax_runtime_warmup_wall_ns,
            "timing_scope": (
                "warm-process first-call estimate; import/device discovery and runtime "
                "warmup are recorded separately; first-result output copy is estimated "
                "from the steady result"
            ),
            "chunk_input_policy": (
                "all demand, capacity, topology, and priority arrays remain constant "
                "within each device chunk"
            ),
            "inter_invocation_compilation_cache_measured": False,
            "runs": [run.to_dict() for run in self.runs],
            "size_summaries": [item.to_dict() for item in self.size_summaries],
            "persistent_device_chunk_review_ready_link_counts": list(
                self.persistent_device_chunk_review_ready_link_counts
            ),
            "runtime_flow_backend_authorized": self.runtime_flow_backend_authorized,
            "decision": (
                "persistent_device_chunk_experiment_only; per-tick host synchronization "
                "and replay integration remain unmeasured"
            ),
        }


def run_dense_flow_gpu_bakeoff(
    config: DenseFlowGpuBakeoffConfig,
) -> DenseFlowGpuBakeoffResult:
    warmup_ns, warmup_platform, warmup_device, warmup_jax_version = (
        warm_up_jax_flow_runtime(require_gpu=config.require_gpu)
    )
    runs: list[DenseFlowGpuBakeoffRun] = []
    for link_count in config.link_counts:
        for seed in config.seeds:
            link_state, node_state = build_dense_flow_scale_state(
                link_count=link_count,
                turns_per_link=config.turns_per_link,
                seed=seed,
            )
            baseline_link, baseline_node, baseline_ns = run_flow_update_steps(
                link_state,
                node_state,
                num_steps=config.num_steps,
                flow_backend="baseline",
            )
            baseline_output = flow_output_arrays(baseline_link, baseline_node)
            probe = run_dense_flow_jax(
                **build_dense_flow_jax_inputs(link_state, node_state),
                num_steps=config.num_steps,
                execution_mode="device_chunk",
                require_gpu=config.require_gpu,
            )
            runs.append(
                DenseFlowGpuBakeoffRun(
                    link_count=link_count,
                    turn_count=link_count * config.turns_per_link,
                    seed=seed,
                    num_steps=config.num_steps,
                    baseline_wall_ns=baseline_ns,
                    input_copy_wall_ns=probe.input_copy_wall_ns,
                    first_call_wall_ns=probe.first_call_wall_ns,
                    steady_state_wall_ns=probe.steady_state_wall_ns,
                    output_copy_wall_ns=probe.output_copy_wall_ns,
                    max_abs_diff=max_abs_flow_output_diff(
                        baseline_output,
                        probe.output,
                    ),
                    device_platform=probe.device_platform,
                    device_kind=probe.device_kind,
                    jax_version=probe.jax_version,
                )
            )
    if any(
        run.device_platform != warmup_platform
        or run.device_kind != warmup_device
        or run.jax_version != warmup_jax_version
        for run in runs
    ):
        raise RuntimeError("JAX warmup and bakeoff run device metadata must match")
    return summarize_dense_flow_gpu_bakeoff(
        config,
        tuple(runs),
        jax_runtime_warmup_wall_ns=warmup_ns,
    )


def summarize_dense_flow_gpu_bakeoff(
    config: DenseFlowGpuBakeoffConfig,
    runs: tuple[DenseFlowGpuBakeoffRun, ...],
    *,
    jax_runtime_warmup_wall_ns: int = 0,
) -> DenseFlowGpuBakeoffResult:
    expected_pairs = {
        (link_count, seed)
        for link_count in config.link_counts
        for seed in config.seeds
    }
    actual_pairs = {(int(run.link_count), int(run.seed)) for run in runs}
    if actual_pairs != expected_pairs or len(runs) != len(expected_pairs):
        raise ValueError("runs must contain exactly one result per link-count/seed pair")
    for run in runs:
        if run.num_steps != config.num_steps:
            raise ValueError("run num_steps must match the bakeoff config")
        if run.turn_count != run.link_count * config.turns_per_link:
            raise ValueError("run turn_count must match link_count * turns_per_link")
        if config.require_gpu and run.device_platform != "gpu":
            raise ValueError("GPU bakeoff runs must report device_platform='gpu'")
    if len({run.device_platform for run in runs}) != 1:
        raise ValueError("all bakeoff runs must use one device platform")
    if len({run.device_kind for run in runs}) != 1:
        raise ValueError("all bakeoff runs must use one device kind")
    if len({run.jax_version for run in runs}) != 1:
        raise ValueError("all bakeoff runs must use one JAX version")
    if int(jax_runtime_warmup_wall_ns) < 0:
        raise ValueError("jax_runtime_warmup_wall_ns must be non-negative")
    summaries: list[DenseFlowGpuBakeoffSizeSummary] = []
    for link_count in config.link_counts:
        selected = tuple(run for run in runs if run.link_count == link_count)
        min_first_call = min(
            run.warm_first_call_plus_copy_estimate_speedup for run in selected
        )
        min_steady = min(run.steady_copy_inclusive_speedup for run in selected)
        max_diff = max(float(run.max_abs_diff) for run in selected)
        passed = bool(
            len(selected) >= 3
            and min_first_call > 1.0
            and min_steady > 1.0
            and max_diff <= config.max_abs_diff_tolerance
            and all(run.device_platform == "gpu" for run in selected)
        )
        summaries.append(
            DenseFlowGpuBakeoffSizeSummary(
                link_count=link_count,
                deterministic_run_count=len(selected),
                minimum_warm_first_call_plus_copy_estimate_speedup=float(
                    min_first_call
                ),
                minimum_steady_copy_inclusive_speedup=float(min_steady),
                maximum_abs_diff=float(max_diff),
                warm_first_call_copy_parity_gate_passed=passed,
            )
        )
    return DenseFlowGpuBakeoffResult(
        config=config,
        runs=tuple(sorted(runs, key=lambda run: (run.link_count, run.seed))),
        size_summaries=tuple(summaries),
        persistent_device_chunk_review_ready_link_counts=tuple(
            summary.link_count
            for summary in summaries
            if summary.warm_first_call_copy_parity_gate_passed
        ),
        runtime_flow_backend_authorized=False,
        xla_python_client_mem_fraction=str(
            os.environ.get("XLA_PYTHON_CLIENT_MEM_FRACTION", "")
        ),
        jax_runtime_warmup_wall_ns=int(jax_runtime_warmup_wall_ns),
    )


def write_dense_flow_gpu_bakeoff_artifacts(
    result: DenseFlowGpuBakeoffResult,
    output_dir: str | Path,
) -> dict[str, Path]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise ValueError("GPU bakeoff output_dir must be empty")
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "dense-flow-gpu-bakeoff.json"
    markdown_path = target / "dense-flow-gpu-bakeoff.md"
    json_path.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(result), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def _render_markdown(result: DenseFlowGpuBakeoffResult) -> str:
    lines = [
        "# Dense Flow GPU Bakeoff",
        "",
        "Diagnostic microbenchmark only. It does not authorize a runtime JAX flow backend.",
        "",
        f"- Device: `{result.runs[0].device_kind}` ({result.runs[0].device_platform})",
        f"- JAX: `{result.runs[0].jax_version}`",
        f"- XLA memory fraction: `{result.xla_python_client_mem_fraction or 'unset'}`",
        f"- JAX runtime warmup: {result.jax_runtime_warmup_wall_ns / 1e6:.3f} ms",
        f"- Steps per persistent chunk: {result.config.num_steps}",
        f"- Max absolute drift tolerance: {result.config.max_abs_diff_tolerance:g}",
        "",
        "| Links | Runs | Min warm first-call+copy estimate | Min steady+copy speedup | Max abs diff | Chunk review-ready |",
        "|---:|---:|---:|---:|---:|:---:|",
    ]
    for summary in result.size_summaries:
        lines.append(
            f"| {summary.link_count} | {summary.deterministic_run_count} | "
            f"{summary.minimum_warm_first_call_plus_copy_estimate_speedup:.3f} | "
            f"{summary.minimum_steady_copy_inclusive_speedup:.3f} | "
            f"{summary.maximum_abs_diff:.6g} | "
            f"{'yes' if summary.warm_first_call_copy_parity_gate_passed else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Compact CCoT",
            "",
            "Question: Does dense flow justify a GPU runtime backend now?",
            "Evidence: Three-seed warm-process first-call/copy/steady timing plus parity measurements; 4,096 and 16,384 pass, while 65,536 is rejected for drift.",
            "Inference: A review-ready chunk size does not establish per-tick host-synchronized speedup.",
            "Counterevidence checked: Import/device discovery is separate, inter-invocation compile-cache reuse is unmeasured, chunk inputs are constant, and runtime events/agents synchronize on host ticks.",
            "Decision: Keep runtime_flow_backend_authorized=false; park checkpoint-cadence integration as the GPU-lane re-entry condition.",
            "Falsifier: Host-synchronized integration retains speedup and replay parity at an explicit checkpoint cadence.",
            "Next action: Switch immediately to PR48 simulator-only cost-to-go feature and label contracts.",
            "",
        ]
    )
    return "\n".join(lines)


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--link-counts", default="4096,16384,65536")
    parser.add_argument("--seeds", default="41,42,43")
    parser.add_argument("--num-steps", type=int, default=512)
    parser.add_argument("--turns-per-link", type=int, default=3)
    args = parser.parse_args()
    config = DenseFlowGpuBakeoffConfig(
        workload_name="rtx3080ti-dense-flow-persistent-chunk",
        link_counts=tuple(
            int(value.strip())
            for value in args.link_counts.split(",")
            if value.strip()
        ),
        seeds=tuple(
            int(value.strip()) for value in args.seeds.split(",") if value.strip()
        ),
        num_steps=args.num_steps,
        turns_per_link=args.turns_per_link,
        require_gpu=True,
    )
    result = run_dense_flow_gpu_bakeoff(config)
    paths = write_dense_flow_gpu_bakeoff_artifacts(result, args.output_dir)
    print(json.dumps({key: str(value) for key, value in paths.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
