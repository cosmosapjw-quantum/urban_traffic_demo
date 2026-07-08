# Visualization and UI

## 목적
왜 막히는지, 언제 바뀌는지, 어떤 intervention이 무엇을 바꾸는지를 읽는 navigator-style UI.

## 최소 레이어
- zones / barriers / major corridors
- edge congestion
- generalized cost
- bottleneck intensity
- selected OD corridor flow
- incidents

## 패널
- weekday/weekend
- time-of-day
- play/pause/speed
- top bottlenecks
- average travel time
- accessibility delta

## observables
- mean link speed
- queue length distribution
- route entropy
- reroute count
- bottleneck persistence
- accessibility loss
- person-hours lost

## 기술 원칙
- viewer는 decimated state만 받는다
- frame skip 허용
- logging artifact를 실제 현상으로 오독하지 않게 metric 정의를 문서화
- 중간 지도 품질 검토는 `metroflow.ui.static_map`의 static HTML/SVG artifact를 우선 사용한다
- static city map은 road class, zone/POI, bridge, queue/congestion overlay를 포함하지만
  interactive viewer나 품질 검증 판정은 아니다
