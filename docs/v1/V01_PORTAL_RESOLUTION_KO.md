# V01 등록 출입구 차단 해소 연구

## 대상과 채택한 구성

기준 소스는 `2e4b11547a7ff8bf2ce5ccf53c55ccc2a84d141c`의 포털 없는 V02 동결 지도다. 원본 도로·지형·블록·주민을 유지하고 `generated_entries.generate_entries`가 새 합성 출입구를 가진 별도 `CitySnapshot`을 구성한다. 출입구는 기존 시설에 대한 추론이 아니라 명시적인 신설 모델이다. 기존 source archive와 새 patch는 각 SHA256, parent/new city identity로 연결한다.

조건은 장애물이 없는 유효 블록 polygon, 균일 면적 활동 prior, 평면 접근속도 1.4 m/s, 출입구 폭 2 m, 최대 경사 0.12, 출입구별 선언 용량 1 veh/s이다. 마지막 용량은 engineering prior인 admission rate이며 일일 교통의 receiving/storage 또는 수요 수용 검사를 대체하지 않는다. 인구별 loop 없이 면적측도를 적분한다.

각 활동 블록의 경계 꼭짓점을 후보로 만들고, 해당 꼭짓점을 포함하는 삼각분할 triangle의 centroid에서 꼭짓점까지의 유한 길이 corridor를 시도한다. `compile_entry`가 실제 block 내부, 제외 polygon과의 폭 포함 간격, 지형 경사, 양의 길이와 용량을 검사한다. 유효 후보 중 좌표·corridor 순서로 한 문을 선택한다. 이 순서는 명시된 합성 배치 정책이며 최적 출입구라는 주장은 하지 않는다. 실패 블록의 주민은 미서비스량에 남긴다.

## 유향 연결의 구성적 근거

도로의 유향 link를 정점으로, compiler의 `allowed_turns`를 유향 간선으로 갖는 그래프를 쓴다. 선택된 하나의 strongly connected component(SCC)를 S라 하자. 문 p가 있는 실제 지상 node에서 출발하는 link a_p∈S와 그 node로 도착하는 link b_p∈S를 각각 확보한다. 임의의 문 p,q에 대해 SCC 정의로 a_p에서 b_q까지 유향 경로가 존재한다. 각 그래프 간선은 compiler가 허용한 실제 turn이므로, 그 경로는 p에서 출발하여 q로 도착하는 합법적 도로 경로다. 반대 방향도 같은 논증으로 존재한다. 링크의 단순 접촉이나 무향 연결을 이 조건으로 대체하지 않는다.

원본 `planned_plain` seed7의 독립 검사에서 3,714개 link 중 첫 link의 SCC에는 3,710개만 속했다. 전체 도로가 하나의 SCC라는 가정은 사용하지 않는다. 구현은 iterative Kosaraju로 성분을 계산하고 각 문에 departure/arrival link 증거를 기록한다. 실도로의 사건 폐쇄와 동적 혼잡은 별도 시간 의존 검사다.

## 접근시간과 CDF의 적분

등록된 실제 문 집합 P_b에 대해 접근시간은 T_b(x)=min_{p∈P_b} d_b(x,p)/v 이다. d_b는 블록 안의 최단 평면 경로이고 v=1.4 m/s다. corridor의 construction length를 여정 지연에 다시 더하지 않는다. 주민량 N_b와 면적 A_b를 써서 도시 CDF는 전체 요청 인구 N을 분모로 Σ_b (N_b/A_b)∫_{B_b}1[T_b(x)≤t]dx로 정의한다. 미서비스 주민은 유한 접근시간 CDF에서 빠지지만 분모에는 남는다.

삼각 cell i의 centroid c_i, 정규화 면적 무게 w_i, 지연 τ_i=T_b(c_i), 기존 quadrature RMS radius r_i를 사용한다. triangle은 convex이므로 내부 두 점 사이의 직선이 허용된다. 따라서 |T_b(x)−τ_i|≤|x−c_i|/v≤R_i/v이며 R_i=√12 r_i는 모든 꼭짓점까지의 거리의 상한이다. 실제 CDF는

- F_lower(t)=Σ_i w_i 1[τ_i+R_i/v≤t],
- F_upper(t)=Σ_i w_i 1[τ_i−R_i/v≤t]

사이에 있다. 주민량으로 가중한 도시 합에도 같은 부등식이 유지된다. 가운데 centroid CDF는 quadrature 추정이며 표본 p95를 인증된 quantile로 재명명하지 않는다. 평균 오차는 기존 Σ_i w_i r_i/v 경계를 재사용한다.

## 루프 수행과 근거 상태

R1–R3에서는 기존 V01의 등록 출입구 부재와 M03의 실제 corridor 계약을 읽고, 합성 신설·서비스 존재·시간 적분·동적 용량을 구분했다. R4–R5에서는 경계 triangle corridor와 공통 legal-turn SCC를 선택하고 위 도달성과 CDF 경계를 직접 유도했다. R6에서는 독립적으로 compiler 방향·turn 의미와 면적 적분 코드를 대조했다. R7의 원본 한 지도 SCC 계산은 실제 실행됐으며, 전체 38개 구성 실행 결과는 `artifacts/v1_portal_resolution_20261027`의 지도별 audit/patch와 종합 영수증을 따른다. R8–R10의 V01 판정·남은 의무·재개점은 실제 결과를 확인한 뒤 PLAN과 해당 영수증에 기록한다. 이 문서의 수학적 구성만으로 전체 실행 통과를 예고하지 않는다.

C1–C5는 기존 `compile_city`, `compile_activity`, `compile_entry`, `activity_access`를 재사용한 새 구성 모듈과 체크포인트 runner로 연결된다. C6–C8의 실제 테스트·38개 지도 결과와 C10의 게시 identity는 영수증을 따른다. C9 독립 코드 검토는 SCC 간선 방향, 최종 snapshot identity로의 entry 재검증, 전체 인구 분모, 부분 서비스 상태의 차단 유지, CDF radius 대응을 확인했다. 원본 patch로부터 새 도시를 재구성할 때 source archive hash와 parent/new identity를 모두 검사해야 한다.

새로운 불가능성 정리를 주장하지 않으므로 strong no-go 채택은 해당하지 않는다. 실패가 생기면 그 입력의 후보 부족·기하·연결·자원 원인과 보존된 미서비스 인구를 기록한다. 검증의 완료 여부는 생성된 문 수만으로 판정하지 않는다.

## 동일 기하의 재사용

`CitySnapshot.with_portals`는 이미 compile/load된 불변 snapshot에서 portal registry만 교체한다. 도로·지형·stock·legal-turn network를 그대로 재사용하고, full compiler와 공유하는 `_validated_portals` 및 `_city_identity`를 적용한다. corridor 검증은 각 후보와 최종 snapshot에 대해 계속 수행한다. 이 경로는 신뢰된 compiled snapshot의 동종 registry 갱신으로 한정한다. 임의로 수동 구성한 network의 물리 검증을 대체하는 API로 사용하지 않는다.

`test_portal_only_update_matches_full_compile_and_rejects_bad_contact`는 registry 입력 순서가 달라도 full compile과 새 snapshot의 identity 및 직렬화가 같음을 검증한다. 독립 재실행에서 `tests/v1/test_generated_entries.py tests/v1/test_city_contract.py`는 Python 3.12에서 20 passed(1.76 s), Python 3.13에서 20 passed(1.60 s)를 얻었다. 본 검증은 공유 identity helper, 물리 contact 거절, source identity 일치, CDF 구간 및 미서비스 장부를 포함한다. 전체 지도 캠페인의 실제 결과는 지도별 영수증을 따른다.

## 실제 구성 결과와 판정 범위

38개 `*.audit.json`을 확인한 결과 새 출입구 총 19,993개를 구성했고, 모든 지도에서 `registered_unserved_residents=0`, 실제 entry validation과 legal-turn connectivity가 PASS였다. 지도별 요청 주민 100,000명을 보존한 결과다. 완료된 38개 실행의 내부 wall 시간 합계는 750.62 s, 최대는 43.81 s였다. `corridor_river` seed17(index34)은 병렬 실행 중 45 s 한도로 중단됐으며, 다른 계산 종료 후 동일 45 s 한도에서 단독 재실행하여 18.04 s에 완료됐다. 최초 timeout은 `CAMPAIGN.json`에 보존되어 있다.

원본 index0과 patch로부터 새 snapshot을 복원한 `REPLAY.txt`는 identity `14487f8be6f7606d50e200d719fbdd447b6e1acf89b30f08010de495022b037e` 및 829개 출입구의 일치를 기록한다. 나머지 각 지도는 source hash/parent identity와 새 patch hash/new identity를 보존한다.

이에 따라 등록 출입구 부재와 접근성 미지원이라는 V01의 특정 finding은 새 합성 지도 버전에서 해소할 수 있다. 원본 V02 동결 지도에서의 실패 기록은 유지된다. 실제 일일 수요를 새 지도에 배정하고 동적 receiving·storage·경로·미완료 장부를 실행하는 의무는 계획된 V03에 남으며, 여기서 얻은 출입구 존재와 정적 연결 근거와 구분한다. V01 전체 상태는 나머지 물리 fixture와 현재 소스 영수증을 함께 확인하여 PLAN에 기록한다.
