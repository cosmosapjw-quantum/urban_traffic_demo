# 차단 checkpoint의 작업공간 실측 (진단 전용)

2026-11-17 · 입력: `532effe` campaign의 세 last-valid checkpoint (`retained_capacity_v2` binding 그대로).
도구: [PROBE_WORKSPACE.py](PROBE_WORKSPACE.py), 진단 binary `742624d1…`(동일 소스 + `budget_trace` feature).
요약 수치: [WORKSPACE_PROBE_SUMMARY.json](WORKSPACE_PROBE_SUMMARY.json); 원자료 `probe_{river,coastal,valley}.json`.

**범위:** 진단 binary는 counting allocator로 Rust heap live bytes를 세고, `observe` 모드에서
guard 초과를 기록한 뒤 계속 진행했다. 초과 이후의 tick은 측정용이며 campaign 상태나
수용 근거가 아니다. 기존 checkpoint 헤더·binding은 수정하지 않았고, 세 경우 모두
load 직후 보고서가 원래 receipt의 last-valid 보고서와 같았다(`loaded_report_identical=true`).
Python 객체 heap과 allocator metadata는 counted Rust heap에 포함되지 않는다.

## 관측: guard 요구량 vs 실제 동시 live heap

| 사례·tick 끝 | counted Rust heap peak | process peak RSS | 최대 비율 guard | 요구/허용 |
|---|---:|---:|---|---:|
| River 25,370s | 2.645 GB | 2.904 GB | checkpointability | 1.003 |
| River 25,380s | 2.817 GB | 3.021 GB | checkpointability | 1.103 |
| Coastal 32,680s | 2.713 GB | 2.820 GB | road packet interval packing | 1.099 |
| Coastal 32,690s | 2.869 GB | 3.000 GB | road packet interval packing | 1.233 |
| Valley 25,610s | 2.359 GB | 2.643 GB | road packet interval packing | 1.046 |
| Valley 25,630s | 3.214 GB | 3.160 GB | road packet interval packing | 1.409 |

모든 tick에서 실제 heap은 6 GiB 계상 예산의 절반 수준인데 guard는 이를 넘었다.

## 관측: 항목 분해

- **Coastal/Valley road step**: `event_bytes`가 2.35–4.40 GB로 지배 항목이다. Valley 25,630s에서
  base 1.51 GB, event 4.40 GB, interval rows 5.58 M(×144 B = 0.80 GB). 같은 tick의 실제 candidate
  event 버퍼는 0.54 GB였다. 소스상 이 항은 생성된 **모든** event 행에 대해 3×2× 성장 여유(336 B),
  sink 행(120 B), sink 문자열 2개, sink map(256 B)을 road step 동안 부과한다.
  그러나 sink는 road step이 반환한 **뒤** `e.2 == None`(출구) event에 대해서만 만들어진다.
- **Entry interval split**: `interval_rows`가 step 전체 누적이며 행마다 3×48 B를 부과한다.
  실제 `point`/`split` Vec, `combine()` 색인·출력은 각 구간 끝에 해제되고, packed 행만 candidate로 이동한다.
- **River checkpointability**: `validation_scratch` 상한 2.06–2.07 GB가 지배 항목이다.
  실제 검증은 `HashMap<usize, Sum>`이며, 상한은 key 수 `min(rows, legs)`의 4× 성장 계수다.

## 관측: River 재로딩 전후 차이 = capacity만

| River 25,350s | 원래 실행(실패 진단) | 새 프로세스 load |
|---|---:|---:|
| entering 행 | 8,938,145 | 8,938,145 |
| entering stage capacity / block | 10,781,774 / 43,288 | 8,938,240 / 34,915 |
| journey dynamic storage | 360,612,800 B | 299,477,456 B |
| road parts / capacity | 2,210,205 / 2,210,205 | 2,210,205 / 2,210,205 |

물리 행·보고서·재저장 바이트는 같고, 차이는 부분적으로 채워진 stage block의 capacity
(단편화)뿐이다. 재로딩 직후 한 tick이 더 진행된 이유가 이것이며, 다음 tick부터는 다시
같은 guard가 초과됐다. 따라서 재로딩은 해결책이 아니다.

## 분류와 조치 (`retained_capacity_v3`, commit `7e3748a`)

| 항목 | 분류 | 조치 |
|---|---|---|
| road step의 sink envelope | 수명 불일치(아직 없는 버퍼) | road step은 input+current+candidate(재할당 시 3행분) event 버퍼만; sink envelope는 road step 후 **실제 출구 수**로 별도 guard |
| `interval_rows` 3×48 B 누적 | 수명 종료 후 누적 | 현재 구간 workspace + candidate로 이동한 packed 행의 실제 allocation만 |
| validation map 4× 상한 | 보수 상한(구조 교체 가능) | `(leg<<32|row, mass)` 제자리 정렬 → 각 leg에 같은 순서의 `Sum::add`; 16 B/행 + 8 B/leg 정확식 |
| stage block 단편화 | 실제 capacity slack | 이번 변경 범위 밖(필요 시 lossless 재압축 후보) |

물리 경로는 바뀌지 않는다. 검증: Rust 단위 회귀 5개(구 HashMap 경로와 bit 동일, 구간 workspace 해제,
sink 항 분리), scoped 260 검사, legacy 점유 구간 25,240→25,340s 3회 checkpoint `ef4719a8…` 동일.
