# Feature Specification: JAX Graph-Aware Cost-To-Go Bakeoff

Status: ACCEPTED

Threshold provenance: the author attests that architecture, seeds, epochs, and
decision thresholds were fixed in the working tree before the canonical run.
There is no independent versioned preregistration evidence, and none of these
values may be relaxed after observing the result.

## Goal

Measure whether PR50's directed graph tensors provide held-out-map predictive
value over PR48's row-local features on the RTX 3080 Ti, without creating a
runtime NN backend or changing route legality.

## Evidence

- PR49 rejects a row-local MLP admission path because 69.07% of covered
  near-duplicate rows have conflicting normalized targets.
- PR50 supplies immutable graph samples, baseline targets, exact PR49 map
  holdout provenance, and memory-bounded padding.
- The local optional JAX environment reports JAX 0.10.2 on one CUDA GPU,
  `NVIDIA GeForce RTX 3080 Ti` with 12,288 MiB.
- Adam optimization will use optional Optax rather than a project-local
  optimizer implementation.

## Canonical Workload

- Generated map styles: `grid_core`, `polycentric_tod`, `organic`.
- Scenario seeds: `17`, `29`, `41`; PR49's held-out scenario seed remains `29`.
- Dynamic states: `free_flow`, `stressed_closure`.
- Four geometry-only destinations per map.
- Expected graph samples: 72 total, 48 train and 24 validation.
- Model initialization/training seeds: `41`, `42`, `43`.
- GPU memory environment: record `XLA_PYTHON_CLIENT_MEM_FRACTION`; canonical run
  uses `0.70` unless an explicit lower value is required to avoid allocation
  failure.

## Fixed Models And Training

- Row-local control: four hidden layers over the same normalized PR50 node
  features, sized to keep trainable parameter count within 15% of the graph
  candidate.
- Graph-aware candidate: the same node encoder plus 16 recurrent reverse-edge
  message-passing steps using destination-node hidden state, PR50 edge features,
  and blocked/edge masks. Message weights are shared across steps.
- Hidden width: 32. Optimizer: Optax Adam. Learning rate: `1e-3`. A parameter
  count mismatch above 15% makes the comparison `inconclusive`.
- Epochs: 30. Graph minibatch size: 4. No dropout, checkpoint selection,
  early stopping, hyperparameter search, or post-result architecture change.
- Node and edge normalization statistics are derived from train masks only.
- Training target is `log1p(label_cost_to_go / per_graph_max_travel_time)`;
  evaluation reports raw and normalized MAE/RMSE after inverse transform.
- Both models receive the same train/validation graph order, target masks,
  normalization, epoch permutations, and training seeds.

## Canonical Decision Gate

- All three seed runs must be finite and use `device_platform="gpu"`.
- Corpus, graph contract, PR49 holdout, normalization, and model-config
  fingerprints must be identical across model seeds.
- A repeated seed-41 run must match prediction/metric output within `1e-4`
  maximum normalized prediction difference and `1e-5` normalized MAE.
- Graph-aware mean validation normalized-MAE ratio must be at most `0.90`
  relative to row-local control, and at least two of three model seeds must
  individually reach ratio `<= 0.90`.
- Parameters, optimizer state, and device inputs are blocked before the first
  measured training step. First-call compile-inclusive and steady
  train/inference timings are recorded separately after an independently
  recorded import/device warmup, but timing does not authorize runtime
  integration in this PR.
- Passing yields `graph_signal_supported`. A finite deterministic miss yields
  `graph_signal_not_supported`. A determinism miss yields `inconclusive`.
  Missing or mismatched PR49 provenance, or failure to obtain the required GPU,
  fails execution before an artifact is written.

## Artifacts

- Write JSON, Markdown, and manifest diagnostics.
- Record JAX/Optax versions, GPU kind/platform, CUDA memory fraction, corpus,
  graph-split and PR49 map-holdout fingerprints, feature normalization, model config and
  final parameter fingerprints, parameter counts, compile/steady timings,
  aggregate and per-map/state/distance-bin metrics, seed ratios, and decision
  state. Distance bins are fixed to `[0,.25)`, `[.25,.50)`, `[.50,.75)`, and
  `[.75,1.000001)` over `euclidean_distance_by_spatial_diagonal`.
- Do not persist raw labels, graph tensors, optimizer state, predictions, or
  model parameters.

## Non-goals

- No runtime backend/config value, checkpoint loading, route choice, route
  legality, replay authority, cache replacement, or simulation state mutation.
- No external data, named-city calibration, empirical validation, RL/LLM
  routing, PyTorch/libtorch, GNN framework, or custom CUDA kernel.
- No claim that lower validation error implies real-city validity or safe
  deployment.
- No threshold, architecture, epoch, feature, or split adjustment after the
  canonical result is observed.

## Acceptance

- Core/package import remains JAX/Optax-lazy; missing optional dependencies fail
  with a clear experiment-unavailable error.
- Corpus construction reproduces PR49's exact static-network holdout
  fingerprint and fails closed on any mismatch.
- Row-local control ignores edge arrays; graph candidate consumes directed edge
  indices/features and masks without treating padding or blocked edges as real.
- Metric aggregation weights valid target rows and reports every non-empty
  distance bin for every validation map and dynamic state; no validation labels
  influence normalization/training.
- The fixed canonical corpus must populate all four declared distance bins for
  every held-out map/state. Result construction rejects missing/duplicate slice
  identities, cross-model count mismatch, or slice aggregates that do not
  reconstruct top-level MAE/RMSE.
- Focused JAX tests exercise reverse-edge propagation, blocked-edge masking,
  optimizer execution, and same-seed short-run repeatability when the optional
  JAX extra is installed.
- Artifact generation is deterministic for a supplied result and rejects a
  non-empty output directory.
- Runtime NN authorization and route-legality change remain hardcoded false.
- Existing deterministic replay/runtime tests remain green.

## Compact CCoT

Question: Does directed graph context add held-out-map cost-to-go signal beyond
the rejected row-local representation?
Evidence: PR49 isolates row-local target conflict; PR50 closes graph and split
contracts; a CUDA JAX device is available.
Inference: One fixed, controlled graph-vs-row-local experiment can change the
NN-lane decision without reopening runtime authority.
Counterevidence checked: Graph training may be slower, nondeterministic, or no
more accurate; all are explicit stop outcomes.
Decision: Run a three-seed GPU bakeoff with one deterministic repeat and no
post-result tuning.
Falsifier: The graph model misses the fixed improvement gate, violates
determinism/provenance, or produces non-finite output.
Next action: If supported, specify a separate inference/profile RFC; otherwise
stop the cost-to-go NN lane and return to the Rust/NumPy/GPU-kernel queue.
