# Research Synthesis

## 최종 결론
- 도시 생성은 단일 procedural trick으로는 부족하다.
- shape/tensor/growth skeleton + CA/LUTI zoning + CSUR lane grammar가 필요하다.
- traffic backbone은 mesoscopic hybrid core가 맞다.
- persistent citizen은 유지하되 active trip만 fast loop에 올린다.
- route choice는 generalized cost + path-size correction + conditional reroute여야 한다.
- learning은 EMA/bandit 먼저, GNN/LSTM은 후순위다.

## 살아남는 두 후보
- S2: WorldState contract + multirate scheduler + cache invalidation
- S1: mesoscopic hybrid core + generalized-cost routing + lagged land-use feedback

## 핵심 리스크
- stale cache
- tick conversion mismatch
- same-tick positive feedback
- meso에 micro realism을 기대하는 baseline mismatch
- logging-driven false confidence
