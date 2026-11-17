# V03 Rust 계산코어 후속 이식 — 2026-11-16

기준 commit은 `b13c7d31bf20f4f6ef275e87dc5ce578474beced`다. 이번 작업은 직접 factorized 달력 생성, 도로 물리 상태, 서비스·여정 장부와 결합 시간 루프를 Rust로 이식한다. Python은 현재 정적 물리 모델 구성, 일부 marginal 계산, 진단·checkpoint 변환을 계속 담당한다. 전체 calendar를 새 코어에 직접 연결하는 생성자까지 완성된 것은 아니다.

## 코드와 수학 계약

달력의 순서·ID는 기존 `FactorizedSchedule.iter_records/iter_legs`와 대응한다. 각 OD·mode 질량은 원래 좌결합 f64 연산 순서를 유지한다. stationary/unassigned cohort도 ID를 소비하므로 그 공백을 보존한다. outward와 return의 parent, dwell, activity/profile/law metadata를 유지한다. Rust는 예산·수량 overflow를 사전 순회로 검사한 뒤 저장소를 채운다. 전체 Python leg 배열이나 두 번째 전체 Rust leg 배열을 만들지 않는다.

도로 법칙은 기존 T02/T04와 같다. class별 latent는

\[
\dot p_c=r_c(1-p_c)-\nu_c p_c,
\qquad
\dot v=\operatorname{clip}\!\left(\sum_c w_c\frac{U p_c-v}{\tau_c},-\min_c b_c,\min_c a_c\right)
\]

를 계산한다. 각 local interval에서 질량·조성·공간·관측 cap을 동결하고, latent 반 step → midpoint 계수의 정확한 clipped characteristic → latent 반 step을 적용한다. 거리와 passage는 같은 characteristic을 사용한다. 단위는 m, s, 차량량이며 기존 closure와 boundary quantization을 유지한다. 이식 자체가 연속식 오차를 없앤다는 주장은 하지 않는다.

다중 class footprint, FIFO, 혼합 head의 회전 차단, 가중 junction 배분을 보존한다. 수용공간은 interval 시작 상태에서 계산한다. 같은 step의 유출로 새 수용공간을 만들지 않는다. 외부 source는 끝 경계에 입장하고, 전달 속도·latent는 기존 midpoint marks로 혼합한다. 부분 통행 factor는 유량을 줄이지만 이를 속도 cap에 다시 곱하지 않는다.

서비스는 잔여 버스 용량의 비례 승차, 전체 차량 도착 후 하차, step 끝 도착시각, dwell 이후 출발을 유지한다. 귀환은 이전 완결 상태의 receipt와 dwell을 사용한다. 버스의 귀환 승차는 지정 window 전체가 eligible이어야 한다. 사람·calendar 차량상당량·화물 장부는 물리적 road 차량 class 장부와 구별하여 교차검증한다.

`advance_native_joint`는 road/service/journey를 함께 빌려 GIL을 해제하고 모든 numerical tick을 Rust에서 실행한다. 실패한 tick은 세 상태를 함께 이전 완결 tick으로 되돌린다. 호출 경계에서만 Python snapshot을 만들고 독립 oracle 검사를 적용한다. 일반적 bitwise 동등성은 주장하지 않으며, 물리 field/event 비교는 rel `2e-11`, abs `2e-10` 및 driver의 명시적 허용오차를 사용한다.

## 구현 연결

- `v1_calendar.rs` / `native_calendar.py`: `compile_native_factorized_calendar` 직접 생성. 이전 streaming compiler도 명시적 oracle로 유지.
- `v1_road.rs` / `native_road.py`: persistent `V1Road`, 동일 경로 벡터 공유, physical state·junction·latent·차량/시간 장부, raw snapshot binding, batch 실패 checkpoint.
- `v1_journey.rs` / `native_journey.py`: native service scheduling과 journey transitions, 결합 Rust 시간 루프, 마지막 유효 tick 복구.
- `release_driver.py`: `METROFLOW_V1_ENGINE_BACKEND=rust` 또는 명시적 `engine_backend='rust'`. 경로 준비는 별도로 `METROFLOW_V1_ROUTING_BACKEND=rust`를 선택한다. 오타·native 실패는 명시적으로 거절한다.
- `run_v1_local_acceptance.py`: native mode에서 시간 단위로 묶어 advance한다. Rust 내부 tick 시간·최대 기록 수를 수집하고 매시간 checkpoint를 저장한다. frontend 변환·검사 비용은 별도 계측하며 전체 wall time에는 포함된다.

## 검증과 발견한 제한

실제 로컬 5900X / 관측 RAM 33,549,770,752 B / Python 3.12.3 / rustc 1.99.0에서 release build를 실행했다. 관련 회귀 **111개**, 계획 검사 **9개**가 통과했다. 물리 multi-class FIFO·신호·통제·재개, Python numerical callback 금지, service/journey rollback, 전일 소형 driver와 campaign hourly batching을 포함한다. 전체 저장소 CI·merge는 사용자 지시에 따라 보류했다.

행동 검증의 초기 RED는 잘못된 engine backend 선택이 조용히 무시되는 사례다. 최초 Rust build에서는 PyO3 optional argument 뒤 required argument의 signature annotation이 없어 compile 실패했고 수정 후 성공했다. 이 build 실패를 행동 RED로 세지 않았다. 독립 검토 및 구현 중 큰 유한 승객량 합계 overflow, 승차 허용오차에서 발생하는 작은 음의 대기시간 moment를 처리했다. 후자는 원래 oracle의 수치를 보존하고 clipping하지 않았다.

실제 하천 도시의 256-leg prefix는 원본 5,093,765개 중 5,093,509개를 활성화하지 않은 **진단 입력**이다. 이를 전체 도시 실행으로 합산하거나 외삽하지 않는다. 기본 journey record budget 20,000에서 27,040 s까지 진행한 뒤 resource failure가 발생했고 마지막 유효 checkpoint를 보존했다. 8 GiB process guard를 유지한 별도 진단에서 record budget을 200,000으로 명시하여 같은 prefix의 28,800 s 실행을 완료했다. 전역 기본값이나 V03 수용 한도를 바꾸지 않았다.

원본 zero-to-8h Python oracle 진단은 180초 외부 deadline 안에 완료 영수증을 만들지 못했다. 이 timeout을 Rust와의 완결 상태 비교나 임의 가속률로 바꾸지 않는다. 최초 source 이전의 빈 상태가 불변이라는 조건을 검사하는 `--start-s` 옵션은 양 backend의 동일한 유효 초기상태에서 활성 구간을 비교하기 위한 별도 진단이다.

최종 수치는 동봉한 `RECEIPT.json` 및 `final-*.json`, `matched-*.json`을 따른다. 실제 동작 중인 사용자 호스트의 한 번씩의 계측이며, 안정적인 성능 분포나 전체 campaign 속도는 아니다. old `prefix-rust-initial.json`의 `simulated_s=0`은 실패 출력 필드의 구버전 값이고 실제 진전은 같은 파일의 `last_valid_time_s=27040`이다. 새 계측 도구는 이를 교정해 마지막 유효 시간을 기록한다.

## 최종 계측

| 항목 | Python oracle | Rust | 범위 |
|---|---:|---:|---|
| 하천 전체 5,093,765-leg 등록 | 21.1685 s | 직접 생성 4.0804 s | 5.19배; 이전 Python→Rust streaming은 31.1204 s |
| 같은 전체 달력 최대 RSS | 1,528,008,704 B | 733,450,240 B | 약 52.0% 감소; 등록·보관만 |
| 실제 도시 256-leg 06:00→08:00 시간적분 | 78.4777 s | 1.1626 s | 67.50배; 동일 유효 초기상태·설정 |

해안 2,449,750 legs는 2.1590 s / 383,123,456 B, 계곡 918,450 legs는 1.9752 s / 176,246,784 B로 등록했고 총량이 일치했다. 전체 24시간 수송 결과가 아니다.

활성 구간의 보고서·checkpoint에서 수치 128,748개와 기타 leaf 36,512개를 비교했다. 최대 절대차 7.28e-12, max(1,|a|,|b|)로 정규화한 최대차 1.23e-15였다. 빈 상태 06:00 초기화의 native 종점 checkpoint는 00:00부터 실행한 native 종점과 byte-identical이다. 00:00→08:00 native prefix 시간적분은 2.7345 s이며 최대 RSS 84,787,200 B, 최종 road 기록 1,802개·journey 기록 44,628개다.

## 남은 작업

1. `NativeJointReleaseRuntime`의 Python 정적 생성자를 교체한다. native full calendar에서 road/service/journey registry로 직접 연결하여 Python 전체 leg tuple 및 helper graph 중복을 제거한다.
2. 전체 활성 상태와 완료·귀환 history를 실제로 계측한다. 현재 20,000-leg 준비 제한과 기본 20,000-record 제한은 유지한다. 한정 prefix의 낮은 RSS를 전체 도시의 예산 증거로 사용하지 않는다.
3. 동결 candidate에서 원래 세 도시 × 각 3회 24h, 해상도 대조, checkpoint replay를 수행한다. 그 뒤 별도 수용 심사를 거친다.

전체 DAG는 **19/21 (90.5%)**, V03 **BLOCKED**를 유지한다. 이번에 계산코어의 세 부분을 이식한 사실과 V03의 전체도시 수용은 별도 상태다.

## 재현 명령

```bash
CARGO_BUILD_JOBS=2 cargo build --release --locked -p metroflow-rust
# 현재 Python ABI에 맞는 위 extension을 환경에 설치한 뒤
PYTHONPATH=src python -m pytest -q tests/v1/test_native_calendar.py tests/v1/test_native_factorized_calendar.py tests/v1/test_native_road.py tests/v1/test_native_journey.py tests/v1/test_native_driver.py
python tools/measure_v1_native.py --mode calendar-native-factors --out calendar.json
python tools/measure_v1_native_runtime.py --backend rust --record-budget 200000 --out prefix.json
METROFLOW_V1_ENGINE_BACKEND=rust METROFLOW_V1_ROUTING_BACKEND=rust python tools/run_v1_local_acceptance.py --prepare-only
```

마지막 prepare-only 명령은 현재 전체 달력 제한을 명시적으로 보고한다. release 수용 성공 명령으로 제시한 것이 아니다. 로컬 기존 checkout은 변경하지 않았고, 전용 `/home/cosmosapjw/urban_traffic_rust_20261116` worktree에서 실행했다.
