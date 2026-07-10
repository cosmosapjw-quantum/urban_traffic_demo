# City Map Re-Architecture PR List

Status: active
Last updated: 2026-07-10

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

Status: pending.

- Add typed centerlines, link-to-geometry assignments, and deterministic
  geometry fingerprints.
- Preserve endpoint-only topology behavior as the default adapter.
- Commit: `feat(map): add typed road geometry contract`.

## PR35 - Centerline Topology Compiler

Status: pending.

- Compile generated links into canonical physical centerlines.
- Add deterministic endpoint snapping and intersection validation.
- Migrate legacy `csur_module_*` diagnostic keys to project-owned
  `road_hierarchy_module_*` names with documented artifact impact.
- Expose `sidecar_local_fabric` through an explicit city-generation config,
  but keep the current standard mode as default until gates pass.
- Commit: `feat(map): compile generated centerlines`.

## PR36 - Road Section Grammar

Status: pending.

- Replace placeholder lane grammar with project-authored unit, section-end,
  and base/shift/transition/ramp contracts.
- Add canonical profile fingerprints and fail-closed validation.
- Commit: `feat(map): add road section grammar`.

## PR37 - Section And Node Compiler

Status: pending.

- Assign profiles from road hierarchy and compile aggregate lanes/capacity.
- Compile node through continuity, turn-pocket eligibility, conflict groups,
  and signal eligibility without lane-level simulation.
- Commit: `feat(map): compile sections and nodes`.

## PR38 - Static Ribbon Renderer

Status: pending.

- Render centerline polylines as width-aware road ribbons with optional median,
  shoulder, ramp, repair-link, and bridge layers.
- Add roads-only, zones-only, and POIs-only diagnostic outputs.
- Commit: `feat(ui): render typed road geometry`.

## PR39 - OSM Reference Import

Status: pending.

- Add offline normalized OSM XML import as optional development tooling.
- Project, clip, split shared-node intersections, simplify, and classify ways.
- Runtime must not fetch network data or require OSM dependencies.
- Commit: `feat(map): add offline osm centerlines`.

## PR40 - Validation Closure

Status: pending.

- Gate deterministic fingerprints, weak connectivity, intersection validity,
  random OD reachability, section continuity, and replay compatibility.
- Regenerate diagnostic map artifacts and record remaining visual limitations.
- Commit: `test(map): close city map validation gates`.

## Hardware-Fit Boundary

- Keep orchestration and contracts in Python.
- Keep baseline geometry arrays and field calculations in NumPy.
- Consider Rust only after spatial splitting, planarization, or graph-search
  stages are measured as material CPU/control-flow costs.
- Consider JAX/GPU only for measured dense morphology-field or batched scoring
  work, with compile and steady-state timing separated.
- Do not add C++/CUDA, PyTorch, or new runtime backend names in this roadmap.
