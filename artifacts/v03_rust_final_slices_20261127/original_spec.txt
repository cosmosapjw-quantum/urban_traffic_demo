# Feature Spec — 001 MetroFlow

## Summary
100k급 도시에서 도시발전-교통 상호작용을 설명 가능하게 시뮬레이션하는 엔진.

## Functional requirements
- persistent citizens
- mesoscopic traffic core
- generalized-cost routing
- candidate path K + path-size correction
- event-triggered reroute
- weekday/weekend + time-of-day demand
- lagged accessibility-based land-use feedback
- navigator-style visualization

## Non-functional requirements
- deterministic replay
- cache correctness
- scalable on single machine
- JAX-friendly pure core

## Acceptance criteria
- bridge/IC bottleneck reproduced
- bypass / induced-demand directionality reproduced
- weekday/weekend patterns differ
- no same-tick feedback explosion
- replay passes
