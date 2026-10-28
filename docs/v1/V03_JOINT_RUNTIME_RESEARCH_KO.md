# V03 공유 수송·귀가·서비스 결합 연구

기준은 `2776faea4eb2c72883c4aadcfdb5898523dbe538`의 exact factorized calendar와 bounded ReleaseRuntime이다. 원본 도시·주민·활동비율·기회량, 24시간 세 사례×3회와 wall/RSS 수용기준은 유지한다. 이번 문서는 `/root/v03_review_joint`의 독립 유도·코드 대조와 실제 경량 실행을 기록한다. 전체 DAG 완료율은 19/21이며 V03의 최종 판정은 실제 영수증을 따른다.

## 공유 수송의 비선형 결합

동일한 입구의 한 tick receiving 공급을 C, 서로 다른 OD의 수요를 d1,d2라 하면 단독 실행 합산은 min(d1,C)+min(d2,C), 공동 실행은 min(d1+d2,C)이다. d1,d2≥C>0이면 각각 2C,C다. 이는 공급 제약의 이 명시적 반례이며 모든 분할법에 대한 불가능성 정리는 아니다. 따라서 페이지는 달력·경로의 컴파일 단위로 사용할 수 있지만 물리적 혼잡을 독립 실행한 뒤 더할 수는 없다.

기존 실제 ReleaseRuntime fixture의 같은 경로에 각 1000veh인 두 OD를 부여하고 1s step으로 t=3s까지 실행했다. 단독 실행의 road occupancy는 0.9veh였다. 독립 두 실행을 더하면 1.8veh, 한 shared runtime의 두 OD 공동 occupancy는 0.9veh이고 pending은 1999.1veh였다. 이 검사는 실제 `scenario_city`, `ReleaseRuntime` 및 T04 경로를 사용했다. 최초 진단에서 Cell의 필드를 mass로 잘못 읽어 AttributeError를 얻었고 occupancy로 고쳐 재실행했다. 해당 실패는 물리 반례가 아니라 검산 스크립트의 필드 접근 오류다.

재현의 핵심 계산은 `tests/v1/test_release_runtime.py`의 fixture로 city,leg를 얻고, leg.amounts를 Amounts(1250,1000), 두 번째 leg.id를 other로 교체한 뒤 각각 `(leg,)`, `(leg,other)` ReleaseRuntime을 advance(initial(),3)하는 것이다. 도로 재고는 `fsum(c.occupancy for c in state.journey.traffic.cells)`로 비교한다.

## 귀가의 조건과 원래 시각

귀가 의도 누적분율을 F(t), 출행 완료분율의 시각별 측도를 dG(u), 최소 체류시간을 D라 하자. 동일 cohort에 대해 누적 귀가 방출 R(t)는

`R(t) ≤ min(F(t), ∫[u+D≤t] dG(u))`

를 만족해야 한다. 요청을 먼저 생성하고 completion receipt와 dwell을 충족한 양만 방출한다. 방출 시각을 늦추더라도 원래 의도 시각의 1차모멘트를 새 방출 시각으로 덮어쓰지 않는다. 방출량이 요청 profile의 누적분율 구간 [a,b]에 해당하면 그 구간의 generalized inverse quantile 적분으로 birth moment를 계산한다. 실제 방출시각 r가 born b보다 늦으면, 접근 보행이 b부터 이미 진행됐다고 취급하지 않도록 effective origin delay=(r−b)+physical_access로 표현할 수 있다. 이때 H=Σmass(r−b)는 명시적 intent holding moment이며 JourneyModel의 origin residence에서 H를 빼 physical origin access를 얻는다. H를 intent_hold로 별도 더하면 whole-journey 체류 장부가 유지된다. 요청이 아직 방출되지 않은 양은 별도 pending 장부에 남는다.

## 서비스와 한 번의 도로 진전

B01 ServiceModel.step과 JourneyModel.step은 각각 PacketNetwork.advance_interval을 호출한다. 같은 network 객체를 보유했다는 사실만으로 두 상태가 하나의 물리 세계를 이루지는 않는다. 둘을 순차 step하면 한 global tick에 도로가 두 번 진행할 수 있다. 결합은 서비스의 준비/출발 offer 생성, 전체 자동차·버스·화물의 한 물리 advance, 공통 event의 서비스/여정별 소비 순서를 사용해야 한다. 승객 persons와 고정 fleet vehicles 및 화물 kg는 별도 장부다. calendar의 bus-equivalent vehicles를 곧바로 고정 fleet로 재명명할 수 없다. 이 인터페이스 의무를 구현 담당자에게 전달했다.

## 정확한 달력과 유한 활성 상태

FactorizedSchedule은 독립 비례 OD의 주변합을 저장하여 달력 저장량을 O(H+J+S)로 줄인다. 전체 OD 순회 및 동시 활성 물리 상태까지 같은 차수로 줄었다는 결론은 나오지 않는다. ReleasePlan의 source-tree LRU와 access-law LRU는 eviction 시 동일 정적 입력을 재계산하며 수요를 삭제하지 않는다. 법적 turn을 link-state 간선으로 구성하므로 단순 node 접촉을 임의 turn으로 추가하지 않는다. 풀린 경로 페이지는 같은 live runtime으로 전달되어야 하며 active-route/record 한도를 넘으면 마지막 유효 checkpoint와 달력 cursor를 남겨 자원 실패로 처리한다.

서로 다른 블록의 문이 같은 지상 node에 놓이면 public path가 빈 경로일 수 있다. 이 경우 유효한 access+egress-only 여정 또는 명시적인 미지원 pending 처리를 선택해야 한다. 길이가 양수인 임의 road cycle을 삽입하면 모델이 바뀐다.

## 단계와 독립 검토

R1–R3/C1–C2는 고정 입력과 기존 수송 호출을 실제로 읽고 source/의미 의존성을 확인했다. R4–R5/C3–C5는 위 공유 공급 반례, 귀가 gate, intent holding 분해, 서비스 한 번의 도로 advance 구조를 직접 구성하고 구현자와 연결했다. R6–R7/C6–C8은 실제 0.9 대 1.8veh 판별 실행과 코드 대조를 수행했다. R8–R10/C9–C10에서는 발견한 아래 지적의 수정과 실행 결과를 기존 PLAN/영수증에 연결한다. 이 문서의 유도와 제한된 검산을 전체 도시 24h 실행으로 확대하지 않는다.

독립 검토 지적:

- ReleasePlan cursor가 총 calendar amount보다 큰 materialized amount를 허용하면 음의 remaining ledger가 된다. offset0의 양의 materialized amount 및 끝 offset의 불일치도 거절해야 한다. 구현자에게 총계·경계 검증과 복원 cursor의 정확한 prefix 검증 의무를 전달했다.
- Return의 원래 birth가 eligibility보다 빠를 때 origin access를 이미 소비한 것으로 취급할 위험이 있다. 위 intent_hold 분해와 quantile-band first moment 계산을 제안했다.
- 같은 network 객체로 ServiceModel/JourneyModel을 각각 step하는 방식의 double advance 위험을 버스·수송 구현자에게 전달했다.

새로운 strong no-go 주장은 채택하지 않았다. 로컬 측정 캠페인은 실제 환경과 반환 영수증이 확보될 때 별도 판정한다.

## 현 소스 검토에서 닫은 지적

ReleasePlan은 현재 amount 상한, offset0/끝 offset의 총계 일치, 중간 offset의 원래 calendar prefix 재생성 대조를 적용한다. 이 cursor 검증은 달력 prefix의 의미를 검사하며 실제 물리 활성화 이력은 runtime checkpoint의 의무다. ReleaseRuntime은 completion receipts와 dwell gate, 오래된 미방출 요청의 quantile-band birth moment, return_intent_hold의 origin residence 분해를 구현했다. intrazonal 자동차·비차량 지연과 같은 문 node를 가진 두 블록의 access+egress 합성도 처리한다. 이 변경들을 독립적으로 한 번 대조했고 추가 중대 오류는 발견하지 못했다.

실제 독립 검증 명령은 두 supported Python에서 `-m pytest -q tests/v1/test_release_runtime.py tests/v1/test_release_plan.py tests/v1/test_release_services.py`다. 각각 14개가 통과했으며 Python3.12는 1.08s, Python3.13은 1.41s였다. 이는 그 시점의 세 모듈 검증이며, 이후 서비스 pending 정량화 또는 joint wrapper 변경이 있으면 해당 변경의 별도 결과를 영수증에서 확인한다.

서비스 계획의 미배정 장부에서는 추가로 `(id,reason)`만 보존하고 원래 amounts/profile을 잃으면 미지원 요청을 정량적으로 복원할 수 없다는 지적을 전달했다. 요청 legs 또는 explicit pending amounts와 시간분포를 보존하고 requested=assigned+unassigned가 되도록 해야 한다. B01의 road-stop 도착과 승객 전체 여정 egress는 서로 다른 관측이다.

서비스 pending 정량화 지적은 수정됐다. 현재 ReleaseServicePlan은 immutable source_legs를 보존하고 PendingService에 시간 window·fraction·Amounts를 기록한다. assignment_report는 persons/occupancy-equivalent vehicles/cargo kg 각각 requested=assigned+unassigned를 제공하며 고정 fleet vehicles를 별도 표시한다. 독립 재실행에서 서비스 4개 테스트가 0.62s에 통과했다.

후속 joint consumer는 B01의 binary eligible passenger ID와 분율 eligibility를 구별해야 한다. 출행이 일부만 완료된 시점에 전체 귀가 PassengerCohort ID를 허용하면 현재 대기자 전원이 탑승할 수 있다. 정량적인 eligible amount 제약을 구현하거나, cohort 전원이 완료+dwell을 충족한 때만 해당 ID를 허용하는 보수적 whole-cohort closure를 명시해야 한다.

## Joint wrapper의 실제 검토 지적

신설 JointReleaseRuntime은 ServiceModel.step만 호출하며 ReleaseRuntime helper를 접근법칙·경로 구성에만 사용하므로, 두 물리 step을 순차 수행하는 구조는 피했다. 귀가 버스는 해당 귀가 window의 누적 요청분율 전체가 출행 완료+dwell을 충족했을 때만 ID를 허용하는 보수적 window closure를 적용한다.

독립 소스 검토에서 아래 구체적 지적을 구현자와 root에게 전달했다.

- 자동차·internal 경로와 달리 bus/freight의 calendar released/completed가 실제 ServiceState에 교차 결합되지 않은 부분. bus는 `released=Σ(onboard+arrived)×carrier/persons`, `completed+egress=Σarrived×carrier/persons`; freight는 `released=Σreleased_flag×vehicles`, `completed+egress=Σfreight_completed`로 묶어야 한다.
- 서비스 계획의 source TripLeg와 joint calendar의 같은 ID를 가진 TripLeg가 정확히 일치하는지 확인해야 한다. city ID와 leg ID만 같고 amounts/profile이 다르면 metadata와 물리 장부의 대응이 깨진다.
- `birth_carrier_s`가 finite/nonnegative인지만 검사하면 checkpoint의 원래 birth moment를 임의로 바꿀 수 있다. car/internal은 누적 방출 quantile의 정확한 적분, bus는 실제 boarded 양과 window birth metadata, freight는 dispatch flags와 window metadata로 재검산할 수 있다.
- completion receipts는 단순 분율합 외에 각 시각·분율의 유한성, 0≤시각≤현재시각, 양의 분율을 검사해야 한다. NaN 분율을 허용하면 비교식이 거짓이 되어 장부 검사를 우회할 수 있다.

이 항목의 종료 상태는 수정된 소스와 회귀 실행 결과를 확인한 뒤 영수증에 기록한다.

## 실제 세 도시 calendar 검산

`artifacts/v1_v03_joint_20261027/*.plan.json`은 원본 도시/patch/schedule identity와 16-leg 정적 컴파일 cursor를 기록한다. 모든 도시의 resident stock은 100000명이다. 원래 독립 OD 달력의 outward/return/freight 전체 leg 수는 river weekday seed17이 5,093,765개, coastal weekend seed41이 2,449,750개, valley weekday seed7이 918,450개다. 이 수는 차량·주민의 개별 궤적 수가 아니라 목적·모드·OD·시각을 보존하는 달력 leg 레이블 수다. 각 도시에서 정적 페이지 16개만 구성했고 나머지 calendar 양은 remaining ledger에 남겼다. 실제 시뮬레이션 시간은 0이며 이 결과를 24시간 성능으로 외삽하지 않는다.

마지막으로 실제 internal-only joint calendar를 생성했을 때 `ValueError: nonempty unique route tags`를 재현했다. helper의 inert clock route가 ServiceModel 구성으로 전달되지 않아 발생한 구현 오류다. 이 반례와 zero-physical-road-mass 회귀를 구현자에게 전달했고, 이 지적까지 수정한 뒤 이번 bounded C9 검토를 종료한다. 추가 검토를 재귀적으로 늘리지 않는다. 남은 노드 완료 의무는 실제 전체 수송과 지정 로컬 캠페인의 실행 증거다.

## Bounded C9 종료

위 joint 지적들은 현 소스에서 수정됐다. source_legs의 정확한 calendar binding, bus/freight의 실제 서비스 단계와 calendar 단계 합계, 원래 birth moment 재계산, finite receipt 시각·분율 검사가 추가됐다. internal-only calendar에는 수요를 주입하지 않는 clock route를 등록하며 실제 road released/completed가 모두 0인 회귀를 추가했다. independent 최종 명령 `python -m pytest -q tests/v1/test_joint_release_runtime.py`는 Python3.12에서 4 passed(0.63s), Python3.13에서 4 passed(1.03s)를 반환했다. 실제 검사에는 car/bus/freight를 함께 실행하는 동안 tick당 ServiceModel.step이 정확히 한 번 호출되는지, 양의 목적지 egress가 아직 완료로 세어지지 않는지, 서비스/원래 시각/receipt 변조가 거절되는지, checkpoint continuation과 inert clock이 포함된다.

이로써 이번에 식별한 구현 지적의 독립 검토는 닫는다. 유한 calendar 집합의 실제 joint 실행 경로가 생겼으며 전체 OD 활성화·고정된 세 24h 사례×3회 계측의 실행 증거는 아직 별도 의무다. 계획의 19/21 완료율을 이 작은 검증만으로 올리지 않는다.
