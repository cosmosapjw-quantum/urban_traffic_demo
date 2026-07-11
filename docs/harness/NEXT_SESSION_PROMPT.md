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
8. `docs/harness/CLAIM_LEDGER.md`
9. `docs/audit/metroflow_external_audit_20260711/README.md`

Current state:

- The external audit found a critical functional blocker before PR52:
  generated networks/initialization provide no route-derived turn demand, so
  eager active agents fill source queues but do not move.
- `SimulationState` also lacks the legacy accessibility/land-use multirate
  cadences; do not describe the runtime as a closed LUTI loop.
- Python 3.12 + NumPy baseline remains authoritative.
- Rust CPU is optional and explicit/fail-closed.
- JAX/GPU remains an active watchlist, not a default. PR49 and PR51 close the
  current row-local and fixed graph cost-to-go NN hypotheses without tuning.
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
- PR49 audits 64,968 deterministic simulator rows and rejects a row-local MLP
  because the fixed relation gate fails.
- PR50 freezes immutable directed graph tensors and exact map-holdout
  provenance without accelerator imports.
- PR51's fixed JAX/Optax graph bakeoff misses its accuracy gate independently
  of repeat nondeterminism. It does not authorize a runtime NN backend.
- PR52's owner-selected acceleration lane is blocked until runtime closure.

Next recommended workflow:

1. Open a runtime-closure spec for typed turn movements, route-tail demand
   assembly, generated multi-hop movement/completion, vehicle conservation, and
   a canonical full dynamic-state replay digest.
2. Port or explicitly retire the legacy medium/slow accessibility and land-use
   cadences before describing `SimulationState` as an integrated LUTI runtime.
3. Keep Python/NumPy baseline route legality and replay authoritative; do not
   use Rust, GPU, or NN work to mask missing baseline behavior.
4. After closure, refresh the hardware-fit atlas on the functional workload and
   keep Rust/control-flow, NumPy/SIMD, GPU tensor, and custom-kernel lanes
   distinct.
5. Preserve failed NN results as stop evidence. A different hypothesis requires
   a future owner-authorized spec and new falsifier.

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

Treat PR52 as blocked until the runtime-closure gate is green.

Required gates:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
```
