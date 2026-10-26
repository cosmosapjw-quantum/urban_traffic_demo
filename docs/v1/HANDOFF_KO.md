# M02 이후 인계

repo: cosmosapjw-quantum/urban_traffic_demo
integration: research/v1-integration-20261025
branch: v1/m02-layered-contract-20261026
plan: docs/v1/PLAN.json 1.0.2

최신 AGENTS·실제 HEAD·병렬 작업과 PLAN.json을 먼저 확인한다.
bootstrap PR #25는 b687425b1daa6ce61f912240cafbd9f294b0578b로 병합됐다.
P00/M01/T01/I01은 그 actual merge와 최종 HEAD CI run40184942213을 근거로 ACCEPTED다.

현재 M02는 VERIFIED_SCOPED, next_node=M02다. M02_CONTRACT_KO.md,
artifacts/v1_m02_20261026/RECEIPT.json과 SOURCE_MANIFEST.json을 읽는다.
6도시×3seed의18개8km/res42 atlas 및 snapshot JSON 왕복, 4복원문법,
109개Python3.12 관련회귀, 60개Python3.13 V1 시험을 재사용한다.
이것을 100k24h 활동·수송 또는 전체 제품 완료로 확대하지 않는다.

새 PR의 HEAD와 CI(양쪽 Python의 validate-city --matrix 포함)를 확인해 통합하라.
그 actual merge를 확인한 뒤 M02를 ACCEPTED로 갱신하고 PLAN 위상순서로 한 노드만 선택한다.
소스가 바뀌지 않았다면 next_node가 M02라는 이유로 같은 전체 감사를 반복하지 않는다.
신규 main merge/release tag, 계획 밖 기능이나 수용문턱 완화는 실행하지 않는다.

공개 입력은 compile_city/load_city이며 face graph와 directional transport graph는 별개다.
Atlas polygon은 권위다. 복원 문법도 같은 snapshot/compiler를 사용한다.
M02는 compiler의 signals=False를 사용하며 신호제어는 T03의 소유권이다.
PortalRef는 선언한 block↔ground node 대응만 담는다. M03은 이 snapshot을 소비해
활동·복수 출입구를 진행하며, 접근시간/용량을 현재 PortalRef가 해결했다고 가정하지 않는다.
폐쇄 도달성은 정적 legal-turn graph 검사다. active 차량을 삭제하거나 동적 정체를 해결했다고 하지 않는다.
