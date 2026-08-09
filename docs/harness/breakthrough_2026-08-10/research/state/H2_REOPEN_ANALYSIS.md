# H-002 narrow reopen — normalized-value ordering

DATE: 2026-08-10  
STATUS: REOPEN_ANALYSIS_ONLY_NO_DECISION  
SCOPE: H-002 only; no promotion, rejection, implementation authorization, or
change to prior state files.

## Bound inputs

| Input | SHA-256 | Relevant scope |
|---|---|---|
| `task-4-5-validation-performance-brief.md` | `41585f436832e37d734b80bd52c195ca7b922170cadf4d2b69894bb8609fcf6c` | Lines 379-422: `sorted(normalized_items)` and sorted normalized mapping pairs precede JSON emission. |
| `PHYSICS_MATH_VALIDATION.md` | `e1a0503f1e227058fcef00715c3ecafe9bebbc5cdb53f34c32c534f879f94b58` | Prior H-002 exact-byte preorder and resource assumptions. |
| `HYPOTHESIS_GRAPH.md` | `2c439b29b3a7aca8a2bb7c930f8446bee0527b316548dfcda7f3f6dec2515e83` | Original lazy replay family. |
| `SURVIVOR_HANDOFF.md` | `c1343064c88148e68f15230e6c9beb25cc645f01fbf829804905e8ba6fdba0b8` | Later virtual-byte formulation; read as context, not authority over the brief. |

## Reopened defect

Let `N(x)` be the brief's recursive normalized Python value and let `J(z)` be
its canonical JSON bytes. The controlling order is Python order on `N`, not
lexicographic order on `J(N)`:

- `N(2) < N(10)`, but `J(10) <lex J(2)` because byte `"1" < "2"`;
- therefore `frozenset((2, 10))` must normalize in order `(2, 10)`, and a
  mapping with keys `2, 10` must place key `2` first;
- Unicode-string order is likewise Python `str` order before JSON escaping,
  not order of escaped ASCII JSON bytes.

The Phase-6 proposition based on `B(x) <=lex B(y)` is therefore not equivalent
to the frozen normalization grammar. Canonical bytes remain the final emitted
observable, but they are not the sort key.

## Corrected virtual relations

Define two nonmaterializing operations over original references:

`VEQ(x,y) := (N(x) == N(y))`  
`VLT(x,y) := (N(x) < N(y))`, including the same `TypeError`.

They must implement Python normalized-value semantics, not impose a new total
type rank:

1. Exact `bool`/`int` use Python numeric equality/order; exact strings use
   Python string equality/order; `None < anything`, including `None`, raises as
   Python does.
2. Virtual tuples compare left-to-right exactly like Python tuples: test element
   equality first; on the first unequal element call its virtual `<`; if every
   shared element is equal, compare lengths. Thus `(0,None) < (1,"x")` succeeds
   without inspecting the heterogeneous second elements.
3. Float, `Fraction`, frozenset, reviewed-record, mapping, and raw-tuple views
   expose exactly the synthetic tuple nodes frozen by `N`; an exact enum exposes
   its value string. Raw tuples can therefore collide with synthetic wrappers.
4. For mapping key references `k1,k2`, `PAIR_LT` virtually compares
   `(N(k1),N(map[k1])) < (N(k2),N(map[k2]))`. If keys are equal it compares
   values, exactly as Python tuple ordering does; it is not key-only ordering.

No global heterogeneous-type rejection is equivalent: nested tuples can be
comparable because an earlier field decides the order. Conversely, assigning a
private type rank would suppress required heterogeneous `TypeError`.

## Algorithm A — reference-only Python-sort-equivalent replay

This is the corrected candidate, not a promoted design.

1. **Preflight in materialized traversal order.** Walk the entire finite,
   acyclic grammar in the same order as `N`: tuple/record fields in declaration
   order, frozenset iteration order, and mapping insertion order with key before
   value. At every nested sortable node, perform the virtual sort and collision
   scan, then discard its ordered reference buffer. Emit/hash no byte yet. This
   preserves “unsupported before hashing” and nested failure precedence.
2. **Virtual views.** Implement `VEQ` and `VLT` with cursor frames over original
   objects plus constant synthetic tags/field names. A frame may recursively
   obtain a sorted list of original members/keys for a nested frozenset/mapping,
   but never constructs `N(x)`, a normalized prefix, or member/key bytes.
3. **Schedule-equivalent reference sort.** For each frozenset, copy only its
   original member references in iteration order. For each exact dict/proxy,
   copy only original keys in insertion order and fetch values from the stable
   exact backing. Sort those reference lists with a pinned Python-3.12 Timsort
   state machine using `VLT` or `PAIR_LT`. Its run discovery, merge/gallop
   decisions, comparison direction, and temporary buffers must match the
   materialized `sorted(...)`; buffers contain original references only.
4. **Mapping collision precedence.** Only after `PAIR_LT` sorting succeeds,
   scan adjacent keys with `VEQ`. Equal normalized keys raise
   `ValueError("canonical mapping keys collide")`. If equal keys have
   heterogeneously incomparable normalized values, pair sorting raises
   `TypeError` first, exactly as sorting materialized normalized pairs would.
   Frozensets do not perform this collision scan.
5. **Replay emission.** After the whole preflight succeeds, repeat the same
   virtual ordering locally and stream `J(N(x))`. Keep each current collection's
   ordered original-reference buffer only until that node is emitted.

### Conditional proof

Assume: exact admitted types; finite acyclic input; no caller-defined behavior;
the object graph and exact mapping backing remain unchanged from preflight
through emission; the runtime is the pinned Python 3.12 sort semantics.

- Structural induction on the normalization grammar gives
  `VEQ(x,y) == (N(x)==N(y))` and either
  `VLT(x,y) == (N(x)<N(y))` or the same Python `TypeError`.
- The reference Timsort starts with the same iteration sequence and receives
  the same result/exception for every comparison in the same schedule. By
  induction on sort transitions, its permutation or first comparison exception
  equals `sorted` on materialized normalized items/pairs.
- Successful lexicographic pair order groups equal first components; therefore
  every normalized-key collision is adjacent. The post-sort `VEQ` scan finds
  exactly those collisions. Pair-sort `TypeError` necessarily precedes it.
- Streaming the frozen JSON grammar over the same normalized order yields the
  same bytes, digests, and byte count as `json.dumps(N(x), ...)`.

The proof is conditional, not an official memory/runtime result.

## Complexity and retention

For a sortable node of `n` references, Timsort uses `O(n log n)` virtual
comparisons and `O(n)` temporary original references; its control stack is
`O(log n)`. A comparison costs the recursively visited common normalized prefix.
With nested sortable nodes and no retained normalized cache, conservative time
is recursive and can multiply as
`O(product_i(n_i log n_i) * P)` on adversarial nested common prefixes. Preflight
plus emission repeats this work.

Auxiliary retention along one active recursion path is
`O(sum_i n_i + d + L)`: original-reference buffers for active sortable nodes,
depth/control frames `d`, and the one allowed scalar/string JSON token of size
`L`. No asymptotic statement proves the isolated `<32 MiB` or practical-runtime
gate.

## Alternative B — generic reference mergesort

A simpler stable mergesort over original references with `VLT`/`PAIR_LT` has the
same result on a mutually orderable domain and retains no normalized bytes. It
is not exact enough for this contract: a different comparison schedule can
change which heterogeneous operands are compared first, the `TypeError` message
direction, and whether that error precedes a later mapping collision. It is
therefore only a performance/proof comparator, not the production-equivalent
candidate unless the brief explicitly relaxes exception precedence.

## Hostile and boundary cases

- `{2,10}` frozenset and mapping keys; negative/multi-digit integers;
  non-ASCII/escaped strings; signed-zero float wrappers; enum/string and
  synthetic-wrapper/raw-tuple normalized collisions.
- Top-level heterogeneous members/keys; tuple comparisons decided before or at
  a heterogeneous field; `None`; `bool`/`int`; equal-key mapping values whose
  comparison raises before collision detection.
- Empty/singleton collections; equal-normalized frozenset members; nested maps
  and frozensets; very long common prefixes and deep nesting.
- Exact-type rejection before equality/hash/iteration; cyclic dataclass/dict
  graphs; mapping-proxy backing mutation; mutation between preflight/replay; any
  behavior-bearing subclass or reentrant comparison attempt.

## Cheapest decisive discriminator

Build a test-only *spec reference* that literally materializes the brief's
`N` and calls Python `sorted` on normalized items/pairs; do not use the current
JSON-key sorter as oracle. Differential Algorithm A against it on:

1. fixed `{2,10}` and Unicode-order vectors;
2. exhaustive small admitted values and every permutation of heterogeneous,
   tuple-short-circuit, duplicate, and mapping-collision/value-precedence cases,
   asserting bytes plus exact exception type/message and no yielded byte;
3. randomized nested values and comparator-law checks restricted to domains
   where Python normalized ordering succeeds; and
4. join/retained-object spies plus bounded long-prefix time/`tracemalloc`.

Only after those pass should six-style parity and isolated raw-RSS run. Any
schedule drift, byte/error mismatch, retained normalized state, unstable-read
acceptance, excessive prefix time, or memory failure falsifies Algorithm A.

REOPEN_VERDICT: PRIOR_BYTE_ORDER_PROOF_INVALID_FOR_FROZEN_GRAMMAR;
CORRECTED_REFERENCE_ONLY_ALGORITHM_CONDITIONAL_AND_UNVERIFIED.
