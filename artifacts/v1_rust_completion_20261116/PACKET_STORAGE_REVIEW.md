# PackedTime / packet 공통 interval 저장의 독립 검토

2026-11-16. 기준 commit `7b5e518f6c098ed831551da4e66d980addf80dd8` 위의 추가 저장 표현 변경을 검토한다. 이미 종결한 event-clock 수치 처리와 storage decode R1 검토는 재개하지 않는다. 이 문서의 범위는 `PackedTime`, `PacketParts::Uniform/Mixed`, 그 iterator/codec/byte accounting과 직접 회귀검사다.

상태: **SOURCE REVIEW CLOSED — 미해결 P0/P1 0건.** 구현 담당자의 Rust/test 최종 freeze를 확인했다. 아래 식별은 검토 시점 소스이며 최종 rustfmt/build manifest는 root가 별도로 바인딩한다. 빌드/native 테스트/실제 시뮬레이션은 root가 실행하며 이 검토자는 실행 PASS를 선행 선언하지 않는다.

## 실제 입력 근거와 허용되는 표현 변경

`PART_LINEAGE_PROBE.json`은 t=25,490s checkpoint `d5d584ed47a9af4e2a77cedacf04c0b45a6899f9e534e2a76579ecc2e16bae6b`의 45,715개 road packet, 2,313,316개 part를 검사했다. 모두 packet 내부 interval이 동일했고 mixed packet은 0이었다. 이는 해당 시점의 관찰이며 모든 허용 상태의 uniform성 증명은 아니다. 그래서 mixed interval의 정확한 fallback이 필요하다. 반복 route/offset 또는 인접한 같은 target은 packet을 합칠 근거가 아니다.

별도 `numeric_resume_t1.json`은 기존 수치 실패를 지나 t=25,520s까지 진행한 뒤 `entry interval split`의 road quota로 중단한 기록이다. 필요한 accounting bytes는 1,342,245,688, quota는 1,342,231,185이며 실제 peak RSS는 1,585,893,376 bytes다. `PART_LINEAGE_PROBE.json`의 25,490s 상태와 이 실패 상태를 같은 데이터로 혼동하지 않는다.

변경은 각 finite `Option<f64>` endpoint를 8-byte `PackedTime`으로 보관하고, 한 packet의 모든 endpoint bits가 같을 때 두 endpoint를 packet 공통값으로 저장하는 것이다. 각 part의 tag/route offset/mass/birth는 그대로다. Uniform의 CorePart는 32-byte 구성이고 Mixed는 48-byte Part를 보관하는 설계다. 실제 `size_of`와 enum/packet overhead는 빌드한 native 검사로 확인해야 한다. 기존 64-byte Part에서 PackedTime만 적용한 16-byte 절감은 위 probe에서 37,013,056 bytes의 payload 계산값이며, RSS 실측 개선율이 아니다.

## 반드시 유지할 의미

| 경계 | 검토 조건 |
| --- | --- |
| finite endpoint encoding | Some의 finite IEEE bits를 그대로 저장하며 None sentinel `u64::MAX`와의 충돌을 nonfinite 입력 거절로 막는다. source offer, Python row restore, binary decode 및 내부 interval 생성 경로가 checked constructor를 사용해야 한다. |
| numeric comparison / bit identity | `Option<f64>` 숫자 비교에서 +0/-0는 같지만, common interval 판정과 기존 combine key 및 wire에서는 원래 bits를 구별한다. None과 Some(-0/+0), subnormal, 최대 finite를 서로 바꾸지 않는다. |
| Uniform / Mixed | 모든 a,b bits가 동일한 packet만 Uniform으로 저장한다. 다르면 원래 순서의 Mixed를 유지한다. 동일 target packet을 합치거나 같은 route/offset의 다른 mass·birth·entry interval을 합치지 않는다. |
| stored iteration | Uniform iterator는 공통 endpoint와 각 CorePart를 결합해 기존 Part 행을 같은 순서로 정확히 복원한다. Mixed iterator는 원래 각 행을 그대로 반환한다. mass/birth의 재합산·반올림·정렬 변경을 저장 최적화에 섞지 않는다. |
| transition / split | portion, combine, interval split의 기존 f64 식과 group별 fsum 입력 순서를 유지한다. 저장용 pack/unpack만 변하며 packet FIFO 경계와 target은 유지한다. |
| wire format | 기존 `MFWHOLE1`의 packet/part count·순서 및 option tag+f64 little-endian bits를 그대로 쓴다. 메모리 enum variant를 wire에 새로 노출하지 않는다. |
| failure | byte/decode/invalid endpoint 실패는 이전 owner/checkpoint를 보존한다. malformed nonfinite endpoint를 None으로 흡수하지 않는다. |

## 메모리와 정책 검토 조건

retained bytes는 Uniform의 CorePart capacity, Mixed의 Part capacity, 커진 Packet/enum 크기와 모든 registry capacity를 실제 구조에 맞춰 센다. logical part 수만 32 bytes와 곱해 mixed payload나 packet header를 생략하지 않는다.

raw48 Vec에서 Core32 Vec로 변환할 때 두 allocation은 한동안 공존한다. decode와 runtime pack은 새 Core32 reserve 전에 그 추가 transient를 검사해야 한다. decode 이후 최종 compact retained size만 검사하는 방식은 허용되지 않는다. temporary combine/interval split 자료가 여전히 48-byte Part이면 그 scratch도 48-byte 기준으로 계상한다. 저장을 읽기 위해 불필요한 전체 raw Vec를 반복 생성하지 않고, iterator에서 행을 값으로 복원하는 경로를 검토한다.

legacy raw-record guard의 단위와 기본값은 유지한다. bounded byte 모드만 실제 구조 크기/capacity를 반영한다. 이번 engine의 road/journey owner quota를 가용 예산의 1/2씩으로 배분하는 정책은 별도 명시되며 기존 총 6GiB accounting 및 8GiB RSS/7,200s gate를 늘리는 변경이 아니다. 이 배분의 성능 효과는 실제 실행으로 판단한다.

## byte identity의 비교 범위

- 저장 표현만 다르고 같은 legacy policy/input/binding이면 기존 성공 prefix의 전체 checkpoint byte identity를 확인한다.
- bounded owner quota를 1/4:3/4에서 1/2:1/2로 바꾸면 model/resource binding이 달라진다. 이 경우 예전 bounded checkpoint 전체 bytes와 같다고 주장하지 않는다. 이전 binding을 무검증 재해석하지 않는다.
- 기존 row codec의 option bits/순서는 별도로 대조하고, 동일한 새 policy에서 uninterrupted/resumed/thread-count replay의 checkpoint bytes를 비교한다.

최종 회귀 소스는 단일 endpoint뿐 아니라 한 packet 안에서 +0/-0만 다른 여러 row, None/Some 또는 다른 interval의 혼합, 부분 portion 이후 재저장, packet 경계·wire roundtrip 및 byte 예산 실패를 구분해야 한다. 실제 실행 결과는 최종 source/binary manifest와 함께 root 영수증으로 확정한다.

## 최종 확인 결과

- `PackedTime::new`는 finite Some만 IEEE bits로 보존하고 None을 전용 sentinel로 표현한다. source Part, raw-row restore, binary decode와 내부 split/transfer endpoint 생성에 checked constructor가 적용되었다. numeric PartialEq/PartialOrd는 Option 의미를 유지하며, Uniform 판정은 숫자 equality 대신 두 endpoint의 u64 bits를 비교한다.
- `PacketParts::Uniform`의 CorePart와 공통 endpoint에서 `PartIter`가 각 기존 Part를 값으로 복원하며, Mixed는 원래 Part를 복사한다. 둘 다 입력 순서를 유지한다. 저장 최적화에 packet 합병·part 재정렬·mass/birth 재합산이 추가되지 않았다. `portion`, group별 `combine`, interval split의 f64 식과 순서를 확인했다.
- wire writer와 Python snapshot은 iterator로 복원한 기존 row를 출력한다. option tag와 float bits, packet target·packet/part 순서가 유지된다. 새 enum variant는 wire에 나타나지 않는다.
- retained accounting은 variant별 실제 capacity × CorePart/Part 크기와 커진 Packet 크기를 사용한다. `RoadDecodeBudget::pack_parts`는 새 Core32 reserve 전에 추가 비용을 더하고, 변환 후 raw48 capacity를 차감한다. runtime pack도 추가 Core allocation 전에 `RoadWorkBudget::require`를 호출한다. raw-row restore는 이미 존재하는 typed input buffers와 새 owner 비용까지 보수적으로 계상한다.
- `test_native_packed_intervals.py`의 22개 parametrized 사례 소스를 읽었다. finite endpoint 극한, 한 packet 안 ±0 bits 차이/None·Some/다른 interval의 Mixed 순서, layout, 기존 whole-wire roundtrip, nonfinite/sentinel 충돌 거절 및 packing 중 두 buffer 공존 budget 실패의 owner 보존을 겨냥한다. 검토자가 직접 실행하지 않았다.
- engine의 가용 예산 절반씩 배분은 그대로 finite quota이며, odd remainder는 journey에 귀속된다. `storage_config`가 이 단위·고정 배분·quota 간 borrowing 없음 및 identity binding을 명시한다. 분할 비율 변경은 저장 exactness 증명과 별도 자원 정책이며 총 예산·과학적 수용문턱을 바꾸지 않는다.

이 범위에서 추가 blocking source finding은 없다. 기존 event-clock 처리 또는 전체 campaign 정확성을 다시 심사한 결론이 아니다. actual old/new replay, 새 policy의 restart/branch/thread byte identity 및 24h resource 결과는 최종 실행 영수증에서 확인한다.

## 검토 소스 식별

| 파일 | SHA256 |
| --- | --- |
| `crates/metroflow-rust/src/v1_road.rs` | `04e25af00322af66a298455869169d75deff8ca699cfd747faeb2437c6538c5d` |
| `crates/metroflow-rust/src/v1_engine.rs` | `d2f79e9d7dde7f55ef0af82c1085a762670ce7118cde1be4d5c27f97925491f1` |
| `tests/v1/test_native_packed_intervals.py` | `7ebbd67472793eef6b82170285883464db87a870999fb96b52a4a01e3eb6282b` |
