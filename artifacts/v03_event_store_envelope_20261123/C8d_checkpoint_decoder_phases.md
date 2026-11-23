# C8d: checkpoint decoder의 실제 순차 수명

작성: 2026-11-23. 현재 R8 내부의 한정된 계상 교정이며 새 연구 루프가 아니다. 코드 소유는 crates/metroflow-rust/src/v1_journey.rs 한 파일이다. Event의 실제 40 B 표현은 별도 C8e 작업이며 본 파일이 수정하지 않는다.

## 1. 실제 실패와 고정 identity

R8b 원본 실행은 historical checkpoint 25720 s에서 25730 s를 요청했지만 whole checkpointability에서 중단됐다. Required=5,943,686,424 B, dynamic pool=5,789,366,831 B. Committed tick=0, valid advanced duration=0이다. Road transfer 도달을 10초 완료로 표시하지 않는다.

- Commit: 6aeb9a7a09700a0ca5a27a665abfbe38b4bf2b77.
- Candidate source SHA-256: 76242d92122179ad3ac023e7116568ace83b7b7d5f944fb5dc267e7e552569bc.
- Native binary SHA-256: 66b1046a42396eaa694bc4eb183394d8f41eda8b0d53ebc9d081c47c2bc40645.
- R8b_original_100k_25720_requested_10s.json: SHA-256 fc1fedae8efe59fae5fb4a22c6d4f0ea093e80fc0c42640124e22f4b1770d4ba.
- Record-only 동일 실패: R8b_record_checkpointability_25720_requested_10s.json, SHA-256 12600bc5ac419c3d6782a8fbf11de87affe172b00c0eff32dd3cffe360ea4c28.
- 두 영수증 bytes를 각각 C8d_preserved_ 접두사 파일로 보존했다. Record-only 실행은 guard를 우회하지 않았으며 wall 143.010 s는 성능 결과로 사용하지 않는다.

Native total 6,442,450,944 B, process cap 8,589,934,592 B, 기존 fixed reserve 653,084,113 B는 그대로다. Fixed reserve는 trace의 base 570,379,213 B와 call binding 82,704,900 B의 합이며, 차가 위 dynamic pool이다.

## 2. 원인과 source proof

기존 checkpointability_source_joint_phase_bytes의 future 항은 decoded_road + decoded_journey + road_decode_scratch였다. 실제 NativeWholeEngine::load의 순서는 다음과 같다.

1. road.read_state가 RoadState를 반환한다. 그 함수의 row/packet decoder 및 keyset 작업용 임시 값은 반환 시 해제된다.
2. service.read_state가 이벤트 저장소와 service state를 구성한다.
3. journey.read_state가 새 Journey를 구성하고 내부 상태를 검사한다.
4. storage_admission과 validate_bundle이 완성된 Bundle을 검사한 뒤 restore한다.

따라서 road decoder scratch와 새 decoded Journey는 함께 살아 있지 않다. 반면 완성된 decoded Journey와 whole validation workspace는 함께 살아 있으므로 후자의 항을 생략할 수 없다. 기존 v1_engine.rs의 실제 load/admission/validation과 v1_journey.rs의 read_state를 읽어 이 순서를 확인했다.

현재 tick의 sinks 역시 과거 값으로 계속 남는 owner가 아니다. service.finish에 전달한 sinks clone은 함수 반환 시 해제되고, 원래 sinks Vec는 journey.finish로 move되어 그 함수 반환 전에 소비·해제된다. Whole checkpointability guard는 그 반환 뒤 실행된다. Load 경로는 이 tick의 sink Vec를 생성하지 않는다. 이 사실을 새로운 byte credit으로 사용하지 않았으며 기존 event/store charge를 그대로 유지한다.

기존 모델은 source input/current owners, candidate와 future 독립 decoder, Arc pointer로 확인된 실제 old pair 공유를 구분해 왔다. 그 정책과 identity 근거를 유지하고 decoder 내부의 source-visible 순차 수명만 나눴다. 새 미래 Arc alias credit, cap 완화, physics 변경, wire 변경은 없다.

## 3. 최소 구현

V = max(validation_scratch - call_binding_reserve, 65536), 차는 saturating subtraction이다.

- Future road decode phase: decoded_road + max(road_decode_scratch,65536).
- Future Journey/validation phase: decoded_road + decoded_journey + V.
- Future peak: 위 두 phase의 max.
- 기존 실제 joint candidate phase와 future peak의 max를 취한다.
- 기존 fixed source owners, 독립 event decoder upper 및 census charge는 그대로 더한다.

새 함수 checkpointability_sequential_decode_phases가 이 두 phase를 반환한다. Checkpoint lifetime의 journey_input은 restore clone의 retained_input_bytes 대신 이미 보유한 original_input_journey_bytes를 사용한다. Trace에서 실제 original registry가 clone보다 160,912 B 크므로 상향 교정이다. Old cached 값도 trace에 남기고 actual original 값, effective event decode upper, 두 future phase를 새로 출력한다.

이 변경은 decoded_road 및 road_decode_scratch 자체의 기존 상계를 줄이지 않는다. Road decoder의 intermediate Uniform/keyset 표현에 대한 기존 component-envelope 전제도 새로 증명했다고 주장하지 않는다. 실제 decoder의 원래 세부 guard와 부모의 완전한 checkpoint reload/동일 wire 검사가 계속 필요하다. C8e는 actual persistent 40 B 절감을 다루며 unknown-input future decode의 generic 48 B 상계를 유지한다.

## 4. 기존 48 B trace 재계산

| 항목 | Bytes |
|---|---:|
| decoded_road | 1,209,974,272 |
| road_decode_scratch | 936,563,136 |
| decoded_journey | 354,019,848 |
| validation_scratch | 459,527,536 |
| call_binding_reserve | 82,704,900 |
| V | 376,822,636 |
| decoded_journey + V | 730,842,484 |
| 실제 original input Journey | 302,394,480 |
| 이전 cached input Journey | 302,233,568 |
| Original registry 상향 교정 | 160,912 |

Future road phase가 우세하므로 가상의 동시 Journey 354,019,848 B가 제거된다. 여기에 original registry 160,912 B를 다시 더한다.

5,943,686,424 - 354,019,848 + 160,912 = 5,589,827,488 B.

기존 pool과의 차는 199,539,343 B다. **이 값은 old 48 B 실제 trace를 새 계상식에 넣은 재계산이며, 새 40 B 바이너리의 실제 측정이나 진척 영수증이 아니다.**

Trace의 candidate_event는 retained 1,168,612,200 B지만 실제 lifetime은 max(retained, canonical decode upper)를 쓴다. Frozen 48 B 소스의 24,322,678행 decode 식에서 effective 값은 1,168,677,032 B이며 차는 64,832 B다. 이 effective 값을 사용해야 원래 5,943,686,424 B가 정확히 재현된다. 새 trace 필드는 이 구별을 직접 보여 준다.

## 5. 실제 RED/GREEN과 소유권

새 module v03_checkpoint_decoder_sequential_lifetimes_20261123_tests의 4개 검사:

1. 실제 frozen 48 B 실패의 재현, sequential phase 기대값, original registry 상향 보정.
2. Decoded Bundle whole validation이 우세한 반례: 그 workspace를 생략하면 undercharge가 됨.
3. Future independent decoder에 candidate alias credit을 주지 않음, 실제 source +1 B의 cap 초과.
4. Joint candidate phase가 더 큰 경우 그 peak를 유지.

기존 production으로 실제 RED는 2 passed / 2 failed, exit 101이었다. 하나는 old trace 5,943,686,424 B와 sequential 기대값의 불일치, 다른 하나는 validation-dominant fixture에서 기존 6,271,656,856 B가 필요한 7,253,103,440 B보다 작았던 실패다. 즉 새 식이 모든 상황에서 무조건 bound를 줄이는 변경은 아니다.

Production 교정 후 같은 module은 4 passed / 0 failed, exit 0이었다. 실제 명령은 cargo test --offline --workspace --lib v03_checkpoint_decoder_sequential_lifetimes_20261123_tests -- --nocapture. CARGO_TARGET_DIR=/home/cosmosapjw/worktrees/urban-traffic-v03-unique-accounting-20261120/target, RUSTFLAGS=-C link-arg=-lpython3.12를 사용했다.

- C8d_rust_red.log / C8d_rust_red_receipt.json.
- C8d_rust_green.log / C8d_rust_green_receipt.json.
- Before Journey SHA-256: c95c17aeada5d526f7dcf7ce2406ac68f70c6ba12b00aa70db46ccdcbff58a4a.
- RED fixture 포함 SHA-256: 7dad5e93fc411132ac07c16b9d9b86d914d8d6fe0024b0583f9d5f3fd97f7c54.
- Final Journey SHA-256: 2d3397ff500fbb9e96a9ae04343f7638c037974bd652583761e84996009fff35.
- v1_journey.rs의 git diff --check 정상 종료.

Target을 C8e 소유자에게 반환했고 source는 고정했다. 이 기록 작성 시 최종 combined library는 C8e 구현 후 실행 대기다. 그 결과는 아래에 별도로 기록하며 중복 broad test는 하지 않는다. 본 작업은 release build/copy, native_binding 변경, commit/push 또는 원본 100k 실행을 하지 않았다.


## 최종 combined library 근거 재사용과 종료

C8e 소유자가 실행한 최종 C8e_rust_library.log를 실제로 읽었다. **261 passed / 0 failed / 2 ignored**이고 새 C8d 4개도 모두 이름별 ok로 확인했다. 이 최종 gate를 재사용했으며 C8d에서 전체 library를 중복 실행하지 않았다.

- 최종 log SHA-256: 8b35982c487bafde4c4b211e4a3be1dcf61988ac330ee3ee9a221f8b16e917b6.
- 최종 Journey SHA-256: 2d3397ff500fbb9e96a9ae04343f7638c037974bd652583761e84996009fff35.
- 함께 검사한 최종 Road SHA-256: e25adb5d6c5d7bdb1202f6c529f5b7a3b1a23334f8f63b9fbb9780e81277db2d.
- C8e 첫 combined library의 기존 page-size assertion 실패는 C8e_rust_library_first_failure.log에 보존됐다(260 passed / 1 failed / 2 ignored). C8d의 별도 RED/GREEN도 그대로 유지한다.

C8d source와 기록을 고정하고 종료한다. 이 완료는 한정 코드·계상 검증이다. 새 최종 native의 실제 original frontier 실행, persisted full checkpoint의 독립 reload 및 wire 동일성은 부모가 수행할 후속 실행이며 여기서 성공을 선행 주장하지 않는다.
