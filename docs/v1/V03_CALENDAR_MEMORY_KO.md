# V03 calendar 출발분포 공유 메모리 개선

기준은 `5a1492443012347965c75e33afb10d7a0803af41`의 `demand`와 `factorized_demand`다. 모든 demand dataclass는 이미 frozen/slots이므로 slots 재적용은 개선이 아니다. 실제 반복 할당은 각 OD cohort마다 새로 생성되던 불변 `DepartureProfile`·`DepartureWindow`였다.

`demand.calendar_profiles(day,purpose)`는 기존 `schedules.daily_profiles`의 값을 최대 8개 day/purpose 쌍으로 공유한다. 두 compiler가 같은 helper를 사용한다. 각 cohort의 사람·차량·화물량, ID, 목적, 차종, 왕복 의존성, 진도 장부는 서로 별개다. 출발분포를 근사하거나 확률을 합치는 연산은 없다. Profile과 windows는 frozen slots dataclass이고 windows 컨테이너는 tuple이다. 캐시 eviction도 재생성 비용만 바꾸며 값을 바꾸지 않는다.

이 변경에서 dense schedule의 canonical identity/asdict, factorized identity와 모든 TripLeg 값, checkpoint encode/decode를 원래 함수 호출과 대조했다. 두 Python에서 관련 19개 검사(calendar memory 2, daily demand 14, factorized 3)가 각각 통과했고 ruff가 통과했다. 원래 compiler의 worker 부족 거절도 그대로 유지한다.

메모리 계산은 `artifacts/v1_v03_memory_20261029/benchmark.py`로 재현한다. 50 home × 50 job × 3 mode, 왕복 포함 15,000 leg를 실제 지연 생성한 뒤 tuple로 보유했다. Marginal schedule은 측정 밖에서 만들었다. 균일 합성 fixture의 worker fraction은 양쪽 모두 0.1이다. 최초 default 0.5 시도는 job support 부족을 올바르게 거절했으며 측정 결과에 포함하지 않았다. 5회 짝지은 실행의 순서는 번갈아 바꿨다. 매 쌍 전체 TripLeg tuple의 정확한 동등성을 확인했다.

| 관측량 | 기존 | 공유 |
|---|---:|---:|
| tracemalloc retained 평균 [byte] | 6,741,274.4 | 3,861,970.4 |
| tracemalloc peak 평균 [byte] | 6,746,946.4 | 3,867,546.4 |
| tracing 중 구성시간 평균 [s] | 0.702803 | 0.485430 |
| 보유한 고유 departure profile 수 | 15,000 | 2 |

이 fixture의 retained allocation은 42.71% 줄었다. 이것은 Python 추적 할당이며 전체 RSS가 아니다. 시간에는 tracemalloc 오버헤드가 포함된다. 원자료, Python 버전, 부모 commit, 관련 source SHA256은 `RESULT.json`에 있다.

이번 변경은 입력을 유지하는 표현 공유다. 실제 92만–509만 leg의 전체 상태 준비, runtime의 경로/진도/완료 영수증 비용, 20,000-leg 사전 활성화 예산은 그대로 남는다. 큰 도시의 24h 성능으로 외삽하지 않는다. 전체 로컬 캠페인은 NOT_RUN이고 V03 완료율은 19/21(90.5%) 그대로다. 다음 의무는 이 공유를 포함한 전체 준비·runtime 비용의 실제 자원 측정과 exact 상태 표현 개선이다.
