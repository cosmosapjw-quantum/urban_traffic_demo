# V03 실제 도시 연결과 로컬 수용시험 재개

현재 완료율은 19/21이며 V03은 실행 완료가 아니다. `tools/run_v1_acceptance.py`와 `scenarios/v1/release_matrix.json`은 지정한 river weekday seed17, coastal weekend seed41, valley weekday seed7의 100000 주민 입력을 원본 archive와 출입구 construction patch의 SHA, parent/new city identity로 복원한다. 기존 C02 two-zone fixture를 이 도시로 대신 보고하지 않는다.

preflight는 모든 주민 블록의 residential ActivityMeasure, 일자리 블록의 job ActivityMeasure, 별도 service ActivityMeasure를 기존 compiler로 구성한다. 서비스 기회량=해당 jobs stock은 이번 입력에 명시한 합성 prior다. 고정된 day profile과 모드·목적 및 1000kg freight를 `compile_daily_demand`에 그대로 전달한다. resident 수나 활동분율을 줄이지 않는다. 기존 max_cohorts=20000을 넘으면 `BLOCKED_RESOURCE`를 보존한다.

실제 river weekday seed17 및 valley weekday seed7은 기본 worker fraction에 필요한 job opportunity support가 부족해 PHYSICAL_INFEASIBLE을 반환했다. 인구·활동분율·일자리 용량을 조정해 통과시키지 않았다. 이 물리 입력 계약을 먼저 해결해야 한다.

실제 coastal weekend seed41 preflight는 427 residential zones와 478 job/service zones를 복원했고 dense OD/cohort budget 초과를 확인했다. 하드코딩된 C02 gate/freight endpoints 때문에 다중 블록 도시의 ServiceModel 조립까지 이어지는 일반 adapter도 현재 없다. 이 구현 의존성을 `BLOCKED_IMPLEMENTATION_DEPENDENCY`로 반환하며, runtime/RSS·simulated time은 각각 NOT_RUN·0이다. 로컬 전체 캠페인은 별도 `BLOCKED_LOCAL_EXECUTION`이다. CLI는 두 경우 모두 exit2이며 로컬 호스트에서 실행해도 미구현 경로가 자동 통과하지 않는다.

다음 최소 작업은 D01의 선언된 OD와 각 목적/차종/시간 profile을 보존하는 bounded/factorized cohort 표현을 선택·검증하고, 각 실제 PortalRef node를 사용해 legal-turn routes와 access laws를 ServiceModel로 연결하는 것이다. 단순히 max_cohorts를 키워 전체 dense 곱을 물질화하거나 two-zone으로 축소하면 기존 의미·자원 조건을 충족한 것으로 셀 수 없다. 화물의 실제 origin/destination, scheduled bus와 passengers, 원래 birth times, unfinished demand, checkpoint 복원도 같은 도시 identity에 묶어야 한다.

그 adapter의 작은 지도 검증 후, 사용자의 실제 로컬 CPU/RAM/OS/Python을 다시 확인하고 세 case 각3회 86400s 실행을 계측한다. wall<=7200s, peakRSS<=8GiB, tick p50/p95, route latency p99, peakrecords, short matched refined-dt 관측과 24h 장부·checkpoint/continuous 대조를 기록한다. 이번 cloud preflight 결과를 그 성능 시험으로 외삽하지 않는다. 전체 repo CI·통합·최종 수용은 사용자 지시대로 보류한다.

명령:

```sh
python tools/run_v1_acceptance.py --matrix scenarios/v1/release_matrix.json --repeat 3 --preflight-only --out artifacts/v1_v03_20261027
```

단위검증은 `tests/v1/test_release_preflight.py`의 실제 patch 재구성/변조 거절, demand 실패 보존과 허위 실행 receipt 방지를 대상으로 한다. Python3.12/3.13 각각2개 통과, ruff 통과를 실행했다. 원본 동결 지도를 변경하지 않았다.

## 2026-10-27 연구 루프 갱신

`factorized_demand`가 원래 독립 OD를 정확한 지연 생성으로 표현한다. release matrix는 명시적 `unassigned_home` 정책을 사용하여 취업 희망/배정/미배정량을 보존한다. 세 실제 도시 모두 factorized COMPILED다. `ReleaseRuntime`은 제한된 자동차 출발 집합의 실제 공유 도로망·접근분포·checkpoint 실행을 제공한다. 전체 경로 활성화, 귀가 의존성, 버스·화물 결합은 남아 있다. 새 근거는 `artifacts/v1_v03_resolution_20261027/RESEARCH_RECEIPT.json`, 유도·독립검토는 `V03_RESOLUTION_RESEARCH_KO.md`를 따른다. 완료율19/21 유지.

## 2026-10-27 공동 실행 후속 연구

`ReleasePlan`은 실제3개 도시의 정확한 calendar를 bounded페이지로 구성하고 미구성 수요를 정량 보존한다. `ReleaseRuntime`은 완료+dwell 귀가/내부 이동을, `ReleaseServicePlan`은 명시 fleet/depot와 미배정 장부를 제공한다. `JointReleaseRuntime`은 유한 경로집합의 모든 차종을 단 하나의 ServiceModel.step으로 갱신하며 접근/이탈/귀가 장부와 checkpoint를 검증한다. Python3.12/3.13 각각38개 관련검사와ruff통과. 근거: `artifacts/v1_v03_joint_20261027/RECEIPT.json`; 유도와독립검토: `V03_JOINT_RUNTIME_RESEARCH_KO.md`.

남은 구현은 전체 calendarcursor를 점유중 joint도로상태와 하나의 트랜잭션/checkpoint로 활성화하는 driver 및 active record 예산 처리다. 도시 전체 fixedfleet/depot 입력도 명시해야 한다. 그 후 실제 로컬3case각3회24h 계측을 수행한다. 현재 페이지16개씩의 경로구성은 simulated0s이며 전체 실행을 대신하지 않는다. 완료율19/21유지.
