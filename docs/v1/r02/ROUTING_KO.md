# R02 공유 경로와 유한정보 재탐색

## 계약과 경계

입력은 T03의 directed lane-group/허용 turn graph, R01 DecisionObservation,
차종·목적별 Preference, origin 또는 link_exit DecisionBoundary다.
RoutingModel.from_lanegroups는 실제 Group.physics.length_m를 사용한다.
비용 입력에 현재 물리 상태나 미래 사고 일정은 없다. 같은 허용 정보와 동일 위치·선호는
같은 경로 확률을 만든다. 관측 시각·origin/en_route 표면을 결정 경계와 맞추고
미전달·미래 비용, 다른 차종, 중복·누락 링크 비용을 거절한다.

R01 자동 adapter의 완료 route 평균은 링크 비용으로 분해하지 않는다.
링크별 완료 계측 또는 명시한 링크 prior를 R01에 등록해서 전달해야 한다.
이 노드는 경로 제안과 집계 선택 확률을 반환한다. C01이 이후 실제 수송 흐름에 적용한다.
기존 T04 PacketNetwork나 active_suffix의 물리 solver를 바꾸지 않는다.

RouteCommitment는 전체 link tuple과 현재 점유 position을 소유한다.
link_exit 입력이 이 점유 링크의 head와 일치할 때만 suffix를 제안한다.
새 commitment도 이미 지난 prefix 및 현재 점유 링크와 position을 보존한다.
제안은 점유 링크의 순간 교체, 차량량 이동 또는 도착 처리가 아니다.
실제 출구 통과 이후 position 갱신과 흐름 적용은 runtime 소유다.
같은 origin/destination 노드는 LOCAL_ACTIVITY_REQUIRED이며 0초 완료로 세지 않는다.

## 비용과 후보

링크의 보고된 조건부 시간 c_e[s]와 길이 l_e[m], toll q_e[명시 화폐단위]에서
G_e = w_t c_e + w_l l_e + w_q q_e를 만든다.
w_t는 무차원 양수, w_l은 s/m, w_q는 s/화폐단위다.
선호의 purpose와 vehicle_class도 cache key에 포함한다. 이 비용은 조건부 행동 추정이며
실제 최소 시간·전체분포·system optimum을 뜻하지 않는다.
이미 지난/점유 prefix는 suffix 비용 비교에서 제외한다.

기존 active_suffix.routing.destination_potential의 합법 incoming-link Dijkstra를 재사용한다.
목적지·차종·선호·비용 epoch별 potential은 origin 간 공유한다.
loopless 후보는 그 potential을 lower bound로 사용하는 bounded best-first search로 구한다.
이미 지난 노드를 다시 지나는 suffix와 금지 turn은 제외한다. K는 1~3이다.

기존 candidate_paths는 K=1 동률에서 ID 사전순으로 한 경로만 택했다.
R02는 K번째 비용 경계의 동률까지 확인한다. 동률이 K를 넘으면
BLOCKED_RESOURCE로 반환하고 ID에 의해 경로 집합을 잘라 확률을 주지 않는다.
비용 동률 비교 허용오차는 relative/absolute 1e-12다. 후보의 표현 순서는 ID를 사용할 수
있지만 비용 경계의 집합과 집계 확률은 ID 재명명으로 편향되지 않는다.

경로 중복 보정은 PS_r = Σ_(e in r) (l_e/L_r)/n_e이며,
n_e는 후보 중 링크 e를 쓰는 경로 수다. 집계 확률은
P_r ∝ exp(-G_r/θ) PS_r^β, θ[s]>0, β≥0로 정의한다.
동일 geometry를 중복 후보로 세지 않는다. 예를 들어 동일 비용에서
PS=(.75,.75,1)이면 β=1에서 확률은 (.3,.3,.4)다.
계산은 최소 비용을 빼고 log-sum-exp로 정규화한다. 극단적 비용 차이의
확률 underflow=0은 명시적 부동소수점 근사이며 차량량 삭제가 아니다.

시간은 보고된 링크 평균의 합이고 일반화 비용은 별도 필드다.
조건부 regret은 기존 suffix 비용에서 후보 최저 비용을 뺀 값이며 realized regret이 아니다.
링크별 조건부 모집단이 서로 다르면 이 합은 행동 비용 closure다. 링크 간 상관이나
여정 전체 p95를 재구성하지 않으며 실제 완료 통행시간의 검증을 대신하지 않는다.

## 예산·캐시·실패

graph_budget은 link+turn 입력 크기를, expansion/frontier_budget은 경로 탐색을 제한한다.
역방향 potential은 유한 입력 graph에서 계산하고 OD별 전수 경로는 저장하지 않는다.
cache_budget은 목적지/선호/정보 epoch별 potential 수를 제한한다. 결정적 LRU eviction을
사용한다. cache는 geometry 비용 표만 소유하며 inflight 차량량·cohort를 소유하지 않는다.
캐시 eviction은 이미 반환한 RouteCommitment와 수송 상태를 바꾸지 않는다.
graph/turn/길이/toll/topology version, 차종/목적/선호, 관측 source/version/stamp/age/population
변화는 cache identity에 반영된다. topology 변경은 점유 commitment hot-swap을 허용하지 않는다.

검색 한도를 넘으면 부분 후보에 확률을 부여하지 않고 직전 RoutingState를 반환한다.
합법적이고 비용이 유한한 기존 suffix/baseline이 있으면 fallback으로 유지한다.
없으면 외부 대기다. 현재 점유는 호출자가 보존하며 teleport나 차량량 삭제가 없다.
명시적 wall-clock timeout 대신 재현 가능한 deterministic work budget을 제공한다.

구조적으로 연결되지 않은 합법 graph는 PHYSICAL_UNREACHABLE,
graph 경로는 있지만 현재 belief에서 유한 경로가 없으면 NO_PERCEIVED_PATH다.
비용 합 overflow는 NUMERICAL_ERROR와 입력 checkpoint로 보존하며
물리적 불능으로 재분류하지 않는다. 모델/경계/차종 오류도 입력 checkpoint를 보존한다.
거대한 유한 비용의 potential은 overflow를 분리하기 위해 scale을 적용해 계산한다.

## 검증과 한계

한정 테스트는 합법 turn, closure/reopen/새 간선, preference 단위,
경로 중복, ID 재명명, K 동률 경계, 점유 prefix 유지, origin/exit 경계,
paired remote 사고, 공유 potential/cache invalidation/eviction/pickle 재개,
예산 fallback, 극단 비용과 numerical overflow, 실제 T03/T04 상태 불변성을 검산한다.
정적 Braess 65→80 **분** oracle는 기존 함수를 재사용한다. 이는 고전적 정적
nonatomic 사용자 균형의 검산이며 동적 T04 또는 path-size logit의 정확도 검증은 아니다.
V1 본체는 SI 초를 사용하며 oracle의 분은 격리된 예외다.

전체 CI, 통합·최종 수용, city runtime의 실제 경로 재배분, Braess의 동적 재현,
24h·100k 성능은 이번 노드의 완료 주장이 아니다. 다음 B01과 C01이 이 표면을 소비한다.
