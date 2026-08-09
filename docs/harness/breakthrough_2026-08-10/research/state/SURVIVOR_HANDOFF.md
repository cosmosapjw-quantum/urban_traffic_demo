# Phase 9 Survivor-Only Formalization and Coding Handoff

DATE: 2026-08-10
DECISION_REVIEW_SHA256: `def0b9b96052e449b0b6da2802b5add2b8b65e2f2768a5a4cf96d756a9f79a7f`
H2_SUPERSEDING_DECISION_SHA256: `b660615d7044b25661c3edb9fbb95b8df7b041909663cd2508d221bb65238193`
STATUS: RESEARCH_SURVIVORS_FORMALIZED_DESIGN_ONLY

Only H-002, H-003, H-005, and the H-006 control appear below. H-001 is not a
survivor and returns to evidence acquisition. H-004 is rejected. Nothing here
authorizes implementation, production/test edits, a long gate, Task C, G5, or
Task 6.

## Fixed invariants

- Exact integer/Fraction geometry, signed orientation, exact area, DCEL
  `V-E+F=1+C`, tile partition/ownership, semantic ordering, public bytes and
  fingerprints, deterministic replay, and exhaustive cold validation.
- No external-data learning, tolerance relaxation, approximate clipping,
  trusted token bypass, silent fallback, or public API expansion.
- Canonical ordering and receipt state are dimensionless infrastructure; they
  may not reinterpret physical units or map semantics.

## S-002-R1 — virtual normalized-value canonical ordering

### Definitions

Let `D` be the finite acyclic admitted-value grammar, `N(x)` the controlling
brief's recursive Python normalization, and `B(x)` the final exact JSON byte
stream. Ordering authority is `N`, not `B`. Define virtual relations
`VEQ(x,y) := (N(x) == N(y))` and `VLT(x,y) := (N(x) < N(y))`, including the
same Python `TypeError` where normalized values are not mutually comparable.
For mappings, `PAIR_LT` reproduces normalized `(key, value)` tuple comparison
before the adjacent normalized-key collision scan. Final JSON bytes remain the
observable output but are never used as sort keys.

The candidate may compare original references only. It may not retain a
normalized tree, normalized member/key bytes, persistent prefixes, or a private
cross-type rank. A complete stable preflight must finish before any output byte
is yielded or either digest is updated.

### Conditional proposition

`SUPPORTED_DERIVATION:` Under exact admitted types, finiteness, acyclicity,
behavior freedom, stable reads, and the pinned Python 3.12 runtime, structural
`VEQ/VLT/PAIR_LT` can reproduce the outcomes of materializing `N` and invoking
the same built-in `sorted`/Timsort schedule on the same original iteration
order. This is not a total order over heterogeneous values: the same comparison
must raise the same `TypeError`. After a successful mapping-pair sort, equal
normalized keys are adjacent and reject; equal-normalized frozenset members are
admitted.

### Complexity claim

`HYPOTHESIS:` Auxiliary space is bounded by original-reference sort buffers,
control depth, and one allowed scalar token. Repeated recursive comparisons can
still make long common prefixes prohibitively slow. No analytic claim proves
the official `<32 MiB` or `<=45 s` gates.

### Required coding-design seams

1. Independently reviewed immutable spec vectors first, including numeric
   `2/10`, negative and multidigit integers, escaped/Unicode strings, mixed-type
   `TypeError`, tuple short-circuit, enum/string equality, and raw/synthetic
   tuple collisions.
2. A future separately authorized test-owned materialized-`N` differential;
   production remains unchanged during that gate.
3. Exact cycle/behavior/stable-read preflight and no-emission-before-invalidity.
4. Exact result and exception type/message/schedule parity using pinned Python
   3.12 `sorted`, then retention spies, long-prefix resource tests, six-style
   180-leaf oracle, isolated raw RSS, and separate combined-wall gate.

### Kill conditions

Any normalized-value result/error/precedence drift, output before preflight,
retained normalized state, Python-runtime mismatch, official memory failure, or
downstream-blocking long-prefix runtime kills this formulation.

## S-003 — exact projection `P`, stable capture `C`, registry transition `R`

### Projection algebra `P`

`P` maps the frozen finite grammar to exact behavior-free immutable values.
Required laws are:

- `P(P(x)) = P(x)` (idempotence);
- no caller-owned mutable object is reachable from `P(x)` (alias freedom);
- exact input types are checked before field access, iteration, equality,
  hashing, conversion, or NumPy byte access;
- cycles and unsupported behavior-bearing values fail closed;
- arrays become independent bytes-backed, C-contiguous, irreversibly read-only
  arrays with exact dtype/shape and no dtype metadata;
- mapping proxies are rebuilt from a deep-copied exact backing dictionary.

These are `HYPOTHESIS/PROOF_OBLIGATIONS`, not current implementation facts.

### Stable capture `C`

For an authority `a`, `C` obtains a pre-seal, projects a snapshot, obtains a
post-seal, and accepts only exact equality plus mandatory source cross-binding.
`CONTESTED_LIMIT:` This detects persistent TOCTOU drift under the reviewed
process-integrity model; it does not defeat unsynchronized mutate-and-restore
ABA. Stronger concurrency requires an authority-owned version/lock and is not
silently claimed.

### Locked registry `R`

All descriptor validation, input copying, candidate reconstruction, comparison,
transition, lexical eviction, clear, and count occur inside one module-owned
`RLock`. The critical section is the linearization interval for cooperating
registry operations.

Reference transitions:

| State/event | Transition |
|---|---|
| absent lookup | `MISS`, state unchanged |
| unsupported/stale lookup candidate | atomically delete, then `MISS` |
| exact current candidate | return validated immutable `HIT` |
| current-content/source mismatch | exact named error; no fallback |
| absent supported registration | insert validated copy; retain lexical 512 |
| equal supported incumbent | idempotent; preserve incumbent |
| unequal supported incumbent | collision error; preserve incumbent |
| malformed incumbent on registration | delete and fail closed; do not insert |
| clear/count/fresh process | lock-owned clear/exact length/empty new process |

`SUPPORTED_DERIVATION:` A complete lock interval gives a serial order for these
cooperating transitions. It does not linearize arbitrary upstream mutation.

### Required coding-design seams

1. Freeze a field/type/record-count grammar before adding behavior.
2. Table-driven exact/subclass/alias/cycle/mapping/array tests for `P`.
3. Persistent-drift seams for `C` and explicit ABA limitation.
4. Sequential model then deterministic barrier histories for `R`.
5. Six-style leaf/seal oracle and independent final review.

### Kill conditions

Any retained alias, hostile behavior execution, mixed accepted capture,
unsupported overwrite, lost incumbent, or non-serializable cooperating history.

## S-005 — execution-prefix phase evidence and unchanged failure

### Definitions

Freeze an execution graph `G=(V,E)`, a deterministic chronological execution
order `pi`, and an ownership function `O(v)` containing the exact payload,
schema, count, and source-byte grammar produced by phase `v`. Presentation order
is a separate mapping and is never treated as chronology.

For a trace with completed prefix `(v_1,...,v_k)` and failure during `f`, define:

- completed prefix rows: `COMPLETED` with their existing receipts;
- active row `f`: `FAILED_DURING_PHASE` with bounded diagnostics;
- every unexecuted phase: `NOT_REACHED_AFTER_FAILURE`, retaining `blocked_by=f`
  and whether the relation is descendant or fail-fast order/sibling;
- the public facade records internally and re-raises the same exception without
  rerunning any phase.

### Ownership repair

`HYPOTHESIS:` `global_corridors` must either own an actual immutable corridor
plan consumed downstream, or corridor/hierarchy/role rows must belong to their
real producing surface phase. A label cannot own data it does not create.

### Required coding-design seams

1. Current-source DAG and owner catalog, then exact byte/count grammar.
2. Independent docs review before timers/wrappers.
3. Small deterministic DAG failure at every seam, including skipped siblings.
4. Exact exception type/message/cause and zero-rerun assertions.
5. Corridor ownership mutation, success-byte identity, and overhead tests.

### Kill conditions

Misowned data, ambiguous byte grammar, lost prior receipt, rerun, chronology/
presentation confusion, changed public output/error, or unacceptable overhead.

## S-006 — mandatory falsifiable control

`SUPPORTED:` The current record does not identify one smallest integrated fix.
Keep Task 3B performance, Task B memory/state, Task 4/5 integration, and G5
instrumentation as separate gates. Run randomized no-op/baseline controls beside
mechanism tests.

`KILL_CONTROL_WHEN:` Stable exact joint-performance evidence, bounded canonical
streaming, projection/registry closure, and causal-failure evidence all pass
their independent gates. H-006 may not delay work after this joint falsifier.

## Excluded branches

- H-001: `REOPEN_EVIDENCE`; only V-001 exclusive-capacity measurement is allowed
  before a renewed claim audit/decision. No optimization plan is a survivor.
- H-004: `REJECT`; direct capsule transport adds lifecycle burden without a
  demonstrated advantage. Do not prototype it alongside the registry route.

## Claim-evidence map

| Claim | Classification | Evidence / next gate |
|---|---|---|
| Current streaming retains canonical bytes | SUPPORTED | E-006 |
| Virtual normalized-value comparison | SUPPORTED_DERIVATION, conditional | H2 reopen validation/decision |
| `<32 MiB` and practical runtime | HYPOTHESIS | V-002 official gate |
| Current snapshot alias and hostile lookup | SUPPORTED | E-007/E-008 |
| `P/C/R` closes all cases | HYPOTHESIS | V-003 |
| Registry-only linearizability | SUPPORTED_DERIVATION | Phase 6, exact lock scope |
| Current G5 ownership/failure grammar is defective | SUPPORTED | E-014/E-015 |
| Execution-prefix repair is correct | HYPOTHESIS | V-005 |
| Task 3B exact sufficient change set exists | INFERENCE_ONLY / REOPEN | V-001 |
| Task 4/5 receipts are integrated | UNSUPPORTED | separate future Task C |

## Coding-harness handoff order

1. Contract-only acceptance of S-002/S-003/S-005 and S-006 limits.
2. Read-only repository localization and exact impact map.
3. At most three bounded solutions, with S-002 then S-003 as the selected
   Task B path; S-005 remains docs-first and dependency-gated.
4. Write milestones/tests/kill criteria only. Phase 5 implementation and later
   execution gates are `NOT_AUTHORIZED` in this run.

PHASE_9_STATUS: COMPLETE_SURVIVORS_ONLY
