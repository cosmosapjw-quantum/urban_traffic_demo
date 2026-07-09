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
- Deep runtime audit found `active_agent_pool_write` as the current active-agent
  parent hot path, while `active_agent_candidate_selection` is not review-ready.
- `active_agent_pool_write` has already been split into
  `active_agent_pool_array_write` and `active_agent_plugin_memory_write`.
- `active_agent_plugin_memory_write` is larger than array write, but below the
  standalone 0.30 review gate.

Next recommended slice:

1. Reduce selected-candidate metadata writes in per-slot plugin memory, or move
   hot fields into typed diagnostics while preserving replay/UI behavior.
2. Re-run eager runtime suite for seeds `41,42,43` at 1-step and 2-step.
3. If parent `active_agent_pool_write` falls below the review gate, move back to
   route candidate refresh/Rust graph-core planning.
4. If typed-array pool replacement becomes dominant, consider Rust/typed-array
   write planning.
5. Do not add NN/JAX scoring until a scoring stage becomes review-ready.

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
