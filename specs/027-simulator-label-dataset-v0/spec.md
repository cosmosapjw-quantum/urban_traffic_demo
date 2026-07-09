# PR07 Simulator Label Dataset v0

## Goal

Add deterministic simulator-only label export for future cost-to-go and route
scoring surrogate experiments, while keeping baseline routing/flow authority and
runtime fallback unchanged.

## Scope

- Add a Python/NumPy-only learning label module under `metroflow.learning`.
- Export cost-to-go labels from baseline dynamic-potential authority.
- Export route-scoring labels from existing K-route candidate metadata and
  path-size selection authority.
- Produce stable JSONL-ready records with schema version, source authority,
  config/backend fingerprint, input features, labels, and deterministic
  fingerprint.
- Keep exports in-memory/file-optional utilities; no model training, runtime NN
  inference, or external datasets.

## Non-Goals

- Do not add PyTorch, JAX training, libtorch, CUDA, custom kernels, or model
  dependencies.
- Do not change runtime routing authority, route legality, replay semantics, or
  backend defaults.
- Do not ingest external data.
- Do not turn label export into validation evidence.

## CCoT Record

- Question: What is the minimal NN/GPU-enabling substrate that does not change
  simulator authority?
- Evidence: Guardrails require simulator labels before NN admission. PR06 now
  records route-score batch shapes but still keeps route legality in baseline/
  Rust authority.
- Inference: The next useful artifact is deterministic label export from the
  authoritative baseline, not a model harness.
- Counterevidence checked: Adding a model now would bypass label provenance and
  fallback gates.
- Decision: Add schema-stable simulator-only label export for cost-to-go and
  route scoring.
- Falsifier: If this PR imports external data or adds runtime model authority,
  revert.
- Next action: Add RED tests, implement labels, review, gate, commit.

## Acceptance Criteria

- Cost-to-go export records one row per reachable node for selected
  destinations with `label_cost_to_go`, destination metadata, and route/backend
  authority metadata.
- Route-scoring export records candidate path costs, path-size factors, selected
  candidate index/id, utility, and route-score vector for selected ODs.
- Label metadata records explicit units:
  `label_cost_to_go` and `candidate_path_costs` use
  `generalized_travel_time_cost_ticks`; path-size factors are `dimensionless`;
  selected utility and route-score vectors use
  `path_size_corrected_utility` with formula
  `-candidate_path_cost + path_size_gamma * log(candidate_path_size_factor)`.
- Label export is deterministic for the same inputs and changes fingerprint when
  authoritative labels change.
- JSONL writer emits sorted, stable records without external data.
- Core runtime imports do not eagerly import JAX, torch, CUDA, or `_metroflow_rust`.
- Targeted tests, full pytest, ruff, and whitespace gates pass.
