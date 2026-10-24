# 느린 접근·개발 연구 단위

Base eed80ea54378281bf79994caf7348ce0b3009bbb. 순수Python, main/default 불변. 기존 road grammar,지형,합법회전,시야gate를재사용한다. native_subagent NOT_RUN: 직렬구현/CAS/반례검증.

사이트에는 실제 footprint,고정수용량K,현재주민H,지상access node,opened_epoch를둔다. 도로가가깝다는이유만으로access를부여하지않는다. 새주민은기존접근가능한vacancy에먼저배분하고,대기수요가있을때만접근로를건설한다. H_total+pending=offered,0<=H<=K,신규중심선<=예산을유지한다. 기존주민을재배치하거나capacity를늘려통과시키지않는다.

기회접근성 A_p=sum_j J_j exp(-T_pj/tau),건설점수=min(pending,K_p)*A_p/new_length. T는실제방향/층/합법회전그래프의free-flow시간이다. 신호/혼잡은이번slow목적함수에서제외하며실현통행시간과동일시하지않는다. J는일자리기회이고취업배정이아니다. 후보접근로를물리적으로만든뒤평가하며채택마다graph접근성을재계산한다. 가장짧은적격frontage를후보로써전역경제/도로최적화는아니다. 주택비용/용지비/건설기간은생략한명시적모형이다.

현재site는외생으로선언한빈80m정방개발지이며법적필지자동분할이아니다. 종전구역의spare capacity>=95를확인하고8site에각95명cap을준다. 배경100kstock은선정근거로고정하고신규360명(120x3epoch)의별도장부만추적한다. 각epoch의완료인구120/240/360,신규도로2/1/1. 네형태모두새4site접근,불법중심선교차0,cycle rank불변. grid800.009484m,organic361.433371m,superblock800.010719m,ring128.111754m를썼다. epoch마다450m예산이다.

새7tests는미구현seam에서실패확인후구현;관련부모와20tests통과. 같은평지의일자리anchor를좌우로바꾸면개발위치도반대로변한다. 접근없음/예산없음/보호footprint/도달불가능일자리에서는주민을대기에보존한다. 기존빈용량을쓸수있으면새도로를짓지않는다.

문헌동기: Waddell et al.(2010), Microsimulating parcel-level land use and activity-based travel, JTLU https://www.jtlu.org/index.php/jtlu/article/view/124. 접근성↔위치선택연결의원문초록을확인했으며그자료/모형/추정법을재현한것은아니다.

다음traffic단위: 기존fixed-entry-delay의같은차로순서역전을common-distance-clock과FIFO서비스로다루는별도reference,그리고K개주기패턴ring의정확한대칭축약. 기존도시core를덮어쓰지않고한정검증후게시한다. 전체repoCI/경험적도시형성/로컬전일100k/게임비교는범위밖이다.
