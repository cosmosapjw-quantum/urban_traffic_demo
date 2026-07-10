# Runtime Acceleration Decision Guardrails

Status: active
Last updated: 2026-07-10

This document controls runtime backend/NN triage after the deep acceleration
audit. It exists to prevent local-minimum optimization loops, evidence drift,
and repeated instrumentation that does not change the next engineering action.

## Scope

Applies to:

- Rust CPU backend migration choices.
- JAX/GPU/NN surrogate experiment admission.
- Runtime benchmark interpretation.
- Whole-code hardware-fit atlas interpretation.
- `/review` checks for acceleration-related diffs.

Does not authorize:

- PyTorch/libtorch/custom CUDA dependencies.
- NN as routing authority.
- Runtime defaults other than deterministic Python/NumPy baseline.

## Whole-Code Hardware-Fit Atlas

Before opening a new backend implementation slice after a step-back request,
generate or refresh the hardware-fit atlas:

```bash
.venv/bin/python -m metroflow.benchmarks.run --hardware-atlas \
  --hardware-atlas-artifact-prefix artifacts/runtime_spine_review/hardware-fit-atlas
```

If a runtime suite JSON artifact already exists, link its stage timings:

```bash
.venv/bin/python -m metroflow.benchmarks.run --hardware-atlas \
  --hardware-atlas-runtime-suite-json artifacts/runtime_spine_review/runtime-suite-eager-smoke.json \
  --hardware-atlas-artifact-prefix artifacts/runtime_spine_review/hardware-fit-atlas
```

The atlas is a diagnostic planning artifact. It maps static symbol roles to
Rust CPU, NumPy/SIMD, JAX/GPU, future torch/custom CUDA, NN surrogate, and
keep-Python lanes without importing JAX, torch, CUDA, or `_metroflow_rust`.

Atlas decision cards are not implementation authorization. They only identify
which measured probe can change the next action. Open implementation only when
runtime-stage evidence or copy-inclusive microbench evidence supports the card.

## Current Evidence Baseline

Primary artifact:
`artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`

Project state summary:
`docs/harness/PROJECT_STATE.md`

Observed on seeds `41,42,43` with eager trip generation:

- `route_candidate_refresh` remains a large stage.
- Baseline dynamic-potential Dijkstra now preserves `float32` heap updates and
  reaches generated OD routes that were previously misclassified as no-route.
- `route_candidate_potential` is now review-ready in the 1-step and 2-step
  eager suites.
- `dynamic_potential_recompute` is the dominant nested cost inside route
  candidate refresh.
- `route_candidate_path_build` is below the 0.30 review gate after the baseline
  Dijkstra correctness fix.
- `active_agent_update` and `active_agent_allocation` are no longer
  review-ready after batched plugin-memory replacement.
- `active_agent_pool_write` is now split into
  `active_agent_pool_array_write` and `active_agent_plugin_memory_write`.
- `active_agent_plugin_memory_write` is near zero after batched replacement.
- `active_agent_candidate_selection` is small in both 1-step and 2-step smoke
  workloads.

Current implication:

- Active-agent pool-array replacement stays on the Rust CPU watchlist but should
  not drive the next slice.
- Route next slice should target dynamic-potential recompute and cache
  amortization before greedy path-build.
- Explicit whole-suite `routing_backend="rust_cpu"` is still not runtime-ready:
  debug `maturin develop` timed out at 90 seconds, while release
  `maturin develop --release` completed the 1-seed/1-step eager suite in
  `26.70s` versus `8.02s` for baseline.
- Release Rust routing moves cost away from dynamic-potential recompute and into
  path-build/metadata copy-boundary work, so the next slice should be a narrower
  potential-only/cache-amortization contract rather than whole-routing
  activation.
- NN remains a supervised cost-to-go surrogate research lane, not a runtime
  authority or route-legality replacement.

## Metacognitive Self-Ask

Before adding another timing counter, backend, or optimization patch, answer all
questions in the patch description or review artifact:

1. What decision will this new evidence change?
2. What is the concrete alternative if the evidence contradicts the current plan?
3. Is the measured stage exclusive, nested, or overlapping?
4. Does this target code execution cost, memory layout cost, or policy/scoring
   quality?
5. Could the result be a workload artifact of 1-step eager activation?
6. Does the change preserve deterministic replay and baseline fallback?
7. Does it reduce the code path, or only add another reporting surface?

If the answer to question 1 is "none", stop and do not add instrumentation.

## Step-Back Gates

Trigger a step-back review instead of another micro-optimization when any of
these conditions hold:

- Three consecutive benchmark/reporting patches refine the same conclusion.
- A new metric is nested inside an already nested metric without changing the
  recommended next slice.
- Candidate stage mean share moves by less than 5 percentage points across two
  deterministic suites and the same stage remains review-ready.
- The proposed optimization improves a non-review-ready stage while a
  review-ready stage remains untreated.
- A GPU/NN proposal targets state mutation rather than batch scoring or dense
  numeric kernels.

Required step-back output:

- Restate the highest-level project objective.
- List current hypotheses and at least one falsifier for each.
- Decide whether to implement, instrument, or stop.
- Update this document or `docs/harness/DECISION_LOG.md` if the decision changes.

## Compact CCoT Record

Use a compact chain-of-claims record, not private reasoning transcript. The
record should be short, auditable, and evidence-linked:

```text
Question:
Evidence:
Inference:
Counterevidence checked:
Decision:
Falsifier:
Next action:
```

This format is mandatory for acceleration review artifacts and optional for
ordinary implementation commits.

## Backend Admission Rules

### Rust CPU

Open a Rust CPU slice when:

- the target stage is CPU/control-flow heavy;
- baseline/Rust parity can be tested on deterministic input;
- the Python boundary can remain NumPy-owned or explicit copy-boundary;
- explicit `rust_cpu` can fail closed and `auto` can fallback.

Current Rust-ready candidates:

- dynamic-potential recompute/cache amortization
- route candidate path-build graph core only after potential recompute is
  reduced or falsified
- `active_agent_pool_array_write` only after route potential work is addressed or
  active-agent array write becomes review-ready again

### JAX/GPU

Open a JAX/GPU slice when:

- work is dense or batch scoring shaped;
- stage is review-ready or a clear sub-stage will become review-ready at scale;
- baseline labels remain authoritative;
- first-call compile time and steady-state time are measured separately.

Current JAX/GPU watchlist:

- dynamic-potential cost-to-go batches after first-call compile and steady-state
  timing are separated;
- route candidate scoring or metadata batches at larger K;
- flow update at larger dense workloads.

### NN Surrogate

Open an NN surrogate slice only when:

- deterministic simulator labels are collected;
- baseline route legality remains authoritative;
- the target is scoring/cost approximation, not state mutation;
- replay can record model/version/fallback metadata.

Current NN watchlist:

- cost-to-go surrogate labels from dynamic potential;
- route scoring labels after candidate scoring becomes a material stage.

## `/review` Checklist

Every acceleration-related `/review` must read:

1. `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`
2. `docs/harness/RUNTIME_ACCELERATION_DECISION_GUARDRAILS.md`
3. `docs/harness/PROJECT_STATE.md`
4. `docs/harness/DECISION_LOG.md`
5. `docs/harness/DEPRECATED_IDEAS.md`
6. `docs/VALIDATION_BENCHMARK_PLAN.md`
7. The latest `artifacts/runtime_spine_review/hardware-fit-atlas.md`, if the
   review changes acceleration direction or opens a new backend slice.

Review must explicitly check:

- Is the patch adding instrumentation without a decision it can change?
- Is a nested metric being treated as exclusive wall-clock share?
- Is GPU/NN being aimed at deterministic state mutation?
- Does the static hardware-fit atlas agree with the measured runtime stage?
- Does the patch preserve explicit fail-closed backend behavior?
- Are docs and benchmark artifacts updated when the decision boundary changes?

## Next Slice Boundary

Preferred next implementation slice:

- close PR48's target-independent cost-to-go feature and group-split contract;
- audit that contract across multiple generated city styles, seeds,
  destinations, and dynamic states before fitting a model;
- keep Python baseline Dijkstra as label and route-legality authority;
- keep Rust potential/cache work and active-agent array write on their existing
  watchlists while the NN label lane receives this bounded step-back slice;
- return to GPU flow only through the explicit checkpoint-cadence falsifier in
  PR47, not through another nested flow timing counter.

Stop condition:

- If PR49 finds degenerate row-local features or cross-map holdout cannot be
  constructed, do not tune an MLP. Specify adjacency/edge tensors or stop the
  surrogate lane before PR50.
