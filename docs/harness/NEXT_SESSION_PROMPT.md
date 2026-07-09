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
- `route_candidate_path_build` is review-ready in both 1-step and 2-step eager
  suites.

Next recommended slice:

1. Open a narrow Rust CPU route path-build slice or first split path-build if
   needed to keep the Rust contract small.
2. Keep Python baseline route legality authoritative.
3. Re-run eager runtime suite for seeds `41,42,43` at 1-step and 2-step after
   the route path-build change.
4. Keep active-agent pool-array replacement on the watchlist.
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
