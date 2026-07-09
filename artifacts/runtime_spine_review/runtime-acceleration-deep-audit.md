# Runtime Acceleration Deep Audit

Date: 2026-07-09

This is a smoke diagnostic artifact for backend/NN triage. It is not a validation
claim and does not authorize CUDA, libtorch, or NN runtime defaults.

Decision guardrails for future work:
`docs/harness/RUNTIME_ACCELERATION_DECISION_GUARDRAILS.md`

## Commands

```bash
.venv/bin/python -m metroflow.benchmarks.run --runtime-suite \
  --runtime-suite-workload smoke-runtime-suite-eager \
  --runtime-suite-seeds 41,42,43 \
  --runtime-suite-steps 1 \
  --runtime-suite-eager-trip-generation \
  --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-smoke

.venv/bin/python -m metroflow.benchmarks.run --runtime-suite \
  --runtime-suite-workload smoke-runtime-suite-eager-2step \
  --runtime-suite-seeds 41,42,43 \
  --runtime-suite-steps 2 \
  --runtime-suite-eager-trip-generation \
  --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-2step-smoke
```

## Evidence

| stage | 1-step mean share | 2-step mean share | gate status |
|---|---:|---:|---|
| route_candidate_refresh | 0.491154 | 0.465925 | eligible both runs |
| route_candidate_potential | 0.197926 | 0.185767 | below 0.30 |
| route_candidate_path_build | 0.248170 | 0.236580 | below 0.30 |
| route_candidate_metadata | 0.026730 | 0.024097 | below 0.30 |
| active_agent_update | 0.432556 | 0.407347 | eligible both runs |
| active_agent_allocation | 0.429381 | 0.396307 | eligible both runs |
| active_agent_candidate_selection | 0.035368 | 0.033726 | below 0.30 |
| active_agent_pool_write | 0.386110 | 0.354578 | eligible both runs |
| active_agent_pool_array_write | 0.097621 | 0.089724 | below 0.30 |
| active_agent_plugin_memory_write | 0.283766 | 0.260598 | below 0.30 |
| active_agent_movement | 0.002056 | 0.009024 | below 0.30 |

## Findings

1. Active-agent cost is not movement and not route-choice scoring. The dominant
   nested stage is still `active_agent_pool_write`.
2. Inside pool write, `active_agent_plugin_memory_write` is much larger than
   `active_agent_pool_array_write`, but it does not clear the 0.30 review gate
   in either suite. This supports a narrow Python data-layout slice before Rust
   array-write planning.
3. NN/JAX route-choice scoring is not the immediate bottleneck in this workload.
   `active_agent_candidate_selection` stays near 3.5 percent in both runs.
4. Route refresh remains a major candidate, but it splits into two sub-threshold
   graph workloads: `route_candidate_path_build` and `route_candidate_potential`.
   This argues for Rust/algorithmic route-core work before GPU kernels.
5. NN remains relevant as a supervised surrogate surface for route cost-to-go
   and route scoring labels, but it should not replace deterministic routing
   authority or be treated as the next runtime hot-path fix.

## Next Slice Recommendation

Proceed with a Python data-layout slice before a Rust/JAX/NN implementation slice:

- reduce or remove dict-heavy plugin-memory writes for selected candidate metadata;
- keep typed-array pool replacement as a Rust CPU watchlist, not the next patch;
- keep route-candidate path-build/potential timings in the benchmark gate;
- only open NN/JAX scoring once labels and stage shares show scoring, not state writes,
  is the limiting factor.
