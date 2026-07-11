# Feature Specification: Cost-To-Go Graph Tensor Contract

Status: ACCEPTED

## Goal

Define immutable, leakage-aware NumPy graph tensors for future graph-aware
cost-to-go experiments without fitting a model or granting an NN routing or
runtime authority.

## Evidence

- PR49's canonical diagnostic retains all 64,968 rows and has usable dynamic
  response and map holdout support, but rejects the row-local MLP path because
  69.07% of covered near-duplicate rows have conflicting normalized targets.
- Baseline cost-to-go depends on directed connectivity, per-link travel cost,
  and blocked-link state. Those relationships are not represented by an
  independent row-local matrix.
- PR49's `relation_rejected` state authorizes only a graph data-contract slice.
  It is not evidence that graph learning will succeed.

## Scope

- Add one graph sample per static network, dynamic link state, and destination.
- Preserve the directed graph as local `int32` source/destination edge indices.
- Reuse PR48's ordered 20-column node feature contract for every node.
- Add ordered, dimensionless `float32` edge features for normalized length,
  free-flow speed, lane count, travel cost, effective capacity, incident
  multiplier, blockability, and one-hot road class.
- Preserve blocked links as a separate boolean edge mask.
- Store baseline dynamic-potential node targets plus a target mask for
  unreachable nodes. Baseline routing remains the only label authority.
- Fingerprint schema, static topology/geometry, dynamic state, destination,
  arrays, authority metadata, individual samples, padded batches, and splits.
- Add deterministic padded batching with node, edge, and target masks; padded
  edge indices use `-1` and all other padded numeric values use zero.
- Enforce an explicit maximum padded-byte budget before allocating a batch.
- Add a map-level split contract that accepts the validation static-network
  fingerprints, held-out/selection seeds, and source holdout fingerprint from
  PR49. Recompute the full holdout payload before keeping every sample from one
  static network in exactly one partition.

## Decision States

- This PR may mark the graph tensor contract `ready_for_bakeoff` only when
  schema, parity, immutability, batching, split, fingerprint, and import gates
  pass.
- `ready_for_bakeoff` authorizes only PR51's bounded experiment. It does not
  authorize a runtime backend, model checkpoint, route choice, or state update.
- Any incomplete or contradictory authority/split metadata fails closed.

## Non-goals

- No JAX model, GNN library, PyTorch/libtorch, CUDA kernel, training loop,
  accuracy claim, or runtime inference path.
- No NN route legality, replay authority, state mutation, cache replacement,
  or backend configuration value.
- No external data, named-city calibration, empirical validation, raw label
  artifact, or change to baseline Dijkstra.
- No assumption that graph tensors will reduce PR49's row-local conflict.

## Acceptance

- Sample arrays are C-contiguous, exact dtype, finite where masked, copied on
  construction, backed by immutable buffers, shape-validated, and free of
  persistent node/link IDs in model tensors. Raw sample construction without
  verified network/state/baseline sources fails closed.
- Directed edge indices exactly preserve CSR link direction and reject invalid
  local indices.
- Node targets and target masks match baseline dynamic-potential output;
  destination target is valid and zero.
- Static topology/geometry changes alter the static/sample fingerprint.
  Travel-time, capacity, incident, or closure changes alter the dynamic/sample
  fingerprint without changing the static fingerprint.
- Padded batches preserve every sample exactly under masks, reject empty input,
  reject over-budget allocation, and never expose padding as a valid edge/node.
- Map splits are deterministic under sample reordering, cover every sample
  exactly once, keep static networks disjoint, and reject missing/unknown
  validation fingerprints, source-holdout mismatch, or empty partitions.
- Importing the graph tensor module does not load JAX, torch, CUDA, or the Rust
  extension.
- Existing deterministic replay and runtime backend contracts remain unchanged.

## Compact CCoT

Question: What is the smallest graph-aware substrate justified by PR49?
Evidence: Row-local support is nondegenerate but relation-conflicted, while
baseline targets are functions of directed dynamic edge state.
Inference: Freeze graph samples, masks, batching, and map split provenance
before selecting a model architecture.
Counterevidence checked: A data contract cannot establish graph-model accuracy
or GPU speed.
Decision: Implement NumPy-only experiment substrate and keep all runtime
authority in baseline routing.
Falsifier: The contract cannot preserve baseline labels and directed dynamic
state in deterministic, memory-bounded batches without leakage.
Next action: Open PR51 only after all contract reviews and gates pass.

## Review Closure

- `/review-spec`: no findings after restricting sample creation to the verified
  builder, completing the schema fingerprint, and binding holdout provenance.
- `/review-code`: no findings after immutable-buffer, factory-ownership,
  split-canonicalization, peak-byte-budget, and discriminating edge tests.
- `/review-drift`: no findings after recomputing PR49 holdout provenance and
  preserving baseline/runtime authority boundaries.
- Generated-city smoke: 861 nodes, 3,120 directed edges, two destinations,
  1,722 retained target rows, 534,996 final array bytes, and 1,069,992 estimated
  peak construction bytes. Diagnostic only; no speed or validation claim.
- Final gates: `560 passed`, Ruff clean, `git diff --check` clean.
