# Corrected Breakthrough Plan Independent Rereview

DATE: 2026-08-10  
REVIEW_SCOPE: final plan and pre-reset design contracts only; no production diff  
REVIEWER: independent non-author  
VERDICT: **PASS — PLAN ONLY**  
IMPLEMENTATION_AUTHORITY: **NO**

The final corrected plan closes all six P1 and three P2 findings from the
initial review. It is a coherent, fail-closed route to a future clean-room
replay. This verdict authorizes no project write, reset, test change, production
implementation, Task C, Task 4/5 capture integration, long performance run,
commit, push, PR, or traffic-algorithm transition.

## Bound inputs

| Input | SHA-256 | Disposition |
|---|---|---|
| `BREAKTHROUGH_PLAN.md` | `abec626aaf2f71bb9429d646db8b8d7ffd82594b0b3a2db4cbf267f1074fabdf` | final reviewed candidate |
| `H2_ORDERING_CONTRACT.md` | `48b0f180d69df9ca2504fa16a45035f4d470ca7393436d5aaaa0d3cb0629fc4c` | final reviewed H-002-R1 contract |
| `CONTRACT_ROWS.md` | `c5c735832f72c2685c0eda6eefcb8a9db8062e06da9f297fc62987a0e6a7cf82` | final reviewed schema/count/mapping contract |
| initial independent review | `db991ac6252e9f094d7ad5b1a1c9ffe875911a41fa74e8a675e4c1796ba2a700` | preserved BLOCK evidence |
| H-002 reopened decision | `b660615d7044b25661c3edb9fbb95b8df7b041909663cd2508d221bb65238193` | conditional design promotion only |
| controlling Task 4/5 brief | `41585f436832e37d734b80bd52c195ca7b922170cadf4d2b69894bb8609fcf6c` | normalization, schema, capture, and performance authority |

The project checkpoint hashes in the plan were independently rechecked:
receipt source `5181eb4b...`, focused tests `434442e0...`, and replay report
`2f63435a...`. The four rebound research closeout/state hashes also match their
current files.

## Prior finding closure

| Finding | Final disposition | Evidence in final candidate |
|---|---|---|
| P1-1 normalized Python order versus JSON-byte order | **CLOSED** | Plan sections 1.2 and 4 plus `H2_ORDERING_CONTRACT.md` make materialized `N`, Python 3.12 sorting, pair-value precedence, `2/10`, mixed-type errors, and immutable independent vectors authoritative. JSON bytes are output only. |
| P1-2 invalid RSS command and absent wall gate | **CLOSED** | Plan 9.1 reproduces the controller's exact argv/output and append authority. Plan 9.2 adds two fresh processes, a literal syntactically valid script, `<=45_000_000_000 ns`, environment receipts, nonzero-exit failure, and cross-replicate fingerprint equality. RSS and wall cannot offset one another. |
| P1-3 self-staling manifest | **CLOSED** | Plan 1.3-1.5 assigns immutable bytes to a dedicated manifest and review, keeps chronology in the mutable report, binds the manifest SHA before each slice, and invalidates rather than edits it when a new owner behavior appears. |
| P1-4 schema, mapping, and counts left to implementation | **CLOSED** | `CONTRACT_ROWS.md` freezes all ten private records including `_Task5CsrProjection.arrays: tuple[tuple[str, np.ndarray], ...]`, signed seeds, identity-scoped per-leaf mapping admission, all 30 record-count formulas, and malformed-incumbent semantics. Plan 1.1 requires a zero-finding pre-reset review and stops on disagreement. |
| P1-5 negative mapping/CSR nodes could start GREEN | **CLOSED** | Plan 1.3-1.4 separates `OWNER_RED`, `REGRESSION_GREEN`, and `SETUP_INVALID`, forbids one common stub from owning hidden branches, and requires a scratch dry-run at every exact checkpoint before live replacement. Sections 3 and 5 apply this rule to mappings, primitive branches, and CSR guards. |
| P1-6 stable capture assigned to the two-file Task B lane | **CLOSED** | Plan 6 explicitly limits Task B to projection/registry primitives and defers both named capture functions to a separately authorized `scalable_authority.py` integration plan. Section 9 remains closed after Task B. |
| P2-1 incomplete checkpoint and regression commands | **CLOSED** | Plan 2 binds one JSONL line/call ID, both byte lengths and hashes, both extraction commands, and the exact scaffold node. Section 8 enumerates focused, lint/format, Task 3/3B, legacy nine-file, downstream collection/single-adapter/ordered-two-file, and oracle commands; it additionally freezes exactly 80 downstream node IDs and ordered-body SHA `70026af8...`. An unrelated isolation failure blocks and is not fixed in the two-file lane. |
| P2-2 unfrozen RED/resource/registry parameters | **CLOSED** | Plan 4 and the H2 contract freeze `PYTHONHASHSEED=0`, runtime provenance, `random.Random(20260810)`, 10,000 cases, maximum depth 8, a frozen corpus/hash, exact 700-member common-prefix fixtures, three GCs, tracing/timer boundaries, `32 MiB`, `45 s`, and no final join. `CONTRACT_ROWS.md` fixes malformed lookup/register outcomes; `_is_owned()` is test-spy-only. |
| P2-3 undefined provenance and overclaimed self-review | **CLOSED** | Undefined `S-002`/`S-003` references and the contradictory completeness claim are absent. Paths and hashes are literal, uncertainties remain explicit, and the plan ends with `IMPLEMENTATION_AUTHORITY: NO`. |

## Additional adversarial checks

### Artifact authority and chronology

The normalized-order vector corpus is owned by the separate immutable JSON
packet, not by the already-reviewed H2 contract or mutable replay report. The
vector review and manifest review are separate artifacts. A late behavior
discovery invalidates the manifest. This avoids stale-prefix and post-hoc RED
selection.

### Deterministic ordering and error evidence

The final bytes close the fresh-process nondeterminism risk: vector generation,
replay, focused tests, dependency tests, and oracle verification use
`PYTHONHASHSEED=0`; the exact CPython implementation/version/executable/platform
is recorded. The randomized corpus is local, source-bound, ordered, and hashed.
Claims about Timsort schedule and exact exception messages are explicitly
restricted to that environment.

### Memory and runtime false-green resistance

The long-prefix fixtures are constructed before measurement. Three exact GCs
precede tracing; `tracemalloc.start()`/`reset_peak()` and `perf_counter_ns()`
begin at the frozen boundary; consumption stops only after a test-owned
sort-completed observation and does not join the final stream. The focused
Python-allocation discriminator, official raw `VmRSS` controller, and combined
wall gate are three separate falsifiers. None is presented as already passed.

### Scope and dependency integrity

Task B may change only the receipt source and focused receipt test under a
future authorization. Capture `C`, source registration, Task 4/5 integration,
Task 3B capacity work, and G5 instrumentation have separate prerequisites. The
plan preserves the current Task 3B `<20 s` failure, Task 5 ordered-suite blocker,
and absence of traffic-algorithm authority.

## Reviewer-role assessment

### Domain expert

No physical geometry, unit, DCEL, tile ownership, public payload, fingerprint,
or replay convention is redefined. The plan narrows itself to validation
evidence and preserves S2-before-S1 and the baseline path. Domain impact is
therefore nil at this design-only stage.

### Numerical-methods reviewer

H-002-R1 is a conditional algorithmic construction, not a measured result. Its
reference relation, exception precedence, stability assumption, bounded input
grammar, randomized/exhaustive differentials, memory limit, and runtime kill are
falsifiable. No tolerance, approximate order, hash order, or calibration is
introduced.

### Software/reproducibility reviewer

Recovery bytes, environment, commands, immutable evidence, mutation authority,
RED ownership, rollback hashes, and cross-file stop conditions are explicit.
The plan prevents current buggy serializer agreement from becoming an oracle
and prevents a first-GREEN guard from being relabeled RED.

### Skeptical editor

The minimal defensible claim is: the corrected design is ready to request
authority for the pre-reset vector/manifest packet. It is not implementation
ready until those immutable artifacts exist and pass their own independent
reviews, and it is not a city-map completion, performance pass, or traffic
algorithm result.

## Validation summary

### Changed files

- `PLAN_INDEPENDENT_REREVIEW.md` only — pure documentation/review evidence.
- No project source, test, report, brief, oracle, or prior review was edited.

### Commands run

| Command | Result | Notes |
|---|---:|---|
| `sha256sum` over the three final candidates, initial review, H2 decision, controlling brief, project checkpoint, and rebound research state | PASS | All hashes match the bound values above. |
| Extract the plan 9.2 shell body and pipe it to `bash -n` | PASS | Exit 0; syntax only, no map build. |
| `python3 tools/validate_harness.py` from the coding-harness root | PASS | Exit 0: `Coding harness validation passed.` |

### Numerical impact

None. This rereview changes no executable or numerical artifact and runs no
simulation, serializer implementation, oracle regeneration, or benchmark.

### Reproducibility notes

- Review conclusions are bound to the complete SHA-256 values above.
- H-002 exact error/schedule claims are limited to the future recorded CPython
  3.12, `PYTHONHASHSEED=0` environment.
- Prior `177 passed` and timing/RSS observations remain prior receipts; they
  were not rerun or promoted by this review.

### Failures / skipped checks

- No production diff exists, so no implementation correctness verdict is made.
- Focused Task B, six-style 180-leaf, dependency, oracle, official RSS, combined
  wall, Task 3B capacity, Task 4/5 integration, G5, and traffic gates were not
  run.
- The immutable vector packet, behavior manifest, and their independent reviews
  do not yet exist. Their absence is a planned pre-implementation hard stop, not
  an open defect in this plan.

### Remaining risks

- Algorithm A may fail exact differential, memory, or runtime gates.
- Identity-scoped proxy backing and the 30 counts still require the planned
  executable vectors before source replacement.
- Task 3B performance, Task 5 readiness, G5 authority, and traffic readiness
  remain independently open.

### Next validation step

After explicit file authority, create the immutable normalized-order vector
packet and behavior manifest, dry-run every proposed node against its exact
scratch checkpoint, and obtain zero-finding independent reviews before any live
two-file replacement.

## Suggested claims

### Required downclaims

- “corrected clean-room replay design passed independent plan review”;
- “H-002-R1 is conditionally testable, not implemented or admitted”;
- “Task B, Task C, Task 3B performance, Task 5, G5, and traffic work remain
  unclosed.”

### Stronger claim permitted only later

“Task B is strictly replayed and admitted” requires the frozen manifest/vector
reviews, every owned RED/GREEN receipt, final two-file hashes, focused/dependency
gates, exact six-style equivalence, H-002 resource admission, and a new final
implementation review.

## Review gate

```text
Review Gate: PASS — PLAN ONLY
Open P0: 0
Open P1: 0
Open P2: 0
Open P3: 0
Prior 6 P1 / 3 P2: CLOSED IN FINAL BOUND BYTES
Plan suitable for requesting pre-reset artifact authority: YES
Strict chronology proof executed: NO
Implementation authorization: NO
Task C authorization: NO
Traffic-algorithm authorization: NO
```
