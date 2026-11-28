# MetroFlow V1 실행 지침

2026-11-28 사용자 결정: `docs/akm/RESEARCH_SSOT_KO.md` v1.0.0이 과학연구의 방향·순서·유한 DAG·anti-drift/anti-local-minima 중단 규칙의 정본이다. `docs/v1/PLAN.json`은 V1 제품/수용/릴리스의 규범 실행계획으로 유지한다. 두 권위의 범위를 혼동하지 않는다. `python tools/v1_plan.py render`로 상세 문서·DAG·PR 작업표를 생성하고, `validate`와 `next`로 기준과 다음 노드를 확인한다.

## 실행 권위
- 과거 roadmap·인계의 다음 작업·구현 순서는 역사적 근거다. 새 노드를 자동 활성화하지 않는다.
- 이전 AGENTS는 `docs/archive/AGENTS_pre_v1_20261025.md`에 원본 blob 그대로 보존한다. 원래 main의 호환 경로를 삭제하라는 지시가 아니다.
- 현재 bootstrap PR #25는 b687425에서 통합·수용됐다. M02는 PR #26(954e644)에서 수용됐다. M03는 PR #27에서 한정 검증됐고 미통합이다. D01도 한정 검증된 누적 구현이다. T02도 유한응답 closure를 한정 검증했다. T03의 차로군·교차로 계약도 한정 검증했다. T04의 시간구간·유한응답 수송도 한정 검증했다. R01의 인과적 정보 channel과 완료 비용 관측도 한정 검증했다. R02의 합법 공유 경로·유한정보 suffix 제안도 한정 검증했다. B01 운영도 한정 검증했다. C01 실행기·저장/재개도 독립 병렬 한정 검증했다. M04 지연 개발·실행기 연결도 한정 검증했다. C02의 선택한 두 구역 하루 실행도 한정 검증했다. V02 지도 감사도 실행 완료했으나 등록 portal 0과 실제 접근성 미지원 finding을 유지한다. P01을 한정 검증했고 V01도 새 합성 출입구의 38개 지도 물리 접근·유향 연결 감사로 한정 검증했다. 원본 무출입구 지도 증거는 보존한다. V1 릴리스 DAG의 다음 노드는 V03이다 (과학연구의 다음 노드는 AKM SSOT에서 선택). 완료 구현·한정 실행은 19/21(90.5%); 최종 수용은 5/21이며 전체 CI·통합은 보류한다. P00/M01/T01의 한정 검증을 전체 저장소 통합이나 V1 완성으로 확대하지 않는다.
- bootstrap은 `v1/foundation-access-journey-20261025` → `research/v1-integration-20261025`의 하나의 PR이다. I01 수용 전 후속 기능 PR을 진행하지 않는다. main merge와 release tag는 최종 사용자 승인 전 실행하지 않는다.
- 2026-10-26 사용자 변경: 한정 검증 영수증을 가진 VERIFIED_SCOPED 또는 ACCEPTED 선행 위에서 누적 구현 브랜치를 쌓는다. 전체 CI·통합·별도 수용 심사는 모든 DAG 구현 후 수행한다. 현재는 PR merge/전체 CI를 실행하지 않는다. STOPPED/BLOCKED는 선행조건이 아니다. 2026-10-26 최신 사용자 승인에 따라 독립 노드는 파일 소유권을 나누어 병렬 구현한다. 공유 계획·게시는 직렬화한다.
- 계획 변경은 PLAN.json 버전과 근거를 먼저 갱신한다. 범위·수용문턱을 통과 목적으로 완화하지 않는다. 사용자 승인 없는 scope 증가는 금지한다.
- 2026-11-16 V03 후속: 실제 로컬 5900X/관측 RAM 31.25GiB에서 세 도시의 예산 사전 거절, 전체 하천 달력 5,093,765 legs 보관(peak RSS 1.42GiB), 각 도시 256-leg 공유 runtime 준비와 한정 회귀를 수행했다. 생성자·장부 검사 중복 계산과 route p99 구간 계측을 개선했다. `artifacts/v1_v03_scaling_20261116/RECEIPT.json`을 따른다. 전체 calendar의 경로/물리 상태 활성화 및 3case×3회24h는 남았으며 19/21과 V03 BLOCKED를 유지한다.
- 2026-11-17 V03 후속: 차단 checkpoint 실측으로 계상 수명 불일치를 교정했다(`retained_capacity_v3`, `adde1a3`; 260 scoped, legacy replay bytes 동일). 짧은 게이트는 25,650/32,730/25,420s에서 멈췄고, guard 우회 진단에서 road interval part 행이 아침 진입 구간에 수십 초마다 배가해 Valley는 8 GiB에서 실제 할당 실패했다. `artifacts/v1_v03_workspace_20261117/RECEIPT.json`을 따른다. 24h 0/9, 19/21, V03 BLOCKED 유지. 당시의 표현 변경 보류는 아래 2026-11-23 사용자 승인과 현재 PLAN의 constructive next action으로 갱신됐다.
- 2026-11-17 선택 (a): 부분 head 서비스가 새 행의 약 80%를 만들고(서비스마다 모든 행의 새 구간 packet 생성), bit 동일 병합 상한은 수 %다(`ATTRIBUTION_KO.md`). 당시 비례 조성 표현(실수 산술 동치)과 모델 계약은 보류했으며, 아래 최신 사용자 승인 범위에서 구성적으로 검토한다.
- 2026-11-17 선택 1 사전측정의 역사적 범위: 측정한 실수 산술 병합의 packet 감소는 1.01–1.08배였고 당시에는 재작성하지 않았다. 이 측정은 모든 정확한 표현의 24h 불가능성을 증명하지 않는다. 당시의 근사 집계 금지는 아래 2026-11-23 사용자 승인 범위에서 명시적 모델 변형 연구로 갱신되며, 원래 V03 수용문턱은 유지한다.

## 유지하는 과학·구현 계약
- 2026-11-16 사용자 승인: Rust CPU 계산코어·Python frontend로 전환한다. 기존 Python 코어는 이행 중 명시적 scientific oracle로 보존한다. JAX/GPU·차량 위치 전수추적·RL-first·외부데이터 학습은 V1 범위 밖이다.
- 연속 위치·속도 기초, 목적·차종·정보를 보존한다. 계산 closure의 가정과 유효범위를 명시한다.
- immutable WorldState, SI 단위, rate와 increment 구별, 차량량·사람·화물·체류량 장부, 다중 시간척도와 지연 피드백, 버전별 캐시 invalidation, 실제 checkpoint 재개를 유지한다.
- 물리 대칭, 수동 좌표공변, 표현 quotient, 수치 근사를 구분한다. ID·해시·기록 수를 물리 관측과 혼동하지 않는다.
- 행동 반례를 먼저 검산하고 변경 의존성만 회귀한다. 최초 import 실패를 행동 RED로 재명명하지 않는다. 실행하지 않은 검증은 NOT_RUN이다.
- 실패는 모델·수치·구현·환경·자원·물리적 불능으로 구분하고, 마지막 유효 상태를 보존한다. 질량 삭제나 수요 축소로 예산을 맞추지 않는다.
- 해시/manifest는 연구 재현성의 식별용이며 보안 인프라를 확장하지 않는다. 문서·검증 자체를 재귀적으로 감사하는 작업은 하지 않는다.


## 2026-11-23 사용자 승인과 매 턴 역사적 drift watchdog

- MetroFlow 연구를 이어가는 매 턴, 최초 `0492364`의 `docs/PRD.md`, `specs/001-metroflow/spec.md`, 교통·도시 설계와 `6524500`의 `memory/constitution.md`를 역사적 기준으로 현재 변경을 대조한다. 원본 commit/blob identity와 확인된 근거를 재사용하고, 해당 변경의 동기·가정·관측량 차이를 짧게 기록한다. 이 문단은 당시 역사적 지시다. 현재 연구 실행 범위·DAG 권위는 AKM SSOT이고, 기존 V1 수용 권위는 PLAN.json이다.
- 보존할 원 동기는 100k mesoscopic 도시의 지도·교통·접근성·지연 개발·미래 수요의 결합, 병목·우회·유발수요의 설명, 목적·차종·유한정보·유한응답과 사람/차량/화물 장부다. 반복되는 배열 표현이나 특정 IEEE 연산열 자체를 최초 과학 목적과 동일시하지 않는다.
- 사용자는 원 목적을 보존하는 surgical model revision과 새로운 명제·증명·구현의 병행을 승인했다. bit 동일 표현, 실수 산술 동치의 수치 구현, 제어된 근사 모델을 명시적으로 구별한다. 모델 변형에는 가정·단위·유효범위·오차 및 원래 관측과의 대조를 붙이고 버전을 분리한다. 이를 원래 V03의 수요·허용오차·8GiB/7200s·24h3case×3회 기준을 완화하는 승인으로 해석하지 않는다.
- 매 턴 watchdog에는 보존된 동기, 변한 가정, 실제 유도/계산/완료한 물리 구간, 남은 drift 위험을 기록한다. 같은 실패를 다음 guard로 옮기는 작업만 반복하면 source 표현과 실제 소비 경로를 재검토한다. 과거 좁은 병합 실험을 일반적 no-go로 확대하지 않는다.
- watchdog은 새 DAG 노드·승인 게이트·재귀 감사 루프가 아니다. 실제 이론/코드/실험 산출물을 우선하고, 이미 승인된 작업을 재승인 요청으로 멈추지 않는다. 현재 한정 검증19/21,최종수용5/21,V03BLOCKED,원래24h완주0/9를 유지한다.
- 이전 causal-rank 연구의 역사적 근거는 `docs/research/V03_CAUSAL_RANK_20261123.md`와 `artifacts/v03_causal_rank_20261123/`에 있다. 당시 native는 Valley0→25700s를 원본 checkpoint와 byte 동일하게 실행했고 전체 캘린더3/3을 준비했다. 25710s indexed sweep은 자원 차단 상태다. optional rank adapter와 고정 service의 closure bound를 native coupled-city 완료로 확대하지 않는다.

- 2026-11-23 최신 coding C1–C10 완료 근거는 docs/research/V03_CODING_RECONSTRUCTION_20261123.md와 artifacts/v03_coding_reconstruction_20261123/C10_RESEARCH_RECEIPT.json이다. 최신 source796849f7/native96e8e20은 Valley0→25710s 전체 wire·장부를 동일하게 재현하고 checkpoint25710→25720s를 완료했다. fresh25720은 journey 예약에 따른 낮은 road allowance로, 재개25730은 transfer candidates로 각각 자원 차단된다. 전체 캘린더 준비3/3, Rust190 passed·2 ignored, Python42 passed, finite wire/physical16쌍과 scoped 독립 검토가 완료됐다. PLAN1.1.29의 다음 작업은 journey input/current/pending stage/history 최대비용의 실제 owner를 분해하고 영속 source/interval 소비 경로를 구성적으로 개선하는 것이다. 25720을 fresh 연속 실행 성공으로 확대하지 않으며 원 기준·19/21 scoped·5/21 accepted·24h0/9·V03 BLOCKED를 유지한다.

- 2026-11-23 다음 10단계 누적 결과: research/v03-measure-lift-loop-20261123에서 현재 native source99765850/native378619a7의 StageQueue 안정적 재분할로 Valley0→25720s의 전체 checkpoint wire·장부가 원본과 동일하게 완료됐다. 25730s는 fresh source remainder packing 및 resumed transfer candidates로 각각 자원 차단된다. 10/10 연구 단계 완료, DAG19/21 한정 완료·5/21 수용, 최신 전체 calendar 준비3/3, 원래24h0/9. 신규 Marked cumulative-rank FIFO/체류시간 명제와 exact-rational shadow는 별도 science-model v0이며 현재 native physics 교체를 의미하지 않는다. StageQueue repack 구·신 Arc 공존 working peak의 정확한 global accounting은 미검증으로 보존한다. 최초0492364 PRD/spec 및6524500 constitution의 도시–교통–접근성–지연개발–수요 원동기와 전체 원문턱을 지킨다. 규범 PLAN1.1.30을 사용한다.

- 2026-11-24 현재 PLAN1.1.31. V03 L01–L10 근거는 artifacts/v03_remainder_rebuild_20261124/L10_RESEARCH_RECEIPT.json에 있다. 실제 Valley 25,720 s 체크포인트의 전체 wire와 물리 장부를 동일하게 복원했다. 부하 검증의 상태 소유권 수명 분리와 고정 지지집합의 교차로 할당 안정성 증명은 별도 성과다. DAG 19/21 한정 완료·5/21 수용, 원래 24h 0/9, V03 BLOCKED를 유지한다. 최초 0492364와 6524500의 delayed LUTI, 병목·우회·유발수요와 replay 계약을 유지한다.

- 2026-11-26의 역사 대조는 최초 PRD/spec 0492364와 constitution 6524500을 기준으로 V03_STRUCTURAL_RESET_20261126.md에 기록했다. 예산 공제와 키 공유의 실제 소유자를 검증했고, 원 수요와 도로에 대한 모형의 누적 진입·유출 및 병목 개입을 원 엔진과 대조했다. 다음 연구 턴에도 원본 동기, 이번에 바뀐 물리 가정, 원 엔진과 공통으로 측정한 관측량, 남은 편향을 대조한다. 최신 V1 수용 상태는 docs/v1/PLAN.json을 따른다. 연구 실행 순서는 2026-11-28 AKM SSOT를 따른다.

## 2026-11-26 Rust backend correction (user instruction)
- Production backend, scientific compute, input preparation, benchmark/measurement and headless execution must be Rust. Python is frontend/serialization only or explicitly opt-in independent oracle/test. C++/Python historical research engines are retained for provenance, not accepted as new backend execution.
- Never count a Python-driven experiment as standalone Rust evidence merely because it invokes a Rust extension. Keep typed backend functional coverage, standalone execution coverage, and original V03 acceptance separate. Prefer Rayon indexed parallelism and measured data layout/SIMD; use faer only for a genuine linear algebra workload. No change of original physics or release limits to inflate completion.

## 2026-11-28 AKM research epoch (current)
- Before further research read docs/akm/RESEARCH_SSOT_KO.md; use python tools/akm_plan.py validate/next. Default one eligible node, at most two independent nodes. Do not restart an automatic R1–R10/C1–C10 loop. Research stages are not release nodes.
- Preserve original exact solver/checkpoints as reference, not mandatory production representation. Distinguish model, numerical, implementation, runtime, resource and permission errors. AD/ALM rules in the SSOT are binding. Two nonproductive attempts terminate the corresponding approach; decision/terminal edges never point backward. No new candidate or cap changes just to show progress.
- User retains final approval for candidate/release contract, full CI/main merge. No original V03 acceptance credit from archived projected city or synthetic labs. Historical positive_next_action and prior watchdog notes are evidence, not current research scheduler.

- 2026-11-28 D05 final: retain Rust calculation backend and Python presentation frontend (user instruction). Python scientific oracle/receipt audit is not runtime. Read latest AKM SSOT status; D05 exhausted, D07 distinct ready node. No claim of whole-model convergence from service fixture.

- 2026-11-28 D08 user architecture correction: reuse existing Rust implementations before writing replacement kernels. Current default manifest entry is Rust native via metroflow-v1 run --manifest; native city/AKM aliases delegate directly. Historical Python facade lazy, explicit oracle only, no fallback. Report actual execution ownership separately from raw LOC; do not delete historical reference code to inflate ratio. D08 scoped terminal; next D09 original-city pilot, original PLAN unchanged.
