# Metroflow Urban Traffic Research Simulator

Metroflow는 결정론적 합성 도시, mesoscopic link/node flow, 동적 경로 탐색,
active agents, replay, 정적 지도 진단, 그리고 optional Rust/JAX 실험 표면을
결합하는 연구용 프로토타입이다. Python 3.12 + NumPy baseline이 권위 경로이며,
현재 구현은 실도시 검증이나 완결된 100k 통합 시뮬레이션으로 간주하면 안 된다.

외부 감사용 전체 발전사, 알고리즘 설명, 실패한 실험, claim boundary, 재현
절차는 `docs/audit/metroflow_external_audit_20260711/README.md`에서 시작한다.
그 문서의 정지 verdict는 `96e54ca` source baseline과 `e428de8` audit delivery의
역사적 negative control이다. 2026-07-12 후속 수정은 generated route-to-turn-demand
연결과 정확한 turn/sink token commit을 NumPy baseline에서 닫았으며, 범위와 남은
한계는 audit packet의 `10_RUNTIME_CLOSURE_REMEDIATION_20260712.md`에 기록한다.
이는 seed 41 소형 probe의 내부 검증일 뿐 100k scale, 실도시, 물리적 통행시간,
통합 LUTI, 또는 재배포 권한을 검증하지 않는다.

## 로컬 Python / GPU 기준
- Ubuntu 24.04 기본 Python 3.12를 기준으로 한다.
- repo-local `.venv`를 사용한다.
- 기본 설치는 NumPy baseline만 요구한다.
- NVIDIA RTX 3080 Ti 12GB는 optional `jax` extra의 JAX CUDA 13과 Optax를
  GPU benchmark/NN experiment에만 선택적으로 사용한다.
- core loop 기본값은 항상 baseline이며, JAX/CUDA 경로는 명시적으로 요청한 경우에만 사용한다.
- JAX/GPU와 NN surrogate는 route scoring, policy scoring, dense flow batch처럼 tensor-friendly stage의
  후보 실험 표면으로 유지한다. Python/NumPy baseline만 replay와 validation authority이며 Rust는
  parity-tested optional accelerator다.
- cost-to-go NN 실험은 baseline Dijkstra label, ID-free versioned model inputs,
  target-independent destination-group split을 먼저 요구한다. Row-local v1은
  cross-city 일반화 증거가 아니며 runtime route legality를 소유하지 않는다.
- multi-city audit는 row-local v1의 target conflict가 높아 MLP 경로를
  fail-closed로 거부했다. 이후 adjacency/edge-state tensor와 graph-aware JAX
  실험도 accuracy/determinism gate를 통과하지 못했으며 baseline Dijkstra
  authority는 유지된다.
- graph tensor 계약은 directed edge index, dynamic edge features/blocked mask,
  baseline node target mask, byte-bounded padding, static-network holdout을
  read-only NumPy로 고정한다. 이는 PR51 실험 substrate이며 runtime NN backend가 아니다.
- PR51 canonical graph-aware JAX bakeoff는 평균 held-out normalized-MAE ratio
  `1.0581`, seed gate `0/3`, repeat determinism 실패로 graph signal을 지지하지
  못했다. Threshold/architecture를 재조정하지 않고 현재 graph cost-to-go
  runtime NN 경로를 닫는다.
- `edge_backend="rust_cpu"`와 `edge_backend="jax"`는 실패 시 예외를 내고,
  `edge_backend="auto"`만 `rust_cpu` → `jax` → `baseline` 순서의 fallback을 허용한다.
- `SimulationConfig`의 runtime backend 기본값은 `edge_backend="baseline"`,
  `flow_backend="baseline"`, `routing_backend="baseline"`, `agent_backend="baseline"`이다. Rust routing backend는
  dynamic-potential node cost-to-go, next-link action scoring,
  deterministic greedy single-candidate path core, ranked-K candidate enumeration,
  candidate cost/path-size metadata, candidate selection, reroute decision core를 담당한다.
  Rust agent backend는 active-agent movement action plan만 반환하며 Python이 immutable
  `ActiveAgentPool` replacement를 적용한다.
- `route_max_candidates`는 기본값 1을 유지하지만 2 이상을 명시하면 Python baseline이
  dynamic-potential heuristic과 turn restriction을 사용해 결정론적 ranked K 후보 경로를 생성한다.
  `routing_backend="rust_cpu"` 또는 Rust 사용 가능한 `auto`에서는 같은 ranked-K enumeration을
  Rust CPU copy-boundary backend로 실행할 수 있으며, 후보 cost/path-size metadata도 같은
  Rust boundary에서 계산한다. runtime candidate selection도 Rust backend에서 선택적으로
  수행할 수 있으며, 이 결과는 baseline 결과와 parity를 유지해야 한다.
  candidate set metadata는 각 후보의 baseline path cost와 path-size factor를 함께 기록한다.
  `route_path_size_gamma` 기본값은 0.0이라 기존 비용 기반 선택을 보존하고, 0보다 크게 설정하면
  `-cost + gamma * log(path_size)` utility로 중복 경로를 보정한다.
- 디스플레이 GPU 메모리 여유가 필요하면 실행 전에 `XLA_PYTHON_CLIENT_MEM_FRACTION=.70`처럼 제한한다.

설치/확인:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

선택 JAX/CUDA 경로 확인:

```bash
.venv/bin/python -m pip install -e ".[dev,jax]"
XLA_PYTHON_CLIENT_MEM_FRACTION=.70 .venv/bin/python -c "import jax; print(jax.default_backend()); print(jax.devices())"
XLA_PYTHON_CLIENT_MEM_FRACTION=.70 .venv/bin/python -m pytest tests/test_meso_core.py::test_evolve_edges_fast_tick_jax_backend_matches_baseline_output -q
```

Dense-flow persistent-device GPU bakeoff:

```bash
XLA_PYTHON_CLIENT_MEM_FRACTION=.70 .venv/bin/python \
  -m metroflow.benchmarks.gpu_flow_bakeoff \
  --output-dir artifacts/gpu_dense_flow_bakeoff_20260711 \
  --link-counts 4096,16384,65536 --seeds 41,42,43 \
  --num-steps 512 --turns-per-link 3
```

이 bakeoff는 chunk 내부의 demand/capacity/topology를 고정한 GPU 실험이다. 현재 runtime의
per-tick host synchronization, event/agent mutation, replay를 검증하지 않으므로
`flow_backend="jax"`를 허가하지 않는다. canonical 결과에서 4,096/16,384 links는 실험 gate를
통과하지만 65,536 links는 `1e-3` drift gate를 넘어서 탈락한다.

선택 Rust CPU edge backend 빌드/확인:

```bash
.venv/bin/python -m maturin develop --manifest-path crates/metroflow-rust/Cargo.toml
.venv/bin/python -m pytest tests/test_meso_core.py::test_evolve_edges_fast_tick_rust_backend_matches_baseline_output -q
.venv/bin/python -m pytest tests/test_flow_engine_rust_backend.py::test_rust_flow_backend_matches_baseline_output -q
.venv/bin/python -m pytest tests/test_routing_rust_backend.py -q
.venv/bin/python -m pytest tests/test_active_agent_rust_backend.py -q
```

Rust extension crate는 crate-local `crates/metroflow-rust/pyproject.toml`에서 distribution name을
`metroflow-rust`로 둔다. root Python package `metroflow`를 덮어쓰면
`python -m metroflow...` CLI와 normal imports가 깨지므로, Rust build metadata는 root
`pyproject.toml`과 분리되어야 한다.

현재 Rust CPU backend는 `traffic.meso` edge batch evolution과 `flow.engine` baseline flow array
core, `routing.dynamic_potential` node cost-to-go, next-link action scoring,
greedy single-candidate route path core, ranked-K route candidate enumeration,
candidate cost/path-size metadata, candidate selection, reroute decision core, active-agent
movement action planning을 담당한다.
Python wrapper가 NumPy-compatible
입력을 edge는 `Vec<f64>`, flow는 `Vec<f32>` / `Vec<i32>` / `Vec<bool>`, routing은 CSR/비용 배열
`Vec<i32>` / `Vec<f32>` / `Vec<bool>`, active-agent slot/action 배열은 `Vec<i32>`로 복사한 뒤
Rust 확장 `_metroflow_rust`를 호출한다.
explicit `rust_cpu` backend는 실패 시 예외를 내고, `auto`만 baseline fallback을 허용한다.
ranked-K route candidate generation, metadata, selection과 reroute decision은 Python baseline을 authority로 유지하며,
Rust routing backend는 같은 contract를 optional accelerator로 제공한다.
`torch_cuda`와 `custom_cuda`는 아직 runtime config 값이 아니며, 단일 stage가 3개 이상의 deterministic
seed에서 wall time의 30%를 지속적으로 넘고 Rust/baseline parity가 green일 때 별도 slice로만 연다.

## 외부 `metro/` 구현 비교 반영
- `metro/` 폴더는 v1 목적에 가까운 donor 구현으로 취급한다.
- 현재 루트의 실행 기준은 Ubuntu 24.04 + Python 3.12 + RTX 3080 Ti CUDA 13이다.
- `metro/` 코드는 루트 runtime policy, deterministic replay, baseline fallback을 유지하는 단위로 흡수한다.
- root `src/metroflow/`와 `tests/`는 외부 `metro/` 폴더 없이 import/test가 가능해야 한다.
- 1차 반영 대상은 deterministic city backbone 생성, baseline dynamic-potential routing,
  RoadNetworkCSR, link/node flow state, active-agent pool, OD-UCB/policy blend, generator_v2 preview/gate contract이다.
- 추가 흡수된 foundation slice는 zoning/POI placement, deterministic citizen/trip demand,
  UI packet/stream-buffer contracts, simulation state/control/invariant contracts, UI snapshot/control/preset adapters이다.
- baseline `sim.init.build_initial_simulation_state`와 `sim.step.simulation_step`은 donor 의존성 없이
  city→demand→event effects→route/agent intent→turn/sink demand→flow→exact commit→invariant→UI snapshot의
  deterministic runtime spine substrate를 제공한다. Finalized generated topology의 exhaustive
  incoming×outgoing turn authority와 active route-tail turn/sink demand를 사용해 Python/NumPy
  baseline이 정확한 정수 movement token을 agent와 queue에 함께 commit한다.
- active-agent spine은 activated trip을 선택된 route candidate의 첫 링크에 배정하고, source link queue에
  차량 1대를 삽입한다. 새로 삽입된 agent는 같은 tick에 이동하지 않으며, 이후 link-to-link 이동은
  해당 route turn의 realized token만 소비한다. Source service와 downstream receiving capacity는
  fractional residual을 가진 하나의 deterministic integer authority로 조정된다.
- agent slot memory는 선택된 candidate id/index/count와 baseline path cost/path-size factor,
  path-size utility를 보존한다.
- runtime reroute는 incident 또는 route refresh cadence에서만 현재 링크 이후 tail 후보를 검토한다.
  cooldown이 남은 slot은 기존 route tail을 유지하고 cooldown만 감소한다.
- final-link completion은 sink discharge budget을 소비한다. link-to-link movement는
  internal turn과 같은 deficit scheduler에서 source-service token을 공정하게 경쟁하고,
  agent 제거와 final-link queue 감소를 같은 transaction으로 적용한다. final link의
  `dst_node_id`가 agent destination과 다르면 fail-closed한다. sink discharge budget 때문에 대기한 agent 수는
  `active_agent_sink_wait_this_tick` 및 `active_agent_sink_wait_total` telemetry/metrics에 기록된다.
- 현재 agent는 tick당 최대 한 route turn만 통과하며 `progress_01`은 물리적 sub-link 위치가 아니다.
  Flow는 finite storage와 spillback이 없는 point-queue 모델이다. 새 per-turn agent ABI는 Python
  authority이며 unsupported Rust agent/flow 선택은 fail-closed한다.
- reporting/experiment 표면으로 simulator-only learning experience, run summary comparison,
  Navigator UI stream packetization, benchmark smoke runner, scenario presets, adaptive policy plugin registry를 흡수했다.
- `SimulationState` runtime replay는 `make_runtime_replay_boundary`와 `replay_simulation_sequence`를 사용한다.
  replay boundary는 전체 config, 실제 static routing authority, initial dynamic-state fingerprint를
  기록하고 결과는 final dynamic-state fingerprint를 보존한다. Host timing 진단만 제외하며
  service/receiving/turn residual, sink flow, demand lifecycle, agent 배열/경로를 포함한다.
- integrated runtime benchmark는 `run_measured_runtime_spine_benchmark`를 사용하며 flow/routing backend와
  agent backend, route candidate/dynamic-potential cache counters, active-agent update wall time 및
  timing totals를 결과에 보존한다.
  `format_runtime_stage_timing_markdown`은 flow, route candidate refresh, dynamic potential,
  reroute decision, active-agent update stage의 wall-time share와 future GPU 후보 stage를
  reviewer-facing section으로 렌더링한다.
  nested timing으로 route candidate potential/path-build/metadata와 active-agent allocation/movement도
  함께 기록해 coarse stage 안의 병목을 분해한다. active-agent allocation은 candidate selection과
  pool write로 한 번 더 나눠 NN/JAX scorer 후보와 CPU/Rust state-write 후보를 분리한다.
  `summarize_runtime_gpu_candidate_gate`와 `format_runtime_gpu_candidate_gate_markdown`은
  3개 이상의 unique deterministic seed 결과를 집계해 모든 run에서 30% 이상인 stage만 GPU
  review 후보로 남긴다.
  `run_measured_runtime_spine_benchmark_suite`는 seed별 runtime benchmark를 실행한 뒤 같은
  gate report와 markdown을 함께 반환하는 Python orchestration surface다.
  `format_runtime_benchmark_suite_markdown`은 suite result를 reviewer-facing markdown으로 렌더링한다.
  `run_runtime_benchmark_suite`는 suite result, aggregate GPU candidate gate report, reviewer-facing
  markdown을 함께 반환하는 public benchmark runner facade다.
  CLI에서는 `python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-seeds 41,42,43
  --runtime-suite-steps 8`로 같은 review artifact를 stdout에 출력한다.
  `--runtime-suite-report-path artifacts/runtime-suite.md`를 함께 주면 markdown artifact를 파일로 남긴다.
  `--runtime-suite-json-path artifacts/runtime-suite.json`은 같은 suite result와 GPU candidate gate를
  machine-readable JSON으로 저장한다.
  `--runtime-suite-html-path artifacts/runtime-suite.html`은 stage gate와 per-seed backend를
  standalone review HTML로 렌더링한다.
  `--runtime-suite-artifact-prefix artifacts/runtime-suite`는 `.md`, `.json`, `.html`,
  `.manifest.json`을 한 번에 쓰는 long-run review bundle 표면이다.
  `--runtime-suite-eager-trip-generation`은 초기 trip demand를 생성해 routing/active-agent 단계가
  비어 있는 smoke 결과만 보지 않도록 한다.
  JSON/HTML/manifest에는 GPU gate와 별도로 acceleration candidate report를 포함한다. 이 report는
  stage별 JAX/GPU 적합도, NN surrogate 적합도, Rust CPU 적합도, 다음 timing probe와 coarse/nested
  timing overlap 경고를 남기며, C++/CUDA 또는 NN 구현 허가가 아니라 다음 실험 선택 자료다.
  manifest의 `*_candidate_stage_names`는 구조적 적합도 목록이고, `*_review_ready_stage_names`는
  현재 workload의 GPU gate까지 통과한 목록이다.
- whole-code hardware-fit atlas는 static AST/text scan으로 function/class symbol의 role tag,
  data surface, hotspot signal, hardware fit, compact CCoT, decision card를 만든다. 이 artifact는
  JAX, torch, CUDA, `_metroflow_rust`를 import하지 않으며, GPU/C++/NN 구현 허가가 아니라
  다음 measurement probe 선택 자료다.
  `python -m metroflow.benchmarks.run --hardware-atlas --hardware-atlas-artifact-prefix
  artifacts/runtime_spine_review/hardware-fit-atlas`로 `.md`, `.json`, `.html`, `.manifest.json`
  bundle을 생성한다. 기존 runtime suite JSON을 함께 연결하려면
  `--hardware-atlas-runtime-suite-json artifacts/runtime_spine_review/runtime-suite-eager-smoke.json`을
  추가한다.
- isolated routing candidate benchmark는 `run_measured_routing_candidate_benchmark`를 사용하며
  dynamic-potential recompute/cache counters와 timing totals, final candidate path, ranked-K candidate
  paths/costs/path-size metadata, routing copy-boundary note를 기록한다.
- review visualization은 `run_runtime_diagnostic_rollout`와 `write_runtime_diagnostic_html`로 생성한다.
  산출물은 static HTML/SVG이며 smoke diagnostic으로만 해석한다.
- generated city map 검토는 `build_static_city_map_artifact`와 `write_static_city_map_html`을 사용한다.
  산출물은 typed centerline/section 폭, road class, zone/POI, bridge, connectivity repair link,
  queue/congestion overlay를 포함하는 static HTML/SVG이다.
- 로컬 OSM XML reference는 `import_osm_xml_file`로 meter-space typed geometry/topology에
  정규화할 수 있다. 이 경로는 표준 라이브러리만 사용하고 네트워크 요청을 하지 않으며,
  default runtime 입력이나 synthetic generator validation evidence가 아니다.
- same-layer 교차를 graph node로 승격한 검토용 topology는
  `CityGenerationConfig(topology_mode="sidecar_local_fabric_planar")`로 명시한다.
  이 모드는 topology/geometry gate를 통과하지만 초기화 비용과 route-ID 호환성 때문에
  runtime default로 승격되지 않았다.
- terrain, continuous streets, planar blocks, block land use, POIs, sections,
  turns, CSR을 하나의 simulation input으로 컴파일하는 현실형 경로는
  `CityGenerationConfig(topology_mode="realistic_synthetic_v1",
  zone_poi_coupling_mode="block_based_v1")`로 명시한다. 이 조합은
  fail-closed이며 legacy fallback이 없고 아직 runtime default가 아니다.
  `metroflow.city.generate_city_map(config, scenario_id, seed)`가 composed
  blueprint와 runtime map의 권위 entrypoint다.
- 방사형 이외의 합성 형태는 `CityGenerationConfig(morphology_style_id=...)`로 선택한다.
  지원 값은 `grid_core`, `polycentric_tod`, `river_constrained`, `superblock_mixed`,
  `organic`, `ring_radial`이며 기본 `auto`는 기존 scenario별 선택을 보존한다. 문헌 기반
  실측값과 생성 morphometric은 reference/diagnostic 전용이고 특정 실제 도시 재현 주장이 아니다.
  `grid_core`, `river_constrained`, `superblock_mixed`, `organic`은 sidecar topology mode에서만
  허용되며 지원하지 않는 `standard` 조합은 fail-closed한다.
- 동일 seed의 형태 비교 bundle은
  `python -m metroflow.ui.morphology_atlas --output-dir artifacts/city_morphology_atlas_20260710
  --seed 17`로 생성한다.
- `step_world`의 긴 인자 목록은 호환용으로 유지하고, 신규 호출자는 `step_world_from_inputs`와
  `FastTickInput`/`MediumTickInput`을 우선 사용한다.
- 새 이식 코드는 baseline fallback, immutable `WorldState`, explicit units, deterministic replay 요구를 유지해야 한다.
- visual/render dependencies는 optional이어야 하며, core import를 막으면 안 된다.

## 핵심 구현 순서
- 먼저 S2:
  - WorldState
  - contracts
  - multirate scheduler
  - cache invalidation
  - replay benchmark
- 다음 S1:
  - mesoscopic hybrid core
  - generalized-cost routing
  - candidate path K + path-size correction
  - event-triggered reroute
  - lagged land-use feedback

## 다음 작업
- `docs/harness/PROJECT_STATE.md`, `docs/harness/CLAIM_LEDGER.md`, 그리고
  `docs/audit/metroflow_external_audit_20260711/README.md`를 현재 authority로 사용한다.
- seed 41에서 통과한 functional closure와 exact dynamic-state replay를 더 넓은 generated/event
  workload와 scale/memory benchmark로 확장하고 물리적 link traversal 의미를 명시한다.
- legacy accessibility/land-use cadence를 `SimulationState`에 통합하거나 complete LUTI claim을
  명시적으로 폐기하기 전에는 city-to-traffic-to-LUTI loop를 완결됐다고 부르지 않는다.
