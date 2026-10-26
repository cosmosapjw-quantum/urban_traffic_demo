# R01 인과적 비용 정보

T04 PacketNetwork 물리는 그대로 두고 immutable InformationState를 독립적으로 갱신한다.
관측→전달→origin/en_route 결정의 표면만 제공하며 경로 선택은 다음 R02다.
legacy active_suffix/causal.py는 PackedModel 재현 기준으로 유지한다. 그 예측 closure를
V1의 실제 완료 통행시간으로 바꾸어 부르거나 두 물리를 섞지 않는다.

## 관측과 단위

CostKey는 link/route, 식별자, 차종을 구별한다. CostObservation은 초 단위 비용,
관측 구간, 완료 이후 stamp, 차량량, 센서 좌표(m), source/version, estimand와
population 식별자를 가진다. 무한 비용은 명시적 불능을 나타내며 NaN은 거절한다.
부분집단 완료 평균을 전체집단 ETA로 표시하지 않는다. 오차 비교는 동일 key,
measure, population에서만 허용한다. 관측 표본에 없는 상관이나 p95는 복원하지 않는다.

completed_route_observations는 T04의 최종 유출 Event를 읽어
Σ[mass*(start+end)/2 - birth_moment]/Σmass를 계산한다. 이미 포함된 source,
queue, signal, transfer 체류시간을 다시 더하지 않는다. since_s 이후에 완전히
끝난 Event만 택하며 호출자는 이 cursor를 다음 polling에 넘긴다. stamp는 읽은
물리 시각이므로 과거 완료 표본을 늦게 polling했다고 조기 전달되지 않는다.
네트워크의 실제 차종 registry와 model.check를 재사용한다.

birth_moment는 원래 여정의 출생이다. 따라서 중간 유출 Event에서 birth를 빼서
링크 이동시간으로 오표기하지 않는다. 링크 비용은 명시적으로 별도 계측한 완료
표본을 CostObservation에 넣어 제공할 수 있다. 현재 adapter는 route만 자동 생성한다.

## 전달 법칙

채널 direct/v2v/server/history 각각 coverage, radius_m, latency_s,
propagation_mps, max_age_s를 요구한다. direct/v2v 반경은 유한해야 하며 서버와
history는 무한 반경을 선언할 수 있다. 모든 채널의 유효 age는 유한하다.

거리 d에서 stamp+latency+d/propagation ≤ now, d ≤ radius,
now-stamp ≤ max_age일 때만 보고서를 이용한다. 최신 전달 stamp를 사용하고
같은 stamp의 서로 다른 채널은 명시한 채널 순서로 선택한다. 같은 channel/key/stamp의
상충 보고서는 오류다. ID 사전순으로 다른 비용을 고르지 않는다.
아직 전달되지 않은 최신 보고서가 이전의 전달된 보고서를 가리지 않는다.
coverage 밖, 아직 미전달, 만료 상태는 모두 선언한 PriorCost로 돌아간다.
정적 prior도 같은 estimand를 명시해야 하며 실제 truth를 조회하는 fallback은 없다.

InformationModel.observe는 오직 저장된 history, 고정 채널 계약, 관측자 위치를 받는다.
origin과 en_route 모두 이 동일 표면을 쓴다. 호출자가 정한 고정 결정 시계를 사용하고
사고 발생으로 refresh를 앞당기는 hook은 제공하지 않는다. V2V는 선언된 통신 측정치의
전달 채널이며 차량 위치 전수추적이나 relay 상관 재구성을 구현하지 않는다.

## 자원·재개와 범위

advance는 단조 시각으로 기존 보고서와 새 보고서를 처리하고 채널 age horizon을
벗어난 것만 결정적으로 제거한다. 중복 전달은 idempotent하다. horizon 안의 시간
표식을 평균내어 예산에 맞추지 않는다. record_budget 초과는 BudgetExceeded와
직전 유효 InformationState를 보존한다. 설정 identity가 다르면 state 재사용을 거절한다.

테스트는 paired worlds, 범위 밖 사고, direct local, server 원격 지연, V2V predecessor,
history 우선순위, 만료, 미완료/미래 관측 거절, 차종/coverage, 예산 checkpoint,
pickle 재개, T04 실현 통행시간과 물리 불변성을 검산한다.
전체 도시 runtime 연결, 경로 최적화, 전체 CI, 통합·최종 수용은 이 노드의 완료 주장이 아니다.
