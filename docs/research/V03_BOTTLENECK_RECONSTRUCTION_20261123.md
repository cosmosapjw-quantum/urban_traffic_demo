# MetroFlow V03 연속 병목의 이론 재구축 — 2026-11-23

## 범위와 기준

이번 요청은 누적 blocker 데이터를 바탕으로 발산적으로 수행하는 이론 R1–R10이다.
생산 코드 변경, native 빌드, 추가 도시 실행은 이 연구 단위의 산출물이 아니다.
경량 기호·유리수 계산은 명제의 판별 근거로 사용한다. 이전의 단계별 commit/push
지시는 유지한다. 기준은 `492e27618696df2514b088a64de450cf69746647`이며,
현재 실행 권위는 `docs/v1/PLAN.json` 1.1.28이다. 원래 DAG19/21,최종수용5/21,
V03BLOCKED,24h0/9를 연구 단계 수와 구별한다.

## R1 — 계산 가능한 연구 질문과 원래 목적

**질문.** 동일한 물리적 수송을 표현하는 과정에서 생기는 source-head×service와
active-source×interval-cut 전개를, 실제 제어 변화·조성 기저·필요한 관측량에
따라 계산하도록 바꿀 수 있는가? 정확한 표현과 제어된 모델 변형의 여러 경로를
실제로 유도하고, 어느 연산까지 닫히며 다음 병목을 어디에 남기는지 판별한다.
25,710초의 현재 guard 하나를 통과시키는 byte credit은 연구 목표가 아니다.

**원래 동기와 이번 턴의 drift watchdog.** `0492364:docs/PRD.md`
(blob `f8cc371410ca0e24b0947cda3d6772787efddc7a`)는 약100,000명 규모에서
도시 생성–교통–접근성–도시발전–행동/학습의 설명 가능한 결합, bulk mesoscopic
수송, bridge/IC 병목, 우회로의 초기 완화와 후속 유발수요를 명시한다.
`6524500:memory/constitution.md`(blob `7c78e214c9558bcb1023854e55025f1c554aadee`)도
같은 결합 목표를 고정한다. 현재 heap row나 과거 IEEE 곱셈열은 역사적 구현
선택이며, 그 자체가 이 물리적 목표의 정의는 아니다. 정확한 기준 경로는 보존한다.

**보존할 물리 계약.** 차량량[veh],사람[person],화물[kg],birth first moment[veh·s],
시간[s],거리[m],속도[m/s]를 구별한다. 유한응답,명시적 eligibility,FIFO,
class/purpose/information,유향 합법 경로,보존 장부,불변 상태와 재시작을 보존한다.
모델 변형은 가정과 관측 오차를 함께 명시하고 기존24h 수용을 자동 대체하지 않는다.

**근거 상태.** 이전 native는 현재 source에서0→25700s를 실행하고 이전 전체
3,405,043,386B checkpoint와 byte 동일성을 검증했다. 25710s는 indexed sweep
preflight에서5,051,633,256B>5,025,214,575B로 거절됐다. Transfer258,538검사는
통과했고 event payload275,578,880B를 실제 절감했으나 추가 완료 tick은0이다.
이를 모델 오류나 모든 정확한 표현의 불가능성으로 일반화하지 않는다.

**이론적 완료 기준.** (i) 실제 producer–consumer 연산과 비용의 대응,
(ii) 실패 메커니즘이 다른 복수 후보의 정의·명제·직접 유도,
(iii) 가정이 빠졌을 때의 명시적 반례와 복원 조건,
(iv) 판별 가능한 경량 계산,
(v) 정확/조건부/근사/미해결을 구분한 열려 있는 후보군과 계산 계약을 남긴다.
새 구현이나 실제25710 통과는 이번 이론 단계 완료 기준에 넣지 않는다.

R2 근거·재사용, R3 주장·전제, R4 후보 구성, R5 유도, R6 독립 검증,
R7 판별 계산, R8 후보별 판정, R9 수학적·계산 계약, R10 보존·재개를 수행한다.
탐색 범위를 유지하며 단일 production 경로를 강제로 선정하지 않는다.


## R2 — 누적 증거, 소비 경로, 문헌의 재사용 범위

**고정 근거.** artifacts/v03_bottleneck_theory_20261123/R2_source_anatomy.json은
기준 HEAD, 원래 receipt 경로·Git blob·SHA256, 원본 숫자와 재계산을 보존한다.
기준 native source set SHA256은
bea107c2888885966c901a0f30a6d7edcb50a24e5cbbbe31d3f8bf020536943d,
binary SHA256은 22a7cebc751b575521a8360ab7e235aa7fa6fa9e4d54c8ac8904b35e708ae57a다.
이번에는 해당 binary를 재실행하지 않았다.

| 실제 관측 | 값 | 정확한 의미 |
|---|---:|---|
| 마지막 유효 물리 시간 | 25,700 s | 이전 S08 실행; 25,710은 실패 |
| 현재 cell part / packet | 34,610,422 / 631,350 | S07 입력 상태; 활성 차량 수가 아님 |
| road 차량량 | 778.5767388933845 veh | released 922.1750575039921 − completed 143.59831861060766; pending=0 |
| journey active 차량량 | 1,234.1174136872 veh | 다른 journey 단계 포함; road 분모와 구별 |
| 한 실패 tick의 service / event row | 258,022 / 17,429,035 | service마다 source 조성을 반복 전개 |
| incoming row / exact time run | 17,143,679 / 206,999 | event time sharing만으로 조성 반복은 남음 |
| 첫 destination raw → combined | 468,093 → 458,667 | 감소 2.0137%; sweep 결과를 아직 만들지 못함 |
| 그 destination 유한 interval pair | 2,610 | 서로 다른 (a,b); endpoint 수 아님 |
| raw point row | 135,915 | combine 이후 point row 수 아님 |
| 세 captured head의 고유 tag | 464, 454, 442 | 질량 각각 0.216279, 0.215711, 0.110862 veh; 각 time pair 1개 |

road 차량량 1 veh당 저장 part는 약44,453행이다. 이 비율은 현재 관측 상태의
표현 팽창을 드러내며, 미래 복잡도 하한이나 전체 unique tag 수를 뜻하지 않는다.
전체 live unique tag 수와 각 destination의 endpoint 수는 미측정이다.

**생산–소비의 연결.** v1_road.rs의 현재 구현을 읽어 다음 사슬을 확인했다.

1. motion은 전체 cell의 class 질량·길이·latent에서 유한응답 계수를 만든다.
2. 교차로는 현재 FIFO head의 destination 질량비와 점유길이비로 rate를 계산한다.
3. service마다 head의 모든 tag 행을 비례 분할하고 event와 incoming을 만든다.
4. destination은 동일 tag/offset/time key를 합치고 interval 경계를 sweep한다.
   각 slab의 active 조성을 다시 펼쳐 retained packet을 만든다.
5. incoming speed·class latent는 source 시각별 mark의 질량가중합을 사용한다.
   이후 같은 key를 합쳐도 앞선 mark 소비가 이미 끝나야 한다.
6. 새 tick의 sink는 journey completion/egress/다음 leg와 service 상태를 바꾼다.
   이전 tick의 last_events 전체 행은 외부 조회·checkpoint·검증·예산계상에 쓰인다.
   실제 다음 leg를 정하는 ReceiptHistory는 별개이며 제거할 수 없다.

따라서 반복 비용은 단순히 event Vec 하나가 아니라
\[
 W_{\rm head}=\sum_{\text{service }s}|{\rm head}(s)|,\qquad
 W_{\rm overlay}=\sum_{\text{slab }I}\sum_{\text{active source }r}|{\rm supp}\,\mu_r|
\]
의 두 전개와 이를 따라 생기는 mark/retained state/checkpoint의 재물질화다.
이는 현재 eager 연산의 비용 모형이지 모든 표현에 대한 불가능성 명제가 아니다.

**guard 이름의 재해석.** S07 실패의 실제 구조식은
\[
2{,}602{,}210{,}912+1{,}485{,}159{,}656+
950{,}538{,}768+13{,}723{,}920=5{,}051{,}633{,}256\ {\rm B}.
\]
순서대로 base, event, incoming, indexed scratch다. 허용량은5,025,214,575B.
index scratch를 전부 없애도5,037,909,336B로12,694,761B가 초과한다.
따라서 인덱스만 줄이는 변경은 이 구조식 아래 충분하지 않다. 이것은 guard
회계의 대수적 사실이며 RSS의 엄밀한 하한으로 해석하지 않는다.

**이미 얻은 성과의 경계.** 이전 time carrier는 해당 실패 tick에서
275,578,880B payload를 실제 절약했다. 하지만 17.4M 논리 행·17.1M incoming,
이전 last_events와 retained packet까지 제거하지 않았다. 앞선 fixed-head rank
실험은 반복 비례 분할을 줄였지만 실제 destination overlay, changing capacity,
source marks, journey feedback의 폐쇄성을 아직 증명하지 않았다.
11월17일의 작은 인접 병합률은 그 병합 연산의 효과에 대한 증거다.
공유 조성 연산자·행동 quotient·제어된 측도 모델의 효과를 부정하지 않는다.

**원전과 재사용 계약.**

- [Le Boudec–Thiran, Network Calculus](https://leboudec.github.io/netcal/latex/netCalBook.pdf),
  variable-capacity node의 input-output characterization: causal lossless
  work-conserving 출력은 \(D(t)=\inf_{s\le t}\{E(s)+C(t)-C(s)\}\)다.
  이는 eligibility 이후의 서버 관계다. 도로의 유한응답/유한공간/다상품 비율을
  자동으로 증명하지 않는다. 여기서는 이 관계의 **arrival와 capacity가 함께
  변하는 안정성**을 새로 유도한다.
- [Wright et al., 2017, TRB105:212–234](https://doi.org/10.1016/j.trb.2017.09.001):
  multi-commodity node의 비음수·수요·공급·비례성·priority와 lane interaction에
  따른 partial FIFO를 정식화한다. §3의 partial FIFO는 명시적 모델 변형이다.
  실제 shared lane의 엄격 FIFO를 계산 편의로 풀어 주는 근거로 사용하지 않는다.
- [Sering–Vargas Koch–Ziemke, arXiv:2105.13202v2](https://arxiv.org/html/2105.13202v2):
  양의 고정 arc transit time/capacity와 deterministic queue를 가진 packet
  routing의 fluid limit을 다룬다. 이 결과를 density-dependent finite-response,
  spillback, latent dynamics, 도시개발의 결합모델로 직접 옮기지 않는다.
- 이전 causal FIFO 문서의 fixed-service nonexpansiveness와 rank-block
  \(\delta/4\) 누적오차는 그 가정에서 재사용한다. 새로운 coupled error 결론에는
  capacity·eligibility·support·control 변화의 추가 경계가 필요하다.

**이번 단계의 산출.** 첫번째 실패 guard를 최적화 문제의 정의로 삼는 해석을
폐기하고, source 조성에서 최종 관측까지 이어지는 재전개 사슬을 모델링했다.
source/counter 의미는 읽기 검증, 수치 합은 재계산 완료다. 새 도시 실행은 NOT_RUN.


## R3 — 재구축 명제와 필요한 전제

연속 병목의 해소를 주장하려면 producer에서 줄인 표현이 다음 consumer에서
다시 전개되지 않아야 한다. 다음 여섯 경로를 독립적으로 구분한다.
이 단계의 명제는 이후 R5의 증명과 R6/R7의 판별에 연결한다.

| 경로 | 변경하는 수학적 대상 | 해결할 반복 | 반드시 남는 의무 |
|---|---|---|---|
| O 관측 trace 분리 | 물리 state와 lossless 과거 event carrier | flat history의 상시 보관·동시 복사 | same-tick sink, ReceiptHistory, decoder/validator, full export 비용 |
| A 조성 연산자·구간 측도 | 양의 조성 root와 projection/pushforward, persistent overlay | head×service 및 source×slab의 행 할당 | 실제 query family, reachable ancestry, virtual knot 수 |
| B 행동 quotient와 provenance fiber | class+complete residual route의 물리 좌표 | 동등한 tag의 물리 제어 중복 | tag별 sink/egress/정책, FIFO 위치, fiber 읽기 비용 |
| C support 보존 rank/phase 모델 | eligibility와 marked cumulative measure | 필요 정확도 이상의 조각 세분 | support 경계·용량 피드백·event 시간의 안정성 |
| D 양의 moment 재구성 | 정해진 행동 stratum의 충분한 관측 feature | 분포 atom 수 | feature의 진화/소비 연산 폐쇄성 또는 정량 residual |
| E flux 적분형 mark | 시간별 source mark를 flux-weighted 적분 | 인위적 구간 분할에 따른 mark 변화·중복 | 제어 phase 경계, 기존 midpoint와 다른 버전 |

O는 lossless carrier로 byte-compatible 가능성을 다루지만 아직 구현되지 않았다.
A/B는 현재 이산 알고리즘의 **실수 산술 counterpart**에 대한 동치다.
C/D/E의 의미 있는 일부는 별도 버전의 모델·수치 규약이다.
이를 하나의 “exact” 표지로 합치지 않는다.

**단위와 상태.** mass \(m\)[veh], birth moment \(B\)[veh·s],
eligible/departure cumulative \(E,D\)[veh], service opportunity \(C=\int cdt\)[veh],
\(c\)[veh/s], speed \(v\)[m/s], distance \(X\)[m], latent \(p\)[1].
도로의 길이 점유 계산과 정지 footprint는 서로 다른 class 계수다.
규모가 다른 변수를 함께 쓰는 피드백 norm에는 \(M_*,T_*,V_*,X_*=V_*T_*\)
등의 명시적 무차원화가 필요하다.

**후속 증명의 조건.**

- O: 과거 trace가 물리 update에 들어가지 않는다고 해서 admission/validation까지
  무관한 것은 아니다. 원본과 재구축 모두 admissible인 transition에서 물리
  동치를 먼저 주장하고, decoder-equivalent validation을 요구한다.
- A/B: 원래 packet order·target·eligibility·point/slab order·head/event knot,
  fraction snapping 규칙을 유지한다. 물리 제어 입력의 contraction이 정확해야
  한다. 실수 재결합이 IEEE 연산열·underflow·signed zero를 보존한다는 주장은 없다.
- C: fixed service를 가정하지 않는다. \(E,C\)의 공동 변화부터 경계를 유도한다.
  zero capacity 자체는 cumulative 안정성을 깨지 않지만, 공급이0인 movement의
  존재와 head support가 바뀌면 작은 질량오차가 큰 service 차이를 만들 수 있다.
- D: 보존 feature 일치만으로 미래 동치가 나오지 않는다. feature 공간의 pullback
  또는 generator 불변성, nonlinear consumer의 충분상태 조건을 별도로 요구한다.
- E: source characteristic과 latent hazard를 고정한 phase 안에서 적분한다.
  실제 제어의 변화까지 임의로 합치지 않는다. 기존 midpoint rule과는 다른 수치
  모델이며 과거 byte identity를 수용 근거로 재사용할 수 없다.

**판별할 반례와 복원 조건.** 다음 반례는 특정 생략의 실패를 보이는 용도로 쓴다.

1. 총량·평균 age가 같아도 eligibility CDF는 다를 수 있다 → target/rank profile 유지.
2. 동일 next destination도 route tail이 다르면 다음 junction에서 갈라진다
   → complete residual behavior 또는 refinement 가능한 partition.
3. 동일 조성의 인접 slab도 midpoint mark가 달라질 수 있다
   → virtual event knots 유지, 또는 E의 적분 규약을 별도 채택.
4. 작은 blocked tail을 whole-head에 섞으면 전량을 막을 수 있다
   → decision support boundary 유지와 node sensitivity 조건.
5. 짧은 시간의 연속의존성은 장기 피드백 안정성이 아니다
   → finite-horizon bound와 별도의 small-gain/delay 조건.

여기서 제시한 제한은 각 명제의 적용영역이다. 연구 목적 전체에 대한 no-go는
주장하지 않는다. 전역 row 수·DAG ancestry·behavior/fiber 크기·24h 자원 성립은
현재 미해결이며, R7의 경량 예제를 실제 도시 검증으로 승격하지 않는다.


## R4 — 여섯 후보의 실제 구성과 구별되는 예

**O: 관측 trace를 손실 없이 분리한다.** 물리 상태를 X, 이전 detailed trace를 O라
두고, 새 sink의 작용을 포함하는 \(X'=F(X,u)\)와 \(O'=G(X,u)\)로 쓴다.
lossless codec \(d(e(O))=O\)를 쓰면 공통 admissible transition에서
\(({\rm id},d)\widehat T=T({\rm id},d)\)다. 예산 통과 여부까지 같다는 뜻은 아니다.
입력 old trace의 실제 flat payload923,664,448B와 같은 trace의 timed payload
464,781,312B 사이에는458,883,136B 차이가 있다. 지속 carrier로 바꾸는 조건부
표적이며, 아직 실측 절감으로 보고하지 않는다. full export와 active history는 남는다.

**A: 조성을 연산자로 남기고 interval overlay까지 닫는다.** label/offset의 양의
질량·birth 측도 \(v=(m,B)\)에 Scale, Sum, destination projection \(P_j\),
route advance R을 정의한다. event e가 비율 \(f_e\)를 구간 \(I_e\)로 내보내면
\[
\mathcal F_j=\sum_{e\to j}RP_j(f_ev_e)\otimes U_{I_e}.
\]
각 endpoint slab는 active source들을 펼친 배열 대신 양의 persistent sum-tree
root를 가리킨다. 삽입/종료는 leaf를 활성/0으로 바꾸는 경로 갱신으로 처리한다.
signed density 차분의 수치 상쇄를 기본 구현으로 가정하지 않는다.

예를 들어 \(U_m=(4,2,0),U_B=(8,10,0)\),
\(V_m=(0,2,2),V_B=(0,12,16)\)를 두고,
U/2를[10,12]와[12,14], V를[11,13]에 보내면:

| slab | mass vector | birth vector |
|---|---|---|
| [10,11] | (1,1/2,0) | (2,5/2,0) |
| [11,12] | (1,3/2,1) | (2,17/2,8) |
| [12,13] | (1,3/2,1) | (2,17/2,8) |
| [13,14] | (1,1/2,0) | (2,5/2,0) |

중간 두 slab는 조성 root를 공유하지만 기존 event knot12는 남긴다.
두번째 slab에서 label1,3은J, label2는K로 가며 공급이(2,1)veh/s이면,
sending4veh/s 아래 전체율은7/3veh/s다. 3/7s 서비스는
mass(2/7,3/7,2/7), birth(4/7,17/7,16/7)를 보낸다.
따라서 “원래 흐름을 결정하는 rate”와 “태그별 수송” 모두 같은 root의 contraction으로 계산된다.

**B: 물리적으로 같은 행동을 quotient하고 출처를 fiber로 보존한다.**
각 기존 FIFO slab 안에서
\(\kappa(\ell,o)=(\mathrm{class}(\ell),p_\ell[o:])\)가 같은 tag를 묶는다.
\(M_g=\sum_{z\in g}m_z\), \(K_g(z)=m_z/M_g\), \(J_g(z)=B_z/M_g\)를 유지하면
\(m_z=M_gK_g(z),B_z=M_gJ_g(z)\)로 복원된다. 균등 service는 M만 스케일하고,
여러 source의 혼합은 질량가중 fiber 합이다.

동일 class/suffix인 두 label의 mass(3,1), birth(6,4)를1/4 서비스하면
mass(3/4,1/4), birth(3/2,1)이다. 두 label이2와1person/veh를 운반한다면
1veh의 물리 흐름에서 person량7/4가 정확히 복원된다. bus run별 completion
threshold와 egress law는 fiber projection 뒤에 적용한다. tag를 버리지 않는다.
차종·현재속도 또는 next destination만 같다는 이유로 전체 미래행동을 합치지 않는다.

**C: support 경계를 보존하는 rank/phase 재구축.** common speed의 이동좌표
\(X(t)=\int_0^t v(s)ds\)에서 cohort는
\(x(t;\tau)=\min\{L,X(t)-X(\tau)\}\)를 따른다. 도착 질량은 ordered boundary
queue에 남기고 \(D\le E\)인 rank prefix만 방출한다. class/purpose/info와
birth mark를 운반한다. support 경계를 먼저 넣은 뒤 mass간격δ를 추가하면
block 수는 구성적으로 \(\lceil M/\delta\rceil+J_\sigma\) 이하이다.
\(J_\sigma\)의 전역 상한은 아직 없다.

이 경계가 필요한 예: A prefix(1−ε)는 열린 출구, B suffixε는 공급0 출구로 간다.
순서 보존 queue는1−ε를 방출한다. 전체를 하나의 homogeneous block로 평균하면
처음부터 B가 head에 섞여 방출0이다. ε=10^-4에서 composition prefix오차는
0.00009999veh지만 출발량 차이는0.9999veh다. mandatory support경계 하나를
보존한 두 block은 이 예를 정확히 복원한다.

**D: 충분한 feature를 보존하는 양의 moment 재구성.** 유한 양의 atom 분포에서
m개의 feature(상수1 포함)를 고정하면 선형종속 제거로 at most m개의 source atom에
같은 feature integrals를 구현한다. 예를 들어 p={0,1/4,1/2,3/4,1}의 균등분포는
p={0,1/2,1}, weight(1/4,1/2,1/4)로 m0,m1,m2=(1,1/2,3/8)를 보존한다.
affine latent law \(p'=r-\lambda p\)에서는 이 moment 공간이 닫힌다.
FIFO eligibility와 tag별 정책까지 닫히려면 해당 질의를 별도로 포함해야 한다.

**E: midpoint 대신 source flux의 시간적분으로 mark를 정의한다.**
held phase의 실제 uniform flux r에 대해
\[
J_v=r[\chi(b)-\chi(a)],\quad
J_p=r\left[P(b-a)+(p_0-P)e^{-\lambda a}
\frac{1-e^{-\lambda(b-a)}}{\lambda}\right].
\]
여기서 χ는 source characteristic의 누적거리, \(\lambda>0\), P는 latent 평형값이다.
\(\lambda=0\)은 상수 p0의 극한으로 처리한다. 이 적분은 동일 physical phase의
분할에 가법적이다. receiving mark 평균도 분할에 무관하다.
기존 midpoint와 다른 버전이므로 새로운 검증 대상이다. 실제 rate·target·support가
변하는 경계를 없애는 주장은 아니다.

**발산적 관계.** O는 observer, A는 표현, B는 행동 차원, C는 해상도와 support,
D는 feature 충분성, E는 수송 mark의 수치 규약을 바꾼다. A+B+O처럼 조합할 수 있지만
어느 경로도 혼자24h resource 충족을 보장하지 않는다. 같은 query를 매번 전개하면
A의 비용은 evaluator로, copied fiber를 만들면 B의 비용은 provenance로 이동한다.


## R5 — 직접 유도와 증명

전체 정의·단위·중간 계산·반례는 다음 세 동반 문서에 보존한다.

- [정확 표현과 행동 quotient](V03_BOTTLENECK_EXACT_TRANSPORT_20261123.md):
  A1 구간측도 연산 폐쇄, A2 원래 이산 step의 실수 동치,
  B1 class/residual-route quotient, sink/egress/fiber 계산.
- [결합 capacity와 support-aware 측도](V03_BOTTLENECK_COUPLED_MEASURES_20261123.md):
  공동 arrival/capacity 안정성, 조건부 피드백, support 복원,
  phase/FIFO/장부, 지연 개발의 small-gain 계산.
- [관측자 분리·충분 질의·flux 적분](V03_BOTTLENECK_OBSERVER_MARKS_20261123.md):
  O1 lossless observer, Q1 dual closure, Q2 양의 feature 재구성,
  E1 보존적이고 분할에 가법적인 finite-response mark 수송.

### 공동 arrival/capacity 경계

연속 비감소 E, 절대연속 비감소 C, \(E(0)=C(0)=0\)인 초기빈 서버에서
\[
D(t)=\inf_{0\le s\le t}\{E(s)+C(t)-C(s)\}.
\]
\(f=C-\widetilde C\)라 두면 두 infimum 내부 차이는
\(\Delta E(s)+f(t)-f(s)\)다. 따라서
\[
\boxed{\|D-\widetilde D\|_{\infty,[0,t]}
\le\|E-\widetilde E\|_{\infty,[0,t]}
+\operatorname{osc}_{[0,t]}(C-\widetilde C)
\le\epsilon_E+\int_0^t|c-\widetilde c|ds.}
\]
이는 service율 양의 하한을 쓰지 않으므로 zero-capacity 구간도 포함한다.
초기 eligible stock이 양수인 경우는 별도 empty-history candidate C(t)를
min에 넣어야 한다. 누적시간 역함수에는 별도의 양의 departure slope가 필요하다.

\(E=3(t-1)_+\), \(C=\min(t,1)\), \(\widetilde C=2(t-1)_+\), \(0\le t\le2\)이면
capacity sup차이는1이지만 \(D(2)=0,\widetilde D(2)=2\)다.
따라서 capacity의 sup차이를 계수1로 더하는 개선은 거짓이며 oscillation항이 필요하다.

무차원화한 물리 state오차 z와 누적 departure오차 d에 대해
\[
z\le z_0+L_y\int(z+d)+\int r_y,\quad
e\le\eta_E+L_E\int(z+d),\quad
|c-\widetilde c|\le L_c(z+d)+r_c
\]
가 실제 연산자에서 성립하면 위 경계와 Gronwall로
\[
\boxed{z(t)+d(t)\le
[z_0+\eta_E+\int_0^t(r_y+r_c)ds]e^{(L_y+L_E+L_c)t}.}
\]
고정 class/movement support, nonvacuum, positive active denominators,
bounded-density eligibility 또는 적절한 hybrid event 처리가 그 전제다.
원래 multi-sender allocator 전체의 상수와 도시 전체 feedback 상수는 미확정이다.

### 질의 폐쇄와 양의 재구성

기능적 요약 \(P\mu=(\langle\psi_i,\mu\rangle)_i\)가 정확하려면 모든 제어·guard·reset이
이 요약과 남겨 둔 explicit state에서 결정되고, 수송 pullback이
\(A_a^*\psi_i=\sum_jM_{ij}(a)\psi_j\)로 닫혀야 한다.
적분의 쌍대성으로 \(P(A_a\mu)=M(a)P\mu\)이고 event별 귀납이 가능하다.
이 조건이 A의 cheap query와 B의 sufficient behavior를 연결한다.

양의 atom의 feature vectors가 m차원에서 종속이면
\(\sum_i a_i\phi(\theta_i)=0\), \(\sum_i a_i=0\)인 a를 골라,
\(s=\min_{a_i>0}w_i/a_i\), \(w'_i=w_i-sa_i\)로 갱신한다.
모든 weight는 비음수, feature는 불변, atom은 적어도 하나 줄어든다.
반복하면 at most m source atoms로 충분하다. 이는 positive cubature의
유한 입력에 대한 구성적 증명이며, 세계 최초 정리라는 주장은 없다.
consumer \(g=\sum_i\alpha_i\phi_i+r_g\), \(|r_g|\le\epsilon_g\)면
\[
|\langle g,\mu-\widehat\mu\rangle|\le2M\epsilon_g
\]
이므로 구체적인 residual을 피드백 경계에 넘길 수 있다.
eligibility·rare blocked indicator가 feature에 없으면 이 residual이 작다는
주장은 불가능할 수 있다. 실제 필요한 indicator를 보존하는 것이 복원이다.

### finite-response 적분형 수송

held characteristic의 거리 χ와 latent \(p=P+(p_0-P)e^{-\lambda t}\)에서
\(r\int v=r[\chi(b)-\chi(a)]\)와 R4의 latent integral을 직접 얻는다.
구간 합의 가법성으로 receiving weighted moment와 보존량이 임의의 인위적
세분에 무관함을 증명했다. 기존 midpoint차이는
\(rh^3\sup|g''|/24\)로 국소 제어한다. 가속도 포화 전후를 분리하며 실제
control phase 변화는 유지한다. Wolfram에서 antiderivative와 분할 잔차가0이었다.

### 배경 모델의 피드백 안정성

occupancy–speed의 busy/unclipped 예
\(\dot n=a-\gamma v,\ \tau_v\dot v=U_0-\kappa_n n-v\)는 양의 eigenvalue를 갖는다.
수요 \(a=a_0-kn\)를 쓰는 지정된 모델에서는 trace/determinant로
\(k>\gamma\kappa_n\)가 Hurwitz 조건이다.
지연 개발 \(\tau_z\dot z=-\chi n(t-d)-z\), 수요항 \(+\beta z\)까지 포함하면
\[
k>\gamma\kappa_n+\beta\chi
\]
가 모든 고정 유한 d에 대해 양의 decay rate를 구성하는 충분조건이다.
각 지연에 같은 uniform decay rate를 주장하지 않는다. weighted envelope의
세 부등식으로 증명하며 실제 M04 parameter 충족은 아직 조사하지 않았다.
이는 단기 수치오차 경계를 장기 도시 안정성으로 오해하지 않도록 하는 구성적
피드백 모델이다.

**진행 중 독립 검토에서 즉시 반영한 교정.** transversality와 Lipschitz reset만으로
jump가 있는 state의 same-time sup 안정성을 얻는다는 문장을 철회했다.
reset \(y\mapsto y+1\)이1과1+ε에 일어나면 sup차이는1이다.
연속 state의 mode-switching 추정과 event-aligned jump 관측을 분리했다.
새 jump-metric 정리나 원래 native atomic eligibility의 포괄적 안정성은 주장하지 않는다.


## R6 — 독립 단회 검토와 surgical correction

[독립 검토 전문](V03_BOTTLENECK_INDEPENDENT_REVIEW_20261123.md)은 고정 source
492e276의 git object와 실제 함수들을 읽고, 저자 판정을 전제로 삼지 않은 한 번의
검토다. 발견된 두 실질적 오류와 한 근거 연결 문제를 같은 회차에서 수정했다.

| 항목 | 반례·결함 | 반영한 최소 교정 |
|---|---|---|
| F1 jump state 안정성 | reset이1과1+ε에 일어나면 event shiftε이나 same-time sup차이는1 | 연속 state/mode-only 추정으로 제한; jump·atomic CDF는 event alignment나 atom오차 별도 |
| F2 Mixed packet의 결합 정보 | 동일tag·동일clock목록·동일총량도 clock별 mass배분은 다를 수 있음 | endpoint keyη별 root/fiber, 원래 head membership·target·공통 service fraction 유지 |
| F3 양의 재구성 증명 참조 | 저자 문서 축약 뒤 “위 증명” 참조가 남음 | 실제 소거 증명을 observer/marks Q2에 보존하고 연결 교정 |

F2의 두 상태
\[
\mu=\tfrac12\delta_{(z,1)}+\tfrac32\delta_{(z,2)},\qquad
\nu=\tfrac32\delta_{(z,1)}+\tfrac12\delta_{(z,2)}
\]
는 tag mass2와 clock목록{1,2}가 같지만 결합측도는 다르다.
따라서 일반 Mixed 입력에는 \(v_{h,\eta}\)와 \(M_{g,\eta},K_{g,\eta},J_{g,\eta}\)를 쓴다.
이 η 성분을 새 FIFO head로 나누면 안 된다. 원래 head에서 정한 f를 모두에
공통 적용하고 remainder의 η를 보존하며, outgoing만 원래처럼 새 service
interval로 reset한다. 실제 endpoint-component 수도 비용에 포함했다.

**검토 후 유지된 결과.** A/B의 가정된 실수 동치, O의 공통 admissible 영역의
관측자 분해, E의 held integrand 가법성, 공동 E/C 경계, 조건부 Gronwall,
양의 feature 소거와 residual경계는 해당 조건 아래 유지됐다.
새 native 구현이나24h 수용을 검증한 결과로 해석하지 않는다.

**실제 journey 인터페이스의 더 구체적인 계약.** sink egress는 delay-law
pushforward 뒤 원래 due prefix인 end+10^-10을 사용한다. receipt 시각은
max(t, raw_due_time), receipt fraction은 해당 leg total로 정규화한다.
A의 “원래 sampling convention”은 이 세 연산을 포함한다.
bus tag별 near-one threshold, active ReceiptHistory, 다음 leg release도 유지한다.

**독립 산술 확인.** index항을 전부 제거한 구조합계5,037,909,336B,
동일 allowance 대비12,694,761B 초과, old-trace 조건부 payload차이458,883,136B가
기록과 일치했다. 이는 새 memory 측정이 아니다. input/current/candidate와
외부 snapshot에서 reachable한 실제 소유자를 모두 포함한다는 비용 계약을 유지한다.

수정 문단을 다시 읽는 것까지 같은 단회 검토에 포함하고 검토를 종료했다.
새 감사 루프는 만들지 않는다. 미확정한 native query support와 coupling 상수는
R8/R9의 연구 내용으로 남긴다.


## R7 — 기호·유리수·고정밀 판별 계산

[재현 계산과 입력·출력](../../artifacts/v03_bottleneck_theory_20261123/calculations/README.md)을
보존했다. Python3.12.14 표준 라이브러리로 두 caller를 실제 실행했고 모두 exit0이다.
기존 fluid-server helper는 그대로 재사용했고, 새 caller가 E와 C를 함께 바꾼다.
생산 코어 import, native build, 추가 도시 실행은 하지 않았다.

| 계산 | 실제 결과 | 증거의 범위 |
|---|---|---|
| 공동 E/C 변화 | 유리수 PL128쌍에서 oscillation·rate-L1 경계 성립 | 유한 사례 검산; 일반 증명은R5 |
| 독립 queue balance | reflection 결과와 정확히 일치 | 내부 queue-emptying knot까지 포함 |
| capacity sup계수1 반례 | capacity오차1, departure오차2 | 잘못된 강화를 배제 |
| rare blocked tail | prefix오차9999/10^8, departure차이9999/10^4 | support 보존 조건 판별 |
| overlay·quotient 예 | R4의 mass/birth/person/cargo 분수가 정확히 일치 | 실제 도시속도 결과 아님 |
| Mixed endpoint 반례 | 동일총량2, clock prefix질량1/2와3/2 | 결합 정보의 필요성 |
| jump event 반례 | time shift1/100, same-time오차1 | 수정된 metric 구분 |
| 초기 eligible stock | 올바른D(0)=0, 잘못된empty식은2 | 초기조건 후보 필요 |
| positive elimination | source5atoms→2atoms, m0/m1/m2보존 | 모든 consumer의 정확성은 아님 |
| nonlinear p^3 consumer | 실제차이1/32, 경계2Mε≈0.096225 | feature residual의 구체적 예 |

positive elimination은 p=0,1/4,1/2,3/4,1의 균등질량에서
두 null방향으로 weight를 이동해 p=1/4,1에(2/3,1/3)을 남겼다.
m0,m1,m2=(1,1/2,3/8)는 같다. 그러나 p^3는1/32만큼 달라진다.
\(g_0=(3/2)p^2-(1/2)p\)에 대해
\(\sup_{[0,1]}|p^3-g_0|=\sqrt3/36\)이므로 Q2/Q3의 residual경계에 들어온다.
완료량을 보존하는 것과 임의 비선형 소비자를 보존하는 것을 실제 계산으로 구분했다.

### mark 적분의 해상도 실험

\(v(t)=1-e^{-t}\), flux1veh/s, [0,2]s에서 정확한 moment는
\(1+e^{-2}=1.135335283236612691894\)veh·m/s다.

| 균일 subinterval 수 | 기존 midpoint moment의 절대오차 | 적분식 subdivision 잔차 |
|---:|---:|---:|
| 1 | 0.128905834421 | 60자리 Decimal에서0 |
| 2 | 0.0350038969023 | 0 |
| 4 | 0.00894167870186 | 0 |
| 8 | 0.00224763306707 | 0 |
| 16 | 0.000562676319057 | 0 |
| 32 | 0.000140717157173 | 0 |

모든 값이 \(T h^2\sup|v''|/24\) 경계 안에 있고, 분할을2배로 할 때 오차비는
4로 접근한다. 이것은 지정된 held phase의 수치 실험이며 성능 benchmark가 아니다.
latent 적분도 λ=0,0.1,2에서 분할 잔차를10^-56 이하로 확인했다.

Wolfram의 실제 입출력을 함께 보존했다. antiderivative 잔차0, semigroup split
잔차0, midpoint차이의 양의 형태 잔차0을 얻었다.
별도 계산에서 피드백 행렬의 determinant
\((k-\gamma\kappa_n)/\tau_v\), nonlinear consumer 차이1/32도 확인했다.
기호 계산은 식의 검산이며, 원래 도시의 계수·수용·실행 결과를 대체하지 않는다.
