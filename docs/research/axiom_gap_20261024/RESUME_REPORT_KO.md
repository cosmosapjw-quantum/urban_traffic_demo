# 연속속도·간격 통계·인과적 정보: 이론과 두 구현의 한정 결산

2026-10-24. 연구 브랜치 `research/axiom-gap-sight-information-20261024`. 중단 복구 기준 `6f45a3ccc75fe1da07e0820776d0b5ae617a7ae2`, 원래 비교 기준 `f0d5d2280677ae436cef9ec92533be1fef595ec4`. 사용자의 일곱 관찰을 상위 원리로 유지한다. 이번 문서는 중단됐던 독립 이론 검토, 지도, 교통 연구 단위의 최종 검증이다. 새로운 전체 연구 사이클이나 외부모델 성능 순위는 시작하지 않았다.

## 1. 복구와 증거 범위

이론 `123b22062bdbfb03573b3595d063303fbb3c0c62`, 지도 `0ada99fb5f3f02ff935cd96c7aad88e382e31dfb`, 교통 `6f45a3ccc75fe1da07e0820776d0b5ae617a7ae2`가 원격에 보존돼 있었다. 임시 작업트리와 신규 RED/GREEN 로그는 남아 있지 않았다. 부모 번들 SHA256 `90af00543fe053fd57f496b25c6627cb93e6bc00aed7b399742afe1c257a5472`를 확인해 복원하고, 게시된 source와 정확한 Git blob identity를 대조했다. 이전 stage receipt의 통과 숫자만 승계하지 않고 실행을 다시 했다. 부모 테스트12개를 포함하는 격리된 납품 workspace이며 전체 remote checkout의 공용 conftest와 CI를 실행한 것은 아니다.

이전 SciSpace 검색 결과는 후보 탐색으로만 쓰고, 이번에는 publisher/official 원문에서 적용 범위를 재확인했다. DOI 10.1137/19M1258980의 출판연도는 **2019**다. 이전 DERIVATION_KO.md [4]의2020을 이 문서로 정정한다. 제약을 갖는 특정 kinetic model에서의 결과를 이 코드에 그대로 전용하지 않는다. 독립 이론 단위는 구현과 분리된 유도를 뜻하며 별도 연구자의 독립 심사를 뜻하지 않는다. native_subagent: NOT_RUN.

## 2. 원래 p식의 조건부 유도

실제 위치와 속도는 연속이며, 비교용으로만 이산 목표제어 sigma in {0,1}를 도입한다. 전이율0→1은 alpha,1→0은 nu이고 실제 운동은

    ds/dt=v,    dv/dt=(U*sigma-v)/tau

다. U>0,alpha>0,nu>0,tau>0를 고정하고, 공간 수송/출입을 제거한 균질 closed ensemble을 조건화한다. sigma는 실제 차량속도 자체가 아니다. v는[0,U]에 머물고 연속이며 가속도는U/tau 이하로 유계다. 따라서 tau→0을 유한 가감속 법칙의 정확한 동일성이라고 부를 수 없다.

생성자를 sigma,v,sigma*v,v²에 작용시키면 p=E[sigma],m=E[v],r=E[sigma*v],z=E[v²]에 대해

    p'=alpha-(alpha+nu)*p,
    m'=(U*p-m)/tau,
    r'=(U*p-r)/tau+alpha*m-(alpha+nu)*r,
    z'=2*(U*r-z)/tau.

이 네 식은 위 고정-rate 선형모형 아래 정확하다. 원 코드의 m=U*p는 일반 transient의 identity가 아니다. tau*(alpha+nu)<<1, 느린 환경변화, 초기층 처리 등의 근사가 필요하다. 반대로 정상 평균 m*=U*p*는 이 선형모형에서 모든 양의 tau에 대해 성립한다. 정상 평균과 과도응답을 구별해야 한다.

정상상태에서 p*=alpha/(alpha+nu), Var(v)=U²*p*(1-p*)/[1+(alpha+nu)*tau]다. x=v/U의 정상 총밀도는 Beta(alpha*tau,nu*tau), 조건부 두 성분은 f1=x*f,f0=(1-x)*f다. 이는 zero total velocity flux에서 얻는 결과이며, 별도의 도시 운전자 데이터 적합이 아니다. 두 속도 원자분포의 분산은 tau→0 약한 극한으로만 회복된다. 가감속을 clip하거나 rate를 미시상태에 의존시키면 이 네 모멘트의 정확한 닫힘도 다시 검토해야 한다.

CAS에서 정상 forward 잔차1개, 정상 모멘트 잔차4개, 과도 평균식 잔차1개가0이었다. alpha=.2/s,nu=.3/s,U=20m/s,tau=3s,p(0)=1,m(0)=20에서 t=2s의 U*p는12.4145532941m/s, 정확한 m은17.6539096971m/s다. 정상 분산은 two-atom96이 아니라38.4m²/s²다.

## 3. 추가 가정의 심사와 선택한 수정

nu=nu0+beta(N/K)²는 공리에서 유일하게 유도되지 않는다. 균일한 차간거리, 고정 lane당 jam spacing h_j, 특정 hazard beta*(h_j/(h+ell))² 등을 추가하면 같은 형태가 나오지만, 일반적인 간격분포에서는 E[phi(h)]를phi(E[h])로 대체할 수 없다. 기존 density-square 식은 미시 상호작용의 증명된 결과가 아니라 조건부 closure로 남긴다.

통행시간도 L/E[v]로 자동 결정되지 않는다.100m를5m/s와15m/s로 가는 같은 질량 두집단은 E[T]=40/3s이지만 L/E[v]=10s다. Instantaneous stop/go의 특별한 균질 stationary rate 모형에서 initially moving이면 평균 통과시간L/U*(1+nu/alpha)가 정확하지만, initially stopped이면 추가1/alpha, stationary initial mixture이면 추가(1-p*)/alpha가 있다(L>0). 이 결과를 time-varying p, finite acceleration 또는 신호·queue가 이미 포함된 총지연에 다시 적용하지 않는다.

선택한 국소 연속속도 reference는 차종별 response/acceleration/braking/minimum-gap/headway를 명시하고

    u(h)=min(U_road,U_class,max(0,(h-h0)/T_h)),
    dv/dt=clip((u(h)-v)/tau,-b,a),    ds/dt=v

를 사용한다. 비포화 구간에서 v(t)=u+(v0-u)exp(-t/tau), 이동거리=u*t+(v0-u)*tau*(1-exp(-t/tau))다. 포화 구간은 상수가속도로 적분해 연속 접합한다. 같은 characteristic의 최초도달 root를 비용으로 사용한다. 구현은 질량이 붙은 phase quadrature를 push-forward하며 차량 ID를 만들지 않는다. 속도값은 두 값에 제한되지 않는다.

간격은 한 국소 계산 동안 고정된다. 따라서 이 코드는 **간격분포의 자율 진화식을 가진 kinetic network solver가 아니다.** 고정간격20m와 같은 평균을 갖는5/35m의 두집단을 같은 초기속도2m/s에서1초 진화시키면 평균속도는 각각4와3.1967346701m/s, 분산은0과.6452351901m²/s²다. 같은 데이터에서 다른 반응률의 화물차 평균은2.2762669277m/s다. 같은두 quadrature 질량을1000배하면100000veh를 표현해도 bin은2개다. 이것이10만명의 서로 다른 행동을 해결한 것은 아니다.

Bounded acceleration/headway target만으로 충돌회피가 입증되는 것은 아니다. 실제 gap은 h'=w-v이므로 다음 단계에서는 이 결합과 leader uncertainty 아래 제동가능집합을 다뤄야 한다. 현재 frozen-gap 예를 실제 platoon의 장기안전 증거로 쓰지 않는다. 국소 reference를 도시 비용에만 교체해 운송식과 불일치하게 만들지도 않았다.

## 4. 지도 단계: stopping-sight 입장 조건

기존 지형·교량·층·형태·접근로 생성기는 유지한다. 새 접근로 후보의 부모 지상도로에 차종별 시야 조건을 추가한다. 반응 중 속도가 일정하고, 제동 중 순감속이 하한 b_eff 이상이라는 가정에서

    b_eff=b-g*grade/sqrt(1+grade²),
    D=v*delta+v²/(2*b_eff)+margin

을 사용한다. grade는 해당 도로의 최대 절댓값으로서 최악의 내리막을 보수적으로 적용한다. b_eff<=0이면 admissible한 정지거리로 보고하지 않는다. D만큼 떨어진 각 허용 접근 방향의 eye와 접속점의 target을 잇고, bilinear terrain에 대한 연속 clearance를 patch endpoints와 이차식 극점에서 계산한다. 부모도로에 충분한 접근 구간이 없으면 unknown으로 거절한다.

이것은 두 방향의 지정된 정지거리 관측점에 대한 **terrain-only line-of-sight**다. 건물·움직이는 가림물체, 전 접근구간의 지속 시야, 모든 합류상충, 교차로 안전을 인증하지 않는다. 반응 중 내리막에서 자유가속하는 경우까지 보수적인 식이라고 확장해서는 안 된다. 차종/반응시간/감속/eye height는 연구 입력이며 공식 도로기준 충족 주장이 아니다.

새 반례의8m 고개에서는 요구거리45.869821m, 최소시야 clearance=-.656983m여서 거절되고 평탄 대조는 통과한다. 실제 네 형태에서는 시야조건을 추가해도 선택된4개 접근로가 모두 동일했다. 길이는 grid800.003655m,organic361.433371m,superblock800.003655m,ring186.813959m다. 각900m예산,cycle rank,부모분할길이,검사된 불법중심선교차0을 재검증했다. 따라서 새 판별능력이 생긴 것이지 이번 네 지도가 외관상 더 좋아졌다는 결과는 아니다.

## 5. 도시 교통 단계: 물리와 관측의 분리

CausalPackedModel은 기존 PackedModel의 활동도 수송을 유지한다. 차량이 아직 모르더라도 실제 폐쇄/저장량은 물리적으로 작용한다. 반면 출발 경로비용에는 해당 source에서 허용된 과거 보고만 사용한다. 거리d<=R이고 now>=stamp+latency+d/c_info인 최신 CostFrame만 사용하고, 반경 밖은 고정 prior를 유지한다. Static 전체 지도는 알려져 있어도 dynamic remote truth를 즉시 읽지 않는다.

현재 물리 interval의 예측 비용은 interval 종료시각에 완료된 보고로 저장한다. 아직 완료하지 않은 frame은 현재 선택에서 보이지 않는다. 전역 사고가 routing refresh 시계만 바꿔 정보를 누설하지 않도록 갱신 cadence도 실제 factor 변화와 분리했다. 관측 history는 가장 오래 필요한 query의 predecessor를 보존해 줄이고, 한도를 초과하면 직전 immutable state를 돌려준다.

이 단계의 정보는 **고정 출발지별 관측 channel과 링크 전체 비용을 보고하는 virtual sensor**다. 주행 중 위치에 따라 변하는 내비게이션, 센서가 실제로 관측 가능한 queue 추정, 정보 오류에 대한 posterior, class별 도시 물리까지 구현한 것은 아니다. Same suffix의 geometry 공유는 가능하지만 다음에 class별 물리를 통합할 때 서로 다른 전이법칙의 질량을 무조건 합쳐서는 안 된다.

비예견성의 쌍세계 시험은 demand0으로 물리적 feedback을 분리했다.2초에 실제 폐쇄가 발생하면 전역 현재상태 모드는2초에 경로선호를 바꾼다. 완료보고3초,거리50m,전파속도10m/s,처리지연2초에서는3+5+2=10초에 처음 변경된다. 반경20m의 observer는50m밖 보고로 선택을 바꾸지 않는다. 이는 모든 실제 혼잡영향이 영원히 없어야 한다는 명제가 아니라 같은 허용정보에서 같은 행동이어야 한다는 조건이다. 별도 양의수요4veh 시험에서는 폐쇄중 유출0과 질량보존,재개후완료를 확인했다.

## 6. 현재 실행한 도시 대조와 비용

이전 저장된 동일 input JSON의370directed roads,100OD schedules,100000resident stock에서2초격자로300초만 관측했다. 새로운 지도 시야조건은 이 대조 지도와 별도의 모듈 시험이며, frozen-gap 연속속도 core도 도시 물리로 교체하지 않았다.

| 수량 | 전역 현재정보 | 유한정보 |
|---|---:|---:|
| 방출veh |480.9633992969|480.9633992969|
| 완료veh |17.4585343269|17.4574282890|
| 도로내veh |463.5048649700|463.5059710078|
| 최대 저장량비 |.7856893566|.8073216707|
| 최대 도착기록 |2853|2686|
| 목적지 potential solve |110|1000|
| source 경로 보완 |59|39|

보존잔차 최대1.1937117961e-12veh. 유한정보는 최대12개 frame,4440cost scalar를 보관했다. 목적지별 공동계산이 source별 서로 다른 비용으로 나뉘면서 solve가 늘었다. 이것은 현실성/계산비용 trade-off이지 속도개선 결과가 아니다. 완료량의 작은 차이는 통계적 결론이나 교통최적화 결과가 아니다. 두실행모두 HORIZON_REACHED이고 전체 mean journey는null이다.

## 7. 이번 재개에서 고친 실제 오류와 검증

실행기가 horizon/dt를 무조건 round해3초요청을4초실행으로 만들면서3초라고 보고했다. 또한 입력과 무관하게 resident_stock=100000을 표기했다. 공개 runner에 대한 두 RED를 기록한 뒤 시간격자 불일치를 명시적으로 거절하고, 주민stock을 입력의 ledger에서 읽도록 수정했다. 동일 시험2개 GREEN. 수송 물리는 바꾸지 않았다.

최종 격리 workspace: 수치/교통94개,지도/시각/접근27개,runner수정2개,합123개통과. 부모 suffix reference12개를 포함한다. 이전 신규19개에 대한 최초RED로그는 소실돼 재확인했다고 부르지 않으며, 이번2개만 fresh RED/GREEN이다. Model/PackedModel × 정상/폐쇄 ×100ticks의400상태fingerprint는 원 비교부모와 정확히 같았다. compileall 및 python -S 과학실행을 확인했다. 그림4개는 실제 JSON또는 검사된해를 사용하고 terrain반례/인과성두그림을 직접 열어검수했다.

전체repoCI,공용conftest,Python3.12,사용자local전일100k,관측calibration,fullFIFO,전역안전증명,독립subagent심사:미수행. 통과범위는 조건부 유도/국소 reference/시야gate/출발정보/짧은도시실행이며 'first-principle 도시교통모형 전체완성'이 아니다.

## 8. 재현과 다음 최소 단위

납품의 code/에서 아래를 실행한다. 원격에는선행commit들의코드도있다. city input은번들inputs에보존돼있고 원격전체generated artifact와동일시하지않는다.

```bash
PYTHONPATH=src python -m pytest -q tests/test_foundation_kinetics.py tests/test_causal_information.py tests/test_sight_frontage.py tests/test_axiom_runner_contract.py
PYTHONPATH=src python -S tools/run_axiom_traffic.py --city-input inputs/grid_core_100k.json --horizon 300
PYTHONPATH=src python -S tools/run_sight_research.py
python tools/plot_axiom_evidence.py
```

현재DAG는 T가정유도→M시야기하→C국소연속속도+source정보→검증/게시에서닫는다. 다음구성은 h'=w-v와실제제동한계를포함한단일도로의조건부분포모형이다. 먼저안전집합의feasible control과정보지연을분리하고,같은f1/다른gap반례,양성/질량,자유류first-passage,미관측사건무반응을잠근다. 그뒤 gap/velocity/class/필요한memory를공유suffix수송에어떻게축약할지선택한다. 비용만새모형으로바꾸고실제수송은옛p에남기는비일관성은피한다.

## 원문헌 확인과 적용 범위

[1] Puppo et al.(2017), DOI10.3934/krm.2017033: 특정collision kernel에서 얻은 제한된 정상속도 support이며 모든transient의두속도근거가아니다.
[2] Chiarello and Tosin(2023), DOI10.3934/krm.2022038: nonlocal leader/headway dynamics와특정극한에서의거시유도. 본clip law와network를입증한것이아니다.
[3] Bayen,Keimer,Porter,Spinola(2019), DOI10.1137/19M1258980: 과거정보를허용하는nonanticipative routing framework. 원문의존재유일성을우리wrapper의정리로전용하지않는다. 앞선2020표기를정정한다.
[4] FHWA Speed Concepts Informational Guide, Appendix 및Chapter4: reaction/braking/grade에따른sight-distance구조. 본실험의1초반응과4m/s²등은공식설계기준을그대로쓴것이아니다.

이번문헌재확인은publisherabstract/introduction과officialHTML범위다. 이론식은본문직접유도와CAS검산,성능/동역학은보존된실행자료를근거로구분한다.
