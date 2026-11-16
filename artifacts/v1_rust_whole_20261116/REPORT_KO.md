# V03 Rust 전체 달력 연결 및 실제 로컬 검증

2026-11-16 UTC. 기준 commit `83197dcdc5c3a32a13d3a940da9976f68a542e78`.
규범 계획은 `docs/v1/PLAN.json`이다. DAG는 **19/21 (90.5%)**이며,
이 보고서는 V03 내부 구현의 한정 검증이다. V03와 RLS01을 완료로 승격하지 않는다.

## C1. 목표와 기준선

이전 native core는 Rust에서 물리·서비스·journey를 진행했지만 Python이
전체 leg tuple, 서비스 계획, helper graph를 먼저 생성했다. 이번 목표는
이 초기 구성과 상태 보존까지 native에 연결하고, 실제 세 도시의 전체 달력이
동일한 하나의 road owner에 들어가는지 측정하는 것이다. 이전 256-leg 진단을
전체 도시 수용시험으로 재사용하지 않았다.

## C2. 계산 계약과 데이터 연결

`FactorizedSchedule`의 marginal 입력과 고정 fleet만 frontend에서 직렬화한다.
`NativeCalendar`의 각 leg는 Rust의 route/service/journey registry에 직접 들어간다.
원래 cohort/parent ID, 목적·차종, 출발 profile, SI 양과 시각, 접근 지연법칙,
최소 체류시간을 보존한다. 수요를 지원하지 못하는 leg는 pending으로 남는다.

car·bus·freight는 한 `V1Road`를 공유한다. 기존 유한응답 물리 kernel,
old-state 수용 공간, FIFO, loopless legal-turn 경로, bus 실제 탑승·하차,
화물 배차 및 원래 의도 출발시각의 일차 모멘트를 변경하지 않았다.
고정 fleet 24대와 서비스 최대 run 수 20,000도 유지했다.

## C3. 상태와 이력의 수치 설계

Python으로 매번 전체 상태를 복사하는 대신 불변 `NativeWholeState`를 반환한다.
이전 snapshot은 후속 진행·분기·복원 이후에도 유효하다. 이진 checkpoint는
schema, city/schedule/fleet, step, resource 설정에 결속된다.

완료 이력은 원래 `(time, fraction)` 행과 순서를 모두 유지한다. 64행 이하의
persistent block을 공유하므로 이력 복제 비용은 전체 과거 행 수에 비례하지 않는다.
반환 적격성은 원래 `time + dwell <= now` 판정과 정확한 부동소수점 합산을 유지한다.
`time <= now - dwell`로 바꾸면 binary64 경계에서 달라지는 사례도 시험했다.

leg 수를 L, 과거 완료 행 수를 H라 하면 상태 복제의 이력 부분은
O(L+H)에서 O(L)로 줄었다. 빈 이력 header는 24바이트에서 8바이트가 되었고,
append는 최대 64개 이전 행만 복사한다. 원시 행은 삭제·시간 binning·반올림하지
않으며 block cache 자체의 메모리는 추가된다. 임의 순서 시각에 대한 적격성 조회의
최악 비용은 여전히 O(H)다. dense leg 배열의 매 tick 순회·복사도 남아 있다.

## C4. 작업 분할과 자원 정책

marginal static 준비, whole engine, native owner/codec, lossless history,
독립 oracle 검토를 병렬로 수행했다. 실제 도시 성능 측정은 같은 로컬 worktree에서
별도 process로 수행했다. Python 3.12.3, Rust 1.99.0, Ryzen 9 5900X,
실측 RAM 33,549,770,752바이트이며 과학 계산 thread 수는 1이다.

새 whole runner는 native accounting 6GiB와 process address space 8GiB를
명시한다. 이는 최종 peak RSS 8GiB·하루 wall 7,200초 목표를 완화하지 않는다.
기본 논리 record 예산은 20,000이다. 진단에서 다른 예산을 사용하면 영수증에
별도로 기록하고 기본값을 바꾸지 않는다.

## C5. 구현 산출물

- `v1_engine.rs`, `native_engine.py`: native 전체 구성, 불변 snapshot, 요약과 이진 저장·복원.
- `native_static.py`: 전체 OD 열거 없이 marginal 접근 법칙·도로·fleet 입력 준비.
- `native_release_driver.py`: 전체 calendar cursor와 runtime binding.
- `v1_history.rs`: 손실 없는 persistent completion 이력.
- `v1_journey.rs`, `v1_road.rs`: 공유 입력과 Rust owner codec, 교차 장부 검증.
- `run_v1_local_acceptance.py`: 명시적인 `rust_whole` 선택, native 시간별 batch,
  `.bin` checkpoint와 실제 tick 계측. 기존 Python oracle은 비교 대상으로 남아 있다.

## C6. 구현 검증

실제 로컬 release build 및 관련 **105개 테스트**가 통과했다.
새 테스트는 혼합 교통 oracle 대조, profile·law 합산, 이전 snapshot 불변성,
새 runtime에서 재개·추가 진행, checkpoint byte identity, 손상·과대 크기·NaN·
유한하지만 잘못된 birth moment·owner clock 불일치 거부를 포함한다.
Python OD iterator와 기존 Python runtime 생성자를 금지한 상태에서도 새 driver가
전체 factorized calendar를 구성하는 것을 확인했다. 전체 저장소 CI는 실행하지 않았다.

## C7. 과학적 교차 검증

독립 Python joint oracle과 작은 혼합 fixture의 requested/released/completed,
pending/active, 원래 출발시각 모멘트, bus·freight 물리 장부를 대조했다.
완료 시각 이력은 Python `math.fsum`과 직접 비교했다. 검토에서 발견한
checkpoint의 유한한 birth 위조 허용 문제는 복원 전 native 교차 검사로 수정했다.
개별 owner 형식 검증만으로 과학적 보존을 인정하지 않는다.

## C8. 전체 달력 실측과 재현

아래는 각 도시의 **전체 달력 구성, 최초 10초, checkpoint 저장·복원** 측정이다.
구성 시간은 native calendar 생성과 정적 도로/서비스/journey 생성까지 포함한다.
peak RSS는 process 전체 측정이다.

| 도시 | 전체 leg | native 구성(s) | peak RSS(bytes) | checkpoint(bytes) |
|---|---:|---:|---:|---:|
| River | 5,093,765 | 48.971551 | 2,171,146,240 | 163,298,622 |
| Coastal | 2,449,750 | 31.390759 | 1,161,740,288 | 78,646,478 |
| Valley | 918,450 | 8.731241 | 475,160,576 | 29,539,598 |

각 영수증의 `unactivated_legs=0`, `python_calendar_leg_objects=0`, `road_owners=1`을
확인했다. 10초는 최초 수요 출발 전이므로 세 경우 모두 requested/released/completed,
road release와 peak dynamic record가 0이다. 이 표로 혼잡 구간이나 24시간 성능을
주장할 수 없다. 지원되지 않는 leg도 River 3,392,401, Coastal 1,631,129,
Valley 610,820개로 명시적으로 남는다. 전체 활성화가 전체 OD 지원을 뜻하지 않는다.

Valley 전체 달력을 0초부터 8시간까지 시도한 기본 예산 실행은 **25,210초**의
유효 상태를 보존하고 다음 tick에서 `joint journey record budget`으로 중단됐다.
전체 wall은 100.245588초, peak RSS는 453,529,600바이트였다.
실행환경 오류나 8GiB 메모리 고갈이 아니라 **논리적 기록 수 제한**이다.

예산을 **2,000,000개로 명시한 별도 진단**도 25,380초에서 같은 제한에 걸렸다.
전체 wall은 153.419405초, peak RSS는 1,013,796,864바이트였다. 개수 제한을
100배 높이는 것만으로는 8시간에 도달하지 못했으며, 기본 20,000개 설정은
변경하지 않았다. 이는 원래 전체 수요를 누락하지 않은 실행 결과다.

두 마지막 유효 checkpoint를 **새 runtime**에서 복원하고 다시 저장한 파일은
원본과 byte-identical이었다. 다음 tick을 재시도하면 같은 resource 오류가
재현됐고 rollback checkpoint도 원본과 byte-identical이었다. 후속 실패가
이전 불변 snapshot을 바꾸지 않았음을 확인했다. 이는 실패 지점의 정확한
재현이며, 아직 완료되지 않은 하루 실행의 replay 성공을 뜻하지 않는다.

원본 이진 checkpoint는 실제 전용 worktree의 같은 artifact 경로에 남아 있고,
파일 크기·SHA는 영수증에 기록했다. 대용량 checkpoint 자체를 Git에 넣지 않았다.
소스·binary·matrix identity는 `SOURCE_MANIFEST.json`과 개별 영수증으로 결속했다.

```bash
PYTHONPATH=src .venv/bin/python tools/measure_v1_native_whole.py \
  --case river_weekday_s17 --horizon-s 10 --wall-s 300 \
  --out artifacts/v1_rust_whole_20261116/river_whole_10s.json
PYTHONPATH=src .venv/bin/python tools/measure_v1_native_whole.py \
  --case valley_weekday_s7 --horizon-s 28800 --wall-s 300 \
  --out artifacts/v1_rust_whole_20261116/valley_whole_to_8h.json
```

## C9. 독립 심사

심사자는 소스 36개 SHA와 세 초기 실측 영수증의 binary/source identity,
105개 테스트 로그를 대조했다. 판정은 native 전체 초기화 연결의 한정 수용이다.
10초 영수증의 저장·복원 report 동등성과 소형 fixture의 재개 후 연속 실행 동등성을
구분했고, 대규모 장기 실행의 동등성으로 확대하지 않았다.

## C10. 결정과 남은 차단

Python 전체 leg 생성 및 중복 helper graph를 거쳐야 했던 초기 구성 차단은
새 `rust_whole` 경로에서 해소됐다. 기본 20,000-record 제한에서 전체 도시 활성
시간대 진입이 차단되는 것이 실제 로컬에서 재현됐다. 다음 핵심 작업은 활성 stage와
history의 정확한 저장·검증을 유지하면서 논리 record 예산과 byte accounting을
정합적으로 설계하고, dense 전체 leg 매 tick 작업을 줄이는 것이다.

V03 수용에는 여전히 세 도시 각각 24시간×3회, 장부·replay, refined-step 대조,
8GiB/7,200초 실측과 별도 심사가 필요하다. 전체 CI·통합·merge는 사용자 정책대로
보류한다. 이 상태에서 RLS01 릴리스 완료를 선언하지 않는다.
