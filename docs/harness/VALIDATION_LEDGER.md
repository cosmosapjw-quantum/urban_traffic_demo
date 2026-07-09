# Validation Ledger

## 2026-07-09: Runtime Acceleration Guardrails

Change class: documentation / planning governance / review control

Commands run for this ledger entry:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
```

Observed results:

- `282 passed`
- `ruff check .` passed
- `git diff --check` clean

Benchmark evidence referenced:

- `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`
- `artifacts/runtime_spine_review/runtime-suite-eager-smoke.json`
- `artifacts/runtime_spine_review/runtime-suite-eager-smoke.manifest.json`

Review evidence added:

- `artifacts/runtime_spine_review/runtime-acceleration-guardrails-review.md`

Validation interpretation:

- These smoke benchmark artifacts are diagnostic evidence only.
- They are not publication evidence, scientific validation, or authorization for
  GPU/CUDA/NN runtime defaults.
- Deterministic baseline replay remains authoritative.

Next validation required:

- Run targeted tests after adding the pool-write sub-breakdown.
- Re-run `.venv/bin/python -m pytest -q`, `.venv/bin/python -m ruff check .`,
  and `git diff --check` before committing implementation changes.

## 2026-07-09: Active-Agent Pool-Write Sub-Breakdown

Change class: runtime telemetry / benchmark reporting / diagnostic artifact

Commands run for this ledger entry:

```bash
.venv/bin/python -m pytest tests/test_runtime_spine.py::test_simulation_step_accumulates_runtime_stage_timing_totals tests/test_runtime_spine.py::test_active_agent_allocation_records_selected_candidate_metadata -q
.venv/bin/python -m pytest tests/test_measured_benchmarks.py::test_measured_runtime_benchmark_reports_nested_route_and_agent_stage_shares tests/test_metro_absorption_benchmarks_plugins.py::test_runtime_acceleration_candidate_report_profiles_nested_stage_fits -q
.venv/bin/python -m pytest tests/test_active_agent_rust_backend.py -q
.venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager --runtime-suite-seeds 41,42,43 --runtime-suite-steps 1 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-smoke
.venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager-2step --runtime-suite-seeds 41,42,43 --runtime-suite-steps 2 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-2step-smoke
.venv/bin/python -m ruff check .
git diff --check
.venv/bin/python -m pytest -q
```

Observed results:

- targeted runtime tests: `2 passed`
- targeted benchmark/reporting tests: `2 passed`
- active-agent Rust parity tests: `6 passed`
- 1-step eager benchmark suite regenerated
- 2-step eager benchmark suite generated
- `ruff check .` passed
- `git diff --check` clean
- full test suite: `282 passed`

Diagnostic artifacts updated or added:

- `artifacts/runtime_spine_review/runtime-suite-eager-smoke.{json,md,html,manifest.json}`
- `artifacts/runtime_spine_review/runtime-suite-eager-2step-smoke.{json,md,html,manifest.json}`
- `artifacts/runtime_spine_review/runtime-pool-write-subbreakdown-review.md`
- `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`

Validation interpretation:

- `active_agent_pool_write` remains the review-ready active-agent parent stage.
- `active_agent_plugin_memory_write` is larger than
  `active_agent_pool_array_write`, but neither substage is independently
  review-ready.
- The next implementation slice is data-layout/metadata reduction, not
  immediate Rust array-write, JAX/GPU, or NN scoring.
- These benchmark artifacts remain smoke diagnostics, not validation evidence
  or default-backend authorization.

Next validation required:

- After metadata reduction, regenerate the same 1-step and 2-step eager suites
  and compare `active_agent_pool_write`,
  `active_agent_plugin_memory_write`, and `active_agent_pool_array_write`.

## 2026-07-09: Batched Active-Agent Plugin-Memory Replacement

Change class: runtime data-layout optimization / benchmark diagnostic update

Commands run for this ledger entry:

```bash
.venv/bin/python -m pytest tests/test_runtime_spine.py::test_active_agent_allocation_batches_plugin_memory_replacement -q
.venv/bin/python -m pytest tests/test_runtime_spine.py::test_active_agent_allocation_batches_plugin_memory_replacement tests/test_runtime_spine.py::test_active_agent_allocation_records_selected_candidate_metadata tests/test_runtime_spine.py::test_active_agent_allocation_applies_path_size_correction_when_configured -q
.venv/bin/python -m pytest tests/test_active_agent_rust_backend.py -q
.venv/bin/python -m pytest tests/test_measured_benchmarks.py::test_measured_runtime_benchmark_reports_nested_route_and_agent_stage_shares tests/test_runtime_diagnostics.py::test_runtime_diagnostic_rollout_captures_frames_route_cache_and_summary -q
.venv/bin/python -m pytest tests/test_runtime_spine.py -q
.venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager --runtime-suite-seeds 41,42,43 --runtime-suite-steps 1 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-smoke
.venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager-2step --runtime-suite-seeds 41,42,43 --runtime-suite-steps 2 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-2step-smoke
.venv/bin/python -m ruff check .
git diff --check
.venv/bin/python -m pytest -q
```

Observed results:

- RED check: expected failure before batching, `_replace_pool_plugin_memory`
  was called once per allocation.
- allocation targeted tests: `3 passed`
- active-agent Rust parity tests: `6 passed`
- runtime benchmark/diagnostic targeted tests: `2 passed`
- runtime spine tests: `30 passed`
- 1-step eager benchmark suite regenerated
- 2-step eager benchmark suite regenerated
- `ruff check .` passed
- `git diff --check` clean
- full test suite: `283 passed`

Diagnostic interpretation:

- `active_agent_pool_write` is now below the 0.30 review gate in both eager
  suites.
- `active_agent_plugin_memory_write` is near zero after batching.
- `route_candidate_path_build` is now review-ready in both eager suites.
- The next implementation slice moves to Rust CPU route path-build, not further
  active-agent pool-write work, JAX/GPU, or NN scoring.

Next validation required:

- Before route path-build Rust work, add RED parity tests around the smallest
  path-build boundary and keep Python baseline route legality authoritative.

## 2026-07-09: Baseline Dynamic-Potential Float32 Heap-Staleness Fix

Change class: routing correctness fix / acceleration decision reset

Commands run for this ledger entry:

```bash
.venv/bin/python -m pytest tests/test_metro_absorption_routing.py::test_generated_baseline_dynamic_potential_does_not_drop_float32_heap_updates -q
cargo fmt --all --check
CARGO_TARGET_DIR=/tmp/metroflow-cargo-target cargo test --workspace
CARGO_TARGET_DIR=/tmp/metroflow-cargo-target .venv/bin/python -m maturin develop --manifest-path crates/metroflow-rust/Cargo.toml
.venv/bin/python -m pytest tests/test_metro_absorption_routing.py::test_generated_baseline_dynamic_potential_does_not_drop_float32_heap_updates tests/test_metro_absorption_routing.py::test_advanced_dynamic_potential_prefers_less_congested_path -q
.venv/bin/python -m pytest tests/test_routing_rust_backend.py -q
/usr/bin/time -f 'elapsed=%E cpu=%P' timeout 90s .venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager-baseline-1seed-postfix --runtime-suite-seeds 41 --runtime-suite-steps 1 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-baseline-1seed-postfix-smoke
/usr/bin/time -f 'elapsed=%E cpu=%P' timeout 90s .venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager-rust-routing-1seed-postfix --runtime-suite-seeds 41 --runtime-suite-steps 1 --runtime-suite-eager-trip-generation --runtime-suite-routing-backend rust_cpu --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-rust-routing-1seed-postfix-smoke
CARGO_TARGET_DIR=/tmp/metroflow-cargo-target .venv/bin/python -m maturin develop --release --manifest-path crates/metroflow-rust/Cargo.toml
/usr/bin/time -f 'elapsed=%E cpu=%P' timeout 90s .venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager-rust-routing-1seed-release --runtime-suite-seeds 41 --runtime-suite-steps 1 --runtime-suite-eager-trip-generation --runtime-suite-routing-backend rust_cpu --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-rust-routing-1seed-release-smoke
.venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager --runtime-suite-seeds 41,42,43 --runtime-suite-steps 1 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-smoke
.venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager-2step --runtime-suite-seeds 41,42,43 --runtime-suite-steps 2 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-2step-smoke
```

Observed results:

- RED check: generated seed `41` baseline route `422 -> 8` produced no route
  before the fix.
- targeted generated-OD routing regression: `1 failed` before the fix, then
  `2 passed` with the adjacent baseline routing test after the fix.
- Rust gates: `cargo fmt --all --check` passed; `cargo test --workspace`
  reported `52 passed`.
- maturin rebuild succeeded for CPython 3.12.
- Rust routing Python parity suite: `22 passed`.
- baseline 1-seed/1-step eager suite completed in `elapsed=0:08.02`.
- explicit Rust routing 1-seed/1-step eager suite timed out at `90s` with the
  debug extension.
- release Rust extension rebuild succeeded.
- explicit Rust routing 1-seed/1-step eager suite completed in
  `elapsed=0:26.70` with the release extension; route potential fell to
  `0.019283` share, but path-build and metadata rose to `0.424858` and
  `0.497658`.
- regenerated 3-seed 1-step eager suite: `route_candidate_potential`
  mean share `0.537567`; `route_candidate_path_build` mean share `0.244385`.
- regenerated 3-seed 2-step eager suite: `route_candidate_potential`
  mean share `0.509388`; `route_candidate_path_build` mean share `0.231000`.

Diagnostic interpretation:

- Previous route path-build review-readiness was caused by a baseline
  correctness bug that made reachable ODs appear unreachable.
- The current route acceleration target is dynamic-potential recompute/cache
  amortization, not path-build.
- Runtime-wide explicit Rust routing remains deferred until path-build/metadata
  copy-boundary costs are amortized or bypassed with a narrower potential-only
  contract.

Next validation required:

- Add generated-OD dynamic-potential cache/recompute microbenchmarks and compare
  Python baseline vs Rust potential without enabling runtime-wide Rust routing.
