# V03 작업공간 계상 교정과 실제 차단 원인 재분류

작성 2026-11-17 (KST). **24시간 완료 0/9회.** 세 도시 모두 짧은 재현 게이트에서 차단됐고,
같은 원인이 재현되어 공식 3×3 캠페인·재개·refined 대조는 실행하지 않았다(`NOT_RUN_DEPENDENCY_BLOCKED`).
DAG 진척은 **19/21(90.5%)**, V03 BLOCKED, RLS01 PLANNED(미착수) 그대로다.
전체 CI·통합·main merge·release·최종 ACCEPTED 판정은 별도 심사로 남긴다.

## 결론

1. **이전 차단의 1차 원인은 계상 수명 불일치였다(관측).** `532effe` checkpoint 세 개를 같은 binding으로
   다시 읽어 진단 binary로 측정했을 때, counted Rust heap은 tick당 2.4–3.2 GB였는데 guard는 6 GiB 예산을
   넘겼다. 지배 항목은 road step 동안 모든 event에 부과한 sink envelope, step 전체에 누적한 interval 행
   3×48 B, 검증 map의 4× 성장 상한이었다. 상세: [WORKSPACE_PROBE.md](WORKSPACE_PROBE.md).
2. **교정 후 남은 차단은 실제 물리 표현의 폭증이다(관측).** guard를 우회한 진단 실행에서 road part 행이
   아침 시작 구간에서 50–100 모의초마다 약 두 배로 늘었다. Valley는 guard 없이 25,700s에서 실제 할당이
   실패했고(`native road allocation unavailable`, 8 GiB 주소공간, peak RSS 6.20 GiB), Coastal·River도
   RSS 5.11/3.92 GiB로 증가하던 중 다른 guard에 걸렸다. 따라서 현재 guard는 실제 메모리 소진을 앞서
   막았으며, 계상 교정만으로 24시간 완주는 불가능하다.
3. 남은 해결책은 계상이 아니라 road의 정확한 interval packet 표현의 증가율 문제다. 이를 줄이는 방법은
   모델·표현 결정이고(시간 binning·허용오차 완화는 금지 사항), 사용자 결정이 필요하다.

## 교정 내용 (`retained_capacity_v3`)

| 변경 | commit | 근거 |
|---|---|---|
| road step: input+current+candidate event 버퍼만(재할당 시 3행분); sink envelope는 road step 후 **실제 출구 수**로 별도 guard | `7e3748a` | sink는 road step 반환 후 `e.2 == None` event에 대해서만 생성 |
| entry interval: 현재 구간 workspace + candidate로 이동한 packed 행의 실제 allocation | `7e3748a` | `point`/`split`/`combine` 버퍼는 구간 끝에 해제 |
| 검증 stage 합: `HashMap<usize,Sum>` → `(leg<<32\|row, mass)` 제자리 정렬, 각 leg에 원래 순서의 `Sum::add` | `7e3748a` | 16 B/행 + 8 B/leg 정확식; 구 경로와 bit 동일(단위 회귀) |
| interval packet slot과 cell packet 예약(이전 누적 항이 암묵적으로 덮던 부분) | `adde1a3` | 독립 리뷰 지적 반영 |
| env 기반 guard 여유 기록기; counting allocator·observe는 `budget_trace` feature 진단 build 전용 | 둘 다 | campaign build 결정 불변(리뷰 확인) |

검증(모두 `adde1a3` 또는 명시 후보):

| 항목 | 결과 |
|---|---|
| scoped native·packet·PLAN 검사 | **260 passed** (기존 251 + 분류 회귀 9) |
| Rust 단위 회귀 | 5 passed (stage 합 bit 동일, 구간 workspace 해제, sink 항 분리) |
| legacy 점유 구간 25,240→25,340s 3회 | checkpoint `ef4719a8…` 3회 동일(이전 후보와 같음); 물리 불변 증거 |
| 독립 diff 리뷰 | MAJOR 1건(packet slot 미계상) → `adde1a3`에서 수정; 실패 원자성·결정 불변 확인 |
| 이전 v2 checkpoint | v3 binding에서 재해석하지 않음; frozen binary `3e0696…`로만 읽음 |

## 짧은 재현 게이트 (`adde1a3`, binary `4e6ba9e1…`, 1 worker, 8 GiB RLIMIT_AS)

| 사례 | 이전 차단(532effe) | 새 차단 | wall | peak RSS | guard / 당시 road 행 |
|---|---:|---:|---:|---:|---|
| Valley weekday s7 | 25,600s | **25,650s** | 268.7s | 2.972 GiB | road transfer candidates / 16.5 M parts |
| Coastal weekend s41 | 32,660s | **32,730s** | 504.5s | 2.832 GiB | road transfer candidates / 11.4 M parts |
| River weekday s17 | 25,350s | **25,420s** | 1,209.5s | 2.665 GiB | road transfer candidates / 5.7 M parts |

이전 차단 구간을 50–70 모의초 넘었을 뿐 게이트(차단+3,600s)를 통과하지 못했다. wall은 다른 세션이
~9 GB RSS를 쓰는 공유 host에서 trace record 모드로 측정했으므로 공식 성능 수치가 아니다
(River 같은 구간 이전 측정 761s). 원자료: `gate_final_*.json`, `GATE_FINAL_*.log`; `7e3748a` 게이트는 `gate_*.json`.

## 실제 메모리 증가 (guard 우회 진단, 비-campaign)

| 사례 | 게이트 차단 시 road parts | 진단 종료 시각 / parts | 최대 cell parts | tick당 event | peak RSS | 종료 사유 |
|---|---:|---:|---:|---:|---:|---|
| Valley | 16.5 M @25,650s | 25,700s / **34.6 M** | 1.41 M | 17.4 M | 6.20 GiB | 실제 할당 실패(8 GiB 주소공간) |
| Coastal | 11.4 M @32,730s | 32,830s / **26.3 M** | 0.75 M | 12.2 M | 5.11 GiB | road state validation guard |
| River | 5.7 M @25,420s | 25,500s / **12.6 M** | 0.21 M | 5.0 M | 3.92 GiB | road state validation guard |

같은 진단에서 Valley 25,200s까지는 counted heap이 0.32 GB였다. 증가는 아침 수요 진입과 함께 시작되어
수십 초 단위로 배가된다. 원자료: `diag_observe_*.json`. Valley 진단은 `adde1a3`와 같은 Rust 소스를
commit 직전 작업트리에서 빌드한 진단 binary `2d52036c…`로 실행했다(receipt의 git_commit 필드는 `7e3748a`).

**유도(미검증 가설):** `interval_packets`는 cell로 들어오는 행을 모든 시작·끝 시각이 만드는 기본 구간마다
나누고(`count`는 그 구간을 덮는 행 수), 서로 다른 출발 cell의 event 경계가 섞이면 한 행이 여러 조각으로
갈라진다. 조각은 다음 transfer에서 다시 나뉘므로 혼잡 진입 시 행 수가 경계 수에 비례해 곱해질 수 있다.
이 귀속은 코드 구조에서의 추론이며 항목별 계측으로 확정하지 않았다.

## 남은 blocker와 선택지

- **Blocker:** 정확한 interval FIFO packet 표현의 행 증가율이 아침 진입 구간에서 8 GiB 안에 머물지 않는다.
  분류: 자원(물리 표현 규모); 수치 오류·장부 오류·OOM 외 환경 문제 아님.
- 수요 축소·질량 삭제·시간 binning·허용오차 완화·예산 상향은 하지 않았다.
- 가능한 방향(모두 사용자 결정 필요): (a) 분할 조각의 귀속 계측 후 bit 동일한 lossless 병합 조건 탐색,
  (b) 기본 구간 분할을 대체하는 정확한 표현(예: 행별 구간을 유지하는 mixed packet FIFO) 설계 — 물리 계약 변경 여부 심사 필요,
  (c) V03 수용 기준·범위 재검토.

## 보존

로컬 전용(Git 제외): 이전 campaign last-valid checkpoint 3개(경로·SHA는
[../v1_rust_completion_20261116/LOCAL_CHECKPOINTS.json](../v1_rust_completion_20261116/LOCAL_CHECKPOINTS.json)),
frozen v2 binary `artifacts/v1_rust_completion_20261116/budget_final_binary/`(`3e0696…`).
이번 게이트·진단은 checkpoint를 저장하지 않는 짧은 실행이며 새 last-valid 파일은 없다.
