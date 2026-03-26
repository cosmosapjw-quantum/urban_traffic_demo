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
기본 baseline은 point-queue / LTM 계열로 시작한다.

링크 업데이트:
x_e(t+dt) = x_e(t) + inflow_e(t) - outflow_e(t)

노드 제약:
0 <= y_(e->f)(t) <= min(D_e(t), S_f(t), movement_capacity_(e->f)(t))

필수 조건:
- non-negativity
- capacity respect
- storage respect
- deterministic update order

## multirate
- fast tick: traffic
- medium tick: navigation / accessibility
- slow tick: land-use / policy / learning
