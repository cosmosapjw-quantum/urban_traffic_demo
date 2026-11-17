# 진입 측도 투영 이후의 자원 병목과 후속 구현 계약

기준일: 2026-11-17. 현재 구현의 실제 Valley pilot는 `h=1 s`, `dt=10 s`에서
26,010 s까지 진행한 뒤 `BLOCKED_RESOURCE`로 종료했다. 실패 분류와 마지막 유효
상태를 유지한다. 이 문서는 코드 변경 없는 후속 인계다. 아래 EventBatch는
**제안·미구현**, scaled mark block 공유는 별도 이론 후속이며 현재 검증된
candidate에 포함되지 않는다. 어떤 항목도 전체 24시간 실행 성공을 뜻하지 않는다.

## 1. 실행 근거와 상태의 구분

SSOT는 `artifacts/v1_entry_projection_20261117/VALLEY_PILOT.json`이다.

- native binary SHA-256:
  `b34832c7803e5ca2be5e7c1a1f83c2d2a83faf29ca7d7956e4943a01f1ce57a3`.
- 해당 `v1_road.rs` SHA-256:
  `47179f9973ed66f909159377e069cd65d8f822f8f956154ccfc75b73a19846aa`.
- pilot JSON SHA-256:
  `f8c25f78da4c17e5d525a4c4a6c9ea59048366791809d4309652e86de155582d`.
- 실패: `phase=transfer candidates`, required `4,538,183,888 B`,
  phase budget `4,538,183,714 B`. 다음 candidate가 한도를 174 B 초과했다.
  이 차이는 작은 예산 증액으로 캠페인이 해결된다는 근거가 아니다.
- 마지막 유효 road: 10,530,239 parts / 14,103 packets,
  vector capacity 433,478,944 B. Uniform 4,554,089 parts와
  Mixed 5,976,150 parts가 있다. `part_capacity == total_records`이므로
  이 snapshot의 주된 문제가 불필요한 Part Vec capacity라는 해석은 맞지 않는다.
- 마지막 유효 journey: 12,829,076 records,
  dynamic storage 416,864,464 B. 마지막 service events는 5,187,668행이다.
- 마지막 **검증된** projection: 입력 5,059,064 → 출력 3,540,968 parts,
  5,243 cohorts, 2,600 protected support boundaries. 행 감소는 약 30.0%,
  압축비는 약 1.429배다. 새 cohort당 평균 675.37 categories이고, 보관된 road
  packet당 평균 746.67 parts다. tag·remaining route를 유지하는 비용이 크다.
- 실패 proposal은 26,010 s에서 시작한 `road_step`이며 commit하지 않았다.
  위 projection 진단은 실패 proposal의 결과가 아니다.
- wall 285.713 s, peak RSS 3,176,062,976 B. 구조적 동시 생존 예산과 RSS는
  다른 관측량이다. RSS가 phase budget보다 작다는 사실로 guard를 무효화하지 않는다.

기존 exact guard의 25,650 s와 비교하면 시뮬레이션 시간으로 360 s 더 진행했다.
이는 이번 설정의 관측된 개선이며, 비용 성장률의 변화나 하루 완주의 증거는 아니다.

## 2. 실패 phase의 구체적인 비용식

현재 코드에서 `RoadWorkBudget::transfer`는 매번 서비스되는 head packet의
전체 Part 수를 event counter에, 그중 다음 road destination이 있는 Part 수를
incoming counter에 더한 직후 `require`를 호출한다. 이 검사는 `portion`과
그 결과의 실제 push보다 앞선다. 같은 head를 부분 서비스하면 그 head의 categories를
다음 서비스에서도 다시 센다. counter는 고유 차량·고유 tag 수가 아니다.

64-bit 대상에서 현재 layout은 다음과 같다. 다른 ABI에는 이 수치를 이식하지 말고
`size_of`와 실제 native layout 보고로 다시 확인한다.

| 형식 | 포함 정보 | 행 크기 |
|---|---|---:|
| `EventRow` | tag, source, optional destination, mass, start, end, birth | 64 B |
| `Part` | tag, offset, mass, birth, packed start/end | 48 B |
| `Mark` | class, mass, entry speed, latent mark | 32 B |
| `CorePart` | tag, offset, mass, birth; time은 packet 공통 | 32 B |

결합 실행에서, 생성 event 수를 E, incoming 수를 I, 기존 입력/현재 service event
buffer capacity bytes를 각각 E_input, E_current라 하면 transfer phase의 식은
다음과 같다. E>0일 때 작은 Vec 최소 capacity 항을 제외한 식이다.

```
required = base
         + E_input + E_current + 3 * E * 64 + 96
         + 2 * I * (48 + 32)
         + interval_retained + interval_transient + extra
```

이 phase에서는 projection output을 아직 만들지 않았으므로 interval 항과 extra는
통상 0이다. 따라서 내부 road transfer Part 한 행당 증가분은
`192 + 160 = 352 B`, sink로 나가는 Part 한 행당 증가분은 `192 B`다.
실제 증가 단위는 한 head의 전체 categories다. `3 * E`는 event Vec가 증가할 때
이전·새 allocation이 함께 살아 있는 보수적 envelope이며, 세 벌의 물리 event가
관측됐다는 뜻은 아니다.

`base`에는 적어도 다음 항이 들어간다.

```
3 * max(state_retained_bytes, retained_input_bytes)
+ 32 * state_part_rows
+ offers_len * (4 * sizeof(Part) + sizeof(Offer))
+ 96 * max_cell_parts
+ groups * (1024 + classes * 1024)
```

원래 call-input immutable snapshot, 현재 owner, candidate와 기존 검산·분할
scratch가 동시에 존재하는 수명을 고려한다. 입력 snapshot이 언제 생겼는지는
같은 물리시각의 checkpoint만으로 정해지지 않는다.

road에 주어진 phase budget은 dynamic shared pool에서 journey의 알려진 동시
생존량을 먼저 뺀 값이다. 이번 수치에서는
`5,789,366,594 - 4,538,183,714 = 1,251,182,880 B`가 빠졌고,
세 벌 기준 한 벌은 417,060,960 B다. 마지막 committed journey의 416,864,464 B와
동일하지 않은 것은 prepare candidate를 포함한 phase의 최대 생존량을 쓰기 때문이다.

### 왜 투영이 이 검사에 앞서지 못했는가

현재 순서는 다음과 같다.

1. 전체 junction service loop에서 EventRow, raw incoming Part, Mark를 보관한다.
2. 살아남은 road queue를 candidate로 이동하고 source admission을 처리한다.
3. cell별 incoming을 combine한 뒤 support 경계와 시간 격자를 계산한다.
4. projection cohort를 만들고 state·ledger·storage 검사를 거쳐 commit 후보를 반환한다.

실패는 1번 안에서 발생했다. 그러므로 이번 h=1 정책은 이전 tick에서 보관한 road
state를 줄였지만, **이번 tick의 모든 전송 후보를 먼저 구체화하는 비용**은 제거하지
못했다. 임의로 먼저 작은 chunk를 투영하면 아직 도착하지 않은 interval의 movement
support를 놓칠 수 있으므로, chunking만으로 이 순서를 바꾸는 것은 같은 정책이 아니다.

코드 provenance: `v1_road.rs`의 `RoadWorkBudget::require/transfer`,
`ServiceEventAccounting::road_step_bytes`, `step_state`의
`work.transfer(packet.parts.len(), incoming_count)`와 최종
`projected_packets` 호출을 참조한다. 현재 파일에서 각각 약 539–581,
325–333, 2493–2498, 2763–2765행이다. 행 번호보다 위 SHA와 함수가 기준이다.

## 3. 한 가지 구체적 후속: exact EventBatch와 공통 header

첫 구현 후보는 **event 자체의 구체화·보관 표현을 바꾸는 것**이다.
모든 tag event, 질량, birth, source/destination, start/end와 iteration 순서를
그대로 유지한다. sink가 아닌 event를 삭제하거나 관측 가능성을 제거하지 않는다.

한 head를 한 서비스 구간에서 처리할 때 source, start, end는 모든 Part에 공통이다.
이를 공통 header에 한 번 쓰고, 각 Part에는 tag, destination, mass, birth만 둔다.
예시 구조는 다음과 같다.

```
EventBatch {
    source: usize,
    start_bits: u64,
    end_bits: u64,
    rows: Vec<EventCore>,       // 이 batch의 정확한 row count로 fallible reserve
}
EventCore {
    tag: usize,
    packed_destination: usize, // usize::MAX는 sink; 실제 group index와 충돌 금지
    mass_bits: u64,
    birth_bits: u64,
}
```

`EventCore`는 64-bit에서 32 B, batch header와 Vec는 대략 48 B다.
E개 events와 H개 batch의 payload는 대략 `32 E + 48 H`가 된다.
이는 기존 `64 E`와 비교할 식이며 실제 padding/allocator 측정 전 확정 byte
명세가 아니다. 많은 작은 batch에서는 header 이득이 사라질 수 있으므로 H와
batch row-count 분포를 먼저 측정한다.

또한 global EventRow Vec를 계속 재할당하는 대신 batch별 정확한 row 수를
예약하면, 이미 채운 모든 event rows를 복사하는 old/new 대형 buffer 공존을
피할 수 있다. 바깥 batch Vec가 증가할 때는 작은 header들만 이동한다.
**실제 allocation을 바꾼 뒤 그 수명을 다시 계상하는 구현**이다. 현재 `3 E` 계수를
그대로 낮추는 guard 완화가 아니다. allocation 실패는 여전히 candidate를 폐기한다.

마지막 event 수 5,187,668에 대해 기존 row payload의 최소치는 332,010,752 B다.
core만으로는 166,005,376 B이고 batch header·allocator overhead가 추가된다.
같은 E를 새 candidate에 대입한 기존 `3 * 64 E` 항은 996,032,256 B다.
이 계산은 잠재적 상수배 절감의 크기를 설명한다. **실패 순간의 E는 현재 JSON에
없으므로 실제 실패 tick 절감량으로 쓰면 안 된다.**

기존 `PacketParts::Uniform`도 공통 a/b를 packet에 두고 `CorePart`를 보관한다.
`PackedTime`은 finite clock의 IEEE payload를 유지한다. 이는 공통 header 표현을
이미 사용한 코드 provenance지만, EventBatch의 올바름을 대신 검증하지는 않는다.
특히 projected Mixed cohort에는 tag별 centroid가 다르므로 이를 공통 time으로
억지로 바꾸지 않는다.

### 구현 경계와 반드시 지킬 호환성

- Road 내부 반환형과 `NativeServiceCore.last_events`, coupled runner의 event
  iteration·storage accounting이 함께 바뀌어야 한다. road 끝에서 즉시 기존
  `Vec<EventRow>`를 전부 다시 만들면 주요 이득을 잃는다.
- 기존 순서의 `(tag, source, destination, mass, start, end, birth)`를 만들어내는
  ordered iterator를 제공한다. 부동소수점 연산은 추가하지 않고 원래 bit를 보관한다.
- service/journey가 쓰는 sink iterator도 같은 순서와 값을 유지한다.
  현재 `v1_journey.rs` 1565–1572행은 sink만 소비하지만, 1693행에서 전체 events를
  보관하고 467–477행에서 전체 events를 checkpoint에 쓴다. 관측자를 생략해서
  비용을 줄이는 구현은 이 제안과 다르다.
- checkpoint writer는 기존 row wire 순서로 **streaming** 직렬화한다. compatible
  checkpoint reader 역시 decode 중 제한을 확인하고 batch 표현을 구성해야 한다.
  Python `road_events()` 또는 직접 road API처럼 기존 row 결과를 명시적으로
  요청하는 경계에서만 materialize하며, 그 별도 allocation도 예산 검사를 한다.
- 기존 exact h=0 및 h>0의 state/events 값과 순서를 대조한다. 같은 model과 resource
  binding에서 기존 checkpoint의 read, 이어서 진행, write bytes가 유지되는지 검증한다.
  resource accounting binding을 바꿀 필요가 생기면 과거와 섞지 않고 명시적으로
  version한다. 단순 wire 호환과 resource-policy 호환을 혼동하지 않는다.
- layout의 `size_of`, batch capacity, retained owner/input/candidate, growth 중 peak와
  clone/checkpoint decode 수명까지 guard 식에 포함한다. 동일 process address-space
  한도 아래 accounting envelope와 actual allocation/RSS를 함께 기록한다.
- 실패 원자성, source/sink destination sentinel, 빈 event stream, 한 행 batch,
  다중 목적지 head, 반복 부분 서비스, 동일 시각의 서로 다른 batch를 검사한다.

## 4. 최소 추가 실측과 판정선

새 전체 도시 캠페인을 먼저 반복할 필요는 없다. 다음 두 측정으로 구현의 기대
효과를 구체화할 수 있다.

1. 기존 last-valid event stream에서 연속 `(source, start_bits, end_bits)` 구간의
   수 H와 row-count 분포, 현재 event buffer capacity를 측정한다. 이는 값의
   재계산이 없는 read-only census다. binary checkpoint에 있는 event 구간을
   streaming으로 읽으면 대형 Python event list 생성도 피할 수 있다.
2. 필요한 경우 알려진 실패 직전 구간만 기존 candidate와
   `METROFLOW_BUDGET_TRACE=record`로 재현한다. 이 모드는 guard 결정을 바꾸지 않는다.
   `budget_trace_snapshot()`에서 `road_work:transfer candidates`의 base,
   event_bytes, incoming_rows, interval 항, extra와 event batch 관련
   `xfer.serve_rows`의 calls/sum/max를 보존한다. observe 모드나 guard 우회는 쓰지 않는다.

saved 26,010 s checkpoint에서 새 호출을 시작하면 call-input에도 5,187,668개의
last events가 생긴다. 원래 여러 tick을 이어서 실행하던 호출의 input buffer와는
다를 수 있다. 따라서 이 재현의 required bytes를 원래 수치와 동일하다고 주장하지
말고 E_input, E_current, 생성 E와 I, 호출 시작 시각을 별도로 기록한다. 원래 phase
식의 완전 동일 대조가 필요할 때만 동일 call 시작 snapshot·tick 묶음을 재사용한다.

구현 후 첫 판정은 해당 국소 구간에서 event byte/순서 동일성과 실제 allocation
감소를 동시에 확인하는 것이다. 통과하더라도 road의 tag별 parts와 journey histories는
계속 증가할 수 있다. 이 상수배 최적화만으로 24시간을 보장하거나 현재
`BLOCKED_RESOURCE`를 해제하지 않는다.

## 5. scaled mark block 공유와의 연결

별도 이론 후속의 scaled mark block은 반복 부분 서비스에서 동일 tag 조성을
매번 새 Part 배열로 복제하는 구조를 더 직접적으로 다룬다. immutable category
block과 서비스량·구간 계수를 공유할 수 있다면 road cohort, transfer workspaces,
향후 journey mark 표현까지 재사용의 범위를 넓힐 수 있다. 이에 관한 유도·동치 조건은
`CONSERVATIVE_MARK_BLOCK_NEXT_KO.md`의 후속 분석을 따른다.

EventBatch는 그 구조의 작은 선행 구성요소가 될 수 있다. 공통 시간·source header와
mark rows의 분리를 도입하지만, 현재 제안은 **계산된 mass/birth bit를 그대로 보관**한다.
반면 scaled block은 `mass * fraction`을 언제 구체화하는지 바꿀 수 있으므로 실수
산술 동치가 곧 기존 binary64 실행의 bit 동치가 되지는 않는다. 연속 부분 분할의
rounding, birth moment, per-category centroid, 다른 movement support와 이후 route
분기, block의 잔여 부분과 소유권 수명을 따로 계약하고 검증해야 한다.

두 후속의 완료 상태를 합치지 않는다. 이번 candidate는 support-preserving entry
projection의 구현·한정 검증과 실제 자원 실패를 보존한 상태이며, EventBatch 및
scaled mark block은 다음 구현을 위한 구체적인 인계다.
