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
- 002-fast-edge-evolution: Added the original pure-baseline fast edge evolution feature; JAX is now optional extra only
- 009-gpu-venv-runtime: Updated runtime contract to Python 3.12 + `jax[cuda13]`; added optional JAX fast-edge backend with baseline fallback
- 010-metro-absorption-foundation: Absorbed donor city/flow/routing/demand/UI/sim contract slices into root; root code must not import from external `metro/`
- 011-metro-absorption-reporting: Added simulator-only learning experience, run summaries, UI stream server, benchmark smoke runner, scenario presets, and policy plugin registry without `metro/` dependency
- 012-backend-rearchitecture: Moved JAX outside core contracts; root runtime stores NumPy arrays and keeps JAX as optional accelerator extra
- 015-runtime-spine: Connected `SimulationState` step to event effects, flow update, route candidate cache, active-agent movement, runtime replay, and measured runtime benchmark
- 016-route-candidate-k: Enabled deterministic Python baseline ranked K route candidates while keeping Rust routing as an optional kernel accelerator
- 018-rust-ranked-routing: Added optional Rust CPU ranked-K route candidate enumeration with Python baseline parity and explicit/auto fallback policy
- 017-path-size-choice: Added configurable path-size route-choice correction to runtime selection, replay fingerprint, and benchmark metadata
- 019-rust-agent-backend: Added optional Rust CPU active-agent action planning with Python-owned immutable pool replacement
- 020-runtime-stage-gate: Added runtime stage timing totals and GPU candidate reporting without adding CUDA dependencies
- 021-runtime-gpu-gate-aggregate: Added multi-run runtime GPU candidate gate aggregation while keeping CUDA backend names documentation-only
- 022-rust-crate-modules: Started Rust crate module split by extracting common constants, result aliases, and validators
- 023-rust-edge-module: Moved Rust CPU edge batch evolution into a focused `edge` module without changing the PyO3 API
- 024-rust-flow-module: Moved Rust CPU flow array core into a focused `flow` module without changing the PyO3 API
- 025-rust-agent-module: Moved Rust CPU active-agent action planner into a focused `agent` module without changing the PyO3 API
- 026-rust-reroute-module: Moved Rust CPU reroute decision core into a focused `reroute` module without changing the PyO3 API
- 027-rust-routing-module: Moved Rust CPU routing kernels into a focused `routing` module while keeping `lib.rs` as the PyO3 facade
- 028-runtime-benchmark-suite: Added Python runtime benchmark suite orchestration for unique seed runs and GPU gate markdown artifacts
- 029-runtime-suite-reporting: Added reviewer-facing markdown rendering for runtime benchmark suite GPU gate artifacts
- 030-runtime-suite-runner: Added a public benchmark runner facade returning suite result, aggregate GPU gate report, and review markdown
- 031-runtime-suite-cli: Added `--runtime-suite` benchmark CLI mode with fail-closed seed parsing
- 032-runtime-suite-artifact: Added `--runtime-suite-report-path` markdown artifact output for long-run benchmark review
- 033-rust-packaging-split: Added crate-local maturin metadata so Rust extension install does not shadow the root `metroflow` package
- 034-runtime-suite-json: Added machine-readable runtime suite JSON artifacts for frontend/diagnostic consumers
