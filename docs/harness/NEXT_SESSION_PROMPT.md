# Next Session Prompt

Continue in `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo` on
branch `008-routing-runtime-integration`.

Read these first:

1. `AGENTS.md`
2. `docs/harness/RUNTIME_ACCELERATION_DECISION_GUARDRAILS.md`
3. `docs/harness/PROJECT_STATE.md`
4. `docs/harness/DECISION_LOG.md`
5. `docs/harness/DEPRECATED_IDEAS.md`
6. `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`
7. `docs/VALIDATION_BENCHMARK_PLAN.md`

Current state:

- Python 3.12 + NumPy baseline remains authoritative.
- Rust CPU is optional and explicit/fail-closed.
- JAX/GPU and NN surrogate lanes are active watchlists, not defaults.
- Batched plugin-memory replacement reduced `active_agent_pool_write` below the
  review gate.
- `active_agent_candidate_selection` is not review-ready.
- `route_candidate_refresh` is the current dominant parent stage.
- `route_candidate_potential` / `dynamic_potential_recompute` is the current
  review-ready nested route stage.
- `route_candidate_path_build` fell below the review gate after fixing baseline
  dynamic-potential `float32` heap-staleness.
- Whole-runtime explicit `routing_backend="rust_cpu"` is slower than baseline
  on the 1-seed/1-step eager suite even with a release Rust extension, so Rust
  routing work must remain narrower than the whole routing backend.
- PR08 optional route surrogate harness is complete in `29daebe`.
- PR09 is complete; active-agent state layout implementation remains deferred by
  evidence, and pool-array replacement stays on the watchlist until it becomes
  review-ready.
- PR10 Zero-Copy/Rayon RFC is accepted without authorizing zero-copy NumPy FFI,
  Rayon, or new Rust build surface.
- PR11 C++/CUDA Admission RFC is complete in `55af343` without authorizing
  C++/CUDA, libtorch, CMake, or new runtime backend values.
- PR12 roadmap closure is complete; roadmap state, decision logs, validation
  docs, and handoff are consolidated.
- City-map PR33-PR40 are complete. `sidecar_local_fabric_planar` is explicit-only;
  `standard` remains default after the rejected performance/compatibility trial.
- The next city-quality work is morphology/block formation measured against the
  offline OSM reference adapter, not more renderer styling or unconditional
  planarization.

Next recommended workflow:

1. Open a new spec only after refreshing the hardware-fit atlas or runtime
   benchmark evidence that can change a parent-stage decision.
2. Keep four lanes visible: Rust/control-flow, NumPy/SIMD numeric, GPU tensor
   batch, and NN surrogate labels.
3. Treat smoke artifacts as diagnostics only; validation claims still require
   deterministic replay and invariant evidence.
4. Keep Python baseline route legality and deterministic replay authoritative.
5. Keep active-agent pool-array replacement and route path-build on the
   watchlist.
6. Do not add NN/JAX scoring until cost-to-go labels, compile-vs-run timing, and
   fallback semantics are defined.

Required self-check before coding:

```text
Question:
Evidence:
Inference:
Counterevidence checked:
Decision:
Falsifier:
Next action:
```

Required gates:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
```
