# 형성사 기반 도시 지도 적대적 시각 감사

- 기준 커밋: `01c80b432344f94209daaa198bb1eb007839fc7f`
- 최종 fingerprint: `9469afef2b40fcd3389bbc00499008747300116498ed55baf13772f5667c0ff3`
- 감사 범위: 구조적·시각적 개연성, 형성사와 hierarchy의 정합성
- 비범위: 실제 도시와의 경험적 동등성, 교통 성능, 토지시장, 건축물, 지형·수계

## 감사 원칙

이미지의 보기 좋은 정도보다 생성 메커니즘과 관찰 형상의 일치를 우선했다. 각 finding은 관찰된 결함, 도시형성 이론상의 영향, 최소 수정, 재검증 결과로 닫았다. 동일 결함의 맹목적 재시도는 하지 않았고, 최대 3회의 수정 루프를 사용했다.

## Round 0: 희박한 전역 배치

- 증거: `round0_sparse_baseline.svg`
- 지표: 230 nodes, 64 km², road density 1.524 km/km², primary components 10.
- 관찰: 중심부 밖에 긴 고립 가지가 많고 bounded block은 좁은 내부에 집중된다. 도시 외곽이 점진적 탐색 전선이라기보다 드문 tree branch로 보인다.
- 이론 영향: exploration이 densification보다 지나치게 우세하고, hierarchy가 하나의 역사적 backbone으로 지속되지 않는다.
- 수정: 25 km²·320 nodes의 경량 연구 스케일, late node의 causal attachment, epoch별 loop budget.

## Round 1: causal하지만 spider-web에 가까운 망

- 증거: `round1_causal_growth.svg`
- 지표: mean degree 2.825, dead-end share 0.178, road density 4.825, primary components 7.
- 관찰: 연결성과 밀도는 개선됐지만 다수의 짧은 가지와 방사형 fan이 남아 Voronoi/spider-web 인상을 준다.
- 이론 영향: 성숙 district의 국소 survey order와 역사적 arterial continuity가 약하다.
- 수정: densification node의 부분 grid snapping, severe cul-de-sac의 bounded closure, old-core-to-centres/gateways path union.

## Round 2: hierarchy 연결은 복구됐지만 감사 지표가 잘못됨

- 증거: `round2_connected_hierarchy.svg`
- 지표: mean degree 3.194, dead-end share 0.075, blocks 188, primary components 1.
- 관찰: primary backbone은 연결됐고 block mesh도 형성됐지만, global orientation entropy가 높다는 이유만으로 무질서 경고가 발생했다. 일부 primary path는 edge-load 중심 분류 때문에 zigzag가 강조됐다.
- 이론 영향: 서로 다른 방향을 갖는 다핵 district의 전역 다방향성을 국소 무질서로 혼동한다.
- 수정: old core의 radial/tangential 적용 범위를 900 m로 제한, district별 두 survey axes, oriented shortest path hierarchy, local orientation coherence 추가.

## Round 3: 최종

- 증거: `formative_city_final.svg`, `formative_city_final_age.svg`
- 지표: mean degree 3.200, dead-end share 0.0688, road density 5.684, local coherence 0.9245, age–radius Spearman 0.6069, primary components 1.
- 판정: 구조적 gate PASS, error 0, warning 0.

### 최종 장점

- 오래된 중심부에서 더 짧고 촘촘한 edge가 나타난다.
- secondary centres를 연결하는 corridor와 외곽 gateway로 이어지는 primary backbone이 하나의 component다.
- 외연에서 edge와 block이 커지고 형성 epoch가 증가한다.
- global orientation entropy가 높지만 local coherence도 높아, 회전된 district 조직의 공존으로 해석 가능하다.
- crossing 없는 surface planarity와 cycle/block 관계가 유지된다.

### 남은 결함

- 일부 외곽 face가 너무 크고 polygonal하다.
- 곡률, 지형, 수계, parcel subdivision, overpass가 없다.
- pruning이나 철거는 문헌상 중요하지만 구현되지 않았다.
- commercial/industrial/park 색상은 구조적 heuristic이며 경제모형 출력이 아니다.
- 따라서 최종 그림은 도시형성 이론을 반영한 실험적 graph map이지 실제 도시의 시각적 복제품이 아니다.

## 최종 claim gate

`PASS`는 strict replay, causal growth, connected planar graph, hierarchy continuity, block/loop presence에 한정한다. empirical realism과 production default promotion은 `UNRESOLVED`다.
