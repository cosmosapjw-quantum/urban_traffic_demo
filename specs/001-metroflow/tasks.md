# Tasks: 001 MetroFlow Baseline

**Input**: Design documents from `/specs/001-metroflow/`  
**Prerequisites**: `spec.md`, `plan.md`, `contracts/`

## Execution Rules

- `S2` foundation tasks must complete before `S1` baseline expansion.
- Every task must map to one or more requirements from `spec.md`.
- Every task must include a validation command.
- Narrow regression commands run before the full suite.
- Persistent citizens and visualization remain deferred and must not be pulled
  into `001`.

## Format: `[ID] [P?] Description`

## Phase 1: Contracts and S2 Foundation

- [X] T001 Define immutable `WorldState` in `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/metroflow/core/state.py` and `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/tests/test_state_contracts.py`
- [X] T002 Implement unit and invariant validation in `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/metroflow/core/contracts.py`, `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/metroflow/core/units.py`, and `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/tests/test_state_contracts.py`
- [X] T003 Implement multirate scheduler in `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/metroflow/sim/scheduler.py` and `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/tests/test_scheduler.py`
- [X] T004 Implement cache invalidation API in `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/metroflow/core/cache.py`, `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/metroflow/core/state.py`, and `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/tests/test_state_contracts.py`
- [X] T005 Implement deterministic replay-input fingerprint surface in `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/metroflow/sim/replay.py`, `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/metroflow/metrics/benchmarks.py`, and `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/tests/test_replay.py`

## Phase 2: Demand Schedules

- [X] T006 Implement weekday / weekend and time-of-day schedule baseline in `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/metroflow/demand/schedules.py`, `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/metroflow/demand/trip_generation.py`, and `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/tests/test_demand_schedules.py`

## Phase 3: Traffic and Routing Baseline

- [X] T101 Implement mesoscopic edge and node baseline in `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/metroflow/traffic/meso.py` and `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/tests/test_meso_core.py`
- [X] T102 Implement generalized-cost routing and candidate path K in `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/metroflow/traffic/routing.py` and `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/tests/test_routing.py`
- [X] T103 Implement path-size correction and event-triggered reroute fallback in `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/metroflow/traffic/routing.py` and `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/tests/test_routing.py`

## Phase 4: Accessibility and Lagged Land-Use

- [X] T104 Implement accessibility cache and invalidation hooks in `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/metroflow/demand/accessibility.py` and `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/tests/test_accessibility.py`
- [X] T105 Implement lagged land-use feedback in `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/metroflow/landuse/evolution.py` and `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/tests/test_landuse_feedback.py`

## Phase 5: Scenario and Benchmark Validation

- [X] T106 Add bridge / merge / bypass toy scenario regressions in `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/tests/test_meso_scenarios.py`
- [X] T107 Add city100k-like smoke benchmark proxy coverage in `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/metroflow/metrics/benchmarks.py` and `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/tests/test_benchmarks.py`
- [X] T108 Run narrow regression commands in the exact validation order defined in `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/specs/001-metroflow/plan.md`
- [X] T109 Run the full pytest suite and ruff on `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/src/` and `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo/tests/`

## Deferred Work (Out of 001 Scope)

- [ ] T201 Persistent citizen life-cycle table and behavior model
- [ ] T202 Visualization / observability viewer
- [ ] T203 EMA memory
- [ ] T204 OD-path bandit
- [ ] T205 Lane grammar compiler
- [ ] T206 Node compiler
- [ ] T207 Optional neural plugin

## Dependencies

- T001 -> T002 -> T003 -> T004 -> T005
- T005 -> T006
- T003 + T006 -> T101
- T101 -> T102 -> T103
- T004 + T006 -> T104
- T104 -> T105
- T101 + T103 -> T106
- T005 + T106 -> T107
- T001..T107 -> T108 -> T109

## Validation Order

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

## Task Details

### T001

- Covers: `FR-001`, `CR-001`
- Deliverable: immutable world tree plus versioned state sections
- Validation:
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_state_contracts.py`

### T002

- Covers: `FR-002`, `CR-001`, `DR-001`
- Deliverable: explicit unit, range, and invariant validation
- Validation:
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_state_contracts.py`

### T003

- Covers: `FR-003`, `CR-002`, `DR-002`, `DR-005`
- Deliverable: cadence helpers plus forbidden same-tick coupling guards
- Validation:
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_scheduler.py`

### T004

- Covers: `FR-004`, `CR-004`
- Deliverable: explicit graph / land-use / policy invalidation helpers
- Validation:
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_state_contracts.py`

### T005

- Covers: `FR-005`, `CR-005`, `SC-002`
- Deliverable: replay-input fingerprint record / journal surface and deterministic smoke benchmark without transition reconstruction
- Validation:
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_replay.py`

### T006

- Covers: `FR-006`, `SC-003`
- Deliverable: deterministic weekday / weekend and time-of-day demand schedule baseline
- Validation:
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_demand_schedules.py`

### T101

- Covers: `FR-007`, `DR-003`, `SC-004`
- Deliverable: mesoscopic traffic baseline with conservation and non-negativity
- Validation:
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_meso_core.py`

### T102

- Covers: `FR-008`, `CR-003`, `DR-004`
- Deliverable: generalized cost and candidate path K baseline
- Validation:
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_routing.py`

### T103

- Covers: `FR-008`, `CR-003`
- Deliverable: path-size correction and deterministic reroute fallback
- Validation:
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_routing.py`

### T104

- Covers: `FR-009`, `CR-004`
- Deliverable: accessibility cache with explicit invalidation hooks
- Validation:
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_accessibility.py`

### T105

- Covers: `FR-009`, `DR-005`, `SC-004`
- Deliverable: lagged accessibility-based land-use feedback only
- Validation:
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_landuse_feedback.py`

### T106

- Covers: `FR-010`, `SC-004`, `SC-005`
- Deliverable: bridge / merge / bypass toy scenario regressions
- Validation:
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_meso_scenarios.py`

### T107

- Covers: `FR-010`, `SC-005`
- Deliverable: city100k-like benchmark record with deterministic proxy scores populated
- Validation:
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_benchmarks.py`

### T108

- Covers: `NFR-001`
- Deliverable: recorded narrow-to-broad validation execution
- Validation: run commands 1-10 from `Validation Order`

### T109

- Covers: `NFR-001`, `NFR-003`, `NFR-004`
- Deliverable: final pytest + ruff pass for `001`
- Validation:
  `PYTHONPATH=src .venv/bin/python -m pytest -q && PYTHONPATH=src .venv/bin/python -m ruff check src tests`
