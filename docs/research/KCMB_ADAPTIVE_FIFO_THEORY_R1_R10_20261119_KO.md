# KCMB Adaptive FIFO: 표현 불변성 교정과 인증 가능한 순서 축약 · 이론 R1–R10

2026-11-19 KST · `cosmosapjw-quantum/urban_traffic_demo` · scoped experimental research. 부모 commit `61c6c73a715b61a7fbcf91dc3b4528ba2ca6518a` (ordered FIFO). 원본 V1 PR #41 head `0b9caa8cc60a3ba087722e0360b997c5dfb61d62`; main/원래 V03 수용 조건은 변경하지 않는다.

## R1 목표
KCMB는 microscopic 자기구동·두 상태 Markov 제어에서 유도한 kinetic six moments와 macroscopic finite-volume supply/receiving, 그리고 단일 차로의 route-run FIFO를 연결하는 물리 근사다. 다음 단계의 과학적 질문은 **run의 분할만 바뀌었을 때 합류 노드의 유량이 바뀌지 않도록 교정하고, 순서 관련 모든 관측을 보존하는 경우에만 run 기록을 축약할 수 있는가**이다. 정확성을 우회하여 메모리를 줄이는 시간 binning은 허용하지 않는다.

## R2 기준·선행문헌
직접 코드: `src/metroflow/v1/kcmb_ordered_fifo.py`의 `OrderedKCMBBoundedNetwork.step`, `src/metroflow/v1/kcmb_network.py`의 `progressive_junction`, `v1_kcmb_node.rs`. 주석이나 이전 테스트를 물리 증명으로 대신하지 않고 실제 수송량을 대조한다.

일차 문헌: Bar-Gera & Carey (2022), *Constructing a cell transmission model solution adhering fully to first-in-first-out conditions*, DOI `10.1016/j.trb.2022.04.002`; Jin & Jayakrishnan (2005), *First In, First Out Properties of a Commodity-Based Kinematic Wave Simulation Model*, DOI `10.1177/0361198105193400121`; Wright, Gomes & Horowitz (2017), *On node models for high-dimensional road networks*, `Transportation Research B`. 이들은 exact/partial FIFO의 물리적으로 다른 전제와 계산비용을 근거로 하며 본 KCMB 알고리즘의 새 정리를 증명하지 않는다.

## R3 상태·가정
같은 물리 link의 `OrderedRun(a,m,t_{ready})`는 route `a`, 물리 차량량 `m [veh]`, 자유류 하한 시각 `t_{ready}`를 보유한다. Route별 kinetic `Y_{ia}=(m0,m1,j0,j1,z0,z1)`는 linked driver-control Markov 생성자에 따라 시간진화한다. 각 physical node는 유일한 receiving resource set을 가지며 같은 tick에 들어온 질량은 다음 tick부터만 전송할 수 있다.

**동치 조건 E:** 현재 tick `n`에 인접한 두 run이 같은 route이며 둘 다 `t_{ready}≤n`이면 두 run의 순서정보는 이후 route-label completion/cumulative-flow/kinetic total 관측에 차이를 줄 수 없다. 두 run을 합친 `(a,m1+m2,0)`으로 표시한다. 수학적 합치는 연산은 물리적인 entry timestamp에 대한 전수 관측을 대상으로 하지 않는다. 서로 다른 route, 미래 ready tick, 다른 class law, 서로 다른 물리 lane/pocket에는 결코 적용하지 않는다.

## R4 후보
A. 시간/route에 상관없이 모든 run 병합: FIFO red-turn 반례로 기각.
B. `(route,ready_tick)`가 같은 인접 run만 병합: 기존 구현, 혼잡 시 성숙한 same-route cohort가 길어질 수 있다.
C. 모든 성숙한 인접 same-route run을 병합하고 노드 수송 요청을 성숙한 **최대 연속 동일-route prefix**로 평가: **선택**.
D. 정확 FIFO를 유지한 채 single-route link를 latency-ring으로 축약: 선택 C 이후 별도 scalable 연구 후보.
E. 복잡한 교차로에만 exact FIFO island, 나머지는 moment-only: 순간정보 지우기는 미래 신호변화에 취약, 오차 검증 없이 실행 금지.

## R5 유도와 실제 반례

### 반례 E1: 기존 알고리즘의 run-partition 비불변성 [DIRECT NUMERIC OBSERVATION]
두 incoming link `n,s`가 같은 receiving link `out`을 공유한다. Route A의 `n`에 2veh, route B의 `s`에도 2veh가 있고 둘 다 동일 차종/kinetic speed state를 갖는다. A의 queue를 `[(A,2,ready=0)]` 또는 `[(A,0.2,ready=0),(A,1.8,ready=1)]`로 기록하되 현재 step에서 두 부분 모두 출구 통과 가능하다. 동일 receiving limit `C_{out}=0.3veh/s`, `dt=0.5s`와 priority가 같은 두 inbound link에서 **원 코드**는 각각
```text
A route flow 0.0750000000 / 0.042857142857
B route flow 0.0750000000 / 0.107142857143 [veh/step]
```
의 차이를 낸다. 현 node solver가 먼저 `0.2`의 head를 group demand로 올리고, 다른 link와 수신예산을 경쟁하므로 저장 표현이 물리 유량을 바꾼다. 이는 **현 구현의 명백한 관측상 오류**이고 압축 금지의 정당화가 아니다.

### 정리 E2: eligible-prefix aggregation의 표현 불변성 [DERIVED, CONDITIONAL]
한 node의 각 incoming link에서 현재 step에 eligible인 **맨 앞 연속된 동일-route** run의 총질량 `H_i`를 계산한다. 후보 sending demand는 `d_i=min(H_i,S_{ia}^{remaining},G_{ia}^{remaining})`로 하고, physical node의 receiving count/metres 및 우선순위 제약을 사용해 `x_i`를 결정한다. 실제 전송량 `x_i`는 해당 prefix의 앞에서부터 순서대로 감소시키며, 해당 prefix를 모두 소비했을 때만 다음 route run을 후보에 올린다.

이때 같은 route·모두 eligible인 한 prefix의 어떤 유한한 분할도 `H_i`와 pre-step `Y_{ia}`를 변경하지 않는다. 따라서 모든 경쟁 그룹의 `d_i`가 동일하고 node allocator가 deterministic, 수신 ledger와 priority가 같으면 `x_i`도 동일하다. 송출한 질량을 head prefix에서만 소모하므로 다음 node round의 collapsed prefix abstraction 역시 동일하다. Node-round 및 timestep에 대한 귀납법으로 같은 조건의 분할·병합이 전체 route-wise 수송량과 미래 macroscopic kinetic/queue-flux observables를 바꾸지 않는다. □

**필수 전제:** 개별 run의 class 법칙은 route에만 의존하며, source-subtick arrival 순서는 입력으로 주어지지 않고 고정 tie rule을 사용한다. 두 prefix 원소가 모두 `ready≤현재`여야 하며, run별 position/speed/travel-time observation은 원래 모델에도 없다. 실제 구현의 `1e-12veh` numerical completion charge 및 roundoff 차이는 별도 허용오차다.

### 정리 E3: certified coalescence의 미래시간 안전성 [DERIVED]
현재 eligible인 인접 동일-route `r_1,r_2`의 `ready_tick≤n`은 모든 미래 `n'≥n`에 대해 여전히 eligible하다. 따라서 둘의 `ready`를 `0`으로 바꾸고 질량을 합쳐도 이후 timestep의 head block 및 최소 자유류 하한 판정이 달라지지 않는다. 새로운 ingress는 old queue 뒤에 붙고 time-eligibility가 유지된다. 정리 E2와 결합해 경로별 수송 관측량을 보존한다. 서로 다른 route가 interleaving되면 절대 병합하지 않는다. □

### 정리 E4: 고정 상태 예산과 한정적 절감 [DERIVED]
기존 bulk `6NK+3K`의 모멘트 상태와 전체 ordered run `R`, maximum `B`에 대해 `R≤B`와 `O(NK+B)` 표현 요소 수의 상한은 유지한다. 새 알고리즘은 모든 성숙한 인접 same-route run을 하나로 병합하므로 `R_{after}≤R_{before}`이고, 적합한 긴 same-route backlog에서는 run 수를 크게 줄일 수 있다. 그러나 번갈아 나타나는 route sequence 및 미래 ready run은 이 변환으로 감소하지 않아, **모든 도시/수요에서 엄격한 상한 개선 또는 성능 향상**을 증명하지 않는다.

## R6 한계와 공격적 반례
- 서로 다른 route A/B가 교차 등장하면 순서가 교차로 통행에 실제로 영향을 주므로 병합하지 않는다.
- 같은 route라도 하나의 run은 `ready_tick>n`이고 앞 run이 eligible이면 병합하지 않는다(미래 도착시간 변경).
- 두 inbound link의 weighted merge에서 동일-route prefix를 나눴을 때 원 구현의 throughput이 달라지는 E1을 먼저 실패 테스트로 보존하고, 앞부분의 요청 집계만 수정한다.
- 자원 ledger, source pending, strict route-head prefix/ready delay, original checkpoint format/model_id와 clone of immutable state를 유지한다.
- 사후 coalescence만 추가하면 E1이 유지되므로 **먼저 node demand를 prefix-canonical하게 바꿔야 한다**.

## R7 경량 판별 검증 설계
- 동일 bulk `Y`, 동일 route inventory, 단지 eligible prefix run partition이 다른 두 queue를 비교한다. A/B turn flows, downstream mass, pending+completed, kinetic moment를 같은 numerical tolerance로 검사.
- A/B와 B/A 역전, red/green, ineligible head, queue budget, heavy homogeneous backlog, alternating-route low-compressibility 반례를 분리한다.
- 이미 공개된 baseline run tests(ordered FIFO 15개, network 19개 등)와 최근 Python/Rust 회귀를 바꾼 부분만 검증한다. New exact abstraction은 optional research mode, production Rust/V1은 건드리지 않는다.

## R8 판정
E1은 [REPRODUCED NUMERICALLY]이고 node dependency가 원인이다. E2–E4는 [DERIVED, CONDITIONS ABOVE]. 새 연구 알고리즘의 실제 throughput parity와 자원/속도는 코딩 검증 후에만 [IMPLEMENTATION VERIFIED]로 승격한다. 현행 unordered/ordered/partition-canonical 모형을 구분하지 않은 한 실제 도시 FIFO 수용으로 승격할 수 없다.

## R9 코드 계약
최소 변경 1: 기존 opt-in ordered model에서 sending candidate를 front single run 대신 maximal eligible same-route prefix의 총량으로 계산한다. 실제 service는 반드시 queue 앞에서부터 prefix consumption으로 실시간 장부에 계상한다. 상태를 버리지 않는다.

최소 변경 2: 새 명시적 opt-in `CertifiedAdaptiveFIFO` 버전에서 **현재 시각에 모두 eligible인 인접 동일-route** run을 합치고, 자원 예산과 checkpoint를 별도 model_id로 보존한다. 이 단계는 kinetic moment 및 physical node routing 규칙을 바꾸지 않는다.

Acceptance: same-run split/merged node flow parity, legacy FIFO red test, source ledger, Python/Rust node parity, deterministic checkpoint/replay, physical cap and lane-metres, overflow fail-closed, compared measured run count and walltime. Blind coarsening/time binning은 범위 밖.

## R10 저장·후속 실행
이론 보고서를 부모 FIFO 커밋 `61c6c73a715b61a7fbcf91dc3b4528ba2ca6518a` 위 별도 worktree의 stage commit으로 올리고 검증한 원격으로 push한다. 그 뒤 행동 RED→구현 GREEN, C1–C10 코딩, 자원/오차측정, 한정 receipt를 각 완료 단계마다 다시 push한다. V03 3×3×24h, real traffic observation accuracy 및 full network invariant entropy are NOT_RUN/UNRESOLVED. 원본 `main`·PR41 및 원래 `v1_road.rs` 수정/merge 없음.
