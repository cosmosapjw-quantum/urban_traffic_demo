# Project State

Last updated: 2026-07-10

## Runtime Baseline

Facts:

- Host baseline is Python 3.12 on Ubuntu 24.04.
- Default runtime authority is Python/NumPy deterministic baseline.
- Rust CPU backend is optional and explicit/fail-closed.
- JAX CUDA 13 remains optional for RTX 3080 Ti 12GB experiments.
- Whole-code hardware-fit atlas is the current step-back artifact for choosing
  Rust CPU, NumPy/SIMD, JAX/GPU, NN surrogate, or keep-Python lanes.
- `docs/PRD_ACCELERATED_RUNTIME.md` and
  `docs/harness/ACCELERATION_PR_LIST.md` are the active long-term roadmap for
  spec-driven/subagent-driven acceleration work.
- PR01 (`31064c5`), PR02 (`b434258`), PR03 (`e292685`), PR04 (`a80b369`),
  PR05 (`987cdbc`), PR06 (`c2c052f`), and PR07 (`b636b2a`) are complete.
- PR08 (`29daebe`) is complete.
- PR09 (`52e7aec`) and PR10 (`04554ca`) are complete.
- PR11 (`55af343`) and PR12 are complete. The acceleration roadmap state is
  consolidated without authorizing C++/CUDA, libtorch, CMake, Rayon, zero-copy
  NumPy FFI, or new runtime backend values.

## Acceleration Evidence

Canonical evidence artifact:

- `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`

Do not copy benchmark tables into other docs unless the values are needed for a
specific decision. Link to the canonical evidence artifact instead.

## Current Accepted Direction

Derived conclusions:

- `active_agent_pool_write` was reduced below the review gate by batching
  plugin-memory replacement.
- `active_agent_pool_array_write` remains below the review gate and should stay
  a watchlist item.
- `active_agent_candidate_selection` is not currently the hot path.
- Route candidate refresh is now the dominant review-ready parent stage.
- `route_candidate_potential` and `dynamic_potential_recompute` are the current
  review-ready route substages after fixing baseline Dijkstra `float32`
  heap-staleness.
- `route_candidate_path_build` is no longer review-ready after the baseline
  correctness fix.
- Explicit whole-runtime `routing_backend="rust_cpu"` is slower than baseline
  for the 1-seed/1-step eager suite even with a release Rust extension
  (`26.70s` versus baseline `8.02s`), because cost moves into Rust
  path-build/metadata copy-boundary work.
- Keep Rust routing work narrow: potential-only/cache amortization first,
  path-build/metadata later only if their release-profile evidence improves.
- NN/JAX remains a watchlist for cost-to-go surrogate labels or dense scoring,
  not the next route-legality authority.

## Open Risks

- Smoke eager workloads may overrepresent activation/allocation cost.
- Nested timing shares overlap and must not be summed as exclusive wall-clock
  partitions.
- Repeated instrumentation can become a local-minimum trap if it no longer
  changes the next implementation decision.
- Static hardware-fit labels are not performance evidence unless linked to
  runtime stage timings or copy-inclusive microbench results.

## City Map State

- Typed physical centerlines, road sections, node interfaces, width-aware SVG
  ribbons, and offline no-network OSM XML import are implemented.
- `sidecar_local_fabric_planar` is an explicit fail-closed review mode with
  endpoint, intersection, section, sampled-OD, and replay gates.
- `standard` remains the runtime default. A planar default trial raised the full
  suite from about 48 seconds to 281 seconds and broke a route-ID regression.
- The final planar seed-44 image is topologically legal but still visually
  dominated by sparse hub clusters and long direct corridors. Morphology realism
  remains open and is not solved by further renderer or planarization work.
- PR42 adds a three-seed physical-network quality envelope and a versioned,
  narrowly scoped structural gate. Staggered streets reduce excess four-way
  intersections without cutting network continuity, and river return streets
  reduce corridor dead ends. The new visual audit still shows isolated precinct
  patches separated by bare inter-district links, so citywide continuity and
  morphology-aware land use remain open.
- PR43 adds global local-street cell presence and local-junction proximity,
  rejects a presence-only Goodhart failure, and supplies style-specific
  continuous infill. All explicit styles pass gate v2 across the deterministic
  matrix; integrated river audit leaves barrier crossings to bridge links.
  The maps remain schematic and are not named-city realism evidence.
- PR44 keeps legacy zone/POI placement as the default and exact fallback. The
  explicit morphology mode recomputes gate v2 against actual geometry, verifies
  bounded district/subcenter anchor provenance, preserves aggregate land-use
  contracts, and fingerprints the effective placement in runtime replay.
  Final gate: `493 passed`; Ruff and diff checks clean.
- Canonical diagnostic bundle:
  `artifacts/city_continuous_fabric_20260711/` and
  `artifacts/city_continuous_fabric_quality_20260711/`.

## Next Implementation Decision

Open a new spec only after refreshing the hardware-fit atlas or runtime
benchmark evidence that can change a parent-stage decision. The strongest
watchlist lanes remain dynamic-potential/cache work, dense flow scaling,
route-score batch probes, simulator-label-driven surrogate experiments, and
active-agent pool-array replacement only if it becomes review-ready again.
The next city-map slice is PR45, a diagnostic morphology accessibility audit.
It may add zone/POI overlays and multi-seed access/OD metrics, but it must not
change demand, route legality, or runtime defaults. PR46 demand coupling remains
conditional on a decision-changing PR45 defect. Renderer-only work and named-city
fit remain out of scope.
