# mark_block_scaled_v1: 불변 category block 공유 (bounded unit 3)

2026-11-17 · 기준 `82cfc7a`(EventStore) + `bccbc5a`·`952b34e` cherry-pick(`127276d`, `c2f6dd7`)
· 구현 `f825a64`, 계상 보완 `0c0206e` · 영수증 `RECEIPT.json`.
설계 근거: `docs/v1/CONSERVATIVE_MARK_BLOCK_NEXT_KO.md` §3–8.

## 1. 결론

- **관측**: 같은 Valley `h=1 s`, `dt=10 s` 입력의 0→25,900 s prefix에서 road 보유 저장이
  행 표현 vector capacity 285.8 MB → retained 118.7 MB, peak RSS 2.146 GB → 1.364 GB(−36.4%),
  checkpoint 903 MB → 628 MB(−30.5%), transfer guard 요구량 1.905 GB → 1.493 GB(−21.6%)로 줄었다.
- **관측**: 전체 pilot은 여전히 **BLOCKED_RESOURCE**, 마지막 유효 26,080 s(행 표현 26,050 s, +30 s).
  실패 단계는 `entry interval split`에서 `transfer candidates`로 이동했다
  (required 4,027,672,896 B > budget 4,027,620,138 B).
- **도출**: road 보유 상태(196 MB)는 더 이상 지배 항이 아니다. 차단 시점에는 (1) 논리 행 수에
  비례하는 보수적 작업공간 계상과 실제 per-row scratch, (2) 매 step 펼쳐지는 service event 행(11.1M),
  (3) journey 기록(18.3M)이 지배한다. 같은 tag가 여러 view term에 나타나 논리 행이 행 표현보다 빨리
  증가한다(§5). 표현 변경은 상수배 이득이며 아침 진입 구간의 폭증(약 100–130 s마다 배가)을 해결하지 못했다.
- 기본 `rows` 경로는 도시 규모에서 bit 동일함을 확인했다(checkpoint SHA-256 `ab73c40f…` 동일).

## 2. 표현과 수치 정책

정책 이름 `mark_block_scaled_v1`. road identity의 `entry_projection_support_v1:<width>` 뒤에
`:mark_block_scaled_v1`을 붙인다. `h>0`에서만 허용하고 기본값 `rows`는 변경 없음. bounded 저장 정책의
resource binding은 이 표현에서만 `retained_capacity_v5`(행 표현은 `retained_capacity_v4` 그대로).

- `MarkBlock`(불변, `Arc` 공유, 결정적 `id`): 행 `(tag u32, offset u32, mass, birth, entry)` 32 B.
  행은 남은 경로 suffix `path[offset..]`와 tag로 **엄격 정렬**되어 모든 route-prefix view가 하나의 연속
  행 구간이고 view 안에서 다음 movement별 연속 run이 된다. 임의 subset mask를 만들지 않는다.
- `Term = (block, lo, hi, shift, lambda, entry)` 40 B. 논리 행은
  `(tag, offset+shift, lambda·mass, lambda·birth, entry)`, `entry`가 NaN이면 행 자신의 entry centroid.
- 부분 서비스: served 계수 `lambda·f`; remainder는 **제자리에서** `lambda·(1−f)` — 행 복사 없음.
  served term은 다음 movement별 sub-view(`shift+1`)로 receiving cell에 들어간다(route offset 혼합 없음).
- event·ledger·mark: served 논리 행을 `(tag, offset)`로 fsum 병합한 행(행 표현과 같은 키)으로 기존
  loop를 그대로 돌린다. event 질량은 contribution이 가진 계수와 같은 곱이다.
- entry projection: 시간 edge·support barrier·atom·grid 규칙은 행 표현과 같다(view의 distinct next
  movement가 행들과 같은 시각에 support를 바꾼다). 한 segment 안에서 같은 view의 조각은 `gamma·lambda`와
  entry moment를 fsum으로 합치고, 다른 view는 별도 term으로 둔다(숨은 저차원 근사 없음). source admission
  행(및 이 정책 하에서 서비스된 행 packet)은 기존 combine 후 cohort마다 새 block 하나가 된다.
- 양의 질량 underflow: `lambda·min_mass < f64::MIN_POSITIVE`(subnormal 포함)면 명시적 ArithmeticError.
  양의 질량을 조용히 버리지 않는다(행 표현의 반례 (a)와 달리).

**수치 동등성 구분**
1. 실수 산술: 같은 측도(질량·birth·entry 1차 모멘트, tag·offset·class·FIFO·movement support)의 재표현.
2. 부동소수점: `(m·f1)·f2` 대신 `m·(f1·f2)`, 병합 순서 변경 → bit 동일하지 않다. 작은 fixture에서
   질량·birth·entry 모멘트·event (tag,dest) 합계는 행 표현과 ≤1e-12 상대(실측 ~1e-16)로 일치.
3. bit 재현: 같은 정책·binary 안에서 checkpoint 저장/복원/재개는 bit 동일(단위 시험, 도시 규모 resave).
   **행 표현과의 bit 동일성은 주장하지 않는다.**

checkpoint wire(정책 활성 시에만): `t` 다음에 block 카운터와 도달 가능한 block pool을 id 오름차순으로
한 번씩 쓰고, packet은 kind(0 행 / 1 공유)와 term(id, lo, hi, shift, lambda, entry)을 쓴다. 복원 시 id
범위·순서, 행 양수·유한성·cell 일치·suffix 정렬, view의 공통 prefix, 계수 표현 가능성, term 정렬, 미참조
block을 검사하고 실패하면 거절한다. 행 표현 wire는 바이트 단위로 그대로다. `snapshot()/restore()`의
StateRow는 논리 행 export이며 복원하면 행 packet이 된다(그 경로의 계보 보존·bit 재개는 주장하지 않음).

계상(v5): state마다 도달 가능한 block payload를 id 기준으로 **한 번** 센다(다른 state와 공유된 block은
각 state에 다시 세므로 보수적). term 표, 새 block, served 행 materialization(`logical × 2 × Part`),
pool decode scratch를 할당 **전에** 검사하고 실패 시 후보를 버린다. per-logical-row 작업공간 계상(`rows×32` 등)과
incoming 계상(행당 `2×(Part+Mark)`)은 행 표현 공식을 보수적으로 그대로 두었다(상수·guard 완화 없음).

## 3. 검증 (실행한 것)

| 항목 | 결과 |
|---|---|
| Rust 단위 시험 전체 | 76 passed. 신규 7: 행 경로와 divergence→reconvergence·2 class 비교, 10⁴회 부분 서비스 무증가와 질량·birth·entry 보존, 계수 underflow 명시 실패, checkpoint 저장/복원/재개 bit 동일과 손상 거절, 할당 실패 시 상태 불변, 정책 identity/거절, ulp 경계 반례(§4) |
| Python 회귀(지정 목록 + 신규 `tests/v1/test_mark_block_native.py` 6 + `tests/v1/test_v03_counterexamples.py`) | 356 passed, 5 xfailed. xfail 5개는 반례 suite의 strict xfail 그대로. `bccbc5a`로 기존 5 실패 해소, 새 실패 없음 |
| Valley 25,900 s prefix: rows 경로(새 binary `5145e7c3`) vs 기준 `a0077a07` | report 동일, checkpoint 903,148,860 B SHA-256 `ab73c40f…` **동일** |
| Valley 25,900 s prefix: mark 경로(binary `67c720ba` = `f825a64`) | REACHED_HORIZON (§4) |
| Valley pilot 28,800 s 목표: mark 경로(binary `5145e7c3` = `0c0206e`) | BLOCKED_RESOURCE 26,080 s (§5) |
| Valley checkpoint 재적재→재저장 | 25,900 s(이전 binary가 쓴 파일)·26,080 s 모두 byte 동일. 25,900 s에서 한 step 재개 성공, 26,080 s는 같은 자원 사유로 다시 거절 |

## 4. 같은 입력 prefix 0→25,900 s (관측)

| 관측 | rows (기준·control) | mark_block_scaled_v1 | 변화 |
|---|---:|---:|---:|
| road packet | 10,327 | 10,355 | +28 |
| category 행 / 논리 행 | 6,597,345 | 8,694,737 | ×1.318 |
| 저장된 term | — | 339,147 | — |
| block / block 행 / block bytes | — | 21,182 / 3,149,008 / 102,582,656 | — |
| road 보유 저장(계상) | vector cap. 285,818,928 | retained 118,656,136 | — |
| service event 행(마지막 step) | 3,676,670 | 3,731,350 | +1.5% |
| journey 기록 | 8,432,096 | 8,451,861 | +0.2% |
| guard: transfer candidates | 1,904,836,360 | 1,492,822,720 | −21.6% |
| guard: road base 항 | 1,092,728,512 | 674,240,024 | −38.3% |
| guard: entry interval split | 2,044,338,392 | 1,500,818,696 | −26.6% |
| 실제 transfer buffer | 539,286,560 | 287,377,120 | −46.7% |
| guard: journey checkpointability | 2,353,331,532 | 1,852,060,156 | −21.3% |
| peak RSS | 2,145,710,080 / 2,146,484,224 | 1,364,283,392 | −36.4% |
| wall (공유 host, 참고) | 223.7 / 248.6 s | 270.6 s | +9–21% |
| checkpoint | 903,148,860 B | 627,919,030 B | −30.5% |

물리 report(execution) 차이는 5개 필드뿐이다. requested/released/pending, released intent 1차 모멘트는 동일.

| 필드 | rows | mark | 차이 | 상대 |
|---|---:|---:|---:|---:|
| persons.completed | 292.26080497874847 | 292.26380913279627 | +0.00300415 | 1.03e-5 |
| persons.active | 2011.4256847587405 | 2011.4226806046927 | −0.00300415 | 1.49e-6 |
| vehicles.completed | 231.1557644767189 | 231.15816779995558 | +0.00240332 | 1.04e-5 |
| vehicles.active | 1608.8442355233378 | 1608.8418322001012 | −0.00240332 | 1.49e-6 |
| service.road_completed_veh | 370.33891943665583 | 370.33982733749264 | +0.000907901 | 2.45e-6 |

completed 증가와 active 감소가 같은 크기이므로 질량은 보존되고 **완료 시각**이 다르다(관측).
원인(작은 fixture 관측 + 도출): 두 표현의 질량·모멘트는 ~1e-16로 같지만, 연속 junction event 경계의 1 ulp
gap(반례 suite 결함 (b))이 한 표현에서만 생기고(`25.698747293149196` vs `25.6987472931492`), projection이 이를
보호 support 경계로 잘라(결함 (c)) cohort 수가 달라진다. 그 cohort가 서비스되면 midpoint 대기시간
적분(class ledger[3])이 9.06e-8 상대만큼 달라진다 — PLAN residence 허용 1e-8보다 크다. 이 반례는 Rust 시험
`ulp_event_boundary_changes_cohort_count_not_observables`에 엄격 단언으로 보존했다(결함 (b)/(c)를 고치면
뒤집혀야 함). 도시 규모에서도 packet 수가 28개 다르다. 따라서 1e-5 차이는 질량 공유 자체보다 event 시각
반올림에 대한 support 판정의 불연속이 표현 간 ulp 차이를 증폭한 것으로 판단한다(도시 규모 개별 귀속은
NOT_RUN). 이것을 exact라고 부르지 않는다.

## 5. Pilot 0→28,800 s 목표 (관측)

- **BLOCKED_RESOURCE**, 마지막 유효 **26,080 s**, `phase_working_budget_guard`, exit 2.
- `native road storage budget exceeded: phase=transfer candidates, required_bytes=4027672896, budget_bytes=4027620138`.
  같은 상태를 재적재해 재시도하면 phase `mark block service materialization`(4,194,190,000 > 4,194,118,554)으로 거절된다.
- peak RSS 2,599,641,088 B, wall 449.1 s.
- 마지막 유효 road: 24,808 packet, 논리 행 28,379,216, term 1,530,046, block 26,007, block 행 4,030,894,
  block bytes 131,111,808, road retained 196,131,888 B, 최대 cell 논리 행 3,704,195.
  service event 11,126,414행, journey 18,333,623 기록(dynamic 587 MB).
- checkpoint(로컬 전용) `local_probe/valley_markblock_h1.last_valid.bin` 1,428,197,230 B, SHA-256 `13e0f9fe…`.
- 참고(이전 rows pilot 26,050 s): 14,287,428 행 / 18,372 packet, event 7,206,642, journey 15,605,033, RSS 3.54 GB, checkpoint 1.79 GB.

**도출(측정 아님)**: 차단 시점 road base ≈ 3×196 MB + 32 B×28.4M 논리 행 + 96 B×3.70M(최대 cell)
≈ 1.85 GB; event 항(입력·현재·후보) ≈ 1 GB 이상; incoming 계상 = 병합된 served 진입 행당 160 B.
road 보유분은 작고 논리 행·event 행에 비례하는 항이 지배한다. trace를 켠 차단 시점 분해는 NOT_RUN.

**논리 행 증가**: 25,900 s ×1.32, 26,080 s 28.4M(rows 26,050 s 14.3M의 약 2배). 같은 tag가 서로 다른
출발 block(source cell×step)의 term에 나뉘어 나타나 cohort당 논리 행이 늘어난다(설계 문서 §6 "source
다양성" 위험의 실측). 저장 bytes는 줄었지만 논리 행 비례 CPU·scratch·계상은 늘었다.

## 6. 실행하지 않은 것 (NOT_RUN)

- Python oracle의 mark 표현 구현·대조(Rust rows 경로와만 대조).
- event block(서비스 event를 term 단위 보관, 소비 지점에서 지연 전개); event 행은 여전히 materialize.
- per-logical-row scratch(motion class 합, rates destination Vec, check_state class Vec, byclass)의 per-term
  전환과 계상 재유도; incoming 계상의 term 기반 재유도.
- 행이 모두 빠진 block 압축/GC(살아있는 view가 block 전체를 유지: 26,080 s에 block 행 4.03M).
- cohort term 수가 행 수를 넘을 때의 materialize(compaction) 규칙.
- 도시 규모 1e-5 완료 시각 차이의 개별 귀속, trace 켠 차단 시점 guard 분해.
- 동적 routing, 다른 도시·case, 3×3 24h campaign, native thread >1.
- Valley 규모에서 연속 실행 대비 재개 결과 동일성(작은 engine fixture에서만 확인).

## 7. 다음 단계 제안

1. event block: served term을 `(source, dest, start, end, term)`로 보관하고 sink 소비 지점에서만 tag별 전개.
2. per-logical-row scratch를 per-term(class·dest 합)으로 바꾸고 계상을 term 수 기반으로 재유도(상수 완화 아님).
3. cohort compaction: term 수×40 B가 distinct 행×32 B를 넘으면 새 block으로 materialize(이름 있는 규칙, identity 포함).
4. 위 셋은 모두 상수배다. 아침 진입 구간의 cohort×category 폭증을 멈추지 못하면 24h는 불가하므로
   성장 원인(반례 (b)/(c)의 ulp sliver 경계 포함)의 판별을 우선 권한다.
