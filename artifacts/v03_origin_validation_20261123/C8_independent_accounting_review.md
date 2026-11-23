# C8 독립 코드 검토 — actual owner lifetime / fresh checkpoint

## 범위와 최초 판정

2026-11-23, 독립 검토자 `/root/c8_accounting_review`. 기준은 `e2a9fb56a189c05ed35417edad64744255c0bb8b` 이후 C8 native diff이며, 전체 CI·이전 streaming implementation·이론의 재감사가 아니다. Native source를 변경하거나 Cargo/build/물리 실험을 실행하지 않았다. 저자 로그를 읽어 확인한 결과와 내가 실행한 정수 산술을 구분한다.

최초 동결 소스:

| 파일 | SHA256 |
|---|---|
| v1_road.rs | 01694c9ec17d06b43188a9d8e9d93a4dd099173533642e993631befa5ef3a939 |
| v1_journey.rs | 30b2ed00af97eb97d3c40f91f627ccfdb08e3d1db2225f59bce1b344ed2be256 |
| v1_engine.rs | bf078c2d45fda2805531812b3f74a2955a0b4137098c2cc6fc959bf8743f4e93 |

**최초 판정: REVISION_REQUIRED — fresh Journey의 실제 마지막 validator phase 1건 누락.** 부모와 저자가 이 finding을 수용했다. 저자의 새 동결 뒤 아래에 해당 수정만 확인한 종료 판정을 추가한다. 최초 283 passed/2 ignored/exit 0은 이 누락을 발견하지 못한 이전 소스의 실제 한정 검증이며, 향후 수정 소스로 승격하지 않는다.

## F1 — fresh Journey read_state의 유지된 3×max 검사가 예측에서 빠짐

정확한 source 연결은 `v1_journey.rs`의 `NativeJourneyCore::read_state` 마지막 `self.validate(&state)?` → `validate`의 capped branch → `check_storage_limit(storage_budget, retained_input_bytes, journey_storage_bytes(s), 0)`다. 마지막 함수는 유지된 `WORKING_COPIES=3`과 `STORAGE_SCRATCH_RESERVE=65536`을 적용한다. Fresh constructor의 dynamic Journey owner가 0이어도 완성된 decoded Journey에는 3J+65536 admission이 적용된다. Engine load는 이 시점에 constructor current road, old empty event shell, 독립 decoded road와 service events를 보유한다.

그러나 최초 `checkpointability_fresh_bundle_bytes`는 그 owners에 J 한 개와 whole-bundle scratch만 더했다. 따라서 whole-bundle scratch가 2J+65536보다 작은 경우 실제 loader의 마지막 Journey 검사를 충분히 포락하지 못한다. Road decode의 3D 상한은 별도 크기의 Journey 3J를 보장하지 않는다. 이 누락은 실제 memory corruption 보고가 아니라, precommit fresh-readability 보증과 유지된 실제 admission 사이의 불일치다. 실제 loader는 여전히 거절하므로 guard 우회가 발생하지 않았다.

독립 정수 판별은 `C8_independent_accounting_arithmetic.py/.json`에 보존했다. D=E=J=1,000,000 B, source/candidate road 및 stage의 실제 pointer-credit 인자를 각각 900,000 B, call binding 제거 뒤 whole scratch=65,536 B, constructor road/empty event 각 1,024 B인 helper 입력에서:

- current source/candidate: 4,465,536 B;
- 최초 fresh road: 3,066,560 B;
- 최초 fresh bundle: 3,067,584 B;
- 실제 유지된 fresh Journey-validator phase: 5,067,584 B.

4,800,000 B cap에서 최초 max는 승인하지만 실제 Journey validator phase는 거절한다. 이는 helper 함의에 대한 정수 반례이며, 실제 교통 상태 실행이나 behavioral RED로 이름을 바꾸지 않는다.

최소 수정은 `R_initial + E_empty + D + E_decoded + 3*J_decoded + 65536`을 독립 fresh phase로 MAX에 추가하는 것이다. 기존 whole-bundle 검증 phase와 road phase는 유지하며, 실제 Journey validator·cap·허용오차를 낮추지 않는다. 저자가 이 수정과 좁은 회귀를 진행 중이다.

## 나머지 지정 범위의 검토 결과

C8의 native production diff와 새 테스트, engine caller, 관련 loader/validator/interner 호출부를 읽었다. 다음 범위에서 추가 material finding은 발견하지 못했다.

- 원 input capacity는 caller의 실제 `state.value.road.retained_storage_bytes()`에서 전달된다. source-bound 현재 owner에서만 R0+R+max(R0,R)를 쓰고 witness 부재는 3max로 남는다. capacity witness 자체를 Arc 공유 증명으로 쓰지 않으며, clock이 만료된 원 input Arc credit은 부활하지 않는다.
- source preparation/prediction의 미래 incoming combine exclusion은 `retire_completed_motion_scan`에서 종료된다. 실제 서비스 incoming owner 생성과 결합 이전이며, source offer의 별도 4Part overlap reserve 및 row/event guards는 유지된다. 64개 offer의 f64 event/wire 동일성과 standalone fallback을 실제 저자 로그가 확인한다.
- road decoder와 미래 envelope 모두 제거된 O(parts) mass 배열 reserve를 없앴다. 실제 expansion validator는 별도 pre-growth guard를 유지한다. candidate와 fresh wire는 같은 row/f64 scan을 사용하므로 measured scratch witness의 근거가 있다. SharedKeys source의 작아진 owner를 fresh decode에 재사용하지 않고 독립 Uniform 24B / Mixed 48B와 한 raw-packet overlap을 센다.
- optional interning의 미래 절감량을 admission에서 차감하지 않는다. 유지된 3max floor와 실제 한 decoded owner+두 retained-source 상한+전체 interner workspace를 비교하고, 맞지 않으면 이미 검증된 independent state를 반환한다. 신규 keys/moments payload 및 metadata 구조 allowance를 소스와 대조했다. 이 allowance는 명시된 native layout의 계상이며 일반 allocator/RSS 정리가 아니다.
- current commit과 fresh runtime은 분리된 상황이다. 후자의 road/service/Journey가 존재하기 전후를 구분하고 실제 constructor current road를 별도 인자로 받는다. 영구 initial snapshot·dense/static/call-binding reserve를 해제하거나 cap을 바꾸지 않는다. 현재 candidate event bytes와 독립 future decode upper도 다른 phase에서 사용한다.
- Engine actual load의 road/service/Journey/bundle/restore guards는 유지된다. Fresh-runtime 계약은 원 문서에 있던 보증이며, 43,200s same-engine resume은 별도의 미완료 V03 수용 의무다. 이 검토는 이를 fresh restore로 대체하지 않는다.

읽어 확인한 저자 증거: C8_validation_preflight_red/green/targeted.log, C8_checkpoint_RED/GREEN.log, C8_checkpoint_final_lib.log/.exit, C8_checkpoint_final_scoped.log, C8_validation_original_cadence_preflight.md, C8_checkpoint_author_note.md. 로그의 RED는 allocated state를 사용하는 실제 guard 실패이고 GREEN은 같은 cap과 wire를 사용하는 실제 decoder/road proposal 결과다. 내가 이를 다시 실행한 것으로 합산하지 않는다.

## 남은 실증 의무와 drift watchdog

부모가 최종 native에서 전체100k frontier, saved full checkpoint의 fresh-runtime load/replay, 원 hourly cadence/time-zero 경로를 실행해야 한다. 현재 읽은 unit log나 산술로 새 physical prefix, 24h 완료, 43,200s same-engine resume, native ETA 관측, V03 PASS를 주장하지 않는다.

Watchdog: ALIGNED_WITH_OPEN_OBLIGATION. 이번 검토는 설명 가능한 mesoscopic 도시의 실제 실행 및 exact checkpoint 보존을 지원한다. 수요, 단위·시계, FIFO/finite response, row/f64 wire, 허용오차·자원 cap을 바꾸지 않으며, guard 통과 자체를 원 교통·routing 과학의 완료로 세지 않는다. 원 역사 재감사는 반복하지 않았다.

## F1 수정 확인 — 대기

최종 수정 source와 한정 검증 로그를 받은 뒤 F1의 누락된 phase만 확인한다.

### F1 최종 종료 — RESOLVED

저자의 최소 수정만 추가 확인했다. `v1_journey.rs` 최종 SHA256은 `285cf61a9e1339dbf68a0754d1efdd76d8d21a33ceed6931fe29b7b97380f32d`이며 road `01694c9e…`와 engine `bf078c2d…`의 전체 hash는 위 최초 표와 동일함을 직접 확인했다. 새 `checkpointability_fresh_journey_validation_bytes`는 constructor current road/empty event + independent decoded road/event + `WORKING_COPIES*J_decoded + STORAGE_SCRATCH_RESERVE`를 계산한다. Production `required`는 기존 current/road/bundle max에 이 phase를 단조 추가하며, 새 trace term도 존재한다. 실제 Journey read_state/validate와 3×max floor 및 자원 cap은 변경하지 않았다.

수정의 실제 regression은 4,096 receipt를 갖는 Journey를 serializer/read_state로 복원한다. decoded actual owner 84,992B, declared upper119,664B, 이전 residual allowance185,200B에서 유지된 validator required320,512B가 실제 거절된다. 수정 residual424,528B에서는 전체65,632B wire가 동일하게 복원된다. 이 결과는 저자가 실행한 `C8_checkpoint_journey_validator_fix_lib.log/.exit`를 직접 읽어 확인했다: **285 passed, 0 failed, 2 ignored, exit0**, test실행0.18s. 기존 최종283개 로그와 혼동하지 않는다. 내 독립 정수 witness는별도 실행exit0이며 native regression을 내가 실행했다고 주장하지 않는다.

**최종 한정 판정: F1 RESOLVED; 나머지 지정 C8 diff 범위에서 추가 material finding 없음.** 이는 선언된 source/phase 계상 변경을 실험 후보로 내보낼 수 있다는 독립 코드검토 판정이다. 100k 규모의 cap 적합성, 저장된 전체 checkpoint의 fresh-runtime 복원, original-hourly time-zero 실행, same-engine43,200s 재개, 24h 캠페인 성공은 부모의 실제 실험으로 별도 판정해야 한다. 새로운 broad audit이나 재귀 검토를 시작하지 않고 이 검토를 종료한다.
