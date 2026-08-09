# H-002 Reopened External Decision

DATE: 2026-08-10  
ROLE: fresh narrow external decision reviewer  
DECISION: `PROMOTE`  
METHOD: separate dimensions; no aggregate score

## Bound evidence

| Input | SHA-256 | Scope used |
|---|---|---|
| Controlling Task 4/5 brief | `41585f436832e37d734b80bd52c195ca7b922170cadf4d2b69894bb8609fcf6c` | Canonical-normalization table and streaming constraints, lines 379--422 |
| `state/H2_REOPEN_ANALYSIS.md` | `fd3bb760ae586b52d3d4bdf3a7f34a3d22229ba2fcc830d385fd620cac093cf4` | Corrected normalized-value relations, Algorithm A, proof, limits, discriminator |
| `state/H2_REOPEN_VALIDATION.md` | `a5ffbb140d9ecca3c4c5886aaba719eeadeb0223e923d968d12d77491aef3218` | Conditional physics/mathematics validation; no admission |
| Original Phase 8 decision | `def0b9b96052e449b0b6da2802b5add2b8b65e2f2768a5a4cf96d756a9f79a7f` | Superseded H-002 byte-order formulation and authorization boundary |
| Coding-plan independent review | `db991ac6252e9f094d7ad5b1a1c9ffe875911a41fa74e8a675e4c1796ba2a700` | P1-1 normalized-value-order blocker |
| P1-1 reviewed plan | `cf50117959a7a9ed47f25456235f5f27fd59d6bc09bf5921bf20a2a2ff8e1ec0` | Plan rejected for choosing JSON-byte order |

## Claim being decided

The original H-002 claim based on lexicographic canonical-JSON-byte order is
invalid and is not promoted. The promoted replacement is the conditional
Algorithm A claim:

- `VEQ`, `VLT`, and `PAIR_LT` virtually reproduce equality, ordering, and the
  same `TypeError` behavior of the brief's recursively normalized Python values;
- sorting starts from the same original iteration sequence and follows pinned
  Python 3.12 `sorted`/Timsort comparison semantics;
- mapping pairs are ordered by normalized key and then normalized value, with
  the post-sort normalized-key collision check preserving error precedence;
- equal-normalized frozenset members remain admitted;
- complete stable preflight occurs before any byte is yielded or hash updated;
  and
- only original-reference buffers, control frames, and one allowed scalar token
  may be retained. No normalized values, prefixes, trees, or member/key bytes
  may be retained.

This claim assumes exact admitted types, finite acyclic behavior-free values,
an unchanged object graph/backing from preflight through emission, and the
pinned Python 3.12 comparison schedule.

## Separate decision dimensions

- **Evidence:** The brief directly makes `sorted(normalized_items)` and sorted
  normalized mapping pairs authoritative. P1-1 independently demonstrates that
  JSON-byte sorting gives the wrong `2/10` order. The reopen analysis supplies a
  corrected conditional construction; no implementation or resource result is
  claimed.
- **Physical validity:** No physical unit, coordinate, geometry, topology,
  authority byte, or deterministic-replay convention changes. JSON remains the
  exact emitted observable but is no longer misused as the sort discriminator.
- **Mathematical validity:** The structural-induction argument is coherent under
  the stated assumptions. It preserves tuple short-circuiting, heterogeneous
  comparison exceptions, mapping value comparison after equal keys, collision
  adjacency after successful pair sorting, and no-emission-before-invalidity.
  It correctly abandons a false total preorder over all admitted heterogeneous
  values.
- **Novelty:** Virtual normalized-value comparison and schedule-matched sorting
  are contract-specific engineering, not a new ordering theorem or scientific
  breakthrough. Novelty is not needed for this narrow blocker.
- **Testability:** A literal test-owned materialized normalization plus Python
  `sorted` is an independent spec reference. Fixed `2/10` and Unicode vectors,
  exhaustive comparison/precedence cases, randomized nested values, retention
  spies, six-style parity, RSS, and runtime supply distinct falsifiers.
- **Robustness:** Mixed types, tuple early decisions, `None`, `bool`/`int`,
  escaped strings, enum/string and raw/synthetic tuple collisions, equal-key
  incomparable values, deep nesting, cycles, backing mutation, and long common
  prefixes remain mandatory boundary cases.
- **Tractability:** Revised Phase 9 formalization and immutable spec vectors are
  bounded. A separately authorized test-local spec-reference differential is
  the cheapest executable discriminator before six-style or isolated gates.
- **Assumption burden:** Exact Python 3.12 sort scheduling and stable repeated
  reads are strong dependencies. They must be explicit contract inputs; a
  generic mergesort, private cross-type rank, or current buggy encoder cannot
  substitute for them.
- **Remaining uncertainty:** No immutable vector packet, Algorithm A prototype,
  exact exception differential, retention proof, `<32 MiB` raw-RSS result, or
  `<=45 s` combined-wall result exists. Recursive common-prefix work may still
  make the candidate impractical.

## Contrary case and disposition

`HOLD` is defensible because P1-1's immutable vectors and every executable
resource result are still missing. That objection blocks implementation and
admission, not revised design formalization: the controlling order is now
unambiguous, the prior counterexample is repaired rather than hidden, the
conditional proof has survived independent validation, and the next test can be
made independent of both current code and the candidate. `REJECT` would be
premature because no mathematical contradiction remains in the repaired claim.

## Exact authorization

`PROMOTE` authorizes only:

1. revision of the H-002 Phase 9/coding-design artifacts so every byte-order
   statement is replaced by the normalized-value-order Algorithm A contract;
2. design and independent review of immutable spec vectors and exact exception-
   precedence requirements; and
3. eligibility for a **future, separately authorized, test-local** materialized
   spec-reference/differential prototype.

It does **not** authorize that prototype now, any production or repository edit,
the behavior manifest, serializer replacement, Task B admission, opening Task C,
six-style execution, official RSS/runtime execution, or any parity, memory,
runtime, completion, or gate-pass claim.

## Next gate

Revise and independently review the Phase 9/coding design and immutable
normalized-value vectors first. A separate authority decision may then allow the
test-local spec-reference prototype. Production remains closed until exact
bytes and exact exception precedence, no preflight emission, reference-only
retention, six-style parity, `<32 MiB` raw RSS, and `<=45 s` combined wall all
pass their own gates.
