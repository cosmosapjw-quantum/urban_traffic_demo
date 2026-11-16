# V03 Rust 전환 연구 루프 — 2026-11-16

이번 단위는 V1의 f64 합법 경로 탐색을 persistent Rust 객체로 연결하고, 전체 factorized calendar를 Rust에 보관하는 첫 이식이다. Python frontend-only는 최종 목표이며 현재 Python은 달력 생성과 물리·서비스 tick을 계속 소유한다. 전체 교통 활성화와 V03 수용은 남아 있다.

## 기준과 기존 작업의 회수

- 기준 코드: `58debca4b967eef2af237898ff3ea27c7596180f`.
- 실제 로컬 원본: `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo`. 수정된 사용자 파일은 보존했다. 이번 실행은 `/home/cosmosapjw/urban_traffic_rust_20261116`의 별도 worktree에서 수행했다.
- 회수한 과거 자료: `MetroFlow_Rust_Default_Engine_Compiled_Package_20260824.patch`, SHA256 `7d89e8be20339709a9c0dc894a26dc7db75bdc0d857637ffb30f7bc7fe4a1326`. 17개 파일·6,371줄이며 주 내용은 아키텍처, 실행계획, 감사·검증 도구다. Rust 엔진 구현 완료 증거로 채택하지 않았다.
- 당시 설계의 Rust-owned state / coarse Engine calls / Python frontend / explicit oracle 원칙을 현재 승인된 방향과 연결했다. 구버전의 14개 PR 계획을 새 DAG로 자동 편입하지 않았다.
- 기존 `crates/metroflow-rust`의 flow/routing/agent 커널은 V1과 미연결이고 주로 f32 기반이다. V1의 f64·합법회전·loopless 계약을 보존하는 별도 모듈을 호환 crate 안에 추가했다.

## 원인과 설계

`ReleaseDriver`는 전체 leg 수가 20,000을 넘으면 열거 전에 거절한다. 그 이후에도 service max_runs, Python route registry, helper의 물리 모델, 공유 service/packet state와 기록 예산이 있다. Rust 선택만으로 이 제한이 모두 해소되지는 않는다.

경로 탐색은 기존과 같은 비음수 비용 `c_i`와 합법 후속 링크를 사용한다. 도착점으로의 potential은 목적지 도착 링크에서 `V_i = c_i`, 나머지 링크에서 `V_i = c_i + min_j V_j`이고 도달 불능은 +∞다. 후보 탐색은 물리 노드 재방문 금지, lexicographic tie, expansion budget=2000 및 truncated 판정을 유지한다. 기존 `LegalRouteCache`의 노드 재방문 가능한 최단 walk를 대체 oracle로 사용하지 않았다. Rust는 그래프와 유한 destination LRU를 보유하며, batch 검색 동안 GIL을 해제한다.

달력은 각 leg의 ID/cohort, parent, dwell, 사람·차량·화물량, 원본 activity/law metadata와 departure profile을 보존한다. 표준 cN/out/home 문자열은 가역 정수로 저장하고 임의 ID는 원문으로 보관한다. profile 적분은 기존 구간 겹침 식으로 계산한다. 수량 합계는 Neumaier 보상합이며 Python math.fsum과의 일반적 bitwise 동등성을 주장하지 않는다. 수치 비교 허용오차와 실제 결과는 테스트·영수증에 기록했다.

현 factorized generator의 outward-before-return 순서를 입력 계약으로 사용한다. 임의로 재배열된 leg 스트림은 별도 지원 대상이다. 페이지 실패 시 leg/ID/총량 커밋은 원자적이며, 어댑터에서 미리 intern한 metadata까지 되돌리는 transaction은 아니다. byte_budget는 영속 저장량의 회계 추정이며 Python/FFI 페이지와 재할당 transient를 포함하는 프로세스 RSS 상한이 아니다. 계측은 별도 8 GiB address-space guard와 300초 외부 timeout을 사용했다.

## 구현과 한정 검증

- `v1_routing.rs`, `native_routing.py`: f64 Rust graph, bounded LRU, single/batch search. `routing_backend.py`에서 `METROFLOW_V1_ROUTING_BACKEND=rust`로 명시 선택. 기본 python_oracle과 silent fallback 없이 구별한다.
- `release_runtime.py`와 `release_services.py`: 실제 V1 car/helper와 service 준비 경로에 연결했다.
- `v1_calendar.rs`, `native_calendar.py`: 전체 스트림의 native 등록, profile/metadata 공유, 초기 zero progress arrays, 요청량 적분, identity binding, 실패 시 보존.
- `test_native_runtime_parity.py`: 실제 native 호출을 확인하면서 car/bus/freight 공유 모델의 120초 상태·장부 및 125초 checkpoint/resume 결과를 Python oracle과 대조한다. 이 fixture 실행은 전체 도시 24시간 수용과 구분한다.
- 독립 검토에서 유한 확률/수량의 합계 overflow가 NaN 검사를 우회하는 반례를 발견했다. 명시적 유한 총량 검사와 회귀 사례로 수정했다.
- 최초 remote rebuild는 전송된 파일 mtime이 기존 빌드보다 과거여서 이전 확장을 재사용했다. V1RoutingGraph import 실패를 환경/빌드 식별 오류로 기록하고, 소스 mtime 갱신·재빌드 후 해결했다. import 실패를 행동 검증의 RED로 세지 않았다.
- sandbox에는 Rust/pytest가 없어 native 실행은 실제 로컬에서 수행했다. backend 오타를 기존 코드가 조용히 수용하는 행동 반례는 수정 전에 직접 확인했다.

## 재현

```bash
cargo build --release --locked -p metroflow-rust
# 위 빌드 확장을 해당 Python 환경에 설치한 뒤
PYTHONPATH=src python -m pytest -q tests/v1/test_native_routing.py tests/v1/test_native_calendar.py tests/v1/test_native_runtime_parity.py tests/v1/test_routing_backend_selection.py tests/v1/test_release_runtime.py tests/v1/test_release_services.py tests/v1/test_joint_release_runtime.py
python tools/measure_v1_native.py --mode routing --out routing.json
python tools/measure_v1_native.py --mode calendar-python --out calendar-python.json
python tools/measure_v1_native.py --mode calendar-rust --out calendar-rust.json
```

원본 계측의 최종 파일은 `final-routing.json`, `final-calendar-python.json`, `final-calendar-rust.json`이다. 동일 실제 하천 도시·schedule identity로 대조한다. native binary 및 소스 SHA256, Python/rustc/OS/CPU와 관측 RAM을 보존한다. 각 성능 계측은 한 번의 bounded measurement이며 전체 3×3 campaign 분포가 아니다. 다른 부하가 실행 중인 사용자 호스트이므로 성능 배율을 보편 상수로 사용하지 않는다.

## 최종 실제 로컬 계측

| 항목 | Python oracle | Rust | 해석 |
|---|---:|---:|---|
| 같은 256개 실제 도시 경로 질의 | 2.1696 s | 0.0643 s | graph 준비 포함 33.74배; 전체 runtime 배율 아님 |
| 전체 5,093,765 legs 보관 peak RSS | 1,527,717,888 B (1.423 GiB) | 724,267,008 B (0.675 GiB) | 프로세스 peak RSS 52.59% 감소 |
| 전체 달력 등록 | 20.8679 s | 30.8480 s | Rust 등록이 1.48배 느림 |

환경은 Python 3.12.3, rustc 1.99.0, Ryzen 9 5900X, 관측 RAM 33,549,770,752 B, scientific threads=1이다. Rust 등록 어댑터도 Python에서 leg를 생성하고 페이지별 FFI 변환·검증을 수행하므로 이 단계를 제거하는 후속 이식이 필요하다. 세 비용의 개별 비중은 아직 profiling하지 않았다. 원본 JSON의 `rss_limit_bytes`는 구현상 RLIMIT_AS(address space)의 설정값이며, RSS는 별도 측정치다.

동일한 코드에서 관련 7개 파일의 **44 tests passed**, 계획·local campaign CLI의 **12 tests passed**를 확인했다. 최종 benchmark source SHA256은 게시 파일과 일치한다. 빌드 바이너리 SHA256은 `f5738ba9c2b71f7e926a2487788fd65dc4f329cc7a41567f443df637c933625d`이다. 전체 CI·통합은 사용자 지시에 따라 보류했다. 3case×3회24h는 전체 공유 runtime 활성화가 아직 구현되지 않아 실행하지 않았다.

## 남은 이식 순서

1. factorized schedule 열거를 Rust로 이동해 Python leg 생성·페이지 변환 비용을 제거한다. 현재 어댑터를 일반 스트림 reference로 보존한다.
2. 같은 물리 수송 계보의 packet/kinetic state와 bus/freight/journey 장부·접근/귀환 eligibility를 Rust가 함께 소유하도록 옮긴다. Rust calendar에서 Python 전체 tuple을 재구성하지 않는다.
3. 전체 calendar를 한 공유 road runtime에 연결한다. 메모리 예산은 실제 native 활성 상태 계측으로 정하고, 수요 축소나 독립 batch 실행 결과 합산을 사용하지 않는다.
4. 같은 입력의 상태·checkpoint·refined dt를 대조하고, 동결 candidate에서 원래 3case×3회24h 수용시험을 실행한다.

PLAN v1.1.18은 사용자의 현재 지시로 기존 pure-Python 제한을 교정했다. CPU·과학 계약·10만 주민·8 GiB·2시간 기준과 전체 CI/통합 보류는 유지한다. DAG **19/21 (90.5%)**, V03 BLOCKED를 유지한다.

## 참고 원전

- PyO3 0.23.4 conversion traits: https://pyo3.rs/v0.23.4/conversions/traits.html
- PyO3 0.23.4 Vec conversion 구현: https://docs.rs/pyo3/0.23.4/src/pyo3/conversions/std/vec.rs.html

FFI 변환이 Python 객체 생성을 동반한다는 설계 근거로 사용했다. 이번 성능 주장은 위 문서가 아니라 실제 실행 영수증에 근거한다.
