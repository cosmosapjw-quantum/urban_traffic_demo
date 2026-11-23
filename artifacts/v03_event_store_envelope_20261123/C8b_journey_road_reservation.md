# C8b: road proposal 직전 Journey owner reservation

기록일: 2026-11-23. 부모가 지정한 R8/C8 내 추가 수술이며 앞선 수학 검토를 재실행하지 않았다.

## 변경 범위와 identity

- 코드 소유: crates/metroflow-rust/src/v1_journey.rs 한 파일.
- 원본 bytes 보존: C8b_v1_journey_before.rs.
- 변경 patch: C8b_journey_road_reservation.patch.
- Before SHA-256: 8366b8d9eaee24b0abfa8e214cd00cce904a1b0b5aeb4291fb41604dcdf66f20.
- After SHA-256: c95c17aeada5d526f7dcf7ce2406ac68f70c6ba12b00aa70db46ccdcbff58a4a.
- 원래 engine fixed reserve, native 6 GiB, process 8 GiB, source/demand, dt, physics, checkpoint wire, driver identity는 변경하지 않았다. v1_road.rs는 별도 소유자가 수정하며 본 작업은 그 API를 변경하지 않는다.

## 실제 변경

road.propose_owned_step 직전에는 original input/current/pending Journey가 모두 알려져 있다. 기존 3*max 예약을 이 구간에서만 다음 값으로 바꾼다.

J_road = J_input + J_current + J_pending - P(input,current) - P(current,pending).

P는 기존 journey_shared_stage_payload_census가 실제 Arc<Block> pointer 교집합에서 확인한 immutable Access Vec payload bytes다. Value equality, owner 크기, producer state 또는 guard counter의 동일성은 공유 증거로 사용하지 않는다. 같은 allocation이 세 owner에 모두 존재하면 두 pair 차감으로 하나의 payload charge가 남는다. Block metadata, Arc control, 각 registry, history charge는 각 owner에서 유지하며 dense per-leg buffers는 원래 engine fixed reserve에서 계속 계상한다.

원래 입력 snapshot의 registry capacity가 복원 clone보다 클 수 있으므로 road phase의 J_input은 original_input_journey에서 한 번 계산한다. Current/pending history는 prepare에서 바뀌지 않는 기존 history_bytes cache를 유지한다. Original 또는 pending 참조가 없으면 기존 3*max fallback으로 돌아가고 census를 할당하지 않는다.

## Census 자체의 수명과 선행 guard

차감 증거를 만들기 전에 다음 uncredited peak를 고정 total과 비교한다.

required_preflight =
 actual_old_road_owners + actual_old_event_owners + physical_offer_Vec_capacity
 + J_input + J_current + J_pending
 + max(S_input_map, S_current_map) + original_64KiB_scratch.

- Road는 input+committed 두 owner만 있다. 아직 없는 future road candidate 또는 3*max road를 이 census preflight에 넣지 않는다.
- 원래 restore-time road pointer witness의 clock이 현재 clock과 같을 때만 그 확인된 payload credit을 쓴다. Clock이 바뀌거나 witness가 없으면 두 owner를 온전히 계상한다.
- Event는 기존 concrete_service_event_owner_bytes와 실제 Arc::ptr_eq 결과로 기존 input/current를 계상한다.
- 이미 살아 있는 physical offers Vec의 실제 capacity와 기존 allocator padding을 포함한다.
- 각 S upper는 source의 세 queue block_count 합이 0이면 0, 그 밖에는 hash_entries_upper_bytes(max(blocks,2))를 계산하고 두 배로 잡는다. 단일 entry에도 필요한 HashMap 최소 usable capacity를 반영하며, 성장 중 old/new table이 함께 있는 transient 및 각 table의 control/allocator padding을 덮는 구조적 상계다.
- 두 census는 순차적으로 실행한다. 각 HashMap은 helper 반환 전에 drop되므로 scratch peak는 합이 아니라 max다.
- 각 helper의 실제 HashMap capacity 기반 scratch가 해당 source의 단일-table upper 이내인지 확인한 후에만 pointer credit을 채택한다. Growth peak의 두-table reserve와 이 단일-table actual-capacity 검사를 구분한다. Upper를 넘으면 오류를 반환한다.
- Road proposal이 시작될 때 map은 모두 해제돼 있다. 지속적인 Journey reservation에서 scratch를 빼는 조작은 없으며, 실제 StageQueue payload의 중복만 차감한다.

이 구조적 계상은 기존 allocator-envelope 전제를 사용하며 RSS 자체의 정리로 주장하지 않는다. Preflight guard는 실제 allocation 전에 수행하며 uncredited Journey 합에 대해 strict하게 거절한다.

## 의미 있는 검증 항목

새 test module: v03_road_phase_journey_source_census_20261123_tests, 7개.

1. 세 실제 alias가 두 payload copy만 제거하며 모든 history·shell charge를 유지.
2. 독립적으로 할당한 동일 값에는 credit 0.
3. Append로 복사된 tail에는 credit 0이고 기존 공유 full blocks만 정확히 차감.
4. Original reference가 없는 호출은 3*max 및 무할당 census fallback.
5. Restore-time road witness의 clock 만료, witness 부재, source-byte clamp.
6. Uncredited owner 합·physical Vec·scratch의 cap 경계: cap에서 허용, cap-1 및 other_live+1에서 거절, 아직 입증되지 않은 credit으로 census 비용을 충당하지 않음.
7. 두 순차 census의 measured scratch max, actual capacity upper와 upper+1 검사, 여러 HashMap growth 경계.

git diff --check -- crates/metroflow-rust/src/v1_journey.rs는 실제 정상 종료했다.

초기 기록 시 cargo는 NOT_RUN이었고 shared target은 event_store_implementation이 소유했다. 이후 해당 agent의 실제 library 실행에서 발견된 아래 scratch 경계 실패를 교정했고, target을 반환받아 scoped 7개와 최종 library 회귀를 실행했다. 원본 heavy 실행, release build/copy, commit, push는 본 작업에서 하지 않았다.


## 실제 실패·교정·최종 검증

최초 공동 library 실행은 event_store_implementation이 수행했다. Journey source SHA ae8ed6dab7f5ee3f3ce95f4ee09143222539189ffb9c2d92c9484030f5cc5d5c에서 250 passed / 1 failed / 2 ignored, exit 101이었다. 실패 항목은 actual_census_capacity_is_checked_and_sequential_scratch_is_a_max의 block_count=1이다. 원본은 C8c_rust_full.log이고, 동일 bytes를 C8b_initial_library_failure.log로 보존한다.

분류는 새 census wrapper의 **구현 계상 오류**다. HashMap usable capacity가 단일 entry에서 이미 3인데 generic 2*entries 상계로 계산해 단일-table charge를 196 B로 잡았다. 실제 capacity-based charge는 230 B였다. 비영 block 수에 대해서만 최소 requested envelope를 2로 올려 단일-table 상계를 264 B로 교정했다. 원래 global helper나 정책 cap은 변경하지 않았다. 이후 scoped 출력에서 실제 230 B <= 264 B를 확인했다.

Target 반환 뒤 본 작업자가 실제 실행한 두 명령:

- cargo test --offline --workspace --lib v03_road_phase_journey_source_census_20261123_tests -- --nocapture
- cargo test --offline --workspace --lib -- --nocapture

두 명령의 환경:

- CARGO_TARGET_DIR=/home/cosmosapjw/worktrees/urban-traffic-v03-unique-accounting-20261120/target
- RUSTFLAGS=-C link-arg=-lpython3.12
- cwd=/home/cosmosapjw/worktrees/urban-traffic-v03-event-store-moment-envelope-20261123

| 실제 검사 | 결과 | 원본 로그 / 실행 영수증 |
|---|---|---|
| 새 C8b scoped module | 7 passed, 0 failed, exit 0 | C8b_rust_scoped.log / C8b_rust_scoped_receipt.json |
| Workspace library 회귀 | 251 passed, 0 failed, 2 ignored, exit 0 | C8b_rust_library.log / C8b_rust_library_receipt.json |
| 최종 git diff --check, v1_journey.rs 한정 | 정상 종료 | 도구 실행 출력으로 확인 |

두 실행의 Journey source SHA는 최종 After 값 c95c17aeada5d526f7dcf7ce2406ac68f70c6ba12b00aa70db46ccdcbff58a4a다. 이는 한정된 Rust library 검증이며 전체 저장소 CI·원본 full-day 실행·process RSS 수용을 뜻하지 않는다. Ignored 2개는 통과 수에 넣지 않았다. Shared target 사용을 종료하고 소유자와 부모에게 반환을 알렸다. 부모의 최종 diff/guard/lifetime 통합 검토 및 원본 10→20→40 실행은 별도 단계다.
