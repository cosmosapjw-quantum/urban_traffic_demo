# Zero-Copy/Rayon Admission RFC

Status: RFC only

This document defines when Metroflow may open a future Rust zero-copy NumPy FFI
or Rayon implementation slice. No implementation is authorized by this document.

## Current Boundary

The current Rust CPU backend deliberately uses a copy boundary:

- edge evolution: Python-compatible inputs copied into Rust `Vec<f64>`;
- flow, routing, reroute, and route metadata: copied into `Vec<f32>`,
  `Vec<i32>`, or `Vec<bool>`;
- active-agent action planning: copied into `Vec<i32>`;
- Python owns NumPy arrays, immutable state replacement, replay metadata,
  diagnostics, and fallback behavior.

This keeps the Rust extension simple and deterministic while backend parity is
still being established.

## Admission Rule

Open a zero-copy or Rayon implementation PR only when all conditions hold:

- a parent runtime stage remains review-ready after current cache/fallback work;
- copy-boundary timing is measured separately from Rust compute time;
- the copy boundary is a material part of the parent-stage cost, or the Rust
  compute core is already faster and copy cost blocks parent-stage improvement;
- baseline NumPy ownership, dtype, shape, and contiguity rules are written as a
  public contract before any implementation patch;
- explicit `rust_cpu` behavior remains fail-closed and `auto` fallback remains
  baseline-safe;
- replay fingerprints and benchmark metadata preserve the backend and
  copy-boundary decision.

## Zero-Copy Candidate Interface

A future zero-copy PR may consider PyO3 NumPy bindings such as
`PyReadonlyArray` for read-only inputs and explicit owned NumPy outputs. That PR
must first document:

- accepted dtypes and dimensions for each function;
- contiguous layout requirements and copy fallback behavior;
- lifetime and GIL assumptions;
- whether output arrays are newly allocated or reuse caller-owned storage;
- exact exception behavior for dtype, shape, index, and non-finite input errors.

No hidden mutation is allowed. Python state replacement remains authoritative.

## Rayon Candidate Interface

A future Rayon PR may consider parallelizing only isolated Rust kernels whose
input/output slices have independent writes. It must first document:

- workload size thresholds where parallelism is enabled;
- deterministic reduction/order behavior;
- thread-pool configuration and interaction with Python callers;
- benchmark evidence that parallel overhead is amortized;
- rollback to serial Rust or Python baseline when the threshold is not met.

Rayon is not appropriate for small control-flow-heavy calls where thread setup,
copying, or Python orchestration dominates.

## Current Decision

Do not add zero-copy NumPy FFI, Rayon, or new Rust build surface in PR10.
Continue recording copy-boundary metadata in benchmarks and reopen
implementation only when measured evidence changes a parent-stage decision.

## Compact CCoT

Question: Should Metroflow add zero-copy NumPy FFI or Rayon now?

Evidence: Current docs and benchmark metadata already record Vec copy
boundaries. Whole-runtime Rust routing remains slower than baseline because
parent-stage cost moved into path-build and metadata boundary work, and
active-agent state layout is below the review gate.

Inference: A design RFC is useful, but implementation would be premature.

Counterevidence checked: Static atlas entries identify several Rust-compatible
symbols, but atlas hardware-fit labels are diagnostic and not implementation
authorization.

Decision: Keep PR10 RFC-only; require copy-inclusive evidence before opening
zero-copy or Rayon implementation.

Falsifier: A deterministic benchmark shows copy-boundary cost blocks a
review-ready parent stage after the Rust compute core itself is proven faster.

Next action: Open PR11 as a C++/CUDA admission RFC, with no build scaffold until
a narrow kernel clears the evidence gate.
