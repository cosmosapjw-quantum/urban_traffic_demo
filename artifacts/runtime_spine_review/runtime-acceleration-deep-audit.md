# Runtime Acceleration Deep Audit

Date: 2026-07-09

This is a smoke diagnostic artifact for backend/NN triage. It is not a validation
claim and does not authorize CUDA, libtorch, or NN runtime defaults.

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
  --runtime-suite-eager-trip-generation
```

## Evidence

| stage | 1-step mean share | 2-step mean share | gate status |
|---|---:|---:|---|
| route_candidate_refresh | 0.496430 | 0.465788 | eligible both runs |
| route_candidate_potential | 0.198407 | 0.183364 | below 0.30 |
| route_candidate_path_build | 0.251846 | 0.238289 | below 0.30 |
| route_candidate_metadata | 0.027139 | 0.024714 | below 0.30 |
| active_agent_update | 0.426526 | 0.403433 | eligible both runs |
| active_agent_allocation | 0.423402 | 0.391733 | eligible both runs |
| active_agent_candidate_selection | 0.034726 | 0.034645 | below 0.30 |
| active_agent_pool_write | 0.380415 | 0.348166 | eligible both runs |
| active_agent_movement | 0.002045 | 0.009464 | below 0.30 |

## Findings

1. Active-agent cost is not movement and not route-choice scoring. The dominant
   nested stage is `active_agent_pool_write`, so the next active-agent slice
   should target Python immutable pool/plugin-memory writes, likely with a
   tighter typed-array data path or Rust allocation/write planning.
2. NN/JAX route-choice scoring is not the immediate bottleneck in this workload.
   `active_agent_candidate_selection` stays near 3.5 percent in both runs.
3. Route refresh remains a major candidate, but it splits into two sub-threshold
   graph workloads: `route_candidate_path_build` and `route_candidate_potential`.
   This argues for Rust/algorithmic route-core work before GPU kernels.
4. NN remains relevant as a supervised surrogate surface for route cost-to-go
   and route scoring labels, but it should not replace deterministic routing
   authority or be treated as the next runtime hot-path fix.

## Next Slice Recommendation

Proceed with a CPU/Rust data-layout slice before a JAX/NN implementation slice:

- split active-agent pool write into typed-array replacement vs plugin-memory dict update;
- reduce or remove dict-heavy plugin-memory writes for selected candidate metadata;
- keep route-candidate path-build/potential timings in the benchmark gate;
- only open NN/JAX scoring once labels and stage shares show scoring, not state writes,
  is the limiting factor.
