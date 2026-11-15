# V03 경로 요청 지연의 유계 메모리 계측

2026-11-16. 대상은 `run_v1_local_acceptance.py`의 각 독립 worker에서
준비 시작부터 실행·보고까지 실제 호출한 경로 API의 wall latency다.
이는 교통의 물리 여행시간이나 접근분포 계산시간과 구별한다.
이 계측 구현으로 V03의 전체 도시 실행 또는 수용 상태가 자동 변경되지는 않는다.

## 관측량과 호출 경계

`RouteLatencyMeasurements` context 안에서 `perf_counter_ns`로 측정한다.
`release_runtime.path`, `release_services.path`는 각 LRU/경로 캐시의 바깥에
계측 경계를 두므로 호출된 hit와 miss를 모두 포함한다.
`LegalRouteCache.resolve`와 직접 호출한 `candidate_paths`도 측정한다.
한 경로 요청 안에서 다른 계측 API가 호출되면 가장 바깥 요청만 한 번 센다.
따라서 inventory 검증과 실제 runtime 준비가 각각 요청한 경로는 각각 포함되지만,
한 요청을 wrapper와 내부 search에 이중 계상하지 않는다.

처음부터 경로 API를 호출하지 않는 intrazonal 처리나 예산 사전 거절은 경로
표본을 만들지 않는다. 해당 worker의 요청 수가 0이면 `NOT_MEASURED`,
`p99_ns=null`이다. 실패하거나 도달 경로가 없는 실제 요청도 latency 모집단에
포함하며, 예외 발생 수는 별도로 기록한다. 원래 반환값과 예외는 유지된다.
계측 context가 없으면 clock을 읽거나 histogram을 갱신하지 않는다.

시간 표본은 각 최외곽 함수 호출을 감싼 두 clock read의 차이다. timer 자체의
오버헤드를 빼지 않으며 histogram 갱신은 측정구간 밖에서 이루어진다.
실행 wall에는 계측 오버헤드가 포함된다. context는 worker의 단일 과학 실행
thread에 적용되며, 다른 thread의 경로를 측정했다고 주장하지 않는다.

## p99의 정의와 정확한 포괄 구간

관측 수를 N, 오름차순 표본을 x_(k)라 하면 보고 대상은
`k = ceil(0.99 N) = (99 N + 99) // 100`에 해당하는 nearest-rank 통계량이다.
실제 모든 표본을 배열에 저장하는 대신 7,425개 고정 counter를 사용한다.

- 0–255 ns는 정수값마다 독립 bucket을 갖는다.
- 256 ns 이상, 2^64 ns 미만에서는 `s = bit_length(x) - 8`,
  `m = floor(x / 2^s)`로 정하고 `128 <= m <= 255`인 bucket을 사용한다.
  이 bucket의 정확한 정수 포괄 구간은
  `[m 2^s, (m+1) 2^s - 1]`이다.
- 2^64 ns 이상은 overflow bucket이다. 관측된 최대값을 상한으로 함께
  보고하며 이 bucket에는 미세해상도 보장을 적용하지 않는다.

counter 누적합이 최초로 k 이상인 bucket에는 x_(k)가 반드시 들어간다.
그 bucket의 하한·상한을 실제 관측 min·max로 좁힌 구간을 `p99_ns`에
그대로 보존한다. 비포화 bucket 폭/하한은 1/128 이하이며, midpoint를
정확한 p99처럼 보고하지 않는다. 향후 latency 문턱이 L ns로 정해지면
`upper <= L`인 경우만 이 계측으로 통과를 입증하고, 구간이 문턱을
가로지르면 추가 해상도가 필요하다. 현재 PLAN에는 독립적인 p99 수치문턱이 없다.

histogram의 항목 수는 표본 수와 독립적이다. 각 counter는 Python 정수이므로
정수의 비트 길이가 표본 수에 따라 증가할 수 있다는 점까지 포함해,
표본별 시간 배열을 유지하는 O(N) 보유량을 제거한 구조다.

## 실제 검증

기존 예산 실패 worker에서 `route_latency`가 누락된 행동을 새 단언으로
확인했다: Python 3.12에서 1 failed, 1 passed. 구현 후 다음을 검사했다.

- bucket 경계와 99/100/101 표본 rank에서 실제 정렬 p99가 보고 구간에 포함됨.
- 10,000개 추가 표본 뒤에도 histogram 길이는 7,425로 유지됨.
- overflow와 무표본 상태를 별도로 표현함.
- cache miss/hit 두 요청과 실패한 직접 search 한 요청을 실제 함수 반환값과
  함께 검사하고, 내부 search가 이중 계상되지 않음.
- source-tree cache의 hit/miss 및 도달불가 query가 각각 계수됨.
- 작은 실제 `scenario_city(1000)`의 CLI 준비가 `MEASURED_INTERVAL`을
  생성하고 matrix SHA·준비 상태·실행시간 0을 보존함.

관련 명령:

```sh
python -m pytest -q tests/v1/test_route_metrics.py tests/v1/test_local_campaign_cli.py tests/v1/test_release_plan.py tests/v1/test_routing_commitment.py tests/test_routing.py
```

Python 3.12와 3.13에서 각각 55 tests 통과(0.96 s, 0.95 s).
변경 파일 ruff 통과. 초기 3.13 명령의 존재하지 않는
`tests/v1/test_routing.py` 경로는 수집 전 exit 4였으며 실제 경로로 고친
위 실행과 구별한다. 작은 준비 fixture의 첫 실행은 inventory 설정의
`departures_s` 누락으로 실패했고, fixture에 명시적 출발시각을 넣어 수정했다.
전체 저장소 CI와 통합은 사용자 지시에 따라 수행하지 않았다.

실제 100k 전체 calendar가 20,000-leg 사전 한도에서 거절되는 동안 그
worker의 경로 요청 수는 0일 수 있다. 그러한 영수증은 전체 도시 p99를
측정한 증거가 아니며, 한도 해소 뒤 실제 캠페인의 측정 구간이 필요하다.
