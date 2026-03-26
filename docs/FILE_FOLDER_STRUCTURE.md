# File / Folder Structure Design

## 권장 트리
repo/
- AGENTS.md
- README.md
- docs/
- memory/
- specs/
- src/metroflow/
  - core/
  - map/
  - demand/
  - traffic/
  - landuse/
  - policy/
  - sim/
  - metrics/
  - viz/
- tests/
- bench/
- tools/

## 모듈 책임
- core/: state, contracts, cache, journal
- map/: graph generator, lane grammar, node compiler
- demand/: citizens, schedules, trip generation, accessibility
- traffic/: meso, routing, incidents
- landuse/: evolution
- policy/: ema, bandit, optional neural policy
- sim/: scheduler, replay, orchestration
- metrics/: observables, benchmark calculators
- viz/: streaming/view model/UI
