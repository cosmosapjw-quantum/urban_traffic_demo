# MetroFlow causal FIFO: independent bounded review

## 정규화한 대상과 최종 판정

**Primary verdict: proved as written.** 이 판정의 대상은 아래에 정규화한 **최종 문서의 제한된 수학 명제 묶음**이다. 고정된 homogeneous source head의 실수 산술 RC, 고정 질량 분할의 RB, 공통 속도 아래의 eligibility, 고정 서비스 기회의 국소 안정성을 뜻한다. 전체 MetroFlow 네트워크 안정성, binary64 collapsed cursor의 byte identity, 24시간 V03 수용을 뜻하지 않는다.

연결된 production 변경에 대해서는 **source inspection 및 명시한 유한 범위에서 implementation-verified**로 판정한다. 이 변경은 연속하는 이벤트의 동일한 시각 쌍을 공유하는 표현 변경이다. RC rank cursor를 production 물리에 통합한 변경은 아니다. 아래의 메타데이터 계상 finding은 같은 검토 과정에서 수정됐고, 수정 후 경계 테스트를 독립 재실행했다.

검토자는 원시 정의와 코드에서 중요한 함의를 다시 유도했다. 처음 제출된 문서의 판정은 `correct only after a stated restriction`이었으며, 수정한 원본의 오류를 삭제하거나 초기 증거를 최종 증거로 바꾸지 않는다. 최종 문서에서 필요한 제한을 확인한 후 위 판정으로 좁혀 갱신했다.

### RC: 한 source head의 비례 서비스

유한한 고정 행 집합에 대해 질량 \(m_j>0\), birth first moment \(b_j\ge0\), 고정된 ordered keys와 entry endpoints를 둔다. \(M=\sum_jm_j>0\). 비음수 서비스량 \(d_1,\ldots,d_K\)에 대해 \(Q_k=\sum_{\ell\le k}d_\ell\le M\)이며, 잔량이 0이 되면 종료한다. \(f_k=d_k/(M-Q_{k-1})\)로 모든 행을 동일하게 서비스할 때

\[
m_j^{(k)}=m_j(1-Q_k/M),\qquad
b_j^{(k)}=b_j(1-Q_k/M),
\]

\[
\Delta m_j^{(k)}=m_jd_k/M,\qquad
\Delta b_j^{(k)}=b_jd_k/M.
\]

독립 유도의 핵심은 \(1-f_k=(M-Q_k)/(M-Q_{k-1})\)의 곱이 telescoping한다는 점이다. 따라서 고정된 label/class/person conversion 등 모든 고정 선형 첨부량도 보존된다. source 재혼합이나 route advancement 이후에는 새로운 source 정의가 필요하다.

0 질량 행으로 확장할 때는 birth도 0이어야 하며, native의 `mass > 0` 필터와 shape-preserving algebraic view를 구분해야 한다. 최종 문서는 이를 명시한다. 이 명제는 실수·유리수 산술 명제이며, 반복 binary64 곱을 단일 scale로 접었을 때의 byte identity를 주장하지 않는다.

### RB: 고정 질량 블록의 prefix certificate

유한한 \(h\ge0\), 가측 \(0\le\rho\le1\), \(F(x)=\int_0^x\rho(s)ds\), \(F(h)=ph\), \(p\in[0,1]\)에 대해 모든 \(x\in[0,h]\)에서

\[
\max(0,ph-h+x)\le F(x)\le\min(ph,x),
\quad |F(x)-px|\le hp(1-p)\le h/4.
\]

앞쪽에 commodity를 모은 \(\rho=1_{[0,ph]}\)와 뒤쪽에 모은 \(\rho=1_{[h-ph,h]}\)가 각각 두 편차의 극값을 실현한다. 최대점은 \(x=ph\), \(x=h(1-p)\)다. \(p=1/2\)이면 \(h/4\)가 달성된다. label의 임의 합집합에 같은 스칼라 명제를 적용하면 유한 label prefix discrepancy의 zero-sum half-L1 bound가 따른다.

전체 블록의 label별 총량을 정확히 보존하는 **고정 분할**에서 앞선 완전 블록은 상쇄된다. 따라서 최대 블록 질량이 \(\delta\)이면 cumulative prefix error는 \(\delta/4\), 두 prefix의 차인 일반 구간은 \(\delta/2\) 이하이다. remainder를 반복해서 새로 평균내는 절차에는 이 증명이 적용되지 않는다.

\(z\in[z_{\min},z_{\max}]\)인 첨부량에는 정규화 \((z-z_{\min})/(z_{\max}-z_{\min})\)로 \(h(z_{\max}-z_{\min})/4\)가 따른다. 상수 첨부량은 정확하다. 질량 오차의 단위는 vehicle mass, birth first moment 오차의 단위는 vehicle-seconds다.

최종 문서는 실제로 \(0,\delta,2\delta,\ldots,M\)의 고정 grid를 선택한다. \(M>0\)에서 비어 있지 않은 블록은 정확히 \(\lceil M/\delta\rceil\)개이며, 추가 mandatory boundary가 \(J\)개이면 최대 \(\lceil M/\delta\rceil+J\)개이다. 단순히 각 블록 질량이 \(\delta\) 이하라는 조건만으로는 상한이 나오지 않는다.

### Eligibility와 공통 속도

비음수 locally integrable 공통 속도 \(v(t)\), \(X(t)=\int_0^tv(u)du\), 단조 entry-rank map \(\tau(q)\), 길이 \(L>0\)를 둔다. \(X(t)-X(\tau(q))\ge L\)은 rank에 대해 downward closed다. 따라서

\[
E(t)=\sup\bigl(\{0\}\cup\{0<q\le A(t):X(t)-X(\tau(q))\ge L\}\bigr)
\]

가 유효한 prefix frontier를 정의한다. \(D\)가 비감소이고 \(0\le D\le E\le A\)이면 FIFO와 동일 cumulative composition을 통한 commodity conservation이 성립한다. 빈 eligibility 집합에서도 \(E=0\)이다.

이 명제는 initially empty link와 공통 속도에 조건부이다. 초기 stock이 있으면 초기 거리 또는 eligibility profile이 필요하다. class-specific overtaking이나 일반적인 혼잡 node에 하나의 frontier를 자동 적용하지 않는다.

### 고정 서비스 기회의 안정성

최종 문서는 \(E,\widetilde E:[0,T]\to[0,M]\)가 연속·비감소이고 0에서 시작하며, 동일한 외생적 \(C\)가 절대연속·비감소이고 \(C(0)=0\)이라고 제한한다. initially empty work-conserving fluid server에서는

\[
D_E(t)=C(t)+\inf_{0\le s\le t}[E(s)-C(s)].
\]

각 후보가 \(E\)의 변화에 최대 \(\epsilon\)만큼 변하므로 infimum도 그 이상 변하지 않는다. 따라서

\[
\|D_E-D_{\widetilde E}\|_\infty\le
\|E-\widetilde E\|_\infty=\epsilon.
\]

\(F\)가 동일 rank domain에서 1-Lipschitz이고 \(\|F-\overline F\|_\infty\le\delta/4\)이면 triangle inequality로

\[
|F(D_E(t))-\overline F(D_{\widetilde E}(t))|
\le\epsilon+\delta/4.
\]

문서의 queue positivity, departure monotonicity, capacity-increment bound, backlog가 양수일 때의 work conservation 논증을 확인했다. 초기 jump 또는 초기 backlog를 추가하면 초기조건의 별도 규약이 필요하다. 현재 명제는 연속인 eligible arrivals를 명시해서 그 경계를 넘지 않는다. head composition에 따라 service나 receiving supply가 달라지는 network feedback에는 적용하지 않는다.

## 의존 관계와 obligation matrix

의존 관계는 다음과 같다.

- 고정 keys와 동일 비례 변환 → RC telescoping → 고정 선형 첨부량 보존.
- 비음수 density 및 density≤1 → prefix envelope → sharp scalar bound → label-subset/attribute reduction → 고정 분할의 prefix·interval bound.
- 비음수 공통 속도 및 단조 entry rank → downward-closed eligibility → 하나의 prefix frontier → FIFO와 cumulative conservation.
- 동일 외생적 service clock 및 initially empty work conservation → reflection formula → infimum의 비팽창성 → Lipschitz composition bound.

여기서 load-bearing leaves는 직접 유도와 명시한 모델 조건이다. 문헌은 맥락 자료이며 위 명제의 외부 정리 의존성이 아니다. 문헌의 novelty·우선권·논문 전체를 검토한 보고서는 아니다.

| Obligation | 최종 상태 | 근거 및 한계 |
|---|---|---|
| RC 실수 산술 | passed | 직접 telescoping 및 원문 induction |
| RB scalar/vector/attribute | passed | 양 끝 envelope 및 명시적 extremizer |
| 고정 블록의 누적 오차 | passed | 완전 블록 상쇄; 재평균화 제외 |
| 블록 수 상한 | passed after correction | 실제 grid 선택 및 추가 boundary 수 명시 |
| 빈 eligibility 집합 | passed after correction | 집합에 0 포함 |
| native remainder에 대한 적용 | passed within scope | 실제 공통 fraction과 endpoint 보존 확인 |
| native readiness와 fraction clamp | passed after restriction | tolerance-aware predicate와 실행된 fraction 사용 명시 |
| 고정 서비스 안정성 | passed | reflection 및 elementary infimum inequality |
| production 시각 쌍 재구성 | passed in reviewed contract | raw bits, source event order, checked indices |
| production carrier metadata 예산 | passed after correction | actual type sizes 및 독립 실행한 경계 테스트 |
| collapsed binary64 byte identity | not claimed | 실제로 일반적 associativity가 성립하지 않음 |
| source-bound sample의 미래 fraction 재현 | not addressed | corpus는 실제 혼합물이며 미래 fraction trace는 아님 |
| 현재 binary의 original checkpoint continuation | reviewed: BLOCKED_RESOURCE | transfer는 통과했으나 indexed sweep에서 거절; committed advance 0 s |
| coupled network·24h V03 수용 | out of scope | 이론과 단위 테스트로 대체할 수 없음 |

## Production 표현 변경의 검토

`4509a4fb19ec3adad8b79ef3144d02a1fda89108` 대비 `v1_road.rs`의 변경을 읽었다. source row마다 생성되는 EventRow의 mass, birth, tag, source, destination은 그대로 유지한다. 시작·종료 시각은 연속한 source-order run에서 `(u64,u64)` raw-bit 쌍으로 한 번 저장하며, 각 32-byte row에 checked u32 time index를 둔다.

추가 행 \(R\), 연속 time run \(U\), page size \(B=4096\)에서 physical payload는

\[
32B\lceil R/B\rceil+16B\lceil U/B\rceil.
\]

기존 payload는 \(48B\lceil R/B\rceil\)다. \(U\le R\)이므로 payload는 증가하지 않지만, 모든 시각이 다르면 두 descriptor family로 인해 **총 메모리**는 소폭 증가할 수 있다. 새 projection은 두 family와 descriptor growth를 모두 포함한다. 무조건적인 전체 메모리 감소로 해석하면 안 된다.

실제 source의 유일한 `events.push_checked` 경로는 한 serve 안에서 동일 `start_time`, `end_time`을 사용한다. emitted rows는 `mass > 0` 필터 때문에 head length 이하이다. 따라서 head length로 추가 행을 projection하는 방식은 보수적이다. 행순서·시각 raw bits·signed zero가 유지되며 mass/birth 계산 또는 reduction order의 변경은 발견되지 않았다. 입력 이력과 현재 이력은 여전히 각각 계상되고, 실제 shared-input/current 관계일 때만 한 번 계상한다. 최종 flat EventRow와 기존 retained history를 압축한 것으로 잘못 공제하지 않는다.

### 발견과 같은 검토 과정의 수정

초기 carrier 변경에서 `ChunkedEvents`는 x86_64에서 64B에서 120B로 증가했는데, 두 기존 metadata allowance가 96B에 머물렀다.

- empty generic page allowance는 120B carrier보다 24B 작았다.
- postroad flatten 단계는 carrier 120B와 flat Vec header 24B가 공존하므로 최소 144B가 필요하며, 이전 96B는 48B 부족했다.

이는 국소 envelope의 누락이며 실제 RSS 초과나 물리 오류를 관측했다는 뜻은 아니다. 최종 소스는 generic allowance를 `size_of::<ChunkedEvents>()`, postroad allowance를 이에 `size_of::<Vec<EventRow>>()`를 더한 값으로 수정했다. timed carrier의 192B allowance는 유지했다. 해당 두 경계 테스트와 이벤트 표현 네 테스트를 독립 실행해 모두 통과했다.

## 실행한 검산과 정확한 유한 범위

### RC/RB exact-rational checker

실행: `python /workspace/scratch/cd2a858c7a5c/rank_fifo_proposal_checks.py`.

- 120개 seeded heads: row count 1, 2, 7, 31별 30개, 각 25개 서비스로 총 3,000 split steps.
- 길이 1부터 10까지 모든 binary equal-volume profile 2,046개에서 모든 정수 prefix cut 20,480개.
- stopped eligibility frontier를 넘는 수동 입력은 거절됨.

이는 임의의 가측 profile, fractional cut, 모든 multiclass vector, binary64 underflow 또는 물리적 speed trajectory의 exhaustive 검사가 아니다. 보편 명제는 위 분석적 증명에 의존한다. checker의 root identity 검사는 원본 tuple 재사용을 확인하지만 `take()`의 served tuple 생성까지 없다는 allocation 증거는 아니다.

### Optional rank prototype

실행: `python /workspace/scratch/cd2a858c7a5c/test_fifo_rank.py`.

14개 테스트가 통과했다. immutable source 공유, ordered keys 및 endpoints, exact rational splits, 정지 frontier, 10,000개의 특정 floating split에 대한 정해진 tolerance, sub-ULP 입력 거절 등을 확인한다. 이 Python 코드는 collapsed-rank algebraic adapter이고 production traffic engine이 아니다. float test의 한정 성공으로 임의의 binary64 trajectory를 보증하지 않는다.

### 고정 서비스 안정성 checker

remote `tools/research/check_causal_service_stability.py`의 원시 코드를 읽고, 출력 파일을 쓰지 않는 실행을 독립 재수행했다.

- seed 7, 17, 41, 2691별 24개, 총 96개 rational piecewise-linear pair.
- queue-balance recurrence와의 비교 193개.
- composition crossing 및 interior queue-drain knot를 포함한 정확한 output breakpoint 4,077개.
- 수작업 draining 사례에서 \(t=3/2\), \(D=1\).
- service clock을 바꾸면 동일 arrivals라도 departure error가 2가 되는 negative control.

원래 입력 knots만 비교하지 않고 내부 queue-drain 및 composition-crossing knots를 구성한다. 해당 PL 사례들에서는 구간별 affine 차이의 supremum을 정확히 계산한다. random finite instances이며 모든 continuous arrivals의 exhaustive 검사는 아니다.

### Production targeted tests

실행한 기존 binary:

`/home/cosmosapjw/urban_traffic_v03_causal_rank_20261123/target/debug/deps/_metroflow_rust-ce861d44b76e7ee1`

- filter `event_carrier_metadata_tests`: 2 passed, 0 failed.
- filter `v1_road::exact_event_time_run_tests`: 4 passed, 0 failed.

parent가 보고한 broader road regression은 111 passed, 2 existing ignored다. 그 전체 집합은 이 reviewer가 재실행하지 않았으며, 위 6개 독립 targeted 결과와 구분한다. 앞선 `S04_native_regression.log`의 45-pass 결과 및 `S04_original_continuation.json`은 이전 source의 증거이므로 최종 carrier 실행 결과로 사용하지 않았다.

## Provenance와 남은 경계

검토 종류: isolated independent subagent, read-only production review, 추가 child reviewer 없음. 이 파일 외의 수정은 수행하지 않았다. 실제 수정은 author/parent가 수행했고, reviewer는 동일한 bounded review 안에서 필요한 correction만 확인했다.

| Artifact | Identity |
|---|---|
| 최초 `theory_proposal.md` | SHA256 `5a478ed41db62bb52f3c5948f45262f5a758c34dff2accfbbfcacf0f1ca398a5` |
| 최초 rational checker | SHA256 `c854c43866877ab014ef1a472bb50afd3e9f124084bdeef39e3b155b00386279` |
| 원본 physical source 기준 | commit `606b3ac6a899ba5b8b9ac064d82f609c7ff6cadf` |
| 위 기준의 `v1_road.rs` | git blob `832bcd150a33c8c6ba89d8909e5f584ade87c74e` |
| production diff 기준 | commit `4509a4fb19ec3adad8b79ef3144d02a1fda89108` |
| correction 전 production file | SHA256 `6461155b3dc1df93bd174d63b546047da38af1da6deec8fc2548f08554b4c604` |
| 최종 production file | SHA256 `f27ccbee4472472b5e59995de9bf64cc00a7cb042202d15b073ab5aad176983e` |
| 최종 `docs/research/V03_CAUSAL_FIFO_THEOREMS_20261123.md` | SHA256 `70a8379a6107c52030ab235161943e9bcbd3fad06ab8407f9c9d5d3c6331d041` |
| 고정 서비스 checker | SHA256 `cc1303e89294a1d7a73777c02dda15b724ad5cef8f73de1398199dfb5a32478f` |
| `S06_original_fifo_heads.json` | SHA256 `7152480c49fec04d4a700c9f0716d140f0c3a7c62d967d323723203be71c711c` |

remote device는 `edd1b263-56a0-4391-8a2a-677dd00eabf5`, repo는 `/home/cosmosapjw/urban_traffic_v03_causal_rank_20261123`다. 원본 source의 `served_parts`, `portion`, fraction clamp/snap, `EventClock::after_ready`, remainder endpoint 보존을 직접 읽었다. readiness tolerance는 `1e-10 s`, snap 조건은 `1-f<1e-14`다.

실제 head corpus의 464/454/442개 행과 source metadata를 확인했다. 문서는 해당 corpus를 실제 source mixtures라고 기록하고, observed future service fractions 또는 whole-network execution으로 부르지 않는다. 이 reviewer는 3.4GB checkpoint 전체를 다시 읽어 hash를 계산하지 않았으며, corpus의 checkpoint provenance는 extractor의 기록에 의존한다.

최종 범위에서 남은 수학적 gap은 발견하지 않았다. 아래에 같은 검토 과정에서 후속 제공된 실제 실행 receipt를 추가한다. script exit 0, 요청 horizon, synthetic split, finite test success만으로 scientific success를 선언하지 않는다. 유용한 연구 단계 산출물은 인정할 수 있으나 original DAG21의 node count 또는 V03 수용 상태로 바꾸지 않는다.

## 후속 실제 증거: 같은 bounded review의 마지막 추가 기록

parent의 요약만 사용하지 않고 remote의 `S07_original_continuation.json`과 `S07_rank_head0_benchmark.json`을 직접 읽었다. 원본 source와 source-zero run 전체를 다시 감사한 기록은 아니다. 이때 production file SHA256은 위 최종 correction의 `f27ccbee…`와 동일했다.

### 원본 checkpoint에서 native continuation

| 항목 | 실제 receipt 값 |
|---|---|
| source commit | `03b76ccf2ef6bc087d38681c78716e749cce3943` |
| source identity | `bea107c2888885966c901a0f30a6d7edcb50a24e5cbbbe31d3f8bf020536943d` |
| native binary SHA256 | `22a7cebc751b575521a8360ab7e235aa7fa6fa9e4d54c8ac8904b35e708ae57a` |
| source dirty | `false` |
| input checkpoint SHA256 | `ac7a209c6adfd594c791d1ac4b5b33c6e013ae73b7b594e42121115c89bd8369` |
| full wire roundtrip | receipt에 `true`로 기록 |
| initial / completed time | 25,700 s / 25,700 s |
| valid advanced duration | 0 s |
| completed steps / horizons | 모두 빈 목록 |
| 결과 | `BLOCKED_RESOURCE` |
| 실패 단계 | `indexed sweep preflight` |
| required / budget | 5,051,633,256 B / 5,025,214,575 B |

초과량은 26,418,681 B다. 이전·완료 mass ledger가 동일함을 receipt에서 직접 비교했다. 이는 실패한 candidate를 commit하지 않고 마지막 유효 상태가 보존됐다는 기록과 일치한다. 이 검토자는 checkpoint 전체 roundtrip을 새로 실행하지 않았으며, 그 binary identity 검증은 source-bound driver receipt의 결과로 인용한다.

이번 candidate에서는 258,538번의 `transfer candidates` guard가 모두 통과했다. 이후 첫 indexed sweep preflight에서 거절됐다. 따라서 기존 transfer 단계의 자원 차단을 지나간 것은 실제 구현 성과이며, `25700→25710` tick을 완료한 것은 아니다.

실패 전에 만든 **미커밋 candidate events**는 17,429,035개, 연속 time run은 206,999개였다. 이는 실제로 완료한 city departures의 수로 해석하지 않는다. payload는 561,184,768 B이며 기존 48B candidate 표현 대비 275,578,880 B가 절약됐다. reviewer가 행 페이지 4,256개와 time 페이지 51개로 식을 다시 계산해서 두 숫자가 일치함을 확인했다. 이 절감량은 temporary event payload의 측정이며 전체 process RSS 또는 retained history의 절감량이 아니다.

`S07_original_continuation.json` SHA256:
`38e15baaf9555cd0c5fae2e55f6c51fbb3e04d9642acb690ad9597ed51e1e4b9`.

### 실제 464-row head를 사용한 Python rank benchmark

입력은 실제 checkpoint corpus의 cell 466, 첫 packet, 464-row composition이다. 서비스 fraction은 실제 future trace가 아니라 `f_k=1/(2K-k)`의 synthetic half-service schedule이다. 두 구현은 1,000번마다 old snapshot을 보관했고, 100,000번 실행에서는 각각 100개 snapshot을 유지했다.

| subdivisions | eager wall (s) | rank wall (s) | eager peak (B) | rank peak (B) | max mass difference | max birth difference |
|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 0.4762786800 | 0.0198906620 | 105,540 | 54,092 | 4.7921736024e-17 | 1.7763568394e-12 |
| 10,000 | 5.0043623720 | 0.1778576780 | 577,916 | 54,908 | 5.7332610881e-16 | 1.9312551558e-11 |
| 100,000 | 50.6546291080 | 1.7483256490 | 5,301,132 | 62,844 | 1.2491743751e-14 | 1.9905144200e-10 |

오차는 per-key eager remainder와 collapsed-rank remainder의 차이다. 각 run의 464개 key에 대해 source mass/birth에서 tolerance를 다시 계산하고, receipt의 threshold 및 최대값과 대조했다. manual half-service oracle error도 검사했다. 모두 아래의 **adapter 전용** 문턱을 통과했다.

\[
|\Delta m_k|\le10^{-9}\max(1,m_k),\qquad
|\Delta b_k|\le10^{-8}\max(1,b_k).
\]

시간은 `tracemalloc`을 켠 상태의 wall time이다. memory는 measurement 이전에 구성된 shared root를 제외한 incremental Python allocation peak이며 native RSS가 아니다. 이 비교는 remainder 생성과 sampled immutable snapshot 보관을 측정한다. native event 생성, row 소비, node rate, interval overlay, 실제 전체 물리 실행의 가속률은 측정하지 않았다. 100,000회에서 약 29배의 Python wall ratio 또는 약 84배의 incremental allocation peak ratio를 native speedup·전체 메모리 감소로 일반화할 수 없다.

benchmark artifact의 명시적 결론도 `V03_full_day_evidence=false`다. 원본 composition에서 특정 synthetic fraction schedule을 재생한 유용한 numerical/implementation evidence이며, observed service replay 또는 full-city 수용은 아니다.

`S07_rank_head0_benchmark.json` SHA256:
`f3c45dfc339e97de62f0ce5caf58d9ca8edb0ddb3ee6e56b6701ed33d0d71a33`.

이 추가 기록은 mathematical verdict를 바꾸지 않는다. Production 결과의 분류는 **event representation의 한정 검증 및 자원 병목 이동; tick advance 0 s; V03 여전히 미수용**이다. 별도 source-zero 실행의 검증과 결과는 parent가 관리하며 이 reviewer의 완료 조건에 포함하지 않았다.
