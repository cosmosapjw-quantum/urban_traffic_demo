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
  hot path, while `active_agent_candidate_selection` is not review-ready.

Next recommended slice:

1. Split `active_agent_pool_write` into typed-array pool replacement timing and
   plugin-memory dict update timing.
2. Re-run eager runtime suite for seeds `41,42,43`.
3. If plugin-memory dict update dominates, reduce selected-candidate metadata
   writes or move hot metadata into typed arrays.
4. If typed-array pool replacement dominates, consider Rust/typed-array write
   planning.
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
