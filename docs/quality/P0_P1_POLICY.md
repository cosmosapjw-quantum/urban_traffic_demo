# P0/P1 Policy for MetroFlow Research Code

This repository is a single-developer research project. Security, hostile tampering,
multi-user authorization, compliance, and enterprise release governance are out of
scope unless the user explicitly changes the project threat model.

## P0

A defect is P0 when it can silently produce or bless wrong research behavior:

- wrong units, dtype, sign, boundary condition, phase order, RNG stream, or cache state;
- route-legality, topology, conservation, checkpoint, or deterministic-replay failure;
- multiple components mutating one canonical state without a single transaction;
- a failed or stale evidence surface being accepted as success;
- changing oracle outputs, tolerances, negative results, or frozen evidence to fit code;
- silent backend fallback that hides a missing or failed authority.

## P1

A defect is P1 when it leaves a major implementation or evidence boundary incomplete:

- missing principal edge/boundary cases;
- a fallback, cache invalidation, checkpoint, or backend-selection path not covered;
- partial implementation reported as complete;
- required tests/receipts absent or skippable;
- performance claims excluding transfer, compile, allocation, memory, or full-engine costs;
- a fresh-context review not performed;
- a specification boundary guessed rather than blocked.

## Executable-contract rule

Every foreseen P0/P1 must have at least one of:

1. an executable positive/negative/regression test;
2. a mechanically checkable assertion/invariant;
3. a registered STOP/BLOCKED gate when mechanical verification is impossible.

A prose warning alone is not a valid P0/P1 control.

## Agent policy

```text
DO_NOT_ASK_USER_QUESTIONS = true
DO_NOT_GUESS_ACROSS_SPECIFICATION_BOUNDARY = true
UNRESOLVED_SPEC_ACTION = BLOCKED_BY_UNRESOLVED_SPEC
CHANGE_TESTS_OR_TOLERANCES_TO_FIT_IMPLEMENTATION = forbidden
SUPPRESS_FAILURES = forbidden
SAME_CONTEXT_FINAL_REVIEW = forbidden
```

Agents must search repository code, docs, tests, and frozen artifacts first. If those
sources do not determine the required semantics, stop with exact blocker evidence.

## Merge closure

For a high-risk PR:

```text
P0 = 0
P1 = 0
unresolved = 0
actual diff is within scope
required evidence bundle is complete
fresh-context audit-only review passes
```

P2/P3 may remain only when explicitly recorded and outside the PR claim.
