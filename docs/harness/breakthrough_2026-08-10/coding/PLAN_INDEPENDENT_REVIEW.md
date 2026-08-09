# Breakthrough Plan Independent Review

DATE: 2026-08-10
REVIEW_SCOPE: plan-only; intentionally no production diff
PLAN_SHA256: `cf50117959a7a9ed47f25456235f5f27fd59d6bc09bf5921bf20a2a2ff8e1ec0`
REVIEWER: independent non-author
VERDICT: **BLOCKED**

The project hashes match baseline. With no implementation, no P0 is reported.
Six P1 and three P2 findings block authorization and strict chronology closure.

## P1 blockers

### P1-1 — H-002 orders canonical JSON bytes, but the controlling brief orders normalized Python values

**Location:** `BREAKTHROUGH_PLAN.md:148-233`; controlling brief `:381-422`;
current receipt source `:525-543,576-585`.

**Impact:** A transitive comparator can match the current materialized function
while violating the reviewed table, corrupting all downstream receipt evidence.

**Evidence:** The brief specifies `tuple(sorted(normalized_items))` and sorted
normalized mapping pairs. Current materialized and streaming code sort JSON
encodings. A fresh current-hash probe produced:

```text
frozenset(2, 10): ["frozenset",[10,2]]
dict {2, 10}:     [[10,"ten"],[2,"two"]]
```

Both implementations agree, but Python's integer order is `2, 10`; mixed
normalized types can also make bare Python sorting fail with `TypeError`.

**Required repair:** Before the behavior manifest, freeze one reviewed total
ordering contract and immutable discriminating vectors including `2/10`, mixed
normalized types, escaped strings, enum/string equality, and mapping collision.
Do not let the implementation or current buggy reference choose the authority.

### P1-2 — the official RSS command is guaranteed to fail, and no practical-runtime gate is executable

**Location:** `BREAKTHROUGH_PLAN.md:410-424`; frozen controller
`tools/run_task45_validation_performance.py:30-55,568-575`; brief `:2004-2020`.

**Impact:** The command cannot run. Correcting it gates RSS only, not the required
`<=45 s` wall, so a prohibitively slow H-002 could still appear admitted.

**Evidence:** The controller requires the exact output argument
`.superpowers/sdd/scalable_synthetic_v2_implementation_plan/task-4-5-validation-performance-report.md`.
The plan supplies `task-45-validation-performance.json`; `_parse_args` rejects
any nonexact tuple with parser exit 2. The plan's “unacceptable runtime
regression” has no command, threshold, or receipt.

**Required repair:** Use the controller's exact frozen command/output and add the
separate exact fresh-process combined-wall command and `<=45 s` disposition.
Bind output mutation authority explicitly. Keep RSS and runtime as separate gates.

### P1-3 — the completeness manifest is stored in a report that every later slice mutates

**Location:** `BREAKTHROUGH_PLAN.md:41-92,96-143`.

**Impact:** The Task 1 hash becomes stale on the first append, so nothing proves
manifest rows were not edited after observing a late requirement.

**Evidence:** Task 1 puts the manifest in the “designated mutable replay report”
and hashes the “manifest-bearing report”; Tasks 2-6 repeatedly append that same
report. No immutable sidecar, canonical byte range, prefix hash, or per-append
prefix verification is defined.

**Required repair:** Give the reviewed manifest immutable bytes of its own, or
freeze an exact report prefix/section digest and verify that prefix before every
append. Bind the independent manifest review to that immutable digest.

### P1-4 — known exact-schema and record-count boundaries are not actually frozen

**Location:** `BREAKTHROUGH_PLAN.md:63-83,245-294,359-383,511-518`; brief
`:1028-1147,1164-1180`; current/scaffold `_Task5CsrProjection`.

**Impact:** Replay can finish green against the wrong private schema and certify
chosen rather than authoritative 180-leaf counts.

**Evidence:** The brief declares
`arrays: tuple[tuple[str, np.ndarray], ...]`; both the authoritative scaffold and
current source declare `Any`. The plan says schema changes are a kill condition
and its self-review claims schemas match, but no annotation/API RED repairs this.
Likewise, “catalog/map leaves `1 + their declared repeated rows`” is not an exact
formula for each static leaf. `allowed_mapping_leaves` object-identity admission
is a proposed interpretation, not frozen brief text, and changes current type-
allowlist behavior.

**Required repair:** Resolve these as reviewed contract rows before reset. List
every private annotation, per-leaf mapping admission object/type rule, and all 30
leaf record-count formulas literally; add independent API/formula vectors.

### P1-5 — the stated slice order cannot make every mapping rejection node RED

**Location:** `BREAKTHROUGH_PLAN.md:55-61,79-83,161-179`.

**Impact:** Inventory cannot create a historical RED; first-GREEN/masking can recur.

**Evidence:** After Step 1 implements primitive fallthrough rejection, an
unlisted exact dict, dict subclass, arbitrary Mapping, and hostile proxy/backing
can already reject with zero behavior calls. Their negative tests may therefore
start GREEN before mapping admission exists. Conversely, grouping primitive,
tuple, Fraction, float, enum, and frozenset in one node permits an early missing
branch to mask later branches. Resetting farther back to a universal stub makes
negative tests fail only on the common stub, not on their claimed owner behavior.

**Required repair:** Dry-run every manifest node against its exact scratch
checkpoint before any live replacement and preserve exit/discriminator output.
Classify naturally already-green fail-closed guards as non-owning regression
tests or obtain an explicit lifecycle interpretation/waiver; do not fabricate a
RED or count a common stub as several behavior-specific REDs.

### P1-6 — stable capture is assigned to the wrong file and has no exact seam

**Location:** `BREAKTHROUGH_PLAN.md:55-61,298-355`; brief `:1191-1293`;
`CODE_TASK.md` out-of-scope boundary.

**Impact:** Step 7 either invents an API or cannot run; it pulls future Task 5
integration into the two-file Task B replay.

**Evidence:** The controlling brief assigns both stable capture functions to
`scalable_authority.py` with exact signatures. The plan edits only the receipt
module/tests, gives only “a named copy seam,” and forbids Task 3/3B/4/5 edits and
Task C integration.

**Required repair:** Remove production capture `C` from the Task B replay and
defer it to an authorized Task 5 integration plan, or first amend/review an exact
receipt-module helper contract and scope. A placeholder seam is insufficient.

## P2 findings

### P2-1 — exact recovery and regression commands are incomplete

**Location:** `BREAKTHROUGH_PLAN.md:107-143,403-408`.

The source JSONL extraction command was reproduced and yields the expected
`55734c7b...` hash. No equivalent line/pointer/hash is supplied for the API-only
test checkpoint. “Task3+3B focused,” “legacy nine-file suite,” and “ordered 80”
are not exact commands. The option to fix a cross-file isolation assertion is
also outside the two-file scope. Bind the test checkpoint exactly, enumerate all
commands/paths, and stop on unrelated failures rather than embedding a future fix.

### P2-2 — several REDs and kill gates have no frozen parameters

**Location:** `BREAKTHROUGH_PLAN.md:181-186,229-241,327-332`.

The bounded `tracemalloc` threshold/input cardinality, randomized seed/case
count, long-prefix runtime budget, and malformed-candidate delete-versus-error
semantics are deferred to implementation. `_VALIDATION_RECEIPT_LOCK._is_owned()`
is a private CPython probe proposed as a production assertion rather than a
test-only observation. Freeze exact parameters/error outcomes and avoid making a
private interpreter method part of production correctness.

### P2-3 — plan provenance references are undefined and the self-review overclaims completeness

**Location:** `BREAKTHROUGH_PLAN.md:49-53,511-518`.

`S-002` and `S-003` are not defined anywhere in the coding harness. The claim
that no error handling, tests, or tolerances remain unspecified conflicts with
P1-2/P1-4/P1-6 and P2-2. Replace the identifiers with exact paths/hashes and
rerun self-review only after all placeholders are closed.

## Review gate

```text
Review Gate: BLOCKED
Open P0: 0
Open P1: 6
Open P2: 3
Open P3: 0
Implementation authorization: NO
Strict chronology closure demonstrated by plan: NO
```

No repository file was edited, no long test was run, and no production-diff
correctness verdict is made because the planned diff does not yet exist.
