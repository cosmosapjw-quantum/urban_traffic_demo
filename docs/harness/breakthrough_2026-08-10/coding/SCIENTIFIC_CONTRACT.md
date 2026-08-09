# SCIENTIFIC_CONTRACT.md

DATE: 2026-08-10
SOURCE: superseding research survivor handoff SHA
`726af7260e31fc40101b942e49ac2b642aae1f0f89609f1d8facc15135d0dd65`

## Conventions

- Coordinates/lengths: exact integer mm unless exact `Fraction` mm is explicit.
- Areas: exact mm^2; signed doubled area determines orientation.
- Topology: planar DCEL `V-E+F=1+C`, including unbounded face/components.
- Canonical identity: exact bytes and digests; no tolerance or reseal equivalence.
- Runtime: fresh-process wall seconds; inclusive profile rows are nonadditive.

## Invariants

1. Public authority payload, fingerprint, semantic order, physical geometry,
   tile owners, and deterministic replay are byte-for-byte fixed.
2. Cold validation remains exhaustive; hot admission recomputes current content
   and source bindings and never accepts a trusted token.
3. Canonical values are finite, acyclic, exact-type, deterministic, and
   behavior-free before replay/iteration/equality/hash/field access.
4. Projection `P` must terminate, be idempotent, and retain no caller-owned
   mutable alias. NumPy copies are exact C arrays backed by immutable bytes.
5. Stable capture `C` detects persistent pre/post drift; arbitrary ABA mutation
   is outside its claim unless an owner lock/version is introduced explicitly.
6. Registry `R` is linearizable only for cooperating operations wholly inside
   one module-owned `RLock`.
7. Instrumentation ownership follows actual producers; presentation order never
   substitutes for chronological execution order.
8. Failure observation records a completed prefix and one active failure, then
   re-raises the unchanged public exception without phase rerun.

## Conditional mathematical claims

- Ordering authority is the brief's recursively normalized Python value `N(x)`,
  not canonical JSON bytes. Virtual `VEQ/VLT/PAIR_LT` must reproduce the same
  Python 3.12 result or `TypeError` as materializing and sorting `N`.
- Mapping pairs sort by normalized key then value before adjacent normalized-key
  collision rejection; equal-normalized frozenset members remain admitted.
- The candidate retains only original references, control frames, and one scalar
  token after complete stable preflight. This is a design hypothesis, not an RSS
  or runtime result.
- A complete registry critical section supplies a serial order for registry
  transitions only, not for arbitrary upstream mutation.

## Validity range and forbidden moves

Valid only for the frozen finite receipt grammar and current exact map model.
Forbid approximate geometry, external-data learning, tolerance relaxation,
silent fallback, public API expansion, proof/capsule trust, distributed/GPU-first
redesign, and traffic-algorithm work.

## Failure semantics

Any normalized-value/byte/error/precedence drift, preflight emission, retained
normalized state, retained alias, behavior execution, nontermination,
current-content mismatch, unsupported overwrite, nonserializable cooperating
history, misowned phase payload, rerun, or changed public exception blocks
promotion. A memory pass with prohibitive runtime also fails practical closure.
