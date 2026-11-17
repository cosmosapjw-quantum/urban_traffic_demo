# EventStore: 공통 header를 공유하는 road event 저장 (bounded unit 2)

2026-11-17 · 기준 `11775f7`(632bbc7 + support census) · 새 binary `a0077a07…`
· 비교 binary(게시 후보) `b34832c7…` · resource binding `retained_capacity_v4`.

## 변경

- `EventStore`(`crates/metroflow-rust/src/v1_road.rs`)가 `Vec<EventRow>`를 대체한다.
  - 연속된 행이 같은 `source`와 bit 단위로 같은 `start`/`end`를 가지면 하나의 header(32 B)를 공유한다.
  - 행 자체는 `tag`, 목적지, `mass`, `birth`만 둔다(32 B). sink는 `usize::MAX` sentinel로 표시하고, 실제 index와 충돌하면 거부한다.
  - 모든 f64는 원래 bit 그대로 보관하며 연산을 추가하지 않는다.
- 행과 header는 **고정 용량 chunk**(65,536행 / 4,096 header)에 정확히 예약된다. 따라서 큰 event 버퍼가
  두 배로 재할당되며 이전 버퍼와 함께 살아 있는 일이 없다. 증가하는 것은 작은 chunk pointer 벡터뿐이다.
- `iter()`는 원래 `(tag, source, dest, mass, start, end, birth)` 순서와 값을 그대로 낸다. checkpoint wire 형식,
  journey sink 소비, service 검증은 그 iterator를 쓴다. 행 전체를 만드는 곳은 `road_events()` 같은 명시적 row API 경계뿐이다.
- 계상은 새 소유·수명에서 다시 유도했다: road step 동안 `input + current + upper_bytes(E, H)`.
  `upper_bytes`는 채워질 chunk 전체와 pointer 벡터의 재할당 공존을 덮는다. H는 서비스 호출 수로, 실제 header 수의 상한이다.
  checkpoint decode의 행 한도는 최악(행마다 header 1개, 64 B/행 + chunk 여유)으로 계산한다.
  - 계상식이 바뀌므로 binding을 `retained_capacity_v4`로 올렸다. v3 checkpoint를 새 정책으로 재해석하지 않는다.

## 검증

| 항목 | 결과 |
|---|---|
| Rust 전체 단위 검사 | 69 passed (EventStore 4개 신규: chunk 경계를 넘는 순서·bit, header 병합 조건(−0.0 구분 포함), sentinel 충돌 시 부분 행 없음, 채우는 동안 `allocated ≤ upper` 및 decode 한도) |
| Python 회귀 (projection·native·driver·journey·plan 302개) | 297 passed, 5 failed. **실패 5개는 게시 binary `b34832c7`에서도 동일하게 실패**한다(게시 binary는 binding 기대값 1개 포함 6 failed). 새 실패는 없다. |
| 동일 입력 Valley h=1 prefix 0→25,900 s, 두 binary 순차 실행 | 보고서·debug 상태(저장 계상 제외) 동일. checkpoint 903,148,860 B는 같은 길이의 binding 문자열만 다르며, 정규화하면 SHA-256 `ab73c40f…`로 **동일** |

## 측정 (같은 prefix, 25,200→25,900 s 호출)

| 관측 | 게시 binary | EventStore | 변화 |
|---|---:|---:|---:|
| transfer guard의 event 항 | 974,356,192 B | 231,217,128 B | −76.3% |
| transfer guard 요구량 (allowance 대비) | 2,647,975,280 B (0.535) | 1,904,836,216 B (0.385) | −28.1% |
| 실제 transfer 버퍼(events+incoming+marks) | 687,920,576 B | 539,286,560 B | −21.6% |
| events / headers | 3,676,670 / — | 3,676,670 / 4,447 | header당 약 827행 |
| process peak RSS | 2,539,683,840 B | 2,145,710,080 B | −15.5% |
| wall (공유 host, 참고용) | 235.5 s | 223.7 s | — |

## 실제 pilot (handoff 명령, 26,100 s 목표)

- 결과: **BLOCKED_RESOURCE, 마지막 유효 26,050 s**(게시 후보 26,010 s, +40 s).
- 실패 단계: `entry interval split`, required 4,307,007,920 B > budget 4,282,459,002 B. transfer 단계는 더 이상 한도가 아니다.
- peak RSS 3,543,003,136 B, wall 336.8 s.
- 마지막 유효 road는 14,287,428 parts / 18,372 packets(packet당 약 778 category 행). journey 15,605,033 records, service events 7,206,642행.
- checkpoint(로컬 전용) `valley_eventstore_h1.last_valid.bin`, 1,788,414,564 B, SHA-256 `92bbdc09…`.

## 해석

EventStore는 event 표현의 상수배 비용과 재할당 복사를 제거했고, 물리 결과는 bit 단위로 같다.
그러나 차단은 다음 단계(진입 interval 분할)로 옮겨 갔을 뿐이다. 지배 비용은 cohort마다
category 벡터(약 778행)를 복제하는 road 표현 자체다. 이는 `CONSERVATIVE_MARK_BLOCK_NEXT_KO.md`의
immutable mark-block 공유가 겨냥하는 비용과 같다. 이 단위만으로 24시간 진행은 보장되지 않는다.
