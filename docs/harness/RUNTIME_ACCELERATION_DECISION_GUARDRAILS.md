# Runtime Acceleration Decision Guardrails

Status: active
Last updated: 2026-07-09

This document controls runtime backend/NN triage after the deep acceleration
audit. It exists to prevent local-minimum optimization loops, evidence drift,
and repeated instrumentation that does not change the next engineering action.

## Scope

Applies to:

- Rust CPU backend migration choices.
- JAX/GPU/NN surrogate experiment admission.
- Runtime benchmark interpretation.
- `/review` checks for acceleration-related diffs.

Does not authorize:

- PyTorch/libtorch/custom CUDA dependencies.
- NN as routing authority.
- Runtime defaults other than deterministic Python/NumPy baseline.

## Current Evidence Baseline

Primary artifact:
`artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`

Project state summary:
`docs/harness/PROJECT_STATE.md`

Observed on seeds `41,42,43` with eager trip generation:

- `route_candidate_refresh` remains a large stage.
- `route_candidate_potential` and `route_candidate_path_build` are both
  sub-threshold nested graph workloads.
- `active_agent_update` is large because of `active_agent_allocation`.
- `active_agent_allocation` is large because of `active_agent_pool_write`.
- `active_agent_candidate_selection` is small in both 1-step and 2-step smoke
  workloads.

Current implication:

- Active-agent next slice should target pool/plugin-memory writes, not NN/JAX
  route-choice scoring.
- Route next slice should target Rust/algorithmic graph core before custom CUDA.
- NN remains a supervised surrogate research lane, not the next runtime hot-path
  fix.

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

- `active_agent_pool_write`
- route candidate graph core, especially `route_candidate_path_build`

### JAX/GPU

Open a JAX/GPU slice when:

- work is dense or batch scoring shaped;
- stage is review-ready or a clear sub-stage will become review-ready at scale;
- baseline labels remain authoritative;
- first-call compile time and steady-state time are measured separately.

Current JAX/GPU watchlist:

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

Review must explicitly check:

- Is the patch adding instrumentation without a decision it can change?
- Is a nested metric being treated as exclusive wall-clock share?
- Is GPU/NN being aimed at deterministic state mutation?
- Does the patch preserve explicit fail-closed backend behavior?
- Are docs and benchmark artifacts updated when the decision boundary changes?

## Next Slice Boundary

Preferred next implementation slice:

- split `active_agent_pool_write` into typed-array replacement and
  plugin-memory dict update;
- reduce dict-heavy selected-candidate metadata writes when possible;
- keep existing route timing evidence unchanged until active-agent write cost is
  either reduced or falsified as the dominant cost.

Stop condition:

- If pool-write sub-breakdown shows dict/plugin-memory is not dominant, step
  back before implementing Rust pool-write changes.
