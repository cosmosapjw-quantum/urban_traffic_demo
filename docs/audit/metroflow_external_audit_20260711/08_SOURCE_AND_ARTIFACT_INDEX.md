# Source And Artifact Index

## Source Scale At Audit Baseline

| Inventory | Count / size |
|---|---:|
| Git commits | 120 |
| Recorded authors | 1 |
| Python source files | 127 |
| Rust source files | 7 |
| Python test files | 56 |
| Python `test_*` functions | 508 |
| Python + test lines | about 63,835 |
| Rust lines | about 2,689 |
| Tracked artifact files | 99 |
| Ignored artifact files present on audit host | 36 |
| Total artifact files present on audit host | 135 |

Counts are snapshot diagnostics and may change in the documentation commit.
The generated package metadata records the exact packaged revision inventory.

## Primary Runtime Entry Points

- `src/metroflow/sim/init.py` - integrated runtime construction
- `src/metroflow/sim/step.py` - integrated fast-tick spine
- `src/metroflow/sim/state.py` - runtime aggregate and refs
- `src/metroflow/sim/orchestrator.py` - legacy multirate runtime
- `src/metroflow/core/state.py` - legacy frozen `WorldState`
- `src/metroflow/sim/replay.py` - replay boundary and sequence

## Traffic And Routing

- `src/metroflow/flow/state.py` - NumPy link/node state
- `src/metroflow/flow/engine.py` - authoritative turn-flow arrays
- `src/metroflow/traffic/meso.py` - legacy edge evolution
- `src/metroflow/routing/dynamic_potential.py` - reverse Dijkstra
- `src/metroflow/routing/candidates.py` - ranked K paths
- `src/metroflow/sim/routing_runtime.py` - cache, choice, reroute, agents
- `src/metroflow/sim/active_agents.py` - packed pool

## City, Map, Demand, And Land Use

- `src/metroflow/city/generator_v2.py` - current synthetic generator
- `src/metroflow/city/connectivity.py` - weak components and repair
- `src/metroflow/city/planarization.py` - explicit planar sidecar
- `src/metroflow/city/district_mesh.py` - local morphology mesh/biases
- `src/metroflow/map/` - centerline/section/node/OSM contracts
- `src/metroflow/demand/` - citizens, schedules, trips, accessibility
- `src/metroflow/landuse/evolution.py` - lagged legacy update

## Acceleration And Experiments

- `src/metroflow/backends/rust_cpu.py` - lazy PyO3 facade
- `crates/metroflow-rust/src/` - Rust modules and PyO3 exports
- `src/metroflow/backends/jax_flow.py` - optional dense flow
- `src/metroflow/benchmarks/gpu_flow_bakeoff.py` - PR47 experiment
- `src/metroflow/learning/cost_to_go_features.py` - PR48 features
- `src/metroflow/learning/cost_to_go_graph_tensors.py` - PR50 graph contract
- `src/metroflow/benchmarks/jax_graph_cost_to_go_bakeoff.py` - PR51
- `src/metroflow/benchmarks/hardware_atlas.py` - static hardware-fit atlas

## Governance And Evidence

- `AGENTS.md` - active engineering constraints
- `docs/harness/RUNTIME_ACCELERATION_DECISION_GUARDRAILS.md`
- `docs/harness/PROJECT_STATE.md`
- `docs/harness/DECISION_LOG.md`
- `docs/harness/DEPRECATED_IDEAS.md`
- `docs/harness/VALIDATION_LEDGER.md`
- `docs/harness/CLAIM_LEDGER.md`
- `docs/VALIDATION_BENCHMARK_PLAN.md`
- `docs/map/CITY_MAP_SOURCE_PROVENANCE.md`

## Canonical Diagnostic Artifacts

| Artifact | Purpose | Claim ceiling |
|---|---|---|
| `artifacts/runtime_spine_review/` | stage timing/atlas | diagnostic only |
| `artifacts/city_continuous_fabric_20260711/` | morphology images | visual smoke |
| `artifacts/city_continuous_fabric_quality_20260711/` | structural metrics | synthetic regression |
| `artifacts/city_landuse_accessibility_20260711/` | access metrics | synthetic reachability |
| `artifacts/gpu_dense_flow_bakeoff_20260711/` | frozen JAX flow | microbenchmark |
| `artifacts/cost_to_go_feature_audit_20260711/` | row-local audit | feature diagnosis |
| `artifacts/jax_graph_cost_to_go_bakeoff_20260711/` | graph/control test | failed diagnostic |

Large HTML and PNG files are included only when tracked by git. The audit ZIP
does not claim that every historical artifact is complete or independently
attested.

## Known Missing Or Stale Surfaces

- no root `LICENSE`, `COPYING`, or `NOTICE`;
- no `.github/workflows` CI;
- no Python or complete environment lock; Rust has tracked `Cargo.lock`;
- no retained pre-import/donor git ancestry;
- `city/gate_reporting.py` has lazy imports for nonexistent
  `metroflow.tools.analyze_city_map_image` and
  `metroflow.tools.track_city_map_history`;
- README/project description contained historical “starter skeleton” wording at
  source baseline `96e54ca`; the audit documentation commit corrects it;
- experiment manifests do not share one provenance schema.

## Git History Index

When built from the committed packet, the ZIP includes:

- `history/metroflow-all-refs.bundle` - all refs and reachable objects;
- `history/commit-history.tsv` - hash/date/author/subject;
- `history/refs.txt` - ref targets;
- `provenance/git-fsck.txt` - object-integrity command output;
- `provenance/tracked-files-sha256.json` - snapshot file hashes.

The bundle preserves the available history, not history that was never imported.
