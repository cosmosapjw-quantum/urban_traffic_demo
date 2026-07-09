# Acceleration PR List

Last updated: 2026-07-10
Status: active execution queue

## Execution Contract

Every PR starts with a spec file under `specs/02x-<slug>/spec.md` and a task
list under `specs/02x-<slug>/tasks.md`. Each PR is implemented by a fresh
subagent or a tightly scoped inline task. The controller provides exact context;
subagents must not rediscover the whole repository.

Each PR has at most three review/fix loops:

1. `/review-spec`: spec compliance, public contract, scope, forbidden work.
2. `/review-code`: bugs, maintainability, test quality, import boundaries.
3. `/review-drift`: atlas/benchmark evidence, local-minimum risk, claim
   provenance.

If findings remain after three loops, mark the PR `BLOCKED`, do not commit
feature code, and record the blocker in `DECISION_LOG` or `PROJECT_STATE`.

Commit only after targeted tests, full gates, exact staged-file review, and
closed review findings.

## PR00 — Docs Bootstrap

Status: complete in `3607530`.

- Create `docs/PRD_ACCELERATED_RUNTIME.md`.
- Create `docs/harness/ACCELERATION_PR_LIST.md`.
- Create `docs/superpowers/plans/2026-07-10-metroflow-accelerated-runtime.md`.
- Record the roadmap decision in source-of-truth docs.
- Review: docs/spec only; verify no runtime claims or backend authorization are
  added.
- Commit: `docs(prd): define accelerated runtime roadmap`.

## PR01 — Workload Matrix v1

Status: complete in `31064c5`.

- Extend benchmark metadata for workload classes:
  - eager runtime 1-step and 2-step;
  - generated OD routing;
  - dense flow/turn batch;
  - route candidate K>1 scoring;
  - active-agent dense pool.
- Do not add backend logic.
- `enabled` means measured in the current suite; entries requiring another
  probe must use explicit `coverage_state` metadata rather than claiming
  coverage.
- Tests: benchmark payload schema, manifest metadata, no eager accelerator
  imports.
- Commit: `test(benchmarks): add hardware-fit workload matrix`.

## PR02 — Atlas Decision-Card Closure

Status: complete in `b434258`.

- Link workload matrix outputs to `hardware-fit-atlas` decision cards.
- Render next-probe summaries for reviewer-facing markdown/HTML.
- Anti-drift gate: no duplicate stage cards; no new probe unless it changes a
  decision.
- Tests: stage-card aggregation, duplicate prevention, artifact schema.
- Commit: `docs(benchmarks): link atlas cards to workload matrix`.

## PR03 — Dynamic-Potential Cache Amortization

Status: complete in `e292685`.

- Target destination potential recompute/cache behavior in the Python baseline.
- Improve cache invalidation observability and stale-entry pruning before
  adding any new backend or widening reuse policy.
- Preserve baseline route legality and replay fingerprints.
- Scope guard: do not reuse potentials across `runtime_flow_generation` or
  incident-generation changes.
- Tests: cache hit/recompute/prune counters, invalidation generation changes,
  no-route behavior, replay parity.
- Commit: `perf(routing): amortize dynamic potential cache`.

## PR04 — Rust Potential-Only Bakeoff

Status: complete in `a80b369`.

- Compare Python and Rust dynamic-potential only.
- Do not enable whole-runtime Rust routing.
- Acceptance: generated OD parity, copy-boundary timing, and parent route
  refresh reduction.
- Tests: Rust extension optional skip, explicit fail-closed behavior, `auto`
  fallback, copy-boundary metadata.
- Commit: `perf(routing): benchmark rust potential core`.

## PR05 — Dense Flow Scale Probe

Status: complete in `987cdbc`.

- Build larger synthetic flow/turn workloads.
- Compare NumPy baseline, Rust flow, and optional JAX compile/steady-state.
- Do not add custom CUDA scaffold.
- Scope guard: `jax_optional` is a benchmark probe backend, not a runtime
  `flow_backend` value.
- Tests: scaled dense flow benchmark schema, optional JAX skip, first-call vs
  steady-state timing fields.
- Commit: `test(flow): add dense flow acceleration probe`.

## PR06 — Route Metadata/Scoring Batch Probe

Status: complete in `c2c052f`.

- Measure K>1 candidate metadata, path-size scoring, and reroute scoring batch
  shapes.
- Determine NumPy/JAX/NN fit without changing route legality.
- Scope guard: scoring probes are benchmark-only and cannot become route
  legality or runtime state-mutation authority.
- Tests: K>1 metadata timing, path-size utility preservation, reroute scoring
  batch shape metadata.
- Commit: `test(routing): add route scoring batch probes`.

## PR07 — Simulator Label Dataset v0

Status: complete in `b636b2a`.

- Generate deterministic simulator-only labels for cost-to-go and route
  scoring from baseline authority.
- No external data and no runtime NN authority.
- Scope guard: labels are supervised experiment substrate only and cannot become
  route legality or runtime fallback authority in this PR.
- Tests: deterministic label export, label schema, replay fingerprint, no
  external file/network dependency.
- Commit: `feat(learning): add simulator label export`.

## PR08 — Optional NN Experiment Harness

Status: complete in `29daebe`.

- Add optional experiment surface only after PR07 labels exist.
- Prefer optional Python-side training/inference first.
- If PyTorch is introduced, it must be an optional extra and excluded from core
  import.
- Scope guard: surrogate outputs are experiment-only and cannot become route
  legality or runtime fallback authority in this PR.
- Tests: optional dependency skip, model/version/fallback metadata, no route
  legality authority.
- Commit: `feat(learning): add optional route surrogate harness`.

## PR09 — Active-Agent State Layout Recheck

Status: complete in `52e7aec`.

- Reopen active-agent array/pool work only if workload matrix makes it
  review-ready.
- Current evidence keeps `active_agent_pool_array_write` below the review gate.
  No active-agent state layout implementation is authorized in this PR.
- Update `DEPRECATED_IDEAS.md`, `PROJECT_STATE.md`, and `DECISION_LOG.md`;
  preserve existing slot-order determinism, pool replacement parity, and
  telemetry tests without changing runtime behavior.
- Reopen only if typed-array pool replacement becomes review-ready across
  deterministic seeds, or route potential work is completed and active-agent
  array write again dominates the next review-ready stage.
- Commit: `docs(harness): defer active agent layout recheck`.

## PR10 — Zero-Copy/Rayon Feasibility RFC

Status: RFC accepted; implementation not authorized.

- Evaluate Rust zero-copy NumPy FFI and Rayon only after copy-boundary cost is
  measured.
- RFC first; implementation only if evidence supports it.
- Tests: documentation link checks and no build-surface changes unless a later
  implementation PR opens them.
- No zero-copy NumPy FFI, Rayon, or new Rust build surface is allowed in this
  PR.
- Admission RFC: `docs/rust/ZERO_COPY_RAYON_ADMISSION.md`.
- Commit: `docs(rust): define zero-copy backend admission`.

## PR11 — C++/CUDA Admission RFC

- Define future custom CUDA/libtorch candidate interface for one narrow kernel:
  dense flow, route-score batch, or OD/policy batch.
- No build scaffold unless a prior PR proves the gate.
- Tests: docs/checklist only, no accepted runtime config values.
- Commit: `docs(cuda): define custom kernel admission gate`.

## PR12 — PRD/State Closure

- Consolidate `PROJECT_STATE`, `DECISION_LOG`, `DEPRECATED_IDEAS`,
  validation benchmark docs, and next-session prompt.
- Record which PRs were completed, deferred, blocked, or superseded.
- Tests: documentation consistency checks and final gates.
- Commit: `docs(harness): record acceleration roadmap state`.

## Spec Template

Use this template at `specs/02x-<slug>/spec.md`:

```markdown
# <Feature Name> Spec

## Goal
<One sentence.>

## Evidence
- Hardware atlas card:
- Runtime benchmark artifact:
- Replay/parity artifact:

## In Scope
- <Specific behavior.>

## Out Of Scope
- <Forbidden behavior.>

## Public Contract
- APIs/config/artifact keys:
- Fallback behavior:
- Replay/cache impact:

## Acceptance Criteria
- Targeted tests:
- Full gates:
- Review loop max: 3

## Compact CCoT
Question:
Evidence:
Inference:
Counterevidence checked:
Decision:
Falsifier:
Next action:
```

Use this template at `specs/02x-<slug>/tasks.md`:

```markdown
# <Feature Name> Tasks

- [ ] Write RED tests for the public contract.
- [ ] Verify RED failure.
- [ ] Implement the smallest baseline-safe change.
- [ ] Run targeted tests.
- [ ] Update docs/artifacts if decision boundaries changed.
- [ ] Run `/review-spec`; fix findings.
- [ ] Run `/review-code`; fix findings.
- [ ] Run `/review-drift`; fix findings or stop after loop 3.
- [ ] Run full gates.
- [ ] Stage exact files and commit.
```

## Subagent Prompt Template

```markdown
You are implementing <PRxx title> in urban_traffic_demo.

Controlling files:
- AGENTS.md
- docs/PRD_ACCELERATED_RUNTIME.md
- docs/harness/ACCELERATION_PR_LIST.md
- docs/harness/RUNTIME_ACCELERATION_DECISION_GUARDRAILS.md
- artifacts/runtime_spine_review/hardware-fit-atlas.md

Task:
<Paste exact PR section and task checklist.>

Hard boundaries:
- Do not add external-data learning.
- Do not add RL/LLM route authority.
- Do not add lane-level microscopic default.
- Do not add PyTorch/libtorch/custom CUDA unless this PR explicitly admits it.
- Preserve Python/NumPy baseline authority, fallback, immutable state, cache
  invalidation, and deterministic replay.

Required output:
- Files changed.
- Tests run with exact commands.
- Review notes.
- Commit SHA or BLOCKED reason.
```

## Review Checklist

### /review-spec
- Does the implementation satisfy the spec and nothing outside it?
- Are public APIs, artifact keys, and fallback semantics explicit?
- Are forbidden scopes absent?

### /review-code
- Are imports lazy where optional backends are involved?
- Are tests behavior-focused and deterministic?
- Are copy-boundaries and dtype conversions explicit?
- Are unrelated refactors absent?

### /review-drift
- Does the latest atlas agree with measured stage evidence?
- Does the PR change a decision, or only add reporting surface?
- Are nested metrics not treated as exclusive wall-clock share?
- Is GPU/NN kept away from deterministic state mutation?
- Is the compact CCoT present and falsifiable?

## Anti-Drift Rules

- Stop after two consecutive PRs on the same stage unless the second changes the
  parent-stage decision.
- If stage share moves by less than 5 percentage points and recommendation is
  unchanged, stop instrumentation and switch lanes.
- If a nested metric improves but the parent does not, record it and stop that
  lane.
- GPU/NN cannot target deterministic state mutation. If a GPU/NN proposal
  touches state apply, reroute it to Rust/Python layout work.
- Smoke artifacts are diagnostics only. Validation claims require replay,
  invariants, and deterministic multi-seed evidence.
- Keep Rust/control-flow, NumPy/SIMD numeric, GPU tensor batch, and NN
  surrogate lanes visible in every step-back.
