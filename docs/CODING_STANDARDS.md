# Coding Standards

## units
- time conversion 명시
- length = meter
- speed = m/s 내부 고정
- generalized cost는 시간 [s]로 통일

## state
- mutable global state 금지
- WorldState를 통해서만 상태 이동
- version counter 없는 cache 금지
- `SimulationState` runtime step은 immutable replacement만 사용하며 flow/event/routing/agent 상태를
  `with_dynamic_updates`로 교체한다
- activated trip allocation이 flow queue를 바꿀 때는 `LinkState`를 새 객체로 교체하고,
  source link queue 및 travel-time cost를 같은 tick에서 함께 갱신한다
- active-agent link movement는 `flow_link_state.outflow_vehicles` 예산보다 많은 discrete agent를
  전진시키면 안 된다. 같은 tick에 새로 배정된 slot은 이동하지 않는다
- `agent_backend="rust_cpu"`는 active-agent pool/plugin memory를 직접 mutate하면 안 된다.
  Python wrapper가 slot/path/budget arrays를 복사해 Rust action plan을 받고,
  `ActiveAgentPool.from_internal_arrays(...)`를 통해 immutable replacement를 적용한다
- active-agent final-link completion은 final link의 effective capacity에서 계산한 sink discharge budget보다
  많은 discrete agent를 완료시키면 안 된다. zero capacity 또는 active closure에서는 final link에 대기하고
  `active_agent_sink_wait_this_tick` 및 `active_agent_sink_wait_total` counter를 증가시킨다
- active-agent reroute는 incident 또는 refresh cadence에서만 평가한다. cooldown이 남은 slot은
  route tail을 바꾸지 않고 cooldown만 감소시킨다
- route candidate cache key/fingerprint는 geometry id, link count, flow generation, incident generation,
  destination, refresh policy를 포함해야 한다
- `route_max_candidates > 1`은 Python baseline ranked K candidate generator를 authority로 사용한다.
  optional Rust backend는 같은 candidate order와 metadata를 재현해야 한다. turn restriction,
  blocked-link mask, max-hop limit을 보존하고 deterministic cost/id tie-break를 유지해야 한다
- `route_path_size_gamma` 기본값은 0.0이어야 하며, 0보다 큰 값만 path-size logit 보정을 활성화한다.
  replay boundary와 measured runtime benchmark는 이 값을 보존해야 한다

## JAX
- 기본 runtime contract는 NumPy/stdlib host state를 사용한다
- core loop는 pure function
- host PRNG는 deterministic uint32 key contract를 사용한다
- scan/vmap/segment ops 우선
- JAX/CUDA 경로는 optional extra 설치 후 명시적 backend 선택일 때만 사용
- `jax` backend는 fail-closed, `auto` backend만 Rust/JAX 실패 후 baseline fallback 허용
- baseline fallback 경로는 항상 유지
- 단일 RTX 3080 Ti 12GB 기준: distributed multi-GPU 금지
- accelerator kernel cache는 shape/dtype/backend별 런타임 컴파일 cache로 취급
- WorldState/cache token은 accelerator compile cache에 의존하면 안 됨
- JAX 메모리 preallocation은 실행 환경 변수로만 제어
- `RoadNetworkCSR`, `LinkState`, `NodeState`, `ActiveAgentPool` 저장 배열은 NumPy `ndarray`를 authoritative 형식으로 사용한다

## backend boundary
- runtime acceleration changes must answer the self-ask and step-back gates in
  `docs/harness/RUNTIME_ACCELERATION_DECISION_GUARDRAILS.md` before adding another timing
  metric, backend, or NN/GPU experiment surface
- backend 입력/출력은 contiguous NumPy-compatible arrays와 explicit dtype을 사용한다
- backend는 hidden mutation 없이 새 배열/상태를 반환한다
- Rust CPU backend의 현재 slice는 `traffic.meso` edge batch evolution, `flow.engine` baseline flow array core,
  `routing.dynamic_potential` node cost-to-go, next-link action scoring,
  greedy single-candidate route path core, ranked-K route candidate enumeration,
  candidate cost/path-size metadata, candidate selection, reroute decision core,
  active-agent movement action planning을 담당한다
- explicit `rust_cpu` backend는 fail-closed이고, `auto`에서만 baseline fallback을 허용한다
- 현재 Rust CPU wrapper는 edge 입력을 `Vec<f64>`, flow/routing 입력을 `Vec<f32>`/`Vec<i32>`/`Vec<bool>`,
  active-agent slot/action 입력을 `Vec<i32>`로 복사한다
- Rust zero-copy NumPy FFI 또는 Rayon parallelism은
  `docs/rust/ZERO_COPY_RAYON_ADMISSION.md`의 admission rule을 통과한 별도 PR에서만
  구현한다
- C++/libtorch/custom CUDA build surface 또는 `torch_cuda`/`custom_cuda` runtime backend는
  `docs/cuda/CPP_CUDA_ADMISSION.md`의 admission rule을 통과한 별도 PR에서만 구현한다
- Rust extension crate의 Python distribution name은 root package `metroflow`와 달라야 한다.
  `maturin develop --manifest-path crates/metroflow-rust/Cargo.toml`이 root editable install을
  shadow하면 CLI/import smoke를 실패로 간주한다
- `edge_backend="auto"`는 `rust_cpu` → `jax` → `baseline`, `flow_backend="auto"`는 `rust_cpu` → `baseline` 순서만 허용한다
- `routing_backend="auto"`는 `rust_cpu` → `baseline` 순서만 허용한다
- `agent_backend="auto"`는 `rust_cpu` → `baseline` 순서만 허용한다
- routing candidate `auto`는 Rust dynamic-potential cost-to-go, next-link action scoring,
  greedy path, ranked-K route candidate, candidate metadata, candidate selection 함수가 모두
  사용 가능할 때만 Rust를 선택한다
- reroute decision `auto`는 Rust reroute decision 함수가 사용 가능할 때만 Rust를 선택한다
- Rust routing backend는 ranked K candidate set을 가속할 수 있지만, Python baseline candidate order와
  metadata가 authoritative contract다. result/report에는 `candidate_enumeration_backend`와
  `candidate_metadata_backend`를 남겨야 한다
- PyTorch/libtorch/custom CUDA는 profiling 이후 좁은 hot kernel에만 추가한다
- `torch_cuda`/`custom_cuda`는 현재 runtime config 값이 아니며, 단일 stage가 최소 3개 deterministic
  seed에서 wall time의 30%를 넘고 Rust/baseline parity가 green일 때만 별도 slice로 검토한다
- runtime benchmark는 flow update, route candidate refresh, route candidate potential/path-build/metadata,
  dynamic-potential recompute, reroute decision, active-agent update, active-agent
  allocation/candidate-selection/pool-write/movement stage timing을 보존해야 한다. GPU 후보 표시는
  `gpu_candidate_stage_names` metadata로만 남기고 runtime backend 값으로 승격하지 않는다
- runtime acceleration candidate report는 GPU gate와 분리한다. JAX/GPU fit, NN surrogate fit,
  Rust CPU fit, custom CUDA fit은 planning metadata이며 backend config 값이나 validation claim이 아니다.
- GPU/C++ 착수 후보는 `summarize_runtime_gpu_candidate_gate`로 3개 이상의 unique deterministic
  seed 결과를 집계해 모든 run에서 threshold를 넘는 stage만 `gpu_review_eligible`로 표시한다
- `run_measured_runtime_spine_benchmark_suite`는 seed 중복을 fail-closed로 거부하고,
  suite result에 per-seed results와 GPU candidate gate markdown을 함께 보존해야 한다

## process and assurance governance
- process, gate, and assurance inflation guardrails are defined in `docs/harness/PROCESS_INFLATION_GUARDRAILS.md`
- 개발 작업은 단일 helper가 아닌 behavior cluster 단위(e.g., S11, S12–13, S14–15, S16–17)로 묶어 진행한다
- 각 behavior cluster는 공개 behavior RED 및 GREEN을 유지하되, 내부 private helper 구현 중 micro-commit 및 전체 test suite 반복 실행(gate inflation)을 금지한다. 내부 루프는 fast targeted unit test만 사용한다
- 구현은 단일 직렬 구현자(single serial implementer)가 전담하며, 동시 multi-agent write 또는 병렬 subagent 수정 루프를 금지한다
- subagent review는 읽기 전용(read-only)으로 candidate가 freeze된 이후에만 수행하며 최대 3회로 제한한다
- 후보 freeze 상태에서만 executable test-partition gate, provenance 검증, Ruff,
  same-head CI 전체 suite를 실행한다
- 선행 PR(e.g., PR88)이 merge되거나 구조적으로 종료되기 전에는 후속 PR(e.g., PR89)에 대한 선행 검토 및 보증 문서 작성을 금지한다
- 보증 및 제안 문서의 줄 수는 대상 source+test 코드의 줄 수를 초과하지 않도록 엄격히 제한한다 (assurance inflation 방지)
- 메타인지 평가는 단 1회 수행하여 `*_METHOD_PILOT=PASS|SPLIT` 형태의 관측 가능한 결과로 환원하고, 평가 자체를 재평가하는 행위는 `META_RECURSION_BLOCKED`로 차단한다

## tests
- 새 상태변수/계약 추가 시 테스트 동시 추가
- numerical method 변경 시 benchmark 필수

## external implementation imports
- 외부 `metro/` 구현은 reference source로만 사용한다.
- 이식된 root 코드는 외부 `metro/` 폴더가 없어도 import/test가 가능해야 한다.
- ROCm/container/JAX-first 전제를 루트 기본값으로 승격하지 않는다.
- 이식은 루트 `GraphState`/`WorldState` 계약을 보존하는 작은 vertical slice로 제한한다.
- dynamic-potential routing의 기본 구현은 pure baseline이어야 하며, accelerator 경로는 별도 명시 backend만 허용한다.
- city generator 개선은 ring/radial/bridge 같은 구조적 contract와 gate를 먼저 옮기고, 대형 generic frameworkization은 금지한다.
- `sim.orchestrator.step_world`는 compatibility surface로 유지하고, 장기 runtime 회귀는
  `sim.step.simulation_step`의 `SimulationState` spine을 기준으로 추가한다.

## learning
- baseline fallback 필수
- reward/cost clipping rule 명시
- update cadence 문서화
- cost-to-go supervised labels는 baseline dynamic-potential만 authority로
  사용한다. ID/index는 provenance이며 model feature가 아니다.
- surrogate split key는 label/fingerprint가 아니라 static network와
  destination input provenance로 만들고 동일 destination의 여러 scenario,
  tick, dynamic state를 한 partition에 유지한다.
- row-local feature matrix는 cross-city graph representation이 아니다. 여러
  map holdout evidence 없이 일반화 또는 runtime routing authority를 주장하지 않는다.
- cost-to-go graph tensor는 local directed indices만 model input으로 사용하고,
  persistent IDs는 fingerprint provenance에만 남긴다. Node/edge/target padding은
  명시 mask와 byte budget을 가져야 하며 baseline Dijkstra target을 재계산하거나
  route legality를 대체하지 않는다.
- graph sample은 verified network/link-state/baseline builder에서만 생성하고,
  array는 write flag를 다시 켤 수 없는 immutable buffer를 사용한다. Map holdout
  fingerprint는 validation set과 독립 문자열로 받지 않고 전체 split payload에서 재계산한다.
- optional JAX NN bakeoff는 Optax optimizer, train-only normalization, fixed
  map holdout, parameter-count fairness, first/steady timing, repeat determinism을
  기록한다. Accuracy gate가 독립적으로 실패하면 determinism 세부 튜닝을 반복하지 않는다.
