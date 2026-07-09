# PRD — Accelerated Runtime Re-Architecture

Last updated: 2026-07-10
Status: active planning authority

## Product Definition

Metroflow targets an explainable 100k-scale synthetic city simulation where city
generation, mesoscopic traffic, routing, demand, active agents, diagnostics,
and optional learning surfaces remain deterministic and replayable. The
accelerated runtime program restructures the project around a stable Python
frontend/orchestration layer, NumPy authority, optional Rust CPU kernels, and
optional GPU/NN experiment lanes.

This PRD extends `docs/PRD.md`. It does not replace the core city-traffic PRD.

## Problem

Recent acceleration work exposed a local-minimum risk: repeated timing splits
can keep refining the same conclusion without changing the next engineering
decision. The project now needs a spec-driven process that compares static code
roles, runtime stage timings, deterministic replay evidence, and backend
contracts before implementing another optimization.

## Goals

- Preserve Python 3.12 + NumPy deterministic baseline as runtime authority.
- Keep `SimulationState`, replay, UI, diagnostics, and experiment orchestration
  in Python.
- Use Rust CPU only for branch/control-flow-heavy or deterministic mutation
  kernels with parity tests and explicit fail-closed backend selection.
- Use NumPy/SIMD for array-style flow, edge, cost, and aggregate baselines.
- Keep JAX/GPU and future PyTorch/custom CUDA as optional experiment lanes for
  dense numeric batches, route metadata/scoring, policy scoring, and supervised
  surrogate inference.
- Require `hardware-fit-atlas`, runtime benchmark evidence, and deterministic
  replay evidence before backend promotion.
- Run future work as spec-driven/subagent-driven PR slices with capped review
  loops and explicit anti-drift checks.

## Non-Goals

- External-data learning.
- RL/LLM-first route authority.
- NN route-legality authority.
- Lane-level microscopic default.
- ECS/plugin-first rewrite or broad frameworkization.
- Distributed multi-GPU.
- Immediate PyTorch/libtorch/custom CUDA dependency or build scaffold.
- Runtime default changes without parity and no-regression evidence.

## Architecture

The runtime is split into four lanes:

1. **Python orchestration/frontend:** config, `SimulationState`, replay,
   diagnostics, benchmark runners, UI snapshots, document/report generation,
   and optional experiment control.
2. **NumPy authority:** authoritative host arrays and deterministic baseline
   implementations for flow, edge, routing metadata, active-agent state, and
   replay-visible schemas.
3. **Rust CPU kernels:** optional PyO3 backends for graph search, route
   enumeration, deterministic action planning, and branch-heavy batch cores.
4. **GPU/NN experiment lanes:** optional JAX/GPU first, future PyTorch/custom
   CUDA only after benchmark admission. Targets are dense flow, batched route
   scoring/metadata, reroute/policy scoring, and supervised cost-to-go labels.

Core state must not store accelerator-native arrays. Optional backends are
explicit and fail closed; only `auto` may fall back to baseline.

## Evidence And Admission Rules

- Static `hardware-fit-atlas` labels are planning evidence, not performance
  proof.
- Runtime stage timing is diagnostic unless linked to a decision card and
  deterministic replay evidence.
- Smoke artifacts are not validation evidence.
- A backend PR must include:
  - a decision card from the latest hardware-fit atlas;
  - a measured probe that can falsify the chosen backend;
  - replay or parity tests proving baseline behavior is preserved;
  - fallback metadata for optional backend failure;
  - copy-boundary, compile-time, and steady-state timing where applicable.
- GPU/NN work is admitted only when it targets scoring, dense numeric batches,
  or supervised labels. Deterministic state mutation must stay Python/Rust.

## Success Criteria

- `.venv/bin/python -m pytest -q` passes.
- `.venv/bin/python -m ruff check .` passes.
- `git diff --check` is clean.
- Replay determinism and cache invalidation contracts remain intact.
- Runtime default remains baseline unless a separate promotion PR proves parity,
  fallback, and no material regression.
- GPU/NN experiment surfaces record labels, model/version/fallback metadata,
  first-call compile time, steady-state time, and deterministic fallback.

## Controlling Documents

- `docs/harness/RUNTIME_ACCELERATION_DECISION_GUARDRAILS.md`
- `artifacts/runtime_spine_review/hardware-fit-atlas.md`
- `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`
- `docs/harness/PROJECT_STATE.md`
- `docs/harness/DECISION_LOG.md`
- `docs/harness/DEPRECATED_IDEAS.md`
- `docs/VALIDATION_BENCHMARK_PLAN.md`
- `docs/harness/ACCELERATION_PR_LIST.md`
