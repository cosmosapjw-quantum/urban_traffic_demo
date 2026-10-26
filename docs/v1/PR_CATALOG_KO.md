# V1 PR 작업표

`PLAN.json`에서 생성. 논리 PR key는 GitHub PR 번호가 아니다. 미래 PR을 실제 생성했다고 표시하지 않는다.

한 노드 한 Draft PR. 직전 누적 구현 브랜치를 base로 고정한다. PR merge 없이 부모 HEAD 위에서 진행하고 main/release는 별도 승인한다.

|키|제목|의존|branch|base|
|---|---|---|---|---|
|V1-P00|[V1 P00] 단일 계획·DAG·요구사항 기준 확정|-|v1/foundation-access-journey-20261025|research/v1-integration-20261025|
|V1-M01|[V1 M01] 면적 활동측도를 출입구·접근시간 법칙으로 컴파일|P00|v1/foundation-access-journey-20261025|research/v1-integration-20261025|
|V1-T01|[V1 T01] 원래 출발시각을 보존하는 전체 여정 연결|M01|v1/foundation-access-journey-20261025|research/v1-integration-20261025|
|V1-I01|[V1 I01] 전체 저장소 통합 기준선과 V1 facade 확립|P00, M01, T01|v1/foundation-access-journey-20261025|research/v1-integration-20261025|
|V1-M02|[V1 M02] 지형·입체도로·회전·구조물의 단일 지도 계약|I01|v1/m02-layered-contract-20261026|research/v1-integration-20261025|
|V1-M03|[V1 M03] 활동가중 블록·복수 출입구·주거용량의 현실적 연결|M02, M01|v1/m03-activity-access-20261026|research/v1-integration-20261025|
|V1-D01|[V1 D01] 10만 주민의 집단별 하루 활동·수요 장부|M03, I01|v1/d01-daily-demand-20261026|v1/m03-activity-access-20261026|
|V1-T02|[V1 T02] 연속속도 기초에서 유한응답 집계 closure 확정|I01|v1/t02-finite-response-20261026|v1/d01-daily-demand-20261026|
|V1-T03|[V1 T03] 차로군·합류·회전·신호와 구조물 장애 모델 통합|T02, M02|v1/t03-lanegroups-nodes-20261026|v1/t02-finite-response-20261026|
|V1-T04|[V1 T04] 시간구간 이관·기록압축·통행관측의 수치 일관성|T03, T01|v1/t04-transfer-time-20261026|v1/t03-lanegroups-nodes-20261026|
|V1-R01|[V1 R01] 인과적 정보 channel과 동일물리 비용 관측|T04, I01|v1/r01-causal-information-20261026|v1/t04-transfer-time-20261026|
|V1-R02|[V1 R02] 공유 경로·유한정보 재탐색·Braess 보존|R01, T03|v1/r02-shared-routing-20261026|v1/r01-causal-information-20261026|
|V1-B01|[V1 B01] 버스·화물의 최소 운영과 승객/차량 분리|D01, T03, R02|v1/b01-parallel-20261026|v1/r02-shared-routing-20261026|
|V1-C01|[V1 C01] 단일 WorldState·다중 시간척도·저장/재개 실행기|I01, D01, T04, R02|v1/c01-parallel-20261026|v1/b01-parallel-20261026|
|V1-M04|[V1 M04] 실현 접근성에서 느린 도시개발로의 지연 피드백|C01, M03|v1/m04-lagged-growth-20261026|v1/c01-parallel-20261026|
|V1-C02|[V1 C02] 하루 도시 실행·시나리오·관측 패키지|C01, B01, M04, T01|v1/c02-parallel-20261027|v1/m04-lagged-growth-20261026|
|V1-P01|[V1 P01] 관측동등 경량화와 자원 상한 확립|C02|v1/p01|research/v1-integration-20261025|
|V1-V01|[V1 V01] 통합 물리·관측·대칭 적대 검증|C02|v1/v01|research/v1-integration-20261025|
|V1-V02|[V1 V02] 도시형태·지형·접근의 적대적 시각 검수|M02, M03, M04, C01|v1/v02-parallel-20261027|v1/m04-lagged-growth-20261026|
|V1-V03|[V1 V03] 로컬 10만 주민·24시간 실제 실행과 수치 수용시험|P01, V01, V02|v1/v03|research/v1-integration-20261025|
|V1-RLS01|[V1 RLS01] 1차 완성 릴리스·설치·재현·문서 정리|V03, I01|v1/rls01|research/v1-integration-20261025|

## 모든 PR 본문에 포함할 내용

- 변경한 공개 계약과 단위
- 대칭/표현중복/보존/관측 구분
- 실패 반례와 회귀 evidence
- 같은 입력의 baseline 또는 명시적 물리 차이
- rollback과 checkpoint
- 계획 상태 및 완료조건 갱신

각 노드의 입력·파일·가정·단위·수용시험·중단조건은 MASTER_PLAN_KO.md의 해당 절을 그대로 참조한다.

