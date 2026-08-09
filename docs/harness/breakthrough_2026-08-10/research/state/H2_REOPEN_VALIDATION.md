# H-002 Reopen Physics/Mathematics Validation

DATE: 2026-08-10
INPUT_SHA256: `fd3bb760ae586b52d3d4bdf3a7f34a3d22229ba2fcc830d385fd620cac093cf4`

## Short verdict

The prior canonical-byte ordering theorem is invalid for the frozen brief.
Algorithm A's corrected virtual `VEQ/VLT/PAIR_LT` construction is mathematically
equivalent to materialized normalized-value sorting only under its explicit
finite, acyclic, stable-read, behavior-free, exact-Python-3.12 assumptions.
The proof is coherent; memory and practical runtime remain unverified and are
high-risk. Status: `PASS_WITH_CONDITIONS` for design formalization,
`NOT_YET_TESTABLE` for admission.

## Assumptions and conventions

- `N(x)` is exactly the brief's recursive Python normalization.
- Sorting uses the repository's exact Python 3.12 runtime and original iteration
  order; no private cross-type rank is introduced.
- Inputs are finite, acyclic, exact-type, behavior-free, and unchanged through
  preflight and emission.
- Final JSON bytes remain exact observables but are not sort keys.

## Equation-by-equation audit

| Item | Status | Issue | Fix |
|---|---:|---|---|
| `N(2) < N(10)` versus `J(N(10)) <lex J(N(2))` | PASS | Concrete counterexample invalidates byte ordering. | Add immutable 2/10 and Unicode vectors. |
| `VEQ(x,y) == (N(x)==N(y))` | PASS_WITH_CONDITIONS | Requires structural induction and exact leaf equality. | Restrict to frozen grammar and reject cycles/behavior first. |
| `VLT(x,y) == (N(x)<N(y))` | PASS_WITH_CONDITIONS | Heterogeneous exceptions and tuple short-circuit must match. | Use recursive Python semantics, not a total type rank. |
| `PAIR_LT` | PASS_WITH_CONDITIONS | Literal pair sorting compares normalized values after equal keys. | Preserve pair-sort exception before collision scan. |
| reference sorting permutation/exception | PASS_WITH_CONDITIONS | Comparison schedule must match `sorted(N(...))`. | Use the same built-in Python 3.12 Timsort over `cmp_to_key` views and prove identical `<` outcomes. |
| collision adjacency | PASS | Successful lexicographic pair ordering groups equal first components. | Scan adjacent keys with `VEQ` after sort. |
| no byte before invalidity | PASS_WITH_CONDITIONS | Emission could otherwise leak before a later nested failure. | Complete stable preflight before yielding/hash update. |
| space `O(sum n_i+d+L)` | CONCERN | Active nested reference buffers and sort temporaries count toward RSS. | Measure retained objects and official raw RSS. |
| time | CONCERN | Nested comparison, preflight, and emission may multiply common-prefix work. | Freeze a `<=45 s` combined-wall gate and long-prefix kill test. |

## Dimensional / sign / limit checks

No physical unit, sign, geometry, or topology changes. Boundary cases are
numeric 2/10, negative/multidigit integers, Unicode/escaped strings, None,
bool/int, signed-zero wrapper tuples, raw/synthetic tuple collisions, equal-key
heterogeneous values, empty/singleton nodes, deep nesting, and mutation between
passes.

## Fatal blockers

- No immutable spec vector currently freezes normalized-value order/precedence.
- No differential Algorithm A implementation/test exists.
- No official `<32 MiB` or `<=45 s` result exists.
- Stable-read ownership from preflight through emission is a contract dependency.

## High-priority fixes

1. Replace all H-002 byte-order claims with normalized-value-order claims.
2. Freeze literal spec-reference vectors before replay.
3. Differential exact bytes and exact exception type/message/schedule.
4. Treat memory and runtime as separate mandatory gates.

## Safe claims

- Current JSON-key sorting violates the frozen 2/10 normalized order.
- A virtual recursive comparator can reproduce `N` equality/order conditionally.
- Mapping pair-sort errors can precede collision detection under the literal grammar.

## Claims requiring downscoping

- “total preorder for all admitted values” -> successful mutually comparable
  normalized domains plus exact propagated TypeError elsewhere.
- “bounded-memory solution” -> candidate retention bound only, not RSS evidence.
- “same behavior as current reference” -> current reference is not authority.

## Minimal revision plan

Freeze spec vectors, independently re-review Algorithm A, and permit only a
test-local differential prototype. Production remains closed until exact parity,
retention, `<32 MiB`, and `<=45 s` all pass.

REOPEN_VALIDATION_STATUS: COMPLETE_CONDITIONAL_NO_ADMISSION
