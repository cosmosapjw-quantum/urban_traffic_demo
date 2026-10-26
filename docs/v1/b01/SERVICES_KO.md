# B01 최소 고정노선 운영

ServiceModel은 T04 TransportModel이 구성한 단일 PacketNetwork와 finite-response motion을
그대로 사용한다. 버스 leg와 화물이 같은 road node 공급·수용·물리 길이 저장량을 경쟁한다.
별도 도로 solver나 버스 수요에 비례하는 차량 생성은 없다. PassengerCohort persons와
스케줄 버스 vehicles, FreightRun vehicles/cargo_kg는 서로 다른 장부다.

BusRun은 두 정류장 사이의 합법 link tuple들의 목록과 timetable, 정원, dwell을 가진다.
정류장은 off-road bay로 선언한다. 각 bus run은 차량량 1이며 leg 완료 시 다음 정류장에
정차하고 actual arrival+dwell 및 timetable 둘 다 충족한 뒤 다음 leg로 재진입한다.
중간 정류장에서도 연속 경로의 합법 turn을 검증한다. 정차는 capacity-window로 도로 전체를
폐쇄하지 않는다. stop 도착은 해당 차량량 전체가 유출된 step end에 정해진다.
이는 부분 유출과 step-boundary holding을 포함하는 명시적 집계 closure이며
개별 버스 위치 전수추적이나 정류장 미시모형이 아니다.

같은 정류장·시각의 승차 가능 cohort는 잔여 정원을 비례 배분한다. 초과 승객은 waiting에
그대로 남고 이미 출발한 run을 자동 증차하거나 다른 run으로 환승하지 않는다.
목적 정류장에서 하차한 사람과 마지막 leg를 완료한 버스 차량은 별도 완료 상태다.
waiting person-seconds는 승차한 대기와 아직 대기 중인 누적량을 포함한다.
D01의 persons를 이 cohort에 공급할 때 D01의 occupancy 기반 fractional bus vehicles를
다시 도로에 투입하면 안 된다. 실제 차량 공급은 고정 BusRun 스케줄이 소유한다.
이 어댑터의 전체도시 수요 연결은 C02 소유다.

FreightRun은 허용 링크, gross kg/vehicle와 허용 최대 중량을 명시한다.
화물 질량은 실제 최종 유출 차량량에 비례해 배달되고 미완료량이 별도로 남는다.
외부 source/stop timetable는 fixed step 경계에서만 방출하므로 step refinement가 필요하다.
이 최소 운영기는 환승·버스 dispatch 최적화·공차 재배치·stop road blocking을 지원하지 않는다.

immutable ServiceState는 실제 road queues와 모든 서비스/승객/화물 상태를 소유한다.
매 step에서 persons 보존, capacity와 기존 PacketNetwork 차량 보존을 검증한다.
report는 도로 버스량+정류장/완료 버스량=고정 fleet stock도 검산한다.
예외는 직전 ServiceState checkpoint를 보존한다. 전체 CI와 통합은 별도 심사까지 보류한다.

CarRun의 선택적 고정 source도 같은 네트워크에 투입하며 3차종 동시 보존 검사를 포함한다.
서비스 identity는 frozenset 허용 링크를 정렬하여 프로세스 재시작에도 고정한다.
