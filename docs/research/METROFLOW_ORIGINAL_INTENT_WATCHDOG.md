# MetroFlow 원 동기와 매 턴 drift watchdog

권위: 2026-11-23 사용자는 원 repo 역사를 거슬러 원 동기·직관을 보존하는지 매 턴 점검하라고 요청했다. 현 실행 권위 `docs/v1/PLAN.json`은 그대로다. 본 문서는 확인한 역사와 현재 판단을 연결하며, 과거 문서의 미완료 상태·다음 작업·구버전 scope를 재활성화하지 않는다.

## 확인 가능한 원 역사

| source | 확인한 동기·구성 | 현재에 적용할 의미 |
|---|---|---|
| `049236458fdb5a7e327b0e494ab5f5cc3ad25b61:docs/PRD.md` | 약100k 주민의 설명 가능한 synthetic 도시, 지도–교통–접근성–개발 연결 | 실제 도시 동역학·하루 실행이 목적; 자료구조/기록 수는 수단 |
| 같은 commit의 `docs/RESEARCH_SYNTHESIS.md`, `docs/TRAFFIC_DYNAMICS_DESIGN.md` | mesoscopic bulk flow; destination/path/behavior commodity; point-queue/LTM 출발; supply/storage/nonnegative mass; fast/medium/slow cadence | 개별 차량 전수추적·특정 packet 표현이 원래 목적은 아님. 법칙·경로·행동·인과성은 보존 |
| `65245008af2387a8ce56e72d54a198394de3eee2` constitution | 단위·보존·immutable state·결정론·지연 feedback·equivalent outcomes | 물리 동등성과 바이트 동일성을 구분; 현 실험의 명시적 byte 계약은 별도로 준수 |
| `3d83db01e9d028578de857ab66d98bf7964a5e3c:docs/research/ACTIVE_MESO_DESIGN_20261024.md` | 목적지 지향 self propulsion, mass-preserving gain/loss, mesoscopic 절감, collision-derived legal-link Dijkstra cost | 정지/재출발·혼잡·경로 선택을 연결. potential은 양의 시간 cost-to-go, 역학적 에너지가 아님 |
| `bf2325d:docs/research/symmetry_observables_20261025/TRAFFIC_KO.md` | ID 재명명이 합류 우선순위를 바꾸는 반례를 교정한 PacketNetwork. 같은 입장 boundary는 exchangeable, 서로 다른 과거 packet은 FIFO | label이 운동을 지배하지 않게 하며 물리 순서·관측량 보존 |
| T02 `7d5e388`, T04 `91bc4f0`, 현 PLAN | 실제 연속 속도와 latent 제어확률을 구분하는 finite-response, interval transport, original birth moment, causal finite information | V03에서 실제로 수용할 현재 모델. 초기 더 느슨한 집계를 무단 대체하지 않음 |

첫 확인 가능 commit 이름은 `import repaired bundle`이다. 그 이전 구상의 전체 역사나 donor의 전 ancestry를 복원했다는 주장은 하지 않는다. 2026-07-11 origin audit는 탐색 지도와 당시의 contract-accumulation 경고로 재사용하되, 당시 GPU/NN 연구 scope와 runtime 미완료 상태를 현재 사실로 가져오지 않는다.

## 과학적 정체성과 현 계약의 두 축

초기 active-meso는 real vehicle-equivalent를 사용하며 개인 이력·차선별 FIFO·속도분포 세부형상 소실을 명시했다. 정확한 packet 순서와 비교용 바이트 조건은 이후 선택된 계약이다. 원 동기를 보존한다는 이유로 현재 승인된 FIFO/finite-response/원수요를 바꾸지 않으며, 바이트를 지켰다는 이유만으로 원 동기의 관측·routing 문제를 해결했다고 하지 않는다.

현재 원래 과학 목표에 직접 연결되는 공백은 `docs/v1/r01/INFORMATION_KO.md`와 `docs/v1/r02/ROUTING_KO.md`에 명시돼 있다. final external exits에서 완료 route 평균은 계산할 수 있지만 birth moment는 여정 출생이어서 중간 유출에서 빼면 링크 시간이 아니다. 링크 비용은 별도 boundary 측정이 필요하다. 서로 다른 조건부 모집단의 링크 평균 합은 행동 closure이며 actual ETA나 전체분포가 아니다. 따라서 이번 루프는 causal boundary measurement에서 FIFO 경로 arrival-time 구간과 decision potential을 구성하는 정리를 개발한다.

## 매 턴·단계의 적용

기존 연구 기록/응답에 다음을 짧게 포함한다. 별도 감사 파일을 매번 만들거나 동일 역사 전체를 반복 조사하지 않는다.

1. 원 목표 연결: 이번 산출물이 설명 가능한 mesoscopic 물리, 유한정보 경로, 지연 feedback, 원본 하루 실행 중 무엇을 진전시키는가?
2. 보존한 현 계약: 수요·규모·장부·선택된 운동/순서·dt·정보 인과성·예산 중 실제 변화는 무엇인가?
3. 관측 의미: 모집단, 측도, 시계, 완료 정의, 단위를 이전 증거와 맞춘다.
4. 진전 근거: 새 정리, 실제 코드 동작, 실제 유효 물리시간, 판별된 실패를 제시한다. test 수·문서 수·hash 수를 대용으로 쓰지 않는다.
5. 판정: `ALIGNED`, `ALIGNED_WITH_OPEN_OBLIGATION`, `DRIFT_REQUIRES_REVISION`; 실제 이탈과 최소 수정 하나를 적는다.

## 이번 턴의 판정과 surgical revision

`ALIGNED_WITH_OPEN_OBLIGATION`. 실제 validator의 O(parts) 임시배열 제거는 원래 mesoscopic 계산 절감에 기여한다. 검사를 삭제하거나 예산 multiplier만 줄이는 경로는 채택하지 않았다. 반복된 next-guard 수정만으로 원래 목표를 대신하지 않도록 새 routing 관측 정리와 원 수용 cadence 실행을 함께 요구한다.

원 acceptance runner는 hourly boundary까지 native를 호출하며 내부 dt=10s다. 연구 runner의 tick당 반환은 owner 수명이 다르므로 one-tick 실패만으로 원 cadence 전체를 판정하지 않는다. 이번에는 현재 source의 time-zero 원 cadence baseline을 실제 실행한다. 그 결과는 checkpoint continuation과 별도 집계한다.

2026-11-17의 '정확 병합/조성 공유로24h불가' 문구는 당시 제한된 후보와 관찰 구간의 engineering 판단이다. 새 정확 표현·owner 수명·streaming validator를 금지하는 수학적 no-go가 아니다. 물리 scope·예산·수요는 변경하지 않고 이 잘못된 일반화만 교정한다.
