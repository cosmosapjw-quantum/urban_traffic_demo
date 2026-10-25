# T: 식별자와 집계 조각이 합류 물리를 결정하지 않도록 구성

부모 ordered_network의 실제 대칭 합류에서 source group ID만 a/b로 바꾸면 관측 집단 F/G의 평균 완료시간4.46/7.74s가7.74/4.46s로 바뀌었다. 전체 체류량12.2veh·s는 같아서 질량/총시간 검사만으로는 잡히지 않는다. 동일질량을100조각씩 나눠 넣으면 부모 결과6.08/6.12s와 최대202records였다. 공개부모동작2개RED를 보존했다.

새 PacketNetwork는 별도 연구모형이며 기존 defaults는 바꾸지 않는다. 같은 numerical boundary에 입장한 질량에는 exchangeable mixing을 명시하고, 다른 과거 입장 packet의 FIFO는 유지한다. ID는 관측 tag이며 물리적 우선순위가 아니다. Packet은 공통거리 target과 route별 mass/birth moment를 저장한다. 같은 future route, 같은 law, 같은 target에서 같은 관측tag의 조각은 합칠 수 있다. 원래 개별 age quantile이나 age-dependent control은 이 상태만으로 재현하지 않는다.

물리대칭: 같은수요/같은priority/같은supply인대칭합류에서F/G의평균은같다. priority3:1로바꾸면유량이3:1로달라져야하며이를gauge로제거하지않는다. 표현중복: ID치환,입력리스트순서,같은질량fragment분할,공통거리origin의동시이동. 시간원점은signal/closure/source관측까지함께이동해야동등하다. 서로다른실제시간을boundary에서섞는것은정확한gauge가아닌추가closure다.

선두packet에 beta_ij의고정route비율을두고0<=q_i<=S_i,sum_i beta_ij*q_i<=R_j를만족하는weighted progressive filling을사용한다. 이것은max-min priority정책이며모든node invariance조건/전역최대throughput을입증한것은아니다. 차단된양의turn fraction은같은공유packet을막지만독립group은막지않는다. OLD공간예약/endboundary진입과분리된source/transfer residence장부는부모원리를재사용했다.

관측: 질량·차로점유·그룹별완료량·출생/완료1차모멘트·총체류·수치이관대기. 동일fragment에서q*(m1+m2)/M=q*m1/M+q*m2/M, birth moment도같으므로이관측을위한집계가선형으로교환한다. 임의coarse-graining이아니라지정한동등관계에서의quotient다. Floating roundoff는별도허용한다.

최종newtraffic11tests통과. 부모ID반례와달리새모형은F/G6.1/6.1s,이름교체후도같고100fragment입력후도같다. 최대기록4개다. 202->4는해당작은대조이지도시전체메모리절감률이아니다. 39group/6route의같은도시입력300s에서label/node/tag전체치환시최대점유차8.88e-16veh,총체류차1.46e-11veh·s,record수동일. 서로다른바이트hash를물리차이로판정하지않았다.

도시부모와새혼합모형의300s대조:150veh방출,부모완료1.608006/active56.436626/pending91.955367,새완료1.799511/active56.245122/pending91.955367. peak parts902->745. 이는혼합closure도달라진비교라순수압축효과나실제교통개선으로해석하지않는다. 각mean=null,HORIZON_REACHED. 배경100k주민교통은미실행. 기존scalar활동도/pointservice를재사용하며연속gap closure,유한정보dynamicrouting,후방shock와전일100k는미통합/미검증이다.
