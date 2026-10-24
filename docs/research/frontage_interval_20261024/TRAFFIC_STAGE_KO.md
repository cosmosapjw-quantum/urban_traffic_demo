# 교통 계산 단계: interval reference와 packed-grid 후보의 분리

Pure Python 연구용 opt-in 경로다. `Model`의 기본 동작은 유지하며 `_mature/_arrival/_pack/_residence`만 정책 seam으로 분리했다. 부모와 shared130tick/switching500tick 상태 및 fingerprint가 정확히 일치했다. gain-loss 활동도, 합법turnDijkstra, node allocation, committed suffix의 원래 구성은 유지한다. 사용자는 차량별 운동이 아닌 mesoscopic 계산을 원하며, 이 조건을 성능실험의 선택기준으로 삼았다.

`IntervalModel`: [a,b)의 일정 유량을 [a+tau,b+tau)로 이동하고 출발/도착/신호/폐쇄/queue depletion 경계에서 substep을 나눈다. 단일10초,두링크20초,부분시간 수요,signal queue1.91초,source backlog2.2초를 해석기준과 대조했다. 시간구간별 일정 유량에서 system residence 증가 S*h+(in-out)*h²/2를 쓴다. 동일rate연속구간을 합치고 수치적으로같은rate를 상대1e-12로 합치는 경우 cumulative mass와1차moment 변화상한을 기록한다. 이 표현오차는 비선형 전체교통해 오차정리가 아니다. 활동도는 fixed bulk cadence에서 진입delay snapshot을 갱신한다. FullFIFO/LWR충격파 해법이 아니다.

그러나 최초 도시시험은48.55초에24000record예산을 넘었다. 다중주기/구간sweep수정후60초는통과했지만241substeps/약4.35s와3515records였고 legacy동일60초는12ticks/약0.107s였다.400substep stress는68.340835초까지만 진행했다. resource stop과checkpoint를 보존한다. 따라서 이 구현은 소규모 연속시간 oracle/reference이며 도시기본후보로 채택하지 않는다.

`PackedModel`: 입력수요/신호/incident의 모든경계를dt에정렬하도록 요구한다. 기존정수clock의2tick행정지연을 제거하고,같은suffix에 일정질량이연속도착하는tick구간을(첫tick,끝tick,mass_per_tick)으로저장한다. 합칠rate는정확히같아야하며 양의질량pruning은없다. Residence는한tick의source/completion을일정rate로해석한trapezoid다. 고정freeflow경로에서는T_dt=sum ceil(tau_e/dt)*dt,0<=T_dt-T<링크수*dt다. 이오차경계를혼잡/신호/전체망일반정리로확장하지않는다. Frozen-entry시간에의한추월/FIFO결함과prestep storage의보수성은남는다.

10초oracle에서legacy20/14/12/11s(dt4/2/1/.5),packed12/10/10/10,interval10/10/10/10이다. 일정source80s의도착record는packed/interval1개이며legacy는4/6/11/21개다. Packed의unaligned입력은ValueError이며시간경계를둥글려통과시키지않는다. 도시의28s green때문에기존dt5가아닌동일dt2를양쪽에사용했다.

동일370road/100OD/100k주민stock의300초: legacybaseline완료15.479407,peak7631records,packed17.458534,peak2853records. 양쪽released480.963399veh,보존잔차<=1.3e-12veh,full journey mean=null이다. 도로수요의남은3300초를완료했다고말하지않는다. 교량폐쇄대조도동일입력으로수행했고packed완료18.266375,peak2932record였다. 짧은horizon완료량의증가를일반교통효율이나Braess증명으로부르지않는다. walltime은단일sandbox측정이며전체성능인증이아니다.

새map의실제accesssite2개를O/D로삼은희박freeflow실험에서경로가새spur로시작/끝남을확인했다. Grid연속기준145.4993s/packed154s,organic75.0062/82s이며5links*dt2=10s오차상한내다. Access구간자체가각각약24.23s/10.4~10.8s를부과하므로0비용teleport가아니다. 전체구역OD를새접근로에재할당하거나intrazonal수요를해결한것은아니다.

최종분리실행: numeric79passed, map23passed, 합102. 전체한번실행은45s host timeout으로완료판정하지않고두묶음의exit0을근거로삼는다. 새시험34개=map7+interval17+packed10. 원격repo범위90개와번들parent-reference12개는다른범위다. independent native subagent/전체repoCI/Python3.12/로컬100k전일/실측calibration은NOT_RUN. 실제코드/입력/로그/막힌후보/그림은최종번들에보존한다.
