# V03: 질량·1차 모멘트·support로 구성하는 age-excess 관측 구간

작성: 2026-11-23 KST. 기준 연구 계보: `3c8650abc8b556387e7f24ce84b1e676e6e8b141`; 후속 브랜치 `research/v03-event-store-moment-envelope-20261123`.

## 1. 해결 대상과 근거 상태

기존 `age_excess_transport.py`는 실제 원자 birth 측도를 입력받아 유한 창의 정확한 stop-loss 곡선 K(u)를 계산한다. 그러나 원본 native event에는 각 미세 birth 원자 전체가 아니라 질량 m과 birth-time mass B 등 집계량이 있다. 여기서는 그 불완전한 자료에서 평균을 지연 분포로 대체하지 않고, 가능한 모든 양의 측도를 포함하는 관측 구간을 구성한다. FIFO·source 순서·원래 f64 물리 계산을 변경하지 않는 관측 closure다.

- **Established / literature-supported:** convex function의 Jensen 하계, endpoint chord 상계, conditional support refinement.
- **Derived in this project:** age-excess kernel에 대한 sharp 동시 threshold 구간, 명시적 gap, birth-moment 사상, fixed-source censor 상계, 안전한 secant CDF 구간과 수렴 조건.
- **Exact finite checked:** 2,790개 rational distribution/threshold 배치, 2,520개 strict-tail/CDF 배치, extremizer·경계·합성·반례.
- **Implementation verified:** 독립 Python Fraction 관측기와 검사 10개.
- **Conditional for native measurements:** 실제 support 및 first-moment 의미가 입증되어야 한다. f64 집계량을 받는 것만으로 전체 반올림 오차의 interval certificate가 생기지는 않는다.

기존 수학의 전역적 신규성은 주장하지 않는다. 프로젝트의 이론 업그레이드는 이전에는 계산할 수 없었던 K(u)를, 현재 자료로 계산 가능한 보장 구간과 추가 관측의 정량적 수렴 기준으로 연결하는 것이다.

## 2. 정의와 단위

유한한 양의 age measure ν를 취하고 다음 자료만 알고 있다고 하자.

\[
m=\int d\nu,\quad A=\int a\,d\nu,\quad
\operatorname{supp}\nu\subseteq[L,H],\quad
0\le L\le H<\infty,\quad mL\le A\le mH.
\]

m의 단위는 선택한 관측 질량, a,L,H,u는 s, A와 K는 질량·s다. 원래 차량 질량을 관측하면 vehicle·s이고, 반복된 내부 event를 관측하면 incidence-weighted vehicle·s이므로 두 모집단을 혼동하지 않는다.

\[
K_\nu(u)=\int(a-u)_+d\nu(a).
\]

물리 threshold는 보통 u≥0이다. Secant 계산을 위해 u∈R로 자연스럽게 연장하며, u≤L에서는 K=A−mu가 정확하고 u≥H에서는 K=0이다. m=0이면 A=0을 요구하고 K=0으로 정의한다. L=H이면 A=mL이고 K=m(L−u)+이다.

## 3. 명제 1: sharp stop-loss envelope

m>0, L<H, 평균 μ=A/m이면

\[
\boxed{K_-(u)=(A-mu)_+\le K_\nu(u)\le
K_+(u)=
\frac{(mH-A)(L-u)_+ +(A-mL)(H-u)_+}{H-L}.}
\]

**하계 증명.** g_u(a)=(a−u)+는 a의 convex function이다. 질량 m로 정규화해 Jensen 부등식을 적용하면 E[g_u(a)]≥g_u(E[a])다. 양변에 m을 곱하면 K_-를 얻는다.

**상계 증명.** a∈[L,H]에서 convex chord는

\[
g_u(a)\le
\frac{H-a}{H-L}g_u(L)+\frac{a-L}{H-L}g_u(H)
\]

이다. 이를 ν에 대해 적분하면 K_+가 나온다.

**Sharpness와 동시성.** 하계는 mδ_μ, 상계는

\[
\frac{mH-A}{H-L}\delta_L+
\frac{A-mL}{H-L}\delta_H
\]

에서 달성된다. 이 두 측도는 u와 무관하므로 모든 threshold에서 각각의 extremum을 동시에 달성한다. Sharpness는 mass/mean/support만 주어진 양의 측도 전체에 대한 것이다. 원래 discrete birth calendar의 추가 제약까지 사용한 가능집합의 sharpness는 주장하지 않는다.

**구성적 예제.** 실제 age1,5의 단위 질량 두 개는 m=2,A=6이다. support[0,6]만 아는 경우 u3에서 K∈[0,3]이고 실제 K=2다. 평균 age3에 모든 질량을 놓는 대체는 K=0을 주므로 정확한 관측이 아니다. 실제 추가 관측으로 두 bin의 자료 (m,A,L,H)=(1,1,0,2),(1,5,4,6)를 얻으면 u3에서는 K=2로 정확하게 좁혀진다.

## 4. 명제 2: 명시적 오차 폭과 실제 refinement

한 block의 envelope gap은 support 밖에서0이고, L≤u≤H에서는

\[
K_+-K_-=
\begin{cases}
m(H-\mu)(u-L)/(H-L),&u\le\mu,\\
m(\mu-L)(H-u)/(H-L),&u\ge\mu.
\end{cases}
\]

따라서

\[
\sup_u(K_+-K_-)=
\frac{m(\mu-L)(H-\mu)}{H-L}
\le\frac{m(H-L)}4.
\]

마지막 부등식은

\[
\frac{H-L}{4}-\frac{(\mu-L)(H-\mu)}{H-L}
=\frac{(2\mu-L-H)^2}{4(H-L)}\ge0
\]

에서 따른다. Wolfram Language가 gap branch identity, 이 제곱식의 residual, 상계의 A-미분 계수를 각각 {0,0,(H−u)/(H−L)}로 확인했다.

서로 겹치지 않는 실제 측도 부분 ν_i의 mass와 moment를 알면 하·상계를 더한다. 각 child support가 parent support 안에 있고 질량·모멘트가 정확하게 더해지는 실제 refinement에서는

\[
K_-^{\rm parent}\le\sum_iK_-^{(i)}
\le K\le\sum_iK_+^{(i)}\le K_+^{\rm parent}.
\]

하계의 단조성은 parent 평균에 대한 Jensen를 child 평균에 적용하면 나온다. 상계의 단조성은 parent chord가 각 child endpoint의 g_u보다 크므로 child chord보다도 크다는 사실에서 나온다. 원자 개수를 새로 추정하는 가정은 필요하지 않다.

각 block의 support 폭을 Δ_i라 하면

\[
0\le K_+^{(n)}-K_-^{(n)}
\le\frac14\sum_i m_i\Delta_i
\le\frac{M\Delta_{\max}^{(n)}}4.
\]

고정된 유한 총질량에서 최대 폭이0으로 가면 전체 K 곡선에 대해 uniform convergence를 얻는다. **반드시 실제 bin 질량·모멘트를 추가로 관측해야 한다.** 집계평균을 임의 분할하거나 mean 원자를 진짜 분포로 선언해서 얻은 폭 감소는 이 정리에 해당하지 않는다.

Nonnested partition은 bin 수가 늘어도 단조성을 보장하지 않는다. 저장된 반례는 age i=0..8, mass (1+i mod3)/2에서 기존 bins0..4와5..8을 인접한 두 원자씩 묶은5개 bins로 교체한다. u=9/2에서 기존 정확한 K=37/4에 비해 새 하계는35/4로 낮아진다. 초기 검사의 실패는 이 비중첩 refinement 전제를 잘못 구성한 fixture였고, 해당 실패 로그와 반례를 보존했다.

## 5. 명제 3: censor와 CDF를 안전하게 연결

블록들이 원래 source의 최종 완료 질량 O를 나타내고, 고정 source M*≥O에서 미완료·미진입 질량 C=M*−O를 +infinity에 둔다고 하자. δ>0이면

\[
\boxed{
P(W_H\ge u+\delta)
\le\frac{C+\min(O,K_+(u)/\delta)}{M^*}.}
\]

각 완료 w≥u+δ는 (w−u)+≥δ이므로 완료 tail 질량은 K(u)/δ 이하이고, K≤K_+를 사용하면 된다. 미완료 질량은 분모에서 제거하지 않는다. 이것은 특정 내부 passage row collection을 자동으로 고유 차량 완료 모집단으로 바꾸는 식이 아니다.

**Pointwise envelope를 미분해서 CDF 상·하계라고 해석하면 안 된다.** 대신 h>0에서

\[
\frac{K(v)-K(v+h)}h\le O(w>v),\qquad
O(w>v)\le O(w\ge v)\le\frac{K(v-h)-K(v)}h
\]

를 사용한다. 따라서

\[
q_-(v)=\max\{0,[K_-(v)-K_+(v+h)]/h\},
\quad
q_+(v)=\min\{O,[K_+(v-h)-K_-(v)]/h\}
\]

이면 q_-≤O(w>v)≤q_+이고,

\[
\boxed{
\frac{O-q_+(v)}{M^*}\le F_H(v)\le
\frac{O-q_-(v)}{M^*}.}
\]

구현은 H_i≤v인 확정 below-or-equal 질량과 L_i>v인 확정 strict-tail 질량으로 이 구간을 추가로 좁힌다. 이 때문에 zero-width support 원자는 equality 방향까지 정확히 처리된다. 일반적인 atom에서는 backward secant에 equality mass가 포함되므로 넓은 구간이 남을 수 있다.

같은 h에서 실제 refinement는 K_-를 올리고 K_+를 내리므로 이 CDF 구간도 단조롭게 좁아진다. 관측 envelope의 uniform 오차를 ε_n라 하고, h_n→0 및 ε_n/h_n→0이면 실제 K의 양쪽 미분이 일치하는 지점, 즉 해당 age law의 continuity point에서 CDF 구간이 수렴한다. Atom에서 같은 결론을 추가 가정 없이 주장하지 않는다.

## 6. 명제 4: birth-moment 사상과 오차 민감도

공통 관측시각 t에 birth support b∈[b_-,b_+]와 birth-time mass B=∫b dν를 알면

\[
A=mt-B,\qquad L=t-b_+,\qquad H=t-b_-.
\]

b_+≤t를 요구한다. 시간 원점을 t→t+s,b→b+s로 옮겨도 A와 age support는 변하지 않는다. Native row의 mass와 birth moment를 사용할 때 같은 관측시각을 사용해야 한다. 모든 row에 snapshot t를 적용하면 결과는 **snapshot 시각의 event-incidence age measure**다. row별 end를 적용한 passage age measure와 다르며, 어느 쪽도 자동으로 최종 journey 완료 지연을 뜻하지 않는다.

고정 m,L,H에서 K_-는 A에 대한1-Lipschitz 함수다. K_+의 기울기는 [g_u(H)−g_u(L)]/(H−L)∈[0,1]이므로 역시1-Lipschitz다. 따라서 실제 A와 기록값 Â 사이에 **별도로 입증된** |A−Â|≤ε가 있으면 하계를 ε만큼 낮추고 상계를 ε만큼 높인 구간이 안전하다. 실제 구현은 exact Fraction 입력에 대한 결과이며, native 계산의 ε를 임의로 지정하거나0으로 추정하지 않는다.

## 7. 구현·검증 계약

파일:

- `src/metroflow/v1/age_moment_envelope.py`
- `tests/research/test_v03_age_moment_envelope_20261123.py`

API:

- `AgeMomentBlock(mass, age_moment, lower_age, upper_age)`: 양의 측도 가능 조건 검사.
- `from_birth_moment(m,B,t,bmin,bmax)`: 외부에서 입증한 birth support를 age support로 변환.
- `stop_loss_envelope(blocks,u)`: 원래 mass/moment, 하·상계, uniform gap 상한.
- `censored_tail_upper_bound(envelope,delta,assigned_source_mass)`: censor 포함 tail 상계.
- `cdf_envelope(blocks,v,h,assigned_source_mass)`: strict-tail secant 및 support에 따른 CDF 구간.

재현 명령:

```bash
PYTHONPATH=src python3 -m pytest -q -s tests/research/test_v03_age_moment_envelope_20261123.py --tb=short
```

실제 결과: **10 passed**, `EXACT_ENVELOPE_CASES=2790 EXACT_CDF_CASES=2520 MAX_GAP_RATIO=1/4`. 로그: `artifacts/v03_event_store_envelope_20261123/C5_python_envelope_tests.log`. 실패한 초기 nonnested fixture 로그: `C5_non_nested_fixture_failure.log`. Import 실패를 행동 RED로 부르지 않았고, 표본 통과를 보편적 정리의 증명으로 대체하지 않았다.

## 8. 원전 연결

[Huang, Ziemba & Ben-Tal (1977), Operations Research 25(2),315–325](https://pubsonline.informs.org/doi/10.1287/opre.25.2.315)의 publisher 초록은 Jensen와 Edmundson–Madansky를 작은 support 구간에 순차 적용하는 방법을 명시한다. 여기의 refinement 발상은 이 기존 계보에 속한다.

[Pierre-Louis, Bayraksan & Morton (2011), WSC, §3.1, p.4174, 식(2)(3)](https://www.informs-sim.org/wsc11papers/371.pdf)의 실제 PDF에서 conditional Jensen 하계와 endpoint-support 상계를 확인했다. 이 논문의 다변량 문제에는 독립성 가정이 있지만, 본 문서의 한 차원 age block 및 disjoint measure 합에는 변수 간 독립성을 가정하지 않는다.

Madansky (1959), Annals of Mathematical Statistics30,743–746, [DOI10.1214/aoms/1177706203](https://doi.org/10.1214/aoms/1177706203)의 서지정보는 Exa와 SciSpace에서 확인했다. DOI 본문 접근은 실패했고, 원저자의 [RAND P-1418 (1958)](https://www.rand.org/pubs/papers/P1418.html) 초록은 Parallel에서 확인했다. 따라서 그 원문의 특정 정리 번호를 읽었다고 주장하지 않는다. 본 명제들은 위에 직접 증명을 제공했다.
