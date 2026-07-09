# PR05 Dense Flow Scale Probe

## Goal

Add a benchmark-only dense flow/turn workload probe that compares NumPy
baseline, optional Rust flow, and optional JAX compile-vs-steady-state timing
without changing runtime `flow_backend` values.

## Scope

- Add dense synthetic `LinkState`/`NodeState` fixture generation inside the
  benchmark layer.
- Add `MeasuredDenseFlowScaleBenchmarkConfig`,
  `MeasuredDenseFlowScaleBenchmarkResult`, and
  `run_measured_dense_flow_scale_benchmark`.
- Probe backends are benchmark-only: `baseline`, `rust_cpu`, `jax_optional`.
- Record link/turn size, wall-clock timing, baseline/probe fingerprints,
  max absolute diff, copy-boundary note, JAX availability, first-call timing,
  steady-state timing, and JAX host/device input/output copy timing.
- Require `num_steps >= 2` for `jax_optional` so first-call and steady-state
  measurements are both backed by at least one executed step.
- Preserve runtime `FLOW_UPDATE_BACKENDS == ("baseline", "rust_cpu", "auto")`.

## Non-Goals

- Do not add `jax` to runtime flow backend config.
- Do not add PyTorch, libtorch, C++, CUDA build scaffolds, or custom kernels.
- Do not change `flow.engine` runtime semantics.
- Do not promote benchmark smoke outputs to validation evidence.

## CCoT Record

- Question: Is dense flow a NumPy/SIMD, Rust CPU, or JAX/GPU candidate at larger
  scale?
- Evidence: The hardware atlas keeps dense flow on the NumPy/Rust/JAX watchlist,
  but workload matrix marks it as requiring a dedicated probe.
- Inference: A benchmark-only scaled fixture can provide copy/compile-aware
  evidence without changing runtime authority.
- Counterevidence checked: JAX as a runtime backend would violate the current
  base contract and is unnecessary for a probe.
- Decision: Add dense-flow probe only; do not add runtime backend values.
- Falsifier: If this PR accepts `flow_backend="jax"` or changes runtime flow
  outputs, revert.
- Next action: Add RED tests, implement probe, review, gate, commit.

## Acceptance Criteria

- Baseline dense probe records deterministic schema and output fingerprint.
- Rust dense probe matches baseline when `_metroflow_rust` is available.
- JAX optional probe records unavailable metadata when absent, or first-call and
  steady-state timing plus input/output copy timing and parity when present.
- JAX optional runtime/init/compile failure records deterministic fallback
  metadata instead of propagating benchmark failure.
- Dense-flow output fingerprints include `turn_demand`.
- Runtime flow backend registry does not include JAX.
- Targeted tests, full pytest, ruff, and whitespace gates pass.
