# Deprecated Ideas

Last updated: 2026-07-09

Deprecated here means "do not pursue in the next slice unless new benchmark
evidence falsifies the current decision." It does not mean permanently banned.

## Immediate NN/JAX Active-Agent Route-Choice Scoring

Status: deferred

Reason:

- `active_agent_candidate_selection` remained near 3.5 percent in both 1-step
  and 2-step eager suites.
- The active-agent hot path is currently `active_agent_pool_write`, which is
  deterministic state mutation rather than batch scoring.

Reopen condition:

- A broader deterministic suite makes candidate selection review-ready, or a
  larger route-choice candidate set makes scoring dominate pool writes.

## More Route Timing Splits Before Pool-Write Work

Status: deferred

Reason:

- Route refresh is already split into potential, path build, and metadata.
- Potential and path-build are both below the 0.30 review threshold in current
  smoke suites.
- Another route split would not currently change the next implementation action.

Reopen condition:

- Pool-write optimization is completed or falsified, and route refresh remains
  the leading review-ready stage.

## Custom CUDA Runtime Kernel Scaffolding

Status: deferred

Reason:

- Current review-ready stages are graph/control-flow or state-write heavy.
- No dense numeric kernel has yet shown sustained exclusive dominance after
  Rust/baseline parity.

Reopen condition:

- A dense flow, route-score, or OD/policy batch stage is review-ready across at
  least three deterministic seeds and has a narrow kernel contract.

## Immediate Rust Pool-Array Write Backend

Status: deferred

Reason:

- `active_agent_pool_write` is now below the review gate after batching
  plugin-memory replacement.
- `active_agent_pool_array_write` remains visible but below the review gate.
- `route_candidate_path_build` is currently the stronger Rust CPU candidate.

Reopen condition:

- Typed-array pool replacement becomes review-ready across deterministic seeds,
  or route path-build work is completed and active-agent array write again
  dominates the next review-ready stage.
