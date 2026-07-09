# Project State

Last updated: 2026-07-10

## Runtime Baseline

Facts:

- Host baseline is Python 3.12 on Ubuntu 24.04.
- Default runtime authority is Python/NumPy deterministic baseline.
- Rust CPU backend is optional and explicit/fail-closed.
- JAX CUDA 13 remains optional for RTX 3080 Ti 12GB experiments.
- Whole-code hardware-fit atlas is the current step-back artifact for choosing
  Rust CPU, NumPy/SIMD, JAX/GPU, NN surrogate, or keep-Python lanes.
- `docs/PRD_ACCELERATED_RUNTIME.md` and
  `docs/harness/ACCELERATION_PR_LIST.md` are the active long-term roadmap for
  spec-driven/subagent-driven acceleration work.
- PR01 (`31064c5`), PR02 (`b434258`), PR03 (`e292685`), and PR04 are
  complete. PR05 dense flow scale probe is next.

## Acceleration Evidence

Canonical evidence artifact:

- `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`

Do not copy benchmark tables into other docs unless the values are needed for a
specific decision. Link to the canonical evidence artifact instead.

## Current Accepted Direction

Derived conclusions:

- `active_agent_pool_write` was reduced below the review gate by batching
  plugin-memory replacement.
- `active_agent_pool_array_write` remains below the review gate and should stay
  a watchlist item.
- `active_agent_candidate_selection` is not currently the hot path.
- Route candidate refresh is now the dominant review-ready parent stage.
- `route_candidate_potential` and `dynamic_potential_recompute` are the current
  review-ready route substages after fixing baseline Dijkstra `float32`
  heap-staleness.
- `route_candidate_path_build` is no longer review-ready after the baseline
  correctness fix.
- Explicit whole-runtime `routing_backend="rust_cpu"` is slower than baseline
  for the 1-seed/1-step eager suite even with a release Rust extension
  (`26.70s` versus baseline `8.02s`), because cost moves into Rust
  path-build/metadata copy-boundary work.
- Keep Rust routing work narrow: potential-only/cache amortization first,
  path-build/metadata later only if their release-profile evidence improves.
- NN/JAX remains a watchlist for cost-to-go surrogate labels or dense scoring,
  not the next route-legality authority.

## Open Risks

- Smoke eager workloads may overrepresent activation/allocation cost.
- Nested timing shares overlap and must not be summed as exclusive wall-clock
  partitions.
- Repeated instrumentation can become a local-minimum trap if it no longer
  changes the next implementation decision.
- Static hardware-fit labels are not performance evidence unless linked to
  runtime stage timings or copy-inclusive microbench results.

## Next Action

Open PR05 as a dense flow scale probe. Do not add custom CUDA or GPU runtime
config values; compare NumPy baseline, Rust flow, and optional JAX only through
copy/compile-aware measured probes.
