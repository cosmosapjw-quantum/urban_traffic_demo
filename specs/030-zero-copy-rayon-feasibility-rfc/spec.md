# PR10 Zero-Copy/Rayon Feasibility RFC

## Goal

Define the admission gate for future Rust zero-copy NumPy FFI and Rayon work
without adding build surface or runtime behavior.

## Evidence

- Hardware atlas card: Rust wrapper conversion helpers and routing/flow symbols
  are possible acceleration candidates, but diagnostic only.
- Runtime benchmark artifact:
  `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`.
- Replay/parity artifact: no runtime behavior changes in this PR.

## In Scope

- Create `docs/rust/ZERO_COPY_RAYON_ADMISSION.md`.
- Mark PR09 complete and PR10 RFC accepted in roadmap docs.
- Advance project state and next-session handoff to PR11.
- Add docs consistency tests proving PR10 is admission-only and no Rust
  `rayon`/NumPy FFI dependency has been added.

## Out Of Scope

- Do not add `rayon`, `numpy`, `pyo3-ffi`, CMake, C++/CUDA, libtorch, or new
  runtime backend values.
- Do not change Rust crate code, Python wrappers, benchmark runners, or runtime
  semantics.
- Do not claim zero-copy or Rayon performance validation.

## Public Contract

- APIs/config/artifact keys: unchanged.
- Fallback behavior: unchanged.
- Replay/cache impact: unchanged.
- Admission doc: future implementation requires copy-boundary timing that can
  change a parent-stage decision.

## Acceptance Criteria

- Targeted tests: `tests/test_acceleration_roadmap_docs.py`.
- Cargo/Python dependency files do not add zero-copy/Rayon build surface.
- Full gates: pytest, ruff, `git diff --check`.
- Review loop max: 3.

## Compact CCoT

Question: Should Metroflow add zero-copy NumPy FFI or Rayon now?

Evidence: Current Vec copy-boundaries are documented and benchmark metadata
records copy-boundary notes, but no copy-inclusive benchmark has yet authorized
zero-copy or Rayon implementation.

Inference: A clear admission RFC prevents premature build complexity while
keeping the Rust CPU lane ready.

Counterevidence checked: Static atlas entries are hardware-fit signals, not
implementation authorization.

Decision: Keep PR10 documentation-only.

Falsifier: Copy-boundary timing blocks a review-ready parent stage after Rust
compute itself is proven faster.

Next action: Open PR11 as C++/CUDA admission RFC.
