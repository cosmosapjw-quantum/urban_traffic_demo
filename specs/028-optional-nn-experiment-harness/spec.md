# PR08 Optional NN Experiment Harness

## Goal

Add an optional route-surrogate experiment harness that consumes PR07 simulator
labels, records model/version/fallback metadata, and never becomes route
legality or runtime authority.

## Scope

- Add `metroflow.learning.surrogate` as a Python/NumPy-first experiment module.
- Add a lazy `torch_optional` experiment backend that is allowed only through an
  optional dependency extra and must fallback to baseline metadata when
  unavailable.
- Expose model fingerprints, label fingerprints, backend requested/actual,
  fallback reason, model family/version, and runtime authority metadata.
- Provide deterministic baseline NumPy fit/predict helpers for route-scoring
  labels.

## Non-Goals

- Do not add runtime `routing_backend`, `agent_backend`, or `flow_backend` NN
  values.
- Do not use NN outputs for route legality, active-agent state mutation, replay
  authority, or default simulation behavior.
- Do not add libtorch/C++/CUDA/custom kernel scaffold.
- Do not train on external data.

## CCoT Record

- Question: How can Metroflow open the NN lane without route-authority drift?
- Evidence: PR07 now exports deterministic baseline labels. Guardrails require
  labels, fallback, model/version fingerprint, and no route-legality authority.
- Inference: A small optional harness is appropriate if it is explicitly
  experiment-only and fallback-bearing.
- Counterevidence checked: Adding runtime NN config values would bypass
  deterministic baseline authority.
- Decision: Add optional harness and optional `torch` extra only; keep runtime
  unchanged.
- Falsifier: If this PR accepts runtime NN backend values or imports torch at
  core package import time, revert.
- Next action: Add RED tests, implement harness, review, gate, commit.

## Acceptance Criteria

- Base dependency remains `numpy`; `torch` is optional extra only.
- Importing `metroflow.learning` and `metroflow.learning.surrogate` does not
  import torch, JAX, CUDA modules, or `_metroflow_rust`.
- Baseline surrogate fit/predict is deterministic from route-scoring labels and
  records label/model fingerprints.
- `backend="torch_optional"` falls back with deterministic metadata when torch
  is unavailable or fails.
- Result metadata states `runtime_authority="baseline_fallback_only"`.
- Runtime config rejects NN/GPU backend names.
- Targeted tests, full pytest, ruff, and whitespace gates pass.
