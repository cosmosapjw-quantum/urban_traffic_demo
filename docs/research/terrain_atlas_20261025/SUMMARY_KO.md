# 지형·도시유형 지도 생성과 세 차례 시각수정 결산

2026-10-25. Base c462c3f20b5e5c0c81b821f3c41910fbc3143f4b. 이번은 지도만이며 부모교통/main/default는변경하지않았다. 교통실행이아니라 새 RoadMap을기존compile_traffic에실제로통과시켰다. 상세유도·모든회차지도/로그는납품번들 REPORT_KO.md에있다.

## 구성
8×8km,64km²합성영역,높이는64×64patch bilinear terrain,물과보호구역은polygon이다. Flat/river/coast/valley/lake와planned/polycentric/radial/corridor를교차시킬수있다. 후보망은제한된평면매립망이며실측도시나학습모형이아니다.

표면경로비용은 L[1+5(g/.08)^2],교량은4L,회전은lambda(1-cos theta),lambda=2*size/resolution[m]다. 양의등가건설길이이며통행시간이아니다. incoming-edge A*는후보망에서꺾임을고려하고물/보호구역/8%경사를위반하는도로를선택하지않는다. 정착중심지·외부gateway를잇는간선,연결성장,infill의세단계다. phase는건설연도가아니다.

교량은실제수계를건너는후보chain중40~900m,grade8%이하,보호구역배제,양안선형고도+8mcrown deck의지형clearance를검사한다. 최대3개및간격0.13*영역크기조건이다. 하중/홍수위/통항안전은미해상이다. 새로운atlas에는지상도로와수계교량만있다. 옛고가본선/램프코드는보존하지만이번생성에자동이식하지않았다.

bounded half-edge face는연결평면망에서E-V+1과대조한다. 분할의rank변화0,component연결0,내부chord1과비용양수성을명시적WolframLanguage로검산했다. 개발block은법적필지가아니다. 면적5000~180000m²,2A/P>=20m,단순경계,마스크비중첩,보수적지형경사조건을통과한면에고정용도/밀도와net65%용량을준다. 불충족면은open_space다. 목표인구는용량을넘겨증대하지않고pending으로남긴다. 부분polygon clipping은미구현이다.

중요: 수계/보호구역의권위는 Atlas.landscape.water/protected다. RoadMap.terrain의레거시rectangle mask는비어있으므로옛rectangle-only zone_city/attach_zones를그대로사용하면안된다. 새지도identity는향후routing/landuse cache를무효화하며점유된교통world에hot-swap하지않는다.

## 실제 세 시각수정
1. 하천도시의계단식간선과원형도시의중심tree를확인했다. 각도비용과primary orbital을추가했다. 두실패시험뒤같은시험통과.
2. 닫힌block만개발하는현재모형에서서비스대상이없는nonarterial fringe leaf를제거했다. 중심지/gateway/간선은보존했다. 계곡에서87구간제거. 이는실제주거cul-de-sac의보편적금지가아니다. 용도색상범례도추가했다.
3. 교차행렬에서radial/coast와radial/valley의분리orbital fragment가Euler검사를실패했다.8km해안반례는790+6nodes의두성분이었다. 각각의가능한순환구간을허용경로로root에연결하고도달불가능5후보는거절했다. 최종786nodes/1346segments의단일망이다. UNACCEPTED결과를보존했고gate를완화하지않았다.

마지막회차closeout의평지방사형에서는공유끝점의공선선분에대한roundoff-sized determinant가가짜교차를만들었다. 정확한좌표반례를기록후직선공유끝점의기하성질로감사함수를수정했다. 실제동일방향겹침은여전히거절한다. 지도형태를추가수정하는네번째회차는없다.

## 최종 여섯 사례
모두size8000,resolution42,seed17,100000주민/40000일자리stock. node는degree2분절점도포함하며전부실제교차로수는아니다.

| 사례 | node | 구간 | 길이km | bounded faces | 교량 |
|---|---:|---:|---:|---:|---:|
|planned_plain|1017|1861|354.517|845|0|
|polycentric_river|992|1579|303.695|588|2|
|radial_plain|1049|1853|359.278|805|0|
|coastal_port|890|1402|266.799|513|0|
|valley_city|533|758|138.464|226|3|
|lake_city|946|1466|280.018|521|0|

모두독립연결검사1component,검사된비공유중심선교차0,불법표면수계통과0,보호구역통과0,경사8%이하와인구장부를통과했다. 하천/계곡교량각1개씩제거해도연결되지만모든교량동시폐쇄·교통용량을보장하지않는다. 여섯최종그림은실제저장JSON을렌더링했다.

4km/resolution20/목표20000주민의4형태×5지형20조합도연결/기하검사를통과했다. 그러나polycentric/valley898명,radial/valley585명,corridor/lake1149명이용량부족이다. 이결과를실패없는인구충족으로보고하지않는다. 하나의seed에서크기/해상도를함께바꾼것이므로수렴·확률적uncertainty검증은아니다.

최종육안판정에서도반복mesh,강한극좌표대칭,직각간선,산지쪽공백,외생중심지/산업위치는남는다. coastal_port는산업prior의이름이며항만부두/물류모형이아니다. 그림색은용도이지인구밀도가아니다. 실제도시형성·경험적현실성PASS는부여하지않는다.

## 검증과 재현
납품격리workspace: 부모177+신규21=198passed,31.33s,exit0. 부모source/test/tool75파일바이트불변. 신규4과학코어remote blob=실행본. stdlib AST,python -S,compileall확인. 그림만matplotlib/NumPy. 전체remote repoCI,Python3.12,독립native subagent,실측보정,전일100k교통은NOT_RUN.

```bash
PYTHONPATH=src python -m pytest -q tests/test_terrain_city*.py
PYTHONPATH=src python -S tools/run_terrain_atlas.py --case polycentric_river --stage replay
PYTHONPATH=src python -S tools/run_terrain_atlas.py --case valley_city --stage replay
PYTHONPATH=src python -S tools/check_atlas_matrix.py artifacts/terrain_atlas_matrix_replay.json
python tools/plot_terrain_atlas.py artifacts/terrain_atlas_20261025/replay/polycentric_river.json
```

같은out/case는덮어쓰므로새stage/out을쓴다. 좌표는local metres이며위경도GeoJSON이아니다. runner는diagnostic이고최종gate는receipt의실제contacts/components/masks/stock을읽어판정한다. 원격은source/tests/요약/receipt를저장하고모든rawJSON/PNG/SVG/중간실패로그는납품번들에있다.

## 문헌 적용
Galin et al.2010 DOI10.1111/j.1467-8659.2009.01612.x의지형비용경로,Chen et al.2024 DOI10.1111/cgf.15053의도로/필지접근연결,Boeing2019 DOI10.1007/s41109-019-0189-1의복수형태지표를참고했다. Publisher/author HTML과초록확인범위이며원알고리즘전체·도시데이터재현을주장하지않는다.

다음한정단위는이번block경계를기존access_development의느린점유·건설루프에연결하는것이다. 고가/램프추가시지상face와전체routing graph를분리한다. 현재교통물리를이번지도성과에따라승격하지않는다.
