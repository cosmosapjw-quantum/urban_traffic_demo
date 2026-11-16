# MetroFlow V1: 앞으로의 단일 작업계획

규범 원본은 [PLAN.json](PLAN.json)의 현재 버전이다. 기존 독립 연구 인계의 다음 노드를 따로 실행하지 않는다. 공유 `node_defaults`는 모든 노드의 증거·rollback·PR 검토 계약이며, 생성 문서에는 각 노드에 펼쳐서 표시된다.

```bash
python tools/v1_plan.py render
python tools/v1_plan.py validate
python tools/v1_plan.py next
```

첫 명령은 `MASTER_PLAN_KO.md`, `DAG.mmd`, `DAG.dot`, `PR_CATALOG_KO.md`를 생성한다. 이 생성 뷰는 규범 JSON과 별개로 편집하지 않는다. 납품 번들에는 생성 문서와 PNG/SVG도 포함된다. fresh checkout에서 검증 전에 위 render를 실행한다.

## 1차 완성

지도·지속적인 집단 활동·집계 교통·제한된 정보 경로선택·지연 개발이 한 실행기에서 연결되는 headless 연구 시뮬레이터다. 기준은 8×8km, 10만 주민, 24시간이며 승용차·정해진 노선의 버스·화물 운영을 구분한다. 실제 시민/차량 전수 추적, 3D 게임, 완전한 대중교통 배정, 실도시 보정 및 게임 우월성은 포함하지 않는다.

## 현재와 다음

현재 진척과 다음 노드는 `PLAN.json`의 `implementation_progress`, `nodes`, `next_node`를 따른다. 완료 구현·한정 실행과 최종 수용은 서로 다른 상태다. 전체 CI·통합·최종 릴리스는 별도 심사 후 진행한다.

V03의 전체 도시 계산은 Rust의 `NativeWholeEngine`과 Python frontend로 이행 중이다. 빌드·설치와 실제 로컬 모의실험 명령은 [NATIVE_RUNTIME_KO.md](NATIVE_RUNTIME_KO.md)에 정리한다. 기존 Python 수치 경로는 명시적 비교 oracle로 보존한다. 각 실행의 성공·차단 여부는 계획에 연결된 영수증으로 확인한다.

현재 작업은 [정확한 저장 표현과 실행 계약](../../artifacts/v1_rust_completion_20261116/IMPLEMENTATION_CONTRACT.md), [자원 정책 검토](../../artifacts/v1_rust_completion_20261116/RESOURCE_POLICY_REVIEW.md), [sub-ULP event 수치 분석](../../artifacts/v1_rust_completion_20261116/EVENT_RESOLUTION_ANALYSIS.md)에 연결된다. 공유 stage·공통 packet interval 저장과, 이전 stall 구간에서만 활성화되는 보상 시계의 수치 확장을 구분한다. 현재 `retained_capacity_v2` accounting은 생성 preflight와 retained runtime 자료의 수명을 분리하고, 하나의 shared dynamic 예산을 단계별 공존 allocation에 따라 사용한다. 공개 road/journey 상한은 더할 수 있는 별도 quota가 아니다. 총예산·resource policy를 checkpoint identity에 바인딩하므로 이전 고정분배 checkpoint를 무검증 재사용하지 않는다. 구체적인 수명·capture/decode·재로드 검증 상태는 [RUNTIME_BUDGET_REVIEW.md](../../artifacts/v1_rust_completion_20261116/RUNTIME_BUDGET_REVIEW.md)를 따른다. 한 후보의 테스트·진행 기록을 이후 후보의 전체 24시간 수용 증거로 확대하지 않는다.

## 의존 단계

|단계|노드|산출물|
|---|---|---|
|현재 기반|P00, M01, T01, I01|계획 권위·접근분포·전체 여정·저장소 통합|
|공간·활동|M02, M03, D01|입체지도·복수 출입구·하루 활동수요|
|수송물리|T02, T03, T04|유한응답 closure·차로군/노드·시간 이관|
|행동·운영|R01, R02, B01|인과적 정보·합법 재탐색·버스/화물|
|도시 통합|C01, M04, C02|불변 WorldState·지연 개발·하루 시나리오|
|수용·릴리스|P01, V01, V02, V03, RLS01|경량화·물리/지도 감사·로컬 100k24h·릴리스|

정확한 의존성, 파일, 입력/출력, 가정, 불변량, 관측, 시험, 완료·중단조건, 예산, PR 키는 PLAN.json의 각 노드에 있다. 미래 파일·명령은 예정 계약이며 이미 존재하거나 통과했다는 뜻이 아니다. 논리 PR 키는 실제 GitHub PR 번호와 구별한다.

## 완료 문턱

세 10만 주민 24h 시나리오를 실제 로컬에서 각각 세 번 계측한다. 계획의 공학적 목표는 case당 7,200초 이내, peak RSS 8GiB 이하다. 이는 현재 측정 결과나 성능 약속이 아니다. 같은 입력의 수치오차·질량·체류 장부, 실제 checkpoint 재개, 6도시×3seed 지도 검사를 함께 요구한다. 24h 관측 종료와 모든 과부하 여정 완료는 별개다.

`validate --release`는 현재 반드시 거절한다. 모든 필수 노드의 ACCEPTED 상태와 G-* 영수증 경로·SHA256이 갖춰져야 파일 바인딩을 검증한다. 이것은 과학적 주장 검토의 대체물이 아니다.

## 기반 실험의 이력

초기 기반 실험에서는 하천도시의 기존 경로 하나에서 두 private link를 접근/이탈 분포로 **교체**하고 공공도로7개를 통해2veh 상당량을 운송했다. 이 실험은 배경100k 수송을 포함하지 않았다. 당시 보고서 `FOUNDATION_REPORT_KO.md`와 `artifacts/v1_foundation_20261025/FINAL_RECEIPT.json`을 참조한다. 이 역사적 범위를 현재 전체 도시 실행 결과로 읽지 않는다.
