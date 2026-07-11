# Feature Specification: Multi-City Cost-To-Go Feature Audit

Status: ACCEPTED

Threshold provenance: the canonical thresholds were fixed in this PR before
the canonical CLI run and were not relaxed after the result was observed. This
is not a prior tracked preregistration.

## Goal

Decide whether PR48's row-local cost-to-go feature contract is sufficiently
non-degenerate for a bounded JAX MLP bakeoff, or whether adjacency/edge tensors
must be specified first.

## Evidence

- PR48 supplies 20 versioned, immutable, ID-free model inputs and baseline-only
  labels, but explicitly does not establish cross-city adequacy.
- One 861-node/3,120-link generated-city probe completes topology, CSR, and four
  destination labels in about 1.4 seconds on the local host, so a 3x3x2 matrix
  is feasible without another timing-instrumentation PR.
- Canonical 3-style/3-seed/2-state execution retains all 64,968 expected rows,
  has 90% nonconstant columns and 99.89% joint dynamic response, but rejects the
  row-local MLP probe: 20.04% relation coverage contains 69.07% conflicting rows,
  above the fixed 25% limit.

## Scope

- Audit exactly three or more unique morphology styles and seeds.
- For each generated map, select at least four spatially dispersed destinations
  from geometry only.
- Export baseline labels under free-flow and deterministic stressed/closure
  link states.
- Summarize per-feature variance/range/nonzero share, normalized distance bins,
  target support, closure coverage, per-map destination-group split viability,
  near-duplicate feature/target conflicts, and a deterministic seed-level map
  holdout fingerprint.
- Write compact JSON, Markdown, and manifest diagnostics without raw label rows.

## Canonical Decision Gate

- At least 70% of feature columns must have standard deviation above `1e-6`.
- Target standard deviation must exceed `1e-6`.
- Every map must contain both dynamic states, at least one deterministic closure,
  full `node_count * destination_count` row retention, and at least four
  destination groups that can form the PR48 v1 split.
- Closure selection must retain directed reachability by accepting a closure
  only when its edge endpoints remain connected through an alternate path.
- At least 5% of rows must enter a cross-map, 5%-quantized near-duplicate
  comparison; no more than 25% of covered rows may have normalized target range
  above `0.10`.
- At least 1% of matched free-flow/stressed rows must change both feature and
  target values.
- A fixed seed-49 map split must hold one scenario seed out across every style,
  with no static-network fingerprint overlap.
- Only the exact 4-destination, 3%-closure, `1e-6`, 70% canonical profile may
  produce an actionable `admissible` or `relation_rejected` state. Exploratory
  threshold overrides can produce summaries only.
- `admissible` authorizes only a subsequent row-local JAX MLP probe.
  `relation_rejected` routes PR50 to an adjacency/edge-tensor contract; every
  other failure is `inconclusive` and stops the surrogate lane.

## Non-goals

- No model fitting, accuracy claim, runtime backend, or route-legality change.
- No external data, named-city calibration, empirical validation, GNN library,
  PyTorch/libtorch, or CUDA scaffold.
- No raw dataset artifact or new runtime timing counter.

## Compact CCoT

Question: Can row-local v1 support a meaningful GPU model experiment?
Evidence: PR48 closes provenance/leakage contracts but feature support across
generated-city diversity was unmeasured.
Inference: Audit support and holdout feasibility before selecting a model.
Counterevidence checked: Nonzero variance does not prove predictive adequacy.
Decision: Admit only a feature-support diagnostic with a gate fixed before the
canonical run and preserve the failed threshold unchanged.
Falsifier: A leakage-safe graph contract cannot preserve directed topology and
dynamic edge state within deterministic memory-bounded batches.
Next action: The canonical row-local gate fails. PR50 must define
adjacency/edge-state tensors; graph-aware JAX training remains conditional in
PR51.

## Review Closure

- `/review-spec`: no findings after decision-state and artifact reconciliation.
- `/review-code`: no findings after gate-consistency, authority, array-aliasing,
  and public closure-path fixes.
- `/review-drift`: no findings after threshold-provenance downclaim and
  reason-specific decision routing.
- Canonical bundle regenerated independently and byte-compared.
- Final gates: `547 passed`, Ruff clean, `git diff --check` clean.
