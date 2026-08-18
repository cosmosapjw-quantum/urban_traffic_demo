# Validation Ledger

> **2026-08-08 — the image artifacts named below are no longer tracked.** All 44
> committed PNGs were deleted in preparation for the second external audit. Two
> reasons, and neither is that they were wrong. They were rendered by code that
> has since been substantially repaired, so a reviewer opening one would be
> looking at a generator that no longer exists — and the claim ledger forbids
> presenting image artifacts as scientific validation, which a file list headed
> "tracked diagnostic bundle" quietly does. The **measured** artifacts beside
> them (`.json`, `.md`, `.manifest.json`) are untouched, and every entry's
> reproduction commands still regenerate its screenshots on demand.
>
> The replacement gallery is `artifacts/external_audit_2_maps/`, rendered by
> `tools/render_audit_maps.py` from the current tree, captioned out of
> `morphology-control-table-v3-20260808.json`, and byte-reproducible via
> `--check`. It illustrates; it still measures nothing.

## 2026-07-13: Realistic City Plausibility Audit

Change class: fixed-corpus morphology audit, structural distribution gate, and
diagnostic contact-sheet review

Commands and gates:

```bash
.venv/bin/python -m pytest tests/test_realistic_city_plausibility.py -q
/usr/bin/time -f 'elapsed=%e max_rss_kb=%M' \
  .venv/bin/python -m metroflow.benchmarks.realistic_city_audit \
  --artifact-prefix artifacts/runtime_spine_review/realistic-city-pr62-plausibility
google-chrome --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
  --window-size=2400,3600 \
  --screenshot=artifacts/runtime_spine_review/realistic-city-pr62-plausibility.png \
  file://$PWD/artifacts/runtime_spine_review/realistic-city-pr62-plausibility.html
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
```

Observed results:

- audit unit/artifact suite: `8 passed in 13.56s`;
- canonical matrix: six registered styles x seeds `17,29,41,44,53`;
- all 30 maps generated; report fingerprint
  `6ab9f8c9c62f36aeedffd67707f2c3e9072274ca91f1e836dc14d69fcde3316b`;
- canonical audit: `0/30` maps passed, `144.26 s` wall time, `272,112 KiB`
  maximum RSS;
- full repository: `767 passed in 563.66s`;
- Ruff and whitespace gates passed;
- Chrome produced a nonblank `2400x3600` PNG contact sheet whose five layers
  align with the same representative generated maps.

Failure evidence:

- every map is outside the pinned 20-percent-expanded envelope on mean node
  degree and dead-end share;
- seven maps exceed the frozen 800 m developed branch-free corridor gate;
- independent `grid_core` seed-17 recount: 799 nodes, 2,147 physical edges,
  mean degree 5.374, 528 degree-six nodes, and only 29 parallel-edge extras;
- representative local-road length share is 95-98 percent while collector
  length share is zero;
- dominant 10 m segment bins hold 42-65 percent and dominant 2,500 m2 block
  bins hold roughly 70-95 percent, matching the repeated triangular lattice in
  the contact sheet.

Review corrections:

- split audit authority from reporting/CLI instead of retaining a new 1,084-line
  mixed-responsibility module;
- removed preview geometry from JSON, reducing it from 31 MB to 108 KB without
  changing the report fingerprint;
- added chain, junction, and cycle gold tests for the branch-free corridor gate;
- documented compiled-fragment circuity as 1.0 by construction rather than
  presenting it as realistic-curvature evidence.

Claim boundary:

- **IMPLEMENTED:** deterministic 30-map audit, fixed reference envelope,
  structural gates, compact artifacts, and aligned diagnostic contact sheet.
- **BLOCKED:** `realistic_synthetic_v1` default promotion and broad
  morphological-plausibility claim.
- **STILL VALID:** deterministic topology/CSR/zone/replay simulation-input
  substrate from PR60.
- **NOT VALIDATED:** named-city similarity, empirical traffic/demand/land-use,
  street curvature, or global representativeness of the eight-city corpus.

## 2026-07-13: Explicit Spatial Queue Runtime

Change class: runtime traffic semantics, finite-storage invariants, replay and
diagnostic provenance

Commands and gates:

```bash
.venv/bin/python -m pytest tests/test_spatial_queue_runtime.py -q
.venv/bin/python -m pytest \
  tests/test_spatial_queue_runtime.py tests/test_runtime_spine.py \
  tests/test_runtime_flow_closure.py tests/test_runtime_replay_closure.py \
  tests/test_measured_benchmarks.py tests/test_runtime_diagnostics.py \
  tests/test_metro_absorption_reporting_learning_ui.py \
  tests/test_static_city_map.py tests/test_runtime_environment.py \
  tests/test_imports.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
```

Observed results:

- spatial queue targeted suite: `12 passed in 1.49s`;
- related runtime/UI/backend suite: `135 passed in 46.69s`;
- full repository: `759 passed in 503.97s`;
- fresh `sim.config`, `sim.step`, and `traffic` import loaded no JAX, torch, or
  `_metroflow_rust` modules;
- Ruff and whitespace gates passed.

Functional impact:

- `point_queue_v1` remains the default replay/regression authority;
- explicit NumPy `spatial_queue_v1` advances resident agents from physical link
  length, free-flow speed, and tick duration, and only exit-ready agents submit
  turn or sink demand;
- storage is derived in vehicles as
  `floor(length_m * lanes / jam_spacing_m)` with a minimum of one vehicle;
- source admission and downstream receiving both fail closed when storage is
  exhausted, including deterministic competing-turn ordering;
- finite-storage shape, authority, and occupancy are independently checked by
  runtime invariants;
- telemetry, replay, UI snapshots/static metadata, and measured runtime
  benchmarks preserve `traffic_model` and deterministic spillback counters.

Review corrections:

- replaced an invalid source-full fixture whose queue had no corresponding
  agent with a lifecycle- and mass-consistent two-trip scenario;
- added missing telemetry serialization and benchmark/UI model provenance;
- stopped counting exit-wait agents as physically progressed on every tick;
- included physical-progress planning time in the parent active-agent stage.

Claim boundary:

- **INTERNALLY VERIFIED:** explicit coarse link residency, finite storage,
  deterministic spillback, exact queue/agent mass, pause, and replay in the
  exercised synthetic fixtures.
- **NOT VALIDATED:** empirical travel time, jam density, fundamental diagram,
  backward shockwave speed, lane behavior, real-city traffic, or 100k closure.
- No Rust, JAX, C++/CUDA, lane-level, or external-data-learning path was opened.

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

## 2026-07-11: PR47 JAX Dense-Flow Persistent Chunk

Change class: optional GPU microbenchmark; historical ledger closure

Canonical command:

```bash
XLA_PYTHON_CLIENT_MEM_FRACTION=.70 .venv/bin/python \
  -m metroflow.benchmarks.gpu_flow_bakeoff \
  --output-dir artifacts/gpu_dense_flow_bakeoff_20260711 \
  --link-counts 4096,16384,65536 --seeds 41,42,43 \
  --num-steps 512 --turns-per-link 3
```

Recorded result:

- 4,096 links: drift `0.0008612`, minimum warm/steady speedup
  `1.1247x` / `12.2843x`; pass.
- 16,384 links: drift `0.0008769`, minimum warm/steady speedup
  `4.2620x` / `37.7757x`; pass.
- 65,536 links: drift `0.0015769` above the fixed `0.001` gate; fail.
- Frozen 512-step device chunks do not measure per-tick host mutation,
  synchronization, checkpoint ownership, or runtime replay. No runtime backend
  is authorized.

Provenance limitation: the artifact predates the common audit-manifest schema
and has no independent attestation. A fresh reproduction must use a new output
directory and record commit, environment, command, and checksums.

## 2026-07-11: PR48 Cost-To-Go Feature Contract

Change class: NumPy experiment data contract; historical ledger closure

Canonical verification commands:

```bash
.venv/bin/python -m pytest tests/test_cost_to_go_features.py tests/test_runtime_environment.py -q
.venv/bin/python -m ruff check .
git diff --check
```

Recorded result and boundary:

- Versioned 20-column ID-free model matrix, independent static/dynamic
  fingerprints, baseline-Dijkstra targets, and target-independent group split
  are implemented.
- Final repository gate at that commit was `522 passed`.
- No model was fitted and no cross-network generalization or runtime NN backend
  was authorized.

## 2026-07-11: PR49 Multi-City Cost-To-Go Feature Audit

Change class: simulator-only feature identifiability diagnostic; historical
ledger closure

Canonical commands:

```bash
.venv/bin/python -m metroflow.learning.cost_to_go_audit \
  --output-dir artifacts/cost_to_go_feature_audit_20260711 \
  --style-ids grid_core,polycentric_tod,organic \
  --seeds 17,29,41 --destination-count 4 --closure-fraction 0.03
.venv/bin/python -m pytest tests/test_cost_to_go_feature_audit.py tests/test_cost_to_go_features.py -q
```

Recorded result and boundary:

- 64,968 rows retained; 90% nonconstant features; 99.889% joint dynamic
  response; 20.042% relation coverage.
- Near-duplicate target conflict is `8,994/13,021 = 69.073%`, above the fixed
  25% maximum. The row-local MLP hypothesis is rejected without threshold
  tuning.
- The artifact persists summaries, not raw rows or independent attestation.

## 2026-07-11: PR50 Cost-To-Go Graph Tensor Contract

Change class: NumPy directed graph data contract; historical ledger closure

Canonical verification commands:

```bash
.venv/bin/python -m pytest tests/test_cost_to_go_graph_tensors.py tests/test_cost_to_go_feature_audit.py -q
.venv/bin/python -m ruff check .
git diff --check
```

Recorded result and boundary:

- Directed local edge indices, 13 edge features, blocked mask, baseline node
  targets, byte-bounded padded batches, fingerprints, and static-network split
  are implemented.
- Recorded smoke: 861 nodes, 3,120 edges, 1,722 targets, 534,996 final bytes,
  1,069,992 estimated peak bytes; final repository gate `560 passed`.
- This validates a data contract only. It provides no accuracy, speed, or
  runtime-authority claim.

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

- The external whole-repository audit supersedes PR52 lane selection. Close
  typed turn authority, route-derived demand, generated multi-hop movement,
  vehicle conservation, and full-state replay before refreshing any
  acceleration evidence. Do not tune the failed PR51 graph hypothesis.

## 2026-07-11: Whole-Repository External Audit Packet

Change class: history/architecture/research audit, executable defect probe,
claim ledger, and integrity-checked external review packaging

Commands run:

```bash
.venv/bin/python -m metroflow.benchmarks.runtime_self_drive_probe \
  --scenario-seed 41 --steps 3 --expect-stalled
.venv/bin/python -m pytest tests/test_external_audit_package.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
cargo fmt --all --check
CARGO_TARGET_DIR=/tmp/metroflow-cargo-target cargo test --workspace
```

Observed results:

- defect probe: 16 initial trips; 15 active agents and 15 queued vehicles by
  tick 1; zero turn demand, outflow, and movement through tick 3;
- external-audit package tests: `8 passed`;
- full Python suite: `578 passed in 159.46s`;
- Ruff passed and `git diff --check` was clean;
- Cargo format passed; Rust workspace: `52 passed`;
- three bounded review/fix loops closed document, drift, packaging, checksum,
  ref-race, path, shallow-history, and fault-injection findings.

Claim boundary:

- The audit packet is externally reviewable source/history evidence, not
  scientific validation or independent reproduction.
- The executable probe confirms a critical baseline defect: generated routes
  do not produce turn demand, so the integrated runtime is not self-driving.
- The audit blocks PR52 acceleration selection until generated multi-hop
  movement, conservation, full-state replay, and runtime authority closure pass.
- No root license exists; archive integrity is not a redistribution grant.

Packet source:
`docs/audit/metroflow_external_audit_20260711/README.md`.

Delivery packaging command, to be run only after committing this packet:

```bash
.venv/bin/python tools/build_external_audit_bundle.py --output-dir dist
```

## 2026-07-12: Runtime Closure Remediation

Change class: Python/NumPy functional baseline correction, generated turn
authority, exact agent/queue flow commit, explicit tick units, and historical
audit supplement

Commands run during remediation:

```bash
.venv/bin/python -m metroflow.benchmarks.runtime_self_drive_probe \
  --scenario-seed 41 --steps 20 --expect-closed
.venv/bin/python -m pytest \
  tests/test_flow_units.py \
  tests/test_runtime_flow_closure.py \
  tests/test_runtime_replay_closure.py \
  tests/test_runtime_spine.py -q \
  -k 'not test_runtime_reroute_passes_configured_routing_backend'
.venv/bin/python -m pytest tests/test_external_audit_package.py -q
.venv/bin/python -m pytest -q \
  --deselect tests/test_meso_core.py::test_evolve_edges_fast_tick_explicit_jax_backend_is_fail_closed \
  --deselect tests/test_replay.py::test_replay_boundary_and_result_record_edge_backend \
  --deselect tests/test_runtime_spine.py::test_runtime_reroute_passes_configured_routing_backend
.venv/bin/python -m ruff check .
git diff --check
```

Recorded bounded result:

- generated seed 41: 16 trips, 51,886 compiled turn rows, 45,544 permitted;
- 15 routable trips complete by tick 16; one no-route trip fails explicitly;
- tick 20 has zero active agents and zero queue vehicles;
- all 20 ticks pass runtime invariants with maximum per-link agent/queue delta
  `0.0`;
- focused flow/closure/replay/runtime suite: `53 passed, 1 skipped, 1 deselected`;
- external-audit package suite: `9 passed`;
- runtime closure replay suite: `9 passed`;
- dependency-neutral broad suite: `583 passed, 20 skipped, 3 deselected in
  193.44s`; the three explicit optional-integration tests then report `3
  skipped` after receiving dependency guards;
- Ruff and `git diff --check` pass.
- JAX and the built `_metroflow_rust` extension are absent in this container.
  Cargo is also unavailable, so the new Rust unit test was added but not
  executed here; Rust formatting/workspace results must be refreshed in a Rust
  toolchain environment before delivery.

Functional impact:

- generated routes now produce legal per-turn and sink demand before flow;
- realized integer tokens update the matching agents and queue mass atomically;
- source service and downstream receiving capacity share deterministic residual
  authorities, including merge contention;
- sink and internal-turn demand share deficit scheduling, receiving-token
  excess is an invariant failure, and a final-link endpoint must match the
  active-agent destination before completion;
- missing/non-finite runtime authority and non-integral vehicle tokens fail
  closed both in invariant validation and before a subsequent flow overwrite;
- free-flow time is stored in configured tick units and point-queue delay is
  `t_ff + queue/capacity`;
- unsupported explicit Rust per-turn agent/flow paths fail closed; `auto`
  preserves the Python baseline fallback.
- canonical replay fingerprints full config, static routing authority, and all
  replay-authoritative dynamic state; two fresh seed-41 20-tick runs have equal
  final-state fingerprints and stale residual boundaries fail before execution.

Claim boundary:

- This closes the audit's historical self-drive defect only at
  `INTERNALLY VERIFIED` small-probe scope.
- It does not validate 100k operation, physical link traversal, finite storage
  or spillback, named-city behavior, empirical traffic, or the split LUTI loop.
- The 2026-07-11 packet remains historical evidence. Later ZIPs must include
  `10_RUNTIME_CLOSURE_REMEDIATION_20260712.md` and identify their own committed
  `packaged_commit`; no root redistribution license has been added.

## 2026-07-12: Pulled Proposal Acceptance And Adversarial Validation

Change class: external proposal review, corrective runtime/flow/replay/JAX
patches, multi-seed/scale experiments, and claim-boundary refresh

Reviewed commits:

- proposal: `46f0fd7abcc484a2f52db16bf17bf0b4d64a6300`;
- corrective commits: `44d1145`, `505bb11`, `e30af45`, `368e719`, `eb042bc`.

Core commands run:

```bash
.venv/bin/python -m maturin develop \
  --manifest-path crates/metroflow-rust/Cargo.toml
cargo fmt --all --check
CARGO_TARGET_DIR=/tmp/metroflow-cargo-target cargo test --workspace
.venv/bin/python -m pytest \
  tests/test_active_agent_rust_backend.py \
  tests/test_flow_engine_rust_backend.py \
  tests/test_routing_rust_backend.py -q
.venv/bin/python -m metroflow.benchmarks.runtime_self_drive_probe \
  --scenario-seed 41 --steps 20 --expect-closed
XLA_PYTHON_CLIENT_MEM_FRACTION=0.70 \
  .venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
```

Final gates:

- full Python/JAX-enabled suite: `623 passed in 198.69s`;
- Rust workspace: `53 passed`;
- installed-extension Rust parity: `35 passed`;
- Ruff, Cargo format, and `git diff --check`: passed;
- JAX 0.10.2 reports `cuda:0` on the RTX 3080 Ti.

Adversarial findings corrected:

- independently rounded fractional service/receiving tokens could phase-starve
  a valid turn; bounded one-token carry restores four expected movements over
  the 10-tick `0.6/0.4` probe;
- residual `1.0`, negative turn indices, and NaN/Inf tick units now fail closed;
- route destination and plugin-memory trip identity are validated before first
  movement; incident activation and clearance both invalidate routing;
- static legal turn-pair lookup is reused instead of rebuilding 51,886 rows
  twice per tick;
- replay boundary binds ordered controls, actual RNG key, and step count;
  replay snapshots detach input aliases and transition witnesses reconcile
  flow-input queue, realized flow, output queue, and sink completion;
- NaN queue/progress values and structured-dtype digest collisions are rejected;
- JAX dense flow now uses the same point-queue receiving and additive-delay
  equations as NumPy/Rust;
- same-tick reroute destination potentials and identical link/destination
  selections are shared without changing per-agent policy decisions.

Measured experiments:

- ten seeds x 64 ticks: 158 trips, 148 completed, 10 classified no-route,
  146 multi-hop completions, all runs closed, all invariants passed, maximum
  observed link-agent mass delta `0.0`;
- population 1,000: 147 trips close at tick 19 in 0.695 local seconds;
- population 10,000: 3,105 trips close at tick 156; same-tick reroute caching
  reduces local runtime from 77.068 s to 16.022 s with unchanged terminal counts;
- population 100,000: 31,069 trips initialize, but the 240 s bounded post-fix
  run reaches only tick 128 (20,280 complete, 163 no-route, 10,626 active);
  observed invariants and queue/agent mass remain exact, but closure is not
  validated;
- 16,384-link/32,768-turn/16-step JAX: maximum NumPy drift `1.43e-5`, steady
  chunk 1.20 ms, compile/copy-inclusive first probe about 67.6 ms versus NumPy
  12.50 ms. This is an amortization candidate, not runtime promotion evidence.

Artifact:
`artifacts/runtime_spine_review/external-proposal-validation-20260712.md`.

Claim boundary:

- corrected functional closure is internally verified at multi-seed and 10k
  synthetic scope;
- 100k closure/throughput, physical traversal, spillback, real-city validity,
  LUTI integration, and independent reproduction remain unvalidated;
- Python/NumPy remains authoritative; Rust/JAX remain optional; no NN/custom
  CUDA/runtime-backend promotion follows from these diagnostics.

## 2026-07-13: PR63 Realistic City Scale And Hardware-Fit Gate

Change class: fresh-process diagnostic benchmark and promotion gate

Canonical command:

```bash
/usr/bin/time -f 'elapsed=%e max_rss_kib=%M' \
  .venv/bin/python -m metroflow.benchmarks.realistic_city_scale \
  --artifact-prefix \
  artifacts/runtime_spine_review/realistic-city-pr63-scale
```

Evidence:

- `18` city-authority runs, `18` fixed 20-tick runs, `3` realistic stage
  profiles, and `6` paired-budget runs;
- populations `1,000`, `10,000`, and `100,000`; seeds `17,29,41`;
- total elapsed `894.31 s`; parent maximum RSS `229,980 KiB`;
- report fingerprint
  `149571c18552e5cc655a0c33844fe487a7b6165cea808b1c55a3b47655f5278e`;
- performance gate failed, default promotion false, Rust generation probe false;
- artifact bundle:
  `artifacts/runtime_spine_review/realistic-city-pr63-scale.{json,md,html}`
  and `.manifest.json`.

Claim boundary: local host diagnostic only. It establishes neither empirical
city realism nor calibrated traffic. PR62 remains the independent morphology
gate, and no timing result can override it.

## 2026-07-13: PR64 Default Promotion Closure

Command:

```bash
.venv/bin/python -m pytest \
  tests/test_realistic_city_default_promotion.py -q
```

Result: canonical PR62 and PR63 fingerprints reload, both gates remain false,
the default remains `standard`, and the machine decision records `BLOCKED`.
No runtime or generator feature code is added. Final repository gate:
`778 passed in 590.18s`; Ruff and diff checks pass.

## 2026-08-09: G0 Map-Evidence Recovery

Change class: integrity-boundary repair and deterministic evidence tooling;
no city/runtime generator change

Protected inputs were inspected read-only and were not repacked, resealed, or
placed on `sys.path`:

```bash
sha256sum \
  MetroFlow_map_generation_reaudit_2026-08-08.zip \
  MetroFlow_CAPR_research_2026-08-08.zip \
  MetroFlow_CAPR_research_2026-08-08.bundle
unzip -t MetroFlow_map_generation_reaudit_2026-08-08.zip
unzip -t MetroFlow_CAPR_research_2026-08-08.zip
zipinfo -1 MetroFlow_map_generation_reaudit_2026-08-08.zip | wc -l
zipinfo -1 MetroFlow_CAPR_research_2026-08-08.zip | wc -l
git bundle verify MetroFlow_CAPR_research_2026-08-08.bundle
```

Input receipts:

- map re-audit ZIP: 241,084 bytes, SHA-256
  `9b566eed6a8ee077c1f6b77d87aaacd0c37b0d23d47534658c6bc681f87a9c4c`,
  147 archive members, CRC clean;
- CAPR ZIP: 590,250 bytes, SHA-256
  `fc2559589a246d239bf19cdfc584cea18c513f5cd9ef37761d73e35770831393`,
  169 archive members, CRC clean;
- CAPR bundle: 349,682 bytes, SHA-256
  `0adb0de9e66916722c6f170dab5a21da325397a041caa6baeb1ce889b4229626`,
  bundle verification clean at producer HEAD
  `bc879f8323d4bcf4bc76883641b570f464ae38c9`.

The map ZIP contains 145 true non-integrity payloads. `SHA256SUMS.txt` has 146
valid rows (145 payloads plus `FILE_MANIFEST.json`). `FILE_MANIFEST.json` also
has 146 rows (145 payloads plus `SHA256SUMS.txt`), with exactly one disagreement:
the checksum member is declared as 16,240 bytes / SHA-256
`173e6922a87520cc33816c4b8e0055dc74423211586ccecfeca249e68c47ed72`
but is actually 16,327 bytes / SHA-256
`d14931aca032539f8809435d7bc3702053b1fa2ec688c0cbf0560c3cdffa0879`.
Verdict: payload integrity holds; package integrity is `PARTIAL` because the
wrappers are cyclic.

The CAPR `CONTENT_MANIFEST.json` declares 167 payloads and excludes itself plus
`PACKAGE_METADATA.json`. All 167 payload sizes and SHA-256 values match both the
ZIP and bundle producer tree. Exact CAPR ZIP reconstruction remains open because
the bundle lacks package metadata, the packaging command/contract, and an
external ZIP digest.

S0 row-derived diagnostic means are p=.20 degree `4.56823`, dead-end share
`0.02930`; p=.35 degree `3.88152`, dead-end share `0.11234`. Its implementation
status is `IMPLEMENTED_DIAGNOSTIC`; historical byte replay remains
`NOT_REPRODUCIBLY_CLOSED`. Audited base
`3c6a5c794ca5e06878ecb50eb935435208b8f2be` and producer/receipt
`516a71293ef8ee9f9795a7c818500f47ddcaa426` are recorded separately.

G0 tooling now has a payload-only manifest and an external detached digest. Its
verifier applies the semantic claim firewall to archived payloads, excludes
integrity-wrapper case/path variants, and publication is strict no-clobber for
all existing targets plus the three protected historical basenames. A failed
new publication removes both ZIP and sidecar. The null-control v2 runner binds
the verified checkout/import origins and actual Python/NumPy versions, accepts
only the exact typed 6 x 5 x 5 matrix, records the audited base as the historical
commit, and repeats the repository/source check after collection.

A bundle call's two serializations share one in-memory member set and therefore
record only `IN_PROCESS_SERIALIZATION_MATCH_ONLY`. No cross-build status is
embedded. Promotion is confined to a separate replay receipt that compares ZIP
and sidecar bytes supplied from two independent clean checkout/process runs.
No such canonical v2 bundle or replay receipt was emitted in this dirty,
uncommitted session. The final G0 gate remains blocked until a clean immutable
producer commit and canonical environment lock exist and the independent runs
match.

Focused implementation evidence:

```bash
.venv/bin/python -m pytest \
  tests/test_map_evidence_bundle.py tests/test_null_operator_control.py -q
.venv/bin/python -m pytest tests/test_external_audit_package.py -q
.venv/bin/python -m ruff check \
  tools/build_map_evidence_bundle.py \
  tools/run_null_operator_control.py \
  tests/test_map_evidence_bundle.py \
  tests/test_null_operator_control.py
```

- bundle/null-control contracts plus live control:
  `61 passed, 1 xfailed in 91.19s`;
- existing external-audit package regression: `9 passed in 2.71s`;
- focused Ruff gate: passed.

Fix-round REDs were observed before the matching implementation: the fully
resealed promoted payload was accepted; `SHA256SUMS.txt` case/path variants and
existing/protected outputs were accepted or overwritten; the manifest claimed
`CANONICAL_BYTES_VERIFIED`; arbitrary/coerced matrix identifiers and an extra
fraction row were accepted; provenance from one repository could precede
measurement imports from another; runtime-lock mismatch and post-collection
drift did not stop publication. Each branch now has a direct production-symbol
test. The overlapping exploratory timing run was discarded and is not evidence.

A direct builder attempt against the current repository HEAD exited `1` with
`RuntimeError: working tree must be clean before evidence snapshot`; its scratch
directory contained only captured stdout/stderr and no ZIP or sidecar. This is
the expected G0 blocker, not a failed artifact that may be resealed.
