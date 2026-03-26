# Detailed Tasks — 001 MetroFlow

## Ordering
S2 first, then S1, then demand/policy/map expansion.

## T001 WorldState
- Add dataclasses for each state section
- Add `make_empty_world_state()`
- Add `with_version_bump(...)`

## T002 Units/Contracts
- Add UnitsConfig
- Add SimulationConfig
- Add `validate_time_scale_separation(config)`
- Add `validate_state_contract(world)`

## T003 Scheduler
- Add `TickSchedule`
- Add `SchedulerDecision`
- Add `scheduler_decision(step_idx, schedule)`

## T004 Cache
- Add `CacheRegistry`
- Add invalidation functions:
  - `invalidate_on_graph_edit`
  - `invalidate_on_landuse_edit`
  - `invalidate_on_policy_edit`

## T005 Replay
- Add `InterventionJournal`
- Add `ReplayRecord`
- Add benchmark helper

## T101 Meso baseline
- Add `EdgeDynamicState`
- Add queue/stock update helpers
- Add safe travel-time calculator

## T102 Node projection
- Add `compute_sending_receiving`
- Add `project_feasible_movements`
- Add conservation check

## T103 Routing baseline
- Add `CandidatePath`
- Add `GeneralizedCostWeights`
- Add `path_size_factor`
- Add generalized cost aggregation

## T104 Reroute
- Add `ReroutePolicy`
- Add `should_reroute(...)`
- Add refractory timer logic

## T105 Accessibility
- Add `AccessibilitySnapshot`
- Add zonal skim placeholder
- Add lagged cache handling

## T106 Land-use
- Add `LandUseState`
- Add lagged feedback update placeholder
- Add no same-tick closure guard

## Minimal exit criteria
- T001~T005 all green
- T101~T104 all green
- T105/T106 smoke green
