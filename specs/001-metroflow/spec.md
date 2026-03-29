# Feature Specification: 001 MetroFlow Baseline

## Summary

Build the first implementable MetroFlow baseline for a 100k-scale synthetic city.
`001` delivers the S2 foundation plus the minimum S1 traffic, routing, demand
schedule, accessibility, land-use, replay, and benchmark surfaces required to
start implementation safely under the project constitution.

## Problem Statement

The current `001` artifacts describe the intended simulator at a high level, but
they are not yet precise enough to guide implementation deterministically. The
gaps are:

- public contracts are named but not fully specified;
- acceptance criteria are not measurable enough for review;
- weekday/weekend and time-of-day demand coverage is underspecified;
- the task list is too abstract to support safe execution ordering.

This remediation narrows `001` to the executable baseline needed before any
broader realism, UI, or learning work.

## Authority

The authoritative chain for `001` is:

1. `.specify/memory/constitution.md`
2. this feature specification
3. `specs/001-metroflow/plan.md`
4. `specs/001-metroflow/tasks.md`
5. `specs/001-metroflow/contracts/`

## In-Scope Behavior

- Immutable `WorldState` plus explicit versioned cache state.
- Contract validation for world state, scheduler, routing, accessibility /
  land-use, and replay surfaces.
- Multirate scheduler with explicit fast, medium, and slow cadence separation.
- Cache invalidation for graph, accessibility / land-use, and policy dependent
  state.
- Deterministic replay-input fingerprint record and smoke benchmark over seed +
  intervention journal + declared observation inputs; this surface does not
  reconstruct simulator transitions.
- Weekday / weekend plus time-of-day demand schedules with testable
  differentiation.
- Mesoscopic link / node baseline with conservation, non-negativity, and
  capacity / storage respect.
- Generalized-cost routing with candidate path K, path-size correction, and
  event-triggered reroute with deterministic baseline fallback.
- Accessibility cache and lagged land-use feedback with no same-tick closure.
- Toy traffic scenarios for bridge, merge, and bypass directionality.
- City100k-like synthetic smoke benchmark that records deterministic proxy
  scores rather than measured runtime or memory.

## Out-of-Scope Behavior

- Persistent citizen life-cycle simulation beyond aggregate demand schedules.
- Navigator-style visualization or any other UI / viewer deliverable.
- Lane-level microscopic default.
- RL-first or LLM-first route choice.
- EMA / bandit / neural learning policy work.
- Lane grammar and node compiler implementation.
- Distributed or multi-GPU execution.
- Full framework extraction or plugin-first redesign.

## User Stories

### User Story 1 - Establish the S2 Safety Envelope

As a maintainer, I need immutable world state, explicit contracts, cache
invalidation, and deterministic replay so the baseline can be changed without
silent state drift.

### User Story 2 - Run a Conservative Traffic and Routing Baseline

As a maintainer, I need a mesoscopic traffic core and generalized-cost routing
baseline so bridge / merge / bypass scenarios can be exercised with explicit
conservation guarantees.

### User Story 3 - Exercise Demand and Lagged Feedback Safely

As a maintainer, I need weekday / weekend and time-of-day demand schedules plus
lagged accessibility-based land-use feedback so the simulator captures temporal
variation without same-tick feedback loops.

## Functional Requirements

- **FR-001**: The feature MUST define an immutable `WorldState` contract with
  explicit section ownership, admissible state shapes, materialized graph
  metadata for non-empty graphs, and versioned cache fields.
- **FR-002**: The feature MUST define contract validation for state shape,
  units, invariants, and failure conditions before downstream logic relies on
  them.
- **FR-003**: The feature MUST provide a multirate scheduler with explicit
  fast, medium, and slow cadence semantics and forbidden same-tick couplings.
- **FR-004**: The feature MUST document and implement cache invalidation rules
  for graph edits, accessibility / land-use dependent state, and policy edits.
- **FR-005**: The feature MUST provide a deterministic replay-input
  fingerprint surface and smoke benchmark using a seed, ordered intervention
  journal, and declared observation payload without claiming simulator
  transition reconstruction.
- **FR-006**: The feature MUST provide weekday / weekend and time-of-day demand
  schedules with deterministic baseline schedule generation.
- **FR-007**: The feature MUST provide a mesoscopic traffic baseline with
  non-negativity, conservation, capacity respect, and storage respect.
- **FR-008**: The feature MUST provide generalized-cost routing with candidate
  path K, path-size correction, and event-triggered reroute while preserving a
  deterministic non-learning fallback.
- **FR-009**: The feature MUST provide accessibility caching and lagged
  land-use feedback that reads only lagged accessibility inputs.
- **FR-010**: The feature MUST provide toy scenario validation for bridge,
  merge, and bypass directionality plus a city100k-like smoke benchmark.

## Non-Functional Requirements

- **NFR-001**: Validation must proceed from narrow targeted regressions to the
  full suite; broad green results alone are insufficient.
- **NFR-002**: Every public contract changed by `001` must declare inputs,
  outputs, units, admissible ranges, invariants, and failure conditions in the
  corresponding contract doc.
- **NFR-003**: All baseline execution paths must remain deterministic for
  equivalent inputs, seeds, schedules, and journals.
- **NFR-004**: The `001` implementation must remain a small reversible patch set
  and must not expand into UI, learning, or map-compiler work.

## Contract Requirements

- **CR-001**: `contracts/WORLD_STATE_CONTRACT.md` MUST define the state surface,
  units, versions, invariants, and failure conditions for `WorldState`.
- **CR-002**: `contracts/SCHEDULER_CONTRACT.md` MUST define scheduler inputs,
  cadence semantics, outputs, forbidden same-tick coupling, and failure
  conditions.
- **CR-003**: `contracts/ROUTING_CONTRACT.md` MUST define generalized cost,
  candidate path, reroute, baseline fallback, and routing failure conditions.
- **CR-004**: `contracts/ACCESSIBILITY_LANDUSE_CONTRACT.md` MUST define cache
  invalidation rules, lagged input rules, and accessibility / land-use
  interface boundaries.
- **CR-005**: `contracts/REPLAY_CONTRACT.md` MUST define replay-input
  fingerprint inputs, outputs, determinism expectations, non-goals, and
  failure conditions.

## Dynamics, Time, and Conservation Requirements

- **DR-001**: Every evolving quantity in `001` MUST state whether it is a stock,
  per-tick increment, or per-unit-time rate.
- **DR-002**: Scheduler cadence is measured in integer ticks; demand schedules
  produce deterministic multipliers over those ticks.
- **DR-003**: Traffic stock and queue quantities are vehicle counts; sending,
  receiving, and movement flows are vehicles per tick.
- **DR-004**: Generalized routing cost is expressed in time units and remains
  compatible with deterministic baseline routing.
- **DR-005**: Accessibility and land-use feedback MUST remain lagged; same-tick
  travel conditions MUST not directly trigger same-tick relocation or
  redevelopment.

## Success Criteria

- **SC-001**: `WorldState`, scheduler, cache invalidation, and replay contract
  regressions reject all invalid fixture states used in the narrow test suite.
- **SC-002**: 100% of replay-input fingerprint smoke fixtures produce identical
  fingerprints across duplicate runs with equivalent seed, intervention
  journal, and declared observation inputs.
- **SC-003**: Demand schedule regressions show at least one weekday / weekend
  difference and at least two distinct time-of-day demand peaks in deterministic
  fixtures.
- **SC-004**: 100% of accepted mesoscopic toy-suite updates preserve
  non-negativity, capacity / storage respect, and no same-tick
  accessibility-to-land-use closure.
- **SC-005**: Bridge, merge, and bypass scenario regressions pass, and the
  city100k-like smoke benchmark emits a benchmark record with populated
  deterministic proxy-score fields.

## Validation and Regression Plan

Run the narrow validation sequence in this exact order before the full suite:

1. `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_state_contracts.py`
2. `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_scheduler.py`
3. `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_replay.py`
4. `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_demand_schedules.py`
5. `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_meso_core.py`
6. `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_routing.py`
7. `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_accessibility.py`
8. `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_landuse_feedback.py`
9. `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_meso_scenarios.py`
10. `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_benchmarks.py`
11. `PYTHONPATH=src .venv/bin/python -m pytest -q`
12. `PYTHONPATH=src .venv/bin/python -m ruff check src tests`

## Non-Goals

- `001` does not implement persistent citizens.
- `001` does not implement navigator-style visualization.
- `001` does not implement learning policy modules, lane grammar, or node
  compiler work.
