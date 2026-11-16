# V1 Rust runtime: 로컬 설치와 모의실험

전체 도시 경로는 `NativeWholeEngine`이 달력 활성화, 경로, 도로·서비스·여정 상태,
시간 전진과 물리 장부를 소유한다. Python은 입력 구성, CLI, 실행 감독과 진단을
담당한다. 기존 Python 계산은 비교 oracle로 보존한다.

현재 수용 상태와 실행 근거의 권위는 [PLAN.json](PLAN.json)이다. Rust 빌드나
짧은 실행의 성공은 10만 주민·24시간 전체 수용을 뜻하지 않는다.

## 두 패키지의 기존 설치 경로

저장소 루트에서 Python 3.12 이상과 Rust toolchain을 사용한다. 새 가상환경의
기본 설치 명령은 다음과 같다. 이미 설치한 환경에서는 불필요한 재설치를 생략한다.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
.venv/bin/python -m pip install -c ci-constraints.txt -e '.[dev]'
.venv/bin/python -m maturin develop --release --locked \
  --manifest-path crates/metroflow-rust/Cargo.toml
```

가상환경을 활성화해 `VIRTUAL_ENV`와 `PATH`가 같은 환경을 가리키게 한다. 시스템에
있는 오래된 maturin 대신 해당 환경에 설치한 maturin을 사용한다.
`--locked`는 현재 `Cargo.lock`의 의존성을 사용하며 변경이 필요하면 거절한다.
처음 빌드할 때 설치되지 않은 Python 패키지나 Cargo 의존성은 내려받을 수 있다.
환경에 이미 갖춰진 의존성의 재다운로드는 필요하지 않다.

Python distribution `metroflow`와 Rust extension distribution `metroflow-rust`는
별개다. 기존 `crates/metroflow-rust/pyproject.toml`의 maturin 설정을 재사용한다.
root `pyproject.toml`을 Rust extension의 설정으로 바꾸지 않는다. 이 분리는
extension 설치가 Python CLI와 `metroflow` import를 덮어쓰는 회귀를 방지한다.
생성된 `.so` 파일을 수동으로 복사할 필요가 없다.

설치된 모듈과 frontend를 확인한다.

```bash
.venv/bin/python -c 'import metroflow, _metroflow_rust as native; assert hasattr(native, "NativeWholeEngine"); print(metroflow.__file__); print(native.__file__)'
.venv/bin/python -m metroflow.v1 capabilities
.venv/bin/python tools/run_v1_local_acceptance.py --help
```

`capabilities`는 설치된 기본 CLI의 기능 범위를 보여 준다. 전체 도시 실험은 아래
저장소 실행기로 수행한다. 이 안내 자체는 fresh-install 수용 영수증이 아니다.

## 실제 로컬 전체 도시 실행

기본 입력은 `scenarios/v1/release_matrix.json`에 고정된 10만 주민 도시 세 개다.
예산·수요를 줄인 입력을 전체 수용 결과로 사용하지 않는다. 먼저 실제 CPU/RAM과
측정 환경을 기록하며, 모의실험의 24시간은 벽시계 24시간과 다르다.

```bash
METROFLOW_V1_ROUTING_BACKEND=rust \
  .venv/bin/python tools/run_v1_local_acceptance.py \
  --engine-backend rust_whole --native-threads 1 \
  --storage-policy bounded_bytes_v1 \
  --run-local --case valley_weekday_s7 \
  --out artifacts/v1/local_acceptance
```

CLI의 기본값은 `--engine-backend rust_whole`, `--native-threads 1`,
`--storage-policy bounded_bytes_v1`이다. 기존 `METROFLOW_V1_ENGINE_BACKEND`,
`METROFLOW_V1_NATIVE_THREADS`, `METROFLOW_V1_STORAGE_POLICY`도 기본값으로 읽으며,
명시한 CLI 인자가 환경변수보다 우선한다.

`--case`를 생략하면 세 도시를 선택한다. 실행기는 각 도시의 24시간 반복 실행,
checkpoint 재개와 짧은 refined-dt 대조를 수행하고 결과를 영수증에 남긴다.
원인이 같은 차단 후의 미실행 반복은 성공으로 채우지 않는다. 출력 폴더의
`*.progress.json`, 개별 결과 JSON과 `CAMPAIGN.json`을 구분해서 확인한다.

전체 도시 CLI의 기본 자원 정책은 `bounded_bytes_v1`이며, 가상으로 펼친 기록 수와
저장량을 구분한다. legacy raw-row 정책은 비교와 이전 checkpoint를 위해 유지한다.
직접 사용하는 runtime/driver 생성자의 기본값은 호환성을 위해 `legacy_records`다.
정책 identity가 다르면 checkpoint를 무검증 재해석하지 않는다. 세부 정책과 예산은
실제 결과의 `native_storage` 및 source-bound 영수증에서 확인한다.

CLI의 정책 이름은 `bounded_bytes_v1`을 유지하지만 현재 accounting revision은
`native_storage.resource_binding = retained_capacity_v2`로 구분한다. 생성 단계의
기존 보수적 preflight와 물리 보고서의 `construction.estimated_bytes`는 유지한다.
이 생성 추정량에는 생성 뒤 해제되는 임시 자료와 snapshot allowance가 포함되므로,
실행 중 계속 보유하는 메모리로 간주하여 다시 차감하지 않는다.

실행 예산은 native가 소유하는 Vec/String capacity, 공유 Arc allocation의 identity,
알려진 동시 복사본과 작업공간으로 계상한다. 고정 reserve에는 initial road,
journey dense arrays 4개분, service dense arrays 6개분, 호출용 tag map,
worker/profile·service 준비 scratch와 제한된 관측 버퍼가 포함된다. 전체 CLI
accounting 예산 6GiB에서 이 reserve를 뺀 값이 하나의 shared dynamic pool이다.

road와 journey에 공개되는 `*_dynamic_allowance_bytes`는 이 pool의 **서로 더할 수
없는 상한**이다. 두 값을 합하여 사용 가능한 메모리로 읽지 않는다. prepare,
road proposal, journey finish마다 다른 owner의 알려진 input/current/candidate와
service event·sink 버퍼가 함께 차지하는 비용을 차감한 뒤 해당 단계의 할당을
허용한다. 고정 1/4:3/4 또는 1/2:1/2 분배를 사용하지 않는다.

snapshot capture, 전체 장부 검증, road→service→journey 순서의 checkpoint decode도
각 단계에서 이미 살아 있는 owner와 검증 작업공간을 포함하여 할당 전에 검사한다.
단계별 임시 상한은 공개 호출·load/restore 경계에서 정리한다. 검증 계약에는
commit 후보의 장부 검사와 같은 budget에서 다시 decode할 때 필요한 capacity
여유까지 포함한다. 예산 초과 뒤 반환한 마지막 유효 상태는 fresh runtime의
load/replay로 확인해야 한다. 이 checkpointability guard의 구현·검토 상태는 아래
accounting 검토 기록과 해당 후보의 실행 영수증을 함께 확인한다.

이 수치는 native 구조와 명시적 보수 allowance의 계상값이다. Python frontend,
opaque Rayon/allocator 내부 비용, 임의로 추가 보관한 snapshot까지 포함하는 OS RSS
상한 정리가 아니다. 별도로 적용하는 8GiB 프로세스 주소공간 제한과 측정 peak RSS
수용조건은 유지한다. resource identity는 `retained_capacity_v2`와 전체 예산에
바인딩하며 worker 수나 단계별 임시 quota에는 바인딩하지 않는다. 이전 고정분배
checkpoint는 새 바인딩과 다르므로 바인딩을 변경하여 재사용하지 않고 새 후보로
처음부터 실행한다.

과학 계산 thread 수는 명시적으로 기록한다. Rayon worker 수를 늘려도 모든 경로가
빨라지는 것은 아니므로 기본은 1이며, FIFO·합산·receipt 순서와 재개 결과를 유지한다.
`METROFLOW_V1_ROUTING_BACKEND`는 frontend의 고정 운행 경로 조회에 적용되고,
전체 달력의 OD 경로 탐색은 `rust_whole` 내부 Rust 구현이 담당한다.

## 현재 저장 표현과 수치 수정의 구분

stage는 불변 블록을 공유하고, 아직 준비되지 않은 블록의 반복 복사·검사를 줄인다.
도로 packet의 모든 part가 같은 시간구간을 가질 때는 구간을 packet에 한 번 저장하고
각 part의 tag·offset·질량·birth moment는 그대로 보존한다. 서로 다른 구간의 part는
mixed 표현을 사용한다. 유한한 interval endpoint의 `Option<f64>`는 내부에서
별도 sentinel로 표현하며, 현재 후보는 FIFO 행과 기존 checkpoint wire 형식을
유지한다. 이 저장 변경은 시간 binning이나 물리적 질량 합치기가 아니다.

별도로, 양의 event duration `h`에 대해 `cursor+h==cursor`가 되는 binary64
해상도 문제가 실제 실행에서 발견됐다. 새 수치 경로는 기존 경로가 이 조건으로
정지하던 경우에만 보상된 로컬 시계를 활성화한다. 이후 남은 horizon과 미래
event 거리에도 시계의 낮은 성분을 반영하며, 실제 FIFO 진행과 명시된 국소 예산을
확인한다. 임의의 최소 시간이나 질량 삭제로 진행시키지 않는다.

이 수정은 기존 정지 구간을 넘어서기 위한 **제한된 f64 수치 확장**이다. 이미
진행되던 경로의 표현 보존과 구분해야 하며, 기존 실패 이후 전체 trajectory와
정확한 실수 연산이 동일하다고 주장하지 않는다. 원래 질량 분할의 반올림,
near-one fraction snapping과 threshold 민감성은 별도 검증 대상이다. Python
참조 경로도 보존하여 동일 수치 정책으로 대조하고, 이전 실패와 binary의 근거도
작업 기록에 남긴다.

진단의 `processed_subulp_time_upper_s`를 \(E\), `clock_roundoff_upper_s`를 \(R\)라
하면, \(E\)는 낮은 해상도에서 **처리한 양의 시간의 합 상한**이고 \(R\)은 보상된
시계 연산에서 버려진 반올림 성분의 상한이다. \(E\)를 누락된 시간이나 보상 시계의
오차로 읽지 않는다. `nominal_subulp_service_mass_upper`는 해당 사건의 `rate*h`
명목량 상한이며 전체 질량 오차의 상한이 아니다. 이 진단은 runtime에서 검증된
도로 후보 전이의 누적값으로, 이후 service/journey rollback이나 branch/replay를
포함할 수 있다. 물리적 committed 장부와 다르며 checkpoint에 저장되지 않는다.

수치 근거와 한계는 [EVENT_RESOLUTION_ANALYSIS.md](../../artifacts/v1_rust_completion_20261116/EVENT_RESOLUTION_ANALYSIS.md),
저장 표현의 계약은 [IMPLEMENTATION_CONTRACT.md](../../artifacts/v1_rust_completion_20261116/IMPLEMENTATION_CONTRACT.md),
자원 정책의 권위 추적은 [RESOURCE_POLICY_REVIEW.md](../../artifacts/v1_rust_completion_20261116/RESOURCE_POLICY_REVIEW.md)를 참조한다.
Retained accounting의 구체 포함 범위는 [ROAD_STATIC_ACCOUNTING.md](../../artifacts/v1_rust_completion_20261116/ROAD_STATIC_ACCOUNTING.md)와
[JOURNEY_STATIC_ACCOUNTING.md](../../artifacts/v1_rust_completion_20261116/JOURNEY_STATIC_ACCOUNTING.md),
동시 수명·decode·재로드 검증의 현재 상태는 [RUNTIME_BUDGET_REVIEW.md](../../artifacts/v1_rust_completion_20261116/RUNTIME_BUDGET_REVIEW.md)에 기록한다.

## 실제 진단을 읽는 위치

출력 폴더를 지정한 뒤 다음 필드를 함께 확인한다. `*.progress.json`은 진행 중의
작은 상태 파일이고, 개별 실행 결과 JSON과 `CAMPAIGN.json`이 최종 검토 기록이다.

| 파일·필드 | 의미 |
|---|---|
| `*.progress.json`: `status`, `simulated_s`, `last_valid_checkpoint` | 현재 관측한 진행과 저장된 마지막 유효 상태 |
| 개별 결과: `candidate.source_sha256`, `candidate.git_commit`, `candidate.source_dirty` | 실제 실행 후보 소스와 기준 commit의 관계 |
| 개별 결과: `native_binary.sha256`, `native_binary.path` | 실제 로드한 extension 파일의 fingerprint와 위치 |
| 개별 결과: `native_storage.resource_binding` | 실제 accounting revision; 현재 후보는 `retained_capacity_v2` |
| `native_storage.conservative_static_accounting_bytes` | 호환 필드에 남긴 기존 생성 preflight 추정량; runtime retained bytes가 아님 |
| `native_storage.retained_static_payload_bytes`, `runtime_fixed_reserve_bytes` | 계속 보유하는 native 구조의 계상량과 동시 dense 복사·호출 scratch 등을 포함한 고정 reserve |
| `native_storage.dynamic_shared_pool_bytes`, `road_dynamic_allowance_bytes`, `journey_dynamic_allowance_bytes` | 하나의 dynamic pool과 그 비가산 상한; 두 owner 상한을 더하지 않음 |
| `native_storage.footprint_scope`, `allocation_rationale` | 포함·제외한 allocation과 단계별 admission의 적용 범위 |
| 개별 결과: `native_route_latency` / `route_latency` | Rust 전체 달력 OD 조회 / Python frontend 고정 운행 조회의 별도 측정 |
| 실패 결과: `failure_diagnostics.journey` / `.road` | 펼친 행 수, stage block, 저장량 추정 등 마지막 상태의 진단 |
| 실패 결과: `last_native_metrics.phase_metrics.road_event_resolution` | \(E\), \(R\), sub-ULP 사건 수와 진단의 적용 범위 |
| 실패 결과: `resource_limit_kind`, `reason`, `last_valid` | 생성·shared/phase·checkpoint 작업 예산, logical guard, 측정 RSS 등 원인과 실제 진행 시각 |
| `CAMPAIGN.json` | 반복·재개·refinement의 실행 여부와 별도 심사 요구 |

`retained_capacity_v2` 결과의 자원 분류는 다음과 같이 읽는다. 이전 고정분배
영수증의 `owner_quota_guard`는 그 당시 정책의 역사적 분류로 보존한다.

| `resource_limit_kind` | 검사 범위 |
|---|---|
| `shared_accounting_guard` | 전역/shared pool의 사용 가능한 계상 예산 |
| `phase_working_budget_guard` | road·journey·service 단계의 공존 상태와 작업공간 |
| `checkpoint_working_budget_guard` | capture·전체 검증·commit 후보의 재로드 작업공간 |
| `static_accounting_guard` | 기존 constructor preflight |
| `allocation_or_other_budget` | 실제 allocation 실패 또는 위 분류에 속하지 않는 예산 오류 |
| `measured_peak_rss`, `wall_deadline` | 실제 측정 RSS 또는 벽시계 수용 한도 |

직접 Python frontend를 사용하는 경우에는 `driver.runtime.storage_config()`,
`driver.runtime.event_resolution_diagnostics()`, `driver.debug_state(state)`로 같은
종류의 정보를 읽는다. 특정 snapshot의 상태와 runtime 전체 누적 진단을 혼동하지 않는다.

## 검증 이력과 현재 후보

[TESTS_NUMERIC.log](../../artifacts/v1_rust_completion_20261116/TESTS_NUMERIC.log)의
213개 통과는 [SOURCE_MANIFEST_NUMERIC.json](../../artifacts/v1_rust_completion_20261116/SOURCE_MANIFEST_NUMERIC.json)에
연결된 앞선 수치 수정 후보의 결과다. 그 후보의 실제 Valley 재개는
[1-worker 결과](../../artifacts/v1_rust_completion_20261116/numeric_resume_t1.json)와
[4-worker 결과](../../artifacts/v1_rust_completion_20261116/numeric_resume_t4.json)에서
25,490→25,520초까지 진행한 뒤 road의 entry-interval split owner quota로 중단됐다.
이는 24시간 정상 종료나 측정 RSS 한도 도달을 뜻하지 않는다.

이후 공통 interval 저장과 고정 1/2:1/2 quota 후보 `27e426f`는
[TESTS_FINAL.log](../../artifacts/v1_rust_completion_20261116/TESTS_FINAL.log)의 236개
scoped 검사를 통과했다. 해당 소스·binary는
[SOURCE_MANIFEST_FINAL.json](../../artifacts/v1_rust_completion_20261116/SOURCE_MANIFEST_FINAL.json)에
고정돼 있다. 이 후보의 실제 세 도시 첫 실행 결과는 다음과 같으며,
[CAMPAIGN.json](../../artifacts/v1_rust_completion_20261116/final_campaign/CAMPAIGN.json)에
후속 반복·refinement 미실행과 함께 보존한다.

| 입력 | 마지막 유효 모의 시각 (s) | 벽시계 (s) | peak RSS (GiB) | 분류 |
|---|---:|---:|---:|---|
| River weekday seed17 | 25,210 | 573.184 | 2.023 | 고정 journey owner quota |
| Coastal weekend seed41 | 32,650 | 279.530 | 2.256 | 고정 road owner quota |
| Valley weekday seed7 | 25,600 | 131.853 | 1.924 | 고정 road owner quota |

세 결과는 모두 `BLOCKED_RESOURCE`다. 측정 RSS의 8GiB 초과나 물리적 교통 불능으로
분류하지 않는다. 생성용 임시 자료의 수명과 unused owner quota를 조사한 근거이며,
24시간 정상 종료 영수증은 아니다.

`retained_capacity_v2`는 그 다음 accounting 후보다. 앞선 213·236개 검사와
도시 실행을 새 후보의 최종 검증으로 재사용하지 않는다. 새 후보의 scoped 검사,
실패 후 fresh-load/replay와 전체 도시 실행은 같은 소스·binary·resource identity에
연결된 별도 영수증으로 판정한다. 문서에 새로운 예산식이 있다는 이유로 V03이나
전체 24시간 수용을 완료 처리하지 않는다.

최종 retained-capacity 후보 `532effe`는 실제 release 빌드와
[251개 scoped 검사](../../artifacts/v1_rust_completion_20261116/TESTS_BUDGET_SEQ_FINAL.log)를 통과했다.
[고정 후보 기록](../../artifacts/v1_rust_completion_20261116/RUNTIME_BUDGET_FROZEN.json)의
45개 소스 파일을 실제 host와 commit에 대조한 뒤 새 캠페인을 실행했다.
결과는 [최종 보고서](../../artifacts/v1_rust_completion_20261116/REPORT_KO.md)와
[새 CAMPAIGN.json](../../artifacts/v1_rust_completion_20261116/runtime_budget_campaign/CAMPAIGN.json)에 보존한다.
River 25,350s, Coastal 32,660s, Valley 25,600s에서 shared working guard로 중단됐으며,
24시간 완료는 0/9회다. peak RSS는 각각 2.596/2.365/1.969GiB로, RSS 초과로 분류하지 않는다.

## 결과 해석과 남은 배포 범위

- `EXECUTED_FOR_REVIEW`는 요청한 구간 실행이며, 최종 수용 판정과 다르다.
- 마지막 유효 checkpoint와 `simulated_s`는 차단 전에 완료된 진행을 나타낸다.
- owner 저장 예산, 주소공간 제한과 측정 peak RSS는 서로 다른 계측이다.
- 수용에는 세 도시 각각 세 번의 24시간 실행, 장부·재개·refinement 검토와
  case당 7,200초/8GiB 기준을 함께 충족해야 한다.

설치된 `metroflow-v1 run`의 기존 synthetic/toy 경로는 별도로 보존된다. 저장소의
전체 도시 입력·실행기를 배포 패키지의 한 명령에 묶는 작업, fresh-install 최종
수용, 전체 CI·통합·릴리스는 RLS01 및 별도 심사 범위다.
