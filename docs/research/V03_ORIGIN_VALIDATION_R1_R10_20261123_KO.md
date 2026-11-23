# V03 원 동기·검증 작업공간 연구 루프 — R1–R10 / C1–C10

## R1 / C1 — 목표와 원래 기준 (완료)

기준 커밋은 `78d5e7e7e52e4db618a32ce3eca2e71f01b2433c`, 작업 브랜치는 `research/v03-origin-validation-20261123`이다. 이번 사용자 요청의 범위는 이론·코딩을 병행하는 정확히 10단계이며, 각 단계 완료 후 push한다. 원본 `docs/v1/PLAN.json` v1.1.26과 `scenarios/v1/release_matrix.json`을 수용 권위로 유지한다.

실행 목표는 100,000명/도시, 86,400 물리초, 3도시×3회, dt=10s 및 별도 dt=5s 비교, run당 wall 7,200s, process 8GiB와 native accounting 6GiB이다. RAM 실측은 32,763,440kB(약31.25GiB)다. 전체 저장소 CI와 main 통합은 기존 사용자 결정대로 보류한다.

실제 시작점은 Valley weekday s7의 25,730s 전체 checkpoint다. 직전 결과의 다음 tick 25,740s는 `state validation workspace`의 5,435,700,144B 요구량이 5,297,903,399B 가용량을 137,796,745B 초과해 거절됐다. 이는 resource admission 실패이며 allocator OOM이나 수학적 불가능성 판정이 아니다. 기존의 현재 source 연속 실행은 역사적 checkpoint에서 시작했으므로 time-zero 완주로 세지 않는다.

### 성공조건과 단계별 산출물

| 단계 | 이론·코딩 결합 산출물 | 실제 판별 기준 |
|---|---|---|
| 1 | 원 동기·현재 계약·baseline | 역사 commit과 PLAN, 현재 실패 영수증 연결 |
| 2 | 원전·과거 연구 재사용과 식–코드 조사 | 원래 collision→routing 의도 및 현재 관측 공백 특정 |
| 3 | 전제 교정·수치 알고리즘 | 순간 event age/완료 여행시간 구분, validator 실수요 분석 |
| 4 | 대안 수학 표현·실행 DAG | 3개 이론 경로 비교, streaming validator/cadence 판별 설계 |
| 5 | 새 명제·구현 | 배경 이론의 실제 증명과 실행 가능한 관측 코드, native 수정 |
| 6 | 독립 증명 점검·소프트웨어 검증 | 한 번의 독립 검토, 행동 RED→GREEN와 관련 회귀 |
| 7 | 구성적 계산·물리 대응 | 정확 계산과 original checkpoint/장부/수치 의미 보존 |
| 8 | 실제 길이 증가 실험 | 실측 wall/RSS/유효 prefix 및 원 수용 cadence 비교 |
| 9 | 정식화·독립 코드 심사·준비도 | 입력·source identity에 묶인 결과와 현재 잔여 조건 |
| 10 | 최종 판정·재개점 | 정확히 10단계 push, 결과·실패·미완료를 함께 보존 |

각 행은 단계 산출물을 규정한다. 실패한 실험도 정확한 실패 기작과 유효 prefix를 보존하면 해당 검증 단계의 결과가 되지만, V03 통과나 scientific claim PASS로 바뀌지 않는다.

### 원 동기 drift watchdog — 이번 턴의 초기 판정

초기 import `0492364`의 `docs/PRD.md`, `docs/TRAFFIC_DYNAMICS_DESIGN.md`와 constitution `6524500`을 원 역사로 조사한다. 보존 대상은 설명 가능한 synthetic 도시의 수요–mesoscopic 교통–경로–접근성–지연된 개발 결합, 질량·capacity·storage·인과성·결정론이다. 2026-10-24 `3d83db0`의 `docs/research/ACTIVE_MESO_DESIGN_20261024.md`는 active matter, 질량 보존 collision, 혼잡 비용과 legal-link Dijkstra를 연결한다. 현재 PacketNetwork/FIFO/finite-response 계약은 이후 선택된 실행 권위로 별도 보존한다.

관찰된 위험은 두 가지다. (1) 수십 초씩 전진하는 저장 표현 수정만으로 원래 교통·routing 과학을 대체하는 것, (2) 한 tick마다 Python으로 반환하는 연구 runner의 실패를 hourly native 호출을 사용하는 원 수용시험 전체의 실패로 확대하는 것이다. 이번에는 causal FIFO 관측에서 routing 비용으로 가는 새 구성적 이론과 validator의 실제 materialization 제거를 병행하며, 원 수용 cadence를 명시적으로 비교한다. 원래 목표가 packet row나 hash 자체였다고 재서술하지 않는다.

Watchdog는 매 사용자 턴 및 단계에서 `원 동기 → 이번 산출물의 연결 → 관찰된 이탈 → 가장 작은 교정 → 남은 원 목표`를 짧게 기록한다. 기록만 추가하는 것으로 연구 진척을 대신하지 않는다.

### 시작 준비도

- 선행 구현/한정 검증: 19/21 = 90.476%; 그중 최종 ACCEPTED는 5/21.
- V03 직접 선행 P01,V01,V02: 3/3 VERIFIED_SCOPED.
- 실제 24시간 캠페인: 0/9; V03 BLOCKED.
- 직전 native의 3/3 preparation은 역사적 근거다. 새 native가 생성되면 해당 source로 다시 측정한다.
- 현재 source의 time-zero→24h 궤적, matched refinement, 9회 replay/performance 수용은 미완료다.

근거: `AGENTS.md`, `docs/v1/PLAN.json`, `scenarios/v1/release_matrix.json`, `artifacts/v03_event_store_envelope_20261123/R8e_original_100k_25730_requested_20s.json`, `tools/run_v1_local_acceptance.py`의 `advance_measured` hourly 경계.
