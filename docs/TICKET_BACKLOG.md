# Ticket Backlog (Detailed)

## Epic S2 — State / Contract / Scheduler
### T001 — Define immutable WorldState
목표:
- 시뮬 상태를 단일 immutable tree로 통일

수정 파일:
- `src/metroflow/core/state.py`
- `tests/test_state_contracts.py`

완료 조건:
- WorldState dataclass 정의
- section별 state(graph, traffic, demand, accessibility, landuse, policy, replay) 포함
- test: state 생성 가능, replace 기반 갱신 가능

### T002 — Define units and contracts
목표:
- 단위와 금지 coupling 명시

수정 파일:
- `src/metroflow/core/contracts.py`
- `src/metroflow/core/units.py`
- `tests/test_state_contracts.py`

완료 조건:
- UnitsConfig, SimulationConfig 정의
- forbidden same-tick feedback rule 문서화/검증 함수 제공

### T003 — Implement multirate scheduler
수정 파일:
- `src/metroflow/sim/scheduler.py`
- `tests/test_scheduler.py`

완료 조건:
- fast/medium/slow cadence
- should_run_fast/medium/slow 유틸
- step partitioning 테스트

### T004 — Cache invalidation API
수정 파일:
- `src/metroflow/core/cache.py`
- `src/metroflow/core/state.py`
- `tests/test_state_contracts.py`

완료 조건:
- graph/landuse/policy version bump
- accessibility/route cache invalidation helpers
- stale cache 방지 테스트

### T005 — Replay benchmark
수정 파일:
- `src/metroflow/sim/replay.py`
- `src/metroflow/metrics/benchmarks.py`
- `tests/test_replay.py`

완료 조건:
- seed + intervention journal 기반 replay 가능
- deterministic replay smoke benchmark

## Epic S1 — Mesoscopic Core
### T101 — Baseline mesoscopic edge state
수정 파일:
- `src/metroflow/traffic/meso.py`
- `tests/test_meso_core.py`

완료 조건:
- edge queue/stock/travel_time state
- non-negativity helpers
- one-step edge update smoke

### T102 — Node feasible flow projection
수정 파일:
- `src/metroflow/traffic/meso.py`
- `tests/test_meso_core.py`

완료 조건:
- sending / receiving / movement capacity 기반 projection
- conservation test

### T103 — Generalized-cost routing state
수정 파일:
- `src/metroflow/traffic/routing.py`
- `tests/test_routing.py`

완료 조건:
- link generalized cost
- candidate path structure
- path-size factor util

### T104 — Event-triggered reroute
수정 파일:
- `src/metroflow/traffic/routing.py`
- `tests/test_routing.py`

완료 조건:
- hard event trigger
- ETA degradation trigger
- refractory window test

### T105 — Accessibility cache
수정 파일:
- `src/metroflow/demand/accessibility.py`
- `tests/test_accessibility.py`

완료 조건:
- zonal skim cache
- invalidation hooks
- lagged accessibility storage

### T106 — Lagged land-use feedback
수정 파일:
- `src/metroflow/landuse/evolution.py`
- `tests/test_landuse_feedback.py`

완료 조건:
- lagged input only
- no same-tick relocation feedback
- stability smoke

## Epic Demand / Policy / Map
### T201 — Citizen table and schedules
### T202 — Trip spawning and active-pool allocation
### T203 — EMA perceived-cost updates
### T204 — OD-path bandit baseline
### T301 — Lane grammar skeleton
### T302 — Node compiler skeleton
