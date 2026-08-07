# TDD + SDD MASTER SPEC

## 최종 통합 수학·물리 모델

교통 수요, 링크/노드 흐름, 경로 선택, 재탐색, 접근성, 토지이용,
제한적 온라인 적응을 하나의 규범적 모델로 연결한 문서는
[`TRAFFIC_SIMULATION_FINAL_MODEL_SPEC.md`](TRAFFIC_SIMULATION_FINAL_MODEL_SPEC.md)다.
이 문서는 코드 구현 현황이 아니라 기능별 최종 스펙을 통합한 목표 구현
규격이며, 헌법과 기능별 focused spec/contract가 충돌 시 우선한다.

## 문서 우선(SDD) 순서
1. spec
2. plan
3. tasks
4. implement
5. tests / benchmarks
6. observables 반영

## 테스트 우선(TDD) 계층
- Unit tests
- Invariant tests
- Scenario tests
- Replay tests
- Performance tests

## Definition of Done

### S2 완료 조건
- immutable WorldState
- explicit unit conventions
- multirate scheduler
- cache invalidation tests pass
- deterministic replay benchmark pass

### S1 완료 조건
- link/node mesoscopic core
- generalized-cost routing
- bridge/corridor/bypass toy benchmarks pass
- lagged land-use feedback scenario stable
- no negative queue / no obvious oscillatory blowup

### Learning v1 완료 조건
- EMA/bandit update implemented
- baseline 대비 non-degradation
- fallback verified

## Kill criteria
- S2: cache/replay correctness를 맞추지 못하면 state layout 재설계
- S1: corridor/merge/bypass gold suite도 못 맞추면 core 단순화 후 재구축
- Learning: baseline보다 계속 나쁘면 비활성화
