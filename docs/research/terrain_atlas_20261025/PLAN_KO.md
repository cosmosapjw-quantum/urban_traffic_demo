# 도시 유형·지형 지도 연구 및 구현 계획

Goal: 8km x 8km의 합성 지형에서 도시형태/간선/생활도로/교량/개발블록을 생성하고 최대3회의 실제 시각감사로 교정한다.
Authority: c462c3f20b5e5c0c81b821f3c41910fbc3143f4b; 사용자 이번 요청은 지도만. 부모교통물리/main은변경하지않는다.
Architecture: typed polygon landscape + bilinear terrain; planar candidate substrate; terrain-cost Dijkstra arterial skeleton; connected local growth and infill; explicit bridge candidates; bounded face/finite stock ledgers.
Tech: stdlib scientific core; pytest; matplotlib diagnostic plots only. native_subagent NOT_RUN.

선택: 기존 격자를무조건확대, ML도시복제, 지형제약계층생성 중 마지막. 후보substrate는격자/다핵변형격자/다해상도극좌표/계곡정렬격자이며이를완전한역사적도시형성으로부르지않는다.
시나리오 flat/river/coast/valley/lake, 형태 planned/polycentric/radial/corridor. 기본8km,목표100k주민stock은capacity검사후에만배치.부족시pending장부.실측/DEM/도로설계안전/전일교통없음.

1. landscape module: arbitrary polygon masks, exact segment buffer rejection, synthetic heights. Test narrow obstacle and grade contracts.
2. network module: connected cost paths, dimensioned bridges, local-infill, block extraction and finite stock. Test replay, no undeclared crossing, water bridge-only, Euler ledger, invalid parameters.
3. audit/runner: repeated fixed-seed generation at actual scale; metrics and plots. Record initial images and at most3 coherent correction rounds. Never lower gates or replace seeds to hide failures.
4. verification and publish: affected parents+new tests, stdlib run, GeoJSON and PNG, source hash/result/checkpoint; expected SHA fast-forward research branch per closed stage.

State is immutable; regeneration changes map identity and invalidates future routing/land-use caches. No hot swap of occupied traffic states. Budgets cover input mesh resolution, bridge count/spacing, length; optimization is deterministic greedy/path selection, not global optimum. Land blocks are not cadastral parcels. Whole-polygon exclusion is conservative, not clipped developable area.
