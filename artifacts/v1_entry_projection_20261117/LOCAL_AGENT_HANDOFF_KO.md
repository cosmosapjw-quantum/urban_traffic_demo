# Local agent handoff: 보존적 진입시간 투영 이후의 V03

아래 지시문 전체를 local agent에게 전달한다. 실제 구현·검증된 후보를 이어받는
작업이며, 전체 시뮬레이터를 새로 설계하거나 일반적인 감사만 반복하는 작업이 아니다.

## 복사해서 전달할 지시문 (GitHub 게시본)

저장소 `cosmosapjw-quantum/urban_traffic_demo`의 V03 후속 작업을 수행하라.
**원격 인수 위치는 `origin/research/conservative-kinetic-closure-20261117`이다.**
기존 Git 작업물 또는 체크포인트를 덮어쓰지 말고 아래 방법으로 코드를 수령하라.

```bash
# 아직 clone이 없다면 독립 경로에 새로 받는다.
git clone --branch research/conservative-kinetic-closure-20261117 --single-branch \
  https://github.com/cosmosapjw-quantum/urban_traffic_demo.git urban_traffic_handoff_20261117
cd urban_traffic_handoff_20261117

# 기존 clone을 사용하는 경우에는 대신 다음을 실행한다.
# git status --short                    # 로컬 변경이 있으면 보존 후 분리
# git fetch origin refs/heads/research/conservative-kinetic-closure-20261117
# git switch -c research/entry-projection-agent-20261117 FETCH_HEAD

# 실제 인수 후보가 기준 구현 commit을 포함하는지 검증한다.
git merge-base --is-ancestor f47bf6a3e3a9e7b078bfa4111cb7a5510c68c12c HEAD
printf 'HEAD=%s\n' "$(git rev-parse HEAD)"
test -f artifacts/v1_entry_projection_20261117/RECEIPT.json
test -f docs/v1/CONSERVATIVE_MARK_BLOCK_NEXT_KO.md
```

원격 브랜치가 생성된 이후에는 이를 기준으로 fetch/pull하며, 다른 작업자의
임의 최신 `main`으로 전환하지 않는다. 로컬 분기점이 생긴 경우 `git pull`
자동 merge를 하지 말고 `git fetch` 후 차이를 검사한다. 실행된 원형 candidate는
`f47bf6a3e3a9e7b078bfa4111cb7a5510c68c12c`; 이 인계문 수정은 별도
후속 commit이다. 최신 `HEAD`·tree와 `RECEIPT.json`의 측정 source SHA를 구분하라.
GitHub 원격에 없는 로컬 `.bin` 체크포인트를 원격에서 받은 것으로 주장하지 말라.
현재 사용자는 최신 보고서의 선택지를 원래 모델 동기에 맞게 선택하고, 이론 개선을
코드에 이식하는 일을 승인했다. 선택지는 A이며, `entry_projection_support_v1`이
이미 Python/Rust 실제 경로에 구현돼 있다. 원래 전체 수요·주민 100,000·3도시 각
3회 24시간 목표를 유지하라. 추가 승인 질문으로 이 결정을 되돌리지 말라.
기존 사용자 지침에 따라 전체 저장소 CI, PR merge, main 통합, release와 최종
ACCEPTED 심사는 아직 별도 단계다. 해당 작업을 자동 실행하지 말라.

### 1. 인수 위치와 먼저 읽을 근거

- 원격 추적 기준: `origin/research/conservative-kinetic-closure-20261117`.
- 원격에서 받은 후 독립 agent 작업 브랜치를 생성하여 변경한다. 다른 로컬
  브랜치에 미커밋 변경이 있으면 보존한다.
- 원본 기준 commit: `0b9caa8cc60a3ba087722e0360b997c5dfb61d62`.
- 실제 구현·실측 후보 commit: `f47bf6a3e3a9e7b078bfa4111cb7a5510c68c12c`.
- 다운로드한 `HEAD`와 tree는 `git rev-parse`, 실제 실행 identity는
  `artifacts/v1_entry_projection_20261117/RECEIPT.json`의 source SHA-256으로 확인한다.
  인계 갱신 자체가 원형 후보의 실행 검증을 대체하지 않는다.
- 이전 PC의 `/home/cosmosapjw/urban_traffic_projection_20261117`는 전달 검증에
  사용한 로컬 복사본이며, 다른 agent 장치에 존재한다고 가정하지 말라.
- 기존 `/home/cosmosapjw/urban_traffic_rust_20261116` 및
  `/home/cosmosapjw/urban_traffic_v03_20261116`의 소스·가상환경·체크포인트가
  동일 호스트에 있다면 보존하고, 새 바이너리를 기존 venv에 설치하지 않는다.
  다른 호스트라면 Python/Rust 의존성을 별도로 설정하고 환경을 영수증에 남긴다.

다음 파일을 읽고 이어서 실제 construction/실행을 시작하라.

1. `AGENTS.md`, `docs/v1/PLAN.json` — 현재 실행 권위와 변경된 수치 정책.
2. `artifacts/v1_entry_projection_20261117/RECEIPT.json`, `AUDIT_REPORT_KO.md` —
   실제 테스트, 합성 비교, 도시 실패와 검증되지 않은 범위.
3. `docs/v1/CONSERVATIVE_ENTRY_PROJECTION_DESIGN_KO.md`,
   `CONSERVATIVE_ENTRY_PROJECTION_THEORY_KO.md` — 모멘트·경계·오차 계약.
4. `docs/v1/ENTRY_PROJECTION_RESOURCE_FOLLOWUP_KO.md`,
   `CONSERVATIVE_MARK_BLOCK_NEXT_KO.md` — 이번 실패가 판별한 다음 구현 방향.
5. `VALLEY_PILOT.json`, `PYTHON_RUST_COMPARISON.json` 및 도시 prefix 비교 결과.

### 2. 이미 완료된 것과 실제 실패

새 정책은 동일 receiving cell/admission step/target 안의 category별 질량,
birth moment와 entry first moment를 보존한다. immediate movement support 변화와
원래 point 시각을 보호한다. 동일 시각 atom은 기존 exchangeable packet으로
남긴다. `h=0`은 기존 정확 경로이며 양의 폭은 정책/폭이 다른 checkpoint binding을
사용한다. Python 88개, native 164개, Rust 내부 projection 단위검사 7개가 각각
통과했다. 이 숫자들은 중첩된 suite이므로 독립 검사 수로 합산하지 말라.

Valley 전체 calendar(918,450 legs, 생략 0)를 `dt=10 s, h=1 s`로 실행했다.
26,100초 목표의 한정 실행은 **26,010초에서 BLOCKED_RESOURCE**였다.
이전 exact guard의 25,650초보다 360초 더 진행했지만 병목은 해결되지 않았다.
실패 사유는 `phase=transfer candidates`, required 4,538,183,888 B,
budget 4,538,183,714 B였다. peak RSS는 3,176,062,976 B, wall은 약 285.7 s다.
6 GiB native/8 GiB process 한도는 유지됐다. 마지막 유효 도로 상태는 약
10.53M Parts/14.1k packets였고, 마지막 검증된 투영은 5.06M→3.54M Parts였다.

`transfer candidates`는 모든 served category의 EventRow/incoming Part/Mark를
만드는 단계다. 현재 투영은 junction transfer를 모두 만든 뒤 실행하므로,
실패한 proposal은 그 step의 압축에 도달하지 못했다. 단순히 h를 크게 하거나
support 경계를 지우는 대응을 하지 말라. 이 자료는 물리적 불가능성 정리가 아니다.

추가 범위 감사: 918,450개 leg 중 610,820개(레코드의 66.51%)는
`kind==0 && !assigned`로 집계된다. 도로 leg는 304,368개, 내부 지연 leg는
3,012개, 별도 bus/freight 배정이 있는 나머지 kind0은 250개다. unsupported도
calendar와 requested 장부에는 남고, 수요 발생 후 pending으로 유지된다.
따라서 전 수요 보관을 전 수요의 물리적 이동 지원이라고 표현하지 말라.
이 비율은 인구·차량량의 비율이 아니며 A 정책이 새로 만든 현상도 아니다.
새 실행의 과학적 해석에 앞서 mode/endpoint/접근점/도로연결/서비스 미배정의
원인별 레코드와 persons/vehicles/cargo 가중량을 분해하라. 지원되지 않는
수요를 임의 자동차 경로로 바꾸거나 삭제하지 말라. 필요한 입력·서비스 모델
수정과 저장구조 개선은 별도 근거로 판단한다.

동일 25,500초 prefix의 h0/h1 대조도 실제 완료했다. peak records는
5,304,240→4,039,278, RSS는 973,053,952→860,958,720 B였다. 완료 차량량의
endpoint 차이는 -0.00103624881349 veh이며 source 양과 intent first moments는
동일했다. 전역 시간곡선·모든 category별 오차의 상한으로 확대하지 말라.

### 3. 다음 구현 단위: 시간 압축 이후의 조성 복제 제거

첫 목표는 입출력·순서·장부를 보존하면서 transfer workspace와 반복되는
category block의 복제를 줄이는 것이다. 두 수준을 분리해 작업하라.

**작은 선행 단위:** EventBatch/common-header 또는 청크화된 event 저장으로
반복 header와 큰 Vec 재할당 중복을 제거하라. 모든 tag, source/destination,
질량, birth/time bit와 iteration order, 기존 checkpoint wire 의미를 보존해야
한다. 계상식은 실제 변경된 소유·수명·capacity에서 다시 유도하고 allocation
직전 검사와 rollback을 유지한다. 기존 계수만 낮추거나 guard를 우회하지 말라.
이 상수배 최적화만으로 전일 성공을 약속하지 말라.

**후속 핵심 단위:** A 위에서 생성 계보를 보존하는 immutable mark-block
공유를 구현하라. 부분 서비스의 동일 계수를 category 전체에 적용하는 사실을
사용해 `(block reference, scale, route view, entry-moment data)`로 표현한다.
실수 산술 선형동치와 f64 bit identity를 구별하라. 스칼라 계수를 합성하면
곱셈 순서가 바뀔 수 있으므로 기존 연산 순서를 보존하거나, 명시적으로 이름을
붙인 수치 정책과 오차 검증을 적용해야 한다. tag/category 삭제, 작은 양의
질량 cutoff, route offset 혼합, birth moment 손실은 허용하지 않는다.
서비스·journey receipt에서 즉시 전체 행으로 다시 전개하면 병목이 옮겨갈
뿐이므로 road→event→journey 소비 경로와 checkpoint를 함께 추적하라.

새 구조의 비용은 logical rows, 실제 고유 allocation bytes, fan-out 수,
expression depth, materialization 비용을 구분해 측정하라. 새로운 실제
category/support 다양성까지 일정 메모리라는 보장을 만들어내지 말라.
새 반례를 추가한 후 구현하고 의미 있는 좁은 회귀만 실행하라. 이미 통과한
검증을 이유 없이 전부 반복하지 말라.

### 4. 재현 환경과 명령

아래는 이미 사용한 격리 실행 방식이다. 원래 가상환경의 실행기·의존성은
읽기 전용으로 재사용하고, Rust 산출물과 import 경로는 현재 worktree에 둔다.

```bash
# clone/fetch 후 확인한 새 작업 디렉터리에서 실행한다.
cd "$(git rev-parse --show-toplevel)"
# 동일 PC의 기존 venv가 있다면 재사용할 수 있다. 없다면 새 venv를 구성한다.
TASK_PY=/home/cosmosapjw/urban_traffic_rust_20261116/.venv/bin/python
TASK_CARGO=/home/cosmosapjw/.cargo/bin/cargo
PYO3_PYTHON="$TASK_PY" "$TASK_CARGO" build --release --offline
mkdir -p native_binding
cp target/release/lib_metroflow_rust.so native_binding/_metroflow_rust.so
PYTHONPATH=native_binding:src "$TASK_PY" -c 'import _metroflow_rust; print(_metroflow_rust.__file__)'
```

최초 검증 바이너리 SHA-256은
`b34832c7803e5ca2be5e7c1a1f83c2d2a83faf29ca7d7956e4943a01f1ce57a3`다.
새 코드의 새 build는 별도의 source/binary hash로 기록한다. 과거 결과를 새
바이너리의 실행 결과로 재명명하지 않는다. 공유 host 부하를 확인하고 과학
worker는 1개로 유지한다. 다른 연구 프로세스를 종료하거나 설정을 바꾸지 않는다.

관련 regression 예시는 다음과 같다. 수정한 의존성에 맞게 선택하라.

```bash
PYTHONPATH=native_binding:src:tests/v1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  "$TASK_PY" -m pytest -q \
  tests/test_entry_projection.py tests/v1/test_entry_projection_native.py \
  tests/v1/test_native_retained_accounting.py tests/v1/test_native_byte_budget.py \
  tests/v1/test_native_event_resolution.py tests/v1/test_native_whole_driver.py \
  tests/v1/test_local_campaign_cli.py tests/test_v1_plan.py
```

동일 도시·동일 시간창 대조는 `--worker`를 명시해야 한다. 일반 frontend의
`--run-local`은 정해진 전체 campaign을 실행하므로 `--horizon-s`만으로 단기
실행을 선택했다고 착각하지 말라. 매 실행은 다른 출력 label을 사용한다.

```bash
PYTHONPATH=native_binding:src METROFLOW_V1_ROUTING_BACKEND=rust \
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  "$TASK_PY" tools/run_v1_local_acceptance.py \
  --worker --run-local --case valley_weekday_s7 \
  --engine-backend rust_whole --native-threads 1 \
  --storage-policy bounded_bytes_v1 --entry-projection-width-s 1 \
  --step-s 10 --horizon-s 26100 --label valley_next_h1 \
  --out artifacts/v1_entry_projection_followup/local_probe
```

이전 blocked checkpoint는 정책·폭·source/driver binding이 일치할 때만
읽는다. 정책을 바꾼 새 실험은 새 초기 상태에서 시작한다. save/load로 호출
경계를 바꾸면 call-input event buffer의 수명이 달라질 수 있으므로,
checkpoint 직후 한 tick의 자원량을 원래 장시간 호출과 동일하다고 주장하지 말라.

### 5. 과학 비교와 전체 수용

먼저 exact가 가능한 공통 도시 prefix에서 h=0,1,.5,.25를 비교하라. source,
matrix, dt와 수요는 같아야 한다. 완료곡선, class/destination별 flux,
대기·점유, vehicle/person seconds, birth/entry 모멘트, resource 비용을 기록한다.
그 다음 h를 고정하고 dt를 10→5초로 줄여 독립 비교하라. checkpoint identity가
다른 상태를 교차 적재해서 초기조건을 맞췄다고 주장하지 말라.

`local_w1_bound_veh_s`는 국소 투영 비용 상한이며 global travel-time 오차가
아니다. 진단은 checkpoint 상태도 아니며 rollback된 proposal의 값일 수 있다.
보존 문턱은 PLAN의 mass 1e-9, residence 1e-8 그대로다. 관측 정확도는 원래
gate의 문턱을 적용하며, 없는 문턱을 결과를 본 뒤 통과시키기 위해 신설하지 말라.
원래 gate가 이 정책의 특정 관측량을 다루지 않는다면 수치와 판단 근거를
명시하고 그 관측량은 미수용으로 남겨라.

한정 비교와 자원 증거가 충분해지면 원래 frontend의 캠페인을 실행한다.

```bash
PYTHONPATH=native_binding:src METROFLOW_V1_ROUTING_BACKEND=rust \
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  "$TASK_PY" tools/run_v1_local_acceptance.py --run-local \
  --engine-backend rust_whole --native-threads 1 \
  --storage-policy bounded_bytes_v1 --entry-projection-width-s 1 \
  --matrix scenarios/v1/release_matrix.json \
  --out artifacts/v1_entry_projection_followup/full_campaign
```

위 h=1은 현재 후보 폭이다. 비교 근거로 다른 폭을 선택하면 명령·identity·PLAN과
영수증에 그 결정을 먼저 기록하라. 정해진 3도시×3회 86,400초, 중간 저장/재개,
dt=5초 prefix, 실행당 7,200초·8 GiB gate를 유지한다. 첫 실패의 checkpoint와
원인을 보존하고 같은 후보의 의미 없는 반복을 중지한다. 한정 실행 성공을
24시간 성공으로 확대하지 말라.

### 6. 반환 계약과 종료 조건

실제 수정 코드, 필요한 최소 테스트, source/commit/binary identity, 명령과
종료코드, 측정값, 마지막 유효 checkpoint 위치, 오류 분류, 다음 결정을 반환하라.
이론 오류·수치 오류·구현 오류·자원/환경 실패를 구별하라. 24시간 0/9,
V03 BLOCKED, 구현·한정 실행 19/21, 최종 ACCEPTED 5/21은 새 실제 근거 없이는
바꾸지 말라. 성공하면 변화의 의미와 측정 범위를 보고하고, 실패하면 구체적인
다음 construction 하나를 남겨라. 이미 나온 no-go를 반복하거나 문서 감사만
재귀적으로 늘리지 말라.
