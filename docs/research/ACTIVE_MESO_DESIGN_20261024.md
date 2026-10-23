# Active matter 집계 교통: 코드 설계와 검증 계약

2026-10-24 KST. Parent `9a81cc9291112c950abb8cf1dc517957da0fc289`.
기존 CTM과 production default는 변경하지 않는다. Scientific core는 Python stdlib-only다.

## 목적과 표현

원래 아이디어인 자기구동·목적지 지향 agent, mesoscopic 계산 절감, collision-derived Dijkstra potential을 보존한다. 차량별 ID나 쌍별 상호작용을 계산하지 않고 OD/운전성향/경로 cohort의 정지·주행 질량을 진화시킨다. 질량은 real vehicle-equivalent이며 정수 차량 identity 계약과 다르다. 희망속도·재출발 rate·혼잡 반응·목적지는 그룹별로 보존한다. 개인 이력, 차선별 FIFO와 속도분포 세부형상은 잃는다.

## 계산식과 가정

각 residence stage에서 두 속도 0,v를 사용한다. v=min(road speed,desired speed), h=ceil(L/(v dt)).

    df1/dt=alpha*f0-beta*f1; df0/dt=-df1/dt.
    beta=b*r/max(0.05,1-r), r=transit_mass/link_storage.
    p=alpha/(alpha+beta), m=f0+f1.
    f1'=exp(-(alpha+beta)dt)*f1+(1-exp(-(alpha+beta)dt))*p*m.
    f0'=m-f1'.

alpha,beta는 s^-1이다. alpha는 물리적 가속도 m/s²가 아니다. 밀도 의존 beta는 미보정 평균장 encounter closure이며, ready queue는 transit density에서 제외한다. Frozen-rate update는 양성과 질량을 정확한 산술에서 보존하고 전체 nonlinear split에는 시간 이산화 오차가 있다.

주행상태 진입·균질 고정 rate·경계 대기 없음 조건에서 P01=p(1-exp(-r_c dt)), P10=(1-p)(1-exp(-r_c dt))이다. 다음 stage로 전진하기까지 평균 step 수는 1+P10/P01=1+beta/alpha. 따라서 E[T]=h dt(1+beta/alpha). Wolfram에서 직접 확인했다.

    cost_e^g=h_e^g dt(1+beta_e^g/alpha_g)+ready_queue_e/capacity_e [s].
    Phi_d(u)=min_(u,v)[cost_(u,v)+Phi_d(v)], Phi_d(d)=0.

시간변동에서는 quasi-static predictor다. Queue/capacity는 집계 대기 근사이지 정확한 FIFO 식이 아니다. Signed collision operator 자체를 edge weight로 더하지 않는다. Phi는 양의 시간 cost-to-go이며 mechanical potential energy가 아니다.

## 알고리즘과 파일

`src/metroflow/active_meso.py`: frozen dataclass state, exact local collision, residence-stage transport, continuous node allocation, external pending queue, cost perception and departure shares.

`src/metroflow/kinetic_routes.py`: nonnegative Dijkstra, reverse cost-to-go, bounded Yen loopless candidates, separate affine Wardrop oracle.

`tools/run_active_meso_research.py`: diamond, signal/service, demand scaling, Braess oracle, optional frozen map JSON adapter.

`tools/plot_active_meso_research.py`: optional matplotlib evidence renderer, scientific core에서 사용하지 않는다.

한 step은 pre-step density에서 collision, 한 stage 전진, constrained boundary transfer, source admission 순서다. 새 link로 진입한 mass는 다음 step 전에는 다시 이동하지 않는다. Receiving은 pre-step 잔여 storage와 capacity로 제한한다. Full link는 상류를 막지만 정확한 spatial LWR shock speed를 표현하지 않는다. 미수용 수요는 외부 pending에 남고 released=pending+active+completed를 그룹별로 검사한다.

노드에서는 proportional warm start 뒤 aggregate residual max-flow를 수행한다. Augment는 차량 한 대가 아니라 가능한 실수 mass 전체다. 최대 throughput을 우선하며 그와 충돌하는 proportional fairness나 일반적인 starvation 방지를 보장하지 않는다. Turn conflicts, lane pockets와 full FIFO는 미구현이다.

경로는 admission 때 고정된다. 신규 출발분만 perceived-cost softmax와 exponential relaxation을 사용한다. 기본 tau_cost=30 s, tau_choice=60 s, temperature=10 s는 관측 보정값이 아니다. 이미 이동 중인 mass를 더 좋은 경로로 순간이동시키지 않는다. K<=8, route-search<=512 Dijkstra calls, state<=100000 scalars의 hard budget이 있다. 현재 후보 최저비용과 전역 Dijkstra 최저비용 차이를 candidate_regret로 보고한다. 후보집합 자동 교체는 아직 없으며, 후보가 전부 닫히고 전역 우회로만 남으면 진단 경고와 pending을 유지한다.

## 적대적 반례와 교정

폐쇄 도로를 1e9초 관측으로 smoothing하면 재개 뒤에도 2.39e6초의 가짜 기억을 남기는 반례를 재현했다. 폐쇄는 feasibility로 처리하고, 닫힌 경로의 비용 기억은 동결한다.

비례배분은 작은 2x2 node에서 최대 20 중 15만 보냈다. Residual reassignment로 20을 회복했으며 vehicle-token 반복을 추가하지 않았다.

즉시 best-response 대조군은 0/1 route oscillation을 보였다. 동일 no-incident diamond에서 완화 후보의 최대 share jump는 0.01110, 대조군은 1.0이었다. Cost smoothing, choice relaxation, temperature를 함께 바꾼 비교이므로 단일 parameter의 인과 효과를 주장하지 않는다. 수요 종료 후의 guidance share는 실제 차량 share와 구별한다.

## Braess 보존

Braess는 모든 망에서 필연적이지 않다. 도로 추가 후 travel time이 반드시 줄어야 한다는 조건을 넣지 않았다. 별도 affine cost benchmark에서 Beckmann integral를 최소화해 Wardrop UE를 구한다. Total travel time을 최소화하는 system optimum이 아니다.

Normalized demand 1, 기존 2경로에 100x+100 s, 중간 shortcut 1 s를 주면 기존 평균 150 s, 추가 후 199 s다. 직접 두 경로는 각각 0.01, shortcut 경로 0.98이다. Wolfram과 solver gap<4.1e-10으로 확인했다. 이 static oracle을 dynamic kinetic Braess의 검증으로 바꾸어 말하지 않는다.

## 실제 결과

- 새 aggregate/routing 16 tests, unchanged integer reference 23 tests 통과. 지도는 별도 18 tests와 7개 생성 사례 통과.
- 4 rates x 4 time steps x 2 signal schedules, 32개 포화 서비스 oracle: 최대 오차<5.6e-13 vehicles, 적신호 유출=0.
- Diamond 390 vehicle-equivalent, 200–400 s upper-link closure: dt=2/1/0.5 s 모두 완료, mass error<7.1e-12 vehicles. Pending 포함 평균 체류시간 62.04069/61.47600/61.07617 s. Peak storage ratio 0.83550/0.88765/0.90995. 세 점은 수렴 경향이지 hydrodynamic-limit 증명이 아니다.
- 1000/10000/100000 released mass, 400 steps: 상태 311 scalars 동일, 3회 median 0.0784/0.0816/0.0884 s. 대부분 pending인 과부하 시험이며 10만 대의 실제 도시 주행 검증이 아니다.
- Generated map 1056 directed links, 중심지 왕복 및 새 infill chord probe 3 cohorts: 상태 933 scalars, 60 mass 완료, error<1e-13. Hierarchy capacity/speed는 미보정 prior다.
- Python 3.13.5 실행. compileall, scientific AST stdlib import 검사 통과. Full repository CI/Python3.12/native independent subagent review는 NOT_RUN.

## 재현

```bash
PYTHONPATH=src python -m pytest -q tests/test_active_meso.py tests/test_kinetic_routes.py
PYTHONPATH=src python tools/run_active_meso_research.py --output-dir artifacts/active_meso_run
PYTHONPATH=src python tools/run_active_meso_research.py --output-dir artifacts/active_meso_map --map path/to/map_after.json
python tools/plot_active_meso_research.py --input artifacts/active_meso_run/traffic_results.json --output-dir artifacts/active_meso_run
```

완성 판정은 bounded research implementation이다. 실제 도시 calibration, signal conflicts, lane-level FIFO, capacity drop, spatial backward-wave speed, full time-dependent optimality는 unresolved다. 과거 per-car CTM을 삭제하거나 원래 physics 목표를 일반 CTM으로 대체하지 않았다.

## 참고문헌과 출처 범위

Puppo et al. (2017), Kinetic models for traffic flow resulting in a reduced space of microscopic velocities, DOI 10.3934/krm.2017033: 원 출판사 abstract와 metadata; 적은 속도 mode 동기만 재사용.
Yu, Han, Ochieng (2020), Day-to-Day Dynamic Traffic Assignment with Imperfect Information, Bounded Rationality and Information Sharing, DOI 10.1016/j.trc.2020.02.004, arXiv:1811.10729v4: 저자 abstract/metadata; perception/logit 개념 연결, parameter calibration 아님.
Braess, Nagurney, Wakolbinger (2005), On a Paradox of Traffic Planning, DOI 10.1287/trsc.1050.0127: 원 출판사 abstract/metadata; user/system optimum 구분.

위 문헌이 이 코드의 정확성을 보장하지 않는다. Local two-state solution, first-passage map, explicit counterexamples와 실행 수치는 별도 직접 유도/CAS/검산이다.
