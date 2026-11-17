# 다음 구성: 시간 cohort와 category 측도를 분리해서 저장하기

2026-11-17. 이 문서는 `entry_projection_support_v1`의 후속 표현 개선을 위한
구체적인 인계다. 현재 구현에 이미 들어간 기능이나 실행 완료 결과로 취급하지 않는다.

## 1. 새 실험이 바꾼 판단

이번 전체 수요 Valley pilot은 `h=1 s`, `dt=10 s`에서 simulation time
26,010 s까지 진행한 뒤 자원 한도로 중단했다. 앞선 정확 경로의 guard 시점
25,650 s보다 360 s 뒤지만 24시간 실행은 해결되지 않았다. 이 차이는 진행한
simulation time의 차이이며 wall-time speedup이나 수렴 성공이라는 뜻은 아니다.
앞선 guard 우회 진단의 약 25,700 s와도 구별한다.

마지막 상태에는 14,103개 packet에 10,530,239개 category part가 있었다.
평균적으로 packet 하나가 약 746.67개 category 행을 가진다. 마지막 projection은
약 5.06 million 입력 part를 약 3.54 million 출력 part, 5,243개 cohort로
줄였고, movement support 보호 경계가 약 2,600개였다. 현재 결과는 시간 구간
분할의 비용과 함께 **category 벡터를 cohort마다 복제하는 비용**이 크다는
진단을 준다. 실제 실행 숫자와 세부 조건의 권위는 이번 통합 실행 영수증이다.

과거 정확 경로에서 조성 공유만으로는 packet 수 증가를 막지 못한다는 판단은
그 표현에 관한 것이었다. 지금은 시간 투영을 적용한 뒤이므로 두 방법의 조합을
다시 판별할 근거가 생겼다. 그렇다고 조성 공유가 전체 실행을 해결한다고
미리 결론내리지 않는다. source 다양성이나 조성의 실질적인 rank가 크면
공유 후에도 비용이 클 수 있다.

## 2. 비교와 선택

| 후보 | 바뀌는 것 | 현재 선택 |
|---|---|---|
| 불변 category block과 scalar coefficient의 공유 | 같은 물리 상태를 저장하는 방법. 실수 산술에서는 선형 연산의 재표현이며 float 연산 순서는 달라질 수 있다. | 가장 작은 후속 구성으로 선택한다. |
| class·목적지 등 관측 모멘트만 저장하는 closure 계층 | tag·경로·출생 mark의 일부 분포와 상관을 근사한다. 귀가·체류 등 tag별 후속 행동과의 연결이 추가로 필요하다. | 공유의 이득을 측정한 뒤 남는 문제로 보존한다. |
| 새 full kinetic/PDE solver | 운동·노드·경계와 실행 경로 대부분이 바뀐다. | 이 병목 해결의 선행조건으로 만들지 않는다. |

시간폭을 단순히 늘리거나 support 보호 경계를 없애거나 양의 질량을 잘라내는
방식으로 현재 결과를 성공으로 바꾸지 않는다. 다음 작업도 같은 `h`, `dt`, 수요,
support 규칙과 물리 관측량으로 비교한다.

## 3. 표현: typed measure의 양의 선형 결합

원래 category key는 적어도 `(tag, route_version, route_offset)`를 포함한다.
다음 행동을 바꾸는 정보·활동 mark가 별도로 versioning되어 있다면 그 identity도
유지한다. label이 같다는 이유로 다른 route suffix나 birth moment를 합치지 않는다.

불변 기초 block \(a\)에 두 개의 sparse 측도를 저장한다.

\[
\nu_a=\sum_k m_{ak}\delta_k,\qquad
\beta_a=\sum_k B_{ak}\delta_k.
\]

\(\nu_a\)의 단위는 veh, \(\beta_a\)의 단위는 veh·s다. \(B_{ak}\)는
원래 여정 출생시간의 질량가중 1차 모멘트다. 정규화로 얻은 float 비율을
hash해서 비례성을 추정하지 않는다. 동일 block에서 출발한 부분서비스의
**생성 계보**를 따라 공유를 보존한다.

cohort \(q\)는 physical target과 시간 순서 외에 다음의 sparse coefficient
표를 가진다.

\[
q=\{(a,v,\lambda_{qav},\eta_{qav})\},\qquad \lambda_{qav}>0.
\]

\(v\)는 기초 block의 route-prefix view이고, \(\lambda\)는 무차원 질량
배율, \(\eta\)는 초 단위 entry-moment coefficient다. view의 restriction과
현재 route-offset 이동을 나타내는 선형 map을 \(T_v\)라 하면 cohort의 측도는

\[
\mu_q^M=\sum_{a,v}\lambda_{qav}T_v\nu_a,
\qquad
\mu_q^B=\sum_{a,v}\lambda_{qav}T_v\beta_a,
\qquad
\mu_q^E=\sum_{a,v}\eta_{qav}T_v\nu_a.
\]

입장시각이 \(\bar t\)인 하나의 component는 \(\eta=\lambda\bar t\)다.
서로 다른 진입시간을 합친 뒤에는 \(\lambda\)와 \(\eta\)를 독립적으로
합산해야 entry 1차 모멘트를 잃지 않는다. category별 입장 평균이 필요하면
\(\mu_q^E(k)/\mu_q^M(k)\)를 계산한다.

부분서비스의 \(\theta\in[0,1]\)에 대해

\[
(\mu_q^M,\mu_q^B,\mu_q^E)
\longmapsto
\theta(\mu_q^M,\mu_q^B,\mu_q^E)
\]

이므로 category 행들을 복제할 필요가 없다. served와 remainder는 같은
불변 block을 참조하면서 coefficient만 가진다. 다른 cohort를 하나로 합치는
규칙을 새로 추가하는 것이 아니라, 이미 선택한 cohort 안의 category 측도를
다르게 저장하는 것이다.

## 4. 연산별 구현 계약

### 부분서비스와 장부

head 서비스에서 scalar coefficient를 분할하고, 질량·birth·entry 측도에 같은
분할을 적용한다. class·destination 질량, 점유공간, birth 합은 block/view의
캐시된 선형 summary에 coefficient를 곱해 계산할 수 있다. summary의 key에는
route offset과 관련 registry identity가 들어가야 한다.

`_rates`의 destination 비율과 저장공간 제약은 재구성된 같은 측도에서 계산한다.
서로 다른 법칙의 class를 평균 이름 하나로 바꾸거나, blocked movement의
양의 support를 지우지 않는다. 이 변경만으로 service rate·물리 law를 바꾸지 않는다.

### 분기, route suffix 이동과 결합

목적지 \(j\)로 나가는 질량은 그 next movement를 갖는 mark에 대한 restriction
\(P_j\)를 적용한다. 다음 link에 입장하면 route offset을 한 칸 이동시킨다.
두 연산을 하나의 typed view로 표현한다. 실제 label별 route를 복사하는 대신
불변 route registry와 prefix view를 참조한다.

이때 \(\mu^B\)에도 **동일한 restriction·route map**을 적용한다. 출생시간을
서비스시각으로 다시 쓰지 않는다. 새 link의 진입시간만 실제 서비스구간 평균
\(\bar t_{\rm service}\)에 맞춰
\(\eta=\lambda\bar t_{\rm service}\)로 갱신한다. 원래 source availability와
도로 admission 시각은 기존 T04처럼 구분한다.

time projection은 원래 보호 경계와 category 의미를 유지한다. interval clipping
fraction이 \(\gamma\)이면 mass·birth coefficient는 \(\gamma\lambda\),
entry coefficient는 그 clipped interval의 평균시각을 곱해 만든다. 같은
`(block_id, view_id)` component는 cohort 안에서 \(\lambda\), \(\eta\)를 각각
합산할 수 있다. 서로 다른 block들을 숨은 근사로 하나의 저차원 벡터에 맞추지 않는다.

### Event와 downstream consumer

road packet만 공유하고 매 부분서비스마다 모든 tag를 `Event`로 즉시 펼치면
같은 폭증이 event buffer로 이동할 수 있다. 최소 이식 범위에는 공통
`source/destination/start/end`와 typed mark block을 갖는 **event block**도 포함한다.
linear consumer는 block summary를 사용한다. tag별 완료·귀가·체류 전이가 실제로
필요한 지점에서는 관련 mark만 한 번 순회한다. 그 consumer를 생략하거나 완료
수요를 한 class 합계로 대체해서는 안 된다.

동적 routing이 특정 tag의 suffix를 바꾸면 해당 submeasure를 분리해 새 route
version을 부여한다. 첫 판별 구현은 이미 쓰던 고정 경로 pilot에 한정할 수 있다.
그 결과를 동적 routing 전체에 대한 동등성으로 확대하지 않는다.

## 5. exact의 의미와 부동소수점 정책

위 표현의 동등성은 **실수 산술의 선형 동등성**이다. IEEE-754에서는

\[
\theta(\theta_0m)\ne (\theta\theta_0)m
\]

가 가능하다. remainder를 `(1-theta)*mass`로 만드는 것과 `mass-served`로
만드는 것도 일반적으로 같은 bit를 주지 않는다. 조합·합산 순서가 달라진
mass 차이는 비매끄러운 서비스 경계에서 영향을 줄 수 있다.

따라서 다음 두 선택을 혼동하지 않는다.

- 원래 연산 순서까지 보존하는 expression tree: bit 재현을 목표로 할 수 있지만
  tree 깊이·수명과 실제 평가 비용을 관리해야 한다. 공유만 추가했다고 bit
  identity가 자동으로 성립하지 않는다.
- 새 표현의 연산 순서를 명시한 수치 정책: 실수 산술의 동일 측도를 계산하되
  float 차이는 같은 입력의 기존 A 경로와 검증한다.

후속 인계에서는 두 번째를 선택한다. 제안 정책명은
`entry_projection_support_v1_mark_blocks_v1`이며 **현재 활성화된 이름이 아니다.**
폭 0의 legacy exact 경로는 그대로 두고, `h>0`인 기존 A 정책 위에 선택적으로
올린다. coefficient summation과 served/remainder 생성 규칙을 구현 전에 고정하고
identity에 포함한다. 기존 보존 허용오차나 물리 관측 수용문턱을 통과 목적으로
완화하지 않는다. coefficient·part의 양의 값이 underflow하면 명시적으로 실패한다.

## 6. 표현 깊이와 retained memory의 상한

단순한 lazy `Add(Scale(Add(...)))` tree만 도입하면 깊이와 살아 있는 과거
노드가 계속 늘 수 있다. 현재 구성에서는 cohort마다 `(block_id, view_id)`로
정렬한 **평평한 coefficient 표**를 사용하고, 같은 key의 coefficient를 합친다.
Add/Scale expression을 step마다 새 depth로 누적하지 않는다. coefficient term
수에는 실제 budget을 두며, 작은 coefficient를 잘라서 맞추지 않는다.

고정되고 유한한 route를 갖는 기초 source mark 수를 \(Q\), 각 route 길이를
\(L_i\le D\)라고 하자. source block별 immutable route-prefix trie를 사용하면
source mark 하나가 방문하는 prefix 수는 \(L_i+1\) 이하이고, 전체 prefix
membership은

\[
\sum_{i=1}^Q(L_i+1)\le Q(D+1)
\]

이다. 이는 tag와 birth mark를 삭제하지 않는 **고정 경로의 view 계보**에 대한
선형 상한이다. 기초 block마다 arbitrary subset mask를 새로 만들어 이 상한을
깨지 않는다. 경로에 cycle이 있어도 저장된 유한 route의 offset은 단조 증가한다.
새 routing version을 계속 생성하면 그 수가 별도 비용으로 추가된다.

이 상한은 cohort별 coefficient 수까지 \(QD\)로 제한한다는 뜻은 아니다.
여러 cohort가 여러 basis를 섞으면 coefficient 표는 여전히 커질 수 있다.
입력 basis 수, reachable view 수, cohort별 term 수·고유 mark 수의 분포를
실측해서 이 표현이 이번 데이터의 반복 구조를 실제로 이용하는지 판별한다.
낮은 rank를 가정하거나 음의 weight factorization을 도입하지 않는다.

Garbage collection은 live road, source pending, joint/event buffers, runtime
consumer 및 실제 보관 중인 checkpoint에서 도달 가능한 block/view를 기준으로
수행한다. 이전 immutable state나 외부 checkpoint가 아직 참조하는 block은
살아 있는 것으로 계상한다. 기초 payload, view metadata, coefficient 표,
캐시, event block 및 임시 조립 buffer의 retained capacity를 모두 센다.

측정치는 `logical_expanded_part_count`와 실제 retained allocation을 구분한다.
예산을 실제로 바꾸지 않은 채 표현이 줄인 bytes를 측정해야 한다. 새 counter가
작아졌다는 이유만으로 메모리 개선을 주장하지 않는다.

## 7. checkpoint에서 다시 펼치지 않기

메모리에서 공유한 상태를 기존 JSON의 `packets[].parts[]`로 펼치면 checkpoint
생성 자체가 다시 O(cohort × category) 메모리를 요구할 수 있다. 새 wire 형식은
불변 block pool, route/view table, cohort coefficient 표와 ledger를 각각 한 번
기록하고 ID로 연결해야 한다. Python frontend와 Rust decoder 모두 같은
version을 이해해야 한다.

복원 시 없는 ID·순환 참조·잘못된 route offset·잘못된 정책 identity를 거절하고,
모든 참조와 장부를 확인한 뒤 새 상태를 노출한다. 이전 wire format의 무조건
자동 변환이나 실패 후 부분복원을 하지 않는다. checkpoint 직렬화의 임시
peak RSS와 최종 파일 크기도 판별 항목이다. compatibility export가 필요하면
명시적 진단용 bounded export로 두고 full checkpoint의 기본 경로로 삼지 않는다.

## 8. 로컬 에이전트가 수행할 최소 후속 단위

1. 같은 Valley `h=1`, `dt=10` 입력·기준 commit·수요 identity와 마지막 유효
   checkpoint를 고정한다. 지원되지 않는 기존 checkpoint에 새 정책을 끼우지 않는다.
2. 현재 native `Part` 생성 위치에서 partial service, fan-out, incoming projection,
   event 소비 경로를 추적한다. 기존 공유가 어디에서 flat vector로 다시 펼쳐지는지
   정확히 찾고, 원래 계산식과 사용 중인 birth/route mark를 인계에 기록한다.
3. scoped `MarkBlock`, route-prefix view, flat positive coefficient table,
   block event와 pool checkpoint의 한 vertical slice를 구현한다. 첫 범위는
   동일 fixed-route pilot이다. 시간 support 보호 정책과 수요는 그대로 둔다.
4. 원래 A 경로와 같은 입력에서 category별 mass·birth·entry moment, head
   movement support, class footprint, 서비스율·완료곡선을 비교한다. split→partial
   service→diverge→reconverge→resume가 포함되어야 한다. tiny positive category와
   서로 다른 birth marks를 포함하고 0-width legacy 경로는 독립 회귀한다.
5. 재실행 가능한 짧은 frozen workload에서 peak RSS/retained bytes, basis/view/
   coefficient 수와 event/checkpoint 크기를 측정한다. 그 뒤 동일 예산의 Valley
   morning window를 비교한다. 먼저 전체 3×3 전일 캠페인을 다시 시작하지 않는다.
6. 실제 표현 이득이 없으면 source 다양성·coefficient 밀도·event 소비·checkpoint
   중 원인을 특정하고 그 결과에서 멈춘다. support 경계·tag·질량을 삭제해서 성공으로
   바꾸지 않는다. 이득과 물리 대조가 확인되면 원래 V03 캠페인으로 이어간다.

반환물은 수정 commit, 정책과 wire version, 원래 입력 identity, 정확한 실행 명령,
종료 상태, 수치 비교, 자원 측정, checkpoint roundtrip 결과다. 현재 A 구현과
이번 문서는 그 후속 단위를 실행할 근거를 제공한다. mark-block 이식과 전체
도시 수용은 이 문서를 작성한 시점에 아직 수행하지 않았다.
