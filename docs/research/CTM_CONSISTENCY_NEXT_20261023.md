# 정수 CTM 서비스 일관성과 독립 연속 기준해법

기준: `3ffc153f2f36ba15ff8400de13971bb0239ebcfd`. 지도 후속 루프를 마친 다음 실행했다. 표준 라이브러리 계산, Python3.13.5, optional matplotlib는 그림만 생성한다. 기존 authoritative runtime과 이전 연구 브랜치는 바꾸지 않는다.

## 문제 선택 및 문헌과의 관계

신호 최적화, conflict delay, 연속극한 검증을 비교했으나 먼저 재현된 rate inconsistency를 교정했다. 보존식, identity, max-flow가 맞아도 장시간 서비스율이 틀릴 수 있다. CTM 네트워크 구성은 Daganzo [1], finite-volume와 shock/expansion 검산은 Maulana–Pudjaprasetya [2], Rankine–Hugoniot 및 entropy solution은 Clawpack 연구서 [3]의 원리에 근거한다. [3]의 quadratic FD 예제를 본 코드의 triangular FD 해로 그대로 복사하지 않았다.

## 재현된 반례

길이1000m, v=15m/s, w=5m/s, jam density150veh/km, capacity1800veh/h, 한 셀에100대가 있는 포화 출구를100초 실행했다. 요구 서비스는50대다.

| dt[s] | 이전 독립 잔차법 | 결합 credit법 |
|---:|---:|---:|
|0.5|12|50|
|1|25|50|
|2|50|50|
|5|50|50|
|10|50|50|

모든 경우 mass error는0이므로 보존 검사만으로는 오류를 찾지 못했다. movement의 소수 clock을 이미 정수화된 sending token이 나올 때만 진행해 용량을 이중 감쇠했다. 1초 green/red 교대 시 이전법은0대, 수정법은25대다. receiving 잔차를0.5만큼 어긋나게 둔 두 링크도 이전법은 transfer0, 수정법은50대다.

## 실제 공통 flux로 정산하는 bounded credit

각 node resource r는 upstream sending, downstream receiving 또는 movement capacity다. 실제 demand·신호·incident에서 계산된 비음수 target을 g_r[t] [veh/tick], credit을 c_r[t]∈[0,1] [veh]라 한다.

    offer_r = floor(c_r + g_r),  if g_r>0; otherwise 0.
    c_r' = min(1, max(0, c_r+g_r−x_r)).

여기서 x_r는 node solver가 실제로 배정하고 commit하는 공통 차량수다. receiving의 x에는 node 유입과 source admission을 모두 포함한다. movement clock은 실제 수요·green으로 진행하며, 다른 자원의 정수 token 존재 여부로 gate하지 않는다. red와 zero-capacity incident에서는 full credit이 있어도 offer=0이다. 버리지 않은 최대1대의 credit은 clock 간 영구 반위상 deadlock을 막는다. 무한한 미사용 용량을 저축하지 않는다.

버린 서비스 d_r=max(0,c_r+g_r−x_r−1)라 하면

    c_r' = c_r+g_r−x_r−d_r,
    Σ x_r = Σ g_r + c_r[0]−c_r[T]−Σ d_r.

따라서 초기 credit0이면 누적 실제 서비스는 누적 target을 초과하지 않는다. 임의 구간에서는 시작 credit≤1대까지 packetization 차이가 허용된다. 포화 단일 movement·일정 용량·동일 시작 clock에서 병목률 q의 누적출력은 floor(Tq), 오차<1대다. **막힘·경쟁이 있는 일반 network에서 누적오차<1대라고 주장하지 않는다.** d_r는 실제 유휴/차단 손실이며 전체 네트워크의 최적 처리량 보장도 아니다.

기존 integer max-flow와 throughput-preserving fairness 선택은 유지했다. 최대처리량 보장은 그 tick의 주어진 정수 offer 문제에 한정된다. `CTMConfig.node_token_mode='coupled_credit'`가 연구 lane의 새 기본값이며, `'legacy'`로 반례를 재현할 수 있다. config fingerprint에 mode를 포함한다. 기존 `_residuals` 필드의 내부 경계값은 fractional residual[0,1), node 경계값은 bounded credit[0,1]이다. restart는 mode와 state를 함께 보존해야 한다.

## 셀 저장량과 연속극한의 분리

이전 max(1,floor(k_j lanes dx))는 물리 저장량이1대 미만인 셀에도1대를 만들어냈다. 이제 floor값<1이면 ValueError다. 정수 차량량을 고정한 채 dx→0을 무한히 진행할 수 없으며, 연속극한에는 차량 packet 크기 또는 집계 스케일도 고려해야 한다.

FD는 q(k)=min(vk,C,w(k_j−k))이다. C=vw k_j/(v+w)이면 strict triangle, 그보다 작으면 plateau를 가진 trapezoid다. Plateau 경계는 C/v와 k_j−C/w다. 입력 capacity가 낮은 모든 경우를 유일한 critical density의 triangle이라고 부르던 표현을 교정했다.

## 별도 Godunov reference와 해석해

`pure_traffic/fluid_reference.py`는 실수 cell-average density를 쓰는 독립 scalar corridor solver다. 정수 네트워크의 알고리즘을 대신 검증한 것으로 취급하지 않는다. 단위 k[veh/m], q[veh/s], x[m], t[s], 주어진 reservoir boundary와 초기 Riemann step x0=0을 사용한다.

    F(kL,kR)=min(D(kL),S(kR)),
    k_i' = k_i + (dt/dx)(F_{i−1/2}−F_{i+1/2}),
    max(v,w)dt/dx ≤1.

Density를 clipping해 질량을 수선하지 않는다. Initial mass와 누적 경계 flux로 별도의 보존 장부를 계산한다. 해석 oracle은 strict triangular FD만 지원하며 capped case는 명시적으로 거부한다.

v15,w5,k_j0.15에서 k_c=0.0375veh/m이다. kL0.02,kR0.10의 shock 속도는 (qR−qL)/(kR−kL)=−0.625m/s, t100s 위치−62.5m다. kL0.12,kR0.01의 expansion은 −wt와 vt 사이에 k_c plateau를 가지며 양끝은 contact discontinuity다. Quadratic FD의 매끄러운 fan과 다르다. Wolfram으로 이 값과 credit balance를 검산했다.

## 오차 규범에 대한 적대적 교정

첫 검사는 단일 시점의 numerical cell average와 exact cell average의 오차가 refinement마다 단조 감소할 것을 요구했다. 실제 shock 오차는 N100/200에서0.001354/0.039824veh로 증가했다. 이것은 cell 내 shock 위상의 우연한 상쇄 때문에 그 기준이 부적절함을 보여준다. 실패 로그를 삭제하지 않았다.

이에 더 강한 공간 규범을 추가했다:

    E_profile = ∫ |k_h(x,t)−k_exact(x,t)| dx.

Exact discontinuity에서 셀 구간을 분할하여 적분한다. Exact cell average와 같은 상수 재구성이라도 셀 내부의 실제 step과는 차이가 있다는 단위시험을 추가했다. 원래 cell-average 오차도 결과 JSON에 계속 남긴다. t10,20,...,100의 평균도 보고한다. 이 교정은 tolerance 완화가 아니라 가려졌던 subcell 오차의 포함이다.

| cells | dx[m] | shock profile L1[veh] | expansion profile L1[veh] |
|---:|---:|---:|---:|
|100|40|1.575592|10.458173|
|200|20|0.384846|7.316941|
|400|10|0.304679|5.181818|
|800|5|0.200151|3.664716|

표본시간 평균 shock L1은1.181319→0.142059, expansion은7.442533→2.601967veh로 줄었다. 최대 경계 질량오차는2.14e−14veh다. 유한 표본 수렴 관찰이며 arbitrary network 수렴 정리가 아니다.

## 실행·회귀·시각 검토

```bash
PYTHONPATH=src python -m pytest -q tests/test_pure_python_ctm.py tests/test_ctm_service_consistency.py tests/test_fluid_reference.py
PYTHONPATH=src python tools/run_ctm_consistency_next.py artifacts/next_loop_20261023/traffic
PYTHONPATH=src python tools/validate_pure_python_ctm_research.py --output artifacts/next_loop_20261023/traffic_matrix.json
```

기존12+새서비스12+연속5=29 tests 통과. 서비스 기준선5실패/3통과, 연속 API 부재와 규범 교정의 red 로그를 별도 보존했다. 추가 red/incident gate 및 restart 시험은 구현 후 보강으로, 이를 별도 red-green이라고 부르지 않는다. 기존 matrix의 node residual<1 검사는 새 inclusive-credit 계약에 맞춰≤1로 변경하고 internal residual은 계속<1을 요구한다. 이는 서비스 반례를 없애는 수치 tolerance 완화가 아니다.

9개 seed/부하 조합 모두 보존·저장량·완료·node allocation 검사를 통과했다. 대표 diamond는320대/174ticks, mean travel540s, mass error0, holding events0이며 이전 큰 tick의 결과를 유지했다. 새 fingerprint는 `b39c40b3dcaaf544372b169f7533ce794513ff138d0dbb000a707c0d97893cc9`다.

실제 누적서비스·신호·anti-phase·shock/expansion·수렴 PNG를 확인했다. 포화 곡선은 이론률에 맞는 staircase로 바뀌었다. 팽창 접촉면의 수치 확산은 남지만 refinement로 감소한다. 시각 검토는 동일 세션이며 독립 reviewer는 아니다.

## 판정과 다음 연구

`SCOPED-VERIFIED`, `NOT DEFAULT-READY`. 차량 보존, tested service rate, red/incident hard gates, restart, 별도 연속 corridor 수렴은 검증했다. 정수망의 hydrodynamic scaling limit, partial FIFO와 lane-pocket 보정, conflict delay, capacity drop, detector/OD calibration, 대규모 max-flow 성능은 미해결이다. 지도와 교통 후속 연구를 순차 실행했지만 두 모형을 통합했다는 주장은 하지 않는다.

[1] Daganzo (1995), The cell transmission model, part II: network traffic. Transportation Research B29,79–93. DOI:10.1016/0191-2615(94)00022-R. Original network conservation and multicommodity framework; SciSpace source discovery and bibliographic abstract.
[2] Maulana & Pudjaprasetya (2021), Analysis of cell transmission model for traffic flow simulation with application to network traffic. DOI:10.21914/anziamj.v63.14983. Primary journal page identifies trapezoidal finite-volume discretization and shock/rarefaction validation.
[3] Ketcheson, LeVeque & del Razo, Riemann Problems and Jupyter Solutions, Traffic_flow chapter, https://www.clawpack.org/riemann_book/html/Traffic_flow.html . Rankine–Hugoniot and concave-flux entropy solution; triangular-specific formulas here are derived, not copied from its quadratic example.
