# C++/CUDA Admission RFC

Status: RFC only

This document defines when Metroflow may open a future C++/libtorch or custom
CUDA implementation slice. No implementation is authorized by this document.

## Current Boundary

Metroflow currently keeps Python 3.12 + NumPy as the deterministic authority.
Rust CPU is optional for control-flow-heavy kernels. JAX and torch are optional
experiment lanes, but runtime route legality, state mutation, replay, and
fallback remain baseline-owned.

PR11 does not add C++ sources, CUDA kernels, CMake files, libtorch dependencies,
or runtime backend values such as `torch_cuda` or `custom_cuda`.

## Candidate Kernels

Only one narrow kernel may be proposed by a future implementation PR:

- dense flow: large flow/turn array updates where tensor throughput dominates
  Python/Rust dispatch and copy cost;
- route-score batch: K>1 route metadata, path-size scoring, reroute scoring, or
  other legality-preserving batch score calculations;
- OD/policy batch: batched OD cost or policy scoring where route legality and
  deterministic state application remain baseline/Rust-owned.

GPU/NN work must not target deterministic state mutation, route legality, replay
authority, or cache invalidation authority.

## Admission Rule

Open a C++/CUDA implementation PR only when all conditions hold:

- one candidate stage exceeds the review gate across at least three
  deterministic seeds, and a copy/compile-inclusive probe on the named workload
  shows at least 20 percent parent-stage p50 improvement and no p95 regression;
- first-call compile/build time and steady-state runtime are reported
  separately;
- host-device copy cost is measured and included in the decision;
- Python/NumPy baseline remains authoritative for dtype, shape, replay, and
  fallback;
- explicit GPU backend selection fails closed, while `auto` is the only mode
  allowed to fallback;
- runtime config values and benchmark metadata are specified before
  implementation;
- CPU baseline and optional Rust/JAX comparisons remain available for rollback.
- replay, invariant, and backend parity tests pass with no deterministic output
  drift from the baseline authority path.

## Interface Requirements

A future C++/CUDA PR must specify:

- input/output array ownership and contiguity requirements;
- accepted dtypes and units;
- deterministic handling of invalid, non-finite, or out-of-range input;
- memory budget and RTX 3080 Ti 12GB assumptions;
- device selection and fallback behavior;
- replay fingerprint and benchmark metadata keys;
- build isolation so base installs do not require CUDA, libtorch, CMake, or a
  GPU toolchain.

## Current Decision

Do not add C++/CUDA, libtorch, CMake, or new runtime backend values in PR11.
Keep `torch_cuda` and `custom_cuda` as documented future names only. Open an
implementation slice only after evidence identifies exactly one kernel whose
parent-stage improvement can be falsified.

## Compact CCoT

Question: Should Metroflow add C++/libtorch/custom CUDA build surface now?

Evidence: Current review-ready runtime work remains graph/control-flow and
cache-oriented. Dense flow and route-score probes exist as diagnostics, but no
single GPU kernel has yet cleared the multi-seed evidence gate.

Inference: CUDA admission rules should be explicit before any build complexity
enters the project.

Counterevidence checked: RTX 3080 Ti 12GB and optional JAX/torch lanes make GPU
experiments relevant, but hardware availability is not performance evidence.

Decision: Keep PR11 documentation-only and prohibit build/runtime config changes.

Falsifier: A dense flow, route-score batch, or OD/policy batch probe on a named
deterministic workload shows at least 20 percent parent-stage p50 improvement,
no p95 regression, copy/build time included, and no replay or invariant drift.

Next action: Open PR12 to consolidate project state, decision logs, deprecated
ideas, validation docs, and next-session handoff.
