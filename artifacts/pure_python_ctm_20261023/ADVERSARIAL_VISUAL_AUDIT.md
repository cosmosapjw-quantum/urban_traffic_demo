# 순수 Python CTM 적대적 시각 감사

- 기준: `main@01c80b432344f94209daaa198bb1eb007839fc7f`
- 최종 model fingerprint: `15d3917c30275aaeff72b69ca5c442660457d26b2e81220983e28d833855f8fd`
- 시각 자료: `traffic_audit_rounds.svg`, `final_diamond_evolution.svg`, `final_traffic_timeseries.svg`
- 판정 범위: 작은 controlled network에서의 구조적 교통류 타당성

## 감사 기준

시각적으로 혼잡이 그럴듯해 보이는지만 보지 않았다. 다음의 이론적 질문을 먼저 고정했다.

1. 혼잡이 실제 bottleneck upstream으로 전파되는가?
2. blocked turn이 물리적 이유 없이 다른 turn을 막는가?
3. downstream supply가 남아 있는데 node solver가 flow를 남기는가?
4. merge priority가 starvation 없이 의도한 비율을 만드는가?
5. fixed movement priority가 minority turn을 무한히 굶길 수 있는가?
6. source, cell, movement, sink 간 vehicle identity와 질량이 정확히 닫히는가?

## Round 0, strict FIFO

### 관찰

Diamond corridor에 320 vehicles를 4/tick으로 주입했다. Upper approach incident는 ticks 18-41에 활성화했다.

- tick 80 시점 input link occupancy 약 91%
- peak input occupancy 92.8%
- peak external pending 75
- tick 220에도 77 vehicles active

시각적으로 queue는 incident branch가 아니라 shared input에 과도하게 축적됐다. Lower route receiving과 downstream capacity가 남아 있어도 exit-cell head의 upper movement가 lower movement를 막았다.

### 적대 판정

단일 lane에서 lane-changing이 전혀 없다는 가정이라면 가능한 현상이지만, 2-lane urban approach와 분리된 turning demand에 그대로 적용하는 것은 과도한 full-FIFO artefact다.

### 수정

Movement별 FIFO bucket을 도입했다. 이 선택은 완전한 FIFO가 아니라 lane-group partial FIFO임을 명시했다.

## Round 1, movement-group FIFO

### 관찰

- 320 vehicles가 tick 174에 모두 clear
- peak upper/lower downstream branch cell occupancy 약 86%
- source input peak occupancy 약 31%
- incident 종료 후 branch queue가 점진적으로 해소

`final_diamond_evolution.svg`에서 tick 60-130 사이의 red/orange cells가 merge bottleneck upstream에 남고, tick 174에 사라진다. 이는 finite receiving supply와 backward spillback의 방향과 일치한다.

### 적대 판정

Shock propagation은 qualitative하게 타당하다. 그러나 triangular FD와 authored capacity를 사용하므로 wave speed와 clearance time의 경험적 정확도는 검증되지 않았다.

### 남은 결함

Node의 lexicographic tie-break는 total flow를 최대화하더라도 한 incoming을 굶길 수 있다.

## Round 2, weighted merge fairness

### 관찰

Preloaded saturated 2:1 merge에서 첫 10 ticks를 비교했다.

- lexicographic: A=30, B=0
- weighted virtual finish: A=20, B=10
- node holding events=0

Bar chart에서 lexicographic 정책은 B를 완전히 굶긴다. Weighted solver는 정확한 2:1 ratio를 보인다.

### 적대 판정

Priority ratio는 구현됐다. 다만 이 weight는 관측에서 추론한 것이 아니라 authored control parameter다. Signal stage, lane count, critical gap을 대체하는 보편적 merge law로 해석하면 안 된다.

### 수정

Maximum throughput을 먼저 exact max-flow로 고정하고, 남은 maximum flow를 훼손하지 않는 candidate 중 weighted virtual finish가 작은 token을 선택했다.

## Round 3, movement waiting age

### 관찰

Shared approach에서 major movement weight=4, minor=1로 두었다.

- waiting age 없음: major=15, minor=0
- waiting age 있음: major=8, minor=7
- final maximum wait=1 tick

### 적대 판정

Fixed priority는 minority movement의 지속 demand를 굶길 수 있다. Age priority는 starvation을 제거한다. 그러나 8:7은 long-run movement weight 4:1을 구현한다는 뜻이 아니다. 이 실험에서는 starvation 방지가 2차 목표이고 source sending은 1 token/tick이다.

### 수정

Demand가 있으나 service가 0인 movement의 age를 증가시키고, maximum-throughput-safe candidate 사이에서 age가 큰 movement를 우선했다.

## 최종 판정

### 통과

- mass balance error=0
- node holding events=0
- deterministic replay
- finite storage 위반 없음
- source/movement/sink identity 중복 없음
- incident와 bottleneck upstream에 queue가 형성되고 해소됨
- 2:1 merge priority와 minority turn anti-starvation을 별도 stress test에서 재현

### 미해결

- perfect network-wide FIFO
- lane-changing과 finite turn-pocket
- capacity drop 및 hysteresis
- unsignalized opposing-flow conflict delay
- calibrated signal plans
- 실도시 detector/trajectory 기반 parameter posterior
- production-scale node solver 성능

최종 판정은 `RESEARCH-READY`, `NOT DEFAULT-READY`다.
