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
- route candidate cache key/fingerprint는 geometry id, link count, flow generation, incident generation,
  destination, refresh policy를 포함해야 한다

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
- backend 입력/출력은 contiguous NumPy-compatible arrays와 explicit dtype을 사용한다
- backend는 hidden mutation 없이 새 배열/상태를 반환한다
- Rust CPU backend의 현재 slice는 `traffic.meso` edge batch evolution, `flow.engine` baseline flow array core,
  `routing.dynamic_potential` node cost-to-go core만 담당한다
- explicit `rust_cpu` backend는 fail-closed이고, `auto`에서만 baseline fallback을 허용한다
- 현재 Rust CPU wrapper는 edge 입력을 `Vec<f64>`, flow/routing 입력을 `Vec<f32>`/`Vec<i32>`/`Vec<bool>`로 복사한다
- `edge_backend="auto"`는 `rust_cpu` → `jax` → `baseline`, `flow_backend="auto"`는 `rust_cpu` → `baseline` 순서만 허용한다
- `routing_backend="auto"`는 `rust_cpu` → `baseline` 순서만 허용하며, greedy path construction은 Python baseline에 남아 있다
- PyTorch/libtorch/custom CUDA는 profiling 이후 좁은 hot kernel에만 추가한다

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
