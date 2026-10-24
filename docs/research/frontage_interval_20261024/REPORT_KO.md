# 물리적 도시 접근로와 경량 교통 시계의 후속 연구

2026-10-24. Base `e093ecd35e0af1bc940d3fa36ae09bd0a4a3978a`, 지도 단계 `a92bd461a98262963fdb87092878da9b39cf3c7c`, 교통 단계 `d8077c8fafc1e87746b57b55069b3fa0cca119bf`. 연구 branch는 `research/restored-morphology-layered-traffic-20261024`. 기존 production default는 유지한다. 원 첨부 ZIP의 SHA256은 `2b62fcf55c87e70849cbad99ae4fac9ab0dce3826f9d72225649562223557715`다.

## 연구 결정

지도의 다음 질문은 구역의 중심에서 지상 도로까지 실제 연결을 어떻게 만드는가이다. 전체 도시 형태를 다시 바꾸거나 접근을0비용 metadata로 처리하는 대신, 선언한 활동지점을 기존 local/collector road에 연결하는 예산 제한 연산을 선택했다. 교통의 다음 질문은 원래 active-matter 모멘트와 mesoscopic 상태를 보존하면서 잘못된 행정 tick과 도착 calendar 증가를 어떻게 줄이는가이다. 연속 시간구간 해법과 압축된 고정 시간격자를 실제 비교했다. 전자는 소규모 oracle, 후자는 경계가 정렬된 도시 실행의 opt-in 후보로 남긴다. 성능 한계를 발견한 첫 후보를 성공한 도시 solver로 포장하지 않는다.

## 1. 지도: 실제 frontage 건설

각 활동지점에서 지상 local/collector 도로 polyline의 최근접점을 계산한다. 고가 mainline, ramp, bridge는 접근로 부착 대상에서 제외한다. 후보는 도로 폭을 고려한 수계·보호구역 검사, 연속 지형 경사0.12 제한, 비접속 도로의 교차/높이차 검사를 통과해야 한다. 지상 기존도로의 중간을 나누고 spur 하나를 더하면 `ΔV=2, ΔE=2`, 따라서 `Δ(E−V+C)=0`이다. 새 접속점은 지형 높이를 사용한다. 두 자식 길이는 지형 적분 비율로 배분하되 합을 부모의 authoritative 길이와 같게 한다. 기존 map은 immutable snapshot으로 보존하고 새 길이만900m 예산에 넣는다.

각 지점의 최단 적격 접근 후보를 구한 뒤 활동가중치/추가길이로 순위를 정하는 greedy다. 10만 주민/4만 일자리 stock의 배치는 재사용하지만, 전체 도시의 구역 할당을 최적화하거나 신규도로의 교통편익을 보장하는 목적함수는 아니다. 기존 도시 형태·교량·계층을 지우지 않는다. 원문헌[1]은 지형·계층과접속구조의동기이며 같은 generator의 재현이 아니다.

시각·수치 감사에서0.48794m짜리 새 도로가 나오는 반례를 발견했다. 15m미만은 이미 도로에 접한 `already_fronting`으로 구분한다. 새 도로나 완료된 이동으로 세지 않는다. 접속점이 기존junction20m이내면 기존junction을 재사용해2m부모조각도 막는다. 이 두 길이는 연구 설정이지 실측 토목기준이 아니다. 같은 반례 RED/GREEN이 보존돼 있다.

네형태 seed17에 각4개 접근로를 만들었다. 추가길이 grid800.003655m, organic361.433371m, superblock800.003655m, ring186.813959m. 각900m이내, cycle rank불변, 총길이 증가 장부 잔차1e-7m미만, 검사된 불법 중심선 교차0이다. Organic/ring 최종그림을 직접 읽었다. 반복격자·큰빈원형중심·산지에끊긴도로는 남아 있다. 이번 성과는 물리적인 접근 graph이지 전체 도시 형성이나 필지 현실성의 완성은 아니다.

## 2. 원래 교통 아이디어의 불변 부분

자기추진/정지/재출발의 두상태 gain-loss 모멘트는

    C+ = alpha*n0 - nu*n+, C0 = -C+,
    dp/dt = alpha*(1-p) - nu*p, nu=nu0+beta*(N/K)^2

를 유지한다. 동결된 alpha/nu에서 exact relaxation을 쓰고, 실제 이동 및 합법 incoming-link Dijkstra 비용에는 `L/(v0*p)+Q/mu_eff+mean_red_wait`가 함께 작용한다. 이 폐쇄식은 완전한 Boltzmann 충돌 적분을 유도한 것이 아니다. 코드 `kinetic.py`, `routing.py`, `node.py`는 부모와 동일하다. 차로별/차량별 위치추적 없이 질량과 committed remaining-route suffix를 유지한다.

누적 유량에서 통행시간을 정의하는 문헌[2]와 연속시간 network loading[3]은 참고했지만, 그 논문들의 FIFO·LWR·event efficiency 정리를 이번 코드에 옮겨 주장하지 않는다. frozen-entry delay가 변하면 추월 가능성이 남고, exit movement-group 혼합은 perfect FIFO가 아니다. Pre-step finite space로 receiving을 계산하는 기존 보수적 closure도 남는다.

## 3. 첫 후보: 연속 시간구간 reference

`IntervalModel`은 유입 rate r이 [a,b)에 일정하면 [a+tau,b+tau)에 같은 rate로 exit에 도착하도록 저장한다. source/arrival/signal/incident/depletion 시각에 맞춰 구간을 나눈다. 시스템 내 질량 S, 구간길이 h, 방출/완료rate a,b가 일정하면 residence의 증가량은

    ΔI = S*h + (a-b)*h²/2.

이 적분을 전량 수송 후 완료질량으로 나누어 전체 평균 journey를 구한다. 단일링크10초,두링크7+13=20초,비정렬 source,적색 소량대기1.91초,source backlog2.2초를 해석식과 대조했다. 미완료 도시 평균은 null이다. Wolfram은 uniform interval의 시간shift 평균tau, 질량불변, residence식과 지도cycle불변을 검산했다.

첫 구현은 도시 시각48.5533초에24000record예산을 초과했다. 동결 entry-activity snapshot을 fixed bulk cadence에만 갱신하고 중첩rate sweep을 적용했다. 수치적으로 같은 rate는 상대1e-12와시간8ULP 범위에서 mass-preserving 병합하며 cumulative-count 변화와 시간1차moment 오차를 기록한다. 이는 분포표현의 오차장부이지 비선형 전체해의 오차정리가 아니다. 정확한 동률 병합과 수치 근사 병합을 구별한다.

최종 도시60초는241substeps,peak3515records,약4.35s였다. 같은 기존dt5 입력의legacy60초는12ticks/약0.107s였다.400substep 제한에서는68.340835초까지밖에 진행하지 못했고 peak6605records였다. 첫실패와 마지막 유효 checkpoint를 남긴다. 단순 oracle에서의 정확성이 도시 규모 계산 효율을 보장하지 않았으므로 기본 도시후보로 채택하지 않는다. 전역 이벤트마다 모든 도로/기록을 다시 훑는 비용을 줄이는 연구가 별도로 필요하다.

## 4. 선택한 경량 후보: packed aligned grid

`PackedModel`은 기존 Model에서 calendar maturity,arrival 생성,packing,residence 정책만 분리한다. 기본 Model의 두대조630ticks에서 상태와 fingerprint가 부모와 정확히 일치했다. default변경없이 새 opt-in경로만 다르게 계산한다.

수요·신호·incident 경계는 dt에 정렬돼야 한다. 비정렬 입력은 시간경계를 몰래반올림하지 않고 ValueError로 거절한다. 진입구간 [t,t+dt)의 질량은 d=ceil(tau/dt) tick 뒤의 구간에서exit에 도착한다. 같은suffix에서 같은mass_per_tick이 연속되는경우 (first_tick,last_tick,mass_per_tick) 하나로 저장한다. 이것은 개인차량이 아니라 집계유량bin들의run이다. 서로다른suffix를합치지않으며 동률판정은exact float equality다. 병합허용오차나양의질량삭제는없고 float overlap합산오차는별도질량검사로잡는다.

기존의불필요한2tick과 left-rectangle residence누적을 제거한다. 고정rate/무혼잡/신호없음/입력정렬의 경로에서

    T_dt = sum_e ceil(tau_e/dt)*dt,
    0 <= T_dt - sum_e tau_e < (number of links)*dt.

tau/dt의 exact-integer판정은 코드의1e-12 경계roundoff 범위다. 이식은 구간내 포화queue해법을 정확하게 만들지않는다. subcapacity backlog의평탄화오차가 남으며 경로전체의혼잡에위오차상한을 적용하지않는다. 새고정격자와 연속interval은서로다른수치정책이다.

| dt[s] | legacy 평균[s] | packed 평균[s] | interval 평균[s] |
|---:|---:|---:|---:|
|4|20|12|10|
|2|14|10|10|
|1|12|10|10|
|0.5|11|10|10|

상기10초oracle의80초일정유입에서 peak도착record는legacy4/6/11/21,packed1,interval1이다. 이벤트와주민수를같은것으로세지않는다.

## 5. 통제된 도시 실험과 압축 대조

기존370directed roads,100OD schedules,100k주민stock,3600s출발profile의같은입력을쓴다. Green28/offset30초가dt5와정렬되지않으므로 양쪽에dt2를사용했다. 비교중수요/용량/신호를다르게놓지않았다.

| 300초 관측 | 완료veh | 도로내veh | peak records | wall[s], 단회 |
|---|---:|---:|---:|---:|
|legacy baseline|15.479407|465.483992|7631|2.257|
|packed baseline|17.458534|463.504865|2853|2.172|
|legacy 교량60~180초폐쇄|16.330538|464.632861|8084|2.667|
|packed 같은폐쇄|18.266375|462.697024|2932|1.883|

모두released480.963399veh,최대보존잔차1.3e-12veh미만,finite storage유지다. 300초이후수요/전일평균은해결하지않았다. 폐쇄시일부완료량이더많다고효율향상이나Braess평형의증명으로해석하지않는다. 신호위상·유한horizon·경로응답의복합결과다. 별도정적Braess oracle65→80분은여전히유지됐다.

위legacy-vs-packed비교는시계도변한다. 압축효과만분리하려고 같은수정시계/물리/출발선택에서 point calendar와 run calendar를직접대조했다. peak7200→2853records,완료량차이0,점유량최대차이1.3145e-13veh,residence차이7.276e-12veh*s였다. 약60.4%기록감소는이대조에서만압축자체의효과라고부른다. record수가 peakRSS나전체런타임과같지는않다. 위walltime은한번의sandbox측정이며speedup보장은아니다.

새accessmap의선언site2개를O/D로삼는실제운송도실행했다. 희박·무신호·고정activity조건에서 grid의연속기준145.499300s에packed154s,organic75.006185s에82s. 각경로5links,dt2여서오차<10s이고시작/끝은새접근road다. 접근자체가각각약24.23s와10.38/10.80s를부과한다. 전체인구OD를이새접근점들로재배치한것은아니며 intrazonal/last-mile총수요는후속과제다.

## 6. 검증·수정 기록과 주장 범위

지도최초RED3fail/2pass→GREEN5,submetre/endpoint반례RED2→GREEN7. Interval최초RED7fail/1pass→GREEN8,queue/source반례RED2→GREEN10. 도시fragmentation RED는record한계초과이며경계허용값을느슨하게바꿔통과시킨것이아니다. `single_link_fragmentation_characterization_pass`는처음부터통과했으므로RED라고부르지않는다. Packed최초RED6fail/1pass→GREEN7. 추가회귀/대조를포함한새시험34개(map7+interval17+packed10).

전체집중시험은79개수치묶음+23개지도묶음=102passed다. 원격범위90개와번들parent-reference12개를구분한다. 전체한번실행은host45초timeout으로끝나완료근거로쓰지않고,분리한두명령의exit0을근거로삼았다. 원격readback에서interval의지역generator변수명path/p와runner의미사용import차이를확인해정규화했고27개집중시험및oracle을다시실행했다. 행동변경과바이트정규화를혼동하지않는다.

Python3.13.5,compileall,AST stdlib검사와python-S실행을확인했다. GUI/게임rendering은없고그림은검증용matplotlib뿐이다. native_subagent NOT_RUN,동일구현자의직렬반례/CAS/실행이며독립모델심사는아니다. 전체repoCI/Python3.12/로컬100k전일/fullFIFO/실도시calibration/게임대비우월성은NOT_RUN 또는미해결이다.

다음은전체solver의전면재작성보다작은물리경계를닫는순서다. 첫째,정렬시간격자의queue-depletion오차와adaptive delay추월을독립oracle로측정한다. 둘째,누적곡선/잔여시간bin을이용해진짜variable-ratecalendar를압축하되허용분포오차를명시한다. 셋째,새물리접근로와구역person-trip을연결하고미해상local수요를없애는과정에서총인구와차량수요를보존한다. 교량/도로추가의혼잡악화는자동실패가아니지만,그것을수치결함의변명으로도쓰지않는다.

## 원문헌과 재사용 경계

[1] Galin et al., Authoring Hierarchical Road Networks, Computer Graphics Forum30(7),2021–2030(2011), DOI10.1111/j.1467-8659.2011.02055.x. 지형·계층과접속구조의동기.
[2] Long, Gao, Szeto, Discretised link travel time models based on cumulative flows: Formulations and properties, Transportation Research B45(1),232–254(2011), DOI10.1016/j.trb.2010.05.002. 누적유량기반시간정의와인과성/FIFO를분리하는근거.
[3] Raadsen, Bliemer, Continuous-time general link transmission model with simplified fanning, Part II: Event-based algorithm for networks, Transportation Research B126,471–501(2019), DOI10.1016/j.trb.2018.01.003. 다상품event-network법의비교대상. 이번active-delay모형을그논문의LWR해법이라하지않는다.
