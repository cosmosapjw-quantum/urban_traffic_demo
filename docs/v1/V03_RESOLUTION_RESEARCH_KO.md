# V03 자원·취업·수송 연결 차단 해소 연구

## 대상과 실제 입력

V03은 river weekday seed17, coastal weekend seed41, valley weekday seed7의 실제 지도와 등록 출입구를 사용한다. 원본 `artifacts/v1/map_audit/MATRIX.json`의 index 4/11/12가 입력 권위이며 새 출입구 patch가 별도 도시 identity를 만든다. 기존 2구역 C02 실행과 이 도시 실행은 서로 다른 입력이다. 전체 CI·통합 보류는 유지한다.

원본 JSON을 직접 복원해 블록 재고를 합산한 결과는 다음과 같다.

| 도시 | 주민 persons | jobs opportunities | job_capacity opportunities |
|---|---:|---:|---:|
| polycentric_river seed17 | 100000 | 40000 | 139854 |
| coastal_port seed41 | 100000 | 40000 | 166278 |
| valley_city seed7 | 100000 | 40000 | 75787 |

평일 기본 worker fraction 0.5는 50000명의 취업 의도를 만든다. 따라서 원래 `compile_daily_demand`의 모든 worker를 기존 jobs에 배정한다는 전제는 하천·계곡 입력에서 실패한다. capacity는 미래 상한이고 현재 jobs stock과 다르다. 기존 `GrowthModel.materialize_city`는 housing/resident를 변경하며 jobs를 채우는 함수가 아니다. capacity를 즉시 jobs로 세거나 worker fraction을 0.4로 낮추면 원래 입력 문제를 해결한 것으로 보고할 수 없다.

## 명시적인 공급제약 배정 정책

원래 strict 정책은 유지한다. 별도의 `worker_shortfall="unassigned_home"` 정책에서 requested workers W, 현재 job support J, allocated workers A, unassigned workers U를

A=min(W,J), U=max(W-J,0), W=A+U

로 정의한다. 평일 두 도시에서는 W=50000, A=40000, U=10000이다. U는 집에 남은 미충족 취업 의도이며 완료 trip, 취업자 또는 새 일자리가 아니다. 주민수, worker fraction 및 job stock은 그대로다. 이 정책은 원래 불가능 입력에서 성공한 동일 계산이 아니라, 공급제약을 명시적으로 표현하는 새 배정 모델이다. release 입력에서 정책 이름을 선택하고 영수증에 W/A/U를 기록한다.

origin i의 주민 h_i와 전체 주민 N에 대해 미배정 주민은 U h_i/N이다. 원래 비활동 주민 h_i(1-w-s), 배정 취업자 A h_i/N, 미배정 취업자 U h_i/N, 서비스 배정·미배정·외부 서비스 주민을 합하면 h_i다. 서비스 부족도 기존 `unassigned_service`와 같은 방식으로 보존한다. 미배정 work intent에는 목적과 원래 활동 비율을 남기고 실제 이동 release와 분리한다. U를 미완료 교통 차량으로 생성하면 도착지가 없는 가짜 trip이 되며, U를 완료로 세면 취업 공급 부족을 숨긴다.

이 정책을 적용한 후에도 원본 strict compiler가 동일 입력에 `PHYSICAL_INFEASIBLE`을 반환한 기록은 역사적 근거로 보존한다. 실제 일일 수요 장부는 feasible trip demand, unfulfilled activity intent 및 resident stock을 각각 보고한다.

## 정확한 독립 OD 인수분해

목적 p의 배정 인원 T_p, origin resident h_i, 목적지 opportunity q_j와 support Q_p=Σq_j, mode share s_m에 대해 원래 dense compiler의 cohort 질량은

C_ijpm = T_p (h_i/N) (q_j/Q_p) s_m

이다. origin 벡터, 목적지 벡터, T_p 및 s_m을 저장하면 O(H+J+S) 입력으로 같은 질량을 표현한다. 양의 유한 support와 Σs_m=1에서

Σ_jm C_ijpm=T_p h_i/N, Σ_im C_ijpm=T_p q_j/Q_p, Σ_ij C_ijpm=T_p s_m

이다. 각 원소를 방문하는 순서 또는 유한 chunk 경계는 이 식과 목적·모드·outbound/return profile을 바꾸지 않는다. 대규모 dense 곱을 한꺼번에 메모리에 물질화할 필요가 없다. 동일 블록 origin/destination은 기존 intrazonal law로 처리하며 0초 외부 여정으로 세지 않는다. return leg의 outbound completion 의존성, 최소 dwell, 원래 departure/birth 시각도 유지해야 한다.

작은 feasible 입력에서는 dense compiler와 각 cohort 질량·목적·모드·시간 profile 및 origin/destination marginal을 비교할 수 있다. 공급제약 정책으로 U가 생긴 경우에는 새 W=A+U 장부와 주민 보존을 별도 검증한다. 원래 strict 실패에 dense 동등성 주장을 붙이지 않는다.

희소 OD를 임의로 택해 주변합만 맞추는 방법은 독립 product coupling을 일반적으로 바꾼다. 예를 들어 균등 2×2 OD의 각 원소가 1/4일 때 대각 원소만 1/2로 택하면 같은 주변합을 유지하면서 교차 수요와 교통 경로가 달라진다. 이는 대안 모델 또는 명시적 근사이며 현재 exact 표현의 대체 근거가 아니다.

## 실제 수송 연결과 실행 비용

각 chunk는 실제 도시의 PortalRef, 내부 접근 law와 compiler의 legal-turn graph를 사용한다. 출발 outgoing link에서 도착 incoming link까지의 유향 경로를 찾아야 하며 무향 road contact로 대체하지 않는다. 경로·접근 cache는 city identity, 문, 차종/목적 등 실제 의존성을 키로 삼는다. 원래 birth와 ingress/public/egress 장부를 유지하고 private connector 시간을 중복 가산하지 않는다.

인수분해는 표현 메모리를 줄이지만 모든 OD를 실제 경로로 운송하는 총 계산량을 O(H+J)로 줄인다는 정리가 아니다. 실제 route 열거·관측량·동적 상태는 OD 수에 의존할 수 있다. 전역 receiving/storage를 공유하는 하나의 network state에서 동시에 방출해야 한다. chunk별로 빈 network를 따로 실행하여 결과를 합치면 혼잡 상호작용이 사라진다. 자원 중단 시 아직 방문하지 않은 factor cursor와 이미 요청된 원래 birth profile을 함께 보존해야 한다.

bus 수요를 무한 fleet의 fractional vehicle로 완료 처리해서는 안 된다. 실제 B01 scheduled fleet·승객 대기, freight origin/destination과 미배송량, noncar 및 intrazonal 체류는 해당 소비 계약으로 이어져야 한다. 작고 유한한 경로 실행의 통과는 세 24h 캠페인 전체 완료와 구별한다.

## 연구 루프 추적성과 판정

R1–R3: 원본 V03 수용계약과 기존 demand strict 실패, 재고/용량/의도의 의미를 대조했다. R4–R5: 공급제약 장부와 정확한 OD 인수분해를 선택하고 위 보존식·주변합을 직접 유도했다. R6: 원래 compiler의 `total * home_ratio * dest.mass / support * mode.share`와 각 식을 대조하고 희소 coupling 반례를 구성했다. R7: 실제 동결 JSON 세 개에서 주민·job·capacity 합을 계산했다. R8–R9: strict 입력 실패 보존, 명시 정책 및 계산식/소비 계약을 구현 담당자에게 전달했다. R10: 실행·검증·재개점은 이번 변경의 실제 영수증과 PLAN 상태를 따른다.

독립 검토에서 확인한 수학적 결과는 위 조건 아래의 질량 보존과 OD 식의 정확한 표현 동등성이다. 전체 수송 구현과 로컬 자원 수용은 실제 구현·실행 근거가 필요하다. 새로운 불가능성 정리는 주장하지 않는다. V03 완료율은 로컬 3도시×3회 86400s 실행, 원래 wall/RSS 한도, 수치·장부·checkpoint 대조가 확보될 때 갱신한다.

독립 구현 검토: `factorized_demand.py`의 feasible strict loop 순서·질량·외부 서비스·귀가 profile·화물 연결을 원래 dense compiler와 대조했다. `unassigned_home`의 최종 resident 장부는 원래 worker fraction의 stay-home 질량과 추가 U를 별도로 보존한다. 검증용 aggregate에만 allocated/population을 전달하며 최종 FactorizedSchedule의 requested_workers와 원래 worker_fraction은 유지한다. 이 범위에서 중대한 의미 오류는 발견하지 못했다.

수송 C9 검토에서는 `ReleaseRuntime.check`가 per-leg tuple과 JourneyModel의 전역 released/completed를 서로 묶어 검사해야 함을 지적했다. 구현 담당자가 두 합계의 일치와 unsupported leg의 비방출을 추가했다. 실제 advanced state의 released/completed tuple을 0으로 변조한 독립 실행은 현재 코드에서 `IMPLEMENTATION_ERROR: release and physical road ledgers differ`로 거절됐다. centroid birth와 interval 지연은 명시된 source grid 근사이며 마지막 구간은 다음 경계까지 pending에 남는다. 별도 bus/freight/return 등 미지원 수요가 남은 bounded outbound 실행을 전체 도시 24h 실행으로 승격하지 않는다.
