# M1: atlas block의 실제 접근과 느린 점유

부모1fff1b5666aaef20313686d8916e1e22dd223916. 새모듈만추가,기존source불변. block polygon과Atlas.landscape의수계/보호polygon을권위로쓴다. 중심점이오목polygon밖이면내부후보로바꾸고,경계node까지선분의모든경계교차사이구간이내부인지검사한다. 전체block의mask검사는보수적이다. 지형경사<=.12와2m반폭의mask거리를통과한최단유효접근을선택한다. 중심선의block내부성을확인했을뿐도로포장면/필지소유권/모든junction안전은보증하지않는다.

접근선은지상face생성도로와별도인private access이며본래street graph/block boundary는변경하지않는다. 새접근node를pointteleport로쓰지않고실제길이와속도5/(1+3*grade)m/s를반환한다. 단일대표활동점의거리이며전체주민의block내부이동분포를해상하지않는다.

기존주민H0는보존하고신규유입B와미배치P에sum(H-H0)+P=B,각H<=K를적용한다. 새주민은commissioned access를가진빈용량에먼저배치하고,남으면길이예산안에서min(P,vacancy)*A/length가큰접근을건설한다. A=sum J exp(-T/600s),T는기존합법회전그래프의free-flow와양쪽access시간이다. J는기회이지추가취업배정이아니다. 목적지jobaccess는선언된기존시설이며주거access신규예산과별도장부에그길이를남긴다. 전체부동산시장/혼잡feedback/새간선최적화는아니다.

5개행동반례RED후GREEN,영향지도회귀와합쳐33passed.8km부모지도3개를그대로읽어매epoch500명x3회,500m예산으로실행했다. 각부모100000명불변,신규1500명배치,미배치0. 주거access총길이는하천50.438609m,계곡324.443736m,해안84.212994m다. 가까운경계의대표점에큰빈용량이있는block이유리해지는편향은공사길이효율점수의명시적한계다. 이숫자를도시전체접근교통의해결로해석하지않는다.

다음T1은신규증분만generic visit vehicle-equivalent로바꿔actual access-street-egress경로를수송하는독립공통clock network다. 신규주민을기존40000filled jobs에추가취업시켰다고말하지않는다. Native subagent/전체repoCI/전일100k/실측보정NOT_RUN.
