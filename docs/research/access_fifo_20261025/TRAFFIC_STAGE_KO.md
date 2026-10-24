# 두 단일차로 reference: 공통시계와 주기 ring

부모도시core를바꾸지않는추가모듈이다. 주문형fullFIFO를모든도시교차로에강제하지않는다. ordered_lane은동종공통drift+FIFOfluidserver,periodic_gap은주기패턴의정확한대칭축약이다. 둘은아직하나의kinetic도시solver가아니다.

공통drift:v(t)=U*p(t),p'=alpha-(alpha+nu)p. Z(t)=integral vdt에대해s에진입한질량의출구도달은Z(A)=Z(s)+L. Z가증가하면A'(s)=v(s)/v(A)>=0. 구현은지연값을진입시고정하지않고Z_target=Z_entry+L을저장한다. FIFO서버는먼저들어온집단부터처리하고blockedhead를넘지않는다. Source는tick시작의batch이며같은시각tie순서가입력에명시된다. 입구용량과storage는boundarysplit,출구service는tick내first-passage와연속rate다. spatialshock/finitegap queue는미해상이다.

누적관측:road_vehicle_seconds=(admitted-completed)*now-entry_moment+exit_moment. system에는외부sourcewait를별도로포함한다. quote는같은drift와서버에서얻되fixedrate/supply,no미래경쟁,즉시진입조건부다. nu가density로변하면frozenforecast이며정확한미래비용이아니다. 반경·정보를그대로이식하지않고이새reference의역할을명시한다.

기존Packed반례의early40s/late23s순서역전은현재도시core에남겨보존했다. 새boundarybatchreference에서는early출구14.239134~14.339134s,late20.534951~20.634951s. 원source는0~1/10~11sflowbin,새source는0/10satom이므로시간차를matched물리성능향상이라부르지않는다. 구조적순서성의비교다. 103m,10m/s,batch2veh,exit1veh/s에서first10.3,last12.3,mean11.3,road/systemresidence22.6veh*s를예측과실행이함께낸다.

Ring:K개class/gap/speed패턴을r회반복한다. 제어는모두oldstate에서계산하고,동일한실제dx_leader를사용해h_i_new=h_i+dx_(i+1)-dx_i로갱신한다. 합은망원경상쇄되고L=r sum(h_i+ell_i),markedleader/followermarginal일치가유지된다. deterministictranslation-equivariantlaw아래repeat(F_K)=F_Kr(repeat)라는정확한대칭축약이다. arbitrarypairclosure가아니며주기성을깨는사건은더많은representative를요구한다. 현재localgap/speed는정확한관측,선두제동bound와즉시actuation을재사용한다.

4representatives반복7회와28states직접계산을240steps비교해gap/speed/displacement차이0. 길이1540m잔차6.82e-13m,marginalL1=0. 4states반복25000회는100000vehicles를표현하지만물리lane길이5500km다. 이를10만주민도시성능이라고부르지않는다.

추가로32state작은Fourier섭동에서safetyinactive조건의이산선형행렬과비교했다. dt=.5/.25/.1s에서성장률.04119246/.03875046/.03724645 per s. 코드모드와행렬오차<=7.27e-15m,filter개입0. 불안정성을성공조건에서제거하지않았다. 연속극한분산식tau*lambda^2+lambda-a*(exp(ik)-1)=0은Wolfram잔차0;limit과정Power/Infinity경고는기록하고무경고라고말하지않는다.

새traffic18tests와지도7tests,부모152합177passed(20.90s). 새로운stubRED후구현과추가regression을구분한다. 정지출발dt1e-16에서distance가0이되는소거오차와NaNledger통과는실제두RED뒤수정했다. scientificcorestdlib;전체repoCI/실측/전일100k/독립subagent는NOT_RUN.

재현: PYTHONPATH=src python -m pytest -q tests/test_ordered_lane.py tests/test_periodic_gap.py ; PYTHONPATH=src python -S tools/run_access_fifo_traffic.py. 지도organic결과가같은outputdir에있으면실제로생성한98.100223m접근로단일방향에도연결해mean12.417407s를확인한다. 도시전체OD/교차로연결은이번단계밖이다.
