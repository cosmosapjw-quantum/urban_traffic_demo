# PR09 Active-Agent State Layout Recheck

## Goal

Decide whether active-agent state layout work is review-ready, and record the
decision without changing runtime behavior.

## Evidence

- Hardware atlas card: active-agent symbols remain possible CPU/Rust/NumPy fits,
  but atlas cards are diagnostic only.
- Runtime benchmark artifact:
  `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`.
- Replay/parity artifact: existing active-agent runtime tests remain unchanged.

## In Scope

- Mark PR08 complete in roadmap state after `29daebe`.
- Mark PR09 as deferred by evidence in `ACCELERATION_PR_LIST.md`.
- Update `DEPRECATED_IDEAS.md`, `PROJECT_STATE.md`, and `DECISION_LOG.md` with
  the active-agent layout recheck decision.
- Add docs consistency tests for the PR09 evidence gate.

## Out Of Scope

- Do not change `ActiveAgentPool`, runtime movement, Rust agent backend, or
  active-agent telemetry semantics.
- Do not add new benchmark timing splits for active-agent state layout.
- Do not add GPU/NN state-mutation authority.

## Public Contract

- APIs/config/artifact keys: unchanged.
- Fallback behavior: unchanged.
- Replay/cache impact: unchanged.

## Acceptance Criteria

- Targeted tests: `tests/test_acceleration_roadmap_docs.py`.
- Existing active-agent Rust/runtime tests still pass.
- Full gates: pytest, ruff, `git diff --check`.
- Review loop max: 3.

## Compact CCoT

Question: Should PR09 implement active-agent state layout changes now?

Evidence: Active-agent update/allocation/candidate-selection/pool-write stages
are below the review gate in the deep runtime audit; route refresh and dynamic
potential remain review-ready.

Inference: Active-agent layout stays on the watchlist and should not drive this
slice.

Counterevidence checked: Atlas hardware-fit labels still list active-agent
symbols as acceleration candidates, but atlas cards do not authorize
implementation without measured gate evidence.

Decision: Make PR09 a docs-only evidence-gated deferral.

Falsifier: A broader deterministic suite or post-route-potential benchmark makes
typed-array pool replacement review-ready across seeds.

Next action: Commit the deferral and open PR10 Zero-Copy/Rayon RFC.
