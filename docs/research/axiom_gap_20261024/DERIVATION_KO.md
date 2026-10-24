# 일곱 관찰에서 기존 코드의 추가 가정으로: 독립 이론 연구 단위

2026-10-24. Base f0d5d2280677ae436cef9ec92533be1fef595ec4. 사용자의 AXIOMATIC_FOUNDATIONS_KO.md v0.1이 모델의 상위 기초다. 이 문서는 직접 유도와 후속 구현의 선택이며 경험적 타당성·완전한 kinetic network 해법을 선언하지 않는다. native_subagent: NOT_RUN; 독립 이론 단위라는 뜻은 코드 개선과 분리된 유도이지 별도 모델의 독립 심사가 아니다.

## 1. 원 코드의 위치와 재사용
active_suffix/kinetic.py는 p'=alpha(1-p)-nu*p, nu=nu0+beta(N/K)^2의 동결-rate exact relaxation을 쓰고 engine.py는 L/(U*p)+queue/effective_service+mean_red를 사용한다. 전역 현재 비용으로 모든 OD의 Dijkstra를 갱신한다. PackedModel은 이 물리식을 바꾸지 않고 시계·도착기록을 개선했다. 원 초기 flow/engine.py는 link queue/node allocator였으며 연속 f(s,v,h,mark)가 구현돼 있었다고 소급하지 않는다.

이번 선택은 (T) 가정의 유도/반례, (M) 가감속·국소 가시성을 반영한 접근로 gate, (C) 연속속도 국소 reference와 유한정보 도시 routing이다. 전 도시의 full pair kinetic PDE 전면 재작성이나 p를 단순히 velocity라 이름 바꾸기는 선택하지 않는다. 기존 defaults·질량/저장량·suffix 운송은 유지한다. 외부 데이터 학습과 다른 simulator 정밀 벤치마크는 하지 않는다.

## 2. 기존 p식은 어떤 의미에서 유도되는가
실제 차량속도가 두 값이라는 가정 대신, 목표 제어 sigma in {0,1}가 전이율 alpha:0->1, nu:1->0의 memoryless Markov 과정이고, 실제 v는 연속적으로

    ds/dt=v, dv/dt=(U*sigma-v)/tau

를 따른다는 비교용 가정을 놓는다. sigma는 관측자의 분류 또는 제어상태이며 차량의 존재론적 두 속도가 아니다. U,alpha,nu,tau를 국소적으로 고정하고 동일 class를 조건화한다. 0<=v<=U에서 속도는 연속이고 |a|<=U/tau다. 물리적 가속/제동한계를 넘지 않으려면 tau가 충분히 커야 한다. tau->0 극한은 유한 가감속 공리와 동시에 정확할 수 없는 coarse-time 근사다.

p=E[sigma], m=E[v], r=E[sigma*v], z=E[v^2]를 생성자에 적용하면 정확히

    p'=alpha-(alpha+nu)*p,
    m'=(U*p-m)/tau,
    r'=(U*p-r)/tau+alpha*m-(alpha+nu)*r,
    z'=2*(U*r-z)/tau.

따라서 m=U*p는 일반 transient의 identity가 아니다. 관측시간이 tau보다 길고 tau*(alpha+nu)<<1이며 초기층을 처리할 때만 빠른응답 근사로 쓸 수 있다. 정상상태에서는 p*=alpha/(alpha+nu), m*=U*p*이고

    Var(v)=U^2*p*(1-p*)/[1+(alpha+nu)*tau].

stationary density도 구할 수 있다. x=v/U이면 zero total v-flux 조건으로 f1=x*f, f0=(1-x)*f이고, 정상 forward 식은 f(x) proportional x^(alpha*tau-1)*(1-x)^(nu*tau-1), 0<x<1을 준다. alpha,nu,tau>0의 Beta 분포다. 원 two-atom variance U^2*p*(1-p*)는 tau->0 약한 극한이며 일반 분포를 대표하지 않는다. 가감속을 clip하면 위 네 moment의 exact closure는 더 이상 유지되지 않는다.

CAS stationary residuals는4개 모두0. 예 alpha=.2/s,nu=.3/s,U=20m/s,tau=3s,p(0)=1,m(0)=20m/s에서 t=2s의 U*p는12.414553m/s, 실제 moment m은17.653910m/s다. 정상 variance는 원two-atom96에서38.4m^2/s^2로 바뀐다. 동일한 정상 평균만 맞춘다고 transient와 분산이 맞지 않는다.

## 3. 밀도제곱과 평균통과시간의 추가 가정
nu~(N/K)^2는 일곱 관찰로 유일하게 나오지 않는다. 간격에 대한 hazard가 beta*(hj/(h+vehicle_length))^2이고 균등 간격 h+ell=1/rho, 고정 lane/K를 가정할 때 유사식을 얻는다. 실제 간격분포에서는 E[phi(h)]와 phi(E[h])를 바꾸는 것이 별도 closure이며 generally unequal다. 속도분산만 남겨도 같은 f1·다른 gap correlation 반례는 해결되지 않는다.

L/(U*p*)는 homogeneous stationary instantaneous stop/go process에서 initially moving일 때의 mean passage와 일치한다. 주행에 필요한 시간L/U 동안 mean stop 수nu*L/U, 각 stop mean1/alpha를 더한 것이다. initially stopped라면1/alpha가 추가되고, stationary initial state mixture이면(1-p*)/alpha가 추가된다(L>0). 시간변화·finite acceleration·이질속도·신호와 같은 정지의 중복계산에서는 그대로 쓸 수 없다.

예:100m를 각각5m/s와15m/s로 가는 동일질량 두집단의 E[T]=40/3s, L/E[v]=10s다. 이는 균질속도 폐쇄를 검토할 반례이지 사고/정체 자료에 대한 calibration이 아니다.

## 4. 선택한 연속속도 국소 구성
차종 a와 조건부 gap quadrature G_a(h,v0)를 유지하고, 도로환경이 허용하는 속도cap U_e,a 아래

    u_a(h)=min(U_e,a, max(0,(h-h0_a)/T_a)),
    dv/dt=clip((u_a(h)-v)/tau_a, -b_a, a_a), ds/dt=v

를 사용한다. h는 한 국소 계산 동안 동결된 조건부 환경이다. 차량별 tracking이 아니라 질량이 붙은 분포 quadrature이며 개수는 물리적 차량량과 독립이다. 전역의 headway를 이 식이 스스로 진화시킨다고 주장하지 않는다. 서로 다른 class/gap/speed를 임의 합치지 않는다.

비포화 구간의 characteristic은

    v(t)=u+(v0-u)exp(-t/tau),
    x(t)-x0=u*t+(v0-u)*tau*(1-exp(-t/tau)).

가속/제동 포화구간은 constant acceleration으로 해석적으로 적분하고, |u-v|=limit*tau가 되는 시점 이후 위 해와 접합한다. v는 연속, acceleration은 선언한 한계 내이고 v>=0이다. passage time은 이 동일 x(t)에서 L을 최초로 지나는 root로 계산한다. 집단의 비용은 E_G[T]이며 L/E_G[v]로 바꾸지 않는다. v0=0,u=0의 접근불가능은+infinity다. u=0일 때 감속 후 총 이동거리의 유한 극한을 넘는 목적지도+infinity다.

약한 kinetic 해는 이 flow에 의한 f(s,v,h,a)의 push-forward다. 고정 h 동안 partial_t f+v partial_s f+partial_v(a f)=0, boundary flux 없는 질량보존이다. 이는 frozen-environment local reference이며 자기일관적인 G 방정식·shock·fullFIFO·비충돌 정리는 미해결이다. 안전집합 H=h-h0-T*v의 H'+gamma*H>=0에서 a<=(w-v+gamma*H)/T를 얻지만, braking bound와 함께 feasible인지 및 delayed observations 아래 robust invariant인지 별도 과제다. 단순 headway target을 안전보증으로 부르지 않는다.

## 5. 지도와 정보로 연결할 계산 계약
지도: 길이 예산 frontage 후보는 차량class별 반응시간 delta, 순감속 하한 b_eff>0, 접근속도v에 대해 D=v*delta+v^2/(2*b_eff)+margin을 요구한다. Grade의 worst downhill을 사용해 b_eff=b-g*grade/sqrt(1+grade^2)로 보수적으로 잡는다. 기존지상도로에서 D 떨어진 observer와 접속점 target을 잇는 선분의 terrain clearance를 bilinear patch별 이차식 endpoints/내부극점으로 검사한다. 부모도로가 너무 짧아 시야를 판단할 수 없으면 unknown으로 거절하고 길이를 늘린 것처럼 가정하지 않는다. 반응시간·높이·감속은 명시한 연구설정이고 건설안전 인증이 아니다. 단일 정지 장애물 SSD이지 교차로 모든 상충사고의 safety proof가 아니다.

교통: 실제 physical state와 perceived route cost를 분리한다. 관측(source,t_stamp,cost)은 거리d<=R와 t_now>=t_stamp+delta+d/c_info일 때만 사용한다. 도로의 현재실제 비용은 다음 시각에 완성된 관측으로 보관하고 지금 의사결정에 미래값으로 새지 않게 한다. 반경 밖은 고정 prior를 유지한다. 모든 source OD는 자신의 observation channel을 가지며, 진행 중에 차량별 추적/재탐색을 추가하지 않는다. 같은 admissible 정보에서는 같은 출발선택이어야 한다. Hidden physical capacity 변화가 refresh 시각을 바꾸어 정보를 누설하지 않도록 routing cadence도 실제 전역사고와 분리한다. 물리적 blockage/저장량은 실제상태를 사용하며, 운전자의 믿음이 물리를 변경하지 않는다.

## 6. 확인한 원문헌과 적용 한계
[1] Puppo,Semplice,Tosin,Visconti(2017), Kinetic models for traffic flow resulting in a reduced space of microscopic velocities, doi:10.3934/krm.2017033. Publisher abstract/introduction: 소수 velocity support는 특정 kernel의 steady-state 결과다. 이를 arbitrary transient가 두속도라는 근거로 사용하지 않는다.
[2] Chiarello,Tosin(2023), Macroscopic limits of non-local kinetic descriptions of vehicular traffic, doi:10.3934/krm.2022038. Publisher abstract: optimal-speed/leader/headway law와 nonlocal scaling을 정한 뒤 거시식을 유도한다. 이 문서의 clipped law 또는 hierarchy의 해를 그 논문이 증명했다고 주장하지 않는다.
[3] Gipps(1981), A behavioural car-following model for computer simulation, doi:10.1016/0191-2615(81)90037-0. Publisher abstract: 유한 가감속과 앞차 반응을 물리적 매개변수로 다룬다. 해당 식의 전체 재현/검증은 하지 않았다.
[4] Bayen,Keimer,Porter,Spinola(2020), Time-Continuous Instantaneous and Past Memory Routing on Traffic Networks, doi:10.1137/19M1258980. Publisher abstract: past/current information을 이용한 nonanticipative routing. 그 존재성/유일성 정리를 이번 state wrapper에 전용하지 않는다.
[5] Krall et al.(2021), Obscuring digital route-choice information prevents delay-induced congestion, arXiv:2105.11790. Author abstract: 정보지연 자체가 진동/정체를 만들 수 있다. 지연을 추가했다고 traffic improvement를 보장하지 않는다.
[6] FHWA, Speed Concepts Informational Guide, Appendix: Calculating Inferred Design Speed. Official text: sight distance는 reaction+braking 및 grade와 연관된다. 본문은 SI 직접유도이며 현행 법정 설계기준 준수를 주장하지 않는다.

문헌검색은 가정의 적용범위를 검토하기 위한 것이며 다른모델 정밀성능 benchmark는 아니다. WolframContext의 자동해석은 nu를 독립변수로 잘못 읽어 배제했고 명시적인 Wolfram Language 평가만 검산 근거로 사용했다. 최종 scientific scope는 조건부 유도+국소/인과성 코드이며 전역 kinetic traffic 정초의 모든 빈칸이 닫혔다고 선언하지 않는다.
