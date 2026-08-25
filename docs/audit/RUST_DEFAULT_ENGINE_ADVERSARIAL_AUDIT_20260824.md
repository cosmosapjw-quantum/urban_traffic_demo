# MetroFlow 전체 Rust 기본 엔진 전환 적대적 감사 및 개발 전략

**작성일:** 2026-08-24
**대상:** `cosmosapjw-quantum/urban_traffic_demo`
**기준:** `main@01c80b432344f94209daaa198bb1eb007839fc7f`
**기준 tree:** `13ab0dd317d2581b83aba2d8b7763ef644dd30fb`
**패키지 역할:** 현재 Python-owned runtime을 Rust-owned engine + Python frontend 구조로 옮기기 위한 감사·계약·DAG 확장
**중요:** 이 문서는 속도향상을 이미 입증한 보고서가 아니다. 코드 소유권·경계·정확성 위험을 감사하고, 향후 측정 가능한 이행계약으로 컴파일한다.

## 0. 연구코드 전제

이 프로젝트는 단일 개발자가 직접 사용하는 개인 연구 코드다. 보안, 다중 사용자 권한분리, 악의적 위변조, signed commit, 공급망 공격 대응은 본 감사의 threat model이 아니다. CI, digest, replay, manifest는 다음 용도로만 사용한다.

1. 수치·과학적 결과의 회귀 탐지,
2. 장기 이행 중 state와 증거의 유실 방지,
3. Python oracle과 Rust engine의 차이를 조기에 검출,
4. 속도 주장이 측정 조건을 숨기지 않게 하기.

불필요한 기업형 governance는 추가하지 않는다. 반면 단위, dtype, 경계조건, route legality, vehicle mass, cache invalidation, tick ordering, deterministic replay는 연구 정확성에 직접 연결되므로 hard gate다.

---

## 1. 집행 요약

### 최종 판정

현재 구조는 다음과 같다.

```text
Python
  owns SimulationState, tick order, demand/event/routing/flow/agent composition,
  invariant validation, replay, snapshots, reporting
        |
        +-- repeated fine-grained calls
              |
              v
Rust extension
  edge / flow / routing / reroute / agent kernels
  Vec-in / Vec-out
```

목표 구조는 다음과 같다.

```text
Python frontend
  CLI / config authoring / UI / reports / plots / benchmark orchestration
        |
        | coarse Engine API
        v
Rust Engine
  static city + canonical dynamic state + scheduler + RNG + events + demand
  + routing + flow + agents + land-use/policy state + invariants + replay
        |
        +-- optional persistent GPU numeric chunks
```

현재의 개별 kernel 가속은 폐기할 실패가 아니다. 그러나 Python이 tick을 소유하고 각 단계마다 데이터를 포장·복사하는 동안에는 전체 runtime이 Rust가 되지 않는다. 따라서 이번 계획은 “가장 느린 함수만 Rust로 옮긴다”가 아니라 **canonical state와 tick transaction 전체를 Rust로 옮기는 architecture migration**이다.

### 핵심 판정표

| 항목 | 판정 |
|---|---|
| 기존 Rust edge/flow/routing/reroute/agent kernels | 보존·compatibility oracle로 활용 |
| `src/metroflow/backends/rust_cpu.py`의 list bridge | default path에서 제거 필수 |
| Python `simulation_step` | shadow oracle로 보존, 최종 default path에서는 제거 |
| Rust-owned persistent Engine | 도입 승인 |
| Python frontend | 유지 |
| Python oracle | 최종감사까지 유지, 이후 explicit debug backend |
| Rust default backend | RUST-PR-015 이전 금지 |
| GPU | optional admission; Rust CPU promotion을 막지 않음 |
| JAX/Pallas | tensor-shaped persistent chunks의 1순위 GPU 경로 |
| custom CUDA/JAX FFI | built-in JAX로 부족할 때만 |
| PyTorch custom operator | 학습/tensor ecosystem 필요가 있을 때만 |
| 기존 MAP DAG | `MAP-PR-011`까지 순서 그대로 보존 |
| Rust migration DAG | `MAP-PR-011 -> RUST-PR-001`로만 append |

---

## 2. 코드 기반 FACT 감사

### 2.1 Python이 실제 runtime authority다

`src/metroflow/sim/state.py`의 `SimulationState`는 Python dataclass이며 static/dynamic substate가 광범위한 `Any`, mutable dict, Python object reference를 가진다. `with_clock()`과 `with_dynamic_updates()`는 dataclass replacement로 새 wrapper를 만든다.

`src/metroflow/sim/step.py`의 `simulation_step()`은 한 tick에서 다음 순서를 직접 실행한다.

1. RNG key advance,
2. control 적용,
3. event scheduler,
4. event effect,
5. trip activation,
6. route candidate refresh와 active-agent preparation,
7. flow,
8. agent/route commit,
9. invariant validation,
10. UI snapshot,
11. metrics와 telemetry.

따라서 현재 Rust kernel이 여러 개 있어도 canonical transaction과 failure boundary는 Python이다.

### 2.2 현재 Rust 경계는 copy-heavy다

`src/metroflow/backends/rust_cpu.py`는 거의 모든 배열을 `np.ascontiguousarray(...).tolist()`로 Python list로 바꾸고, PyO3 함수가 반환한 list/tuple을 다시 NumPy 배열로 만든다. 현재 Rust API는 `Vec<T>` 인자와 `Vec<T>` 결과를 사용한다.

이 구조의 비용은 계산 하나가 아니라 다음의 합이다.

```text
NumPy view/coercion
→ Python list 객체 생성
→ Python scalar boxing
→ PyO3 Vec 추출/복사
→ Rust allocation
→ Rust 계산
→ Vec 결과
→ Python sequence
→ NumPy 재할당/복사
```

kernel 자체가 빨라도 tick마다 여러 번 반복되면 boundary가 병목이 된다.

### 2.3 Rust는 kernel 집합이지 engine이 아니다

현재 `crates/metroflow-rust/src`에는 `edge`, `flow`, `routing`, `reroute`, `agent` module과 PyO3 facade가 있다. persistent Rust state를 소유하는 `Engine` class, full scheduler, checkpoint, replay digest, demand lifecycle, static city/DCEL authority는 없다.

### 2.4 backend 설정도 소유권을 분할한다

`SimulationConfig`에는 `edge_backend`, `flow_backend`, `routing_backend`, `agent_backend`가 각각 존재하고 default는 모두 `baseline`이다. 이 구조는 실험에는 유용하지만 최종 Rust-default engine에서는 다음 혼합상태를 허용한다.

```text
flow = Rust
routing = Python
agent = Rust
event/demand/invariant = Python
```

이 조합에서는 state owner가 하나가 아니며, 캐시·event generation·queue transaction의 경계가 계속 Python에 남는다.

### 2.5 중요한 기능이 Rust에 아직 없다

현재 `spatial_queue_v1`은 configuration 단계에서 Python baseline flow를 강제하고, flow code도 discrete-agent authority를 Rust backend와 함께 쓰지 못하도록 막는다. Python flow code에는 residual credit, token carry, sink/internal competition, finite storage와 spillback 등 복잡한 authority가 남아 있다.

또한 Python 쪽에는 대규모 surface가 남아 있다.

- `sim/routing_runtime.py`: 약 83 KB,
- `sim/invariants.py`: 약 43 KB,
- `sim/step.py`: 약 35 KB,
- `sim/replay.py`: 약 29 KB,
- `flow/engine.py`: 약 38 KB,
- demand population/trips, city generation/DCEL/static authority.

따라서 kernel 몇 개를 더 추가하는 것으로 “Rust backend”가 완결되지 않는다.

### 2.6 required CI가 Rust를 보증하지 않는다

현재 required CI 주석은 NumPy path를 authority로 두고 Rust/JAX를 빌드하지 않는다고 명시한다. Rust explicit selection이 없는 경우 관련 테스트는 skip될 수 있다. Rust-default 이행 전에는 최소한 다음이 required surface가 되어야 한다.

- `cargo fmt --check`,
- `cargo clippy`,
- `cargo test --workspace`,
- PyO3 extension build/install,
- Python/Rust shadow parity,
- exact no-skip assertion,
- final `ci gate`.

### 2.7 현재 병렬화는 부분적이며 결정론 정책이 불완전하다

Rust routing은 Rayon을 사용하지만 engine-owned pool과 global thread budget이 없다. Rayon의 parallel reduction order는 일반적으로 지정되지 않으며, floating-point reduce는 완전 결정론적이지 않을 수 있다. 따라서 canonical float authority에서는 unordered `sum/reduce`, float atomics, order-sensitive hash iteration을 금지해야 한다.

### 2.8 SIMD 전략은 stable Rust에 맞춰야 한다

Rust `std::simd` portable SIMD는 2026-08 기준 nightly-only experimental API다. 따라서 default engine은:

1. contiguous SoA loop와 compiler auto-vectorization,
2. allocation reuse,
3. benchmark된 stable `std::arch` runtime dispatch,
4. 필요하면 별도 승인된 stable SIMD crate

순서가 맞다. nightly requirement나 `-C target-cpu=native`만으로 배포되는 binary는 default contract가 될 수 없다.

### 2.9 GPU는 “함수”가 아니라 residence boundary로 판단해야 한다

기존 JAX dense-flow 실험은 일부 규모에서 성능 가능성을 보였지만 큰 규모 drift와 per-tick host synchronization 문제가 남았다. GPU admission의 핵심은 어느 함수가 빠른지가 아니라 다음이다.

- state가 여러 tick 동안 device에 머무르는가,
- compile/transfer/sync를 포함해 Rust CPU보다 빠른가,
- CPU와 GPU가 canonical state를 나눠 소유하지 않는가,
- drift가 field-level contract 안에 드는가.

JAX 공식 문서도 외부 C/CUDA code를 typed FFI로 호출할 수 있고 GPU handler에 CUDA stream을 전달할 수 있다고 설명한다. 그러나 FFI는 유지비가 높아 built-in JAX/Pallas로 충분하지 않을 때의 후순위가 맞다.

---

## 3. 적대적 findings

## P0

### P0-1: canonical state 이중소유 위험

kernel-by-kernel migration을 계속하면 Rust가 계산하고 Python이 state mutation을 적용한다. queue와 agent, route cache와 incident generation처럼 한 transaction이어야 하는 항목이 언어 경계로 갈라진다.

**필수 해결:** Rust `Engine` 하나가 static/dynamic state와 tick commit을 소유한다.

### P0-2: current Rust flow는 default 기능 완결이 아니다

spatial queue와 discrete-agent token authority가 Rust에 없으므로 Rust-default를 먼저 켜면 기능을 잃거나 silent fallback이 필요해진다.

**필수 해결:** point/spatial queue, residual carry, sink/internal token, storage/spillback을 함께 port한다.

### P0-3: deterministic replay가 병렬화로 깨질 수 있다

Rayon work stealing, unordered reductions, HashMap iteration, float atomics은 thread count별 결과 차이를 만들 수 있다.

**필수 해결:** 1/2/4/8 threads에서 동일 digest, fixed partition + ordered combine.

### P0-4: RNG와 scheduler ordering drift

Python tick의 random stream과 event/control order를 그대로 이해하지 않고 port하면 결과가 달라져도 각 kernel unit test는 통과할 수 있다.

**필수 해결:** named RNG streams, explicit phase order, simultaneous-event regression.

### P0-5: cache invalidation drift

routing cache, incident generation, topology/cost/policy generation이 cross-language일 때 stale route가 성공 결과로 남을 수 있다.

**필수 해결:** Rust-owned cache key/generation and exact invalidation matrix.

### P0-6: checkpoint/replay가 incomplete state를 봉인할 위험

persistent Engine은 cache, RNG, residual carry, policy memory까지 checkpoint해야 한다. visible arrays만 저장하면 restore 후 다른 결과가 나온다.

### P0-7: silent fallback은 속도·정확성 실패를 숨긴다

최종 Rust default에서 extension missing, panic, GPU failure를 Python baseline으로 자동 대체하면 사용자는 느린/다른 backend를 성공으로 오인한다.

**필수 해결:** explicit `python_oracle`; Rust default missing/error는 fail closed.

### P0-8: GPU split authority

dense flow를 GPU가 수정하고 routing/agent는 CPU Rust가 수정하면서 transaction이 분리되면 mass와 replay가 깨질 수 있다.

**필수 해결:** coarse device chunk 또는 advisory output만 허용하고 owner를 하나로 유지한다.

## P1

1. required CI가 Rust를 build/test하지 않음.
2. `.tolist()`와 per-kernel FFI가 전체 속도 향상을 차단.
3. Python tick loop가 default path에 남을 가능성.
4. four-backend config가 unsupported mixed ownership을 허용.
5. PyO3 0.23/Rayon 1.10은 migration 시작 시 별도 dependency upgrade 판단이 필요하나 semantic port와 섞으면 안 됨.
6. Rust panic/error가 transactional state를 보장하는지 불명확.
7. `Vec<Vec<T>>`, `Vec<bool>`, per-call allocation이 memory/FFI 효율을 제한.
8. GIL을 잡은 채 긴 Rust 계산을 수행할 가능성.
9. UI snapshot이 every-tick copy boundary로 변할 위험.
10. Rust output을 맞추기 위해 Python oracle/golden/tolerance를 바꿀 위험.
11. SIMD microbenchmark만 좋아지고 full engine/RSS가 나빠질 위험.
12. GPU compile/transfer를 제외한 kernel-only speed claim.
13. optional GPU imports가 CPU-only frontend를 깨뜨릴 위험.
14. long run snapshot/checkpoint에서 memory growth.
15. fresh-context reviewer 없이 구현 agent가 자기 선택을 승인할 위험.

전체 P0/P1 50개는 `RUST_ENGINE_P0_P1_THREAT_CATALOGUE_V1.json`에 test/assertion/STOP gate와 함께 기록한다.

---

## 4. 권장 아키텍처

### 4.1 crate 분리

```text
crates/
  metroflow-core/      # pure Rust rlib, simulation authority
  metroflow-python/    # PyO3 cdylib, thin frontend adapter
  metroflow-rust/      # temporary compatibility facade
```

`metroflow-core`는 Python/PyO3를 import하지 않는다. `metroflow-python`만 Python types와 NumPy bridge를 안다.

### 4.2 Rust Engine API

```text
Engine.create(static_input, config, seed)
Engine.apply_controls(batch)
Engine.apply_events(batch)
Engine.step(n_ticks, snapshot_policy)
Engine.snapshot(kind)
Engine.checkpoint()
Engine.restore(bytes)
Engine.digest()
Engine.metrics()
```

Python은 `Engine.step()` 사이에 per-link/per-agent callback을 넣지 않는다.

### 4.3 data layout

- stable public IDs와 dense internal index 분리,
- CSR graph/turn tables,
- SoA dynamic state,
- ragged routes = `offsets + values`,
- field별 fixed dtype/unit/bounds,
- preallocated scratch buffers,
- snapshot은 read-only copy/borrow,
- checkpoint schema versioning.

### 4.4 CPU 병렬화

- Engine-owned Rayon pool,
- explicit thread count,
- destination/OD batch parallelism,
- disjoint link partitions,
- ordered indexed collection,
- integer reductions or fixed-order float combine,
- thread count가 달라도 identical digest,
- nested BLAS/JAX worker pool 금지.

### 4.5 SIMD

- 먼저 allocation과 memory layout을 고친다.
- auto-vectorization evidence를 확인한다.
- manual kernel은 scalar parity implementation을 함께 둔다.
- stable `std::arch` runtime feature detection만 default 후보로 삼는다.
- nightly `std::simd`와 fast-math는 금지한다.

### 4.6 GPU

우선순위:

1. JAX primitive/Pallas,
2. JAX typed FFI + custom CUDA,
3. direct CUDA bridge,
4. PyTorch custom operator는 실제 학습/tensor integration이 필요할 때만.

GPU candidate는 Rust CPU migration의 terminal dependency가 아니다. 결과가 HOLD여도 Rust-default 진행은 가능하다.

---

## 5. 기존 DAG 보존

현재 도시지도 DAG는 다음 순서다.

```text
MAP-PR-001 → ... → MAP-PR-011
```

기준 main에서는 MAP-PR-001부터 MAP-PR-005까지 병합된 것으로 관측된다. 새 Rust DAG는 기존 node나 edge를 수정하지 않는다.

```text
MAP-PR-011
   ↓
RUST-PR-001
   ↓
...
   ↓
RUST-PR-016
```

따라서 Rust implementation readiness는 현재:

```text
BLOCKED_BY_PREDECESSOR_DAG
```

다. 계획·감사 package는 지금 merge할 수 있지만 implementation PR은 MAP-PR-011의 merge + fresh-context PASS 전에는 시작하면 안 된다.

---

## 6. PR 단계

1. Workspace/CI/frozen oracle
2. State/units/IDs/RNG/checkpoint
3. Static city/network/DCEL
4. Demand/scheduler/control/events
5. Routing/cache/reroute
6. Point/spatial flow
7. Active agents
8. Land-use/policy state
9. Full Rust tick/replay/invariants
10. Coarse PyO3/NumPy boundary
11. Deterministic Rayon
12. SoA/allocation/SIMD
13. Optional GPU admission
14. Full shadow/performance matrix
15. Rust default cutover
16. Fresh-context final audit

각 PR 상세 contract는 `AUDIT_COMPILED_EXEC_PLAN_V1.json`에 있다.

---

## 7. 완료 판단

### architecture completion

- default step path의 `.tolist()` 0,
- per-entity FFI 0,
- Python entity loops 0,
- one Rust owner,
- both traffic models implemented,
- explicit Python oracle only.

### correctness completion

- P0=0, P1=0,
- mass/legality/cache/RNG/checkpoint/replay hard gates,
- 1/2/4/8 thread identical digest,
- public artifact schema parity,
- all required CI surfaces non-skipped.

### performance completion

- medium/large matrix geometric-mean speedup ≥ 2.0,
- peak RSS ≤ 1.25 × Python oracle,
- Python wall share < 5% in no-UI chunk,
- complete copy/compile/warmup evidence,
- missed target => HOLD, not threshold weakening.

---

## 8. 문헌·공식 기술 근거

- PyO3 user guide: https://pyo3.rs/main/
- rust-numpy array borrowing: https://docs.rs/numpy/latest/numpy/
- Rayon parallel iterators and thread pools: https://docs.rs/rayon/latest/rayon/
- Rust portable SIMD nightly status: https://doc.rust-lang.org/nightly/std/simd/
- JAX FFI, including GPU stream context: https://docs.jax.dev/en/latest/ffi.html
- PyTorch custom C++/CUDA operators: https://docs.pytorch.org/tutorials/advanced/cpp_custom_ops.html
- OpenAI Codex workflow: https://openai.com/business/guides-and-resources/how-openai-uses-codex/
- OpenAI harness engineering: https://openai.com/index/harness-engineering/

이 자료들은 architecture 선택을 정당화하지만 MetroFlow 속도 또는 parity의 증거는 아니다. 실제 승격 증거는 repository-local shadow matrix와 fresh review receipt여야 한다.

---

## 9. 최종 권고

whole-engine Rust migration은 타당하다. 현재의 가장 큰 병목은 단일 함수보다 **Python-owned transaction + fine-grained FFI + repeated state repacking**이라는 구조다. 다만 “전부 Rust로 옮긴다”는 목표를 한 거대한 PR로 실행하면 P0/P1 확률이 급증한다. 따라서 전체 범위를 포기하지 않되, state-owner invariant를 기준으로 16개 직렬 risk unit으로 나눠야 한다.

이 package의 의미는 다음과 같다.

```text
전체 migration 범위는 확정
PR별 semantic risk는 작게 분해
모든 P0/P1은 test/assertion/STOP으로 컴파일
fresh-context review가 다음 PR을 unlock
```

Rust-default 전환은 목표지만 현재 상태는 **BLOCKED**다. 먼저 MAP DAG를 끝내고, Rust plan의 RUST-PR-001부터 순서대로 실행해야 한다.
