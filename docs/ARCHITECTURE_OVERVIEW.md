# Architecture Overview

## 3층 분리
1. Spatial / World Layer
   - graph, lane grammar, zones, node compiler
2. Dynamics Layer
   - traffic core, routing, accessibility, land-use, scheduler
3. Interface Layer
   - metrics, logging, replay, visualization

## 핵심 모듈
- core/
  - state, contracts, units, cache, journal
- map/
  - generator, lane_grammar, node_compiler
- demand/
  - citizens, schedules, trip_generation, accessibility
- traffic/
  - meso, routing, incidents
- landuse/
  - evolution
- policy/
  - archetypes, ema, bandit, optional neural plugin
- sim/
  - scheduler, replay, orchestrator
- metrics/
  - observables, benchmarks
- viz/
  - viewer adapter

## 핵심 원칙
- bulk transport와 behavior closure 분리
- WorldState에서만 상태 이동
- 모든 느린 feedback은 lagged
- cache는 versioned
- viewer는 core loop를 막지 않음
