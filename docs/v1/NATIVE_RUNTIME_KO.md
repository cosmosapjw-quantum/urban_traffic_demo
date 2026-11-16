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

현재 후보는 CLI의 6GiB accounting 예산에서 기존 보수적 construction/snapshot
추정량을 뺀 나머지를 road와 journey에 각각 1/2씩 배분한다. 홀수 나머지 1바이트는
journey에 배정하며 owner 사이에 사용하지 않은 quota를 자동 대여하지 않는다.
이것은 process의 8GiB 주소공간 제한이나 측정 peak RSS와 별개의 보호 장치다.
이전 1/4:3/4 배분 파일과 새 1/2:1/2 배분은 checkpoint identity가 다르므로,
이전 파일의 바인딩을 바꾸어 재개하지 않고 새 정책으로 처음부터 실행한다.

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

## 실제 진단을 읽는 위치

출력 폴더를 지정한 뒤 다음 필드를 함께 확인한다. `*.progress.json`은 진행 중의
작은 상태 파일이고, 개별 실행 결과 JSON과 `CAMPAIGN.json`이 최종 검토 기록이다.

| 파일·필드 | 의미 |
|---|---|
| `*.progress.json`: `status`, `simulated_s`, `last_valid_checkpoint` | 현재 관측한 진행과 저장된 마지막 유효 상태 |
| 개별 결과: `candidate.source_sha256`, `candidate.git_commit`, `candidate.source_dirty` | 실제 실행 후보 소스와 기준 commit의 관계 |
| 개별 결과: `native_binary.sha256`, `native_binary.path` | 실제 로드한 extension 파일의 fingerprint와 위치 |
| 개별 결과: `native_storage` | 총 accounting, 보수적 static 추정량과 owner별 quota |
| 개별 결과: `native_route_latency` / `route_latency` | Rust 전체 달력 OD 조회 / Python frontend 고정 운행 조회의 별도 측정 |
| 실패 결과: `failure_diagnostics.journey` / `.road` | 펼친 행 수, stage block, 저장량 추정 등 마지막 상태의 진단 |
| 실패 결과: `last_native_metrics.phase_metrics.road_event_resolution` | \(E\), \(R\), sub-ULP 사건 수와 진단의 적용 범위 |
| 실패 결과: `resource_limit_kind`, `reason`, `last_valid` | owner quota, logical guard, 측정 RSS 등 실패 원인과 실제 진행 시각 |
| `CAMPAIGN.json` | 반복·재개·refinement의 실행 여부와 별도 심사 요구 |

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

공통 interval 저장과 새 1/2:1/2 quota 후보는 그 이후의 변경이다. 앞선 213개 테스트와
재개 결과를 새 후보의 최종 build·full-day 증거로 재사용하지 않는다. 새 결과는 그
후보의 소스·binary·정책 identity에 연결된 실행 영수증으로 판정한다.

## 결과 해석과 남은 배포 범위

- `EXECUTED_FOR_REVIEW`는 요청한 구간 실행이며, 최종 수용 판정과 다르다.
- 마지막 유효 checkpoint와 `simulated_s`는 차단 전에 완료된 진행을 나타낸다.
- owner 저장 예산, 주소공간 제한과 측정 peak RSS는 서로 다른 계측이다.
- 수용에는 세 도시 각각 세 번의 24시간 실행, 장부·재개·refinement 검토와
  case당 7,200초/8GiB 기준을 함께 충족해야 한다.

설치된 `metroflow-v1 run`의 기존 synthetic/toy 경로는 별도로 보존된다. 저장소의
전체 도시 입력·실행기를 배포 패키지의 한 명령에 묶는 작업, fresh-install 최종
수용, 전체 CI·통합·릴리스는 RLS01 및 별도 심사 범위다.
