# 도로 형태·입체 구조 복원과 능동 메조스코픽 교통의 결합

2026-10-24. 저장소 `cosmosapjw-quantum/urban_traffic_demo`, 연구 브랜치 `research/restored-morphology-layered-traffic-20261024`. 복구 기준은 지도 커밋 `0da0d1a4b6c970f4cba7b1b8a4288ec1ddc04be2`, 새 교통 구현은 `00fda27101cb3be6e8b56fbc84d36736b03850bc`다. 이 문서는 현재 실행한 연구용 경로를 설명하며 production default를 변경하거나 전체 저장소 CI를 대체하지 않는다.

## 1. 중단 복구와 실제 범위

중단 전 최종 지도 소스는 원격에 남았지만 샌드박스 작업트리와 수정 과정별 그림·로그는 남지 않았다. 기준 번들 `urban_terrain_zones_demand_research_20261024.zip`의 SHA-256 `b217713482c204a555da257d01a95cbb4a8f7cc34a416d9f97c160c7a5b65b6e`를 확인하고 환경·집계 교통 코어를 복원했다. 지도 4개 모듈과 수정된 토지이용 모듈은 원격 Git blob과 byte identity를 확인했다. 최종 지도 시험과 생성은 새로 실행했다. 따라서 과거 세 차례 지도 수정의 중간 증거를 복구했다고 주장하지 않는다.

이전 단계에서 읽은 원 프로젝트의 장기 구조는 다음과 같다. `IMPLEMENTATION_ROADMAP.md`와 `ARCHITECTURE_OVERVIEW.md`@`77060c84b75195c8a05273e0d1a809caf93e63d4`의 bulk transport/behavior closure 분리, 느린 토지이용 피드백, 교량·합류 대조 시험을 유지한다. `CITY_MAP_PR_LIST.md`@`81f3f09be648cf0669c102c1f4eb33765114f489`의 도로 profile을 집계 용량으로 컴파일하는 계약을 채택한다. `morphology_capabilities.py`@`c9168100367d027f94dd33b848955af2cba3e060`의 형태 구분과 PR#22/`scalable_topology.py`@`c3d7d1b424f49791b0c25b98e8c05b40d0a48bc7`의 단방향 ON/OFF ramp 의미론을 복원한 지도에 연결했다. 과거 PR62의 morphology 0/30 실패 및 PR63의 성능·실현인구 실패는 역사적 실패로 남는다. 별도 제목의 '초장기' 문서는 특정하지 못했으며 전체 브랜치·PR를 전수 복원했다는 주장은 하지 않는다.

이번에는 기존 NumPy/개별 agent pool을 되돌리지 않았다. 계산 코어는 표준 라이브러리이고, 그림에만 matplotlib, 시험에 pytest를 사용한다. 원래 root initializer/core도 원격 원본으로 복원해 staging shim 없이 `python -S` 실행을 확인했다. 변경 없는 `active_suffix` 7개 파일은 이전 번들과 byte-identical하다.

## 2. 지도: 기하·위상·도시 용량을 분리

복원한 네 형태는 직교 격자 `grid_core`, 곡선으로 변형된 격자 `organic`, 선택적 내부 연결을 줄인 `superblock_mixed`, 양안의 동심원·방사형 구획 `ring_radial`이다. `organic`은 호환 식별자일 뿐 실제 도시의 유기적 성장 위상을 구현한 것은 아니다. 다중 중심지 경쟁, 터널 굴착·구조설계, 회전교차로의 동역학, 전체 180개 문법 조합은 이번 범위에 포함하지 않았다.

물리 도로 `Section`은 중심선, 양 끝 `Junction`, 방향별 차로 수, hierarchy, facility, 길이, 경사, 구조물 고장 group을 갖는다. 지상도로·교량의 접속점은 layer0이고, 양방향 고가 본선은 서로 다른 단방향 layer1 도로다. ON ramp만 0→1, OFF ramp만 1→0을 연결한다. XY 투영 교차는 자동 교차로가 아니다. 수계·보호구역·경사 제약은 실제 생성 허용성에 작용하고 거절된 도로를 임의 연결선으로 되살리지 않는다.

Bilinear 지형을 선분에 제한하면 각 raster patch에서

\[
h(u)=Au^2+Bu+C,\qquad \frac{dh}{ds}=\frac{2Au+B}{\ell},\qquad 0\le u\le1
\]

이다. 최대 경사 절댓값은 patch 양 끝에서 계산한다. 선형 deck와 지형의 높이차도 이차식이므로 양 끝과 내부 정지점 \(u_*=-B/(2A)\)를 검사한다. 임의 간격의 점 표본만으로 묻힌 램프를 놓치지 않도록 한 것이다. 표면 도로 길이는 patch별 8-panel Simpson 적분, 구조물은 명시적 3차원 polyline 길이이며 endpoint chord로 대체하지 않는다. cubic Bezier의 끝 접선은 \(3(P_1-P_0)\), \(3(P_3-P_2)\)로 지정해 본선 진행 방향에 맞춘다. 이는 연속 토목 설계기준의 인증이 아니라 연구용 기하 계약이다.

세 seed 7/17/41 × 네 형태의 12개 지도를 새로 생성했다. 모두 검사된 비접속 중심선의 불법 교차 0, 주민 100000명·일자리 40000개를 기존 유한 용량 내에 배치했다. 각 지도는 지상 교량 group3개, 고가 본선 구간10개, 램프7~8개를 갖는다. seed17 결과는 다음과 같다.

| 형태 | junction | 물리 도로 | directed link | weak component |
|---|---:|---:|---:|---:|
| grid_core | 118 | 194 | 370 | 1 |
| organic | 122 | 194 | 370 | 2 |
| superblock_mixed | 117 | 167 | 316 | 1 |
| ring_radial | 137 | 209 | 400 | 2 |

Organic/ring의 고립 도로는 삭제하거나 억지 연결하지 않았고, 주민 stock은 접근 가능한 가장 큰 weak component에만 배치했다. 이 조건은 모든 도로의 strong connectivity를 뜻하지 않는다. OD 가능성은 이후 실제 방향·회전 그래프에서 별도로 검사한다.

## 3. 교통 이론: 원래 구성의 보존

한 링크의 이동 성향을 두 내부 상태의 질량 \(n_+,n_-\)로 나타내는 근사를 생각한다. 링크 내 relaxation substep에서 총량 \(N=n_++n_-\)를 고정하면

\[
C_+=\alpha n_- -\nu n_+,\quad C_-=-C_+,\quad C_++C_-=0,
\]
\[
p=\frac{n_+}{N},\quad \dot p=\alpha(1-p)-\nu p,\quad
\nu=\nu_0+\beta(N/K)^2.
\]

\(\alpha,\nu_0,\beta\) 단위는 s⁻¹, \(N,K\)는 차량 상당량, \(p\)는 무차원이다. 동결 rate에서

\[
p(t+\Delta t)=p_\infty+(p(t)-p_\infty)e^{-(\alpha+\nu)\Delta t},
\qquad p_\infty=\frac{\alpha}{\alpha+\nu}
\]

이므로 비음수 rate와 \(0\le p\le1\)에서 양성성이 보존된다. 이것은 stop/restart gain-loss를 갖는 저차 모멘트 closure이며 완전한 Boltzmann 충돌 적분의 유도나 실제 운전자 통계의 적합 결과가 아니다. 차량 추진·감속과 환경 상호작용은 유지하되 개별 위치·속도를 적분하지 않는 구성이다.

새 지도 compiler는 \(v_e^0,\mu_e,K_e\)를 도로 profile에서 구성하고, 기존 코어는

\[
c_e(t)=\frac{L_e}{v_e^0p_e(t)}+\frac{Q_e(t)}{\mu_{\mathrm{eff},e}(t)}+W_{\mathrm{red},e}(t)
\]

를 경로 비용으로 사용한다. 각 항과 \(c_e\)의 단위는 초다. Dijkstra potential은 열역학적 potential energy가 아니라 합법 경로상의 남은 통행시간이다. 유입 링크를 상태로 갖는 그래프에서 목적지에 도달하지 않은 링크에 대해

\[
V_d(e)=c_e+\min_{(e,f)\in\mathcal T}V_d(f)
\]

를 사용한다. 목적지로 직접 끝나는 링크는 \(V_d(e)=c_e\), 도달 불가능한 경우는 무한대다. 활동도에 의한 지연을 실제 이동시간과 경로 비용에 함께 반영하고, 진입 후의 잔여 경로는 출발 후보 캐시가 갱신돼도 덮어쓰지 않는다. 같은 잔여 경로와 같은 도착 tick을 공유하는 질량을 합치며 개별 차 ID는 만들지 않는다.

동일한 지상망에서 차로 수·용량·저장량·수요 질량을 모두 2배로 늘리면 \(N/K\)와 \(Q/\mu\)가 불변이다. 이번 실행 검산에서도 활동도와 통행 시계는 같고 점유량·완료량·vehicle-seconds는 2배로 변했다. 이는 해당 homogeneous closure의 일관성 검사이지 이질적인 차종·lane changing의 증명이 아니다.

## 4. 지도에서 운송으로 컴파일하는 새 규칙

`restored_traffic.compile_traffic`는 명시된 방향에 대해서만 directed link를 만든다. Local/collector는 방향당1차로, arterial은2차로, mainline은 단방향2차로, ramp는 단방향1차로다. 선언한 jam density \(k_j=0.12\) veh/(m·lane)에 대해

\[
K_e=k_j n_eL_e,\qquad \mu_e=n_e\mu_{\mathrm{lane},e}.
\]

기준 속도(local/collector/arterial/expressway)는 8.33/13.89/16.67/25m/s, 차로당 용량은 .45/.50/.55/.60veh/s이며 ramp는11.11m/s와.45veh/s다. 모든 수치는 연구용 사전 설정이다. 최대 경사 \(g_e\)와 세 점 외접원 곡률 \(\kappa_e\)를 사용해

\[
v_e^0=\min\!\left(\frac{v_{\mathrm{class}}}{1+3g_e},\sqrt{\frac{2\;\mathrm{m/s^2}}{\kappa_e}}\right)
\]

로 제한한다. 곡률0이면 두 번째 제한을 생략한다. 한 링크 전체에 최대 곡률 제한을 쓰므로 보수적이다. 이산 곡률 surrogate이며 연속 곡률·전체 차로 폭·접속 곡선 설계를 인증하지 않는다.

합법 회전은 지상→ON→본선→OFF→지상 순서를 보존하고 즉시 U-turn을 제외한다. 지상 유입 링크가3개 이상인 접속점에는 유입 접근로 한 개씩28초 녹색·2초 clearance를 주며 고가 본선에는 신호를 넣지 않는다. 이는 보수적인 상충 분리다. 독립적인 직진·우회전의 동시 통행, protected left phase, 회전 pocket의 유한 저장량과 partial FIFO는 아직 구현하지 않았다.

수요 planner도 같은 \(\mathcal T\)를 사용한다. 기존 node-Dijkstra는 합법 경로10초인 반례에서 금지 회전을 이용해2초를 반환했다. 새 `allowed_turns` 경로는10초를 반환하며, 회전 제한으로 출근자·일자리 margin을 맞출 수 없으면 기존 max-flow support 검사에서 거절한다. `allowed_turns=None`은 기존 API 동작을 유지한다. '도달 가능한 OD'는 정적 연결성이지 혼잡·관측시간 내 모두 완료 가능하다는 의미가 아니다.

`structure_windows`는 물리 구조물 group의 모든 방향을 닫는다. 교량 한쪽 방향만 닫거나 구조물을 지워 진행 중 질량을 삭제하지 않는다. 기존 진입 차량은 기다리고 새 출발 후보는 살아 있는 대안을 찾는다. small diamond의24veh 시험은 폐쇄 중 해당 교량 outflow0, 전체 질량 보존, 재개 후 전량 완료를 확인했다. 포화 합류에서는 본선·램프 우선순위4:1 아래 공유 receiving1.2veh/s를 .96/.24veh/s로 배분했다.

## 5. 현재 응답에서 실제 수행한 수정과 시각 감사

새 행동 군에 대한 반례와 수정은 다음 세 묶음이다. 이전 중단 전의 세 지도 수정 회차와 혼동하지 않는다.

| 묶음 | 확인된 결함 | 수정·검증 |
|---|---|---|
| 방향·profile compiler | 기존 adapter가 ramp/mainline 역방향을 추가하고 차로 수·곡률을 무시 | 실제 부모 adapter 기준 RED4/기존통과1, 새 구현 GREEN5 |
| 수요–운송 위상 일치 | 금지 회전의2초 지름길 및 불가능한 OD support 허용 | RED2, 동일 시험 GREEN2 |
| 시각 표시 | ramp 화살표가 중심선 대신 endpoint chord 위에 위치 | 실제 렌더 호출을 관찰하는 RED1 후 곡선 sample 사용 GREEN1 |

추가 합류·폐쇄·동일비율 scaling·자원 중단·재현 시험은 regression 검산이다. 모든 시험을 strict TDD라고 부르지 않는다. 현재 독립 subagent 도구가 없어 `native_subagent: NOT_RUN`; 동일 구현자의 직렬 감사, 분석적 반례, Wolfram, 실제 실행으로 검증했다.

최종 네 지도, 교량 폐쇄 점유도, 질량 장부와 dt 민감도 그림을 직접 열어 확인했다. 그림은 실제 실행에 저장된 map JSON/trace를 렌더링한다. 새 seed로 보기 좋은 지도를 골라 바꾸지 않았다. 시각적으로 남은 문제는 반복적 격자 grain, 양안 ring의 빈 중심부와 과도한 대칭, 경사 때문에 잘린 NE 도로, 격자형 zoning, 외부 gateway 수요가 없는 본선 끝점이다. 환경은 도로를 거절하지만 정착지의 성장·지가·필지 분할·개발 순서가 형태를 생성하는 이론은 아직 약하다. 따라서 도시 형성 이론의 경험적 현실성 판정은 미해결이다. 점유도 그림의 선 굵기는 저장량 대비 점유량이며 실제 도로 폭이 아니다.

## 6. 실제 계산 결과와 해석 한계

기준 인구100000명, 취업자40000명, peak 참여율.4, 자동차 person share.55, 탑승인원1.25명이므로 총 차량 상당량은7040이다. 네 형태의 OD는 각각 도로·구역 분포로부터 생성돼 서로 다르다. 300초 관측 결과를 형태별 성능 순위로 비교하면 안 된다.

| 형태 | 계획 도로 수요 | 미해상 구역 내부 수요 | 300초 방출 | 완료 | 도로 내 질량 |
|---|---:|---:|---:|---:|---:|
| grid_core | 5771.561 | 1268.439 | 480.963 | 13.998 | 466.965 |
| organic | 5754.012 | 1285.988 | 479.501 | 13.411 | 466.090 |
| superblock_mixed | 5780.528 | 1259.472 | 481.711 | 27.254 | 454.457 |
| ring_radial | 5114.108 | 1925.892 | 426.176 | 1.779 | 423.853 |

Ring은 외부 pending .543754veh가 추가로 남는다. 각 행의 계획 도로 수요와 미해상 내부 수요 합은7040이고, 비자동차7200person-trips는 별도다. 구역 접근·이탈 및 내부 이동을0초 완료로 세지 않는다. 해당 이동시간은 아직 해상하지 않았다.

네300초 실행의 최대 질량 보존 잔차는3.98e-13veh 이하, 최대 저장량 비율은 roundoff 허용 내1이하다. 주민100000명은 도시 stock이며100000개 서로 다른 개인 이력이나 동시에 운행하는 차량이 아니다. 모든 실행은 `HORIZON_REACHED`, 평균 통행시간은 미완료이므로 null이다.

같은 grid 지도·OD·config의600초 대조에서는 입력 JSON이 완전히 같음을 검사했다. 교량 `bridge:6`의 양방향을60~180초 닫았을 때 완료량134.874212veh, 기준135.516826veh였다. 양쪽 방출량은961.926799veh, 최대 질량 잔차2.39e-12veh다. 이 작은 차이를 일반적인 폐쇄 영향이나 동적 Braess 효과로 해석하지 않는다. 별도 재사용 정적 Braess oracle에서는65→80분 악화가 유지됐다.

## 7. 해결하지 않고 명시한 수치적 결함

Dilute 단일100m 링크의 기준 속도10m/s이면 정확한 free-flow 통행시간은10초다. 기존 `active_suffix` 운송 시계는 dt=4/2/1/.5초에서 각각20/14/12/11초를 기록했다. 진입 시 다음 tick 기준의 due time을 만들고 기존 tick에서 도착을 처리하는 순서 및 vehicle-seconds의 구간 누적이 행정적인 지연을 만든다. 이 특수 조건에서는

\[
T_{\Delta t}=\bigl(\lceil10/\Delta t\rceil+2\bigr)\Delta t,
\qquad 2\Delta t\le T_{\Delta t}-10<3\Delta t
\]

로 설명된다. 혼잡·신호·다중 링크 전체에 이 식을 일반화하지 않는다. 이번 지도 연결 작업에서 재사용 코어를 몰래 바꾸지 않고 반례와 오차를 남겼다. 이는 '정확도 검증 완료'가 아니라 알려진 numerical limitation이다.

같은 grid 입력의300초 실행을 세분하면 다음과 같다.

| dt[s] | 완료veh | peak 도착 묶음 | peak 잔여경로 suffix |
|---:|---:|---:|---:|
| 5 | 13.998490 | 3432 | 1041 |
| 2.5 | 16.014809 | 6262 | 1029 |
| 1.25 | 16.964231 | 11801 | 1029 |

이 세 점은 수렴 증명도, 정확한 실도시 통행량 추정도 아니다. dt를 줄이면 시간 오차를 줄이는 대신 도착 시각별 묶음 수가 늘어난다. suffix 공유가 경로 저장을 줄여도 도착 calendar의 시간bin 비용은 별개다. 작은 fractional flow에서는 묶음 record 수가 표현하는 차량 상당량보다 많을 수 있다. 따라서 '개별 차량을 추적하지 않는다'와 '항상 더 작은 메모리를 쓴다'는 다른 주장이다.

다음 한정 연구 단위는 입력·신호·보존식을 고정한 채 진입/도착/discharge 시각과 vehicle-seconds 적분을 일치시키는 것이다. 단일 링크10초 oracle, multi-link 지연 누적, dt와 무관한 source integral, 임계 녹색 경계, 폐쇄 중 저장량 보존을 먼저 잠그고 event calendar/cohort 압축을 비교한다. 질량 삭제, 수요 축소, 강제 경로 변경으로 기록 수를 줄여서는 안 된다. 그 뒤 구역 내부·access/egress를 집계 connector로 해상한다.

## 8. 검증·재현·상태

Python3.13.5에서 번들의 집중·회귀 시험68개 통과: 기존 환경26, 부모 suffix 참조12, 복원 지도15, 새 교통14, 시각표시1. 원격 저장소에서 이번 환경·복원 파일만 지정하는 명령은56개다. 전체 repo CI, Python3.12, 사용자의 로컬 성능, 전일100k 수요, 실측 calibration, full FIFO, dynamic UE, 게임 비교는 NOT_RUN 또는 미해결이다. source compilation과 `python -S` import에서 NumPy/SciPy/JAX/Torch가 로드되지 않음을 확인했다.

Wolfram은 동결-rate activity ODE 잔차0, 초기조건 잔차0, 차로 scaling의밀도비 불변, 합류24/25와6/25, 반지름10m 곡선의 속도4.47213595m/s를 반환했다. Symbol::undefined2의 symbolic L 경고도 원본 결과에 기록했고 무경고 실행으로 바꾸어 말하지 않는다. CAS 검산은 독립 모델 심사가 아니다.

```bash
# 번들의 code 디렉터리에서 전체 집중 검증
PYTHONPATH=src python -m pytest -q tests
# 원격 repo의 이번 환경·복원 범위만 검증
PYTHONPATH=src python -m pytest -q tests/test_environment_*.py tests/test_restored_*.py
# 지도 및 도시 시험. 실제 인구는100k이나 짧은 관측이다.
PYTHONPATH=src python -S tools/run_restored_research.py --part map --style grid_core --seed 17
PYTHONPATH=src python -S tools/run_restored_research.py --part traffic --style grid_core --horizon 300
PYTHONPATH=src python -S tools/run_restored_research.py --part traffic --style grid_core --horizon 600 --closure
PYTHONPATH=src python -S tools/run_restored_research.py --part controls
# 번들에 보존된 전체 입력/trace로 그림 재생성
python tools/plot_restored_research.py artifacts/restored_layers_20261024/resume
```

`plot_restored_research.py`는 네 형태300초 입력, grid600초 기준/폐쇄, grid300초 dt2.5/1.25 결과가 모두 있을 때 실행한다. 번들에는 모두 있다. 새 repo checkout에서 재생성할 때는 해당 `--style`, `--horizon`, `--dt` 조합을 먼저 실행한다. `--closure` 예시는 grid_core 전용 `bridge:6`을 사용하며 다른 형태에 동일 group 이름이 있다고 가정하지 않는다.

DAG: S0 역사·계약 확인 → S1/S2 지도 복원과 최종형 재검증 → S3 방향·profile·합법 OD·집계 운송 → S4 시각·보존·dt/메모리 감사와 게시. 현재 S3 구현 및 S4 한정 감사는 완료했고, 지도 경험적 현실성·수치 통행시계의 개선·전일100k 목표는 별도 미완료다. 독립 심사를 수행하지 않았으므로 aggregate scientific PASS를 부여하지 않는다.

## 문헌과 적용 범위

Galin, Peytavie, Guérin, Beneš (2011), Authoring Hierarchical Road Networks, Computer Graphics Forum30(7), DOI10.1111/j.1467-8659.2011.02055.x: 지형과 계층 도로·parameterized interchange를 함께 다루는 개념적 근거다. 해당 알고리즘 전체의 재현은 아니다.

Beneš, Wilkie, Křivánek (2014), Procedural Modelling of Urban Road Networks, DOI10.1111/cgf.12283: 주변 정착지·수계·교통을 도시 성장과 연결하는 후속 목표의 근거다. 이번 ring/warped-grid를 그 성장 모형의 구현이라 하지 않는다.

Jabari (2016), Node Modeling for Congested Urban Road Networks, Transportation Research Part B91,229–249, DOI10.1016/j.trb.2016.06.001: 링크모형과 노드모형의 분리 및 상충 movement staging의 필요성을 참고했다. 이번 단순 approach별 phase가 논문의 모든 holding-free/invariance 조건을 구현하거나 입증했다는 주장은 하지 않는다.
