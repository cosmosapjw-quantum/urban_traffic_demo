# [PROJECT_NAME] Constitution

## Core Principles

### I. Contract-First Engineering
State and interface contracts come before feature growth. Every new public
function MUST declare inputs, outputs, units, admissible ranges, invariants
preserved, and failure conditions at the point of definition or in the
authoritative contract doc it references. Invalid states MUST raise or fail
validation immediately; downstream code MUST not normalize, clamp, or silently
repair contract violations.

### II. Conservation Before Realism
Traffic dynamics are invalid if they silently create or destroy mass.
Nonnegativity checks alone are insufficient. Every update that moves vehicles
MUST make sender limits, receiver limits, and any shared budgets explicit in
code or an attached contract, and outflow MUST never exceed physically
available mass.

### III. Deterministic Replay and Auditability
Equivalent inputs, seeds, schedules, and journals MUST produce equivalent
outcomes. Hidden mutation, leaked state across runs, iteration-order
dependence, and implicit randomness are forbidden. Every nontrivial update path
MUST be inspectable through tests, logs, or replay artifacts sufficient to
explain state transitions.

### IV. Explicit Time-Step and Units Discipline
Every evolving quantity MUST state whether it is stored as a stock, per-tick
increment, or per-unit-time rate, and MUST name its units. `dt` handling MUST
be explicit at the update site. Any conversion between rates and increments
MUST be documented and regression tested, especially across multirate
boundaries.

### V. Regression-First Testing
Every repaired failure mode MUST get a targeted regression test before broad
suite runs. Smoke tests do not count as validation for contracts, dynamics,
replay, cache invalidation, or feedback loops. Dynamics work MUST include
baseline reproduction plus edge and adversarial cases. Narrow tests MUST run
before scenario suites, benchmarks, or city-scale runs.

### VI. Small Reversible Patches
Changes MUST be minimal, scoped, and easy to back out. Large refactors,
framework extraction, or architecture redesign are prohibited unless a contract
hole or replay failure makes them unavoidable and the justification is written
in the active plan. Diffs MUST stay scoped to the active feature and MUST not
mix cleanup with behavioral change.

### VII. No Same-Tick Positive Feedback
Accessibility, routing, demand, land-use, and policy feedback loops MUST
respect explicit lag structure. Same-tick closures that feed updated travel
conditions back into generation, relocation, or policy in the same step are
forbidden unless the mechanism is modeled explicitly, justified in the spec,
and covered by stability tests.

### VIII. Documentation Synchronization
When a code-level contract, invariant, validation rule, scheduler rule, or
cache invalidation rule changes, the relevant spec, repair note, contract doc,
or benchmark note MUST be updated in the same workstream. Drift between code,
plan, tasks, tests, and docs is a defect.

## Operational Boundaries

- `S2` work MUST land before `S1` expansion.
- `WorldState` is immutable by default.
- Baseline fallback is mandatory for routing, policy, or learning logic.
- External-data learning is prohibited in baseline work.
- The multirate scheduler is mandatory.
- Cache invalidation rules MUST be documented where caches are introduced or
  changed.
- The viewer or visualization loop MUST not block the simulation core loop.
- The following stay out of default scope unless amended explicitly:
  lane-level microscopic defaults, RL or LLM-first route choice, ECS or
  plugin-first architecture, distributed multi-GPU execution, and full generic
  frameworkization.

## Review and Delivery Gates

Every plan, task set, review, and merge request MUST answer these checks
explicitly:

- Contract impact
- Time-scale impact
- Cache invalidation impact
- Replay and regression impact
- Benchmark impact

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

- Amendments MUST update this file, include a reason, and update affected
  templates or guidance docs in the same change.
- Versioning follows semantic intent: `MAJOR` for removed or materially weakened
  principles, `MINOR` for new principles or new mandatory gates, `PATCH` for
  clarifications that do not change enforcement.
- Compliance review is mandatory in planning and code review.
- Any temporary waiver MUST name the violated principle, the narrow scope, the
  risk accepted, the fallback, and the removal condition.

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

**Version**: [CONSTITUTION_VERSION] | **Ratified**: [RATIFICATION_DATE] | **Last Amended**: [LAST_AMENDED_DATE]
