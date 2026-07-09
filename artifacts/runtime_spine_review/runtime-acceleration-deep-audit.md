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
| route_candidate_refresh | 0.825024 | 0.781313 | eligible both runs |
| route_candidate_potential | 0.537567 | 0.509388 | eligible both runs |
| dynamic_potential_recompute | 0.534764 | 0.506721 | nested dominant |
| route_candidate_path_build | 0.244385 | 0.231000 | below 0.30 |
| route_candidate_metadata | 0.023590 | 0.023508 | below 0.30 |
| active_agent_update | 0.111696 | 0.107321 | below 0.30 |
| active_agent_allocation | 0.109135 | 0.099651 | below 0.30 |
| active_agent_candidate_selection | 0.022911 | 0.021113 | below 0.30 |
| active_agent_pool_write | 0.081766 | 0.073582 | below 0.30 |
| active_agent_pool_array_write | 0.076819 | 0.069100 | below 0.30 |
| active_agent_plugin_memory_write | 0.002240 | 0.002039 | below 0.30 |
| active_agent_movement | 0.001718 | 0.006077 | below 0.30 |

## Findings

1. Batched plugin-memory replacement removed the active-agent pool-write stage
   from the review-ready set. `active_agent_plugin_memory_write` is now near
   zero in both eager suites.
2. `active_agent_pool_array_write` remains visible but sub-threshold; it should
   stay on the Rust CPU watchlist rather than driving the next slice.
3. NN/JAX route-choice scoring is still not the immediate bottleneck in this
   workload. `active_agent_candidate_selection` remains near 2 percent.
4. Route refresh is now the dominant review-ready parent stage, and
   `route_candidate_potential` is the review-ready nested stage in both suites.
5. The previous path-build recommendation was a false local minimum caused by a
   Python baseline Dijkstra `float32` heap-staleness bug. After fixing that
   baseline correctness issue, `route_candidate_path_build` is below the 0.30
   review gate.
6. Explicit whole-runtime `routing_backend="rust_cpu"` remains blocked for
   default/runtime activation: release Rust completed the 1-seed/1-step eager
   suite in `26.70s` versus `8.02s` for baseline, with cost shifted into
   path-build and metadata copy-boundary work. Rust routing should be compared
   as a narrow dynamic-potential/core slice before runtime-wide activation.

## Next Slice Recommendation

Proceed with dynamic-potential recompute and cache-amortization work before a
path-build, JAX, or NN implementation slice:

- keep active-agent pool-array replacement as a Rust CPU watchlist;
- preserve deterministic baseline route legality and replay authority;
- compare Rust CPU dynamic-potential on generated OD workloads before enabling
  runtime-wide Rust routing;
- keep route-candidate path-build and metadata timings in the benchmark gate;
- only open NN/JAX cost-to-go or scoring experiments once labels, compile-vs-run
  timing, and fallback semantics are defined.
