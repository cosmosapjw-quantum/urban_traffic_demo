# V03 외부 감사용 요약: 결과, 근거, 남은 선택지

대상: 외부 감사자 · 기준 2026-11-17 · 저장소 `cosmosapjw-quantum/urban_traffic_demo`,
브랜치 `v1/v03-acceptance-20261027`(draft PR #41). 규범 계획은 `docs/v1/PLAN.json`(v1.1.26)이다.

## 1. 한 줄 판정

V03(주민 10만·전체 수요·세 도시 각 3회 86,400초 실행)은 **미수용·BLOCKED**다. 24시간 완료 **0/9회**,
DAG 진척 **19/21(90.5%)**. 차단 원인은 계상 오류가 아니라, 혼잡 진입 시 정확한 도로 interval packet 표현의
packet 수가 약 50 모의초마다 두 배로 늘어 8 GiB 메모리·7,200초 wall 한도 안에서 하루를 진행할 수 없다는 것이다.
이 결론은 직접 측정에 근거하며, 해결에는 물리 계약 또는 범위에 관한 사용자 결정이 필요하다.

## 2. 고정 조건 (변경하지 않음)

| 항목 | 값 |
|---|---|
| 인구·수요 | 주민 100,000, 전체 달력 수요, 질량 삭제·수요 축소 없음 |
| 사례 | river weekday s17, coastal weekend s41, valley weekday s7 |
| 한도 | native 계상 6 GiB, process 8 GiB(RLIMIT_AS), 실행당 wall 7,200 s |
| 수치 | 질량 상대허용오차 1e-9 등 기존값, 시간 binning 없음, 1 worker |

## 3. 작업 순서와 결과

| 단계 | 내용 | 결과 | 근거 |
|---|---|---|---|
| 기준 | `532effe` 첫 실행 3회 | 25,350/32,660/25,600 s에서 계상 guard 차단, RSS 2.0–2.6 GiB | `../v1_rust_completion_20261116/RECEIPT.json` |
| 1 | 차단 checkpoint를 같은 binding으로 재적재, counting allocator 진단 | 실제 Rust heap 2.4–3.2 GB인데 guard 요구 >6 GiB: 수명 불일치 과대계상 | `WORKSPACE_PROBE.md` |
| 2 | 계상 교정 `retained_capacity_v3` (`7e3748a`, `adde1a3`) | 260 scoped 검사, Rust 단위 5개 통과; 물리 경로 불변 | `RECEIPT.json` |
| 3 | 짧은 재현 게이트(이전 차단+3,600 s) | 25,650/32,730/25,420 s에서 다시 차단(약 50–70 s 전진) | `gate_final_*.json` |
| 4 | guard 우회 진단(전일 목표) | road part가 수십 초마다 배가; Valley는 25,700 s에서 **실제 할당 실패**(8 GiB 주소공간) | `diag_observe_*.json` |
| 5 | 선택 (a) 귀속 | 새 행의 약 80%가 head packet 부분 서비스에서 생성; bit 동일 병합 상한 약 2% | `ATTRIBUTION_KO.md`, `ATTRIBUTION.json` |
| 6 | 선택 1 사전측정 | 실수 산술 정확 병합은 packet 수를 1.01–1.08배만 감소; 조성 공유는 상수배 | `ATTRIBUTION_KO.md` 후반, `attrib4_valley.json` |

공식 3×3 캠페인·checkpoint 재개·matched refined-dt 대조는 같은 원인이 세 사례에서 재현되어 **실행하지 않았다**
(`NOT_RUN_DEPENDENCY_BLOCKED`). 이는 통과·실패 판정이 아니라 미실행이다.

## 4. 증가 기제 (관측과 해석의 구분)

**관측 (Valley, 25,600→25,650 s):** road 행 약 7.2 M 증가 중 부분 서비스 +7.21 M, interval 분할 +2.07 M,
새 offer +0.77 M, combine 병합 −0.59 M, sink −0.46 M. 50초 구간마다 packet 수·부분 서비스 수가 약 2–2.6배,
같은 구간 계산 시간 5.1 s → 91.3 s.

**해석 (코드 구조 근거):** 부분 서비스 한 번마다 head packet은 남고, 그 모든 행의 사본이 새 시간 구간을 가진
downstream packet이 된다. 그 packet이 다음 cell에서 다시 부분 서비스되며 되먹임이 생긴다. 한 tick에 같은 cell로
들어온 packet은 같은 ready 시각을 가지므로, 비례 조성인 인접 packet만 실수 산술에서 정확히 병합 가능하지만,
도착 cell에서는 여러 source head가 번갈아 기여해 그런 쌍이 드물다(1.01–1.08배).

## 5. 검증 범위와 한계

- **확인됨:** scoped native·packet·PLAN 검사 260개; legacy 점유 구간 25,240→25,340 s replay가 checkpoint
  `ef4719a8…`를 3회 동일하게 재현(계상·계측 변경이 물리 bit를 바꾸지 않음); 독립 diff 리뷰 1건(MAJOR 1건 수정).
- **진단 build:** guard 우회(`observe`)와 counting allocator는 `budget_trace` feature 진단 binary에서만 존재하며
  campaign 후보가 아니다. 진단 실행 결과는 원인 측정용이며 수용 근거가 아니다.
- **미실행:** 전체 저장소 CI, 통합, main merge, release, 최종 ACCEPTED 심사, RLS01, 3×3 캠페인.
- **환경:** 공유 host(다른 세션 약 9 GB RSS, swap 사용)에서 측정. wall 수치는 공식 성능 수치가 아니다.
- **해시·재현:** 모든 산출물의 SHA-256은 `RECEIPT.json`의 `evidence_sha256`에 있다. checkpoint·binary 원본은 로컬
  보존(`../v1_rust_completion_20261116/LOCAL_CHECKPOINTS.json`, frozen v2 binary `3e0696…`)이며 Git에 넣지 않았다.

## 6. 남은 선택지 (사용자 결정 필요)

세 경로 모두 현재 계약의 어느 하나를 바꾼다. 감사 시 "무엇을 바꾸는가"와 "무엇으로 검증하는가"를 함께 보아야 한다.

| 선택지 | 바뀌는 것 | 장점 | 위험·비용 | 필요한 검증 |
|---|---|---|---|---|
| **A. 근사 interval 집계** — 같은 cell queue의 인접 packet을 조성이 달라도 정해진 오차 상한 아래에서 병합(예: 시간 분포 모멘트 보존) | 현재 금지된 시간 binning에 해당; 물리 계약(C_RUNTIME/수치정책) 개정 | 표현 크기를 유한하게 묶을 수 있는 유일한 직접 경로 | 결과가 정확 모델과 달라짐; 오차 상한 정의가 사후 완화로 보이지 않도록 사전 고정 필요 | 사전 정의 허용오차, 정확 모델과의 짧은 구간 대조, 보존 장부, refined-dt 대조 |
| **B. 모델 변경** — 부분 서비스가 downstream packet을 만드는 방식·event 해상도 변경(예: tick 내 head 출력의 단일 구간화) | road FIFO의 물리 정의 | 증가 기제 자체를 제거할 수 있음 | 기존 검증(T02–T04 등)의 일부 재검토, 이전 checkpoint 의미 단절 | 해석해·유한응답 검산, 보존, 대칭 검사 재실행 |
| **C. V03 범위 재검토** — 예: 24h gate의 해상도·규모·혼잡 구간 기준 재정의 | 수용 기준(release gate G-DAY/G-SCALE) | 코드 위험 최소 | 원래 제품 목표(10만·24h)에 못 미침 | 사용자 승인된 새 기준과 PLAN 버전 갱신 |

**고려했으나 불충분으로 기각:** (a) bit 동일 병합(상한 약 2%), (1) 실수 산술 정확 비례 조성 표현(packet 수 1.01–1.08배 감소,
메모리 상수배 이득만으로는 수 분의 모의시간 연장). 근거: `ATTRIBUTION_KO.md`.

## 7. 주요 commit

| commit | 내용 |
|---|---|
| `7e3748a` | 수명 기반 계상 `retained_capacity_v3` |
| `adde1a3` | 리뷰 지적(packet slot) 수정, 계측 항목 |
| `a828d4f` | 게이트·guard 우회 진단·차단 재분류 기록 (PLAN 1.1.24) |
| `6e6041a` | 선택 (a) 귀속 (PLAN 1.1.25) |
| `0c55c97` | 선택 1 사전측정 (PLAN 1.1.26) |
