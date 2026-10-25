# V1 단일 계획을 따르는 다음 실행

repo: cosmosapjw-quantum/urban_traffic_demo
integration: research/v1-integration-20261025
bootstrap: v1/foundation-access-journey-20261025
plan: docs/v1/PLAN.json 1.0.0

먼저 실제 bootstrap ref와 PUBLICATION.json을 확인한다. `AGENTS.md`, PLAN.json, `FOUNDATION_REPORT_KO.md`, `artifacts/v1_foundation_20261025/FINAL_RECEIPT.json`을 읽는다. `python tools/v1_plan.py render`, `validate`, `next`를 실행한다. 앞으로 다른 연구 인계의 '다음 노드'를 병렬 실행하지 않는다.

현재 다음은 **I01**이다. P00/M01/T01은 한정 검증되었고 실제 bootstrap PR에서 전체 repository와 공용 conftest·패키징·Python3.12/3.13 수용을 수행해야 한다. 과거 main에 바로 merge하거나, I01 수용 전 M02/T02 기능개발을 시작하지 않는다. 실제 통합 뒤 계획 상태를 갱신한다. 미래 노드의 파일·명령은 목표 계약이며 이미 구현됐다고 가정하지 않는다.

이번 실행은 면적 접근의 시간분포와 원래 출생 모멘트를 보존하는 전체 여정 연결이다. 2개 사설 연결을 제거한7개 공공도로의2veh 상당량이다. 10만 배경 주민의 교통이나24h 실행이 아니다. origin/destination delay law는 경로에 조건화한 독립 주변분포이며 사설 도로의 capacity나 차간거리 안전이 아니다. 기존 scalar activity physics, 고정 경로, signal phase를 재사용했다.

256개는 복원 작업공간의 서로 겹치지 않는156/79/21 시험 합계다. 부모 참조12개 포함, whole-repository CI NOT_RUN이다. 마지막 코드·계획의 영향33개 시험과 실제 도시 입력 replay도 통과했다. 기존104 Python 파일 중103개 불변, packet_network.py만birth accounting 확장이다. 상태 identity v2로 바뀌었으므로 이전 byte fingerprint를 그대로 요구하지 않는다.

작업은 PLAN.json의 노드별 계약·파일·예산·수용조건으로 제한한다. 필수 선행이 ACCEPTED인 노드만 진행하며 STOPPED는 선행조건을 만족하지 않는다. 계획 밖 모델 추가나 릴리스 문턱 완화는 먼저 계획변경 PR로 제안한다. 실측보정·3D게임·JAX/GPU·개별차량 도시default는 현재 범위 밖이다. 실제 사용자 승인 전 최종main merge/tag는 하지 않는다.
