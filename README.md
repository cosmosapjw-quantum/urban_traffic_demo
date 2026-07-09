# Urban Traffic Simulator — Developer Documentation + Starter Skeleton Bundle

이 번들은 다음을 포함한다.

1. 개발자 문서 세트(md)
2. spec-kit 입력/타깃 문서
3. 세분화된 작업 티켓 백로그
4. `src/metroflow/` 코드 스켈레톤
5. 최소 테스트/벤치 스켈레톤

## 로컬 Python / GPU 기준
- Ubuntu 24.04 기본 Python 3.12를 기준으로 한다.
- repo-local `.venv`를 사용한다.
- 기본 설치는 NumPy baseline만 요구한다.
- NVIDIA RTX 3080 Ti 12GB는 optional `jax` extra로 단일 GPU CUDA 13 경로를 선택적으로 사용한다.
- core loop 기본값은 항상 baseline이며, JAX/CUDA 경로는 명시적으로 요청한 경우에만 사용한다.
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
  city→demand→event effects→flow→route candidate cache→active agents→invariant→UI snapshot의
  deterministic runtime spine을 제공한다.
- active-agent spine은 activated trip을 선택된 route candidate의 첫 링크에 배정하고, source link queue에
  차량 1대를 삽입한다. link-to-link 이동은 직전 flow update의 `outflow_vehicles` 정수 예산을
  slot id 순서로 소비한다.
- agent slot memory는 선택된 candidate id/index/count와 baseline path cost/path-size factor,
  path-size utility를 보존한다.
- runtime reroute는 incident 또는 route refresh cadence에서만 현재 링크 이후 tail 후보를 검토한다.
  cooldown이 남은 slot은 기존 route tail을 유지하고 cooldown만 감소한다.
- final-link completion은 sink discharge budget을 소비한다. link-to-link movement는
  `outflow_vehicles` 예산을 쓰고, destination discharge는 final link의 effective capacity가 0보다
  클 때만 deterministic slot 순서로 완료된다. sink discharge budget 때문에 대기한 agent 수는
  `active_agent_sink_wait_this_tick` 및 `active_agent_sink_wait_total` telemetry/metrics에 기록된다.
- reporting/experiment 표면으로 simulator-only learning experience, run summary comparison,
  Navigator UI stream packetization, benchmark smoke runner, scenario presets, adaptive policy plugin registry를 흡수했다.
- `SimulationState` runtime replay는 `make_runtime_replay_boundary`와 `replay_simulation_sequence`를 사용한다.
  replay boundary는 backend config와 route-cache fingerprint를 기록한다.
- integrated runtime benchmark는 `run_measured_runtime_spine_benchmark`를 사용하며 flow/routing backend와
  agent backend, route candidate/dynamic-potential cache counters, active-agent update wall time 및
  timing totals를 결과에 보존한다.
  `format_runtime_stage_timing_markdown`은 flow, route candidate refresh, dynamic potential,
  reroute decision, active-agent update stage의 wall-time share와 future GPU 후보 stage를
  reviewer-facing section으로 렌더링한다.
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
- isolated routing candidate benchmark는 `run_measured_routing_candidate_benchmark`를 사용하며
  dynamic-potential recompute/cache counters와 timing totals, final candidate path, ranked-K candidate
  paths/costs/path-size metadata, routing copy-boundary note를 기록한다.
- review visualization은 `run_runtime_diagnostic_rollout`와 `write_runtime_diagnostic_html`로 생성한다.
  산출물은 static HTML/SVG이며 smoke diagnostic으로만 해석한다.
- generated city map 검토는 `build_static_city_map_artifact`와 `write_static_city_map_html`을 사용한다.
  산출물은 road class, zone/POI, bridge, connectivity repair link, queue/congestion overlay를 포함하는
  static HTML/SVG이다.
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
- `docs/TICKET_BACKLOG.md` 와 `specs/001-metroflow/tasks_detailed.md` 를 기준으로
  `src/metroflow/` 구현을 채워가면 된다.
