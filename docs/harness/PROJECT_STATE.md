# Project State

Last updated: 2026-07-09

## Runtime Baseline

Facts:

- Host baseline is Python 3.12 on Ubuntu 24.04.
- Default runtime authority is Python/NumPy deterministic baseline.
- Rust CPU backend is optional and explicit/fail-closed.
- JAX CUDA 13 remains optional for RTX 3080 Ti 12GB experiments.

## Acceleration Evidence

Canonical evidence artifact:

- `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`

Do not copy benchmark tables into other docs unless the values are needed for a
specific decision. Link to the canonical evidence artifact instead.

## Current Accepted Direction

Derived conclusions:

- `active_agent_pool_write` is the next active-agent target.
- `active_agent_candidate_selection` is not currently the hot path.
- Route candidate refresh remains important, but immediate route work should be
  Rust/algorithmic before custom CUDA.
- NN/JAX remains a watchlist for scoring and surrogate labels, not the next
  runtime state-mutation fix.

## Open Risks

- Smoke eager workloads may overrepresent activation/allocation cost.
- Nested timing shares overlap and must not be summed as exclusive wall-clock
  partitions.
- Repeated instrumentation can become a local-minimum trap if it no longer
  changes the next implementation decision.

## Next Action

Follow `docs/harness/RUNTIME_ACCELERATION_DECISION_GUARDRAILS.md` and split
`active_agent_pool_write` into typed-array replacement vs plugin-memory dict
update before implementing a Rust or data-layout optimization.
