# 정확한 stage 저장 표현과 자원 예산의 최소 정책 교정

작성일: 2026-11-16. 검토 기준: `7b5e518f6c098ed831551da4e66d980addf80dd8`, `docs/v1/PLAN.json` 1.1.22. 이 문서는 저장 표현 변경의 정책·검증 조건을 제안한다. 새로운 압축 구현, 전 도시 24h 실행, 성능 수용 또는 DAG 완료를 검증했다는 영수증이 아니다. 구체 stage block 형식은 구현 담당자의 확정안과 독립 검증을 기다린다.

## 판정과 원래 권위

**판정: 20,000 raw records는 현재 표현에 종속된 명시적 자원 guard이며, 20,000개의 물리적 여행·사람·차량을 허용한다는 과학적 수용조건이 아니다.** 따라서 원래 수요를 그대로 표현하는 exact stage block/shared storage에 맞춰 예산의 단위를 명시적으로 교정할 수 있다. 다만 기존 guard의 이름만 바꾸거나 payload를 무계상하는 것은 정당한 교정이 아니다. `PLAN.json`의 버전과 적용 범위를 먼저 기록하고, 실제 저장량 및 transient 비용을 계측하며, 예산 초과의 원자적 실패를 유지해야 한다.

| 근거 | 확인한 내용 | 해석 범위 |
| --- | --- | --- |
| `AGENTS.md`; `docs/v1/PLAN.json` authority, execution_policy.change_control | PLAN이 유일한 규범 실행계획이다. 계획 변경의 버전·근거를 먼저 갱신하며, 통과를 위한 범위·수용문턱 완화는 허용하지 않는다. ID·해시·기록 수는 물리 관측이 아니다. | 표현 변경은 기록하되 과학적 목표를 바꾸지 않는다. |
| `5caffbcfebe451637d21b0774b2a9ebc0b446c61`, 최초 `docs/v1/PLAN.json`의 T01 | `기본20,000records; 초과 시 명시중단`. 같은 노드의 실제 수용조건은 birth moment, stage별 체류 장부와 분석적 평균, egress 완료 정의다. | 20k는 resource_budget이고 물리 수요 상한이 아니다. |
| 같은 최초 PLAN의 T04, P01 | T04는 2M liveparts 상한에서 `정확압축/지원범위거절`, 질량 삭제·OD 축소 금지를 명시한다. P01은 2veh에서도 생기는 290 arrival records를 예산/압축으로 관리하고 교환성이 증명된 축약만 exact로 인정한다. | PLAN 자체가 원래 수요를 유지하는 표현 개선을 허용한다. T04의 road parts와 journey records를 같은 종류로 취급하지 않는다. |
| `7de7d0fd28c514ec6b029e49f41a815e2b284f61`, `tools/run_v1_acceptance.py` | `max_cohorts=case['max_cohorts']`를 dense demand compiler에 전달했다. | 원래 20k는 물질화할 cohort 수의 제한이었다. |
| `2776faea4eb2c72883c4aadcfdb5898523dbe538`, 같은 파일 | 독립 OD의 정확한 factorized compiler를 도입하고 `max_factors=case['max_cohorts']`로 marginal factor 수를 제한했다. | 수요를 줄이지 않고 저장 표현과 자원 단위를 바꾼 선례다. 새 단위가 자동으로 과학적 관측량이 되는 것은 아니다. |
| `dc0efbade8cc6d536dcecd072680f41a5d5672fc`, `src/metroflow/v1/joint_release_runtime.py` | `len(pending)+len(egress)+len(internal)+sum(map(len,receipts)) > record_budget`이면 `joint journey record budget` 실패와 이전 상태를 반환하도록 도입했다. | 서로 다른 stage의 raw 행 수를 합한 구현 자원 guard다. 각 행의 질량 크기는 count에 반영되지 않는다. |
| 기준 HEAD의 `scenarios/v1/release_matrix.json`, `src/metroflow/v1/native_release_driver.py`, `src/metroflow/v1/native_engine.py` | matrix의 `max_cohorts`, route materialization cap, native journey record budget, event budget, byte budget은 서로 다른 입력이다. | 같은 숫자 20k가 쓰였다고 같은 예산·단위가 아니다. 일괄 변경하지 않는다. |
| `docs/v1/V03_DRIVER_RESEARCH_KO.md`, `V03_SCALING_RESEARCH_KO.md`, `V03_HANDOFF_KO.md` | 사전 물질화 실패는 해당 표현·예산의 결과이며 일반 불가능성 증명이 아니다. 정적 공유 이후 exact dynamic representation은 future kernel과 관측의 교환성 조건을 요구한다. | 과거의 실패 영수증은 보존하고, 새 표현의 실제 검증으로 후속 진전을 판정한다. |

현재 2M journey trace 실패의 raw counts는 `artifacts/v1_queue_debug_20261116/REPORT_KO.md`, `COMPARISON.json`, `growth_trace_final_t4.json`에 보존한다. 이는 당시 표현·예산에서 발생한 실패의 근거다. 새 표현이 동일 raw count에서 중단해야 한다는 과학적 요구를 만들지 않는다. raw logical rows는 새 구현에서도 진단값으로 남긴다.

## 바꾸지 않는 수용조건

PLAN의 G-DAY, G-SCALE, G-REPLAY와 V03을 그대로 적용한다.

- 원래 주민 100,000, 출발 profile, 목적지, 차종, 귀가 의존성, 고정 fleet/depot 입력을 보존한다. 미배정·미출발·대기·활성·완료량을 명시하며 삭제하거나 완료로 재분류하지 않는다.
- river weekday seed17, coastal weekend seed41, valley weekday seed7 각각 86,400s를 실제 실행한다. 각 case 3회, 환경·반복 변동·실제 checkpoint 재개를 기록한다.
- 각 실행의 wall time ≤7,200s, peak RSS ≤8GiB를 유지한다. 단기 replay나 bytes 추정치로 24h/RSS 통과를 대신하지 않는다. 기존 matched refined-dt 대조와 사전 수치 허용오차를 유지한다.
- 보존, FIFO/공유 capacity, 시간·관측·phase 계약과 마지막 유효 checkpoint 보존을 유지한다. 자원 실패와 물리적 혼잡을 구분한다.
- 모든 DAG 구현 후 별도 심사·전체 CI·통합이라는 기존 순서를 유지한다. stage 표현 변경이나 24h 종료만으로 ACCEPTED/release를 선언하지 않는다.

## 제안하는 최소 PLAN 문구와 계측 단위

다음 취지를 PLAN의 버전 변경 및 해당 resource_budget/변경 이력에 기록한다. 역사 문서와 실패 영수증은 소급 수정하지 않는다.

> T01의 기본 20,000 records는 기존 materialized oracle의 raw-row 자원 guard로 보존한다. Rust exact stage 표현에서는 원래 ordered logical rows와 모든 미래 전이·관측을 복원하는 저장 block, 공유 payload 및 예외 상태의 실제 저장 비용을 명시한 별도 resource policy를 사용한다. expanded logical row count는 진단으로 계속 보고한다. 저장 비용은 block header뿐 아니라 고유 공유 payload, 배열 capacity, frontier/exception, 후보 상태·checkpoint의 추가 할당을 포함하며, 미계상 비용과 peak RSS를 따로 보고한다. 해당 예산 초과는 마지막 유효 상태를 보존하는 명시적 resource failure다. 수요·물리 계약과 V03의 7,200s/8GiB target은 바꾸지 않는다. 정확성이 입증되지 않은 stage/road/history 부분은 원래 표현·검사로 유지한다.

| 보고량 | 단위와 최소 정의 | 용도 |
| --- | --- | --- |
| `expanded_logical_rows` | 원래 ordered raw representation으로 펼쳤을 때의 행 수. entering/egress/internal/receipts를 별도 보고한다. | 기존 실패 trace와 비교·분해하는 진단. 압축 형식의 실제 메모리 사용량으로 부르지 않는다. |
| `stored_stage_blocks` | 소유하는 실제 block header 수. block 유형·공유 범위·최대 payload를 명시한다. | 표현별 구조 비용. 무제한 크기의 Vec 전체를 한 개로 세어 예산을 통과시키지 않는다. |
| `shared_payload_bytes` | 해당 state가 참조하는 고유 불변 payload allocation의 용량을 한 번씩 센다. | 공유로 줄인 실제 저장 비용. 같은 allocation을 중복 계산하거나 참조된 payload를 생략하지 않는다. |
| `owned_capacity_bytes` | owned vector/map의 사용 length뿐 아니라 capacity와 부가 index/frontier/exception allocation을 센다. | 빈 container의 과도한 잔류 capacity와 숨은 예외 배열을 드러낸다. allocator 오버헤드 등 미포함 항목은 명시한다. |
| `candidate_checkpoint_extra_bytes` | 기존 state와 동시에 살아 있는 후보·rollback·snapshot/직렬화의 추가 할당. 공유 allocation은 중복하지 않는다. | peak 비용을 retained state만으로 과소평가하지 않는다. 정확한 계상이 불가능한 항목은 추정이라고 표시한다. |
| process peak RSS | 실제 OS 계측 bytes, 기존 G-SCALE 방식 | 전체 Python/Rust/process의 최종 메모리 수용조건. native accounting bytes와 같다고 주장하지 않는다. |

기준 HEAD의 native CLI는 `min(6GiB, matrix RSS limit)`을 construction accounting byte budget으로 전달하고 8GiB address-space 제한을 건다(`tools/run_v1_local_acceptance.py`). 이 기존 construction 추정치는 자동으로 완전한 동적 메모리 계상이 되지 않는다. address-space limit과 peak RSS도 서로 다른 양이다. stage byte policy의 적용 범위를 명시하고, 전체 runtime/transient 비용을 측정해야 한다.

20k를 새 block cap의 숫자로 재사용할지는 구조와 비용 근거를 보고 결정할 수 있지만, 현재 문서만으로 특정 block cap을 승인하거나 성능을 보증하지 않는다. byte ceiling을 올려 통과시키는 변경은 이 교정에 포함하지 않는다. road liveparts, junction events, fleet max_runs, marginal factor 수와 route construction 예산은 독립된 단위로 유지한다. P01의 오래된 `Rust전환은 ... 경량화수단이아님` 문구는 2026-11-16의 명시적 Rust core/Python frontend 승인과 일치하도록 문구만 정리할 수 있으며, 다른 GPU/JAX 등의 제외 범위를 넓히지 않는다.

## Exact stage 표현의 증명·검증 조건

원래 ordered raw 상태를 \(S\), 압축 상태를 \(C\), 정확한 전개 함수를 \(E\), 고정 입력·step의 전이를 \(F\), 요구 관측을 \(O\)라 둔다. 허용 상태·입력의 범위를 명시하고 다음을 만족해야 한다.

\[
E(F_C(C,u))=F_S(E(C),u),\qquad O_C(C)=O_S(E(C)).
\]

이는 C_EQUIVALENCE의 전이·관측 교환성을 가역 저장 표현에 적용한 조건이다. 실제 f64 값과 순서까지 복원하는 구현이면 bitwise 기준으로 비교한다. 일부 값을 잃는 quotient이면 그 값이 모든 미래 분기와 선언된 관측에 불필요함을 별도로 입증해야 한다. mass와 birth 1차 모멘트가 같다는 사실만으로 완료시각+dwell의 임계 자격량, FIFO 또는 분포 동등성이 따라오지 않는다(`V03_SCALING_RESEARCH_KO.md`의 두 atom 반례).

- shared law를 사용할 때도 각 source release의 질량, born/hold, leg/tag/class/parent, stage, atom weight/delay 및 실제 소비 frontier/예외를 복원해야 한다. 아직 입증되지 않은 receipt/history 축약은 하지 않는다.
- 원래 serial 순서, tie 처리, per-tag reduction과 f64 연산 순서를 유지한다. `(born + (delay + hold))`의 재결합, `start+k*dt`로 누적 clock을 대체, 여러 f64 합을 먼저 묶는 변경은 실수 대수의 항등식만으로 bitwise exact가 되지 않는다.
- 작은 oracle fixture에서 각 tick의 전개된 행·순서·원래 f64 값, 미래 eligibility와 물리 장부를 비교한다. 서로 다른 delays, 부분 소비, 같은 시각의 tie, 작은 양, 귀가+dwell, 혼합 car/bus/freight, unsupported/orphan pending을 포함한다.
- 압축 경계 전후의 저장/복원, 점유된 상태의 branching, thread 수 1/2/4/8, 실패 직후 재시도에서 실제 continuation을 비교한다. constructor/decode/runtime의 실제 저장 예산 초과는 부분 commit 없이 이전 유효 상태를 남겨야 한다.
- 원래 2M raw-row 실패를 포함하는 동일 실제 입력의 prefix에서 raw/logical 성장과 stored/byte 비용을 함께 측정한다. resource failure clock 자체는 표현에 따라 달라질 수 있다. 동일한 물리 상태를 계속 계산하는지와 새 저장 예산에서의 원자적 실패를 각각 검사한다.
- 위 비교를 통과해도 실제 3개 도시 ×3회 24h 및 refined-dt/replay gate는 별도 수행한다. 짧은 exactness 검증이 전체 캠페인의 성능·완결 증거가 되지 않는다.

## Checkpoint: byte identity와 semantic compatibility

| 변경 범위 | 요구하는 동등성·호환성 |
| --- | --- |
| 같은 저장 schema와 같은 물리 입력, thread 수만 변경 | 현행 deterministic ordered 계산의 checkpoint byte identity와 실제 재개 결과를 유지한다. thread 수는 scientific identity에 넣지 않는다. |
| 메모리 내부 압축, 기존 wire 형식 유지 | 동일 f64/raw row 순서로 streaming export할 수 있으면 기존 `MFWHOLE1` bytes와의 동등성을 검사할 수 있다. 전체 전개를 메모리에 추가 물질화하지 않아야 저장 개선이 checkpoint peak에서 사라지지 않는다. |
| wire 형식 자체를 압축 block으로 변경 | 새 magic/schema 또는 명시적으로 versioned codec을 사용한다. 다른 바이트 레이아웃을 같은 `MFWHOLE1`로 조용히 읽지 않는다. 형식 사이 byte identity를 요구하는 대신 검증된 lossless 변환과 실제 continuation을 요구한다. |
| legacy checkpoint import | 원래 입력/model binding을 검증한 뒤 \(E(C)=S\)를 보장하는 변환을 수행한다. malformed count/frontier/index/length를 안전하게 거절하고, 같은 점유 상태에서 재개 결과를 대조한다. 지원하지 않는 이전 형식은 명시적으로 거절한다. |
| 새 schema의 uninterrupted/resumed/repeated 실행 | 같은 canonical compressed state의 deterministic serialization 및 continuation을 검사한다. 관측 일치만으로 serialization/replay gate를 대체하지 않는다. |

기준 HEAD의 `crates/metroflow-rust/src/v1_engine.rs`는 `MFWHOLE1` magic과 model binding을 검증하며, native whole identity에는 byte budget이 들어간다. record budget의 단위가 바뀌면 숫자가 같아도 정책 의미가 같지 않다. storage-policy/schema 버전 또는 동등한 명시적 binding을 추가하여 오래된 raw-row 예산을 새 block 예산으로 오해하지 않게 해야 한다. scientific model identity와 resource/storage policy identity를 구분할 수 있지만 기존 파일을 무검증 재해석해서는 안 된다.

이 검토에서 **established**인 것은 위 저장소 권위·원래 guard의 구현·현재 release 목표다. 정확한 stage 공유가 허용된 목표에 부합한다는 판단은 그 근거에 따른 **derived policy interpretation**이다. 구체 새 표현의 exactness, 저장 절감, checkpoint 호환성과 24h 완결은 아직 **unverified**이며 구현과 실제 영수증으로 닫는다.
