# R2 이론 포트폴리오와 실제 유도 checkpoint

기준: 이전 루프 final `90bfca2c2ddf081cbdf40d11b95ff820837d03b5`; 이번 R1 `b5f61d6`.
소유 범위는 이 파일과 `R2_theory_portfolio.py/.json`뿐이다. Production/native, PLAN, 기존 이론, runner는 변경하지 않았다.
현 단계는 부모의 R3/R4 경로 선택 전 포트폴리오다.

## 먼저 판별한 물리 계약

`docs/v1/t02/CLOSURE_KO.md`는 실제 연속 속도와 latent 확률을 구별하며, held target에서 clipped finite-response characteristic을 사용한다.
`docs/v1/t04/TRANSPORT_KO.md`의 motion endpoint ETA는 node-service 대기를 제외한다. 신호/폐쇄는 경계 서비스를 막고 cap 변화에는 유한 가감속으로 반응한다.
따라서 실제 native 속도를 임의로 `w=g*v`로 교체하면 속도 연속성과 운동/대기 시계가 혼동된다. 이번 후보는 **연속 운동 → FIFO 경계 대기/서비스**의 서로 다른 단계를 유지한다.

기존 `V03_FINITE_RESPONSE_PROBE_UPGRADE_20261123.md`의 a>0 response-memory 명제는 재사용 근거이며 새 결과로 세지 않는다.
2026-11-22 `V03_DYNAMIC_FIFO_AGE_R1_R10_C1_C10_20261122_KO.md`는 이미 누적 서비스의 일반화 역함수와 고정 cohort의 route delay를 유도했다. 역함수 자체도 새 결과가 아니다.

## 세 후보와 판별

| 후보 | 중심 수학 | 실제 해소할 공백 | 가장 싼 판별 / 이번 결과 | 남는 전제 |
|---|---|---|---|---|
| A: clipped 운동의 유한창 추진량 | pointwise differential comparison + 양의 response kernel의 유계 forcing 재배열 | 순간 최소속도 a>0 없이 zero target와 finite acceleration을 허용하며 유한 motion 도달상한 구성 | 아래 Lemma A를 직접 증명; exact Fraction 4,356점 비교; 기존 정확 characteristic으로 640창 검사; unclipped tail-pulse 4개 등호검사 | 미래 유한창 추진량은 사전에 보증돼야 함; 같은 characteristic 도중의 bulk mixing jump 제외 |
| B: motion–FIFO node 분해와 공동 서비스 | strict cumulative service, joint min(Cg,R), ordered mass rank | 실제 red 동안 0 service 및 downstream obstruction을 운동 식과 혼동하지 않고 유한 outlet 시간 보증 | 반대 위상은 0veh, 같은 위상은 10veh; 각각 green/supply 적분 10veh로 같음. 7s/7s joint 조건은 정확히 8veh 보증; A와 결합한 34s upper 아래 실제 23.6395s 완료 | 같은 movement에 배정된 receiving/saturation guarantee, work-conserving FIFO, 미래 joint 서비스와 queue-rank mass upper가 필요 |
| C: 두 완료 운동 적분의 parameter identification | 유한차원 선형 관측행렬의 rank | 통과 적분 하나의 forcing/initial-speed 혼동을 제거하고 직접 관측을 이용 | 한 적분에 (v0,V)=(.5,2)와 (.6353735,1.5)가 공존; 두 적분은 determinant .4974401s²로 (.5,2) 복원 | known tau, constant unknown forcing on declared horizon, unclipped/no queue mixing; arbitrary future 변화는 식별 불가 |

**권고:** A를 새 배경 운동 정리로 선택하고 B의 이미 알려진 FIFO/service 구조에 정확히 접합한다.
B만으로 시작하면 지난 cumulative-inverse 이론을 반복할 위험이 있다. C는 계측과 forcing stationarity 의무가 더 크므로 이번 주경로에서는 보류한다.
어느 후보의 실패도 일반적인 no-go로 승격하지 않는다.

## 정의와 전제 — 후보 A

한 homogeneous characteristic을 시간 t0에서 시작한다. 시간은 s, 길이는 m, 속도 V,v는 m/s, 가감속 한계 A,B는 m/s²다.
반응시간 tau>0, 속도 cap b>0, A>0, B>=0는 고정이며

    v'(t) = clip((V(t)-v(t))/tau, -B, A),  x'(t)=v(t)
    0 <= V(t) <= b,  0 <= v(t0)=v0 <= b

를 가정한다. V는 유계 가측 함수이고 solution은 absolutely continuous이다.
이 범위는 invariant다: v=0에서 derivative>=0, v=b에서 derivative<=0.
혼합에 의한 속도 projection, tau/composition 변경, 길이/field 변경은 이 characteristic의 밖이다. 그것까지 자동 보증하지 않는다.

길이 H>0의 각 **선언된 미래 창** I_k=[t0+kH,t0+(k+1)H]에서

    integral_(I_k) V(s) ds >= J,   0 < J <= b H

를 요구한다. J의 차원은 m이며 실제 이동거리가 아니라 target-speed의 시간적분이다.
n개의 창을 쓰는 주장에는 t0+nH까지의 동일 가정과 유효 horizon이 필요하다.
모든 entry t에 쓰려면 t에 정렬한 각 창에서도 조건이 성립하는 sliding-window guarantee가 있어야 한다.
고정 grid 창만 보증될 경우 임의 entry에서 다음 grid까지 최대 H를 별도로 기다리고 v0>=0로 새 bound를 시작한다. 정렬 차이를 숨기지 않는다.

## Lemma A1 — clipping에 견디는 양의 비교계 (derived)

eta=min(1,A*tau/b)라 두면 거의 모든 t에서

    v'(t) >= (eta V(t)-v(t))/tau.

증명: d=(V-v)/tau라 한다.
d<=0이면 clip(d,-B,A)>=d>=(eta V-v)/tau이다.
d>=0이면 eta<=1이고 d<=(b/tau)이므로 eta*d<=A, 따라서
min(A,d)>=eta*d=(eta V-eta v)/tau>=(eta V-v)/tau.
B는 clipping으로 제동을 약하게만 만들기 때문에 추가 하한이 필요 없다.
등호 비교계 z'=(eta V-z)/tau, z(t0)=v0를 잡으면
d/dt[exp((t-t0)/tau)(v-z)]>=0이고 v>=z이다. 따라서

    x(t0+h)-x(t0) >= tau*v0*(1-exp(-h/tau))
        + eta*integral_0^h [1-exp(-(h-r)/tau)] V(t0+r) dr.        (A1)

clipping이 비활성이고 eta=1이면 (A1)은 정확한 Duhamel 적분이다.
eta<1에서 sharpness는 주장하지 않는다.

## Lemma A2 — 유한창 최악 배치와 도달상한 (derived)

n>=1 정수와 h=nH에 대해 (A1)의 kernel K(r)=1-exp(-(nH-r)/tau)는 r에 대해 감소한다.
각 창에서 0<=V<=b와 integral V>=J만 알 때 적분 최소값은 창 마지막 J/b초를 b로 채우는 target가 준다.

비자명한 재배열 단계: 한 창 끝점을 e, c=e-J/b라 하고 V*=b*1_[c,e]라 둔다.
창에서 F=V-V*는 r<c에서 nonnegative, r>c에서 nonpositive이고 integral F>=0이다.
그러므로

    integral K F = integral (K-K(c))*F + K(c)*integral F >=0.

각 항의 부호가 정해지고 K(c)>=0이므로 상기 최소화가 증명된다. 미래 샘플로 적분량을 맞춘 결론이 아니다.

각 창 k의 tail pulse를 적분하면

    J - b*tau*(1-exp(-J/(b*tau))) * exp(-(n-k-1)H/tau)

이다. 기하급수 합을 취하면

    L_n(v0) = tau*v0*(1-exp(-nH/tau))
        + eta*[ nJ - b*tau*(1-exp(-J/(b*tau)))
                       *(1-exp(-nH/tau))/(1-exp(-H/tau)) ]       (A2)

가 x(t0+nH)-x(t0)의 하한이다.
L_n>=ell이면 nondecreasing continuous x의 최초도달 E_ell은 t0+nH 이하이다.
N=min{n>=1:L_n>=ell}를 찾으면 유한 upper를 얻는다.
실제로 L_n >= eta*nJ - eta*b*tau*(1-exp(-J/(b*tau)))/(1-exp(-H/tau))이므로
J>0, eta>0이고 조건이 그때까지 유효하면 유한한 N이 존재한다.
구체적으로 K=b*tau*(1-exp(-J/(b*tau)))/(1-exp(-H/tau))라 두면

    N_sufficient = ceil((ell/eta+K)/J)

는 v0>=0인 모든 경우에 L_N>=ell를 보장하는 계산 가능한 정수 상한이다.
이는 최솟값 N의 upper이며, 실제로는 더 작은 N을 (A2)로 확인할 수 있다.
유한 horizon이 N_sufficient*H보다 짧으면 허용된 창만 검사하고 억지로 horizon을 연장하지 않는다.
**유한하게 주어진 horizon 안에서 N을 찾지 못한 경우는 HORIZON_UNCERTIFIED이며 물리적 unreachable의 증명이 아니다.**

eta=1이고 가속과 제동 clipping이 모두 비활성인 class에서 tail-pulse가 실제 등호를 준다.
예를 들어 A>=b/tau와 B>=b/tau이면 모든 v,V in [0,b]에서 clipping이 비활성이다.
eta=1만으로 B의 조건이 따라오지는 않는다. B가 작아 pulse-off의 제동 clipping이 활성화되면 더 멀리 이동하므로 equality를 주장하지 않는다.
period H의 tail pulse는 sliding-window 적분도 J이므로 본 unclipped 등호 사례는 정렬 위반에 기대지 않는다.
eta<1의 clipped lower는 구성적인 conservative comparison이다.

### 극한과 차원

- tau->0, clipping 비활성 범위에서 각 창 forcing 적분이 실제 거리로 접근한다.
- A->infinity이면 eta->1이지만 제동 clipping은 남을 수 있다. A,B>=b/tau를 함께 만족하면 unclipped 정확 kernel 하한으로 돌아간다.
- J->0이면 선형 증가항이 사라져 단순 coast와 구별되지 않는다.
- V=0 forever이면 v가 감쇠하여 총 coast가 유한할 수 있으므로 J>0 의무를 생략할 수 없다.
- L_n의 모든 항은 m, nH는 s, eta는 무차원이다.
- 위 식은 tau와 A의 동시 극한에 관계없이 eta를 고정한다고 가정하지 않는다.

## 후보 B — 공동 서비스와 완전한 link clock의 조건부 구성

motion endpoint 이후의 ordered ready queue를 별도로 둔다.
같은 movement에 예약/배정된 포화율 C>0 [veh/s], green fraction 0<=g<=1, receiving bound 0<=R<=C [veh/s]로
사용 가능한 service c(t)=min(C*g(t),R(t)) [veh/s]를 정의한다.
경합 node의 nominal 총 capacity를 특정 movement의 c로 그대로 쓰면 안 된다.

FIFO queue가 비어 있지 않은 동안 실제 cumulative departure increment는 integral c이다.
빈 동안 미사용 service는 차량/질량으로 저장되지 않는다.
query는 임의 정수 vehicle ID가 아니라 같은 source stream의 tagged mass rank이며,
motion-ready 시각에 해당 rank까지의 ahead+tagged mass가 W [veh] 이하라는 사전 bound를 쓴다.
뒤에 들어오는 질량은 FIFO에서 이 rank보다 먼저 처리되지 않는다.

### Lemma B1 — joint availability의 constructive lower (derived elementary transfer)

모든 관련 길이 H_s 창에서 integral Cg>=J_g, integral R>=J_r라면

    integral min(Cg,R) >= max(0,J_g+J_r-C*H_s)=J_s.

증명은 0<=a,b<=C에서 min(a,b)>=a+b-C를 적분하고 c>=0을 사용하면 된다.
J_s>0이면 separate average 자료로도 **충분히 큰 겹침을 강제하는 경우에만** 유한 서비스가 보증된다.
J_g+J_r<=C H_s이면 이 자료만으로 positive guarantee를 선언하지 않는다.
이미 직접 joint service lower를 아는 경우에는 그것을 사용해 이 보수적 overlap bound를 개선한다.

### Lemma B2 — 분리한 두 시계의 합성 (classical FIFO step reused + new A input)

motion-ready 시각 u부터 모든 길이 H_s 창에 integral c>=J_s>0이고 rank mass가 W 이하이면
그 rank가 아직 미완료인 동안 queue가 backlogged이므로, m=ceil(W/J_s) 창이 끝날 때까지 최소 mJ_s의 service를 받는다.
따라서 last tagged rank의 outlet은 u+mH_s 이하이다.
A의 motion bound u<=t0+NH와 결합하면

    E_link(t0,W) <= t0 + N H + ceil(W/J_s) H_s.                  (B1)

이 composition은 운동 거리를 서비스 질량과 동일시하지 않는다.
매 단계의 mass/FIFO와 양의 단위를 유지한다.
임의 entry/unknown u에 적용하려면 service guarantee는 모든 해당 시작시각의 창에서 성립해야 한다.
고정 periodic service는 예제에서 이 조건을 만족한다.
고정 grid service guarantee만 있다면 최대 H_s의 정렬 지연을 따로 추가해야 한다.

이 결과는 finite queue rank bound를 쓰므로 전체 미래 arrival curve를 가정할 필요가 없다.
하지만 upstream 재경로화로 W가 늘거나 downstream obstruction으로 J_s가 사라지면 certificate의 전제가 무너진다.
따라서 이를 native endogenous network의 전역 spillback 해소로 확대하지 않는다.

### 실제 반례와 양성 판별

C=2veh/s, H_s=10s. 5s green과 5s receiving 각각의 적분은 10veh다.
green이 [0,5], receiving이 [5,10]이면 joint service는 정확히 0veh다.
둘이 [5,10]에 겹치면 같은 두 평균으로 joint service는 10veh다.
이는 “신호 평균과 supply 평균이 양수면 통과 보증”이라는 잘못된 추론을 판별한다.

green=[0,7], receiving=[3,10]의 10s 주기에서는 각각 14veh이고 겹침 [3,7]에 8veh가 있다.
J_s=14+14-20=8veh는 등호로 달성된다. 신호와 downstream receiving을 함께 제한하면 실제 constructive guarantee가 생긴다.

## 후보 C — 식별 경로의 첫 유도와 판별

unclipped homogeneous 모델 V=theta 일정, tau known에서
v(s)=theta+(v0-theta)exp(-s/tau)이다.
완료 motion passage [a_i,b_i]의 정확한 거리 D_i는

    D_i = E_i*v0+(G_i-E_i)*theta,
    G_i=b_i-a_i, E_i=tau*(exp(-a_i/tau)-exp(-b_i/tau)).

두 행의 determinant는 E1*G2-E2*G1이다.
G1,G2>0, b1<=a2이고 서로 양의 길이인 비겹침 창이면 감소함수 exp(-s/tau)의 평균은 첫 창에서 더 크므로
E1/G1>E2/G2이고 determinant>0이다. 두 적분이 v0,theta를 유일하게 식별한다.
단일 적분은 1차원 해집합을 남긴다. 두 창의 separation이 작거나 tau가 매우 크면 조건수가 나빠질 수 있다.
이 관측은 완료/전달 뒤에만 사용하며, 미래 theta 일정성은 데이터가 증명해 주는 사실이 아니라 별도 모델 전제다.
clipping, queue delay, mixing이나 변화하는 미래 forcing은 이 rank argument의 대상이 아니다.

실제 tau=2s, [0,1],[2,3], (v0,theta)=(.5,2)m/s:
거리 (.8195919791,1.5657521569)m, determinant .4974401185s².
복원 (.5000000000000001,2.0)m/s.
첫 적분만으로는 (.6353735206,1.5)m/s도 일치하지만 두 번째는 구별한다.
단순 observation-matrix 재증명은 이번 주결과로 세지 않는다.

## 원전 → MetroFlow 이식 사전

| 원전 명제/정의 | 원전 객체 | 이식 객체와 단위 | 보존/추가 전제 |
|---|---|---|---|
| Le Boudec–Thiran Def1.3.2, Prop1.3.6 | variable capacity M와 strict service beta | M(t)=integral c [veh], beta(h)=J_s floor(h/H_s) [veh] | backlogged 동안 실제 service; nonnegative rate; 시작 phase 조건 |
| 같은 책 Thm1.4.2 | FIFO virtual delay, horizontal deviation | source mass rank의 ready→outlet delay [s] | cumulative rank를 동일 모집단에 맞춤; queue mean/birth age로 대체하지 않음 |
| 같은 책 Thm1.4.6 | tandem service convolution | motion 최대지연 단계와 ready FIFO service의 분리 | 실제로 동일 흐름이 두 단계를 지나야 함; endogenous 서로 영향은 별도 증명 |
| Farhi–Haj-Salem–Lebacque Def4–5, Thm1–4 | forward demand/backward supply의 2입출력 traffic service matrix | movement receiving guarantee R와 green g를 함께 유지 | scalar green만으로 전체 downstream 공급을 없애지 않음 |
| 기존 T02/foundation characteristic | clipped continuous speed | Lemma A의 v,V,tau,A,B,b | 같은 homogeneous characteristic; composition/mixing jump 제외 |

정확한 원전 URL:
- https://leboudec.github.io/netcal/latex/netCalBook.pdf — 저자 배포본. Def1.3.2, Prop1.3.6, Thm1.4.2, Thm1.4.6을 직접 읽었다.
- https://leboudec.github.io/netcal/ — 저자 book landing page.
- https://arxiv.org/pdf/1408.3447 — Farhi, Haj-Salem, Lebacque, *Upper bounds for the travel time on traffic systems*; Definitions4–5, Theorems1–4, Section3 controlled road section을 직접 읽었다.

Exa는 저자 textbook을, Parallel은 해당 PDF의 수식과 traffic supply/signal 연결을 검색·추출했다.
SciSpace는 두 Farhi 논문의 학술 색인을 교차 확인했다. 원전의 network-calculus 이론을 이번 신규 발견이라고 주장하지 않는다.
Wolfram context와 symbolic integral evaluator는 모두 MCP -32603 Internal error였다. CAS 검증 성공으로 기재하지 않았다.
위 증명은 직접 유도이며 numerical/source oracle은 별개다. 전 세계 최초성은 미심사다.

## 실제 lightweight 실행

실행 명령:

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. timeout 45s python3 artifacts/v03_constructive_remodel_20261123/R2_theory_portfolio.py

Remote process 179782는 실제 정상 종료했다. Script wall=0.06176576s.
`foundation_kinetics.characteristic`의 정확한 held-target clipped 해를 재사용했다.
source SHA256=59b39954feb7fc79cc56ba25d6f9c46a46a6e63d659aee8733552cca040f6e69.
양의 lower를 얻기 위해 임의 speed floor, 질량 삭제, dt 변경을 하지 않았다.

| 실제 계산 horizon | 실제 거리 [m] | 새 lower [m] | unclipped 등호 오차 [m] |
|---|---:|---:|---:|
| 8s | 7.471517765 | 4.541341133 | 0 |
| 16s | 22.828755462 | 12.477993586 | 0 |
| 32s | 54.775487341 | 28.476812085 | 0 |
| 64s | 118.775165326 | 60.476811688 | 1.42e-14 |

고정 예제는 H=8s, J=16m, b=4m/s, tau=2s, A=B=1m/s², v0=0, eta=.5다.
각 8s 주기의 앞4s V=0, 뒤4s V=4이며 실제 clipping이 활성화된다.
ell=20m에 L_3=20.476833335m이므로 motion upper=24s; 실제 최초도달=15.139484898s.
5veh cohort가 이 endpoint에 함께 ready가 되고 위의 10s joint service를 받으면
last rank의 실제 outlet=23.639484898s, 그중 실제 zero-service 대기=6s다.
사전 bound는 24+ceil(5/8)*10=34s다.
이는 실제 정지 서비스를 포함하며 무조건 양의 순간속도 가정이 필요 없다.
control schedule은 decision=0에서 선언돼 있고, 미래 oracle 값은 검증에만 사용했다.

exact Fraction 4,356점의 differential comparison은 모두 만족했고 최소 slack=0이다.
80개 생성 forcing history의 8개 horizon, 총 640개 Python source/reference characteristic 비교가 lower를 포함했다. Rust native는 이 이론 oracle에서 호출하지 않았다.
최소 거리 slack=5.618273216m이었다.
이 유한 숫자 검사는 일반 정리의 증명이나 directed-rounding 인증의 대체물이 아니다.
Python float 출력은 수치 근사이고 해석적 real-arithmetic bound와 구별한다.
실제 source 모델과 일치하는 작은 연구 fixture이며 원100k V03 full-day credit은0이다.

## Origin drift watchdog와 다음 한 단계

원 동기(3d83db01의 active-meso)는 목적지 지향 자기구동/정지·재출발, mesoscopic mass, collision-informed legal routing을 연결한다.
이번 결과는 실제 운동/경계서비스의 시간적 조건으로 예측가능한 통과 상한을 구성하므로 그 질문을 진전시킨다.
현재 continuous speed, FIFO cohort, 차량량·people/cargo 장부, causal information, 원수요/규모/dt/예산은 변경하지 않았다.
관측 모집단은 동일 homogeneous motion characteristic 및 동일 movement의 FIFO mass rank이며 기존 route-conditional mean/birth age와 구별했다.

판정: ALIGNED_WITH_OPEN_OBLIGATION.
실제 진전은 새 clipped finite-window lemma, joint-service 반례를 보완하는 positive construction, 실행된 정확 characteristic 비교다.
남는 최소 의무는 미래 J와 J_s 및 W를 native context에서 어떤 source/계측으로 사전에 보증하는가이다.
부모가 A+B를 선택하면 다음 단계는 horizon/phase/context를 명시적으로 검사하는 별도 연구 observer를 구현하고,
manufactured stop–go/zero service/invalid future-bound 사례를 검증하는 것이다.
현재 native 전체 혼잡에서 조건이 성립했다고 선언하거나 production routing을 활성화하지 않는다.

## 사용한 skill context

physmath-research-loop 1.3.0의 main, THEORY_LOOP.md, POLICY_INTEGRATION.md, STAGE_GUIDE_KO.md;
Mathbox research-program 및 program-protocol; Exa Search, Parallel web-search.
R2 원전 실제 읽기, R3 근거상태 분리, R4 서로 다른 3경로와 cheap discriminator, R5 실제 lemma까지 실행했다.
추가 reviewer/child agent는 만들지 않았다. 부모의 단일 bounded 독립 검토 이후 필요한 수정만 수행한다.
