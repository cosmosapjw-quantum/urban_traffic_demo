# 실제 atlas 블록의 개발·접근·집계 수송 연결

2026-10-25. Base 1fff1b5666aaef20313686d8916e1e22dd223916. main/default/기존 교통 코어를 변경하지 않는 연구 branch. 입력번들 SHA256 facbff8291f0bbe3dda1a2292e1ea3052c470d6b31dfc3a1cf293ac251cf3802.

지도 선택: 전체 도시경제 재작성 또는 새 후보망 대신, 기존 polygon block에 내부활동점-실제 경계도로 node의 유한길이 접근연결을 만들고, 남은 주거용량/대기인구/고정 일자리 접근성으로 느린 점유를 갱신한다. Atlas.landscape polygon이 mask SSOT다. private access와 지상 face graph를 분리하고, 원래 block과 도로는 immutable로 유지한다. 기존 주민은 보존하고 신규 성장과 새 접근건설의 장부를 따로 둔다. 오래된 rectangle-only zoning으로 재배치하지 않는다. 실제 stock 변화만 OD 입력이 되며 access/egress 길이를 0으로 숨기지 않는다.

교통 선택: 기존 PackedModel의 고정진입지연을 고치는 전면교체 대신, ordered_lane의 공통거리clock과 순서있는 질량을 비주기적 다중링크/노드에 연결하는 별도 reference를 구현한다. 명시된 공유 lane-group 내부 FIFO, 합류 공급분배, downstream 시작시각 저장량 예약, 다음 경계에서의 이관을 사용한다. 이관 대기시간을 숨기지 않고 residence ledger에 넣는다. source batch는 vehicle-equivalent이며 개별차량객체/차량수비례 loop를 만들지 않는다. lane-group 분리가 없는 다차로를 전부 fullFIFO로 승격하지 않는다. boundary splitting의 dt오차, finite storage와 공간shock 차이, 기존 activity closure의 가정을 보고한다.

단계: M1 접근기하·mask·용량/성장 보존의 반례와 구현 → 지도 snapshot 실제 재사용/시각검사/게시 → T1 common-clock network의 질량·공급·FIFO·merge·dt 분석 및 구현 → 실제 도시에서 신규주민의 작은 경로집합을 연결/실행 → 영향회귀/보고/게시. 매 닫힌 단계 expected_sha fast-forward. 실측보정·게임비교·전일100k·독립subagent는 NOT_RUN. Native delegation 도구가 없어 직렬 직접유도/CAS/반례검증을 사용한다. 단순코딩수정과 scientific conclusion을 구분한다.

수용조건: 기존 주민 및 unplaced 보존, 새 연결의 polygon 내부성/수계/보호/경사, 입력identity 변경 감지, source-trip/vehicle 단위 장부, per-link 저장량/유입률/유출률, shared-lane 무추월, 막힌 선두의 차로군내 blocking와 독립차로 nonblocking, 제한예산 실패 checkpoint, 동일입력 replay, transient-safe first passage의 수용범위. 연결법은 조건부 연구구성이지 완전한 kinetic closure/전체 network FIFO theorem이 아니다.
