# Conservative Entry Projection Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development for the Rust task and the parent for the independent Python frontend/oracle; one integrated independent review.

**Goal:** implement report choice A while retaining all demand, finite-response physics, physical labels and resource limits.

**Architecture:** support-change endpoint sweep followed by positive category-wise first-moment projection. One cohort per protected time segment. Exact width zero remains the default oracle.

**Tech Stack:** existing Python 3.12/3.13, Rust/PyO3; no new runtime dependencies.

**Spec:** `docs/v1/CONSERVATIVE_ENTRY_PROJECTION_DESIGN_KO.md`.

## Global Constraints

No population/horizon reduction, no mass pruning, no tolerance relaxation. Keep signal/closure and next-movement support barriers; retain original point atoms. Keep exact route/category identities. Policy width enters checkpoint binding. No full repository CI, merge or release in this task. Container experiments remain small; compiled tests use an isolated worktree on the already authorized device.

## Review Focus

Tiny blocked turns must not poison a preceding open-only cohort. Future route differences remain distinct Parts. Invalid and sub-ULP widths fail explicitly. Byte-budget failures preserve state. Exact checkpoints cannot be reinterpreted as projected states.

## Task 1: Python numerical oracle and physical counterexamples

- [x] Add targeted behavior tests for conservation, local W1 bounds, support transitions, atoms, bounded row growth, identity, error/refinement.
- [x] Run baseline failure showing descendant row proliferation; distinguish absent-interface import failures from behavioral failures.
- [x] Implement `project_entry_packets` in `src/metroflow/entry_projection.py`; connect optional width in `packet_network.py`.
- [x] Run the changed dependency tests and preserve commands/output.

## Task 2: Rust implementation and actual runtime integration

- [x] Rust child implements same contract in `v1_road.rs` / `v1_engine.rs` and native parity tests.
- [x] Parent connects `native_road.py`, `native_engine.py`, `native_release_driver.py`, campaign CLI and provenance.
- [x] Compile isolated local worktree, run Python/Rust parity, resource failure and checkpoint replay.

## Task 3: Discriminating experiments and handoff

- [x] Run exact versus projected comparisons with fixed demand; refine projection width separately from timestep.
- [x] Review important diff and resolve concrete findings; stop repeated generic audits.
- [x] Store receipt, local-agent executable instructions and remaining full-scale acceptance obligations. Keep V03 / 19 of 21 status scoped until actual acceptance evidence exists.

## Actual disposition

The implementation and scoped review unit is complete. Python 88, selected native 164, and Rust projection unit 7 tests passed (overlapping suites). The actual full-calendar Valley pilot stopped at 26010 s with transfer-candidate resource rejection; the unchanged 3-city repeated 24h acceptance is NOT_RUN. A paired 25500 s city prefix measured reduced records/RSS and nonzero endpoint observable changes. Evidence, mathematical limits, remaining unsupported transport records, and an executable next construction are recorded in artifacts/v1_entry_projection_20261117. Checked boxes denote completion of these scoped tasks, not completion of V03.
