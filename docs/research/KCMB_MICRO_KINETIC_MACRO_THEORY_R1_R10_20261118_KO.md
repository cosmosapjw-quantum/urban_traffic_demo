# MetroFlow KCMB: microscopic–kinetic–macroscopic 교통 재구성 · 이론 R1–R10

2026-11-18 (KST) · 연구 전용 · **기존 V1 교통 엔진/수용 계약의 대체 승인 아님**

## 연구 식별 · 변경 범위

- 권위 저장소 `cosmosapjw-quantum/urban_traffic_demo`. 본문 조사의 기준은 draft PR #41 `v1/v03-acceptance-20261027`, `0b9caa8cc60a3ba087722e0360b997c5dfb61d62`이며, 별도 연구 worktree `/home/cosmosapjw/worktrees/urban-traffic-v1-audit-20261118`에 작성했다. 기존 사전 연구감사 `docs/research/URBAN_V1_AUDIT_THEORY_LIGHTWEIGHT_20261118_KO.md`를 재사용했다.
- 본 요청은 **이론 전체 R1–R10**이다. 새 physics prototype과 수치 검산은 R7 판별 검증을 위한 탐색 산출물이지 C5 구현 또는 원래 V03 교통 엔진 변경이 아니다. Main, PR #41, PLAN의 원래 수요/오차/성능 기준을 수정하지 않는다.
- 핵심 결론: **KCMB(Kinetic–Conservative Multiscale Bridge)**를 조건부 연구용 모델로 선택했다. 이 모델은 국소적인 microscopic Markov/finite-response 통계 역학, 유한 차원 kinetic moment, 거시적 conservative sending/receiving/공간 혼잡파를 결합한다. 증명은 명시한 영역에서 유효하며 현실 세계 적합도는 field data 검증 전까지 `UNRESOLVED`이다.

## R1. 과학적 목표와 세 가지 동등성

원동기는 microscopic bottom-up의 목적지 지향 자율 운동·제동·정지/재출발·운전자 차이와 macroscopic top-down의 질량 보존·교통 혼잡파·교차로 유량 제약을 **하나의 중간 근사에서 연결**하는 것이다. 단순 집계형 mesoscopy가 최종 지향점이 아니다.

검증 대상은 서로 구분한다. (A) **LOCAL_GENERATOR_EQUIVALENCE**: 동일한 동결 환경 아래 microscopic Markov 생성자에서 유도한 관측 모멘트가 구현된 국소 motion과 일치한다. (B) **MACRO_LIMIT_EQUIVALENCE**: 적절한 평형·균질 한계에서 보존형 LWR/CTM Godunov 해법으로 환원한다. (C) **OBSERVATIONAL_REALISM**: 실제 도시의 관측된 교통 동역학(속도·간격·혼잡파·통과시간·정체 형성)에 대한 예측오차가 경쟁 모형 대비 얼마나 작은지를 자료로 검증한다. A와 B의 정리는 C를 증명하지 않는다.

추가 계산 계약: 상태 메모리와 한 step 작업량은 출발인구 또는 packet splitting의 횟수가 아닌, **선택된 공간 격자·미시 모멘트 수·차로군·node 문제 크기**로 제한된다. 정확한 개별 이벤트/차량 identity까지 잃지 않고 모든 관측을 보존한다는 요구를 이 조건에 몰래 포함시키지 않는다.

## R2. 원 저장소 계보 및 재사용 자료

| 검증된 commit | 시기 | 핵심 구상 | 본 재구성에서의 취급 |
|---|---|---|---|
| `3ffc153` | 10월 23일 | conservation/finite-storage CTM; 수치 service rate, Godunov reference | 거시 보존·shock의 독립 기준 |
| `3d83db0` | 10월 24일 | active-matter two-state cohort, collision gain/loss, positive cost-to-go, aggregate node allocation | Markov 내부상태/자기구동, 여러 경로의 여정 장부 |
| `6f45a3c` | 10월 24일 | 실제 연속속도와 제어 `sigma` 분리, 조건부 characteristic, 과거 정보 | 국소 생성자와 finite-speed motion |
| `10737b2` | 10월 24일 | 조건부 `(h,v,w)` pair, 제동 가능집합, leader-report 인과성 | 편차·상관·국소 안전 점검을 위한 선택적 shadow |
| `25f887a` | 10월 25일 | ordered lane, 반복 gap motif | FIFO 및 이질반응의 경계 사례 |
| `bf2325d` | 10월 25일 | 혼합 packet과 비식별 물리 priority/입장 순서 | 네트워크 장부·물리적 우선순위 |
| `7d5e388` | 10월 26일 | V1 finite response common speed, split integration | 현재 kinetic base / 약점 진단 |
| `bea8453`, PR #30 | 10월 26일 | class lane groups, turns, signals, storage in metres | 유한 저장량·node resource constraints |
| PR #31–#41 | 10월 26일~11월 17일 | 시간구간 packet, causality, multimodal services, native Rust | 통합 근거와 현재 representation explosion |

과거 원전: `docs/research/ACTIVE_MESO_DESIGN_20261024.md`, `axiom_gap_20261024/DERIVATION_KO.md`, `gap_viability_20261024/TRAFFIC_DERIVATION_KO.md`, `symmetry_observables_20261025/TRAFFIC_KO.md`, `PURE_PYTHON_CTM_TRAFFIC_DESIGN_20261023.md`, `CTM_CONSISTENCY_NEXT_20261023.md`, `docs/v1/t02/CLOSURE_KO.md`, `t03/NODE_CONTRACT_KO.md`, `t04/TRANSPORT_KO.md`.

특히 오래된 active-meso의 `f_0/f_1`은 **정지/주행 제어상태**를 나타내며 연속 실제속도 `v`의 두 Dirac 원자라고 일반화할 수 없다. `p=E[sigma]`와 `m=E[v]`를 구분해야 한다. `AXIOMATIC_FOUNDATIONS_KO.md` 자체는 이번 checkout에서 확인되지 않아 그 원문을 읽었다고 주장하지 않는다. 확인한 것은 이를 명시적으로 인용하는 과거 유도 및 해당 구현들이다.

문헌: Helbing(1995) DOI `10.1016/0378-4371(95)00174-6`; Treiber–Hennecke–Helbing(1999) DOI `10.1103/PhysRevE.59.239`; Aw–Rascle(2000) DOI `10.1137/S0036139997332099`; Herty–Puppo–Roncoroni–Visconti(2020) DOI `10.3934/krm.2020010`; Chiarello–Piccoli–Tosin(2021) DOI `10.1016/j.ijnonlinmec.2021.103806`; Daganzo(1995) DOI `10.1016/0191-2615(94)00022-R`; Jin(2015) DOI `10.1016/j.trb.2014.12.006`; de Souza–Verbas–Auld–Tampère(2025) DOI `10.1016/j.simpat.2025.103088`. 이러한 문헌은 kinetic/continuum hierarchy 및 cumulative flows의 계보를 제공하나 KCMB의 새 코드 결과나 실도시 수용을 보증하지 않는다.

## R3. 상태, 단위, 근사와 주장 계약

- 각 균질 lane-cell `i`의 길이 `dx_i [m]`, 총 보유질량 `M_i [veh]`, 저장상한 `J_i [veh]`, 유량상한 `C_i [veh/s]`, backward wave speed `w_i [m/s]`, `dt [s]`.
- 개별 제어 `sigma∈{0,1}`, 실제 `v∈[0,v_max] [m/s]`, 전이율 `alpha:0→1`, `nu:1→0 [s^-1]`, 반응시간 `tau>0 [s]`, 국소 target `U [m/s]`. `sigma`는 속도 두 값이 아니다. 실제 차량 자율 가속은 에너지를 주입하므로 물질 입자 충돌처럼 운동량/에너지 보존을 공리화하지 않는다.
- 입력 국소 상태를 가중 양의 측도 `mu_i(d sigma,dv)`로 보고 비정규화 모멘트 `Y_i=(M_i,P_i,V_i,H_i,Z_i)`를 둔다. `P=∫sigma dmu [veh]`, `V=∫v dmu [veh·m/s]`, `H=∫sigma v dmu`, `Z=∫v² dmu [veh·m²/s²]`. 필요시 운전자 class, 고정 경로/turn group, **법칙이 다른 조건부 gap quadrature**를 별도 mode로 구분한다.
- Local `U,alpha,nu,tau`는 해당 substep에서 동결한다. `acceleration/braking clip`와 leader-feedback가 활성인 경우 뒤의 정확 국소 ODE 정리 적용 대상이 아니다. 그러나 clip이 필요할 경우 별도 조건부 pair/safety 연산자를 갖는 모델 후보는 보존한다.
- 고정 총 source 예정량은 `unreleased/pending`과 실제 admitted, active, completed를 구분하며 가짜 완료를 허용하지 않는다. 여러 차종의 footprint가 다르면 node 인입에는 `∑_c b_c F_{in,c} ≤ L_{free,m}` 추가 제한이 필요하다.
- 네트워크 flux와 route choice는 실제 물리적 정보를 사용한다. 운전자의 perceived cost에는 미래 truth를 제공하지 않으며 timestamp/coverage를 분리한다.

## R4. 발산적 재구성 후보 및 판별

| 후보 | 회복하는 물리 | 계산구조 | 현재 판정 |
|---|---|---|---|
| A. 원래 `PacketNetwork` + persistent interval DAG | 현재 packet 별 사건·FIFO·birth history 의미 | lazy shared nodes, 여전히 논리 사건의 전파 비용 증식 가능 | **연구 유지**: 성능 bound 미증명 |
| B. 2026-10 `ActiveMeso`의 2-state residence stage | 제어상태와 OD cohort, fixed state | `O(E×cohort×stage)`; 속도 두 값의 동역학으로 오해 위험 | kinetic 생성자 재사용 |
| C. `gap_transport` + finite quadrature/OVM | 변위·간격·leader 조건부 안전·stop-go | pair hierarchy, follower-leader marginal compatibility 부담 | 특정 node/교차로 **shadow** 후보 |
| D. 순수 LWR/CTM/LTM | conserved density, shock/spillback | 희소 flux/누적경계; 유한응답·속도분산 소실 | top-down 한계 참조 |
| E. BGK/Enskog/ARZ 비국소 2차 계층 | stop-go instability, anticipation, velocity variance | closure/entropy/junction, near-vacuum 검증 부담 | 장기 연구 후보 |
| **F. KCMB: local Markov moments + Godunov** | microscopic finite response와 macro conservation/shock의 교점 | 고정 `O(cells × fixed modes)` | **선택된 R5/R7 구조** |
| G. 단일종류 cumulative-delay LTM fast path | FIFO 질량순서, lagged free/backward wave | `O(f+b)` state per link at fixed grid/time | F의 조건부 homogeneous-link 가속 |

선택 F는 A의 exact event semantics와 일반적으로 동등하지 않다. 이를 V03의 원래 수치/물리 동일성 PASS로 승격하지 않는다. A는 비트 동일 모형의 별도 탐색으로 유지한다. F가 현실적이지 않은 정체 불안정성/상관을 제거할 가능성에 대비해 C/E를 관측 및 불안정성 검산의 상위 대안으로 남긴다.

## R5. 실제 유도와 조건부 수학 정리

### 정리 1. Microscopic Markov–kinetic moment intertwining

**가정.** 국소 시간구간 `[0,dt]`에서 `U∈[0,v_max]`, `alpha,nu≥0`, `tau>0`는 고정이고, 각각의 follower는 `sigma:0↔1` 연속시간 Markov process를 따르며

```math
dot v=(U sigma-v)/tau,  sigma∈{0,1}.
```

속도 경계 `0≤v≤v_max`에서 drift는 안쪽을 향한다. 임의 유한 양의 초기 분포 `mu_0`에 대해 국소 확률 과정과 그 moment projection `Pi`는

```math
Pi S_t(mu_0)=exp(t A) Pi(mu_0),  (LOCAL EXACT),
```

여기서 `Y=(M,P,V,H,Z)`와 양의 질량 `M`에 대한 generator는

```math
dot M=0,
dot P=alpha M-(alpha+nu)P,
dot V=(U P-V)/tau,
dot H=(U P-H)/tau+alpha V-(alpha+nu)H,
dot Z=2(U H-Z)/tau.
```

**증명.** Markov generator는 `L phi=((U sigma-v)/tau) ∂_v phi + rate_sigma[phi(1-sigma,v)-phi(sigma,v)]`이고 `rate_0=alpha,rate_1=nu`다. `phi=1,sigma,v,sigma v,v²`를 하나씩 대입하면 우변이 정확히 위 5개 모멘트 안에서 닫힌다. 측도와 순간량의 교환은 유계 속도·유한 질량 및 선형 drift에서 정당화된다. 따라서 서로 같은 초기값을 가진 finite linear ODE의 유일성에 의해 등식이 따른다. 운동량 보존식이 아니라 **구동/완화의 정확한 관측 모멘트 관계**이다. □

**통계적 의미.** `N`개 micro 차량이 동일 조건 아래 서로 독립이고 속도가 `[0,v_max]`에 있다면 시각 `t`에서 `Pr(|mean_N(v)-E[v]|≥eps) ≤v_max²/(4 N eps²)`. 이는 bounded random variable의 variance bound와 Chebyshev에서 따른다. 독립성이 없는 실제 차간 상호작용을 이 결과가 증명하지 않는다.

`lambda=alpha+nu>0`이면

```math
p(t)=p_*+(p(0)-p_*)e^{-lambda t}, p_*=alpha/lambda,
m(t)=U p_*+(m(0)-U p_*) e^{-t/tau}
+ (U/tau)(p(0)-p_*) (e^{-lambda t}-e^{-t/tau})/(1/tau-lambda).
```

`lambda=1/tau`에서는 분수의 정확 극한 `t e^{-t/tau}`. `lambda=0`에서는 `p`가 일정하다. 위치는 `∫m(t)dt`로 국소 평균 변위와 연결된다. 앞선 연구 파일 `frozen_relaxation_oracle.py`는 이 다중차종 일반화를 직접 계산한다.

정상상태에서 `E[v]=U p_*`, `Var(v)=U² p_*(1-p_*)/(1+lambda tau)`. `r=E[sigma v]`의 정상방정식을 먼저 풀고 `z=E[v²]=U r`를 사용하면 직접 얻어진다. Wolfram stationary ODE 잔차4개와 분산식 잔차는 0으로 확인됐다. 속도가 두 원자에 고정된다는 가정 없이 내부 속도분산을 정량적으로 유지한다.

### 정리 2. KCMB의 보존·비음성·저장량·moment realizability

**가정.** 유한 개의 고정 공간 셀 `i=1..N`과 유한한 법칙 모드 `a=1..K`를 선언한다. 각 셀 `M_i∈[0,J_i]`; 각 모드의 `Y_{i,a}`는 `sigma∈{0,1}`, `v∈[0,v_max]` 위 유한 양의 측도의 모멘트이다. R5 정리1의 local Markov semigroup `Phi_dt`를 각 모드별로 적용한 뒤, 고정 `dx_i`와 `dt`에 대하여

```math
S_i=min(M_i, C_i dt, (dt/dx_i) V_i),
R_i=min(J_i-M_i, C_i dt, (w_i dt/dx_i)(J_i-M_i)).
```

허용된 교차로 movement `f_{ij}≥0`는 `∑_j f_{ij}≤S_i`, `∑_j f_{ji}≤R_i`를 만족한다. 입력과 출력량은 동시에 commit하고 `∑class f≤component mass`를 유지하도록 동일 모드의 질량·모멘트를 같은 비율로 이동시킨다. 유효한 boundary source moment 역시 양의 측도에서 온다. Class footprint가 다르면 추가 metre-space receiving constraint를 교차로 계산에 포함한다. 모든 법칙이 지배하는 속도는 `0≤v≤v_max`이고 `dt max(v_max,w_i)/dx_i≤1`이다.

**결론.** 임의 유한 step에서 (i) `0≤M_i^{n+1}≤J_i`; (ii) 모든 class/mode moment가 유효한 양의 측도에서 표현 가능; (iii) 전체 차량량에 대해

```math
sum_i M_i^{n+1}-sum_i M_i^n = external_admitted^n-external_completed^n;
planned_total^n = pending^n + sum_i M_i^n + completed^n
```

이 정확한 실수 산술에서 성립한다. (iv) red signal `f=0`, zero receiving `f=0`, source를 같은 step에 두 셀 이상 통과시키지 않는 update ordering이 성립한다. **이 결론은 임의의 microscopic pair 충돌 회피·class-tag strict FIFO를 포함하지 않는다.**

**증명.** Local generator semigroup은 양의 측도의 push-forward/Markov mixing이므로 양수성 및 속도 support를 유지하며 M을 보존한다. 각 셀에서 outflow `O_i≤S_i≤M_i`, inflow `I_i≤R_i≤J_i-M_i`이므로

```math
0 ≤ M_i-O_i ≤ M_i+I_i-O_i ≤ M_i+I_i ≤ J_i.
```

따라서 induction으로 모든 step의 비음성·저장량 bound가 닫힌다. 각 moment vector를 `1-O_i/M_i`배 남기고 nonnegative incoming moment vectors를 합하므로 realizable cone의 convex conic closure 아래 admissible 상태가 된다. 전체 질량식을 모든 i에 대해 합하면 내부 movement `f_{ij}`가 한 쪽에서는 `-f`, 다른 쪽에서는 `+f`로 정확히 상쇄된다. 경계 pending은 admitted만큼 감소하고 planned births만큼 증가하므로 마지막 식이 따른다. 새 입력은 old state로 계산된 flux가 완결된 뒤에만 다음 step의 sending에 관여한다. □

### 정리 3. Homogeneous fast-relaxation macro reduction과 shock

동일 차종·동일 도로환경의 stationary local state에서 `p=p_*`, `v_f=U p_*>0`가 일정하고 `J_i=k_j dx`, `C=v_f w k_j/(v_f+w)`일 때 정리2의 단일차로 flux는 정확히

```math
Q(k)=min(v_f k,C,w(k_j-k)), k_c=w k_j/(v_f+w),
F_{i+1/2}=min(D(k_i),S(k_{i+1})),
k_i^{n+1}=k_i^n+(dt/dx)(F_{i-1/2}-F_{i+1/2}),
```

여기서 `D(k)=min(v_f k,C)`, `S(k)=min(w(k_j-k),C)`인 **삼각 fundamental-diagram LWR에 대한 Godunov/CTM**이다. 따라서 CFL 아래의 scalar homogeneous 구간에서는 기존 Godunov monotone scheme의 보존성·entropy solution 수렴 정리를 해당 조건에 적용할 수 있다. 새로운 임의 비정상/비균질 kinetic network 수렴 정리는 얻지 않았다.

직접 유도: `M=k dx`를 정리2에 대입하면 `S/dt=D(k)`, `R/dt=S(k)`이며 `M'=M+f_{in}-f_{out}`를 `dx`로 나누면 위 수치 flux를 정확히 얻는다. `k_c`는 free 및 congested branch가 만나는 해다. `k_L=0.02, k_R=0.10 veh/m, v_f=15,w=5 m/s,k_j=0.15 veh/m`이면

```math
s_shock=(Q(k_R)-Q(k_L))/(k_R-k_L)=(0.25-0.30)/0.08=-0.625m/s.
```

Riemann entropy shock는 100s 후 `-62.5m`이다. **이 단면 정리는 모델의 충격파 물리를 갖춘 한계를 입증하지만, 일반 stop-and-go wave의 자발적 발생을 보증하지 않는다.**

### 정리 4. 고정 크기의 계산 상태가 packet-genealogy 폭증을 제거하는 조건

**가정.** `N` 공간 셀, 최대 `K` 모드, 유한 node movement graph를 simulation horizon 전체에서 고정하고 class/modal law의 분할·합성은 기존 `K` 슬롯 밖에 새 cohort를 만들지 않는다. 전체 event history/개별 차량 영수증을 런타임 물리 상태에 무제한 누적 저장하지 않는다. 한 node allocation은 도로망의 고정 degree 및 movement 수에 따른 유한 다항 algorithm을 사용한다.

**결론.** 연구용 conservative moment solver가 보유하는 mutable physical state는 `O(N K+N+∑_v P(deg(v)))` 이하의 고정 차원이고, horizon 중 발생한 **부분 packet 서비스 횟수, 최초 차량 수, 유입 mass의 절댓값**에 따른 저장 차원 증가가 없다. 한 step의 산술 비용은 `O(N K+∑_v T_node(deg(v)))`다. 따라서 **V03의 부분 서비스마다 head·remainder·하류 entry interval packet 계보가 추가되는 형태의 메모리 증식은 이 선택한 표현에서는 구조적으로 발생하지 않는다.**

**증명.** 매 step 고정된 `N×K` 순간량을 한 번 local semigroup으로 진화시킨다. 인접 cell boundary마다 제한된 수의 flux와 각 모드의 양을 계산해 이미 존재하는 배열 슬롯에 쓴다. 동적 `Packet` 리스트와 새 entry interval에 비례한 row를 생성하는 연산이 없다. 저장객체의 최대 수를 최초에 정했으므로 induction으로 전 horizon 동일 상한이다. 각 위치/모드당 상수회 선형 모멘트 연산과 선언된 node solver만 수행한다. 실제 wall-time이나 memory byte peak는 구현·cache·input/output·calendar의 조건과 별도로 측정해야 한다. □

**범위 제한.** 이 정리는 원래 `5,093,765`개 OD leg의 모든 개별 birth/route/exit 시각을 해당 고정 상태가 exact 재현한다는 주장이 아니다. `K`를 관측모드를 구별할 만큼 늘리면 `NK`의 값도 증가한다. 임의의 미시 label FIFO를 분포 모멘트만으로 복원하지 않는다.

### 정리 5. 단일종류 cumulative-delay 링크의 유한 이력 표현

Homogeneous one-commodity FIFO fluid link에서, grid delay 정수 `f,b≥1`, 저장량 `J`, 한 step 서비스상한 `C dt`를 고정한다. 누적 유입 `A_n`, 누적 유출 `D_n` (음수시각0)와

```math
send_n=min(C dt,max(0,A_{n-f}-D_n)),
receive_n=min(C dt,max(0,D_{n-b}+J-A_n))
```

를 사용하고 `0≤out_n≤send_n`, `0≤in_n≤receive_n`; `A_{n+1}=A_n+in_n`, `D_{n+1}=D_n+out_n`으로 갱신한다. 무출발 초기상태라면 귀납적으로

```math
0≤A_n-D_n≤J,
Q_n=A_{n-f}-D_n≥0,
V_n=D_{n-b}+J-A_n≥0.
```

**증명.** `D_{n+1}≤A_{n-f}≤A_{n+1-f}`, `A_{n+1}≤D_{n-b}+J≤D_{n+1-b}+J`. 따라서 다음 시각에도 Q,V는 비음수다. 또한 `D_{n+1}≤A_{n+1}`와 `A_{n+1}≤D_{n+1}+J`가 성립한다. 출입량은 매 step `C dt` 이하이며 rolling buffers `f+1,b+1`개면 모든 필요한 lag값을 갱신할 수 있다. 외부 질량 pending을 따로 보존하면 출발 total ledger도 성립한다. □

단일종류 차량의 유입 질량 quantile 순서와 유출 quantile 순서를 같은 순서로 대응시키는 FIFO 정의는 가능하나, 임의의 class/tag 배열과 per-trip 관측을 정확히 복원하는 데 필요한 label memory는 이 정리의 고정 버퍼 계산에 포함되지 않는다. 시간변화 `U,w`, 비균질 초기 상태, 모든 node entropy coupling 및 정확한 원래 V1 dynamics에 대한 별도 정리가 필요하다. 이 구조는 누적유량 LTM fast path 후보이지 검증된 완성판이 아니다.

### 조건부 kinetic instability 진단: 복원할 범위

OVM ring의 clipping 없는 선형화에서 `tau lambda²+lambda=a(e^{ik}-1)`, `a=U'(h_*)>0 [s^{-1}]`. `k→0`에서

```math
lambda=iak+(tau a²-a/2)k²+O(k³).
```

따라서 `tau a>1/2`이면 충분히 긴 파장의 실수부가 양수이고, `tau a<1/2`이면 이 장파기울기에서 감쇠된다. 정확한 정리는 periodic FTL/OVM의 선형화에 대한 것이며 현재 안전필터/누적 macro solver의 불안정 증명은 아니다. KCMB의 단일층 scalar Godunov가 이 자발적 stop-and-go 메커니즘을 모사할 것이라 가정해서는 안 된다. 이를 회복하는 추가 kinetic-gap/ARZ branch는 별도 cross-scale 연구 범위다.

## R6. 적대적 심사 · 실제 반례

1. **평균 gap의 Jensen 오류:** `nu(h)=beta [s/(h+ell)]²`이면 `nu''(h)=6 beta s²/(h+ell)^4>0`. 4/96m의 동률 gap 혼합과 평균 50m 폐쇄는 다른 encounter rate를 보인다. 균질 closure의 거시 보존성을 모든 현장 safety로 승격할 수 없다.
2. **희소 slow class의 비연속적 `U=min_c U_c`:** 존재질량이 0에 가까워도 느린 class 하나의 cap이 전체 속도를 잠글 수 있다. `U`를 soft-min으로 교체하면 별도 lane separation 및 no-overrun 조건이 필요하다.
3. **birth 0/2s 각각 .5veh vs birth 1s의 1veh:** 둘의 mass와 first birth moment는 같지만 t=.5s cumulative availability는 0.5veh vs0이다. 그러므로 first-moment-only 상태로 arbitrary FIFO departure/throughput observables를 exact 복원할 수 없다. 이는 현 방식에 대한 직접 반례이며 모든 압축의 불가능성 no-go는 아니다.
4. **shock 속도 관측 함정:** 종료시 총 mass 차이로 복원한 충격파 위치는 boundary conservation만으로도 정답일 수 있으므로 independent shock-shape 검증이 아니다. 실제 테스트를 밀도 half-height crossing 및 `∫|rho_num-rho_exact|dx`로 교정했다.
5. **엄격한 lane FIFO와 mixed-per-cell transport:** 같은 cell의 class moment를 비례 혼합하면 차량·차선·route 순서가 보존되지 않을 수 있다. 정리2에 **tag FIFO가 포함되지 않는다**. dedicated lane-group 또는 별도 cumulative quantile ledger가 관측 요구일 때 필요하다.
6. **물리적 density penalty 이중계산 가능성:** `U(h,rho)`의 감소와 `receiving`의 capacity limiter가 같은 현상으로 보정될 경우 과도한 정체가 가능하다. 이중 제약의 물리적 의미를 분리하고 calibration/ablation 해야 한다.
7. **macro 수렴의 제한:** 정리3의 macro entropy reduction은 균질 constant-triangle 속도 평형일 때 성립한다. `U(rho,p)`로 flux가 비오목해지거나 신호/차선회전/공간 경계가 변할 때 전역 entropy convergence 정리가 없다.
8. **multi-class footprint:** 실물길이가 다른 bus/freight를 1veh 단위 jam capacity만으로 합산하면 metre-space bound를 위반할 수 있다. 교차로별 `sum b_c inflow_c≤remaining lane-metres`를 반드시 추가한다.
9. **junction entropy/invariance:** Jin(2015)은 invariant하지 않은 junction 모델을 사용하는 LTM에 잘 정의되지 않는 상태가 발생할 수 있음을 지적한다. 기존 V1의 weighted progressive filling 또는 일반 max-flow가 LTM 연속극한의 invariant entropy solver와 자동으로 동등하다고 볼 수 없다. 실제 kinetic moment flux에 결합할 때 merge/diverge node Riemann 문제를 별도로 확인해야 한다.

독립 native subagent dispatch는 현재 호스트에 제공되지 않아 `NOT_RUN`이고, 재검토는 위 명시적 반례와 CAS·Python 검산을 이용한 serial pass다. `R6`에서 검증하지 못한 global microscopic consistency를 PASS로 표시하지 않는다.

## R7. 직접 실행한 판별 검증

- `tools/research/kc_bridge_reference.py`: one-class local Markov + conservative FV toy; `tests/research/test_kc_bridge_20261118.py`의 finite response/공명점, 700step 임의 입력, CFL/외부 인자 오류거절, 해석적 shock, red/spillback, ring OVM dispersion; 추가 과거 연구 3건 포함 **9 passed**.
- Scalar strict triangular FD: `(dx[m], spatial L1[veh], threshold position error[m]) = (20,0.385049,12.5); (10,0.304753,7.5); (5,0.200159,~0); (2.5,0.015822,1.25)`. 동일 100s, 4km 도로, CFL 0.75. 실제 **profile** 오류가 줄었고, 총질량만 이용한 위양성 shock 판정은 제외했다. 네개 수치는 수렴률 정리 증명이 아니라 한정 수치 검사다.
- `run_signal_spillback`: 셀20개, 상태 60 scalars(3 moments×20). 총 offered 240veh, completed 75.3065104, pending 154.6934896, active 10, per-cell jam limit1.5veh. 최초150s red 후 green 및 지속 공급에서 active 보유와 pending을 삭제하지 않았다.
- `tools/research/kc_link_delay_oracle.py`: 같은 source 아래 delayed-count 단일링크를 150step 실행, f3/b5 경과 후 10개 rolling cumulative scalars; offered120, admitted96, completed90, pending24, active6. 무작위 1000step을 f/b=(1,1),(2,5),(10,11)로 실행 시 장부 잔차 최대 약 `8.1e-13veh`이며 배열길이4,9,23으로 고정됐다.
- 최초 V03 진단과의 비교: Valley의 실제 구 코드 복제 state는 25,600→25,650s의 50초에 cell part 5.63M→10.98M이며 packet 111k→210k. 본 새 배열모형은 그 복제 연산을 **하지 않는다**는 정리4를 갖지만, 동일한 full-city input/physical semantics를 실행한 공정한 wall/RSS benchmark가 아니다. 생산성능 우위는 아직 `NOT_MEASURED`다.
- Wolfram 계산: constant-rate 5 moment 정상 잔차=0, `Var(v)` closed expression 확인; OVM 소파수 전개 `iak + (tau a²-a/2)k²`; 충격파 수치는 직접 대입.
- 경험적 도시 자료는 아직 다운로드/정합되지 않았으므로 field accuracy score는 `NOT_EVALUATED`.

## R8. 결과 판정과 계층 선택

**선택:** KCMB의 **local moment semigroup + conservative Godunov**를 수치적으로 해석 가능한 기본 연구모형으로 채택한다. LTM cumulative-delay fast path는 명시된 homogeneous single-commodity 조건에서 선택적 비교 알고리즘으로 보존한다. 임의의 실제 lane disorder와 개인별 근접 안전이 중요한 위치에서는 `gap_transport`와 `periodic_gap`의 조건부 pair micro shadow가 필요하다.

**유효한 수학 주장:** 정리1·2·4·5의 제한된 모형 정리, 정리3의 균질 평형 환원 및 Rankine–Hugoniot 충격파 값, OVM의 국소 선형 불안정 조건. 유효하지 않은 승격: 전 도심 full micro FTL→macro 수렴, 개별 all-tag FIFO, 모든 도시의 충돌 안전, empirical predictive superiority, original V03 bit equivalence, 8GiB/7200s gate.

**비평형 진단 모드 선택:** `eps_tau=tau/T_traffic`, `chi=(alpha+nu)tau`, `sigma_h²/(E[h])²`, `a tau`, route/lane occupancy를 기록한다. 작은 `eps_tau`이고 이종 correlation이 약하면 평형 scalar branch, 그렇지 않으면 kinetic moment branch; gap tail과 safety concern이 크면 conditional pair/shadow, `a tau>1/2` 같은 진단이면 ARZ/BGK instability 연구 lane을 실행할 이유가 생긴다. 정량적 switch threshold는 관측 전 사전 선택하지 않는다.

## R9. 후속 코딩 연구의 식→계산→검산 계약

**상태 API 제안(미구현):** `CellMoment{mode, M_veh,P_veh,V_veh_mps,H_veh_mps,Z_veh_mps2,footprint_m}`와 `FluxLedger{sending_veh,receiving_veh,actual_movement_veh,boundary_veh,active_veh,pending_veh,completed_veh}`. 그래프/차선모델에는 기존의 physical `LanePartition`, `PortalRef`, source/birth time, vehicle class/freight/passenger ledger의 identity를 파괴하지 않는 adapter를 둔다. 각 mode는 서로 다른 `alpha,nu,tau,U,route-law`를 함부로 혼합하지 않는다.

**Step 순서:** `PRE-STEP density+observed information → mode-local kinetic exact semigroup → v_eff & bounded sending/receiving → legal-turn/priority node allocation (same supply ledger) → simultaneous conservative flux transfer → boundary pending/completion → invariant/report`. Routing은 물리 계산의 미래를 참조하지 않으며 차량이 움직이던 경로를 조용히 교체하지 않는다. `dt max(v_max,w)/dx≤1`과 class footprint metre storage를 사전 계약한다.

**우선 검증 사례:** (1) single isolated local cell과 exact stochastic kinetic moments; (2) steady homogeneous CTM/single Riemann shock/rarefaction; (3) 1→1, 2→1, 1→2 node와 3:1 priority, red and no-storage; (4) bus/freight footprint, zero/pending, impossible turn; (5) original FTL ring linear growth, conditional gap-safe shadow; (6) departure order reversal counterexample의 per-tag FIFO 실패 여부; (7) `dt,dx` 공동 refinement와 shock full-profile L1, (8) checkpoint/replay equality with same source; (9) 같은 map/OD/clock에서 기존 V1과 macro baseline과 세부 observables를 비교, (10) 실제 교통 관측자료를 이용한 holdout.

**수학적으로 허용하지 않는 단축:** first moment만 같다는 이유로 age/time shape를 합치는 것, shock L1을 전체질량 위치 잔차로 대신하는 것, 편의상 `nu(E h)`를 `E nu(h)`로 주장하는 것, per-leg cohort와 city demand를 줄이고 원래 100k 실행 완료라 주장하는 것, 안전 shadow의 비충돌 보증을 bulk solver 전체로 이전하는 것.

### Field-data empirical evaluation plan

| 자료 | 측정 단위/제약 | 검증 대상·추정 |
|---|---|---|
| **inD** https://levelxdata.com/ind-dataset/ | 독일 4개 교차로 drone 차량·보행자·자전거·버스/트럭 궤적, 약 10h, 이용 신청 및 비상업 조건 | `P(h,v,Δv,acceleration\mid class)`, 출발 반응, 진입/정지·재출발, turn, near-collision; micro/conditional kinetic. 좌표→실제 lanelet/OpenDRIVE 맞춤 |
| **NGSIM/FHWA** https://data.transportation.gov/d/8ect-6jqj | 0.1s individual vehicle trajectories; freeway I-80/US101와 도시 Lankershim/Peachtree 모두 존재 | 별도 noise filtering 후 follow-the-leader headway and speed variance, gap closure/OVM |
| **UTD19** https://utd19.ethz.ch/ 및 DOI `10.3929/ethz-b-000437802` | 도시40, detector23,541, 3–5min flow/occupancy 또는 speed, 지리좌표, 제공조건/라이선스 확인; raw CSV 약6.6GB | `q(t),v(t)`, occupancy/flow, 병목 지속·MFD/critical accumulation. occupancy를 무보정 density로 직접 치환하지 않음 |
| **Chicago Traffic Tracker** https://data.cityofchicago.org/d/4g9f-3jbs | CTA bus GPS 기반 arterial segment speeds, 약10min, 2024–2026 archive는 현재 업데이트 중지 | 교차로·간선도로의 실제 segment속도/혼잡발생 시각. 버스 편향을 승용차 ground truth로 보지 않음 |
| **NYC TLC Trip Records** https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page | 택시·FHV 탑승/하차 지역, 시각, 이동거리 등; 전체 주민 OD가 아닌 표본 | 동일 지도·OD 모드 조건에서 travel-time CDF, W1, p50/p95, 시간대별 demand/route |
| **Caltrans PeMS** https://dot.ca.gov/programs/traffic-operations/mpr/pems-source | 고속도로 detector speed/flow/occupancy, 무료 계정 요청 | freeway shock, wave-speed, queue discharge capacity, 도시 교차로 자료로 오용 금지 |

**평가 지표:** 1) class/gap/density에 조건화한 속도분포 `W1(P_v,Q_v) [m/s]`, gap 분포 `W1 [m]`, relative speed `W1`, acceleration 및 jerk, velocity autocorrelation, conditional variance. 2) link·시간별 관측치 (o)와 시뮬레이션 (m)에 대한 `GEH=√(2(m-o)²/(m+o))` (둘 다0은0; 동일 시간집계·동일 관측위치만), normalized flow MAE, speed RMSE. 3) bottleneck `onset_s, duration_s, throughput_veh/h, queue_length_m, spillback distance, shock-wave speed_mps` 및 MFD/hysteresis. 4) route OD 조건부 `W1(T_sim,T_obs) [s]`, p50/p90/p95와 이탈/미배정 비율, CDF/CRPS. 5) `peak_RSS, wall, p50/p95 tick, per mode, mass error, memory_scaling(N,K), accuracy/resource Pareto`. 단일 평균속도 또는 single GEH는 사실성 판단의 충분조건이 아니다.

**자료별 설계:** 초기 연구에서는 (A) inD의 한 실제 교차로 지형과 trajectory entry times를 맞추어 micro/kinetic calibration, 다른 날짜·관측 구간 또는 교차로로 holdout; (B) UTD19의 한 실제 도시/동일 지리 detector 집합과 관측 inflow를 사용해 macro/meso calibration, 다른 날·detector로 validation; (C) 동일 도시 도로망·차량종류가 정합될 때만 TLC/Chicago trip/speed를 별도 외적검증. 원래 합성 100k 도시와 지역이 다른 관측을 직접 행대행 비교해 predictive validation이라 부르지 않는다. InD의 `sigma`는 직접 관측되지 않는 **latent control**이므로 `alpha,nu,tau`의 식별가능성 및 측정오차·속도 smoothing 의존성을 평가한다.

**권위 가이드:** FHWA Traffic Analysis Toolbox 2019 ch.5 https://ops.fhwa.dot.gov/publications/fhwahop18036/chapter5.htm 는 최소 하나의 bottleneck-local 성능 측도와 하나의 route travel-time/speed 성능 측도를 함께 권고한다. 또한 holdout field data를 calibration에 혼합하지 않아야 한다. 구식 GEH<5 관행을 물리학 정리 또는 보편적 패스 기준으로 승격하지 않고, 비교 대상과 관측 불확도·실행 목적에 따라 기준을 명시한다. 실제 관측파일을 아직 다운로드/처리하지 않았으므로 모든 field score는 `NOT_MEASURED`.

## R10. 실제 종료·보존·다음 구현 경계

**이론 산출:** 정리1–5, OVM 조건부 선형화, 물리 의미 반례, R7 1차원 독립 프로토타입, 실제 도시 자료·측도 대응표, 코딩 구현 계약. 새로운 publication-level 전 네트워크 미시→거시 동치/실측 우월성은 `UNRESOLVED`이다. 특히 **이론 R1–R10의 산출물을 구성하는 것과 원래 V03 수용은 별개의 작업**이다.

**개별 다음 단계:** 본 코딩 루프에서는 (i) Rust opt-in KCMB 동적 moment/flux kernel, (ii) bounded node and dual metre-count supply, (iii) 작은 lane/gap shadow와 exact deterministic state parity, (iv) bounded-memory step 및 shock (L^1) gates, (v) 자료용 observation adapter로 순서화한다. 기존 Rust V1 및 PLAN의 default physics는 그대로 두며, 새로운 approximation model에 상응하는 `model_id`·checkpoint schema를 사용한다.

**증거 파일:** `tools/research/kc_bridge_reference.py`, `tools/research/kc_link_delay_oracle.py`, `tests/research/test_kc_bridge_20261118.py`, `artifacts/v1_research_20261118/{kc_bridge_reference,kc_link_delay}.json`, 이전 R7의 `frozen_relaxation.json`. 반례는 code/derivation에서 `NUMERICALLY_CHECKED`와 `DERIVED`로 각각 구분한다. Native subagent spawning은 도구가 없어 `NOT_RUN`; 직렬 직접 감사만 수행했다.

현재 PR #41의 기록된 V03 성능/수용은 **19/21·BLOCKED·24h 0/9회**, 여전히 유지한다. 본 이론 연구는 그 수치를 직접 개선했다고 승격하지 않으며, 유한상태 알고리즘의 **구조적 성장 한계 정리**와 다음 실제 성능검증 설계를 제공한다.
