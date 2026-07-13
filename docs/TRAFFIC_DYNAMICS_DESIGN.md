# Traffic Dynamics Design

## 상태변수
- edge queue q_e(t) >= 0
- edge stock x_e(t) >= 0
- movement queue q_m(t) >= 0
- commodity mu = (destination d, candidate-path k, behavior class sigma)

## generalized cost
c_e(t) =
  free-flow time
  + queue delay
  + density penalty
  + event delay
  + turn / signal penalty

## bulk flow
기본 baseline은 `point_queue_v1`이며 기존 replay/regression authority를 유지한다.
명시적 `spatial_queue_v1`은 같은 NumPy turn-token core 위에 물리 link residency와
finite storage를 추가한다. `progress_01`은 이 모드에서만
`min(1, progress + free_flow_speed_mps * tick_seconds / length_m)`로 갱신된다.
저장량 단위는 차량이며 `floor(length_m * lanes / jam_spacing_m)`로 계산한다.
downstream/source 저장량이 없으면 agent는 결정론적으로 대기한다.

링크 업데이트:
x_e(t+dt) = x_e(t) + inflow_e(t) - outflow_e(t)

노드 제약:
0 <= y_(e->f)(t) <= min(D_e(t), S_f(t), movement_capacity_(e->f)(t))

필수 조건:
- non-negativity
- capacity respect
- storage respect
- deterministic update order

`spatial_queue_v1`은 coarse link model이다. lane changing, car following,
backward shockwave calibration, empirical fundamental diagram은 포함하지 않는다.

## multirate
- fast tick: traffic
- medium tick: navigation / accessibility
- slow tick: land-use / policy / learning
