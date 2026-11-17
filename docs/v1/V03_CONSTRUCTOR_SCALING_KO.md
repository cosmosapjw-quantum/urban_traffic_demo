# V03 calendar 준비 비용의 정확한 제거

2026-11-16, 비교 원본 `b41f807c490dda12e036bcb40d9c13370f04223e`의
`ReleaseRuntime` constructor를 대상으로 했다. V03 입력·20,000-leg 예산과
공유 도로 수송의 의미는 유지한다. 이 결과는 V03 전체 도시의 24시간 수용이 아니다.

## 직접 확인한 병목

기존 constructor는 각 leg에 대해 전체 calendar의 ID 집합을 다시 만들고,
귀가 leg마다 부모를 처음부터 순회했다. L개 leg의 부모 검증에 Θ(L²)의
ID 접근이 필요했다. 실제 100-leg 내부 이동/귀가 fixture에서 ID 접근은
13,000회였고, 선형 상한 2,000회를 요구한 회귀 검사가 실패했다.

고유성 검증에도 사용하는 `indices`를 최초 한 번 구축하고 부모를 그
index로 읽도록 고쳤다. 부모 ID·cohort·amounts·부모의 선행 의존성에 대한
기존 검증식은 같다. 같은 fixture에서 ID 접근은 400회이고 model identity가
같다. 검증의 시간복잡도는 Θ(L), 추가 보유량은 기존 indices와 같은 O(L)이다.

동일 endpoint 20개 car leg의 원래 route search는 20회, access 계산은 40회였다.
두 번째 회귀는 이를 실제 계산 함수에 위임하면서 호출 횟수만 세어 검출했다.
고정 city/contract/cost 안에서 endpoint node pair의 원래 route 결과를
최대 1,024개, 완전한 `ActivityMeasure`와 `PortalRef`의 access law를 최대
128개 공유한다. 캐시는 constructor에 한정되며 퇴거 시 같은 함수를 다시 계산한다.
동일 block ID라도 활동 분포·기하·가중치가 다르면 별도 key다. 0 크기는 캐시를
끄며, 캐시 크기 1로 퇴거가 일어나는 경우와 함께 완전한 상태 동등성을 검사했다.

route solver는 원래 `candidate_paths`를 그대로 사용한다. 따라서 physical-node
loopless 조건, expansion budget, 동률 순서가 유지된다. legal link-state Dijkstra로
바꾸면 노드 재방문과 제한 초과의 의미가 달라질 수 있으므로 이 변경에 포함하지 않았다.
시간 계측은 캐시 바깥의 요청 경계에 연결되어 hit도 관측한다.

## 실제 검산

`artifacts/v1_v03_constructor_20261116/benchmark.py`는 pinned constructor 원문을
Git에서 불러와 현재와 같은 공통 의존성 위에서 비교한다. 각 fixture는 3회씩
기존/개선 순서를 번갈아 측정했다. process RSS나 100k 지도에 대한 외삽은 하지 않는다.

| fixture | leg 수 | 원래 평균 wall [s] | 개선 평균 wall [s] |
|---|---:|---:|---:|
| 내부 이동과 귀가 | 4,000 | 0.446653 | 0.011899 |
| 같은 실제 출입구를 공유하는 car | 256 | 0.305637 | 0.007010 |

매 쌍에서 model identity, 모든 route, boundary, internal law가 정확히 같았다.
256-car fixture의 search/access 호출은 256/512회에서 1/2회로 줄었다.
별도의 실제 공유 도로 왕복 120초 실행에서 전체 상태와 report가 정확히 같았고,
왕복 각 1 veh가 완료됐다. raw 값과 source SHA는 같은 디렉터리의 `RESULT.json`에 있다.

Python 3.12와 3.13 각각 `tests/v1/test_release_runtime.py`의 10개 테스트가 통과했다.
변경 소스·테스트·benchmark에 대한 Ruff도 통과했다. 전체 CI는 사용자 지시에 따라
보류한다. 대규모 calendar의 eager 보유량, active record 수, 전체 tick 비용 및
실제 세 도시×3회 캠페인은 별도 의무로 남는다. DAG 완료는 19/21(90.5%)다.
