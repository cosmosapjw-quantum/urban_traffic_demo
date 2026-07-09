# Workload Matrix v1 Spec

## Goal

Add benchmark workload-class metadata that lets acceleration reviews compare
runtime, routing, dense flow, route scoring, and active-agent shapes without
adding backend logic.

## Evidence

- Hardware atlas card: `artifacts/runtime_spine_review/hardware-fit-atlas.md`
  identifies runtime stage groups but does not yet carry workload-class
  coverage metadata.
- Runtime benchmark artifact:
  `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md` warns
  that smoke workloads can overrepresent one-step activation costs.
- Replay/parity artifact: existing measured benchmark tests and runtime replay
  remain authoritative; this PR does not change simulation behavior.

## In Scope

- Add a stable workload matrix schema for:
  - eager runtime 1-step and 2-step;
  - generated OD routing;
  - dense flow/turn batch;
  - route candidate K>1 scoring;
  - active-agent dense pool.
- Expose the matrix through measured runtime suite report data and artifact
  manifests.
- Preserve benchmark payload keys and no eager accelerator imports.

## Out Of Scope

- Backend dispatch changes.
- PyTorch, libtorch, custom CUDA, or new JAX runtime use.
- Changes to runtime defaults, replay semantics, route legality, or state
  mutation.
- Treating smoke artifacts as validation evidence.

## Public Contract

- APIs/config/artifact keys:
  - `MeasuredRuntimeBenchmarkSuiteConfig.workload_matrix`
  - `MeasuredRuntimeBenchmarkSuiteResult.workload_matrix`
  - `report_data["workload_matrix"]`
  - runtime suite manifest key `workload_matrix`
  - workload entry key `coverage_state`, which separates measured suite
    coverage from dedicated-probe requirements.
- Fallback behavior: metadata only; no backend fallback changes.
- Replay/cache impact: none.

## Acceptance Criteria

- Targeted tests:
  - `tests/test_measured_benchmarks.py` verifies workload matrix schema,
    serialization, manifest metadata, and no eager accelerator imports.
- Full gates:
  - `.venv/bin/python -m pytest -q`
  - `.venv/bin/python -m ruff check .`
  - `git diff --check`
- Review loop max: 3.

## Compact CCoT

Question: What workload classes must be visible before another backend or NN
optimization is authorized?

Evidence: The atlas links symbols to stages, while the deep audit shows that
single smoke suites can bias the next slice.

Inference: The next improvement is metadata coverage, not a new backend.

Counterevidence checked: Existing runtime suite timing and atlas cards already
record stages, so this PR must avoid duplicating timing instrumentation.

Decision: Add workload-class coverage metadata at the measured benchmark suite
boundary and artifact manifest.

Falsifier: If the matrix cannot be serialized without importing optional
accelerators or changing benchmark execution, block the PR.

Next action: Implement PR02 only after the matrix can be linked to atlas
decision cards.
