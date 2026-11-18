# KCMB Network Junction Continuation · 이론/코딩 병행 R×C 루프

작성: 2026-11-19 KST. Status: **연구용 opt-in multi-commodity 네트워크, scoped-verified candidate. 기존 MetroFlow V1 V03 수용 아님.**

## 권위·원래 목표 (R1–R3, C1–C2)

- Repository: `cosmosapjw-quantum/urban_traffic_demo`; 원본 V1 draft PR #41 `0b9caa8cc60a3ba087722e0360b997c5dfb61d62`. 직접 부모는 검증된 opt-in KCMB 6-moment branch `55e50ae787f85525f62e96e728bf699413354681`.
- 전용 worktree `/home/cosmosapjw/worktrees/urban-traffic-kcmb-network-20261119`; branch `research/kcmb-network-theory-coding-20261119`. 기존 `v1_road.rs`, `packet_network.py`, PLAN 및 main/PR #41은 변경 금지.
- 원래 물리 동기는 단순 mesoscopic이 아니라 microscopic Markov/finite-response control에서 상향 생성된 kinetic moments와 macroscopic finite-volume conserved flow 및 network node 공급/수신 제약을 하나의 유한 계산형 근사로 연결하는 것이다. 기존 여정/차종/경로의 **의미를 조용히 삭제하지 않는다**. 새 모델은 원래 V1 packet physical semantics와 **동등하지 않은 명시적 후보**이며 3개 도시·100k·24h의 V03수용 문턱을 변경하지 않는다.
- 이 연구에서 실제 선택한 다음 단위는 **물리적으로 방향/회전이 합법인 링크 간 차량량·6-moment 보존형 교차로 수송**이다. 각 route는 서로 다른 immutable commodity이며 route의 link sequence를 따라가는 동안 label을 바꾸지 않는다. Route에서는 같은 링크의 중복 통과를 거부하며, 첫-link/source와 마지막-link/sink를 명시한다. No lane changes; individual temporal strict FIFO is NOT_IMPLEMENTED.
- 원전: Tampère et al. (2011), DOI `10.1016/j.trb.2010.06.004`는 node supply constraint/interaction rule/turn ratios/invariance를 별개 필수 고려사항으로 설명한다. Jin (2015), arXiv:1405.7080/DOI `10.1016/j.trb.2014.12.006`은 non-invariant junctions가 LTM에서 모형 ill-defined를 유발할 수 있다는 사례를 제시한다. Bar-Gera & Carey (2022), DOI `10.1016/j.trb.2022.04.002`는 standard multi-commodity CTM의 FIFO 위반과 정확 FIFO 보정의 큰 계산비용을 분석한다. **이 원전의 증명은 이 신규 solver에 자동 귀속되지 않는다.**

## 후보 발산·선택 (R4, C3)

| 후보 | 자료표현 | 교차로 보증 | 코딩 선택 |
|---|---|---|---|
| A: 원래 V1 packet | full time interval genealogy, signed birth moments | explicit FIFO head order, variable memory | 기존 oracle, 수정 안함 |
| B: commodity fixed moment + shared head mixture | fixed six-moment mode per physical link and route | blocked turn blocks *all* turn fractions in shared lane pool | **구현** |
| C: commodity fixed moment + independent turning pockets | fixed six-moment mode per link and route | route movement may bypass blocked turn, must represent separate lanes | **구현** |
| D: exact tagged FIFO cumulative quantile | time-ordered class/OD mass layers | can express temporal strict FIFO, extra history/state | 후보 유지, 이번 미구현 |
| E: fully invariant node Riemann/LTM | cumulative constraints, invariant SCIR | required for arbitrary network LTM physical solution | 별도 이론 노드 |

**시뮬레이션 단위/정의.** 물리 방향 link `i`는 길이 `L_i[m]`, 차로수 `n_i`, 전역 lane storage `n_i L_i[m]`, 차량 송출/수신량 상한 `C_i dt[veh]`, 후방혼잡파 `w_i[m/s]`, priority `p_i>0`를 갖는다. 고정 route cohort `a`는 (target class `U_a[m/s]`, footprint `b_a[m/veh]`, law `alpha_a,nu_a[1/s],tau_a[s]`)와 실제 link sequence를 갖는다. 차종별 모멘트는 `Y_ia=(m0,m1,j0,j1,z0,z1)`, 무차원속도 `u=v/U_a∈[0,1]`에 대한 비정규화 차량량 모멘트다. `M_ia=m0+m1`, `J_ia=j0+j1`에 의해 보내는 양

```math
d_{ia}=min(M_{ia}, U_a (dt/L_i) J_{ia})
s_i = min(1, C_i dt / sum_a d_{ia})
D_{ia} = s_i d_{ia}.
```

교차로 수신 링크 `j`의 두 독립 자원은

```math
R_j^{veh}=C_j dt,
R_j^{m}=(n_j L_j - sum_a b_a M_{ja})
           min(1,w_j dt/L_j).
```

source의 질량 `pending_a+offer_a`는 *사전 개별 class별 cap을 걸지 않고* 수신 자원을 공동으로 경쟁한다. 이전 버전이 source별 `min(offer,Cdt)`를 중복 적용해 혼합비를 바꾸는 반례를 확인했고 원래 KCMB corridor와 동일한 admission ratio가 되도록 수정했다. 출생·수송·완료는 `released_a=completed_a+pending_a+sum_i M_{ia}` 장부로 보존한다.

## 주 정리와 반례 (R5–R6, C3–C4)

### 정리 1: node mixture flow의 자원 보존과 상태 realizability (DERIVED)

한 node에서 원래 송출 요청 `d_{ge}>=0 [veh]`, 목적 링크 `j(e)`, footprint `b_e[m/veh]`, 동일한 lane-head를 공유하는 movement group `g`, positive priority `w_g`, signal로 제한한 group scale `0<=theta_g<=u_g<=1`를 정의한다. 실제 회전량은 `f_{ge}=theta_g d_{ge}`이고 수신 링크마다

```math
sum_{g,e:j(e)=j} f_{ge} <= R_j^{veh},
sum_{g,e:j(e)=j} b_e f_{ge} <= R_j^m.
```

**증명.** 초기 `theta_g=0`은 모든 부등식을 만족한다. 알고리즘은 active group의 `theta_g`를 `w_g ds`만큼 동시에 증가시키되 `ds`를 각 group의 남은 `u_g-theta_g`, 각 수신 count의 남은 `R_j^{veh}-sum f`, 각 수신 metres의 남은 `R_j^m-sum bf`가 허용하는 증가량 중 최소로 선택한다. 따라서 다음 단계에서도 `theta∈[0,u]`이고 모든 자원이 음수가 되지 않는다. 한 단계에서 cap에 닿은 group 또는 자원의 양의 수요가 있는 group을 비활성화하므로 양의 가중치·유한 group/자원·정확산술에서 각 양의 단계가 적어도 하나의 활성 제약을 제거하여 유한 횟수에 종료한다. 각 물리 link의 송출은 기존 보유량 `M` 및 `Cdt` 이하, receiving은 이전 점유로 정의한 빈 길이 이하이므로 `M_i'=M_i-out_i+in_i`에 대해 `0<=M_i'≤storage_i`를 귀납적으로 얻는다. Class의 순간량은 `Y^{new}=(1-out/M)Phi_dtY+sum_{in}(f/M_{from})Phi_dtY_{from}+Y_source`라는 **양의 측도들의 비음수 선형 결합**이다. 따라서 정확한 kinetic semigroup에서 moment cone realizability를 보존한다. 실제 floating-point에서는 모멘트·장부를 별도로 검사한다. □

이 정리는 `shared_head`가 시간 순서상 완전 FIFO라는 증명이 아니다. Weighted progressive filling도 *일반적인 최대총처리량* 또는 invariant entropy junction solver라는 증명이 아니다.

### 정리 2: 물리 node별 자원문제의 정확한 분해 (DERIVED)

구조적으로 허용된 movement `i→j`는 반드시 `head(i)=tail(j)`이며, 같은 송출 link의 모든 movement는 하나의 `head(i)` node에 속한다. 외부 source도 최초 물리 링크의 `tail(j)` node에 속한다. 한 receiving 링크 자원 `R_j`는 해당 `tail(j)` node에만 속한다.

따라서 모든 movement group과 receiver를 node ID 순서로 재배열하면 resource incidence `B`는 각 node에 대응하는 **block diagonal matrix `diag(B_v)`**가 된다. 위 정리 1의 weighted progressive filling은 활성 제약의 축약/동결을 오직 같은 블록 내부에서 수행하며 다른 node의 자원·group과 상호작용하지 않으므로 global solve의 `f_{ge}`는 각 `B_v`를 독립으로 푼 결과의 합과 같다(정확산술, 그룹 내 priority와 tie rule 동일). **이는 새로운 물리 근사가 아닌 기존 node 문제의 동치인 계산 재구성이다.** □

전체 (L)개 link, (G) sender/source groups, (E) 허용 movement, node `v`에 `G_v` groups 및 수신 `R_v`개의 dense 계산을 쓰면 node workspace는 `O(max_v G_v R_v)`, 총 node계산은 로컬 정책의 유한 반복을 포함해 `O(sum_v (G_v+R_v) G_v R_v + E)` 수준이다. 전역 원형의 `O(G L)` workspace와 구별한다. 본 실험은 link당 하나의 homogeneous 세포와 route별 6개 moment를 보존하므로 physical state는 `6LK+3K` 스칼라(`K` 고정경로 cohort 수)다. 모든 링크가 모든 경로를 실제로 포함한다는 가정은 필요 없지만 dense 배열을 보유하므로 `LK` 크기는 존재한다.

### 정리 3: '완전 FIFO'로의 부당한 승격을 막는 직접 반례 (DERIVED)

micro vehicle queue (q_A=(A,B)), (q_B=(B,A))는 `A`·`B` 차종/경로별 총질량, `E[sigma]`, `E[v]`, `E[v²]`가 같도록 만들 수 있다(차량 속도와 internal control을 같게 설정). 따라서 현재 route별 moment projection `Q(q_A)=Q(q_B)`. B의 출구만 green이고 A 출구가 red이면 strict temporal FIFO에서 `q_A`는 첫 차량 A가 막혀 아무도 출구를 통과하지 못하지만, `q_B`는 첫 차량 B가 통과할 수 있다. 동일한 `Q` 상태로부터 서로 다른 strict FIFO 출력을 모두 복원할 수는 없다. **이 반례는 현재 선택된 유한 moment projection의 정보손실을 증명**하며, arbitrary compressed FIFO algorithms 전체에 대한 강한 no-go 주장이 아니다. `shared_head`은 동질 front mixture(정지 turn 전체 차단), `independent_turn`은 별도 turning pocket이라는 서로 다른 모델링 선택으로 명시한다. □

## 구성적 코드 및 검증 (R7–R9, C5–C9)

`src/metroflow/v1/kcmb_network.py`는 `KCMBLink`, `KCMBRoute`, `KCMBNetworkConfig`, `KCMBNetworkState`, `KCMBBoundedNetwork`, `progressive_junction`을 구현했다. `crates/metroflow-rust/src/v1_kcmb_node.rs`는 표준 PyO3 extension에 새 `allocate_kcmb_nodes` entry를 등록하고 같은 node group flux를 계산한다. 기존 `NativeKCMBCorridor` 및 기존 authoritative `V1Road`를 교체하지 않았다.

- **[BEHAVIORAL RED→GREEN]** 기존 전역 receiver table은 80개 독립 chain junction의 단일 수요에서 80 receiver 행을 계산했다. 새 node-local solve는 1개씩만 계산. link 1600개에서 모든 node group을 활성화한 원형 native global G×L=2.56M entries는 예산 오류를 냈으나 node-local 분해는 동일 물리 상태로 실행되었다.
- **[BEHAVIORAL RED→GREEN]** 동일 진입링크에서 car 100veh, bus 1veh의 과부하 수요를 클래스별 `Cdt`로 먼저 자르면 원래 KCMB의 입장 비율과 크게 달랐다. 수정 후 원래 1-cell KCMB와 class별 admitted/remaining pending 일치.
- **[NUMERICALLY CHECKED]** shared_head 모형에서 서로 다른 출구 중 하나가 red이면 앞 공통 lane 수요가 공동차단되는 반면 separate pockets에서는 열린 회전으로 수송 가능. 2→1의 priority 2:1 수신 1veh이면 `2/3,1/3`이고, class footprint 5/15m 혼합에 10m receiving은 각각 0.5veh로 총10m. Source-vs-upstream compete receiving budget, pending/active/completed per-tag balance, route/noncontiguous/illegal gate rejection, restore identity, 1-cell old corridor parity를 검산.
- **[NUMERICALLY CHECKED]** 400개 독립 node의 동일 자원배분에서 global 수송과 local 분해는 모든 출력을 동일하게 반환했다. Python 중앙 실행시간 global `0.0559595s`, local `0.00224455s`(약 `24.9×`). Rust global `0.000897847s`, local `0.000496649s`(약 `1.81×`). 이는 **노드 자원배분 알고리즘만**의 microbenchmark다.
- **[NUMERICALLY CHECKED]** 전체 opt-in one-route chain의 제한된 Python/Rust backend 비교:

| link / steps | Python total[s] | Rust-node total[s] | speed ratio Python/Rust | state scalars |
|---:|---:|---:|---:|---:|
| 80 / 100 | 0.157044 | 0.114159 | 1.376× | 483 |
| 400 / 40 | 0.307051 | 0.231111 | 1.329× | 2403 |
| 1600 / 12 | 0.373371 | 0.282442 | 1.322× | 9603 |

위 Rust 경로도 **Python을 통해 매 node마다 호출**하므로 전체 joint Rust engine과 다르다. 동일 실험에서 Python/Rust `completed`, `active`, `pending`은 출력한 수치 범위 내 같았다. 미시 상태 데이터가 synthetic인 서로 다른 모델끼리의 기존 V1 대비 speedup은 측정하지 않았다.

## 다음 단계 의무·판정 (R8–R10, C10)

- **선택한 모델:** opt-in 1-cell-per-directed-link multi-commodity network, physical node resource allocation 및 `shared_head`/independent_turn의 명시적 대안. C9 finding은 두 차례 재현한 실제 결함(전역 dense node table / source cap 중복)만 고쳤다. 생산용 V1 packet path는 변경하지 않았다.
- **엄밀한 물리적 한계:** 한 링크 안의 각 route가 6가지 moment로 환원되므로 정리3의 time-order 정보가 없다. `shared_head`의 all-or-nothing red blocking은 exchangeable mixing closure일 뿐 개별 차량 FIFO 법칙을 정확 구현하지 않는다. 일반 불변 junction entropy condition, junction conflict phase/green schedule geometry, 미시 pair 안전성, real field calibration은 미구현. 이러한 차이는 코드 identity/version으로 명확히 드러난다.
- **최소 다음 과학 계산:** 실제 차로의 turning pocket/lane partition과 class-specific `micro gap shadow`를 opt-in 경로에 결합하고, 기존 V1의 exact route/time oracle와 새 solver의 `error vs cost` 파레토를 **동일 synthetic input**에서 평가한 뒤 inD/UTD19에서 class/road/time map-match된 holdout을 수행한다. 선택 목적이 정확 temporal FIFO라면 역사상 weighted mix 대신 bounded-history cumulative queue contract와 추적 오차 측도를 별도 도입한다.
- **Source/Rust audit:** cargo check, isolated Rust unit tests와 이전 155 Python scoped regression을 함께 재검증한다. 새 오라클의 실제 실행기록/결과는 `artifacts/kcmb_network_20261119`와 최종 `NETWORK_RECEIPT.json`에 기록한다. 전체 CI, V03 24h 0/9 해소, main merge, 원격 push 등은 요청되지 않은 단계로 **NOT_RUN**. Native subagent 도구는 제공되지 않아 `NOT_RUN`.
