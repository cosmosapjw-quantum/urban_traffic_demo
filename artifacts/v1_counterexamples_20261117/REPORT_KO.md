# V03 물리 반례 검사와 기존 5개 실패 진단 (2026-11-17)

범위: 한정 검증 단위. 기준 `82cfc7a`, 브랜치 `research/counterex-20261117`.
binary `native_binding/_metroflow_rust.so` sha256 `a0077a0707c398615508e2687f3bf6cb032904be31fa8c779068a6af7d05498b`
(같은 82cfc7a 소스, Rust 변경 없음으로 재빌드하지 않음). V03 BLOCKED, 19/21, 최종 수용 5/21 상태는 바꾸지 않는다.

허용오차는 PLAN `numerical_policy`만 사용한다: 질량 상대 1e-9, 체류량 상대 1e-8, 각각 `max(1, 누적량)` 배.
bit 동일성은 코드가 정확성을 주장하는 곳(h=0 구간 끝점, checkpoint 왕복·재개)에서만 요구한다.
native와 Python oracle은 packet/record 구조가 아니라 물리 관측(셀 스칼라·잠재 상태, tag별 질량·birth·entry 1차 모멘트,
대기열, 전역·class 장부, 사건의 tag·출발·도착별 합계)으로 비교한다. 같은 실수 측도가 다른 record 수로
쪼개질 수 있기 때문이다(아래 결함 2).

## 결과 요약

- 새 검사 `tests/v1/test_v03_counterexamples.py`: **39 passed, 5 xfailed(strict)**, 약 5초.
- 회귀 묶음(projection·packet quotient·native 전체·plan·local CLI + 새 파일): **315 passed, 5 xfailed**, 실패 0.
- 기존 5개 실패: 실제 구현 결함 1개(identity binding)로 귀속, 최소 수정 `bccbc5a` 후 모두 통과.
- Rust 단위 검사: Rust 미변경으로 **NOT_RUN**.

## 사례별 결과 (h ∈ {0, 0.25, 1}; Python oracle `py`와 native `rs`)

| # | 검사 내용 | 결과 | 허용오차 |
|---|---|---|---|
| 1 | 닫힌 회전(c, 0–40 s 폐쇄)을 가는 1e-12 veh가 앞선 개방 흐름 뒤, 늦은 흐름 앞에 있음. 매 tick tiny tag 자체 장부가 자기 질량 기준으로 닫힘(누락 없음), tiny 출차 ≥ 40 s, 늦은 흐름은 tiny 이후에만 출차(추월 없음), 앞선 흐름은 tiny에 오염되지 않고 40 s 전 통과 | PASS (3 폭 × 2 backend) | tiny 장부: 1e-9 × tiny 자체(분석적 소량 검산), 나머지 PLAN |
| 2 | 분기(s→x / s→y) 후 합류(m→t), 같은 경로 다른 label, 같은 suffix를 다른 offset에서 시작하는 route. 모든 transfer가 자기 route의 연속 쌍, 모든 part의 remaining이 자기 route suffix, native raw offset이 해당 셀을 가리킴, tag별 완료 = 출발 | h=0, h=1 PASS; **h=0.25 XFAIL(결함 3)** | PLAN 질량 |
| 3 | 0.1 s × 350 sub-step 동안 head packet 부분 서비스 반복(>50개 서로 다른 서비스 구간). 상류 잔량+출차 = 제공 질량·birth 1차 모멘트, 잔여 part의 birth/질량 비 불변, 하류(2 km, 미출차)의 질량·birth·entry 1차 모멘트 = transfer 사건 합 | PASS (h=0 정확 분할, h>0 투영 모두) | PLAN 질량 |
| 4 | car·bus·freight 한 packet. 길이+정지간격 footprint 재계산 = `occupied_space`, 30 m 공간 제한이 실제로 결속, 공간 ≤ 용량, class 장부 닫힘, 같은 packet 서비스의 class 비율이 제공 비율과 동일(교환가능 혼합) | PASS | PLAN 질량 |
| 5 | 불규칙 구간(0.11–0.37, 0.2–0.93, 점 0.37, 0.5501–1.7, 1.25–1.31). h=0: 모든 출력 구간이 인접 입력 끝점 사이의 기본 조각, FIFO 비중첩, 범주별 3개 모멘트 보존. h∈{.25,.3,1}: 모멘트 보존, 어떤 cohort도 movement-support 경계를 넘지 않음, 원래 점 atom bit 보존, W1 ≤ h/2·질량. 네트워크 수준: 불규칙 dt(0.07–2.03 s)와 우선순위 다른 두 상류 합류에서 native=oracle, 셀 FIFO, h=0에서 보존 끝점이 transfer 사건 시각과 bit 동일 | PASS | PLAN 질량; 끝점 bit |
| 6 | 0 s 파동, 360 s 빈 구간 한 번의 advance, 400 s에 같은 파동. 빈 상태에 packet·pending 없음, 빈 구간 사건 0, projection 입력 0, 두 번째 파동 사건 = 첫 파동의 400 s 평행이동(시간원점 gauge) | PASS | PLAN 질량(시각은 max(1,t) 배) |
| 7 | subnormal(1 ulp) 질량. (a) 단독 1-ulp 차량: 두 backend 모두 명시 거절(oracle: T02 gap 법칙 ValueError, native: junction ArithmeticError h=0) — 조용한 삭제 아님. (b) 2 veh와 같은 packet에서 비례 부분 서비스: **XFAIL(결함 1)**. (c) h=0.25는 'projection underflow' ArithmeticError와 직전 상태 보존, h=1은 정확히 운반 | (a)(c) PASS, (b) XFAIL | 정확(==) |
| 8 | checkpoint: native raw tuple 왕복과 Python dataclass 경계 왕복이 bit 동일, 세 owner의 이후 31 tick 상태·사건 bit 동일, 재개 상태에서 oracle 1 tick과 PLAN 일치. NativeWholeEngine(h=0, 0.25) save/load 보고서 동일, 재저장 byte 동일, 120 s 재개 보고서·sample·저장 byte 동일, 이전 snapshot 불변. persons/vehicles/cargo_kg 각각 requested = released + pending, released = completed + active | PASS | bit; 단위 장부 PLAN 질량 |
| 9 | byte 예산: 너무 작은 예산은 설정 자체가 원자적으로 거절; 수용 가능한 최소 예산에서 다음 tick이 'storage budget'으로 실패하면 raw snapshot·projection 진단·예외 checkpoint가 직전 상태와 동일, 예산 복구 후 재시도 궤적이 무중단 실행과 bit 동일. oracle record 예산 실패 시 `checkpoint` = 마지막 확정 상태. whole engine record 예산 1: advance 실패 후 초기 보고서·저장 byte 불변, 재로드 동일 | PASS | bit |

참고(결함 아님): small fixture 보고서의 cargo_kg `active`가 −2.8e-14(완료가 출발보다 3e-14 큼)이다. PLAN 허용
1e-9 × 100 이내의 반올림 표현이며 사례 8의 단위 장부 검사를 통과한다.

## 발견한 결함 (strict xfail로 보존, 수정하지 않음)

1. **subnormal part의 조용한 소멸 (oracle과 native, h=0).** `packet_network._portion`과 `v1_road.rs::portion()`은
   `mass*f > 0`인 part만 남긴다. 1-ulp part가 2 veh와 같은 packet에 있고 f=0.5이면 서비스분과 잔여분이 모두 0으로
   반올림되어 오류 없이 사라진다. 1e-9 절대 장부 하한은 이를 보지 못한다. 같은 underflow에 대해 entry projection은
   ArithmeticError를 낸다. 실무 크기와는 무관하지만 "질량 삭제 금지" 계약과 불일치한다. 수정(명시 오류 또는 원자 보존)은
   oracle·native 수치 정책 변경이므로 이 단위에서 하지 않았다.
2. **연속 junction 사건 경계의 ulp 불일치 (oracle과 native, 표현).** 사건 끝은 `(t+cursor)+h`, 다음 시작은
   `t+(cursor+h)`로 계산되어 1–2 ulp 겹침 또는 틈이 생긴다(실수 산술로는 연속). 한 목적지로 가는 구간이 겹치면 정확
   구간 법칙(h=0)이 모든 범주를 담은 ulp 폭 sliver packet을 추가로 만든다(사례 2 시나리오 80 tick 동안 각 tick 저장 상태의 ulp 폭 part를 누적해 센 수: oracle 6, native 8).
   질량 오차는 ~1e-15이지만 record 수가 늘고 ulp 규모 FIFO 겹침이 생기며, 두 backend가 서로 다르게 반올림해 record 수가 갈린다.
   V03 road row 증가와의 정량 관계는 측정하지 않았다(NOT_RUN).
3. **projection support 경계의 불연속 (결함 2의 결과, h>0).** t=5 s에 oracle은 y→m 구간을 1-ulp 틈으로, native는 연속으로
   낸다. `entry_projection_support_v1`은 1-ulp 빈 support를 보호 경계로 취급해 두 backend가 다른 cohort를 자른다. 이 차이가
   출차 시각을 바꿔 m의 bus 잠재 상태가 t=9 s에 상대 1.1e-3 차이 난다(PLAN 1e-9 초과). 투영 결과가 ulp 수준 사건 시각에
   불연속적으로 의존하므로, h>0의 native=oracle 동치는 이 시나리오에서 성립하지 않는다.

권고(사용자·물리 계약 결정 대상): 사건 경계를 하나의 반올림 값으로 공유(예: 끝 = t + 다음 cursor)하면 결함 2·3이 함께
해소될 가능성이 높으나 legacy replay bit와 checkpoint byte가 바뀐다. 결함 1은 0 반올림 시 ArithmeticError가 가장 작은 변경이다.

## 기존 5개 실패 진단

| 검사 | 원인 | 분류 | 조치 |
|---|---|---|---|
| test_native_driver::test_native_driver_executes_and_resumes_same_complete_calendar | `NativeRoadNetwork.snapshot()`의 "native snapshot model binding differs" | 실제 구현 결함 | `bccbc5a` 수정 |
| test_native_driver::test_campaign_uses_native_hourly_chunks_with_internal_tick_measurements | 같은 원인으로 첫 initial에서 BLOCKED, simulated_s 0 | 같은 결함 | 같은 수정 |
| test_native_journey::test_native_journey_over_budget_preserves_valid_checkpoint[rust] | 같은 binding 오류 | 같은 결함 | 같은 수정 |
| test_native_journey::test_coupled_native_loop_never_calls_python_tick_methods | 같은 binding 오류 | 같은 결함 | 같은 수정 |
| test_native_journey::test_coupled_native_metrics_count_and_peak_match_observed_complete_ticks | 같은 binding 오류 | 같은 결함 | 같은 수정 |

근본 원인: `f47bf6a`(entry projection 도입)가 `V1Road`에 `reference.identity` 대신
`reference._unprojected_identity`를 넘기도록 바꿨다. 이 속성은 `PacketNetwork` 생성자 안에서 기록되는데,
`lanegroups.packet_model`(`bea8453`, T03)은 생성 뒤 `model.identity`를 city·turn·conflict를 포함한 hash로 다시 묶는다.
그래서 lane-group 도로(서비스·journey·driver 경로)의 native snapshot은 내부 hash를, Python 기준은 외부 hash를 갖게 되어
매 snapshot이 거절됐다. `test_native_road`는 재바인딩 없는 PacketNetwork를 써서 통과했고, f47bf6a 영수증의 native 선택 묶음에는
driver/journey 파일이 없어 회귀가 잡히지 않았다. 검사 파일은 f47bf6a 이후 변경되지 않았다(마지막 `83197dc`). 게시 binary에서도
같은 실패가 나는 것은 원인이 binary가 아니라 Python bridge이기 때문이며 환경 문제가 아니다.

수정(`bccbc5a`, 물리·수치 무변경): native 기준 binding을 공개 identity에서 projection suffix만 제거해 얻는다(h=0에서는 f47bf6a
이전 값과 동일). projection suffix가 없는 투영 reference는 명시적으로 거절한다. 회귀 검사
`test_native_road.py::test_native_binding_follows_rebound_public_identity`는 수정 없이 RED, 수정 후 GREEN임을 확인했다.
검사 기대값은 바꾸지 않았다(오래된 기대가 아니라 실제 결함).
