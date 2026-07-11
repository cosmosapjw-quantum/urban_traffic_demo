# Validation Ledger

## 2026-07-10: Explicit Planar City Contract Closure

Change class: topology/geometry validation plus diagnostic visualization

Commands and gates:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
google-chrome --headless=new --disable-gpu --hide-scrollbars \
  --window-size=1440,1100 --screenshot=<variant>.png file:///tmp/metroflow-pr40/<variant>.html
```

Observed results:

- final full suite: `426 passed` in about `136.7 s`
- focused planar/closure/geometry suite: `23 passed` in about `88.7 s`
- Ruff and whitespace gates passed
- explicit planar seed 44: `2665 -> 0` proper same-layer crossings
- sampled OD reachability: `32 / 32`
- diagnostic initialization wall time in manifest: about `5.24 s`
- trial default promotion was rejected after a `48 s -> 281 s` full-suite
  regression and a route-ID compatibility failure

Tracked diagnostic bundle:

- `artifacts/static_city_map_planar_review_20260710/full.png`
- `artifacts/static_city_map_planar_review_20260710/focused.png`
- `artifacts/static_city_map_planar_review_20260710/roads.png`
- `artifacts/static_city_map_planar_review_20260710/zones.png`
- `artifacts/static_city_map_planar_review_20260710/pois.png`
- `artifacts/static_city_map_planar_review_20260710/manifest.json`
- `artifacts/static_city_map_planar_review_20260710/visual_audit.md`

Claim boundary:

- **VALIDATED CONTRACT:** explicit planar mode has complete typed assignments,
  endpoint anchors, no proper same-layer crossings, deterministic sampled OD
  reachability, and replay parity in the tested seed matrix.
- **DIAGNOSTIC ONLY:** PNG appearance and initialization timing.
- **NOT VALIDATED:** real-world morphology, lane-level behavior, geographic
  correspondence, or suitability as the default runtime topology.

Decision: keep `standard` as the runtime default. Require explicit
`sidecar_local_fabric_planar` until morphology, initialization budget, and route
identifier compatibility are addressed in separate evidence-gated work.

## 2026-07-10: Static City Map Diagnostic Review

Change class: plotting/reporting diagnostic artifact

Commands run for this ledger entry:

```bash
.venv/bin/python -m pytest tests/test_static_city_map.py tests/test_city_connectivity.py -q
google-chrome --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
  --run-all-compositor-stages-before-draw --virtual-time-budget=1000 \
  --window-size=1280,1120 \
  --screenshot=artifacts/static_city_map_review_20260710/static_city_map_full_extent_page.png \
  file://$PWD/artifacts/static_city_map_review_20260710/static_city_map_full_extent.html
google-chrome --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
  --run-all-compositor-stages-before-draw --virtual-time-budget=1000 \
  --window-size=1280,1120 \
  --screenshot=artifacts/static_city_map_review_20260710/static_city_map_largest_component_page.png \
  file://$PWD/artifacts/static_city_map_review_20260710/static_city_map_largest_component.html
convert artifacts/static_city_map_review_20260710/static_city_map_full_extent_page.png \
  -crop 1220x766+30+193 +repage \
  artifacts/static_city_map_review_20260710/static_city_map_full_extent_map_only.png
git diff --check
```

Observed results:

- static-map/connectivity tests: `7 passed`
- Chrome PNG render succeeded for full extent and largest-component HTML
- ImageMagick crop succeeded for map-only PNG
- Image smoke metrics were nonblank:
  - full page: `1280x1120`, `16025` unique colors, nonwhite fraction `0.312464`
  - map-only crop: `1220x766`, `13405` unique colors, nonwhite fraction `0.124470`
  - largest-component page: `1280x1120`, `16025` unique colors, nonwhite fraction `0.312464`

Diagnostic artifacts added:

- `artifacts/static_city_map_review_20260710/static_city_map_full_extent.html`
- `artifacts/static_city_map_review_20260710/static_city_map_largest_component.html`
- `artifacts/static_city_map_review_20260710/static_city_map_full_extent_page.png`
- `artifacts/static_city_map_review_20260710/static_city_map_full_extent_map_only.png`
- `artifacts/static_city_map_review_20260710/static_city_map_largest_component_page.png`
- `artifacts/static_city_map_review_20260710/static_city_map_manifest.json`
- `artifacts/static_city_map_review_20260710/static_city_map_visual_audit.md`

Diagnostic interpretation:

- Seed `44` generated topology renders as one weak component after deterministic
  repair.
- Metadata still records pre-repair weak components with sizes `1121`, `3`,
  `3`, and `1`, and `6` repair links.
- POI overplotting remains the main visual audit limitation for local-road
  inspection.
- This is a smoke/diagnostic artifact, not validation evidence for dynamic
  traffic, route feasibility, lane-level correctness, or real-world geography.

Next validation required:

- Add layer-isolated roads-only, zones-only, and POIs-only static PNGs before
  using the map for detailed local-connectivity review.

## 2026-07-09: Runtime Acceleration Guardrails

Change class: documentation / planning governance / review control

Commands run for this ledger entry:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
```

Observed results:

- `282 passed`
- `ruff check .` passed
- `git diff --check` clean

Benchmark evidence referenced:

- `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`
- `artifacts/runtime_spine_review/runtime-suite-eager-smoke.json`
- `artifacts/runtime_spine_review/runtime-suite-eager-smoke.manifest.json`

Review evidence added:

- `artifacts/runtime_spine_review/runtime-acceleration-guardrails-review.md`

Validation interpretation:

- These smoke benchmark artifacts are diagnostic evidence only.
- They are not publication evidence, scientific validation, or authorization for
  GPU/CUDA/NN runtime defaults.
- Deterministic baseline replay remains authoritative.

Next validation required:

- Run targeted tests after adding the pool-write sub-breakdown.
- Re-run `.venv/bin/python -m pytest -q`, `.venv/bin/python -m ruff check .`,
  and `git diff --check` before committing implementation changes.

## 2026-07-09: Active-Agent Pool-Write Sub-Breakdown

Change class: runtime telemetry / benchmark reporting / diagnostic artifact

Commands run for this ledger entry:

```bash
.venv/bin/python -m pytest tests/test_runtime_spine.py::test_simulation_step_accumulates_runtime_stage_timing_totals tests/test_runtime_spine.py::test_active_agent_allocation_records_selected_candidate_metadata -q
.venv/bin/python -m pytest tests/test_measured_benchmarks.py::test_measured_runtime_benchmark_reports_nested_route_and_agent_stage_shares tests/test_metro_absorption_benchmarks_plugins.py::test_runtime_acceleration_candidate_report_profiles_nested_stage_fits -q
.venv/bin/python -m pytest tests/test_active_agent_rust_backend.py -q
.venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager --runtime-suite-seeds 41,42,43 --runtime-suite-steps 1 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-smoke
.venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager-2step --runtime-suite-seeds 41,42,43 --runtime-suite-steps 2 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-2step-smoke
.venv/bin/python -m ruff check .
git diff --check
.venv/bin/python -m pytest -q
```

Observed results:

- targeted runtime tests: `2 passed`
- targeted benchmark/reporting tests: `2 passed`
- active-agent Rust parity tests: `6 passed`
- 1-step eager benchmark suite regenerated
- 2-step eager benchmark suite generated
- `ruff check .` passed
- `git diff --check` clean
- full test suite: `282 passed`

Diagnostic artifacts updated or added:

- `artifacts/runtime_spine_review/runtime-suite-eager-smoke.{json,md,html,manifest.json}`
- `artifacts/runtime_spine_review/runtime-suite-eager-2step-smoke.{json,md,html,manifest.json}`
- `artifacts/runtime_spine_review/runtime-pool-write-subbreakdown-review.md`
- `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`

Validation interpretation:

- `active_agent_pool_write` remains the review-ready active-agent parent stage.
- `active_agent_plugin_memory_write` is larger than
  `active_agent_pool_array_write`, but neither substage is independently
  review-ready.
- The next implementation slice is data-layout/metadata reduction, not
  immediate Rust array-write, JAX/GPU, or NN scoring.
- These benchmark artifacts remain smoke diagnostics, not validation evidence
  or default-backend authorization.

Next validation required:

- After metadata reduction, regenerate the same 1-step and 2-step eager suites
  and compare `active_agent_pool_write`,
  `active_agent_plugin_memory_write`, and `active_agent_pool_array_write`.

## 2026-07-09: Batched Active-Agent Plugin-Memory Replacement

Change class: runtime data-layout optimization / benchmark diagnostic update

Commands run for this ledger entry:

```bash
.venv/bin/python -m pytest tests/test_runtime_spine.py::test_active_agent_allocation_batches_plugin_memory_replacement -q
.venv/bin/python -m pytest tests/test_runtime_spine.py::test_active_agent_allocation_batches_plugin_memory_replacement tests/test_runtime_spine.py::test_active_agent_allocation_records_selected_candidate_metadata tests/test_runtime_spine.py::test_active_agent_allocation_applies_path_size_correction_when_configured -q
.venv/bin/python -m pytest tests/test_active_agent_rust_backend.py -q
.venv/bin/python -m pytest tests/test_measured_benchmarks.py::test_measured_runtime_benchmark_reports_nested_route_and_agent_stage_shares tests/test_runtime_diagnostics.py::test_runtime_diagnostic_rollout_captures_frames_route_cache_and_summary -q
.venv/bin/python -m pytest tests/test_runtime_spine.py -q
.venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager --runtime-suite-seeds 41,42,43 --runtime-suite-steps 1 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-smoke
.venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager-2step --runtime-suite-seeds 41,42,43 --runtime-suite-steps 2 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-2step-smoke
.venv/bin/python -m ruff check .
git diff --check
.venv/bin/python -m pytest -q
```

Observed results:

- RED check: expected failure before batching, `_replace_pool_plugin_memory`
  was called once per allocation.
- allocation targeted tests: `3 passed`
- active-agent Rust parity tests: `6 passed`
- runtime benchmark/diagnostic targeted tests: `2 passed`
- runtime spine tests: `30 passed`
- 1-step eager benchmark suite regenerated
- 2-step eager benchmark suite regenerated
- `ruff check .` passed
- `git diff --check` clean
- full test suite: `283 passed`

Diagnostic interpretation:

- `active_agent_pool_write` is now below the 0.30 review gate in both eager
  suites.
- `active_agent_plugin_memory_write` is near zero after batching.
- `route_candidate_path_build` is now review-ready in both eager suites.
- The next implementation slice moves to Rust CPU route path-build, not further
  active-agent pool-write work, JAX/GPU, or NN scoring.

Next validation required:

- Before route path-build Rust work, add RED parity tests around the smallest
  path-build boundary and keep Python baseline route legality authoritative.

## 2026-07-09: Baseline Dynamic-Potential Float32 Heap-Staleness Fix

Change class: routing correctness fix / acceleration decision reset

Commands run for this ledger entry:

```bash
.venv/bin/python -m pytest tests/test_metro_absorption_routing.py::test_generated_baseline_dynamic_potential_does_not_drop_float32_heap_updates -q
cargo fmt --all --check
CARGO_TARGET_DIR=/tmp/metroflow-cargo-target cargo test --workspace
CARGO_TARGET_DIR=/tmp/metroflow-cargo-target .venv/bin/python -m maturin develop --manifest-path crates/metroflow-rust/Cargo.toml
.venv/bin/python -m pytest tests/test_metro_absorption_routing.py::test_generated_baseline_dynamic_potential_does_not_drop_float32_heap_updates tests/test_metro_absorption_routing.py::test_advanced_dynamic_potential_prefers_less_congested_path -q
.venv/bin/python -m pytest tests/test_routing_rust_backend.py -q
/usr/bin/time -f 'elapsed=%E cpu=%P' timeout 90s .venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager-baseline-1seed-postfix --runtime-suite-seeds 41 --runtime-suite-steps 1 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-baseline-1seed-postfix-smoke
/usr/bin/time -f 'elapsed=%E cpu=%P' timeout 90s .venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager-rust-routing-1seed-postfix --runtime-suite-seeds 41 --runtime-suite-steps 1 --runtime-suite-eager-trip-generation --runtime-suite-routing-backend rust_cpu --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-rust-routing-1seed-postfix-smoke
CARGO_TARGET_DIR=/tmp/metroflow-cargo-target .venv/bin/python -m maturin develop --release --manifest-path crates/metroflow-rust/Cargo.toml
/usr/bin/time -f 'elapsed=%E cpu=%P' timeout 90s .venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager-rust-routing-1seed-release --runtime-suite-seeds 41 --runtime-suite-steps 1 --runtime-suite-eager-trip-generation --runtime-suite-routing-backend rust_cpu --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-rust-routing-1seed-release-smoke
.venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager --runtime-suite-seeds 41,42,43 --runtime-suite-steps 1 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-smoke
.venv/bin/python -m metroflow.benchmarks.run --runtime-suite --runtime-suite-workload smoke-runtime-suite-eager-2step --runtime-suite-seeds 41,42,43 --runtime-suite-steps 2 --runtime-suite-eager-trip-generation --runtime-suite-artifact-prefix artifacts/runtime_spine_review/runtime-suite-eager-2step-smoke
```

Observed results:

- RED check: generated seed `41` baseline route `422 -> 8` produced no route
  before the fix.
- targeted generated-OD routing regression: `1 failed` before the fix, then
  `2 passed` with the adjacent baseline routing test after the fix.
- Rust gates: `cargo fmt --all --check` passed; `cargo test --workspace`
  reported `52 passed`.
- maturin rebuild succeeded for CPython 3.12.
- Rust routing Python parity suite: `22 passed`.
- baseline 1-seed/1-step eager suite completed in `elapsed=0:08.02`.
- explicit Rust routing 1-seed/1-step eager suite timed out at `90s` with the
  debug extension.
- release Rust extension rebuild succeeded.
- explicit Rust routing 1-seed/1-step eager suite completed in
  `elapsed=0:26.70` with the release extension; route potential fell to
  `0.019283` share, but path-build and metadata rose to `0.424858` and
  `0.497658`.
- regenerated 3-seed 1-step eager suite: `route_candidate_potential`
  mean share `0.537567`; `route_candidate_path_build` mean share `0.244385`.
- regenerated 3-seed 2-step eager suite: `route_candidate_potential`
  mean share `0.509388`; `route_candidate_path_build` mean share `0.231000`.

Diagnostic interpretation:

- Previous route path-build review-readiness was caused by a baseline
  correctness bug that made reachable ODs appear unreachable.
- The current route acceleration target is dynamic-potential recompute/cache
  amortization, not path-build.
- Runtime-wide explicit Rust routing remains deferred until path-build/metadata
  copy-boundary costs are amortized or bypassed with a narrower potential-only
  contract.

Next validation required:

- Add generated-OD dynamic-potential cache/recompute microbenchmarks and compare
  Python baseline vs Rust potential without enabling runtime-wide Rust routing.

## 2026-07-10: Urban Morphology Diversity Substrate

Change class: generated-city morphology contract and diagnostic validation

Commands run:

```bash
.venv/bin/python -m pytest tests/test_city_morphology_diversity.py tests/test_city_planarization.py tests/test_city_map_validation_closure.py -q
.venv/bin/python -m pytest tests/test_metro_absorption_city_generator.py tests/test_centerline_topology_compiler.py tests/test_static_city_map.py tests/test_metro_absorption_sim_init_step.py tests/test_replay.py -q
.venv/bin/python -m metroflow.ui.morphology_atlas --output-dir artifacts/city_morphology_atlas_20260710 --seed 17
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
```

Observed results:

- feature test suite: `13 passed`
- planar/closure review suite: `21 passed`
- init/replay/static compatibility suite: `39 passed`
- full suite: `439 passed in 68.95s`
- Ruff and diff checks passed
- all six explicit planar styles have one weak component, zero remaining
  proper same-layer crossings, and passing sampled-OD validation
- orientation-order spans `0.103–0.853`; dead-end share spans `0.022–0.323`

Claim boundary:

- Graph integrity and deterministic style separation are validated.
- The atlas is diagnostic and does not validate named-city replication or full
  urban realism.
- PR42 must address block continuity, district street density,
  connector/local length ratios, and intersection-mix distributions.

## 2026-07-11: Block Continuity And Density Envelope

Change class: generated-city structural metric, narrow admission gate, and
evidence-backed local-fabric repair

Commands run:

```bash
.venv/bin/python -m pytest tests/test_city_morphology_quality.py tests/test_city_morphology_diversity.py tests/test_static_city_map.py -q
.venv/bin/python -m metroflow.ui.morphology_atlas --output-dir artifacts/city_morphology_atlas_20260711 --seed 17
.venv/bin/python -m metroflow.ui.morphology_quality_report --output-dir artifacts/city_morphology_quality_20260711 --seeds 17,29,41
/usr/bin/time -f 'elapsed=%E cpu=%P maxrss_kb=%M' .venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
```

Observed results:

- targeted morphology/static suite: `49 passed`
- full suite: `472 passed in 125.08s`
- full-suite process: `elapsed=2:05.74`, `cpu=110%`,
  `maxrss_kb=1172748`
- Ruff and diff checks passed
- polycentric four-way median: `0.656 -> 0.603`
- mixed-grid four-way median: `0.630 -> 0.587`
- river dead-end median: `0.324 -> 0.119`
- river block-continuity median: `0.637 -> 0.882`
- independent re-review closed non-finite, connectivity, threshold-duplication,
  metric-naming, seed-matrix, and reporting-layer findings

Claim boundary:

- The versioned v1 gate validates weak connectivity, block continuity,
  convex-hull density, district quadrant presence, and intersection mix only.
- The PNG atlas remains diagnostic. It shows unresolved precinct islands and
  does not validate continuous citywide fabric or named-city replication.
- Zone/POI morphology coupling remains blocked until PR43 global spatial
  coverage and continuous-fabric work passes.

## 2026-07-11: Continuous Fabric Coverage

Change class: global local-fabric metrics, style-aware infill, and structural
gate v2

Commands run:

```bash
.venv/bin/python -m pytest tests/test_city_continuous_fabric.py tests/test_city_morphology_quality.py tests/test_city_morphology_diversity.py tests/test_city_planarization.py tests/test_city_map_validation_closure.py tests/test_static_city_map.py -q
.venv/bin/python -m metroflow.ui.morphology_atlas --output-dir artifacts/city_continuous_fabric_20260711 --seed 17
.venv/bin/python -m metroflow.ui.morphology_quality_report --output-dir artifacts/city_continuous_fabric_quality_20260711 --seeds 17,29,41
/usr/bin/time -f 'elapsed=%E cpu=%P maxrss_kb=%M' .venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
```

Observed results:

- targeted city suite: `67 passed in 83.02s`
- full suite: `479 passed in 134.19s`
- full-suite process: `elapsed=2:14.81`, `cpu=111%`,
  `maxrss_kb=1173412`
- Ruff and diff checks passed
- three-seed median local cell presence:
  `ring 0.172 -> 0.618`, `grid 0.309 -> 0.759`,
  `polycentric 0.338 -> 0.483`, `river 0.342 -> 0.625`,
  `mixed 0.267 -> 0.615`, `organic 0.152 -> 0.491`
- final three-seed junction-proximity minima range from `0.421` to `0.958`
- integrated river test: zero local-road/barrier crossings; intentional bridge
  crossings remain
- independent re-review closed all four initial findings

Claim boundary:

- Gate v2 is a project-owned synthetic regression gate, not empirical city
  validation.
- Presence-only admission was rejected after visual Goodhart evidence; exact
  raster parameters and junction proximity are part of the versioned contract.
- The final atlas is still schematic and does not model parcels, buildings,
  terrain, or morphology-aware land use.
- PR44 may open zone/POI coupling only with legacy default/fallback and replay
  fingerprint coverage.

## 2026-07-11: JAX Graph Cost-To-Go Diagnostic

Change class: optional GPU experiment, graph-vs-row-local numerical comparison,
and diagnostic artifact reporting

Commands run:

```bash
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
XLA_PYTHON_CLIENT_MEM_FRACTION=0.70 .venv/bin/python -m metroflow.benchmarks.jax_graph_cost_to_go_bakeoff --output-dir /tmp/metroflow-pr51-rerun.WRKG0l
.venv/bin/python -m pytest tests/test_jax_graph_cost_to_go_bakeoff.py tests/test_runtime_environment.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
```

Observed results:

- hardware: NVIDIA GeForce RTX 3080 Ti, 12,288 MiB, driver `595.71.05`
- optional stack: JAX `0.10.2`, Optax `0.2.8`, GPU platform selected
- canonical workload: 72 graphs, 48 train, 24 held-out-map validation
- graph/control normalized-MAE ratios: `1.0305`, `1.1823`, `0.9615`
- mean ratio: `1.0581`; fixed `<=0.90` seed gate: `0/3`
- repeat maximum prediction difference: `0.16173`; determinism gate failed
- 144 unique map/state/distance/model/seed slices reconstruct top-level metrics
- targeted PR51/runtime-environment suite: `15 passed`
- full suite: `570 passed in 155.34s`
- full-suite process: `elapsed=2:36.12`, `cpu=117%`, `maxrss_kb=1324980`
- Ruff and diff checks passed; three review perspectives report no findings

Numerical impact:

- No runtime state, route legality, replay authority, or backend default changed.
- The formal diagnostic state is `inconclusive` because repeat determinism
  fails. The accuracy gate fails independently, so deterministic-kernel work
  cannot admit this fixed graph model.
- Parameter/optimizer/device setup is synchronized before first-step timing;
  distance slices and top-level error aggregates are fail-closed.

Reproducibility and claim boundary:

- Architecture, seeds, epochs, and thresholds are author-attested as fixed in
  the working tree before the canonical run; there is no independent versioned
  preregistration record.
- The bundle at `artifacts/jax_graph_cost_to_go_bakeoff_20260711/` is diagnostic
  only and persists no labels, tensors, predictions, optimizer state, or model
  parameters.
- Baseline Dijkstra remains label and route-legality authority. PR51 does not
  validate real-city behavior or authorize a runtime NN backend.

Next validation required:

- PR52 requires an owner-selected step-back among Rust/control-flow,
  NumPy/SIMD numeric, JAX dense-flow checkpoint cadence, and a future narrow
  custom-kernel lane. Do not tune the failed PR51 graph hypothesis.
