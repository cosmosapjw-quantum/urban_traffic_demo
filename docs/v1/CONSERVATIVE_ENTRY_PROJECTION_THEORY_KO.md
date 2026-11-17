# V03 진입시간 측도의 보존적 투영: 이론과 적용 범위

기준 코드: `0b9caa8cc60a3ba087722e0360b997c5dfb61d62`. 연구일: 2026-11-17.
구현 계약은 [설계 문서](CONSERVATIVE_ENTRY_PROJECTION_DESIGN_KO.md)의
`entry_projection_support_v1`을 따른다.

## 1. 선택한 개선과 원래 모델의 관계

최신 보고서의 선택지 A, **오차를 명시하는 interval 집계**를 채택한다.
전체 주민과 수요, 24시간 연구 목표, 유한 응답시간을 가진 운동, 공동 도로의
수신 용량·저장공간, 차종·목적·정보·경로를 유지하면서 진입시간 분포의 표현을
유한 해상도로 바꾸는 선택이다. 정확한 부분서비스를 거듭할 때 생기는 모든
시간 조각을 영구적인 독립 상태로 보관하는 요구를 완화한다.

선택지 B의 FIFO·서비스 규칙 변경은 물리적 가정을 바꾸고, 선택지 C의 규모
축소는 관측하려는 도시 문제를 바꾼다. A도 결과가 달라질 수 있는 수치 근사다.
따라서 기존 정확 경로를 기본값과 비교 기준으로 보존하고, 정책을 켠 결과에는
시간폭과 정책 identity를 함께 남긴다. 앞선 exact merge의 작은 압축률과 자원
실패는 해당 표현의 비용 근거이며, 원래 교통 모델에 대한 불가능성 정리는 아니다.

이 선택은 집단의 운동과 교통 상호작용을 보존하면서 내부 표현을 줄이려는
mesoscopic 관점에 맞는다. Daganzo의 다중 목적지 network CTM도 입장시간
cohort로 FIFO를 표현하며, 같은 simulation clock 구간 안의 순서는 별도로
구별하지 않는다는 근사를 명시한다.[1] 여기서 사용하는 운동·서비스식은 그
논문의 CTM과 동일하지 않지만, 시간 해상도를 갖는 목적지별 cohort라는 선택은
관련된 선행 방법이다.

## 2. 코드가 계산하는 물리적 모델

### 분포에서 공통 속도 closure까지

연속적인 위치와 속도, 구별되는 차종·목적·정보·경로를 연결하는 기초적인 표현은
link 위의 측도

\[
f_\alpha(x,v,p,I,\mathcal R,t)
\]

다. \(\alpha\)는 차종과 활동 종류, \(x\)는 link를 따라 잰 거리[m],
\(v\)는 속도[m/s], \(p\in[0,1]\)는 latent 활동 성향,
\(I\)는 그 시각에 이용 가능한 정보, \(\mathcal R\)은 남은 경로다.
속도와 mark를 적분하면 공간 차량밀도[veh/m]가 된다. 이 표기는 코드의 모든
상태를 하나의 원래 분포로 읽기 위한 대응이며, 코드가 이 분포를 전부 저장하거나
다음 운동론 방정식을 직접 푼다는 주장은 아니다.

예를 들어 transport와 deterministic mark evolution은 형식적으로

\[
\partial_t f_\alpha+v\partial_x f_\alpha
+\partial_v(A_\alpha f_\alpha)
+\partial_p(G_\alpha f_\alpha)
=\mathcal Q_\alpha[f]+\mathcal S_\alpha
\]

처럼 쓸 수 있다. \(\mathcal Q\)에는 선택한 상호작용·경로 갱신이,
\(\mathcal S\)와 graph 경계조건에는 출발·도착·노드 이관이 들어간다.
어떤 항을 실제로 해상하고 어떤 항을 모멘트로 닫는지를 지정해야 계산모델이 된다.
gas-kinetic traffic 모형에서도 유한 가속 응답에서 출발한 뒤 속도분산과 분포
형태에 관한 별도의 closure를 사용한다.[2]

현재 T02/T04는 link의 공통 속도 \(u\)와 class별 \(p_c\)를 사용한다.
속도분포를 \(\delta(v-u)\)로 나타내는 공통 속도 근사와 유사하지만, 실제
구현은 연속 공간 PDE 전체보다 더 집계된 link 운동 및 FIFO cohort 모형이다.
서로 다른 차량의 속도분산·gap 분포·고차 상관은 이 상태에 남아 있지 않다.

`docs/v1/t02/CLOSURE_KO.md`와 `src/metroflow/v1/kinetics.py`의 실제 식은

\[
N=\sum_c n_c,\qquad w_c=n_c/N,\qquad
\bar g=\frac{L_{\rm lane}-\sum_c n_c\ell_c}{N},
\]

\[
U=\min_c U_c(\bar g,\mathrm{cap}),\qquad
\nu_c=\beta_c\left(\frac{s_c}{\bar g+\ell_c}\right)^2,
\]

\[
\dot p_c=r_c(1-p_c)-\nu_c p_c,
\qquad
\dot u=\operatorname{clip}\!\left(
\sum_c w_c\frac{U p_c-u}{\tau_c},
-\min_c b_c,\min_c a_c\right),
\qquad \dot x=u.
\]

여기서 \(n_c\)[veh], \(\ell_c,L_{\rm lane},s_c,\bar g\)[m],
\(\tau_c\)[s], \(r_c,\nu_c,\beta_c\)[s\(^{-1}\)],
\(a_c,b_c\)[m/s\(^2\)]다. \(N=0\)은 별도의 vacuum 경로다.
밀도·조성·cap을 한 local interval에 고정하고 \(p\) half-step,
동일 held characteristic의 속도·거리 적분, \(p\) half-step을 수행한다.

\(p_c\)를 고정하면

\[
\tau_{\rm eff}^{-1}=\sum_c\frac{w_c}{\tau_c},\qquad
V=U\frac{\sum_c w_c p_c/\tau_c}{\sum_c w_c/\tau_c}
\]

를 사용해 비포화 가속도를 \((V-u)/\tau_{\rm eff}\)로 쓸 수 있다.
이는 유한 응답을 보존한다. 실제 속도를 즉시 \(U\sum_c w_cp_c\)로 바꾸는
것은 같은 모형이 아니다.

### 이번 투영이 보존하는 것과 남는 물리적 제한

이번 수정은 위 운동식을 바꾸지 않는다. 한 admission cohort의 category별
질량을 보존하므로, 투영 직후의 \(N\), \(w_c\), 점유길이,
\(\bar g\), 최초 T02 계수는 동일하다. `FiniteResponseMotion.admit`가 사용하는
incoming speed·latent 모멘트도 원래 mark 적분을 그대로 사용한다. 이후의
서비스 순서가 달라져 유출 조성이 변하면 다음 step의 운동은 달라질 수 있다.

공통 속도 closure에는 이미 비매끄러운 경계가 있다. 아주 작은 양의 slow-class
질량도 \(\min_c U_c\)를 결정할 수 있고, 아주 작은 blocked-destination
질량도 strict FIFO head의 서비스를 막을 수 있다. 작은 질량을 삭제하는
cutoff는 이 가정 아래에서 작은 물리적 변화로 보장되지 않는다. 이번 정책은
양의 질량과 category를 유지하고, 표현할 수 없는 underflow를 명시적 실패로
처리한다.

평균 gap만으로 hazard를 계산하는 제한도 그대로다.
\(\phi(g)=\beta s^2/(g+\ell)^2\)는 \(g\ge0\)에서 convex이므로
일반적으로 \(\mathbb E\phi(g)\ne\phi(\mathbb E g)\)다.
이 구분과 공통 속도 내부의 분산 손실은 T02 문서의 기존 결과를 재사용한다.
이번 시간측도 개선을 gap·velocity 분포까지 검증한 결과로 확대하지 않는다.

## 3. 투영할 대상과 순서

한 link의 한 admission step에서 동일한 운동 target을 가진 incoming
`Part`만 함께 처리한다. 다른 link·target·admission step은 섞지 않는다.
원래 part는 \((\mathrm{tag},\mathrm{remaining})\)이라는 category,
질량 \(m_i>0\), 원래 출생시간 1차 모멘트 \(B_i\)[veh·s],
균일 진입 구간 \([a_i,b_i]\)를 가진다. \(a_i=b_i\)이면 point atom이다.
원래 interval 안의 birth mark는 그 part의 일정한 조건부 평균이라는 기존
T04 가정을 사용한다.

폭 \(h>0\)[s], 원점 0의 고정 시간격자에 다음 경계를 더한다.

- 양의 interval들이 가지는 즉시 다음 movement의 지지집합이 바뀌는 시각.
- 모든 원래 point admission 시각.
- 입력의 첫 시각과 마지막 시각.

다음 movement는 `remaining`의 다음 lane group이며 마지막 link의 sink는
독립적인 목적지로 취급한다. 기존 driver의 신호·폐쇄 경계는 admission step을
이미 나누므로 이 정책은 그 경계를 가로질러 결합하지 않는다.

원래의 모든 endpoint를 이용해 elementary packet을 만든 뒤 합치는 방식은
피한다. endpoint sweep에서 movement별 active count를 갱신해 **support가
달라지는 경계만** 추출한다. 점근적인 sweep 비용은 \(O(P\log P)\)이며,
Python 투영은 각 원 interval이 통과하는 격자·보호 경계만 방문한다.
현재 Rust 구현은 K개의 선택된 segment마다 P개의 입력을 다시 훑으므로
적분 비용이 O(PK)다. all-endpoint packet을 전개하지 않지만, K가 커지면
이 재스캔 자체가 다음 성능 병목이 될 수 있다.
category 다양성이나 실제 support 전환 수와 무관한 일정 메모리를 보장하지는
않는다. 기록·byte 예산과 실패 checkpoint는 계속 필요하다.

point atom은 원래 시간을 보존한다. 서로 다른 atom 시각은 별도 순서를
가지며, 동일 시각 atom들은 기존 규칙대로 한 exchangeable packet을 이룬다.
그 시간에서 끝나는
양의 interval cohort 뒤, 같은 시간에서 시작하는 양의 interval cohort 앞에
둔다. 따라서 이산 출발·서비스 사건이 주변 연속 flux에 흡수되지 않는다.

## 4. 질량과 시간 모멘트 보존의 유도

보호 경계를 적용한 segment를 \(J=[L,R]\)라고 하자.
원 interval \([a_i,b_i]\), \(a_i<b_i\)와의 교집합을
\([\alpha_i,\beta_i]\)로 쓰면

\[
\widetilde m_i=m_i\frac{\beta_i-\alpha_i}{b_i-a_i},
\qquad
\widetilde B_i=B_i\frac{\beta_i-\alpha_i}{b_i-a_i},
\qquad
\widetilde T_i=\widetilde m_i\frac{\alpha_i+\beta_i}{2}.
\]

길이가 0인 교집합은 양의 interval 질량을 만들지 않는다. 각 category \(k\)에
대해

\[
M_k=\sum_{i\in k}\widetilde m_i,\qquad
B_k=\sum_{i\in k}\widetilde B_i,\qquad
T_k=\sum_{i\in k}\widetilde T_i,\qquad
\mu_k=T_k/M_k
\]

를 계산한다. 그 category의 진입시간 측도를

\[
\nu_k(dt)=\sum_{i\in k}
\frac{\widetilde m_i}{\beta_i-\alpha_i}
\mathbf 1_{[\alpha_i,\beta_i]}(t)\,dt
\quad\longmapsto\quad
\widehat\nu_k=M_k\delta_{\mu_k}
\]

로 투영한다. 출력 `Part`에는 \(M_k,B_k\)와 진입시간
`entry_start_s=entry_end_s=mu_k`를 남긴다. 실수 산술에서

\[
\int d\widehat\nu_k=\int d\nu_k=M_k,
\qquad
\int t\,d\widehat\nu_k=\int t\,d\nu_k=T_k
\]

이며 birth moment \(B_k\)도 그대로다. 같은 category의 interval 분할·표현
순서는 이 합에 영향을 주지 않는다. 양의 가중 평균이므로
\(L\le\mu_k\le R\)이고, 원래 incoming 구간이 현재 admission 시간 이전이면
투영점도 그 이전이다.

**segment 하나가 FIFO cohort packet 하나다.** category가 다른 Part들은
그 packet 내부에 별도로 남긴다. category별 평균점은 보존된 entry moment의
표현이며, 다시 exact `interval_packets`에 넣어 평균점마다 새 packet을 만들지
않는다. packet 사이의 순서는 보존하지만 segment 안의 조성 순서는
exchangeable로 근사한다. 정확한 원래 분포와 같다는 뜻은 아니다.

비교하면 제거되는 시간분산은 정확히

\[
\int t^2\,d\nu_k-M_k\mu_k^2
=\sum_{i\in k}\widetilde m_i
\left[\frac{(\beta_i-\alpha_i)^2}{12}
+\left(\frac{\alpha_i+\beta_i}{2}-\mu_k\right)^2\right].
\]

0차·1차 모멘트 보존과 2차 이상의 정보 손실을 함께 명시하는 이유다.
bin마다 필요한 모멘트를 보존하면서 representation을 바꾸는 접근은
moment-preserving resampling 문헌에도 사용된다.[3] 그 문헌의 plasma 검증은
이 traffic 정책의 네트워크 정확도를 대신하지 않는다.

## 5. 국소 Wasserstein 비용과 해석

동일 질량 \(M_k\)를 가진 두 측도에 대해, 여기서는 거리 비용을 질량으로
정규화하지 않은 \(W_1\)을 사용한다. 따라서 단위는 veh·s다. 출력 측도가
한 점에 집중되므로 원래 모든 질량을 \(\mu_k\)로 운반하는 coupling만 가능하고

\[
W_1(\nu_k,M_k\delta_{\mu_k})
=\int |t-\mu_k|\,d\nu_k(t)
\equiv E_k.
\]

uniform 부분구간 \([a,b]\)에서 평균점 \(c\)까지의 단위질량 비용은

\[
d(a,b,c)=
\begin{cases}
|(a+b)/2-c|,&c\le a\ \text{또는}\ c\ge b,\\[3pt]
\dfrac{(c-a)^2+(b-c)^2}{2(b-a)},&a<c<b.
\end{cases}
\]

따라서 \(E_k\)는 clipped 부분구간들의 \(\widetilde m_i d_i\) 합으로 직접
계산할 수 있다. 이번 정책에서 원래 point atom은 이동하지 않으므로 그 비용은 0이다.

### 폭에 의한 사전 상한

정규화한 random variable \(T\in[L,R]\)의 평균을 \(\mu\)라고 하자.
\(|t-\mu|\)의 convexity로 그래프는 양 끝점을 잇는 chord 아래에 있으므로

\[
|t-\mu|\le
\frac{R-t}{R-L}(\mu-L)
+\frac{t-L}{R-L}(R-\mu).
\]

평균을 취하면

\[
\mathbb E|T-\mu|
\le\frac{2(\mu-L)(R-\mu)}{R-L}
\le\frac{R-L}{2}.
\]

따라서 segment 폭이 \(R-L\le h\)이면

\[
E_k\le\frac{M_k(R-L)}2\le\frac{M_kh}2,
\qquad
\sum_kE_k\le\frac{h}{2}\sum_kM_k.
\]

이것은 **이번 투영 전후의 시간측도에 관한 실수 산술 결과**다. 임의 Lipschitz
검사함수 \(\varphi\)에 대해서는

\[
\left|\int\varphi\,d\nu_k-\int\varphi\,d\widehat\nu_k\right|
\le \operatorname{Lip}(\varphi) E_k
\]

가 따른다. \(E_k/M_k\)는 초 단위의 평균 운반량이다.

여러 투영에서 기록한 \(E_k\)의 합은 누적 **국소 표현 이동량**이다.
각 투영 사이의 nonlinear traffic evolution이 해당 거리에서 안정적이라는
추가 정리 없이, 그 합을 전체 통행시간·완료곡선·궤도 오차 상한으로 사용할 수 없다.
부동소수점 구현에서는 보존 잔차와 이 상한의 roundoff를 따로 점검하며,
실수 산술의 등식을 bit identity로 바꾸어 주장하지 않는다.

## 6. support 보호가 해결하는 문제와 남는 문제

즉시 다음 movement support가 달라지는 경계를 보존하면 open-only cohort에
뒤따르는 blocked turn을 새로 섞어 앞부분까지 막는 단순 반례를 방지한다.
한 segment의 각 내부 시각에서 합성 유입 측도의 destination support가 일정하므로,
그 support에 수신 용량 0인 목적지가 있으면 원래 조성과 투영 조성 모두 그
제약을 포함한다. 전체 조성비까지 같을 필요는 없다.

그러나 비율이 변하면 양의 receiving capacity와 footprint 제약에 걸리는
서비스율이 달라질 수 있다. 공통 next movement를 지난 뒤 남은 경로가 갈라질
수도 있다. 이 때문에 support 조건은 정확한 동역학적 동등성 정리가 아니다.

신호도 별도 민감성을 가진다. green이 \(t_g\)에서 끝나고 red가 \(T_R\)초
지속되는 한 차량을 생각하면, endpoint 도달시각을
\(t_g-\varepsilon\)에서 \(t_g+\varepsilon\)로 옮긴 입력의 시간측도 비용은
\(2m\varepsilon\)이지만 추가 대기는 \(T_R\)에 가까울 수 있다.
입력측도 비용이 작다는 것만으로 신호가 있는 시스템의 통행시간 오차가 작다고
결론내릴 수 없는 국소 반례다. admission step의 control 경계 보호는 직접적인
경계 혼합을 막지만, 후속 운동에서 신호에 도달하는 시각까지 고정하지는 않는다.

따라서 폭 \(h\)와 운동 적분 step \(\Delta t\)를 독립적으로 줄여 실제
완료곡선·대기·class/destination flux를 비교한다. 정확한 입력 수요와 과거
수용 기준을 유지한 대조가 필요하며, 자원 성공만으로 과학적 수용을 결정하지 않는다.

## 7. 검산 결과와 코드 검증으로 넘기는 항목

### 실제 확보한 근거

- 위 질량·모멘트 보존 및 \(Mh/2\) 상한은 명시한 조건 아래 직접 유도했다.
- 독립 SymPy 실행에서 uniform interval의 절대편차 적분 폐형식 잔차가 0이었다.
  비교 후보인 positive two-endpoint projection의 질량·시간모멘트·coupling
  비용 공식도 잔차 0으로 검산했다. 두-endpoint 후보는 현재 채택한 정책이 아니다.
- 주 실행자가 수행한 Wolfram Language evaluator는 uniform interval의
  질량·시간 1차 모멘트·중점까지의 절대 운반량으로
  `{m, m(a+b)/2, m(b-a)/4}`를 반환했다. 이는 단일 uniform interval의 평균점
  투영 검산이다. 별도의 WolframContext 호출은 internal error로 실패했으며,
  그 검색 실패를 이 대수 검산의 실패나 성공으로 대체하지 않는다.
- 기존 코드·문서를 읽어 T02 공통 속도 closure와 T04 incoming boundary,
  entry interval 분할, birth-moment 장부의 연결을 확인했다.

### 구현·수치 검증 의무

아래 항목의 실행 결과와 범위는
`artifacts/v1_entry_projection_20261117/RECEIPT.json`에 명령·버전·출력으로
기록한다. 40초 합성 교통망에서 Python/Rust 대조, 폭·dt 분리 대조와 재실행을
수행했으며, 국소 테스트와 native checkpoint 회귀를 실행했다. 도시 규모의
정확도와 전체 24시간 수용은 별도 의무다.

1. 겹치는 unequal interval, point atom, 같은 category의 재분할에서 질량·birth
   moment·entry moment와 양성성 검사.
2. open/blocked support 변화, A/B/A 순서, 정확한 point 경계 순서 검사.
3. 폭 0의 기존 정확 경로 회귀, 새 정책과 폭의 model/checkpoint identity 분리.
4. Python projection oracle와 Rust incoming 경로의 같은 입력 비교.
5. \(h,h/2\) 및 별도의 \(\Delta t,\Delta t/2\) 대조에서 완료곡선,
   destination/class split, queue·storage, vehicle-seconds와 peak records 측정.
6. 큰 절대시각, 해상되지 않는 폭, underflow, byte/record 예산 실패 시 원자성과
   마지막 유효 checkpoint를 검사한다. 투영 진단은 checkpoint 상태가 아니며
   가장 최근 검증된 proposed road transition에 관한 값이다. 결합 상태의
   rollback보다 앞선 값일 수 있으므로 누적 물리량처럼 재사용하지 않는다.

전체 3개 도시 × 3회 × 24시간과 원격 전체 CI의 성공 여부는 실제 실행 근거로
별도 판정한다. 국소 유도나 소형 사례만으로 V03의 완료 상태를 올리지 않는다.

## 8. 이론 루프의 현재 결과

| 단계 | 이번 단위의 산출물과 근거 상태 |
|---|---|
| R1 연구 위치 | 최신 V03 표현 폭증과 전체 수요 목표를 확인하고 A를 선택했다. |
| R2 근거 재사용 | T02/T04·foundation 접근측도 결과와 아래 원 논문을 대조했다. |
| R3 전제 정렬 | 공통 속도 closure, uniform interval·birth mark, category·support 계약을 구별했다. |
| R4 표현 탐색 | exact merge, 평균점 cohort, 고정 두-endpoint 투영을 비교해 평균점 cohort를 채택했다. |
| R5 구성적 유도 | category별 0·1차 모멘트 보존, 양성성, 분산 손실, 국소 \(W_1\) 식과 상한을 유도했다. |
| R6 독립 검증 | SymPy와 Wolfram의 uniform 검산, support·신호 반례를 확인했다. |
| R7 판별 검증 | 국소 대수·Python/Rust·소형 network의 h 및 dt 분리 대조를 실행했다. 통합 영수증에 실제 범위와 차이를 기록한다. |
| R8 판정 | 명시적 수치 근사로 채택했다. 전체 네트워크 오차·성능의 수용 판정은 남아 있다. |
| R9 코딩 연결 | 설계 문서에 incoming-before-refinement, 보호 경계, identity, 실패 동작을 연결했다. |
| R10 보존·재개 | 이론·설계·코드·영수증·인계문을 보존한다. 다음 의무는 도시별 정확 경로 대조와 전체 캠페인 수용이다. |

## 참고문헌과 확인 범위

**[1]** C. F. Daganzo, “The cell transmission model, part II: Network traffic,”
*Transportation Research Part B* **29**(2), 79–93 (1995).
[원기관 기록](https://www.its.berkeley.edu/publications/cell-transmission-model-part-ii-network-traffic),
[기관 보존 working paper 본문](https://escholarship.org/content/qt9pz309w7/qt9pz309w7_noSplash_2634ec43bcb4b8626621535d438de62a.pdf),
[DOI](https://doi.org/10.1016/0191-2615(94)00022-R).
Exa에서 기관 abstract와 원 논문 본문을 제공하는 author-paper mirror를 확인했다.
Section 4의 destination·waiting cohort와 같은 clock interval 내부의 FIFO
해상도 제한을 재사용했다. 현 코드와 같은 방정식이라는 근거로 사용하지 않았다.

**[2]** M. Treiber, A. Hennecke and D. Helbing, “Derivation, properties, and
simulation of a gas-kinetic-based, nonlocal traffic model,” *Physical Review E*
**59**, 239–253 (1999).
[저자 preprint](https://arxiv.org/abs/cond-mat/9901240),
[원문](https://arxiv.org/html/cond-mat/9901240),
[DOI](https://doi.org/10.1103/PhysRevE.59.239).
Exa 원문과 SciSpace 서지 검색을 교차 확인했다. 유한 acceleration relaxation과
kinetic-to-macroscopic closure의 역할을 참고했다. arXiv HTML rendering의
표시일과 별도로 출판연도는 arXiv 서지·저널 reference의 1999년이다.

**[3]** D. Faghihi, V. Carey, C. Michoski, R. Hager, S. Janhunen, C. S. Chang and
R. D. Moser, “Moment preserving constrained resampling with applications to
particle-in-cell methods,” *Journal of Computational Physics* **409**, 109317 (2020).
[저자 preprint](https://arxiv.org/abs/1702.05198),
[OSTI 기록](https://www.osti.gov/pages/biblio/1648522),
[DOI](https://doi.org/10.1016/j.jcp.2020.109317).
Parallel와 Exa에서 phase-space bin별 constrained moment preservation 방법을
확인했다. ScienceDirect 직접 추출은 timeout이었고 저자 preprint·기관 기록으로
보완했다. 이 문헌을 본 traffic projection의 독립적인 수렴 증명으로 사용하지 않았다.

검색·확인일은 2026-11-17이다. 위 비교는 채택한 construction의 가까운 방법론을
확인한 범위이며 포괄적인 신규성 또는 최적성 주장은 하지 않는다.
