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
