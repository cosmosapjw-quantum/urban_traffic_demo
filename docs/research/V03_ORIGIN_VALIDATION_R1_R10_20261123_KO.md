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

Watchdog: `ALIGNED_WITH_OPEN_OBLIGATION`. 과거 연구와 다른 새 구성 경로를 선택했고, 원래 finite-information routing과 mesoscopic 실행을 각각 실험으로 연결한다. hourly 호출 실패에서의 예외 checkpoint 회수와 연구 tick 반환의 진전 단위를 분리한다. 원 worker의 실제 회수 동작은 R6에서 확인했다.

## R5 / C5 — 구성적 증명과 실제 구현 (완료)

`V03_FIFO_ROUTE_OBSERVABILITY_THEORY_20261123.md`에 세 명제와 증명을 완성했다. (1) FIFO Γ-Lipschitz 함수 클래스의 존재 필요충분조건과 sharp 전체 상·하 함수, (2) 공간적으로 균질한 τ_r v'=V−v에서 양의 invariant speed bounds가 주는 Γ=v_+/v_−와 τ_min=length/v_+, (3) legal turn graph에서 monotone composition 및 upper-optimal 경로의 regret≤U_*−L_*이다. McShane형 확장과 FIFO shortest paths는 고전 요소이며 이번 성과는 현 프로젝트의 sparse causal observation→physical certificate→route enclosure 연결이다.

증명의 핵심은 (x_i−x_j)_+≤(x_i−t)_++(t−x_j)_+와 표본 양립성으로 모든 lower cone이 모든 upper cone 이하임을 보이고, 양 함수 자체가 admissible임을 구성하는 것이다. 운동학적 certificate는 두 거리 적분식을 빼서 ∫E(t1)^E(t2) v=∫t1^t2 v를 얻은 후 v_−,v_+로 감싼다. 경로식은 덧셈 대신 비감소 함수 합성이며 고정된 반사실적 traffic field에서만 비교한다. 이는 코드 최적화 정리가 아닌 교통 관측·예측 배경이론의 명시적 업그레이드다.

실행 모듈 `src/metroflow/v1/fifo_route_observability.py`와 과학 테스트가 추가됐다. 실제 finite-response exact oracle, causal probe, 빈/미전달/불일치 입력, 미인증 upper의 전파와 legal graph certificate를 제공하며 production R02나 native 수송을 변경하지 않는다. Native 자동 boundary 계측은 미완료로 유지한다.

native `v1_road.rs`는 실제 validator 배열을 streaming expansion으로 대체했다. 같은 순서·같은 f64 축약·같은 검증 조건·같은3×max owner reserve를 유지하면서 동시 scratch와 성장 old+new overlap을 계상한다. 10,000행의 동일 행동 테스트가 GREEN으로 전환됐고(`C5_validation_green.log`,exit0), 입력 road wire도 동일하다. 소스 SHA는b7a3fad3943da61c5ff72fba08d10ea9832d722f1442c161dfc8c244493361dc다. 이는 full100k frontier의 PASS와 별개이며 다음 실험에서 판정한다.

Watchdog: `ALIGNED_WITH_OPEN_OBLIGATION`. 원래 collision/finite-response에서 인과적 경로 비용으로 가는 구체적 명제·물리 oracle을 얻었고, mesoscopic 실행 blocker의 실제 scratch를 줄였다. 원본 driver·calendar·cap·physics·wire는 유지했다.

## R6 / C6 — 독립 검증·native build·원 cadence 실측 (완료)

독립 이론 검토 `/root/fifo_theory_review`는 세 명제의 증명을 별도로 재구성하고, 명시된 범위에서 중대한 결함을 발견하지 않았다. 별도3-clock 유한 함수족400개 입력 중335개 feasible case에서 존재·extrema가 맞았고,24개 유향 그래프의 전체 simple-path 비교가 맞았다. 구현의 distance 함수를 쓰지 않는 독립 원시함수로124개 보류 passage의 exact root bracket과 폭≤1e−10s를 검산했다. 실제 command와 exit0은 `R6_independent_fifo_repro.log/.exit`, 논증은 `R6_independent_fifo_review.md`에 있다. 저자 pytest11개와 독립 검산을 중복 합산하지 않는다.

완료·전달된 과거 표본만 쓰는 미래 t≥d에서는 L(t)=t+τ_min, U(t)=Γt+min_i(u_i−Γx_i)로 단순해진다는 정보량도 확인했다. 따라서 과거 표본이 이번 예측에서 줄이는 것은 미래 upper의 불확실성이다. finite-domain 밖의 경로 보장, 미인증Γ, production boundary 계측은 미완료다. 증명은 외부 정리를 호출하지 않고 닫혀 있다. McShane 원문 Exa 추출의 정확한 page 확인은 독립 HTTP403으로 재현되지 않았고 그 서지 확인을 별도로 표시했다.

native 첫 후보는 표적6개, workspace library267개 통과·2ignored, 독립 코드검토에서 중대한 결함 없음이다. 실제 RED→GREEN,130개 sum bit 사례, 동시 accumulator/성장 overlap, malformed-state 지속 거절을 확인했다. `C6_validation_revision.md`, `C9_independent_validation_review.md`를 따른다. scoped library 검사를 전체 repository CI라고 부르지 않는다.

release build는exit0(관측31.49s). candidate source는c9fdad9cafc138855e5aaa863de15f49a1a13c0ee13dcab99f9f92cf9cb92a26, native는979c92c00e75ea7eb1a35b258ddd8821d413510ba37f5e1fd4aa6fd448830082이며 build시 clean commit3eab636이다(`C6_frozen_candidate.json`). 이후 수정이 있으면 이 근거는 이 후보에 묶어 보존한다.

원래 hourly acceptance를 이전 clean native에서 time-zero로 실행한 baseline은25,730s의 검증·저장된 prefix를 얻고25,740s의 `tick preflight`에서6,682,798,752>5,320,948,967B로 멈췄다. wall651.079687s,peakRSS4,655,276,032B,exit2다. 원 worker는 실패한 call의 예외에 들어 있는 마지막 유효 checkpoint를 회수한다. 전체 call이 원자적으로 롤백된다고 가정하지 않는다. 이5,523,765,378B checkpoint는 이전 역사 checkpoint와 전체SHA c8335535… 및 장부가 정확히 같다. 따라서 같은 wire에도 실제 capacity·sharing과 call-input 수명이 다를 수 있음을 실측했다. 원인 조사에서 restore의 exact-keyset interning과 continuous 경로의 deferred interning, 첫 tick 뒤 만료되는 실제 shared-input witness를 확인했다.

baseline 실행 일부와 Rust 검증/build가 겹쳤으므로651s는 실제 관측 비용이며 격리된 speedup 비교가 아니다. 현재 후보의 time-zero 실행으로 세지 않고, 원래day 캠페인credit은0이다. 원본 영수증과 fullhash 요약은 `R2_baseline_hourly/` 및 `R6_original_cadence_baseline_summary.json`에 있다.

Watchdog: `ALIGNED_WITH_OPEN_OBLIGATION`. 진단 harness가 원 실행을 대표한다고 가정하던 위험을 실제 cadence 재실행으로 교정했고, 관측 의미와 새 이론의 물리적 범위를 독립 확인했다. 남은 실행 blocker는 실제 phase별 계약의 문제로 좁혀 수정한다.

## R7 / C7 — 판별 물리 계산과 첫 full-scale 적용 (완료)

이론의 판별 실험은 τ_r=2s, 속도 knots(0,2),(20,3),(40,2),(100,2) [s,m/s], forcing V=v+τ_r v'의 exact finite-response 해다. invariant range[1.9,3.1]m/s에서Γ=31/19를 인증한다.20s 결정 전에 완료·1s전달된 표본만 예측에 넣고 미래 entry20…35s의4개길이×31시점=124개 통과를 보류했다. exact-rational 적분과 root bracket 폭1e−10s로 전부 확인했다. 저자 실행wall0.143555s, 독립 다른 primitive 검산exit0이며 실제도시 calibration이 아니다.

| 20s 출발의 경로 도착 clock | 예측 구간[s] | 실제 exact bracket의 근삿값[s] |
|---|---:|---:|
| 직접10m | [23.2258064516,26.6813942905] | [23.4314575050666,23.4314575051394] |
| 우회20m+20m | [32.9032258065,56.2142524713] | [35.2786404499797,35.2786404501106] |

직접 upper가 우회 lower보다6.221831516s 작다. 일반 regret bound는3.455587839s, 해당 경로집합의 강한 dominance 판정은regret0이다. 이 결과는 선언한 Γ-function class의 구성적 oracle이며 일반native queue의 Γ 인증과 자동 boundary 계측까지 해결하지 않는다. **R8의 물리 비교 기준 재평가로 해석을 교정했다:** Γ=v_+/v_-를 만들 때 사용한 전역 속도 범위 전체를 이용하면 이미 duration≤length/v_-가 성립한다. 이 특정 예제는 그보다 더 많은 관측 정보의 이득을 입증하지 못한다. 기존 증명과124개 포함 검산은 유지하고, 실제 관측이 선택을 바꾸는 finite-response 기억 정리를 아래 R8에서 추가한다.

원본100k의 첫 새 후보 물리실험은25,730→25,740s를 요청했다. 기존 전체5.523GB wire와 원 mass ledger가 정확히 복원됐고, 이전의 `state validation workspace`를 통과해 road→service_finish→journey_finish까지 진행했다. 그러나 최종 `whole checkpointability`가6,448,942,576>5,789,366,831B로 거절하여 새로운 committed physical time은0s다. native 성공tick0·실패1, road121.472988s, 전체172.840468s,peakRSS4,999,565,312B,exit2다. 결과 `R7_frontier_25730_10s.json/.log/.time/.exit`를 보존했다. 물리 중간 연산이 끝났다는 이유로 완료시간을25,740으로 올리지 않았다.

이 실패는 첫 구현의 실제 기여와 잔여 계약을 구분한다. old validator blocker는 실제100k에서 지나갔고, 다음 checkpoint/decode 사전조건은 남았다. 조사 결과 whole-bundle Journey의 validation maps는 여전히 실제 필요하며 제거할 수 없다. stale O(road parts) 항은 road checkpoint decoder의 validation reserve와 미래 decode envelope에 함께 남아 있다. 두 경로를 일치시키는 수정과 실제 source/current/candidate 수명에 따른 hourly preflight 교정을 C8에서 수행한다. 같은 실패의 맹목적 재실행 대신 원인이 다른 계약 지점을 수정한다.

Watchdog: `ALIGNED_WITH_OPEN_OBLIGATION`. 이론은 원래 traffic→causal routing을 실제 계산으로 연결했고, 코드의 full-scale 적용에서 통과한 phase와 rollback된 전체 tick을 분리했다. 단계 검증을 완료했지만 V03 실행 통과로 바꾸지 않았다.


## R8 / C8 — 수명 기반 교정과 길이 증가 실험 (진행 중)

### 반복 실패의 surgical revision

한 번의 record-only 진단에서 첫 native 후보의 checkpointability 6,448,942,576B를 실제 항별로 분해했다. `road_decode_scratch=1,114,353,504B`에는 이미 streaming으로 바뀐 검증과 맞지 않는 O(parts) 항이 남아 있었고, `validation_scratch=489,255,344B`의 whole-Journey 검증은 여전히 실제 필요했다. 진단은 물리·cap·guard를 바꾸지 않았으며 새 committed 시간0s, wall494.072269s이다. record-mode 시간을 정상 후보의 성능으로 비교하지 않는다. 근거는 `C8_checkpointability_diagnostic.json/.log/.time/.exit`와 보존한 실행 스크립트다.

오래된 예측식을 단순히 작게 만드는 대신 네 수명 상황을 구분한다. 첫째는 실제 원 입력/source/candidate가 공존하는 현재 commit, 둘째는 새 runtime에서 road만 먼저 decode하는 단계, 셋째는 road와 service가 존재하는 상태의 Journey 자체 검증, 넷째는 decode 작업공간 해제 뒤 whole-bundle 검증이다. 독립 검토가 Journey 자체 검증의 기존3×max allowance 누락을 구체적인 반례로 발견했으므로, 실제 검사와 cap은 그대로 두고 별도 세 번째 phase를 추가한다. 서로 배타적인 단계는 최대값으로, 같은 단계의 실제 owner·workspace는 합으로 계상한다. 현재 commit의 실제 공유 credit은 포인터 확인된 immutable Arc에 한정하며 미래 독립 decode에 공유 credit을 전파하지 않는다. 진단값으로 현재 commit 항만 재구성한 보수값은5,286,485,316B로 dynamic pool5,789,366,831B 안에 들어간다. 이는 새 후보 실행 결과가 아닌 기존 진단 항의 산술 재구성이다.

원 문서 `docs/v1/NATIVE_RUNTIME_KO.md`는 예산 실패 뒤 마지막 유효 상태를 fresh runtime에서 load/replay할 것을 요구한다. 이전 precommit source 두 개와 미래 decoder의 합은 실제 postcommit same-engine 재개의 소유자 구성도 증명하지 못했다. 이번 수정은 현재 commit과 fresh restore를 명시적으로 예측하고 실제 loader admission을 그대로 적용한다. V03의43,200s same-engine resume은 별도 필수 수용 의무로 유지한다. 이를 새 문서와 trace 항에 구분해 기록하며, 단지 future guard를 통과했다고 warm resume이 해결됐다고 하지 않는다.

원 hourly 호출의 road preflight는 실제 caller snapshot capacity R0를 engine에서 직접 전달해 R0+R+max(R0,R)를 사용한다. 원 입력의 capacity를 clone의 작은 capacity로 추정하지 않고, source 공유 witness는 실제 clock이 달라지면 만료시킨다. 아직 생성되지 않은 incoming combine 버퍼는 prediction 중에만 제외하고 motion scan 종료 경계에서 다시 계상한다. standalone의 기존3×max fallback, 실제 offer overlap, 전체 cap과 wire·물리·허용오차는 유지한다. 두 production-path 행동 RED가 같은 명령 GREEN으로 바뀌었고,64개 실제 offer의 event f64 bits와 wire가 uncapped oracle과 같았다. 근거는 `C8_validation_preflight_*`와 `C8_validation_original_cadence_preflight.md`다.

최종 source/native 동결, 독립 delta 검토, 전체 규모 재실행과 길이 증가 결과는 아래에 실제 영수증으로 보충한다. 이 절의 진행 상태 자체는 V03 통과를 뜻하지 않는다.


### 독립 검토의 실제 수정과 최종 source gate

독립 검토 `C8_independent_accounting_review.md`는 최초 후보의 fresh Journey 자체 검증 예측 누락(F1)을 발견했다. D=E=J=1,000,000B인 정수 함의 반례에서 예측 max4,465,536B는4,800,000B cap 안이지만 실제 유지된 Journey phase는5,067,584B였다. 이는 독립 산술 반례이며 실제 도시 행동 RED로 부르지 않는다. 실제 loader는 원 guard로 거절하므로 예산 검사가 우회된 것은 아니다.

추가된 별도 phase는 초기 current-road와 빈 event carrier, 독립 decoded-road·event, 기존3×decoded-Journey와64KiB reserve를 함께 센다. 다른 phase와 최대값을 취하며 원 validator나 cap을 낮추지 않았다. 실제4,096-receipt read_state 회귀에서는 이전 allowance185,200B가 실제 요구320,512B를 거절하고, 새 보수 allowance424,528B에서 전체65,632B wire가 동일하게 복원됐다. 최종 scoped Rust library는285passed,0failed,2ignored,exit0이다(`C8_checkpoint_journey_validator_fix_lib.log/.exit`). 독립 검토는 이 수정의 단조 추가와 실제 decoder 회귀를 확인해 F1을 RESOLVED로 종료했고, 지정 C8 나머지 범위에서 추가 material finding은 없었다.

최종 source 동결 commit은64173178d11229825efc553c441f6f90c7541979이다. Journey SHA285cf61a9e1339dbf68a0754d1efdd76d8d21a33ceed6931fe29b7b97380f32d,road SHA01694c9ec17d06b43188a9d8e9d93a4dd099173533642e993631befa5ef3a939,engine SHAbf078c2d45fda2805531812b3f74a2955a0b4137098c2cc6fc959bf8743f4e93다. 앞선6f98c4d의3phase 후보와 그 build·일부 preparation은 중간 근거로 보존하며 최종 후보의 실적으로 승격하지 않는다. 전체 규모 물리 실행은 이 최종 수정과 독립 closure 이후에 시작한다.


### 물리 비교 기준의 재평가와 구성적 이론 업그레이드

매 턴 drift watchdog가 기존 R7 예제의 비교 기준을 다시 물었다. 양의 속도 범위[a,b]에서 Γ=b/a를 인증했다면 이미 통과시간≤ℓ/a다. 전달 완료 표본의 T=u−x≥ℓ/b와 미래t≥u에 대해 Γ-envelope duration=T+(Γ−1)(t−x)≥ΓT≥ℓ/a이므로, 그 예제는 알려진 물리 속도 범위 전체보다 관측이 더 나은 선택을 제공함을 입증하지 못했다. Γ-function class의 정리·sharpness·124개 포함 검산은 유지하지만, 그 물리적 해석을 명시적으로 제한했다. 이를 no-go로 끝내지 않고 같은 배경식 τ v'=V−v의 기억을 새 구성에 사용했다.

완료 통과(x,u,L)에 T=u−x, A=τ(expm1(T/τ)),α=T/A를 놓으면 backward variation-of-constants와 적분 순서 교환으로 L=A v(u)−∫₀ᵀ(e^{s/τ}−1)V(x+s)ds를 얻는다. 적분의 양의 kernel 총량은 A−T이므로 endpoint 속도는 αL/T+(1−α)[a,b] 안이다. 전달 지연과 미래 시간을 forward response로 전파하고 양의 속도 상·하 함수의 거리 적분을 역으로 풀면, 과거 관측에서 인과적으로 좁혀진 FIFO arrival bounds를 구성한다. 새 증명·범위·극한·단위 검사는 `V03_FINITE_RESPONSE_PROBE_UPGRADE_20261123.md`, 실행식은 `src/metroflow/v1/finite_response_probe_certificate.py`에 있다.

판별례는τ=10s,forcing/속도 범위[1,3]m/s,10→15s에10m를 통과하고16s에 전달 완료된 probe다. 새10m 구간의 전역 duration[10/3,10]s는 exact7s 경쟁 경로를 배제하지 못하며 upper-min이7s 경로를 고른다. 유도된 decision speed[1.6974007628,2.3025992372]m/s를 쓰면 새 duration은 약[4.1180114938,6.6224385552]s이고 다른 경로를 선택한다. 참 v=V=2m/s 해의 통행시간은5s이므로2s regret이 사라진다. 이는 관측이 실제 경로 선택을 바꾸는 예제다.

이 dominance는 root의 floating 반올림에 의존하지 않는다. 하단 거리의 정확한 식 Q_-(16,7)=7+5e^{-0.1}(1−e^{-0.7})/(e^{0.5}−1)>52409/5057>10m라는 유리수 비교가 모든 허용 이력에서 duration<7s를 보인다. 수치 root endpoints는 binary64와70-digit Decimal 대조를 통한 수치 검산으로만 표시하며 일반적인 directed-rounding enclosure로 부르지 않는다.

실제 새 표적pytest11개가0.25s에 통과했고, 별도 보류 passage84개(상수forcing60개+관측 뒤forcing변화24개)가 모두 통과했다.120개root를70-digit Decimal 식과 비교한 최대 차이는9.21514e−12s(<2e−11s), 실험wall0.771811s,exit0이다. 기존 이론 모듈·native·수요·dt·cap은 변경하지 않았다. 일반 queue/spillback의 양의forcing 인증과 native matched boundary 계측은 여전히 미완료다. 새 유도에 대한 독립 검토는 기존 정리를 재심사하지 않고 이 추가 범위만 확인한다.


### 정상 반환·저장의 반복 capture 실패와 C8c 통합

첫 C8 최종 native(78b49811…/3bec7cd5…)는25,730→25,740s에서 내부 tick1개 및 checkpointability를 통과했다. 그러나 outer capture/validation이6,887,244,069>6,442,450,944B로 거절하여 연구 runner의 새 반환·저장 시간은0s다. 이어10/20/40s staircase를 실제로 실행했다.10s와20s는 저장까지 성공했고,40s는25,690→25,730s의4개 returned/ledger-checked tick을 마쳤지만 저장 중6,513,265,473>6,442,450,944B로 실패했다. 이 구간에 final wire/hash가 없으므로 전체70s durable chain 성공이나 역사 wire 일치를 주장하지 않는다.

| 요청 window | 반환·장부 clock | 전체 child wall[s] | worker timer[s] | durable 결과 |
|---|---:|---:|---:|---|
| 10s | 25,660→25,670 | 66.813550 | 64.207583 | 저장 성공,2,210,069,010B |
| 20s | 25,670→25,690 | 124.597112 | 122.736730 | 저장 성공,2,949,231,402B |
| 40s | 25,690→25,730 | 364.103844 | 361.212305 | 반환40s,마지막 저장 실패 |

전체 child wall은 시작 admission hash와 Python 시작 비용을 포함한다. worker timer는 prepare·restore·advance·save를 포함하지만 그 전에 수행한 predecessor admission hash는 제외한다. 요청 물리시간과 실제 CPU/wall 실행시간을 혼용하지 않는다. 각 source/native·native tick timing·RSS·원 오류는 `R8_staircase/`에 있다.

같은 후보의 원 CLI에서100k/86400s를 실제 time-zero로 요청했다. hourly25200→28800 호출 중 `native journey stored/working byte budget`가 먼저 발생하고, 예외 checkpoint를 저장하다capture7,611,271,961>6,442,450,944B로 다시 실패했다. 외부wall717.29s,exit1,peakRSS5,286,748,160B다. 최종 worker JSON은 생성되지 않았으며 마지막 저장된 hourly 경계25,200s만 확인된다. 그 이후 내부 clock은 기록되지 않아 추정하지 않는다. source note와 외부 실패 요약은 `C8_remaining_capture_blocker.md`, `R8_pre_capture_original_hourly_failure_summary.json`에 보존했다. 따라서 capture 문제는 tick-return 연구 runner뿐 아니라 원 수용시험의 실패 복구에도 영향을 준다.

C8c는 이 반복 실패를 근거로 capture와 restore가 사용하는 단일 `snapshot_source_owners` 계상 경로를 만들었다. 실제 input I,current C,정확한 clone target T의 container capacity를 모두 세고, 실제 포인터로 확인한 I∩C immutable payload 및 T→clone(T)의 공유 payload만 공제한다. StageQueue row payload·Road parts·ReceiptHistory shallow clone을 구분하고, 입력/current history 사이의 prefix 공유는 보수적으로 남긴다. Event backing은 Arc identity와 측정 size가 모두 같을 때만 하나로 센다. 공제 없는 두 실제 owner와 고정 reserve·순차 census workspace를 먼저 승인하며, census와 이후 clone/validation의 비용은 별도 phase MAX다. 독립 future decoder에 현재 source 공유를 전파하지 않고 cap·validator·물리·wire는 유지했다.

실제 유효 fixture의 기존 capture84,991,238>84,594,070B 및 save/restore84,991,166>84,397,174B가 같은 cap에서 GREEN으로 바뀌었고1,049,076B 전체 wire가 동일했다. 이 fixture는 실제 road event, nonempty StageQueue·ReceiptHistory를 포함한다. 앞선3개 fixture 작성 실패 로그는 보존하지만 behavioral RED로 세지 않는다. 표적7개,전체 Rust library292passed/0failed/2ignored,exit0이다. 독립 C8c 검토의 primary 판정은 지정 범위에서 NO_MATERIAL_FINDING이며, fresh-load→restore→반환은 여전히 실제 큰 checkpoint로 확인한다. 미래 사전 gate 하나만으로 전체 복원 파이프라인의 충분성까지 증명했다고 하지 않는다.

재실행은 이미 성공한10/20s를 무조건 반복하지 않고, 저장된25,690s의 raw receipt SHA `fb6b74b7af38592003d1af169d8c029b9ceb394194e3217d6011d0865dc95732`,전체 wire/source/native를 명시적으로 고정해 같은 실패40s를 다시 실행하도록 준비했다. 변경되거나 저장이 실패한 영수증은 계속 거절한다. 원11개와 이번3개를 포함한 admission14개가0.14s에 통과했다.25,670s 중간 파일은 소비 완료 후 무손실 zstd로 보존했고, 풀어 읽은 전체2,210,069,010B/hash 일치를 확인한 뒤 중복 raw만 제거했다(`R8_staircase/archive_from_25660_duration_10.json`). 역사적 seed는 변경하지 않았다.
