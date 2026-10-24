# 움직이는 간격과 유한 제동의 조건부 kinetic 구성

2026-10-24. 지도 fae7ca986d0dfcffada08ff77b2c3e9472cf1d54 뒤의 교통 이론/코딩 단위. 기존 active_suffix 10개 source는 첨부부모와 byte-identical하며 도시물리·Dijkstra를이모형으로교체하지않았다. 개별차량이아니라 고정된수의 weighted conditional phase nodes를진화시킨다.

## 상태와 명시적 추가 가정
각질량대표점은 (class,mass,x,h,v,w)다. h는범퍼간빈거리[m],v,w는뒤차/앞차속도[m/s],x는뒤차위치[m]. 앞차는조건부mark이고별도의차량량으로두번세지않는다. 실제속도는연속이고정지시0에서포화하며음속도/순간속도보정을하지않는다. 앞차가속도aL는외생scenario이므로자기일관적인전체platoon의pair hierarchy는아직닫히지않는다.

동역학은 dx/dt=v,dh/dt=w-v,dv/dt=u,dw/dt=aL다. 제어는길이Delta동안유지되고0속도에서제동가속도는0으로정지한다. 최대제동b>0,최대가속a>0,앞차가속하한-B,직접측정한현재gap/speed,즉시제어적용을가정한다. 차량간격의관측지연이나actuatorlag는여기에포함되지않는다. 대신선두차속도는과거보고만허용한다. truthful report(wobs,tobs)와aL>=-B이면 w_actual(now)>=w_lower=max(0,wobs-B*(now-tobs)). 제어함수는실제p.w를읽지않는다. 미래보고또는보고/제동bound와모순되는물리상태는계약오류로거절한다.

선호정책은부모의 u_pref(h)=min(Uroad,Uclass,max(0,(h-h0)/T))를유지한다. held nominal acceleration은 (u_pref-v)*(1-exp(-Delta/tau))/Delta를[-b,a]로자른다. 이는안전보증이아닌명시적행동가정이다. 다음안전집합안에서만가능한가속도중nominal과가장가까운값을선택한다. 이는허용된운전자class의모형이며모든인간행동의자연법칙이나경험적calibration이아니다.

## 최종정지거리만으로는안됨
뒤차20m/s,b8m/s²와앞차15m/s,B2m/s²가즉시제동하면최종이동거리차는25-56.25=-31.25m다. 그러나둘이아직움직일때 상대이동은5t-3t²이고 t=5/6s에서25/12m=2.083333m에달한다. 최종정지위치차만0으로clamp하면이접근량을잃는다. CAS의exact값은5/6,25/12,-125/4다. 같은문제계열은Sidorenko et al.2022,doi:10.1109/TIV.2022.3209910의원저자기관abstract에서확인했다. 이구성을새로운안전이론이라주장하지않는다.

## 채택한 안전집합과 직접 증명
Xf(t;v,u,Delta,b)는u를Delta동안유지한뒤-b로정지하는뒤차변위다. Xl(t;wlower,B)는앞차가즉시-B로정지하는최소변위다. E(u)=sup_(t>=0)[Xf(t)-Xl(t)]>=0. 허용조건은 h-h0>=E(u)이며 u in [-b,a]. 속도0포화와제어변경시각에서구간을나누면각변위는최대2차다. 전체최대는0,Delta,앞차/뒤차정지시각,각구간의상대속도0시각중하나다. 수치표본최대로대체하지않고이유한후보집합을검사한다.

증명: 비교원리에의해실제앞차변위는Xl이상이다. 실제뒤차는채택한held control동안Xf와동일하다. 따라서0<=t<=Delta에서 h_actual(t)>=h-[Xf-Xl]>=h0다. 다음제어가계산되지않아도기존계획의full-braking fallback을실제로적용하면이부등식은계속성립한다. 매구간accepted control을이어붙이면검증된구간의불변성은귀납적으로따른다. 이는정확한산술과명시한상한/현재gap측정/actuation을가정한조건부명제다. 일반도로망,끼어들기,불확실한gap,초기상태전체에대한안전정리가아니다.

u를늘리면뒤차의전궤적변위는감소하지않으므로E도단조다. E(-b)>h-h0이면이robust certificate는비어있다. 원상태를보존한ViabilityError를반환한다. 보수적정보때문일수있으므로이를물리적으로피할수없는충돌정리로부르지않는다. 그렇지않으면nominal이허용되면그대로쓰고,불허이면56회bisection으로[-b,nominal]의허용상단을선택한다. roundoff residual은사전에1e-9m로분리했으며gap좌표를snap하지않는다.

## kinetic 의미와상하향관계
보고/기억상태를포함한분포G의한제어구간weak generator는 v*d_x+(w-v)*d_h+u*d_v+aL*d_w다. 내부에서partial_t G+partial_x(vG)+partial_h((w-v)G)+partial_v(uG)+partial_w(aL G)=0이며0속도경계는정지질량을포함하는측도로해석한다. 대표점의질량은고정이고flow를push-forward한다. 평균gap변화는E[w-v]와연결되며평균gap만으로개별선호제어를대체하지않는다. 다른class/정보를구분하는대표점을무조건merge하지않는다. 도달비용도같은구간의적분궤적에서최초root를계산하고inverse mean speed를대신쓰지않는다.

이는일곱관찰의모든빈칸을닫지않는다. leader law의상위상관closure,도로별공간분포/밀도와pair spacing의일관성,전역거시feedback,주행중navigation은남는다. 기존도시수송은여전히별도의activity closure다. 이모듈의exact passage를기존도시routing비용에만삽입하는비일관성은만들지않았다.

## 실행결과
신규교통14tests통과. 최초final-stop/frozen-gap candidate는4failed/5passed였으며,구간말도착시간측정은별도1RED후실제first-hit root로수정했다. 나머지추가시험은regression이다. 60개seed고정초기상태×25단계에서최소gap1.9999999999999913m,선언h0=2m. 별도60개무작위envelope를1001시점의독립직접계산과비교했다. 반올림차와표본화오차상한을구분했다.

30초급제동/재출발:같은nominal law에서안전filter를제거하면gap=-3.610075m인물리적겹침이발생해실행을중단했다. Filter와선두보고지연0/.5/1/2s에서는최소gap2.044209/2.044635/2.044635/2.053773m,질량100고정. 지연동안gap은현재직접측정한다는가정을잊지않는다. 새로운정보가전혀없는초기조건을실제truth로채우지않도록초기보고는별도선언된초기지식이다.

103m/10m/s자유류에서dt2/1/.5/.25s모두동일한연속구간root10.3s를얻었다. 이는그자유류제어문제의검증이지일반혼잡수렴증명은아니다. 동일분포대표점질량을10만배해도대표점2개,물리궤적은같고총질량만10만배다. 10만명각각의상호작용/도시전일운송을실행한것은아니다.

전체격리workspace 142passed(부모123+지도5+교통14),Python3.13.5,stdlib compile/import통과. full repo CI,Python3.12,실측보정,전일100k,별도native subagent심사미실행. SciSpace/Exa는가정검토용이며정밀외부모델benchmark는없다. 연구branch에만게시한다.
