# 최종 감사와 로컬 100000주민 목표의 다음 경계

이번 결과는 terrain/environment compiler와 population-driven demand의 연결이다. 기존 도시 형태/active-meso 연구를 삭제하지 않고, coarse-grid fixture로 환경 제약을 분리 시험했다. 지도 지형은 합성이고 실제 DEM/OSM/지가/인구자료를 사용하지 않았다. Cities: Skylines의 그래픽/기능/성능을 재현하거나 해당 게임보다 우월하다는 측정은 없다.

## 실제 발견과 처리
1. 교량으로 강을 건너도 hill의 급경사 때문에 다른 고립 노드가 남았다. 전역 연결성을 억지로 만들지 않았다. 교량의 효과는 flat-height fixture에서 분리 검증하고, 원 지형의 component는 보고한다. 가장 큰 component 밖의 구역은 도시 stock 배치에서 배제한다.
2. 최초 산업 buffer는 지정 region의 중심경계를 썼고 실제 산업 cell이 더 튀어나왔다. 인접 주거가 buffer를 침범하는 공개 반례를 먼저 재현해 cell footprint 기준으로 고쳤다.
3. OD의 모든 행/열에 이웃이 있어도 일자리 support가 부족할 수 있다. 9/1 worker,5/5jobs 반례를 max-flow feasibility로 거절한다. 일자리 총수를 임의로 맞추거나 IPF 미수렴을 PASS로 바꾸지 않았다.
4. Population을 바로 traffic demand로 취급하지 않는다. 출근 participation/mode/occupancy/시간 profile을 명시한다. 未방출/외부pending/active/completed/local-unresolved/noncar를 별도 ledger로 기록한다.
5. Signal/terrain 조건과 budget failure를 실제 solver로 확인했다. event_budget=1에서 마지막 유효 tick0을 보존하고 BLOCKED_RESOURCE로 끝난다. 이것을 물리 gridlock이나 차량 소실로 부르지 않는다.
6. 같은100k stocks에서 district 해상도를 바꾸면 OD가 달라졌다. 4/11/14districts일 때 unresolved local은2475.915669/1299.959032/791.194706veh다. network는4564.084331/5740.040968/6248.805294veh이며 합은항상7040. 큰 zone으로 계산을 줄이면서 도로 수요가 줄어드는 효과를 숨기지 않는다. 이 sensitivity는 수렴 판정이 아니다.
7. Static Braess oracle65→80min을 다시 확인했다. 이 재사용 검사는 동적 도시의 UE 또는 모든 신규도로의 Braess 성질을 증명하지 않는다.

## 검증과 독립성
최종: 새 environment26tests + 첨부 parent-reference suffix12tests =38passed. 원격 branch에서 환경시험만 실행하면26passed다. 감사4tests는 구현 후 추가한 regression이며 TDD였다고 부르지 않는다. Terrain5/stock5/buffer1/demand6/adapter1의 최초RED가 로그에 있고, 각 수정의GREEN이 보존돼 있다. Python3.13.5, stdlib-only scientific execution/compileall/소스 의존성 검사. native_subagent NOT_RUN, 동일 구현자의 직렬검증+Wolfram+수학반례이며 독립 모델심사가 아니다.

전체 저장소 CI, Python3.12, local CPU/RAM benchmark는 NOT_RUN. 100000주민에는 planning과300s short traffic probe만 했다. 단기probe walltime으로 전일 실행시간을 외삽하지 않는다. 전체 도시의100000명 서로 다른 개인 이력도 생성하지 않는다. 그래픽은 요청에 따라 실행하지 않았다.

## 진행 DAG와 수용조건
E1 terrain->roads: PASS_SCOPED. 수계/보호구역 continuous intersection, explicit bridge, grade, isolation 기록.
E2 environment->stocks: PASS_SCOPED. 면적 accounting, housing/jobs capacity와 정확한 총수.
T1 stocks->OD/time profile: PASS_SCOPED. 양방향 margin/structural zeros/person-vehicle/local ledger.
T2 OD->active_suffix: PASS_SCOPED. 소도시clearance,100k짧은probe,보존·저장량·물리적지연·계산한도.

다음 순서:
N1. 기존 비격자 도시형태와 지형 compiler를 연결. 임의 centerline의 연속 경사/수계 gate, bridge envelope, access connector가 땅/물을 가로지르는지 검사. 임의 connectivity fallback 금지.
N2. local trips와 access/egress를 해상하는 집계 connector. 4/11/14district sensitivity를 줄이는지 matched demand로 검사. 병목을 없애려고 교통량을 축소하지 않는다.
N3. 출근-귀가와 shopping/school/service/freight의 집단 스케줄. 목적별 출발지·도착지 stock/시간 budget을 닫고 noncar를 구별한다. 인구=차량으로 두지 않는다.
N4. 생성된 신호의 phase, 유한turn storage, 수단별/행동별 class를 작은 반례부터 추가. active matter/mesoscopic collision-informed routing과 Braess 가능성을 유지한다.
N5. 로컬 전일100k주민 benchmark. 동일 city/day inputs, CPU core/RAM/버전고정, tick latency p50/p95,peakRSS,live suffix/event growth,수요clearance,정밀도/시간간격 trade-off를 기록한다. sandbox는 매 변경의 작은 회귀만 수행한다.
N6. 공개 대조 시나리오와 관측/미시 참조로 realism/비현실적폐색/순환/teleport를 검증한 후에만 게임보다낫다는 주장 검토. 본연구의 목표이지 완료판정이 아니다.

Slow terrain/landuse version 변경은 새 frozen city와 plan으로 경계를 만든다. 도로 ID hot-swap이나 이동 중 stock의 강제재배치를 허용하지 않는다. Future cache는 graph/zoning/profile version으로 invalidation하며 현재는 매 plan을 새로 계산한다.
