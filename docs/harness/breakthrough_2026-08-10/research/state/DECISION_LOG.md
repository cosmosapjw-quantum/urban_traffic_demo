# DECISION_LOG

Phase 8 decisions are bound to `state/EXTERNAL_DECISION_REVIEW.md`. `PROMOTE`
means survivor-only research/coding-design formalization, never implementation
authorization or a gate pass.

## D-001

DATE: 2026-08-10  
DECISION: `REOPEN_EVIDENCE`  
OBJECT: H-001, repaired smallest-measured exact intervention-set search  
EVIDENCE_REVIEWED: E-001--E-005, E-016; Phase 5; Phase 6; V-001  
RATIONALE: The deficit and digest-only insufficiency are supported, but no
non-overlapping measurement supports a sufficient intervention set or its
cardinality.  
ALTERNATIVES_CONSIDERED: Promote the measurement protocol; reject the branch as
non-mechanistic.  
UNRESOLVED_RISKS: capacity, interaction, run variability, prototype transfer  
NEXT_GATE: V-001 exclusive-capacity receipt, ledger audit, renewed Phase 8

## D-002

DATE: 2026-08-10  
DECISION: `PROMOTE`  
OBJECT: H-002, repaired finite/acyclic/stable virtual canonical-byte ordering  
EVIDENCE_REVIEWED: E-006, E-009, E-017; Phase 5; Phase 6; V-002  
RATIONALE: The defect is reproduced and the conditional ordering argument is
valid, distinguishable, and cheaply falsifiable.  
ALTERNATIVES_CONSIDERED: reference-only radix/prefix partition; H-006 control  
UNRESOLVED_RISKS: raw RSS, retained state, long-prefix replay time  
NEXT_GATE: Phase 9 design formalization only; no implementation or gate pass

## D-003

DATE: 2026-08-10  
DECISION: `PROMOTE`  
OBJECT: H-003, repaired projection `P` / stable capture `C` / locked registry `R`  
EVIDENCE_REVIEWED: E-007--E-010, E-013; Phase 5; Phase 6; V-003  
RATIONALE: Direct alias/hostile defects motivate the separated contract, whose
linearizability claim is now limited to cooperating registry-owned state.  
ALTERNATIVES_CONSIDERED: H-004 direct transport  
UNRESOLVED_RISKS: field completeness, cycles, capture drift, history coverage  
NEXT_GATE: Phase 9 design formalization only; no implementation or Task B pass

## D-004

DATE: 2026-08-10  
DECISION: `REJECT`  
OBJECT: H-004, repaired current-content-verified private receipt transport  
EVIDENCE_REVIEWED: E-011--E-013, E-017; Phase 5; Phase 6; V-004  
RATIONALE: It inherits H-003 trust work, adds lifecycle state, and has no evidence
of a distinct end-to-end advantage over the reviewed registry route.  
ALTERNATIVES_CONSIDERED: Hold for V-004 comparison  
UNRESOLVED_RISKS: an unmeasured advantage could emerge later  
NEXT_GATE: none; a new evidence-backed transport hypothesis would require reopening

## D-005

DATE: 2026-08-10  
DECISION: `PROMOTE`  
OBJECT: H-005, repaired chronological execution-prefix failure contract  
EVIDENCE_REVIEWED: E-014, E-015, E-017; Phase 5; Phase 6; V-005  
RATIONALE: The ownership/status defects are supported, and the repaired internal
record plus unchanged re-raise model removes the ancestor-only/public-error flaws.  
ALTERNATIVES_CONSIDERED: atomic-wrapper boundary reporting  
UNRESOLVED_RISKS: source ownership, exact grammar, skipped-sibling reasons, trace fidelity  
NEXT_GATE: Phase 9 design formalization only; no G5/Task 6 implementation or pass

## D-006

DATE: 2026-08-10  
DECISION: `PROMOTE`  
OBJECT: H-006, bounded null/systematic control  
EVIDENCE_REVIEWED: E-003, E-006, E-009, E-013, E-017; Phase 5; Phase 6; V-006  
RATIONALE: The audited record directly supports uncertainty separation, and the
control has an explicit joint falsifier.  
ALTERNATIVES_CONSIDERED: Hold because it closes no blocker  
UNRESOLVED_RISKS: misuse as an unfalsifiable delay mechanism  
NEXT_GATE: Phase 9 control formalization only; no production code or blocker claim

## D-002-R1 (supersedes D-002's byte-order formulation)

DATE: 2026-08-10  
DECISION: `PROMOTE`  
OBJECT: H-002-R1, virtual normalized-Python-value ordering  
EVIDENCE_REVIEWED: H2 reopen analysis `fd3bb760...`, validation `a5ffbb14...`,
coding-plan review `db991ac6...`, external decision `b660615d...`  
RATIONALE: The former lexicographic JSON-byte proof is false (`2/10` is a direct
counterexample). Under finite/acyclic/behavior-free/stable-read inputs and pinned
Python 3.12, virtual `VEQ/VLT/PAIR_LT` can conditionally reproduce the brief's
materialized normalized-value sort and exact comparison exceptions.  
ALTERNATIVES_CONSIDERED: Hold until executable vectors; reject after the false
byte-order theorem; generic mergesort.  
UNRESOLVED_RISKS: immutable vectors, exact exception schedule, retained state,
raw RSS, long-prefix work, combined wall  
NEXT_GATE: revised coding design and immutable-vector review only; any prototype
or project edit requires separate authorization
