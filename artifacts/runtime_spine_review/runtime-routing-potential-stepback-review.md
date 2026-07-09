# Runtime Routing Potential Step-Back Review

Date: 2026-07-09

This is a diagnostic review artifact. It is not validation evidence and does not
authorize runtime default backend changes.

## Trigger

The prior acceleration direction was Rust route path-build. A step-back was
required because Rust greedy/ranked route candidate code already existed, while
explicit runtime-wide `routing_backend="rust_cpu"` was slower than baseline even
with a release Rust extension.

## Finding

Generated seed `41`, OD node `422 -> 8`, exposed a Python baseline
dynamic-potential bug:

- Rust potential found path `(2053, 2031, 1766, 5505, 5503, 85)`.
- Python baseline returned no path before the fix.
- CSR reverse reachability and blocked-link checks both showed the path was
  valid.
- Root cause: baseline Dijkstra pushed Python-float heap costs but stored
  authoritative distances as `float32`; the stale-entry check could drop valid
  updates after rounding.

Fix:

- `_reverse_dijkstra_node_costs` now rounds candidate costs to `float32` before
  both distance storage and heap push.

## Compact CCoT

Question: Should the next route slice still be Rust path-build?

Evidence: After the fix, 3-seed eager suites show `route_candidate_potential`
at `0.537567` / `0.509388` mean share and `route_candidate_path_build` at
`0.244385` / `0.231000`.

Inference: The previous path-build hot spot was a false local minimum caused by
baseline no-route behavior.

Counterevidence checked: Rust micro parity on generated OD now matches the
fixed baseline path. Release Rust potential recompute is fast, but runtime-wide
Rust routing still takes `26.70s` versus baseline `8.02s` for 1-seed/1-step
eager because path-build and metadata copy-boundary costs dominate.

Decision: Do not proceed with path-build as the next slice. Target
dynamic-potential recompute/cache amortization first.

Falsifier: If potential recompute is reduced and route refresh remains dominated
by path-build or candidate scoring, reopen path-build or NN/JAX scoring.

Next action: Add generated-OD potential/cache microbenchmarks before another
backend activation attempt.

## Evidence Commands

```bash
.venv/bin/python -m pytest tests/test_metro_absorption_routing.py::test_generated_baseline_dynamic_potential_does_not_drop_float32_heap_updates -q
.venv/bin/python -m pytest tests/test_routing_rust_backend.py -q
/usr/bin/time -f 'elapsed=%E cpu=%P' timeout 90s .venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager-baseline-1seed-postfix --runtime-suite-seeds 41 --runtime-suite-steps 1 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-baseline-1seed-postfix-smoke
/usr/bin/time -f 'elapsed=%E cpu=%P' timeout 90s .venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager-rust-routing-1seed-postfix --runtime-suite-seeds 41 --runtime-suite-steps 1 --runtime-suite-eager-trip-generation --runtime-suite-routing-backend rust_cpu --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-rust-routing-1seed-postfix-smoke
CARGO_TARGET_DIR=/tmp/metroflow-cargo-target .venv/bin/python -m maturin develop --release --manifest-path crates/metroflow-rust/Cargo.toml
/usr/bin/time -f 'elapsed=%E cpu=%P' timeout 90s .venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager-rust-routing-1seed-release --runtime-suite-seeds 41 --runtime-suite-steps 1 --runtime-suite-eager-trip-generation --runtime-suite-routing-backend rust_cpu --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-rust-routing-1seed-release-smoke
.venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager --runtime-suite-seeds 41,42,43 --runtime-suite-steps 1 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-smoke
.venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager-2step --runtime-suite-seeds 41,42,43 --runtime-suite-steps 2 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-2step-smoke
```
