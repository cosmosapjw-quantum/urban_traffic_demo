# AGENTS.md

## 최상위 규칙
- 개인 연구용 단일 사용자 코드: 보안·권한분리·악의적 위변조 방어는 기본 범위 밖이다. 해시/manifest는 우발적 손상 확인과 과학적 재현성 식별에만 사용하며 보안성을 주장하지 않는다.
- S2 before S1
- external-data learning 금지
- baseline fallback 필수
- immutable WorldState
- explicit units
- multirate scheduler
- cache invalidation rule 문서화
- deterministic replay 필수
- behavior-cluster TDD (공개 behavior RED/GREEN 유지, private helper 커밋 및 helper 단위 전체 suite 반복 금지)
- 단일 직렬 구현자 + frozen candidate 이후 읽기 전용 subagent review (최대 3회)
- 선행 PR 미완료 시 후속 PR 선행 보증/검토 차단 (PR(n+1) blocked until PR(n) merged/stopped)
- 단일 메타인지 환원 (*_METHOD_PILOT=PASS|SPLIT) 및 META_RECURSION_BLOCKED
- 보증 문서 크기는 대상 source+test 코드 크기 이하로 엄격 제한 (assurance inflation 방지)

## 지금 하지 말 것
- 다중 사용자 인증·인가, 공격자 위협 모델, anti-tamper/서명 인프라, 제품 보안 하드닝 (사용자가 연구 범위를 명시적으로 바꾸기 전까지)
- lane-level microscopic default
- RL/LLM-first route brain
- ECS/plugin-first architecture
- distributed multi-GPU
- full generic frameworkization
- private helper 단위 micro-commit 및 내부 루프 전체 test suite 반복 (gate inflation)
- 부모 PR 미완료 상태에서 자식 PR 선행 보증 문서 작성 (assurance inflation)
- 메타인지 판단 후 반복 재평가 루프 (meta recursion)

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
- process/gate/assurance inflation 영향? `docs/harness/PROCESS_INFLATION_GUARDRAILS.md` 확인
- acceleration 작업 전 `docs/harness/RUNTIME_ACCELERATION_DECISION_GUARDRAILS.md`의 self-ask/step-back gate 확인

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
- 035-runtime-suite-html: Added standalone runtime suite HTML review rendering for stage gate and per-seed backend metadata
- 036-runtime-suite-bundle: Added `--runtime-suite-artifact-prefix` to write markdown, JSON, HTML, and manifest together
- 037-runtime-suite-eager-demand: Exposed `--runtime-suite-eager-trip-generation` for non-empty routing/agent benchmark workloads
- 038-runtime-suite-eager-metadata: Preserved eager trip generation in runtime suite JSON payloads and bundle manifests
- 039-runtime-acceleration-report: Added JAX/GPU, NN surrogate, Rust CPU acceleration candidate reporting and timing-overlap warnings
- 040-runtime-nested-timing: Split route refresh and active-agent update into nested timing stages for deeper GPU/NN backend triage
- 041-active-agent-allocation-timing: Split active-agent allocation timing into candidate-selection and pool-write sub-stages
- 042-runtime-acceleration-guardrails: Added anti-local-minima self-ask, step-back, and compact CCoT review guardrails
- 043-active-agent-pool-write-breakdown: Split pool-write timing into typed-array replacement and plugin-memory write sub-stages
- 044-active-agent-plugin-memory-batch: Batched allocation plugin-memory replacement and redirected next slice to route path-build
- 045-routing-potential-float32-fix: Fixed baseline dynamic-potential float32 heap-staleness and redirected route acceleration toward potential recompute/cache amortization
- 041-urban-morphology-diversity: Added literature-backed diagnostic morphometrics and distinct grid, polycentric, constrained-corridor, multi-grid, organic, and radial city grammars
- 046-city-map-contracts: Added source provenance, typed centerlines, road-section grammar, and static node-interface catalogs without CSUR source reuse
- 047-static-ribbon-map: Added physical-road width-aware SVG rendering, isolated layers, uniform meter projection, and rendered-catalog provenance
- 048-offline-osm-reference: Added standard-library offline OSM XML projection, splitting, clipping, simplification, and typed reference import
- 049-planar-city-validation: Added explicit planar sidecar mode with crossing, assignment, sampled-OD, and replay gates while retaining the standard runtime default
