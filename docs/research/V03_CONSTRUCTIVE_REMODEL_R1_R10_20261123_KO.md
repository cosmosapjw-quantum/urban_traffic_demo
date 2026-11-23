# MetroFlow 구성적 재모델링·실행 연구 — R1–R10 / C1–C10

## R1 / C1 — 원 목적·현재 실패·새 모델링 범위 (완료)

이번 사용자는 직전10단계 종료 커밋 `90bfca2c2ddf081cbdf40d11b95ff820837d03b5` 이후의 새 이론/코딩 결합10단계를 명시적으로 요청했다. 기준 local HEAD와 원격 branch의 동일성을 확인했고, 추적 파일이 깨끗한 상태에서 `research/v03-constructive-remodel-20261123` 작업공간을 분리했다. 이전 루프의 종료는 그대로 보존하며 이번 요청을 그 루프의 미완료나 자동 재시작으로 해석하지 않는다.

현재 사용자 승인은 원 목적과 직관을 유지하면서 새 모델을 적극적으로 탐색·구현·연구 코드에 통합하는 범위까지 포함한다. 새 모델의 보존량·FIFO/인과성·관측량 대응, 실수 산술 동치와 f64/wire 동일성, 근사의 오차를 구분한다. 현 V03의 원 수요·matrix·dt·cap·수용문턱을 모르게 바꾸지 않는다. 기존 main 통합·release tag·전체 repository CI 보류는 유지한다.

### 기준 증거와 실제 열린 문제

기준 source는 `e6a49b7c0cd598ff480a1d3a421fa9e8ae57f227c311d514556a394f137b29db`,native는 `6a6d48c8986ce1ffe1108afa145707b556345f0e7572c7c4f34e7e64b19da808`이다. 원 PLAN v1.1.26과 matrix의 SHA,actual Python/RAM/disk,직전 raw 영수증의 전체 내용·SHA를 `artifacts/v03_constructive_remodel_20261123/R1_baseline.json`에 보존했다. 실제 RAM은31.25GiB이고 과거64GiB 목표를 관측값으로 쓰지 않는다.

직전 후보의25,730s checkpoint는5,523,765,378B이며 full-wire SHA `c8335535408e13266bb4b5f15b10d0854701e644421ae3e8183d7c468d9183c9`다.25,740s는 정상 반환·장부 검사를 통과했으나 저장의 `native snapshot Arc census preflight`가6,807,602,661>6,442,450,944B로 실패했다. 이 상태는 저장된 predecessor가 아니다. 원 time-zero/hourly86,400s 요청은764.18s 뒤 Journey stored/working guard와 복구 저장 census7,221,056,145>6,442,450,944B에서 실패했고,25,200s의 출발 전 all-zero 장부 상태만 durable/fresh 검증됐다. 이 정확한 실패와 그 source를 재사용하며 바뀌지 않은 긴 실패 실행을 먼저 되풀이하지 않는다.

이론의 직전 성과는 τv′=V−v의 기억과 완료된 matched passage 적분에서 미래 통과시간을 구성하는 명제다. 양의 강제력/속도 하한에 의존하므로 실제 정지·spillback으로 적용 범위를 확장하는 것은 여전히 열린 과제다. 또한 원래 mesoscopic 목적과 packet row 폭증을 함께 보아 누적 수송·mass-rank·cohort 표현을 새로 평가한다. 이미 수행한 proportional merge/Γ-envelope를 새 결과로 재명명하지 않는다.

### 이번10단계의 판별 가능한 산출물

| 단계 | 이론/코딩을 연결한 목표 | 실제 완료 근거 |
|---|---|---|
| R1/C1 | 원 동기와 새 모델링 권한,source/실패 기준 | 원 역사·current hash·실제 영수증 연결 |
| R2/C2 | 원전·과거 결과 재사용과 식–코드 대응 | 세 모델 경로의 근거,현재 census/Journey 수명 조사 |
| R3/C3 | 모델 전제·동치·알고리즘 정합성 | 계산 가능한 판별례와 유효한 production-path RED |
| R4/C4 | 발산적 구성에서 후보 선택·실행 DAG | 실제 계산에 따른 선택과 disjoint ownership,재개 admission |
| R5/C5 | 새 명제 증명·선택 모델/수정 구현 | 정의→유도→computational form→실행 코드 |
| R6/C6 | 한정 독립 이론 검증·소프트웨어 검증 | 새 범위의 독립 재유도,같은 명령 RED→GREEN,관련 gate |
| R7/C7 | 모델의 물리·관측량 대응 | 보존·FIFO·극한·반례·원 기준과의 구체적 비교 |
| R8/C8 | 원 규모에서 길이/실행시간 증가 | 실제 wall/RSS/반환·저장·fresh 결과와 원 hourly 비교 |
| R9/C9 | 독립 코드 심사 통합·최종 전제조건 | 최종 후보3도시 preparation과 source-bound 준비도 |
| R10/C10 | 증거·모델 판정·재개점 보존 |10단계 종료/push,미완료와다음최소과제 구분 |

원 release 실행 조건은100,000residents/case,86,400s,3도시×3회,dt10s,별도dt5s refinement,wall7200s/process8GiB/native6GiB다. 준비도는19/21 구현·한정 검증,5/21 ACCEPTED,직접 선행3/3,최종 candidate preparation,full-day0/9를 분리한다. 아직 새 후보를 만들지 않았으므로 직전 후보의3/3 preparation을 이번 새 코드의 검증으로 선반영하지 않는다.

### 병렬 작업과 자원

Native 조사/구현은 `checkpoint_validation_bridge`가 `v1_road.rs,v1_journey.rs,v1_engine.rs`를 소유하고 초기에는 read-only로 실제 원인을 확인한다. `stop_go_model`은 정지·재출발/누적 서비스/관측 모델의 세 경로를 실제 수식·작은 계산으로 비교한다. `remodel_history`는 원 목적과 과거 표현 연구를 대조하고 mass-rank/누적 수송의 독립 대안을 구성한다. 부모는 공유 보고서·PLAN 판단·runner·통합·commit/push·실제 큰 실험을 소유한다. Cargo와 전체 규모 물리 실행은 겹치지 않게 조정한다.

첫 검증/구성 pass와 위험에 근거한 한정 독립 pass를 사용한다. 같은 근거의 감사 재귀나 의미 없는 테스트 수 증가는 하지 않는다. 모델/수치/구현/resource/환경 실패를 구분하며, 실제 새 원인이 확인된 경우에만 다음 수정을 진행한다. 문서·hash·노드 수가 과학적 진전의 대용이 되지 않도록 한다.

### 이번 턴과 R1의 drift watchdog

기준은 `METROFLOW_ORIGINAL_INTENT_WATCHDOG.md`에 연결된 최초 확인 가능 import0492364,constitution6524500,active-meso3d83db0와 현재 T02/T04/R01/R02다. 원 목표는 설명 가능한100k 도시의 mesoscopic 물리,목적지/행동/정보를 보존한 수송,혼잡에서 경로·접근성·지연 feedback으로 가는 연결이다. 이번 후보는 단순히 더 많은 guard를 통과하는 것보다 정지·재출발과 누적 수송의 새 구성으로 실제 관측/실행 문제를 바꾸는지 판별한다.

판정은 `ALIGNED_WITH_OPEN_OBLIGATION`이다. 사용자 새 모델링 승인을 과거 문구로 막지 않고, 새 모델을 기존 V03과 동일하다고 미리 선언하지 않는다. 위 모델 경로의 구체적인 성립 여부와 실제 큰 실행은 뒤 단계에서 판정한다.
