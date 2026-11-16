# Runtime storage 예산의 독립 수명 검토

2026-11-16. 검토 worktree: `urban_traffic_runtime_budget`; 기준 commit `27e426fc64452ae2492828653f94f2506b8881fc`. 현재 실행 중인 기존 campaign 후보와 분리된 작업이다. 범위는 constructor의 임시 추정치와 실제 retained footprint 구분, 알려진 동시 dense state/scratch/event 수명, 그 accounting guard다. 이전 stage/packet/event-clock 검토를 재개하지 않는다.

상태: **SOURCE REVIEW CLOSED — 아래 freeze 소스에서 열린 blocking finding 없음. Native 재시험과 실제 campaign 결과는 별도 gate다.** 검토자는 구현 코드를 수정하거나 native 테스트·실제 campaign을 실행하지 않는다. 전체 6GiB accounting 예산과 8GiB process/RSS 수용조건은 유지한다. allocator/RSS 전체를 정확히 상계하는 정리를 주장하지 않는다.

실제 `final_campaign/river_weekday_s17.run1.json`은 t=25,210s에서 `native journey stored/working byte budget`으로 중단했다. 기존 construction/snapshot estimate는 5,674,574,036 bytes, 각 owner quota는 383,938,454 bytes, peak RSS는 2,172,362,752 bytes다. 마지막 유효 journey dense arrays는 163,000,480 bytes이며 dynamic stage/history는 0이다. 실패 prepare의 generated counters는 entering 574,738, internal 7,912이고 commit된 stage rows는 없다. 낮은 RSS 하나만으로 guard가 잘못됐다고 결론 내리지 않는다. 해제되는 constructor 자료와 retained runtime 자료의 수명 차이를 추적하는 것이 교정 근거다.

## 확인한 수명

| 자료 | 실제 동시 수명 | 예산에 필요한 구분 |
| --- | --- | --- |
| Constructor router | graph, pair cache, lookup/index는 생성 중 사용하고 engine이 보유하지 않는 부분은 build 종료 때 해제된다. persistent paths/metrics 등 engine으로 이동하는 필드는 남는다. | construction peak estimate를 그대로 retained runtime bytes라 부르지 않는다. 이동한 자료와 해제된 자료를 field별로 구분한다. |
| Journey dense arrays | released, completed, birth, ReceiptHistory 참조 배열. 정상 prepare/capture에서 initial_state, caller input, committed owner, pending candidate 또는 result가 공존한다. | 정상 경로의 4배 dense reserve는 근거가 있다. history/stage의 공유 block payload는 별도 dynamic accounting이며 dense 배열과 혼동하지 않는다. |
| Service dense arrays | initial_state, caller input, committed owner, tick rollback service_before에 더해 journey.finish의 before/after people·freight 부분 clone이 공존한다. | service 전체 dense 6배는 정상 peak를 보수적으로 덮는다. last_events, Sink 문자열, sink_mass map은 이 배수 밖이다. |
| Service last_events | tick 중 caller input의 events, owner의 이전 last_events, 새 road events가 공존한다. capture 때 input/current/result의 event Vec가 공존한다. | 현재 tick event 수만 보지 않고 더 큰 이전/input capacity를 포함한다. road의 현재 event workspace와 중복되는 부분은 명시하되 과거 events를 누락하지 않는다. |
| Sink 변환 | road events가 살아 있는 동안 Sink Vec와 service.finish에 넘기는 clone, 각 String payload와 sink_mass HashMap의 Vec<f64>가 공존한다. | EventRow bytes만 세어 문자열·그룹화 scratch를 지우지 않는다. |
| per-call tag_indices | advance_owned_joint는 모든 tag 문자열을 clone한 HashMap을 호출 동안 보유한다. | constructor router cache 해제와 별개다. bucket capacity와 String payload를 포함한다. |
| validate_bundle | stage별 HashMap<usize,Sum> 및 Sum의 expansion Vec를 만들고 scalar map으로 변환한다. active_by_tag의 source map을 순회하며 active target map을 만든다. | 변환 중 구/신 map의 공존 및 expansion payload를 포함한다. scalar entry 개수만 세지 않는다. |

`Vec.capacity()`와 `String.capacity()`는 실제 소유 allocation의 중요한 관측값이지만 HashMap bucket/allocator metadata, Arc allocation header, 공유 payload의 identity와 동시 임시 allocation을 자동으로 포함하지 않는다. 단순 length×struct-size와 실제 capacity 기반 계상, 명시적 보수 reserve 및 OS RSS 관측을 구분한다.

## RUNTIME-R1: 실패 후 restore의 다섯 번째 Journey dense copy

검토 시작본의 `NativeWholeEngine::advance`는 `result=self.capture()` 뒤 `validate_bundle(result)`가 실패하면 result를 유지한 채 `self.restore(input)`를 호출한다. 이 순간 initial_state, caller input, current owner, result, restore가 새로 clone하는 input의 **5개 dense copy**가 잠시 공존할 수 있다. 정상 경로의 4배 reserve만으로 이 실패 경로까지 덮는다고 주장할 수 없다.

최소 교정은 실패 분기에서 `drop(result)` 후 restore하거나 해당 실패 경로의 추가 dense copy를 reserve에 포함하는 것이다. 이 finding은 물리 전이나 수치 계산을 바꾸지 않는다. engine 담당자와 root에 전달했다.

상태: **SOURCE-CLOSED** — 현재 `advance`의 검증 실패 분기는 `drop(result)`를 수행한 뒤 `restore(state)`를 호출한다. 실행 회귀 결과는 root의 native 로그로 별도 확인한다.

## RUNTIME-R2: commit된 상태의 재로드 검증 headroom

`BUDGET_LOAD_PROBE.json`의 70MiB 사례는 first/fresh engine의 fixed reserve 67,294,229 bytes와 shared pool 6,106,091 bytes가 동일하다. t=31s의 마지막 commit 상태는 internal 60,000행, dynamic journey 1,971,912 bytes이고 저장은 성공한다. 그러나 fresh load의 전체 검증 admission은 74,687,434 bytes를 요구하여 같은 73,400,320-byte budget에서 실패한다. 이는 수요·물리 ledger 실패가 아니라 commit과 checkpoint 검증 사이의 resource 계약 불일치다.

현재 tick의 prepare/finish guard는 journey-local scratch를 포함하지만 whole-engine `validate_bundle`의 stage `Sum` partials/maps를 위한 row-wise scratch는 별도다. 후속 실패가 반환한 마지막 유효 상태라도 이 검증 workspace를 확보하지 못할 수 있다. 최소 보수 교정은 commit 전에 재로드/검증 headroom을 admission하거나, 검증 자료구조의 실제 성장마다 allocation 전에 budget을 확인하는 것이다. 전자는 마지막 유효 시간이 더 이르게 끝나는 것을 허용하되, 그 상태의 fresh load와 동일 시간 replay가 같은 budget에서 가능해야 한다. 단순히 load의 검증 guard를 제거하거나 사후 검사로 옮겨서는 안 된다.

같은 조건은 wire 재구성의 일시 저장에도 적용된다. Road uniform packet은 decode 중 `Part48` 원본과 `Core32` 저장 배열이 공존한다. 따라서 최종 retained road bytes만으로 decoder의 선행 admission을 자동 보장하지 못한다. 현재 packet 경계를 보존할 때 충분한 decoded footprint 상한은 retained road bytes에 `48 × max_packet_parts`를 더하고, 별도 decoder validation `16 × total_parts + 32 × (packets + cells)`를 포함하는 것이다. Journey의 flattened stage/history 재구성 capacity 역시 현재 capacity와 별도 비교해야 한다.

상태: **SOURCE-CLOSED.** Root는 이 R2 후보의 native 250 tests 통과를 보고했다. 검토자는 해당 실행을 반복하지 않았으며, 아래 후속 sequential-history 변경의 재빌드는 별도다. 전체 engine 경로는 Journey의 이전 owner와 history counters를 clone 없이 move-stash한다. provisional candidate의 검증·decode headroom admission을 통과한 뒤 road/service/journey를 최종 commit하며, 실패하면 stash와 counters를 move 복원하고 `committed=false`로 남긴다. 이 구간의 dense Journey는 initial/input/old/candidate 네 개이므로 R1의 4-copy reserve를 유지한다.

검토한 최종 precommit 식은 다음과 같다. `T`는 고정 reserve를 뺀 단일 shared pool, `B`는 이미 고정 reserve에 포함한 call binding bytes다. `R*`는 input/current/candidate와 road decode envelope의 최댓값, `J*`는 input/old/candidate와 Journey decode envelope의 최댓값, `E*`는 input/current/new events의 최댓값이다.

`required = 3 R* + 3 J* + 3 E* + max(saturating_sub(V_whole, B), V_road_decode, 64 KiB)`.

`V_whole`은 engine admission과 같은 helper를 호출한다. StageQueue decode envelope는 flattened row 재구성의 registry/tail capacity와 가장 큰 append 선행 reserve를 포함한다. ReceiptHistory는 원래 row 순서가 결정하는 prefix expansion과 block별 row/expansion capacity의 보수 상한을 cache하고, COW 여부에 따른 slack 차이와 decoder의 각 append 상한을 보존한다. 새 cache는 wire 데이터에 포함되지 않으며 rollback 때 기존 history bytes/count와 함께 복원된다. Road decode envelope는 위 raw/packed overlap 및 decoder validation 증가항과 일치한다.

`test_shared_budget_failure_resets_phase_quotas_for_load_and_replay`는 실패 후 마지막 유효 snapshot의 저장, fresh load, 동일 시점 재실행의 checkpoint byte equality를 요구한다. 새 stage/history 테스트는 filtered queue와 매 append COW를 강제한 history에서 fresh decoder의 각 append preflight가 envelope 이하인지 확인한다. 이 검토자는 테스트 소스를 읽었으며 최종 native 실행 성공을 주장하지 않는다.

## 순차 history decode reserve 교정

상태: **SOURCE-CLOSED / FINAL NATIVE REBUILD PENDING.** R1/R2를 재개하지 않고 history decode workspace의 동시 수명만 검토했다. 각 history `i`의 최종 저장 상한을 `F_i`, 그 history를 빈 상태에서 재구성할 때의 최대 working 상한을 `W_i`라 하면, 순차 decoder의 history 부분에는 다음으로 충분하다.

`sum_i F_i + max_i saturating_sub(W_i, F_i)`.

history `j`를 읽는 동안 앞선 history들의 final storage와 현재 history `j`의 workspace만 살아 있다. 따라서 그때의 상한은 `sum_(i<j) F_i + W_j`이며, 비음수인 나머지 final bytes를 더한 위 식 이하이다. 모든 history의 임시 peak를 합하지 않아도 된다. StageQueue의 이미 별도 계상한 decode 상한은 그대로 더한다.

구현은 `history_decoded_final`에 final 상한의 합을 저장하고, append 전후 해당 history의 final delta만 반영한다. `history_decode_extra_max`는 현재 call에서 관측한 `W_i-F_i`의 ever-max이므로 이후 slack이 줄어도 보수 상한을 유지한다. restore/install은 기존 단일 history 순회에서 final 합과 현재 extra 최댓값을 함께 재계산한다. deferred rollback stash는 state, row count, actual bytes, final 합, extra 최댓값을 모두 보존·복원하며, finish가 그 이전에 실패하면 지역 candidate/cache가 폐기되어 기존 owner metadata가 유지된다.

이는 물리 row, prefix expansion 연산, iteration 순서, codec을 바꾸지 않는 accounting 변경이다. `ReceiptHistory`는 기존 cached final upper를 읽는 getter만 추가했고, Journey는 추가 snapshot clone이나 history별 무제한 index를 만들지 않는다. 추가 128-history 회귀는 `128 × final + single extra` 식, 빈 상태 restore, 완료 상태 재설치와 후속 finish를 검증한다. 최종 native 실행 결과는 root가 새 source/binary provenance와 결속해야 한다.

## 현재 확인한 global accounting 경계

고정 reserve는 실제 retained static 자료, initial road, journey dense 4배, service dense 6배, worker/profile/service 준비 scratch, observation reserve를 포함한다. call binding과 전체 검증 scratch는 두 수명의 최댓값으로 잡는다. 남은 하나의 shared pool에서 prepare/road/finish가 동시에 살아 있는 다른 owner를 차감하므로 두 owner의 공개 ceiling을 더해서 사용 가능한 예산으로 해석하지 않는다.

현재 `load`는 road decode 전에 기존 journey/events, service decode 전에 decoded/current road와 기존 journey, journey decode 전에 decoded/current road/events를 차감한다. 각 owner read 이전에 이 quota를 설정하고 모든 decoder/전체 검증 성공 전에는 owner를 설치하지 않는다. 따라서 두 decoder가 독립적으로 shared pool 전체를 쓰는 초기 우려는 현재 소스에서는 해소되어 있다. 이 판단은 위 R2의 reload headroom 문제를 해소했다는 뜻은 아니다.

## 최종 검토 조건

retained runtime footprint는 실제 engine/owner 소유 자료에 바인딩하고, 공유 Arc payload는 주소 identity에 따라 한 번 세거나 보수적으로 중복 계상함을 명시한다. 같은 값의 별도 allocation을 하나라고 간주하지 않는다. 임시 router estimate를 제외했다면 그 대신 알려진 동시 dense copies, call binding/scratch, last_events와 capture validation을 누락하지 않아야 한다.

새 guard는 할당 뒤 수치만 확인하는 방식이 아니라 해당 큰 reserve/clone 이전에 적용되어야 한다. 실제 budget 초과는 입력·owner의 마지막 유효 상태를 유지한다. source/count/physical input을 줄이거나 기존 24h/100k/7,200s/8GiB 목표를 변경하지 않는다. 새로운 budget 식에 따른 scientific/resource identity와 checkpoint 해석을 명시하고, 이전 파일을 무검증으로 다른 정책 단위에 적용하지 않는다.

메모리 accounting 변화 자체로 campaign 성공을 선언하지 않는다. 최종 sequential-history 후보의 native 회귀와 실제 대규모 campaign은 root가 실행 결과를 별도 결속해야 한다. 이전 bounded quota identity는 새 `:bounded_bytes_v1:retained_capacity_v2` 정책과 구별하고, thread 수·임시 phase quota는 identity에 넣지 않는다. legacy 정책의 wire 및 float 연산 순서를 변경하는 작업은 이 검토 범위에 없다.

## 검토한 freeze identity

아래는 2026-11-16 마지막 sequential-history source freeze의 **rustfmt 이전 SHA-256**이다. 최종 formatting/build source와 binary provenance 결속은 root의 manifest에서 수행한다. 앞선 R2 freeze에서 변경된 세 파일의 SHA는 Journey `22a87a346586387a9349e1d99c474be4e16f86a4ad1200faa796fc55001384ba`, History `0e2f3ab807c464ab2bd511f823a9e1960798e43a70e5d0f99bcc93dd5170f412`, retained-accounting test `81376789c6af2937edd5bb07e6fbb07ea54a56cfb6491c8f045919b30366e827`이다. 나머지 아래 파일은 동일하다.

| 파일 | SHA-256 |
| --- | --- |
| `crates/metroflow-rust/src/v1_engine.rs` | `9cae28025e7a5f7b60c2c2c43d51f591de05179160ed2f66954e4d95a1985756` |
| `crates/metroflow-rust/src/v1_journey.rs` | `468f92c0a9d10287c1e67a7c9286cc292cd0181a65f871cd78b1ed71157546c7` |
| `crates/metroflow-rust/src/v1_road.rs` | `e6b100e4e40a1cf6e11dc4e282bf26b981c7ec96b07d182780b6daf8af03a0b7` |
| `crates/metroflow-rust/src/v1_stage.rs` | `630448235bfa84fc804b110783878bec3b3b273b7e292d0804ffc7e5d2e5fc7c` |
| `crates/metroflow-rust/src/v1_history.rs` | `11bf0c8013f410c06851cbc3894501d4203b9c1ac4bc8bf6e60526f24a581296` |
| `tests/v1/test_native_campaign_contract.py` | `3ecbfda63206c9d543370ba0cfc4de6fd284c9383733b14b56f9748d0b0e1e24` |
| `tests/v1/test_native_retained_accounting.py` | `47403381d062c738b5638f94e4886899e278b688f747755ce04733179188d53f` |

## Final native verification

Actual host release build passed (10.21 s). Final sequential-history candidate: 251 scoped tests passed in 9.53 s (`TESTS_BUDGET_SEQ_FINAL.log`). Three occupied legacy replays produced identical physical reports and checkpoint SHA-256 `ef4719a822ac85763679061a5ebd1d431e0edd9cec4e105a15ad1a5f7d4d884f`. All 45 files in `SOURCE_MANIFEST_BUDGET_FINAL.json` match the actual compiled host. These checks do not establish the full-day campaign gate.
