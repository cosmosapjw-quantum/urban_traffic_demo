# 달력 수요의 물리 지원 범위 분해 (세 도시)

2026-11-17 · 도구 [`tools/census_v1_demand_support.py`](../../../tools/census_v1_demand_support.py) ·
엔진 생성자가 실제로 쓰는 support 분기와 **같은 분기**에서 leg마다 원인 코드를 기록했다
(`NativeWholeEngine.support_census()`, 물리 보고서·checkpoint identity에 포함되지 않는 읽기 전용 진단).
binary `68d867ca…`(632bbc7 + census 계측만, EventStore 이전), 1 worker, 8 GiB RLIMIT_AS, peak RSS 2.17 GB.
엔진 집계(`legs`, `unsupported_legs`)와 census 합이 세 도시 모두 일치함을 스크립트가 assert했다.
원자료: `valley_weekday_s7.json`, `coastal_weekend_s41.json`, `river_weekday_s17.json`, `SUMMARY.json`.

## 결과 (레코드와 가중량을 분리)

| 원인 (생성자 분기) | Valley 레코드 | Valley persons | Valley vehicles | 세 도시 persons 비율 |
|---|---:|---:|---:|---:|
| 도로 car 경로 해결 (`kind=1`) | 304,368 | 71,369.9 | 57,095.9 | 59.5–59.8% |
| **bus: 두 block 사이 corridor 없음** | 306,054 | **29,998.3** | 1,199.9 | **25.0%** |
| **noncar interzonal: 수송 모델 없음** | 304,764 | **17,884.6** | 0 | **14.9–15.0%** |
| 내부 지연 (intrazonal car/noncar, 동일 접근점 car) | 3,012 | 745.5 | 504.1 | 0.3–0.6% |
| 서비스 배정 (freight 232, bus 18) | 250 | 1.7 | 1.07 | <0.01% |
| freight 경로 없음·depot 동일 block | 2 | 0 | 0 | 0 (cargo 1.2 kg) |

Valley 합계: 918,450 legs, persons 120,000, vehicles 58,801, cargo 1,000 kg.
지원되지 않는 610,820 레코드(66.51%)는 **persons의 39.9%, vehicles의 2.04%, cargo의 0.12%**다.
Coastal(2,449,750 legs)과 River(5,093,765 legs)도 비율이 거의 같다.
**car leg 가운데 도로 접근점 부재·경로 단절로 실패한 것은 세 도시 모두 0건**이다.
vehicles 열의 bus 값은 버스 승객의 occupancy-equivalent이며 실제 버스 대수가 아니다.

## 원인 분류: 물리 모델 한계 vs 구현·입력 한계

1. **noncar interzonal (persons 약 15%) — 선언된 모델 범위의 경계.** PLAN의 vehicle classes는
   car, scheduled_bus, freight뿐이고 `C_DEMAND`는 "intrazonal/noncar/unreachable을 0초 완료로 세지 않는다"고 정한다.
   보행·자전거 interzonal 수송 법칙이 없으므로 이 수요는 발생 후 pending으로 남는다. 버그가 아니라 범위의 공백이다.
2. **bus 미배정 (persons 25%) — 서비스 공급 모델과 접근 모델의 결합 한계.**
   - 인벤토리는 OD와 무관한 합성 4-stop 순환 노선, 6회 출발이다(`release_matrix.json` `inventory_policy`).
   - 생성자는 출발·도착 block이 **둘 다** stop block인 경우에만 corridor를 찾는다.
     stop까지 걷는 access/egress 법칙이 없어서 일반 OD의 bus 수요는 원리적으로 배정될 수 없다.
   - 버스 class, 고정 fleet, 정류 시간 같은 물리 요소는 구현돼 있다. 빠진 것은 수요와 노선을 잇는 접근 단계와 노선 공급 범위다.
3. **bus intrazonal (Valley 1,308 레코드, 192 persons) — 구현 불일치.** 같은 intrazonal car·noncar는
   내부 지연 법칙(`kind=2`)으로 가는데, bus intrazonal은 corridor 분기로 가서 항상 실패한다.
4. **freight 2건 — 입력 기하.** depot과 같은 block이거나 depot에서 경로가 없다. 질량은 무시할 만하다.

## 보정 제안 (원인 분류 후, 미구현)

수요를 자동차로 바꾸거나 지우지 않는다. 모두 PLAN 개정이 필요한 별도 노드다.

- **P1. 미지원 수요의 장부 분리.** 현재 미지원 pending과 혼잡으로 인한 미완료가 같은 pending에 섞인다.
  `unsupported_by_scope` 같은 별도 장부 열을 두면 24h 결과 해석이 명확해진다. 물리는 바뀌지 않으며 가장 작은 변경이다.
- **P2. 유한응답 보행 접근 법칙.** 이미 쓰는 내부 지연 법칙과 같은 형식(거리·속도 분포)으로 stop access/egress를 정의한다.
  P3와 P4의 전제다. 보행자–차량 상호작용과 보도 용량은 범위 밖임을 명시한다.
- **P3. bus 배정을 "access → 노선 → egress"로 확장.** 노선 공급(stop 수, 경로)을 OD 수요에 맞추는 정책은
  B01 운영 노드의 입력 정책 변경이며, 도로 위 버스 대수와 runtime 비용이 늘어난다.
- **P4. noncar interzonal 수송.** P2의 보행 법칙을 interzonal 거리로 확장하는 새 물리 노드다.
  현재 범위 결정을 바꾸므로 사용자 승인이 필요하다.
- **P5. bus intrazonal을 noncar intrazonal과 같은 내부 지연으로 처리할지 결정.** 영향은 0.16% persons다.

**주의:** 위 제안은 V03의 메모리 차단(도로 interval packet 증가)과 독립이다. 지원 범위를 넓히면
도로 부하와 행 수가 늘어날 수 있다(P3의 버스).
