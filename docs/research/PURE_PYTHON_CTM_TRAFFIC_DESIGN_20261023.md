# 순수 Python 유한저장 교통류 연구 lane 설계

- 저장소 기준: `main@01c80b432344f94209daaa198bb1eb007839fc7f`
- 연구 일자: 2026-10-23
- 상태: `RESEARCH-READY`, `NOT DEFAULT-READY`
- 실행 경로: `metroflow.pure_traffic`
- 구현 제약: Python 표준 라이브러리만 사용, NumPy/JAX/CUDA/GPU/Rust 호출 없음

## 1. 연구 질문과 범위

현재 MetroFlow의 authoritative runtime은 link queue, finite storage, turn token, 개별 vehicle identity를 이미 결합한다. 그러나 한 link를 하나의 aggregate queue로 보는 경우, link 내부의 유한 전파시간과 전방 shock, 후방 spillback을 공간적으로 직접 분해하기 어렵다. 이번 연구의 질문은 다음과 같다.

> 작은 도시 도로망에서 차량 보존, 유한 저장용량, shock 및 spillback, diverge의 head-of-line blocking, merge priority, movement starvation을 동시에 검증할 수 있는 순수 Python 기준 해법을 만들 수 있는가?

이번 lane은 기존 `point_queue_v1` 또는 `spatial_queue_v1`을 교체하지 않는다. 독립적인 작은 network benchmark와 이후 authoritative runtime 개선을 위한 reference implementation만 제공한다. 동적 경로선택, 신호최적화, lane-changing, 교정된 실도시 예측은 범위 밖이다.

## 2. 근거 상태

| 항목 | 상태 | 근거 |
|---|---|---|
| LWR 연속 보존법칙 | established | Lighthill-Whitham 및 Richards [1], [2] |
| CTM의 유한체적/Godunov 해석 | literature-supported | Daganzo [3], [4] |
| finite storage와 backward spillback | literature-supported | CTM 및 LTM 문헌 [3], [4], [9] |
| node demand/supply/priority 제약 | literature-supported | Tampère et al. [5], Jabari [6] |
| perfect network-wide FIFO의 높은 계산비용 | literature-supported | Carey et al. [7], Bar-Gera and Carey [8] |
| 정수 residual 누적오차가 1 vehicle 미만 | derived, Wolfram-checked | §5.3 |
| 최대처리량 보존형 token 선택 | derived, implementation-verified | §6 |
| 세 교정 실험의 결과 | numerically checked | §9, validation artifacts |
| 실제 도시 교통에 대한 calibration | unresolved | 외부 관측자료를 사용하지 않음 |

## 3. 후보 모형 비교와 선택

### 3.1 한 link당 point 또는 spatial queue

장점은 계산비용과 통합 용이성이다. finite storage를 두면 source blocking과 spillback은 나타낼 수 있다. 그러나 queue가 link 내부 어디까지 전파됐는지, incident가 link 안에서 어떤 shock profile을 만드는지는 직접 표현하지 못한다.

### 3.2 Link Transmission Model

LTM은 cumulative count로 link-scale kinematic wave를 효율적으로 다룬다 [9]. 대규모 network에는 매력적이지만, 이번 연구에서는 cell occupancy를 직접 그려 적대적 시각 검수를 해야 하고, vehicle identity와 정수 token을 작은 상태공간에서 추적해야 한다. 따라서 첫 reference lane으로는 CTM이 더 투명하다.

### 3.3 미시적 car-following

가속, 차두간격, lane-changing을 직접 다룰 수 있다. 그러나 lane-level microscopic default는 현재 저장소 정책 범위 밖이고, 이번 질문의 핵심인 conservation, node allocation, spillback을 검증하기에는 자유도가 과도하다.

### 3.4 선택

이번 연구는 triangular fundamental diagram을 사용하는 multi-cell CTM을 채택한다. 각 vehicle은 개별 정수 identity로 유지하고, 연속 CTM flux는 residual accumulator를 통해 정수 token으로 변환한다. Node에서는 처리량 최대화를 1차 목표로 고정하고, 공정성과 waiting age는 2차 선택 규칙으로 적용한다.

## 4. 상태공간과 단위

Directed link \(e\)의 입력은 다음과 같다.

- 길이 \(L_e\) [m]
- lane 수 \(\ell_e\)
- 자유류 속도 \(v_e\) [m/s]
- 후방파 속도 \(w_e\) [m/s]
- jam density \(k_{j,e}\) [veh/km/lane]
- lane capacity \(q_{\max,e}\) [veh/h/lane]
- merge priority weight \(p_e>0\)

시간간격은 \(\Delta t\) [s]다. Cell 수 \(M_e\)와 길이 \(\Delta x_e=L_e/M_e\)는

\[
M_e=\max\left(1,\left\lfloor\frac{L_e}{v_e\Delta t}\right\rfloor\right)
\]

으로 시작하되, 다음 CFL 조건을 통과하지 못하면 fail-closed한다.

\[
\lambda_{v,e}=\frac{v_e\Delta t}{\Delta x_e}\le 1,
\qquad
\lambda_{w,e}=\frac{w_e\Delta t}{\Delta x_e}\le 1.
\]

Wolfram 검산에서 이는 각각 \(\Delta x_e\ge v_e\Delta t\), \(\Delta x_e\ge w_e\Delta t\)와 동치다.

Cell의 정수 저장용량은

\[
N_{j,e}=\left\lfloor
k_{j,e}\,\ell_e\,\frac{\Delta x_e}{1000\ \mathrm{m/km}}
\right\rfloor
\]

이다. 최소 1 vehicle을 요구한다.

## 5. Link CTM

### 5.1 Triangular fundamental diagram

Critical density와 이론적 lane capacity는

\[
k_c=\frac{w}{v+w}k_j,
\qquad
q_{\max}=\frac{vw}{v+w}k_j.
\]

입력 capacity가 이 이론적 상한보다 크면 configuration을 거부한다. 이는 parameter set 내부의 차원적·물리적 모순을 초기에 차단한다.

### 5.2 Sending과 receiving

Cell \(i\)에 \(n_i^t\)대가 있을 때, 한 tick의 sending 및 receiving target은

\[
S_i^t=\min\left(\lambda_v n_i^t,Q\right),
\]

\[
R_{i+1}^t=\min\left(Q,\lambda_w(N_j-n_{i+1}^t)\right),
\]

\[
y_{i\to i+1}^t=\min(S_i^t,R_{i+1}^t)
\]

이다. Incident는 \(Q\)와 \(\lambda_v\)에 bounded multiplier를 적용한다. 모든 내부 이동량은 pre-step state에서 계산하고 한 번에 commit하므로 한 tick에 두 cell boundary를 건너는 차량은 없다.

### 5.3 정수화와 residual

연속 target \(q_t\)를 vehicle token으로 바꿀 때

\[
b_t=\lfloor r_t+q_t\rfloor,
\qquad
r_{t+1}=r_t+q_t-b_t,
\qquad 0\le r_t<1
\]

을 사용한다. 따라서

\[
\sum_{t=0}^{T-1} b_t + r_T
=
\sum_{t=0}^{T-1} q_t+r_0
\]

이고,

\[
\left|\sum b_t-\sum q_t\right|<1.
\]

Wolfram에서 3-step recurrence를 기호적으로 전개해 telescoping identity가 정확히 0임을 확인했다. 사용하지 못한 정수 capacity는 bank하지 않고, fractional residual만 보존한다.

## 6. Holding-free 최대처리량 node solver

### 6.1 Feasible set

Movement \(m=(i,j)\)의 정수 flow를 \(f_m\)라 하면

\[
0\le f_m\le D_m,
\qquad
0\le f_m\le C_m,
\]

\[
\sum_{m:\,\mathrm{from}(m)=i} f_m\le S_i,
\]

\[
\sum_{m:\,\mathrm{to}(m)=j} f_m\le R_j
\]

를 만족해야 한다. \(D_m\)은 movement demand, \(C_m\)은 movement 또는 signal capacity, \(S_i\)는 upstream sending token, \(R_j\)는 downstream receiving token이다.

### 6.2 1차 목표

1차 목표는

\[
F^*=\max\sum_m f_m
\]

이다. 구현은 작은 bipartite residual graph에 대한 deterministic Dinic max-flow로 \(F^*\)를 계산한다. Wolfram의 2-in/2-out integer test에서는 각 upstream과 downstream capacity가 5일 때 정확한 최대값 10을 확인했다.

### 6.3 2차 목표와 안전한 token 선택

단순 lexicographic 선택은 maximum-flow total을 유지하더라도 한 approach를 장시간 굶길 수 있다. 이를 방지하기 위해 각 candidate token을 공정성 순서로 정렬한 뒤, 그 token을 사용한 후 남은 max-flow가 정확히 \(F^*-1\)인지 다시 계산한다. 이 조건을 통과하는 첫 candidate만 commit한다.

따라서 공정성 규칙은 maximum throughput을 낮출 수 없다. 남은 max-flow가 0이 될 때까지 반복하므로, feasible token이 남아 있는데 solver가 멈추는 artificial holding도 없어야 한다.

### 6.4 Weighted virtual finish

Incoming link \(i\)의 priority weight를 \(p_i\)라 하면 다음 marginal key를 사용한다.

\[
K_i=V_i+\frac{s_i+1}{p_i},
\]

여기서 \(V_i\)는 이전 tick의 virtual finish, \(s_i\)는 현재 tick에서 이미 선택된 token 수다. Tick 후

\[
V_i\leftarrow V_i+\frac{f_i}{p_i}
\]

로 갱신하고 active incoming들의 최소값을 빼 수치크기를 제한한다. Weight 2:1의 지속 포화 merge에서는 30 token 뒤 20:10을 준다는 것을 Wolfram과 구현 시험으로 확인했다.

### 6.5 Waiting-age priority

동일 incoming 안에서 고정 movement priority만 쓰면 minority turn이 굶을 수 있다. Demand가 있으나 service가 0인 movement는 waiting age를 1 증가시키고, service가 있으면 감소시킨다. 최대처리량을 보존하는 candidate들 사이에서는 waiting age가 큰 movement를 먼저 선택한다.

## 7. FIFO 의미론

두 모드를 명시적으로 분리한다.

- `strict`: exit cell의 맨 앞 movement와 같은 연속 vehicle만 demand로 인정한다. Single-lane full FIFO의 보수적 근사다.
- `movement`: exit cell을 movement별 FIFO bucket으로 분리한다. Lane-group 또는 partial-FIFO 근사이며, blocked turn 뒤의 open turn이 통과할 수 있다.

`movement` 모드는 완전한 network-wide FIFO를 보장하지 않는다. CTM에서 cell-level FIFO가 link 또는 route-level FIFO를 자동 보장하지 않는다는 문헌상의 문제 [7], [8]를 claim gate에 보존한다.

## 8. 원자적 상태전이와 보존법칙

한 tick은 다음 순서로 계산되지만, 모든 flux는 pre-step state를 기준으로 한다.

1. 요청 release와 source reservoir 등록
2. incident multiplier 계산
3. 내부 cell sending/receiving과 token 산출
4. exit movement demand와 entry receiving 산출
5. movement capacity token 산출
6. node max-throughput 및 fairness allocation
7. 내부 이동, node 이동, sink completion, source admission을 하나의 commit으로 반영
8. vehicle identity, storage, route position, residual, 질량 불변량 검증

두 인접 cell에서 내부 flux \(y\)는

\[
(n_1-y+A)+(n_2+y-Z)-(n_1+n_2)=A-Z
\]

처럼 정확히 상쇄된다. 전역적으로

\[
N_{\mathrm{released}}
=
N_{\mathrm{pending}}+N_{\mathrm{active}}+N_{\mathrm{completed}}
\]

을 매 tick 검사하며, 오차가 0이 아니면 state를 반환하지 않고 예외를 발생시킨다.

Preloaded benchmark state도 각 vehicle의 현재 link와 route position이 일치하는지 확인한다. 잘못 배치된 vehicle은 simulation 시작 전에 거부한다.

## 9. 세 차례 적대적 수정 루프

### Round 0, strict FIFO + lexicographic allocation

320 vehicles를 4 vehicles/tick으로 diamond corridor에 주입하고, upper route의 ticks 18-41에 incident를 가했다.

- tick 220에 243 completed, 77 active
- source-link peak occupancy 0.928
- peak pending 75
- 원인: upper turn의 head vehicle가 blocked되면 lower turn도 full-link FIFO에 묶임

이는 실제 multilane 또는 turn-pocket urban approach에 과도한 blocking이다.

### Repair 1, movement-group FIFO

Movement별 FIFO bucket을 사용했다.

- 320/320 completed
- clear tick 174
- upper/lower downstream branch cell occupancy가 최대 약 0.86까지 상승
- queue가 source 한 점에 갇히지 않고 bottleneck upstream cell들로 전파

시각적으로 shock와 dissipation이 link cell 단위로 나타났다.

### Repair 2, weighted fair maximum-throughput merge

Preloaded saturated 2:1 merge에서 첫 10 ticks를 비교했다.

- lexicographic: A=30, B=0
- weighted fair: A=20, B=10
- holding events: 0

처리량은 유지하면서 authored priority ratio를 구현했다.

### Repair 3, waiting-age priority

Shared approach에서 major turn의 movement weight를 4, minor를 1로 두고 첫 15 ticks를 비교했다.

- age 없음: major=15, minor=0
- age 적용: major=8, minor=7
- 최종 maximum wait: 1 tick

고정 priority의 starvation을 제거하되, 매 token마다 최대처리량 보존 조건을 재검사했다.

상세 시각 판정은 `ADVERSARIAL_VISUAL_AUDIT.md`와 SVG artifacts에 기록한다.

## 10. 구현 구조

- `src/metroflow/pure_traffic/ctm.py`
  - immutable input/state/result dataclass
  - geometry 및 CFL 검증
  - triangular CTM
  - residual tokenization
  - exact maximum-throughput node solver
  - atomic commit, replay fingerprint, invariant validation
- `src/metroflow/pure_traffic/scenarios.py`
  - diamond incident corridor
  - weighted merge
  - priority diverge
  - controlled preloaded initial state
- `tools/run_pure_python_ctm_research.py`
  - bounded experiments
  - strict JSON
  - dependency-free SVG audit atlas, evolution, time series
- `tools/validate_pure_python_ctm_research.py`
  - 9-case seed/load matrix
  - replay parity
  - AST accelerator import/name scan
- `tests/test_pure_python_ctm.py`
  - conservation, travel time, spillback, fairness, FIFO, CFL, preloaded state, route identity, maximum throughput, no-NumPy import

`metroflow.pure_traffic`를 별도 package로 둔 이유는 기존 `metroflow.traffic.__init__`가 NumPy runtime 모듈을 import하기 때문이다. 새 package는 root package의 표준-library state import 외에 외부 numerical dependency를 끌어오지 않는다.

## 11. 검증 상태

### TDD evidence

- RED 1: `metroflow.pure_traffic.ctm` 부재로 import failure
- GREEN 1: core 6 tests 통과
- RED 2: `simulate(initial_state=...)` 미지원
- GREEN 2: controlled initial-condition 실행 통과
- RED 3: route position과 현재 link가 불일치한 preloaded state를 거부하지 않음
- GREEN 3: fail-closed route-link identity invariant 추가
- 최종 focused suite: 12 passed

### Seed/load matrix

Seeds 7, 41, 97과 다음 load를 교차했다.

- 120 vehicles, 2/tick, 120 ticks
- 240 vehicles, 4/tick, 180 ticks
- 320 vehicles, 4/tick, 220 ticks

9/9 cases에서 다음을 만족했다.

- completed=total
- pending=active=0 at horizon
- mass error=0
- node holding events=0
- cell occupancy ratio \(\le1\)
- 모든 residual이 \([0,1)\)
- deterministic replay fingerprint parity

## 12. 적대적 한계와 금지 claim

### 12.1 First-order equilibrium limitation

Triangular FD는 density와 flow 사이의 equilibrium closure다. Acceleration, hysteresis, capacity drop, stop-and-go instability를 독립 state로 표현하지 않는다. 따라서 shock와 spillback은 표현하지만 실제 차량 궤적의 미시적 진동을 재현한다고 말할 수 없다.

### 12.2 Intersection conflict limitation

현재 node capacity는 movement capacity와 optional green cycle로 표현된다. 2026 conflict-aware CTM 연구는 unsignalized conflict가 저수요에서도 delay를 만들지만 standard CTM은 capacity constraint가 비활성일 때 이를 놓칠 수 있음을 지적한다 [10]. 이번 lane은 opposing-demand-dependent free-speed 또는 conflict cell을 구현하지 않았다.

### 12.3 FIFO limitation

Movement-group FIFO는 lane-group availability를 가정한다. Lane 수, turn pocket 길이, lane-changing friction이 명시적으로 없으므로 perfect lane FIFO 또는 route FIFO를 주장하지 않는다.

### 12.4 Calibration limitation

Capacity, jam density, wave speed, priority, incident multiplier는 authored parameters다. 실제 detector, probe trajectory, signal timing, OD posterior로 calibration하지 않았다.

### 12.5 Scale limitation

정확한 max-throughput 보존형 token 선택은 각 token candidate마다 작은 max-flow를 다시 푼다. 작은 network의 reference oracle에는 적합하지만 production city network의 기본 solver로 승격하기 전에 algorithmic profiling과 batched node kernel이 필요하다.

## 13. Claim gate와 다음 안전한 단계

### 허용

- 작은 controlled network에서 finite travel time, storage, shock/spillback
- 정수 vehicle identity와 exact global conservation
- tested node에서 holding-free maximum throughput
- weighted merge priority와 bounded movement starvation
- deterministic replay
- 표준 라이브러리만 사용하는 independent lane

### 금지

- 실제 도시 교통의 calibrated forecast
- perfect network-wide FIFO
- lane-level microscopic fidelity
- unsignalized conflict delay의 일반적 재현
- production default readiness

### 다음 안전한 단계

1. conflict-aware opposing-demand delay와 fixed signal stage를 별도 node operator로 추가한다.
2. triangular FD와 capacity-drop FD를 동일 Riemann test에 비교한다.
3. lane-group partial-FIFO parameter를 명시하고 turn-pocket blocking 실험을 추가한다.
4. current authoritative runtime과 동일 request trace를 사용한 parity/non-parity ledger를 만든다.
5. 그 뒤에만 Python 3.12 full repository CI와 runtime integration PR을 검토한다.

## 참고문헌

BibTeX source of truth는 `PURE_PYTHON_CTM_REFERENCES_20261023.bib`다.
