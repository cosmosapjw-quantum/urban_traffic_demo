# T03 차로군·교차로·구조물 장애 계약

이 구현은 기존 PacketNetwork의 경로·순서·출생 모멘트·체류량 장부를 유지하며,
M02 CitySnapshot의 방향/회전 그래프를 명시적 차로군으로 컴파일한다.
새 별도 도시 수송기를 만들지 않는다. T02의 class mass/bulk 입력에 연결할 adapter를
제공하되, 실제 시간 이관과 운동 clock 교체는 T04에서 수행한다. 현재 이동 clock은
기존 p-only baseline이다. 이를 이미 유한응답 전도시 수송이라고 부르지 않는다.

## 차로군과 물리 공간

`LanePartition(id, link_id, lanes, successors)`는 하나의 방향 link에 속한 실제
차로의 부분집합이다. 부분집합별 차로 수 합은 원래 방향 차로 수와 정확히 같아야 한다.
선언하지 않은 link는 하나의 shared pool로 남는다. 여러 부분집합을 선언하면
그 차로들은 독립 queue이며 `successors`는 원래 합법 회전의 부분집합이어야 한다.
주어진 Route는 이 group ID를 직접 선택한다. 막힌 회전의 수요를 다른 차로로
옮기거나 원래 차로 수를 복제하지 않는다. 차로 변경은 이 모형의 범위 밖이다.

차로군의 길이 L, 차로 수 k에 대해 공간 예산은 kL[m]다. 경로 tag마다 물리
VehicleClass를 명시하고 footprint_c=ell_c+standing_gap[m]로 점유공간을 계산한다.
기본 standing_gap=0은 차량 길이만 쓰는 저장 근사다. legacy `Lane.storage`의
차량 수 값은 새 물리 공간 예산을 대체하지 않는다. registry는 복사 후 읽기 전용으로
보관하고 모든 경로의 class와 모든 group의 공간 예산을 요구한다.

기존 인터페이스의 설정 없는 호출은 차량 수 저장량을 그대로 사용한다. class-aware
mode에서는 sum n_c footprint_c <= kL를 검사하며 초과는 IMPLEMENTATION_ERROR다.
자동 수요 축소나 공간 확대를 하지 않는다. T02 adapter는 실제 packet class량을
합산하고 동일 VehicleClass와 전체 lane length를 전달한다. reserved standing gap을
T02의 실제 mean gap에서 다시 빼지 않는다. adapter의 common speed와 latent template은
호출자가 명시하며 아직 수송기 내부의 유한응답 상태를 갱신하지 않는다.

## 합류와 sending/receiving

ready shared head i의 고정 회전비 beta_ij와 송출률 S_i[veh/s], 수신률 R_j[veh/s]에
대해 0<=q_i<=S_i, sum_i beta_ij q_i<=R_j를 만족하는 weighted progressive filling을
재사용한다. priority는 명시된 물리 입력이고 ID는 우선권을 만들지 않는다.
3:1 priority와 충분한 수요, 4veh/s 공급 fixture는 3과 1veh/s를 준다.
이는 max-min 정책이며 전역 throughput 최적화라고 주장하지 않는다.

양의 beta 중 하나의 공급이 0이면 해당 shared head 전체가 막힌다. 같은 시간에
독립 차로의 head는 다른 입력으로 남아 통과할 수 있다. 이는 known serial FIFO와
동시 입장의 exchangeable packet closure를 구별하는 기존 PacketNetwork 원칙이다.

한 step에는 수신 차량량 R_j*dt와 실제 빈 공간을 서로 다른 자원으로 추적한다.
회전별 class 조성에서 metre/veh 계수를 구해 다음 공간 소진 event까지의 시간을
계산한다. 모든 합류와 local source가 이 두 예산을 공유한다. source는 기존과 같이
내부 transfer 예약 뒤에 입장한다. 빈 공간은 OLD occupancy에서 계산하므로 같은
step의 유출 공간을 곧바로 재사용하지 않는다. 그 수치 holding의 개선은 T04 범위다.

## 신호, 장애, 실패

신호는 반개구간 green window이고 경계는 dt와 정렬되어야 한다. conflict는 동일
교차로의 incoming group 쌍으로 선언한다. joint repeat period 전체의 정렬 interval을
검사해 동시 green을 거절한다. 모순은 CONTRACT_ERROR, 검사 event 예산 초과는
BLOCKED_RESOURCE다. phase를 ID 순서로 발명하지 않는다. 주어지지 않은 신호는
항상 green이며, 주어지지 않은 conflict를 공간 기하로 자동 추론하지 않는다.
따라서 이 aggregate 서비스 모형은 일반 교차로 충돌 회피 인증이 아니다.

기존 structure_windows의 failure_group 권위를 재사용해 교량의 양방향과 관련된
모든 partition, 램프의 명시된 방향에 사건을 확장한다. capacity fraction=0 동안
입장과 유출 서비스를 모두 막고 이미 내부에 있는 질량은 그대로 남긴다. reopening
후 같은 committed route로 진행한다. 폐쇄를 차량 삭제로 표현하지 않는다.
내부 이동 clock의 유한 제동 반응은 이 서비스 폐쇄와 구별하며 T04에서 연결한다.

`event_budget`은 교차로당 event 반복 수, `record_budget`은 packet/transfer record의
예산이다. 초과 시 BudgetExceeded에 입력 checkpoint를 붙인다. 자원 중단과 물리적
대기·gridlock을 혼동하지 않는다. 불법 방향/회전, 모순 신호, 공간 초과를 별도 검사한다.

## 관측과 한정 검증

새 ClassLedger는 class별 released/completed와 source wait, exit point-queue 체류,
수치 transfer hold를 따로 보관한다. released=completed+pending+active를 class별로
검사하고 source/transfer 체류 합도 전역 장부와 대조한다. exit queue 체류는 실제
속도장이 0인 전체 시간의 측정이 아니라 이 point-server 모형의 대기량이다.
거리/시간/출생 모멘트와 전역 residence 검사는 기존 기준을 유지한다.

검증은 3:1 합류, shared 폐색과 독립 회전 대조, 적색 경계, 교량 양방향 폐쇄와
inflight 보존, 램프 방향/층/장애, class 길이 저장량, 합류와 source의 공동 공간,
표현 분할, cache identity, event 중단 checkpoint를 포함한다. 예를 들어 승용차 5m와
화물차 12m를 각각 2veh 공급하고 17m 공간을 주면 각각 1veh만 동시에 입장한다.
100m 방향 link의 두 실제 차로를 각각 독립 partition으로 나누는 fixture에서는
막히지 않은 회전 1veh가 완료하지만 shared pool에서는 두 회전 모두 대기한다.

```sh
python -m pytest -q tests/v1/test_nodes.py
python -m metroflow.v1 physics-oracles --suite junctions --out junctions.json
```

전체 CI·PR 병합·최종 수용은 사용자 지시에 따라 모든 DAG 구현 후 별도 심사로 미룬다.
이 노드는 한정 검증된 누적 구현이며 전도시 24h/10만 주민의 실행 결과가 아니다.
