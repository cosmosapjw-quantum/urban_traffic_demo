# City Map Re-Architecture PR List

Status: active
Last updated: 2026-07-13

## Execution Contract

- Python 3.12 and NumPy remain the deterministic authority.
- `RoadNetworkCSR` remains the runtime topology authority.
- Road sections enrich static geometry and compile aggregate link properties;
  they do not introduce lane-level microscopic state.
- Static PNG/HTML outputs are diagnostic artifacts, not validation evidence.
- Every PR runs `/review-spec`, `/review-code`, and `/review-drift`; at most
  three finding/fix loops are allowed.
- At most three subagents may be active. Each must be closed immediately after
  its result is consumed. Controller closeout must confirm zero open agents.
- GPL source copying and runtime dependency on external donor folders are
  forbidden without a separate licensing decision.

## PR33 - Source Provenance Boundary

Status: complete.

- Record permitted concepts, excluded upstream surfaces, and license stop gate.
- Correct the claim that CSUR is a city-layout or node-connector generator.
- Runtime behavior must not change.
- Validation: `6 passed` targeted; full repository gate `351 passed`; Ruff and
  `git diff --check` passed after the separately committed routing-cache fix.
- Commit: `docs(map): define source provenance boundary`.

## PR34 - Typed Road Geometry Contract

Status: complete.

- Add typed centerlines, link-to-geometry assignments, and deterministic
  geometry fingerprints.
- Preserve endpoint-only topology behavior as the default adapter.
- Validation: `10 passed` targeted; full gate `361 passed`; Ruff and diff check
  passed.
- Commit: `feat(map): add typed road geometry contract`.

## PR35 - Centerline Topology Compiler

Status: complete.

- Compile generated links into canonical physical centerlines.
- Add deterministic endpoint anchoring validation and a diagnostic interior
  intersection audit. PR40 owns the fail-closed planar-intersection gate after
  node compilation; PR35 does not promote this diagnostic to validation.
- Migrate legacy `csur_module_*` diagnostic keys to project-owned
  `road_hierarchy_module_*` names with documented artifact impact.
- Expose `sidecar_local_fabric` through an explicit city-generation config,
  but keep the current standard mode as default until gates pass.
- Validation: `34 passed` focused review suite; full gate `372 passed`; Ruff
  and diff check passed.
- Commit: `feat(map): compile generated centerlines`.

## PR36 - Road Section Grammar

Status: complete.

- Replace placeholder lane grammar with project-authored unit, section-end,
  and base/shift/transition/ramp contracts.
- Enforce directional one-lane deltas and ordered unit continuity: transition
  permits one lane edit; ramp permits one adjacent lane+channel edit.
- Reject coercive numeric/boolean inputs and separate structural from identity
  profile fingerprints.
- Add canonical profile fingerprints and fail-closed validation.
- Validation: `25 passed` focused review suite; full gate `388 passed`; Ruff
  and diff check passed.
- Commit: `feat(map): add road section grammar`.

## PR37 - Section And Node Compiler

Status: complete.

- Assign profiles from road hierarchy and compile aggregate lanes/capacity.
- Compile node through continuity, turn-pocket eligibility, non-through movement count,
  and signal eligibility without lane-level simulation.
- Validation: `7 passed` targeted; public records reject coercive inputs and
  preserve deep immutability; full repository, Ruff, and diff gates passed.
- Commit: `feat(map): compile sections and nodes`.

## PR38 - Static Ribbon Renderer

Status: complete.

- Render centerline polylines as width-aware road ribbons with optional median,
  shoulder, ramp, repair-link, and bridge layers.
- Add roads-only, zones-only, and POIs-only diagnostic outputs.
- Validation: `11 passed` targeted; uniform meter projection, rendered-catalog
  provenance, layer availability, legacy fallback, and component focus covered;
  visual audit remains diagnostic only.
- Commit: `feat(ui): render typed road geometry`.

## PR39 - OSM Reference Import

Status: complete.

- Add offline normalized OSM XML import as optional development tooling.
- Project, clip, split shared-node intersections, simplify, and classify ways.
- Runtime must not fetch network data or require OSM dependencies.
- Validation: `12 passed` targeted; source identity, lane semantics, closed
  roundabouts, implicit motorway direction, antimeridian projection, exact
  input provenance, and fresh-process import firewall covered.
- Commit: `feat(map): add offline osm centerlines`.

## PR40 - Validation Closure

Status: complete.

- Gate deterministic fingerprints, weak connectivity, intersection validity,
  random OD reachability, section continuity, and replay compatibility.
- Regenerate diagnostic map artifacts and record remaining visual limitations.
- Admission: explicit `sidecar_local_fabric_planar` only. Default promotion was
  rejected after a material suite-time regression and route-ID breakage.
- Validation: full repository `426 passed`; focused closure/planar/geometry
  `23 passed`; Ruff and diff checks passed; final PNG bundle visually audited.
- Commit: `test(map): close city map validation gates`.

## Hardware-Fit Boundary

- Keep orchestration and contracts in Python.
- Keep baseline geometry arrays and field calculations in NumPy.
- Consider Rust only after spatial splitting, planarization, or graph-search
  stages are measured as material CPU/control-flow costs.
- Consider JAX/GPU only for measured dense morphology-field or batched scoring
  work, with compile and steady-state timing separated.
- Do not add C++/CUDA, PyTorch, or new runtime backend names in this roadmap.

## PR41 - Urban Morphology Diversity

Status: complete.

- Add reference-only empirical city metrics from peer-reviewed OSM analysis.
- Add physical-centerline orientation, circuity, grain, and connectivity metrics.
- Make existing style IDs select distinct grid, multi-grid, polycentric,
  corridor-constrained, organic, and legacy radial grammars.
- Preserve scenario-resolved `auto` defaults and explicit planar acceptance.
- Generate a six-style comparison atlas and record limitations without city
  replication claims.
- Validation: `13 passed` feature tests; full repository `439 passed`; Ruff and
  diff checks passed; PNG contact sheet visually audited.

## PR42 - Block Continuity And Density Envelope

Status: complete.

- Measure occupied-area street density, block continuity, connector/local
  length ratio, intersection-type mix, and district quadrant presence across
  seeds.
- Reduce excess four-way share in polycentric/mixed styles and excess dead ends
  in corridor styles without fitting named cities.
- Three-seed evidence: polycentric four-way median `0.656 -> 0.603`, mixed
  `0.630 -> 0.587`; river dead-end median `0.324 -> 0.119` and block
  continuity `0.637 -> 0.882`.
- The v1 gate is intentionally scoped to connectivity, density, and
  intersection mix. It does not validate continuous citywide fabric.
- Validation: targeted morphology/static suite `49 passed`; full repository
  `472 passed`; Ruff and diff checks passed; independent finding/fix re-review
  closed all reported issues.

## PR43 - Continuous Fabric Coverage

Status: complete.

- Add a deterministic global spatial-coverage measure that can distinguish
  continuous street fabric from dense but isolated district patches.
- Replace long bare inter-district connectors with style-aware corridor infill
  or a continuous global lattice where the morphology calls for it.
- Preserve style diversity, planar/OD gates, and project-owned broad
  thresholds; do not fit named cities.
- Defer morphology-aware zone/POI placement until this gate passes.
- Pre-change local cell-presence medians ranged from `0.152` to `0.342` for
  non-grid local fabrics; the synthetic continuous lattice scores `0.498` and
  the comparable-length precinct-island fixture is materially lower.
- Gate v2 adds a project-owned `0.40` minimum after style-aware infill while
  retaining all PR42 thresholds.
- A visual-review counterexample showed that long lines can game cell
  presence, so v2 also requires `0.40` local-junction proximity on a 12 by 12
  raster with a `0.5` cell-diagonal radius.
- Three-seed local-presence medians improved: ring `0.172 -> 0.618`, grid
  `0.309 -> 0.759`, polycentric `0.338 -> 0.483`, river `0.342 -> 0.625`,
  mixed `0.267 -> 0.615`, organic `0.152 -> 0.491`.
- Validation: focused city suite `67 passed`; full repository `479 passed`;
  Ruff and diff checks passed; independent finding/fix re-review closed all
  four findings.

## PR44 - Morphology-Gated Zone And POI Coupling

Status: complete; legacy remains the default and morphology placement remains
fail-closed behind the recomputed v2 gate.

- Keep legacy placement as the default and deterministic fallback.
- Admit morphology-aware placement only from a versioned accepted gate.
- Use synthetic district/subcenter context, never empirical named-city fitting
  or external runtime data.

## Realistic Synthetic City Queue

The controlling product contract is
`docs/PRD_REALISTIC_SYNTHETIC_CITY.md`. PR53-PR64 replace further schematic
sidecar refinement with a terrain-to-block-to-runtime pipeline. Existing
PR33-PR45 evidence remains the compatibility and negative-control baseline.

- **PR53 - Product Contract Freeze:** complete; froze thresholds, public
  contracts, claim boundary, and ordered queue. Commit:
  `docs(city): define realistic synthetic city target`.
- **PR54 - Generator Boundary Extraction:** complete; preserved current fingerprints while
  isolating compatibility, typed stage, and finalization boundaries. Commit:
  `refactor(city): isolate generation stage contracts`.
- **PR55 - Terrain And Development Fields:** complete; bounded read-only NumPy fields and
  deterministic centers. Commit: `feat(city): add terrain and development fields`.
- **PR56 - Hierarchical Street Skeleton:** complete; terrain-aware gateways, arterial
  connectivity, and bounded redundancy. Commit:
  `feat(city): generate hierarchical street skeleton`.
- **PR57 - Continuous Local Fabric:** complete; orientation-field local growth and
  collector coupling. Commit: `feat(city): grow continuous local street fabric`.
- **PR58 - Planar Block Compiler:** complete; same-layer T-junction splitting,
  proper-crossing planarization, short-fragment contraction, simple bounded-face
  extraction, and source-street frontage gates pass the 6-style by 4-seed
  matrix. Validation: targeted `29 passed`; full repository `691 passed`;
  Ruff and diff checks passed. Commit:
  `feat(city): compile planar urban blocks`.
- **PR59 - Block Land Use And POIs:** complete; immutable block assignments use
  terrain, center proximity, slope, and road hierarchy; explicit per-hectare
  capacities, frontage access nodes, industrial buffers, and essential POIs
  pass the 6-style by 4-seed matrix. Validation: targeted `27 passed`; full
  repository `718 passed`; Ruff and diff checks passed. Commit:
  `feat(city): couple land use to urban blocks`.
- **PR60 - Simulation Map Compiler:** complete; explicit paired config,
  composed blueprint, no-repair topology/CSR/zoning compiler, 512 sampled OD
  gate, replay fingerprints, runtime initialization, and polygon static-map
  payload pass the 6-style by 4-seed matrix. Validation: targeted `32 passed`;
  related integration `99 passed`; full repository `747 passed`; Ruff and diff
  checks passed. Commit:
  `feat(city): compile realistic map runtime authority`.
- **PR61 - Physical Link Traversal:** complete; preserved the default point
  queue while adding explicit NumPy length/speed residency, finite lane-length
  storage, exit-ready demand, source/downstream spillback, replay/UI/benchmark
  provenance, and finite-storage invariants. Validation: targeted `12 passed`;
  related runtime/UI/backend `135 passed`; full repository `759 passed`; fresh
  import firewall, Ruff, and diff checks passed. Commit:
  `feat(sim): add physical link traversal`.
- **PR62 - Empirical Plausibility Audit:** six styles by five seeds against the
  pinned aggregate envelope. Commit:
  `test(city): audit synthetic city plausibility`.
- **PR63 - Scale And Hardware-Fit Closure:** 1k/10k/100k generation and runtime
  evidence before any Rust generation core is opened. Commit:
  `perf(city): close realistic map scale gate`.
- **PR64 - Default Promotion:** conditional; promote only if every frozen gate
  passes, otherwise record `BLOCKED` without changing the default. Commit when
  admitted: `feat(city): promote realistic generator default`.
