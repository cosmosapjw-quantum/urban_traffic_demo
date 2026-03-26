<!--
Sync Impact Report
Version change: unversioned template -> 1.0.0
Modified principles:
- template principle slot 1 -> I. Contract-First Engineering
- template principle slot 2 -> II. Conservation Before Realism
- template principle slot 3 -> III. Deterministic Replay and Auditability
- template principle slot 4 -> IV. Explicit Time-Step and Units Discipline
- template principle slot 5 -> V. Regression-First Testing
- added -> VI. Small Reversible Patches
- added -> VII. No Same-Tick Positive Feedback
- added -> VIII. Documentation Synchronization
Added sections:
- Operational Boundaries
- Review and Delivery Gates
- Definition of Done
Removed sections:
- None
Templates requiring updates:
- ✅ .specify/templates/constitution-template.md
- ✅ .specify/templates/plan-template.md
- ✅ .specify/templates/spec-template.md
- ✅ .specify/templates/tasks-template.md
- ⚠ pending: .specify/templates/commands/*.md (directory absent in this repo)
Follow-up TODOs:
- None
-->
# MetroFlow Constitution

## Core Principles

### I. Contract-First Engineering
State and interface contracts come before feature growth. Every new public
function MUST declare inputs, outputs, units, admissible ranges, invariants
preserved, and failure conditions at the point of definition or in the
authoritative contract doc it references. Invalid states MUST raise or fail
validation immediately; downstream code MUST not normalize, clamp, or silently
repair contract violations. Rationale: MetroFlow is still a baseline simulator;
undefined interfaces create fake progress and destroy replayability.

### II. Conservation Before Realism
Traffic dynamics are invalid if they silently create or destroy mass.
Nonnegativity checks alone are insufficient. Every update that moves vehicles
MUST make sender limits, receiver limits, and any shared budgets explicit in
code or an attached contract, and outflow MUST never exceed physically
available mass. Rationale: a visually plausible but non-conservative model is
not a valid baseline.

### III. Deterministic Replay and Auditability
Equivalent inputs, seeds, schedules, and journals MUST produce equivalent
outcomes. Hidden mutation, leaked state across runs, iteration-order
dependence, and implicit randomness are forbidden. Every nontrivial update path
MUST be inspectable through tests, logs, or replay artifacts sufficient to
explain state transitions. Rationale: if a result cannot be replayed and
inspected, it cannot be trusted or repaired.

### IV. Explicit Time-Step and Units Discipline
Every evolving quantity MUST state whether it is stored as a stock, per-tick
increment, or per-unit-time rate, and MUST name its units. `dt` handling MUST
be explicit at the update site. Any conversion between rates and increments
MUST be documented and regression tested, especially across multirate
boundaries. Rationale: most silent dynamics bugs in this repo are scale bugs.

### V. Regression-First Testing
Every repaired failure mode MUST get a targeted regression test before broad
suite runs. Smoke tests do not count as validation for contracts, dynamics,
replay, cache invalidation, or feedback loops. Dynamics work MUST include
baseline reproduction plus edge and adversarial cases. Narrow tests MUST run
before scenario suites, benchmarks, or city-scale runs. Rationale: broad green
suites without targeted regressions hide the exact bugs this project keeps
reintroducing.

### VI. Small Reversible Patches
Changes MUST be minimal, scoped, and easy to back out. Large refactors,
framework extraction, or architecture redesign are prohibited unless a contract
hole or replay failure makes them unavoidable and the justification is written
in the active plan. Diffs MUST stay scoped to the active feature and MUST not
mix cleanup with behavioral change. Rationale: the repo is repairing a
baseline, not optimizing for speculative elegance.

### VII. No Same-Tick Positive Feedback
Accessibility, routing, demand, land-use, and policy feedback loops MUST
respect explicit lag structure. Same-tick closures that feed updated travel
conditions back into generation, relocation, or policy in the same step are
forbidden unless the mechanism is modeled explicitly, justified in the spec,
and covered by stability tests. Rationale: uncontrolled same-step feedback
produces artifacts faster than realism.

### VIII. Documentation Synchronization
When a code-level contract, invariant, validation rule, scheduler rule, or
cache invalidation rule changes, the relevant spec, repair note, contract doc,
or benchmark note MUST be updated in the same workstream. Drift between code,
plan, tasks, tests, and docs is a defect. Rationale: this repo uses docs as
executable intent; stale docs are stale requirements.

## Operational Boundaries

- `S2` work MUST land before `S1` expansion. State, contracts, scheduler, cache
  invalidation, and replay are upstream of realism features.
- `WorldState` is immutable by default. Update paths MUST return new state
  rather than mutate shared state in place.
- Baseline fallback is mandatory for routing, policy, or learning logic. A
  simpler deterministic baseline path MUST remain runnable and testable.
- External-data learning is prohibited in baseline work. Model behavior MUST be
  explainable from repository state, authored parameters, and explicit inputs.
- The multirate scheduler is mandatory. Fast, medium, and slow updates MUST
  keep explicit ordering and separation.
- Cache invalidation rules MUST be documented where caches are introduced or
  changed.
- The viewer or visualization loop MUST not block the simulation core loop.
- The following stay out of default scope unless a constitution amendment says
  otherwise: lane-level microscopic defaults, RL or LLM-first route choice, ECS
  or plugin-first architecture, distributed multi-GPU execution, and full
  generic frameworkization.

## Review and Delivery Gates

Every plan, task set, review, and merge request MUST answer these checks
explicitly:

- Contract impact: what public contracts or invariants changed, and where are
  they documented?
- Time-scale impact: what quantities are stocks, rates, or per-tick values, and
  how does `dt` enter?
- Cache invalidation impact: which caches become stale, and what invalidates
  them?
- Replay and regression impact: which deterministic replay paths, journals, or
  regression tests changed?
- Benchmark impact: which baseline, toy, or performance validations must be
  re-run?

For work touching traffic dynamics, routing, accessibility, land-use,
scheduler, or policy:

- targeted regression tests MUST run before the broad suite;
- conservation checks MUST be explicit;
- replay equivalence or justified replay deltas MUST be demonstrated;
- baseline reproduction and at least one edge or adversarial test MUST be
  recorded.

## Governance

This constitution overrides local habits and default templates. A change is
non-compliant until the violating artifact is fixed or the constitution itself
is amended.

Amendment rules:

- Amendments MUST update this file, include a reason, and update affected
  templates or guidance docs in the same change.
- Versioning follows semantic intent: `MAJOR` for removed or materially weakened
  principles, `MINOR` for new principles or new mandatory gates, `PATCH` for
  clarifications that do not change enforcement.
- Compliance review is mandatory in planning and code review. Reviewers MUST
  reject work that lacks contract declarations, hides `dt`, omits conservation
  accounting, breaks replay, or leaves docs/tests unsynchronized.
- If a principle is temporarily waived, the waiver MUST name the violated
  principle, the narrow scope, the risk accepted, the fallback, and the removal
  condition.

## Definition of Done

A feature or repair is not done until all of the following are present in the
same workstream:

- code changes implementing the intended behavior;
- targeted tests for repaired failures and affected invariants;
- validation results, including baseline reproduction and any required
  benchmark or replay evidence;
- artifact updates for every changed contract, scheduler rule, cache rule, or
  benchmark assumption;
- an explicit statement of remaining risks, degraded guarantees, or deferred
  follow-up work.

**Version**: 1.0.0 | **Ratified**: 2026-03-26 | **Last Amended**: 2026-03-26
