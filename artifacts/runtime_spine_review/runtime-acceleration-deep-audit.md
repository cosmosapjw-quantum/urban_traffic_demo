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
| route_candidate_refresh | 0.699435 | 0.637416 | eligible both runs |
| route_candidate_potential | 0.279811 | 0.253102 | below 0.30 |
| route_candidate_path_build | 0.354543 | 0.324356 | eligible both runs |
| route_candidate_metadata | 0.038381 | 0.033308 | below 0.30 |
| active_agent_update | 0.192861 | 0.188055 | below 0.30 |
| active_agent_allocation | 0.188428 | 0.172839 | below 0.30 |
| active_agent_candidate_selection | 0.041488 | 0.039138 | below 0.30 |
| active_agent_pool_write | 0.137235 | 0.123834 | below 0.30 |
| active_agent_pool_array_write | 0.128320 | 0.115920 | below 0.30 |
| active_agent_plugin_memory_write | 0.004017 | 0.003606 | below 0.30 |
| active_agent_movement | 0.002945 | 0.012519 | below 0.30 |

## Findings

1. Batched plugin-memory replacement removed the active-agent pool-write stage
   from the review-ready set. `active_agent_plugin_memory_write` is now near
   zero in both eager suites.
2. `active_agent_pool_array_write` remains visible but sub-threshold; it should
   stay on the Rust CPU watchlist rather than driving the next slice.
3. NN/JAX route-choice scoring is still not the immediate bottleneck in this
   workload. `active_agent_candidate_selection` remains near 4 percent.
4. Route refresh is now the dominant review-ready parent stage, and
   `route_candidate_path_build` is review-ready in both suites.
5. The next backend migration should target Rust/algorithmic route path-building
   before GPU kernels. NN remains relevant only as a supervised route scoring or
   cost-to-go research lane after labels and stage shares justify it.

## Next Slice Recommendation

Proceed with a Rust CPU route path-build slice before a JAX/NN implementation slice:

- keep active-agent pool-array replacement as a Rust CPU watchlist;
- preserve deterministic baseline route legality and replay authority;
- keep route-candidate potential and metadata timings in the benchmark gate;
- only open NN/JAX scoring once labels and stage shares show scoring, not state writes,
  is the limiting factor.
