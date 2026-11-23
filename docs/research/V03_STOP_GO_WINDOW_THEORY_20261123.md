# V03 stop–go window: clipped finite response와 공동 FIFO service

## 결과와 근거 상태

**derived:** 순간 최소속도 \(a>0\)를 요구하던 기존 response-memory 관측 범위를 확장했다. 유한한 시간창마다 보증되는 추진량에서 clipped continuous motion의 거리 하한을 유도하고, 별도의 joint node service와 결합해 실제 정지 구간을 허용하는 outlet 상한을 구성한다.
**literature-supported/reused:** strict service curve, FIFO cumulative-rank delay와 단계 합성은 고전 network calculus 및 기존 MetroFlow 누적 서비스 이론을 재사용한다.
**implementation-verified/numerically checked:** 별도 typed research API, 26개 표적 검사, 정확한 Python characteristic 대조, Decimal85 비교, 유리수 경로 판별을 실행했다.
**unresolved:** 일반 endogenous native network에서 미래 추진량·receiving·rank 상한의 사전 보증. Production routing과 V03 수용은 변경하지 않았다.

이 결과는 자료구조 최적화의 이론이 아니라, 정지·재출발이 있는 mesoscopic 운동에서 유한한 경로 시간 정보를 구성하는 배경 이론의 확장이다.
전 세계 최초성은 심사하지 않았다. 초기 후보와 보류 이유는 artifacts/v03_constructive_remodel_20261123/R2_theory_portfolio.md에 보존한다. 두 통과 적분의 parameter identification 후보 C는 보류했다.

## 1. 두 물리 시계와 source contract

T02는 실제 연속 속도 \(v\)와 latent probability를 구별하고, T04의 motion endpoint ETA는 node-service 대기를 제외한다.
따라서 실제 속도를 \(g(t)v(t)\)로 바꿔 적신호에서 순간 정지시키지 않는다.
아래 모델은 같은 cohort가 **연속 운동으로 endpoint에 도착한 시각 \(u\)**와 **FIFO queue에서 마지막 tagged mass rank가 유출한 시각 \(E\)**를 분리한다.

기존 finite_response_probe_certificate.py의 양의 forcing/속도 하한을 사용하는 완성 통과량→endpoint 기억 명제는 그대로 유지한다.
또한 2026-11-22 V03_DYNAMIC_FIFO_AGE_R1_R10_C1_C10_20261122_KO.md에서 이미 유도한 누적 서비스 역함수와 route delay를 신규 명제로 세지 않는다.

원 단위는 s, m, m/s, m/s², vehicle-equivalent mass(veh)다.
\(J\)는 목표속도의 시간적분[m]이고 \(J_s\)는 서비스 차량량[veh]이며 서로 다른 물리량이다.
이는 동일 homogeneous characteristic, 고정 \(\tau,A,B,b\), 같은 movement의 FIFO rank에 대한 조건부 모형이다.
중간의 bulk mixing jump, 조성 변화에 의한 \(\tau\) 변경, 다른 field/context, 임의 rerouting은 포함하지 않는다.

## 2. 유한 가감속과 창 추진량

\(t_0\)에서 출발하는 길이 \(\ell>0\)의 characteristic을 고려한다.

\[
\dot v=\operatorname{clip}\left(\frac{V-v}{\tau},-B,A\right),
\qquad \dot x=v,
\qquad 0\le V\le b,\quad
0\le \underline v_0\le v(t_0)\le b.
\]

여기서 \(\tau>0\), \(b>0\), \(A>0\), \(B\ge0\)이고 \(V\)는 유계 가측 함수다.
속도는 absolutely continuous이며 \([0,b]\)는 invariant다. 양 끝에서 vector field가 바깥을 향하지 않기 때문이다.
진공이나 혼합 projection을 이 characteristic으로 암묵 대체하지 않는다.

각 선언된 창 \(I_k=[t_0+kH,t_0+(k+1)H]\), \(H>0\)에 대해

\[
\int_{I_k}V(s)\,ds\ge J,\qquad 0<J\le bH
\]

를 가정한다. 현재 최소속도나 목표속도가 0이어도 된다.
조건은 사용할 마지막 창까지 사전에 유효해야 한다. 과거 평균의 외삽 또는 미래 실현값을 본 뒤 추정한 \(J\)가 아니다.

### 명제 1. Clipping에 견디는 비교계

\[
\eta=\min\left(1,\frac{A\tau}{b}\right)>0
\]

이면 거의 모든 시각에서

\[
\dot v\ge\frac{\eta V-v}{\tau}.
\]

**증명.** \(d=(V-v)/\tau\le0\)이면 clipping은 \(d\)보다 큰 값을 주며 \(V\ge0,\eta\le1\)에 의해
\(d\ge(\eta V-v)/\tau\)다.
\(d\ge0\)이면 \(d\le b/\tau\)와 \(\eta d\le A\) 때문에
\(\min(A,d)\ge\eta d=(\eta V-\eta v)/\tau\ge(\eta V-v)/\tau\)다.
제동 cap \(B\)는 derivative를 더 작게 하지 않으므로 별도의 양의 하한은 필요 없다.

\(z(t_0)=\underline v_0,\ \dot z=(\eta V-z)/\tau\)로 잡으면
\(\frac{d}{dt}[e^{(t-t_0)/\tau}(v-z)]\ge0\)이며 \(v(t_0)-z(t_0)\ge0\)이다.
그러므로 \(v\ge z\), 이를 적분하면

\[
x(t_0+h)-x(t_0)\ge
\tau\underline v_0(1-e^{-h/\tau})
+\eta\int_0^h(1-e^{-(h-r)/\tau})V(t_0+r)\,dr. \tag{1}
\]

### 명제 2. 유한창 거리 하한과 constructive passage upper

정수 \(n\ge1\)에 대해

\[
\boxed{
L_n(\underline v_0)=
\tau\underline v_0(1-e^{-nH/\tau})+
\eta\left[
nJ-
b\tau(1-e^{-J/(b\tau)})
\frac{1-e^{-nH/\tau}}{1-e^{-H/\tau}}
\right]
} \tag{2}
\]

는 \(nH\) 동안 이동한 거리의 하한이다. \(L_n\ge\ell\)이면 실제 최초도달 시각은 \(t_0+nH\) 이하다.

**증명.** (1)의 kernel \(K(r)=1-e^{-(nH-r)/\tau}\)는 \(r\)에 대해 감소한다.
한 창의 끝점을 \(e\), \(c=e-J/b\), \(V_*=b\,1_{[c,e]}\)라 두자.
\(F=V-V_*\)는 \(r<c\)에서 nonnegative, \(r>c\)에서 nonpositive이고 \(\int F\ge0\)다.
따라서

\[
\int KF=\int(K-K(c))F+K(c)\int F\ge0.
\]

즉 허용된 target를 창 마지막 \(J/b\)초에 몰아 놓는 배치가 그 창의 적분을 최소화한다.
\(k\)번째 창의 최소 기여는

\[
J-b\tau(1-e^{-J/(b\tau)})e^{-(n-k-1)H/\tau}
\]

이고 기하급수 합으로 (2)를 얻는다. 연속이고 nondecreasing인 \(x\)가 \(\ell\)을 넘으면 그 이전에 최초도달하므로 마지막 결론이 따른다.

\(r=e^{-H/\tau}\), \(C_0=b\tau(1-e^{-J/(b\tau)})<J\)라 쓰면

\[
L_{n+1}-L_n
=\tau\underline v_0r^n(1-r)+\eta(J-C_0r^n)>0.
\]

따라서 full-window threshold를 단조 탐색할 수 있다.
또한 \(K_0=C_0/(1-r)\)에 대해 \(L_n\ge\eta(nJ-K_0)\)이므로

\[
N_{\rm sufficient}=
\left\lceil\frac{\ell/\eta+K_0}{J}\right\rceil \tag{3}
\]

는 계산 가능한 충분 창 수다. 이는 최소 창 수의 상한이다.
유한 validity horizon 안에 이 충분조건이 들어오지 않으면 허용된 창만 사용한다.
실패 반환은 HORIZON_UNCERTIFIED이며 물리적 UNREACHABLE이 아니다.

### Sharpness, 극한과 보존 범위

\(\eta=1\)만으로 sharpness를 주장하지 않는다. 가속·제동 clipping이 모두 비활성인 class, 예컨대 \(A,B\ge b/\tau\)에서는 (1)이 정확하고 각 창의 마지막 pulse가 (2)에 등호를 준다.
작은 \(B\)에서 제동 clipping이 활성화되면 더 멀리 이동할 수 있다.
\(\eta<1\)에서는 conservative comparison bound만 주장한다.

비clipped \(\tau\to0\) 극한은 target 적분으로 돌아간다.
\(A\to\infty\)만으로 제동 clipping은 제거되지 않는다.
\(J\to0\)이면 증가하는 forcing 항이 사라져 coast만으로 도달이 불가능할 수 있다.
모든 \(L_n\) 항은 m이며 \(\eta\)는 무차원이다.
전체 도시에서 gap/cap이 지속적으로 0이면 \(J>0\) 조건 자체가 성립하지 않을 수 있다.

## 3. Joint service와 tagged FIFO rank

한 movement에 배정된 saturation capacity \(C>0\)[veh/s], green fraction \(0\le g\le1\),
receiving limit \(0\le R\le C\)[veh/s]에 대해

\[
c(t)=\min\{C g(t),R(t)\}
\]

를 사용 가능한 서비스율로 둔다.
Queue가 backlogged이면 이 movement의 work-conserving service는 \(c\)를 사용한다.
여러 movement가 경쟁하는 node의 명목 총 capacity를 이 예약된 capacity로 대체하면 안 된다.
빈 queue의 사용하지 않은 service를 질량으로 저장하지 않는다.

실제 motion-ready 시각 \(u\)에 tagged rank까지의 앞선 질량과 tagged 질량 합이 \(W>0\)[veh] 이하라고 사전에 보증한다.
이후 그 rank 뒤에 도착한 질량은 FIFO에서 추월하지 않는다.
\(W\)는 그 준비 시각에서의 모집단에 대한 상한이며 journey birth moment나 완료 route 평균과 다르다.

### 명제 3. Separate marginal에서 joint service를 구성하는 충분조건

모든 관련 길이 \(H_s\) 창에서
\(\int Cg\ge J_g,\ \int R\ge J_r\)라면

\[
\int c\ge J_s:=\max(0,J_g+J_r-C H_s). \tag{4}
\]

이는 \(0\le a,b\le C\)에서 \(\min(a,b)\ge a+b-C\)를 적분하면 된다.
\(J_s>0\)인 경우에만 positive service를 결론낸다.
더 강한 direct joint lower가 독립적으로 보증되면 그것을 별도로 사용할 수 있다.

**판별 반례.** \(C=2\), \(H_s=10\), green과 receiving이 각 5초씩 있으면 각각의 적분은 10veh다.
서로 [0,5]와 [5,10]에 위치하면 joint service는 0이고, 같은 [5,10]에 있으면 10veh다.
양의 marginal 평균 자체가 유한 통과를 보증하지 않는다.
반면 green=[0,7], receiving=[3,10]이면 \(J_g=J_r=14\), 겹치는 [3,7]에서 \(J_s=8\)veh를 정확히 달성한다.

### 명제 4. 실제 정지 서비스를 포함하는 link upper

준비 시각 \(u\)부터 매 길이 \(H_s\) 창에서 joint service \(J_s>0\)가 보증되면

\[
E_{\rm link}\le u+
\left\lceil\frac{W}{J_s}\right\rceil H_s.
\]

rank가 미완료인 동안 해당 앞선 질량이 남아 있으므로 queue는 backlogged이다.
필요한 창 수만큼 제공한 cumulative service가 \(W\)에 도달하므로 FIFO rank도 처리된다.
명제 2의 \(u\le t_0+NH\)와 결합하면

\[
\boxed{E_{\rm link}\le
t_0+NH+\left\lceil W/J_s\right\rceil H_s.} \tag{5}
\]

Node service와 motion의 단위·질량·시계를 분리한 구성이다.
식 (5)의 FIFO/rank 단계는 고전 strict-service 논법의 적용이며 신규 수학적 발견으로 주장하지 않는다.
새로운 물리 입력은 clipping과 zero forcing을 허용하는 명제 1–2다.

## 4. 시간창 phase, 인과성, finite horizon

SLIDING은 validity 내부의 모든 시작시각에 대해 해당 창 보증이 성립한다는 뜻이다.
ALIGNED는 선언된 origin과 정수 \(k\)에 대해 [origin+kH,origin+(k+1)H]만 보증한다.
두 조건을 서로 바꾸지 않는다.

Aligned motion은 query entry 다음 grid로 이동해서 시작한다. 그 이전의 nonnegative 이동은 무시하며, 그 grid에서의 initial-speed lower는 0으로 낮춘다.
이렇게 추가한 phase delay는 최대 한 창이다.
Aligned service도 실제 ready 이후 다음 grid까지 기다리는 upper를 사용한다.
ready 시각이 정확히 알려져 있지 않아도 next-grid 함수와 고정 창 수를 더한 함수가 nondecreasing이므로 \(u\)의 upper에서 평가하면 안전하다.

각 ExAnteBasis는 context, authority, available_at, valid_from, valid_until을 담는다.
authority는 caller가 어떤 가정을 제공했는지 기록하며 자동 증명이 아니다.
query는 decision<=entry이고 모든 basis는 decision까지 전달돼 있어야 한다.
J는 사용한 모든 forcing 창, W는 가능한 모든 ready 시각, J_s는 사용한 모든 service 창에 유효해야 한다.
expiry를 늘려 성공시키지 않는다.

## 5. 경로 판단의 실제 positive result

예제 A는 \(b=4\), \(\tau=2\), \(A=B=1\), \(H=8\), \(J=16\), \(\underline v_0=0\), \(\ell=20\)이다.
8초 주기 앞4초 target0, 뒤4초 target4의 선언된 이력을 둔다.
정확 Python characteristic의 실제 motion 도달은 15.139484898s이고, 위 10초 joint service에 5veh cohort가 도착하면 최종 rank의 실제 outlet은 23.639484898s다.
그 안에 실제 0-service 대기6s가 있다.
사전 constructive upper는 \(24+10=34\)s다.

Float threshold와 독립인 엄밀한 수치 분리를 다음과 같이 얻는다.
\(q=e^{-2}\)라 두면

\[
L_3-20
=4q\{(1-q)(1+q^2)+q^4\}>0.
\]

양의 exponential series와 geometric tail로
\(7<34913/4725<e^2<213359/28875<8\)을 exact Fraction으로 확인했다.
따라서 \(1/8<q<1/7\)이고

\[
L_3-20>4(1/8)(6/7)=3/7\ {\rm m}.
\]

별도의 합법 경로 B가 길이72m, 속도 cap2m/s, nonnegative service delay를 가진다면 최초 도달의 하한은 정확히36s다.
따라서 같은 출발시각에서

\[
E_A\le34<36\le E_B
\]

로 A가 엄밀히 앞선다. 이는 새로운 모델 전제 아래의 실제 pairwise ordering이다.
기존 \(a>0\) 관측 API는 \(a=0\)에서 적용 불가하므로, baseline이 실제로 B를 선택했다고 꾸며내지 않는다.
기존 planner나 production rerouting은 실행하지 않았다.

## 6. 구현과 실제 검증

- src/metroflow/v1/stop_go_window_certificate.py: frozen typed input/result, causal/context/phase/horizon 검사, motion lower의 exponential bracketing와 binary search, joint service와 rank 합성.
- tests/research/test_v03_stop_go_window_20261123.py: 26개 표적 검사, 실제26passed/0.23s.
- tools/research/v03_stop_go_window_experiment_20261123.py: 사전에 생성된 stop–go 이력, 기존 Python clipped characteristic, 별도 periodic FIFO service 적분, Decimal85 대조, exact rational route proof.
- artifacts/v03_constructive_remodel_20261123/R5_theory_experiment.json 및 R7_theory_experiment.json: 실제 크기/horizon/wall과 source identity.

| tier | profiles | 각 실제 horizon [s] | characteristic 구간 | 거리 하한 검사 | wall [s] |
|---|---:|---:|---:|---:|---:|
| 1 | 16 | 32 | 512 | 64 | 0.00943558 |
| 2 | 64 | 128 | 8,192 | 1,024 | 0.06643664 |
| 3 | 256 | 512 | 131,072 | 16,384 | 0.69762463 |
| 4 | 512 | 2,048 | 1,048,576 | 131,072 | 4.76927277 |

총848개 사전 생성 이력, 1,188,352개 characteristic 구간, 148,544개 거리 하한 검사를 실제로 수행했다.
별도의 Decimal85 비교1,696개에서 최대 float 거리 오차는 \(5.7403202\times10^{-13}\)m였고,
선언된 numeric margin 대비 최대 비율은 \(1.3603631\times10^{-4}\)였다.
최소 거리 slack0인 경우는 허용된 등호 case이며, 불필요한 strict inequality를 강요하지 않았다.
모든 link upper는 실제 motion/service oracle의 완료시각을 포함했다.
실험의 최대 실제 0-service 대기는6s다.
R7 process212023은 exit0, tool 관측 runtime5.61s, 내부 wall5.4669937s였다.
인위적인 sleep이나 실행시간 부풀리기는 없었다.

표적 검사에서 context 변경, 미래 전달, phase 지연, finite expiry, positive marginal의 zero overlap, rank scope, 단위 재척도, float threshold margin, numeric underflow를 확인했다.
실제로는16s 전에 도달하는 이력이지만 conservative bound가16s horizon에서 충분하지 않아 HORIZON_UNCERTIFIED를 반환하는 사례도 포함했다.
이는 failed certificate와 physical impossibility를 구별한다.
Rust native는 이 이론 oracle에서 호출하지 않았다.

Float 계산은 analytic real-arithmetic bound의 근사 평가다.
기본 engineering guard는 \(10^{-10}\)m에 실제 중간항 scale의 \(10^{-12}\)를 더하며, threshold와 충분히 분리된 경우에만 upper를 반환한다.
이 guard가 모든 IEEE 연산의 엄밀한 오차 상한이라는 주장은 하지 않는다.
Phase/grid와 서비스 창 수만 exact binary-float Fraction으로 계산하고 결과 시간을 위쪽으로 반올림한다.
이 부분이 exact하다고 transcendental 거리 계산까지 directed-rounding certificate가 되는 것은 아니다.

API 사용 예:

    from metroflow.v1.stop_go_window_certificate import (
        ExAnteBasis, ClippedMotionLaw, ForcingWindow, JointServiceWindow,
        QueueRankBound, evaluate_link_bound,
    )
    basis = ExAnteBasis("declared-stop-go", "controls fixed before decision", 0, 0, 100)
    result = evaluate_link_bound(
        context=basis.context, decision_s=0, entry_s=0, length_m=20,
        law=ClippedMotionLaw(2, 4, 1, 1),
        forcing=ForcingWindow(basis, 8, 16),
        service=JointServiceWindow.from_marginals(
            basis=basis, window_s=10, capacity_veh_s=2,
            green_integral_lower_veh=14, receiving_integral_lower_veh=14),
        rank=QueueRankBound(basis, 5),
    )
    assert result.exit_upper_s == 34

재현:

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python3 -m pytest -q tests/research/test_v03_stop_go_window_20261123.py
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python3 tools/research/v03_stop_go_window_experiment_20261123.py --min-tier 1 --max-tier 2 --out artifacts/v03_constructive_remodel_20261123/R5_theory_experiment.json
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python3 tools/research/v03_stop_go_window_experiment_20261123.py --min-tier 3 --max-tier 4 --out artifacts/v03_constructive_remodel_20261123/R7_theory_experiment.json

## 7. 문헌 이식과 남은 의무

[Le Boudec–Thiran, Network Calculus](https://leboudec.github.io/netcal/latex/netCalBook.pdf)의 Definition1.3.2와 Proposition1.3.6은 backlogged interval의 variable capacity를 strict service curve로 옮기는 근거다.
여기서 누적 bit count를 같은 FIFO movement의 누적 veh mass로, virtual delay를 해당 rank의 ready→outlet delay로 이식했다.
Theorems1.4.2/1.4.6은 delay와 단계 합성의 배경이다.
원전의 hypotheses를 만족하는 동일 흐름이라는 조건을 유지한다.

[Farhi–Haj-Salem–Lebacque, Upper bounds for the travel time on traffic systems](https://arxiv.org/pdf/1408.3447)의 Definitions4–5와 Theorems1–4는 forward demand와 backward supply를 함께 다루는 road-service 구조를 제공한다.
그 전체 CTM이나 service matrix를 현재 native finite-response 모델과 동일시하지 않는다.
이번 scalar bound에는 같은 movement의 explicit receiving guarantee가 추가로 필요하다.
Exa/Parallel로 원문을 읽고 SciSpace로 학술 색인을 확인했다.
Wolfram context와 evaluator는 MCP -32603으로 실패했으며 CAS 성공으로 기록하지 않는다.

미래 J/J_s/W의 사전 근거가 없으면 일반 native 혼잡의 ETA를 이 식으로 보증할 수 없다.
다음 최소 물리 작업은 같은 population/context에서 target/gap/cap/receiving/rank 정보를 실제 boundary instrumentation과 연결하는 것이다.
현재 결과는 그 연결이 충족해야 할 명시적이고 constructive한 충분조건을 제공한다.

## 8. Origin drift watchdog

원 동기 3d83db01의 self propulsion, 정지·재출발, mesoscopic mass와 설명 가능한 routing cost를 직접 진전시킨다.
현재 continuous velocity, FIFO cohort, 정보 인과성, 원수요/dt/예산을 바꾸지 않았다.
관측 모집단은 동일 characteristic과 node의 tagged rank이며 birth age 또는 조건부 route 평균과 섞지 않았다.
실제 증거는 새 clipping/window lemma, stop–go positive case, 반례를 보완한 joint-service 조건, 실행된 oracle다.
판정은 **ALIGNED_WITH_OPEN_OBLIGATION**이다.
합성 연구 fixture의 시간·크기 증가를 원100k도시 V03 하루 실행으로 세지 않으며 full-day credit은0이다.
