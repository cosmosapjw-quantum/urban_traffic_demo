# MetroFlow V03 · transient residence theory & surgical keyset revision · R1–R10/C1–C10 (2026-11-22)

## R1/C1 연구 계약 및 1차 검증

SSOT는 `docs/v1/PLAN.json` v1.1.26, `scenarios/v1/release_matrix.json` 및 원본 Rust physics source이다. 전 단계 최종 parent `472623f011a3b2e8aca21ed2fb2fa1cbc56d45d4`, 연구용 분리 worktree `research/v03-surgical-closure-20261122`. 사용자 원본 `main` 및 기존 작업 tree, 거대 원본 checkpoint는 수정하지 않는다. 원본 V03 조건: 도시별 실제 100,000주민, 3도시 × 3회 × 86,400초, 원본 10초 timestep, 고정 8GiB RLIMIT_AS, 7200초 프로세스 벽시계 캡, source-order FIFO, 경로별 `mass,birth` IEEE f64 값/순서, 체크포인트 wire, 수용 임계값은 그대로 유지한다. 정식 24시간 0/9건, DAG 완료 범위 `19/21` (ACCEPTED/VERIFIED_SCOPED), V03 선행 노드 `3/3`, 최종 소스의 3도시 달력 준비 `3/3`. 이들은 실제 완료가 변경되기 전까지 유지한다.

**실제 재현 출발점:**
- 검증된 25,700초 Valley 10만 주민 checkpoint SHA256 `ac7a209c6adfd594c791d1ac4b5b33c6e013ae73b7b594e42121115c89bd8369`, 원본 3,405,043,386B. 직전 분리 실행 25,700→25,710초 0초 성공: 전송 및 postroad flat 전부 통과, 다음 `continuous keyset allocation` 5,533,362,416B > 5,025,214,575B (508,147,841B 초과). 연속 25,650→25,730초 요청은 유효 50초까지만 완료, 같은 소스 다른 동적 budget에서 `event candidate materialize after road` 5,015,432,736B > 4,939,690,935B (75,741,801B 초과).
- 기존 `RoadState::intern_exact_keysets`는 크기가 다른 각 코호트의 ordered `tag,offset`만 공유하고 `mass,birth`는 독립적으로 보존하는 **표현 최적화**, 수치적 물리 알고리즘 자체가 아니다. `materialize_event_after_road`는 모든 uniform CorePart 신규 사본과 packet-owner 보수 상한을 선불 청구하여 최종 출력 평탄화 이후 물리 계산 완료를 다시 차단한다. 과거 반복 정책 대신 **선택적 eager keyset canonicalization을 hot-path에서 수술적으로 격리**하고, 동일 source·target·serialized binary에서 성립하는지 실험한다. 임의 바이트 credit 금지. 성공 시 나머지 차단은 별도 후속으로 기록.
- 이론은 별개의 배경 물리 연구: 경로별 transient occupation (N_r(t)), birth moment (H_r(t)), age stock (A_r(t)=tN_r(t)-H_r(t)), source/sink flux를 이용해 유한 구간의 실제 체류시간·경로 지연의 **구성적 nonstationary balance theorem**을 유도하고 exact Fraction 전방 검산한다. 이는 단순 keyset 최적화/no-go가 아닌 원본 1차 모멘트 이론의 물리적 확장이다. 가능하면 original `road` mass/residence ledger와 계산상 직접 대응하는 oracle을 추가한다.

**각 R_i/C_i stage**: 최소한 하나의 구체적인 분석·증명·구현·검증 또는 실행 evidence를 Git commit+push로 즉시 보존하고 원격 SHA를 읽어 확인한다. 10단계 지도는 canonical 21-node DAG 자체를 확장하지 않는다. 실험은 25,700→25,710 확인 후 성공 시 20→40→80→160초 요청을 실제 원본 10만 주민 원본 조건으로 증가시켜 각각 진짜 완료된 물리시간, 원본 source/native SHA, RSS, wall, checkpoint SHA, 세 mass ledgers를 계량한다. 문제 반복 시 과거 연구 history를 재평가하고 작은 재시도 대신 하나의 실행 경로를 구조적으로 교정한다.

**하네스 provenance:** 현 호스트에는 native subagent spawn/wait 도구가 노출되지 않아 `native_subagent=NOT_RUN`; 순차 통합과 외부 독립 문헌/기호/유리수 검산을 분리한다. 최종 과학 논문 수용, 9 full-day 시뮬레이션 수용, full CI, main merge는 이번 단계에서 자동으로 주장하지 않는다.
