# Next Session Prompt

Continue in `/home/cosmosapjw/Dropbox/personal_projects/urban_traffic_demo` on
branch `codex/runtime-closure-remediation`.

Read these first:

1. `AGENTS.md`
2. `docs/PRD_REALISTIC_SYNTHETIC_CITY.md`
3. `docs/harness/REALISTIC_CITY_DEFAULT_PROMOTION_DECISION.md`
4. `docs/harness/PROJECT_STATE.md`
5. `docs/harness/DECISION_LOG.md`
6. `docs/harness/CLAIM_LEDGER.md`
7. `docs/harness/DEPRECATED_IDEAS.md`
8. `docs/harness/RUNTIME_ACCELERATION_DECISION_GUARDRAILS.md`
9. `docs/VALIDATION_BENCHMARK_PLAN.md`
10. `artifacts/runtime_spine_review/realistic-city-pr62-plausibility.md`
11. `artifacts/runtime_spine_review/realistic-city-pr63-scale.md`

Current state:

- Python 3.12 + NumPy remains authoritative. Rust CPU and JAX/GPU are optional,
  explicit, and fail-closed; no C++/CUDA backend is admitted.
- PR53-PR60 implement the explicit `realistic_synthetic_v1` terrain-to-runtime
  city pipeline. `standard` remains the default.
- PR61 implements explicit `spatial_queue_v1` physical link residency, finite
  storage, and deterministic spillback. It is substrate, not calibrated traffic.
- PR62 generated all 30 fixed maps but passes `0/30`. Every map fails mean
  degree and dead-end plausibility; seven also fail the 800 m branch-free gate.
- PR63 completed 42 fresh-process scale runs. At 100k, all seeds fail generation
  wall, actual population realization, and paired throughput. RSS and fixed
  20-tick latency ratios pass. No Rust generation stage is admitted.
- PR64 is closed as `BLOCKED`. Both canonical fingerprints validate, the default
  is unchanged, and no feature promotion commit exists.
- `SimulationState` still lacks the legacy accessibility and land-use cadences;
  do not describe the runtime as a closed LUTI loop.

Next specification:

1. Step back across terrain/growth, street topology, land use/capacity, and
   simulation physics before editing.
2. Replace the repeated triangular local fabric with a continuous hierarchy
   that increases legitimate T-junction/dead-end diversity and collector share.
3. Make terrain/barrier response and block-size distribution materially affect
   topology rather than only rendering.
4. Fix block/home/POI capacity so each requested population is actually
   realized, including 1k, 10k, and 100k.
5. Preserve no-repair connectivity, planar intersections, section/turn/CSR
   coverage, 512 sampled OD reachability, replay fingerprints, and explicit
   units.
6. Rerun PR62 before PR63. Do not reopen Rust, GPU, NN, or default promotion
   until the unchanged evidence gates pass or a new falsifiable spec replaces
   them.

Required compact review record:

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
