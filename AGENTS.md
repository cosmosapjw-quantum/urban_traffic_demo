# AGENTS.md

## 최상위 규칙
- S2 before S1
- external-data learning 금지
- baseline fallback 필수
- immutable WorldState
- explicit units
- multirate scheduler
- cache invalidation rule 문서화
- deterministic replay 필수

## 지금 하지 말 것
- lane-level microscopic default
- RL/LLM-first route brain
- ECS/plugin-first architecture
- distributed multi-GPU
- full generic frameworkization

## 구현 순서
1. core/state.py
2. core/contracts.py
3. sim/scheduler.py
4. traffic/meso.py
5. traffic/routing.py
6. demand/accessibility.py
7. landuse/evolution.py
8. policy/bandit.py
9. map/lane_grammar.py
10. map/node_compiler.py

## 필수 체크
- contract 영향?
- time-scale 영향?
- cache invalidation 영향?
- replay/regression 영향?
- benchmark 영향?

## Active Technologies
- Python 3.12 on Ubuntu 24.04 via repository-local `.venv` + Python stdlib dataclasses + pytest
- NumPy baseline runtime by default; optional single-GPU JAX CUDA 13 extra for RTX 3080 Ti 12GB
- Pure baseline path remains the default for deterministic replay and regression gates

## Recent Changes
- 002-fast-edge-evolution: Added Python 3.11 + Python stdlib dataclasses + pytest; repository deps include `jax` and `jaxlib` but this feature stays in the pure baseline path
- 009-gpu-venv-runtime: Updated runtime contract to Python 3.12 + `jax[cuda13]`; added optional JAX fast-edge backend with baseline fallback
- 010-metro-absorption-foundation: Absorbed donor city/flow/routing/demand/UI/sim contract slices into root; root code must not import from external `metro/`
- 011-metro-absorption-reporting: Added simulator-only learning experience, run summaries, UI stream server, benchmark smoke runner, scenario presets, and policy plugin registry without `metro/` dependency
- 012-backend-rearchitecture: Moved JAX outside core contracts; root runtime stores NumPy arrays and keeps JAX as optional accelerator extra
- 015-runtime-spine: Connected `SimulationState` step to event effects, flow update, route candidate cache, active-agent movement, runtime replay, and measured runtime benchmark
- 016-route-candidate-k: Enabled deterministic Python baseline ranked K route candidates while keeping Rust routing as an optional kernel accelerator
- 017-path-size-choice: Added configurable path-size route-choice correction to runtime selection, replay fingerprint, and benchmark metadata
