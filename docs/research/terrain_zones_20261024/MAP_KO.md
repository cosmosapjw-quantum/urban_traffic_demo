# 지형과 토지이용의 유한용량 환경

계산식·구현·시험을 갖춘 작은 연구 환경이다. 기존 generator나 production default를 교체하지 않는다. 지형(느린 외생 입력) -> 도로 허용성 -> 구역 개발용량 -> 실제 인구/일자리 stock 순서다. 도시 전체의 형상을 격자로 바꾸자는 제안이 아니라 환경 제약을 검사하는 coarse fixture다.

## 지형과 도로
Raster 정점 높이[m] 사이의 bilinear 표면을 선언한다. cell의 gradient norm 최대는 네 모서리에서 얻는다. 각 성분은 다른 한 좌표의 affine 함수이고 norm은 convex이므로 모서리들의 최대가 내부를 지배한다. 표면 도로는 raster boundary를 따라 선형으로 놓이므로 경사는 |dz|/horizontal_length다. 3D 길이는 sqrt(horizontal_length^2+dz^2)다. 일반적인 곡선/절토/터널은 미구현이다.

물/보호구역은 폐쇄 rectangle이다. 선분과 rectangle의 연속 교차를 검사하므로 dry endpoint 사이의 좁은 강도 뛰어넘지 못한다. 도로 반폭만큼 확장한 rectangle은 원형 buffer보다 보수적이며 corner 오거절은 가능하다. 강 건너 도로는 선언한 bridge row에서만 생성하고 span<=1000m, grade<=0.12를 요구한다. 이는 bank-to-bank 선형 deck의 기하 gate이지 교량 구조설계나 홍수 해석이 아니다. 자동 연결 복구로 경사/수계 조건을 무시하지 않는다.

합성 fixture는 river, hill, protected woodland를 명시한 prior다. 지형 연구의 비유클리드 비용 관점을 사용하지만 Galin et al.의 전체 알고리즘을 구현한 것은 아니다. construction_index_m는 length*(1+4*grade^2)와 bridge 배수4의 authored 지수이며 금전이나 공사예산의 보정값이 아니다.

## 구역과 유한 stock
Raster cell이 물/보호/50m 수변 exclusion과 겹치거나 build slope>0.10이면 cell 전체를 배제한다. 이는 부분 clipping이 아닌 보수적 해상도 근사다. 가장 큰 도로 component에 frontage가 없는 cell은 inaccessible로 남긴다. 다른 graph component 자체는 삭제하지 않는다. 산업구역의 실제 cell footprint에 150m buffer를 적용하며 주거를 배치하지 않는다.

허용 토지는 residential/mixed/commercial/industrial/civic/park로 나눈다. Net developable area는 cell의65%라는 명시적 prior다. 고정 persons/jobs/visitor places per net hectare에서 floor한 capacity를 얻는다. residential(230,15,15), mixed(340,250,75), commercial(0,550,120), industrial(0,180,0), civic(0,90,220)이다. 경제·지가·주택시장 모형 또는 실측 calibration이 아니다.

N_z=min(K_z,lambda*w_z)의 capped water filling 이후 largest remainder로 정수 stock을 분배한다. 총수는 정확하고 각 capacity를 넘지 않는다. O(Z^2) 상한이며 주민 한 명씩 반복하지 않는다. 수용량 부족은 ValueError이고 밀도를 자동 증대하지 않는다. 인구 stock와 교통 vehicle-equivalent를 혼동하지 않는다.

## 실제 검증
최초 공개 seam RED: terrain5개, stock5개. 산업구역 중심 rectangle만 buffer하던 반례를 추가 재현하고 실제 할당 cell 경계로 수정했다. 최종11개 시험 통과. 6/8/12 raster 크기 x seeds7/17/41의9개 생성 및 stock/gradient 검증 통과. 작은 지형의 급경사 고립 component는 보존한다. River 연결 시험은 flat-height fixture로 분리해 bridge와 hillside 효과를 혼동하지 않는다. 이는 수용 오차 변경이 아니다.

재현: `PYTHONPATH=src python -m pytest -q tests/test_environment_terrain.py tests/test_environment_landuse.py` 및 `PYTHONPATH=src python -S tools/run_environment_map.py`.

Python3.13.5. stdlib scientific core. native_subagent NOT_RUN; CAS+직렬 반례/실행. 그래픽/실도시 calibration/전체저장소CI/로컬100k full-day는 미실행이다.

문헌: Galin et al.(2010), Procedural Generation of Roads, doi:10.1111/j.1467-8659.2009.01612.x; Galin et al.(2011), Authoring Hierarchical Road Networks, doi:10.1111/j.1467-8659.2011.02055.x; Waddell(2002), UrbanSim, doi:10.1080/01944360208976274. 재사용는 terrain feasibility와 land-use/transport 층 분리의 동기이며 이 코드를 해당 논문 재현이라고 부르지 않는다.
