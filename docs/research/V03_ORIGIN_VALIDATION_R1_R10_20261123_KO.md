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

## R2 / C2 — 원전 재사용과 실제 공백 (완료)

원 역사와 현재 모델의 정확한 연결은 `METROFLOW_ORIGINAL_INTENT_WATCHDOG.md`에 보존했다. 독립 조사 agent `/root/origin_drift`는 read-only로 초기 commit·constitution·Oct active-meso·현 R01/R02 문서를 대조했다. 부모도 초기 traffic design, Oct active-meso, R01/R02 및 acceptance 호출부를 직접 읽었다.

현재 과학적 공백은 단순히 age 평균 계산이 아니라, 전달된 제한된 관측에서 정당한 경로 도착시간을 만드는 것이다. 완료 route 평균과 event-incidence age는 링크 입출구 시간 자료가 아니다. 이전 two-state first-passage, KCMB moment closure, 20261122 generalized inverse, 20261123 stop-loss envelope는 재사용하며 신규 결과로 세지 않는다.

외부 수학 기준은 Brian C. Dean, *Shortest Paths in FIFO Time-Dependent Networks: Theory and Algorithms*, 저자 공개 원문 https://people.csail.mit.edu/bdean/tdsp.pdf §2,§3.3,§4.1이다. arrival map E_e(t)≥t의 비감소성, 경로 함수의 합성, 고정 출발시각 label-setting을 재사용한다. 원문은 알려진 전체 시간 함수가 주어진 문제를 다룬다. 이번 추가 의무는 인과적 sparse 측정으로 허용 arrival maps의 상·하 경계를 구성하는 것이며 고전 Dijkstra 자체의 신규성을 주장하지 않는다. McShane1934 원 AMS PDF는403으로 본문확인 실패했으므로 읽었다고 기록하지 않는다.

코드 조사에서 최종 `V1Road::check_state(&out)`가 class별 mass, 전체 mass, residence 배열을 실제 materialize한 뒤 동일 expansion sum으로 축약하는 것을 확인했다. 수정은 같은 입력 순서의 streaming expansion과 성장 전 scratch admission을 사용하며 기존 owner3×max fallback은 유지한다. 원 acceptance 호출은 hourly, 진단 harness는 tick마다 반환하므로 baseline을 기존 frozen native에서 time-zero→25,740s 요청으로 시작했다. 실행 결과는 아직 pending이며 R2의 성과로 완료 credit을 부여하지 않는다.

Watchdog: `ALIGNED_WITH_OPEN_OBLIGATION`. 원 교통→routing 질문을 새 명제의 대상으로 복원했고, 과거24h불가 추정이 모든 정확 표현을 배제하는 것처럼 읽히던 AGENTS 문구를 좁게 교정했다. 원 PLAN·수요·dt·cap은 변하지 않았다.

## R3 / C3 — 전제 정렬과 실제 수정의 판별식 (완료)

세 관측량을 구분했다. (a) snapshot시각의 반복 event-incidence age, (b) once-only completed route duration, (c) 동일 경로환경의 entry시각 x에서 exit시각 E(x). 새 FIFO 경로 정리는(c)를 입력으로 하며(a)의 birth 평균을 링크 통과 표본으로 변환하지 않는다. 시각·단위는 SI초이며 현재 수송 동역학을 바꾸지 않는다.

정확 유리수 판별례를 실행했다: E1(t)=t+10, E2(t)=2t+1, direct(t)=t+16 (t≥0). 모두 FIFO이고 양의 통행시간을 갖는다. t=0의 링크 시간 합은11s지만 합성 도착은E2(E1(0))=21s다. direct는16s라 frozen 합으로 선택하면5s regret이 생긴다. 이는 현재 R02가 이미 조건부 행동 closure로 제한한 합을 actual ETA로 승격하면 안 된다는 구체적 이유이며, 경로 도착함수의 합성이라는 구성적 수정으로 이어진다. 실행 영수증 `R3_fifo_composition_discriminator.json`은 exact-rational 결과다.

새 목표 클래스는 E(t)≥t+τ_min, 0≤E(t)−E(s)≤Γ(t−s) (t≥s), Γ≥1이다. 전달 완료된 boundary 표본 E(x_i)∈[l_i,u_i]를 사용한다. finite Γ의 물리 근거는 양의 속도 하한이 실제로 성립하는 특정 regime에서 따로 증명하며, stop/spillback에서 자동으로 가정하지 않는다. 데이터 양립성과 u_i≥x_i+τ_min을 검사하고, sharpness는 이 함수 클래스에 대한 것으로 한정한다.

native C3의 실제 행동 RED는10,000행 유효 상태에서 기존3×retained+8,192=731,048B allowance를 유지한 검사다. 기존 validator는882,920B를 요구해 거절했고 cargo exit101이었다(`C3_validation_red.log`). 따라서 수정 대상은 검사를 없애는 일이 아니라 실제 O(parts) mass 배열을 같은 순서의 expansion sum으로 축약하는 것이다. 성장할 때 old+new capacity를 먼저 계상하고, accumulator 개수에 무근거 상수 상한을 두지 않는다. 최종 native 적용·독립 검토·대규모 실행은 뒤 단계에서 판정한다.

Watchdog: `ALIGNED_WITH_OPEN_OBLIGATION`. 원래 혼잡→routing 의도를 실제 도착시각 함수로 잇는 판별 결과를 얻었고, 수송·허용오차·수요·cap은 유지했다. 현재 route 평균의 모집단을 새 boundary 데이터로 오인하지 않았다.

## R4 / C4 — 대안 구성과 실행 DAG (완료)

수학 경로 세 가지를 비교했다.

| 경로 | 실제 구성 | 판별과 선택 |
|---|---|---|
| 완료 평균의 정적 합 | Σ_e mean(T_e)의 frozen cost | R3의11s/21s 반례와 모집단 불일치 때문에 actual ETA 정리로 채택하지 않음. 기존 행동 closure의 의미는 보존 |
| 누적 유입·유출 generalized inverse | E(x)=D^{-1}(A(x)) 및 검열 | 이전20261122 결과를 재사용. 현재 희소 지연 관측과 링크 비용의 연결은 추가 필요 |
| FIFO 일방향 Lipschitz envelope | L(t)=max{t+τ_min,max_i[l_i−Γ(x_i−t)_+]}, U(t)=min_i[u_i+Γ(t−x_i)_+] | 과거의 전달 완료 boundary 관측과 명시적 Γ만으로 실제 구성 가능. 함수 양립성·sharpness·route composition을 증명할 주 경로 |

선택한 경로는 미래 실제 혼잡을 정보 입력으로 조회하지 않는다. Γ를 인증할 수 없는 정지/spillback에는 유한 미래 upper를 임의로 넣지 않는다. 독립 검산은 원 finite-response 방정식 τ_r v'=V−v를 정확히 만족하는 양의 piecewise-affine manufactured velocity에서 과거 passage를 측정하고 미래 passage를 보류해 판별한다. 이 manufactured 실험은 도시 calibration이나 production routing 활성화가 아니다.

실행 DAG: native 소스 동결→release build→정확히 고정된25,730s checkpoint의 wire·장부 복원→새10s frontier→새 source의10/20/40s 연결 active-window replay→원 acceptance cadence/time-zero 비교→3case preparation·readiness. 실제 실패가 생기면 동일 실패를 반복하지 않고 source·phase·owner lifetime에 근거해 다음 범위를 결정한다. Cargo는 한 사용자씩, 전체 규모 물리 실험은 직렬화한다. 원 cap을 유지하고 baseline에는 별도의1,800s 탐색 deadline을 둔다. 탐색 timeout은 원7200s 기준의 실패 판정과 다르다.

`tools/research/v03_origin_validation_horizon_20261123.py`는 원 dt=10s를 고정하면서 tick/window/hourly 호출 경계를 명시한다. 새 source에서 사용할 역사 seed는 전체 receipt SHA+checkpoint SHA/size가 고정된25,660s/25,730s 두 개뿐이다. 나머지는 같은 source/native의 저장된 유효 prefix만 허용한다. 실패한 multi-tick native call 내부의 미반환 tick은 credit0이며 이전 반환 상태만 저장한다. 입증되지 않은 cross-native·cap drift·trace override·잘못된 clock credit을 거절하는11개 표적 검사가0.16s에 통과했다(`C4_horizon_admission_tests.log`,exit0). 기존의 여러 역사 예외를 새 runner에 그대로 복제하지 않았다.

Watchdog: `ALIGNED_WITH_OPEN_OBLIGATION`. 과거 연구와 다른 새 구성 경로를 선택했고, 원래 finite-information routing과 mesoscopic 실행을 각각 실험으로 연결한다. hourly 호출의 실패 원자성과 연구 tick 반환의 진전 단위를 분리했다.
