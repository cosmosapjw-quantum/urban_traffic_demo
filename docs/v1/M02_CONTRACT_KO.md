# M02: 하나의 물리 지도와 두 그래프

이 노드는 PLAN.json의 M02다. bootstrap PR #25의 실제 병합은
`b687425b1daa6ce61f912240cafbd9f294b0578b`이고, 그 네 선행 노드는 ACCEPTED다.
새 지도 생성법이나 새 수송 solver를 추가하는 대신 기존 atlas·복원 문법을
`compile_city`/`load_city`라는 같은 공개 경계에서 검사한다.

## 정의와 계산 경계

`CitySnapshot`은 불변 RoadMap, polygon Landscape, FaceGraph, 기존 TrafficNetwork,
선택적으로 선언된 PortalRef, 주민 장부 및 identity를 보존한다.
중첩된 list/dict를 물리 snapshot 입력으로 받아 캐시 뒤에서 변하도록 두지 않는다.
Atlas의 polygon이 수계·보호구역의 권위이며 비어 있는 legacy rectangle로 대체하지 않는다.
복원 RoadMap에 별도 Landscape가 없을 때만 원래 Terrain의 rectangle을 같은 polygon으로
명시 변환한다. 이것은 atlas의 polygon을 추정하는 fallback이 아니다.

공공도로의 방향은 Section의 전·후방 차로 수에 의해 결정된다. 기존
`restored_traffic.compile_traffic(..., signals=False)`를 그대로 호출해 방향별 Road,
legal turn, 차로별 용량·저장량과 failure_group crosswalk를 만든다.
스칼라 흐름의 새로운 closure나 재배차는 구현하지 않는다. 신호는 T03의 소유권이다.
M02가 ID 정렬을 숨은 신호 위상으로 바꾸지 않도록 map-only compiler에서는 신호 생성을 끈다.
기존 legacy compiler의 기본 신호 동작은 바꾸지 않았다.

FaceGraph는 등록된 지상 끝점의 surface/bridge edge와 공급된 block boundary walk를 보존한다.
고가·램프를 XY로 투영해 새 교차로나 새 토지 면을 만들지 않는다.
복원 문법의 공급되지 않은 block을 임의 생성하지도 않는다. bridge의 투영이 다른 도로와
겹쳐도 실제 높이와 등록된 끝점만으로 접속을 판정한다. 비개발 open-space의 약한 단순
boundary walk는 진단 면적으로 보존하며, 개발 가능한 면에는 단순 polygon과 exclusion 검사를 요구한다.
PortalRef는 block ID와 등록 지상 node ID의 선언된 대응이다. 접근시간·용량·최적 출입구는 M03의 일이다.

## 검증 불변량

- Section의 끝점·방향·layer·ramp purpose는 기존 compiler에서 검사한다.
- surface 고도는 bilinear terrain과 같아야 한다. 길이와 최대 경사는 기존
  ground_profile 또는 deck_profile로 재계산한다. 길이는 SI m, 경사는 무차원이다.
  ground_profile은 기존의 terrain patch 분할·8-panel Simpson 길이 계산을 재사용한다.
  재표본화에 따른 길이 비교 허용값은 상대 1e-6/절대 1e-6 m, 경사는 상대 1e-6/절대 1e-8이다.
  전역 물리·수송 수용문턱을 완화한 값이 아니라 이 지도 기하 adapter의 비교 규약이다.
- 도로 폭 prior는 기존 문법과 같은 `(3.5*총차로수+2) m`다. 전체 폭이 보호 polygon과
  겹치면 거절한다. surface/ramp의 물 통과도 거절한다. 개발 block 내부에 완전히 들어 있는
  exclusion polygon도 검사한다. 교량의 물 통과 허용은 기존 facility 의미를 보존한다.
- 자기 교차 및 서로 다른 section의 미등록 교차를 검사한다. 공간 bucket은 후보쌍을 줄이고,
  최종 판정은 piecewise centreline segment에서 한다. 같은 XY 자체는 접속 근거가 아니다.
- 기존 audit와 같은 5m의 수직 간격 prior를 쓴다. 일반 교차에서는 접촉점의 높이 차이를,
  collinear overlap에서는 전체 겹침 구간의 최소 높이 차이를 검사한다.
  겹침에서 높이차는 선형이므로 부호가 바뀌면 최소는 0, 아니면 양 끝 절댓값의 최소다.
  중점 하나만 검사해 접촉을 놓치는 반례를 시험한다. 지하 deck은 거절하며 mainline에는
  terrain과의 간격도 검사한다. 이 값은 도로설계 표준이나 실제 차량 안전 인증이 아니다.
- block area·perimeter·용량·주민/일자리 장부와 방향별 group 예산 10,000을 검사한다.
  부족한 주민 수용량은 PHYSICAL_INFEASIBLE, 예산 초과는 BLOCKED_RESOURCE로 명시한다.
  불가능한 지형을 임의 연결하거나 주민 수를 줄여 통과시키지 않는다.

## 구조물 폐쇄와 관측

`closure_links(group)`는 기존 structure_windows를 통해 같은 물리 group에 묶인
모든 방향·section을 반환한다. 정적 `reachable(origin, closed_groups)`는 incoming-link 상태와
같은 legal-turn graph를 사용한다. 교량 한 개 폐쇄 전후의 연결성, 영향을 받는 방향 수를
보고한다. 이는 진행 중인 차량을 삭제하는 연산이 아니며 동적 정체·대기 응답은 후속 T03/T04다.

보고서의 reachable_residents_after는 reachable boundary node가 하나 이상인 block의 주민 합이다.
이는 명시한 접근성 proxy이며 포털 배정이나 실제 통행 가능량·평균 여정시간이 아니다.
도시 순서·node/section 목록 순서를 바꾸어도 canonical identity는 유지한다.
ID를 재명명하면 byte identity는 달라지며, 역대응한 도달 집합·저장량을 별도로 비교한다.
이 제한된 검사를 일반적인 모든 물리 대칭의 증명으로 확대하지 않는다.

## 수용 근거와 다음 작업

`artifacts/v1_m02_20261026/MATRIX.json`은 8×8km·resolution42의 여섯 도시와
seed7/17/41, 총18개 atlas JSON 및 V1 JSON 왕복 검증이다. 전부 PASS이며 주민 100,000명은
정적 배치 장부다. 24h 활동·교통을 실행한 수가 아니다. 가장 큰 registry도 3,726 방향 group이다.

`RESTORED_MATRIX.json`의 네 문법에는 각각 교량3/mainline10/ramp8이 실제로 들어 있다.
같은 snapshot/방향 compiler를 통과하며, 원래 생성기 파일들은 수정하지 않았다.
새 계약·CLI 반례 시험, 기존 map/traffic/terrain/access/journey 회귀는 RECEIPT.json에 묶는다.
실제 CI 상태와 로컬 검증은 구분한다. 독립 subagent 심사와 전체 제품 릴리스는 주장하지 않는다.

후속 PR은 M02가 통합·수용된 뒤 계획 순서로 진행한다. 현재 PR의 남은 CI를 확인하고
actual merge SHA를 확인하기 전에는 M02를 ACCEPTED로 올리지 않는다.
