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
