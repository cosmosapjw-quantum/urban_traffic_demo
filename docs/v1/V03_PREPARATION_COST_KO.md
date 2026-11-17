# V03 정확한 사전 준비 비용 개선

기존 `ReleaseDriver`는 `ReleasePlan.take`로 각 페이지의 route/access를 계산한 뒤 leg만 남겼다. 이후 `JointReleaseRuntime`이 같은 물리 경로와 접근법칙을 다시 계산했다. 또한 페이지마다 calendar prefix를 재순회해 cursor를 검증했다. 이미 완전한 calendar를 한 번에 활성화하는 driver에는 이 중복 단계가 필요하지 않다.

새 driver는 기존 budget 검사 직후 `schedule.iter_legs()`를 한 번만 순회한다. 페이지는 leg 수집과 기존 page-wise `math.fsum` 누적에만 사용한다. 원래 전체 cursor와 runtime identity를 유지하고, 최종 `plan.summary`가 완전한 cursor의 전체량을 검증한다. 선언된 leg 수보다 iterator가 짧거나 긴 경우 구현 오류로 거절한다. 물리 route/access 구성은 최종 공동 runtime에서 한 번 수행한다. OD 식, 출발시각, class, 목적, shared supply, 실행 중 도로 상태는 바꾸지 않았다.

두 Python에서 관련 검사 각각 4개와 ruff가 통과했다. 새 회귀는 driver에서 `plan.resolve` 호출을 금지한 상태로 단일 calendar 순회를 확인하고, 이전 page 준비로 만든 cursor/runtime identity 및 실제 작은 24h fixture 최종 상태와 정확히 같은지 비교한다.

실제 두 구역·두 leg fixture의 준비 구간을 12회 교대 순서로 측정했다. plan 생성은 측정 밖에 두고, service/runtime 생성과 identity 계산은 양쪽에 포함했다. 기존 평균 0.0346350s, 새 평균 0.0199200s였다. 모든 24개 실행의 최종 cursor와 runtime identity는 일치했다. 원시 표본·분산·환경·소스 SHA256은 `artifacts/v1_v03_prepare_cost_20261027/RESULT.json`에 있다. 이는 해당 작은 준비 작업의 측정이며 release 도시의 실행 시간이나 메모리 통과를 뜻하지 않는다.

20,000 leg materialization budget은 그대로다. 실제 release calendar 약 92만~509만 leg에 대한 자원 차단과 로컬 전체 24h 계측 의무는 유지한다. 이번 변경은 중복 준비와 반복 prefix 순회를 제거하며, 큰 calendar의 eager 물질화 자체는 해결하지 않는다. 전체 완료율은 19/21(90.5%)다.
