# PR06 Route Metadata/Scoring Batch Probe

## Goal

Add benchmark-only probes for K>1 route candidate metadata, path-size scoring,
and reroute scoring batch shapes without changing route legality, runtime
routing authority, or backend defaults.

## Scope

- Extend measured benchmark surfaces with a route scoring batch probe.
- Use existing baseline route candidate generation and scoring contracts.
- Record candidate count, path lengths, metadata timing, path-size gamma,
  route-score batch shape, reroute-score batch shape, wall-clock timing,
  backend/copy-boundary metadata, and output fingerprints.
- Optional JAX may be used only as a benchmark probe for dense score arrays.
- Optional Rust may be observed only through existing explicit/fail-closed
  routing/reroute wrappers.
- Keep route legality and candidate path construction in baseline/Rust authority
  paths; no NN or GPU scoring result may become runtime authority in this PR.

## Non-Goals

- Do not add `torch`, libtorch, CMake, CUDA, or custom kernel scaffolding.
- Do not add runtime `routing_backend="jax"` or GPU config values.
- Do not introduce NN training/inference.
- Do not change route candidate legality, active-agent state mutation, replay
  authority, or default backend values.
- Do not reopen whole-runtime Rust routing enablement.

## CCoT Record

- Question: Are route metadata/scoring operations a NumPy/SIMD, JAX/GPU tensor,
  NN surrogate, or keep-Python candidate?
- Evidence: PR04 kept Rust potential-only because whole-runtime Rust routing was
  slower through path-build/metadata copy boundaries. The hardware atlas still
  keeps route-score batches and NN labels on the watchlist.
- Inference: The next useful probe is not a backend switch; it is a measured
  shape/timing/fingerprint surface for K>1 metadata and reroute scoring.
- Counterevidence checked: Route legality remains graph/control-flow heavy and
  should not move to JAX/NN without replay-safe labels and fallback.
- Decision: Add benchmark-only scoring batch probes and decision-card metadata.
- Falsifier: If this PR changes route legality, accepts runtime GPU backend
  values, or treats score probes as validation evidence, revert.
- Next action: Add RED tests, implement measured probe, review, gate, commit.

## Acceptance Criteria

- K>1 measured route scoring probe records candidate paths, path costs,
  path-size factors, selected index, utility, score batch shape, and metadata
  timing without changing candidate legality.
- Path-size gamma affects selection utility consistently with existing runtime
  behavior and preserves deterministic fallback.
- Reroute scoring batch probe records batch shape, trigger-score fingerprint,
  and decision counts while preserving baseline `decide_reroute_vs_persist`
  semantics.
- Optional JAX probe is lazy and benchmark-only; unavailable or runtime-failed
  JAX records deterministic fallback metadata.
- Runtime backend registries do not add JAX/GPU/NN values.
- Targeted tests, full pytest, ruff, and whitespace gates pass.
