# Metroflow Accelerated Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the long-term spec-driven roadmap and execution machinery for Metroflow accelerated runtime work.

**Architecture:** This is a documentation/bootstrap plan. It creates the PRD, PR queue, spec template, subagent prompt template, and review checklist that future implementation PRs must follow. Runtime code is intentionally out of scope for PR00.

**Tech Stack:** Markdown docs, existing benchmark/atlas artifacts, Python 3.12 + NumPy baseline policy, optional Rust/JAX backend policy.

---

## Controlling Context

Read these before implementing any task:

- `AGENTS.md`
- `docs/PRD_ACCELERATED_RUNTIME.md`
- `docs/harness/ACCELERATION_PR_LIST.md`
- `docs/harness/RUNTIME_ACCELERATION_DECISION_GUARDRAILS.md`
- `docs/harness/PROJECT_STATE.md`
- `docs/harness/DECISION_LOG.md`
- `docs/harness/DEPRECATED_IDEAS.md`
- `artifacts/runtime_spine_review/hardware-fit-atlas.md`

## Task 1: PR00 Documentation Bootstrap

**Files:**
- Create: `docs/PRD_ACCELERATED_RUNTIME.md`
- Create: `docs/harness/ACCELERATION_PR_LIST.md`
- Create: `docs/superpowers/plans/2026-07-10-metroflow-accelerated-runtime.md`
- Modify: `docs/harness/PROJECT_STATE.md`
- Modify: `docs/harness/DECISION_LOG.md`

- [ ] **Step 1: Confirm clean starting state**

Run:

```bash
git status --short --branch
```

Expected: no unstaged/untracked files except files intentionally created by this task.

- [ ] **Step 2: Create the accelerated runtime PRD**

Create `docs/PRD_ACCELERATED_RUNTIME.md` with:

```markdown
# PRD — Accelerated Runtime Re-Architecture

Last updated: 2026-07-10
Status: active planning authority

## Product Definition

Metroflow targets an explainable 100k-scale synthetic city simulation where city
generation, mesoscopic traffic, routing, demand, active agents, diagnostics,
and optional learning surfaces remain deterministic and replayable. The
accelerated runtime program restructures the project around a stable Python
frontend/orchestration layer, NumPy authority, optional Rust CPU kernels, and
optional GPU/NN experiment lanes.
```

Then include Problem, Goals, Non-Goals, Architecture, Evidence And Admission
Rules, Success Criteria, and Controlling Documents sections matching
`docs/harness/ACCELERATION_PR_LIST.md`.

- [ ] **Step 3: Create PR list and templates**

Create `docs/harness/ACCELERATION_PR_LIST.md` with PR00 through PR12, the
three-review loop contract, spec template, tasks template, subagent prompt
template, `/review-spec`, `/review-code`, `/review-drift`, and anti-drift
rules.

- [ ] **Step 4: Create this implementation plan**

Create `docs/superpowers/plans/2026-07-10-metroflow-accelerated-runtime.md`
with the exact task and verification steps needed to reproduce PR00.

- [ ] **Step 5: Update project state**

Modify `docs/harness/PROJECT_STATE.md`:

```markdown
- `docs/PRD_ACCELERATED_RUNTIME.md` and
  `docs/harness/ACCELERATION_PR_LIST.md` are the active long-term roadmap for
  spec-driven/subagent-driven acceleration work.
```

Keep benchmark facts and smoke artifact warnings unchanged.

- [ ] **Step 6: Record decision**

Append to `docs/harness/DECISION_LOG.md`:

```markdown
## 2026-07-10: Spec-Driven Accelerated Runtime Roadmap

Status: accepted

### Context

The hardware-fit atlas links static code roles to runtime stage evidence and
shows that backend work must be selected by evidence, not repeated hot-path
inspection.

### Decision

Use `docs/PRD_ACCELERATED_RUNTIME.md` and
`docs/harness/ACCELERATION_PR_LIST.md` as the controlling roadmap for future
acceleration work. Future PRs must start with specs, run capped review loops,
and preserve baseline authority.

### Next Action

Open PR01 Workload Matrix v1 before implementing another backend slice.
```

- [ ] **Step 7: Run docs sanity checks**

Run:

```bash
pattern='TB''D|TO''DO|fill ''in|implement ''later'
rg -n "$pattern" docs/PRD_ACCELERATED_RUNTIME.md docs/harness/ACCELERATION_PR_LIST.md docs/superpowers/plans/2026-07-10-metroflow-accelerated-runtime.md
```

Expected: no output.

- [ ] **Step 8: Run required gates**

Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
```

Expected: pytest all passed, ruff all checks passed, diff check no output.

- [ ] **Step 9: Review staged files**

Run:

```bash
git status --short
git diff --stat
git diff -- docs/PRD_ACCELERATED_RUNTIME.md docs/harness/ACCELERATION_PR_LIST.md docs/superpowers/plans/2026-07-10-metroflow-accelerated-runtime.md docs/harness/PROJECT_STATE.md docs/harness/DECISION_LOG.md
```

Expected: only PR00 docs/state files changed.

- [ ] **Step 10: Commit**

Run:

```bash
git add docs/PRD_ACCELERATED_RUNTIME.md docs/harness/ACCELERATION_PR_LIST.md docs/superpowers/plans/2026-07-10-metroflow-accelerated-runtime.md docs/harness/PROJECT_STATE.md docs/harness/DECISION_LOG.md
git commit -m "docs(prd): define accelerated runtime roadmap"
```

Expected: commit succeeds with only PR00 docs/state changes.
