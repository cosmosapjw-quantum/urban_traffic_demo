# Validation and Benchmark Plan

## invariant tests
- queue >= 0
- stock >= 0
- capacity respect
- deterministic replay
- cache version consistency
- no same-tick feedback closure

## toy gold suite
1. monocentric city
2. bridge bottleneck
3. merge bottleneck
4. bypass addition
5. incident shock
6. lagged land-use

## integration benchmark
city100k-like synthetic benchmark:
- zone 64
- active trips peak 10k~30k
- ring/radial + bridge + industrial corridor

측정:
- step latency
- memory footprint
- mean generalized cost
- top bottleneck persistence
- cache refresh cost
- viewer overhead
- integrated `SimulationState` runtime spine latency
- route candidate refresh/reuse count
- dynamic potential recompute/cache-hit count
- active-agent allocation/move/complete count
- source-link queue insertion count/queue delta
- outflow-budgeted active-agent movement count

`run_measured_runtime_spine_benchmark`는 `flow_backend`, `routing_backend`,
routing copy-boundary note, route candidate counters, dynamic-potential counters, initial/final tick을 기록한다.
`run_measured_routing_candidate_benchmark`는 OD 단위 dynamic-potential + greedy candidate path를 분리 측정하고,
routing backend, final candidate path, path length, recompute/cache-hit count, copy-boundary note를 기록한다.
runtime replay는 `make_runtime_replay_boundary`와 `replay_simulation_sequence`로
backend config 및 route-cache fingerprint를 고정한다. route-cache fingerprint는 candidate path뿐 아니라
effective/requested routing backend와 fallback metadata도 포함한다.

## backend benchmark
- baseline backend과 optional accelerator backend를 같은 input signature로 비교
- 기본 benchmark는 NumPy baseline만 요구한다
- optional Rust CPU benchmark는 `_metroflow_rust` 확장 빌드 후 `traffic.meso` edge batch,
  `flow.engine` flow core, `routing.dynamic_potential` node cost-to-go 및 greedy single-candidate route path core를 대상으로 한다
- optional JAX benchmark는 `.[jax]` extra 설치 후 RTX 3080 Ti 12GB 단일 GPU만 대상으로 한다
- distributed multi-GPU 측정 금지
- Rust CPU parity test는 baseline `update_edge_state` 수식과 queue/stock/capacity 불변식을 동일 입력으로 비교한다
- Rust CPU flow parity test는 baseline `compute_baseline_flow_arrays_core`와 turn priority, forbidden turn, zero-turn, zero-link, signal timer 결과를 동일 입력으로 비교한다
- Rust CPU routing parity test는 baseline reverse-Dijkstra node cost-to-go와 blocked link, unreachable node,
  zero-link, forbidden-turn greedy path 결과를 동일 입력으로 비교한다
- measured routing candidate benchmark는 baseline/Rust routing backend 요청이 dynamic-potential과 greedy path
  양쪽에 전달되는지, 그리고 result metadata가 final path 및 recompute/cache counters를 보존하는지 확인한다
- routing `auto` fallback test는 Rust routing extension이 cost-to-go와 greedy path를 모두 제공하지 않으면
  Rust wrapper를 호출하지 않고 baseline으로 내려가는지 확인한다
- runtime spine parity는 baseline config에서 event effect, flow update, route candidate cache, active-agent movement,
  replay fingerprint가 deterministic하게 재현되는지 확인한다
- active-agent movement parity는 newly allocated slot의 same-tick movement 금지, source link queue insertion,
  `outflow_vehicles` 예산 이하 link advance, no-outflow 대기를 고정한다
- JAX 첫 호출 compile time과 steady-state runtime을 분리 기록
- benchmark result는 요청 backend를 기록하고, explicit `rust_cpu`/`jax` 요청 실패는 실패로 남김
- `auto` backend만 baseline fallback을 허용한다
- display GPU OOM 회피가 필요하면 `XLA_PYTHON_CLIENT_MEM_FRACTION` 값을 결과에 기록
- baseline보다 느리거나 값 drift가 있으면 baseline을 production default로 유지
- `rust_cpu`는 현재 NumPy-compatible 입력을 edge `Vec<f64>`, flow/routing `Vec<f32>`/`Vec<i32>`/`Vec<bool>`로 복사하므로 benchmark 결과에 copy boundary를 기록한다
- future `torch_cuda` backend는 NumPy array ownership, dtype, copy 여부를 결과에 기록한다
