# M04 실행기 연결

Runtime(growth_model=...)은 GrowthState와 완료된 공간 snapshot을 WorldState에 소유한다.
publish_growth_input은 현재 물리 시각까지 완료된 입력만 동결하고, 현재 landuse city identity와
일치하는지 확인한다. 요청 증분은 정수 주민 수이며 미소비 증분을 덮어쓸 수 없다.

다음 slow phase는 호출 이전 WorldState의 입력만 읽는다. snapshot은 해당 slow tick보다 엄격히
과거여야 하며 이미 소비한 stamp는 다시 사용할 수 없다. 누락·stale 입력이면 전체 advance가
실패하고 원래 WorldState가 checkpoint에 보존된다. 매 epoch의 새 완료 기록 공급은 명시적이다.
요청 증분은 성공한 slow 갱신 후 0으로 초기화하며 pending 인구는 GrowthState에서 계속 보존한다.

materialize_city는 다음 landuse 입력을 생성하며 점유 중 교통 graph/city를 바꾸지 않는다.
기존 city_snapshot_json·trip_schedule은 실행 중 교통의 고정 원본으로 유지한다. 새 city와 새
수요의 실제 도시 재실행 결합은 C02 범위다. 기존 완료 차량 수 snapshot은 공간 접근성이 아니다.

checkpoint whitelist는 accessibility/development의 명시한 dataclass를 포함한다. 비어 있지 않은
GrowthState·snapshot·요청을 JSON 저장/복원해 연속 실행과 대조한다. WorldState schema 필드와
model identity가 달라진 이전 checkpoint를 묵시적으로 이식하지 않는다.

CLI: python -m metroflow.v1 run --scenario lagged_growth_control
이 제어 시나리오는 별도 synthetic baseline/bypass T04 완료 표본을 느린 개발 입력으로 소비한다.
전체 실제 교량 지도 변경·도시 균형·24h 성능 또는 전체 CI/통합 완료를 주장하지 않는다.
