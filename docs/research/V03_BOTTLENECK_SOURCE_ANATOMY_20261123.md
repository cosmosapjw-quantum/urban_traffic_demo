# MetroFlow: 연쇄 병목의 소스·관측량·소유권 해부

## 범위와 판정

이 문서는 현재 원본 소스와 이미 보존된 영수증을 읽어 수행한 R1·R2·R3·R7 작업이다. 읽기 기준 HEAD는 **492e27618696df2514b088a64de450cf69746647**이다. production 코드, 원격 파일, branch, commit, push, native build를 변경하지 않았고 새 물리 simulation이나 runtime benchmark도 실행하지 않았다. 허용된 새 계산은 기존 JSON의 합계·비율과 소스의 정수 비용식 대입, 세 개의 이미 추출된 head JSON 요약뿐이다.

현재 질문은 “다음 guard를 어떻게 통과시킬까?”보다 좁고 계산 가능하게 잡았다. **현재 물리 상태의 어떤 정보가 실제 다음 상태를 결정하며, 그 정보가 source head → 비례 service → event/incoming → interval sweep → retained state → checkpoint에서 어떤 중간 곱집합으로 재물질화되는가?** 기존 수정의 성공과 실패를 모두 보존하고, 병목을 index 하나나 FIFO 자체의 불가능성으로 미리 결론내리지 않는다.

확인된 결과는 다음과 같다.

- 현재 binary는 원본 Valley 100k 입력을 0→25,700 s까지 실행했고 마지막 3,405,043,386-byte wire가 역사적 checkpoint와 동일하다. S07의 25,710 s 시도는 **추가 유효 물리 시간 0 s**인 자원 차단이다. [S07, S08]
- 25,700 s의 cell 상태에는 631,350 packets와 34,610,422 part rows가 있다. road 질량은 약 778.576739 vehicle units이며, journey 전체 active vehicles 1,234.117414와는 범위가 다르다. resident stock 100,000, tag registry, packet 수, part 수, 물리 질량은 서로 다른 양이다. [S07; ENGINE 1664–1719; ROAD 3475–3477]
- 현재 시도는 258,022 source serves에서 17,429,035 event rows를 만들었다. 같은 행들의 exact time-pair runs는 206,999개다. 원본 head×serve와 active source×output interval의 두 전개가 연결된다. [S07; ROAD 3908–4033, 3171–3322]
- 실패한 indexed-sweep scratch 13,723,920 B를 전부 제거한다고 가정해도 나머지 구조식이 allowance보다 12,694,761 B 크다. guard 이름은 전체 원인과 같지 않다. 이 결과는 현재 구조식의 산술이지 실제 RSS 하한이나 표현 일반의 no-go가 아니다.
- 이전 tick의 last_events는 현재 whole-native 경로의 물리 갱신식에는 읽히지 않는다. 현재 tick에서 새로 생성한 sink projection은 service/journey에 사용된다. “이미 소비한 event trace의 보존 형식”과 “현재 tick에서 물리에 필요한 event projection”을 분리할 수 있는 정확한 소스 경계가 있다. [JOURNEY 731–844, 1419–1761]

## R1. 보존할 과학 목적과 실행 계약

049236458fdb5a7e327b0e494ab5f5cc3ad25b61의 PRD 5행은 도시 생성–교통–접근성–도시발전–행동/학습의 설명 가능한 결합을 목표로 한다. 같은 PRD의 17·22·27·28·43행과 spec의 4·8·13·24행은 100k 규모의 mesoscopic transport, 지연 접근성 기반 토지이용 피드백, 우회도로와 유발수요의 방향성을 요구한다. 65245008af2387a8ce56e72d54a198394de3eee2의 constitution도 이를 반복한다. [H0, H1, H2]

현재 과학 동기는 지도와 합법 경로 → 목적·차종·유한정보를 가진 수요 → 유한응답의 교통 → 도착·대기·접근성 → 지연 개발과 이후 수요의 연결이다. 배열 행의 수나 특정 중간 Vec, 특정 부동소수점 연산열 자체가 최초의 물리 목적은 아니다. 그러나 현재 원본 V03 oracle이 가진 route/class/birth/FIFO/eligibility 관측량을 바꾸면 그것이 exact representation인지, 실수 산술 동치의 다른 수치 구현인지, 별도 근사 모델인지 명시해야 한다.

이번 해부에서는 원본 수요, SI 시간, person/vehicle/cargo 장부, 원본 8 GiB/7,200 s 및 24 h × 3 cases × 3 repeats 수용 기준을 수정하지 않는다. 현재 native state/read/write 의미를 읽는다. 문서에 남은 예전 next action이나 제한된 병합 실패를 새 연구 선택지 전체를 막는 규범으로 사용하지 않는다.

## R2. 재사용한 원자료와 identity

현 HEAD의 ROAD·ENGINE·JOURNEY·HISTORY blob은 S07/S08이 사용한 source commit **03b76ccf2ef6bc087d38681c78716e749cce3943**의 같은 파일 blob과 각각 일치한다. 따라서 아래 소스 해석을 해당 영수증의 실제 코어에 연결할 수 있다. 전체 후보 source fingerprint는 **bea107c2888885966c901a0f30a6d7edcb50a24e5cbbbe31d3f8bf020536943d**, binary SHA-256은 **22a7cebc751b575521a8360ab7e235aa7fa6fa9e4d54c8ac8904b35e708ae57a**이다. 본 작업이 binary를 새로 실행해 이 fingerprint를 재검증한 것은 아니다. [S07, S08]

| 표기 | 저장소 상대 경로 | 기준 blob 또는 SHA-256 |
|---|---|---|
| ROAD | crates/metroflow-rust/src/v1_road.rs | blob f2d2031e8710b57b6b1be430ece7695430c19eb3 |
| ENGINE | crates/metroflow-rust/src/v1_engine.rs | blob d245c93936f8210db36cad88fab458b2dc9800cf |
| JOURNEY | crates/metroflow-rust/src/v1_journey.rs | blob 34a0e1fc2841a1dba29684c77e1c0e15aa69c5df |
| HISTORY | crates/metroflow-rust/src/v1_history.rs | blob 9920212dd0a0e3fa85e6ba2f73c536388809833b |
| S07 | artifacts/v03_causal_rank_20261123/S07_original_continuation.json | SHA-256 38e15baaf9555cd0c5fae2e55f6c51fbb3e04d9642acb690ad9597ed51e1e4b9 |
| S08 | artifacts/v03_causal_rank_20261123/S08_time_zero_prefix.json | SHA-256 a7bdfb8c5e016b39685b20a33ae8722ba69ad44ba252bbbcf3f586c5f0a4f79b |
| HEADS | artifacts/v03_causal_rank_20261123/S06_original_fifo_heads.json | SHA-256 7152480c49fec04d4a700c9f0716d140f0c3a7c62d967d323723203be71c711c |
| A17 | artifacts/v1_v03_workspace_20261117/ATTRIBUTION.json | SHA-256 1c5acb5b4a587cbbcc0a2314bd83dae864677a08ea1c7cb787e37602e29eac10 |
| A17-text | artifacts/v1_v03_workspace_20261117/ATTRIBUTION_KO.md | blob b12b9b699d29a333d6ae1b61211f76faf5d6a0b5 |
| SW19 | artifacts/v03_fifo_interval_sweep_20261119/C10_RESEARCH_RECEIPT.json | SHA-256 db1d85cb538b19962c98043935da3e5e1bbce8f89aa618026d35f2b9ffefd74d |
| ST20 | artifacts/v03_fifo_service_stream_20261120/C10_RESEARCH_RECEIPT.json | SHA-256 6ea5fbebfe5a0708e74b0debf3de08eedf2f7ab5e3bb49daf0cf562562683826 |
| UA20 | artifacts/v03_fifo_unique_accounting_20261120/C10_PAIR_POST25650_25700.json | SHA-256 07da5c68ef2a61d4ceb491abeae4bd9c47b088660fc6e93883a17f1522d8316e |
| KEY21 | artifacts/v03_persistent_keyset_20261121/C6_REAL_KEYSET_CENSUS_25680.json | SHA-256 927139140c2a7c93809e466574a5a98950112ee0488c67ec9f6668bf3f0a5d09 |
| EP21 | artifacts/v03_event_pages_20261121/C10_RESEARCH_RECEIPT.json | SHA-256 549a23dc20aac116e386d5625c36e43f507a5ff11f852fb7da394ea16a6df54f |
| PL21 | artifacts/v03_packet_lifetime_20261121/C10_RESEARCH_RECEIPT.json | SHA-256 7d142e26bec01dc01d5dbe88aa85b2eed8ba48b5324892de10515a7eef974dc2 |
| W21 | artifacts/v03_weighted_fifo_20261121/C10_RESEARCH_RECEIPT.json | SHA-256 cdf63a029e079c2763fa047d1ece359f21112011350d9d4354e73d684a60165e |

전체 파일 SHA, last-change commit, S07/S08 counter와 비용식 대입 결과는 동반 JSON에 있다. 대용량 binary checkpoint는 이번 해부에서 다시 열거나 해시하지 않았다. 그 byte identity는 보존된 S07/S08 실행 증거의 재사용이며 새 decode/physical test가 아니다.

## R3. 서로 구분해야 하는 상태 크기

t에서 다음을 정의한다. 질량의 단위는 vehicle units, 시간은 s, birth first moment의 단위는 vehicle·s이다. 기호의 나머지 크기는 정수 개수다.

| 기호 | 정의 | 현재 기록에서의 값/상태 |
|---|---|---|
| \(N_{\rm road}\) | cell+pending에 저장된 \(\sum m\) | 25,700 s: 922.1750575039921−143.59831861060766 = 778.5767388933845 |
| \(N_{\rm journey}\) | journey 장부의 전체 active vehicle amount | 1,234.1174136872016; road만의 질량과 다름 |
| \(T_{\rm live}\) | 살아 있는 고유 tag, 또는 tag/offset support의 개수 | 전체 상태에 대해 선택한 영수증에는 직접 기록되지 않음 |
| \(T_{\rm registry}\) | 등록된 physical route tags | 304,856; unique interned paths는 38,916 |
| \(Q\) | retained FIFO packet 개수 | cell 631,350, pending 0 |
| \(P\) | retained packet의 part row 개수 | 34,610,422 |
| \(S\) | 한 시도에서 source head에 서비스한 횟수 | 258,022 |
| \(E\) | 새 event rows | 17,429,035 |
| \(I\) | 새 raw incoming rows, pending admission 포함 | 17,194,407 |
| \(K\) | 연속 event 행에서 동일한 start/end **bits**의 maximal runs | 206,999; unique endpoint 수가 아님 |
| \(D_j\) | 목적지 j의 서로 다른 nonpoint interval-pair 수 | 첫 처리 cell에서 2,610 |
| \(U_j\) | 목적지 j의 서로 다른 numeric endpoint 수 | S07은 할당 전 차단되어 직접 미측정 |
| \(A_j\) | 모든 출력 interval에서 방문한 active source row incidence의 합 | S07에서 전체 sweep이 수행되지 않아 미측정 |
| \(O_j\) | interval별 combine 이후 남는 출력 part rows 합 | 현재 실패 이후 값 미측정 |
| \(L\) | 동시에 살아 있는 immutable state/trace owner 집합 | 입력 snapshot, committed, candidate 등 phase에 의존 |

ROAD의 Part는 tag, offset, mass, birth, a, b이다. Uniform packet은 공통 a,b와 24 B CorePart 배열을 갖고, SharedKeys는 공통 key 배열과 각 packet 고유의 mass/birth 배열을 갖는다. Mixed는 wide Part 배열이다. 서로 같은 tag 목록을 가져도 두 packet의 mass/birth와 FIFO 위치는 다를 수 있다. [ROAD 132–244]

현재 평균 P/Q≈54.8197이다. P/Nroad≈44,453.45라는 비율은 **작은 양의 fluid 질량을 매우 많은 표현 행이 나누어 가진다는 진단**이다. “실제 차량이 4만 배 생겼다”거나 “tag 구분이 불필요하다”는 뜻이 아니다.

HEADS의 실제 완전 head 세 개를 JSON에서 새로 합산한 결과는 다음과 같다.

| cell | rows / unique tags / unique tag-offset | unique time pairs | \(\sum m\) | \(\sum birth\) |
|---|---:|---:|---:|---:|
| 466 | 464 / 464 / 464 | 1 | 0.21627890666666663 | 5505.063290536906 |
| 908 | 454 / 454 / 454 | 1 | 0.21571050666666675 | 5484.1241845450695 |
| 751 | 442 / 442 / 442 | 1 | 0.11086213333333325 | 2836.118877605572 |

이는 한 head 내부의 tag 축은 실제로 구별되지만 clock 축은 동일함을 보인다. 전체 도시에서 live tags가 이 세 head의 합이라는 뜻은 아니다.

## 실제 전개 연쇄

### 1. 입력 retained state와 head 구성

한 tick은 입력 RoadState를 검사하고 candidate를 만든다. 기존 queue의 part payload는 immutable Arc clone으로 공유하지만 queue slot은 별도다. motion은 cell별 class 질량을 계산하고 각 packet의 target과 공통 cell displacement에서 ready time을 구한다. [ROAD 3499–3559, 3624–3653]

각 junction substep에서 현재 head의 모든 rows를 순회하여

\[
M_h=\sum_{\ell\in h}m_\ell,\qquad
\beta_{hj}=\frac{\sum_{\ell:\,dest(\ell)=j}m_\ell}{M_h},\qquad
\beta^{\rm space}_{hj}
=\frac{\sum_{\ell:\,dest(\ell)=j}m_\ell\,\lambda_\ell}{M_h}
\]

를 다시 만든다. \(\lambda_\ell\)은 receiving/storage를 위한 class footprint다. rates는 \(\beta\), send caps, downstream receive supply와 priority weights를 입력으로 progressive filling을 수행한다. \(\beta^{\rm space}\)는 공간 소진 시간 계산에 쓰인다. tag별 birth나 과거 a,b를 rates가 직접 읽지는 않는다. [ROAD 3691–3777, 3324–3379]

이 단계의 비용은 registry tag 총수만으로 결정되지 않는다. **head가 몇 번 재검사되는지 × 각 head가 몇 행인지**가 중요하다. 기존 lineages의 공유가 있더라도 소비자가 매번 모든 행을 다시 순회하면 연산은 남는다.

### 2. source head × proportional serves

서비스 길이는 남은 tick, 미래 ready, head 질량 소진, downstream free capacity 및 space 소진 중 최소로 정해진다. 적용 비율은 원본 binary64로

\[
f=\min(1,rh/M_h),\qquad 1-f<10^{-14}\Rightarrow f=1
\]

이고, 각 행은 m·f와 birth·f를 별도 반올림한다. 양의 결과만 남는다. partial이면 m·(1−f), birth·(1−f)의 **새 remainder 배열**을 생성하고 pack하여 queue slot을 대체한다. [ROAD 3778–3817, 3911–3924, 1623–1650, 4025–4033]

한 source head h가 k_h개의 살아 있는 rows를 가지고 s_h번 서비스된다면, underflow가 없는 고정 support에서 event occurrences는 k_h s_h이다. 원본은 serve view 자체의 임시 Vec는 피하지만, 그 view의 모든 rows를 새 EventRow/IncomingPart/Mark에 기록한다. partial remainder도 k_h-scale 새 물리 payload다.

이 k_h s_h는 “원본 eager consumer가 전개한 곱집합 크기”다. 실수 산술에서 \(\mu_{h,s}=f_s\mu_h\)라는 factorization을 갖는다는 것과, 모든 후속 관측을 현재 binary64 연산열까지 보존하면서 sublinear하게 계산할 수 있다는 것은 별개 주장이다. 소스는 sum(rounded m_i)를 f·sum(m_i)로 교체하지 말라고 명시한다. [ROAD 1623–1626]

S07에서 평균 E/S≈67.5486 rows/serve, partial serves 36,061/258,022≈13.9759%, partial served-row occurrences 5,834,537이다. all-input P와 이 partial count를 합쳐 “다음 P”를 추정할 수는 없다. sink, survivor, 새 entry, combine, interval split이 모두 개입한다.

### 3. event와 incoming의 서로 다른 소비 경로

모든 served row는 (tag, source, destination, mass, start, end, birth)를 event에 쓴다. destination이 있으면 offset을 한 칸 진행시키고 새 service interval로 a,b를 덮어 incoming에 추가한다. 동반 Mark는 source에서 sample한 speed와 class latent다. sink row는 도로 class/global 장부에 먼저 반영된다. [ROAD 3980–4017]

S07의 실제 road-service incoming은 17,143,679 rows, sinks는 285,356 rows다. pending 입장에서 들어간 50,728 rows를 더해 목적지 raw incoming이 17,194,407가 된다.

현재 candidate event carrier는 32 B payload rows와 연속 time-pair run마다 16 B를 저장한다. B=4096 exact pages이므로 payload는

\[
C_{\rm ev}(E,K)
=32B\lceil E/B\rceil+16B\lceil K/B\rceil.
\]

S07에 대입하면 정확히 561,184,768 B이다. 기존 48 B page rows 대비 실제 payload 절감은 275,578,880 B다. descriptors와 carrier metadata는 별도다. 이 codec은 E를 줄이지 않으며, event field/order/bits만 재인수분해한다. [ROAD 480–608, 637–647; S07]

incoming은 현재 compact Part 40 B와 Mark 16 B가 각 목적지별 B_in=128 pages에 있다. 최종 raw append 이후 descriptor capacities를 고정하고, 목적지의 원래 순서에 따른 speed/latent 계산과 combine이 끝난 다음 그 목적지의 Part와 Mark 소유자를 실제 drop한다. 해당 drop 전에 “나중에 사라질 것”이라는 이유로 비용을 빼지 않는다. [ROAD 2143–2175, 1070–1105, 4192–4233]

### 4. raw interval source → indexed sweep → retained packets

목적지별 combine은 (tag,offset,a_bits,b_bits)가 같은 raw rows를 원래 source index 순서의 sum으로 합친다. S07 첫 처리 cell은 468,093→458,667 rows, 9,426 rows(2.0137%) 감소다. 이때 raw Part+Mark 26,213,376 B가 해제되어 incoming rows는 16,726,314로 줄었다. [ROAD 2210–2244, 4222–4236; S07]

현재 interval_packets는 nonpoint source마다 start/end index, point source마다 point/current_points index 및 source active bitsets를 준비한다. unique endpoints는 그 정렬된 stream을 합쳐 얻는다. 각 elementary interval [u_k,u_{k+1}]에 대해 active source rows를 다시 tag/offset으로 정렬하고

\[
m_{k,\tau}
=\sum_{\ell\in A_k:\,key(\ell)=\tau}
m_\ell\frac{u_{k+1}-u_k}{b_\ell-a_\ell},
\qquad
B_{k,\tau}
=\sum_{\ell\in A_k:\,key(\ell)=\tau}
B_\ell\frac{u_{k+1}-u_k}{b_\ell-a_\ell}
\]

를 계산한다. 각 기여의 multiply/divide는 소스 순서의 binary64 연산이고, point는 별도 처리한다. 각 구간의 결과는 새 CorePart 배열로 retained packet에 저장된다. [ROAD 1748–1905, 2295–2345, 3171–3322]

\[
A_j=\sum_k |A_{jk}|,\qquad
O_j=\sum_k |\{key(\ell):\ell\in A_{jk},\ {\rm positive\ output}\}|
\]

라 두면 보통 \(O_j\le A_j\)다. **active-source × elementary-interval incidence** A_j가 두 번째 전개이다. naive all-row scan을 event sweep으로 바꿔도 출력 O_j 자체를 row로 보존하는 부분은 남는다.

S07의 exact.intervals=2610은 서로 다른 nonpoint (a,b) 쌍의 수다. unique endpoint 수 U_j가 아니다. exact.point_rows=135915는 raw point occurrences이고 combine 이후 point 수도 아니다. 첫 index 비용식을 역산하면 combined point=126,489, nonpoint=332,178이다. 따라서 2,610개의 positive interval-pair를 332,178개의 nonpoint rows가 보유하며 평균 127.2713 rows/pair이다. 이 중복 clock 축과 tag 축의 곱 구조는 구체적이다. 어느 source mixtures를 합쳐도 충분한지는 별도 검증해야 한다.

### 5. retained state와 다음 tick

candidate에는 기존 queue survivors와 새 interval packets가 합쳐진다. 이후 state 검사, road candidate/snapshot guard, event flatten, continuous keyset interning, service finish, journey finish, checkpointability를 모두 지나야 하나의 tick이 commit된다. [ROAD 4089–4115, 4254–4326, 2950–3035; JOURNEY 1548–1761]

한 tick 뒤 저장 행의 정확한 구조는

\[
P_{n+1}
=P_{{\rm surviving\ cell},n}
 +P_{{\rm pending},n+1}
 +\sum_j O_{j,n}.
\]

그 결과가 다음 tick의 head support와 partial-service 횟수에 되먹임된다. 이 식은 P(t)가 장기적으로 지수 증가한다는 정리가 아니다. 병목·서비스 스케줄·sink 배출·수요 시간표·route encounter가 변하면 성장률도 변한다.

### 6. checkpoint와 외부 관측

원본 road wire는 각 packet의 target/row count, 각 part의 tag/offset/mass/birth와 endpoint option payload를 **확장 순서대로** 기록한다. 현재 압축된 Arc/SharedKeys 정보는 wire에 나타나지 않는다. 따라서 내부 factorization을 바꾸더라도 decoder의 row iterator가 같으면 같은 road wire를 stream할 가능성이 있다. 반대로 legacy wire를 만드는 요구에는 확장 행 수에 비례한 I/O 하한이 있다. 그 하한을 모든 내부 tick의 물리 연산 하한으로 옮길 수는 없다. [ROAD 2549–2567]

## 관측량별 실제 소비 계약

| 소비자 | 실제 입력/통계 | 줄일 수 없는 구별 또는 주의 |
|---|---|---|
| motion | cell별 class mass, class parameters, latent, occupied length, cell speed | class support와 공통 유한응답 법칙. tag별 birth 자체는 직접 안 읽음 |
| ready/head 선택 | packet 순서, target, cell displacement, finite-response passage | 평균 질량만으로 FIFO head succession을 결정할 수 없음 |
| rates | head total mass, destination별 β, send/receive, priority | route별 개별 tag보다 destination projection이 직접 필요. 작은 blocked destination support도 물리 반응에 영향 가능 |
| free/space와 하위 event duration | β와 β_space, free, space | footprint-weighted destination mass를 별도 보존해야 함 |
| incoming speed/latent | source 순서의 \(\sum mv\), class별 \(\sum m\ell/\sum m\) | raw Mark/Part alignment; 같은 a,b나 tag만으로 충분하지 않을 수 있음 |
| interval packet 구성 | tag/offset별 시간구간 질량과 birth first moment, point atoms | time support·route composition을 global moments로 없애면 일반적으로 다음 head가 달라짐 |
| road 장부·검증 | class mass, birth/residence moments, route suffix legality | cumulative amount와 rate를 혼동하지 않음; 원본 tolerances 유지 |
| NativeServiceCore.finish | 현재 sink들의 tag별 mass sum | bus/freight 진행. 전달된 sink time은 유효성 검사, bus stop advancement는 tick end를 사용 |
| NativeJourneyCore.finish | 현재 sink의 tag,mass,end, egress access law | egress mass/time 분포; source/start/birth는 이 API의 직접 sink 인자는 아님 |
| ReceiptHistory.eligible | 완료시간+동작별 dwell의 threshold별 누적 fraction | 다음 leg release에 직접 사용. 단순 총완료량으로 대체 불가 |
| last_events publication/checkpoint | 모든 event field, insertion order, binary64 bits | legacy API/byte identity를 요구하면 lossless decoding 필요; 물리 갱신과 저장 형식을 분리할 여지 |
| downstream duration scenario observer | sink mass·midtime·birth, class | 현재 whole-native sink API에 안 들어간 birth도 저장/관측 계약에서 삭제할 수 없음 |

주요 read sites는 ROAD 3037–3169, 3699–3810, 4199–4253, 3380–3496; JOURNEY 790–844, 2046–2062, 2123–2145, 871–875; HISTORY 285–324이다. Python scenario의 sink-duration 관측은 scenarios.py 390–400에서 mass·(start+end)/2−birth를 사용한다. 그 관측은 whole-native next-state path와 같은 실행 경로라고 주장하지 않는다.

## phase와 composition을 분리한 비용식

### 계산 비용

head를 재검사한 occurrence를 v라 하고 k_v를 그 head의 part 수, 목적지 j의 combined input rows를 n_j라 하자. 현재 코어의 주요 비용은 다음 항들로 분해할 수 있다.

\[
W_{\rm step}
= W_{\rm state/motion}(P)
 +O\!\left(\sum_v k_v\right)
 +W_{\rm node}(S,\text{junction degree})
 +O(E+I+\text{partial remainder rows})
 +O\!\left(\sum_j n_j\log n_j\right)
 +W_{\rm sweep}
 +W_{\rm post}.
\]

sweep의 현 consumer는 source-index streams 정렬과 활성행 순회, 각 interval의 key sort 및 output construction을 수행한다. 따라서 대표적 상계 형태는

\[
W_{\rm sweep}
=O\!\left(
 \sum_j n_j\log n_j
 +\sum_{j,k}|A_{jk}|\log(1+|A_{jk}|)
 +\sum_j U_j\lceil n_j/4096\rceil
 +\sum_j O_j
\right).
\]

여기서 bitset term은 구현의 two-level active iterator에 따른 보수적 항이다. 이는 시간 벤치마크나 tight complexity theorem이 아니며 allocator/summation 상세를 단일 상수로 뭉친 composition model이다. 현 구현이 명시적으로 E event rows와 O output rows를 생성하는 한 적어도 그 쓰기 수에 비례한 일은 수행한다. 다른 factorized 알고리즘의 하한은 아니다.

### 살아 있는 소유자의 비용

일반적인 물리 heap은 phase p에서 실제 allocation identity 집합 \(\mathcal A_p\)에 대해

\[
M_p^{\rm payload}=\sum_{a\in\mathcal A_p}{\rm capacityBytes}(a),
\qquad
M_{\rm peak}^{\rm payload}=\max_p M_p^{\rm payload}
\]

로 센다. owner reference 수와 unique backing 수를 혼동하지 않는다. 서로 다른 phase에서만 존재하는 allocation을 합쳐 peak라고 하지 않으며, 서로 다른 packet의 같은 내용도 pointer alias가 아니면 실제 다른 allocation이다.

현재 road structural guard는 좀 더 보수적이다. x86_64 source 크기와 S07 변수로

\[
B_{\rm road}
=3R_{\max}-C_{\rm proven\ alias}
 +32P+248N_{\rm offers}+96P_{\max{\rm cell}}
 +1024G(1+C).
\]

여기서 Rmax는 supplied와 input retained byte estimate의 최대, C_proven alias는 원본/committed의 pointer-identical immutable payload에 대한 단 한 번의 공제다. C는 class count이고 G는 cell/group count다. 위 식은 allocator/RSS 정리가 아니다. [ROAD 2842–2945]

source transfer/remainder phase에는 이후 cell-combine 전용 96Pmaxcell을 빼고 실제 raw+packed remainder를 따로 청구한다. interval phase에는 full B가 복귀한다.

\[
{\cal B}_{p}
=B_{{\rm phase},p}
 +C_{\rm old\ events}+C_{{\rm candidate\ events},p}
 +C_{{\rm raw\ incoming},p}
 +R_{{\rm interval},p}
 +X_{{\rm interval},p}
 +X_{{\rm extra},p}.
\]

incoming raw charge는 56·128·live_pages + frozen descriptor bytes + 8G+128이다. source endpoint index는

\[
C_{\rm index}(n,n_0)
=32(n-n_0)+24n_0
 +8\left(\lceil n/64\rceil+\lceil n/4096\rceil\right)+256
\]

이다. unique edge array는 이후 별도의 8U bytes이며 index preflight 때는 아직 할당하지 않는다. [ROAD 2143–2169, 1766–1776, 3200–3211]

### S07 실패의 정수 분해

| 항 | bytes |
|---|---:|
| full road base | 2,602,210,912 |
| input/current old events + candidate event bound | 1,485,159,656 |
| 아직 살아 있는 raw incoming/marks/pages/descriptors | 950,538,768 |
| 이미 retained한 새 interval rows | 0 |
| 현재 interval transient | 0 |
| 이번 index allocation preflight | 13,723,920 |
| 합계 | **5,051,633,256** |
| 현재 road phase allowance | **5,025,214,575** |
| 초과 | **26,418,681** |

모든 항의 합은 S07 원본 guard 값과 정수로 일치한다. source data를 첫 interval에서 충분히 해제하지 못해서라는 단일 가설도 부정확하다. 첫 cell raw/marks는 실제 drop된 상태지만 나머지 cell들의 raw incoming과 old event histories가 계속 살아 있다.

직전 transfer-candidate 최대와 첫 indexed preflight 사이에는 다음 정확한 차이가 있다.

\[
4\,932\,439\,512
+135\,413\,952
-29\,944\,128
+13\,723\,920
=5\,051\,633\,256.
\]

두 번째 항은 full cell-combine scratch의 복귀, 세 번째는 incoming charge 감소, 마지막은 index buffer다. index 항만 없애면 5,037,909,336 B로 여전히 12,694,761 B 초과한다. 이 guard만 국소 개선하는 접근의 충분성을 검토할 때 즉시 사용할 수 있는 판별식이다.

## 이전 event trace의 수동 관측자 분해: 소스 조건 확인

### 정확히 분리해야 하는 두 event 개념

원본 whole-native 성공 tick을 물리 상태 X와 이미 종료된 이전 event trace O로 쓰면, source가 보장하는 의존성은

\[
X_{n+1}=F(X_n,u_n),\qquad
E_n=G(X_n,u_n),\qquad
O_{n+1}=E_n
\]

형태다. F 안에는 **새 E_n의 sink projection** \(\pi_{\rm sink}(E_n)=(tag,mass,end)\)로 수행하는 service/journey finish를 포함한다. 따라서 “events를 읽지 않는다”는 명제는 틀리며, **이미 이전 tick에서 소비되고 저장된 O_n이 다음 물리 갱신 값에는 재투입되지 않는다**는 범위가 정확하다.

현재 last_events의 전체 production read/write sites는 다음과 같다.

| 파일/행 | 역할 | 다음 물리 수치에 old event payload를 투입하는가 |
|---|---|---|
| JOURNEY 429, 119–120 | capacity bytes | 수치식에는 아님; resource admission에는 영향 |
| JOURNEY 471–476 | ServiceCheckpoint Arc clone / rollback | 원형 보존; 다음 service prepare의 입력은 state.0 |
| JOURNEY 513–523 | checkpoint wire writer | 외부 저장 |
| JOURNEY 576–602 | decoder의 flat EventRow allocation/validation | 복원/검증 |
| JOURNEY 718–719 | road_events() getter가 전체 Vec clone 반환 | 명시적 외부 조회 |
| JOURNEY 1434–1441, 1448–1451 | call_input_events Arc와 그 크기/alias | lifetime/accounting |
| JOURNEY 1486–1499, 1526–1532 | current event bytes와 input/current alias | lifetime/accounting |
| JOURNEY 1586–1589, 1641–1644, 1702–1704 | phase/commit charge | admission |
| JOURNEY 1748 | 새로운 events Arc로 교체 | O_{n+1} 기록 |
| ENGINE 1071, 1227, 1806 | max retained event storage | admission/decode |
| ENGINE 1127–1135 | event tag/index/time/mass binding 검사 | validation |
| ENGINE 1564 | service_last_events count | debug observation |

NativeServiceCore.prepare(731–788)는 self.state와 정적 buses/people/freight/cars를 읽는다. finish(790–844)는 인자로 들어온 현재 sink list를 읽는다. 현재 tick 새 events는 1614–1621에서 sinks로 투영되고 1626/1655–1657을 통해 물리에 사용된다. 이들 경로에 prior last_events payload 재독해는 없다.

같은 이름의 tuple field를 혼동하면 안 된다. Service는 다섯 개 dense physical vectors이고 ServiceCheckpoint는 (Service, Arc<Vec<EventRow>>)다. ENGINE 1681–1683의 service.1은 passenger vector이며 O가 아니다. JOURNEY 875의 s.6[parent]도 ReceiptHistory라는 **물리적 완료시간 history**다. 그 history는 time+dwell≤now 판정에 사용되므로 수동 관측자에 넣으면 안 된다.

### lossless codec 명제의 정확한 범위

O의 encoding Enc와 ordered, bit-preserving decoder Dec가 \(\operatorname{Dec}(\operatorname{Enc}(O))=O\)를 만족하고 다음 조건을 갖는다고 하자.

1. 현재 tick의 sink projection과 물리 연산 순서를 원본과 같게 실행한다.
2. trace를 외부에서 읽을 때 같은 event 순서와 모든 bits를 decode한다.
3. checkpoint writer의 length/fields/optional-destination encoding을 그대로 출력한다.
4. restore/validation도 decoded semantics를 유지한다.

그러면 양 구현이 성공하는 공통 입력 구간에서 X_n이 같다는 것은 위 의존성의 귀납으로 얻어진다. checkpoint stream도 writer가 동일한 ordered EventRows를 받으므로 같다. 이 명제는 현재 소스에서 확인한 조건부 representation-equivalence 결과이며 generic 새 알고리즘 발명으로 주장하지 않는다.

admission과 validation은 O에 의존한다. 따라서 실제 실행 함수 전체가 O와 무관하다고 할 수 없으며, 같은 실패 시점까지 보존하는 정리도 아니다. 압축으로 불필요한 allocation이 사라져 실패하던 run이 진행되는 것은 이 분해의 목적과 양립한다. 새 구현의 actual capacity accounting·decoder·외부 API 부담은 아직 구현되지 않았고 검증되지 않았다.

### 크기와 alias 경계

원본 last_events EventRow는 64 B다. retained charge는 capacity가 양수이면 \(64\,cap+128\)이다. 현재 입력의 old trace는 14,432,257-row capacity, payload 923,664,448 B, structural charge 923,664,576 B이다. S08의 해당 최대 event rows와 flat_rows도 14,432,257다. [S07 engine_admission; S08 road_actual/road_post; JOURNEY 60–71]

그 event 내용의 기존 timed-page payload는 464,781,312 B였다. 따라서 동일 carrier를 **persistent하게 유지하는 가정**에서 payload 차이는 458,883,136 B다. 이것은 현 codec을 저장 경계로 옮길 때의 산술적인 가능량이며 실제 persistent implementation 결과가 아니다. descriptors, current/input alias, restore, API expansion과 향후 K/E 분포를 추가해야 총 peak를 판단할 수 있다.

입력 snapshot과 첫 current service는 같은 Arc backing을 공유한다. call_input_events는 call 끝까지 살아 있다. 첫 commit에서 current가 새 Arc로 교체되면 다음 tick에는 call-input trace와 current trace가 서로 다르며, 동일 내용인지 여부와 무관하게 두 allocation을 세어야 한다. 따라서 “모든 옛 events를 언제나 한 번만 청구”하는 공제는 부당하다.

현 경로는 ROAD 597–608에서 전체 flat 64E array를 먼저 확보한 뒤 timed pages에서 decode한다. ROAD 2950–2982는 road input/current/candidate, old events, page payload/descriptors 및 flat events의 동시 생존을 guard한다. pages가 사라진 다음 continuous keyset interning이 시작된다. capture는 Arc clone이지만 explicit road_events getter와 decoder는 flat payload를 생성한다. 이 네 경계는 서로 다른 비용이다.

원본 event wire 길이는 sink row 수 Z에 대해

\[
8+64E-8Z\quad{\rm bytes}
\]

다. length prefix가 8 B, nonsink의 destination value가 8 B 추가되는 형태다. 순차 decoder에서 원본 writer를 호출하면 전체 flat Vec 없이 동일 wire를 쓰는 것 자체에는 논리적 장애가 없다. 다만 실제 legacy reader가 현재 flat buffer를 요구하는 문제와 외부 getter가 Vec를 반환하는 비용은 별도로 남는다.

## R7. 기존 기록으로 실행한 판별 계산

### 보존된 성장과 이전 개선의 범위

Nov17 A17의 값은 guard 우회 진단 build의 50 s 구간 평균이다. 현재 source의 마지막 snapshot count와 섞지 않는다.

| 구간 끝 s | 평균 cell parts | 평균 packets | partial serves | 해당 50 s wall |
|---:|---:|---:|---:|---:|
| 25,450 | 1,110,040 | 21,237 | 903 | 5.0602 s |
| 25,500 | 1,908,971 | 37,509 | 2,524 | 9.2468 s |
| 25,550 | 3,201,001 | 63,648 | 7,370 | 13.5641 s |
| 25,600 | 5,633,624 | 111,392 | 17,097 | 25.6657 s |
| 25,650 | 10,979,295 | 209,890 | 44,852 | 91.3341 s |

25,600→25,650 구간에서 partial rows 7,209,432, entry split의 추가 rows 2,066,347, offers 768,376, entry combine 감소 587,901, sinks 462,551을 각각 기록했다. 이들은 서로 다른 source lifecycle 계수라 단순히 모두 더해서 snapshot P 증가를 정의하지 않는다. 옛 문서의 “partial service가 주도한다”는 진단은 재사용하지만, 이 local 증가율을 24 h까지 연장한 보편적 불가능성 결론은 재사용하지 않는다.

- Nov19 interval sweep은 25,300→25,600 s의 완전 checkpoint를 byte-identical하게 만들며 관측 wall을 63.95→58.70 s로 줄였다. 반면 해당 두 prefix checkpoint는 83,139,202→866,763,962 B, 10.4255배였고 event index scratch로 RSS가 증가했다. 선택 연산의 개선이 retained genealogy를 제거하지는 않았다. [SW19]
- Nov20 stream/Arc는 같은 25,600 checkpoint를 유지했고 allocation copy를 줄였지만 원본 25,600→25,650 요청은 packet interval packing 5,242,811,264 > 5,242,806,391 B에서 막혔다. 실패 영수증이 정확한 중간 물리 종료 시각을 기록하지 않았으므로 이를 임의의 “25,650 tick 실패”로 더 세밀화하지 않는다. [ST20]
- 이어진 unique-accounting 실험의 25,650 상태에는 310,031 packets/16,528,850 parts가 있었다. 25,700을 향한 시도는 transfer candidates 5,264,847,112 > 5,264,781,391 B에서 막혔으며 최종 25,700 state는 생성하지 못했다. alias correction은 row genealogy를 없애지 않았다. [UA20; 관련 Nov20 문서]
- Nov21 keyset census에서 25,680의 472,127 independently backed Uniform packets는 47,771 ordered keysets만 가졌고 repeated key rows는 23,927,302/25,644,407였다. 정확한 key identity 공유와 packet별 mass/birth 보존이 서로 다른 축임을 실제로 보여 준다. [KEY21]
- event pages, persistent keysets, phase lifetime 개선은 차례로 실제 이전의 postroad/transfer/checkpointability 경계를 통과시켰다. 예를 들어 PL21은 6,040,190,408 B로 과다 합산했던 candidate+future decode를 exclusive phases로 분리하여 5,534,961,208 B로 계산했고 실제 25,700 state를 만들었다. 이것은 source lifetime의 특정 수정이지 모든 병목 해결이 아니다. [EP21, PL21]
- Nov23 현재 source는 연속 0→25,700을 검증했고 S07에서는 transfer를 통과한 뒤 첫 indexed preflight에서 막혔다. 다음 state가 아직 없으므로 이후 flatten/keyset/service/journey/checkpoint 경계가 충분한지는 현재 미측정이다. [S07, S08]

현재 S08 마지막 세 구간의 실제 segment wall은 25,200→25,400: 4.2278 s, 25,400→25,600: 40.5462 s, 25,600→25,700: 130.4662 s다. 마지막 10 s tick의 관측 wall은 24.3468 s다. 시간축 25,700/86,400나 이 국소 증가율을 전체 day workload나 wall 예측에 쓰지 않는다.

### 물리적 복잡성과 표현 곱집합을 가르는 진단

**진단 A — clock와 label incidence 분리.** source별 \(k_h\), serve 수 \(s_h\), E, K, destination별 D_j/U_j, A_j/O_j, 고유 (tag,offset) support와 source-root 수를 동시에 센다. E만 증가했는지, 진짜 FIFO boundary 변화 U와 head-changing composition 수가 같이 증가했는지 구분한다. 기존 S07의 E/K≈84.20 및 첫 cell nonpoint rows/D≈127.27은 동일 clock을 행마다 반복해 물질화한 축의 존재를 이미 판별한다. 이것만으로 rank/span이나 모든 행 집계를 정당화하지는 않는다.

**진단 B — 같은 source가 만드는 행렬의 rank와 소비 통계.** 고정 source h의 tag-by-serve 질량 행렬을 \(M_{\tau s}=m_{\tau}f_s\)로 놓으면 실수 산술에서 rank≤1이다. 물리 head 변화와 다른 source들의 섞임은 별도 factors를 추가한다. 진단은 “서로 같은 완성 row를 병합할 수 있는가?”가 아니라 “같은 source measure와 다른 time/serve coefficients의 tensor product를 저장·조회하는가?”를 묻는다. 현재 binary64의 각 곱·remainder 반올림을 그대로 복원하려면 unary operation sequence 또는 별도 numerical equivalence 조건이 필요하다. dense matrix를 새로 만드는 실험은 이번에 하지 않았다.

**진단 C — 오래된 trace의 수동성.** 현재 whole-native의 prior O에 대한 read-site 전수 검색은 physical feedback과 passive record를 분리한다. trace codec은 정확한 physical X를 건드리지 않고 저장 비용을 줄일 독립 경로다. 반면 journey completion history는 미래 eligibility에 들어가므로 동일 분류에 넣지 않는다. 위 exact read-site 목록이 이 진단의 현재 산출물이다.

**진단 D — 한 guard의 충분성 수치.** S07 index 항 완전 제거 가정 후에도 구조식이 allowance보다 12,694,761 B 큰지 직접 대입했다. 이 검사는 “index만 고치면 다음 tick이 완료될 것”이라는 특정 가설을 반박한다. 다른 exact representations나 전체 물리 모델에 대한 no-go는 산출하지 않는다.

이 네 진단은 해결책의 우열을 미리 고르지 않는다. 어떤 축을 바꾸면 다음 소비자가 같은 정보를 다시 전개해 비용을 복구시키는지 판별하는 데 사용한다.

## 완료된 범위와 정확히 남은 의존성

**source-inspected:** 현재 production data structures, 정확한 serve/interval consumer, service/journey 소비 인자, snapshot/trace alias와 serialization 경계. 관련 파일 blob이 실제 S07 source commit과 일치함을 확인했다.

**derived / numerically checked:** source의 정수 guard 식과 S07 합계, point/nonpoint 역산, carrier payload, old-event 크기, 기존 head JSON 합계, 실제 기록의 국소 비율. 새로운 물리 trajectory나 clock perturbation을 실행한 증거는 없다.

**historical execution evidence reused:** S07의 추가 0 s 실패, S08의 0→25,700 byte identity, Nov19–21의 source-bound 실제 성공/실패. 과거 benchmark의 속도비를 현재 통합코어 성능비로 재명명하지 않는다.

**unresolved:** 미래 coupled-city head/receiving/routing/eligibility feedback에서 각 제안 representation의 충분성; 실제 전체 T_live, U_j, A_j, 이후 retained candidate와 postroad peak; adaptive head changes를 포함한 장기 성장 법칙; full-day resource feasibility. fixed-source sharing이나 fixed-service error bound가 이들을 해결했다고 주장하지 않는다.

선택한 원래 연구 목표는 유지된다. 수치적으로 의미 있는 route/class/birth/FIFO 및 completion-time 관측을 보존하면서, 각 소비자가 실제로 필요로 하는 정보와 그 정보를 담은 중간 물질화 횟수를 분리하는 것이 이번 해부의 결과다. V03 상태는 여전히 BLOCKED, 원래 완전한 24 h는 0/9다.

## 읽기·계산 재현 경로

원격 장치는 cosmosapjw, device edd1b263-56a0-4391-8a2a-677dd00eabf5, repo는 /home/cosmosapjw/urban_traffic_v03_causal_rank_20261123이다. 모든 원격 작업은 Remote Desktop Commander의 읽기 전용 start_process 호출로 수행했다.

실제로 사용한 명령 계열:

- git rev-parse HEAD; git status --short
- rg --files 및 rg -n으로 AGENTS/PLAN, 실제 Rust consumers, 해당 날짜의 진단 문서/영수증 탐색
- Python pathlib.read_text/read_bytes와 json.loads로 선택한 기존 JSON 읽기
- git rev-parse HEAD:path 및 git rev-parse 03b76ccf2ef6bc087d38681c78716e749cce3943:path로 blob equality 확인
- git log -1 --format=%H -- path와 hashlib.sha256(file_bytes)로 provenance 고정
- git show 0492364:docs/PRD.md, git show 0492364:specs/001-metroflow/spec.md, git show 6524500:memory/constitution.md의 관련 문장 대조
- 기존 head rows에 math.fsum을 적용하고 distinct tag/offset/time-pair set의 길이 계산
- S07 counters에서 위 비용식을 정수 대입. 결과는 동반 JSON의 derived_checks에 보존

파일 생성은 지정된 scratch 산출물 두 개뿐이다. 원격 production 파일·checkpoint·git 상태에는 본 작업의 mutation이 없다. 시작 시 이미 존재하던 untracked native_binding/와 S08_time_zero_prefix.final.bin.gz는 건드리지 않았다.

### 역사적 원문 identity

- H0: 049236458fdb5a7e327b0e494ab5f5cc3ad25b61:docs/PRD.md, blob f8cc371410ca0e24b0947cda3d6772787efddc7a.
- H1: 같은 commit의 specs/001-metroflow/spec.md, blob 626b78acad7cafe1f3eadb8166bffb98550e0172.
- H2: 65245008af2387a8ce56e72d54a198394de3eee2:memory/constitution.md, blob 7c78e214c9558bcb1023854e55025f1c554aadee.

