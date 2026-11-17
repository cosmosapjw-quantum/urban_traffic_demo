# Rust 실행 코어·저장 표현·전역 예산 검증 보고서

작성 기준: 2026-11-16 UTC. **실제 세 도시 캠페인은 모두 자원 예산으로 차단됐으며, 24시간 완료는 0/9회다.**
현재 완료 구현·한정 실행은 **19/21(90.5%)**이며 V03의 24시간 수용은 완료되지 않았다.
전체 저장소 CI·통합·merge·release는 사용자가 정한 별도 심사 순서에 따라 보류한다.

## 결론과 근거 상태

도시 실행의 달력 활성화·경로·도로·서비스·여정 상태와 시간 전진은 Rust의
`NativeWholeEngine`이 소유한다. Python은 입력 구성, CLI/process 감독, artifact I/O,
진단·표시를 맡는다. 이전 Python 수치 경로는 명시적 scientific oracle로 보존한다.
이는 기존 toy CLI와 모든 legacy Python 모듈을 삭제했다는 주장이 아니다.

공유 stage 저장, packet 공통 interval 저장, 기존 점유 checkpoint의 재실행은
**implementation-verified(scoped)**다. Sub-ULP event의 보상 시계는 실제 이전 중단
지점을 넘어 진행했지만, 정확한 실수 연산이나 이후 전체 trajectory와의 동일성을
보장하는 주장은 아니다. 새 전역 예산 계상은 독립 소스 검토와 최종 251개 scoped
검사를 통과했다. 해당 범위는 **implementation-verified(scoped)**이며, 실제 캠페인에서는 아래의 자원 중단을 확인했다. 이를 전체 24시간 수용으로 해석하지 않는다.

## 후보와 실행 근거의 경계

| 후보 | 코드·binary 식별 | 확인된 결과 |
|---|---|---|
| 이번 작업 기준 | commit `7b5e518f6c098ed831551da4e66d980addf80dd8`; [BASELINE.json](BASELINE.json) | 이전 queue/Rayon 구현과 저장 표현의 기준 |
| 저장·수치 보완 | commit `1d3de56b675b6a09636c407febd5daf312c895da`; [SOURCE_MANIFEST_NUMERIC.json](SOURCE_MANIFEST_NUMERIC.json); binary `b8a133526c1bbef038e9a20b3f4394f2091f9f892eb0fe46122068d413a6a9a2` | [213 scoped 검사](TESTS_NUMERIC.log); 실제 Valley 25,490→25,520s 재개 뒤 당시 road quota로 차단 |
| 공통 interval·고정 반분 예산 | commit `27e426fc64452ae2492828653f94f2506b8881fc`; [SOURCE_MANIFEST_FINAL.json](SOURCE_MANIFEST_FINAL.json); binary `0cd2e490e9b1323b88c1dff4247dffbcf75b5a667738df7d1e29736f2a0be466` | [236 scoped 검사](TESTS_FINAL.log); 이전 점유 구간 3회 byte 재현; 세 도시 첫 실행은 모두 owner quota 차단 |
| Retained capacity·단계별 shared pool | commit `532effe32f90c20cf3cbc1de350d0e7267f52584`; `retained_capacity_v2`; [SOURCE_MANIFEST_BUDGET_FINAL.json](SOURCE_MANIFEST_BUDGET_FINAL.json) | [최종 251 scoped 검사](TESTS_BUDGET_SEQ_FINAL.log), 기존 점유 구간 3회 byte 재현; `runtime_budget_campaign` 세 도시 첫 실행 모두 `BLOCKED_RESOURCE` |

파일 이름 `SOURCE_MANIFEST_FINAL.json`, `TESTS_FINAL.log`, `final_campaign/`의 “FINAL”은
`27e426f` 후보에 붙인 당시 이름이다. 이후 retained-capacity 후보의 최종 근거로
읽지 않는다. 후보 사이의 resource binding이 다르므로 이전 checkpoint의 identity를
바꾸어 새 정책에 적용하지 않는다.

## 이력·stage·packet 저장에서 바뀐 것

**직접 관측:** 이전 bounded trace에서는 entering stage가 대부분을 차지했고,
현재 조사 checkpoint의 road parts에는 완전히 동일한 fullpart 중복이 없었다.
45,715개 packet 전부가 packet 내부에서 동일한 interval을 공유했다. 서로 다른
packet의 같은 tag/offset 재등장은 실제 interval·FIFO 경계가 다른 경우를 포함한다.
완전한 key-set 검사의 결과와 질량 분포는 [PART_LINEAGE_PROBE.json](PART_LINEAGE_PROBE.json),
[PART_LINEAGE_SUMMARY.json](PART_LINEAGE_SUMMARY.json)에 보존한다. 작은 양수 질량의
존재를 삭제의 근거로 사용하지 않았다.

**구현:** stage는 256행 불변 block을 공유하고, 이미 계산된 `born+delay`의 범위로
아직 준비되지 않은 block을 건너뛴다. 부분 준비 block은 원래 순서로 filter한다.
ReceiptHistory는 원래 row·prefix expansion을 유지하면서 allocation 계상과 공유를
개선했다. Road는 finite endpoint의 bits를 packed 형태로 보존하며, 공통 interval의
행 payload는 `CorePart` 32B, mixed interval의 행은 `Part` 48B를 사용한다. Packet
메타데이터·capacity와 변환 중 raw/packed 버퍼가 공존하는 비용은 따로 계상한다.

**유도와 범위:** ordered sequence의 stable filter와, 저장된 각 행의 bit-exact
복원은 같은 순서의 kernel 입력을 제공한다. 이 논거는 packet 경계를 합치거나
부동소수점 합산을 재결합하는 허가가 아니다. 같은 target을 가진 packet이라도
head mixture와 event midpoint에서 평가하는 비선형 motion/latent 연산이 달라질 수
있으므로 경계를 유지한다. 근거와 검토는 [IMPLEMENTATION_CONTRACT.md](IMPLEMENTATION_CONTRACT.md),
[PART_LINEAGE_ANALYSIS.md](PART_LINEAGE_ANALYSIS.md),
[PACKET_STORAGE_REVIEW.md](PACKET_STORAGE_REVIEW.md)를 따른다.

## 실제 sub-ULP 수치 중단과 보완

[원래 재현](event_probe.json)은 마지막 유효 시각 25,490s에서
`cursor=8.221431926605018`, `h=6.538054381607992e-16`인 양수 사건을 발견했다.
Binary64의 `cursor+h`가 cursor와 같아 기존 kernel이 명시적 수치 오류로 중단했다.

보상 시계는 기존 경로가 이 조건으로 정지하던 경우에만 활성화하고, 양수 시간을
남은 horizon과 future boundary에도 반영한다. 실제 FIFO 진행, 기존 장부 검사와
국소 수치 예산을 유지한다. 이 시간 해상도 확장은 저장 표현 동치와 별개다.
특히 작은 served mass를 큰 잔량에서 빼면 subtraction이 반올림으로 사라질 수 있어,
head retirement 하나만으로 정확한 질량 분할을 증명할 수 없다.

[1-worker 재개](numeric_resume_t1.json)와 [4-worker 재개](numeric_resume_t4.json)는
25,520s의 보고서와 checkpoint bytes가 일치했다. 해당 runtime의 검증된 proposal
진단은 sub-ULP 사건 14개, 처리한 작은 시간 합의 상한
`E=6.080222403902695e-15 s`, 보상 시계 반올림 잔차 상한
`R=5.978086547377985e-31 s`였다. `E`는 누락된 시간이 아니며,
`nominal_subulp_service_mass_upper`도 전체 질량 오차 상한이 아니다. 이 누적 진단은
후속 coupled rollback·branch·replay를 포함할 수 있고 checkpointed physical 장부와
다르다. [수치 분석](EVENT_RESOLUTION_ANALYSIS.md)과 [독립 검토](EVENT_RESOLUTION_REVIEW.md)에
가정·반례·검증 범위를 명시한다.

## Scoped 성능과 병렬 재현성

[이전 측정](../v1_queue_debug_20261116/COMPARISON.json)과
[공통 interval 후보의 재실행](legacy_replay_final.json)은 같은 점유 checkpoint에서
모의 25,240→25,340s 구간을 각각 3회 실행했다. 모든 새 실행의 보고서와 checkpoint
bytes가 이전 결과와 일치했다. 입력 checkpoint SHA-256은
`3bbe3b1b8ecbeb534b946fa31884c922cf5a6e97cdbe6212c0ba763c351df86d`,
출력은 `ef4719a822ac85763679061a5ebd1d431e0edd9cec4e105a15ad1a5f7d4d884f`다.

| 한정 측정 | 이전 `7b5e518` 코드 | 공통 interval 후보 | 관측된 변화 |
|---|---:|---:|---:|
| serial advance 중앙값 | 1.792937s | 1.300164s | 27.48% 감소 |
| process peak RSS | 676,192,256B | 549,531,648B | 18.73% 감소 |

위 표는 공통 interval 후보까지의 결과다. 이후 최종 retained-capacity 후보의
[같은 구간 3회 replay](legacy_replay_budget.json)는 각각
1.401109552 / 1.378083004 / 1.394881746s, 중앙값 1.394881746s,
peak RSS 556,859,392B였다. 보고서와 checkpoint bytes는 세 번 모두 이전 결과와
일치했다. `7b5e518` 측정 대비 advance 중앙값은 22.20%, RSS는 17.65% 낮았다.

모두 실제 공유 host의 한정 구간 관측이다. 다른 작업이 없는 격리 benchmark나
24시간 성능의 외삽으로 해석하지 않는다. 추가 guard 이후의 시간 차이도 이 한 번의
공유 host 비교만으로 독립적인 원인 효과라고 확정하지 않는다.

기존 private Rayon pool과 indexed `ordered_map`을 유지한다. 적용 위치는 독립 cell
motion 예측과 독립 leg chunk 작업이며, 결과 commit·부동소수점 reduction은 원래
순서를 유지한다. [v1_parallel.rs](../../crates/metroflow-rust/src/v1_parallel.rs),
[v1_road.rs](../../crates/metroflow-rust/src/v1_road.rs),
[v1_journey.rs](../../crates/metroflow-rust/src/v1_journey.rs)가 코드 근거다.
[Cargo.lock](../../Cargo.lock)의 실제 버전은 Rayon 1.12.0, rayon-core 1.13.0이다.

이전 1/2/4/8 worker replay와 앞선 수치 후보의 1/4 worker 재개는 동일한 물리 보고서와
checkpoint를 만들었다. 속도는 worker 수에 비례하지 않았다. 앞선 수치 재개에서
1→4 worker는 advance 6.024→5.612s였지만 peak RSS는 1.586→1.995GB로 늘었다.
단일 비교와 공유 host 조건 때문에 일반적인 병렬 speedup을 주장하지 않으며 기본은
1 worker로 유지한다.

**faer 적용 여부:** 이번 코드에는 faer 의존성·호출을 추가하지 않았다.
[crate manifest](../../crates/metroflow-rust/Cargo.toml)와 lockfile에 faer가 없으며,
검토한 경로는 FIFO event 처리·저장 표현·독립 indexed map이다. 이 변경에서 faer의
행렬 분해·선형 solve를 사용했다는 주장을 하지 않는다. 적용성 판단과 외부 조사
근거는 [REFERENCES.md](REFERENCES.md)에 별도로 남긴다. 이 파일은 초기 후보 설계
검토다. 그 문서의 lazy delay-law batches와 due-index 제안은 이번 구현으로 채택한
사항이 아니다. 실제 stage 구현은 원래 행을 보존하는 immutable blocks이며,
후보 설계의 기대효과를 구현·실측 결과로 가져오지 않는다.

## `27e426f`의 실제 세 도시 결과와 분류

세 입력은 원래 100,000 resident stock과 전체 달력을 유지했다. 각 실행 receipt의
candidate는 `27e426fc64452ae2492828653f94f2506b8881fc`, `source_dirty=false`다.

| 입력 | 마지막 유효 모의 시각 (s) | 벽시계 (s) | peak RSS (bytes) | 직접 관측한 차단 |
|---|---:|---:|---:|---|
| River weekday seed17 | 25,210 | 573.184 | 2,172,362,752 | journey stored/working owner quota |
| Coastal weekend seed41 | 32,650 | 279.530 | 2,422,263,808 | road entry interval split owner quota |
| Valley weekday seed7 | 25,600 | 131.853 | 2,066,145,280 | road entry interval split owner quota |

[CAMPAIGN.json](final_campaign/CAMPAIGN.json)과 각 run1 receipt에 마지막 유효 상태,
phase 진단·장부·source/binary identity가 보존돼 있다. 결과는 `BLOCKED_RESOURCE`이며,
후속 같은 후보의 반복·refinement는 `NOT_RUN_DEPENDENCY_BLOCKED`다. 세 도시의 24시간
정상 종료나 RSS OOM으로 바꾸어 보고하지 않는다.

**구현 분석에 근거한 해석:** River에서는 생성 추정량 5,674,574,036B를 실행 예산에서
계속 차감해 각 owner에 383,938,454B만 배정했다. 당시 journey 준비 scratch와 최초
stage 생성이 그 상한에 걸렸다. 낮은 RSS 자체가 교정의 충분한 근거는 아니다.
생성 뒤 해제되는 router/cache와 계속 보유하는 native 배열의 수명 차이, 고정 owner
분할에서 남는 예산을 다른 단계가 사용할 수 없는 구조가 코드에서 확인됐다는 것이
다음 accounting 교정의 근거다. 이는 실제 교통의 물리적 불가능성 증명이 아니다.

## `retained_capacity_v2`의 변경 범위

Constructor의 기존 `n×896` preflight와 물리 보고서의 `estimated_bytes`는 유지한다.
Runtime fixed reserve는 실제 owned Vec/String capacity, 고유 Arc allocation,
initial road, journey dense 4copy·service dense 6copy, 호출용 tag map,
worker/profile/service 준비 scratch와 제한된 관측 버퍼로 구성한다.
전체 accounting 예산 6GiB에서 이 reserve를 뺀 `T`를 하나의 shared dynamic pool로 쓴다.

Prepare, road proposal, journey finish는 함께 살아 있는 다른 owner의
input/current/candidate, event·sink 비용을 차감한 나머지를 해당 owner guard에
제공한다. 공개 road/journey ceilings는 더할 수 있는 별도 예약량이 아니다.
Capture/validation은 별도 전역 preflight를 하고, load는 road→service→journey
순서로 이미 decode한 owner를 다음 할당의 예산에서 차감한다.

추가 독립 검토에서 찾은 실패 경로도 포함한다. 검증 실패의 result를 버린 뒤
restore하여 dense 복사본을 추가로 살려두지 않으며, provisional Journey 후보의
commit 전에 같은 budget에서 checkpoint를 다시 읽고 검증할 headroom을 검사한다.
실패 시 이전 owner와 history 계상 cache를 복원한다. 순차 history decoder는
`sum(final storage) + max(one-history extra workspace)`를 사용한다. 모든 history의
서로 겹치지 않는 임시 peak를 합하는 것과 구분한다. 이 tightening은 row·prefix
expansion·codec의 변경이 아닌 동시 allocation 계상 변경이다.

새 binding은 `bounded_bytes_v1:retained_capacity_v2`와 전체 budget에 연결한다.
Worker 수와 단계별 임시 allowance는 scientific/resource identity에 넣지 않는다.
이전 고정분배 파일은 새 정책에서 무검증 재해석하지 않는다. 상세 포함·제외 범위와
최종 소스 검토는 [ROAD_STATIC_ACCOUNTING.md](ROAD_STATIC_ACCOUNTING.md),
[JOURNEY_STATIC_ACCOUNTING.md](JOURNEY_STATIC_ACCOUNTING.md),
[RUNTIME_BUDGET_REVIEW.md](RUNTIME_BUDGET_REVIEW.md)를 따른다.

이는 allocator 전체·Python frontend·임의로 추가 보관한 snapshot의 RSS를 정확히
상계하는 정리가 아니다. 8GiB 프로세스 주소공간 제한과 실제 RSS 측정은 계속
별도로 적용한다. 수요 축소, 질량 삭제, 시간 binning, 수치 허용오차 완화는 하지 않았다.

## 새 후보의 실제 검증 결과

최종 sequential-history accounting 소스는 [BUILD_BUDGET_SEQ_FINAL.log](BUILD_BUDGET_SEQ_FINAL.log)의
release 빌드 10.21s와 [TESTS_BUDGET_SEQ_FINAL.log](TESTS_BUDGET_SEQ_FINAL.log)의
251개 scoped 검사(9.53s)를 통과했다. 최종 manifest의 소스 45개가 현재 worktree의
SHA-256과 일치함을 다시 확인했다. 앞선 213/236 검사 또는 중간 R2 후보의 결과로
이 최종 결과를 대체하지 않았다.

| 항목 | 상태·근거 |
|---|---|
| 검증·campaign 후보 commit/tree SHA | commit `532effe32f90c20cf3cbc1de350d0e7267f52584`; tree `ffa7017a70733acf68dd24c506cb6c104cf5a99f` |
| 최종 source manifest / 실제 loaded binary SHA-256 | [SOURCE_MANIFEST_BUDGET_FINAL.json](SOURCE_MANIFEST_BUDGET_FINAL.json), 45 source files; binary `3e06969385dffdb9834c56d2cf0831e67e07e618df4f1f2169cff974aa9a3972` |
| 최종 scoped native·packet·PLAN 검사 | **251 passed**, 9.53s; 전체 저장소 CI는 아님 |
| 예산 실패 → 저장 → fresh load → 동일 시각 replay | 최종 251개 검사에 포함된 [70MiB 실패/복원 회귀](../../tests/v1/test_native_campaign_contract.py) 통과 |
| runtime budget 후보의 serial/parallel·legacy 호환 대조 | 실제 legacy 점유 구간 3회 report/checkpoint byte 일치; 최종 251개 검사에 [작은 byte-policy fixture의 1→4 worker restart](../../tests/v1/test_native_storage_policy.py) 포함. 새 대도시 parallel campaign은 미실행 |
| `runtime_budget_campaign` River 결과 | **BLOCKED_RESOURCE**, 마지막 유효 25,350s; wall 590.681s; peak RSS 2.596GiB; `checkpoint_working_budget_guard` |
| `runtime_budget_campaign` Coastal 결과 | **BLOCKED_RESOURCE**, 마지막 유효 32,660s; wall 273.304s; peak RSS 2.365GiB; `phase_working_budget_guard` |
| `runtime_budget_campaign` Valley 결과 | **BLOCKED_RESOURCE**, 마지막 유효 25,600s; wall 131.690s; peak RSS 1.969GiB; `phase_working_budget_guard` |
| 새 후보의 세 도시 × 3회 24h·재개·refinement | **BLOCKED**; 24h 완료 0/9회. 첫 실행 3회가 차단됐으며 후속 반복 6회·refinement 3회는 `NOT_RUN_DEPENDENCY_BLOCKED` |
| 게시 대상 branch | `v1/v03-acceptance-20261027`; 이 보고서와 실제 evidence는 위 source commit의 후속 commit으로 게시하며, 원격 head 확인은 최종 응답에 기록 |

새 실행은 위 commit으로 고정한 후보에서 시작했고, 세 receipt 모두 source clean과
동일한 실제 native binary를 기록한다. [CAMPAIGN.json](runtime_budget_campaign/CAMPAIGN.json)에
3회의 자원 중단과 9개의 dependent 미실행 기록이 보존돼 있다. River는 checkpoint
재로딩 headroom, Coastal은 road entry interval split, Valley는 packet interval
packing에서 동시 작업 예산을 넘었다. 세 번 모두 실제 peak RSS는 8GiB보다 낮았다.
현재 admission의 실패는 실제 RSS OOM이나 물리적 불가능성 증명이 아니다.
구체 수명식과 남은 행 증가는 [ACTUAL_BLOCKER_ANALYSIS.md](ACTUAL_BLOCKER_ANALYSIS.md)를 참조한다.

River의 실제 마지막 유효 checkpoint는 새 프로세스에서 로드했고, 보고서와 재저장한
checkpoint bytes가 원본과 같았다. 입력/roundtrip SHA-256은
`e179f3b9b5b9081a8adb121e51761514654743a8e8bbe4166691dd04cc46425e`다.
재로딩으로 물리 행은 그대로지만 Vec capacity가 달라져 추가 한 tick인 25,360s까지
진행했다. campaign의 마지막 유효 시각 25,350s와 이 별도 진단을 섞지 않는다.
[실제 복구 결과](river_fresh_recovery.json), [진단 코드](VERIFY_RECOVERY.py),
[로컬 checkpoint 목록](LOCAL_CHECKPOINTS.json)에 근거를 보존한다. 이는 full-day
replay 수용시험을 대체하지 않는다. 새로운 표현과 더 정밀한 workspace 계상으로
줄일 여지가 남아 있으나, 현재 후보의 24시간 수용은 여전히 차단 상태다.

## 유지하는 완료 기준

V03은 세 도시 각각 3회의 실제 86,400s 실행, 동일 후보의 checkpoint 재개,
짧은 matched refined-dt 대조, 일일 장부와 unfinished 분리, case당 7,200s wall·8GiB
peak RSS를 요구한다. 모의 시각 24시간은 벽시계 24시간을 기다리라는 뜻이 아니다.
짧은 prefix, native 테스트 개수, 개선된 저장식은 이 gate의 대체물이 아니다.

실제 캠페인 차단에 따라 DAG **19/21(90.5%)**와 V03 미수용을 유지한다. 전체 CI·통합·main merge와
release는 이번 한정 실행과 분리된 사용자 심사 범위다. 새로운 실행이 차단되면
정확한 phase·예산·마지막 유효 상태를 기록하고 모델·수치·구현·환경·자원 실패를
구분해야 한다.
