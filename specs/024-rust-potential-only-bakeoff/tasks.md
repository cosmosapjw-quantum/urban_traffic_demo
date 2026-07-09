# PR04 Tasks

1. Add RED tests for potential-only benchmark API, backend metadata, no candidate
   generation call, explicit Rust fail-closed, `auto` fallback, and optional Rust
   parity.
2. Implement `MeasuredDynamicPotentialBenchmarkConfig`,
   `MeasuredDynamicPotentialBenchmarkResult`, and
   `run_measured_dynamic_potential_benchmark`.
3. Add potential-only copy-boundary notes distinct from whole-route routing
   notes.
4. Update roadmap/project docs with PR04 status and decision boundary.
5. Run `/review-spec`, `/review-code`, `/review-drift`; apply up to three fix
   loops.
6. Run targeted tests, full pytest, ruff, and `git diff --check`.
7. Commit as `perf(routing): benchmark rust potential core`.
