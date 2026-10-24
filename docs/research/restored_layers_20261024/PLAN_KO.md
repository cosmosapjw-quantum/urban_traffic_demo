# 도로 형태·구조물 복원과 집계 교통의 다음 연구 단위

2026-10-24. Base c24dd68c19e9c9666d162938b1e8fb7f3d714835. 기존 defaults와 구현을 덮어쓰지 않는 연구 브랜치.

복원 근거: old protected 008-routing-runtime-integration@77060c84b75195c8a05273e0d1a809caf93e63d4의 IMPLEMENTATION_ROADMAP/ARCHITECTURE_OVERVIEW; docs/harness/CITY_MAP_PR_LIST.md@81f3f09be648cf0669c102c1f4eb33765114f489의 PR33-64 및 PR65-82 장기 DAG; morphology_capabilities.py@c9168100367d027f94dd33b848955af2cba3e060; directed-ramp PR#22 및 scalable_topology.py@c3d7d1b424f49791b0c25b98e8c05b40d0a48bc7. 원래 bulk transport/behavior closure 분리, 느린 feedback, profile-derived aggregate lanes/capacity, bridge failure groups, forward-only ON/OFF ramps를 복원한다. 과거 PR62 morphology 0/30 및 PR63 performance/population 실패를 성공으로 재분류하지 않는다. 정확한 제목의 별도 초장기 문서는 검색에서 특정하지 못했으므로 검색 완료/전수복원을 주장하지 않는다.

대안: 오래된 NumPy runtime 전체를 되돌리기, 새 도시 생성기를 전면 교체하기, 기존 지형·stock·active_suffix 위에 제한된 원래 문법/구조 계약을 이식하기. 마지막을 선택한다. 이번 code는 stdlib로 포팅하는 새 kernel이며 옛 generator의 byte replay가 아니다. grid_core, organic(정확히 warped grid), superblock_mixed, ring_radial을 구현하고 polycentric_tod의 정식 centre competition 및 전체 180-leaf grammar는 보류한다. 물/보호/경사 조건을 통과한 polyline roads만 사용한다. 교량은 명시한 deck/profile, 고가 mainline과 지상은 투영 교차만으로 연결하지 않는다. 단방향 ramps에서만 층을 연결한다. 오래된 3bridge 조건을 모든 작은 fixture에 보편화하지 않으며 규모/고장연결성을 따로 보고한다.

단계별 저장: S0 이 계획과 복원근거, S1 지형·형태·구조물 source/tests 및 최초 지도, S2 최대3회 실제 시각감사와 결함 수정, S3 합법 회전/도로profile/failure-group을 갖는 active-mesoscopic adapter와 작은 교통 대조, S4 최종 회귀·실행자료·인계. 매 단계 expected parent SHA로 fast-forward 게시하며 main은 바꾸지 않는다.

원래 동기: 개별차량 ID/매차량 운동/GPU/JAX 없음. activity gain-loss, finite storage, shared committed suffix, collision-informed incoming-link Dijkstra를 유지한다. 지도물리와 렌더링을 분리하고 그림은 검증을 대체하지 않는다. 차로수는 aggregate capacity/storage로만 작용한다. 불가능한 지형/방향/접속을 무시한 연결복구와 teleport는 금지한다. Braess 가능성을 지우거나 개선을 강제하지 않는다. 100k 주민의 전일성능/실도시 calibration/게임우월성은 이번 주장 범위 밖이다.

검증: 도로 연속 경사·수계 및 교량deck, polyline 실제 길이, 공유 endpoint/층 식별, direction-preserving ramp turn, 도로내 질량/유한storage, whole structure failure, 동일topology 제어, 수치 replay. 작은 unit fixture와 3seed형태 비교, 짧은 도시운송 위주다. Native subagent 도구 없음: native_subagent NOT_RUN, 직렬 반례·CAS·실행검증. 사용자의 현재 실행 지시를 설계/구현 승인으로 적용한다.
