# MetroFlow 이론 재구축: 독립 단회 수학·소스 검토

검토일: 2026-11-23. 범위: 부모의 THEORY ONLY R1–R10 작업 중 한 번의 fresh R6 검토. 구성자의 판정은 전제로 사용하지 않았다. 검토 중 발견한 두 문제를 부모에게 전달했고, 부모가 수정한 해당 문단만 같은 검토 회차에서 다시 읽었다. 재귀 검토, 추가 subagent, production 수정, native build, 도시 실행, benchmark, commit/push는 수행하지 않았다.

## 1. 판정과 실제 수정

**수정된 문서의 핵심 결과는 명시된 조건 아래 재사용할 수 있다.** 최초 문안에서는 원자적 event의 시각 오차를 jump state의 같은 시각 sup 오차로 옮기는 논증이 잘못됐고, 일반 Mixed packet에 대한 lossless fiber 정의에는 mass–clock 결합 정보가 빠져 있었다. 두 문제는 이번 단회 검토 안에서 구체적으로 수정됐다. 이 판정은 현재 native 구현, 전체 도시의 오차 상계, 24 h 자원 충족, V03 통과에 대한 판정이 아니다.

| ID | 원래 심각도 / 현재 관련성 | 정확한 대상 | 결과 |
|---|---|---|---|
| F1 | 높음 / 잘못된 안정성 주장에는 BLOCK_NOW | `metroflow_controlled_routes.md` §3, “Matching atomic events instead of assuming a density” | **해소.** 연속 state의 mode 전환에 한정하고 jump/history에는 다른 비교 척도 또는 atom 오차를 요구하도록 수정한 문장을 읽었다. |
| F2 | 중간 / 일반 Mixed 입력의 lossless 주장에는 FIX_SOON | `metroflow_exact_routes.md` §2.1, Theorem A2, §5.1–5.2 | **해소.** endpoint-conditioned component, 원래 head membership, 공통 service fraction, joint metadata 보존을 명시한 수정문을 읽었다. |
| F3 | 낮음 / 근거 연결의 표현 문제 | controlled note의 “finite-source elimination proof above” | **해소.** 부모 문서 Proposition Q2에 실제 소거 증명을 추가하고 해당 위치를 참조하도록 수정했다. Q2 증명과 $2M\epsilon_g$ bound를 직접 확인했다. |

위 수정 이후 새 재검토 회차를 요구할 현재의 수학적 결함은 발견하지 않았다. 아래의 native 적용·비용 조건들은 이번 검토가 새로 만든 차단 조건이 아니라, 문서가 이미 정확하게 열어 둔 연구 의무다.

## 2. F1: event 시각 정렬과 jump state의 sup 오차는 다르다

### 결함과 반례

최초 문안은 횡단 조건, 유한하고 분리된 event, Lipschitz reset, bounded vector field를 함께 열거한 뒤 event 시각 이동으로 같은 시각 state 오차를 제어할 수 있다고 서술했다. 일반적인 jump state에는 성립하지 않는다.

초기값 $y(0)=0$, 양쪽 flow $\dot y=0$, 한 번의 reset $R(y)=y+1$을 잡는다. 기준 guard는 $g(t)=t-1$, 변경 guard는 $\widetilde g(t)=t-(1+\varepsilon)$, $0<\varepsilon<1$이다. 두 guard의 도함수는 1, guard 차이는 $\varepsilon$, reset은 Lipschitz이며 event는 하나뿐이다. 그런데

\[
y(t)=1_{t\ge1},\qquad
\widetilde y(t)=1_{t\ge1+\varepsilon},
\]

이므로 $t=1+\varepsilon/2$에서 차이가 1이고

\[
\|y-\widetilde y\|_{\infty,[0,2]}=1
\]

이다. flow의 차이는 0이므로 “vector-field jump bound × event-time shift” 항만으로 이 불일치를 흡수할 수 없다. 동일한 문제가 단위 atom이 있는 완료 CDF에도 발생한다. event time 자체는 연속적으로 변해도 같은 시각의 threshold query는 불연속일 수 있다.

### 최소 복구와 확인한 수정

현재 문안은 **state가 연속이고 mode만 바뀌는 경우**로 같은 시각 추정을 제한한다. 유한한 matched event, 횡단성, 같은 event 순서, phasewise Lipschitz flow가 유지되면 서로 다른 mode에 있는 짧은 시간 구간의 적분 오차와 이후 증폭을 합산할 수 있다. bounded service rate가 만드는 연속 출발 누적량도 같은 종류의 추정을 받는다.

실제 jump state 또는 atomic completion history는 event-aligning time change, 그에 적합한 Skorokhod/event-aligned metric, 혹은 별도의 atom 오차를 필요로 한다. 부모는 이 구분과 위 반례를 본문에 반영했으며, 새 jump-metric 정리를 증명했다고 주장하지 않는다. 따라서 F1을 닫는다.

**영향을 받지 않는 결과:** joint $E,C$ reflection bound, 그 가정을 실제로 만족하는 연속 변수에 대한 Proposition A2, 정확 표현 A/B, 수동 historical observer O, held phase의 적분 mark E. 원자적 eligibility가 Proposition A2의 $e(t)$ 가정을 자동 만족한다는 해석만 배제하면 된다.

## 3. F2: label totals와 clock 목록만으로는 결합분포가 복원되지 않는다

### 소스 근거와 최소 반례

기준 `v1_road.rs`의 `check_state` 3433–3463은 각 Part의 route/mass/birth/endpoint 유효성을 검사하지만, 한 packet의 모든 rows가 같은 endpoint를 가져야 한다고 강제하지 않는다. `combine` 2245–2293의 key도 `(tag,offset,a_bits,b_bits)`다. 따라서 일반 초기 Mixed packet을 포함하는 상태 계약에서는 endpoint별 질량 결합을 보존해야 한다.

동일한 원래 head와 target, 동일 $z=(tag,offset)$, $B=0$, 두 point clock $1,2\,\mathrm{s}$를 잡는다. 두 상태를

\[
\mu=\tfrac12\delta_{(z,1)}+\tfrac32\delta_{(z,2)},
\qquad
\nu=\tfrac32\delta_{(z,1)}+\tfrac12\delta_{(z,2)}
\]

로 놓으면 tag total은 둘 다 2 vehicles, birth total은 0, clock 목록도 동일하다. 그러나 clock 1에 붙은 질량은 다르다. 최초 정의의 tag-only $K_g,J_g$와 별도의 clock 목록만으로는 두 상태를 구별하지 못한다.

이 반례는 class/suffix physical quotient의 동역학 자체를 반박하지 않는다. **모든 source-represented endpoint 정보를 lossless하게 복원한다는 더 강한 서술**에 필요한 상태 변수를 지적한다. 하나의 uniform endpoint slab에 국한된 원래 계산에는 문제가 없었다.

### 최소 복구와 확인한 수정

수정문은 각 원래 head $h$를 endpoint key $\eta$별 $v_{h,\eta}=(m_{h,\eta},B_{h,\eta})$로 나타낸다. missing-time state와 필요한 endpoint bits도 key에 포함한다. 중요한 점은 이들이 **하나의 원래 head 안의 구성 성분**이며 새로운 FIFO head가 아니라는 것이다. 물리 query는 성분들에 걸쳐 합산하고, service fraction은 원래 head 전체에서 한 번 결정해 모든 성분에 공통으로 곱한다.

remainder는 기존 $\eta$를 유지한다. outgoing service는 source와 같이 새 event interval로 endpoint metadata를 reset하며, 이는 joint measure에 대한 결정론적 pushforward다. B의 fibers는 $M_{g,\eta},K_{g,\eta},J_{g,\eta}$로 읽는다. 부모가 §2.1/A2/§5.1–5.2와 §5.5 비용식에 이 조건과 endpoint-component count를 추가한 것을 확인했다. 따라서 F2를 닫는다.

이때의 동치는 exact-real **상태·event measure** 동치다. 같은 key의 중복 행을 어떤 행 순서와 operation history로 다시 출력해야 하는가, signed zero/rounding/underflow를 어떻게 재현하는가, legacy wire의 bytes가 같은가는 별도의 원래 arithmetic/serialization 계약을 따른다. A/B의 선형 측도 계산이 그 계약까지 입증했다는 해석은 문서의 명시적 범위를 벗어난다.

## 4. 핵심 결과별 독립 판정

### 4.1 A: 연산자와 interval 표현

positive scaling, addition, destination projection, route pushforward는 유한 label measure에 대해 선형이다. 시간 restriction은 label operator와 commute하므로 elementary slab의 정확한 계수는 $\lvert J\rvert/\lvert I_e\rvert$다. source `combine_interval_mapped` 2295–2346의 좌표식과 일치한다. point atoms는 별도로 처리하며, source `interval_packets` 3234–3311의 point-before-slab 순서를 유지해야 한다.

source `served_parts`/`portion` 1626–1650은 양의 결과를 남긴다. 실수 산술의 $f>0,m>0$에서는 이 필터가 추가 근사를 만들지 않는다. binary64 underflow와 행별 rounding은 이 증명 밖이라는 arithmetic contract도 적절하다.

class totals, occupied length, destination mass, footprint-weighted destination mass, speed/latent numerators를 같은 값으로 공급하면 현재 road law가 선택하는 control과 event를 같은 값으로 재계산할 수 있다. `motion` 3082–3169, `rates` 3324–3379, incoming mark 처리 4192–4253을 직접 읽어 이 consumer map에 반하는 tag-specific 물리 의존성을 찾지 못했다. registry, class identity, head/target/order, event/tick conventions를 고정하는 가정이 필요하다.

동일한 인접 density도 midpoint mark 아래에서는 경계를 제거할 수 없다는 반례는 유효하다. $v(t)=1-e^{-t}$인 예의 차이는

\[
2e^{-1}(\cosh(1/2)-1)
=0.09390193751817855\ \mathrm{vehicle\,m/s}.
\]

따라서 composition storage 공유와 virtual event/head knot 삭제는 다른 연산이다. 현 문서는 이를 구분한다.

balanced persistent active tree가 overlay의 label×slab allocation을 만들지 않고 descriptor를 저장할 수 있다는 구성은 유효하다. 그러나 $V,Q_*$, indexed leaf query 비용, cache lifetime, explicit export 비용을 합쳐야 한다. 따라서 저렴한 descriptor만으로 전체 연산량 감소를 결론내리지 않은 판정도 적절하다.

### 4.2 B: class와 complete suffix quotient

고정 registry와 현재 road law에서 class와 complete residual route가 같은 label은 현재 class contractions, destination projections, route advancement, class mark에서 구별할 필요가 없다. 원래 head와 eligibility 구조, 수정된 endpoint-conditioned state를 유지하면 각 primitive가 quotient와 commute한다.

fiber의 mixture 식 $K'=\sum_r a_rK_r/\sum_r a_r$, $J'=\sum_r a_rJ_r/\sum_r a_r$도 정확하다. $J_g$는 확률밀도가 아니라 단위가 seconds인 birth first-moment density이므로 $J_g\propto K_g$를 임의로 강제하지 않은 점이 중요하다.

complete suffix를 immediate destination으로 축소하면 두 번째 junction에서 미래 행동이 달라진다는 반례, bus tag 두 개의 half completion을 하나의 완료로 합치면 안 된다는 반례 모두 현재 소비자와 맞는다. `v1_journey.rs` 805–839는 tagwise sink mass를 먼저 만들고 bus별 near-one threshold를 적용한다.

**도시 전체의 autonomous quotient는 얻지 못했다.** service/journey, 향후 replanning, 정보·목적별 정책, accessibility/development가 fiber를 읽을 수 있다. 현 문서가 이들을 원래 state와 정확한 tagwise interface로 유지하고, 실제 query 비용 $F,Q_F$를 별도 항으로 남기는 한 road quotient의 타당성과 충돌하지 않는다.

### 4.3 Joint eligibility–capacity reflection과 feedback

\[
D(t)=\inf_{s\le t}\{E(s)+C(t)-C(s)\}
\]

에서 두 integrand의 차이는 $(E-\widetilde E)(s)+f(t)-f(s)$, $f=C-\widetilde C$다. 따라서

\[
\|D-\widetilde D\|_\infty
\le\|E-\widetilde E\|_\infty+\operatorname{osc}f
\le\|E-\widetilde E\|_\infty+\int|c-\widetilde c|
\]

라는 증명은 직접 성립한다. zero-capacity 구간에서 division이 필요하지 않다. 단순히 $\|C-\widetilde C\|_\infty$ 하나로 바꾸면 안 된다는 0→2 예도 정확하다.

초기 stock이 있을 때 `min{C(t), inf[...]}`를 추가한 수정은 필요하고 정확하다. 예를 들어 $E\equiv Q_0>0,C(t)=ct$이면 현재 식은 $D(t)=\min(ct,Q_0)$를 준다. empty-history candidate가 없으면 $D(0)=Q_0$라는 잘못된 결과가 나온다.

dimensionless variables에서 A3를 가정하면 $z+d$에 대한 Volterra inequality와 Gronwall A4가 바로 따른다. 고정 support, positive denominator, eligibility regularity, multi-sender progressive allocator의 각 stage, upstream transfer의 causal closure를 실제로 확보해야 한다는 의무는 남는다. 특히 $\rho(P)<1$, acyclic route-state graph, positive delay는 서로 다른 충분조건이며 현재 도시에서 검증됐다고 할 수 없다.

rare blocked-tail 반례는 whole-queue mass/mark 보존만으로 충분하지 않음을 실제로 보여 준다. $\varepsilon=10^{-4}$일 때 prefix error는 $9999/10^8$ vehicles지만 departure difference는 $9999/10^4$ vehicles다. mandatory support boundary를 유지하면 이 예를 정확하게 복구할 수 있고, 구성된 partition의 `ceil(M/delta)+J_sigma` bound도 타당하다. 이 결과를 일반적인 mesoscopic traffic 불가능성으로 넓히지 않은 것은 맞다.

두 상태 및 지연 development 예의 특성다항식, damping 조건, C3의 weighted-envelope 증명은 일관적이다. C2는 명시된 비음수 coupling과 positive response time에서 충분조건이며 필요조건이 아니다. 실제 native accessibility/development의 gain이나 lag kernel을 측정한 결과로 재명명하면 안 된다.

### 4.4 Positive moments와 실제 consumer

부모 Proposition Q2의 소거 과정은 유효하다. feature에 상수 1을 넣으면 null vector의 성분 합이 0이므로 양·음 coefficient가 함께 존재한다. $s=\min_{a_i>0}w_i/a_i$, $w_i'=w_i-sa_i$는 nonnegativity와 모든 feature integral을 보존하면서 적어도 한 atom을 제거한다. 유한 source에 대해 최대 $m$개 atom까지 종료한다.

동일 mass $M$와 $g=\sum\alpha_i\phi_i+r_g$, $\|r_g\|_\infty\le\epsilon_g$에서 $2M\epsilon_g$ residual도 정확하다. 각 좌표의 단위를 정한 후 계산한다는 계약이 있다. 이 정리 자체는 arbitrary threshold, support test, route policy, future hybrid reset의 오차를 작게 만들지 않는다. dual invariance 또는 실제 uniform residual이 추가로 필요하다는 구분이 적절하다.

### 4.5 O: 수동 historical trace

immutable baseline의 `last_events` production read sites를 `git grep`으로 확인했고, `v1_journey.rs`의 getter/clone/accounting/write/reset 경로와 현재 sink 생성 1614–1626, commit 1748을 직접 읽었다. 원래 call-input trace를 Arc로 붙잡는 1434–1451도 확인했다. `eligible` 871–875의 ReceiptHistory는 미래 leg release에 들어가므로 O로 분류할 수 없다.

현재 tick sink projection을 $F(X,u)$ 안에 포함시키고 **이전** trace만 passive O로 분리한 명제는 정확하다. $d(e(O))=O$와 decoded validation이 성립하면 common-admissible successful sequence에서 귀납 동치가 나온다. 저장 형식이 달라져 resource failure가 개선되는 것과 같은 실패시각까지 보존하지 않는 것은 양립한다.

road sink로부터 car raw egress measure를 delay pushforward하는 A9도 source 2046–2062와 맞는다. 실제 receipt까지 연결할 때는 due retirement가 `end+1e-10` prefix를 쓰고, receipt time이 `max(t, raw_due_time)`, receipt fraction이 leg total로 정규화됨을 보존해야 한다(source 2123–2145). 본문의 “source sampling convention”은 이 구체적 연산을 뜻해야 한다. 기존 explicit journey state를 유지한다는 계약 아래 새로운 결함은 아니다.

### 4.6 E: 적분 mark의 정확한 범위

held source Motion, class share, uniform flux $r_e=M_e/(b-a)$가 고정된 양의 길이 phase에서

\[
J_v=r_e[\chi(b)-\chi(a)],\quad
J_{p,k}=r_e\theta_k\int_a^b p_k(t)dt
\]

는 유한 subdivision에 가산적이다. $J_v$의 단위는 vehicle·m/s, $J_p$는 vehicle이고 receiving mean의 denominator는 양수여야 한다. $\lambda\to0$ 극한은 상수 latent branch와 일치한다. clipped characteristic은 saturation/exponential 전환에서 분리하여 적분하면 된다.

이 불변성은 held integrand와 flux에 대한 것이다. 재분할로 Motion을 재계산하거나 snapped emitted mass, class composition, active node constraint가 달라지면 그 가정을 벗어난다. 현 문서는 genuine phase boundary를 유지하고 midpoint source와 다른 수치 모델임을 명시한다. midpoint $rh^3\|g''\|_\infty/24$ 국소 경계에서 전체 도시의 error equivalence를 곧바로 주장하지 않은 것도 적절하다.

## 5. 독립 실행한 최소 계산과 소유권 검토

새 계산은 scratch에서 Python 정수/Fraction 계산을 한 번 실행한 것으로 한정했다(exit 0). author의 128-case reflection campaign은 companion JSON의 기존 증거로 읽었으며, 이번 검토에서 128개를 다시 실행했다고 주장하지 않는다.

| 대상 | 독립 계산 결과 |
|---|---:|
| S07 structural road base | 2,602,210,912 B |
| indexed failure 합계 | 5,051,633,256 B |
| source index 항 | 13,723,920 B |
| index 항 제거 후 합계 | 5,037,909,336 B |
| 동일 allowance | 5,025,214,575 B |
| index 제거 후에도 남는 초과 | 12,694,761 B |
| candidate timed-page payload | 561,184,768 B |
| conditional old-trace payload difference | 458,883,136 B |

source index 식의 point/nonpoint 구분은 ROAD 1748–1776과 일치한다. payload difference는 `64*14,432,257 - 464,781,312`다. 이것은 기존 두 payload의 산술적인 차이이며 새 persistent implementation의 peak memory 측정값이 아니다.

input/current/candidate roots에서 reachable한 allocation의 union을 세고, backing alias와 descriptor owner를 구별하며, caches와 active history를 포함한다는 lifetime 규칙은 타당하다. 특히 call-input trace가 첫 commit 뒤 current와 다른 allocation이 되는 경계가 소스에 있다. root가 과거 WorldState 전체를 capture하면 표현 크기가 작아도 옛 state를 살려 두므로, payload-only root 조건은 실제 비용 주장에 필요하다.

**병목 이동은 숨겨지지 않았다.** A는 query traversal/cache와 export에, B는 actual suffix/endpoint support와 fiber readout에, O는 외부 full-Vec/legacy wire에, controlled phase route는 mandatory support/event count와 error amplification에 비용을 남긴다. 어떤 방법도 현 자료만으로 8 GiB/7,200 s 또는 원래 24 h workload 충족을 예측할 수 없다.

## 6. 원래 과학 목적과 다음 연결의 경계

검토 문서는 100k bulk mesoscopic map→traffic→accessibility→lagged development→demand라는 목적을 유지한다. finite response, finite information, strict shared-lane FIFO, purpose/class/person/vehicle/cargo 장부를 각각 독립된 consumer obligation으로 다룬다. exact IEEE operation sequence는 현재 compatibility lane으로 남고, 최초 과학 목적과 동일시되지 않는다.

soft-min target은 rare slow class의 기존 hard target을 넘을 수 있으므로, 그 값이 admissibility/safety constraint인 모델에는 원래 closure의 제어 근사로 쓸 수 없다. 본문이 이를 별도 behavioral model로 명시하고 ancillary 후보로 남긴 것은 적절하다. 이는 원래 V03 통과 조건의 수정 권한을 주지 않는다.

이후 코딩 연결에서 필요한 가장 작은 구체적 작업은 이미 제시된 consumer support census와 완전한 한 transition의 interface contract다. source roots, real event/endpoint knots, class/suffix/endpoint groups, distinct pullback queries, active histories, 실제 동시에 살아 있는 owner를 함께 세어야 한다. A/B의 동치 입증과 query 비용 검증을 구분해야 한다. 이번 이론 범위에서 그 native 작업을 실행하지 않은 것은 미실행 상태 그대로 보존한다.

## 7. 읽은 근거와 검토 identity

원격 source 기준은 `/home/cosmosapjw/urban_traffic_v03_causal_rank_20261123`, immutable commit `492e27618696df2514b088a64de450cf69746647`, device `edd1b263-56a0-4391-8a2a-677dd00eabf5`다. 원격 읽기는 `git show <commit>:<path>`와 `git grep ... <commit> -- <paths>`로 수행했다. 다른 agent의 진행 중 HEAD 변경과 분리해 이 고정 source를 읽었다.

직접 확인한 주요 source는 `crates/metroflow-rust/src/v1_road.rs`의 served/portion, interval classifiers/consumer, motion, rates, state checks, event emission, pending admission, mark normalization이며, `v1_journey.rs`의 old-trace lifetime/getter, service threshold, current sinks, egress/receipt, eligibility 경로다. anatomy의 과거 binary/checkpoint identity는 보존된 증거를 재사용한 항목으로 취급했고, 대용량 checkpoint를 새로 decode/hash하거나 binary를 실행하지 않았다.

수정 문단 확인까지 끝난 네 문서의 SHA-256:

| 파일 | SHA-256 |
|---|---|
| `metroflow_exact_routes.md` | `02f7821d5740870616412ef40115d41c9f4f7c0f6cbfac3362a894dec9ddb374` |
| `metroflow_controlled_routes.md` | `88136a87be7783bee21b4b0f9b07b59922edc30431edd45fc352fb5443e06d1f` |
| `metroflow_parent_reconstruction.md` | `c52808b73f3a2fc210fed5d9e58bb2d34c928131ac79d07e99b9869de2b0ad65` |
| `metroflow_theory_anatomy.md` | `eb21a7c0ae8cdf1df445d8e7243fe711a60728cce49610b9dc87202226d93789` |

읽은 companion evidence는 `metroflow_exact_routes_calculation.json`, `metroflow_controlled_routes_checks.json`, `metroflow_theory_anatomy_evidence.json`이다. 그 기록의 author status는 독립 판정의 근거 대신 계산 입력/출력과 source mapping 자료로만 사용했다.

문헌의 두 좁은 재사용 관계도 primary PDF에서 확인했다. [Kruk et al., 2007, Eq. (1.1)](https://arxiv.org/pdf/0710.2977)는 half-line reflection 공식과 uniform norm Lipschitz constant 2를 제시한다. [Bayer–Teichmann, 2005, Corollary 2](https://arxiv.org/pdf/math/0502473)는 finite feature integral의 positive finite realization을 다룬다. 여기의 $E,C$ bound와 유한 source 소거 증명은 본문에서 직접 성립하며, 두 논문을 whole-city FIFO·hybrid feedback theorem으로 확장해 사용하지 않았다. 신규성/strong no-go의 독립 판정은 요청하거나 수행하지 않았다.

`skill_context_used`: PhysMath Research Loop **1.3.0**, `SKILL.md`, `references/THEORY_LOOP.md`, `references/SUBAGENT_MODE.md`, `references/POLICY_INTEGRATION.md`를 실제 읽었다. 적용한 경계는 단회 R6 검토, 수학적 반례와 최소 복구, 원래 과학 목적 유지, typed identity, scope-limited lightweight calculation, 무재귀 종료다. 이번 reviewer가 작성한 산출물은 이 문서 하나다.
