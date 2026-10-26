# T02 선택한 유한응답 closure

이 문서는 `PLAN.json` T02의 국소 운동 계약이다. 기존 foundation_kinetics의 정확
characteristic과 gap_transport의 조건부 pair oracle를 재사용한다. 새 도시 solver를
만들지 않는다. PacketNetwork의 기존 p-only 운동은 아직 교체하지 않았으며 T03/T04가
아래 운동 표면을 소비한다. 전체 CI·통합·최종 수용은 사용자가 정한 별도 심사 뒤다.

## 상태, 단위, 선택

class별 차량량 n_c[veh], 길이 ell_c[m], 반응시간 tau_c[s], 유한 가감속 한계
 a_c,b_c[m/s²], latent 확률 p_c[1]를 가진다. N=sum n_c, w_c=n_c/N이다.
L_lane[m]는 차로 길이의 합이다. mean gap h=(L_lane-sum n_c ell_c)/N이며,
음수 공간은 PHYSICAL_INFEASIBLE로 거절한다. 진공은 별도로 speed=0을 쓴다.
양의 class mass만 받으며 최대 세 차종이다. 같은 class/law의 분할은 n과 n*p를
보존해 합치지만 다른 법칙이나 단위를 임의로 합치지 않는다.

관측 cap과 class별 gap 목표에서

    U = min_c min(U_preferred,c, cap, max(0,(h-h0_c)/T_c))
    nu_c = beta_c [s_c/(h+ell_c)]²
    p'_c = r_c(1-p_c)-nu_c p_c
    v' = clip(sum_c w_c(U p_c-v)/tau_c, -min_c b_c, min_c a_c)
    x' = v

를 하나의 선택된 V1 closure로 고정한다. r,beta는 s^-1, s_c는 m 단위의
선언된 합성 공학 prior다. 실제 속도 v는 연속이고 p는 실제 이동속도가 아니다.
유효 tau_eff=1/sum(w/tau), 목표 V=U sum(w*p/tau)/sum(w/tau)로 쓰면
동결 p에서 기존 characteristic의 형태가 된다. 단순 U*평균(p)와는 일반적으로 다르다.
공통 speed와 clip 이후의 평균화를 선택한 근사다. 개별 clipped 가속의 정확한
기대값이 위 식과 같다고 유도하지 않는다. 느린 class가 아무리 소수여도 양의
질량이면 U의 min에 들어가므로 그 질량이 정확히 0이 되는 경계는 불연속일 수 있다.
이는 명시한 공통 속도 closure의 제한이며 소수 차량량을 삭제해 숨기지 않는다.

## 적분과 비용의 동일성

한 local interval 동안 density/composition/관측 cap을 고정한다. p를 정확히 반 step,
중간 p를 고정한 v와 x를 기존 정확 characteristic으로 한 step, p를 다시 반 step
진화시킨다. p가 고정이면 정확해이고, p가 변하면 대칭 분할 근사다. 비포화 매끄러운
검산에서 dt/2에 따른 2차 수렴을 확인한다. clip 접합이나 환경 변화에서는 그 차수를
보편적으로 주장하지 않으며 후속 T04가 시간 해상도와 경계 flux를 검증한다.

동결 목표 V에서 비포화 구간은 v=V+(v0-V)exp(-t/tau_eff),
Δx=Vt+(v0-V)tau_eff(1-exp(-t/tau_eff))다. 포화 구간은 상수가속도를 정확히
적분해 접합한다. 새로운 cap보다 기존 v가 높아도 순간 잘라내지 않는다.

`predict_passage`는 동일 step들의 Δx를 누적하고, 도달하는 step 안에서는 그 step의
중간 p로 만든 동일한 held characteristic의 root를 푼다. partial root를 구한다고
midpoint를 다른 시각으로 다시 계산하지 않는다. 따라서 공급한 입력과 dt가 같으면
운송과 비용은 같은 수치 궤적이다. 미래 cap/density의 실제값은 입력받지 않으며
환경 stamp>현재 clock은 거절한다. 비용은 현재 허용된 환경을 고정한 예측이다.
실제 미래 통행시간 또는 비예견 routing 전체의 증명으로 확대하지 않는다.

정지 목표의 asymptotic coast 거리를 넘는 경우 UNREACHABLE, horizon 내 도달하지
못한 경우 HORIZON_REACHED, step 예산 초과는 checkpoint를 붙인 BLOCKED_RESOURCE다.
비용을 유한하게 만들기 위한 임의의 speed floor나 질량 삭제를 쓰지 않는다.

## 연속 latent reference와 분산

동종·동결 U,r,nu에서 실제 개별 속도가 v'=(U sigma-v)/tau를 따르고
sigma가 0/1 Markov 제어 상태라는 조건부 reference를 둔다. 개별 속도 두 값이라는
가정은 아니다. clipping이 없는 이 reference에서는

    p'=r-(r+nu)p, m'=(Up-m)/tau
    q'=(Up-q)/tau+r*m-(r+nu)*q, z'=2(U*q-z)/tau

이며 q=E[sigma*v], z=E[v²]다. 정상 p*=r/(r+nu), m*=Up*에서
Var(v)=U² p*(1-p*)/[1+(r+nu)tau]를 얻는다. 실제 fixture U=20,r=.2,nu=.3,
tau=3,p0=1,v0=20,t=2에서 m=17.653910 m/s, Up=12.414553 m/s이고
정상 분산은 38.4와 binary reference 96 m²/s²로 다르다. m=Up는 일반 transient
항등식이 아니다. 공통 bulk speed 상태는 내부 분산을 해상하지 않는다. reference의
분산을 bulk 상태의 실측·해상 분산인 것처럼 채워 넣지 않는다. reference 수렴 시험은
가감속 한계를 충분히 크게 두어 clipping이 비활성인 범위만 비교한다.

## Gap oracle와 보증 범위

`pair_compatibility`는 follower mass/class, leader class, joint(class,speed) marginal,
평균 bulk speed와 sum n(h+ell)=L_lane의 일치라는 ring 필요조건을 확인한다.
leader mark를 두 번째 차량량으로 더하지 않는다. pair speed의 support는 같은
quadrature node를 사용해야 한다. 필요조건 통과는 자기일관적인 pair PDE나
noncollision의 충분조건이 아니다. 기존 gap_transport의 제어는 별도 정보·제동
가정 아래의 국소 안전 oracle로 유지하고 그 인증을 bulk 속도에 이전하지 않는다.

동종 class의 phi(h)=beta[s/(h+ell)]²는 convex이므로 일반적으로 E[phi(h)] !=
phi(E[h])다. 같은 gap 평균 50m를 가진 30/70m 분포도 mean-gap closure와 hazard가
다르다. 독립 foundation_kinetics 구적법은 같은 평균 gap의 4/96m 분포에서
균일 50m와 다른 평균속도 및 양의 분산을 재현한다. 혼합 class의 조건부 gap
상관까지 이 평균식으로 복원한다고 주장하지 않는다. 이 한계 때문에 full pair PDE를
새 필수 연구로 무한 확장하지 않으며 선택 closure의 적용범위를 제한한다.

## 재현과 다음 연결

```sh
python -m pytest -q tests/v1/test_kinetic_closure.py tests/test_foundation_kinetics.py tests/test_gap_viability.py
python -m metroflow.v1 physics-oracles --suite kinetic --out kinetic.json
```

상수 목표/최초도달, 혼합 class와 동종 극한, 분할·질량 scaling, 급제동,
latent mean/variance, 시간 수렴, gap 반례, 미래 관측 거절을 검사한다.
T03/T04는 class mass와 점유공간 갱신 및 실제 flux를 이 운동법칙과 결합한다.
현 단계는 full network shock/FIFO, 충돌 회피, 10만 주민 교통 실행이나 최종 V1 수용이 아니다.
