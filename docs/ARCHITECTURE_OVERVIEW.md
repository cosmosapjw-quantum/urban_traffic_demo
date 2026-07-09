# Architecture Overview

## 3층 분리
1. Spatial / World Layer
   - graph, lane grammar, zones, node compiler
2. Dynamics Layer
   - traffic core, routing, accessibility, land-use, scheduler
3. Interface Layer
   - metrics, logging, replay, visualization

## 핵심 모듈
- core/
  - state, contracts, units, cache, journal
- city/
  - RoadNetworkCSR, generator_v2, realism gates, transit-ready schema, zones/POIs
- flow/
  - LinkState, NodeState, baseline link/node flow engine, traffic events
- routing/
  - dynamic potential, candidate refresh, reroute policy, policy mixer
- learning/
  - OD UCB, policy blend, simulator-only experience extraction, adaptive plugin registry
- map/
  - legacy/simple generator facade, lane_grammar, node_compiler
- demand/
  - legacy citizens/schedules/trip_generation, zoning-backed population/trips, accessibility
- traffic/
  - compatibility baseline meso/routing/incidents
- landuse/
  - evolution
- policy/
  - archetypes, ema, bandit, optional neural plugin
- sim/
  - scheduler, replay, orchestrator, state/control/invariant contracts, baseline init/step,
    runtime route-cache/active-agent spine, run summary, scenario presets
- ui/
  - packet envelopes, stream throttling, snapshot source, control adapter, disruption presets, Navigator stream server
- benchmarks/
  - benchmark smoke runner and report formatting
- metrics/
  - observables, benchmarks
- viz/
  - viewer adapter

## 핵심 원칙
- bulk transport와 behavior closure 분리
- WorldState에서만 상태 이동
- 모든 느린 feedback은 lagged
- cache는 versioned
- viewer는 core loop를 막지 않음
- `SimulationState` runtime spine은 event effects, flow update, route candidate refresh,
  active-agent movement, metrics/replay/UI snapshot을 deterministic 순서로 연결함
- active-agent movement는 lane-level/microscopic model이 아니다. activated trip allocation은 첫 route link의
  `LinkState.queue_vehicles`를 1대 증가시키고, 다음 tick의 link-to-link advance는 flow update가 산출한
  `outflow_vehicles` 예산을 deterministic slot 순서로 소비한다.
- final-link arrival은 sink discharge budget을 소비한다. 목적지 discharge는 final link의
  effective capacity에서 산출한 정수 예산을 deterministic slot 순서로 쓰며, zero capacity/closure에서는
  agent가 final link에 남고 `active_agent_sink_wait_this_tick`/`active_agent_sink_wait_total`로 관측된다.
- `WorldState`/`step_world`는 compatibility contract이고, integrated long-run runtime은
  `sim.step.simulation_step`을 기준으로 확장함
- 기본 backend contract는 NumPy host arrays이며, accelerator 배열은 core state에 저장하지 않음
- JAX는 optional `jax` extra의 explicit backend로만 사용하고, Rust CPU backend는 edge/flow/routing
  및 active-agent action planning 좁은 core를 NumPy-compatible FFI 경계 뒤에서 선택적으로 가속함
- generated city topology는 runtime acceptance 전에 weak-connectivity repair와 strict gate를 통과해야 함
- `metro/` donor 구현은 루트 Python 3.12/CUDA13/runtime policy로 흡수한다.
- root runtime은 외부 `metro/` 폴더 삭제 후에도 import/test가 가능해야 한다.
- optional visual dependencies는 core import를 막으면 안 된다.
