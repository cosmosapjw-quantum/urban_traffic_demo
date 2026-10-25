# 대칭·표현중복·관측량 기반 두 연구 단위

Base1964acf5883baafdc7204d41c9575a1e9f7744d0. 부모zip SHA256 a5cdc69aaffb2f5b7fc84067fe15f17daa087f6e3790f5387a02f30e88ee3d55. 기존 defaults와부모source불변,새연구branch만게시. 사용자현재요청에따라이론+구현을실행한다. native_subagent NOT_RUN;직렬수학유도/CAS/공개반례/실행. 원격전체CI와로컬전일100k는범위밖.

## 구분
물리대칭은고정환경/IC/BC/관측장치를보존하는변환일때만쓴다. 전체geometry와field를같이좌표변환하는것은passive covariance다. ID치환,polygon경계시작점/방향변경,동일미래법칙의질량fragment분할은표현중복이다. 삼각분할/시간격자변경,속도분포축약,관측정보삭제는일반적으로gauge가아니라수치/물리근사다. 질량/면적/체류장부는보존식,공분산trace와시간차는변환불변량,통행시간/접근분포/차종유량은측도와검출위치를정한관측량이다. 해시변화는물리차이가아니다.

## M: 면적측도와출입구
기존한활동점대표대신uniform area라는명시적prior로simple polygon을해석한다. 면적/중심/공분산은정확한polygon적분으로,내부최단접근시간은polygon visibility graph와면적quadrature로계산한다. 내부속도는선언한접근mode이고실제건물/보행data를보정하지않는다. 각삼각형의직경/반경으로Lipschitz적분오차범위를보고한다. 실제atlas의큰오목block에서기존점값과면적평균/상위분위/다중출입구를비교한다. 경계ID/ring표현에불변,좌표모멘트는covariant. 유한삼각분할차이는오차내근사이지exact gauge라부르지않는다. 공공도로와전체도시인구를새로생성하지않고출입구계획/수요표현을개선한다.

## T: 이름순을제거한집계packet
부모실제반례:동일한대칭합류에서source lane ID만바꾸면두OD평균4.46/7.74s가7.74/4.46s로바뀐다. 이름순이물리적동시합류순서가되는결함이다. 새별도network는동일경계시각의입장에명시적exchangeable mixing closure를둔다. 패킷의route composition과질량/출생1차모멘트를보존하고,차로head내고정비율흐름과합류priority를함께적용한다. 늦은서로다른입장시각의FIFO는보존하고동시시각의임의ID순서는제거한다. 같은route/같은target의fragment는측도상합쳐도동역학과평균체류가같아야한다. age-dependent physics/quantile는이quotient로보존한다고말하지않는다. dt내실제시간순서를boundary에서섞는것은명시한approximation이며연속networkFIFO증명이아니다.

## 실행과종료
M모멘트/오목visibility/오차/label반례->구현->실제atlas관측/그림->mapcommit. T동시합류ID반례/fragment분할->packet구현->보존/공급/공유FIFO/독립lane/반대칭대조/동일입력짧은도시실험->trafficcommit. 마지막영향회귀·원격readback·압축번들·복사가능handoff. 별도native review를한것처럼기록하지않는다. 연구범위의추가모형선택은문서에명시하고재승인루프로멈추지않는다.
