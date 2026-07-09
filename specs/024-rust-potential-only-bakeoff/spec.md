# PR04 Rust Potential-Only Bakeoff

## Goal

Add a measured benchmark contract that compares only dynamic-potential
cost-to-go computation across baseline, explicit Rust CPU, and `auto` fallback.

## Scope

- Add a potential-only measured benchmark API under `metroflow.metrics.benchmarks`.
- Record backend requested/actual/fallback, copy-boundary note, node/link counts,
  destination node, wall-clock timing, recompute/cache counters, and a stable
  node-cost fingerprint.
- Keep whole-route candidate generation and runtime-wide Rust routing out of
  this benchmark.
- Preserve explicit Rust fail-closed behavior and `auto` fallback behavior.

## Non-Goals

- Do not add new Rust functions or change the PyO3 extension.
- Do not enable whole-runtime `routing_backend="rust_cpu"` by default.
- Do not change route legality, candidate enumeration, metadata scoring, or
  active-agent movement.
- Do not add JAX, torch, libtorch, C++ or CUDA dependencies.

## CCoT Record

- Question: Can Rust potential performance be measured without conflating it
  with path-build and metadata copy-boundary costs?
- Evidence: Current routing candidate benchmark calls full candidate generation,
  so Rust routing timing includes potential, greedy/ranked path construction,
  metadata, and selection surfaces.
- Inference: A potential-only benchmark is needed before deciding whether Rust
  potential helps the parent route refresh stage.
- Counterevidence checked: Whole-runtime Rust routing was previously slower and
  must not be used as evidence for the narrower potential core.
- Decision: Add a potential-only measured contract and keep whole-runtime Rust
  routing deferred.
- Falsifier: If potential-only benchmark calls candidate generation or changes
  route-candidate/runtime defaults, revert this PR.
- Next action: Add RED tests, implement the benchmark, review, gate, commit.

## Acceptance Criteria

- Potential-only benchmark does not call `create_route_candidate_set`.
- Baseline result records `routing_backend_actual="baseline"`.
- Explicit Rust backend remains fail-closed if the wrapper fails.
- `auto` records fallback metadata when Rust is unavailable or fails.
- If `_metroflow_rust` is available, Rust and baseline node-cost fingerprints
  match for the fixture network.
- Targeted tests, full pytest, ruff, and whitespace gates pass.
