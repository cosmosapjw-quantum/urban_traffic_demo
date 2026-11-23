# R9/C9 실행준비도 표 계약

기록일: 2026-11-23. 대상 worktree: /home/cosmosapjw/worktrees/urban-traffic-v03-event-store-moment-envelope-20261123.

이 문서는 R9/C9의 한정된 실행준비도 계약 정리다. 앞선 모멘트 수학을 재검토하지 않았다. 코드·PLAN·공유 보고서를 변경하거나 build·실험·commit·push를 실행하지 않았다. 부모가 지정한 R8 source commit은 8c5b8942b84e6f06688484ab176a5423f0619c40이다. 이 값과 release/original 10s 실행 진행은 부모가 전달한 맥락이며 본 작업에서 실행 결과를 확인한 증거가 아니다.

## 1. 읽은 권위와 판정 구현

| 자료 | 이 문서에서 사용하는 역할 |
|---|---|
| docs/v1/PLAN.json | 유일한 규범 실행계획, node status, V03 직접 predecessor, 원래 수용조건 |
| scenarios/v1/release_matrix.json | 실제 case 목록·인구·horizon·repeat·자원 상한의 분모 |
| tools/research/v03_readiness.py | PLAN validate 호출, prepare receipt 로딩, live provenance 취득과 readout 작성 방법 |
| src/metroflow/v1/v03_readiness.py | 래퍼가 호출하는 assess_v03_readiness 및 _prepared의 실제 판정 조건 |

PLAN은 version 1.1.26, date 2026-11-17이다. JSON을 읽어 nodes 배열을 직접 집계했다. validate나 readiness CLI를 실행한 결과를 여기서 주장하지 않는다. PLAN의 과거 active_work/current_execution 문장은 해당 기록의 시점이 있는 상태이며, 현재 진행 중인 새 후보 작업의 실시간 계측값으로 사용하지 않는다.

## 2. 전체 DAG와 V03 선행조건

| Node status | 정확한 수 | Node IDs |
|---|---:|---|
| ACCEPTED | 5 | P00, M01, T01, I01, M02 |
| VERIFIED_SCOPED | 14 | M03, D01, T02, T03, T04, R01, R02, B01, C01, M04, C02, P01, V01, V02 |
| BLOCKED | 1 | V03 |
| PLANNED | 1 | RLS01 |
| READY | 0 | 없음 |
| IN_PROGRESS | 0 | 없음 |
| MERGED | 0 | 없음 |
| STOPPED | 0 | 없음 |
| 합계 | 21 | 고유 node 21개 |

PLAN의 구현 진행 정의는 ACCEPTED 또는 영수증으로 고정된 VERIFIED_SCOPED다. 따라서 해당 정의의 완료는 19/21 = 90.48%이고, ACCEPTED 상태 자체는 5/21이다. 이 둘을 최종 수용·전체 CI·통합·release 완료와 같다고 표시하지 않는다. Scorer도 실제 status로 계산한 ID 집합 및 count가 implementation_progress의 기록과 같아야 한다.

| V03 직접 predecessor | 현재 PLAN status | 구현 착수 선행조건에서의 의미 |
|---|---|---|
| P01 — 관측동등 경량화와 자원 상한 확립 | VERIFIED_SCOPED | 한정 검증 근거를 사용하는 선행조건 충족 |
| V01 — 통합 물리·관측·대칭 적대 검증 | VERIFIED_SCOPED | 한정 검증 근거를 사용하는 선행조건 충족 |
| V02 — 도시형태·지형·접근의 적대적 시각 검수 | VERIFIED_SCOPED | 한정 검증 근거를 사용하는 선행조건 충족 |

직접 선행조건은 3/3이다. 이것이 V03 자신의 물리 실행·24h·자원·replay 수용을 대체하지 않는다. 현재 PLAN status는 V03=BLOCKED, RLS01=PLANNED이며 이 계약 작성으로 바뀌지 않았다.

## 3. 원래 실행 분모

| Case ID | City/day/seed | 주민 stock | 각 run horizon | 반복 수 |
|---|---|---:|---:|---:|
| river_weekday_s17 | polycentric_river / weekday / 17 | 100000 | 86400 s | 3 |
| coastal_weekend_s41 | coastal_port / weekend / 41 | 100000 | 86400 s | 3 |
| valley_weekday_s7 | valley_city / weekday / 7 | 100000 | 86400 s | 3 |
| 합계 | 3개 case | 각 case의 원래 stock 유지 | 각 run 24h | 9 runs |

- Calendar preparation의 분모는 case별 준비 영수증 1개, 합계 3이다.
- Full-day 실행의 원래 분모는 3 case × 3 repeats = 9이다. 짧은 prefix, preparation 횟수, 재시작 횟수로 이 분모를 바꾸지 않는다.
- 각 실제 24h run의 원래 자원 목표는 wall <= 7200 s, peak RSS <= 8589934592 bytes = 8 GiB다. Prepare 시점의 resource 통과는 full-day resource 통과를 뜻하지 않는다.
- PLAN의 나머지 V03 수용조건에는 하루말 완료·진행·대기·미출발 장부, checkpoint와 연속 실행의 동등성, 동일 입력의 short matched refined_dt 대조가 포함된다. 시간만 86400에 도달했다고 이 조건들이 자동 통과하지 않는다.
- Original matrix의 exact_factorized_independent_OD, requested=allocated+unassigned worker 장부, 미배정 worker의 stay-home 처리와 기존 inventory prior를 유지한다. 이 계약은 새로운 demand 값이나 수용문턱을 도입하지 않는다.

## 4. Current source/current native preparation 판정

래퍼는 먼저 validate(plan, release=False)를 호출한다. --prep-dir가 있으면 matrix의 각 case에 대해 <case>.prepare.json을 읽는다. 영수증이 하나라도 공급되면 candidate_provenance()와 native_binary_provenance()가 모두 status=MEASURED여야 하며, 아니면 현재 준비도 주장을 거절한다. 해당 호출이 반환한 current source_sha256 및 native sha256을 assessor에 전달한다.

현재 _prepared의 실제 조건은 다음과 같다.

| 항목 | 준비 인정 조건 |
|---|---|
| 실행 종류 | status=WHOLE_CALENDAR_PREPARED |
| 계산 엔진 | engine_backend=rust_whole |
| Case·matrix | case ID가 해당 matrix case와 같고 matrix_sha256이 읽은 원 matrix의 실제 hash와 같음 |
| 준비 모드 | step_s=10, horizon_s=0 |
| 실제 물리 진척 | simulated_s=0 |
| 식별자 형식 | source_sha256, patch_sha256, candidate_source_sha256, native_binary_sha256 모두 64자리 소문자 hex SHA-256 |
| Current source | receipt.candidate_source_sha256 == live_candidate_source_sha256 |
| Current native | receipt.native_binary_sha256 == live_native_binary_sha256 |
| Driver·작업트리 | driver_identity가 비어 있지 않은 문자열이고 candidate.source_dirty is False |
| Calendar | resident_stock == matrix.population; legs는 bool이 아닌 유한한 양수 |
| Prepare 자원 | wall_s와 peak_rss_bytes가 bool이 아닌 유한한 비음수이며 각각 원 matrix 상한 이하 |

통과하면 case status=PREPARED_SCOPED, reason=WHOLE_CALENDAR_PREPARATION_VERIFIED_NOT_DAY다. 누락 영수증은 NOT_RUN/NO_FRESH_PREPARATION_RECEIPT, 조건 불일치는 REJECTED_EVIDENCE와 구체적 reason이다. 같은 case의 중복 영수증이나 원 matrix에 없는 case는 거절한다.

중요한 구현 범위:

- 직접 assess_v03_readiness를 호출하면서 live_candidate_source_sha256 또는 live_native_binary_sha256을 생략하면 해당 current hash 비교가 생략된다. 그런 호출 결과를 현재 source/native와 대조 완료한 준비도라고 표시하지 않는다. 래퍼의 실제 provenance 연결 또는 동등한 live 인자 공급 근거를 함께 기록한다.
- source_sha256 및 patch_sha256은 현재 _prepared에서 hash 형식을 검사한다. Current source의 직접 비교 대상은 candidate_source_sha256이며, current binary의 직접 비교 대상은 native_binary_sha256이다.
- branch_commit은 measurement_context의 별도 provenance다. Commit 문자열만으로 source content와 실제 로드된 native binary의 동일성을 대신하지 않는다.
- 준비 판정은 기존 driver가 만든 WHOLE_CALENDAR_PREPARED 영수증과 source binding을 소비한다. Scorer 자체가 calendar의 모든 leg를 재구성해 검증하는 것은 아니다.
- Receipt의 horizon_s=0, simulated_s=0은 실행하지 않는 준비 모드다. Matrix의 원래 86400 s calendar/acceptance horizon을 0으로 바꾸는 계약이 아니다. step_s=10도 10초 실행 실적이 아니다.

이 작업에는 fresh current 3-city preparation receipt가 공급되지 않았다. 부모가 이후 수행할 prepare 결과는 각 case 영수증과 live hash를 실제로 대조한 뒤에만 판정한다. 본 계약은 current preparation 3/3 통과나 현재 CLI 출력 0/3을 미리 주장하지 않는다.

## 5. 준비도 표의 clock와 실행 credit 계약

각 측정 행은 다음 필드를 구분한다. 절대 clock과 새 후보가 수행한 시간의 차이는 report label만으로 복원하지 않는다.

| 필드 | 의미 |
|---|---|
| evidence_kind | PREPARE_ONLY / FRESH_PREFIX / CHECKPOINT_CONTINUATION / FULL_DAY_RUN |
| candidate_source_sha256, native_binary_sha256 | 이 행에서 실제 실행·준비한 후보의 content identity |
| case_id, matrix_sha256, repeat_id | 원래 3×3 입력과의 대응. Prepare에는 repeat를 full-day credit으로 부여하지 않음 |
| inherited_checkpoint_clock_s | 재사용 checkpoint에서 이미 도달했던 절대 시간. Fresh run이면 0 |
| candidate_run_start_clock_s | 이번 후보 실행이 실제 시작한 절대 clock |
| candidate_run_end_clock_s | 이번 실행이 실제 도달한 절대 clock |
| new_candidate_advanced_s | 관측된 end-start. 준비만 했다면 0 |
| fresh_candidate_elapsed_from_zero_s | 같은 후보로 clock0부터 실제 수행한 연속/증명된 실행 길이. Historical checkpoint를 재사용한 행에서는 이를 별도 NOT_ESTABLISHED로 표시 |
| full_day_credit | 원래 case/repeat의 86400 s 실행과 해당 수용증거가 확인된 경우에만 1, 그 밖에는 0 |
| evidence_path / checkpoint identity | 해당 결과를 실제로 뒷받침하는 receipt/checkpoint. 아직 없으면 미측정 또는 판정 대기 |

| 증거 종류 | 표에서 허용하는 해석 | 물리/full-day credit |
|---|---|---|
| Prepare-only: horizon_s=0, simulated_s=0 | 현재 candidate/native가 원 calendar를 준비했다는 한정 결과 | 물리 진척 0 s; full-day 0/9 |
| Fresh original 0→10 s | 실제 receipt가 확인되면 새 후보의 fresh prefix 10 s | 물리 진척 10 s; full-day 0/9 |
| Historical checkpoint t_cp → t_cp+10 s | 이전 clock t_cp와 새 후보의 continuation 10 s를 별도로 기록 | 새 후보가 수행한 진척은 10 s; fresh-from-zero는 입증되지 않음; full-day 0/9 |
| Current candidate의 실제 full-day receipt | 동일 case/repeat와 frozen identity, 장부·replay·refinement·자원 증거에 연결 | 해당 조건이 확인된 run만 1/9 |

표의 0→10 s와 t_cp→t_cp+10 s는 판정 규칙을 설명하는 예시이며, 현재 R8 실행이 성공했다는 관측 주장이 아니다. Historical checkpoint의 절대 clock을 new candidate since0에 복사하거나, 여러 continuation 행의 끝 clock을 더하거나, 같은 구간의 재실행 시간을 누적해 86400 s로 만들지 않는다. Checkpoint load/continuation 성공은 그 한정된 compatibility/진척 근거로 보존한다.

## 6. Scorer 출력과 캠페인 상태의 구별

현재 assess_v03_readiness는 prepare receipt 전용 진단이다. 반환되는 completed_full_day_runs=0, ready_for_release=False, execution_status=BLOCKED_BY_EXACT_INTERVAL_PACKET_EXPLOSION은 이 코드의 고정 출력이며, real_full_day_execution_evidence는 NONE_IN_SUPPLIED_PREPARATION_RECEIPTS다. 이를 새 물리 실험이나 모든 역사적 campaign receipt를 검색한 결론으로 표시하지 않는다.

PLAN에는 기존 full-day completion 0/9와 resource blocker가 기록돼 있다. 현재 후보의 실제 실행 진행은 새 run receipt에서 별도로 확인한다. 후속 준비가 3/3 통과하더라도 준비도 분모만 3/3이 되며, 9개 full-day 완료를 자동으로 늘리거나 V03/RLS01 status를 승격하지 않는다.

부모가 현재 3-city prepare와 R8 실행 결과를 확보한 뒤에는 위 계약의 해당 관측 행을 채울 수 있다. 본 파일은 그 실행 결과를 생성하거나 선행 승인하는 문서가 아니다.

## 7. 후속 실제 실행 결과 — 최종 후보에서 갱신

위 계약을 작성한 뒤 최종 freeze `dd9686f1d537ed746425dd4a60d1f3e8fc302089`에서 세 도시를 다시 준비했다. Source content SHA256은 `7e8b92020076e01283d532cf0e5825cb30167a533949e6bc6fd071f7b7d8cfe2`, 실제 native SHA256은 `baa3e4ce4f775df5cf3973e749357cc2d5a29cefbf1683355638a0de5b6a5606`다. 각 case의 주민 stock100000, 원 matrix hash, step10s, simulated_s0, source-clean을 확인했다. 이는 R8e 물리 계산과 일부 병행한 준비이며 wall은 독립된 성능 benchmark가 아니다.

| 원 case | Calendar legs | 준비 wall(s) | Peak RSS(B) | 현재 후보 판정 |
|---|---:|---:|---:|---|
| river_weekday_s17 | 5,093,765 | 63.3349520650 | 2,172,858,368 | PREPARED_SCOPED |
| coastal_weekend_s41 | 2,449,750 | 37.1163108810 | 1,116,106,752 | PREPARED_SCOPED |
| valley_weekday_s7 | 918,450 | 21.5053403290 | 447,070,208 | PREPARED_SCOPED |

실제 CLI `tools/research/v03_readiness.py --prep-dir artifacts/v03_event_store_envelope_20261123/R9_final_native_preparation`가 live source/native provenance와 세 receipt를 대조해3/3을 반환했다. Plan validation은21nodes, ACCEPTED5/VERIFIED_SCOPED14/BLOCKED1/PLANNED1, VALID_PLAN_NOT_RELEASE였다. 결과 파일은 `R9_final_source_readiness.json`, 원자료는 `R9_final_native_preparation/*.prepare.json`, validator 출력은 `R9_final_plan_validation.log`다.

이전 freeze의 `R9_current_native_preparation`은 당시3/3을 실제 통과했지만, 최종 후보와 대조한 별도 CLI 실행에서는 세 case 모두 `REJECTED_EVIDENCE / CURRENT_SOURCE_CONTENT_HASH_DIFFERS`, 현재 credit0/3이다. `R9_old_source_rejected_on_final_native.json`에 그 결과를 보존했다. 과거 준비의 성공 사실을 지우지 않으며, 최종3/3에는 새 영수증만 사용한다.

최종 준비도는 canonical19/21(90.48%, 수용5와 범위 검증14), V03 직접 predecessor3/3, 현재 source/native calendar3/3이다. Scorer의 full-day0/9 고정값은 preparation 전용 출력이라는 §6 한계를 유지한다. 실제 이 루프의 물리 기록도24h 완료를 만들지 않았으므로 별도 campaign 판정 역시0/9다. 관측 host는31.25GiB physical RAM으로 계획의64GiB reference host와 일치하지 않는다. Physical horizon·7200s/run·8GiB process cap과 내부6GiB budget은 변경하지 않았다.
