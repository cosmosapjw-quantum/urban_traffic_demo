# KCMB Ordered-Run FIFO: 병행 이론·코딩 연구 루프 R×C

작성 2026-11-19 KST. RESEARCH-ONLY. 앞선 kinetic-conservative 네트워크 모형을 확장하는 **옵트인 대안**이며 기존 V1/V03 교통 solver와 물리적으로 동일하지 않다.

## R1/C1 연구문제와 기준

기준 저장소 cosmosapjw-quantum/urban_traffic_demo. 직접 부모 commit 53ccbeef9986cd5a2fd1c9fa8defebceb636de42, 원래 V1 draft PR #41 head 0b9caa8cc60a3ba087722e0360b997c5dfb61d62. 분리된 worktree는 /home/cosmosapjw/worktrees/urban-traffic-kcmb-fifo-20261119, branch research/kcmb-ordered-fifo-20261119. 기존 roadmap의 100k 주민/3개 도시×3회×24h 수용문턱은 그대로이며 V03은 BLOCKED/0-of-9이다.

핵심 목표는 microscopic self-driven kinetic moments와 macroscopic finite-volume 보존 수송의 양쪽 물리를 유지하되 **물리적 shared lane 내부의 route arrival order**를 회복하는 것이다. 기존 6 moment에 이 순서가 없다는 원래 A/B 반례를 해결하고, 계산 상태의 예산·정확성의 trade-off를 구체적인 코드로 밝힌다.

## R2/C2 원전·재사용

Bar-Gera & Carey (2022), Constructing a cell transmission model solution adhering fully to first-in-first-out conditions, Transportation Research B 161:247–267, DOI https://doi.org/10.1016/j.trb.2022.04.002 는 perfect FIFO가 계산비용을 요구하며 benchmark reference로 유용함을 강조한다. Jin & Jayakrishnan (2005), DOI https://doi.org/10.1177/0361198105193400121 는 multi-commodity kinematic-wave의 FIFO 오차를 논의한다. Wright–Gomes–Horowitz (2017), On node models for high-dimensional road networks, 는 partial FIFO 및 실제 turning pocket의 차선구조를 논의한다. Farda–Balijepalli–Liu (2026)의 multiclass FIFO CTM은 single-lane/link 수준 cohort를 포함하지만 무작위 urban network에서의 모든 차량 추월 부재 증명이 아니다. 본 연구 결과를 원전 논문에 소급하여 귀속시키지 않는다.

기존 src/metroflow/v1/kcmb_network.py의 KCMBBoundedNetwork, progressive_junction, src/metroflow/v1/kcmb.py의 kinetic generator 및 Rust v1_kcmb_node.rs의 node allocator를 읽고 재사용했다. 위 파일들을 수정하지 않고 새 src/metroflow/v1/kcmb_ordered_fifo.py로 격리했다.

## R3/C3 상태·단위·경계

실제 방향 링크 i는 길이 L_i[m], lanes, capacity C_i[veh/s], 후방 혼잡파 속도 w_i[m/s]를 가진다. Route cohort a는 고정 path, target U_a[m/s], 차체 점유길이 b_a[m/veh], switching alpha_a/nu_a[s^-1], response tau_a[s]를 보유한다. 기존 bulk kinetic Y_ia=(m0,m1,j0,j1,z0,z1)의 여섯 비정규화 모멘트는 그대로 유지한다. j는 물리 속도 v를 U_a로 나눈 무차원 u의 모멘트이고, 6개 모두 차량량 단위 veh이다.

새 물리계산 상태에는 link별 (route_id, mass[veh], ready_tick)의 **순서 있는 run list**를 추가한다. 각 route별 run 질량 총계가 Y_ia의 m0+m1과 같아야 한다. 다른 route 또는 다른 ready_tick은 병합 불가하며, 이 둘이 모두 같은 연속 run만 병합한다.

신규 출입 mass는 step 종료 후 뒤에 붙고 ready_tick = entry_tick + ceil[L_i/(U_a dt)]로 정의한다. 기존 initial_profile은 그 initial mass가 이미 현시각에 출구 통과 가능한 물리 상태라고 별도로 선언할 수 있다. 타 upstream 링크나 source에서 같은 tick에 들어온 차량의 실제 서브틱 선후관계는 관측되지 않으므로 (node iteration, upstream-link ID, route ID)의 **결정적 동률 규칙**으로 순서를 정한다. 입장 전 source pending은 route별 총량이라 서브틱 departure FIFO를 복원하지 않는다.

## R4/C4 탐색 후보와 선택

A: 기존 고정차원 moment-only shared_head 및 independent_turn. 메모리는 작지만 A/B와 B/A 내부 순서의 물리적 차이를 식별 불가.

B: 원래 V1의 full history/packet 이력. 시간계보가 풍부하나 V03에서 head partial service에 의한 row 증식이 관측됨.

C: 선택된 ordered route runs + eligibility clock + 한정 run budget, exact adjacent run merging, fail-closed overflow.

D: bounded histogram/quantile 또는 epsilon-mixing approximation. 오차계약과 수치 관측 근거 없이 FIFO로 선언하지 않음.

E: future adaptive FIFO islands. geometry/turn pocket가 중요한 위치에만 고해상도 순서를 유지하고 나머지를 moment closure로 해상하는 후보.

## R5/C5 유도 및 정리

### 정리 F1: 유한비트 순서 정보의 필요 하한 [DERIVED]

차량 이벤트 2m개 중 A가 m개, B가 m개이며 각 차량의 운동상태가 같다고 하자. 모든 이항 route sequence는 같은 route counts와 같은 여섯 bulk kinetic moments를 가진다. 모두 green이고 출구 cap이 한 단계에 하나의 단위-event만 허용하는 strict FIFO 관측으로 나가는 route sequence를 관측하면 최초 sequence를 완전히 재구성할 수 있다. 따라서 **모든 순서에 대해** 정확한 출력시퀀스를 제공해야 하는 결정적 finite-bit state는 적어도 log₂ C(2m,m) bits의 정보가 필요하다. Stirling 전개를 적용하면 이 수는 2m − 0.5 log₂(πm) + O(1/m) bits이다. 즉 무한히 많은 route 순서 자유도를 같은 정밀도의 유한비트 O(K) 상태에서 전부 exact 복원할 수는 없다. 무한정밀 실수 인코딩이나 비한정 가용한 외부 event 기록은 본 정리의 전제가 아니다. 모든 압축 방식에 대한 새 strong universal no-go라고 과장하지 않는다.

### 정리 F2: conditional link FIFO + 인과적 도착시간 [DERIVED]

초기 queue가 물리적 단일 차로의 route-run order를 정확히 지정한다고 가정한다. 각 step에서 오래된 queue의 **front run만** 송출 후보이며, front가 완전히 제거된 다음에만 다음 run을 후보로 제시한다. 이번 step의 ingress는 모든 노드의 old-run service 이후 queue 뒤에만 삽입한다. 귀납적으로 각 link의 이번 step 출구 유량은 기존 queue에 대한 prefix service이며 뒤 run이 앞 run을 뛰어넘을 수 없다. 신입 mass는 same-step multi-link teleport가 불가능하다.

추가로 initial nonready 출입은 ready_tick까지 송출이 금지되므로 free-flow minimum T_free=L/U에 대해 T_eligible=ceil(T_free/dt)*dt ≥ T_free이고 0≤T_eligible−T_free<dt다. 이는 엄격한 최소 여행시간 하한이지만, 실제 속도 분포에 따라 더 느린 travel-time의 정량오차 상한은 아니다. Run별 운동모멘트는 저장하지 않으므로 microscopic per-vehicle velocity history의 정확한 FIFO가 아니라 **선택된 link queue order에 대한 exact route-head FIFO**다.

### 정리 F3: 운동모멘트·mass·node receiving의 결합 [DERIVED]

각 route bulk kinetic generator는 기존 Phi_dt=exp(dt A)이고 sending S_ia는 기존 min(M_ia, U_a dt/L_i * J_ia)와 link capacity의 합산 제한을 따른다. Node에서 실제 transfer f_ia는 아직 제공되지 않은 sending 예산, 현재 head-run의 mass/route, gate, downstream receiver의 count C_j dt와 free lane-metres R_j^m를 동시에 만족하도록 progressive filling한다. 수신 자원은 **pre-step** 여유로만 정산하며, 다른 node로 넘어온 질량은 현재 tick에 다시 출발하지 못한다.

하나의 route mass M에서 f가 송출되면 Y→(1−f/M)Y, 수신 또는 source 유입은 nonnegative multiple of its kinetic Y를 더한다. 정확 실수 산술에서는 mass ledger, queue-run total, moment realizability, nonnegative flow와 link storage가 귀납적으로 보존된다. 실제 float implementation은 별도의 조건별 mass/route-run·footprint·moment 검사로 확인한다. Node-local factorization은 독립된 downstream receiver의 물리적 tail node 소유권 때문에 이전 연구 정리와 동일하게 적용된다. 일반 최대 처리량·invariant entropy node solver 보증은 아니다.

### 정리 F4: run budget과 중단규칙 [DERIVED]

N links, K fixed routes, 현재 총 run 수 R, 명시적인 최대 B=max_runs라 하자. 이 구현의 저장 상태는 6NK+3K 개의 bulk scalars와 3R개의 label/mass/clock 필드이며 R≤B이다. 따라서 O(NK+B)개의 표현 요소를 사용한다. 이번 원형의 지역 node 계산은 필요한 old-run front를 반복적으로 서비스하기 때문에 시간 복잡도는 처리된 run 수와 node degree에 의존한다. **최악 run complexity가 demand 크기와 독립**이라는 주장은 하지 않는다.

새 상태가 R>B이면 FIFOQueueBudgetError를 반환하고 기존 immutable snapshot을 checkpoint로 첨부한다. 어떠한 mass도 출력에서 삭제하거나 사용자 몰래 coarse time binning하지 않는다. 이는 original V03 물리·8GiB·24h 완료를 보증하지 않고, 실패 상태를 bounded representation으로 정확하게 분류한다.

## R6/C6 적대적 검증 및 실제 수정

1. 동일 bulk moment에 A-leading/B-leading 입력: A red, B green이면 B 통과량은 0veh vs 0.25veh. 이전 shared_head는 0veh만, independent_turn은 0.25veh만 예측해 order-dependent observable의 전체를 복원하지 못했다.
2. 500개의 교대 0.02veh run에서는 부분 서비스가 선두에 약 1.7347×10⁻¹⁶veh의 IEEE 잔량을 만들어 다음 완전 녹색 step의 수송을 영구적으로 막는 **실제 RED**가 확인됐다. 완전히 served된 head의 0<잔량≤10⁻¹²veh는 오차질량까지 실제 transfer/receive로 예약하고 receipt의 numerical_completion_charge_veh에 기록하는 최소 수정 후 GREEN. 보정은 한 사건당 ≤10⁻¹²veh, event 수에 비례한 누적 오차예산이 생긴다. 문헌의 엄밀한 exact node capacity는 float 구현에서 이 작은 수치 한계 내에서만 주장한다.
3. preloaded 5×10⁻¹³veh run을 처리할 수 없던 경우도 **행동 RED→GREEN**으로, 10⁻¹²veh 이하 링크 내부 run은 입력 단계에서 numerical resolution 위반으로 거절한다. 서브해상 source 질량은 pending에서 누적·보존될 수 있으며, real positive mass를 잘못 지워 내보내지 않는다.
4. 연속 같은 route/ready_tick의 exact run 병합과 다른 ready의 분리, front signal 차단, fail-closed run budget, model_id과 checkpoint, 스토리지·차종 장부, randomized Python/Rust node flux 및 200step parity 검사.
5. 입장 전 pending route pool은 동시 source의 순서정보를 이미 잃는다. 그 부분의 완전 FIFO를 지원한다고 쓰지 않는다. within-tick 입장 실제 순서는 동률 가정이다.

## R7/C7: 직접 수행한 정량검증과 산출코드

- src/metroflow/v1/kcmb_ordered_fifo.py: new KCMBBoundedNetwork subclass, FIFOQueueState, OrderedRun, source/edge events and bounded run snapshots. 기존 kernel과 V1 authoritative files는 수정하지 않음.
- tests/research/test_kcmb_ordered_fifo_20261119.py: visible behavior, adversarial roundoff, random conservation, backend comparison, eligible time, overflow, checkpoint, invalid state.
- tools/research/bench_kcmb_ordered_fifo.py: synthetic ambiguity under two gate policies and run-count/latency comparison.
- artifacts/kcmb_fifo_20261119/python_fifo_probe.json 및 rust_fifo_probe.json: 실제 measured example. 이 데이터셋은 실도시 Field Data가 아니다.

## R8/C8: 한정 성능 결과

Synthetic single link, 4 steps, 서로 다른 ordered run 구성을 가진 경우. Rust는 **물리 kernel 전체가 Rust로 컴파일된 것이 아니라 Python 수송 + Rust node allocation**이라는 의미로 구별한다.

| initial run 수 | Python-node 중앙 tick[µs] | Rust-node 중앙 tick[µs] | 4-step 뒤 남은 총 run 수 |
| 1 | 104.00 | 101.13 | 5 |
| 100 | 316.52 | 217.19 | 75 |
| 500 | 987.71 | 631.41 | 338 |

500-run 첫 단계의 numerical roundoff charge는 3.47×10⁻¹⁶veh이고 최대 sampled mass ledger error는 약 2.13×10⁻¹⁴veh이다. 이는 source mixture, 순서복잡도가 다른 세 테스트이므로 동일 물리 문제 대비 acceleration factor로 외삽하지 않는다. Rust-node가 Python-node보다 빠른 것처럼 보이지만 호스트 소규모 측정의 불확실성과 프로세스 RSS는 별도 자료로 보아야 한다.

## R9/C9: 의도적 근사/관측 해석과 후속 코드 계약

지원되는 strict FIFO는 현재 모델의 **admitted within-link order**에 한정된다. Incoming multi-link tie는 선언한 sort rule을 따르고, outside pending arrival order/각 차량 위치/turn-pocket lane change/microscopic pair safety는 해상하지 않는다. Run마다 actual velocity 분포가 달라도 같은 route에 대해 bulk 평균 kinetic moments로 flux를 계산하므로 microscopic full car-following equivalence를 추정해서는 안 된다. 단일 차로이지만 교차로 일부에 독립 turning pockets가 있는 실제 도시에서 all shared-head blocking을 적용하면 과잉 spillback이 가능하다.

다음 실험 후보: (i) 실제 lane geometry를 근거로 turning pocket별 ordered cohort를 분리하는 adaptive island, (ii) ordered vs coarse 관측량의 cumulative-flow/Wasserstein·arrival p95 오차 대비 비용 측정, (iii) 실제 지도와 inD·UTD19 data의 시간방향 정합 및 holdout. 이를 검증 없이 production V1의 본래 model과 교체하지 않는다.

## R10/C10: 종료 경계

이론의 conditional proofs, native node를 재사용한 ordered FIFO 원형, 자원/수치 검증, 정확히 실패한 반례와 수정 결과를 별도 파일/브랜치에 보존한다. 완료 여부는 실제 pytest/Rust test/build/test receipts에 의해 결정하며, 원격 push·PR 생성·merge 및 V03 release campaign은 이번 실행에서 NOT_RUN이다. Native subagent 도구는 연결된 호스트에서 제공되지 않아 NOT_RUN이며 직접 직렬 검증을 수행한다.
