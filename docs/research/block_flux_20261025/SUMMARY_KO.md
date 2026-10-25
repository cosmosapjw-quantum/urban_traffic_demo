# 블록 개발에서 순서 보존 수송까지: 한정 결과

2026-10-25. Base1fff1b5666aaef20313686d8916e1e22dd223916. Branch research/atlas-block-flux-20261025. 지도bd743fefe0d6dece7894348f1fe2722a3a25c95d, 교통8d7182344c0b7184de026f4c5e5a335289a526c2. 전체 직접유도·실험입력·체크포인트·그림은 납품 REPORT_KO.md와번들에있다. 원부모88개source/test/tool파일불변,main/default불변.

## 지도
Atlas.landscape polygon을권위로block내부활동점에서실제경계도로node까지private access를만든다. 오목polygon의선분은경계교차로분할한모든열린구간을내부검사한다. 전체block과mask중첩은거절하며,접근선은2m mask거리와12%경사를검사한다. 기존public street/face는바꾸지않고실제길이와5/(1+3g)m/s의선언속도를전달한다. 포장면/소유권/모든junction안전인증은아니다.

기존주민H0를보존하고새점유H,미배치P,유입B에sum(H-H0)+P=B,H<=K를강제한다. 먼저개통된접근의vacancy를채우고남은수요에서min(P,vacancy)*A/length가큰접근을예산내건설한다. A=sum J exp(-T/600s),T는private접근+legalstreetfreeflow+목적지접근시간이다. J는기회이지새근로자의filledjob배정이아니다. 목적지접근은선언된기존시설이며새주거접근예산과별도장부다.

8km하천/계곡/해안지도각100000기존주민에서500명x3epoch의신규1500명은모두수용됐다. 새주거접근총길이50.438609/324.443736/84.212994m. 실제상세그림에서하천의큰오목block은23.07m접근한점으로신규797명을대표한다. 이는singleactivitypoint와길이효율선택의편향이며전체block내부이동분포를해상한결과가아니다.

## 교통 이론과 구현
새ordered_network는기존ordered_lane의동종commonclock Z'=U*p,p'=alpha(1-p)-nu*p,nu=nu0+beta(N/K)^2를재사용한다. 같은group에target=Z(entry)+L을저장하므로도달순서가보존된다. 선두route질량만node에보내고선두가막히면같은group의뒤집단도대기한다. 독립group은대기하지않는다. 합류에서는모든선두가downstream공급을공동으로나눈다. priority3:1,총수용1veh/s대조는.75/.25veh/s였다.

OLD점유량에서R_j=min(mu_in*dt,K_j-N_j)를예약하므로새로비워지는공간은다음step에사용한다. 각node가같은budget을중복사용하지않으며유량은선두질량·보내는율·받는율·예약공간을넘지않는다. 내부서비스는도달/소진/공간소진시각에서구간을나눈다. downstream진입과source진입은step끝이다. source는내부예약뒤에배분한다. 신호/폐쇄는dt정렬을요구하고비정렬입력을반올림하지않는다.

[a,b]에유출한질량m이t1에진입하는수치적holding=m*(t1-(a+b)/2). 이를물리적혼잡으로부르지않고별도누적한다. 각링크N'=N-O+sumF+A와source P'=P+B-sumA를합하면internalF가상쇄된다. 실행마다

    released=completed+pending+sum occupancy
    I_system=sum I_road+I_source_wait+I_transfer

를검사한다. 두보존대수잔차0,서비스구간의holding적분은명시적WolframLanguage로검산했다. 자동WolframContext검색결과는근거에서제외했다.

동시에합류한연속유량은endboundary에서시작/끝시간·source·route의결정론적batch순서로놓는다. 명시그룹안의FIFO이지모든연속서브질량의perfectnetworkFIFO정리는아니다. finite전체storage가공간shock파속이나차간거리안전을보장하지않는다. 연속gap모형및유한정보dynamicrouting은이번network에미통합이며기존모듈을유지했다.

## 도시 연결 실험
신규1500명*.2방문*.6자동차person비율/1.2탑승인원=150vehicle-equivalent다.120noncarperson-trip은별도다. 취업배정이나10만기존주민의전체교통이아니다. 경로는실제private–street–private이며초기freeflow고정경로다. Public도로당한방향의한reference공유차로만사용해fullmultilane을무조건FIFO로강제하지않는다. 신호는full기하에서28s녹색/2sclearance로만들고빈경로제거로주기를줄이지않았다.

하천:6경로/39group,60초방출150veh,1초격자,1676초전량완료. 평균932.889619s. road체류77179.082530veh·s,외부대기61988.677797veh·s,수치이관765.682498veh·s,합139933.442825veh·s. 질량잔차<=2.274e-13veh,최대storage비1,최대record1560. 기록수가차량량보다많을수있으며성능우월성을주장하지않는다.

계곡:2400초요청hosttimeout으로완료근거없음. 별도120초관측은18경로/102group,150veh방출,완료2.733422,active70.979399,pending76.287179veh. 질량잔차<=2.843e-14veh,최대storage비1,최대record1529. 평균시간null,HORIZON_REACHED,상태보존. 물리gridlock/구현오류로단정하지않는다.

두링크210m/10m/s의dt1/.5/.25/.125초대조:총평균22.705/21.705/21.455/21.205초,도로체류만21.010초. source와interface대기를따로보고한다. 일반도시수렴증명이아니다. 공급·storage·질량을함께1000배한대조의정규화오차3.55e-15,기록16개로동일. 정적Braess65→80분을재확인했으나새fixed-route도시의동적UE시험은아니다.

## 검증과 재현
부모198+신규17=215개. 단일전체호출은host시간제한으로제외했고150/44/21의세분리묶음이모두exit0이다. 신규지도5·network6·localledger1은실패후수정,추가5개는구현후회귀다. 3새scientificcore는원격Gitblob과일치한다. block_access의빈줄1개차이는AST동일성과영향7tests로확인후납품byte를맞췄다. Python3.13.5,stdlib AST/compileall/python-S통과. 전체repositoryCI,3.12,독립subagent,실측,전일100k,게임비교NOT_RUN.

```bash
PYTHONPATH=src python -m pytest -q tests/test_atlas_block_access.py tests/test_ordered_network.py tests/test_block_visit_plan.py
PYTHONPATH=src python -S tools/run_block_flux.py artifacts/terrain_atlas_20261025/final/polycentric_river.json --traffic --out artifacts/block_flux_replay
PYTHONPATH=src python -S tools/check_block_flux.py artifacts/block_flux_replay/CONTROLS.json
```

parent atlas JSON은납품에있으며원격source만받으면parentrunner로같은seed/size/resolution을먼저생성한다. 다음은continuousnodehandoff의순서정보와calendar증가의trade-off,그리고큰block의multipleactivity/access표현이다. 원리적연속속도를버린것이아니라기존조건부수송을실제도시입력에연결한검증단위다.

원문헌: Waddell et al.2010 DOI10.5198/jtlu.v3i2.124의입지/교통결합동기(Exapublisherabstract;directweb403); Tampère et al.2011 DOI10.1016/j.trb.2010.06.004의node공급/보존조건(publisherabstract/introduction); Salehi et al.2018 DOI10.1177/0361198118792997의불필요한차단/재경로구분(publisherabstract). 해당전체모형이나모든invariance정리를재현했다고주장하지않는다.
