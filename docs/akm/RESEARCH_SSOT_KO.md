# MetroFlow AKM 연구 SSOT 및 유한 연구계획 v1.0.0

**2026-11-28 | Active Kinetic Mesoscopy (AKM)**  
연구 기준점: f3e13c2b0251f97c1fd5da601ab8995d44ec2f5c, PLAN v1.1.54.  
권위: 2026-11-28 사용자 요청에 따른 연구 방향, 연구 노드 선택 및 중단 기준의 정본. 이 문서는 구현을 기존 V03의 차단 사유에 종속시키는 연구 정책을 대체한다. 기존 V1 제품/수용/릴리스 계약은 `docs/v1/PLAN.json`이 담당한다. 두 문서가 서로의 범위를 침범하면 즉시 범위를 정리하고 결과를 수용하지 않는다. 이전 보고서·PLAN 내 historical positive_next_action·AGENTS의 V03 연구 순서는 보존된 근거이지 AKM 연구의 자동 실행 명령이 아니다. 본 문서 내 DAG JSON 블록만이 AKM의 기계 판독용 계획이다. DAG.mmd, DAG.dot, 실행 요약 및 영수증은 생성물/근거이며 독립 권위를 갖지 않는다.

## 1. North Star와 연구 질문

목표는 차량과 운전자의 목적지향적 자기구동을 비평형 확률과정으로 구성하고, 그 미시적 반응과 거시적 교통망의 저장/수송 제약을 mesoscopic 동역학으로 결합하여, 도시의 구조와 행태가 어떻게 혼잡·경로 선택·접근성·활동·장기 수요를 공동으로 형성하는지 설명하는 것이다.

1. Bottom-up: 연속 위치/속도, 유한 가속 및 반응, 주행 제어상태, 행동 class, 차간격·정보·상호작용에서 국소 generator 및 분포/모멘트로 간다. 현 상태에 의존하는 정지/재출발률은 명시적인 closure이며 실측 보정 전에는 경험 법칙이다.
2. Top-down: topology, 법적 회전, 유한 저장, 유입/유출 용량, 신호, 다중 시간척도, 활동·서비스·공간 제약으로 가능한 거시 수송을 규정한다. 이 환경은 다음 미시 반응에 실제로 돌아가야 한다.
3. Mesoscopic: 물리적 관측량의 적절한 집계, 필요 시 순서/age/passive mark 해상도, realizability와 수치 오차, 복잡도 상계를 동시에 설계한다. 차량 질량을 작은 조각으로 무한 복제하는 표현은 본질이 아니다.
4. Causal coupling: 완료 통행 관측과 유한 정보 → 지연 경로 선택 및 접근성 → 활동/입지/미래 수요. 물리 변화와 선택 변화의 효과를 paired experiment로 구분한다.

연구 질문: (Q1) 반응·상호작용이 fundamental diagram과 이력/혼잡을 어떻게 만든다? (Q2) 해상도에 따른 순서와 차종별 spillback의 오류를 어떻게 통제한다? (Q3) 제한된 정보에서 경로 선택은 혼잡을 어떻게 이동시키며 인프라 개입에 어떤 부호의 반응을 보인다? (Q4) 접근성 변화는 lagged activity/land-use를 통해 수요에 어떻게 돌아오는가? (Q5) 이 모든 것을 100k 주민과 24h 공유망에서 보존·재현·검증할 수 있는가?

비목표: 모든 미시 궤적의 전수 적분, 기존 부동소수점 순서의 전 모델 강제, 모든 관측량의 무한 정밀 복원, 근거 없는 MIPS/열역학 평형/운동량 보존/차량 안전성 주장, 실측 없는 calibration, GPU/RL 우선, 프론트엔드 미관 우선, 10초 전진 경쟁. 기존 결과는 삭제하지 않는다.

## 2. 역사와 재사용 계약

| 원천/계보 | 이어갈 성과 | 확대 해석 금지 |
|---|---|---|
| 0492364 PRD/spec/TRAFFIC_DYNAMICS_DESIGN/ROUTING_AND_LEARNING_DESIGN; 6524500 constitution | 도시·교통·접근성·행태, active pressure/queue/urgency, SI, deterministic replay, lagged update | 특정 packet 자료구조가 원동기라고 주장하지 않음 |
| 3ffc153 CTM, 3d83db0 active_meso/active_suffix | 동시 sending/receiving 및 정지–재출발 residence, 양의 Dijkstra 비용, bounded suffix | 이동/정지 상태를 실제 속도의 두 값으로 동일시하지 않음 |
| 123b220, 6f45a3c, 10737b2, 7d5e388 | finite response, 합법적/인과적 정보, gap/braking 비교, T02 | 특정 gap law나 local characteristic이 모든 충돌 방지/네트워크 안전을 증명하지 않음 |
| 23b200d,55e50ae KCMB | 연속속도 조건부 6-moment generator, positivity, kinetic corridor | 국소 generator closure를 비선형 advection/network closure와 혼동하지 않음 |
| T03/T04, exact packet engine, 0b9caa8 | 순서 민감 반례, birth/route/age 장부, 물리·수치 차단 구분, 정확한 국소 oracle | exact replay를 물리 진리 또는 production 필수 표현으로 강제하지 않음 |
| 862b288 sibling numerical policy | 공통 event boundary, release timing, subnormal 질량 결정의 의미 검토 | 현재 계보에 들어오지 않은 정책을 적용됐다고 주장하지 않음; blind cherry-pick 금지 |
| rank/receipt/delay, 11/26–28 연구 | causal projection, transport bound, dictionary, stable scatter, exact wire/recovery | 근사 별 identity, 이전 (M/4) 오해 재사용 금지, 전체 장기 오차 상계 미증명 |
| metroflow-headless 및 11/26 projected Valley | finite storage/receiving, class footprint, common-rank access, return owner, native CLI | projected vehicle 운송을 original 100k 전체 calendar 및 passenger/land-use와 동일시하지 않음 |
| native atlas, access compiler, phase runtime, routing, journey/observers | 지도/등록 entry·exit, 접근 법칙, 지연 경로·성장, 사람/차량/화물 분리 장부 | 개별 fixture의 scoped 기능을 완성 도시의 구현이라고 하지 않음 |
| MFWHOLE1–4 및 canonical digest | 별 모형 identity, semantic/byte 비교, transaction/restore, streaming 계측 | 타 모형의 bit identity를 요구하지 않음; 복구 없는 스냅샷을 checkpoint라고 부르지 않음 |

초기 Library 자료 `ACTIVE_MESOSCOPIC_TRAFFIC_RESEARCH_20261024_KO.md`, `URBAN_SUCCESSOR_TRAFFIC_20261024_KO.md`에서 자기구동/상호작용→지연→경로비용, no individual tracking, suffix 공유 목적을 대조했다. 당시 인용된 AXIOMATIC_FOUNDATIONS_KO.md v0.1 원문은 Git/Library 제목 검색에서 확보하지 못했다. 따라서 7개 관찰의 원문을 복원했다고 선언하지 않는다. 역사 원천과 해시는 `artifacts/active_kinetic_meso_20261128/R01_source_history.txt`, `R02_sources.sha256`에 보존한다(후자는 역사 기준 파일 manifest이지 이후 수정된 현재 tree의 manifest가 아님).

## 3. 새 모형의 이론 계약

상세 유도: [R01–R10](../research/ACTIVE_KINETIC_MESO_THEORY_20261128.md).

차종 c에서 실제 v=U_c u, u∈[0,1], drive 제어 σ∈{0,1}. U_c [m/s], q_e,c=min(1, speed_limit_e/U_c), τ>0 [s], α>0, ν≥0 [s⁻¹]. frozen 환경에서 u'=(qσ−u)/τ, 0→1 rate α, 1→0 rate ν. 거시 occupancy φ는 실제 점유 차로 길이/저장 길이. 첫 synthetic hazard ν=ν0+βφ², β [s⁻¹]. 선택한 식은 Bellomo-style active/kinetic 동기를 계승하지만 Boltzmann 이체 collision kernel에서 유도했다고 주장하지 않는다. 차종별 경로 위치에 6개의 모멘트 Mσ,Jσ,Zσ 및 birth B [veh·s]를 유지한다. 속도 모멘트는 normalized u를 사용하므로 모두 veh 단위. B는 시간표지 적분이며 조건부 birth-speed joint law까지 복원하지 않는다.

양의 측도에서 switching과 affine drift는 moment cone을 각각 보존한다. Symmetric S(h/2)D(h)S(h/2)는 frozen generator에서 local O(h³), global O(h²); nonlinear frozen coefficients와 transport splitting까지 포함한 전체 알고리즘의 2차 정확도는 미확립. 균질 q=1, α,ν>0에서 p*=α/(α+ν), stationary u ~ Beta(ατ,ντ), Var(u)=p*(1−p*)/(1+(α+ν)τ). ν=0 degenerate limit 별도. 균질 밀도 perturbation에 대한 velocity response −U p*ν_ρ /[(α+ν+iω)(1+iωτ)]. 이 이중 지연은 반응 구조의 후보이며 불안정성/MIPS 증명은 아니다. 균질 q=1의 정적 flux Uρp*는 ν=ν0+β(ρ/ρjam)²일 때 물리 범위 안의 φ²=(α+ν0)/β에서 turnover를 가질 수 있다. 주기 교란/비균질 검증은 D04/D05에서 수행한다.

### A. AKM-A (고정 support kinetic mixture)

도너 route-position 슬롯 i의 flux proposal min(M_i,h U_c J_i/L_e), J_i=J0+J1. 출구 총량과 각 목적지의 차량 수/차종별 차로 길이 quota를 동시에 제한한다. 현재 receiving은 pre-step free space × min(1,h wave_speed/L_f); 이 식은 임의의 정확한 physical wave law가 아니라 공급 closure다. 내부 이동과 source가 receiver quota를 공유하고 donor 공통 scale을 사용한다. 동일한 fraction으로 모든 모멘트 및 B를 전송하고 나머지를 유지한다. 동일 시각에 update, 한 step 다중 링크 순간이동 없음. 유입 및 유출의 합으로 비음성, route 질량, birth 및 storage를 보존하는 실수 산술 명제. 구현은 binary64 허용오차 내 검사, 모든 subnormal 조건부 모멘트의 엄밀 양성까지 보증하지 않음. Path registry 고정 조건에서 O(P+E+R) 상태·workspace·step work. 동적 route 추가는 별도 transaction. 현재 비례 혼합은 속도/age 선택적인 kinetic flux나 순서보존형 FIFO의 정확 해가 아니다. donor 공통 factor가 미사용 공급량을 만들 수 있다. 작은 A fixture는 수동 legal graph 선언만 가지며 일반 그래프 adapter는 미구현.

### B. AKM-B (finite-storage whole-batch queue)

검증된 Rust headless finite-storage/receiving과 common-rank access를 그대로 사용. 각 road의 active mean field p,u를 occupancy 변경 시 frozen generator의 정확한 평균 해로 갱신한다. admission 시 base finite-response passage/u_entry를 사용한다. 이는 frozen entry time-dilation approximation이며, 분포의 평균 first passage나 시간변동 density의 정확한 개별 속도 적분은 아니다. class footprint와 순서, return/event ownership은 기존 queue에서 유지. Whole-batch head blocking 및 departure mesh의 수치 편향은 별도 측정한다. B의 projected full-day receipt에는 도시 전체 state checkpoint/replay가 없다. 초기 원본과 다른 archive schedule의 scope를 유지한다.

### C. Detailed reference, D. Bounded alternate

C는 기존 exact packet, rank/receipt/delay, gap, CTM 등 비교 및 반례용. 실패 frontier를 보존하며 유효한 범위에서만 oracle로 쓴다. D는 sparse OD/finite agent/ordered hybrid 중 필요시 최대 하나 선택할 독립 fallback (관측 가능한 OD/지원집합을 바꾸면 모형변경 명시). 미시 실험은 통계 생성 과정의 검증을 위해서만 개별 궤적을 표본화한다. 도시 solver의 개별 위치 전수 추적으로 되돌아가지 않는다.

## 4. 이번 R01–R10 및 C01–C10의 증거

R/C 20개 단계는 한 번의 제한된 연구 수행의 단계 수이며, 20개 생산 모듈 또는 V1 DAG 20개 노드의 최종 수용이 아니다. 이론 문서 및 실행 기록은 단계별 실질 산출물을 묶어 milestone commit으로 게시했다. 개별 단계 20개 push로 보고하지 않는다.

| 단계 | 이번 완료 범위 | 근거/상태 |
|---|---|---|
| R01 | 원동기 및 계보 재정초 | source history; scoped |
| R02 | 문헌/구현 조사, 재사용 매핑 | theory R2, source manifest; abstract/introduction level |
| R03 | PDMP/6-moment 유도, 단위 및 가정 | theory R3; derived |
| R04 | A/B/C/D 경쟁 가설, 선택과 배제 | theory R4; derived/conjectural |
| R05 | positive switching+affine drift 및 보존적 유한 support 명제 | theory R5; derived under stated assumptions |
| R06 | turnover, 두 시간척도 response 및 반례 | theory R6; derived, network instability unresolved |
| R07 | 독립 유리수, RK4, 유한차분 및 Rust 미시 표본 | R07_independent_oracle.json, R07_micro_pdmp.json; checked |
| R08 | 근거/오차/미검증 가설 분리 | 본 문서 §§3,5; scoped review |
| R09 | 계산 계약과 2개 독립 구현 경로 | theory R9, Rust code; implemented scoped |
| R10 | 유한 계획/재개/종료 정책 | 본 SSOT; scoped |
| C01 | parent 고정 및 기존 코드 inventory | 4bd91ee, R01/R02 |
| C02 | active kinetic public interface 및 normalized moment | active_kinetic.rs; scoped |
| C03 | positivity·moment·density contract, old queue reuse seam | theory+active_kinetic.rs/queue.rs |
| C04 | 반례/독립 oracle 및 TDD 기준 | C05 red/green, R07 |
| C05 | 실제 local kinetic 구현, behavior RED→GREEN | 32762b3, C05_kinetic*.log |
| C06 | fixed support multiclass 동시 network transport | 6160f28, C06_network_test.log |
| C07 | projected Valley active mobility arm | 859e11f, C07_active_city_tests.log, C07_input_provenance.json |
| C08 | synthetic 12 cases, delayed policy, restart, projected 8h/full-day 대조 | bb0484b 및 C08_*; initial probe failure 보존 |
| C09 | microscopic event experiment 및 Rust headless 재시험 | d2edb3e, R07_micro_pdmp.json, C09_* |
| C10 | 결과 cross-check, 새 연구 authority, DAG 검증 및 복구 가능한 closeout | C10_RESEARCH_RECEIPT.json, DAG generated views, backup manifest |

## 5. 실험 결과 및 실제 미해결점

* 국소 미시–모멘트: 1024 exact rational atom pushforward, 1024 quota cases, 96 RK4 mean cases (max abs 4.33e−15), 99 flux derivative finite differences; 독립 주기 occupancy perturbation 세 주파수의 두-pole complex response 상대오차 최대 1.40e−6. Rust microscopic PDMP 100000 trajectories/time, t=10,200s, deterministic seeds. Stationary analytic mean .4, var .12; sampled mean .399183, var .119801. Six bounded statistics within predeclared Hoeffding joint envelope .005954 plus discretization tolerance (conditional IID bound, not proof of PRNG IID). Fine dt .005/.01 difference max 5.74e−7.
* A: synthetic four-road/four-route/two-class 12 slots; twelve cases 1200,3600,86400s including weekday/weekend, closure/baseline, active off, 1/10/100 demand amplitudes and dt refinement. All reached requested horizon; residual mass at most 1.70e−10 veh, birth residual at most 1.26e−6 veh·s, max storage within bound. Hot advance 0 alloc/0 realloc after initialization; first measurement included status String allocation and failed, corrected measurement boundary. Two actual mid-state restart byte identities (600→1200 and 43200→86400). Full-day closure mean of completed journeys 833.770s at dt5 vs 892.470s at dt2.5; 7.04% relative to coarse, a scientifically material resolution gap. Closure vs no closure 833.770 vs 154.572s; this is model-specific synthetic intervention not real bridge proof. Positive pending at 100× ≈36548.640 veh, retained rather than removed. Last active tail remains even in low amplitude runs.
* B: archive network SHA af8a0c16e2bd31d4a42282e83d076ea10075e6cbe0bb3982dfb5978cfa9f72a5, passages SHA a310ee706ae3eb64ba35eef2c9275da38141dbd32eb89f86bcb6a90c89bd73c1. 1586 links, 38916 paths, 796098 archived subcohort groups; 3182886 initial batches in this run. 8h 10.24s wall; 24h active 91.37s wall, RSS287760384 B, zero interaction 93.45s wall, RSS289087488 B. Both completed all projected vehicles (car57095.9403264, freight.998825, bus24; no remaining active); β=0 result payload (except added active stats) exactly equals 11/26 baseline receipt. Car completed mean 798.447→807.691s; extra passage allocation 664429.278 veh·s (not necessarily additive to realized total trip time); max storage .999999827, max receiving .999982174. 1200s departure mesh, fixed paths, older archive scope. No claim of calibrated real effects, matched current original schedule, complete passenger/land-use coupling, active-city refinement, or city restart. Timings one run each on shared host, not proven speedup.
* Native headless Rust tests: 14 lib + 1 bin, no Python/C++ core dependency. Original native tests 304 historical, not rerun for unmodified exact engine. No full CI/main merge. Independent algorithms (Fraction/RK4/microscopic) are not independent agents. Native subagent unavailable.
* Original acceptance remains 19/21 implemented/scoped or accepted, 5/21 accepted; native Rust scoped 14/15; V03 original full day 0/9, 8h refinements 0/3, original exact frontier25750s, adaptive branch25760s (junction event cap), adaptive delay32820s. AKM B result is not a V03 PASS. R01–R10 and C01–C10 do not change this.

## 6. 연구 프로그램의 진행 방식: Anti-drift와 Anti-local-minima

매 연구 회차에는 아래 네 항목을 짧은 하나의 receipt로 기록한다. 이를 별도의 연구 과제로 늘리거나 반복 감사하지 않는다.

**AD1 목적 추적:** 원래 Q1–Q5 중 실제로 답한 질문, 필요한 물리 관측량과 반증 기준, 해당 historic blob/commit. 단순 record 감소·guard 통과·모의시계 이동은 독립 과학 결과가 아니다. 구체적 물리 결과/오차와 연결하지 못하면 reference 보수로 분류.

**AD2 의미 보존:** 입력/관측/가정/단위/모형 identity, source 및 birth/active/pending/completed(사람/차량/화물) 장부, causal time·합법 경로·물리 공급/저장, 관측 가능한 departure/arrival/age, 개입 조건을 확인한다. 바뀐 closure와 quotient를 명시하고 판별 실험을 사전 고정. 다른 모형에 bit parity를 요구하지 않고, 같은 알고리즘의 restart/serialization에만 요구. 과거 승인된 수치 정책을 다시 읽되 자동 복귀 금지.

**ALM1 자원 배분:** 다음 준비 노드에서 과학 가설과 관측 실험 우선. 구체적인 exact reference가 필요한 경우에만 한 bounded diagnostic를 수행하며 한 epoch 작업량(실제 구현·실험·분석 시간)의 15%를 원칙적 상한으로 둔다. 운영상 불가피한 초과는 이유와 시간 기록, 다음 epoch에 자동 이월 금지. 사용자 명시 요청은 별도 scope. 보호 기준은 원래 외부 budget; 내부 guard 변경은 명시적 진단 또는 새 identity에서만. 물리 보존/무결성 위반은 즉시 중단.

**ALM2 유한 판정:** 같은 blocker를 고치는 두 번의 차별화된 시도(각각 하나의 원인 가설 및 측정)에서 새 과학적 관측·오차/복잡도 법칙 개선 또는 유효 물리 시간대 진입 중 아무 것도 얻지 못하면 그 candidate의 해당 접근을 STOPPED로 보존한다. 단순 threshold 변경, 같은 원인으로 늘어난 horizon 수치, 새 blocker의 명명만으로 새 시도로 초기화하지 않는다. 원인을 바꾼 대안 하나를 선택하거나 D11 결정으로 간다. 모든 실패/미완료를 보존하며 성공 기록으로 대체하지 않는다. 적대감사는 1 primary pass + 위험에 근거한 1 independent check로 끝낸다. 검증 자체의 재귀 감사 금지. 후보 A/B 두 개, fallback D 최대 1개(추가 후보는 이 버전 종료 후 사용자 결정). 

**실험 계약**: 실험 전에 model/closure, 입력 digest, seed, dt/mesh, comparison domain, 단위/관측 정의, 허용오차, wall/RSS 및 실행횟수, 판정과 실패 처리 기록. 기존 V1 허용오차 유지; 연구 노드에는 사전 등록한 판단 기준을 따로 둔다. 예: underloaded T04 의미의 mean max(1s,2%)와 overload 미완료/curve ≤2% demand를 적용 가능한 동일 물리 문제에서만 사용. 과부하 평균 통행시간만으로 그 gate를 대신하지 않음. A의 day gap은 이번 negative evidence로 남기고, D05에서 새로운 finer ladder 및 congestion observables로 검증. 외부 CTM/LTM과 비교는 동일한 flux/가정/실험의 한계에서만. 동일한 run에 대한 재계측과 새 물리 experiment를 구분. Actual wall/RSS, support scaling, native code and semantic provenance. No test count, stage count or forecast of future work as completion.

**다음 작업 선택:** 한 회차 기본 단위는 DAG의 준비된 노드 하나(독립 파일 소유권으로 최대 2개). R1–10/C1–10은 사용자가 선택할 때의 수행 형식이지 무한 재시작 trigger가 아니다. 최초 D04/D06 READY에서 아래 후속 회차를 수행했다. 현재 기계 판독 DAG의 READY 노드만 선택한다. 기존 연구는 reference lane으로만. 정상 완료 시 새 자동 cycle 금지. DAG 수치/성과는 이 문서의 scope 별로 보고하고 original release readiness와 분리한다.

## 6.1. 2026-11-28 후속 S01–S10: D04/D06 first attempts (status update, no policy change)

D04 VERIFIED_SCOPED: exact geometric/negative-binomial residence law, 16 actual free-flow pulses, active relaxation pulse, FIFO AB/BA counterexample, metre supply and positive velocity-selective flux. Sharp third moment uncertainty width <= M/16; 4096 independent rational tests. Prior two-pole response bound reused. No global jam-wave convergence. D06 VERIFIED_SCOPED **input/owner coupling only**: original 918450-leg manifest and native access/service/journey ledger retained; fixture 120/360s and migrated Valley25320→25380→25560→26160s actually run; separate AKMFULL1 identity, independent bit recovery. D06 gate concerns adapter/ownership and explicit discrepancies, not all-demand completion. 610820 inherited unsupported legs remain pending, and missed bus return (2 persons) is a falsifying observation for naive mixing as a transport replacement. No V03 credit. Both nodes consume one attempt each, D05 now READY. Full-day candidate selection and D09/D12 remain unexecuted.

**AD1** Q1/Q2: distinguish temporal/spatial dispersion and kinetic selective flux, actual active slowdown and order counterexample. Q5: original calendar and physical owner bridge, actual morning segment and return connection evidence. Historical roots from 0492364/6524500/3d83db0 bound in S01_history. **AD2** positive mass/birth/route positions and source/return/service ledgers checked; migration intentionally loses rank and within-link distance, separate identity; authored hazard/wave speed, no cross-model bit parity. **ALM1** zero new exact reference ticks and zero old guard changes; only archived exact input load and historical comparison. No precise time-fraction claim for the tool/review effort. **ALM2** one bounded attempt each with preset matrix completed, no guard chase or blind reruns; retain fixture declaration and compiler failures as implementation errors. Next D05 must address actual residence/return effects, support/history growth and two-closure comparison, not repeat native frontier runs. Use the remaining finite DAG, no automatic additional cycle.

Evidence: [theory and execution notes](../research/AKM_OBSERVABLES_OWNERS_20261128.md); `artifacts/akm_observables_owners_20261128/S09_audit.json`, `S10_RESEARCH_RECEIPT.json`. Original PLAN v1.1.55 byte-identical. Native code research feature only, Caution for research use, not ready for product/release.

## 6.2. 2026-11-28 D05 first attempt: closure refinement and service interface

D05 remains READY with attempts_used=1/2. All S01–S10 research steps performed; this does not make the physical convergence gate pass. A comparison uses 20 actual synthetic cases including 6 full-day runs (5/2.5/1.25s, two policies), 12 overload runs and 2 fixed-offer controls, plus 8 pulse cases. One-pass residual allocation and velocity-selected flux separately satisfy local feasibility/realizability; the combined A variant fails the day mean refinement gate more strongly than baseline (9.271% vs 2.531% finest adjacent gap), so retain its kernel as scoped research but reject it as current resolution solution. B same projected archive AM horizon 28800 at mesh1200/600/300: mean gap .0179%, sampled completion/incomplete gap .0647% at finest adjacent comparison; peak storage and receiving gaps .03009/.23057 remain significant. B is preferred projected fixed-route comparison, not original-calendar bridge or converged network congestion.

One optional D fallback family: whole scheduled-bus characteristic with deterministic same-link bus order, no all-class FIFO claim. Actual same-manifest fixture at dt1: both buses blocked on metre quota, 16 persons complete (mixed 18). Distinct diagnostic dt.5 and dt2: 16 and 20 persons respectively, both buses complete at dt2, arrivals46/76s. The strict atomic method is inconsistent as dt->0 under fixed positive supply; do not change quota, schedule or step solely to obtain a pass. Active-track checkpoint at t36 and actual split replay to360 bit-identical with direct dt2; corrupted track and wrong model rejected. Original-city 25320->25380 no-bus compatibility control and independent recovery match previous A owner ledger, not new science frontier or city bus validation. Earlier 26160s A state remains valid for its own identity. Interface partial reservation law with strict slack derived and independently checked in 512 rational cases, not integrated. This is the selected next constructive mechanism of the same D family, not a new fourth candidate.

**Next final D05 attempt**: implement bounded interface crossing state (upstream remainder, receiving reservation, whole logical bus, causal finite-distance progress) with no credit borrowed from future; validate actual same fixture h=.5/1/2, partial entry/exit recovery, count/metre/birth/parent ledger, competing merge and strict slack negative case. For A compare actual joint spatial/temporal refinement and factorial selective/residual ablation at matched geometry; for B use one finite predeclared finer congestion window with matched release/arrival and receiving observations rather than re-running identical archive. If no candidate has physical improvement within remaining attempt, reject/redirect or terminal stop according to D05/D11 dependency rules. Do not rerun guard chase or automatically begin D07. No full-day original V03 credit.

**AD1** Q1/Q2 physical flux/residence, congestion peaks, timed transfer and counterexample. Historical source blob IDs in S01. **AD2** original inputs, no changed cap/timetable, distinct identity, actual conservation and replay; diagnostic dt changes explicit. **ALM1** zero new exact reference ticks, bounded historical-source compatibility control only. **ALM2** one D05 attempt consumed; physical failure preserved and remaining attempt targeted. All original V1 PLAN v1.1.55 bytes unchanged. No native subagent available; independent numerical and wire checks instead; no full CI or main merge.

Evidence: [theory and implementation report](../research/AKM_D05_TRANSPORT_20261128.md); `artifacts/akm_d05_transport_20261128/S09_audit.json`, `S10_RESEARCH_RECEIPT.json`. Release verdict CAUTION_RESEARCH_ONLY.

## 6.3. 2026-11-28 D05 final attempt: reserved boundary and bounded closure decision

D05 VERIFIED_SCOPED, attempts_used=2/2, no further attempt. D04/D06 prior scoped evidence unchanged. D05's terminal decision is NOT a whole-model convergence PASS: all four A policies fail joint spatial/temporal day criterion; 22/24 actual runs completed and two moment-cone failures at 28217.5/28216.25s preserved. B projected mesh300/150 seven stamps: mean gap 0.003218%, completed gap 0.07278%, peak storage gap .010942, receiving .028614 > .02 diagnostic gate; B remains projected comparator, not production. D reserved interface (AKMFULL3) selected only as scheduled-service subclosure: original dt1 and distinct .5/2s diagnostic manifests all complete 20 persons,13.06 vehicle-equivalent,100kg, both buses, arrivals44/74.5,45/75,46/76s. Source t31 and sink t45 (separate .5veh/s exit diagnostic) partial checkpoint recovery and split/direct continuation bit-identical. Competing merge consumes current quota, exact slack control retains partial carrier, no fictitious service completion. No cap, original timetable or V1 release gate change. Old AKMFULL1/2 fixture bytes unchanged. D retains unvalidated proportional fluid car/freight; no original active-bus city run or full-day convergence. Reject A whole-network convergence solution, retain local kernels; B for comparison; D scoped service research, no production candidate selection. This is a physical result enabling the next distinct research question D07, not an invitation to retry D05.

User architecture instruction (2026-11-28): retain Rust backend / Python frontend. Physical solver, observation, ownership and persistence logic stays Rust; Python UI/receipt presentation and independent mathematical oracle only. Native dependency and ldd checked; new read-only Python UI adapter has 3 passing tests; no claim production GUI integration.

**AD1** Q1/Q2 same physical inputs, real service resolution and counterexamples; original historical blob IDs in S01. **AD2** separate model identities, conserved physical boundary increments and logical owners, raw negative evidence; partial sink reservoir is not completed service. **ALM1** zero new original exact ticks/cap changes, no exact time-fraction measurement. **ALM2** D05 bounded two attempts exhausted; do not repeat same closure refinement loop. Next D07 use scoped selected interface service plus explicitly identified comparator/limitations for causal legal routing and paired infrastructure intervention, not unsupported production claims. D09/D11 retain global transport and history, unsupported demand, exact-slack and cross-class fairness obligations. No D07 execution in this turn. Original PLAN v1.1.55 byte-identical. Full CI/main merge not run. Native subagent unavailable, independent arithmetic/wire audit instead.

Evidence: [D05 final theory/implementation report](../research/AKM_D05_FINAL_INTERFACE_20261128.md); `artifacts/akm_d05_final_20261128/S09_audit.json`, `S10_RESEARCH_RECEIPT.json`. Verdict CAUTION_RESEARCH_ONLY.

## 6.4. 2026-11-28 D07 attempt 1: causal path choice and graph intervention

D07 VERIFIED_SCOPED, attempts_used=1/2. Fixed-set path-size logit TV sensitivity <= epsilon/(2Theta), conditional regret bound and one-medium-step linear Schur threshold lambda*g<1 derived, 2048 logit/1620 root cases independently checked. Rust bounded synthetic reserved-cohort lab reuses D05 interface increment, positive kinetic mean distance, existing Information/Routing. K=3 exhausts lab candidates; separate existing router K4/K8 legal turn tests. Graph installation changes actual physical support at t300, removal rejected at540 while live commitments use link, accepted after drain at1800 in all six bypass runs. Same owner/birth/prefix and current quotas; physical suffix changes only at ready and unreserved boundary; no future data, actual completed link passage windows and separate observed no-entry signals. 40s latency,80s age,20s medium, blackout420..540 leads prior fallback500..560. All nine finite matched 1800s cases complete all 300/150/75 fixed births. Source-only no-bypass vs installed bypass vs ready reroute means 145.1167/120.5667/84.4033 (gap2),77.2467/69.6267/69.0667(gap4),67.6667/64.56/50.36(gap8). 115/13/6 actual changes (111/13/6 distinct owners). Reroute-vs-bypass gap2 harms128 despite improving mean, gap4 harms33 improves14, gap8 bypass-only harms2 with max+107s. Not a Pareto improvement, Braess proof or induced-demand experiment. Policy enabled from t0, not just after installation. Actual independent 440s partial checkpoint replay and resume byte identity; selected malformed/future controls rejected. Original native calendar and scheduled bus owners not coupled in this lab; no 100k scalability or physical convergence claim. D05 limitations unchanged. New D07 wire AKMD07LAB1, not AKMFULL3 or production. Read-only Python receipt adapter extended; all physical/routing logic Rust. D07 closes scoped question; no identical repeat.

**AD1** Q3 infrastructure intervention, lagged information, distributional effects, historic source IDs and actual passage journals. **AD2** same source births and physical coefficients except explicit graph/policy, owner/prefix and quotas preserved, graph identities/replay, finite mean characteristic cohort approximation disclosed. **ALM1** zero new original exact ticks/guard changes, no time-fraction measurement. **ALM2** one bounded attempt; D08/D09 ready separately, no auto execution. Original V1 PLAN v1.1.55 byte-identical. D08 next recommended: reuse lagged growth/phase law for at least two slow epochs, paired frozen/endogenous demands with population/activity source ledger, use D07 accessibility only within its valid scope; no same-tick feedback. D09 separate one-original-city pilot with existing external limits; D07 small lab does not establish integration. Full CI/main merge not run. Independent native subagent unavailable; direct execution and independent artifact/oracle audit. Verdict CAUTION_RESEARCH_ONLY.

Evidence: [D07 report](../research/AKM_D07_CAUSAL_ROUTING_20261128.md); `artifacts/akm_d07_causal_routing_20261128/S09_audit.json`, `S10_RESEARCH_RECEIPT.json`.

## 6.5. 2026-11-28 D08 attempt 1: native lagged LUTI and Rust-first entry

D08 VERIFIED_SCOPED, attempts_used=1/2. Existing D07 World adapted to explicit birth registry (old fixed-gap wire byte identical), existing M04 Growth/compile_accessibility reused without duplicate solver. Four paired synthetic arms, 3 actual drained fast windows each, 2 slow updates each; same external increments25/25, 150 initial residents, one authored site50 capacity, access threshold72s, fast1800, slow3600. No bypass: placed150 each, pending0/25/50, trips150, mean77.2467s. Bypass+ready reroute fixed: placed150/175/200, trips150/150/150, explicitly inactive0/25/50, means69.0667s. Endogenous: placed150/175/200, trips150/175/200, means69.0667/49.8114/49.925s; 525 total trips and29062 veh*s vs frozen450 and31080 veh*s. Nonmonotone response depends on changed birth timing, routing and scenario, not general induced-demand or welfare theorem. Observations at1800/5400/9000 and growth3600/7200; population/activity/age ledgers independently verified. Partial slow checkpoint after first drained window recover/resume byte equality; invalid stamp/stock/birth/config rejected. No occupied-traffic reset or hot swap. Single origin one-way synthetic work model, authored threshold/inflow, not full original calendar, empirical calibration or full city LUTI. Prior D05/D07 limitations retained.

Rust-first correction requested by user: previous native atlas generation, v1_prepare_city and v1_calendar reused through metroflow-native-city CLI. Real Valley100k fresh generated city and manifest match older Rust backup exact bytes; 918450 calendar legs,120000 person trips,58801 veh-equivalent,1000kg. Historical 100010-person grown snapshot also re-prepared exact bytes,120004 persons/58802.96 veh/1000kg. This is actual preparation, not a new full-city growth feedback or original acceptance run. Prior modules' blob IDs verified; not wholesale stale source restore. S06 receipt null identity corrected S07 static identity, reverified. README previously named Python authority; corrected current authority and labelled old notes historical. Python v1 lazy compatibility facade; native command aliases and default run --manifest calls Rust exact; AKM optional research mode, missing native binary fails closed, explicit oracle only. Actual python -S frontend executed native D08, original exact120s fixture (20 people complete), AKM interface360 fixture same previous bytes, historical-next city prep same bytes. Native Rust324 passed/2 ignored, headless20, Python13 passed incl explicit historical oracle. Historical Python test opt-in failure diagnosed and corrected test environment only. Current source census Rust40391/Python96567 physical lines (29.49% Rust); prior historical 13/15 functional coverage is not a new whole-repo coverage claim. Remaining large Python legacy APIs not migrated globally, no full GUI or CI acceptance. Native dependency tree/ldd no Python runtime.

**AD1** original lagged land use/transport motive, actual accessibility/stock/activity and historical code provenance; explicit architecture correction. **AD2** strict lag, exact old artifacts and actual source/demand ledger, separate synthetic identity; conditional outcomes not calibration. **ALM1** zero new original city exact ticks or guard changes; time fraction not measured. **ALM2** one D08 attempt, finite scoped decision, no automatic D09. Next D09 READY: use existing original calendar/owner paths and Rust native-city/CLI, assess actual shared transport AM/PM/24h and restart within original limits, preserve D05 convergence/owner history and D07/D08 small-lab limitations; no V03 acceptance without authorized candidate. Native subagent not available; direct execution and independent arithmetic/receipt audit. Original V1 PLAN v1.1.55 unchanged. Verdict CAUTION_RESEARCH_ONLY.

Evidence: [D08 report](../research/AKM_D08_RUST_LUTI_20261128.md); `artifacts/akm_d08_rust_luti_20261128/S09_audit.json`, `S10_RESEARCH_RECEIPT.json`.

## 6.6. 2026-11-28 D09 attempt 1: structural support and bounded pilot

원본 Valley 100k의 918450 calendar leg (120000 person trips, 58801 vehicle-equivalents, 1000 kg)를 실제 Rust native owner registry에서 분류했다. 610820 legs에 direct support가 없으며, day profile 및 parent eligibility를 포함한 낙관적 완료 상계는 72115.96491075 person trips, 미완료 하계는 47884.03508925 (39.90336%)다. 이 값은 PM/day simulation 실측이 아니며, 원본 demand 보존과 수송 support 충족은 별개의 조건이다. 고정 버스와 interzonal noncar의 결손은 mode substitution 또는 수요 삭제로 해결하지 않는다.

기존 Rust observer-guarded entry/egress, schedule/stream receipt, delay calendar를 D05 reserved interface에 재사용하여 distinct identity `akm-native-reserved-interface-clock-v1`를 구현했다. 시간 cell quotient의 양의 질량/1차 모멘트 보존과 적용 한계는 S02, 실제 fixture history 1012→15 및 split/direct byte parity는 S05. 원본 source 25320→25380 matched AM에서 사람/차량/화물 ledger 및 road mass/birth는 정확 일치, class offered 최대 차이 7.16227e-12 veh (roundoff). Road rows 624850 동일; journey records [1833556,287095,55921,59571]→[876091,149339,55921,2121], checkpoint 146702340→110736097 bytes. Cross-closure byte identity는 주장하지 않는다.

Fresh day target86400은 실제 25430s에서 중단 (wall66.712s, peakRSS1122936KiB, 4 physical scheduled buses exited, 953296 road rows, 232.037652veh active); migrated target86400은 25470s에서 중단 (continuation wall25.485s, peakRSS1102936KiB, 959509 rows). 양쪽 failed committed state 독립 byte recovery 성공. 한 번의 분류 tick은 1004024 rows > 기존 1000000 cap, Resource, rollback bytes 동일. 실제 road census: 50728 tags, mass≤1e-9veh rows 173429 (18.1926%), 총 1.423480515e-5veh, birth 0.3588279568veh*s. 미세 양의 support는 삭제하지 않았다. 기존 A migrated 26160 및 D05/D07/D08의 한정 범위 증거는 유지. D09 claim gate는 미충족, PM/24h NOT_REACHED. 내부 6GiB/1M과 외부 8GiB/7200s 변경 없음. Rust-first CLI `--engine pilot` 명시 선택, default exact 유지; Python frontend 표시만. Tests 325 native passed/2 ignored, headless20, Python15; full CI/merge 미실행.

**D09 READY, attempts 1/2.** 마지막 시도는 동일 D family에서 보존적 finite-propagation/route 또는 temporal support 표현을 실질 변경하고, mode/service별 미지원 범위와 parent obligation을 명시해야 한다. 단순 cap 증설, tiny-mass pruning, blind resume 또는 새 후보 우회 금지. 원본 support 해결 및 실제 24h/restart gate를 만족하지 못하면 STOPPED/redirect, D10은 자동 시작하지 않는다. 자료: [연구보고서](../research/AKM_D09_CITY_PILOT_20261128.md), `artifacts/akm_d09_city_pilot_20261128/S09_audit.json`, S10 receipt. Verdict BLOCKED_D09 / CAUTION_RESEARCH_ONLY.

## 6.7. 2026-11-28 D09 final attempt: sealed finite cohorts, terminal nonacceptance

D09 final attempt2/2. Same D reserved-service family, new research identity akm-native-reserved-sealed-cohort-clock-v1 / AKMFULL4. One sealed active mean-distance fluid cohort plus one waiting aggregate per route-position; waiting footprint counted and no reset of moving batch by new arrival. Reuse existing Rust kinetic react_with_distance, reserved bus interface and prior native clock-cell journey quotient; no exact source migration, no mass pruning or cap increase. Conditional finite local drainage derived and4096 rational cases; native two-link pulse, quota and malformed progress checks. Actual fixture360 completes20 persons/13.06veh/100kg, old road rows3/history15 ->0/5, same-identity partial31 recovery/split-direct bytes; old pilot360 bytes unchanged. Free-flow 100m/10m/s second .125veh arrival3s later: h=1/.5/.25 actual extra delay7s each vs independent single arrival. Batch synchronization has a nonvanishing physical error; not a convergent arbitrary-arrival model or strict FIFO.

Original fresh Valley25430 matched comparison: old953296 -> new371733 support (including45477 waiting; -61.0055%), <=1e-9veh rows173429 ->0; same requested1277.77778/released734.50874 persons, completed6.71027 ->5.31628; road mass232.037652->239.668978veh. Four physical buses completed, no passenger-coverage equivalence. History26206->3239. New wall61.455s/RSS821364KiB vs old66.712s/1122936KiB (shared host, no controlled performance claim). Continuation toward86400 reaches26310, peak900304 below unchanged1M, final882264 incl55272 waiting, waiting51.177645veh, active1175.013227veh, <=1e-9 rows0. Persons requested6166.66667/released3672.54368/completed1324.83668/active2347.70700/pending2494.12299. Stopped by assistant-chosen180s advance slice (actual180.978s, wall190.239s, RSS1502732KiB), NOT a resource guard or full external7200s trial. Total fresh+continuation wall251.693s, no PM/day verification. Both checkpoints independently byte recovered, full-city direct/split trajectory not run. No conclusion of later full-day performance/no-go. Original 24 fixed one-run buses 960 aggregate seats vs30000 passenger intents; prior actual owner admission bound47884.03508925 person trips/day uncompleted and610820 unsupported legs retained, no mode substitution or extra fleet; independent seat bound not new calendar. Original D05/D07/D08 limitations unchanged.

**D09 STOPPED, attempts2/2**, not verified-scoped node acceptance. Physical evidence and failed gate kept. **D10 BLOCKED_TERMINAL, attempts0/2** because successful D09 is prerequisite; no holdout claimed or executed. **D11 READY** distinct decision: compare A/B/D physical and computational Pareto/claim matrix including negatives, select one only if evidence supports it, otherwise no candidate. D12 still requires explicit user authorization and original unchanged acceptance gates; no automatic execution. Rust-first --engine cohort opt-in, default exact and no Python fallback. Native329 passed/2 ignored, headless20, Python17. Independent wire/receipt and arithmetic checks, no native subagent/full CI/merge. Original V1 PLAN byte-identical. AD1 actual Q1/Q2/Q5 and original service capacity, AD2 owner/birth/progress/clock and negative refinement, ALM1 zero new exact ticks/no guard change (time fraction not measured), ALM2 final differentiated attempt exhausted. Evidence [report](../research/AKM_D09_FINAL_COHORT_20261128.md), `artifacts/akm_d09_final_cohort_20261128/S09_audit.json`, S10 receipt. Verdict STOPPED_D09 / CAUTION_RESEARCH_ONLY.

## 6.8. 2026-11-28 D11: 유한 후보 판정

D11 VERIFIED_SCOPED, attempts1/2. A/B/D finite archived comparison executed in Rust (no new simulation). A 22/24 reached, two moment-cone stops, selective finest adjacent gap43.2832%; B matched AM mean gap0.003218% but receiving abs gap0.028614 >0.02; D original service deficit and 7s free-flow counterexample retained, 61.0055% support reduction not physical parity. No common-domain total Pareto ranking; UNKNOWN not PASS; no compensation by runtime. Rust-native decision reproduced byte-identically; independent Fraction oracle on raw data; read-only Python frontend. D11 selected **NO_CANDIDATE**; scoped local/causal/LUTI results remain. D12 STOPPED zero attempts, no approved candidate and no acceptance campaign. D13 READY for terminal synthesis, not auto-executed here. D09/D10 unchanged. Original V1 PLAN byte-identical; default Rust exact unchanged, no full CI/main merge, no universal no-go. AD1/AD2 archived scope preserved; ALM1 zero new exact ticks/cap changes; ALM2 no reopening stopped node. Evidence: [D11 report](../research/AKM_D11_CANDIDATE_DECISION_20261128.md), `artifacts/akm_d11_decision_20261128/S06_decision.json`, S08 independent audit. CAUTION_RESEARCH_ONLY.

## 7. 유한 DAG: 정의와 종료

D00–D03은 이번 재정초의 실측 범위에 대해 VERIFIED_SCOPED. D04–D10은 유한 science/implementation 실험. D11은 성공뿐 아니라 실패가 담긴 terminal evidence로 decision. 후보가 없다는 근거 있는 decision 자체는 D11 VERIFIED_SCOPED로 기록하며, D12는 STOPPED reason으로 종료해 D13을 활성화한다. D12는 candidate가 선택되고 사용자 승인으로 release candidate contract가 명시된 경우에만 기존 V03 전체 수용시험; 기존 3×3/3 matched refinement와 외부 limits 변경 없음. D13은 결과·통합심사 및 사용자 결정 기록으로 닫는다. 선택되지 않거나 실패한 dependency 때문에 실행할 수 없는 노드는 정확한 terminal reason과 evidence로 STOPPED/BLOCKED_TERMINAL (환경이 재개되면 새 승인된 계획) 처리. 종료까지 진행하기 위한 terminal dependency는 성공 dependency와 다르다. D11이 실행된 뒤 후보를 재생성하거나 D05로 역행하는 edge가 없다. 모든 노드는 최대 시도 횟수(실행된 차별 가설 단위, 하위 반복 횟수는 사전 기록)를 소비한다. D00–D03 각 1회 이미 소비. D04–D13 합 20회 이하의 추가 시도, global max 24회. 한 시도에 사용할 finite run matrix를 먼저 고정하고, resource failure 후 동일 run blind repeat는 최대 1회이며 같은 시도 예산에서 소모한다. V03 9+3 실행은 D12의 명시된 하나의 캠페인으로 취급(실패 시 예산 내 한 후보의 추가 캠페인만, 승인 없는 재시작 금지). 사용자가 새 연구 범위를 요청하면 버전을 변경하며 기존 종료 결과를 덮어쓰지 않는다.

### 기계 판독 DAG (authoritative)

<!-- AKM_DAG_BEGIN -->
```json
{
  "plan_id": "METROFLOW-AKM",
  "version": "1.0.0",
  "date": "2026-11-28",
  "reference_release_plan": "docs/v1/PLAN.json",
  "baseline": "f3e13c2b0251f97c1fd5da601ab8995d44ec2f5c",
  "maximum_work_in_progress": 2,
  "maximum_candidates": 3,
  "max_reference_work_fraction": 0.15,
  "maximum_total_attempts": 24,
  "nodes": [
    {
      "id": "D00",
      "name": "원동기 및 SSOT 재정초",
      "requires": [],
      "requires_terminal": [],
      "status": "VERIFIED_SCOPED",
      "attempts_used": 1,
      "max_attempts": 1,
      "question": "Q1-Q5",
      "deliverable": "원천 계보, 이론/코드 맵, finite research contract",
      "claim_gate": "역사 원천/실제 R/C 증거 대조",
      "evidence": "artifacts/active_kinetic_meso_20261128/C10_RESEARCH_RECEIPT.json"
    },
    {
      "id": "D01",
      "name": "미시-kinetic bridge",
      "requires": [
        "D00"
      ],
      "requires_terminal": [],
      "status": "VERIFIED_SCOPED",
      "attempts_used": 1,
      "max_attempts": 1,
      "question": "Q1",
      "deliverable": "PDMP generator, positive moment map, local response, micro oracle",
      "claim_gate": "독립 rational/RK4/100k microscopic comparison",
      "evidence": "artifacts/active_kinetic_meso_20261128/R07_micro_pdmp.json"
    },
    {
      "id": "D02",
      "name": "A: bounded kinetic network",
      "requires": [
        "D01"
      ],
      "requires_terminal": [],
      "status": "VERIFIED_SCOPED",
      "attempts_used": 1,
      "max_attempts": 1,
      "question": "Q1,Q2,Q5",
      "deliverable": "fixed route-position multiclass kernel, intervention and replay lab",
      "claim_gate": "12 synthetic cases, positivity/birth/mass/storage, bounded slots; refinement gap preserved",
      "evidence": "artifacts/active_kinetic_meso_20261128/C08_lab_results.json"
    },
    {
      "id": "D03",
      "name": "B: projected active city",
      "requires": [
        "D01"
      ],
      "requires_terminal": [],
      "status": "VERIFIED_SCOPED",
      "attempts_used": 1,
      "max_attempts": 1,
      "question": "Q1,Q2,Q5",
      "deliverable": "headless archive Valley active/zero 8h/24h comparison",
      "claim_gate": "same archive inputs, historical zero payload parity, projected conservation; not acceptance",
      "evidence": "artifacts/active_kinetic_meso_20261128/C08_city_active86400.json"
    },
    {
      "id": "D04",
      "name": "관측 및 반례의 공동 기준",
      "requires": [
        "D01",
        "D02",
        "D03"
      ],
      "requires_terminal": [],
      "status": "VERIFIED_SCOPED",
      "attempts_used": 1,
      "max_attempts": 2,
      "question": "Q1,Q2",
      "deliverable": "matched free/overload pulse, dynamic jam/relaxation, merge/blocked turn, two-pole response; CTM/LTM/exact oracle where compatible",
      "claim_gate": "pre-registered observable/tolerance matrix; demonstrate at least one true counterexample and one correct limit; no assumption of full FIFO equivalence",
      "evidence": "artifacts/akm_observables_owners_20261128/S09_audit.json",
      "scope": "shared discriminator matrix, sharp local bound, no full-network equivalence"
    },
    {
      "id": "D05",
      "name": "혼합/순서 및 해상도 closure 선택",
      "requires": [
        "D04"
      ],
      "requires_terminal": [],
      "status": "VERIFIED_SCOPED",
      "attempts_used": 2,
      "max_attempts": 2,
      "question": "Q1,Q2",
      "deliverable": "A: active blocked-turn/residual allocation and dt 5/2.5/1.25 day; B: same archive active mesh1200/600/300 or bounded matched peak windows; optional one ordered hybrid",
      "claim_gate": "matched observable deltas and support/complexity; overload incomplete/curve error distinguished; reject or redirect if refinement does not improve within fixed two attempts",
      "prior_findings": "D04 geometric residence and sharp third-moment envelope; D06 missed fixed return connection; compare finite propagation/spatial refinement, actual arrival/eligibility curves and journey history growth; no cap escalation",
      "last_attempt_evidence": "artifacts/akm_d05_final_20261128/S09_audit.json",
      "last_attempt_result": "D05_FINAL_SELECTION_VERIFIED_SCOPED_NOT_RELEASE",
      "next_action": "D05 closed; D07 distinct causal routing/infrastructure study; preserve negative findings for later gates",
      "evidence": "artifacts/akm_d05_final_20261128/S09_audit.json",
      "scope": "terminal closure discrimination and verified scheduled-service interface on native fixture only; all A day-resolution arms rejected, B projected comparator with receiving limitation; full network convergence unresolved"
    },
    {
      "id": "D06",
      "name": "원 도시 선언 및 전체 질량 장부 연결",
      "requires": [
        "D02",
        "D03"
      ],
      "requires_terminal": [],
      "status": "VERIFIED_SCOPED",
      "attempts_used": 1,
      "max_attempts": 2,
      "question": "Q2,Q5",
      "deliverable": "Rust adapter for current original legal graph/calendar, access/egress, bus passenger/freight, departure/return and all person/veh/cargo demand; support cardinality census",
      "claim_gate": "no demand omission, matched tiny and active city prefix, source/birth/return ledger, actual recovery; compare projected vs original identities",
      "evidence": "artifacts/akm_observables_owners_20261128/S09_audit.json",
      "scope": "original input and owner binding, actual fixture/city migration/recovery; missed return and inherited unsupported legs retained; no all-demand completion"
    },
    {
      "id": "D07",
      "name": "인과적 경로 선택과 인프라 개입",
      "requires": [
        "D04",
        "D05"
      ],
      "requires_terminal": [],
      "status": "VERIFIED_SCOPED",
      "attempts_used": 1,
      "max_attempts": 2,
      "question": "Q3",
      "deliverable": "K legal path candidates, medium information delay/expiry, source-only and ready-boundary reroute, graph transaction, paired bridge/bypass experiment",
      "claim_gate": "same demand/topology except intervention; no future info/illegal path, reroute conserves committed journey owner; nontrivial flow/queue/route response, compare negative cases",
      "prior_findings": "D05 terminal scoped selection: D AKMFULL3 service interface; A global day refinement unvalidated, B projected comparator only. Rust backend/Python frontend. Proceed causal legal route/graph and paired intervention research, no production acceptance.",
      "evidence": "artifacts/akm_d07_causal_routing_20261128/S09_audit.json",
      "scope": "bounded synthetic actual causal ready suffix, installed graph and matched interventions; original calendar/whole-city integration, convergence and demand elasticity not verified",
      "last_attempt_result": "D07_VERIFIED_SCOPED_SYNTHETIC_NOT_RELEASE"
    },
    {
      "id": "D08",
      "name": "접근성-도시발전 지연 feedback",
      "requires": [
        "D06",
        "D07"
      ],
      "requires_terminal": [],
      "status": "VERIFIED_SCOPED",
      "attempts_used": 1,
      "max_attempts": 2,
      "question": "Q4",
      "deliverable": "port verified growth/phase laws to selected candidate; two slow epochs with paired frozen vs endogenous demand",
      "claim_gate": "source population/activity ledger and lagged update; no same-tick feedback, observed accessibility/land-use/demand differences; no calibration claim",
      "prior_findings": "D07 finite causal routing lab completed; original owner bridge D06 and reserved-service D05 remain scoped, A/B convergence limitations preserved. No original full-city or release acceptance. Rust backend/Python frontend.",
      "evidence": "artifacts/akm_d08_rust_luti_20261128/S09_audit.json",
      "scope": "two actual slow transitions per paired arm, existing D07/M04 synthetic lagged LUTI, native historical city/calendar preparation byte replay, Rust-first frontend; original city LUTI and full-day unverified",
      "last_attempt_result": "D08_VERIFIED_SCOPED_LAGGED_LUTI_AND_NATIVE_ENTRY_NOT_RELEASE"
    },
    {
      "id": "D09",
      "name": "전체 수요 1개 도시 pilot",
      "requires": [
        "D05",
        "D06",
        "D07"
      ],
      "requires_terminal": [],
      "status": "STOPPED",
      "attempts_used": 2,
      "max_attempts": 2,
      "question": "Q1,Q2,Q3,Q5",
      "deliverable": "one original 100k city shared transport, AM/PM and 24h candidate run, full physical observables, actual restart",
      "claim_gate": "all declared demand, 24h, peakRSS≤8GiB/wall≤7200s as pilot, byte/semantic replay within model; record full active/pending; no original campaign credit",
      "prior_findings": "D05 D06 native owner/interface scoped; D07 D08 finite causal transport/lagged feedback synthetic only. Existing Rust atlas, preparation and calendar exact historical parity; run --manifest defaults Rust exact, optional interface research. Original full-city 24h not validated; carry all D05 negatives and history/unsupported demand. D09 attempt1 quantified unsupported persons >=47884.03508925/day, actual 1004024>1000000 next-step rows, positive tiny tail, matched AM temporal quotient; actual native owner history compressed, spatial route support still fails.",
      "last_attempt_evidence": "artifacts/akm_d09_final_cohort_20261128/S09_audit.json",
      "last_attempt_result": "FINAL_NONACCEPTANCE: actual finite-cohort prefix improvement and checkpoint recovery; 26310s session-limited, original service support and free-flow consistency unresolved; full day not tested",
      "next_action": "D09 closed, no further attempt; D11 candidate decision only",
      "evidence": "artifacts/akm_d09_final_cohort_20261128/S09_audit.json",
      "scope": "final bounded same-D closure attempt; no original city acceptance"
    },
    {
      "id": "D10",
      "name": "독립 지형/요일/해상도 holdout",
      "requires": [
        "D08",
        "D09"
      ],
      "requires_terminal": [],
      "status": "BLOCKED_TERMINAL",
      "attempts_used": 0,
      "max_attempts": 2,
      "question": "Q1-Q5",
      "deliverable": "River/Coastal held-out geometry/weekday/weekend; 10s/5s 8h matched active comparison; lagged experiment repeat",
      "claim_gate": "predeclared original-compatible metrics, no source/schedule change hidden; paired and held-out results plus resource profile, failures retained",
      "evidence": "artifacts/akm_d09_final_cohort_20261128/S09_audit.json",
      "scope": "unmet D09 success prerequisite; no holdout run or attempt",
      "last_attempt_result": "NOT_RUN_DEPENDENCY_D09_STOPPED",
      "next_action": "D11 decision; do not claim holdout evidence"
    },
    {
      "id": "D11",
      "name": "유한 후보 선택/중단",
      "requires": [
        "D01",
        "D02",
        "D03"
      ],
      "requires_terminal": [
        "D04",
        "D05",
        "D06",
        "D07",
        "D08",
        "D09",
        "D10"
      ],
      "status": "VERIFIED_SCOPED",
      "attempts_used": 1,
      "max_attempts": 2,
      "question": "Q1-Q5",
      "deliverable": "Pareto/claim matrix for A/B and optional one fallback, select one or no candidate",
      "claim_gate": "all paths terminal with evidence; no survivor based solely on runtime. If unresolved physical discrepancies, STOPPED/decision report rather than endlessly extend",
      "prior_findings": "D09 STOPPED after2 differentiated attempts, D10 BLOCKED_TERMINAL unrun. Compare original A/B/D scoped benefits and unresolved physical/owner/support/scale limits; select none unless evidence warrants candidate. No D12 without explicit user authorization.",
      "evidence": "artifacts/akm_d11_decision_20261128/S06_decision.json",
      "last_attempt_evidence": "artifacts/akm_d11_decision_20261128/S06_decision.json",
      "last_attempt_result": "NO_CANDIDATE_RESEARCH_DECISION",
      "scope": "finite archived A/B/D claim matrix and independent arithmetic; decision complete, no model acceptance or new simulation",
      "next_action": "D12 stopped without campaign; D13 terminal synthesis only"
    },
    {
      "id": "D12",
      "name": "기존 V03와 승인된 candidate의 수용",
      "requires": [
        "D11"
      ],
      "requires_terminal": [],
      "status": "STOPPED",
      "attempts_used": 0,
      "max_attempts": 2,
      "question": "Q5",
      "deliverable": "explicit user-authorized candidate identity/contract, original frozen matrix 3×3 full day and 3 refinements, original resource limits, acceptance review",
      "claim_gate": "unchanged release thresholds, actual evidence; if no approved candidate, terminal nonacceptance and close",
      "evidence": "artifacts/akm_d11_decision_20261128/S06_decision.json",
      "last_attempt_result": "NOT_RUN_NO_SELECTED_OR_APPROVED_CANDIDATE",
      "scope": "terminal nonacceptance; zero attempts; no candidate and no campaign authorization",
      "next_action": "D13 synthesis; do not launch original release campaign"
    },
    {
      "id": "D13",
      "name": "연구 종료 및 통합 심사",
      "requires": [
        "D11"
      ],
      "requires_terminal": [
        "D12"
      ],
      "status": "READY",
      "attempts_used": 0,
      "max_attempts": 2,
      "question": "Q1-Q5",
      "deliverable": "final evidence/negative results/decision, source-backed comparison, preserve checkpoints; integration/full CI only user-approved",
      "claim_gate": "no open automatic cycle, no final release claim without existing PLAN acceptance; explicitly close or request user decision",
      "prior_findings": "D11 verified scoped decision selected none; D12 STOPPED zero attempts; preserve all negative and scoped positive evidence. No automatic new cycle or release claim."
    }
  ]
}
```
<!-- AKM_DAG_END -->

## 8. 운영 및 재현

`python tools/akm_plan.py validate`, `render`, `next`는 Markdown 정본의 기계 판독 검증/그래프 생성/다음 노드 계산이다. Python은 연구 계획/문서 생성 및 명시 독립 oracle에 사용하며 simulation backend가 아니다. `cargo test --offline -p metroflow-headless`, `cargo run --offline --release -p metroflow-headless --bin metroflow-active-micro -- OUTPUT_JSON` 및 `metroflow-active-lab -- OUTPUT_DIR`로 작은 독립 실험 재현; 새 output 경로 필요. `metroflow-active-city NETWORK PASSAGES MESH_S HORIZON_S SEED THREADS OUTPUT_JSON ALPHA BETA TAU`는 역사 입력 hash가 일치하는 경우만 이번 실험 재현. 실제 바이너리, 데이터, 실행 영수증은 C10과 backup manifest. 도구 실패 또는 unavailable 정보는 NOT_RUN/BLOCKED 분류. 새 release candidate로 채택하기 전까지 exact V03 reference와 이전 branch/backup을 보존한다.

## 9. 문헌과 적용 한계

Puppo et al. (2017) [kinetic traffic equilibria](https://doi.org/10.3934/krm.2017033), Chiarello & Tosin (2023) [nonlocal kinetic hydrodynamic limits](https://doi.org/10.3934/krm.2022038), Daganzo (1995) [CTM network](https://doi.org/10.1016/0191-2615(94)00022-R), Jin (2015) [LTM](https://doi.org/10.1016/j.trb.2014.12.006), Cates & Tailleur (2013) [density-dependent motility coarse-graining](https://doi.org/10.1209/0295-5075/101/20010). 이번 확인은 초록/도입 수준. 모델 식/조건부 증명은 project-derived, 외부 논문의 모든 정리를 재현하지 않았다. 초기 프로젝트의 active matter 방향을 되살리되 실제 교통은 방향성/법적 경로/driver 목적과 외부 추진·손실을 가지므로 isotropic active-particle 이론의 상전이를 직접 대입하지 않는다.
