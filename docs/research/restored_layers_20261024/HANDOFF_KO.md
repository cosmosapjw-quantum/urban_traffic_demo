# 재개 인계: 실제 교통 clock와 도착 calendar가 다음 단위

저장소 cosmosapjw-quantum/urban_traffic_demo, 브랜치 research/restored-morphology-layered-traffic-20261024. 지도 복구 기준0da0d1a4b6c970f4cba7b1b8a4288ec1ddc04be2, 교통 구현00fda27101cb3be6e8b56fbc84d36736b03850bc. 이후 최종 감사 커밋은 실제 branch HEAD와 납품 PUBLICATION.json을 읽어 확인한다. 과거 대화의 최종 SHA를 현재 HEAD로 가정하지 않는다.

먼저 AGENTS.md, docs/research/restored_layers_20261024/RESUME_REPORT_KO.md, artifacts/restored_layers_20261024/RESUME_RESULTS.json을 읽어라. 원래 active-matter gain-loss moment + shared committed suffix + collision-informed incoming-link Dijkstra를 보존한다. Pure Python scientific core; GPU/JAX/개별 차량 위치 추적/production default 변경 없음. 그동안의 역사·정책을 다시 전수 감사하지 말고 바뀐 파일과 이번 계산 의존성만 읽어라.

현재 4형태×3seed 지도,100k stock,네300초 교통,matched grid600초 교량폐쇄,dt5/2.5/1.25 probe가 저장돼 있다. 번들68시험과 원격 환경·복원56시험은 다른 범위다. full repoCI와 독립subagent검토는 NOT_RUN이다. 과거 map3회 수정의 중간로그는 소실됐고 이번 최종 재실행 증거만 권위로 삼는다.

다음 계산 질문: exact10초 단일 링크가 dt1초에서12초로 계산되는 tick offset을 어떻게 제거하면서 유한 저장량·신호·폐쇄·질량 보존과 연속 출발량 적분을 유지할 것인가? src/metroflow/active_suffix/engine.py의 due_tick, source admission, maturity, discharge, vehicle_seconds 순서를 먼저 유도하라. dt 세분에서 arrival3432→6262→11801, suffix1041→1029→1029라는 서로 다른 scaling을 분리하라. source/arrival/discharge 시각과 cohort residual-time 표현을 비교하되 per-car loop로 회귀하거나 질량을 버리지 마라.

단일 링크·다중 링크·녹색 경계·폐쇄 재개에 대해 원래 반례 RED를 보존하고 수정 후 동일 시험을 실행하라. 기존 source-choice·path commitment·물리 ledger 및 Braess oracle은 의존성이 바뀐 범위에서 재사용/회귀하라. 도시 비교는 지도/OD/출발 profile을 동일하게 고정한다. 형태마다 다른 OD의 완료량을 성능 순위로 비교하지 않는다. 시각 감사는 실제 실행 입력JSON을 렌더링한다.

각 행동 군이 닫힐 때 연구 브랜치에 expected_sha를 사용해 fast-forward 게시하고 원격 readback을 확인하라. main merge는 하지 않는다. 체크포인트에는 실제 코드·입력·결과·실패·최소 재개점을 포함한다. clock/calendar 다음은 미해상 구역 내 이동과 access/egress의 집계 connector다. 10만 주민 전일 성능이나 실도시/게임 우월성을 먼저 선언하지 않는다.
