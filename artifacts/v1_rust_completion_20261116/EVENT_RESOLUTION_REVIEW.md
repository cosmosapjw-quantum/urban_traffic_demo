# 양수 sub-ULP event duration의 독립 수치·코드 검토

2026-11-16. 기준 commit은 `7b5e518f6c098ed831551da4e66d980addf80dd8`이다. 이 검토는 `INDEPENDENT_REVIEW.md`에서 종결한 stage 저장/byte-policy 검토와 별개다. 원래 raw-count 제한을 넘은 실제 실행에서 드러난 `packet event resolution exhausted`의 후속 수치 처리만 대상으로 한다. 검토자가 구현 파일을 수정하거나 compiler/native pytest/전체 시뮬레이션을 실행하지 않는다.

상태: **SOURCE REVIEW CLOSED — 미해결 P0/P1 0건.** 구현 담당자의 source freeze를 확인했다. 아래 검토본은 rustfmt 이전이며 최종 format/build 소스와 실제 검사 결과의 binding은 root의 실행 영수증에서 별도로 확정한다. source review 종결은 native 테스트·실제 실패 checkpoint 재개·24h 실행의 PASS 판정이 아니다.

## 허용하는 주장의 범위

양수 duration `h`가 binary64 local cursor의 ULP보다 작아서 `cursor+h==cursor`인 것은 0의 물리적 duration이라는 뜻이 아니다. 최초로 이 상황이 발생할 때 실제 FIFO head retirement가 가능한 경우에만 두 성분 local clock으로 전환하고, 그 이후 horizon/future boundary 계산에 남은 성분을 반영하는 것은 제한된 수치 해상도 보완이다. 기존 성공 경로에서는 기존 단일 f64 연산 경로를 유지해야 한다.

이 처리는 exact mass splitting, 실수 연산의 정확한 전체 수송, 또는 모든 후속 network trajectory의 동일성을 보장하지 않는다. 작은 시간 오차도 readiness/귀가 자격 같은 불연속 분기에서 후속 상태를 바꿀 수 있다. 처리한 sub-ULP duration, 실제 clock residual의 보수 상한, rate-weighted 진단과 기존 장부·용량 tolerance를 각각 보존·보고해야 한다. 단기 재개 성공은 24h 수용과 별개다.

## 확인한 반례와 검토 피드백

| 항목 | 구체 반례 또는 조건 | 필요한 처리 |
| --- | --- | --- |
| head retirement만으로 rate 보존 불충분 | `cursor=1, h=2^-54`, rate=1인 A의 mass=h와 B의 mass=1. A는 소진되지만 B는 served=h>0, `fl(1-h)=1`이다. N개 A를 처리하면 B의 원래 mass가 그대로인 채 `N*h`가 누적될 수 있다. N=2^20이면 `5.820766091346741e-11`이다. binary64 계산으로 직접 확인했다. | discrete progress는 종료 근거다. mass split exactness의 증거로 사용하지 않는다. horizon debt와 별도로 기존 보존·수용량 검사를 유지한다. |
| high word만으로 loop 종료 불가 | `hi==dt, lo<0`이면 실제 두 성분 clock은 horizon보다 작다. | activation 뒤 `remaining=(dt-hi)-lo`로 loop 종료를 판정한다. |
| 보상 모드의 정상 마지막 step | 위 상태에서 `h=-lo`는 high word를 바꾸지 않고 low word를 0으로 만들 수 있다. head는 완전히 소진되지 않을 수 있다. | 최초 activation의 head-retirement 요구와 이후 compensated-pair progress를 구분한다. |
| horizon subtraction의 반올림 | `dt=10, hi=.125, lo=1e-20`이면 f64 remaining은 `9.875`다. 이를 처리한 clock은 `(10,1e-20)`가 될 수 있다. | 보상 덧셈의 discarded third term만 error로 세면 부족하다. 선택된 horizon/future duration의 endpoint residual도 따로 계상한다. |
| compensated pair도 정체 가능 | `hi=1, lo=2^-54, h=2^-108`에 일반 TwoSum 3회 갱신을 적용하면 pair는 그대로이고 third residual은 `2^-108`이다. 이 예는 `parallel_references`가 exact Fraction 대조로 확인했다. | pair가 실제 증가하거나 실제 head retirement가 있어야 한다. 둘 다 없으면 기존 checkpoint를 보존하며 거절한다. |
| idle future jump | 활성 flow가 없어서 명시적 future timestamp로 이동하는 경우다. | `hi=future, lo=0`으로 설정한다. 이전 debt를 timestamp 뒤에 중복 적용하지 않는다. |

큰 head/receiver에서 작은 차감이 사라지는 현상은 원래 fraction/subtraction 연산의 국소 반올림이다. 하지만 종전 구현은 첫 stagnant event에서 중단했으므로 그 반복을 허용하는 새 경로의 누적 오차를 따로 검토해야 한다. finite queue/event cap이 있으면 무한 증폭은 아니지만, 행 수가 늘어날수록 오차가 저절로 상쇄된다고 가정할 수 없다.

## Compensated clock의 검토 기준

일반 TwoSum을 사용해 `(s,e)=TwoSum(hi,h)`, `(v,f)=TwoSum(lo,e)`, `(new_hi,new_lo)=TwoSum(s,v)`로 갱신하면 새 두 성분의 실수 합은 이전 합+h−f다. 따라서 버린 third residual의 절댓값을 보수적으로 누적한다. FastTwoSum의 크기 순서 전제를 임의로 가정하지 않는다. horizon/future 차감의 반올림 residual도 포함해야 한다.

`Σsubulp_h`는 compensated clock에서 반드시 누락된 시간과 같은 양이 아니다. 이는 해당 분기에서 처리한 duration 진단이며, 실제 clock residual bound와 분리한다. 양수 bound의 누적은 단순 `+=`의 반올림 누락을 고려하여 outward 처리한다. 구현의 `rate_weighted_mass_bound`는 sub-ULP 구간의 outward `Σ(rate*h)`로서 nominal service 진단이다. 기존 fraction 근사·near-one snap·각 part 연산의 모든 반올림을 포함한 mass-error bound 또는 전체 trajectory 오차의 상한이라고 부르지 않는다.

최초 activation은 유한 양수 h, 기존 fraction 계산·snap 규칙 아래 실제 head 완전 소비에 한정한다. h=0/비유한 값, 강제로 늘린 h, `nextafter(cursor,+∞)`를 event duration처럼 쓰는 처리, 작은 mass 삭제는 허용하지 않는다. 기존 source/part/turn/FIFO 순서와 원래 fraction 연산을 유지한다. activation 뒤 timestamp·midpoint·ready·horizon 해석을 일관되게 적용하며, 남는 binary64 반올림과 그 claim 범위를 명시한다.

기존 `1e-10s` readiness tolerance는 전역 mass/trajectory 오차 정리가 아니다. 같은 값 또는 그보다 작은 명시적 local clock guard를 사용할 수 있지만, 원래 mass/storage/first-moment 검사를 대체하거나 tolerance를 늘려 통과시켜서는 안 된다. budget 또는 progress 검증 실패는 candidate를 폐기하고 이전 tick의 상태를 보존해야 한다.

## 최종 소스 확인과 실행 증거 구분

- Rust와 Python diff에서 최초 activation의 유한 양수 duration/head snap 조건, 이후 compensated-pair 진전 또는 실제 head retirement, remaining 기반 loop 종료, no-future break와 idle future jump reset을 확인했다.
- 선택한 horizon/future boundary의 subtraction residual, 일반 TwoSum의 discarded third-word residual, 최종 overshoot를 따로 누적하고 기존 `1e-10s` 범위에서 거절하는 경로를 확인했다. 원래 mass fraction·FIFO/part 순서와 장부 검사는 유지된다.
- `test_native_event_resolution.py`의 tiny head 보존, 큰 competing head와 rational-rate 대조, 실제 probe 수치의 `hi==dt/lo<0` endpoint, pair 정체, future reset, refined horizon 및 ordinary-path 비활성 검사를 읽었다. 기존 Python oracle과 새 native가 같은 결과라는 것만으로 real-arithmetic exactness를 주장하지 않고 Fraction 기준과 별도 ordinary-roundoff allowance를 사용한다.
- 새 clock budget 초과와 h=0 underflow의 두 실패 검사는 native owner의 이전 snapshot 보존을 검사한다. budget 사례는 `cursor=2^20`, tiny duration `2^-34`의 반복으로 새 guard를 실제로 겨냥한다. 이 검토자가 실행하지는 않았다.
- receiver subtraction의 작은 차감 소실 반례는 분석 문서에 남아 있다. 전역 정확성을 주장하지 않으며, 기존 receiving/storage/ledger 검사와 실제 실행 결과가 계속 필요하다.
- activation 없는 이전 성공 prefix의 actual checkpoint bytes/report 대조 및 실제 실패 checkpoint의 재개·진단 계측은 root가 실행한다. 아직 제공되지 않은 실행 결과를 이 문서에서 PASS로 선행 판정하지 않는다.

event resolution 누적 진단은 scientific checkpoint와 별개다. road proposal의 검사를 통과한 뒤 후속 journey.finish에서 coupled rollback될 수 있으므로, 해당 진단을 전부 committed physical progress라고 해석하지 않는다.

검토에서 제기한 endpoint/rounding/progress 조건이 최종 diff에 반영되었고, 추가 blocking source finding은 없다. 추가 유도·반례는 `EVENT_RESOLUTION_ANALYSIS.md`와 `.json`에 보존되어 있다. 전체 캠페인 수용이나 새 DAG 진척은 이 검토의 범위가 아니다.

## Source freeze 식별 (rustfmt 이전)

| 파일 | SHA256 |
| --- | --- |
| `crates/metroflow-rust/src/v1_road.rs` | `fa6bfc259c61b563e73402525063dfb6c0668afd7ba37784c967c69d11e42ef5` |
| `src/metroflow/packet_network.py` | `b04352ba72df7bfcf1651a2af52be59ad8d2131d349eb8c2e3bff7e081e072de` |
| `tests/v1/test_native_event_resolution.py` | `c04eae7cfc28827641027177c3ad049266631ff13222de330b7c0e70533c88d6` |
