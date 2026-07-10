# Feature Specification: Cost-To-Go Surrogate Feature Contract

Status: ACCEPTED

## Goal

Turn the simulator-only cost-to-go label rows into a learnable, leakage-aware
NumPy dataset contract without granting an NN any routing or runtime authority.

## Evidence

- PR27 cost-to-go rows currently expose only node and destination identifiers.
- Baseline dynamic-potential routing depends on geometry/topology plus current
  link travel cost and blocked-capacity state; identifiers alone do not encode
  that surface.
- PR47 found a credible GPU tensor lane, but deliberately parked runtime flow
  integration. The anti-local-minima rule now requires switching to the NN
  label lane rather than adding another flow timing layer.

## Scope

- Add a versioned cost-to-go model-input schema containing normalized geometry,
  node degree, usable-link cost, effective-capacity, blocked-link, and
  destination indicators plus an explicit one-tick absolute cost scale.
- Keep node/destination IDs as provenance fields, but exclude them from the
  model feature matrix.
- Fingerprint the feature contract, static network/geometry, and dynamic link
  state independently.
- Build a contiguous `float32` NumPy feature/target dataset from authoritative
  records.
- Add deterministic group splitting. All rows sharing static network and
  destination remain in one partition across scenarios, ticks, and dynamic
  states.

## Non-goals

- No model fitting, JAX/Torch import, GPU benchmark, or runtime NN backend.
- No NN route legality, state mutation, replay authority, or fallback change.
- No external data, learned demand, GNN framework, or custom CUDA scaffold.
- No claim that row-local features are sufficient to generalize across unseen
  city graphs; that is a falsifiable question for the next experiment.

## Acceptance

- Model inputs are finite, dimensionless, ordered by a versioned constant, and
  contain no identifier/index fields.
- Features respond to geometry, dynamic travel-time, capacity, and closure
  changes while labels remain baseline-Dijkstra authoritative.
- Dataset creation rejects legacy/malformed rows instead of silently filling
  missing inputs.
- Split output is deterministic under record reordering and has no group
  overlap; fewer than two groups fails closed.
- Imports remain NumPy-only and do not load JAX, torch, CUDA, or the Rust
  extension.
- Runtime backend/config contracts remain unchanged.

## Compact CCoT

Question: What must exist before a GPU cost-to-go surrogate bakeoff is valid?
Evidence: Current rows are identifier-only, while the target changes with graph
geometry and dynamic link state.
Inference: Freeze a model-input and grouped-split contract before fitting.
Counterevidence checked: Row-local features may still be insufficient for
cross-city generalization, so this PR cannot authorize a model.
Decision: Add deterministic feature/dataset substrate only.
Falsifier: Features are degenerate on generated cities, leak destinations
between partitions, or fail to respond to authoritative state changes.
Next action: Run a multi-city feature audit, then open a JAX training bakeoff
only if the contract is non-degenerate and leakage-safe.

## Review Closure

- `/review-spec`: closed after preserving absolute travel-cost scale, grouping
  destinations across scenarios/states, recomputing split keys, and enforcing
  public dataset/split invariants.
- `/review-code`: closed after binding immutable record/dataset/split payloads
  to verified fingerprints, validating feature domains, rejecting duplicate
  provenance and mixed-network v1 splits, and preserving duplicate-destination
  compatibility through deterministic deduplication.
- `/review-drift`: closed with no findings after confirming the row-local and
  cross-city limitations, baseline authority, PR49 decision gate, conditional
  PR50 scope, and four-lane anti-drift visibility.
