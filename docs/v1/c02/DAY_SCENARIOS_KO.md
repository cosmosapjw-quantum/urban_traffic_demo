# C02 하루 시나리오와 관측

하나의 실제 compile_city 결과에서 두 활동 구역·연결 도로·portal을 만들고,
M03 activity→D01 전체 평일/주말 cohort calendar→B01 서비스와 T04 PacketNetwork→장부로 실행한다.
10k는 주민 stock이며 10k 동시 차량을 생성하지 않는다. 1k 검산 및 10k 평일/주말은 실제86400s를 끝까지 실행한다.
6개 scenario manifest는 baseline weekday/weekend,1k analytic,bridgeclosure,bypass,growth weekday다.
이것은6개 형태학적 도시를 각각 실행했다는 뜻이 아니다. 형태학 matrix는 V02에서 별도 검수한다.

## 방출·반환·수송

D01 요청의 매10초 적분을 읽고, 완료 outbound receipt+minimum dwell 한도 안에서만 귀가를 방출한다.
차량용 추가 경계 offers와 실제 per-tag outlet Event를 같은 ServiceModel/PacketNetwork에서 소비한다.
돌아오는 bus는 outbound의 실제 승객 완료를 전제로 탑승한다. fixed run별 정원100이며 주민 증가로
운행 차량을 자동 증차하지 않는다. D01 bus occupancy-derived 차량 상당량은 교통량으로 다시 방출하지 않는다.
반환된 B01 승차/하차 person fraction을 D01 release/complete에 반영한다.
화물은 두 delivery window의 실제 고정 FreightRun 방출/유출로 kg와 차량을 따로 닫는다.

origin/egress는 실제 M03 geometry에서 얻은 평균 access delay의 명시적 moment closure다.
차량의 calendar first moment는 대기 pool에 적분하고, 합법 방출에 비례해 time mark를 나눈다.
따라서 총 first moment를 보존하지만 대기 pool 내 조건부 시간 상관/FIFO는 복원하지 않는다.
차량 road 진입 전 access queue와 road 유출 후 egress queue를 별도로 유지한다.
noncar는 같은 합법 지상 경로 길이/1.4m/s+access/egress의 합성 보행 지연으로 실행한다.
지원 경로가 없는 외부/다른 intrazonal 요청은 pending으로 남기며 0초 도착시키지 않는다.

10초 방출/정차/도착 경계의 수치 hold가 있다. 이 시나리오의 하루 종료는 dt refinement 정확도 증명이 아니다.
버스·화물의 source birth는 실제 run offer 시각이고 car는 calendar birth부터 origin access를 포함한다.
따라서 `recorded_birth_to_outlet_mean_s`는 서로 다른 출생 정의를 명시한 차량 기록 평균이며 공통 여정 평균이 아니다.
차종별 clock scope와 평균도 따로 제공한다. whole_person_trip_mean과 p95는 지원되지 않아 null이다.
완료 조건부 평균을 전체집단 평균으로 표시하지 않는다.

## 통제와 지연 개발

bridgeclosure는 동일 city와 calendar의 connector 양방향에7~12시 capacity0을 적용한다.
bypass는 동일 요청을 유지하는 실제 추가 합법 section이다. 추가 도로가 항상 더 좋은 결과를 낸다고 강제하지 않는다.
고정 free-time legal 경로를 사용하며 현재 사고 truth를 보아 동적으로 다시 배정하지 않는다.
`demand_control_identity`는 geometry/version을 제외한 OD·mode·amount·calendar를 동결해 수요 통제를 검증한다.

growth는 임의의 population+100 설정이 아니다. 별도 이전 epoch의 실제 T04 완료 표본을
compile_accessibility→M04 GrowthModel.advance(3600s,increment100)→materialize_city에 넣고,
그 다음 city의 D01 다음 calendar를 생성한다. 이 endogenous contrast는 baseline 동일수요 통제와 구별한다.
두 epoch를 연결한 next-calendar counterfactual이며 도시 전체 다일 동역학/가격 균형은 아니다.

## 실행·출력과 검산

`python -m metroflow.v1 run --scenario city10k_weekday --days 1 --artifacts DIR --out SUMMARY.json`

report.json은 stock·trip stage·차량·승객·cargo·시간·측정 wall/RSS를 기록한다.
city.json과 city.svg는 바로 그 실행의 map이며 hourly.csv/stages.csv도 같은 결과에서 출력한다.
RSS는 Linux process peak의 관측값으로 외부 프로세스/독립 메모리 벤치마크가 아니다.
미실행100k/전체 CI 성능 지표는 null이다. 일일 checkpoint resume은 지원하지 않으며 C01 toy resume과 혼동하지 않는다.

독립1k oracle: work500+service200,car60%/occupancy1.25,왕복2회 →672car차량,
fixed4bus+1freight →677도로차량 완료. bus work125/방향은 정원100에 제한되고
service50/방향은 모두 승차하므로300bus person-trip 완료,50person-trip 대기다.
총1400person-trip 중1350완료이고 기존 주민1000은 home/activity/transit 장부에서 보존된다.
최종 acceptance와 전체 CI·통합은 별도 심사까지 보류한다.
