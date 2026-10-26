# T04 시간구간과 유한응답 수송

선택된 수송 계보는 여전히 PacketNetwork다. `TransportModel`은 이를 구동하는
시간구간 정책이며 별도 도로 solver가 아니다. T03의 공급·공간·회전·신호·class
장부와 T02의 finite-response characteristic을 같은 경로에 연결한다.
기존 옵션 없는 PacketNetwork 호출은 p-only baseline을 유지한다.

## 하나의 운동과 도달시각

Cell은 공통 speed와 class별 latent p를 immutable 상태로 보관한다. 실제 packet
class 질량과 전체 차로 길이를 T02에 전달하고, frozen density/cap 아래의 p-half /
characteristic / p-half 분할로 속도와 이동거리를 함께 계산한다. endpoint 도달시각은
그 step에서 사용한 동일 held characteristic의 최초 root다. ETA도 같은 T02 함수를
사용하지만 현재 관측 환경과 조성을 고정한 **조건부 예측**이며 실제 미래 혼잡을
미리 아는 값이 아니다. link_eta는 node service 대기를 제외한 운동 endpoint ETA다. 현재 폐쇄는 같은 cap=0을
사용하며 미래 재개를 미리 가정하지 않는다. 완료 curve와 평균 관측은 실제 outlet Event에서 계산한다.

수신 경계에서는 기존 질량과 incoming 질량의 speed·latent 1차 모멘트를 합쳐
공통 bulk 상태로 투영한다. 내부 이관은 outlet 시각의 characteristic speed/p를
전달하며 외부 source의 entry speed는 명시된 prior다(기본 0m/s). 이 투영은
공통속도 closure이지 개별 속도분포의 정확한 복원이나 충돌 회피가 아니다.
가감속 한계는 조성이 고정된 운동 구간에서 적용되며 조성 변화의 평균 투영과 구별한다.

## BoundaryFlux와 순서

`BoundaryFlux(tag,start_s,end_s,mass_veh,birth_moment)`는 veh 단위의 균일 경계율이다.
birth_moment가 없으면 해당 시간창에서 태어난 source의 정확한 1차 모멘트를 쓴다.
외부에서 이미 발생한 journey age를 전달하면 entry window 이전의 원 출생 모멘트를
명시한다. 이 경우 입력 flux 안의 birth mark는 일정한 조건부 평균이라는 가정이다.
point source도 지원하며 소비 cursor가 checkpoint에 들어가 재개 때 중복 방출하지 않는다.
source schedule은 모델 identity에 포함된다. 사람·화물량을 차량량으로 암묵 변환하지 않는다.

동일 window/tag/mark의 질량 분할은 정확 합산한다. 연속 window의 동일 rate/mark도
부동소수점 표현에서 정확히 같을 때만 병합한다. 실제 다른 입장시각은 gauge가 아니다.
Part는 tag·remaining route·boundary interval·birth moment를 보관한다. incoming
flux의 모든 끝점으로 공통 구간을 나누고, 같은 구간에서 겹치는 부분만 exchangeable
packet으로 혼합한다. 서로 겹치지 않는 구간은 packet FIFO 순서로 유지한다.
source의 실제 도로 입장은 선택 정책의 admission boundary point로 기록하며,
원래 source availability window는 schedule/deferred queue에 남는다.

압축은 같은 법칙·route·시간구간의 가산 질량/1차 모멘트만 합친다. 서로 다른
class는 다른 tag registry로 유지한다. 인위적으로 시간창을 합쳐 예산을 맞추지 않는다.
float 시간 해상도로 start=end가 된 극소 outlet도 삭제하지 않고 point measure로
완료 curve에 포함한다. 이는 무한 물리 서비스율의 주장이 아니라 시간 표현의 한계다.

## 선택한 시간 근사와 분리 장부

driver는 고정 원점의 max_step 격자와 source·신호·폐쇄 경계에서 나눈다. 수신
공간은 이전 occupancy에서 예약하고 transfer는 해당 작은 구간의 끝에 입장한다.
source window를 정확히 적분한 뒤 다음 경계에서 전달하고, 기존 source admission도
구간 끝에서 이루어진다. 이 holding을 없앴다고 주장하지 않는다. **남아 있는 시간
편향을 명시적으로 계측하고 dt refinement로 수용한다.** 기본 max_step은 0.1초다.
현재 신호·폐쇄 입력은 max_step과 정렬된 T03 계약 범위를 유지한다. source 창의 끝점은
임의 시각을 허용한다. 정렬되지 않은 control schedule은 조용히 샘플링하지 않고 거절한다.

source_arrival_quantization은 availability에서 다음 전달 경계까지의 적분 지연이다.
source_admission_quantization은 마지막 입장 step의 전체 경계 holding으로 정의한다.
그 이전 step에 남아 있던 source 대기는 source_queue로 분리한다. 후자는 이 분할
정책의 queue/holding 분해이며 연속시간 source server의 보편적인 정확 분해가 아니다.
transfer_quantization은 outlet Event의 실제 중간시각부터 다음 입장 경계까지의
veh·s다. 외부에서 전달한 이전 journey age는 이 수치 대기와 별도로 보관한다.

road source에 아직 넘기지 않은 마지막 flux 구간도 deferred 장부에 포함한다.
전체 released=completed+source_pending+active를 검사하고, 출생/유출 1차 모멘트에서
얻은 전체 veh·s와 road/source/transfer/pre-entry 항의 합을 대조한다. 미출생 일정은
not_yet_released로 남는다. 전체 모집단 평균은 모든 scheduled mass가 완료됐을 때만
내고, 그 전에는 완료 집단 조건부 평균만 낸다. 출생–도착의 joint 분포가 해상되지
않으므로 p95를 만들어내지 않고 UNSUPPORTED로 표시한다.

신호/사건 경계를 가로지르는 core interval은 거절한다. 폐쇄는 입출력 서비스를
막으면서 공통 목표 cap=0에 유한 제동으로 반응한다. point queue와 공통 drift는
명시한 집계 closure이며 이 조합을 개별 차량 안전성 증명으로 승격하지 않는다.

## 예산·실행·관측

기본 live/history record 상한은 2,000,000이며 그 이상 설정은 거절한다.
기존 node event budget과 별도로 advance 호출당 substep_budget(기본 100,000)을
노출한다. 초과 시 마지막 유효 checkpoint와 호출 시작 checkpoint를 남겨 재개할 수
있다. demand 삭제, OD 축소, 양의 질량 culling은 하지 않는다. peak packets/parts/
records를 기록하고 CLI subprocess의 wall time과 Linux peak RSS를 따로 측정한다.
이 작은 fixture의 계측은 24h 도시 성능 약속이나 전체 메모리 보증이 아니다.

```sh
python -m pytest -q tests/v1/test_transfer_time.py
python -m metroflow.v1 physics-oracles --suite timing --out timing.json
```

## 고정 수용 결과와 한계

210m 두 링크, 10m/s, 충분한 service의 무대기 기준은 21초다. 기존 dt=10초
baseline은 t=0의 1veh point source에서 41.005초다. 같은 point source 대조는
dt=.2에서 21.405초, dt=.1에서 21.205초다. 별도의 균일 [0,1]초 source에서는
dt=.2에서 21.501초, dt=.1에서 21.2505초이며
기준 및 dt/2 대조의 mean 오차 <= max(1초,2%) 문턱을 통과한다. 정확한 21초
수송을 달성했다고 말하지 않는다. 차이는 source/transfer holding과 service 항이다.

20veh 수요·유한 source receiving과 outlet service의 과부하 fixture에서는
30초 시점 완료 curve의 dt/2 최대 차이가 총수요의 0.75%다. source 미완료와 목적지
미완료 차이도 각각 2% 문턱 안에 든다. 실제 source backlog와 진행 차량은 남긴다.
이는 특정 underload/overload fixture의 수용이며 모든 혼잡 network의 보편 오차
정리, shock/FIFO 수렴 정리, 실도시 보정이나 10만 주민 24h 실행 완료가 아니다.

class/route·시간창 보존, 조건부 ETA와 endpoint root, source 분할, 원점 재개,
질량/veh·s, red boundary, finite braking, budget 중단을 함께 검증한다. 다음 R01/R02와
C01은 이 한 transport interface의 관측과 실제 완료 영수증을 소비한다. 전체 CI·통합·
최종 수용은 모든 DAG 구현 후 별도 심사로 보류한다.
