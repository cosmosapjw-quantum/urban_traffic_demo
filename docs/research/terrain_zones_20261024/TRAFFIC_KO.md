# 도시 stock에서 활동도 기반 집계 교통까지

2026-10-24. 지형·토지이용 단계 뒤 실행한 별도 이론/코딩 연구 단위다. 표준 라이브러리만 사용하며 그래픽·관측 calibration·게임 비교는 범위 밖이다.

## 표현과 권위
주민 stock[persons], 일자리 stock[jobs], 시간구간별 person-trip, vehicle-equivalent와 동시 active mass를 분리한다. 기존 원격 `active_meso.py`와 첨부의 `active_suffix/`는 다른 구현이다. 이번은 첨부 `urban_accessibility_suffix_research_20261024.zip`(SHA256 2f325e19126b42be80bbff98fefa77230e476778a687da3293e37d316026b022)의 active_suffix 7개 모듈을 byte-preserved dependency로 신규 게시한다. 원격 active_meso와 CTM은 수정하지 않는다.

## 대안과 선택
개인 일과표 microsimulation, 무제약 중력배분, 양방향 margin을 지키는 entropy/IPF를 비교했다. 이번은 마지막을 택한다. 동일인 trip-chain, 귀가, 화물/서비스 이동은 아직 구현하지 않으며 부족한 일자리를 몰래 증대시키지 않는다. 주거/일자리 stock과 느린 도시변화를 빠른 교통에 연결하는 LUTI 관점[1], entropy 기반 공간분포[2]가 동기다. 해당 원 논문의 전체 simulator를 재현하지 않는다.

도로 접근점이 있는 구역을 공간 bin, 연결 component, river bank로 묶는다. 대표점은 기존 도로 node 중 가중 중심에 가까운 점이다. 강 양안을 하나의 centroid로 합쳐 가짜 연결을 만들지 않는다. 이 대표점 근사는 구역 내부 접근거리·분산을 잃으므로 local trips를 별도 unresolved 장부에 둔다. service_capacity는 향후 방문수요 입력이며 지금은 출력 metadata다.

## OD의 직접 구성
취업자 O_i와 실제 배치된 일자리 D_j의 합이 같아야 한다. 비용 c_ij[s]는 고정 지형 road speed와 평균 signal delay의 Dijkstra skim이다. 도달 불가능한 쌍은 structural zero다. 같은 구역의 비용120s는 분포의 deterrence prior이지 해상한 이동시간이 아니다.

K_ij=exp(-c_ij/tau), tau=900s를 두고 아래를 최소화한다.

    sum_(i,j) T_ij (log(T_ij/K_ij)-1)
    sum_j T_ij=O_i, sum_i T_ij=D_j, T_ij>=0.

Lagrange 미분은 log(T_ij/K_ij)+lambda_i+mu_j=0이므로
T_ij=a_i K_ij b_j다. Row/column scaling을 번갈아 적용한다. 각 행의 최소비용을 지수에서 빼는 것은 고정 row margin 아래 상수항만 바꾸므로 해를 바꾸지 않는다. Wolfram stationarity residual=0.

반복 전에 support max-flow로 margin의 실행가능성을 검사한다. 각 행/열에 이웃이 있어도 충분하지 않다. 예를 들어 O=(9,1),D=(5,5), 첫 행이 첫 열만 도달하면 infeasible이다. 이 반례와 총수 불일치, zero margin, max_iter 고갈을 검사한다. 총수 불일치는 DemandInfeasible, 비수렴은 RuntimeError다. 지수범위>700은 log-domain 해법 필요 오류로 분리하고 조용히 support를 삭제하지 않는다. IPF 종료조건은 normalized max margin residual<=1e-9다. Population에 비례하는 반복이 아니라 district matrix에 비례한다.

## 사람에서 도로 차량량으로
100000 residents, workers/residents=0.4, peak participation=0.4, car person share=0.55, occupancy=1.25 persons/car를 명시한다.

    100000 * 0.4 * 0.4 = 16000 peak person-trips
    16000 * 0.55 = 8800 car person-trips
    8800 / 1.25 = 7040 vehicle-equivalents.

나머지7200person-trip은 비자동차 모드이며 이번 도로 solver로 수송하지 않는다. 100k 기준14districts/156OD에서 unresolved local791.194706veh, network6248.805294veh다. 시간 profile weights의 합은1이고 각 bin의 rate는 amount*weight/duration이다. 0~3600s 한 bin에서 300s 관측은 network demand의1/12만 release한다. 아직 방출되지 않은 계획량을 pending 또는 completed로 잘못 세지 않는다.

## 실제 동역학과 비용
기존 active_suffix의 activity closure를 유지한다.

    dp/dt=alpha(1-p)-nu*p, nu=nu0+beta(N/K)^2.
    p_new=p_eq+(p-p_eq)exp[-(alpha+nu)dt], p_eq=alpha/(alpha+nu).
    tau_run=L/(v*p), c=tau_run+exit_queue/effective_service+mean_red_wait.

Frozen-rate collision은 양성·질량을 보존하고, 지연은 운송과 Dijkstra 비용 양쪽에 들어간다. 두 상태 kernel은 기체 Boltzmann의 엄밀 유도가 아니라 declared active-matter-inspired closure다. kinetics/routing/node source는 이전 attachment와 동일하다. 출발 후보 변경은 진행 중 suffix를 덮어쓰지 않고, 차량 ID 없이 (due_tick,suffix,mass)만 진화시킨다. 유한 저장량, 실제 signal*incident 공동 가용성, node aggregate max-flow, 가짜 holding 방지는 기존 모형의 범위로 유지한다. Full FIFO, 내부 shock, 속도분산은 미해결이다.

이번 terrain adapter는 양방향 12/(1+3|grade|)m/s, surface0.5/bridge0.7veh/s, storage0.12veh/m를 사용한다. Degree>=3에서 접근로 한 개씩 green28s/allred2s이고 conflict를 쌍별 선언한다. 경사계수·용량·mode share·occupancy는 모두 authored prior다. 경사가 있다고 차량가속/연료/안전까지 계산한 것은 아니다.

## 실제 결과
새 수요6+coupling5시험, 기존 environment11과 suffix12회귀를 합해34passed. Repo에서 새 시험만 실행하면22passed다. Parent-reference12개는 첨부 검증 fixture와 함께 번들에 보존한다. 1000/10000/100000 resident stock에서 matrix196cells/14districts/156OD가 동일했고 계획 생성 약0.008~0.010s였다. 이를 10만명의 서로 다른 행태를 해결한 benchmark로 부르지 않는다.

3000주민,108directed roads,3districts,6OD: network146.567858veh 모두 수송; 1800s 관측, mean385.340110s, peak occupancy0.44230, suffix49,arrival171. 64.632142veh local trips는 이 완료량에 포함하지 않았다.

100000주민,500directed roads,14districts,156OD: 300s 관측만 수행. released520.733774,completed32.707462,active488.026313,pending 약2.1e-16,not-yet-released5728.071519veh. 차량 ledger 잔차<=3.42e-13,최대 occupancy0.32932, suffix1426,arrival5200,route repair113회. 전체 mean은 null이다. Route regret<=14.92044s는 refresh 때 추정비용의 cache gap이지 실제 journey prediction 오차가 아니다. 현재 sandbox 약1.03s 실행은 이 짧은 probe에만 해당한다.

## 실행과 한계
`PYTHONPATH=src python -m pytest -q tests/test_environment_*.py`
`PYTHONPATH=src python -S tools/run_environment_traffic.py`

Topology/terrain/zoning/demand plan은 교통 중 고정한다. 토지이용 feedback과 cached skim의 재계산은 다음 slow-step에서 전체 새 plan을 만드는 계약이다. Runtime route-cost refresh와 도시 stock 업데이트를 같은 timestep으로 섞지 않는다. 장기 local목표는 안정적인 100k 주민 day-schedule이지만 지금은 전일운송, 다중수단, 귀가/서비스/화물, 응급차, 실제신호, empirical realism, 게임 대비 우월성을 검증하지 않았다. Braess를 없애는 optimizer나 모든 도로 추가의 이득 조건은 없다.

[1] Waddell(2002), UrbanSim, doi:10.1080/01944360208976274. Primary abstract와 metadata, LUTI 동기.
[2] Wilson(1967), A statistical theory of spatial distribution models, doi:10.1016/0041-1647(67)90035-4. Primary metadata와 entropy 공간분포 계보. 본 IPF 식은 위 직접 유도와 구현으로 검증.
[3] Puppo et al.(2017), reduced microscopic velocities, doi:10.3934/krm.2017033. 소수 kinetic mode의 동기이며 이번 계수의 calibration이 아니다.
