# Validation and Benchmark Plan

Runtime acceleration planning is additionally governed by
`docs/harness/RUNTIME_ACCELERATION_DECISION_GUARDRAILS.md`. Benchmark evidence
must pass its self-ask and step-back gates before another instrumentation or
backend slice is opened.

## runtime-closure status and prerequisite

The NumPy baseline now passes the first five functional closure checks below on
the deterministic seed-41 small workload. Acceleration and 100k integration
claims remain blocked until the remaining replay, scale, physical-semantics,
and LUTI boundaries are closed or explicitly removed from the product claim:

- compiled topology exposes typed legal turn movements;
- active route tails produce deterministic per-turn demand before flow;
- at least one generated multi-hop trip moves and completes;
- source insertion, link queues/stocks, sinks, failures, and completions satisfy
  one link-level vehicle-conservation equation;
- a canonical digest covers all dynamic state and replays exactly;
- medium/slow accessibility and land-use cadences are either ported into
  `SimulationState` or removed from the integrated-runtime claim.

Current bounded positive probe:

```bash
.venv/bin/python -m metroflow.benchmarks.runtime_self_drive_probe \
  --scenario-seed 41 --steps 20 --expect-closed
```

Expected internal evidence: 16 generated trips, 15 completions, one explicit
no-route failure, zero remaining active agents/queue mass, no invariant failure,
zero per-link agent/queue delta, and equal final-state fingerprints from two
fresh 20-tick replay runs. This is a fail-closed functional regression
probe, not a 100k, empirical, or physical traffic validation benchmark. The
historical `--steps 3 --expect-stalled` negative control applies only to audit
delivery commit `e428de848184`.

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
- traffic model provenance, physical-progress count, exit-ready count, source
  spillback waits, and downstream storage-blocked turn count

`run_measured_runtime_spine_benchmark`는 `flow_backend`, `routing_backend`, `agent_backend`, `traffic_model`,
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

## generated land-use admission

- `zone_poi_coupling_mode="legacy"`가 기본값이며 explicit legacy와 결과가 같아야 한다.
- `morphology_gated`는 저장된 boolean을 그대로 신뢰하지 않는다. 현재 topology에서 morphology
  metrics를 다시 계산하고 gate v2 전체 payload, 실제 road geometry fingerprint, finite/in-bounds
  district/subcenter anchor digest를 모두 대조한다.
- gate/geometry/style/anchor가 없거나 stale이면 morphology placement를 사용하지 않고 exact legacy
  placement로 fallback하며 reason metadata를 남긴다.
- admitted mode도 zone/POI ID, count, type mix, capacity aggregate를 바꾸지 않는다.
- runtime replay static-input fingerprint는 실제 zone/POI 값, normalized node-zone maps, road geometry,
  coupling gate/anchor provenance를 포함한다. 같은 의미의 dict/immutable mapping 및 key ordering은
  같은 hash를 만들어야 하고 POI-only mutation은 다른 hash를 만들어야 한다.
- static zoning/POI visual output은 diagnostic smoke artifact이며 접근성·수요 validation 주장이 아니다.
- morphology land-use accessibility audit은 최소 3개 unique seed에서 legacy/morphology 각각의 POI
  access validity, zone-node coverage, directed representative-zone reachability, aggregate contract,
  placement separation을 함께 기록한다.
- audit output directory는 비어 있어야 하고 registered style id만 허용한다. manifest는 생성된 HTML,
  JSON, Markdown 파일을 열거하며 모든 산출물은 `pr46_authorized=false`를 유지한다.
- static map은 기록된 zoning fingerprint를 실제 zones/POIs/node-zone map으로 재계산해 대조한다.
  fingerprint가 없으면 coupling provenance를 표시하지 않고, mismatch는 fail-closed 오류다.

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
- spatial-queue parity는 physical link travel time, exit-ready demand gating,
  one-space merge ordering, finite source/downstream storage, queue/storage
  invariant, pause, replay, benchmark/UI provenance를 고정한다. 이 테스트는
  empirical traffic 또는 shockwave validation이 아니다.
- Rust CPU active-agent parity test는 slot order budget consumption, skipped same-tick slots,
  no-route release, final-link sink wait/completion, shared-link budget ordering, wrapper copy-boundary
  action plan을 Python baseline과 동일 입력으로 비교한다
- active-agent reroute parity는 incident/refresh-cadence trigger, cooldown-preserve behavior,
  current-link 이후 route tail replacement, reroute/cooldown telemetry counters를 고정한다
- JAX 첫 호출 compile time과 steady-state runtime을 분리 기록
- cost-to-go surrogate data는 baseline dynamic-potential labels만 사용한다.
  Model matrix에서 ID/index를 제외하고 feature/static-network/dynamic-state
  fingerprint를 분리하며, static-network/destination group을 train과
  validation에 중복 배치하지 않는다.
- row-local cost-to-go v1 split은 same-network unseen-destination 진단만
  지지한다. Cross-city validation claim은 별도 map holdout과 feature-variance
  audit 전에는 금지한다.
- PR49 canonical audit의 near-duplicate target conflict gate는 row-local MLP를
  거부한다. 이 threshold를 완화하지 않으며, graph-aware 실험은 directed
  adjacency, edge-state, padding mask, map-holdout fingerprint가 먼저 고정돼야 한다.
- PR50 graph tensor contract는 directed edge parity, baseline target/mask parity,
  static/dynamic/sample fingerprint response, read-only exact dtype, padded slice
  reconstruction, byte-budget rejection, static-network split disjointness를
  검증해야 한다. 이 gate는 PR51 실험만 열며 validation/runtime claim은 열지 않는다.
- PR51 graph-aware JAX bakeoff는 exact PR49 holdout, 3 model seeds, row-local
  parameter-matched control, train-only normalization, compile/steady timing,
  repeat prediction/MAE difference를 기록한다. Canonical result는 mean MAE ratio
  `1.0581`, seed pass `0/3`, repeat failure이므로 runtime/validation 승격을 금지한다.
- JAX dense-flow persistent chunk bakeoff는 process/device warmup을 별도 기록하고, per-shape
  first call은 warm-process trace/compile/execute estimate로만 부른다. first-result output copy는 steady
  result copy를 사용한 estimate임을 명시해야 한다.
- device chunk 내부 demand/capacity/topology/priority는 고정 입력이다. event/agent mutation,
  per-tick host synchronization, inter-invocation compile-cache reuse, replay parity를 측정하지 않았으므로
  chunk speedup만으로 runtime `flow_backend="jax"`를 추가할 수 없다.
- GPU chunk admission은 3개 unique seed 모두에서 warm first-call+copy 및 steady+copy speedup이 1보다
  크고, integer/bool output이 exact하며, finite float max drift가 `1e-3` 이하일 때만 허용한다.
  65,536-link canonical run은 drift 초과로 fail-closed 상태다.
- benchmark result는 요청 backend를 기록하고, explicit `rust_cpu`/`jax` 요청 실패는 실패로 남김
- runtime benchmark result는 route-candidate refresh, route-candidate potential/path-build/metadata,
  dynamic-potential recompute, routing compile estimate timing totals, flow/active-agent/reroute
  decision wall-time totals, active-agent allocation/candidate-selection/pool-write/pool-array-write/plugin-memory-write/movement wall-time totals,
  `runtime_stage_timings`, `gpu_candidate_stage_names`를 metrics/run summary와 동일한 key로 보존한다
- isolated routing-candidate benchmark result는 route-candidate refresh와 dynamic-potential recompute
  timing totals를 own stats에서 보존한다
- `auto` backend만 baseline fallback을 허용한다
- display GPU OOM 회피가 필요하면 `XLA_PYTHON_CLIENT_MEM_FRACTION` 값을 결과에 기록
- baseline보다 느리거나 값 drift가 있으면 baseline을 production default로 유지
- `rust_cpu`는 현재 NumPy-compatible 입력을 edge `Vec<f64>`, flow/routing `Vec<f32>`/`Vec<i32>`/`Vec<bool>`,
  active-agent `Vec<i32>`로 복사하므로 benchmark 결과에 copy boundary를 기록한다
- zero-copy NumPy FFI 또는 Rayon implementation PR은
  `docs/rust/ZERO_COPY_RAYON_ADMISSION.md`의 조건처럼 copy-boundary timing이 parent-stage
  decision을 바꿀 수 있음을 먼저 보여야 한다
- future `torch_cuda`/`custom_cuda` backend는 아직 config 값으로 받지 않는다. 후보 stage는 flow,
  route candidate refresh, reroute decision, active-agent update wall-time share를 기준으로 산정하고,
  단일 stage가 3개 이상의 deterministic seed에서 30%를 넘은 뒤에만 NumPy array ownership, dtype,
  copy 여부를 포함하는 별도 acceptance contract를 연다
- C++/libtorch/custom CUDA implementation PR은 `docs/cuda/CPP_CUDA_ADMISSION.md`의 조건처럼
  dense flow, route-score batch, OD/policy batch 중 하나의 narrow kernel만 대상으로 해야 하며,
  compile/build time, steady-state time, host-device copy cost를 분리해 기록해야 한다
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
- `run_runtime_benchmark_suite`는 public benchmark runner facade로 suite artifact, aggregate gate
  report, review markdown을 한 dict에 담아 반환한다. 이 facade는 장기 benchmark 실행 표면이며
  runtime core 또는 UI snapshot code에 의존성을 역류시키면 안 된다
- benchmark CLI의 `--runtime-suite` 모드는 같은 facade를 호출한다. seed 목록은 comma-separated
  integer list로 받고 빈 목록은 argparse 단계에서 실패해야 한다
- `--runtime-suite-report-path`는 review markdown artifact를 UTF-8 파일로 저장하며, 저장된 파일은
  GPU/C++ 구현 허가가 아니라 long-run 검토 입력으로만 취급한다
- `--runtime-suite-json-path`는 같은 suite result를 machine-readable JSON으로 저장한다. JSON은
  seed, per-seed backend metadata, runtime stage timings, aggregate GPU candidate gate report를
  보존해야 하며 markdown을 다시 파싱하는 용도로 쓰면 안 된다
- `--runtime-suite-html-path`는 같은 JSON payload를 embedded data attribute와 stage/per-seed tables로
  렌더링한다. 이 HTML은 review/diagnostic artifact이며 runtime core 또는 UI snapshot dependency를
  추가하면 안 된다
- `--runtime-suite-artifact-prefix`는 markdown, JSON, HTML, manifest를 함께 쓰는 bundle 표면이다.
  manifest는 artifact path, workload, seed list, step count, GPU review eligible stage와
  JAX/GPU, NN surrogate, Rust CPU 후보 stage 이름만 보존하고, volatile wall-clock 값을 검증 주장으로
  승격하면 안 된다
- `--runtime-suite-eager-trip-generation`은 초기 trip demand를 생성해 routing/active-agent stage timing을
  관측하기 위한 옵션이다. 이 옵션은 benchmark workload metadata로 취급하고 replay/validation claim으로
  과장하지 않는다. JSON payload와 bundle manifest는 `eager_trip_generation` 값을 보존해야 한다
- runtime acceleration candidate report는 GPU gate와 별도로 stage별 JAX/GPU 적합도, NN surrogate
  적합도, Rust CPU 적합도, custom CUDA 적합도, 다음 timing probe를 기록한다. coarse stage와 nested
  stage가 함께 측정되면 `timing_overlap_warning`을 남겨 mean share 합계를 exclusive wall-clock
  partition으로 오독하지 않게 해야 한다
- hardware-fit atlas는 `python -m metroflow.benchmarks.run --hardware-atlas
  --hardware-atlas-artifact-prefix artifacts/runtime_spine_review/hardware-fit-atlas`로 생성한다.
  이 artifact는 AST/text 기반으로 function/class symbol의 role tag, data surface, hotspot signal,
  Rust CPU/NumPy-SIMD/JAX-GPU/future torch/custom CUDA/NN surrogate/keep-Python 적합도,
  compact CCoT, decision card를 기록한다
- hardware-fit atlas는 JAX, torch, CUDA, `_metroflow_rust`를 import하지 않아야 한다. runtime suite
  JSON을 `--hardware-atlas-runtime-suite-json`으로 전달하면 stage timing을 symbol group에 연결하지만,
  이 연결은 다음 probe 선택 자료이지 validation claim이나 backend 구현 허가가 아니다
- nested stage는 coarse stage를 대체하지 않는다. route-candidate potential/path-build/metadata와
  active-agent allocation/candidate-selection/pool-write/movement는 병목 분해용 evidence이며,
  합산값을 runtime 전체 share로 재해석하면 안 된다
- manifest의 `*_candidate_stage_names`는 구조적으로 medium/high fit인 stage 목록이고,
  `*_review_ready_stage_names`는 그중 현재 suite의 `gpu_review_eligible`까지 통과한 stage만 담아야 한다
- acceleration-related `/review` must use
  `docs/harness/RUNTIME_ACCELERATION_DECISION_GUARDRAILS.md`,
  `docs/harness/PROJECT_STATE.md`,
  `docs/harness/DECISION_LOG.md`, and
  `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md` as controlling context
