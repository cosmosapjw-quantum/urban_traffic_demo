# M04 지연 개발 정책

CompletedAccessibility는 block별 완료 통행 표본의 차량량 가중 평균과 완료 epoch,
city identity, source version을 보존한다. 미관측 block은 unsupported이며 0초·현재 truth로
대체하지 않는다. 이 값은 조건부 완료 표본 기반의 합성 입지 지표이며 전체 주민 ETA가 아니다.

GrowthModel은 고정 slow clock(기본3600s)에서 이전 완료 snapshot만 소비한다.
stamp < now이고 이전에 소비한 stamp보다 새로워야 한다. 현재 landuse의 canonical
materialize_city(state).identity와 일치해야 하므로 오래된 city version을 몰래 재사용하지 않는다.

사이트는 M03 compile_entry로 물리 corridor를 검증한 등록 portal 및 명시적 추가 주거용량이다.
원본 landmask/contact와 entry의 유한 길이·용량을 다시 확인한다. 개발 footprint는 기존
등록 block 안의 용량 증분으로 한정하며 새 토지 polygon/도로 건설은 하지 않는다.
후보별 정책 priority는 명시적이며 유일해야 한다. ID를 물리 우선순위로 해석하지 않는다.
건설 길이 비용은 해당 corridor 한 번만 청구한다. 접근성 임계값 이하인 후보 중 명시 순서로
증분 주민을 배치하고 용량/건설 예산에 못 맞춘 인구는 PENDING_DEVELOPMENT에 보존한다.

원래 주민은 기본적으로 동일 block에 남는다. CohortMove가 명시될 때만 주어진 정수 인구를
이동하며 도착지 용량/접근성을 검사한다. 원래 주민 + 누적 요청 증분 = 현재 점유 + 대기이며
canonical 다음 city의 unplaced_residents에도 대기를 반영한다. 이동의 실제 통근·이삿짐
수송은 이 정책의 완료 주장이 아니다. 새 city는 기존 점유 traffic에 hot-swap하지 않는다.

compile_next_demand는 새 canonical CitySnapshot으로 실제 ActivityMeasure를 재컴파일하고
D01 compile_daily_demand를 호출한다. 1000→1010 주민 대조에서 실제 resident_stock과 city/demand
identity가 바뀌는 것을 검사한다. 이는 daily calendar input 생성이며 전체24h 실행은 C02다.

lagged_growth_control은 동일 차종·T04 수송을 사용하는 1000m baseline과100m synthetic bypass의
실제 완료 유출 기록을 소비한다. bypass 수요는3600s부터 발생하고3780s에 완료 snapshot을
읽는다. baseline100s대의 접근성에서는3600s 증분10명이 대기하고 bypass10s대 결과는 다음
7200s slow epoch에서만 소비되어1010명으로 변한다. 이 shortened-link 대조는 합성 우회이며
교량/토목 기하 인증이나 실제 도시 교량의 효용 보장이 아니다.

검증은 same/future tick, 재사용 epoch, stale city version 거절, 유한지원/예산/용량,
기존 주민 보존, 명시적 block간 이동, forged negative/NaN 비용과 원본 stock 거절,
canonical city 및 실제 다음 demand 증분을 포함한다. 가격균형·대규모 재배치·전체 CI·통합은 제외한다.
