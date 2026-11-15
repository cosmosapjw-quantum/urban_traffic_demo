# V03 정확한 공유 표현과 준비 비용 연구

작성일: 2026-11-16 (Asia/Seoul). 검토 기준: `b41f807c490dda12e036bcb40d9c13370f04223e`와 이번 작업의 `ReleaseRuntime` 준비 경로. V03 전체 실행은 별도 실제 실행 근거를 요구한다. 완료 수는 **19/21 (90.5%)**로 유지한다.

## 문제와 선택

현재 전체 calendar는 river 5,093,765, coastal 2,449,750, valley 918,450 legs다. FactorizedSchedule의 정적 저장량은 주변 support에 비례하지만, ReleaseDriver는 전체 legs를 준비하고 JointReleaseRuntime은 leg별 장부를 보유한다. 불변 출발 profile 공유는 의미를 유지하는 저장 최적화지만, 전체 eager 활성화와 매 tick 전체 leg 순회 비용을 제거하지 않는다.

이번 변경은 **동일한 정적 입력의 중복 계산을 제거**한다. 원본 runtime의 준비 코드를 읽어 다음 두 원인을 확인했다.

1. 부모 leg 검증은 각 leg마다 전체 ID 집합을 만들고 `next`로 부모를 탐색했다. L개 legs에 대해 ID 집합 생성만 O(L²)였다. 한 번 생성한 ID→index 매핑으로 기존 중복 ID·부모 cohort·amount 검증을 유지하면 O(L)이다.
2. 같은 origin/destination을 가진 목적·출발창별 legs도 `candidate_paths`와 양 끝 `activity_access`를 반복했다. 이들의 입력은 해당 runtime 생성 중 고정된다. 정확한 키를 사용하는 제한된 LRU는 캐시 miss 때 원래 함수를 호출하며 eviction은 재계산만 일으킨다.

행동 RED 측정은 구현 담당자가 얻었다: internal legs 100개에서 ID 읽기 13,000회, 동일 endpoint 자동차 legs 20개에서 경로탐색 20회·접근법칙 구성 40회. 수정 후 결과는 별도 실행 영수증의 실제 수치를 사용한다. 시간 측정 없이 이 연산 횟수를 wall-time 개선율로 바꾸지 않는다.

## 정적 공유의 정확성 조건

순수 함수 f의 모든 의미 입력을 key K가 식별하고, f의 반환값이 불변이면 같은 K에서 f를 재호출하거나 이전 반환값을 공유하는 것은 값 의미가 같다. 현재 runtime 안에서 city, graph, link costs, allowed turns, access depth는 고정된다. 따라서 경로 캐시 키는 이 고정 context에서 `(origin_node, destination_node)`, 접근 캐시 키는 **전체 ActivityMeasure와 등록 gate**를 포함해야 한다. block ID만으로 다른 밀도·활동 support를 합치면 안 된다. 서로 다른 runtime 사이의 캐시에는 city/graph/version도 필요하다.

경로 tuple이나 DelayLaw를 공유해도 leg ID, 목적, 차종, 양, 출발 profile, 부모 관계, 최소 체류시간, released/completed, 완료 영수증은 독립적으로 보존한다. 이 변경은 dynamic cohort 수를 줄이는 물리적 aggregation이 아니다. 캐시 용량을 제한해 추가 저장량을 제어하며, identity·checkpoint와 최종 상태의 값 동등성을 검증한다.

`candidate_paths`와 `LegalRouteCache.resolve`는 현재 동일한 solver가 아니다. 전자는 physical-node loopless 경로와 2,000 expansion 한도를 사용하고 후자는 legal directed-link Dijkstra에서 node 재방문을 허용한다. tie 처리도 대조해야 한다. 이번 캐시는 원래 `candidate_paths`를 보존한다. solver를 교체하려면 이 차이를 명시한 별도 행동 계약과 회귀 근거가 필요하다.

## 동적 합병에 필요한 조건

공유 receiving/storage 때문에 전체 수송 연산 T는 일반적으로 선형이 아니다. 동일 도로를 갖는 독립 실행을 합쳐도 한 공유 도로 실행과 같지 않다. 이 비가산성의 실제 반례는 기존 `V03_JOINT_RUNTIME_RESEARCH_KO.md`에 보존되어 있다.

표현 축약 Q를 정확하다고 부르려면, 허용한 모든 상태와 입력에서 다음 조건을 확인해야 한다.

\[
Q T(s,u)=\widehat T(Qs,Qu),\qquad O(s)=\widehat O(Qs).
\]

첫 식은 한 step과 표현 축약의 교환성, 둘째 식은 요구 관측량 보존이다. 초기 상태에서 성립하고 매 step 귀납이 닫히면 유한 시간 실행에서도 성립한다. 여기서 O에는 차량·사람·화물뿐 아니라 출발 모멘트, leg별 목적·완료·귀가 자격과 checkpoint 재개 관측도 포함한다. route suffix만 같다는 조건으로 두 식은 따라오지 않는다.

현재 PacketNetwork의 `combine`은 동일 clock target에서 tag·remaining suffix·entry interval이 같은 part의 mass와 birth moment만 합친다. JourneyModel의 진입 합병도 tag·born time·delay를 보존한다. 이 정의는 기존 관측 계약에 맞춘 제한된 표현 동치이며 다른 target, 미세 순서, 차종 반응, 목적 또는 미래 법칙을 지우는 허가가 아니다.

특히 동일 도로 suffix를 갖더라도 하차·egress 법칙, 후속 목적지, 서비스 예약, 귀가 부모·체류 조건이 다르면 정적 경로 자료는 공유할 수 있으나 동적 완료 장부를 하나로 합칠 수 없다. 동적 물리 패킷을 공유하려면 필요한 목적별 provenance 벡터나 조건부 측도를 유지하고, 모든 분기에서 해당 성분을 복원할 수 있어야 한다.

## Birth moment의 충분 범위와 반례

질량 \(m_i\ge0\), 원래 출발시각 \(b_i\,[s]\)에 대해

\[
M=\sum_i m_i,\quad B=\sum_i m_i b_i,\quad
I(t)=\sum_i m_i(t-b_i)=Mt-B.
\]

따라서 공통 시각의 누적 age/체류량은 mass와 1차 모멘트로 복원된다. 단위는 각각 veh, veh·s, veh·s이며 사람 carrier에도 같은 식을 적용한다. 그러나 \(\bar b=B/M\)의 단일 atom으로 바꾸면 2차 모멘트 손실은 두 성분에서

\[
\sum_{i=1}^2m_i b_i^2-M\bar b^2
=\frac{m_1m_2}{m_1+m_2}(b_1-b_2)^2\ge0.
\]

임계 자격량 \(E(t)=\sum_i m_i\mathbf1[b_i\le t]\)도 M,B만으로 결정되지 않는다. \(m_1=m_2=1\), \(b_1=0\,s\), \(b_2=10\,s\)에서 \(t=4\,s\)의 원래 자격량은 1이고, 평균시각 5s의 질량 2 atom은 0이다. 완료시각+dwell에 의존하는 귀가 자격에 같은 반례가 적용된다. 따라서 원래 모멘트를 보존했다는 사실만으로 귀가 창, age quantile 또는 FIFO 동등성을 주장할 수 없다.

위 항등식·분산식·임계 반례를 Wolfram Language로 직접 계산했다. 실행 코드와 결과는 `artifacts/v1_v03_scaling_20261116/RESEARCH.json`에 기록한다. 이 계산은 대수 검산이며 simulator 실행 검증은 아니다.

## 문헌 근거와 적용 범위

- Daganzo (1995), *The Cell Transmission Model, Part II: Network Traffic*, Transportation Research B 29(2), 79–93, [저자 소속기관 기록](http://www.its.berkeley.edu/publications/cell-transmission-model-part-ii-network-traffic), DOI `10.1016/0191-2615(94)00022-R`: 시간 의존 OD와 network junction에 대한 multi-commodity 수송을 다룬다. 목적지 경로 정보의 유지가 추가 계산·메모리 비용을 요구한다는 문헌 근거다. 본 코드의 exact aggregation을 증명하는 문헌은 아니다.
- Jin and Jayakrishnan (2005), *First In, First Out Properties of a Commodity-Based Kinematic Wave Simulation Model*, Transportation Research Record 1934(1), 197–207, [저자 소속기관 기록](https://its.uci.edu/research_products/published-journal-article-first-in-first-out-properties-of-a-commodity-based-kinematic-wave-simulation-model), [출판사 원문 기록](https://journals.sagepub.com/doi/10.1177/0361198105193400121), DOI `10.1177/0361198105193400121`: commodity 기반 유한 격자에서 FIFO 위반과 격자 축소에 따른 수렴을 구분한다. commodity 총량 보존 또는 수렴성을 고정 해상도의 정확한 FIFO 동등성과 혼동하지 않아야 한다는 근거다. SciSpace [검색 레코드](https://scispace.com/papers/first-in-first-out-properties-of-a-commodity-based-kinematic-ayma29mytb8v)로 탐색하고, 기관·출판사 abstract를 대조했다.

Exa는 첫 원전을, SciSpace는 관련 commodity/FIFO 논문을, Parallel은 두 번째 원전의 기관·출판사 기록을 찾는 데 사용했다. 기관 페이지의 최신 게시일은 논문 발행일과 구분했다. 본 메모는 확인한 abstract와 코드상의 직접 유도 범위만 채택한다. 외부 논문에서 해당 구현의 성능·정확성 보증을 가져오지 않는다.

## 남은 실질 의무

이번 정적 준비 개선 뒤에도 전체 leg 물질화, tick별 전체 calendar 순회, leg별 완료 영수증과 active record 수는 남는다. 현재 20,000 leg cap과 원래 수요를 유지하며 전체 도시에 대한 RSS/24h 완료를 추정하지 않는다. 이후 구현은 동일 future kernel의 정적 공유, 실제 활성 시간창을 사용하는 event index, 필요한 provenance를 갖는 exact dynamic representation 순서로 검토할 수 있다. 각 선택은 위 교환성·관측 조건을 만족하는 실제 반례/동등성 검사와 수치 해상도 대조를 요구한다. 현재 구조가 일반적으로 불가능하다는 결론은 내리지 않는다.

## 이번 구현의 독립 검토 결과

최종 작업 소스의 `release_runtime.py`, `release_services.py`, `joint_release_runtime.py`, `route_metrics.py`와 CLI 연결을 한 번 독립 검토했다. 수정된 부모 lookup은 중복 ID 검사 뒤 동일한 leg를 선택하며 기존 부모·cohort·amount 검증을 유지한다. 자동차 access 캐시는 전체 불변 ActivityMeasure+PortalRef, 서비스 access 캐시는 고정 도시/door context에서 전체 ActivityMeasure를 키로 사용한다. 캐시 수명은 각 생성·컴파일 호출 안이며 original path solver는 바뀌지 않았다. 상태와 관측을 합치는 변경은 없다.

Joint checkpoint 검사는 stage를 tag별로 모으되 entering→egress→internal 순서와 각 `math.fsum` 입력 순서를 유지한다. 서비스 inverse index도 원래 서비스 순서를 보존하므로 합산 순서와 장부 검증 의미가 같다. 변경으로 인한 구체적인 의미 결함은 발견하지 못했다.

경로 계측은 실제 호출된 최외곽 등록 API를 표본 단위로 하며 내부 중첩 solver는 중복 집계하지 않는다. 준비 경로, 호출된 cache hit, 경로 없음 반환과 예외 요청도 표본에 포함한다. `failed_calls`는 예외로 끝난 호출의 수이며 경로 없음 반환과 다르다. 무호출은 `NOT_MEASURED`와 null 구간이다. p99는 정수 nearest rank `ceil(0.99*N)`가 속한 histogram bucket의 **포괄 구간**이며 exact scalar quantile가 아니다. 64-bit 범위 bin과 overflow 경계, min/max clamp가 해당 순서통계량을 포괄함을 코드와 edge-case 시험에서 대조했다. 반환값·예외·simulation identity와 분리된 계측이다.

독립 실행 명령은 다음과 같다.

```sh
.venv/bin/python -m pytest -q tests/v1/test_route_metrics.py tests/v1/test_release_runtime.py tests/v1/test_release_services.py tests/v1/test_joint_release_runtime.py tests/v1/test_local_campaign_cli.py
.venv313/bin/python -m pytest -q tests/v1/test_route_metrics.py tests/v1/test_release_runtime.py tests/v1/test_release_services.py tests/v1/test_joint_release_runtime.py tests/v1/test_local_campaign_cli.py
```

실제 결과: Python 3.12 **32 passed (2.84s)**, Python 3.13 **32 passed (2.68s)**. cache eviction/full-measure 구분, full state 동등성, 질량합을 보존하는 tag 변조 거절, 여러 서비스 window의 장부, histogram rank와 중첩 호출·예외 복구를 포함한다. 검토한 유한 범위에서 미해결 중대 지적은 없다. 이 결과는 100k 도시 24h 실행이나 release 수용을 대체하지 않는다.
