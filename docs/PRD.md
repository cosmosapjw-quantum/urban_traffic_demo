# PRD — 도시교통 시뮬레이터

## 제품 정의
인구 약 100,000명 규모의 도시를 대상으로,
도시 생성–교통–접근성–도시발전–행동/학습을 결합한 설명 가능한 시뮬레이터를 만든다.

## 문제
기존 city-builder 교통 AI의 문제:
- deterministic shortest path 고착
- bypass 효과 미약
- bridge/IC/arterial 병목 반복
- 교통 변화가 도시발전에 거의 반영되지 않음
- 도시 구조 변화가 수요 구조를 제대로 바꾸지 못함

## 목표
- persistent citizen 유지
- bulk transport는 mesoscopic core
- generalized-cost routing
- candidate path K + path-size correction
- event-triggered reroute
- weekday/weekend + AM/PM 수요 패턴
- lagged accessibility-based land-use feedback
- navigator-style UI

## In-scope
- shape + LUTI + project-authored modular road-section grammar 지도 생성
- link/node 기반 mesoscopic traffic
- zonal accessibility cache
- slow land-use feedback
- EMA/bandit 기반 online adaptation
- 실시간/준실시간 observability UI

## Out-of-scope (v1)
- lane-level microscopic default
- full public transit assignment
- parking micro
- RL/LLM-first
- distributed multi-GPU
- full generic ECS/plugin framework

## 성공 기준
- bridge/IC bottleneck 재현
- bypass 추가 시 초기 완화 + 이후 일부 induced-demand 방향성
- weekday/weekend, AM/PM 차이 재현
- replay determinism
- stale cache 없음
- same-tick positive feedback 없음
