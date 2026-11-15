# V03 실제 로컬 비용 진단 — 2026-11-16

완료 구현·한정 실행은 **19/21 (90.5%)**, 최종 수용은 5/21이다. V03의 실제 3개 도시 × 3회 24h 수용 캠페인은 미실행이며 RLS01은 대기한다. 전체 CI·통합·merge는 사용자 지시에 따라 보류한다.

이번 실행은 실제 `cosmosapjw` 장치에서 수행했다. CPU는 AMD Ryzen 9 5900X, Linux에서 관측한 메모리는 33,549,770,752 B(약 31.25 GiB), Python은 3.12.13이다. 기존 계획의 reference RAM 64GB를 관측값으로 재사용하지 않는다. 기존 작업 checkout에 수정 파일이 있어 별도 `/home/cosmosapjw/urban_traffic_v03_20261116` clone을 사용했다. baseline HEAD는 `b41f807c490dda12e036bcb40d9c13370f04223e`; 변경 코드의 개별 SHA는 새 영수증과 benchmark에 기록했다. 실행 뒤 가져온 원본 JSON 및 테스트 로그의 SHA256은 장치에서 직접 계산한 값과 일치한다.

## 전체 달력의 실제 저장 비용

변경 전 공개된 baseline과 원래 release matrix로 세 도시 준비 검사를 수행했다. 하천 5,093,765, 해안 2,449,750, 계곡 918,450 legs가 기존 runtime 사전 활성화 한도 20,000을 넘어 모두 `BLOCKED_RESOURCE`였다. cursor 0과 전체 잔량을 보존했다. 이는 물리 시뮬레이션 실행 결과가 아니다.

별도 진단에서는 가장 큰 하천 도시의 원래 factorized iterator를 끝까지 순회하여 **5,093,765개 모든 TripLeg를 동시에 보관**했다. 도시·주민·모드·목적·시간분포를 바꾸지 않았다. 목록 생성 17.95191초, 지도와 활동 준비·수량 검사 포함 30.16804초, 실제 프로세스 peak RSS 1,526,939,648 B(약 1.42 GiB)였다. 전체 persons 120,000, vehicle equivalents 58,801, cargo 1,000kg이 폐쇄형 총계와 일치한다. 이 persons 값은 왕복 leg 양이며 주민 재고 100,000명과 구별한다.

따라서 이 실행환경에서 **달력 보관만으로 8 GiB 예산을 초과한다는 진단은 지지되지 않는다**. 진단은 경로·서비스·공동 물리 runtime을 활성화하지 않았다. 경로 registry, leg별 장부와 active records의 비용 및 하루 wall/RSS는 별도 측정 대상이다. product의 20,000-leg 한도를 자동 증가시키지 않는다.

재현: `python artifacts/v1_v03_scaling_20261116/measure_calendar.py --out calendar.json`. 이 진단은 300초/8GiB 중단 검사를 갖고, 성공 상태도 `FULL_CALENDAR_RETAINED_FOR_DIAGNOSIS`로 구분한다. 원본 측정은 `artifacts/v1_v03_local_20261116/RIVER_CALENDAR.json`에 있다.

## 변경 코드의 실제 PC 비교

동일한 PC에서 원본 함수와 수정 함수를 짝지어 실행했다. 각 행은 **서로 다른 한정 fixture**이며 속도비를 실제 큰 도시에 외삽하지 않는다.

| 한정 측정 | 원본 평균 | 수정 평균 | 확인한 동등성 |
|---|---:|---:|---|
| 내부 이동 4,000 legs 생성자, 3쌍 | 0.36998 s | 0.00864 s | identity·경로·boundary·내부 법칙 |
| 같은 endpoint 도로 256 legs 생성자, 3쌍 | 0.23105 s | 0.00505 s | 위와 동일; 별도 120s 왕복 상태·report |
| 1,500 legs/활성 기록의 장부 검사, 5쌍 | 41.671 ms | 5.188 ms | 4 tick 상태·checkpoint 바이트·재개·변조 거절 |
| 두 activity measures를 공유하는 버스 1,000 legs 준비, 5쌍 | 3.55504 s | 0.01093 s | 매 쌍 전체 service plan |

생성자는 부모 lookup을 O(L²)에서 O(L)로 바꾸고 기존 solver의 결과와 전체 활동측도에 대한 법칙을 제한된 캐시에 공유한다. Joint 검사는 같은 `fsum` 입력 순서를 유지하면서 stage/service 역색인을 사용한다. 상세 유도와 원본 행동 실패는 각 `V03_*_COST_KO.md`, `V03_CONSTRUCTOR_SCALING_KO.md`에 있다. cache 적중이 많은 fixture의 개선 폭은 실제 OD 분포의 개선 폭을 보장하지 않는다.

route latency는 최외곽 경로 API 요청을 계측하며 호출된 cache hit도 포함한다. 고정 7,425개 counter로 nearest-rank p99의 **포괄 구간**을 보고한다. 이 수치는 물리 여행시간이나 전체 도시의 p99를 대신하지 않는다. budget 사전 거절로 호출이 0이면 `NOT_MEASURED`와 null을 기록한다. 자세한 모집단·오차·실패 의미는 `V03_ROUTE_LATENCY_KO.md`를 따른다.

실제 세 도시에서도 각각 원래 달력의 첫 256 legs와 고정 fleet를 단일 runtime으로 준비하고 초기 상태 장부를 검사했다. 모두 `BOUNDED_PREFIX_PREPARED`, simulated 0s이며 나머지 전체 달력의 수량을 보존한다. 각 실행에서 132개 경로 요청을 관측했으며 p99 포괄 구간은 하천 [19.005440, 19.136511] ms, 해안 [19.136512, 19.267583] ms, 계곡 [9.895936, 9.961471] ms였다. 이 값은 첫 prefix와 inventory 준비의 모집단에만 적용한다. 세 영수증의 모든 실제 import source SHA는 게시 후보 파일과 일치한다. 재현 명령: `python artifacts/v1_v03_scaling_20261116/measure_preparation.py --case river_weekday_s17 --legs 256 --out prefix.json`.

검증은 변경 의존성에 해당하는 92개 테스트와 계획 검사 9개를 scratch Python 3.12/3.13에서 각각 수행했고, 실제 PC Python 3.12.13에서도 같은 코드 검사 92개가 통과했다. 전체 저장소 CI는 실행하지 않았다. 후속 대상은 전체 calendar를 단일 공유 runtime에 활성화할 때의 비용과 활성 상태 표현이다. 원래 경로 solver의 의미나 귀가 완료시각 분포를 지우는 집계는 별도 동등성 증명 없이 적용하지 않는다.
