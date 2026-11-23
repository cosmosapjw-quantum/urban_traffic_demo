# C8c 독립 검토 — capture/save의 실제 immutable owner 계상

## 범위·판정·identity

2026-11-23, 검토자 `/root/c8_accounting_review`. 이번 검토는 새로 관측된 outer capture/save 실패에 대응하는 **C8c 변경 한 번**에 한정한다. 이전 C8 또는 이론의 재감사가 아니다. Isolated worktree `/home/cosmosapjw/worktrees/urban-traffic-v03-origin-capture-fix-20261123`에서 기준 `64173178d11229825efc553c441f6f90c7541979` 이후 세 native 파일의 diff, 연결된 clone/storage 함수, 실제 RED/GREEN·관련 library 로그를 읽었다. Main source/native 또는 실행 프로세스를 변경하지 않았다. Cargo/build/대규모 실행/commit/push도 수행하지 않았다.

**Primary verdict: NO_MATERIAL_FINDING — 지정된 C8c 변경에서 중대한 계상·수명·pointer-credit 결함을 발견하지 못했다.** 실제 release 규모의 저장·fresh load·재개 성공을 의미하지 않는다.

| 최종 동결 파일 | 직접 확인한 SHA256 |
|---|---|
| v1_road.rs | e6cc7627cb74497fb5a108897df860e8a3da5567c121ad73a601a3cf2346e617 |
| v1_journey.rs | bdae60a4f7110d21c148430e31e22c816c6fa7c27cb9ac056985ab7ffc7b6740 |
| v1_engine.rs | ddc0e42ea5396c64564a822a858b7fbd652be311a2082bfb908eefe0146287db |

## 실제 실패와 수정의 직접 연결

부모 worktree의 두 원 영수증을 직접 읽었다. `R8_final_frontier_25730_10s.json`은 내부 successful tick1/failed0 뒤 outer capture/validation에서 6,887,244,069>6,442,450,944B로 멈췄고, 정상 반환·최종 wire가 없어 새 유효 시간0s다. `R8_staircase/from_25690_duration_40.json`은 네 반환 tick과 장부 검사로25,730s까지40s를 계산했으나 SAVE_VALID_PREFIX에서6,513,265,473>6,442,450,944B로 멈췄다. 이 후자는 반환된 계산 prefix는 있지만 새 durable wire가 없다. 두 상태를 혼합하지 않았다.

기존 helper는 input/current/future clone을 구분하면서도 Journey의 immutable stage/history 복사를 전체 동적 owner로 중복 계상하고, 현재 input/current가 실제 공유하는 payload를 일부 반영하지 않았다. C8c는 `snapshot_source_owners` 한 경로에서 capture와 restore의 실제 clone source를 명시하고 관련 lifetime을 일관되게 계상한다. 자원 cap, 물리 수요·dt·FIFO·finite response, f64 연산, tolerance, serialization 또는 실패 snapshot 선택은 diff에서 바뀌지 않았다.

## Owner credit의 논증과 코드 대응

Input I, current C, exact clone target T를 두면 T=C가 capture이고 T=I가 restore다. Road 비용은 R(I)+R(C)+R(T)에서 새로 측정한 고유 live pair intersection과 exact target-clone의 고유 immutable payload만 뺀다. `snapshot_arc_witness`는 `(layout kind, Arc pointer)`를 키로 사용하며 값·clock·wire 유사성은 credit 근거가 아니다. 반복 SharedKeys는 한 owner pair마다 한 번만 빼고, packet/cell/pending/ledger container, latent map, Arc/control allowance와 실제 source의 spare capacity는 남긴다. Source clone의 Vec capacity가 더 작아질 수 있다는 이유로 원 input capacity를 줄이지 않는다.

한 allocation에 대한 input/current의 계상 multiplicity를 mI,mC라 하면 capture의 road payload 계상은

`mI + 2*mC - 1[both live] - 1[current live]`.

둘 다 참이면 최소3−2=1, current에만 있으면2*mC−1≥1, input에만 있으면mI≥1이다. Restore는 I/C를 교환한다. 따라서 실제 세 handle이 같은 payload를 참조할 때도 최소 한 payload가 남고, 중복 reference를 여러 번 보수 계상한 경우 이를 과하게 차감하지 않는다.

StageQueue의 derive Clone은 `Vec<Arc<Block>>`의 registry를 새로 만들고 immutable Block을 공유한다. Pair census는 모든 세 stage를 가로질러 실제 Arc intersection을 중복 없이 센다. Target-clone credit은 각 registry가 참조하는 row capacity만 빼므로, 개별 Block header/control·registry capacities는 계속 계상된다. 한 payload의 clone reference multiplicity를 상쇄한 뒤에도 `mI+mC-1[both live]≥1`이 남는다.

ReceiptHistory의 derive Clone은 `Option<Arc<Block>>`만 복제한다. 이 경로에서 새 history chain/row/expansion buffer가 만들어지지 않으므로 target의 전체 measured history dynamic bytes를 한 번 차감하는 것이 맞다. Outer `Vec<ReceiptHistory>`와 dense per-leg arrays는 기존 RuntimeStorage의 fixed dense reserve에 남는다. Input/current의 공통 history prefix는 추가로 차감하지 않는다.

Service checkpoint/rollback의 clone은 `Arc<ChunkedEvents>`를 복제한다. 따라서 E(I)+E(C)로 시작하고 실제 `Arc::ptr_eq` 및 같은 measured storage가 확인된 pair만 한 번 차감한다. Equal-valued 별도 event Arc에는 credit0이다. Future independent decoder에는 이 source witness를 사용하지 않는다.

독립 `C8c_independent_owner_arithmetic.py/.json`을 실행해 owner multiplicity0…4 및 두 clone target의 **48개 구성**에서 위 road/stage/history 부등식을 확인했다(exit0). 이는 설명된 일반 정수 논증의 유한 보조 검산이며 native behavioral test나 물리 실행으로 세지 않는다.

## Census·clone·검증 수명

새 pointer table 전에는 fixed base+call binding+아직 살아 있는 두 owner의 무공유 합+max(road table upper, stage table growth upper)를 먼저 admission한다. 미래 clone이나 아직 얻지 않은 pair credit으로 census를 승인하지 않는다. Road HashMap은 source backing occurrence 수로 한 번 reserve하고 실제 capacity를 upper와 비교한다. Stage census는 기존 old+new table growth allowance를 보존한다. 두 table은 순차 생성·해제되고 어떤 table도 미래 clone/whole-bundle validation까지 남지 않으므로 phase max를 사용하는 것이 맞다.

Final required는 census의 전체 요구량과 actual source/target-clone owner + unchanged validation/call-binding phase 중 큰 값이다. Metadata container의 independent clone은 source retained-size의 추가 owner 항에 남는다. `git diff --check`를 내가 직접 실행해 exit0을 확인했다.

HashMap bounds는 프로젝트가 사용하는 현재 native layout/std 구조 계상이며 allocator 독립적 RSS 정리가 아니다. 원 retained-size accessor의 기존 내부 진단 allocation을 이번 수정이 모두 재설계했다고 주장하지 않는다. 8GiB process 제한과 실제 peak RSS·6GiB 구조 계상 수용은 그대로 별도 조건이다.

## Fresh load에서의 연결과 남은 조건

Input=None인 독립 decoded-bundle validation은 기존 공식과 gate를 그대로 사용한다. Load는 road→service→Journey decode, bundle admission/validation 뒤 `restore(&state)`를 수행한다. 이때 decoded Bundle은 이제 실제 input owner이고, constructor/current owner와의 관계를 새 live pointer witness로 조사한다. 처음부터 hypothetical decoded state를 기존 current payload와 공유한다고 가정하지 않는다. Restore의 input/current/clone-target container 및 새 census는 그 실제 경계에서 다시 admission한다. Standalone·unknown-source의 기존 fallback도 유지된다.

따라서 실제 load→restore→반환 경로는 별도로 guarded 상태다. 이번 검토는 기존 fresh-checkpointability 사전식 하나만으로 모든 후속 census/restore가 자동 승인된다는 더 강한 충분성 정리를 새로 증명하지 않는다. 실제 전체 크기 checkpoint를 저장한 뒤 fresh runtime에서 마지막 restore와 반환 validation까지 성공하는 증거가 필요하다. 같은 엔진43,200s resume도 별도 V03 의무다.

## 실제 검증 로그 확인

처음 `C8c_RED*` 이름의 세 fixture construction 오류는 behavioral RED가 아니다. 실제 크레딧은 수정된 유효 fixture와 `C8c_behavioral_RED` → `C8c_behavioral_GREEN`만 사용한다.

| 실제 경로 | 유지한 cap[B] | 수정 전 실제 결과 | 수정 후 실제 결과 |
|---|---:|---|---|
| Native zero-step advance: restore/capture/whole validation | 84,594,070 | required84,991,238로 거절 | 같은 fixture/cap에서 통과 |
| Native save: restore admission 포함 | 84,397,174 | required84,991,166로 거절 | 통과; 전체1,049,076B wire 동일 |

Fixture에는8,192 real road tags, 실제 characteristic outflow events,4,096 stage rows와 nonempty history가 있으며 whole-bundle ledger를 먼저 검증한다. Zero-step fixture는 capture 동작 검증이지 새로운 physical progress가 아니다. Wire 비교는 수정 runtime의 높은 cap과 유지된 bounded cap 사이의 전체 바이트 비교이며, 미실행 cross-native 대규모 동치로 확대하지 않는다.

직접 읽어 확인한 저자 결과는 behavioral2FAIL(exit101)→2PASS(exit0), scoped7PASS(exit0), final library **292 passed,0 failed,2 ignored,exit0**이다. 추가 scoped fixtures는 실제 clock 변경 뒤 살아 있는 pointer intersection, 독립 같은 값의 owner credit0, census preflight cap−1 거절, unknown-source floor, input spare capacity, repeated SharedKeys의 unique credit을 다룬다. 이 native 검사는 저자가 실행했으며 내가 재실행한 것으로 합산하지 않는다.

## 종료·원 동기 watchdog

새 finding 또는 코드 수정 요구는 없다. 이 독립 검토는 여기서 종료하며 broad runtime audit, 기존 이론 심사, 추가 실험 행렬을 시작하지 않는다. 실제40s durable retry, frontier, 통합 final native의 fresh restore, original-hourly의 별도 Journey budget 실패는 부모의 실제 결과로 판정해야 한다. 과거의 내부 성공 tick과 snapshot recovery를 정상 반환·저장·재개 성공으로 승격하지 않는다.

Watchdog: **ALIGNED_WITH_OPEN_OBLIGATION**. Exact immutable state와 원래100k 도시의 day/replay/recovery 목표를 보존하는 실행 수정이다. 원 교통·routing 과학의 배경 이론 업그레이드와 별개이며, 이것만으로 새 V03 노드·24h 실행·물리 시간 완료를 부여하지 않는다.
