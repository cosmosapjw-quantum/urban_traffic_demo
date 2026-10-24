# 원 프로젝트의 도로 형태·구조 계약을 지형 위에 복원

2026-10-24. 연구용 stdlib kernel, production default 불변. 기존 코드를 그대로 rollback한 것이 아니라, 원 프로젝트의 검증 가능한 계약과 일부 문법을 작은 Python 구현으로 이식했다.

## 복원 근거와 경계
`IMPLEMENTATION_ROADMAP.md`/`ARCHITECTURE_OVERVIEW.md`@77060c84b75195c8a05273e0d1a809caf93e63d4는 bulk transport와 behavior closure 분리, bridge/corridor/merge toy suite, ranked paths, lagged land use, lane grammar/node compiler의 장기 순서를 보존한다. `CITY_MAP_PR_LIST.md`@81f3f09be648cf0669c102c1f4eb33765114f489의 PR33-64와 PR65-82를 읽었다. 도로 profile은 static geometry와 집계 용량으로 컴파일하며 개별 차로 추적을 뜻하지 않는다. 과거 PR62 morphology 0/30, PR63 성능/실현인구 실패, PR67 이후 NOT_REACHED는 그대로 역사적 실패다.

`morphology_capabilities.py`@c9168100367d027f94dd33b848955af2cba3e060의 grid_core, organic(정확히 warped grid), superblock_mixed, ring_radial 구조를 이식했다. polycentric_tod의 전체 중심지 모형과 180-leaf grammar, tunnel 구조/굴착, 실제 OSM은 복원 범위 밖이다. PR#22 및 scalable_topology.py@c3d7d1b424f49791b0c25b98e8c05b40d0a48bc7에서 forward-only ON/OFF ramps, structure failure group, endpoint/layer authority를 채택했다. 원 코드의 NumPy runtime, 오래된 per-car pool을 다시 도입하지 않는다. 정확한 별도 제목의 '초장기' 문서를 특정하지 못했으며 전체 archive 전수조사를 주장하지 않는다.

## 실제 모형
4.8km 정방형, 합성 river/hill/protected land를 사용한다. Local/collector는 방향당1lane, arterial은2lane, expressway는 one-way2lane, ramp는 one-way1lane다. 수계는 지정 bridge/mainline만 통과하며 protected land와 급경사는 거절한다. Bridge deck는 양안 선형 높이+8m crown의 명시적 polyline이고 하중/홍수/구조설계가 아니다. Two separate mainline carriageways, 양안 ON/OFF ramp, 세 surface bridge group을 생성한다. XY 투영 교차는 junction을 만들지 않는다.

Bilinear terrain을 선분으로 제한하면 h(u)=A u²+B u+C이므로 경사 dh/ds=(2Au+B)/ell의 최대절댓값은 patch endpoints에서 얻는다. Deck-terrain gap도 quadratic이므로 endpoints 및 0<u*=-B/(2A)<1인 극점을 검사한다. 내부 clearance는 C-B²/(4A). 따라서 sparse sampling으로 놓칠 buried ramp를 막는다. Ground arclength는 각 patch에서8panel Simpson으로 근사하며, endpoint chord가 아니다. Cubic Bezier ramp의 끝 접선은3(P1-P0),3(P3-P2)로 mainline 방향을 맞춘다. 이 식들은 Wolfram과 별도 analytic fixture로 확인했다.

Surface road contact와 grade-separated crossing을 분리한다. Shared endpoint만 연결 권위다. 다른 centreline crossing에는5m 이상 높이차를 요구한다. 도로 반폭만큼 확장한 rectangle으로 보호구역/수계를 보수적으로 검사한다. 일반 road-to-road pavement envelope, 곡률 설계기준, full lateral clearance는 인증하지 않는다.

## 세 시각 반례와 수정
1. 최초 ring ramps가 반대 mainline을 .42~.78m 높이차로 가로질렀다. 8개 illegal contacts. Both carriageways를 먼저 배치하고 각 방향 바깥쪽 접근 후보를 택한 뒤 높이차를 검사했다.
2. 수정 뒤에도 ramp가 hillside 안으로 organic -.166m, ring -.997m 들어갔다. Exact quadratic deck-ground minimum gate를 추가했고 다른 허용 후보로 대체했다. 경사/clearance 문턱은 낮추지 않았다.
3. 직선 ramp의 mainline 접속각이 다수55~77도, organic97.8도였다. Directed Bezier tangents와 진행방향 제약으로 교정했다. 세 차례의 RED/GREEN과 그림을 별도 보존한다. 마지막 외관이 좋다고 실제 도시 형태 PASS를 선언하지 않는다.

## 토지이용 연결
기존 terrain/zone capacity 배분은 재사용한다. `zone_city`에 optional frontage_nodes를 추가했고 기본 격자 API는 보존했다. 실제 layer0 surface junction만 접근점으로 삼는다. 구역중심에서500m 이내이고 물/보호/급경사를 통과하지 않는 접속을 검사한다. 이 거리와 접근가능성은 측정하지만 access/egress 통행시간 및 intrazonal transport는 아직 해상하지 않는다. 가장 큰 weak component에만 주민을 배치하며 hillside의 다른 component를 억지로 연결하지 않는다.

## 실행 결과
새 지도시험15passed, 기존 landuse6passed. Four styles x seeds7/17/41=12개 실제 생성·접촉·경사·용량 시험. 모든 사례 100000residents/40000jobs를 용량 내에 배치했고 illegal centreline crossings=0이다. Bridge3, mainline10, ramps7~8. Grid/superblock은 weak component1, organic/ring은2가 남았다. 이 결과를 전체연결성 PASS로 바꾸지 않는다.

Seed17: grid118nodes/194roads, organic122/194, superblock117/167, ring137/209. 주거수용량 grid/superblock165464, organic163072, ring112840. 원래 도로군의 형태 차이를 재도입했지만 terrain-response가 낮은 규칙적 직교구획, ring 중심부 공백, 격자형 zoning, undeveloped fringe 및 고속도로 끝점의 외부 gateway 수요 미설정은 남는다.

재현: `PYTHONPATH=src python -m pytest -q tests/test_restored_map.py`; `python tools/render_restored_city.py`. Scientific core는 stdlib, 그림만 matplotlib다. Python3.13.5; 전체repositoryCI/실도시calibration/native independent review는 NOT_RUN.

문헌의 적용: Galin et al.2011 DOI10.1111/j.1467-8659.2011.02055.x의 terrain-aware hierarchy 동기, Beneš et al.2014 DOI10.1111/cgf.12283의 settlement/environment coupling 동기. 특정 생성 알고리즘이나 empirical accuracy의 재현을 주장하지 않는다.
