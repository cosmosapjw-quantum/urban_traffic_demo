# release_interval_v1: 방출 시점 정책 평가 — 판정 NOT_ADOPT

2026-11-17 · branch `research/release-timing-20261117` (기준 274a4ff) · binary `40c741db…`.
사용자 결정: "방출 시점 변경은 성능이 향상될 때만 도입". 조정 세션은 이를 (a) dt=10 대 dt=5 차이를 줄이고
(b) 계산 비용(peak records, peak RSS, tick당 CPU)을 측정 잡음 이상으로 악화시키지 않는 경우로 해석했다.
지표·문턱·판정 규칙은 구현과 도시 실행 **전에** `LAUNCH.json`(commit 4669f72, 21:35)으로 고정했고,
구현(530e494)과 실행은 그 이후다. 이 보고서는 규칙을 바꾸지 않는다.

## 정책 (opt-in, identity `:release_interval_v1`)

- 부모 없는 도로·내부 leg는 step `[t, t+Δ)`에서 F(t+Δ)까지 방출한다. 격자 시각의 방출 장부가 A·F(T)로 정확하다.
- 접근 지연 atom (d, w)마다 x = fmod(d, Δ)로 두고 출생 구간 (t−x, t+Δ−x]만 행으로 만든다. 모든 개체의 준비시각이 한 step 안에 있어
  step 끝에 due가 된다. 준비 전 offer나 진입은 없고, 행 수는 legacy와 같다.
- 방출됐지만 아직 행이 없는 접근 질량 A·Σw(F(T)−F(T−x))는 시계·Δ·profile·law로 정해지므로 checkpoint 필드가 늘지 않는다.
  stage·물리 장부 검사(Rust와 Python oracle)에 포함했다.
- 도로 도착은 행의 평균 준비시각 τ(step 안으로 clamp)에 source queue로 들어간다. pre-entry + source wait 합은 legacy와 같다.
  도로의 step 끝 진입 규칙은 바꾸지 않았다. 자식 leg의 방출, 버스, 화물은 legacy 그대로다.
- 보존: 단위별 질량, 방출·행별 birth 1차 모멘트, 도착 1차 모멘트, FIFO, support 경계, 두 장부 항등식, rollback, checkpoint 형식.
- 오차 차수: 두 정책 모두 Δ의 1차다. 첫 진입 − 준비시각의 평균은 legacy 약 1.5Δ, 정책 0.5Δ다(`LAG_ORDER.json`, Δ=20…2.5).
  격자 시각의 방출 장부 결손은 legacy 약 λΔ, 정책 0이다.

## 검증

- Rust 84 passed (신규 8). Python 지정 회귀 356 passed, 5 xfailed (기준과 동일). 신규 `tests/v1/test_release_timing.py` 18 passed:
  oracle–native 일치, save/load/resume, 정책 간 checkpoint 교차 거부, budget 실패 rollback, step 안 인과 위반 거부를 포함한다.
- legacy bit identity: 25,900 s checkpoint SHA-256 `ab73c40f…` 일치. 또 legacy dt=10/5의 25,500 s 표본이 이전 binary `a0077a07`과 bit 동일했다.
- 정책 단언을 legacy에 적용하면 3건 실패한다(`red_legacy_counterexample.log`). Rust 초안을 테스트보다 먼저 쓴 점은 이 반례 기록으로 보완했다.

## 도시 대조 (Valley, h=1, bounded_bytes_v1; 네 run 모두 26,000 s 도달, 보존 전부 통과)

gap = dt10 − dt5, r = |정책 gap| / |legacy gap|.

| 지표 @25,500 s | legacy gap | 정책 gap | r |
|---|---:|---:|---:|
| A1 방출 persons | −16.693 | 0.000 | 0.000 |
| A2 journey 완료 veh | −1.766 | −1.335 | 0.756 |
| A3 road 완료 veh | −7.585 | −6.312 | 0.832 |
| A4 목적지 완료 L1 | 1.766 | 1.335 | 0.756 |

26,000 s의 r: A1 0, A2·A4 0.930, A3 0.940. 정확도 조항 (a)와 (a′)는 통과했다.

| 비용 (정책/legacy, 같은 dt) | C1 records | C2 RSS | C3 CPU/tick |
|---|---:|---:|---:|
| dt10 @25,500 | 1.028 | 1.037 | **1.113 > 1.10** |
| dt10 @26,000 | 0.839 | 0.828 | 1.030 |
| dt5 @25,500 | 1.012 | **1.079 > 1.05** | 0.905 |
| dt5 @26,000 | 0.963 | 0.976 | 0.889 |

## 판정: NOT_ADOPT

비용 조항 (b)가 25,500 s에서 두 번 실패했다. 사전 규칙에 따라 legacy 방출을 유지하고, 정책 코드는 opt-in 연구 branch에만 둔다.

판정에 쓰지 않은 사후 정보:
- 실행 중 host load average가 10–37(24 thread)이었다.
- 두 timing에서 동일한 코드 구간(journey_finish)의 시간이 짝 run끼리 10–36% 달랐다.
- 빈 상태 0–3,600 s를 ABBA 순서로 잰 정책 CPU 비율은 0.956이었다(`IDLE_OVERHEAD.json`).

따라서 비용 실패는 공유 host의 측정 잡음과, 수요가 실제 시각에 더 일찍 들어와 생기는 물리적 부하 이동이 섞였을 가능성이 크다.
통제된 부하에서 재측정할지는 사용자 결정이다.

## 과학적 결론

방출 시점 정책은 방출 장부 gap을 전부 제거하지만, 완료량 gap은 25,500 s에서 약 17–24%, 26,000 s에서 약 6–7%만 설명한다.
지배적인 dt 민감도는 도로의 step 끝 source 진입과 운동·이관 이산화에 있다. 다음 dt 정밀화 연구는 그쪽이 대상이다.

## NOT_RUN

ReleaseRuntime/ReleaseDriver 경로(CLI가 거부), mark_block_scaled_v1과의 조합, River·Coastal, 26,000 s 이후, 24 h, 반복 실행,
dt<5, h≠1, road class별 모멘트, 통제 부하에서의 비용 재측정. V03 BLOCKED, 19/21, 5/21은 바뀌지 않는다.
