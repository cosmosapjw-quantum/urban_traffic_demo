# Atlas Decision-Card Closure Spec

## Goal

Link workload matrix metadata to hardware-fit atlas decision cards so reviewers
can see which workload classes support, block, or defer each backend decision.

## Evidence

- Hardware atlas card: `artifacts/runtime_spine_review/hardware-fit-atlas.md`
  already generates stage links and decision cards.
- Runtime benchmark artifact:
  `report_data["workload_matrix"]` from PR01 distinguishes measured suite
  coverage from configured or dedicated-probe requirements.
- Replay/parity artifact: no runtime behavior changes; artifact shape only.

## In Scope

- Read workload matrix entries from a runtime suite payload passed to
  `build_hardware_atlas`.
- Link workload entries to decision cards by stage group/target.
- Render workload support and next-probe summaries in JSON, markdown, HTML, and
  manifest artifacts.
- Prevent duplicate stage decision links.

## Out Of Scope

- New benchmark workload execution.
- Backend implementation or backend default changes.
- PyTorch, libtorch, custom CUDA, or new JAX runtime use.
- Treating static atlas output or smoke metadata as validation evidence.

## Public Contract

- Hardware atlas payload keys:
  - `workload_matrix`
  - `decision_workload_links`
  - `next_probe_summaries`
- Hardware atlas manifest keys:
  - `workload_class_count`
  - `next_probe_summary_count`
- Fallback behavior: if no workload matrix exists, emit empty link/summary
  lists and preserve current atlas behavior.
- Replay/cache impact: none.

## Acceptance Criteria

- Targeted tests:
  - `tests/test_hardware_atlas.py` verifies workload-card linking, duplicate
    prevention, artifact schema, and no eager accelerator imports.
- Full gates:
  - `.venv/bin/python -m pytest -q`
  - `.venv/bin/python -m ruff check .`
  - `git diff --check`
- Review loop max: 3.

## Compact CCoT

Question: Which workload classes can change the next backend decision for each
atlas card?

Evidence: PR01 adds measured/configured/dedicated-probe workload coverage; the
atlas already owns decision cards.

Inference: The correct closure is a report-layer join, not a new benchmark or
backend.

Counterevidence checked: A workload matrix without observed coverage remains
diagnostic only and cannot authorize implementation.

Decision: Link workload classes to existing atlas decision cards and render
falsifiable next-probe summaries.

Falsifier: If linking creates duplicate cards or invents probes unrelated to a
decision card, block the PR.

Next action: Use the linked summaries to drive PR03 cache amortization or
redirect if the evidence changes.
