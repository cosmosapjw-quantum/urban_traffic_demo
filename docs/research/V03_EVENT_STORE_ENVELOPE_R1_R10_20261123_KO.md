# MetroFlow V03 · Persistent events and moment envelopes · R1/C1–R10/C10

## R1/C1 · 재개 기준과 실제 목표 (2026-11-23 KST)

기준 commit은 3c8650abc8b556387e7f24ce84b1e676e6e8b141이며 원격 branch와 일치를 확인했다. 새 branch는 research/v03-event-store-moment-envelope-20261123이다. 기존 브랜치와 4.68GB checkpoint를 보존한다.

원본 Valley weekday seed7, 주민100000, dt10s, 8GiB RLIMIT_AS, 7200s/run, 86400s×3cities×3repeats의 수용 조건을 유지한다. PLAN.json v1.1.26은 19/21 scoped, 5/21 accepted, V03 직접 선행3/3, 원본 하루0/9다. 연구단계 커밋은 DAG 완료수에 더하지 않는다. 전체 저장소 CI와 main merge는 기존 사용자 정책에 따라 보류한다.

직전 결과는 t25720 원본 물리 상태의 저장·현재 native 전진재현·full-wire 독립복원·질량 장부 일치다. checkpoint bytes4677350066, SHA256447570b8721b17fa19edf159bc4c474cfd6ad41dc936ab0b0114d902e36f0bf9. 실제 파일은 이전 worktree의 artifacts/v03_age_loss_checkpoint_20261122/R6_original_100k_25710_off_requested_20s.final.bin이다. 다음t25730에서 transfer header reservation 요구4867627464B, allowance4867625327B로2137B 초과했다. 작은 초과는 이후tick 전체의 필요여유를 뜻하지 않으며 실제OOM/no-go 증거가 아니다.

### 이번 이론 목표

미세birth측도가 없어 기존 K(u)=sum m(w−u)+ 관측을 원도시에 그대로 적용할 수 없다는 의무를 구성적으로 다룬다. 실제 사용 가능한 질량m, birth 1차moment B, 명시적 age support[L,H]로 sharp stop-loss 하한·상한을 도출한다. 추가분포를 적합하지 않고 관측 가능한 정보로 지연/age envelope를 계산하며, support partition refinement에서의 단조성·수렴오차와 유한창검열을 연결한다. 내부passage/event 질량과 최종journey완료를 구분하고 전역적신규성은 주장하지 않는다.

### 이번 코드 목표

현재 road의 48B compact event pages를 whole-engine service.last_events까지 영속 전달하여 64B EventRow flatten allocation과 그 공존 peak를 제거한다. standalone/Python flat API와 MFWHOLE1 wire, 원래 f64 bits/order/None sentinel, registry wide fallback을 유지한다. 원본20,270,113행에서16B/row 차이는324321808B인 설계치며 descriptor·padding·live owner는 별도 계상한다. 임의credit이나 cap완화 없이 실제 원본t25730 완주와 저장/독립복원으로 판정한다.

### 10단계 실행 연결

| 단계 | 이론 산출 | 코드·실험 산출 |
|---|---|---|
| R1/C1 | 질문·원래계약 고정 | 기준source/checkpoint/worktree |
| R2/C2 | 원전·기존결과 대응 | 실제flatten/decoder 호출경로 |
| R3/C3 | sharp envelope 명제·가정 | 영속page API·bytepool 설계 |
| R4/C4 | 대표extremizer·판별계산 | 행동회귀·실행자원 준비 |
| R5/C5 | 증명·계산식 완결 | 관측기·compact service 구현 |
| R6/C6 | 독립 exact 검산 | Rust/Python·원본10s 실행 |
| R7/C7 | 실제관측 연결 | 유효checkpoint 기반20/40s 확장 |
| R8/C8 | 결과범위·실패재평가 | 새실제blocker에 대한 선택적수술 |
| R9/C9 | 재사용정리·계산계약 | 현재native3도시준비·정량준비도 |
| R10/C10 | 검토교정·다음의무 | 최종실험/ledger/원격게시 |

각 단계마다 별도 commit과 push 후 원격 SHA를 확인한다. 성공한 물리구간만 누적하고, 실패상태의 시계를 전진으로 세지 않는다. 장시간확장은10→20→40→80s 순서로 이전구간의 저장가능한 실제성공에 의존한다. 데이터·계산산출물은 해당 git branch에, 대용량bin/so는 로컬에 보존한다.

## R2/C2 · 원전·과거 실패와 실제 호출 경로

기존 이론의 blocker는 미세birth측도를 갖지 않은 native 집계에서 full K(u)를 유일하게 복원하려던 점이다. 이를 moment/support로 식별가능한 구간으로 바꾼다. 단순분포가정이나 평균원자화는 하지 않는다. Huang–Ziemba–Ben-Tal(1977), Operations Research25(2):315–325, https://pubsonline.informs.org/doi/10.1287/opre.25.2.315 는 convex expectation의 Jensen/Edmundson–Madansky bound와 smaller-support partition refinement를 명시한다. Pierre-Louis–Bayraksan–Morton(2011), https://www.informs-sim.org/wsc11papers/371.pdf §3.1 p4174 eq(2),(3)은 conditional Jensen lower와 endpoint upper의 실제 계산식을 제공한다. Madansky1959 DOI10.1214/aoms/1177706203은 metadata를 확인했으며 해당 DOI원문 접근은 실패했다. RAND 원저자1958P1418 초록 https://www.rand.org/pubs/papers/P1418.html 을 보완근거로 읽었다. 새 전역정리라는 주장은 하지 않는다.

Wolfram 독립계산에서 (u−L)(H−u)/(H−L) <= (H−L)/4 (L<u<H)가 True이며, support[0,4], mean2, mass1의 u={1,2,3}에서 (lower,upper)={(1,3/2),(0,1),(0,1/2)}를 얻었다. 기존first/second moment와 positive-part family는 유지하되 point estimate 대신 bounds로 연결한다.

C2 소스 원자료: whole 실행은 road.propose_owned_step → materialize_event_after_road → ChunkedEvents.into_flat_checked → NativeServiceCore.last_events:Arc<Vec<EventRow>>다. road의 compact row는 이미48B이고 fourf64와 checked registry u32를 보존하지만, service 영속상태에서는64B flat row로 되돌린다. 새수술은 이 flatten allocation과 page/flat의 동시존재를 제거하는 것이다. read_state의 독립 decoded Vec도 같은영속page로 직접 읽는다. standalone/Python flat ABI는 보존한다.

과거R10 destination ID압축의32B는 해당임시벡터만 줄였으며 t25730을 해소하지 못했다. 더 이상의 근거없는 고정credit은 채택하지 않는다. 2026-11-17의 '24h 불가' 문구는 당시표현·측정에 대한 engineering extrapolation으로 보존하며 보편적 no-go로 재사용하지 않는다. 이번 저장표현수술도 full-day 성공은 실제9runs로만 판정한다.

준비도는 기존19/21 scoped, 직접선행3/3, originalday0/9다. 새native는 아직 구현·빌드하지 않았으므로 이 단계에서 새로운 실행성공을 주장하지 않는다.

## R3/C3 · 명제와 계산·저장 계약 채택

유한 positive age measure의 질량m>0, 1차moment A, support[L,H], 0<=L<=H를 가정한다. A in[mL,mH]는 필수이며 L=H이면 해당원자만 가능하다. H>L에 대해

```math
K_lower(u) = max(A-mu,0),
K_upper(u) = [(mH-A)(L-u)+ + (A-mL)(H-u)+]/(H-L).
```

K_lower<=K<=K_upper는 Jensen와 convex chord로 성립한다. mean원자는 모든threshold의lower를, endpoint의 질량(mH−A)/(H−L), (A−mL)/(H−L)는 모든threshold의upper를 동시에 달성한다. sharp의 가능집합은 mass/mean/support만 지정한 모든 positive measures이며 추가적인 숨은birth calendar 조건의sharp를 주장하지 않는다. 단위m은vehicle, A와K는vehicle·s다.

실제질량·moment를 관측한 support sub-bins으로 나누면 lower는 증가하고 upper는 감소한다. 균일gap상한 Σm_j(H_j−L_j)/4에서 실제 support분할 폭이0으로가면 K envelope는 균일수렴한다. 집계평균을 임의로 쪼개는 것은 refinement가 아니다. K envelope를 직접 미분해 CDF bound라고 주장하지 않고, h>0의 유한차분으로 strict tail의 안전한 bound를 만든다.

공통관측시각t의 native event-incidence 질량과 birthmoment B는 A=m*t−B로 연결한다. 같은차량의여러passage가 포함될 수 있으므로 unique-source나최종journey완료 통계로 해석하지 않는다. birth support는 caller의 실제source 근거가 필요하며 평균값으로 추정하지 않는다. Fraction oracle는 정확 계산, native f64는 별도 rounding error 상태를 표시한다.

C3 저장설계: whole path의 ChunkedEvents를 Arc로 service에 그대로 보관하고 순서보존 iter로 validate/write/report한다. decoder도 compact 가능한registry에서 직접page로읽고 wide registry에서는64B를보존한다. page payload뿐 아니라 descriptors·allocationpadding·동시live owner를 모두 계상한다. call-input/current/candidate의 실제Arcidentity만 공유로 처리한다. Python/standalone flatAPI는 경계에서만 명시materialize한다. native observer hook은 immutable snapshot의 행수/actualstorage/mass/B/agefirst를 O(1) 추가메모리로 집계한다.

원본 source/binary bytes를 바꾸기 전 behavior regression을 기록한다. missing API/import/compiler symbol 실패는 행동RED로 세지 않는다. 원본 t25720 full-wire 재직렬화·질량장부를 먼저통과한 뒤10s,20s,40s를순차실행한다. library shared build target은 Rust worker 단독사용 후 부모에게반환한다.

## R4/C4 · 구성 예제·반례와 실행 준비

질량1, support[0,4], mean2를 고정하면 mean원자δ2와 endpoint혼합(δ0+δ4)/2가 같은정보를가지나 K(2)는각각0과1이다. 기존처럼 하나를 추정값으로 택하는 대신 [0,1]을 반환하면 두가능성모두포괄하고 sharp하다. 동일support에서 width/4=1은 실제달성되며 오차상한을임의로줄일수없다. 평균만 재분할해δ2로만드는방식은입력정보를추가하지않고가능집합을바꾸므로채택하지않는다. 검열source와CDF는 K bound의미분이아닌검증가능한유한차분/positive-part상계로연결한다.

C4 실제 behavior regression: 서비스checkpoint8193행의 기존write→read 결과retained524480B=64×8193+128B가 행당56B미만이라는목표를위반했다. Rust assertion1failed, exit101을 C5_rust_red.log에보존했다. 초기 잘못된 exact-filter의0test결과는RED로세지않았다. 다음stage는같은실제load/restore/serialize동작에서compact저장량과wirebits를확인한다.

부모실행기 tools/research/v03_event_store_horizon_20261123.py를준비하고 py_compile을통과했다. 정확히pinned된원본t25720 receipt/hash만cross-native진입점으로사용하고, 시작시full-wire와원장일치를재검사한다. 각tick10s를원래순서로전진하며완료후상태만저장한다. duration0은RESTORE_ONLY_VERIFIED로기록하고물리실행으로세지않는다. 초기/최종event-incidence moment관측은실행성공과분리되어관측hook실패가물리결과로오인되지않는다.

현재관측host에는50GiB여유disk가있고거대기존bin을복사하지않는다. 새실험은한프로세스씩원래8GiB캡안에서수행한다. 원본day0/9, DAG19/21을유지한다. 새native물리실험은R5 source-clean release빌드후시작한다.

## R5/C5 · 이론·영속 event 구현 완료

이론 원문은 V03_AGE_MOMENT_ENVELOPE_THEORY_20261123.md, exact oracle는 src/metroflow/v1/age_moment_envelope.py다. sharp all-threshold bound, 최대gap/진짜nested refinement, censor/secantCDF, commonclock birthmoment사상을 증명했다. 10개 저장된 Python검사에서2790 exact envelope와2520 strict-tail/CDF 배치를통과했다. 비중첩partition을nested라고구성한초기fixture오류는 수정하고 실제반례로보존했으며 생산코드오류로재명명하지않았다.

Rust whole-engine은 ChunkedEvents를 service.last_events의Arc로직접넘긴다. Flat EventRow의추가할당을만들지않고, write_state는원래field/order를iter로직렬화한다. decoder는wire행수에맞춰마지막page를정확히예약하며registry가넓으면wide64B경로를유지한다. 전체descriptor성장transient·pagepadding·carrier·독립decodedstore를보수적으로계상한다. 동일8193행 behavior회귀는수정후통과했고, 전체workspace library는231passed/0failed/2ignored다. 기존unused/dead-code warnings는남아있다. 중간3개검사실패와정확한기대값교정은 C5_native_verification_notes.md에보존했다.

원래4f64 bits/order/None sentinel,4096page경계,wideindex,옛snapshot불변,cap−1거절을검사했다. 작은부분충전page에서는compact가exact-flat보다클수있으므로항상절감한다는주장은하지않는다. 실제20m행저장량과원본tick은다음실험으로판정한다.

Native service_event_moment_summary(state)는common snapshot시각에서M=sum m,B=sum birthmoment,A=sum(mt−B)를O(1)추가메모리로읽는다. Neumaier중앙값과각binary64연산의outward interval을반환하며과거solver오차나실제숨은분포를certify한다고주장하지않는다. 부모adapter tools/research/v03_event_age_observation_20261123.py는원본nonnegativeclock birth support조건아래추가배열없이이자료를Fraction bound로연결한다. exactfixture m2,A4,t4,u2에서 K∈[0,2],mean2를확인했다.

R5에서는소스/단위·과학검사까지만완료했다. 원본물리실행은clean commit의release .so를빌드한뒤수행한다. canonical19/21,originalday0/9유지.

## R6/C6 · 독립 이론 검증과 실제 원도시 실패 재현

독립 검토자는 저자의 pytest와 별도로 명제·extremizer·gap·nested refinement·strict-tail/CDF·censor·시간 원점 이동을 직접 유도했다. 80개 비영 분포에서 envelope 1,440건, CDF 8,640건, censor 8,640건, refinement 720건 등을 Fraction으로 확인했다. 구체적 수정 finding은 0건이며 범위와 fixture 입력 오류 교정은 R6_independent_moment_review.md에 보존했다. 당시 메모리 실행의 관측 출력 기록과 재현 recipe를 구분했으며 원본 로그 파일이 있다고 주장하지 않는다.

R5 source-clean release 빌드는 성공했다. Source SHA는 620e85a5c7146de5373a11bd4e637f59de9d463d04a9f293250ce6e575dcf3e7, native SHA는 734a8d320a1a1e633014c99108ec03ed5f52cb1407b26a659e1e150e8b480c4a다. 빌드 뒤 provenance helper의 잘못된 import 경로 1회 실패는 빌드 실패와 구분해 R6_release_identity.json에 기록하고 정확한 tools.run_v1_local_acceptance 경로로 교정했다.

원본 Valley 100k, dt10s, 8GiB cap에서 t25720의 4,677,350,066B checkpoint를 새 native로 읽고 전체 wire SHA와 vehicles/persons/cargo 질량 장부 일치를 확인했다. 이어 요청한 10s는 t25730에서 아래 실제 guard로 중단됐다.

```text
phase=transfer candidates
required_bytes=4867625496
budget_bytes=4867625327
excess_bytes=169
status=BLOCKED_RESOURCE
valid_advanced_duration_s=0
wall_total_s=103.73899049402098
peak_rss_bytes=4713345024
```

따라서 persistent event 구현의 단위검사 성공을 원본 tick 성공으로 승격하지 않는다. 예전 transfer-header guard와 비교해 phase는 바뀌었지만 road budget 숫자가 동일하다. 다음 단계는 실제 소유 관계와 phase pool 전달을 추적하여 표현 절감이 어느 시점에 반영되는지 규명한다. 임의 credit이나 원래 cap 완화는 사용하지 않는다.

R6 native 관측은 wrapper DriverState를 전달한 연결 오류로 initial/final 모두 OBSERVER_ERROR였다. 실패 receipt를 보존했고 adapter 결과도 NOT_OBSERVED다. runner의 두 인자를 state.runtime_state로 수정하고 py_compile을 통과했다. 수정된 연결의 실제 관측 검증은 다음 실행에서 한다. 현재 full-day0/9, canonical scoped19/21은 변하지 않는다.

## R7/C7 · 원도시 모멘트 연결과 blocker 성분 측정

관측 wrapper 수정 후 실제 원본 t25720을 복원하고 record-only 진단을 수행했다. mode는 명시적 `--diagnostic-trace`와 `METROFLOW_BUDGET_TRACE=record`로 일치시킨다. guard/cap/수요/물리식은 유지하며 `observe` bypass는 쓰지 않는다. receipt는 diagnostic_only=true와 실제 runner SHA를 기록한다. 이 진단을 uninstrumented 성능이나 새 물리 전진으로 세지 않는다. t25730 transfer 후보에서 다시 막혔고 valid advance=0, 총91.317s였다.

Native hook은 실제20,270,113행을 추가 대형 배열 없이 관측했다. retained event storage=973,795,840B, 기존 exact-flat 비용64×20,270,113+128=1,297,287,360B 대비323,491,520B 절감이다. M=289.71353127054977 vehicle-incidence, A=92,384.13792878596 vehicle·s다. stored-f64 관측 산술 enclosure는 M∈[289.7135308459402,289.7135316739664], A∈[92384.13779576562,92384.13805545286]. 이는 과거 solver roundoff의 enclosure가 아니다.

### 실제 source로 support 강화

R7_birth_support_provenance.md는 empty initial road/queues/events, 고정 inventory의 최초 버스 출발21600s, private weekday 최초25200s, freight service 최초36000s, 별도 direct service cars가 빈 목록임을 추적한다. 초기 passenger waiting reservoir는 birth0의 road 차량이 아니다. 따라서 선언된 exact model의 event birth support는 [21600,T]이고, T25720에서 age support는 [0,4120]이다. 평균에서 birth 하한을 역추론하지 않는다. retained-part의 절대1e-8 moment slack과 decoder의 제한된 검사를 명시해 수치적 역사 오차 인증과 구분했다.

이 source 정보로 universal gap 상계는 M×25720/4에서 M×4120/4로 좁아진다(103/643배, 약6.24배 개선). 실제 첫 모멘트는 강화된 support와 양립한다. 관측 평균 age의 산술 구간은 [318.8809899971519,318.88099180489985]s다.

| threshold u(s) | K 하한(vehicle·s) | support[0,4120] 상한 | support[0,25720] 상한 |
|---|---:|---:|---:|
| 0 | 92384.137796 | 92384.138055 | 92384.138055 |
| 60 | 75001.325895 | 91038.737987 | 92168.622959 |
| 300 | 5470.078294 | 85657.137712 | 91306.562573 |
| 600 | 0 | 78930.137368 | 90228.987090 |
| 1800 | 0 | 52022.135992 | 85918.685159 |
| 3600 | 0 | 11660.133929 | 79453.232262 |

R7_native_moment_envelope_21600.json과 _0.json은 exact Fraction 및 approximate 수치를 모두 보존한다. 현재 정보에서 q>0의 tail에는 a≥q ⇒ a/q≥1을 적분해 P_incidence(a≥q)≤min(1,A/(Mq))를 함께 사용한다. q>H이면0이다. M,A interval에서는 A_high/(M_low q)가 안전하다. q3900s에서 상계0.08176435687305124를 얻었다. K(u)/(q−u)의 임의 threshold 결과만 선택해 더 약한 값을 최선이라고 제시하지 않는다. 이 Markov 결과는 기존 이론의 직접 corollary이고 신규 일반정리라는 주장은 없다. Unique vehicle 또는 최종 journey 완료·검열 분포로 해석하지 않는다.

### 실제 메모리 성분과 다음 수술

동일한 road budget4867625327B는 event 절감 누락의 증거가 아니었다. journey 비용을 먼저 pool에서 빼고 event 비용은 required 쪽에 더하는 구조다. 실제 진단의 초과점 required4867733760B는 base1901806568 + event1772443240 + incoming925609136 + source diagnostics267874816 등으로 구성된다. 원래 guard와 record 진단의 exact 초과 bytes는 다르므로 동일 성능 표본으로 취급하지 않는다. C8은 원래 call-input/committed/third-owner의 실제 Arc와 수명을 추적해 보수적 중복 비용을 구분한다. 관측한169B에 맞춘 임의 credit은 사용하지 않는다.

## R8/C8 · 실제 소유 관계 수술과 과거 계상 교정

현재 후보는 `v1_road.rs`에서만 frozen queue 소유 관계를 교정한다. prediction은 immutable source의 PacketParts를 Arc clone하고 out.cells의 packet 목록은 비어 있다. readiness가 정확히 +∞인 queue는 모든 유한 ordinary/compensated event clock의 heads에서 제외되어 served/remainder 경로에 들어가지 않는다. 마지막에 동일 payload를 survivor로 이동한다. 따라서 source↔working candidate의 실제 pointer 일치 backing만 distinct(layout,Arc pointer)로 한 번 계상한다. 별개 allocation의 같은 수치나 단순 refcount는 근거로 쓰지 않는다. Packet/Vec shell과 allocator metadata는 계속 계상하고 census 자체의 requested/actual capacity도 credit 적용 전에 검사·해제한다.

별도로 기존 source/committed 공유 규칙의 자기 비교를 원래 restore-time witness와 clock 일치로 제한했다. 실제 이전 tick의 credit101376B가 다음 tick에도 살아남던 행동 오류를 1개 실행/1개 실패(exit101)로 재현했다. 수정 후 original input proof가 만료된 tick에는 해당 credit을 주지 않는다. 이 변경은 작은 실제 오류 교정이며 full multi-tick memory theorem을 주장하지 않는다.

6개 bounded 검사와 workspace library237passed/0failed/2ignored를 통과했다. full tick의 event f64 bits/order, 원래 input 불변, uncapped reference와 candidate wire equality, survivor Arc identity, 중복 SharedKeys, wide registry, 독립 allocation 거절, census cap/정확경계+1B 거절을 포함한다. 부모는 실제 prediction→finite-clock 제외→survivor 이동 경로와 전체 diff를 확인했다. 초기에 test constructor3곳이 새 필드를 빠뜨린 E0063 compile 실패는 behavior RED와 구분해 보존했다. 상세 근거는 C8_native_ownership_verification.md 및 C8_rust_*.log다.

이론 판정은 sharp moment/support envelope와 진짜 분할 refinement를 derived/literature-supported로, exact oracle를 implementation-verified로, 실제 원도시값을 conditional numerically-checked로 유지한다. 최초birth21600s support는 명시적 원본 source에 근거한 exact-model 전제다. 과거 solver 오차와 unique final-journey 완료 측도는 별도 미완료 의무다. 이전 실패에서 full-day no-go를 도출하지 않는다.

이 source freeze commit은 다음 원본 실행의 identity를 고정하기 위한 중간 게시다. 실제 frozen 절감량·t25730 통과·실행 구간 증가는 아직 주장하지 않는다. release 빌드 뒤 trace-off로 확인하고 R8 결과를 추가 게시한다.

### R8a 원본 결과와 추가 수술 결정

Source0ee8b70a6dff332153571c4e77c69f27086aefd317976cf029b00572d4fa3c14, native e4d6f6d88ad36aca588ce62e5bdee6386ab583e0c2202b8ea8530120f09f0bf1에서 t25720 전체 wire/장부 복원은 통과했다. 그러나 요청10s는 `transfer header reservation: required_bytes=4867627752, budget_bytes=4867625327`에서 중단됐다. valid advance0s, 총116.704s, peak약4.891GiB다. frozen 수술의 unit 통과와 stage 이동만으로 실제 t25730 blocker가 해소됐다고 주장하지 않는다. R8_original_100k_25720_requested_10s.json에 실패를 보존한다.

전체 phase 예산을 다시 추적했다. 원래 acceptance CLI는 native 내부6GiB와 process8GiB를 구분한다. 내부6GiB 중 fixed reserve는 약653MB, shared dynamic pool은약5.789GB다. 이 원래 두 cap과 driver identity는 그대로 유지한다. fixed reserve 자체를 임의로 줄이지 않는다.

두 가지 직접적인 큰 소유 중복을 병렬로 교정한다. 첫째, road serviced incoming의 mass/birth/start/end는 이미 저장된 event의 동일 f64 값을 중복 보관한다. event가 모든 incoming 소비보다 오래 살아 있는 경로에 checked event_index+offset 참조 저장을 적용하고 pending/direct/noninterval/wide fallback은 유지한다. 둘째, road 단계에서 original input/current/pending Journey가 모두 구체적으로 알려져 있는데도3×max를 예약하는 부분을 실제 owner 합과 pointer-verified StageQueue payload 중복으로 교정한다. census의 실제 임시 저장은 먼저 검사하며 history와 dense/metadata를 임의로 credit하지 않는다. 이 수정은2425B 초과에 맞춘 보정값과 무관하다. 구현과 실제 원본 실행 결과는 아래에 별도 기록한다.

### R8b/c 구현·통합 검증 완료, 원본 재실행 준비

Serviced incoming은 event_index+offset의8B 참조이고 Mark16B는 그대로다. 기존40B Part+16B Mark에서24B로 바뀌므로 서비스 행의 실제 payload32B를 제거한다. pending은40B 원본 spill+8B 순서 참조+16B Mark이며 추가8B를 숨기지 않고 계상한다. 현재 event에 실제 append된 index만 사용하고 네 f64 bits, source FIFO, offset을 보존한다. view가 incoming과events를 함께 빌리므로 읽는 동안 data가 살아 있으며 Weak token은 다른 store 연결만 거절한다. 별도 token Arc/control/padding을 store actual/decode/append 비용 모두에 추가했다. 따라서 R7의 이전 binary 저장량과 새 binary의 고정 shell 크기를 동일시하지 않는다.

Road 전의 Journey 예약은 실제 original input/current/pending 합에서 두 쌍의 pointer-verified StageQueue row payload만 차감한다. History·dense·shell·registry는 유지한다. 원본 snapshot과 restore clone의 registry capacity 차이를 반영하고, census 전에는 모든 uncredited Journey와 실제 old road/event·physical offer·map 성장 scratch를 먼저 검사한다. 두 map은 순차로 생성·해제하므로 peak는 max다. 참조가 없으면 기존3×max로 돌아간다. 1-entry HashMap 최소 capacity를 빠뜨린 중간 상계196B<actual230B 오류는264B로 교정했으며 원래 cap을 바꾸지 않았다.

기존10,000행 물리 transfer는 같은2,300,000B cap에서 required2,301,864B로 실패했고 새 참조 표현 후1s/10,000events를 완료했다. 7개 incoming 검사와7개 Journey 검사를 포함한 최종 workspace library는251passed/0failed/2ignored(exit0)다. 중간250pass/1fail은 위HashMap계상오류로 보존했다. Partial-service+pending wire 비교를 실제 실행하면서 발견한 uncapped descriptor guard 오류도 두 storage-only helper의 limit=None 경로에서 좁게 고쳤다. 물리검증과 capped조건은 유지했다.

부모는 변경된 전체 생산 diff, 실제 Part←Event bit 대입, event 수명, source별 page/Mark/direct spill 계상과 source/candidate/journey 경계를 확인했다. 최종 파일 SHA는 road5b982c4a771ba156141941ec1fdfa49fd3bd9b7723049fae0ad62352e409cf24, journeyc95c17aeada5d526f7dcf7ce2406ac68f70c6ba12b00aa70db46ccdcbff58a4a다. 상세 증거는 C8b_journey_road_reservation.md, C8c_native_event_reference_verification.md, C8b_rust_library_receipt.json이다. 다음 source-freeze push 후 현재 release의 원본10s를 실행한다. 성공 시20s와40s로 순차 확대한다.

### R8b 원본 결과: transfer 통과, checkpointability 경계 도달

Source freeze commit6aeb9a7a09700a0ca5a27a665abfbe38b4bf2b77에서 release 빌드는 성공했다. Candidate source76242d92122179ad3ac023e7116568ace83b7b7d5f944fb5dc267e7e552569bc, native66b1046a42396eaa694bc4eb183394d8f41eda8b0d53ebc9d081c47c2bc40645다. 원본 full-wire/장부는 다시 일치했고 actual native moment의 M/A/행수도 이전 관측과 일치했다. Identity token 고정비용152B를 포함한 event storage는973795992B다.

원본 t25720→25730 요청10s는 road_step89.442818868s, service_finish0.026496753s, journey_finish0.109081989s를 실제 수행한 뒤 joint checkpointability에서 거절됐다. required5943686424B > shared dynamic budget5789366831B, 초과154319593B다. 기존 transfer guard를 실제 통과한 증거지만 coupled commit은 rollback됐으므로 valid advance0s, final saved checkpoint 없음이다. 총wall152.15648579597473s, peakRSS4955889664B. 원래 native6GiB/process8GiB와 물리·입력은 유지했다. R8b_original_100k_25720_requested_10s.json/.log를 원자료로 보존한다.

같은 frozen binary의 record-only 실행을 별도로 시작해 checkpointability 구성항을 측정한다. guard bypass는 없으며 record 진단의 시간을 uninstrumented 성능으로 사용하지 않는다. Source provenance는 시작 시점에 고정되고 loaded binary는 교체하지 않는다. 진단이 checkpoint를 읽기 시작한 뒤 새 Rust source 분석/수정은 병행 가능하지만 새 binary 실행과 섞지 않는다. 다음 수정은 실패가 실제로 지목한 저장·독립복원 수명에 한정한다.

같은 freeze의 세 도시 calendar 준비는 WHOLE_CALENDAR_PREPARED3/3이며 simulated_s는 모두0이다. River5093765legs/63.370s/2172882944B, Coastal2449750legs/36.252s/1116143616B, Valley918450legs/21.200s/446832640B. R9_current_native_preparation 및 R9_current_source_readiness.json은 이 freeze의 역사적 준비 근거로 보존한다. 준비 실행은 R8b 계산과 겹쳤으므로 wall을 고립 성능 benchmark로 해석하지 않는다. 후속 production source가 바뀌면 최종 source의 준비를 새 경로로 다시 실행한다.

### R8d · 독립 decoder의 순차 수명 교정

Record-only 진단은 원래 uninstrumented 실패와 같은 required=5,943,686,424 B를 재현했다. 그 안에는 road decoder scratch 936,563,136 B와 decoded Journey 354,019,848 B가 동시에 들어 있었다. 실제 `NativeWholeEngine::load`는 road.read_state가 반환된 다음 service와 Journey를 읽고, 마지막에 decoded Bundle을 검증한다. Road decoder 임시 배열은 새 Journey가 만들어지기 전에 해제된다.

따라서 독립 복원 부분은 다음 두 실제 phase의 최댓값으로 계산한다. 모든 기존 input/current owner, 독립 decoded road, event decode upper, census 비용은 유지한다.

- road decode: decoded_road + max(road_decode_scratch, 65,536 B)
- Journey decode 및 최종 검증: decoded_road + decoded_journey + max(validation_scratch − call_binding_reserve, 65,536 B)

실제 frozen trace에서 후자의 추가 부분은 730,842,484 B이고 road scratch보다 작다. 동시에 input Journey는 clone의 cached 302,233,568 B 대신 실제 original snapshot의 302,394,480 B를 사용하여 누락된 registry 160,912 B를 올려 잡았다. 이 두 교정을 이전 48B trace에 적용하면 required=5,589,827,488 B, margin=199,539,343 B다. `R8d_decoder_phase_replay.json`은 이 산술 재평가이며 새 물리 실행 결과가 아니다. 새 40B 저장 후보에 대한 실제 요구량과 혼동하지 않는다.

4개 목표 검사 중 기존 코드에서 2개가 실패했고, 교정 후 4개 모두 통과했다. 실제 실패 trace 재현, 나중의 whole-validation이 peak인 경우, 독립 decoder에 candidate Arc credit을 주지 않는 조건, candidate phase가 더 큰 경우를 포함한다. 부모는 load 순서와 validate_bundle의 실제 할당 경로를 확인했다. 기존 road decoder envelope 자체의 모든 일반성을 새로 증명했다고 주장하지 않으며, 최종 후보의 원본 저장·독립 복원으로 해당 실행 상태를 별도로 검증한다.

### R8e · 정확한 40B event 저장 표현과 통합 검사

실제 원본 road registry는 1,586개 group을 사용한다. 네 f64를 유지한 채 tag:u32, source:u16, destination:u16으로 저장하고 destination65535를 None sentinel로 구별하면 40B 행이 된다. 범위를 넘는 행은 기존 48B compact 또는 64B wide 표현을 사용한다. 한 page가 나중에 넓은 ID를 만나면 그 page만 48B로 승격하고, 앞선 page·행 순서·logical index는 유지한다. 승격 시 동시에 살아 있는 기존 40B page, enum descriptor의 실제 크기, page padding과 identity token을 모두 계상한다.

실제 road proposal은 registry 길이 증거가 있을 때만 40B 상계를 쓴다. 파일을 읽기 전 service decoder의 row admission은 아직 payload 범위를 모르므로 generic 48B/64B와 한 page 승격 overlap을 유지한다. `decode_storage_upper_bytes`도 같은 값을 반환한다. 실제 retained 저장이 40B라는 이유만으로 향후 decoder가 더 작은 상한을 수용한다고 주장하지 않는다.

행동 RED 두 건은 기존 20,011행 decoded payload960,528B가 목표800,440B를 초과한 사례와, 10,000행 실제 proposal이 동일2,000,000B cap에서 required2,024,048B로 실패한 사례다. 수정 후 관련 범위 검사12개가 통과했고, decoder 수명 수정과 합친 최종 workspace library는261passed/0failed/2ignored(exit0)다. 두 IEEE 부호 zero와 subnormal, 네 f64 bit, ID 경계/None, mixed page 승격, incoming reference index, 실제 NativeServiceCore write→read→write wire equality, cap−1 거절을 검사했다.

첫 전체 library 실행의260pass/1fail은 과거 page 용량 assertion이 여전히48B를 기대한 오류였다(actual163840B, expected196608B). 실제40B 타입 크기로 기대값을 고쳤으며 실패 로그는 `C8e_rust_library_first_failure.log`로 보존했다. 무조건 통과하도록 assertion을 제거하지 않았다.

최종 source는 road SHA256 e25adb5d6c5d7bdb1202f6c529f5b7a3b1a23334f8f63b9fbb9780e81277db2d, journey SHA256 2d3397ff500fbb9e96a9ae04343f7638c037974bd652583761e84996009fff35다. 부모는 전체 production diff와 실제 load 순서·page 승격 수명·decoder admission 일치·검사 출력을 확인했다. 다음 게시로 source를 고정한 뒤 원본 물리 구간과 저장·재복원을 측정한다. 이 단위검사 결과 자체는 새 원도시 시간의 완료 근거가 아니다.

### R8e 실제 원본 성공: t25,730 저장과 독립 복원

Freeze commit `dd9686f1d537ed746425dd4a60d1f3e8fc302089`를 push/readback한 뒤 release를 빌드했다. 최종 candidate source는 `7e8b92020076e01283d532cf0e5825cb30167a533949e6bc6fd071f7b7d8cfe2`, native binary는 `baa3e4ce4f775df5cf3973e749357cc2d5a29cefbf1683355638a0de5b6a5606`다. 이전 t25,720 checkpoint의 전체 wire와 원장을 다시 확인했다. 그 시점의 actual event storage는 811,700,624 B로, 직전48B 후보973,795,992 B보다162,095,368 B 작다. Payload 계산값162,160,904 B에서 enum descriptor 증가65,536 B를 반영한 실제 차다. 기존 flat64B 대비 실제 차는485,586,736 B다.

원본 Valley100k의 t25,720→25,730 요청10s를 모두 완료했다. `PHYSICAL_TICK_VALID` 후 저장한 checkpoint는5,523,765,378 B이며 SHA256 `c8335535408e13266bb4b5f15b10d0854701e644421ae3e8183d7c468d9183c9`다. Tick wall93.59907537000254s, 전체 준비·입력 wire 확인·관측·최종 저장 포함183.13121596100973s, peakRSS4,599,537,664 B다. Original native6GiB/process8GiB를 유지했고 source/step/tolerance를 바꾸지 않았다. R8e_original_100k_25720_requested_10s.json이 원자료다.

별도 프로세스에서 이 새 checkpoint를 읽고 전체 wire SHA와 원장을 재확인했다. `R8e_original_100k_25730_requested_20s.log`의 초기 확인이 그 독립 복원 근거다. 이어진20s의 결과는 아래에 별도로 기록하며, 입력 복원 성공만으로20s를 완료했다고 세지 않는다. 이번 source가 clock0부터25,730까지 직접 적분했다는 주장은 없고, 역사적25,720을 입력으로 새로 완료한 시간은10s다.

새 t25,730 관측은24,322,678 event rows, M=296.0959150767445 vehicle-incidence, A=95,763.46799473118 vehicle·s다. 저장된 f64 관측의 산술 구간으로 mean age는[323.420428299876,323.4204304814221]s다. Exact-model birth≥21,600s에서 age support는[0,4,130]s다. K(3,600)의 조건부 상한은12,289.25862456 vehicle·s이며 broad birth≥0 support의82,364.77070178보다 좁다. Positive-age tail at3,900s는0.08292831550805696 이하로 제한된다. 이는 event-incidence 측도이며 unique/final journey와 과거 solver rounding 인증으로 확대하지 않는다. 두 support의 exact-rational 계산은 R8e_native_moment_envelope_25730_21600.json 및 _0.json에 보존했다.

### R8e 다음20s의 실제 실패와 남은 최소 표적

저장된25,730에서 요청한20s는 첫 다음 tick25,740의 `state validation workspace` guard에서 멈췄다. required5,435,700,144 B, 해당 road allowance5,297,903,399 B, 초과137,796,745 B다. valid advance0s, 총wall181.41707062599016s, peakRSS4,943,294,464 B, 새 checkpoint 없음이다. Native phase의 road_step112.460139715s 뒤 service/journey finish는 수행되지 않았다. 앞선25,730 저장 성공을 취소하지 않으며, 실패한25,740을 frontier에 더하지 않는다.

실제 `V1Road::check_state`의 이 guard는 `3 × max(candidate retained, retained_input) + 16 × rows + 32 × (packets + cells)`의 범용 상계를 사용한다. 이번 수술의 source-aware preproposal·checkpoint guard와 별개로 남아 있는 보수적 검사다. 이것을 실제 allocator OOM 또는 모델의 보편적 no-go로 재명명하지 않는다. 다음 최소 구현 표적은 standalone 검사 계약을 유지하면서, whole proposal에서 이미 알려진 input/current/candidate owner 및 validation scratch의 수명을 이 검사에 전달할 수 있는지 검증하는 것이다. 해당 식의 임의 차감이나 상한 완화는 이번에 수행하지 않았다.

원래 acceptance CLI는 native를 hourly boundary까지 한 번에 advance하고 시간별 checkpoint를 남긴다. 이번 frontier runner는 한 call마다 원래10s tick을 실행해 실패 직전 상태를 명확히 보존하는 진단 cadence다. 같은 dt/driver/물리를 유지하더라도 call-input owner 수명과 Python binding overhead는 같지 않다. 따라서 짧은 checkpoint continuation 실패를 현재 source의 clock0부터 실행한 hourly campaign 실패 또는24h 불가능성 증거로 확대하지 않는다. 원본 전체 campaign의 새 source 실행은 계속 별도 의무다.

현재 후보의 다중 tick 동작과 시간 확대는 엄격히 고정된 과거 원본25,650 checkpoint에서10s→20s→40s를 순차 실행하여 확인한다. 이 활동 구간 재실행은 frontier 증가와 별도 열에 기록하고, 마지막25,720 wire가 기존 SHA와 일치하는지도 확인한다. 다음 절에 실제 결과만 기록한다.

### R8/C8 완료 · 실제10→20→40s 재실행과 source 연결

동일한 최종 source/native에서 원본 Valley100k의 과거 활동 구간을 순차 실행했다. 각 행은 직전 행의 저장된 checkpoint를 새로운 프로세스에서 전체 wire/장부 확인 후 이어받는다. 원래 dt10s, native6GiB/process8GiB, 원본 source·driver·matrix를 유지했다.

| 시작→완료(s) | 요청/유효 물리시간(s) | 전체 wall(s) | Peak RSS(B) | 저장 checkpoint(B) |
|---|---:|---:|---:|---:|
| 25650→25660 | 10/10 | 52.925615 | 1,898,229,760 | 1,912,366,706 |
| 25660→25680 | 20/20 | 89.970393 | 2,401,353,728 | 2,552,318,466 |
| 25680→25720 | 40/40 | 279.527187 | 4,064,927,744 | 4,677,350,066 |

40s 행의 네 tick wall은37.0295630820,46.1926528010,59.1622603720,73.7348391770s였다. 모든 tick의 원장을 검사했고 마지막 상태를 저장했다. 전체 wall에는 도시 준비·독립 복원·전체 wire 확인·관측·최종 checkpoint 쓰기와 SHA 계산이 포함된다. 이 runtime 변화는 활동량과 상태량이 커지는 실제 시계 구간의 측정이며 고립된 알고리즘 speedup 비교가 아니다.

마지막25,720 checkpoint는4,677,350,066 B, SHA256 `447570b8721b17fa19edf159bc4c474cfd6ad41dc936ab0b0114d902e36f0bf9`로 이전 루프의 원본과 완전히 같은 크기/SHA이고 질량 장부도 일치한다. 이것은 앞서 새로25,730까지 전진한10s 실행의 입력과도 동일하다. 따라서 동일 최종 후보의70s 활동 구간 재검증과 그 byte-identical 입력에 연결되는10s frontier 확장이 성립한다. 하나의 uninterrupted80s 프로세스 또는 clock0부터의 현 후보 궤적이라고 주장하지 않는다.

최종 frontier25,730의5,523,765,378 B checkpoint는 다음20s 프로세스에서 독립 full-wire/장부 복원을 통과했다. 이 이미 완료된 복원 근거를 R10에서 재사용한다. 비교 영수증은 `R8e_replay_frontier_identity.json`, 전체 staircase는 `R8e_active_window_staircase.json`이다. R8은 실제25,730 blocker 해소·저장·독립 복원·점증 실행을 완료했고,25,740의 새로운 validation workspace guard는 남은 과제로 보존한다.
