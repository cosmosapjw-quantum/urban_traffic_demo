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
