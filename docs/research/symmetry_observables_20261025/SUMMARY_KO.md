# 대칭·표현중복·관측량 기반 지도와 교통 결과

Base1964acf5883baafdc7204d41c9575a1e9f7744d0. Branch research/symmetry-measure-packets-20261025. 지도1bfb3f589403e7ff187cf684e19b7f05d8db11e5,교통bf2325d1d9b6146fe79290d9ddf9ca5069280c6c. 상세보고서는납품REPORT_KO.md,분리유도는이branch의MAP_KO/TRAFFIC_KO.md에있다. 부모97개Python파일과main/default는변경하지않았다.

## 1. 세 축의 구분
물리대칭은환경/IC/BC/관측조건을고정한F(gS)=gF(S)다. 같은공급·priority의합류팔교환은대칭,한쪽priority변경은물리변경이다. 전체geometry/field의같은좌표이동은passivecovariance이며고정지형안의도시회전과다르다.

ID치환,polygon경계시작점/방향/공선표본,동일미래법칙·target의mass조각은표현중복이다. 질량분할은일반적으로군작용이아니므로새gaugefield를만든것이아니다. 정확한축약은QF=FbarQ와O=ObarQ의지정범위에서판정한다. 삼각분할·dt·활동prior·서로다른시간의혼합은일반적으로gauge가아니다.

질량은source/sink를포함한보존장부,완료량은시간변화하는관측,공분산은covariant이고trace/det는좌표불변이다. 같은총질량/총체류라도집단별통행시간이다를수있다. 원점·ID에불변인값이라고경험적으로검증된관측이되는것도아니다. 추진/제동이있는차량계에운동량·에너지보존이나Noether정리를자동적용하지않는다.

## 2. 지도 이론·구현
AreaAccess는simplepolygon의uniformplanararea를활동측도로선언한다. 실제주민data가아니다. 기존boundary도로node를portal로두고T(x)=min_j[d_B(x,d_j)/u+c_j]를polygonvisibilitygraph로계산한다. 오목영역바깥shortcut은금지한다. 기존Atlas.landscape의수계/보호mask를검사하고공공도로/블록경계는불변이다.

A,mu,C는triangle의정확한0/1/2차다항적분으로계산하며mu'=Rmu+a,C'=RCR^T,E|X-d|²=tr(C)+|mu-d|²를쓴다. geodesic제곱거리를Euclidean항등식으로대체하지않는다. centroidquadrature에서는각triangle내1/u-Lipschitz성과Cauchy-Schwarz로

    |<T>-sum w_k T(c_k)| <= sum w_k sqrt(tr(C_k))/u

를직접유도하고계산한다.4분할마다상한이절반이되는것을검산했다.이는선언한모형의적분오차상한이며activityprior·floatingpredicate·p95의오차상한이아니다. rotation후재삼각분할의유한quadrature는정확한gauge가아니므로결합오차범위로비교한다. boundary표현과ID는정규화로동등하다. portal후보오차가겹치면not_excluded집합을남기고고유최적해를선언하지않는다.

실제8km지도에서이전증분점유가큰block3개를고정했다. 하천pointproxy23.0747m→uniformarea평균142.6559±9.0616m,p95추정227.4504m. 계곡64.0009m→238.8945±13.3087m,해안34.1373m→146.9475±9.8689m. 추가boundaryportal시나리오의평균은각122.8874/160.1725/126.3428m. 원래3Dsinglepoint와새planarareamean은서로다른측도다. 실제주민거리의실측보정이나공사완료·도시전체교통개선을뜻하지않는다. 새분포를아직citydemand에재주입하지않았고private접근을중복더하지않는다. Q=384/512/384는주민수와독립인적분노드다.

## 3. 교통 반례와 수정
부모동일합류에서도로ID만교체하면F/G평균4.46/7.74s가7.74/4.46s가됐다. 총체류12.2veh·s는그대로였다. actual부모동작의2RED를보존했다.100fragment입력은부모6.08/6.12s,최대202parts였다.

새PacketNetwork는같은numericalboundary입장을exchangeablymixedpacket으로표현한다. 더오래된packet은FIFO,동시질량은ID순서가없다. 이는알려진serialorder를정확히압축한것이아니라새혼합closure다. 그다음같은law/route/target/tag의fragment를질량과birth1차moment로합치는것은정확한표현quotient다. 서비스비율theta에대해theta(m1+m2)=theta*m1+theta*m2,출생moment도같고eventtime/공급은합계만사용한다. tag는관측용이며우선순위가아니다. agequantile/age-dependentcontrol/다른class법칙은닫히지않는다.

node는q_i<=S_i,sum beta_ij q_i<=R_j의weightedmax-min정책이다. positivefraction이막히면공유packet은막히고독립lane은진행한다. priority3:1의물리적변경은유량을3:1로바꾼다. 모든nodeinvariance정리나최대throughput을보장하지않는다. 공통거리clock,OLD빈공간예약,endboundary진입은부모원리를재사용하고I_system=sumI_road+I_source+I_transfer와mass장부를매step검사한다. Z와target을같은상수만큼이동하는distanceorigin은진짜표현중복이다. 시각원점은signal/incident까지같이옮겨야동등하다.

새모형F/G평균은6.1/6.1s,ID교체후와100fragment후도같다. 최대4parts. 202->4는작은제어의기록수이지도시메모리benchmark가아니다. 공급/storage/mass를함께1000배한유사계의정규화오차1.7764e-15,기록수동일이며고정도시차량수증가와다르다.

## 4. 실제 도시 관측
같은하천계획39groups/6routes,신규1500주민에서150veh를60초방출하고300초관측. 부모완료1.608006/active56.436626/pending91.955367,새완료1.799511/active56.245122/pending91.955367veh. peakparts902/745,최대storage비1,질량잔차각4.2633e-14/2.8422e-14veh. 둘다HORIZON_REACHED,전체mean=null. 동시혼합closure도달라졌으므로완료량·기록차이를순수압축/실제교통개선으로해석하지않는다.10만배경주민은미수송.

새모형도시에서모든도로/노드/tag와리스트순서치환후최대점유차8.88e-16veh,완료차2.22e-16veh,총체류차1.4552e-11veh·s,tag출구moment차1.4211e-14veh·s,기록수동일. rawhash는정상적으로달라졌고역대응된관측으로판정했다.

## 5. 검증과 경계
새지도8+교통11=19,부모215와합234tests. 겹치지않는150/63/21묶음이모두exit0. 부모reference12포함,전체repoCI아니다. 최초map2는singlepoint/straightseam,traffic2는actual부모RED. 나머지는추가회귀이며전부TDD라고하지않는다. 빈packet오류의별도RED/GREEN도보존했다.97부모Python파일바이트불변,새core2의remoteGitblob확인,Python3.13.5,stdlibAST/python-S/compileall통과.

실제JSON의6그림중하천block과합류반례를직접열어검수했다. CAS초기protectedC오류는숨기지않고cv로정정후trace/det잔차0을얻었다. 단위정방형평균거리(sqrt2+asinh1)/3,trianglevariance1/9,질량·birthmoment·시각origin장부잔차0도확인했다. native_subagent NOT_RUN. 실측/전일100k/whole-repoCI/연속gap도시통합/유한정보route통합은미수행이다.

다음은substep입장시간을더보존할때혼합관측과recordcost를비교하고,면적prior를실제building/activity가중으로확장하는한정작업이다. mesh변화나새혼합물리를gauge라고부르지않는다.

```bash
PYTHONPATH=src python -m pytest -q tests/test_area_observables.py tests/test_packet_quotient.py
PYTHONPATH=src python -S tools/run_symmetry_observables.py --part map
PYTHONPATH=src python -S tools/run_symmetry_observables.py --part traffic
PYTHONPATH=src python -S tools/run_symmetry_observables.py --part city --seconds 300
PYTHONPATH=src python -S tools/check_observable_contracts.py
python tools/plot_symmetry_observables.py
```

parent입력JSON은납품에보존됐다. 원격source만받으면이전atlas/blockfluxrunner로같은입력을재생성해야한다. 원문대조: Görnerup/NilssonJacobi2010 DOI10.1142/S0219525910002542의닫힌선형축약동기,Smits etal2015 DOI10.1016/j.trb.2015.01.002의node모형비유일성과turn보존,Chen/Song/Ortner2024 DOI10.1111/cgf.15053의접근설계동기. Author/publisherabstract범위이며그정리를본비선형모형검증으로전용하지않는다.
