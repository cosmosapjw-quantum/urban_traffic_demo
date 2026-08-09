# RESEARCH_STATE

PROJECT: Urban Traffic Scalable Map Breakthrough
VERSION: 1.0
CURRENT_PHASE: closeout_complete
LAST_UPDATED: 2026-08-10

## Primary question

PRIMARY_RQ: What is the smallest invariant-preserving algorithmic and
architectural change set that can close the current scalable-city map blockers
without changing exact public authority bytes, physical geometry, deterministic
replay, or fail-closed validation?

## Subquestions

1. Which jointly sufficient Task 3B kernels can remove at least the measured
   7.531264014-second wall gap, given that eliminating `_digest` alone is
   mathematically insufficient?
2. What exact streaming-order construction satisfies the receipt serializer's
   canonical equivalence while retaining only original key/member references
   under the 32 MiB delta?
3. What immutable projection algebra and linearizable registry state machine
   close the remaining Task B alias/hostile-candidate/lock blockers?
4. How can Task 4/5 consume current-content receipts without weakening cold
   exhaustive validation or introducing a trusted bypass?
5. What causal phase-result representation makes G5/Task 6 instrumentation
   truthful on both success and failure paths?

## Scope

IN_SCOPE:

- Current frozen Task 3B, Task 4, Task 5, Task B, G5, and Task 6 evidence.
- Exact integer-millimetre and `Fraction` geometry, DCEL invariants, tile
  partitioning, deterministic semantic identities, receipt canonicalization,
  snapshot immutability, registry linearizability, and runtime complexity.
- Read-only source inspection, bounded diagnostics, mathematical derivation,
  hypothesis comparison, and verification-plan design.

OUT_OF_SCOPE:

- Production or test edits, commit/push/PR actions, traffic-flow/routing/demand
  algorithm work, new external datasets, tolerance or gate relaxation, output
  resealing, and any claim that Task 3B or Task B is already admitted.

## Conventions

- Coordinates and lengths owned by scalable geometry are exact integer mm
  unless a type explicitly carries exact `Fraction` mm.
- Areas are exact mm^2; no floating-point geometric predicate is admitted.
- Canonical byte and fingerprint equality is exact, not tolerance based.
- Runtime figures are fresh-process wall receipts, not derivations.
- Existing public authority bytes and fingerprints are fixed observables.
- `PASS`, `FAIL`, `BLOCKED`, and research-hypothesis decisions remain distinct.

## Evidence standard

- Primary project source and frozen reports/reviews with exact hashes.
- Reproducible bounded source inspection or diagnostics with exact commands.
- Mathematical arguments must expose assumptions, dimensions, limiting cases,
  counterexamples, and falsifiers.
- Literature is optional and may not override current project measurements.

## Approval boundary

- Research-state files under this temporary harness may be updated.
- No repository production/test/brief/review/manifest file may be changed.
- No candidate may be promoted directly by its producer; independent review and
  decision gates are required.

## Hypothesis status

ACTIVE_HYPOTHESES: none; H-002 was narrowly reopened and superseded before closeout

PROMOTED: H-002-R1 normalized-value design, H-003, H-005, H-006-control
(design formalization only)

ON_HOLD: H-001 (`REOPEN_EVIDENCE`, V-001 only)

REJECTED: H-004 private capsule transport

## Blockers

KEY_BLOCKERS:

- Task 3B public wall 27.502387543/27.458000162 s exceeds strict <20 s.
- `_digest` complete elimination would still leave 21.032597882 s.
- Task B is chronology-clean only through Slice 18 and lacks remaining bounded
  streaming, deep snapshot, hostile-candidate, and final six-style closure.
- Task 4/5 receipt integration and final Task 5 review remain closed.
- G5 instrumentation has unresolved source-ownership and failure-state grammar.

MISSING_EVIDENCE:

- Non-overlapping ablation estimates for a jointly sufficient Task 3B bundle.
- Immutable normalized-value vectors and a proof/test pair for lazy canonical
  ordering without materializing `N` or normalized member/key bytes.
- A complete immutable snapshot grammar and linearizability model.
- Current-source causal phase ownership and failure-envelope proof.

## Gate

CURRENT_COMPLETION_BAR:

- Every core blocker has direct current evidence or an explicit evidence gap.
- Distinct candidate families have a falsifier and costed verification path.
- Physics/math audit finds no fatal geometry/unit/topology inconsistency in any
  promoted survivor.
- Independent decision gate selects PROMOTE/HOLD/REJECT without aggregate-score
  substitution.

NEXT_GATE: Independent re-review of the corrected coding-harness plan

NEXT_MINIMAL_ACTION: Replace every obsolete byte-order claim in the coding plan,
freeze immutable normalized-value vectors and exact resource/contract gates, and
obtain an independent zero-P0/P1/P2 plan verdict before any implementation.
