# Runtime Plugin-Memory Batch Review

Date: 2026-07-09
Mode: Brooks-Lint PR Review
Scope: batched active-agent plugin-memory replacement, regenerated runtime
benchmark artifacts, acceleration decision update

## Review Inputs

- `docs/harness/RUNTIME_ACCELERATION_DECISION_GUARDRAILS.md`
- `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`
- `docs/harness/PROJECT_STATE.md`
- `docs/harness/DECISION_LOG.md`
- `docs/harness/DEPRECATED_IDEAS.md`
- `docs/harness/VALIDATION_LEDGER.md`
- `artifacts/runtime_spine_review/runtime-suite-eager-smoke.md`
- `artifacts/runtime_spine_review/runtime-suite-eager-2step-smoke.md`

## Verdict

No blocking findings.

The patch changes the next implementation decision rather than adding another
reporting surface. It removes repeated per-allocation plugin-memory pool
replacement, preserves the existing selected-candidate metadata behavior, and
makes route candidate path-build the next review-ready CPU/control-flow target.

## Compact CCoT Record

```text
Question:
Should the next slice stay in active-agent pool writes or move to route
candidate path-build?

Evidence:
After batching plugin-memory replacement, active_agent_pool_write is below the
review gate in 1-step and 2-step eager suites. route_candidate_path_build is
review-ready in both suites.

Inference:
Continuing active-agent pool-write optimization now risks a local minimum. The
next useful CPU backend slice is route path-building.

Counterevidence checked:
active_agent_pool_array_write remains measurable but below threshold.
active_agent_candidate_selection remains small, so NN/JAX scoring is not the
immediate runtime fix.

Decision:
Move to a narrow Rust CPU route path-build contract next.

Falsifier:
If route path-build sub-analysis shows metadata or scoring dominates, stop
before implementing Rust graph code.

Next action:
Read routing candidate path-build internals and add RED baseline/Rust-boundary
tests.
```

## Findings

No blocking findings.

Residual risk: benchmark suites are still eager smoke diagnostics. They justify
the next engineering slice, not default backend policy or validation claims.

## Review Checklist

- Instrumentation or optimization changed the next decision: pass.
- Nested metrics are not treated as exclusive wall-clock totals: pass.
- GPU/NN is not aimed at deterministic state mutation: pass.
- Explicit backend fail-closed behavior is untouched: pass.
- Benchmark artifacts and decision docs are updated with the new boundary: pass.
