# M: 면적활동측도와출입구 계획

기초prior는주민별객체가아닌simple polygon의uniform planar area다. 수계/보호polygon이없는실제atlasblock만대상. 원래경계와공공도로는불변. 출입구는기존surface 경계node이고새공사완료나필지분할을주장하지않는다. 평면내부최단거리/선언속도+외부시간으로접근을측정한다. 건물/문턱/교통안전/경사속도분포는미포함.

대칭: 균질정방형과대칭인두출입구에서는교환시서비스분담이같다. 외부시간200s를한쪽에추가하면대칭은깨진다. 좌표를전체같이회전/이동하면중심은Rmu+a,공분산은RCR^T. 고정지형안의임의도시회전이대칭이라는뜻은아니다.

표현중복: boundary시작점/순회방향/같은경계상의공선점/portal ID를바꿔도같은기하/관측을얻는다. 서로다른삼각분할이나한점축약은정확한gauge가아니다. canonical triangulation은ID에무관하지만rotation때유한quadrature가달라질수있으므로오차범위로비교한다.

불변량과관측: 면적A,정규화질량1,중심mu,공분산C를삼각형의정확한1·2차적분으로계산한다. trace(C),det(C),E|X-d|²=trace(C)+|mu-d|²는적절한좌표변환에서불변. 평균접근시간T와분위수는분포와속도·출입구조건을명시해야하는관측량이다. polygon visibility graph의geodesic시간을삼각형centroid로적분하고

|E[T]-sum w_k T(c_k)| <= sum w_k sqrt(trace(C_triangle_k))/u

를보고한다. 각삼각형안에서짧은직선이가능하므로T는1/u-Lipschitz; Cauchy-Schwarz로평균거리오차상한을얻는다. 이는이모형의수치적분오차이며uniform prior의현실성오차나floating predicate까지포함하는interval arithmetic인증은아니다. variance/p95는quadrature추정으로만표기한다.

초기singlepoint/straightshortcut baseline에대한두수치RED후구현. 최종8tests통과. 100m정방형corner의면적평균은100(sqrt2+asinh1)/3=76.51957m로centroid70.71068m와다르다. 오목L형shortcut은내부경로3.8172로고쳐진다.

실제8km부모atlas에서큰block3개를고정해관측. 하천기존대표접근23.0747m→uniform area평균142.6559±9.0616m,p95추정227.4504m. 계곡64.0009m→238.8945±13.3087m;해안34.1373m→146.9475±9.8689m. 두번째경계door의한정제안에서는각122.8874,160.1725,126.3428m로줄었다. 외부비용0인내부접근시나리오이고전체도시통행개선이아니다. 기존점값과새평균은서로다른측도에대한관측임을명시한다. 후보오차구간이겹치면유일최적door를선언하지않고not_excluded집합을반환한다.
