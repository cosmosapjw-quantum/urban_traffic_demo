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

`run_measured_runtime_spine_benchmark`는 `flow_backend`, `routing_backend`, `agent_backend`,
routing/agent copy-boundary note, route candidate counters, dynamic-potential counters,
active-agent update wall time, runtime reroute/persistence counters, initial/final tick을 기록한다.
`run_measured_routing_candidate_benchmark`는 OD 단위 dynamic-potential + route candidate path를 분리 측정하고,
routing backend, final candidate path, ranked-K candidate paths/costs/path-size metadata, path length,
recompute/cache-hit count, copy-boundary note를 기록한다.
`route_max_candidates > 1` baseline test는 ranked K candidate path 순서, turn restriction, blocked-link
회피, deterministic tie-break, `max_candidates_returned`, candidate path cost, path-size factor metadata를
고정한다.
path-size correction test는 `route_path_size_gamma=0.0` 기본 비용 선택 보존, gamma 활성화 시
`-cost + gamma * log(path_size)` utility 선택, replay config fingerprint, measured runtime benchmark metadata를
고정한다. run summary와 benchmark report도 route path-size gamma를 reviewer-facing metadata로 보존한다.
runtime replay는 `make_runtime_replay_boundary`와 `replay_simulation_sequence`로
backend config 및 route-cache fingerprint를 고정하고, replay result는 runtime reroute/persistence totals를
보존한다. route-cache fingerprint는 candidate path뿐 아니라
effective/requested routing backend와 fallback metadata도 포함한다.

## backend benchmark
- baseline backend과 optional accelerator backend를 같은 input signature로 비교
- 기본 benchmark는 NumPy baseline만 요구한다
- optional Rust CPU benchmark는 `_metroflow_rust` 확장 빌드 후 `traffic.meso` edge batch,
  `flow.engine` flow core, `routing.dynamic_potential` node cost-to-go, next-link action scoring,
  greedy single-candidate route path core, ranked-K route candidate enumeration,
  candidate cost/path-size metadata, candidate selection, reroute decision core,
  active-agent movement action planning을 대상으로 한다
- optional JAX benchmark는 `.[jax]` extra 설치 후 RTX 3080 Ti 12GB 단일 GPU만 대상으로 한다
- distributed multi-GPU 측정 금지
- Rust CPU parity test는 baseline `update_edge_state` 수식과 queue/stock/capacity 불변식을 동일 입력으로 비교한다
- Rust CPU flow parity test는 baseline `compute_baseline_flow_arrays_core`와 turn priority, forbidden turn, zero-turn, zero-link, signal timer 결과를 동일 입력으로 비교한다
- Rust CPU routing parity test는 baseline reverse-Dijkstra node cost-to-go, next-link action costs,
  blocked link, unreachable node, zero-link, forbidden-turn greedy path, ranked-K candidate paths,
  candidate cost/path-size metadata, path-size utility selection, reroute decision score/boolean을
  동일 입력으로 비교한다
- measured routing candidate benchmark는 baseline/Rust routing backend 요청이 dynamic-potential,
  greedy path, ranked-K enumeration, candidate metadata, candidate selection, reroute decision에 전달되는지,
  그리고 result metadata가 final path, ranked-K candidate metadata, candidate enumeration/metadata backend,
  requested/actual backend/fallback, recompute/cache counters를 보존하는지 확인한다
- ranked K route candidate generation은 Python baseline authority로 검증한다. Rust backend 성능 주장은
  copy-boundary와 `candidate_enumeration_backend` metadata를 함께 기록한 경우에만 허용한다
- route-candidate `auto` fallback test는 Rust routing extension이 cost-to-go, next-link scoring,
  greedy path, ranked-K candidate enumeration, candidate metadata, candidate selection을 모두
  제공하지 않으면 Rust wrapper를 호출하지 않고 baseline으로 내려가는지 확인한다
- reroute decision `auto` fallback test는 Rust reroute decision 함수가 없거나 실패하면 baseline으로
  내려가는지 확인한다
- runtime spine parity는 baseline config에서 event effect, flow update, route candidate cache, active-agent movement,
  replay fingerprint가 deterministic하게 재현되는지 확인한다
- active-agent movement parity는 newly allocated slot의 same-tick movement 금지, source link queue insertion,
  `outflow_vehicles` 예산 이하 link advance, no-outflow 대기, final-link sink discharge budget 이하
  completion, zero-capacity final-link 대기와 `active_agent_sink_wait_this_tick`/`active_agent_sink_wait_total`
  telemetry를 고정한다
- Rust CPU active-agent parity test는 slot order budget consumption, skipped same-tick slots,
  no-route release, final-link sink wait/completion, shared-link budget ordering, wrapper copy-boundary
  action plan을 Python baseline과 동일 입력으로 비교한다
- active-agent reroute parity는 incident/refresh-cadence trigger, cooldown-preserve behavior,
  current-link 이후 route tail replacement, reroute/cooldown telemetry counters를 고정한다
- JAX 첫 호출 compile time과 steady-state runtime을 분리 기록
- benchmark result는 요청 backend를 기록하고, explicit `rust_cpu`/`jax` 요청 실패는 실패로 남김
- runtime benchmark result는 route-candidate refresh, dynamic-potential recompute, routing compile estimate
  timing totals, flow/active-agent/reroute decision wall-time totals, `runtime_stage_timings`,
  `gpu_candidate_stage_names`를 metrics/run summary와 동일한 key로 보존한다
- isolated routing-candidate benchmark result는 route-candidate refresh와 dynamic-potential recompute
  timing totals를 own stats에서 보존한다
- `auto` backend만 baseline fallback을 허용한다
- display GPU OOM 회피가 필요하면 `XLA_PYTHON_CLIENT_MEM_FRACTION` 값을 결과에 기록
- baseline보다 느리거나 값 drift가 있으면 baseline을 production default로 유지
- `rust_cpu`는 현재 NumPy-compatible 입력을 edge `Vec<f64>`, flow/routing `Vec<f32>`/`Vec<i32>`/`Vec<bool>`,
  active-agent `Vec<i32>`로 복사하므로 benchmark 결과에 copy boundary를 기록한다
- future `torch_cuda`/`custom_cuda` backend는 아직 config 값으로 받지 않는다. 후보 stage는 flow,
  route candidate refresh, reroute decision, active-agent update wall-time share를 기준으로 산정하고,
  단일 stage가 3개 이상의 deterministic seed에서 30%를 넘은 뒤에만 NumPy array ownership, dtype,
  copy 여부를 포함하는 별도 acceptance contract를 연다
- `format_runtime_stage_timing_markdown`은 measured runtime benchmark result의 stage timing과
  GPU 후보 gate를 reviewer-facing report section으로 렌더링한다. 이 section은 구현 허가가 아니라
  다음 backend slice를 정하기 위한 measurement artifact다
- `summarize_runtime_gpu_candidate_gate`는 같은 workload의 measured runtime benchmark result를
  3개 이상의 unique deterministic seed 단위로 집계한다. `format_runtime_gpu_candidate_gate_markdown`은
  모든 run에서 threshold를 넘은 stage만 GPU/C++ review 후보로 표시한다
- `run_measured_runtime_spine_benchmark_suite`는 seed별 runtime benchmark 실행, per-seed result,
  aggregate GPU candidate gate report, reviewer-facing gate markdown을 한 artifact로 묶는다
- `format_runtime_benchmark_suite_markdown`은 suite artifact를 review markdown으로 렌더링하며,
  이 markdown은 GPU/C++ 구현 허가가 아니라 후보 stage 검토 자료로만 해석한다
