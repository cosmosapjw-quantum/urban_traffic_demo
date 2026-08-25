# Codex Handoff — MetroFlow Rust-Owned Engine Migration

You are receiving an **audit-compiled execution package**, not a prose implementation suggestion.

Repository:

```text
cosmosapjw-quantum/urban_traffic_demo
```

Audit source:

```text
main SHA: 01c80b432344f94209daaa198bb1eb007839fc7f
tree SHA: 13ab0dd317d2581b83aba2d8b7763ef644dd30fb
```

Primary authority:

```text
docs/exec-plans/rust-default-engine/AUDIT_COMPILED_EXEC_PLAN_V1.json
```

Read in this exact order:

```text
1. AGENTS.md
2. docs/quality/P0_P1_POLICY.md, if present in the current base
3. docs/audit/RUST_DEFAULT_ENGINE_ADVERSARIAL_AUDIT_20260824.md
4. docs/exec-plans/rust-default-engine/README.md
5. docs/exec-plans/rust-default-engine/RUST_ENGINE_ARCHITECTURE_CONTRACT_V1.json
6. docs/exec-plans/rust-default-engine/AUDIT_COMPILED_EXEC_PLAN_V1.json
7. docs/exec-plans/rust-default-engine/RUST_ENGINE_P0_P1_THREAT_CATALOGUE_V1.json
8. docs/exec-plans/rust-default-engine/RUST_ENGINE_INVARIANT_TEST_MATRIX_V1.json
9. docs/exec-plans/rust-default-engine/RUST_ENGINE_EVIDENCE_BUNDLE_SCHEMA_V1.json
10. docs/exec-plans/rust-default-engine/RUST_ENGINE_FRESH_CONTEXT_REVIEW_CONTRACT_V1.json
```

## Immediate instruction

Do **not** start Rust migration implementation until this command returns exit 0:

```bash
python tools/validate_rust_default_engine_plan.py   --check-readiness RUST-PR-001
```

The current expected result is:

```text
BLOCKED_BY_PREDECESSOR_DAG
```

because the existing map-generation DAG must finish through `MAP-PR-011`.

A blocked result is correct completion for the current state. Do not bypass, reorder, or edit the existing MAP DAG.

## When the predecessor is complete

Materialize exactly one PR contract:

```bash
python tools/materialize_rust_default_engine_pr.py   --pr-id RUST-PR-001   --base-sha "$(git rev-parse main)"   --output ".codex/contracts/RUST-PR-001.json"
```

Then implement **RUST-PR-001 only**.

Never implement a later PR early. The overall migration is whole-engine, but each PR is one semantic risk unit.

## Agent policy

```text
ASK_USER_QUESTIONS = false
GUESS_ACROSS_SPEC_BOUNDARY = forbidden
UNRESOLVED_SPEC_ACTION = BLOCKED_BY_UNRESOLVED_SPEC
CHANGE_TESTS_OR_TOLERANCES_TO_FIT_IMPLEMENTATION = forbidden
SUPPRESS_OR_RECLASSIFY_FAILURES = forbidden
SAME_CONTEXT_FINAL_REVIEW = forbidden
```

Repository/docs/tests are the source for resolving ambiguity. If they do not resolve it, stop with exact evidence rather than inventing semantics.

## Core architectural objective

Final target:

```text
Python:
  CLI, config authoring, UI, reporting, plotting, benchmark orchestration,
  optional learning experiment frontend, explicit python_oracle debug backend.

Rust:
  canonical static and dynamic state, scheduler, RNG, controls/events, demand,
  routing, flow, agents, land-use/policy state, invariants, replay,
  checkpoint/restore, runtime metrics.

GPU:
  optional coarse persistent numeric chunks after Rust CPU parity.
```

Do not continue the present pattern of adding isolated Vec-in/Vec-out kernels to the default path. The default endpoint is a persistent Rust `Engine` with coarse calls.

## Per-PR workflow

1. Verify exact base SHA and clean worktree.
2. Run plan validation and readiness.
3. Read only the materialized PR contract plus referenced source/tests.
4. Demonstrate public-behavior RED.
5. Implement bounded GREEN.
6. Run targeted, negative, regression, cargo and full-relevant checks.
7. Compute actual changed paths with Git.
8. Fill an evidence bundle conforming to the schema.
9. Self-review for obvious defects.
10. Stop implementation context.
11. Start a fresh reviewer context with:
    - exact base SHA,
    - exact final SHA,
    - actual diff,
    - materialized contract,
    - raw logs,
    - unresolved blockers.
12. Reviewer first pass is audit-only.
13. P0/P1 findings go back to implementation context.
14. Repeat until P0=0, P1=0, unresolved=0.
15. Merge only then.

## Evidence command

```bash
python tools/verify_rust_default_engine_evidence.py   --contract ".codex/contracts/RUST-PR-001.json"   --evidence ".codex/evidence/RUST-PR-001.json"
```

## Forbidden shortcuts

- Do not mark a partial subsystem port as a complete Rust engine.
- Do not retain `.tolist()` or per-entity Python/Rust calls in the final default path.
- Do not modify the Python oracle, scientific outputs or tolerances to make Rust pass.
- Do not use unordered floating reductions or float atomics for canonical state.
- Do not enable nightly `std::simd` or fast-math as the default.
- Do not introduce silent fallback.
- Do not make GPU availability a prerequisite for Rust CPU correctness.
- Do not claim speedup without the complete shadow/performance receipt.

## Handoff completion format

Return:

```text
PR_ID
BASE_SHA
FINAL_SHA
ACTUAL_CHANGED_PATHS
COMMANDS_AND_EXIT_CODES
INVARIANT_RESULTS
FAILURE_MODE_RESULTS
UNRESOLVED_BLOCKERS
EVIDENCE_BUNDLE_PATH
FRESH_REVIEW_RECEIPT_PATH
VERDICT
```

Until MAP-PR-011 is complete, return:

```text
VERDICT=BLOCKED_BY_PREDECESSOR_DAG
```
