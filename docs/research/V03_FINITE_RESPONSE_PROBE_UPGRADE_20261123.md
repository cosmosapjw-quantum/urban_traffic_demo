# 완료 통과 관측에서 유한응답 경로 시간으로 — R8 이론 보강

## 결과와 근거 상태

기존 FIFO–Γ 포락선의 정리와 구현은 유지한다. 이번 보강은 알려진 전역 속도 범위를 비교 기준에 포함했을 때 그 물리 실험이 관측의 추가 이득을 입증하지 못했다는 해석 공백을 교정한다. 유한응답 운동의 기억을 사용해 완료된 통과 적분에서 현재 속도 구간을 유도하고, 이를 미래 거리·도착시각 구간으로 전파한다. 전역 속도 범위만 사용할 때 선택되는7s 경로가 새 관측으로5s 경로로 바뀌는 사례를 구성했다.

- **derived:** 완료 통과 → endpoint 속도 → 전달 뒤 속도 → 미래 도착 bound.
- **derived, exact rational decision:** 주어진 두 경로에서 관측이 제공하는 strict dominance. 부동소수점 root의 반올림에 의존하지 않는다.
- **numerically checked / implementation-verified:** 연구 모듈,11개 표적 테스트,84개 보류 통과와120개70-digit Decimal root 비교.
- **unresolved:** 일반 native queue/spillback의 양의 forcing bounds 인증과 matched boundary 자동 계측. Production routing과 V03 수용 조건은 변경하지 않았다.

## 1. 이전 Γ 실험의 정확한 의미

공간적으로 균질한 속도에 알려진 양의 범위 a≤v≤b가 있으면, 길이 ℓ의 전역 통과시간은 ℓ/b≤T≤ℓ/a다. 기존 운동학적 certificate는 Γ=b/a를 제공했다. 완료된 표본 entry x, exit u와 예측시각 t≥d≥u에 대해 Γ-envelope의 미래 duration cap은

    u + Γ(t−x) − t
    = (u−x) + (Γ−1)(t−x)
    ≥ Γ(u−x)
    ≥ Γℓ/b = ℓ/a.

표본 여러 개의 최소값을 취해도 이 비교는 유지된다. 따라서 이 특별한 Γ certificate의 완료 표본은 이미 알려진 전역 속도 upper-duration ℓ/a보다 좁은 미래 upper를 주지 않는다. 이는 기존 declared Γ-function class의 sharpness나 FIFO composition 명제가 틀렸다는 뜻이 아니다. 그 클래스에 양의 물리 속도 범위를 추가한 뒤의 **관측 정보 이득**에 대한 비교다. 기존 R7 manufactured oracle의 interval 포함·경로 dominance는 그 자체로 유효하지만, 알려진 속도 범위에 비해 관측이 경로 판단을 개선했다는 증거로 사용하면 안 된다.

이 비교에서 멈추지 않고, 같은 finite-response 배경식이 가진 시간 기억을 사용한다.

## 2. 정의·모델·관측 계약

하나의 고정된 공간적으로 균질한 traffic context에서

    τ dv/ds = V(s) − v(s),       τ>0,
    0<a≤V(s)≤b,                a≤v(x)≤b

를 가정한다. V는 측정 가능·국소 유계이면 충분하고, v는 절대연속인 해다. 변화율·계수 τ와 forcing 범위는 사전에 인증된 입력이다. probe 하나로 이를 추정하지 않는다. 양의 불변 speed interval은 variation-of-constants 식에서 바로 나온다.

관측은 동일한 ordered boundary label의 정확한 entry x, exit u, 통과 거리 L이다.

    T=u−x>0,    L=∫[x,u]v(s)ds,    a≤L/T≤b.

이 표본의 전달은 u≤delivered≤d에서 완료되어야 한다. d가 의사결정 시각이다. Event birth age, 반복 event-incidence 평균, completed-population 평균을 이 L/T로 대체하지 않는다. 미래 질의에서도 같은 traffic context와 forcing bounds가 exit까지 유효해야 한다. 유한 수요의 재경로화가 장 자체를 바꾸는 효과는 포함하지 않는다.

SI 단위는 x,u,d,T,τ,h가 s, L,ℓ가 m, v,V,a,b가 m/s다. 아래 α와 지수의 인자는 무차원이다. 정지·spillback처럼 양의 a가 성립하지 않는 상태는 이 정리의 적용 범위 밖이다.

## 3. 명제 — 완료된 적분으로 endpoint 속도 구간 구성

A=τ(exp(T/τ)−1), α=T/A라 놓는다. T>0이면 A>T이고0<α<1이다. 그러면

    v(u) ∈ [ α(L/T)+(1−α)a,  α(L/T)+(1−α)b ].

관측이 모델과 양립하면 이 구간은 [a,b] 안에 있다.

**증명.** Endpoint v(u)에서 backward variation-of-constants를 쓰면, 0≤s≤T에서

    v(x+s) = exp((T−s)/τ)v(u)
             − (1/τ)∫[s,T] exp((r−s)/τ)V(x+r)dr.

이를 s에 대해 적분하고 적분 순서를 바꾸면

    L = A v(u) − ∫[0,T](exp(r/τ)−1)V(x+r)dr.

커널은 비음이고 적분은 A−T이므로, 마지막 적분은 [a(A−T),b(A−T)]에 들어간다. 양수 A로 나누면 원하는 구간이다. L/A의 단위는 m/s이고 α=T/A는 무차원이므로 차원이 일치한다.

이 결과는 일반적으로 최적 도달가능 집합 전체의 sharpness를 주장하지 않는다. 초기 속도 범위가 특정 극단 forcing 이력과 양립하지 않으면 더 좁힐 수 있다. 아래 판별례에서는 두 극단 forcing 이력의 초기 속도가 실제 허용 범위 안에 있어 양 endpoint를 달성하는 물리 이력도 구성할 수 있다.

## 4. 명제 — 전달 지연과 미래 통과로의 전파

m=L/T, δ=d−u라 두면 decision speed의 유효 구간은

    l_d = a + α(m−a)exp(−δ/τ),
    r_d = b − α(b−m)exp(−δ/τ).

이는 endpoint 구간과 forward variation-of-constants, a≤V≤b에서 나온다. 따라서 모든 s≥d에 대해

    w_−(s)=a+α(m−a)exp(−(s−u)/τ) ≤ v(s)
    ≤ b−α(b−m)exp(−(s−u)/τ)=w_+(s).

미래 entry t≥d에서 duration h≥0 동안의 거리는 다음 사이에 있다.

    Q_−(t,h)=a h+τ α(m−a)exp(−(t−u)/τ)(1−exp(−h/τ)),
    Q_+(t,h)=b h−τ α(b−m)exp(−(t−u)/τ)(1−exp(−h/τ)).

새 길이 ℓ>0에 대해 Q_+(t,h_lo)=ℓ, Q_−(t,h_hi)=ℓ의 유일한 양의 해를 정의하면,

    ℓ/b ≤ h_lo(t) ≤ E(t)−t ≤ h_hi(t) ≤ ℓ/a.

**증명.** w_−와 w_+는 [a,b] 안의 양의 함수이므로 Q의 h 미분도 양수이고 a 이상이다. Q(t,0)=0, Q(t,h)→∞라서 각 root가 유일하다. 실제 passage의 거리 ℓ가 Q_−≤∫v≤Q_+ 사이에 있으므로 단조 역함수로 부등식을 얻는다. a h≤Q_−≤Q_+≤b h에서 전역 구간 안의 nesting도 따른다. a<m<b, 유한한 양의 τ와 유한한 t−u이면 두 exponential memory 항이 양수이므로 각 전역 endpoint보다 엄격한 개선이 생긴다. 이것은 실수 산술의 정리이며, underflow가 생긴 floating 구현이 그 엄격성을 항상 표시한다는 주장은 아니다.

각 양의 w에 대한 passage map은 누적 거리 F_w의 역함수로 E_w(t)=F_w^{-1}(F_w(t)+ℓ)다. 따라서 lower/upper arrival 함수도 엄격한 FIFO 함수다. 기존 `V03_FIFO_ROUTE_OBSERVABILITY_THEORY_20261123.md` Proposition3의 monotone composition과 legal-turn graph 비교를 그대로 적용할 수 있다. 이번 실행은 명시한 두 parallel legal route를 직접 비교한다. General native graph routing이나 production의 경로 선택 정책은 활성화하지 않았다.

**극한 점검.** 전달 지연 또는 예측 시간이 τ에 비해 커지면 기억은 사라지고 전역 [ℓ/b,ℓ/a]로 돌아간다. τ→0에서도 α→0이다. τ→∞에서는 α→1이고 유한한 δ,t−d에서 속도는 관측 평균 m에 고정되는 극한을 가져 양 root가 ℓ/m으로 수렴한다. a=b이면 처음부터 단일 상수 속도와 단일 통과시간이다.

## 5. 전역 속도 범위만으로는 결정되지 않는 실제 판별례

τ=10s, [a,b]=[1,3]m/s인 corridor A에서 참 해를 v=V=2m/s로 둔다. entry10s,exit15s의10m 통과를16s에 전달받고 즉시 결정한다. 계산은 다음과 같다.

    α = 0.5/(exp(0.5)−1) ≈ 0.7707470412683991,
    v(15) ∈ [1.770747041268399,2.229252958731601]m/s,
    v(16) ∈ [1.6974007627801533,2.3025992372198467]m/s.

같은 맥락의 다음10m 통과에 대한 수치 duration 구간은 약[4.1180114938,6.6224385552]s다. Departure16s의 arrival clock은 약[20.1180114938,22.6224385552]s이며 실제 arrival은21s다. 이 값들을 clock과 duration 사이에서 혼용하지 않는다.

경쟁 route B는 다른 인증된 corridor의14m를 상수2m/s로 통과하므로 정확히7s다.

| 사용한 정보 | A duration [s] | B duration [s] | upper-min 선택 | 참 해에서 regret |
|---|---:|---:|---|---:|
| 알려진 전역 속도 범위 | [10/3,10] | [7,7] | B | 2s |
| 완료 probe+유한응답 기억 | 약[4.1180114938,6.6224385552] | [7,7] | A | 0s |

A의 upper가 B의 exact lower보다 약0.37756s 작다. 결정의 엄격성은 approximate root에도 의존할 필요가 없다. 정확한 식은

    Q_−(16,7)=7+5 exp(−0.1)(1−exp(−0.7))/(exp(0.5)−1).

다음 유리수 비교를 쓴다.

- exp(−0.1)>9/10.
- exp(0.7)>1+7/10+(7/10)^2/2=389/200이므로1−exp(−0.7)>189/389.
- exp(0.5)의 n≤2 합은13/8이다. n≥3 첫 항은1/48이고 이후 항 비율은1/6보다 작으므로 tail<1/40, 따라서 exp(0.5)<33/20.

모든 항이 양수이므로

    Q_−(16,7)>7+5(9/10)(189/389)/(13/20)
               =7+17010/5057
               =52409/5057
               >10.

즉 A의 analytic worst-case duration은 엄격히7s보다 작다. 이 결과는 위 probe와 forcing 범위에 양립하는 모든 허용 이력에 대해 A의 robust dominance를 보인다. 참 상수 해에서의2s regret 제거는 그 보장의 한 실제 관측 사례다.

해당 probe endpoint bound의 극단 이력도 유효하다. 관측 구간에 V=a 또는 V=b를 두면 필요한 entry 속도는 각각

    v_x^(a)=1+0.5/(1−exp(−0.5)) ≈ 2.2707470413,
    v_x^(b)=3−0.5/(1−exp(−0.5)) ≈ 1.7292529587

로 [1,3] 안이다. 이후에도 각 극단 forcing을 유지하면 lower/upper speed field가 실현된다. 따라서 이 특정 probe에서는 미래 duration endpoint의 달성 이력까지 구성된다. 모든 probe의 global sharpness로 일반화하지 않는다.

## 6. 계산·구현·실행 근거

새 research-only 모듈:

    src/metroflow/v1/finite_response_probe_certificate.py

API는 completed matched passage, 명시적 context, 전달 완료 decision, τ와 양의 speed bounds를 요구한다. 비인과적·다른 context·잘못된 관측 종류·물리 범위와 모순되는 mean을 거절한다. expm1와 positive convex form을 사용해 작은/큰 T/τ 및 거리 적분의 cancellation을 줄였다. 양의 단조 거리식을 [ℓ/b,ℓ/a]에서 이분한다. 요구 tolerance에 도달하지 못하면 unresolved root로 오류를 낸다.

`NumericalDurationBounds`와 root brackets는 binary64 계산값이다. 일반적인 directed-rounding interval package 또는 전역 floating error 증명을 구현한 것은 아니다. Mathematical enclosure는 위 실수 정리이며, 이번 경로 dominance는 별도 exact rational argument로 닫았다.

실제 실행 명령:

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python3 -m pytest -q tests/research/test_v03_finite_response_probe_20261123.py
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. timeout 60s python3 artifacts/v03_origin_validation_20261123/R8_response_probe_experiment.py

첫 표적 실행은11passed,exit0,0.25s였다. Probe/causal/context 거부, 전역 nesting/FIFO, 단위 재척도, τ·지연 극한, 동일 speed의 collapse, 실제 extreme-forcing witness, 근 해상도 실패를 확인했다.

실험은 미래 데이터를 predictor에 전달하지 않고 다음84개를 확인했다.

- 참 상수 speed1.25/2/2.75m/s × entry16/17/20/25/40s × length2/5/10/20m =60개.
- 같은 v=2 완료 probe 뒤 decision16s에서 미래 forcing이1 또는3m/s로 바뀌는 해 × entry16/20/40s × 같은4개 길이 =24개.

모든 통과가 analytic bound의 floating 평가 안에 수치 tolerance2e−11s로 들어갔다.60개 상수 사례의 두 bound root, 총120개를 별도70-digit Decimal 식과 비교했고 최대 차이는9.215140108950740790481086699e−12s였다. 정확한 root 값과 모든 case 행, source 전후 hash를 JSON에 보존했다. 실제 experiment wall은0.771810545s,exit0이다. 유한 사례의 성공이 일반 정리의 증명 대신 사용되지는 않는다.

근거 파일은 `artifacts/v03_origin_validation_20261123/`의 `R8_response_probe_experiment.py/.json/.log/.exit`, `R8_response_probe_tests.log/.exit`, `R8_response_probe_manifest.json`이다. Manifest는 before/after source identity, 실제 Python·CPU와 실행 상태를 기록한다. 실제 root의 대규모 native 실험과 별개의 작은 연구 계산이며 V03 full-day credit은0이다.

## 7. 원 동기 drift watchdog와 남은 적용 의무

원 역사 `METROFLOW_ORIGINAL_INTENT_WATCHDOG.md`의 finite-response 교통 → 제한된 인과적 관측 → 설명 가능한 경로 선택 목표를 따른다. 기존의 느슨한 Γ-envelope 사례를 관측 정보의 실제 이득으로 과대해석하던 공백을 특정했고, τ의 기억을 통한 endpoint-speed 재구성으로 교정했다. 새 결과는 자료구조나 메모리 최적화 정리가 아니라 관측·예측에 관한 배경 이론의 구성적 업그레이드다.

판정은 `ALIGNED_WITH_OPEN_OBLIGATION`이다. 일반 native 혼잡에서 τ와 양의 forcing/velocity bounds가 해당 context에 실제로 성립하는지, exact matched boundary 자료를 어떻게 계측할지, 유한 수요 재경로화가 field를 바꾸는 효과는 미완료다. 기존 FIFO·수요·질량·f64 wire·dt·예산·V03 수용은 변경하지 않았다. 옛 정리나 수치 검산을 지우지 않고, 그 물리 해석을 더 강한 비교 기준으로 수정했다.
