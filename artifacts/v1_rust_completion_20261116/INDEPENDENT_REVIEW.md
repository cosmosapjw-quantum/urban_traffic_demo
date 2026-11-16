# Rust persistent stage / byte policy 독립 소스 검토

2026-11-16. 기준 commit: `7b5e518f6c098ed831551da4e66d980addf80dd8`; 검토 대상은 해당 commit 위의 현재 작업 diff다. 범위는 `v1_stage.rs`, `v1_journey.rs`, `v1_history.rs`, `v1_road.rs`, `v1_engine.rs` 및 stage/byte-policy 회귀검사다. 코드는 수정하지 않았고 compiler·pytest·실제 시뮬레이션은 독립 검토자가 실행하지 않았다. 아래 판단은 **source-reviewed**이며 실행 PASS가 아니다.

## 판단

exact stage row 순서·ready predicate, road combine의 group별 fsum 입력 순서, coupled tick의 commit 순서에서 신규 P0/P1 결함을 찾지 못했다. byte-policy checkpoint decode에서 reserve 전에 실제 저장량을 제한하지 않는 P1 한 건을 전달했고, 후속 수정의 소스 검토로 닫았다. **미해결 source-review P0/P1은 0건이며 독립 소스 검토는 종결한다.** 실제 build/test·기존 binary 대조·캠페인 성공은 root의 실행 영수증으로 별도 판정한다.

### P1-R1: road checkpoint decode의 packet/part allocation 선행

초기 검토본 `V1Road::read_packets/read_state`는 `record_budget = storage_bytes / size_of::<Part>()`에 따른 행 수 제한만 적용하고, packet registry와 part Vec를 먼저 `checkpoint_vec`로 할당했다. 실제 retained storage 검사 `check_state`는 전체 decode 뒤에 있었다. one-part packet N개라면 part payload 외에 packet registry N개의 저장량이 필요하므로 raw part count가 허용 범위여도 decode 중 byte allowance를 초과할 수 있다. malformed/truncated 파일도 큰 count를 선언해 실제 데이터 읽기 전에 이 할당을 유발할 수 있다. 기존 owner 및 이미 decode한 owner와 공존하는 비용도 고려해야 한다.

최소 수정은 각 reserve 전 누적 decode allocation의 보수 상한을 검사하는 것이다. packet registry, part capacity와 고정 state 배열/latent 비용을 포함하고, decode 실패 시 기존 세 owner를 설치하지 않아야 한다. count-derived ceiling은 보조 sanity guard로 유지할 수 있다. 이 finding은 물리 해석 변경이나 새로운 알고리즘을 요구하지 않는다.

상태: **CLOSED — 소스 수정 확인; 실행 검증은 root 영수증 참조.**

수정본은 `RoadDecodeBudget`에서 `3 × max(current/call-input retained bytes, decoded bytes) + validation scratch`를 검사한다. outer cells/pending/ledger, packet registry, parts와 latent insert의 각 reserve 전에 누적 비용을 확인한다. 두 회귀 사례는 raw count ceiling 이내의 과대 packet-registry/part length를 truncated body에 기록하고 EOF보다 먼저 `checkpoint decode preflight` MemoryError가 나는지, 기존 checkpoint bytes가 유지되는지 검사하도록 작성되었다. 해당 검사 소스는 읽었으며 이 검토자가 실행하지는 않았다.

## 결함을 찾지 못한 구체 경로

| 검토 항목 | 소스 근거와 판단 | 실제 검증의 별도 조건 |
| --- | --- | --- |
| StageQueue 표현 | 256 raw Access rows 단위의 immutable Arc block이다. 행 수를 줄이는 압축·atom 합병이 아니다. 각 row의 leg, mass, born, delay를 그대로 유지하고 공유하는 저장 구조다. | 보고서에서 raw-row 감소 또는 과학적 상태 축약으로 부르지 않는다. |
| ready predicate와 순서 | block min/max는 기존 `born + delay` 연산으로 계산한다. false인 전체 block만 건너뛰며, partial block은 원래 row predicate로 stable filter한다. callback은 block/row 삽입 순서다. `born <= now-delay`로 재결합하지 않는다. | unsorted readiness, 경계 반올림, 여러 block의 retire/fork tests가 이를 겨냥한다. |
| append byte estimate | 기존 payload와 registry capacity를 포함하고 추가 full-tail/registry 성장 여유를 둔다. partial filter로 비2제곱 capacity가 생긴 tail의 growth와 COW 공존도 검토했다. | allocator 전체나 process RSS의 엄밀한 상한 정리라고 확대하지 않는다. |
| ReceiptHistory | raw row/timestamp와 기존 expansion 합산은 유지한다. 새 값은 capacity 기반 storage cache이며 clone/push 후 다시 계산한다. shared prefix를 logical owner마다 세므로 이 부분은 과소계상보다 보수 중복계상 방향이다. | cached bytes가 실제 grow/fork와 일치하는 회귀검사가 필요하다. |
| Road combine | 기존 BTreeMap의 key 순서와 같게 index를 정렬하고 동률에는 원래 index를 사용한다. 따라서 같은 key의 mass/birth `sum` 입력 순서가 같다. 최종 유효 output key는 유일하므로 unstable sort가 동률 물리 순서를 바꾸지 않는다. | 혼합 interval·비연속 동일 key·다양한 지수의 Python oracle 대조 및 실제 이전 checkpoint replay를 요구한다. |
| Coupled rollback | road는 immutable old state에서 candidate를 계산한다. service.finish 이후 journey.finish가 마지막 fallible operation이며, 성공 뒤 road를 설치한다. 실패하면 service를 복원하고 journey pending을 버리며 이전 road/journey committed state를 유지한다. | byte 실패가 prepare/road/finish 각각에서 발생할 때 실제 checkpoint·clock 보존을 검사한다. |
| Legacy codec | StageQueue write는 원래 flattened row 순서/값을 쓴다. block metadata는 serialize하지 않는다. legacy policy의 identity 및 `MFWHOLE1` layout은 유지한다. | 이전 binary가 만든 점유 checkpoint와 matched continuation의 실제 byte 비교를 통과해야 implementation-verified가 된다. |
| Explicit policy binding | `bounded_bytes_v1`을 명시적으로 선택하며 road/journey 할당 quota를 identity suffix에 포함한다. legacy raw-record default는 보존하고 policy가 다른 checkpoint는 binding에서 거절한다. | 다른 policy 사이 바이트 불일치는 예상되는 binding 차이다. 물리 상태 비교와 같은-policy replay byte 비교를 별도 수행한다. |

## 자원 주장과 남은 한계

후속 수정의 stage/history는 `3 × max(dynamic storage, retained call-input storage) + proposal/offer scratch + 64KiB`를 quota와 비교하며, byte policy에서도 raw logical counts를 관측용으로 유지한다. road도 batch 호출의 최초 input이 이후 감소한 현재 상태와 동시에 살아 있을 수 있다는 점을 retained-input charge로 포함하며, state snapshot/candidate 및 source/transfer/interval workspace의 structural allowance를 검사한다. engine은 기존 static construction estimate를 제외한 금액을 road 1/4, journey 3/4로 배분한다. 이 비율은 저장 비용 배분 정책이며 물리 법칙이나 측정된 최적 비율이 아니다.

이 accounting은 std allocator의 모든 내부 비용, 임의의 user-retained snapshots, 전체 Python/Rust process peak를 완전히 세는 정리가 아니다. 코드의 `storage_config.scope`와 별도 process limit/RSS 계측이 이 한계를 명시한다. 실제 8GiB RSS·7,200s wall 및 원래 100k 수요의 3개 도시×3회 24h gate를 바꾸지 않는다. byte policy로 예전 raw-count failure clock을 넘는 것은 표현별 resource decision 변경이며 물리 exactness나 캠페인 수용의 증거 자체가 아니다.

## 검토 시점 소스 식별

아래는 초기 독립 검토본의 SHA256이다. P1 수정 후 바뀐 파일은 후속 절에 별도로 바인딩해야 한다.

| 파일 (`crates/metroflow-rust/src/`) | SHA256 |
| --- | --- |
| `v1_stage.rs` | `d3adc602aebfbe319f3df3ce1b2b69fdb72e09be406f5c6c34c4e70d14bbf94e` |
| `v1_journey.rs` | `6739df0e2c360e4351162cecff0fedae07336ece2c1e2c5dd25adf68b4dcbf4a` |
| `v1_history.rs` | `2c5923f26edea2d295e44a8fff2cf36074c443a50904ec8cfa8caa627d21ad1b` |
| `v1_road.rs` | `a5a4f92738fc56ee5c4e4234d0cfe762341fb9297d8a4343120abf9de67bc8a9` |
| `v1_engine.rs` | `ad0dd8ab99dd5bea79054d065a9af5f0fa39a49f68b63d4e28afc7eb409cfe12` |

신규 검사 소스는 `tests/v1/test_native_stage_storage.py` (`8a88e87e88d84f7bf7743f8a7082d113f5271902e3f428dbbdc6ad06fedcfb25`), `test_native_byte_budget.py` (`f40a26a898fe2bac0e97a963484cf172000099272d60a9c98ac6fcf3116d2416`), `test_native_storage_policy.py` (`8d8fcee6ceea9c47f90a5bab4201dc38c75fef70d4e13e5795fae2f4701bfc26`)다. 실행 결과는 root의 실제 build/test 영수증에서 별도로 확인한다.

R1 및 retained-input 후속 수정 검토본 SHA256: `v1_road.rs` = `5da6d9a06d2feb634e28a00b3894046727024815bc3a877ad1821588a69558d5`, `v1_journey.rs` = `729f94dde081d3a9b053e164a66ad9c40a89246db894e10df7446174b362abab`, `tests/v1/test_native_byte_budget.py` = `f160d432e6eb0e20c437c4e9693369e1100ded23c66e0ee1e8d9a89c9943f209`.
