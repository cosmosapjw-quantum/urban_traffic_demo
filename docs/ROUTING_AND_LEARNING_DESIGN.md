# Routing and Learning Design

## candidate path set
각 OD pair에 대해 K개 경로 유지.
권장 K = 4~8

## time-dependent path cost
각 path의 비용은 링크 비용을 해당 도착 예정 시각에서 평가한 합으로 둔다.

## path-size correction
중복 경로 과대평가 방지를 위해 path-size factor 사용.

## path choice
path probability ~ exp(
  - lambda_sigma * expected_cost
  + gamma_sigma * log(path_size)
)

## active-matter closure
movement cost는 다음을 포함:
- expected downstream cost
- downstream density
- movement queue
- node pressure
- alignment EMA
- urgency
- preference bias
- noise

split ratio는 softmax 형태로 계산.

## conditional reroute
reroute iff:
- hard event on current route
or
- ETA degradation beyond threshold
and
- refractory window satisfied

## learning 순서
1. EMA perceived cost
2. OD-path bandit
3. archetype adaptation
4. optional GNN/LSTM plugin
