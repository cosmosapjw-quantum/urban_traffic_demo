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

과학 계산 thread 수는 명시적으로 기록한다. Rayon worker 수를 늘려도 모든 경로가
빨라지는 것은 아니므로 기본은 1이며, FIFO·합산·receipt 순서와 재개 결과를 유지한다.
`METROFLOW_V1_ROUTING_BACKEND`는 frontend의 고정 운행 경로 조회에 적용되고,
전체 달력의 OD 경로 탐색은 `rust_whole` 내부 Rust 구현이 담당한다.

## 결과 해석과 남은 배포 범위

- `EXECUTED_FOR_REVIEW`는 요청한 구간 실행이며, 최종 수용 판정과 다르다.
- 마지막 유효 checkpoint와 `simulated_s`는 차단 전에 완료된 진행을 나타낸다.
- owner 저장 예산, 주소공간 제한과 측정 peak RSS는 서로 다른 계측이다.
- 수용에는 세 도시 각각 세 번의 24시간 실행, 장부·재개·refinement 검토와
  case당 7,200초/8GiB 기준을 함께 충족해야 한다.

설치된 `metroflow-v1 run`의 기존 synthetic/toy 경로는 별도로 보존된다. 저장소의
전체 도시 입력·실행기를 배포 패키지의 한 명령에 묶는 작업, fresh-install 최종
수용, 전체 CI·통합·릴리스는 RLS01 및 별도 심사 범위다.
